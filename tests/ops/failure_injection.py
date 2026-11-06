"""Failure injection on STAGING: database outage, app restart and hard kill while students keep working.

    python3 tests/ops/failure_injection.py

A few logged-in students keep loading pages and submitting quizzes. We stop Postgres, restart and SIGKILL the web
container, and record what users see second by second, how long recovery takes, and whether any quiz submission
the user saw as successful is missing from the database afterwards.
"""
import os
import re
import subprocess
import sys
import threading
import time
from collections import Counter

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "api"))
from lms import LMS  # noqa: E402

REPO = os.environ.get("REPO_DIR", os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
log, acked = [], []
stop = threading.Event()


def dc(*args):
    return subprocess.run(["docker", "compose", *args], cwd=REPO, capture_output=True, text=True, timeout=180)


def worker(username):
    s = LMS().login(username)
    slug = None
    while not stop.is_set():
        try:
            if slug is None:
                html = s.get("/courses/").text
                slug = re.search(r'href="/courses/(qa-course-\d+)/"', html).group(1)
                quiz = re.search(rf"/courses/{slug}/quizzes/\d+/", s.get(f"/courses/{slug}/").text).group(0)
            r = s.get(quiz, timeout=15)
            if r.status_code == 302 and "/login/" in r.headers.get("Location", ""):
                log.append((time.time(), "logged-out")); s.login(username); continue
            tok = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', r.text)
            body = r.text
            ans = {m.group(1): m.group(2) for m in re.finditer(r'name="(q\d+)" value="(\d+)"', body)}
            p = s.post(quiz, {**ans, "csrfmiddlewaretoken": tok.group(1) if tok else ""}, form_page=quiz, timeout=15)
            ok = p.status_code == 302 and "/result/" in p.headers.get("Location", "")
            if ok:
                acked.append(int(p.headers["Location"].rstrip("/").split("/")[-1]))
            log.append((time.time(), r.status_code if r.status_code != 200 else p.status_code))
        except Exception as e:  # connection refused / reset while the app is down
            log.append((time.time(), type(e).__name__))
            time.sleep(0.5)
        time.sleep(0.3)


def window(t0, t1):
    return Counter(str(c) for t, c in log if t0 <= t < t1)


def recovery(after):
    good = [t for t, c in log if t > after and c == 302]
    return round(good[0] - after, 1) if good else None


threads = [threading.Thread(target=worker, args=(f"lt{1400 + i:04d}",), daemon=True) for i in range(6)]
for t in threads:
    t.start()
time.sleep(20)
events = []

t = time.time(); dc("stop", "db"); events.append(("Postgres stopped for 30 s", t)); time.sleep(30)
t2 = time.time(); dc("start", "db"); events.append(("Postgres started again", t2)); time.sleep(30)
t3 = time.time(); dc("restart", "web"); events.append(("web container restarted (graceful)", t3)); time.sleep(40)
t4 = time.time(); dc("kill", "-s", "KILL", "web"); dc("up", "-d", "--no-deps", "--pull", "never", "web"); events.append(("web SIGKILLed and started", t4))
time.sleep(40)
stop.set()
for th in threads:
    th.join(timeout=20)

print("| Event | What users got in the next 30 s | Recovered after |")
print("|---|---|---|")
for name, ts in events:
    print(f"| {name} | {dict(window(ts, ts + 30))} | {recovery(ts)} s |")
ids = ",".join(map(str, acked)) or "0"
stored = dc("exec", "-T", "web", "python", "manage.py", "shell", "-v0", "-c",
            f"from courses.models import QuizAttempt;print(QuizAttempt.objects.filter(pk__in=[{ids}]).count())").stdout.strip()
print(f"\nquiz submissions acknowledged to users: {len(acked)}; found in DB afterwards: {stored}")
r = LMS().get("/")
print("homepage after the tests:", r.status_code)
logs = dc("logs", "--since", "5m", "web").stdout
print("500 errors logged by Django:", logs.count("Internal Server Error"), "| OperationalError lines:", logs.count("OperationalError"))
