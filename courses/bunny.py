"""Bunny Stream integration: create videos, sign browser (TUS) uploads, and sign playback URLs.

The Bunny API key never leaves the server. Instructors upload straight from their browser to Bunny
using a short-lived signature, so large videos never pass through Django or nginx.
Docs: https://docs.bunny.net/reference/tus-resumable-uploads and
https://docs.bunny.net/docs/stream-embed-token-authentication
"""
import hashlib
import json
import logging
import re
import time
import urllib.error
import urllib.request

from django.conf import settings
from django.core import signing

log = logging.getLogger(__name__)

API_BASE = "https://video.bunnycdn.com"
TUS_ENDPOINT = f"{API_BASE}/tusupload"
EMBED_BASE = "https://iframe.mediadelivery.net/embed"
VIDEO_ID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
VIDEO_ID_RE_ANY = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
UPLOAD_TOKEN_SALT = "courses.bunny.upload"
UPLOAD_TOKEN_MAX_AGE = 24 * 3600


class BunnyError(Exception):
    pass


def is_enabled():
    """Uploads need both the library ID and the API key."""
    return bool(settings.BUNNY_STREAM_LIBRARY_ID and settings.BUNNY_STREAM_API_KEY)


def _request(method, path, payload=None):
    if not is_enabled():
        raise BunnyError("Bunny Stream is not configured.")
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(
        f"{API_BASE}/library/{settings.BUNNY_STREAM_LIBRARY_ID}{path}", data=data, method=method,
        headers={"AccessKey": settings.BUNNY_STREAM_API_KEY, "Accept": "application/json",
                 "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            body = resp.read()
    except (urllib.error.URLError, TimeoutError) as e:
        raise BunnyError(f"Bunny Stream request failed: {e}") from e
    return json.loads(body) if body else {}


def create_video(title):
    """Create an empty video in the library and return its GUID."""
    guid = _request("POST", "/videos", {"title": (title or "Lesson video")[:200]}).get("guid", "")
    if not VIDEO_ID_RE.match(guid):
        raise BunnyError("Bunny Stream did not return a video ID.")
    return guid


def delete_video(video_id):
    """Best effort: a failed delete only leaves an orphan video in Bunny, so log and carry on."""
    if not (is_enabled() and video_id and VIDEO_ID_RE.match(video_id)):
        return
    try:
        _request("DELETE", f"/videos/{video_id}")
    except BunnyError:
        log.warning("Could not delete Bunny video %s", video_id, exc_info=True)


def tus_credentials(video_id, ttl=None):
    """Headers the browser sends to Bunny's TUS endpoint. Valid for `ttl` seconds."""
    expires = int(time.time()) + (ttl or settings.BUNNY_STREAM_UPLOAD_TTL)
    lib = str(settings.BUNNY_STREAM_LIBRARY_ID)
    signature = hashlib.sha256(f"{lib}{settings.BUNNY_STREAM_API_KEY}{expires}{video_id}".encode()).hexdigest()
    return {"endpoint": TUS_ENDPOINT, "library_id": lib, "video_id": video_id,
            "expires": expires, "signature": signature}


def make_upload_token(course_id, video_id):
    """Signed proof that this server created `video_id` for this course, so a form can't attach someone else's video."""
    return signing.dumps({"c": course_id, "v": video_id}, salt=UPLOAD_TOKEN_SALT)


def read_upload_token(token, course_id):
    try:
        data = signing.loads(token, salt=UPLOAD_TOKEN_SALT, max_age=UPLOAD_TOKEN_MAX_AGE)
    except signing.BadSignature:
        return None
    if data.get("c") != course_id or not VIDEO_ID_RE.match(str(data.get("v", ""))):
        return None
    return data["v"]


def embed_url(video_id, ttl=None):
    """Player URL for a lesson page. Signed with the embed token key when one is configured."""
    lib = settings.BUNNY_STREAM_LIBRARY_ID
    if not (lib and video_id):
        return ""
    url = f"{EMBED_BASE}/{lib}/{video_id}"
    key = settings.BUNNY_STREAM_TOKEN_KEY
    if key:
        expires = int(time.time()) + (ttl or settings.BUNNY_STREAM_EMBED_TTL)
        token = hashlib.sha256(f"{key}{video_id}{expires}".encode()).hexdigest()
        return f"{url}?token={token}&expires={expires}&autoplay=false&preload=true&responsive=true"
    return f"{url}?autoplay=false&preload=true&responsive=true"
