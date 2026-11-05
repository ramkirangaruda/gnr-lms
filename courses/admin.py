from django.contrib import admin

from .models import Certificate, Choice, Course, Doubt, DoubtReply, Enrollment, Lesson, Question, Quiz, QuizAttempt


class LessonInline(admin.TabularInline):
    model = Lesson
    extra = 0
    fields = ("order", "title", "video_url")


@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    list_display = ("title", "level", "is_published", "created_at")
    inlines = [LessonInline]
    search_fields = ("title",)


class ChoiceInline(admin.TabularInline):
    model = Choice
    extra = 4


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ("text", "quiz", "marks")
    inlines = [ChoiceInline]


admin.site.register([Quiz, Enrollment, QuizAttempt, Doubt, DoubtReply])


@admin.register(Certificate)
class CertificateAdmin(admin.ModelAdmin):
    list_display = ("student", "title", "course", "issued_on", "issued_by")
    search_fields = ("student__username", "title")
