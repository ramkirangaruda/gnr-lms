from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import School, User


@admin.register(User)
class GNRUserAdmin(UserAdmin):
    list_display = ("username", "first_name", "last_name", "role", "student_type", "school", "grade", "is_active")
    list_filter = ("role", "student_type", "school", "is_active")
    search_fields = ("username", "first_name", "last_name", "email")
    fieldsets = UserAdmin.fieldsets + (("GNR", {"fields": ("role", "student_type", "school", "grade", "batch", "phone", "must_change_password")}),)


@admin.register(School)
class SchoolAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "city", "is_active")
    search_fields = ("name", "code")
