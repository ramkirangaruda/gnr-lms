from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied


def role_required(*checks):
    """Allow the view if the user passes any of the given checks, e.g. role_required("is_owner", "is_instructor")."""
    def decorator(view):
        @wraps(view)
        @login_required
        def wrapper(request, *args, **kwargs):
            if any(getattr(request.user, c) for c in checks):
                return view(request, *args, **kwargs)
            raise PermissionDenied
        return wrapper
    return decorator


staff_required = role_required("is_owner", "is_instructor")
owner_required = role_required("is_owner")
manager_required = role_required("is_owner", "is_instructor", "is_school_admin")


def visible_students(user):
    """Students this user is allowed to see and manage."""
    from .models import User
    qs = User.objects.filter(role=User.Role.STUDENT).select_related("school")
    if user.is_owner or user.is_instructor:
        return qs
    if user.is_school_admin and user.school_id:
        return qs.filter(school_id=user.school_id)
    return qs.none()


def can_view_student(user, student):
    return user.pk == student.pk or visible_students(user).filter(pk=student.pk).exists()
