"""Regression tests for the launch-readiness fixes (REPORT.md issue IDs in each test name's docstring)."""
import io
import tempfile
from datetime import timedelta

from django.core.cache import cache
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone

from accounts.models import School, User
from courses.models import Certificate, Course, Doubt, DoubtReply, Enrollment, Lesson, Quiz, QuizAttempt, QuizStart

PNG = (b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00"
       b"\x00\x0cIDATx\x9cc\xf8\xff\xff?\x00\x05\xfe\x02\xfe\xa75\x81\x84\x00\x00\x00\x00IEND\xaeB`\x82")
MEDIA = tempfile.mkdtemp(prefix="gnr-test-media-")


@override_settings(MEDIA_ROOT=MEDIA, MEDIA_ACCEL_REDIRECT=False)
class HardeningTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("setup_gnr", owner="owner", password="owner123", demo=True, stdout=io.StringIO())
        cls.course = Course.objects.get()
        cls.quiz = Quiz.objects.get()
        cls.school = School.objects.get(code="demo")
        cls.student = User.objects.filter(role="student", school=cls.school).order_by("username").first()
        cls.other = User.objects.create_user("lonely", password="pw123456x", role="student", student_type="in_house")

    def setUp(self):
        cache.clear()

    def login(self, username, pw):
        self.client.logout()
        r = self.client.post("/login/", {"username": username, "password": pw})
        self.assertEqual(r.status_code, 302, f"login failed for {username}")

    # ---------- B-1 ----------
    def test_login_lockout_after_repeated_failures(self):
        """B-1: 10 wrong passwords lock the account for a while, even with the right password."""
        for _ in range(10):
            self.assertEqual(self.client.post("/login/", {"username": self.student.username, "password": "nope"}).status_code, 200)
        r = self.client.post("/login/", {"username": self.student.username, "password": "student123"})
        self.assertEqual(r.status_code, 429)
        self.assertContains(r, "Too many wrong passwords", status_code=429)
        cache.clear()
        self.login(self.student.username, "student123")

    def test_weak_passwords_rejected_at_first_login(self):
        """B-1: first-login password must pass the validators."""
        self.student.must_change_password = True
        self.student.save()
        self.login(self.student.username, "student123")
        for weak in ["123456", "12345678", "password1", "abc12"]:
            r = self.client.post("/welcome/password/", {"new_password1": weak, "new_password2": weak})
            self.assertEqual(r.status_code, 200, weak)
        r = self.client.post("/welcome/password/", {"new_password1": "Robo-Arm-42", "new_password2": "Robo-Arm-42"})
        self.assertRedirects(r, "/dashboard/")

    def test_admin_login_uses_throttled_page(self):
        r = self.client.get("/admin/login/")
        self.assertEqual(r.status_code, 302)
        self.assertTrue(r["Location"].startswith("/login/"))
        self.login(self.student.username, "student123")  # signed-in student: 403, not a redirect loop
        self.assertEqual(self.client.get("/admin/login/").status_code, 403)

    def test_session_ends_with_browser_unless_remembered(self):
        """M-8: shared lab PCs forget the student when the browser closes."""
        self.client.post("/login/", {"username": self.student.username, "password": "student123"})
        self.assertTrue(self.client.session.get_expire_at_browser_close())
        self.client.logout()
        self.client.post("/login/", {"username": self.student.username, "password": "student123", "remember": "1"})
        self.assertFalse(self.client.session.get_expire_at_browser_close())

    # ---------- B-2 / M-1 ----------
    def test_private_files_need_permission(self):
        """B-2: lesson files and private doubt photos are not public."""
        lesson = self.course.lessons.first()
        lesson.attachment.save("sheet.pdf", ContentFile(b"%PDF-1.4 worksheet"))
        doubt = Doubt.objects.create(student=self.student, course=self.course, title="t", body="b", is_private=True)
        doubt.image.save("photo.png", ContentFile(PNG))
        self.assertNotIn("photo", doubt.image.name)  # random name, can't be guessed
        att, img = lesson.attachment.url, doubt.image.url
        self.client.logout()
        self.assertEqual(self.client.get(att).status_code, 302)  # anonymous -> login
        self.assertEqual(self.client.get(img).status_code, 302)
        self.login("lonely", "pw123456x")  # not enrolled, not the asker
        self.assertEqual(self.client.get(att).status_code, 404)
        self.assertEqual(self.client.get(img).status_code, 404)
        self.login(self.student.username, "student123")
        r = self.client.get(att)
        self.assertEqual(r.status_code, 200)
        self.assertIn("attachment;", r["Content-Disposition"])
        self.assertEqual(self.client.get(img).status_code, 200)
        self.login("instructor1", "instructor123")
        self.assertEqual(self.client.get(img).status_code, 200)

    @override_settings(MEDIA_ACCEL_REDIRECT=True)
    def test_caddy_sends_the_file_after_the_check(self):
        lesson = self.course.lessons.first()
        lesson.attachment.save("sheet.pdf", ContentFile(b"%PDF-1.4"))
        self.login(self.student.username, "student123")
        r = self.client.get(lesson.attachment.url)
        self.assertEqual(r["X-Accel-Redirect"], "/" + lesson.attachment.name)

    def test_traversal_and_unknown_paths_404(self):
        self.login("owner", "owner123")
        for p in ["/media/../config/settings.py", "/media/%2e%2e/manage.py", "/media/secret/thing.txt"]:
            self.assertEqual(self.client.get(p).status_code, 404, p)

    def test_html_attachment_rejected(self):
        """M-1: staff can't upload files the browser would run as a page on our site."""
        self.login("instructor1", "instructor123")
        lesson = self.course.lessons.first()
        r = self.client.post(f"/courses/{self.course.slug}/lessons/{lesson.pk}/edit/", {
            "title": lesson.title, "order": 1, "duration_minutes": 1,
            "attachment": SimpleUploadedFile("evil.html", b"<script>alert(1)</script>", content_type="text/html")})
        self.assertEqual(r.status_code, 200)
        lesson.refresh_from_db()
        self.assertFalse(lesson.attachment)

    # ---------- H-1 / H-2 / M-2 ----------
    def _answers(self, right=True):
        return {f"q{q.id}": [str(c.id) for c in q.choices.filter(is_correct=right)][:1] for q in self.quiz.questions.all()}

    def test_quiz_timer_is_enforced_by_the_server(self):
        """H-1: the clock starts on opening and survives refreshes; late answers score 0."""
        self.quiz.time_limit_minutes = 5
        self.quiz.save()
        url = f"/courses/{self.course.slug}/quizzes/{self.quiz.pk}/"
        self.login(self.student.username, "student123")
        self.client.get(url)
        QuizStart.objects.filter(student=self.student).update(started_at=timezone.now() - timedelta(minutes=4))
        r = self.client.get(url)  # refresh: only ~1 minute left, not 5 again
        self.assertLessEqual(r.context["remaining"], 61)
        QuizStart.objects.filter(student=self.student).update(started_at=timezone.now() - timedelta(minutes=10))
        self.client.post(url, self._answers())
        a = QuizAttempt.objects.get(student=self.student)
        self.assertTrue(a.is_late)
        self.assertEqual(a.score, 0)

    def test_post_without_opening_or_twice_records_one_attempt(self):
        """M-2: a double submit (or a POST without opening the quiz) can't add attempts."""
        url = f"/courses/{self.course.slug}/quizzes/{self.quiz.pk}/"
        self.login(self.student.username, "student123")
        self.client.post(url, self._answers())
        self.assertEqual(QuizAttempt.objects.filter(student=self.student).count(), 0)
        self.client.get(url)
        self.client.post(url, self._answers())
        self.client.post(url, self._answers())
        self.assertEqual(QuizAttempt.objects.filter(student=self.student).count(), 1)

    def test_answers_hidden_until_pass_or_last_attempt(self):
        """H-2: a failed attempt with attempts left shows the score only."""
        self.quiz.max_attempts = 2
        self.quiz.save()
        url = f"/courses/{self.course.slug}/quizzes/{self.quiz.pk}/"
        self.login(self.student.username, "student123")
        self.client.get(url)
        r = self.client.post(url, self._answers(right=False), follow=True)
        self.assertNotContains(r, "choice-right")
        self.client.get(url)
        r = self.client.post(url, self._answers(right=False), follow=True)  # last attempt used
        self.assertContains(r, "choice-right")

    # ---------- M-3 / M-4 ----------
    def test_generated_logins_use_fast_temporary_hash(self):
        self.login("owner", "owner123")
        r = self.client.post("/users/generate/", {"student_type": "in_house", "count": "5"})
        self.assertEqual(r.status_code, 200)
        u = User.objects.filter(must_change_password=True, role="student").latest("id")
        self.assertTrue(u.password.startswith("pbkdf2_temp$"))

    # ---------- M-5 / M-6 / L-1 ----------
    def test_deleting_instructor_keeps_answers(self):
        ins = User.objects.create_user("ins9", password="x", role="instructor")
        d = Doubt.objects.create(student=self.student, title="t", body="b")
        DoubtReply.objects.create(doubt=d, author=ins, body="Answer")
        ins.delete()
        self.assertEqual(d.replies.get().author, None)
        self.login(self.student.username, "student123")
        self.assertContains(self.client.get(f"/doubts/{d.pk}/"), "Former GNR team member")

    def test_student_with_certificate_cannot_be_deleted(self):
        Certificate.objects.create(student=self.other, title="x")
        self.login("owner", "owner123")
        self.client.post(f"/users/{self.other.pk}/delete/")
        self.assertTrue(User.objects.filter(pk=self.other.pk).exists())

    def test_only_issuer_or_course_instructor_can_revoke(self):
        foreign = Course.objects.create(title="Someone else's")
        cert = Certificate.objects.create(student=self.student, course=foreign, title="x")
        self.login("instructor1", "instructor123")
        self.assertEqual(self.client.post(f"/certificates/{cert.code}/", {"revoke": "1"}).status_code, 403)
        self.login("owner", "owner123")
        self.client.post(f"/certificates/{cert.code}/", {"revoke": "1"})
        self.assertFalse(Certificate.objects.filter(pk=cert.pk).exists())

    # ---------- L-3 / L-4 / H-4 ----------
    def test_school_admin_scope(self):
        hidden = Course.objects.create(title="Not my school's")
        self.login("school_demo", "school123")
        self.assertEqual(self.client.get(hidden.get_absolute_url()).status_code, 403)
        self.assertEqual(self.client.get(self.course.get_absolute_url()).status_code, 200)
        self.assertNotContains(self.client.get("/courses/"), "Not my school")
        self.assertEqual(self.client.get(f"/courses/{self.course.slug}/quizzes/{self.quiz.pk}/").status_code, 403)

    def test_doubt_photo_size_cap(self):
        self.login(self.student.username, "student123")
        big = SimpleUploadedFile("big.png", PNG + b"\x00" * (11 * 1024 * 1024), content_type="image/png")
        r = self.client.post("/doubts/ask/", {"category": "kit", "title": "Big photo", "body": "x", "image": big})
        self.assertEqual(r.status_code, 200)
        self.assertFalse(Doubt.objects.filter(title="Big photo").exists())

    def test_healthz(self):
        r = self.client.get("/healthz")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json(), {"status": "ok"})
