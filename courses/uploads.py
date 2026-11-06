"""Upload paths with unguessable names, so a file URL can't be found by guessing (e.g. IMG_0001.jpg).

Images get a random name; documents keep their original name inside a random folder, so downloads still look right.
These are plain functions (not lambdas) because migrations import them by name.
"""
import os
import re
import uuid


def _random_name(prefix, filename):
    ext = os.path.splitext(filename)[1].lower()[:10]
    return f"{prefix}{uuid.uuid4().hex}{ext}"


def _random_folder(prefix, filename):
    base = re.sub(r"[^\w.\- ]", "_", os.path.basename(filename)).strip() or "file"
    return f"{prefix}{uuid.uuid4().hex[:16]}/{base[-120:]}"


def doubt_image(instance, filename):
    return _random_name("doubts/", filename)


def reply_image(instance, filename):
    return _random_name("doubts/replies/", filename)


def quiz_image(instance, filename):
    return _random_name("quiz/", filename)


def lesson_video(instance, filename):
    return _random_folder("lessons/videos/", filename)


def lesson_attachment(instance, filename):
    return _random_folder("lessons/files/", filename)
