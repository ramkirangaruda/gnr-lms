"""Create the first GNR owner account, and optionally demo data.

    python manage.py setup_gnr --owner admin --password 'S3cret!'
    python manage.py setup_gnr --demo        # sample school, instructor, course, quiz, students
"""
import datetime

from django.core.management.base import BaseCommand
from django.utils import timezone

from accounts.models import School, User
from accounts.services import bulk_create_students


class Command(BaseCommand):
    def add_arguments(self, p):
        p.add_argument("--owner", default="")
        p.add_argument("--password", default="")
        p.add_argument("--demo", action="store_true")

    def handle(self, owner, password, demo, **_):
        if owner:
            u, created = User.objects.get_or_create(username=owner, defaults={"role": User.Role.OWNER})
            u.role, u.is_staff, u.is_superuser = User.Role.OWNER, True, True
            if password:
                u.set_password(password)
            u.save()
            self.stdout.write(self.style.SUCCESS(f"Owner '{owner}' {'created' if created else 'updated'}."))
        if demo:
            self._demo()

    def _demo(self):
        from courses.models import Course, Enrollment, Lesson, Question, Quiz
        from portal.models import Competition, Newsletter

        school, _ = School.objects.get_or_create(code="demo", defaults={"name": "Demo Public School", "city": "Hyderabad"})
        ins, made = User.objects.get_or_create(username="instructor1", defaults={
            "role": User.Role.INSTRUCTOR, "first_name": "Ravi", "last_name": "Kumar"})
        if made:
            ins.set_password("instructor123"); ins.save()
        sa, made = User.objects.get_or_create(username="school_demo", defaults={
            "role": User.Role.SCHOOL, "school": school, "first_name": "Demo", "last_name": "Coordinator"})
        if made:
            sa.set_password("school123"); sa.save()

        course, made = Course.objects.get_or_create(title="Robotics Level 1: Build Your First Robot", defaults={
            "description": "Learn motors, sensors and Arduino basics by building a line-following robot.",
            "age_group": "Grades 5-8", "created_by": ins})
        if made:
            course.instructors.add(ins)
            for i, (t, url) in enumerate([
                ("What is a robot?", "https://www.youtube.com/watch?v=8wHvhm8u0Ss"),
                ("Meet the Arduino", "https://www.youtube.com/watch?v=nL34zDTPkcs"),
                ("Motors and motor drivers", ""),
            ], 1):
                Lesson.objects.create(course=course, title=t, order=i, video_url=url,
                                      content="Watch the video, then try the activity in your kit.", duration_minutes=10)
            quiz = Quiz.objects.create(course=course, title="Robot basics quiz", pass_percentage=60, time_limit_minutes=10)
            for text, opts in [
                ("Which part is the 'brain' of our robot?", [("Arduino board", True), ("Battery", False), ("Wheel", False)]),
                ("Which of these are sensors?", [("Ultrasonic sensor", True), ("IR sensor", True), ("DC motor", False)]),
            ]:
                q = Question.objects.create(quiz=quiz, text=text)
                for o, ok in opts:
                    q.choices.create(text=o, is_correct=ok)

        if not User.objects.filter(role=User.Role.STUDENT).exists():
            rows = [{"first_name": n} for n in ["Aarav", "Diya", "Kabir", "Meera", "Ishaan"]]
            for u, pw in bulk_create_students(rows, User.StudentType.SCHOOL, school=school, grade="6", courses=[course]):
                u = User.objects.get(username=u.username); u.set_password("student123"); u.must_change_password = False; u.save()
            for u, pw in bulk_create_students([{"first_name": "Rohan"}, {"first_name": "Sana"}], User.StudentType.IN_HOUSE, courses=[course]):
                u = User.objects.get(username=u.username); u.set_password("student123"); u.must_change_password = False; u.save()

        Newsletter.objects.get_or_create(title="Welcome to the GNR Robotics LMS", defaults={
            "summary": "Everything you need to learn robotics, in one place.",
            "body": "Watch lessons, take quizzes, ask doubts and earn certificates. Happy building!"})
        Competition.objects.get_or_create(title="GNR RoboRace 2026", defaults={
            "description": "Build the fastest line-follower and race it on our championship track!",
            "event_date": timezone.localdate() + datetime.timedelta(days=30),
            "registration_deadline": timezone.localdate() + datetime.timedelta(days=20),
            "venue": "GNR Robotics Centre", "eligibility": "Grades 5-10", "prizes": "1st: ₹5000 + trophy\n2nd: ₹3000\n3rd: ₹2000"})
        self.stdout.write(self.style.SUCCESS(
            "Demo data ready. Logins: instructor1/instructor123, school_demo/school123, students demo260001…/student123"))
