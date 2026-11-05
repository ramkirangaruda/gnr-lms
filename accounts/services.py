"""Account auto-generation: readable usernames and passwords, created in one transaction."""
import base64
import csv
import io
import re
import secrets

from django.db import transaction
from django.utils import timezone

from .models import User

# No look-alike characters (0/O, 1/l/I) so kids can type passwords easily.
_ALPHABET = "abcdefghjkmnpqrstuvwxyz23456789"


def random_password(length=8):
    return "".join(secrets.choice(_ALPHABET) for _ in range(length))


def username_prefix(student_type, school=None):
    yy = timezone.localdate().strftime("%y")
    code = (school.code if school else "gnr").lower()
    code = re.sub(r"[^a-z0-9]", "", code) or "gnr"
    return f"{code}{yy}"


def _next_seq(prefix):
    nums = [int(m.group(1)) for u in User.objects.filter(username__startswith=prefix).values_list("username", flat=True)
            if (m := re.fullmatch(re.escape(prefix) + r"(\d{4,})", u))]
    return max(nums, default=0) + 1


@transaction.atomic
def bulk_create_students(rows, student_type, school=None, grade="", batch="", courses=()):
    """Create one student per row. Returns a list of (user, plain_password)."""
    from courses.models import Enrollment

    prefix = username_prefix(student_type, school)
    seq = _next_seq(prefix)
    created, users = [], []
    for r in rows:
        password = random_password()
        u = User(
            username=f"{prefix}{seq:04d}",
            first_name=r.get("first_name", "")[:150],
            last_name=r.get("last_name", "")[:150],
            email=r.get("email", "")[:254],
            phone=r.get("phone", "")[:20],
            grade=(r.get("grade") or grade)[:20],
            batch=(r.get("batch") or batch)[:50],
            role=User.Role.STUDENT,
            student_type=student_type,
            school=school if student_type == User.StudentType.SCHOOL else None,
            must_change_password=True,
        )
        u.set_password(password)
        users.append(u)
        created.append((u, password))
        seq += 1
    User.objects.bulk_create(users, batch_size=500)
    if courses:
        # bulk_create on PostgreSQL/SQLite returns PKs; re-fetch to be safe on other DBs.
        saved = User.objects.filter(username__in=[u.username for u in users])
        Enrollment.objects.bulk_create(
            [Enrollment(student=u, course=c) for u in saved for c in courses], ignore_conflicts=True)
    return created


def credentials_csv_data_uri(created):
    """CSV of the new credentials as a data: URI, so plain passwords are never stored on the server."""
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Name", "Username", "Password", "School", "Grade", "Batch"])
    for u, pw in created:
        w.writerow([u.get_full_name(), u.username, pw, u.school.name if u.school else "GNR in-house", u.grade, u.batch])
    return "data:text/csv;base64," + base64.b64encode(buf.getvalue().encode()).decode()
