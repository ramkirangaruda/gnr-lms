from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from accounts.forms import StyledMixin
from accounts.models import School, User
from accounts.permissions import staff_required, visible_students
from courses.models import Certificate, Course, Doubt, Enrollment, QuizAttempt
from courses.doubts import visible_doubts
from courses.views import student_course_stats

from .models import Competition, GalleryItem, Newsletter


class NewsletterForm(StyledMixin, forms.ModelForm):
    class Meta:
        model = Newsletter
        fields = ["title", "summary", "body", "cover", "pdf", "published_on", "is_published"]
        widgets = {"body": forms.Textarea(attrs={"rows": 10}), "published_on": forms.DateInput(attrs={"type": "date"})}


class GalleryForm(StyledMixin, forms.ModelForm):
    class Meta:
        model = GalleryItem
        fields = ["title", "event", "caption", "image"]


class CompetitionForm(StyledMixin, forms.ModelForm):
    class Meta:
        model = Competition
        fields = ["title", "description", "banner", "event_date", "registration_deadline", "venue", "eligibility",
                  "prizes", "registration_link", "results", "is_published"]
        widgets = {"description": forms.Textarea(attrs={"rows": 5}), "prizes": forms.Textarea(attrs={"rows": 3}),
                   "results": forms.Textarea(attrs={"rows": 3}),
                   "event_date": forms.DateInput(attrs={"type": "date"}),
                   "registration_deadline": forms.DateInput(attrs={"type": "date"})}


def home(request):
    today = timezone.localdate()
    return render(request, "portal/home.html", {
        "newsletters": Newsletter.objects.filter(is_published=True)[:3],
        "competitions": Competition.objects.filter(is_published=True, event_date__gte=today).order_by("event_date")[:3],
        "gallery": GalleryItem.objects.all()[:8],
        "features": [
            ("bi-play-btn", "Video lessons", "Step-by-step builds you can pause, replay and learn at your own pace."),
            ("bi-ui-checks", "Quizzes", "Instant results with answer review so you know exactly what to revise."),
            ("bi-chat-dots", "Doubt clarification", "Stuck on a circuit or code? Ask with a photo and get answers from instructors."),
            ("bi-award", "Certificates", "Earn verifiable certificates for every course and competition."),
        ],
        "stats": {"students": User.objects.filter(role=User.Role.STUDENT).count(),
                  "schools": School.objects.filter(is_active=True).count(),
                  "courses": Course.objects.filter(is_published=True).count()},
    })


@login_required
def dashboard(request):
    u = request.user
    today = timezone.localdate()
    ctx = {
        "newsletters": Newsletter.objects.filter(is_published=True)[:3],
        "competitions": Competition.objects.filter(is_published=True, event_date__gte=today).order_by("event_date")[:3],
    }
    if u.is_student:
        courses = [e.course for e in u.enrollments.select_related("course").filter(course__is_published=True)]
        ctx.update(stats=student_course_stats(u, courses),
                   attempts=u.quiz_attempts.select_related("quiz", "quiz__course")[:5],
                   certificates=u.certificates.select_related("course")[:5],
                   open_doubts=u.doubts.filter(is_resolved=False).count(),
                   answered_doubts=u.doubts.filter(is_resolved=False, has_staff_reply=True).count())
        return render(request, "portal/dash_student.html", ctx)

    students = visible_students(u)
    doubts = visible_doubts(u).filter(is_resolved=False, has_staff_reply=False)
    if u.is_instructor:
        my_courses = Course.objects.filter(Q(instructors=u) | Q(created_by=u)).distinct()
    elif u.is_school_admin:
        my_courses = Course.objects.filter(enrollments__student__school_id=u.school_id).distinct()
    else:
        my_courses = Course.objects.all()
    ctx.update(
        n_students=students.count(),
        n_in_house=students.filter(student_type=User.StudentType.IN_HOUSE).count(),
        n_school=students.filter(student_type=User.StudentType.SCHOOL).count(),
        n_courses=my_courses.count(),
        n_open_doubts=doubts.count(),
        n_certs=Certificate.objects.filter(student__in=students).count(),
        recent_doubts=doubts.select_related("student", "course").annotate(n_metoo=Count("me_too")).order_by("-n_metoo", "created_at")[:6],
        recent_attempts=QuizAttempt.objects.filter(student__in=students).select_related("student", "quiz")[:8],
        my_courses=my_courses.annotate(n_students=Count("enrollments", distinct=True), n_lessons=Count("lessons", distinct=True))[:8],
        schools=School.objects.annotate(n=Count("users", filter=Q(users__role=User.Role.STUDENT))) if u.is_owner else None,
    )
    return render(request, "portal/dash_staff.html", ctx)


# ---------- generic CRUD for portal content ----------

def _crud(request, model, form_cls, pk, list_url, title, owner_field=None):
    obj = get_object_or_404(model, pk=pk) if pk else None
    if request.method == "POST" and "delete" in request.POST and obj:
        obj.delete()
        messages.success(request, f"{title} deleted.")
        return redirect(list_url)
    form = form_cls(request.POST or None, request.FILES or None, instance=obj)
    if request.method == "POST" and form.is_valid():
        o = form.save(commit=False)
        if owner_field and not obj:
            setattr(o, owner_field, request.user)
        o.save()
        messages.success(request, f"{title} saved.")
        return redirect(list_url)
    return render(request, "courses/form.html", {"form": form, "title": f"{'Edit' if obj else 'New'} {title.lower()}",
                                                 "back": f"/{list_url}/" if not list_url.startswith("/") else list_url,
                                                 "deletable": obj is not None})


def newsletter_list(request):
    qs = Newsletter.objects.all()
    if not (request.user.is_authenticated and request.user.is_staff_member):
        qs = qs.filter(is_published=True)
    return render(request, "portal/newsletter_list.html", {"page": Paginator(qs, 12).get_page(request.GET.get("page"))})


def newsletter_detail(request, pk):
    n = get_object_or_404(Newsletter, pk=pk)
    if not n.is_published and not (request.user.is_authenticated and request.user.is_staff_member):
        return redirect("newsletter_list")
    return render(request, "portal/newsletter_detail.html", {"n": n})


@staff_required
def newsletter_form(request, pk=None):
    return _crud(request, Newsletter, NewsletterForm, pk, "/newsletters/", "Newsletter", "created_by")


def gallery(request):
    qs = GalleryItem.objects.all()
    event = request.GET.get("event", "")
    if event:
        qs = qs.filter(event=event)
    events = GalleryItem.objects.exclude(event="").values_list("event", flat=True).distinct().order_by("event")
    return render(request, "portal/gallery.html", {"page": Paginator(qs, 24).get_page(request.GET.get("page")),
                                                   "events": events, "event": event})


@staff_required
def gallery_form(request, pk=None):
    return _crud(request, GalleryItem, GalleryForm, pk, "/gallery/", "Photo", "uploaded_by")


def competition_list(request):
    today = timezone.localdate()
    qs = Competition.objects.all()
    if not (request.user.is_authenticated and request.user.is_staff_member):
        qs = qs.filter(is_published=True)
    return render(request, "portal/competition_list.html", {
        "upcoming": qs.filter(event_date__gte=today).order_by("event_date"),
        "past": qs.filter(event_date__lt=today)[:20]})


def competition_detail(request, pk):
    c = get_object_or_404(Competition, pk=pk)
    if not c.is_published and not (request.user.is_authenticated and request.user.is_staff_member):
        return redirect("competition_list")
    return render(request, "portal/competition_detail.html", {"c": c})


@staff_required
def competition_form(request, pk=None):
    return _crud(request, Competition, CompetitionForm, pk, "/competitions/", "Competition")
