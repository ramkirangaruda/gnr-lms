# GNR Robotics LMS

Learning platform for GNR Robotics: owners, instructors, partner schools, and in-house + school students.

## Features

| Area | What it does |
|---|---|
| **Roles** | **Owner** (everything), **Instructor** (courses, quizzes, doubts, certificates, student logins), **School Admin** (sees only their own school's students and progress, can create logins for them), **Student** (in-house or school) |
| **Logins** | Create single logins; **auto-generate** hundreds of student accounts from a count or a CSV (usernames like `dps260001`, `gnr260001` for in-house); download the credentials as CSV or print slips; students must set their own password on first login; password reset by staff |
| **Courses** | Create, edit and delete courses; lessons with YouTube/Vimeo links **or** uploaded MP4s, notes and downloadable material; draft/publish; enrol a whole school, grade, batch, all in-house students, or a list of usernames |
| **Quizzes** | Single- and multi-answer questions with images, marks, pass %, timer with auto-submit, attempt limits, answer review after submission |
| **Doubts** | Q&A hub: students ask from anywhere (course, lesson or general), pick a topic (code, circuit, kit…), attach photos, paste code between ``` marks, and can keep a doubt private. While typing, similar answered doubts are suggested. A **Community** tab shows classmates' answered doubts. "I have this doubt too" votes push common doubts to the top of the instructors' **Needs an answer** queue. Students can mark the best answer; replying again reopens a doubt. A badge in the nav shows the queue size / new answers. |
| **Tracking** | Per-student report (lesson progress, quiz history, best scores, certificates, doubts), course progress table, overview of all students by school; printable |
| **Certificates** | Owners and instructors issue certificates to one or many students (or "certify everyone who completed this course"); printable A4 PDF; public verification link `/verify/<id>/`; revoke |
| **Portal** | Newsletters (text + cover + PDF), photo gallery grouped by event, competition details (dates, deadline, venue, prizes, registration link, results) |

## Run locally (for trying it out)

```bash
pip install -r requirements.txt
python manage.py migrate
python manage.py setup_gnr --owner admin --password 'ChooseAStrongPassword'
python manage.py setup_gnr --demo      # optional sample data
python manage.py runserver
```
Open http://localhost:8000. Demo logins: `instructor1 / instructor123`, `school_demo / school123`, `demo260001 / student123`.

Run the tests: `python manage.py test`

## Production (one server, about 1,000+ students)

A VPS with **2 vCPU / 4 GB RAM** (e.g. AWS Lightsail, DigitalOcean or Hetzner, roughly $12–24/month) is enough.

1. Point a DNS **A record** for your subdomain (e.g. `lms` → `lms.gnrrobotics.com`) at the server's IP address.
2. On the server (Ubuntu 24.04, with Docker installed: `curl -fsSL https://get.docker.com | sh`):

```bash
git clone https://github.com/ramkirangaruda/gnr-lms.git && cd gnr-lms
cp .env.example .env          # edit: DJANGO_SECRET_KEY, LMS_DOMAIN, DJANGO_ALLOWED_HOSTS, CSRF origins, DB password
docker compose up -d --build
docker compose exec web python manage.py setup_gnr --owner admin --password 'ChooseAStrongPassword'
```

This runs PostgreSQL, Redis, Django (gunicorn, 5 workers × 4 threads) and **Caddy**, which gets a free Let's Encrypt
HTTPS certificate for `LMS_DOMAIN` by itself, redirects http to https, and serves uploaded files directly.
Ports 80 and 443 must be open in the server's firewall. **Never run `setup_gnr --demo` on the live server**: it creates
logins with publicly known passwords.

To try it on the bare IP before DNS is ready, set `LMS_DOMAIN=:80`, `SECURE_COOKIES=0`, and add the IP to
`DJANGO_ALLOWED_HOSTS` and `http://<ip>` to `DJANGO_CSRF_TRUSTED_ORIGINS`. Switch back once the domain works.

**Updating:** `git pull && docker compose up -d --build` (migrations run automatically on start).
**Logs:** `docker compose logs -f web` (errors include the full traceback).

**Backups:** `sh deploy/backup.sh` writes a database dump and a copy of all uploads to `backups/` and keeps 14 days.
Schedule it nightly with `crontab -e` (the line is at the top of the script) and copy `backups/` off the server
regularly (for example with `rclone` to Google Drive or Backblaze B2), because a backup on the same server dies with it.
Restore (tested): `docker compose exec -T db pg_restore -U gnr -d gnr_lms --clean --if-exists < backups/db_<date>.dump`,
then the uploads: `docker compose exec -T web sh -c 'tar -xzf - -C /app' < backups/media_<date>.tar.gz`.

**Videos:** prefer **unlisted YouTube or Vimeo links**. They cost nothing in bandwidth and stream smoothly to every student at once. Uploaded MP4s work too, but they use your server's bandwidth.

## Scaling up later (AWS)

No code changes, only settings:
1. **Uploads → S3:** set `AWS_STORAGE_BUCKET_NAME`, `AWS_S3_REGION_NAME`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY` in `.env`, then copy the existing `media/` folder into the bucket (`aws s3 sync`).
2. **Database → RDS PostgreSQL:** point `POSTGRES_HOST` etc. at RDS.
3. **More app servers:** run several `web` containers behind a load balancer; sessions and cache already go through Redis (use ElastiCache).
4. Add CloudFront in front of S3 for fast video delivery.

## Frontend & animations

The site is server-rendered (fast, works without JavaScript). Animations come from [React Bits](https://reactbits.dev)
components (Threads, GradientText, ShinyText, SpotlightCard, Counter) running on Preact as small "islands":

- They load **after** the page has finished loading, and only the components a page uses are fetched (~25 KB gzipped in total).
- They pause when off-screen, respect the "reduce motion" accessibility setting, and the WebGL background is skipped on data-saver / 2G connections.
- The built files are already in `static/islands/`, so **the server does not need Node.js**. To change a component:
  `cd frontend && npm install && npm run build`.

React Bits is licensed MIT + Commons Clause (`frontend/src/rb/LICENSE*`): fine to use in this LMS, but the components can't be resold on their own.

## Project layout

```
accounts/   users, roles, schools, login auto-generation (services.py), permissions.py
courses/    courses, lessons, quizzes, progress, doubts, certificates, reports
portal/     home page, dashboards, newsletters, gallery, competitions
templates/  all pages (Bootstrap 5 + red/white/black theme in static/css/gnr.css, works on phones)
frontend/   source for the React Bits animation islands (built into static/islands/)
deploy/     Caddyfile (HTTPS + uploads) and backup.sh
```
The Django admin at `/admin/` (owners only) gives raw access to all data.
