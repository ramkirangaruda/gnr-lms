from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, Max, Prefetch, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from accounts.models import User
from accounts.permissions import can_view_student, staff_required, visible_students

from . import bunny
from .doubts import visible_doubts
from .forms import CertificateForm, CourseForm, EnrollForm, LessonForm, QuestionForm, QuizForm, parse_usernames
from .models import (Certificate, Choice, Course, Enrollment, Lesson, LessonProgress, Question,
                     Quiz, QuizAttempt)


# ---------- helpers ----------

def _get_course_for_view(request, slug):
    course = get_object_or_404(Course, slug=slug)
    u = request.user
    if u.is_student:
        if not course.is_published or not Enrollment.objects.filter(student=u, course=course).exists():
            raise PermissionDenied("You are not enrolled in this course.")
    return course


def _get_course_for_edit(request, slug):
    course = get_object_or_404(Course, slug=slug)
    if not course.can_manage(request.user):
        raise PermissionDenied
    return course


def course_progress(student, course, lesson_count=None):
    total = lesson_count if lesson_count is not None else course.lessons.count()
    done = LessonProgress.objects.filter(student=student, lesson__course=course).count()
    return round(done * 100 / total) if total else 0


def student_course_stats(student, courses):
    """Per-course progress + quiz stats for one student, in a handful of queries."""
    course_ids = [c.id for c in courses]
    lesson_totals = dict(Lesson.objects.filter(course_id__in=course_ids).values("course_id")
                         .annotate(n=Count("id")).values_list("course_id", "n"))
    done = dict(LessonProgress.objects.filter(student=student, lesson__course_id__in=course_ids)
                .values("lesson__course_id").annotate(n=Count("id")).values_list("lesson__course_id", "n"))
    attempts = QuizAttempt.objects.filter(student=student, quiz__course_id__in=course_ids).select_related("quiz")
    best = {}
    for a in attempts:
        if a.quiz_id not in best or a.percent > best[a.quiz_id].percent:
            best[a.quiz_id] = a
    stats = []
    for c in courses:
        total = lesson_totals.get(c.id, 0)
        quiz_best = [a for a in best.values() if a.quiz.course_id == c.id]
        stats.append({
            "course": c,
            "lessons_total": total,
            "lessons_done": done.get(c.id, 0),
            "progress": round(done.get(c.id, 0) * 100 / total) if total else 0,
            "quizzes_taken": len(quiz_best),
            "quiz_avg": round(sum(a.percent for a in quiz_best) / len(quiz_best)) if quiz_best else None,
            "best_attempts": quiz_best,
        })
    return stats


# ---------- courses ----------

@login_required
def course_list(request):
    u = request.user
    qs = Course.objects.annotate(n_lessons=Count("lessons", distinct=True), n_students=Count("enrollments", distinct=True))
    if u.is_student:
        qs = qs.filter(is_published=True, enrollments__student=u)
    q = request.GET.get("q", "").strip()
    if q:
        qs = qs.filter(Q(title__icontains=q) | Q(description__icontains=q))
    courses = list(qs)
    progress = {}
    if u.is_student:
        progress = {s["course"].id: s["progress"] for s in student_course_stats(u, courses)}
    for c in courses:
        c.my_progress = progress.get(c.id)
        c.manageable = c.can_manage(u)
    return render(request, "courses/course_list.html", {"courses": courses, "q": q})


@login_required
def course_detail(request, slug):
    course = _get_course_for_view(request, slug)
    u = request.user
    lessons = list(course.lessons.all())
    quizzes = course.quizzes.annotate(n_q=Count("questions"))
    if not course.can_manage(u):
        quizzes = quizzes.filter(is_published=True)
    done_ids = set()
    if u.is_student:
        done_ids = set(LessonProgress.objects.filter(student=u, lesson__course=course).values_list("lesson_id", flat=True))
        best = {}
        for a in QuizAttempt.objects.filter(student=u, quiz__course=course).select_related("quiz"):
            if a.quiz_id not in best or a.percent > best[a.quiz_id].percent:
                best[a.quiz_id] = a
        quizzes = list(quizzes)
        for qz in quizzes:
            qz.best = best.get(qz.id)
    for l in lessons:
        l.done = l.id in done_ids
    progress = round(len(done_ids) * 100 / len(lessons)) if lessons and u.is_student else None
    return render(request, "courses/course_detail.html", {
        "course": course, "lessons": lessons, "quizzes": quizzes, "progress": progress,
        "can_manage": course.can_manage(u),
        "certificate": Certificate.objects.filter(student=u, course=course).first() if u.is_student else None,
    })


@staff_required
def course_form(request, slug=None):
    course = _get_course_for_edit(request, slug) if slug else None
    form = CourseForm(request.POST or None, request.FILES or None, instance=course)
    if request.method == "POST" and form.is_valid():
        c = form.save(commit=False)
        if not course:
            c.created_by = request.user
        c.save()
        form.save_m2m()
        if not course and request.user.is_instructor:
            c.instructors.add(request.user)
        messages.success(request, "Course saved.")
        return redirect(c)
    return render(request, "courses/form.html", {"form": form, "title": "Edit course" if course else "New course",
                                                 "back": course.get_absolute_url() if course else "/courses/"})


@staff_required
def course_delete(request, slug):
    course = _get_course_for_edit(request, slug)
    if request.method == "POST":
        title = course.title
        video_ids = [v for v in course.lessons.values_list("bunny_video_id", flat=True) if v]
        course.delete()
        for video_id in video_ids:
            bunny.delete_video(video_id)
        messages.success(request, f"Deleted course “{title}”.")
        return redirect("course_list")
    return render(request, "courses/confirm_delete.html", {"obj": course, "kind": "course",
                                                           "warning": "All lessons, quizzes, attempts and doubts in this course will be deleted."})


# ---------- lessons ----------

@login_required
def lesson_detail(request, slug, pk):
    course = _get_course_for_view(request, slug)
    lesson = get_object_or_404(Lesson, pk=pk, course=course)
    u = request.user
    if request.method == "POST" and u.is_student:
        LessonProgress.objects.get_or_create(student=u, lesson=lesson)
        lessons = list(course.lessons.all())
        if course_progress(u, course, len(lessons)) == 100:
            Enrollment.objects.filter(student=u, course=course, completed_at__isnull=True).update(completed_at=timezone.now())
        idx = [l.id for l in lessons].index(lesson.id)
        if idx + 1 < len(lessons):
            return redirect("lesson_detail", slug=slug, pk=lessons[idx + 1].pk)
        messages.success(request, "You finished every lesson in this course!")
        return redirect(course)
    lessons = list(course.lessons.all())
    ids = [l.id for l in lessons]
    i = ids.index(lesson.id)
    done = u.is_student and LessonProgress.objects.filter(student=u, lesson=lesson).exists()
    return render(request, "courses/lesson_detail.html", {
        "course": course, "lesson": lesson, "lessons": lessons, "done": done,
        "prev": lessons[i - 1] if i > 0 else None, "next": lessons[i + 1] if i + 1 < len(lessons) else None,
        "quizzes": lesson.quizzes.filter(is_published=True), "can_manage": course.can_manage(u),
        "doubts": visible_doubts(u).filter(lesson=lesson).select_related("student")
                  .annotate(n_replies=Count("replies")).order_by("is_resolved", "-updated_at")[:10],
    })


@staff_required
def lesson_form(request, slug, pk=None):
    course = _get_course_for_edit(request, slug)
    lesson = get_object_or_404(Lesson, pk=pk, course=course) if pk else None
    initial = None if lesson else {"order": (course.lessons.aggregate(m=Max("order"))["m"] or 0) + 1}
    form = LessonForm(request.POST or None, request.FILES or None, instance=lesson, initial=initial, course=course)
    if request.method == "POST" and form.is_valid():
        l = form.save(commit=False)
        l.course = course
        l.save()
        if form.old_bunny_video_id:
            bunny.delete_video(form.old_bunny_video_id)
        messages.success(request, "Lesson saved.")
        return redirect("lesson_detail", slug=slug, pk=l.pk)
    return render(request, "courses/lesson_form.html", {
        "form": form, "course": course, "lesson": lesson, "back": course.get_absolute_url(),
        "bunny_enabled": bunny.is_enabled(),
        "title": "Edit lesson" if lesson else f"Add lesson to {course.title}"})


@staff_required
@require_POST
def lesson_bunny_upload(request, slug):
    """Create an empty Bunny video and hand the browser short-lived TUS upload credentials.

    Only instructors who can manage this course (or owners) get here; the API key stays on the server.
    """
    course = _get_course_for_edit(request, slug)
    if not bunny.is_enabled():
        return JsonResponse({"error": "Bunny Stream is not set up on this server."}, status=503)
    title = (request.POST.get("title") or "").strip() or "Lesson video"
    try:
        video_id = bunny.create_video(f"{course.title} – {title}")
    except bunny.BunnyError:
        return JsonResponse({"error": "Could not reach Bunny Stream. Please try again."}, status=502)
    creds = bunny.tus_credentials(video_id)
    creds["token"] = bunny.make_upload_token(course.pk, video_id)
    return JsonResponse(creds)


@staff_required
def lesson_delete(request, slug, pk):
    course = _get_course_for_edit(request, slug)
    lesson = get_object_or_404(Lesson, pk=pk, course=course)
    if request.method == "POST":
        video_id = lesson.bunny_video_id
        lesson.delete()
        bunny.delete_video(video_id)
        messages.success(request, "Lesson deleted.")
        return redirect(course)
    return render(request, "courses/confirm_delete.html", {"obj": lesson, "kind": "lesson"})


# ---------- quizzes ----------

@staff_required
def quiz_form(request, slug, pk=None):
    course = _get_course_for_edit(request, slug)
    quiz = get_object_or_404(Quiz, pk=pk, course=course) if pk else None
    form = QuizForm(request.POST or None, instance=quiz, course=course)
    if request.method == "POST" and form.is_valid():
        q = form.save(commit=False)
        q.course = course
        q.save()
        messages.success(request, "Quiz saved. Now add questions.")
        return redirect("quiz_manage", slug=slug, pk=q.pk)
    return render(request, "courses/form.html", {"form": form, "course": course, "back": course.get_absolute_url(),
                                                 "title": "Edit quiz" if quiz else "New quiz"})


@staff_required
def quiz_manage(request, slug, pk):
    course = _get_course_for_edit(request, slug)
    quiz = get_object_or_404(Quiz, pk=pk, course=course)
    edit_q = None
    if request.GET.get("edit", "").isdigit():
        edit_q = get_object_or_404(Question, pk=request.GET["edit"], quiz=quiz)
    form = QuestionForm(request.POST or None, request.FILES or None, instance=edit_q,
                        initial=None if edit_q else {"order": quiz.questions.count() + 1})
    if request.method == "POST":
        if "delete_question" in request.POST:
            if request.POST["delete_question"].isdigit():
                Question.objects.filter(pk=request.POST["delete_question"], quiz=quiz).delete()
            messages.success(request, "Question removed.")
            return redirect("quiz_manage", slug=slug, pk=pk)
        if "delete_quiz" in request.POST:
            quiz.delete()
            messages.success(request, "Quiz deleted.")
            return redirect(course)
        if form.is_valid():
            with transaction.atomic():
                q = form.save(commit=False)
                q.quiz = quiz
                q.save()
                form.save_choices(q)
            messages.success(request, "Question saved.")
            return redirect("quiz_manage", slug=slug, pk=pk)
    questions = quiz.questions.prefetch_related("choices")
    attempts = quiz.attempts.select_related("student")[:50]
    return render(request, "courses/quiz_manage.html", {"course": course, "quiz": quiz, "questions": questions,
                                                        "form": form, "edit_q": edit_q, "attempts": attempts})


@login_required
def quiz_take(request, slug, pk):
    course = _get_course_for_view(request, slug)
    quiz = get_object_or_404(Quiz, pk=pk, course=course)
    u = request.user
    if not quiz.is_published and not course.can_manage(u):
        raise PermissionDenied
    questions = list(quiz.questions.prefetch_related(Prefetch("choices", queryset=Choice.objects.order_by("?"))))
    past = QuizAttempt.objects.filter(quiz=quiz, student=u) if u.is_student else QuizAttempt.objects.none()
    if u.is_student and quiz.max_attempts and past.count() >= quiz.max_attempts:
        messages.info(request, "You have used all attempts for this quiz.")
        return redirect("quiz_result", slug=slug, pk=pk, attempt=past.first().pk)
    if request.method == "POST":
        if not u.is_student:
            messages.info(request, "Preview only – staff answers are not recorded.")
            return redirect("quiz_manage", slug=slug, pk=pk)
        score = total = 0
        answers = {}
        for q in questions:
            picked = {int(x) for x in request.POST.getlist(f"q{q.id}") if x.isdigit()}
            correct = {c.id for c in q.choices.all() if c.is_correct}
            answers[str(q.id)] = sorted(picked)
            total += q.marks
            if picked and picked == correct:
                score += q.marks
        attempt = QuizAttempt.objects.create(quiz=quiz, student=u, score=score, total=total, answers=answers)
        return redirect("quiz_result", slug=slug, pk=pk, attempt=attempt.pk)
    for q in questions:
        q.multi = sum(1 for c in q.choices.all() if c.is_correct) > 1
    return render(request, "courses/quiz_take.html", {"course": course, "quiz": quiz, "questions": questions,
                                                      "attempts_used": past.count()})


@login_required
def quiz_result(request, slug, pk, attempt):
    course = _get_course_for_view(request, slug)
    a = get_object_or_404(QuizAttempt, pk=attempt, quiz_id=pk, quiz__course=course)
    if not can_view_student(request.user, a.student):
        raise PermissionDenied
    questions = list(a.quiz.questions.prefetch_related("choices"))
    for q in questions:
        q.picked = set(a.answers.get(str(q.id), []))
        q.correct_ids = {c.id for c in q.choices.all() if c.is_correct}
        q.is_right = bool(q.picked) and q.picked == q.correct_ids
    return render(request, "courses/quiz_result.html", {"course": course, "attempt": a, "questions": questions})


# ---------- enrollment & reports ----------

@staff_required
def course_students(request, slug):
    course = _get_course_for_edit(request, slug)
    form = EnrollForm(request.POST or None)
    if request.method == "POST":
        if "remove" in request.POST:
            if request.POST["remove"].isdigit():
                Enrollment.objects.filter(course=course, student_id=request.POST["remove"]).delete()
            messages.success(request, "Student removed from course.")
            return redirect("course_students", slug=slug)
        if form.is_valid():
            d = form.cleaned_data
            students = User.objects.filter(role=User.Role.STUDENT, is_active=True)
            filt = Q(pk__in=[])
            if d["school"]:
                filt |= Q(school=d["school"])
            if d["in_house"]:
                filt |= Q(student_type=User.StudentType.IN_HOUSE)
            names = parse_usernames(d["usernames"])
            if names:
                filt |= Q(username__in=names)
            students = students.filter(filt)
            if d["grade"]:
                students = students.filter(grade__iexact=d["grade"])
            if d["batch"]:
                students = students.filter(batch__iexact=d["batch"])
            objs = [Enrollment(student_id=sid, course=course) for sid in students.values_list("id", flat=True)]
            Enrollment.objects.bulk_create(objs, ignore_conflicts=True, batch_size=500)
            messages.success(request, f"Enrolment updated ({len(objs)} matching students).")
            return redirect("course_students", slug=slug)
    return render(request, "courses/course_students.html", {"course": course, "form": form, **_course_report(course, request)})


def _course_report(course, request, student_qs=None):
    enrolls = course.enrollments.select_related("student", "student__school").order_by("student__school__name", "student__username")
    if student_qs is not None:
        enrolls = enrolls.filter(student__in=student_qs)
    q = request.GET.get("q", "").strip()
    if q:
        enrolls = enrolls.filter(Q(student__username__icontains=q) | Q(student__first_name__icontains=q)
                                 | Q(student__batch__icontains=q) | Q(student__school__name__icontains=q))
    page = Paginator(enrolls, 100).get_page(request.GET.get("page"))
    ids = [e.student_id for e in page]
    n_lessons = course.lessons.count()
    done = dict(LessonProgress.objects.filter(lesson__course=course, student_id__in=ids).values("student_id")
                .annotate(n=Count("id")).values_list("student_id", "n"))
    best = {}
    for a in QuizAttempt.objects.filter(quiz__course=course, student_id__in=ids).only("student_id", "quiz_id", "score", "total"):
        k = (a.student_id, a.quiz_id)
        best[k] = max(best.get(k, 0), a.percent)
    rows = []
    for e in page:
        scores = [v for (sid, _), v in best.items() if sid == e.student_id]
        rows.append({"e": e, "s": e.student, "progress": round(done.get(e.student_id, 0) * 100 / n_lessons) if n_lessons else 0,
                     "quiz_avg": round(sum(scores) / len(scores)) if scores else None, "quizzes": len(scores)})
    return {"rows": rows, "page": page, "q": q, "n_lessons": n_lessons}


@login_required
def course_report(request, slug):
    course = get_object_or_404(Course, slug=slug)
    u = request.user
    if not (course.can_manage(u) or u.is_owner or u.is_instructor or u.is_school_admin):
        raise PermissionDenied
    ctx = _course_report(course, request, student_qs=visible_students(u))
    return render(request, "courses/course_report.html", {"course": course, **ctx})


@login_required
def student_report(request, pk):
    student = get_object_or_404(User.objects.select_related("school"), pk=pk, role=User.Role.STUDENT)
    if not can_view_student(request.user, student):
        raise PermissionDenied
    courses = [e.course for e in student.enrollments.select_related("course")]
    return render(request, "courses/student_report.html", {
        "student": student, "stats": student_course_stats(student, courses),
        "attempts": student.quiz_attempts.select_related("quiz", "quiz__course")[:30],
        "certificates": student.certificates.select_related("course"),
        "doubts": student.doubts.select_related("course")[:20],
    })


@login_required
def students_overview(request):
    u = request.user
    if not (u.is_owner or u.is_instructor or u.is_school_admin):
        raise PermissionDenied
    qs = visible_students(u).annotate(
        n_courses=Count("enrollments", distinct=True),
        n_lessons=Count("lesson_progress", distinct=True),
        n_attempts=Count("quiz_attempts", distinct=True),
        n_certs=Count("certificates", distinct=True),
    ).order_by("school__name", "grade", "username")
    q = request.GET.get("q", "").strip()
    if q:
        qs = qs.filter(Q(username__icontains=q) | Q(first_name__icontains=q) | Q(last_name__icontains=q) | Q(batch__icontains=q))
    if request.GET.get("school", "").isdigit():
        qs = qs.filter(school_id=request.GET["school"])
    from accounts.models import School
    return render(request, "courses/students_overview.html", {
        "page": Paginator(qs, 50).get_page(request.GET.get("page")), "q": q,
        "schools": School.objects.all() if not u.is_school_admin else [], "school": request.GET.get("school", "")})


# ---------- certificates ----------

@login_required
def certificate_list(request):
    u = request.user
    qs = Certificate.objects.select_related("student", "course", "issued_by", "student__school")
    if u.is_student:
        qs = qs.filter(student=u)
    elif u.is_school_admin:
        qs = qs.filter(student__school_id=u.school_id)
    q = request.GET.get("q", "").strip()
    if q:
        qs = qs.filter(Q(student__username__icontains=q) | Q(student__first_name__icontains=q) | Q(title__icontains=q))
    return render(request, "courses/certificate_list.html", {"page": Paginator(qs, 50).get_page(request.GET.get("page")), "q": q})


@staff_required
def certificate_issue(request):
    initial = {}
    if request.GET.get("course", "").isdigit():
        c = Course.objects.filter(pk=request.GET["course"]).first()
        if c:
            initial["course"] = c
            initial["achievement"] = f"successfully completed the course “{c.title}”"
            if request.GET.get("completed"):
                done = c.enrollments.filter(completed_at__isnull=False).exclude(
                    student__certificates__course=c).values_list("student__username", flat=True)
                initial["usernames"] = "\n".join(done)
    form = CertificateForm(request.POST or None, initial=initial)
    if request.method == "POST" and form.is_valid():
        d = form.cleaned_data
        certs = [Certificate(student=s, course=d["course"], title=d["title"], achievement=d["achievement"],
                             grade=d["grade"], issued_on=d["issued_on"], issued_by=request.user) for s in d["usernames"]]
        Certificate.objects.bulk_create(certs)
        messages.success(request, f"Issued {len(certs)} certificate(s).")
        return redirect("certificate_list")
    return render(request, "courses/certificate_issue.html", {"form": form, "courses": Course.objects.all()})


@login_required
def certificate_view(request, code):
    cert = get_object_or_404(Certificate.objects.select_related("student", "course", "issued_by", "student__school"), code=code)
    if not (can_view_student(request.user, cert.student)):
        raise PermissionDenied
    if request.method == "POST" and request.user.is_staff_member and "revoke" in request.POST:
        cert.delete()
        messages.success(request, "Certificate revoked.")
        return redirect("certificate_list")
    return render(request, "courses/certificate.html", {"c": cert, "verify_url": request.build_absolute_uri(f"/verify/{cert.code}/")})


def certificate_verify(request, code):
    """Public page anyone (parents, schools) can use to check a certificate is genuine."""
    cert = Certificate.objects.select_related("student", "course").filter(code=code).first()
    return render(request, "courses/verify.html", {"c": cert})
