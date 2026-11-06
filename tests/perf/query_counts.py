"""Count SQL queries and time per key page, per role, on the seeded staging data (finds N+1s and slow pages).

    docker compose exec -T web python manage.py shell < tests/perf/query_counts.py
"""
import time
from django.db import connection
from django.test import Client
from django.test.utils import CaptureQueriesContext
from django.conf import settings
from courses.models import Course, Enrollment, Doubt
from accounts.models import User

settings.ALLOWED_HOSTS = ["*"]
c1 = Course.objects.get(slug="qa-course-1")
st = User.objects.get(username="lt0001")
cs = Enrollment.objects.filter(student=st).first().course
l = cs.lessons.first(); qz = cs.quizzes.first()
pages = {
    "qa_owner": ["/dashboard/", "/courses/", "/users/", "/students/", f"/courses/{c1.slug}/report/", f"/courses/{c1.slug}/students/",
                 "/certificates/", "/doubts/", "/doubts/?tab=all", f"/students/{st.pk}/", "/schools/", f"/courses/{c1.slug}/quizzes/{c1.quizzes.first().pk}/manage/"],
    "qa_inst1": ["/dashboard/", "/doubts/", "/students/"],
    "qa_sch1": ["/dashboard/", "/users/", "/students/", f"/courses/{c1.slug}/report/"],
    "lt0001": ["/dashboard/", "/courses/", f"/courses/{cs.slug}/", f"/courses/{cs.slug}/lessons/{l.pk}/", f"/courses/{cs.slug}/quizzes/{qz.pk}/",
               "/doubts/", "/doubts/?tab=community", "/certificates/"],
    None: ["/", "/login/", "/newsletters/", "/competitions/", "/gallery/"],
}
print(f"{'role':10} {'page':60} {'status':>6} {'queries':>7} {'ms':>6}")
for who, urls in pages.items():
    c = Client()
    if who:
        c.force_login(User.objects.get(username=who))
    for u in urls:
        with CaptureQueriesContext(connection) as ctx:
            t = time.perf_counter(); r = c.get(u); ms = (time.perf_counter() - t) * 1000
        print(f"{who or 'anon':10} {u[:60]:60} {r.status_code:>6} {len(ctx.captured_queries):>7} {ms:>6.0f}")
