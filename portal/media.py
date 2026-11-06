"""Every uploaded file goes through a permission check before it's served.

Public:     course thumbnails, newsletter covers/PDFs, gallery photos, competition banners.
Protected:  lesson videos and worksheets (must be able to open the course), quiz images (the course, and the quiz
            must be published unless you manage it), doubt photos (must be able to see the doubt: private ones are
            only for the student and staff).

In production Django only decides; Caddy sends the bytes (fast, with range requests for video seeking) when the
response carries X-Accel-Redirect (see deploy/Caddyfile). Without Caddy (local runs) Django streams the file itself.
"""
import mimetypes
import os
import posixpath

from django.conf import settings
from django.contrib.auth.views import redirect_to_login
from django.http import FileResponse, Http404, HttpResponse

PUBLIC_PREFIXES = ("courses/thumbs/", "newsletters/", "gallery/", "competitions/")
DOWNLOAD_PREFIXES = ("lessons/files/",)  # always download, never render in the browser


def _allowed(user, name):
    from courses.doubts import visible_doubts
    from courses.models import Doubt, DoubtReply, Lesson, Question

    if name.startswith(PUBLIC_PREFIXES):
        return True
    if not user.is_authenticated:
        return None  # ask them to log in
    if name.startswith(("lessons/videos/", "lessons/files/")):
        lesson = Lesson.objects.select_related("course").filter(**{
            "video_file" if name.startswith("lessons/videos/") else "attachment": name}).first()
        return bool(lesson and lesson.course.can_view(user))
    if name.startswith("quiz/"):
        q = Question.objects.select_related("quiz__course").filter(image=name).first()
        return bool(q and q.quiz.course.can_view(user) and (q.quiz.is_published or q.quiz.course.can_manage(user)))
    if name.startswith("doubts/replies/"):
        r = DoubtReply.objects.filter(image=name).only("doubt_id").first()
        return bool(r and visible_doubts(user).filter(pk=r.doubt_id).exists())
    if name.startswith("doubts/"):
        return visible_doubts(user).filter(image=name).exists()
    return False


def serve_media(request, path):
    name = posixpath.normpath(path).lstrip("/")
    if name.startswith("..") or "/../" in f"/{name}/" or name in ("", "."):
        raise Http404
    ok = _allowed(request.user, name)
    if ok is None:
        return redirect_to_login(request.get_full_path())
    if not ok:
        raise Http404  # don't reveal whether a private file exists
    full = os.path.join(settings.MEDIA_ROOT, name)
    if not os.path.isfile(full):
        raise Http404
    public = name.startswith(PUBLIC_PREFIXES)
    if settings.MEDIA_ACCEL_REDIRECT:
        resp = HttpResponse()
        resp["X-Accel-Redirect"] = "/" + name
    else:
        resp = FileResponse(open(full, "rb"), content_type=mimetypes.guess_type(full)[0] or "application/octet-stream")
    resp["Cache-Control"] = "public, max-age=604800" if public else "private, max-age=3600"
    if name.startswith(DOWNLOAD_PREFIXES):
        resp["Content-Disposition"] = f'attachment; filename="{os.path.basename(name)}"'
    return resp
