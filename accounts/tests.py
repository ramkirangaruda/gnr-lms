import io
import re

from django.core import mail
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase, override_settings

from .models import School, User


class PasswordResetTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("setup_gnr", owner="owner", password="owner123", demo=True, stdout=io.StringIO())
        cls.school = School.objects.get(code="demo")
        cls.other_school = School.objects.create(name="Other School", code="oth")
        cls.student = User.objects.filter(role="student", school=cls.school).order_by("username").first()
        cls.other_student = User.objects.create_user("oth260001", password="x123456", role="student",
                                                     school=cls.other_school, student_type="school")

    def setUp(self):
        cache.clear()

    def login(self, username, pw):
        self.client.logout()
        r = self.client.post("/login/", {"username": username, "password": pw})
        self.assertEqual(r.status_code, 302, f"login failed for {username}")

    def _temp_password(self, response):
        return re.search(r'<td class="font-monospace">([^<]+)</td>', response.content.decode()).group(1)

    # ---- staff reset: works with no email at all ----

    def test_staff_reset_without_email_forces_change_on_next_login(self):
        self.assertEqual(self.student.email, "")
        for actor, pw in [("owner", "owner123"), ("instructor1", "instructor123"), ("school_demo", "school123")]:
            self.login(actor, pw)
            r = self.client.post(f"/users/{self.student.pk}/reset-password/")
            self.assertContains(r, "New password")
            temp = self._temp_password(r)
            self.assertEqual(len(mail.outbox), 0)
            self.student.refresh_from_db()
            self.assertTrue(self.student.must_change_password)
            self.assertFalse(self.student.check_password("student123"))

            self.login(self.student.username, temp)
            self.assertRedirects(self.client.get("/dashboard/"), "/welcome/password/")
            r = self.client.post("/welcome/password/", {"new_password1": "mynewpass1", "new_password2": "mynewpass1"})
            self.assertRedirects(r, "/dashboard/", fetch_redirect_response=False)
            self.student.refresh_from_db()
            self.assertFalse(self.student.must_change_password)
            self.assertTrue(self.student.check_password("mynewpass1"))

    def test_school_admin_cannot_reset_other_schools_or_staff(self):
        self.login("school_demo", "school123")
        self.assertEqual(self.client.post(f"/users/{self.other_student.pk}/reset-password/").status_code, 403)
        instructor = User.objects.get(username="instructor1")
        self.assertEqual(self.client.post(f"/users/{instructor.pk}/reset-password/").status_code, 403)
        self.login(self.student.username, "student123")
        self.assertEqual(self.client.post(f"/users/{self.other_student.pk}/reset-password/").status_code, 403)

    def test_reset_requires_post(self):
        self.login("owner", "owner123")
        self.client.get(f"/users/{self.student.pk}/reset-password/")
        self.student.refresh_from_db()
        self.assertTrue(self.student.check_password("student123"))

    def test_user_list_has_reset_button(self):
        self.login("instructor1", "instructor123")
        self.assertContains(self.client.get("/users/"), f"/users/{self.student.pk}/reset-password/")

    # ---- email reset ----

    def test_login_page_links_to_forgot_password(self):
        self.assertContains(self.client.get("/login/"), 'href="/password/forgot/"')

    def _reset_link(self):
        return re.search(r"http://testserver(/password/reset/\S+/)", mail.outbox[-1].body).group(1)

    def test_email_reset_by_username_and_by_email(self):
        self.student.email = "parent@example.com"
        self.student.must_change_password = True
        self.student.save()
        for value in (self.student.username.upper(), "Parent@Example.com"):
            mail.outbox.clear()
            r = self.client.post("/password/forgot/", {"email": value})
            self.assertRedirects(r, "/password/forgot/sent/")
            self.assertEqual(len(mail.outbox), 1)
            self.assertEqual(mail.outbox[0].to, ["parent@example.com"])
            self.assertIn(self.student.username, mail.outbox[0].body)

        r = self.client.get(self._reset_link(), follow=True)
        self.assertContains(r, "Choose a new password")
        r = self.client.post(r.redirect_chain[-1][0], {"new_password1": "Robots4ever!", "new_password2": "Robots4ever!"})
        self.assertRedirects(r, "/password/reset/done/")
        self.student.refresh_from_db()
        self.assertTrue(self.student.check_password("Robots4ever!"))
        self.assertFalse(self.student.must_change_password)
        # link is single-use
        self.assertContains(self.client.get(self._reset_link(), follow=True), "This link has expired")

    def test_no_email_sent_for_account_without_email_or_unknown_user(self):
        for value in (self.student.username, "nobody", "nobody@example.com", " "):
            r = self.client.post("/password/forgot/", {"email": value})
            if value.strip():
                self.assertRedirects(r, "/password/forgot/sent/")
        self.assertEqual(len(mail.outbox), 0)

    def test_shared_parent_email_sends_one_mail_per_child(self):
        a, b = User.objects.filter(role="student", school=self.school).order_by("username")[:2]
        User.objects.filter(pk__in=[a.pk, b.pk]).update(email="family@example.com")
        self.client.post("/password/forgot/", {"email": "family@example.com"})
        self.assertEqual(len(mail.outbox), 2)
        self.assertEqual({m.body.split("Username: ")[1].split()[0] for m in mail.outbox}, {a.username, b.username})

    @override_settings(PASSWORD_RESET_EMAILS_PER_HOUR=2)
    def test_reset_emails_are_rate_limited_per_account(self):
        User.objects.filter(pk=self.student.pk).update(email="kid@example.com")
        for _ in range(4):
            self.client.post("/password/forgot/", {"email": "kid@example.com"})
        self.assertEqual(len(mail.outbox), 2)

    @override_settings(EMAIL_BACKEND="accounts.tests.BrokenBackend")
    def test_smtp_failure_does_not_crash(self):
        User.objects.filter(pk=self.student.pk).update(email="kid@example.com")
        r = self.client.post("/password/forgot/", {"email": "kid@example.com"})
        self.assertRedirects(r, "/password/forgot/sent/")

    @override_settings(PASSWORD_RESET_BY_EMAIL=False)
    def test_forgot_page_without_smtp_points_to_staff(self):
        User.objects.filter(pk=self.student.pk).update(email="kid@example.com")
        r = self.client.get("/password/forgot/")
        self.assertContains(r, "Ask your instructor or school coordinator")
        self.assertNotContains(r, "Send reset link")
        self.client.post("/password/forgot/", {"email": "kid@example.com"})
        self.assertEqual(len(mail.outbox), 0)

    # ---- bulk-created students keep working with blank emails ----

    def test_bulk_students_with_and_without_email(self):
        self.login("owner", "owner123")
        csv = b"first_name,last_name,grade,batch,email\nZoyaa,Rao,7,B,\nYuvaan,Singh,7,B,vikram.parent@example.com\nXenia,Iyer,7,B,\n"
        r = self.client.post("/users/generate/", {
            "student_type": "school", "school": self.school.pk,
            "csv_file": SimpleUploadedFile("s.csv", csv, content_type="text/csv")})
        self.assertContains(r, "Download CSV")
        anya, vikram, meera = (User.objects.get(first_name=n) for n in ("Zoyaa", "Yuvaan", "Xenia"))
        self.assertEqual((anya.email, meera.email), ("", ""))
        self.assertEqual(vikram.email, "vikram.parent@example.com")
        # editing a student with no email still saves
        r = self.client.post(f"/users/{anya.pk}/", {
            "first_name": "Zoyaa", "last_name": "Rao", "email": "", "phone": "", "role": "student",
            "student_type": "school", "school": self.school.pk, "grade": "7", "batch": "B", "is_active": "on"})
        self.assertEqual(r.status_code, 302, r.content[:2000])
        self.client.logout()
        self.client.post("/password/forgot/", {"email": anya.username})
        self.assertEqual(len(mail.outbox), 0)
        self.client.post("/password/forgot/", {"email": vikram.username})
        self.assertEqual(mail.outbox[0].to, ["vikram.parent@example.com"])


class BrokenBackend:
    def __init__(self, *a, **kw):
        pass

    def send_messages(self, messages):
        raise ConnectionRefusedError("SMTP down")
