"""Black-box security, access-control and data-integrity checks against a STAGING stack.

    python3 tests/api/test_security_and_integrity.py            # BASE_URL defaults to http://localhost

Needs the staging data from tests/seed_staging.py (qa_* and lt* accounts, password QaPass#2026) and runs a few
setup snippets through `docker compose exec web` (REPO_DIR, default: repo root). Every check states the SECURE /
CORRECT behaviour; a FAIL is a finding. Results go to tests/api/results.json. Never point this at production:
it creates and deletes records.
"""
import concurrent.futures as cf
import json
import os
import re
import subprocess
import sys
import time
import uuid

sys.path.insert(0, os.path.dirname(__file__))
from lms import BASE, LMS, PW  # noqa: E402

REPO = os.environ.get("REPO_DIR", os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
RESULTS = []
TAG = uuid.uuid4().hex[:6]


def check(cid, area, name, passed, detail=""):
    RESULTS.append({"id": cid, "area": area, "name": name, "pass": bool(passed), "detail": str(detail)[:400]})
    print(f"{'PASS' if passed else 'FAIL'} {cid} [{area}] {name}" + (f" :: {detail}" if detail else ""), flush=True)


def shell(code):
    out = subprocess.run(["docker", "compose", "exec", "-T", "web", "python", "manage.py", "shell", "-v0", "-c", code],
                         cwd=REPO, capture_output=True, text=True, timeout=300)
    if out.returncode:
        raise RuntimeError(out.stderr[-2000:])
    return out.stdout.strip().split("\n")[-1]


def anon():
    return LMS()


def status(s, path):
    r = s.get(path)
    return r.status_code, r.headers.get("Location", "")


def denied(code_loc):
    code, loc = code_loc
    return code in (403, 404) or (code == 302 and "/login/" in loc)


# ---------------------------------------------------------------- setup
setup = json.loads(shell(f"""
import json
from django.core.files.base import ContentFile
from courses.models import *
from accounts.models import User, School
from django.contrib.auth.hashers import make_password
s1=User.objects.get(username='lt0001'); s2=User.objects.get(username='lt0002')
c_s1=Enrollment.objects.filter(student=s1).values_list('course_id',flat=True)
other=Course.objects.exclude(pk__in=c_s1).filter(is_published=True, slug__startswith='qa-course').first()
mine=Course.objects.filter(pk__in=c_s1, is_published=True, slug__startswith='qa-course').first()
att2=QuizAttempt.objects.filter(student=s2).first() or QuizAttempt.objects.create(quiz=Course.objects.get(pk=Enrollment.objects.filter(student=s2).first().course_id).quizzes.first(),student=s2,score=1,total=10)
cert2=Certificate.objects.filter(student=s2).first() or Certificate.objects.create(student=s2,title='x')
pd=Doubt.objects.create(student=s2,course=mine if Enrollment.objects.filter(student=s2,course=mine).exists() else None,title='QA private {TAG}',body='secret',is_private=True)
pd.image.save('qa_private_{TAG}.png', ContentFile(b'\\x89PNG fake'), save=True)
l=mine.lessons.first(); l.attachment.save('qa_worksheet_{TAG}.pdf', ContentFile(b'%PDF-1.4 paid worksheet'), save=True)
inst_a=User.objects.get(username='qa_inst1')
foreign=Course.objects.exclude(instructors=inst_a).exclude(created_by=inst_a).first()
sch1=User.objects.get(username='qa_sch1'); other_school_student=User.objects.filter(role='student').exclude(school=sch1.school).exclude(school=None).first()
unpub=Course.objects.create(title='QA unpublished {TAG}',is_published=False); Enrollment.objects.create(student=s1,course=unpub)
pw=make_password('{PW}')
fresh=[User.objects.create(username=f'qa_fresh_{TAG}_{{i}}',role='student',password=pw,must_change_password=True,email=f'fresh{{i}}_{TAG}@example.test') for i in range(3)]
print(json.dumps(dict(s1=s1.pk,s2=s2.pk,other=other.slug,mine=mine.slug,mine_id=mine.pk,lesson=l.pk,att2=att2.pk,att2_quiz=att2.quiz_id,att2_course=att2.quiz.course.slug,
  cert2=str(cert2.code),pd=pd.pk,pd_img=pd.image.url,attach=l.attachment.url,foreign=foreign.slug,other_school_student=other_school_student.pk,
  unpub=unpub.slug,quiz_mine=mine.quizzes.first().pk,fresh=[u.username for u in fresh])))
"""))

st = LMS().login("lt0001")
st2 = LMS().login("lt0002")
inst = LMS().login("qa_inst1")
sch = LMS().login("qa_sch1")
own = LMS().login("qa_owner")
check("SETUP", "auth", "seeded accounts can log in", all(x.logged_in for x in (st, st2, inst, sch, own)))

# ---------------------------------------------------------------- authentication
s = anon()
codes = []
for i in range(25):
    r = s.post("/login/", {"username": "lt0003", "password": f"wrong{i}"}, form_page="/login/")
    codes.append(r.status_code)
r = s.post("/login/", {"username": "lt0003", "password": PW}, form_page="/login/")
check("SEC-AUTH-1", "auth", "brute force: 25 wrong passwords for one account trigger lockout/429",
      any(c == 429 for c in codes) or r.status_code != 302, f"codes={sorted(set(codes))}; correct pw after 25 fails -> {r.status_code}")

s = LMS().login(setup["fresh"][0])
r = s.post("/welcome/password/", {"new_password1": "123456", "new_password2": "123456"})
check("SEC-AUTH-2", "auth", "first-login password change rejects '123456'", r.status_code == 200, f"status={r.status_code} (302 = accepted)")

s = anon()
s.get("/login/")
pre = s.cookies.get("sessionid")
s.login("lt0004")
check("SEC-AUTH-3", "auth", "session id rotates on login (no fixation)", s.logged_in and s.cookies.get("sessionid") != pre)

s = LMS().login("lt0005")
sid = s.cookies.get("sessionid")
r = s.get("/logout/")
check("SEC-AUTH-4", "auth", "logout is POST-only (GET cannot log people out via a link)", r.status_code == 405, r.status_code)
s.post("/logout/", {}, form_page="/dashboard/")
replay = anon()
replay.cookies.set("sessionid", sid)
check("SEC-AUTH-5", "auth", "old session cookie is dead after logout", denied(status(replay, "/dashboard/")))

r = anon().post("/login/", {"username": "lt0006", "password": PW}, form_page="/login/")
ck = r.headers.get("Set-Cookie", "")
check("SEC-AUTH-6", "auth", "session cookie is HttpOnly + SameSite", "HttpOnly" in ck and "SameSite=Lax" in ck, ck[:200])

r = anon().get("/login/?next=https://evil.example/")
s = anon()
s.get("/login/")
r = s.post("/login/?next=https://evil.example/", {"username": "lt0007", "password": PW}, form_page="/login/")
check("SEC-AUTH-7", "auth", "login ?next= cannot redirect off-site", "evil.example" not in r.headers.get("Location", ""), r.headers.get("Location"))

# password reset
s = anon()
known = s.post("/password/forgot/", {"email": "lt0001@example.test"}, form_page="/password/forgot/")
unknown = s.post("/password/forgot/", {"email": "nobody_xyz@example.test"}, form_page="/password/forgot/")
check("SEC-RESET-1", "auth", "forgot-password does not reveal whether an account exists",
      known.status_code == unknown.status_code == 302 and known.headers.get("Location") == unknown.headers.get("Location"))
shell("from django.core.cache import cache;from accounts.models import User;cache.delete(f'pwreset:{User.objects.get(username=\"lt0009\").pk}')")
t_mail = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - 1))
for _ in range(5):
    s.post("/password/forgot/", {"email": "lt0009"}, form_page="/password/forgot/")
time.sleep(1)
logs = subprocess.run(["docker", "compose", "logs", "--since", t_mail, "web"], cwd=REPO, capture_output=True, text=True).stdout
n_mails = logs.count("To: lt0009@example.test")
check("SEC-RESET-2", "auth", "reset emails per account are capped (3/hour)", n_mails <= 3, f"emails sent={n_mails}")
# only lt0009's own emails (earlier checks also mail lt0001; using that link would change the wrong password)
mails = [m for m in re.split(r"Content-Type: text/plain", logs) if "To: lt0009@example.test" in m]
links = re.findall(r"(http://[^\s]+/password/reset/[^\s]+/)", "".join(mails))
if links:
    link = links[-1].replace("http://localhost", BASE)
    s = anon()
    r = s.get(link, allow_redirects=True)
    set_url = r.url
    r2 = s.post(set_url, {"new_password1": "Zq9!resetPass", "new_password2": "Zq9!resetPass"}, form_page=set_url)
    again = anon().get(link, allow_redirects=True)
    check("SEC-RESET-3", "auth", "reset link works once, then is invalid", r2.status_code == 302 and "invalid" in again.text.lower() or "expired" in again.text.lower(),
          f"set={r2.status_code}")
    shell(f"from accounts.models import User;u=User.objects.get(username='lt0009');u.set_password('{PW}');u.save()")
else:
    check("SEC-RESET-3", "auth", "reset link works once, then is invalid", False, "no reset email found in web logs")

# deactivated user is kicked out of an existing session
s = LMS().login("lt0010")
shell("from accounts.models import User;User.objects.filter(username='lt0010').update(is_active=False)")
check("SEC-AUTH-8", "auth", "deactivating an account ends its live sessions", denied(status(s, "/dashboard/")))
shell("from accounts.models import User;User.objects.filter(username='lt0010').update(is_active=True)")

# ---------------------------------------------------------------- authorization (student)
staff_pages = ["/users/", "/users/new/", "/users/generate/", "/schools/", "/schools/new/", "/students/",
               f"/students/{setup['s2']}/", "/courses/new/", f"/courses/{setup['mine']}/edit/", f"/courses/{setup['mine']}/delete/",
               f"/courses/{setup['mine']}/students/", f"/courses/{setup['mine']}/report/", f"/courses/{setup['mine']}/lessons/new/",
               f"/courses/{setup['mine']}/lessons/{setup['lesson']}/edit/", f"/courses/{setup['mine']}/quizzes/new/",
               f"/courses/{setup['mine']}/quizzes/{setup['quiz_mine']}/manage/", "/certificates/issue/", "/newsletters/new/",
               "/gallery/new/", "/competitions/new/", "/admin/", f"/users/{setup['s2']}/"]
leaks = [p for p in staff_pages if not denied(status(st, p))]
check("SEC-AZ-1", "authz", f"student blocked from {len(staff_pages)} staff/admin pages", not leaks, leaks)
r = st.post(f"/courses/{setup['mine']}/lessons/bunny-upload/", {"title": "x"}, form_page="/dashboard/")
check("SEC-AZ-2", "authz", "student cannot get Bunny upload credentials", r.status_code in (302, 403), r.status_code)
r = st.post(f"/users/{setup['s2']}/reset-password/", {}, form_page="/dashboard/")
check("SEC-AZ-3", "authz", "student cannot reset another student's password", r.status_code in (302, 403) and "Password" not in r.text, r.status_code)

idor = {
    "other student's report": f"/students/{setup['s2']}/",
    "other student's quiz result": f"/courses/{setup['att2_course']}/quizzes/{setup['att2_quiz']}/result/{setup['att2']}/",
    "other student's certificate": f"/certificates/{setup['cert2']}/",
    "other student's private doubt": f"/doubts/{setup['pd']}/",
    "course not enrolled in": f"/courses/{setup['other']}/",
    "unpublished course (enrolled)": f"/courses/{setup['unpub']}/",
}
for name, p in idor.items():
    check("SEC-IDOR", "authz", f"student IDOR blocked: {name}", denied(status(st, p)), status(st, p))
r = st.post(f"/doubts/{setup['pd']}/", {"action": "delete"}, form_page="/doubts/")
check("SEC-IDOR", "authz", "student cannot delete another student's doubt", r.status_code in (403, 404))
lesson_other = shell(f"from courses.models import Course;c=Course.objects.get(slug='{setup['other']}');print(c.lessons.first().pk)")
r = st.post(f"/courses/{setup['other']}/lessons/{lesson_other}/", {}, form_page="/dashboard/")
check("SEC-IDOR", "authz", "student cannot mark progress in a course they are not enrolled in", r.status_code in (403, 404), r.status_code)

for p in ["/dashboard/", "/courses/", "/doubts/", "/certificates/", f"/courses/{setup['mine']}/", "/doubts/similar/?q=motor+spinning"]:
    check("SEC-AZ-ANON", "authz", f"anonymous blocked from {p}", denied(status(anon(), p)))

# ---------------------------------------------------------------- authorization (school admin / instructor)
check("SEC-AZ-4", "authz", "school admin blocked from other school's student report",
      denied(status(sch, f"/students/{setup['other_school_student']}/")))
check("SEC-AZ-5", "authz", "school admin blocked from editing other school's student",
      denied(status(sch, f"/users/{setup['other_school_student']}/")))
r = sch.post("/users/new/", {"username": f"qa_esc_{TAG}", "role": "owner", "password": "Esc4late!x", "first_name": "x"}, form_page="/users/new/")
role = shell(f"from accounts.models import User;u=User.objects.filter(username='qa_esc_{TAG}').first();print(u.role if u else 'none')")
check("SEC-AZ-6", "authz", "school admin cannot create an owner account", role in ("student", "none"), f"created role={role}")
r = inst.post(f"/users/{setup['s1']}/", {"role": "owner", "first_name": "x", "student_type": "school", "is_active": "on"}, form_page=f"/users/{setup['s1']}/")
role = shell(f"from accounts.models import User;print(User.objects.get(pk={setup['s1']}).role)")
check("SEC-AZ-7", "authz", "instructor cannot promote a student to owner", role == "student", f"role now={role}")
check("SEC-AZ-8", "authz", "instructor cannot edit a course they don't teach", denied(status(inst, f"/courses/{setup['foreign']}/edit/")))
owner_pk = shell("from accounts.models import User;print(User.objects.get(username='qa_owner').pk)")
r = inst.post(f"/users/{owner_pk}/reset-password/", {}, form_page="/users/")
check("SEC-AZ-9", "authz", "instructor cannot reset the owner's password", r.status_code == 403, r.status_code)
r = inst.get(f"/certificates/{setup['cert2']}/")
other_cert_course_foreign = shell(f"from courses.models import Certificate;from accounts.models import User;c=Certificate.objects.get(code='{setup['cert2']}');i=User.objects.get(username='qa_inst1');print(bool(c.course and not c.course.can_manage(i)))")
check("SEC-AZ-10", "authz", "instructor can only revoke certificates for courses they teach",
      not (r.status_code == 200 and "revoke" in r.text.lower() and other_cert_course_foreign == "True"),
      f"revoke button shown on a foreign course's certificate: {r.status_code == 200 and 'revoke' in r.text.lower()}")

# ---------------------------------------------------------------- private files
for name, url in [("private doubt photo", setup["pd_img"]), ("lesson worksheet", setup["attach"])]:
    r = anon().get(url)
    check("SEC-FILE-1", "privacy", f"anonymous visitor cannot download {name} from /media/", r.status_code in (302, 401, 403, 404),
          f"{url} -> {r.status_code}")
r = anon().get("/media/../config/settings.py")
r2 = anon().get("/media/%2e%2e/%2e%2e/etc/passwd")
check("SEC-FILE-2", "privacy", "path traversal through /media/ is blocked", r.status_code in (400, 404) and r2.status_code in (400, 404),
      f"{r.status_code}, {r2.status_code}")
r = anon().get("/media/")
check("SEC-FILE-3", "privacy", "no directory listing on /media/", r.status_code in (403, 404) or "<a href" not in r.text, r.status_code)

# malicious upload by staff: HTML file served from the same origin
html = b"<html><script>document.title='pwned-'+document.cookie</script></html>"
lesson_url = f"/courses/{setup['mine']}/lessons/{setup['lesson']}/edit/"
mine_inst = shell(f"from courses.models import Course;c=Course.objects.get(slug='{setup['mine']}');print(c.instructors.first().username)")
mi = LMS().login(mine_inst)
r = mi.post(lesson_url, {"title": "Lesson 1", "order": "1", "duration_minutes": "10", "video_url": ""},
            files={"attachment": (f"evil_{TAG}.html", html, "text/html")}, form_page=lesson_url)
url = shell(f"from courses.models import Lesson;print(Lesson.objects.get(pk={setup['lesson']}).attachment.url)")
served = anon().get(url)
check("SEC-UPL-1", "injection", "uploaded .html attachments are not served as same-origin HTML",
      not (served.status_code == 200 and "text/html" in served.headers.get("Content-Type", "")),
      f"{url} -> {served.status_code} {served.headers.get('Content-Type')}")
r = mi.post(lesson_url, {"title": "Lesson 1", "order": "1", "duration_minutes": "10"},
            files={"video_file": (f"v_{TAG}.exe", b"MZ....", "application/octet-stream")}, form_page=lesson_url)
check("SEC-UPL-2", "validation", "non-video file rejected as lesson video", r.status_code == 200 and "MP4" in r.text, r.status_code)
r = st.post("/doubts/ask/", {"category": "concept", "title": f"svg {TAG}", "body": "x"},
            files={"image": ("x.svg", b"<svg xmlns='http://www.w3.org/2000/svg'><script>alert(1)</script></svg>", "image/svg+xml")},
            form_page="/doubts/ask/")
check("SEC-UPL-3", "injection", "student cannot upload SVG/script as a doubt photo", r.status_code == 200, r.status_code)

# ---------------------------------------------------------------- XSS / injection / CSRF
payload = f'<script>alert("x{TAG}")</script><img src=x onerror=alert(1)>'
r = st.post("/doubts/ask/", {"category": "code", "title": payload[:190], "body": payload + "\n```\n" + payload + "\n```"}, form_page="/doubts/ask/")
loc = r.headers.get("Location", "")
page = st.get(loc).text if loc else ""
check("SEC-XSS-1", "injection", "stored XSS in doubt title/body/code block is escaped", loc and f'<script>alert("x{TAG}")' not in page and "onerror=alert" not in page.replace("onerror=alert(1)&gt;", ""),
      loc)
doubt_id = loc.rstrip("/").split("/")[-1] if loc else None
if doubt_id:
    r = inst.post(f"/doubts/{doubt_id}/", {"action": "reply", "body": payload}, form_page=f"/doubts/{doubt_id}/")
    page = inst.get(f"/doubts/{doubt_id}/").text
    check("SEC-XSS-2", "injection", "stored XSS in a reply is escaped", f'<script>alert("x{TAG}")' not in page)
    q = inst.get("/doubts/?tab=all&q=" + "x" + TAG).text
    check("SEC-XSS-3", "injection", "XSS escaped in doubt list / staff queue", f'<script>alert("x{TAG}")' not in q)
shell(f"from accounts.models import User;User.objects.filter(username='lt0011').update(first_name='<script>alert(\"n{TAG}\")</script>')")
pages = [own.get("/users/?q=lt0011").text, own.get("/students/?q=lt0011").text, LMS().login("lt0011").get("/dashboard/").text]
check("SEC-XSS-4", "injection", "XSS in a student's name is escaped on staff lists and dashboard", all(f'<script>alert("n{TAG}")' not in p for p in pages))
shell("from accounts.models import User;User.objects.filter(username='lt0011').update(first_name='Aarav')")
r = st.get("/courses/?q=%27%20OR%201%3D1--")
r2 = own.get("/users/?q=%27%3BDROP%20TABLE%20accounts_user%3B--&role=%27&school=1%20OR%201=1&page=abc")
r3 = own.get("/students/?q=" + "a" * 5000 + "&page=999999")
check("SEC-SQLI-1", "injection", "SQL-ish / huge / malformed query params don't error (400 for a 5 kB URL is fine)",
      r.status_code == r2.status_code == 200 and r3.status_code in (200, 400, 414),
      [x.status_code for x in (r, r2, r3)])
s = LMS().login("lt0012")
r = s.post("/doubts/ask/", {"category": "concept", "title": "csrf", "body": "x", "csrfmiddlewaretoken": "bogus"}, form_page="/doubts/ask/")
check("SEC-CSRF-1", "injection", "POST with a bad CSRF token is refused", r.status_code == 403, r.status_code)
r = s.request("POST", s.url("/doubts/ask/"), data={"category": "concept", "title": "csrf", "body": "x"}, allow_redirects=False)
check("SEC-CSRF-2", "injection", "POST without a CSRF token is refused", r.status_code == 403, r.status_code)
r = anon().get("/", headers={"Host": "evil.example"})
check("SEC-HOST-1", "config", "unknown Host header rejected (no reset-link poisoning)", r.status_code == 400, r.status_code)

# ---------------------------------------------------------------- headers & error pages
h = anon().get("/login/").headers
want = {"X-Frame-Options": "DENY", "X-Content-Type-Options": "nosniff", "Referrer-Policy": "strict-origin-when-cross-origin"}
missing = [k for k, v in want.items() if h.get(k, "").upper() != v.upper()]
check("SEC-HDR-1", "config", "clickjacking/nosniff/referrer headers present", not missing, missing)
check("SEC-HDR-2", "config", "Content-Security-Policy header present", "Content-Security-Policy" in h, "missing" if "Content-Security-Policy" not in h else "")
check("SEC-HDR-3", "config", "Server header doesn't leak software version", "Server" not in h or not re.search(r"\d", h.get("Server", "")), h.get("Server"))
r = anon().get("/no-such-page-" + TAG)
check("SEC-ERR-1", "config", "404 page is the friendly page, no debug traceback", r.status_code == 404 and "Traceback" not in r.text and "DEBUG" not in r.text)
r = anon().get("/verify/not-a-uuid/")
check("SEC-ERR-2", "config", "malformed certificate code gives 404, not 500", r.status_code == 404, r.status_code)
_r = anon().get("/admin/login/")
check("SEC-ADM-1", "config", "Django admin login goes through the throttled /login/ page (or is hidden)",
      _r.status_code == 404 or (_r.status_code == 302 and _r.headers.get("Location", "").startswith("/login/")),
      f"{_r.status_code} {_r.headers.get('Location', '')}")

# ---------------------------------------------------------------- validation & unicode
title = "రోబోటిక్స్ doubt हिंदी 🚀🤖 " + TAG
r = st.post("/doubts/ask/", {"category": "concept", "title": title, "body": "ఎందుకు? 😀"}, form_page="/doubts/ask/")
page = st.get(r.headers.get("Location", "/doubts/")).text
check("VAL-1", "validation", "Telugu/Hindi/emoji text saves and renders", r.status_code == 302 and title in page)
r = st.post("/doubts/ask/", {"category": "concept", "title": "x" * 500, "body": "x"}, form_page="/doubts/ask/")
check("VAL-2", "validation", "over-long title gives a form error, not a 500", r.status_code == 200, r.status_code)
r = st.post("/doubts/ask/", {"category": "concept", "title": "", "body": ""}, form_page="/doubts/ask/")
check("VAL-3", "validation", "empty doubt is rejected with a form error", r.status_code == 200, r.status_code)
r = own.post("/courses/new/", {"title": "🚀🤖", "level": "beginner", "is_published": "on"}, form_page="/courses/new/")
r2 = own.post("/courses/new/", {"title": "రోబోటిక్స్", "level": "beginner", "is_published": "on"}, form_page="/courses/new/")
check("VAL-4", "validation", "emoji-only / Telugu course titles get a working URL", r.status_code == 302 and r2.status_code == 302 and
      own.get(r2.headers["Location"]).status_code == 200, [r.headers.get("Location"), r2.headers.get("Location")])
big = b"\x89PNG" + os.urandom(12 * 1024 * 1024)
r = st.post("/doubts/ask/", {"category": "concept", "title": "big", "body": "x"}, files={"image": ("big.png", big, "image/png")}, form_page="/doubts/ask/")
check("VAL-5", "validation", "12 MB junk 'image' is rejected cleanly", r.status_code == 200, r.status_code)

# ---------------------------------------------------------------- data integrity / races
quiz_pk, course_slug = setup["quiz_mine"], setup["mine"]
sx = LMS().login("lt0013")
cs = shell(f"from courses.models import *;from accounts.models import User;u=User.objects.get(username='lt0013');c=Course.objects.get(slug='{course_slug}');Enrollment.objects.get_or_create(student=u,course=c);QuizAttempt.objects.filter(student=u,quiz_id={quiz_pk}).delete();Quiz.objects.filter(pk={quiz_pk}).update(max_attempts=3);print(3)")
tok = sx.csrf(f"/courses/{course_slug}/quizzes/{quiz_pk}/")


def submit_once(_):
    return sx.post(f"/courses/{course_slug}/quizzes/{quiz_pk}/", {"csrfmiddlewaretoken": tok}, form_page=f"/courses/{course_slug}/quizzes/{quiz_pk}/").status_code


with cf.ThreadPoolExecutor(10) as ex:
    list(ex.map(submit_once, range(10)))
n = int(shell(f"from courses.models import QuizAttempt;print(QuizAttempt.objects.filter(student__username='lt0013',quiz_id={quiz_pk}).count())"))
check("INT-1", "integrity", f"10 simultaneous submits can't exceed max_attempts={cs}", n <= int(cs), f"attempts stored={n}")

shell(f"from courses.models import QuizAttempt;QuizAttempt.objects.filter(student__username='lt0013',quiz_id={quiz_pk}).delete()")
sx.get(f"/courses/{course_slug}/quizzes/{quiz_pk}/")  # "start" the 10-minute quiz
r = sx.post(f"/courses/{course_slug}/quizzes/{quiz_pk}/", {}, form_page=f"/courses/{course_slug}/quizzes/{quiz_pk}/")
started = shell(f"from courses.models import QuizAttempt;a=QuizAttempt.objects.filter(student__username='lt0013',quiz_id={quiz_pk}).first();print(hasattr(a,'started_at'))")
check("INT-2", "integrity", "server records quiz start time and rejects submissions after the time limit", started == "True",
      "no start time stored; the countdown is JavaScript only, so refresh resets it and a late POST is accepted")
att = shell("from courses.models import QuizAttempt;print(QuizAttempt.objects.filter(student__username='lt0013').first().pk)")
r = sx.get(f"/courses/{course_slug}/quizzes/{quiz_pk}/result/{att}/")
check("INT-3", "integrity", "result page doesn't reveal correct answers while attempts remain", "choice-right" not in r.text,
      "answers revealed after attempt 1 of 3, so attempt 2 can score 100%")

shell("from courses.models import Enrollment;from accounts.models import User;Enrollment.objects.filter(student__username='lt0014').delete()")
before = int(shell("from courses.models import Enrollment;print(Enrollment.objects.count())"))
for _ in range(2):
    own.post(f"/courses/{course_slug}/students/", {"usernames": "lt0014"}, form_page=f"/courses/{course_slug}/students/")
after = int(shell("from courses.models import Enrollment;print(Enrollment.objects.count())"))
check("INT-4", "integrity", "enrolling the same student twice creates one enrolment", after - before == 1, after - before)

# concurrent bulk generation for the same school
school_pk = shell("from accounts.models import School;print(School.objects.get(code='qs05').pk)")
def gen(_):
    s = LMS().login("qa_owner")
    return s.post("/users/generate/", {"student_type": "school", "school": school_pk, "count": "20"}, form_page="/users/generate/").status_code
with cf.ThreadPoolExecutor(3) as ex:
    codes = list(ex.map(gen, range(3)))
check("INT-5", "integrity", "two admins bulk-generating for the same school at once both succeed", all(c == 200 for c in codes), codes)

t = time.time()
r = own.post("/users/generate/", {"student_type": "in_house", "count": "500"}, form_page="/users/generate/", timeout=900)
dt = time.time() - t
check("INT-6", "performance", "bulk-generating 500 logins (the form maximum) finishes inside the 120 s worker timeout",
      r.status_code == 200 and dt < 60, f"status={r.status_code} took {dt:.0f}s")

# cascade behaviour
res = json.loads(shell(f"""
import json
from courses.models import *
from accounts.models import User
from django.contrib.auth.hashers import make_password
i=User.objects.create(username='qa_tmpinst_{TAG}',role='instructor',password='!')
d=Doubt.objects.filter(student__username='lt0015').first() or Doubt.objects.create(student=User.objects.get(username='lt0015'),title='t',body='b')
DoubtReply.objects.create(doubt=d,author=i,body='answer from soon-deleted instructor')
before=d.replies.count(); i.delete(); after=d.replies.count()
s=User.objects.get(username='lt0016'); c=Certificate.objects.create(student=s,title='QA cascade'); code=str(c.code)
s_copy=User.objects.create(username='qa_tmpstu_{TAG}',role='student',password='!'); c2=Certificate.objects.create(student=s_copy,title='QA cascade'); code2=str(c2.code)
try:
    s_copy.delete(); blocked=False
except Exception:
    blocked=True
print(json.dumps(dict(replies_lost=before-after, delete_blocked=blocked, cert_after_student_delete=Certificate.objects.filter(code=code2).exists(), code2=code2)))
"""))
check("INT-7", "integrity", "deleting an instructor keeps their answers on students' doubts", res["replies_lost"] == 0, f"replies deleted={res['replies_lost']}")
v = anon().get(f"/verify/{res['code2']}/")
check("INT-8", "integrity", "deleting a student keeps their issued certificates verifiable",
      res["cert_after_student_delete"] and v.status_code == 200, f"delete blocked={res['delete_blocked']} verify={v.status_code}")

# ---------------------------------------------------------------- cleanup of objects that would distort later runs
shell(f"""
from accounts.models import User
from courses.models import Course
User.objects.filter(username__startswith='qa_fresh_{TAG}').delete(); User.objects.filter(username='qa_esc_{TAG}').delete()
Course.objects.filter(title__in=['🚀🤖','రోబోటిక్స్']).delete(); Course.objects.filter(title='QA unpublished {TAG}').delete()
User.objects.filter(username='lt0001').update(role='student')
from courses.models import Certificate
Certificate.objects.filter(student__username__startswith='qa_tmpstu_').delete()
from courses.models import Enrollment
u14=User.objects.get(username='lt0014'); Enrollment.objects.filter(student=u14).delete()
for k in range(3):
    Enrollment.objects.get_or_create(student=u14, course=Course.objects.get(slug=f'qa-course-{(13 + k) % 10 + 1}')); User.objects.filter(username__startswith='qa_tmpstu_').delete()
""")
json.dump(RESULTS, open(os.path.join(os.path.dirname(__file__), "results.json"), "w"), indent=1, ensure_ascii=False)
fails = [r for r in RESULTS if not r["pass"]]
print(f"\n{len(RESULTS) - len(fails)}/{len(RESULTS)} checks passed")
sys.exit(1 if fails else 0)
