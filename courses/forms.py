from django import forms

from accounts.forms import StyledMixin
from accounts.models import School, User

from . import bunny
from .models import Certificate, Course, Lesson, Question, Quiz

VIDEO_EXTS = (".mp4", ".webm", ".mov", ".m4v")


class CourseForm(StyledMixin, forms.ModelForm):
    class Meta:
        model = Course
        fields = ["title", "description", "thumbnail", "level", "age_group", "instructors", "is_published"]
        widgets = {"description": forms.Textarea(attrs={"rows": 4}), "instructors": forms.SelectMultiple(attrs={"size": 4})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["instructors"].queryset = User.objects.filter(role=User.Role.INSTRUCTOR)


class LessonForm(StyledMixin, forms.ModelForm):
    # Filled in by the browser after it finishes uploading to Bunny Stream (see lesson_form.html).
    bunny_upload_token = forms.CharField(required=False, widget=forms.HiddenInput)
    remove_bunny_video = forms.BooleanField(required=False, label="Remove the Bunny Stream video from this lesson")

    class Meta:
        model = Lesson
        fields = ["title", "order", "video_url", "video_file", "content", "attachment", "duration_minutes"]
        widgets = {"content": forms.Textarea(attrs={"rows": 6})}

    def __init__(self, *args, course=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.course = course
        self.new_bunny_video_id = None
        if not self.instance.bunny_video_id:
            del self.fields["remove_bunny_video"]

    def clean_video_file(self):
        f = self.cleaned_data.get("video_file")
        if f and hasattr(f, "name") and not f.name.lower().endswith(VIDEO_EXTS):
            raise forms.ValidationError("Upload an MP4/WebM/MOV video.")
        return f

    def clean(self):
        d = super().clean()
        token = d.get("bunny_upload_token")
        if token:
            video_id = bunny.read_upload_token(token, self.course.pk if self.course else None)
            if not video_id:
                self.add_error(None, "The video upload link has expired or is invalid. Please upload the video again.")
            else:
                self.new_bunny_video_id = video_id
        return d

    def save(self, commit=True):
        """Apply Bunny changes. Returns the lesson; the replaced/removed Bunny video id is in `old_bunny_video_id`."""
        lesson = super().save(commit=False)
        old = lesson.bunny_video_id
        if self.new_bunny_video_id:
            lesson.bunny_video_id = self.new_bunny_video_id
        elif self.cleaned_data.get("remove_bunny_video"):
            lesson.bunny_video_id = ""
        self.old_bunny_video_id = old if old and old != lesson.bunny_video_id else None
        if commit:
            lesson.save()
        return lesson


class QuizForm(StyledMixin, forms.ModelForm):
    class Meta:
        model = Quiz
        fields = ["title", "description", "lesson", "pass_percentage", "time_limit_minutes", "max_attempts", "reveal_answers", "is_published"]
        widgets = {"description": forms.Textarea(attrs={"rows": 2})}

    def __init__(self, *args, course=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["lesson"].queryset = course.lessons.all() if course else Lesson.objects.none()


class QuestionForm(StyledMixin, forms.ModelForm):
    """A question with up to 5 options; tick the correct one(s)."""
    choice_1 = forms.CharField(max_length=300)
    choice_2 = forms.CharField(max_length=300)
    choice_3 = forms.CharField(max_length=300, required=False)
    choice_4 = forms.CharField(max_length=300, required=False)
    choice_5 = forms.CharField(max_length=300, required=False)
    correct = forms.MultipleChoiceField(choices=[(str(i), f"Option {i}") for i in range(1, 6)],
                                        widget=forms.CheckboxSelectMultiple, help_text="Tick every correct option")

    class Meta:
        model = Question
        fields = ["text", "image", "marks", "order"]
        widgets = {"text": forms.Textarea(attrs={"rows": 2})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["correct"].widget.attrs = {}
        if self.instance.pk:
            choices = list(self.instance.choices.all())
            for i, c in enumerate(choices[:5], 1):
                self.initial[f"choice_{i}"] = c.text
            self.initial["correct"] = [str(i) for i, c in enumerate(choices[:5], 1) if c.is_correct]

    def clean(self):
        d = super().clean()
        for i in d.get("correct", []):
            if not d.get(f"choice_{i}"):
                self.add_error("correct", f"Option {i} is marked correct but is empty.")
        return d

    def save_choices(self, question):
        question.choices.all().delete()
        correct = set(self.cleaned_data["correct"])
        for i in range(1, 6):
            text = self.cleaned_data.get(f"choice_{i}")
            if text:
                question.choices.create(text=text, is_correct=str(i) in correct)


class EnrollForm(StyledMixin, forms.Form):
    school = forms.ModelChoiceField(queryset=School.objects.all(), required=False, help_text="Enrol every student of this school")
    in_house = forms.BooleanField(required=False, label="Enrol all in-house students")
    grade = forms.CharField(required=False, help_text="Optional: only this grade")
    batch = forms.CharField(required=False, help_text="Optional: only this batch")
    usernames = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 3}),
                                help_text="Or list usernames separated by spaces, commas or new lines")


class CertificateForm(StyledMixin, forms.ModelForm):
    usernames = forms.CharField(widget=forms.Textarea(attrs={"rows": 3}),
                                help_text="One or more student usernames (spaces, commas or new lines)")

    class Meta:
        model = Certificate
        fields = ["course", "title", "achievement", "grade", "issued_on"]
        widgets = {"issued_on": forms.DateInput(attrs={"type": "date"})}

    def clean_usernames(self):
        names = {n for n in self.cleaned_data["usernames"].replace(",", " ").split() if n}
        students = list(User.objects.filter(username__in=names, role=User.Role.STUDENT))
        missing = names - {s.username for s in students}
        if missing:
            raise forms.ValidationError(f"Unknown student usernames: {', '.join(sorted(missing))}")
        return students


def parse_usernames(text):
    return {n for n in (text or "").replace(",", " ").split() if n}
