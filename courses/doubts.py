"""Doubts hub: students ask, classmates learn from answered doubts, instructors work an answer queue."""
from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render

from accounts.forms import StyledMixin

from .models import Course, Doubt, DoubtReply, Enrollment, Lesson


def visible_doubts(user):
    qs = Doubt.objects.all()
    if user.is_owner or user.is_instructor:
        return qs
    if user.is_school_admin:
        return qs.filter(student__school_id=user.school_id)
    my_courses = Enrollment.objects.filter(student=user).values("course_id")
    return qs.filter(Q(student=user) | Q(is_private=False) & (Q(course__isnull=True) | Q(course_id__in=my_courses)))


def _course_choices(user):
    if user.is_student:
        return Course.objects.filter(enrollments__student=user, is_published=True)
    return Course.objects.all()


class AskForm(StyledMixin, forms.ModelForm):
    class Meta:
        model = Doubt
        fields = ["course", "lesson", "category", "title", "body", "image", "is_private"]
        labels = {"title": "Your question in one line", "body": "Explain your doubt",
                  "course": "Course", "lesson": "Lesson (optional)", "is_private": "Keep this private (only instructors can see it)"}
        help_texts = {"is_private": "", "course": ""}
        widgets = {"body": forms.Textarea(attrs={"rows": 6, "placeholder": "What were you trying to do? What happened instead? Paste code or error messages here."}),
                   "title": forms.TextInput(attrs={"placeholder": "e.g. My ultrasonic sensor always reads 0 cm", "autocomplete": "off"})}

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        courses = _course_choices(user)
        self.fields["course"].queryset = courses
        self.fields["course"].empty_label = "General robotics doubt (no course)"
        self.fields["lesson"].queryset = Lesson.objects.filter(course__in=courses).select_related("course")
        self.fields["lesson"].label_from_instance = lambda l: l.title

    def clean(self):
        d = super().clean()
        if d.get("lesson") and d.get("lesson").course_id != getattr(d.get("course"), "id", None):
            self.add_error("lesson", "That lesson is not part of the selected course.")
        return d


class ReplyForm(StyledMixin, forms.Form):
    body = forms.CharField(label="Your reply", widget=forms.Textarea(attrs={"rows": 3, "placeholder": "Write a reply…"}))
    image = forms.ImageField(required=False, label="Attach a photo")
    mark_resolved = forms.BooleanField(required=False, label="This solves the doubt – mark as resolved")


@login_required
def doubt_list(request):
    u = request.user
    base = visible_doubts(u).select_related("student", "course", "lesson").annotate(
        n_replies=Count("replies", distinct=True), n_metoo=Count("me_too", distinct=True))

    if u.is_student:
        tabs = [("mine", "My doubts", base.filter(student=u)),
                ("community", "Community", base.exclude(student=u).filter(has_staff_reply=True))]
    else:
        tabs = [("queue", "Needs an answer", base.filter(is_resolved=False, has_staff_reply=False)),
                ("answered", "Answered", base.filter(is_resolved=False, has_staff_reply=True)),
                ("resolved", "Resolved", base.filter(is_resolved=True)),
                ("all", "All", base)]
    tab = request.GET.get("tab") or tabs[0][0]
    qs = dict((k, q) for k, _, q in tabs).get(tab, tabs[0][2])

    q, course, cat = request.GET.get("q", "").strip(), request.GET.get("course", ""), request.GET.get("cat", "")
    if q:
        qs = qs.filter(Q(title__icontains=q) | Q(body__icontains=q))
    if course == "general":
        qs = qs.filter(course__isnull=True)
    elif course.isdigit():
        qs = qs.filter(course_id=course)
    if cat:
        qs = qs.filter(category=cat)
    if u.is_instructor and request.GET.get("mine"):
        qs = qs.filter(Q(course__instructors=u) | Q(course__created_by=u) | Q(course__isnull=True)).distinct()
    qs = qs.order_by("-n_metoo", "created_at") if tab == "queue" else qs.order_by("is_resolved", "-updated_at")

    return render(request, "courses/doubt_list.html", {
        "page": Paginator(qs, 20).get_page(request.GET.get("page")),
        "tabs": [(k, label, query.count()) for k, label, query in tabs], "tab": tab,
        "courses": _course_choices(u).only("id", "title"), "categories": Doubt.Category.choices,
        "f": {"q": q, "course": course, "cat": cat, "mine": request.GET.get("mine", "")},
    })


@login_required
def doubt_ask(request):
    if not request.user.is_student:
        messages.info(request, "Only students can ask doubts. Answer them from the queue here.")
        return redirect("doubt_list")
    initial = {k: request.GET.get(k) for k in ("course", "lesson") if request.GET.get(k)}
    form = AskForm(request.POST or None, request.FILES or None, user=request.user, initial=initial)
    if request.method == "POST" and form.is_valid():
        d = form.save(commit=False)
        d.student = request.user
        d.save()
        messages.success(request, "Doubt posted! An instructor will answer soon – you'll see it under My doubts.")
        return redirect("doubt_detail", pk=d.pk)
    categories = [(v, label, Doubt.CATEGORY_ICONS[v]) for v, label in Doubt.Category.choices]
    return render(request, "courses/doubt_ask.html", {"form": form, "categories": categories,
                                                      "lessons": form.fields["lesson"].queryset})


def doubt_create(request, slug):
    """Old per-course URL – forwards to the ask page with the course pre-selected."""
    course = get_object_or_404(Course, slug=slug)
    url = f"/doubts/ask/?course={course.pk}"
    if request.GET.get("lesson"):
        url += f"&lesson={request.GET['lesson']}"
    return redirect(url)


@login_required
def doubt_similar(request):
    """Small JSON search so students see already-answered doubts while typing a new one."""
    words = [w for w in request.GET.get("q", "").split() if len(w) > 3][:5]
    if not words:
        return JsonResponse({"results": []})
    cond = Q()
    for w in words:
        cond |= Q(title__icontains=w)
    qs = visible_doubts(request.user).filter(cond, has_staff_reply=True).values("pk", "title")[:5]
    return JsonResponse({"results": list(qs)})


@login_required
def doubt_detail(request, pk):
    u = request.user
    d = get_object_or_404(visible_doubts(u).select_related("student", "student__school", "course", "lesson"), pk=pk)
    is_owner = d.student_id == u.id
    can_reply = is_owner or u.is_staff_member
    can_moderate = is_owner or u.is_staff_member
    form = ReplyForm()

    if request.method == "POST":
        action = request.POST.get("action", "reply")
        if action == "reply" and can_reply:
            form = ReplyForm(request.POST, request.FILES)
            if form.is_valid():
                DoubtReply.objects.create(doubt=d, author=u, body=form.cleaned_data["body"],
                                          image=form.cleaned_data["image"] or "")
                if u.is_staff_member:
                    d.has_staff_reply = True
                if form.cleaned_data["mark_resolved"]:
                    d.is_resolved = True
                elif is_owner and d.is_resolved:
                    d.is_resolved = False  # student follow-up reopens the doubt
                d.save()
                return redirect(f"{request.path}#latest")
        elif action == "metoo" and u.is_student and not is_owner:
            if d.me_too.filter(pk=u.pk).exists():
                d.me_too.remove(u)
            else:
                d.me_too.add(u)
            return redirect("doubt_detail", pk=pk)
        elif action == "accept" and can_moderate:
            reply_id = request.POST.get("reply", "")
            if not reply_id.isdigit():
                return redirect("doubt_detail", pk=pk)
            reply = get_object_or_404(DoubtReply, pk=reply_id, doubt=d)
            d.replies.update(is_accepted=False)
            reply.is_accepted = True
            reply.save(update_fields=["is_accepted"])
            d.is_resolved = True
            d.save()
            messages.success(request, "Marked as the best answer. Doubt resolved!")
            return redirect("doubt_detail", pk=pk)
        elif action in ("resolve", "reopen") and can_moderate:
            d.is_resolved = action == "resolve"
            d.save()
            return redirect("doubt_detail", pk=pk)
        elif action == "delete" and (u.is_staff_member or (is_owner and not d.replies.exists())):
            d.delete()
            messages.success(request, "Doubt deleted.")
            return redirect("doubt_list")
        elif action != "reply":
            raise PermissionDenied

    replies = d.replies.select_related("author")
    related = []
    if d.course_id:
        related = visible_doubts(u).filter(course_id=d.course_id, has_staff_reply=True).exclude(pk=d.pk).only("pk", "title")[:5]
    return render(request, "courses/doubt_detail.html", {
        "d": d, "replies": replies, "form": form, "can_reply": can_reply, "can_moderate": can_moderate,
        "is_owner": is_owner, "metoo_count": d.me_too.count(), "i_metoo": d.me_too.filter(pk=u.pk).exists(),
        "related": related,
    })
