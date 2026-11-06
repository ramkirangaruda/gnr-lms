import csv
import io
import logging

from django import forms
from django.conf import settings
from django.contrib.auth.forms import PasswordResetForm, SetPasswordForm
from django.core.cache import cache
from django.db.models import Q

from .models import School, User

logger = logging.getLogger(__name__)


class StyledMixin:
    """Adds Bootstrap classes to every widget."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for f in self.fields.values():
            w = f.widget
            if isinstance(w, forms.CheckboxInput):
                w.attrs.setdefault("class", "form-check-input")
            elif isinstance(w, (forms.Select, forms.SelectMultiple)):
                w.attrs.setdefault("class", "form-select")
            else:
                w.attrs.setdefault("class", "form-control")


class SchoolForm(StyledMixin, forms.ModelForm):
    class Meta:
        model = School
        fields = ["name", "code", "city", "contact_email", "contact_phone", "is_active"]


class UserCreateForm(StyledMixin, forms.ModelForm):
    password = forms.CharField(required=False, widget=forms.TextInput,
                               help_text="Leave blank to auto-generate a password")

    class Meta:
        model = User
        fields = ["first_name", "last_name", "username", "email", "phone", "role",
                  "student_type", "school", "grade", "batch"]

    def __init__(self, *args, actor=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].required = False
        self.fields["username"].help_text = "Leave blank to auto-generate"
        restrict_fields(self, actor)


class UserEditForm(StyledMixin, forms.ModelForm):
    class Meta:
        model = User
        fields = ["first_name", "last_name", "email", "phone", "role", "student_type",
                  "school", "grade", "batch", "is_active"]

    def __init__(self, *args, actor=None, **kwargs):
        super().__init__(*args, **kwargs)
        restrict_fields(self, actor)


def restrict_fields(form, actor):
    """Only owners can create owners/instructors/school admins; school admins are locked to their school."""
    if actor is None or actor.is_owner:
        return
    form.fields["role"].choices = [(User.Role.STUDENT, "Student")]
    if actor.is_school_admin:
        form.fields["school"].queryset = School.objects.filter(pk=actor.school_id)
        form.fields["student_type"].choices = [(User.StudentType.SCHOOL, "School student")]


class BulkGenerateForm(StyledMixin, forms.Form):
    student_type = forms.ChoiceField(choices=User.StudentType.choices)
    school = forms.ModelChoiceField(queryset=School.objects.filter(is_active=True), required=False,
                                    help_text="Required for school students")
    grade = forms.CharField(required=False, max_length=20)
    batch = forms.CharField(required=False, max_length=50)
    count = forms.IntegerField(required=False, min_value=1, max_value=500,
                               help_text="Number of blank accounts to create (if not uploading a CSV)")
    csv_file = forms.FileField(required=False, label="Or upload a CSV of students",
                               help_text="Columns: first_name, last_name, grade, batch, email, phone (header row required)")
    course_ids = forms.MultipleChoiceField(required=False, label="Enrol them in courses",
                                           widget=forms.SelectMultiple(attrs={"size": 5}))

    def __init__(self, *args, actor=None, **kwargs):
        super().__init__(*args, **kwargs)
        from courses.models import Course
        self.fields["course_ids"].choices = [(c.pk, c.title) for c in Course.objects.only("id", "title")]
        if actor and actor.is_school_admin:
            self.fields["school"].queryset = School.objects.filter(pk=actor.school_id)
            self.fields["student_type"].choices = [(User.StudentType.SCHOOL, "School student")]

    def clean(self):
        data = super().clean()
        if data.get("student_type") == User.StudentType.SCHOOL and not data.get("school"):
            self.add_error("school", "Choose the school for school students.")
        rows = []
        f = data.get("csv_file")
        if f:
            try:
                text = f.read().decode("utf-8-sig")
            except UnicodeDecodeError:
                raise forms.ValidationError("CSV must be UTF-8 encoded.")
            reader = csv.DictReader(io.StringIO(text))
            for r in reader:
                r = {(k or "").strip().lower(): (v or "").strip() for k, v in r.items()}
                if any(r.values()):
                    rows.append(r)
            if not rows:
                raise forms.ValidationError("The CSV has no student rows.")
            if len(rows) > 2000:
                raise forms.ValidationError("Please upload at most 2000 students at a time.")
        elif data.get("count"):
            rows = [{} for _ in range(data["count"])]
        else:
            raise forms.ValidationError("Enter a number of accounts or upload a CSV.")
        data["rows"] = rows
        return data


class ForcedPasswordChangeForm(StyledMixin, forms.Form):
    new_password1 = forms.CharField(label="New password", widget=forms.PasswordInput, min_length=6)
    new_password2 = forms.CharField(label="Confirm new password", widget=forms.PasswordInput)

    def clean(self):
        d = super().clean()
        if d.get("new_password1") != d.get("new_password2"):
            raise forms.ValidationError("Passwords do not match.")
        return d


class ResetRequestForm(StyledMixin, PasswordResetForm):
    """'Forgot password' by username OR email. Only accounts that have an email address can be reset this way;
    students without one are reset by their instructor or school coordinator. The page never says which it was,
    so it can't be used to find out who has an account."""
    email = forms.CharField(label="Username or email", max_length=254,
                            widget=forms.TextInput(attrs={"autocomplete": "username", "autocapitalize": "none",
                                                          "autofocus": True}))

    def get_users(self, value):
        value = value.strip()
        if not value:
            return []
        qs = User._default_manager.filter(is_active=True).exclude(email="").filter(
            Q(username__iexact=value) | Q(email__iexact=value))
        limit = settings.PASSWORD_RESET_EMAILS_PER_HOUR
        users = []
        for u in qs:
            if not u.has_usable_password():
                continue
            key = f"pwreset:{u.pk}"
            cache.add(key, 0, 3600)
            if cache.incr(key) > limit:
                logger.warning("Password reset email limit reached for user %s", u.pk)
                continue
            users.append(u)
        return users

    def send_mail(self, *args, **kwargs):
        # An SMTP outage should not show the visitor an error page; it goes to the log instead.
        try:
            super().send_mail(*args, **kwargs)
        except Exception:
            logger.exception("Could not send password reset email")


class ResetSetPasswordForm(StyledMixin, SetPasswordForm):
    """Setting a password from an emailed link counts as choosing your own password."""
    def save(self, commit=True):
        self.user.must_change_password = False
        return super().save(commit)
