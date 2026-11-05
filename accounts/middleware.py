from django.shortcuts import redirect
from django.urls import reverse


class ForcePasswordChangeMiddleware:
    """Auto-generated accounts must set their own password on first login."""
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        u = getattr(request, "user", None)
        if u and u.is_authenticated and u.must_change_password:
            allowed = (reverse("first_password"), reverse("logout"))
            if request.path not in allowed and not request.path.startswith(("/static/", "/media/")):
                return redirect("first_password")
        return self.get_response(request)
