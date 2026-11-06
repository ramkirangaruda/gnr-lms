# GNR LMS launch-readiness report

Tested 2026-11-06 on `main` (d26fc88: PR #1 Bunny video + PR #2 production Docker) plus PR #3 (forgot password, f88caaa).
Staging was the full Docker stack (Caddy, gunicorn, PostgreSQL 16, Redis) with the **whole stack pinned to 2 CPUs and
~4 GB RAM** to match the planned 2 vCPU / 4 GB VPS. The load generator ran on separate CPUs. All data was fake
(1,516 seeded accounts, 10 courses, 4,500 enrolments, about 23k lesson completions and 12k quiz attempts, 585 doubts). No real email was sent:
reset emails went to the container log. Bunny Stream was faked, because there's no account yet.

## 1. Verdict: **GO WITH FIXES**

1. Every role's core journey works end to end in a real browser (57/57), and all 37 unit tests pass on PostgreSQL. Access control held in every IDOR and role-escalation test I tried (34 checks).
2. Capacity is fine for the stated peak: 300 students browsing at once used about 30% of the 2 vCPUs, with page p95 under 50 ms and zero errors over a 30-minute soak (75k requests, no memory growth). 500 students submitting a quiz in the same minute took p95 19 ms.
3. What breaks first is **logins arriving all at once**. Each login costs about 0.2 s of CPU (password hashing), so 500 students pressing Login together wait up to about 45 s, and every other page slows down while that happens.
4. Two issues should block a public launch to children. There's **no login rate limiting** while weak passwords like `123456` and predictable usernames (`dps260001`…) are allowed. And **uploaded files (including "private" doubt photos) can be downloaded without logging in** by anyone who has the URL.
5. Operations are thin. Backups work (restore verified) but stay on the same server. Nothing alerts anyone at 2 AM, container logs grow without limit, and the quiz timer and answer review make quiz scores easy to game.

All of the must-fix items are small, contained code or config changes. I estimate 1–2 days of work. **Nothing has been fixed yet.**

## 2. Issue table

Severity: **Blocker** = fix before real users. **High** = fix before launch, or before relying on that feature.
**Medium** = fix soon after launch. **Low** = backlog. Check IDs refer to `tests/api/test_security_and_integrity.py`.

| ID | Sev | Area | Steps to reproduce | Expected vs actual | Evidence | Suggested fix |
|---|---|---|---|---|---|---|
| B-1 | **Blocker** | Auth | POST `/login/` 25× with wrong passwords for `lt0003`, then the right one. Separately, at first login set the password to `123456`. | Expected lockout or 429 after a few failures, and weak passwords rejected. Actual: all 25 attempts got a normal 200, the right password still logged in, and `123456` was accepted. Student usernames are sequential (`<school><yy><nnnn>`), so an attacker can try common passwords on every account. `/admin/login/` has the same problem. | SEC-AUTH-1, SEC-AUTH-2, SEC-ADM-1 | Throttle failed logins per username and per IP (e.g. django-axes, or a cache counter: 10 failures in 15 min → wait). Add `CommonPasswordValidator` + `NumericPasswordValidator`, min length 8. `ForcedPasswordChangeForm` must call `validate_password()` (today it only checks length ≥ 6). |
| B-2 | **Blocker** | Privacy | Student posts a *private* doubt with a photo. Log out and open the photo's `/media/doubts/…` URL. Do the same with a lesson worksheet. | Expected: login and permission required. Actual: **200 for anyone**. Caddy serves `/media/` straight from disk with no auth. File names are the original upload names (e.g. `IMG_20261106_1015.jpg`), so they're guessable. This covers doubt photos (children's circuits, possibly faces), worksheets, quiz images (which leak quiz questions) and MP4 lessons. | SEC-FILE-1 | Serve `/media/` through a Django view that checks permission and hands the file to Caddy (or move uploads to private S3 with signed URLs, which `django-storages` already supports via `AWS_QUERYSTRING_AUTH`). At minimum, rename uploads to random UUID names. |
| H-1 | High | Quizzes | Open a 10-minute quiz, refresh, or POST the answers 2 hours later. | Expected: the server enforces the time limit. Actual: the countdown is JavaScript only. Refreshing resets it, and late POSTs are accepted. | INT-2, `quiz_take.html` | Store an attempt start time when the quiz opens, and reject or auto-score submissions after `time_limit + grace`. |
| H-2 | High | Quizzes | Take a quiz with 3 attempts and fail it. The result page shows every correct answer (✓). Retake it. | Expected: answers hidden while attempts remain (or a per-quiz setting). Actual: they're always shown, so attempt 2 scores 100%. | INT-3, `quiz_result.html` | Show correct answers only after the last attempt (or after a pass), controlled by a quiz option. |
| H-3 | High | Capacity | 500 students log in at the same moment (start of class). | Expected: a few seconds' wait. Actual: login p95 46 s, max 50 s. During the 1,000-user ramp minute, *all* pages went to p95 5–18 s. | §3 quiz-burst and ramp tables | Spread out class logins (2 weeks of session life already means most students don't log in again). Size to 4 vCPU if whole schools log in in the same minute. Don't lower the hash cost. |
| H-4 | High | Ops | Break the app at 2 AM. | Expected: someone gets told. Actual: no health-check URL, no uptime monitor, no error alerts (no Sentry, no `ADMINS` email). Docker logs have no rotation (67 MB from about 3 h of testing, growing without limit). The 500 page is a bare "Server Error (500)". | `docker inspect` LogConfig `{}`; no `templates/500.html` | Add a `/healthz` view and a free uptime monitor (UptimeRobot / Better Stack). Add Sentry (free tier) or `ADMINS` + SMTP. Set `logging: {driver: json-file, options: {max-size: 10m, max-file: "5"}}` in compose. Add a friendly `500.html`. |
| H-5 | High | Backups | Run `deploy/backup.sh` and look at the result. | Expected: automatic, off-server copies. Actual: the restore **works** (row counts matched), but backups stay on the same disk. Media is a full tarball every night (589 MB with one video, × 14 days kept). One disk failure loses everything. | `tests/ops/backup_restore_check.sh` | Push `backups/` off the server nightly (rclone to Backblaze B2 / Google Drive / S3). Once videos live on Bunny, the media tarball stays small. |
| H-6 | High | Video | Plan for 300 students watching at once. | Bunny isn't set up yet. MP4s on the VPS don't scale: 300 × 1080p streams ≈ 780 Mbit/s, and 1,000 students × 4 h a month ≈ 4.6 TB, over the 4 TB a $24 droplet includes. A 416 MB upload through the app also ties up one of the 20 worker threads for the whole upload (13 s locally, minutes on school broadband). | Upload spike, §3 | Create the Bunny account before launch and use Bunny or YouTube for every lesson video. Keep the MP4 field for small clips only. |
| M-1 | Medium | Security | As an instructor, attach `evil.html` to a lesson and open it. | Expected: download only. Actual: served as `text/html` from the same origin, so a rogue or hacked instructor account can run script as the owner (stored XSS → create an owner login). | SEC-UPL-1 | Allow-list attachment extensions, and have Caddy send `Content-Disposition: attachment` + a CSP `sandbox` on `/media/`. B-2's fix covers this too. |
| M-2 | Medium | Integrity | 20 parallel POSTs of the same quiz (limit 3 attempts). | Expected: 3 stored. Actual: **4** stored in 3 of 5 trials (6 in one full-suite run). Check-then-insert race. | INT-1, race script | `select_for_update` on the student/quiz row, or count inside a transaction before insert. |
| M-3 | Medium | Integrity | Two staff bulk-generate logins for the same school at the same time. | Expected: both succeed. Actual: **500** for the second (`duplicate key … accounts_user_username_key`). | INT-5, web log | Take a per-prefix lock (`select_for_update` on School, or a Postgres advisory lock) in `bulk_create_students`, or retry on IntegrityError. |
| M-4 | Medium | Perf | Bulk-generate 500 accounts (form max). A 2,000-row CSV is allowed. | Actual: 87–89 s at idle for 500, so roughly 6 min for 2,000 (estimated, not run). The page looks hung and blocks a CPU. | INT-6 | Hash once per batch with a faster temporary hasher (the student must change the password at first login anyway), or run it as a background job. |
| M-5 | Medium | Integrity | Delete an instructor who answered doubts. | Expected: the answers stay. Actual: their **replies are deleted** (`DoubtReply.author` CASCADE). | INT-7 | `on_delete=SET_NULL` (show "former instructor"), and prefer deactivating over deleting. |
| M-6 | Medium | Integrity | Delete a student who has certificates. | Expected: the certificate stays verifiable. Actual: the certificate rows are deleted and the `/verify/` link says invalid. | INT-8 | `SET_NULL` + store the student name on the certificate, or block deleting students with certificates (deactivate them instead). |
| M-7 | Medium | Reliability | Sustained load for about 25 minutes. | Gunicorn `--max-requests 2000` recycles workers mid-keepalive, and Caddy got "connection reset" → 502 on about 1 in 10,000 requests (11 in the ramp), all POSTs. | Caddy error log, ramp table | Raise `--max-requests` (e.g. 20000) or drop it. Set Caddy `transport http { keepalive 30s }` lower than gunicorn's keep-alive. |
| M-8 | Medium | Privacy | Student uses a shared school-lab PC and closes the browser without logging out. | The session stays valid for 2 weeks, so the next child is logged in as them. (Config review, not a test failure.) | `settings.py` (no `SESSION_EXPIRE_AT_BROWSER_CLOSE`) | Session ends when the browser closes, or a short idle timeout, for students. Keep a longer session for staff if wanted. |
| L-1 | Low | AuthZ | Instructor A opens a certificate for a course they don't teach. | They can **revoke** it. Any instructor can delete any certificate. | SEC-AZ-10 | Allow revoke only if `course.can_manage(user)` (or owner only). |
| L-2 | Low | Headers | Look at the response headers. | No `Content-Security-Policy`. (X-Frame-Options, nosniff, Referrer-Policy, HSTS and Server-header removal are all fine.) | SEC-HDR-2 | Add a CSP in the Caddyfile (`script-src 'self'` plus YouTube/Bunny frames). |
| L-3 | Low | AuthZ | A school admin opens any course or quiz URL. | They can view unpublished courses and quiz questions for any course (not answers or other schools' students). | Manual check (200) | Restrict school admins to courses their students are enrolled in. |
| L-4 | Low | Uploads | Student uploads a huge image. | No per-file size cap below Caddy's 2 GB (a 12 MB fake image is rejected by Pillow, but a real 500 MB image would be accepted and stored). Review finding, not load-tested. | `forms.py` | Validate `image.size` ≤ 10 MB for doubt photos. Set `request_body max_size` per path in Caddy. |
| L-5 | Low | Supply chain | Look at `requirements.txt`. | Unpinned ranges (`Django>=5.2,<6`), so every rebuild can pull new versions nobody tested. `pip-audit`: no known vulnerabilities today. `npm audit`: 2 vite/esbuild dev-server advisories (build time only, not shipped). | pip-audit, npm audit | Pin with a lock file (`pip-compile`). Bump vite when convenient. |
| L-6 | Low | Accessibility | Run axe-core (WCAG A/AA) on key pages. | Colour contrast (`.eyebrow` and muted text, 10 pages). Password field has no `<label for>`. Filter `<select>`s unlabelled (/doubts/, /users/, /students/). Lesson video iframe has no `title` when it's YouTube. Course thumbnail links have no text. No skip link. Quiz images have `alt=""`. | `tests/e2e/a11y_results.json` | Small template fixes. Let instructors add alt text to quiz images. |
| L-7 | Low | UX | Staff open the doubt queue when 200+ doubts are waiting. | Oldest first, 20 per page, so a new doubt is on page 10+. (Found because the browser test couldn't see its new doubt.) | e2e walkthrough | Fine if FIFO is intended. Otherwise add a "newest" sort. |

**No problems found** in: session fixation, logout invalidation, POST-only logout, open redirects, reset-link reuse,
reset-email enumeration and rate limit, Host-header poisoning, CSRF, stored XSS (doubts, replies, names, code blocks),
SQL-ish and malformed parameters, path traversal, directory listing, SVG/script image upload, non-video "video" upload,
deactivated users' live sessions, duplicate enrolments, Telugu/Hindi/emoji text, over-long and empty input, N+1 queries
(query counts are flat), and DB-connection use (max 21 of 200).

## 3. Load test results

Setup: k6, with realistic students (log in once, then dashboard → course → lesson → mark complete → doubts, sometimes a quiz,
with 3–15 s of thinking between pages), plus 3 admins refreshing reports. All results are on the 2 CPU / ~4 GB stack. Full numbers are in
`tests/load/results-2026-11-06.md`.

**Ramp (steady minutes, users already logged in):**

| Concurrent users | Req/s | Page p50 | Page p95 | Page p99 | Errors | Web CPU (of 200%) | DB CPU |
|---|---|---|---|---|---|---|---|
| 50 | 7 | 20 ms | 46 ms | 217 ms | 0% | 11% | 12% |
| 200 | 28 | 19 ms | 39 ms | 65 ms | 0% | 38% | 12% |
| 300 | 41 | 23 ms | 48 ms | 67 ms | 0% | 57% | 16% |
| 500 | 68 | 24 ms | 64 ms | 96 ms | 0% | 87% | 30% |
| 1,000 | 110–114 | 1.1–1.7 s | 2.7–4.2 s | 3.2–4.9 s | 0.08% (502) | 151% | 40% |
| 1,500 | 114 | 5.8 s | 10 s | 14 s | 0.06% (502) | 150% (saturated) | 41% |

**The minute in each step when new users log in:** 200 new logins in a minute on top of 300 online users gave page p95 333 ms (fine).
500 new logins in a minute on top of 500 online users gave **p95 12–18 s, login p95 23 s**.

**Other scenarios:**

| Scenario | Result |
|---|---|
| Login storm: 1,059 different students in 5 min (5/s for the first minute, then 3/s), nothing else running | login p95 228 ms, 0 errors, web CPU 102% in minute 1 |
| 500 students log in at the same instant, then all submit the same quiz within one minute | login p95 **46 s** (max 50 s). Quiz submit p95 **19 ms**. **500/500 attempts stored**, 0 errors |
| Upload spike during 300-user soak: 416 MB lesson MP4 + 40 students posting 3 MB doubt photos at once | MP4 stored in 13 s (local network). Photos p95 5.2 s, all 40 saved. Other users' p99 rose to 2.7 s for that minute, then recovered |
| 30-min soak, 300 users + 2 admins | 75,167 requests, **0 errors**. Page p95 42–45 ms after warm-up. Web RAM flat at 314–318 MiB (no leak). DB 105–109 MiB. 21 DB connections |
| Admin reports during peak | p95 746 ms in the soak (the `/students/` overview with 1,500 students takes about 190 ms alone) |

**Bottleneck:** web CPU, and specifically PBKDF2 password hashing at login (1,000,000 iterations, about 0.18 s of CPU each).
Under steady browsing the 2 vCPUs reach about 85% at 500 users. RAM is not a constraint (web < 0.5 GB, DB about 0.1 GB of 4 GB), and neither are DB connections (21 of 200).
Two things weren't problems: no N+1 queries (`tests/perf/query_counts.py`: 3–14 queries per page, flat as the data grows), and static files are served with far-future caching.

**Recommended capacity**

| | Recommendation |
|---|---|
| Launch (≈300 peak, logins spread over a few minutes) | **2 vCPU / 4 GB is enough**, with about 40% CPU headroom at 300. Keep `WEB_CONCURRENCY=5` (5 workers × 4 threads). One Postgres on the same box is fine. |
| Whole schools logging in during the same minute, or > 500 active | **4 vCPU / 8 GB** (≈ $48/mo on DigitalOcean). Logins/s and browsing capacity roughly double. Set `WEB_CONCURRENCY=9`. |
| Video | Must be on Bunny (or YouTube), never the VPS (see H-6). |
| Not needed yet | Separate DB server, load balancer, CDN for static files (WhiteNoise + Caddy compression are enough at this size). |

## 4. Security findings, ranked by how easy they are to exploit

1. **B-1 Password guessing at scale.** No login needed, only a script. Usernames are predictable, there's no throttle, and `123456` is allowed.
2. **B-2 Unauthenticated file downloads.** Needs only a URL (shared, leaked or guessed). Exposes children's photos, worksheets and quiz questions.
3. **H-1/H-2 Quiz integrity.** Any student can do it with a refresh or a second attempt. Grading risk, not a data breach.
4. **M-1 Staff HTML upload → same-origin XSS.** Needs a malicious or compromised instructor account. Escalates to owner.
5. **M-2 Quiz attempt-limit race.** Needs deliberate parallel requests. Gives an extra attempt or two.
6. **M-8 Shared-PC sessions.** Needs physical access to a lab PC.
7. **L-1 Any instructor can revoke any certificate.** Insider only.
8. **L-2 No CSP / L-5 unpinned dependencies.** Defence in depth.

Secrets: no keys found in git history. `.env` is git-ignored, and the client bundle contains no secrets (the Bunny API key stays on the server and uploads use short-lived signatures).
Cookies: `HttpOnly` + `SameSite=Lax` confirmed. `Secure` is on by default in production (`SECURE_COOKIES=1`; staging turned it off for plain http).
`DEBUG` is off and the 404 page is friendly. `manage.py check --deploy` only flags HSTS and SSL-redirect, which Caddy handles.

## 5. Coverage matrix

| Feature / flow | Tested | How |
|---|---|---|
| Login, logout, first-login forced password change | ✅ | browser + HTTP |
| Forgot password by email (PR #3), rate limit, link reuse, staff reset | ✅ | HTTP, console email backend |
| Owner: schools, users, roles, bulk generate (count + CSV), credentials sheet | ✅ | browser + HTTP |
| School admin: own-school users and reports only | ✅ | browser + HTTP |
| Instructor: courses, lessons (YouTube, MP4, attachment), quizzes, doubt queue, certificates | ✅ | browser |
| Student: courses, lessons, progress, quizzes, results, doubts (photo, code, me-too, accept), certificates | ✅ | browser + load |
| Newsletters, gallery, competitions, public certificate verify | ✅ | crawl + HTTP |
| Access control / IDOR for every role | ✅ | 34 checks |
| Search, filters, pagination, malformed params | ✅ | HTTP |
| Unicode (Telugu, Hindi, emoji), long and empty input, bad files | ✅ | HTTP |
| Races (quiz attempts, enrolment, bulk generate), cascades on delete | ✅ | HTTP + DB |
| Load: ramp to 1,500, login storm, quiz burst, upload spike, 30-min soak | ✅ | k6 |
| DB outage, graceful app restart, SIGKILL, recovery, no lost submissions | ✅ | `tests/ops/failure_injection.py` |
| Backup + full restore, fresh deploy from an empty DB (23 migrations) | ✅ | scripts |
| Accessibility (axe WCAG A/AA), phone layouts (Pixel 7, iPhone 13 sizes), slow 3G | ✅ | Chromium only |
| **Bunny Stream for real** (upload, encode, signed playback) | ❌ | no account yet. Browser side tested against a fake Bunny |
| **Real HTTPS / Let's Encrypt, HSTS over TLS, Secure cookies over TLS** | ❌ | needs the real domain and server |
| **Real SMTP delivery** (Brevo), spam folder, 300/day limit | ❌ | console backend only. Volume is fine: resets only, 3/hour per account |
| **Safari, iOS Safari, Firefox, real Android Chrome** | ❌ | only Chromium is in this container. Phones were emulated by screen size and user agent, not engine |
| Real WAN latency, school-network upload speeds | ❌ | local network. Slow 3G emulated in the browser (login page 274 kB, 6.5 s first visit; cached pages 0.5 s) |
| Screen-reader walkthrough | ❌ | automated axe checks only |
| 24 h+ soak, disk filling over weeks | ❌ | 30-min soak only. Disk growth estimated from logs and backups |
| Assignments, grading of submissions, attendance, payments/fees, parent role, email verification, push/email notifications | n/a | not features of this LMS |

## 6. Pre-launch checklist

**Must fix before launch**
- [ ] B-1 Login throttling + password validators (incl. first-login form) + protect `/admin/`
- [ ] B-2 Permission-checked media (or private storage + random file names)
- [ ] H-4 `/healthz` + uptime monitor + error alerts (Sentry or email) + Docker log rotation + friendly 500 page
- [ ] H-5 Nightly off-server backup copy, plus one restore drill on the real server
- [ ] H-6 Bunny account set up and one real upload/playback tested (or every launch video on YouTube)
- [ ] H-1 / H-2 Server-side quiz timer and hidden answers, **if quiz scores count** for anything (certificates, school reports). Otherwise move to "soon after".
- [ ] Merge PR #3, set real SMTP, run `tests/` once against the real server after the first deploy

**Can follow in the first weeks**
- [ ] H-3 Plan class logins (stagger) or move to 4 vCPU before a whole-school event
- [ ] M-1 … M-8 (staff HTML uploads, attempt race, bulk-generate lock and speed, cascade deletes, worker recycling 502s, shared-PC sessions)
- [ ] L-1 … L-7 (certificate revoke rights, CSP, school-admin course scope, image size cap, pinned deps, accessibility fixes, doubt sort)

## Re-running

See `tests/README.md`. In short: start the QA stack with `tests/docker-compose.qa.yml`, seed with `tests/seed_staging.py`, then run
`tests/e2e/walkthrough.js`, `tests/api/test_security_and_integrity.py`, `tests/load/lms.js` (k6) and the `tests/ops/` scripts.
The security suite is written so each finding above is a FAIL today and should turn into a PASS when fixed.
