"""Seed a STAGING database with fake data for QA and load tests. Never run against production.

    docker compose exec -T web python manage.py shell < tests/seed_staging.py

Creates (idempotently, prefix qa_/lt):
  qa_owner, qa_inst1..5, 10 schools each with qa_sch<N> admin, 1500 students lt0001..lt1500,
  10 courses x 10 lessons, 1 timed quiz (10 questions) per course, enrolments, progress, attempts,
  doubts with replies, certificates, newsletters, competitions.
All passwords: QaPass#2026 (fake, staging only).
"""
import random
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.hashers import make_password
from django.db import transaction
from django.utils import timezone

from accounts.models import School, User
from courses.models import (Certificate, Choice, Course, Doubt, DoubtReply, Enrollment, Lesson, LessonProgress,
                            Question, Quiz, QuizAttempt)
from portal.models import Competition, Newsletter

assert "prod" not in settings.ALLOWED_HOSTS[0], "refusing to seed what looks like production"
random.seed(42)
PW = make_password("QaPass#2026")
N_STUDENTS = 1500

with transaction.atomic():
    owner, _ = User.objects.get_or_create(username="qa_owner", defaults=dict(role="owner", password=PW, is_superuser=True,
                                                                            is_staff=True, email="owner@example.test"))
    insts = [User.objects.get_or_create(username=f"qa_inst{i}", defaults=dict(role="instructor", password=PW,
             first_name=f"Instructor{i}", email=f"inst{i}@example.test"))[0] for i in range(1, 6)]
    schools = []
    for i in range(1, 11):
        s, _ = School.objects.get_or_create(code=f"qs{i:02d}", defaults=dict(name=f"QA School {i}", city="Hyderabad"))
        schools.append(s)
        User.objects.get_or_create(username=f"qa_sch{i}", defaults=dict(role="school", school=s, password=PW))
    have = set(User.objects.filter(username__startswith="lt").values_list("username", flat=True))
    names = ["Aarav", "Diya", "Ishaan", "Ananya", "Vihaan", "Saanvi", "రాము", "सीता", "Kabir", "Meera 🚀"]
    User.objects.bulk_create([User(username=f"lt{i:04d}", password=PW, role="student",
                                   first_name=random.choice(names), last_name="QA",
                                   student_type="school" if i % 3 else "in_house",
                                   school=schools[i % 10] if i % 3 else None, grade=str(5 + i % 6),
                                   batch=f"B{i % 4}", email=f"lt{i:04d}@example.test" if i % 2 else "")
                              for i in range(1, N_STUDENTS + 1) if f"lt{i:04d}" not in have], batch_size=500)
    students = list(User.objects.filter(username__startswith="lt").order_by("username"))

    courses = []
    for c in range(1, 11):
        course, created = Course.objects.get_or_create(slug=f"qa-course-{c}", defaults=dict(
            title=f"QA Robotics Course {c}", description="Seeded course for QA. Arduino, sensors, motors.",
            created_by=owner))
        course.instructors.add(insts[c % 5])
        courses.append(course)
        if created:
            Lesson.objects.bulk_create([Lesson(course=course, title=f"Lesson {l}: Sensors part {l}", order=l,
                                               video_url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                                               content="Build the circuit.\n```\nvoid setup(){}\n```", duration_minutes=10)
                                        for l in range(1, 11)])
            qz = Quiz.objects.create(course=course, title=f"Quiz {c}", time_limit_minutes=10, max_attempts=3, pass_percentage=60)
            for qn in range(1, 11):
                q = Question.objects.create(quiz=qz, text=f"Question {qn}: what does a resistor do?", order=qn)
                Choice.objects.bulk_create([Choice(question=q, text=f"Option {k}", is_correct=(k == 1)) for k in range(1, 5)])

    if not Enrollment.objects.filter(course__slug__startswith="qa-course").exists():
        Enrollment.objects.bulk_create([Enrollment(student=s, course=courses[(i + k) % 10])
                                        for i, s in enumerate(students) for k in range(3)], batch_size=2000)
        lessons = {c.id: list(c.lessons.all()) for c in courses}
        prog, atts = [], []
        quizzes = {c.id: c.quizzes.first() for c in courses}
        for i, s in enumerate(students):
            for k in range(3):
                c = courses[(i + k) % 10]
                for l in lessons[c.id][:random.randint(0, 10)]:
                    prog.append(LessonProgress(student=s, lesson=l))
                if random.random() < 0.5:
                    sc = random.randint(0, 10)
                    atts.append(QuizAttempt(quiz=quizzes[c.id], student=s, score=sc, total=10, answers={}))
        LessonProgress.objects.bulk_create(prog, batch_size=2000, ignore_conflicts=True)
        QuizAttempt.objects.bulk_create(atts, batch_size=2000)
        doubts = [Doubt(student=random.choice(students), course=random.choice(courses), title=f"Seeded doubt {n} motor not spinning",
                        body="My motor does not spin.\n```\nanalogWrite(9, 255);\n```", is_private=(n % 7 == 0))
                  for n in range(500)]
        Doubt.objects.bulk_create(doubts)
        DoubtReply.objects.bulk_create([DoubtReply(doubt=d, author=random.choice(insts), body="Check the wiring.")
                                        for d in Doubt.objects.all()[:300]])
        Doubt.objects.filter(pk__in=Doubt.objects.all()[:300].values("pk")).update(has_staff_reply=True)
        Certificate.objects.bulk_create([Certificate(student=s, course=courses[i % 10], issued_by=owner,
                                                     achievement="completed the QA course") for i, s in enumerate(students[:300])])
        Newsletter.objects.bulk_create([Newsletter(title=f"QA Newsletter {n}", summary="Monthly update", body="News")
                                        for n in range(15)])
        Competition.objects.bulk_create([Competition(title=f"QA RoboRace {n}", description="Line follower race",
                                                     event_date=timezone.localdate() + timedelta(days=n * 10 - 30))
                                         for n in range(8)])
print("seeded:", User.objects.count(), "users,", Enrollment.objects.count(), "enrolments,",
      LessonProgress.objects.count(), "progress,", QuizAttempt.objects.count(), "attempts,", Doubt.objects.count(), "doubts")
