"""Upload spike, run WHILE a k6 browsing load is going (STAGING only):
  - one instructor uploads a large lesson MP4 through the normal lesson form (no Bunny), and
  - 40 students post doubts with a 3 MB photo inside the same ~30 s ("deadline rush").

    python3 tests/load/upload_spike.py /path/to/big.mp4
"""
import concurrent.futures as cf
import os
import re
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "api"))
from lms import LMS  # noqa: E402

video = sys.argv[1]


def noise_png(w=1000, h=1000):
    """A real ~3 MB PNG (random pixels don't compress), like a phone photo of a circuit."""
    import struct
    import zlib
    rows = b"".join(b"\x00" + os.urandom(w * 3) for _ in range(h))
    c = lambda t, d: struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xffffffff)
    return b"\x89PNG\r\n\x1a\n" + c(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)) + c(b"IDAT", zlib.compress(rows, 1)) + c(b"IEND", b"")


big_png = noise_png()


def instructor_upload():
    s = LMS().login("qa_inst3")  # teaches qa-course-2 in the seed data
    course = "qa-course-2"
    page = f"/courses/{course}/lessons/new/"
    t = time.time()
    with open(video, "rb") as f:
        r = s.post(page, {"title": "Load-test big MP4", "order": "99", "duration_minutes": "22"},
                   files={"video_file": ("chapter1.mp4", f, "video/mp4")}, form_page=page, timeout=1200)
    return ("instructor MP4 upload", f"{os.path.getsize(video) / 1e6:.0f} MB", r.status_code, round(time.time() - t, 1))


def student_doubt(i):
    s = LMS().login(f"lt{1200 + i:04d}")
    t = time.time()
    r = s.post("/doubts/ask/", {"category": "circuit", "title": f"Deadline doubt {i} motor driver", "body": "photo attached"},
               files={"image": (f"circuit{i}.png", big_png, "image/png")}, form_page="/doubts/ask/", timeout=300)
    return r.status_code, round(time.time() - t, 2)


with cf.ThreadPoolExecutor(41) as ex:
    big = ex.submit(instructor_upload)
    time.sleep(2)
    res = list(ex.map(student_doubt, range(40)))
    print(big.result())
codes = {}
for c, _ in res:
    codes[c] = codes.get(c, 0) + 1
ts = sorted(t for _, t in res)
print(f"40 doubt-photo uploads: status {codes}, p50 {ts[len(ts) // 2]} s, p95 {ts[int(len(ts) * .95) - 1]} s, max {ts[-1]} s")
