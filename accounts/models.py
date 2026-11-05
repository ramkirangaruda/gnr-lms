from django.contrib.auth.models import AbstractUser
from django.db import models


class School(models.Model):
    name = models.CharField(max_length=200, unique=True)
    code = models.SlugField(max_length=20, unique=True, help_text="Short code used in auto-generated usernames, e.g. 'dps'")
    city = models.CharField(max_length=100, blank=True)
    contact_email = models.EmailField(blank=True)
    contact_phone = models.CharField(max_length=20, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class User(AbstractUser):
    class Role(models.TextChoices):
        OWNER = "owner", "GNR Owner"
        INSTRUCTOR = "instructor", "Instructor"
        SCHOOL = "school", "School Admin"
        STUDENT = "student", "Student"

    class StudentType(models.TextChoices):
        IN_HOUSE = "in_house", "In-house (GNR centre)"
        SCHOOL = "school", "School student"

    role = models.CharField(max_length=20, choices=Role.choices, default=Role.STUDENT, db_index=True)
    student_type = models.CharField(max_length=20, choices=StudentType.choices, blank=True)
    school = models.ForeignKey(School, null=True, blank=True, on_delete=models.SET_NULL, related_name="users")
    grade = models.CharField("Class / grade", max_length=20, blank=True)
    batch = models.CharField(max_length=50, blank=True, help_text="Batch or section name")
    phone = models.CharField(max_length=20, blank=True)
    must_change_password = models.BooleanField(default=False)

    class Meta:
        indexes = [models.Index(fields=["role", "school"])]

    @property
    def is_owner(self):
        return self.role == self.Role.OWNER or self.is_superuser

    @property
    def is_instructor(self):
        return self.role == self.Role.INSTRUCTOR

    @property
    def is_school_admin(self):
        return self.role == self.Role.SCHOOL

    @property
    def is_student(self):
        return self.role == self.Role.STUDENT and not self.is_superuser

    @property
    def is_staff_member(self):
        """Owners and instructors: can manage courses, quizzes, certificates."""
        return self.is_owner or self.is_instructor

    def __str__(self):
        return self.get_full_name() or self.username
