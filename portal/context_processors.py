def nav_counts(request):
    """Badge on the Doubts nav link: unanswered queue for staff, freshly answered doubts for students."""
    u = getattr(request, "user", None)
    if not u or not u.is_authenticated or u.must_change_password:
        return {}
    from courses.doubts import visible_doubts
    if u.is_student:
        n = u.doubts.filter(is_resolved=False, has_staff_reply=True).count()
    else:
        n = visible_doubts(u).filter(is_resolved=False, has_staff_reply=False).count()
    return {"nav_doubts": n}
