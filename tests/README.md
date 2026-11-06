# Launch-readiness test kit

Everything here runs against a **staging** copy of the stack with fake data. None of it is safe to point at
production: it creates, edits and deletes records, and the load test will saturate the server.

## 1. Start a staging stack sized like the 2 vCPU / 4 GB VPS

```sh
cp .env.example .env        # then set DJANGO_SECRET_KEY, LMS_DOMAIN=:80, SECURE_COOKIES=0,
                            # DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1, DJANGO_CSRF_TRUSTED_ORIGINS=http://localhost
# fake Bunny keys so the upload UI appears (the browser test intercepts all Bunny traffic):
#   BUNNY_STREAM_LIBRARY_ID=123456  BUNNY_STREAM_API_KEY=fake-api-key  BUNNY_STREAM_TOKEN_KEY=fake-token-key
# reset emails go to the container log, never to a real inbox:
#   EMAIL_BACKEND=django.core.mail.backends.console.EmailBackend  PASSWORD_RESET_BY_EMAIL=1
docker compose -f docker-compose.yml -f tests/docker-compose.qa.yml up -d --build
docker compose exec -T web python manage.py setup_gnr --owner admin --password 'OwnerPass123!' --demo
docker compose exec -T web python manage.py shell < tests/seed_staging.py      # 1,500 students, 10 courses, ...
```

`tests/docker-compose.qa.yml` pins the whole stack to CPUs 0-1 with memory caps, so the load generator can run on
the other CPUs of the test machine (`taskset -c 2,3 k6 ...`).

## 2. Functional + security

| Command | What it checks |
|---|---|
| `docker compose exec -T web python manage.py test` | 37 unit/integration tests |
| `python3 tests/e2e/make_fixtures.py && node tests/e2e/walkthrough.js` | 57 browser checks: every role's journey, crawls of every linked page |
| `python3 tests/api/test_security_and_integrity.py` | 70 checks: auth, access control/IDOR, XSS/CSRF/SQLi, uploads, headers, races, cascades |
| `AXE_PATH=.../axe.min.js node tests/e2e/a11y_and_devices.js` | axe-core WCAG A/AA, console errors, phone layouts, slow 3G |
| `docker compose exec -T web python manage.py shell < tests/perf/query_counts.py` | SQL queries + ms per key page (N+1 guard) |

The API suite states the *secure* behaviour; a FAIL is a finding. Results land in `tests/api/results.json`.

## 3. Load

```sh
sh tests/load/monitor.sh mon.csv &                    # CPU / RAM / DB connections every 5 s
taskset -c 2,3 k6 run -e SCENARIO=ramp --out csv=ramp.csv.gz tests/load/lms.js          # 50→1500 VUs, 3 min holds
taskset -c 2,3 k6 run -e SCENARIO=login_storm tests/load/lms.js                          # 1,000 logins in 5 min
taskset -c 2,3 k6 run -e SCENARIO=quiz_burst tests/load/lms.js                           # 500 quiz submits in 1 min
taskset -c 2,3 k6 run -e SCENARIO=soak -e SOAK_VUS=300 -e SOAK_MIN=30 --out csv=soak.csv.gz tests/load/lms.js
python3 tests/load/analyze.py ramp.csv.gz mon.csv --stages 50,200,300,500,1000,1500
```

Before the load test, set the QA quizzes to unlimited attempts so every submit is a real one:
`docker compose exec -T web python manage.py shell -c "from courses.models import Quiz;Quiz.objects.filter(course__slug__startswith='qa-course').update(max_attempts=0)"`
