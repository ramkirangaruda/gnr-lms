"""Slow down password guessing: after too many failed logins, an account (or an IP) must wait.

Counts live in the cache (Redis in production), so they are shared by all gunicorn workers.
"""
from django.conf import settings
from django.core.cache import cache


def _keys(username, ip):
    return f"loginfail:u:{(username or '').strip().lower()[:150]}", f"loginfail:ip:{ip or '-'}"


def client_ip(request):
    # Caddy sets X-Forwarded-For; only its first hop matters (Caddy is the only thing that can reach gunicorn).
    fwd = request.META.get("HTTP_X_FORWARDED_FOR", "")
    return (fwd.split(",")[0].strip() if fwd else request.META.get("REMOTE_ADDR", "")) or "-"


def is_locked(username, ip):
    ku, ki = _keys(username, ip)
    return (cache.get(ku, 0) >= settings.LOGIN_FAILS_PER_USER) or (cache.get(ki, 0) >= settings.LOGIN_FAILS_PER_IP)


def record_failure(username, ip):
    for key in _keys(username, ip):
        cache.add(key, 0, settings.LOGIN_LOCKOUT_SECONDS)
        try:
            cache.incr(key)
        except ValueError:  # expired between add and incr
            cache.set(key, 1, settings.LOGIN_LOCKOUT_SECONDS)


def clear(username):
    cache.delete(_keys(username, None)[0])
