import re
import uuid

from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils import timezone
from django.utils.text import slugify

User = settings.AUTH_USER_MODEL


class Course(models.Model):
    class Level(models.TextChoices):
        BEGINNER = "beginner", "Beginner"
        INTERMEDIATE = "intermediate", "Intermediate"
        ADVANCED = "advanced", "Advanced"

    title = models.CharField(max_length=200)
    slug = models.SlugField(max_length=220, unique=True, blank=True)
    description = models.TextField(blank=True)
    thumbnail = models.ImageField(upload_to="courses/thumbs/", blank=True)
    level = models.CharField(max_length=20, choices=Level.choices, default=Level.BEGINNER)
    age_group = models.CharField(max_length=50, blank=True, help_text="e.g. Grades 5-8")
    is_published = models.BooleanField(default=True)
    created_by = models.ForeignKey(User, null=True, on_delete=models.SET_NULL, related_name="courses_created")
    instructors = models.ManyToManyField(User, blank=True, related_name="courses_teaching",
                                         limit_choices_to={"role": "instructor"})
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify(self.title)[:200] or "course"
            slug, n = base, 2
            while Course.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug, n = f"{base}-{n}", n + 1
            self.slug = slug
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse("course_detail", args=[self.slug])

    def can_manage(self, user):
        return user.is_authenticated and (
            user.is_owner or (user.is_instructor and (self.created_by_id == user.id or self.instructors.filter(pk=user.pk).exists()))
        )

    def __str__(self):
        return self.title


class Enrollment(models.Model):
    student = models.ForeignKey(User, on_delete=models.CASCADE, related_name="enrollments")
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="enrollments")
    enrolled_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = ("student", "course")


class Lesson(models.Model):
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="lessons")
    title = models.CharField(max_length=200)
    order = models.PositiveIntegerField(default=0)
    video_url = models.URLField(blank=True, help_text="YouTube / Vimeo link (recommended: saves server bandwidth)")
    video_file = models.FileField(upload_to="lessons/videos/", blank=True, help_text="Or upload an MP4 file")
    content = models.TextField(blank=True, help_text="Notes / instructions shown below the video")
    attachment = models.FileField(upload_to="lessons/files/", blank=True, help_text="Worksheet, code, PDF…")
    duration_minutes = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["order", "id"]

    def embed_url(self):
        """Turn a YouTube/Vimeo link into an embeddable player URL."""
        url = self.video_url or ""
        m = re.search(r"(?:youtube\.com/(?:watch\?v=|embed/|shorts/)|youtu\.be/)([\w-]{11})", url)
        if m:
            return f"https://www.youtube-nocookie.com/embed/{m.group(1)}?rel=0"
        m = re.search(r"vimeo\.com/(?:video/)?(\d+)", url)
        if m:
            return f"https://player.vimeo.com/video/{m.group(1)}"
        return url

    def __str__(self):
        return f"{self.course} – {self.title}"


class LessonProgress(models.Model):
    student = models.ForeignKey(User, on_delete=models.CASCADE, related_name="lesson_progress")
    lesson = models.ForeignKey(Lesson, on_delete=models.CASCADE, related_name="progress")
    completed_at = models.DateTimeField(default=timezone.now)

    class Meta:
        unique_together = ("student", "lesson")


class Quiz(models.Model):
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="quizzes")
    lesson = models.ForeignKey(Lesson, null=True, blank=True, on_delete=models.SET_NULL, related_name="quizzes",
                               help_text="Optional: attach the quiz after a specific lesson")
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    pass_percentage = models.PositiveIntegerField(default=50)
    time_limit_minutes = models.PositiveIntegerField(default=0, help_text="0 = no limit")
    max_attempts = models.PositiveIntegerField(default=0, help_text="0 = unlimited")
    is_published = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
        verbose_name_plural = "quizzes"

    def __str__(self):
        return self.title


class Question(models.Model):
    quiz = models.ForeignKey(Quiz, on_delete=models.CASCADE, related_name="questions")
    text = models.TextField()
    image = models.ImageField(upload_to="quiz/", blank=True)
    marks = models.PositiveIntegerField(default=1)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order", "id"]

    def __str__(self):
        return self.text[:80]


class Choice(models.Model):
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name="choices")
    text = models.CharField(max_length=300)
    is_correct = models.BooleanField(default=False)

    def __str__(self):
        return self.text


class QuizAttempt(models.Model):
    quiz = models.ForeignKey(Quiz, on_delete=models.CASCADE, related_name="attempts")
    student = models.ForeignKey(User, on_delete=models.CASCADE, related_name="quiz_attempts")
    score = models.PositiveIntegerField(default=0)
    total = models.PositiveIntegerField(default=0)
    answers = models.JSONField(default=dict)  # {question_id: [choice_ids]}
    submitted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-submitted_at"]
        indexes = [models.Index(fields=["student", "quiz"])]

    @property
    def percent(self):
        return round(self.score * 100 / self.total) if self.total else 0

    @property
    def passed(self):
        return self.percent >= self.quiz.pass_percentage


class Doubt(models.Model):
    class Category(models.TextChoices):
        CONCEPT = "concept", "Concept / theory"
        CODE = "code", "Code & programming"
        CIRCUIT = "circuit", "Circuit & wiring"
        KIT = "kit", "Kit / parts / hardware"
        ASSIGNMENT = "assignment", "Assignment / project"
        OTHER = "other", "Something else"

    student = models.ForeignKey(User, on_delete=models.CASCADE, related_name="doubts")
    course = models.ForeignKey(Course, null=True, blank=True, on_delete=models.CASCADE, related_name="doubts",
                               help_text="Leave empty for a general robotics doubt")
    lesson = models.ForeignKey(Lesson, null=True, blank=True, on_delete=models.SET_NULL, related_name="doubts")
    category = models.CharField(max_length=20, choices=Category.choices, default=Category.CONCEPT, db_index=True)
    title = models.CharField(max_length=200)
    body = models.TextField()
    image = models.ImageField(upload_to="doubts/", blank=True, help_text="Photo of your circuit / code / robot")
    is_private = models.BooleanField(default=False, help_text="Only instructors can see a private doubt")
    is_resolved = models.BooleanField(default=False, db_index=True)
    has_staff_reply = models.BooleanField(default=False, db_index=True)
    me_too = models.ManyToManyField(User, blank=True, related_name="doubts_me_too")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["is_resolved", "-updated_at"]

    CATEGORY_ICONS = {"concept": "bi-lightbulb", "code": "bi-code-slash", "circuit": "bi-lightning-charge",
                      "kit": "bi-tools", "assignment": "bi-journal-check", "other": "bi-question-circle"}

    @property
    def category_icon(self):
        return self.CATEGORY_ICONS.get(self.category, "bi-question-circle")

    @property
    def status(self):
        if self.is_resolved:
            return "resolved"
        return "answered" if self.has_staff_reply else "open"

    def get_status_display(self):
        return {"resolved": "Resolved", "answered": "Answered", "open": "Waiting for answer"}[self.status]

    def __str__(self):
        return self.title


class DoubtReply(models.Model):
    doubt = models.ForeignKey(Doubt, on_delete=models.CASCADE, related_name="replies")
    author = models.ForeignKey(User, on_delete=models.CASCADE)
    body = models.TextField()
    image = models.ImageField(upload_to="doubts/replies/", blank=True)
    is_accepted = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]


class Certificate(models.Model):
    student = models.ForeignKey(User, on_delete=models.CASCADE, related_name="certificates")
    course = models.ForeignKey(Course, null=True, blank=True, on_delete=models.SET_NULL, related_name="certificates")
    title = models.CharField(max_length=200, default="Certificate of Completion")
    achievement = models.CharField(max_length=300, blank=True,
                                   help_text="e.g. 'successfully completed Robotics Level 1' or 'won 1st place in RoboRace'")
    grade = models.CharField(max_length=20, blank=True)
    issued_by = models.ForeignKey(User, null=True, on_delete=models.SET_NULL, related_name="certificates_issued")
    issued_on = models.DateField(default=timezone.localdate)
    code = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)

    class Meta:
        ordering = ["-issued_on", "-id"]

    @property
    def short_code(self):
        return str(self.code).split("-")[0].upper()

    def __str__(self):
        return f"{self.title} – {self.student}"
