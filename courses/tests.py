import io

from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase

from accounts.models import School, User
from courses.models import Certificate, Course, Doubt, Enrollment, LessonProgress, Quiz, QuizAttempt


class LMSFlowTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("setup_gnr", owner="owner", password="owner123", demo=True, stdout=io.StringIO())
        cls.course = Course.objects.get()
        cls.quiz = Quiz.objects.get()
        cls.school = School.objects.get(code="demo")
        cls.student = User.objects.filter(role="student", school=cls.school).order_by("username").first()

    def login(self, username, pw):
        self.client.logout()
        r = self.client.post("/login/", {"username": username, "password": pw})
        self.assertEqual(r.status_code, 302, f"login failed for {username}")

    def assertPagesOK(self, urls):
        for u in urls:
            r = self.client.get(u)
            self.assertEqual(r.status_code, 200, f"{u} -> {r.status_code}")

    def test_public_pages(self):
        self.assertPagesOK(["/", "/login/", "/newsletters/", "/gallery/", "/competitions/"])
        self.assertEqual(self.client.get("/dashboard/").status_code, 302)

    def test_owner_pages(self):
        self.login("owner", "owner123")
        c = self.course
        self.assertPagesOK(["/dashboard/", "/users/", "/users/new/", "/users/generate/", "/schools/", "/schools/new/",
                            "/students/", f"/students/{self.student.pk}/", "/courses/", "/courses/new/", c.get_absolute_url(),
                            f"/courses/{c.slug}/edit/", f"/courses/{c.slug}/students/", f"/courses/{c.slug}/report/",
                            f"/courses/{c.slug}/lessons/new/", f"/courses/{c.slug}/quizzes/new/",
                            f"/courses/{c.slug}/quizzes/{self.quiz.pk}/manage/", f"/courses/{c.slug}/quizzes/{self.quiz.pk}/",
                            f"/courses/{c.slug}/lessons/{c.lessons.first().pk}/", "/doubts/", "/certificates/",
                            "/certificates/issue/", "/newsletters/new/", "/gallery/new/", "/competitions/new/",
                            f"/users/{self.student.pk}/", "/admin/"])

    def test_bulk_generate_csv_and_first_login(self):
        self.login("owner", "owner123")
        csv = b"first_name,last_name,grade,batch\nAnya,Rao,7,B\nVikram,Singh,7,B\n"
        r = self.client.post("/users/generate/", {
            "student_type": "school", "school": self.school.pk, "course_ids": [self.course.pk],
            "csv_file": SimpleUploadedFile("s.csv", csv, content_type="text/csv")})
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Download CSV")
        anya = User.objects.get(first_name="Anya")
        self.assertTrue(anya.username.startswith("demo"))
        self.assertTrue(Enrollment.objects.filter(student=anya, course=self.course).exists())
        pw = next(pw for u, pw in r.context["created"] if u.username == anya.username)
        # first login forces a password change
        self.login(anya.username, pw)
        self.assertRedirects(self.client.get("/dashboard/"), "/welcome/password/")
        self.client.post("/welcome/password/", {"new_password1": "newpass99", "new_password2": "newpass99"})
        self.assertEqual(self.client.get("/dashboard/").status_code, 200)

    def test_bulk_generate_count_in_house(self):
        self.login("instructor1", "instructor123")
        r = self.client.post("/users/generate/", {"student_type": "in_house", "count": 25, "batch": "Sat-AM"})
        self.assertEqual(len(r.context["created"]), 25)
        self.assertEqual(User.objects.filter(batch="Sat-AM", student_type="in_house").count(), 25)
        self.assertEqual(len({u.username for u, _ in r.context["created"]}), 25)

    def test_in_house_ignores_selected_school(self):
        self.login("instructor1", "instructor123")
        r = self.client.post("/users/generate/", {"student_type": "in_house", "school": self.school.pk, "count": 1})
        u = r.context["created"][0][0]
        self.assertTrue(u.username.startswith("gnr"), u.username)
        self.assertIsNone(u.school)

    def test_malformed_ids_do_not_crash(self):
        self.login("owner", "owner123")
        for url in ["/users/?school=abc", "/students/?school=abc", "/certificates/issue/?course=abc",
                    f"/courses/{self.course.slug}/quizzes/{self.quiz.pk}/manage/?edit=abc"]:
            self.assertEqual(self.client.get(url).status_code, 200, url)
        r = self.client.post(f"/courses/{self.course.slug}/students/", {"remove": "abc"})
        self.assertEqual(r.status_code, 302)

    def test_student_learning_flow(self):
        self.login(self.student.username, "student123")
        c = self.course
        self.assertPagesOK(["/dashboard/", "/courses/", c.get_absolute_url(), "/doubts/", "/certificates/",
                            f"/students/{self.student.pk}/"])
        for lesson in c.lessons.all():
            self.client.post(f"/courses/{c.slug}/lessons/{lesson.pk}/")
        self.assertEqual(LessonProgress.objects.filter(student=self.student).count(), c.lessons.count())
        self.assertIsNotNone(Enrollment.objects.get(student=self.student, course=c).completed_at)
        # quiz: answer everything correctly
        data = {}
        for q in self.quiz.questions.all():
            data[f"q{q.id}"] = [str(ch.id) for ch in q.choices.filter(is_correct=True)]
        r = self.client.post(f"/courses/{c.slug}/quizzes/{self.quiz.pk}/", data)
        attempt = QuizAttempt.objects.get(student=self.student)
        self.assertEqual(attempt.percent, 100)
        self.assertRedirects(r, f"/courses/{c.slug}/quizzes/{self.quiz.pk}/result/{attempt.pk}/")
        self.assertContains(self.client.get(r.url), "100%")
        # doubt
        r = self.client.post("/doubts/ask/", {"course": c.pk, "category": "kit", "title": "Motor not spinning", "body": "Help!"})
        doubt = Doubt.objects.get()
        self.assertRedirects(r, f"/doubts/{doubt.pk}/")
        # student cannot access staff pages
        for u in ["/users/", "/courses/new/", "/certificates/issue/", "/students/", f"/courses/{c.slug}/students/"]:
            self.assertIn(self.client.get(u).status_code, (302, 403), u)
        # instructor answers the doubt
        self.login("instructor1", "instructor123")
        self.client.post(f"/doubts/{doubt.pk}/", {"body": "Check the motor driver wiring.", "mark_resolved": "on"})
        doubt.refresh_from_db()
        self.assertTrue(doubt.is_resolved)
        # instructor certifies completers
        r = self.client.get(f"/certificates/issue/?course={c.pk}&completed=1")
        self.assertIn(self.student.username, r.context["form"].initial["usernames"])
        self.client.post("/certificates/issue/", {"course": c.pk, "title": "Certificate of Completion",
                                                  "achievement": "completed Level 1", "issued_on": "2026-11-04",
                                                  "usernames": self.student.username})
        cert = Certificate.objects.get()
        self.assertPagesOK([f"/certificates/{cert.code}/"])
        self.client.logout()
        self.assertContains(self.client.get(f"/verify/{cert.code}/"), "Genuine certificate")

    def test_unenrolled_student_blocked(self):
        other = User.objects.create_user("lonely", password="pw123456", role="student", student_type="in_house")
        self.login("lonely", "pw123456")
        self.assertEqual(self.client.get(self.course.get_absolute_url()).status_code, 403)

    def test_school_admin_sees_only_own_students(self):
        other_school = School.objects.create(name="Other School", code="oth")
        outsider = User.objects.create_user("oth260001", password="x" * 8, role="student", school=other_school, student_type="school")
        self.login("school_demo", "school123")
        self.assertPagesOK(["/dashboard/", "/students/", "/users/", f"/students/{self.student.pk}/",
                            f"/courses/{self.course.slug}/report/"])
        self.assertEqual(self.client.get(f"/students/{outsider.pk}/").status_code, 403)
        self.assertNotContains(self.client.get("/students/"), "oth260001")
        # school admins can only create students for their own school
        r = self.client.post("/users/new/", {"first_name": "New", "role": "instructor", "school": other_school.pk})
        self.assertEqual(r.status_code, 200)
        self.assertFalse(User.objects.filter(first_name="New", role="instructor").exists())
        self.assertEqual(self.client.get("/schools/").status_code, 403)

    def test_course_crud_by_instructor(self):
        self.login("instructor1", "instructor123")
        self.client.post("/courses/new/", {"title": "Drone Basics", "level": "beginner", "is_published": "on"})
        course = Course.objects.get(title="Drone Basics")
        self.assertTrue(course.instructors.filter(username="instructor1").exists())
        self.client.post(f"/courses/{course.slug}/lessons/new/", {
            "title": "Intro", "order": 1, "duration_minutes": 5,
            "video_file": SimpleUploadedFile("v.mp4", b"\x00" * 100, content_type="video/mp4")})
        self.assertEqual(course.lessons.count(), 1)
        self.client.post(f"/courses/{course.slug}/quizzes/new/", {"title": "Q1", "pass_percentage": 50,
                                                                  "time_limit_minutes": 0, "max_attempts": 0, "is_published": "on"})
        quiz = course.quizzes.get()
        self.client.post(f"/courses/{course.slug}/quizzes/{quiz.pk}/manage/", {
            "text": "2+2?", "marks": 1, "order": 1, "choice_1": "3", "choice_2": "4", "correct": ["2"]})
        self.assertEqual(quiz.questions.get().choices.get(is_correct=True).text, "4")
        self.client.post(f"/courses/{course.slug}/students/", {"school": self.school.pk})
        self.assertEqual(course.enrollments.count(), User.objects.filter(school=self.school, role="student").count())
        self.client.post(f"/courses/{course.slug}/delete/")
        self.assertFalse(Course.objects.filter(title="Drone Basics").exists())

    def test_instructor_cannot_edit_others_course(self):
        User.objects.create_user("ins2", password="ins2pass", role="instructor")
        self.login("ins2", "ins2pass")
        self.assertEqual(self.client.get(f"/courses/{self.course.slug}/edit/").status_code, 403)
        self.assertEqual(self.client.post(f"/courses/{self.course.slug}/delete/").status_code, 403)


class DoubtHubTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("setup_gnr", owner="owner", password="owner123", demo=True, stdout=io.StringIO())
        cls.course = Course.objects.get()
        s = list(User.objects.filter(role="student", school__code="demo").order_by("username"))
        cls.a, cls.b = s[0], s[1]
        cls.outsider = User.objects.create_user("out1", password="out12345", role="student", student_type="in_house")

    def login(self, user, pw="student123"):
        self.client.logout()
        self.assertEqual(self.client.post("/login/", {"username": user, "password": pw}).status_code, 302)

    def ask(self, **extra):
        data = {"course": self.course.pk, "category": "code", "title": "Servo jitters when moving",
                "body": "```\nservo.write(90);\n```\nIt shakes."}
        data.update(extra)
        self.client.post("/doubts/ask/", data)
        return Doubt.objects.latest("id")

    def test_ask_pages_render(self):
        self.login(self.a.username)
        for url in ["/doubts/", "/doubts/?tab=community", "/doubts/ask/", f"/doubts/ask/?course={self.course.pk}",
                    "/doubts/similar/?q=servo%20jitters"]:
            self.assertEqual(self.client.get(url).status_code, 200, url)
        d = self.ask()
        r = self.client.get(f"/doubts/{d.pk}/")
        self.assertContains(r, "<pre><code>servo.write(90);</code></pre>", html=False)

    def test_general_doubt_and_lesson_must_match_course(self):
        self.login(self.a.username)
        d = self.ask(course="", title="What is PWM?")
        self.assertIsNone(d.course)
        lesson = self.course.lessons.first()
        n = Doubt.objects.count()
        self.client.post("/doubts/ask/", {"course": "", "lesson": lesson.pk, "category": "code", "title": "x", "body": "y"})
        self.assertEqual(Doubt.objects.count(), n)  # rejected: lesson without its course

    def test_cannot_ask_in_unenrolled_course(self):
        self.login("out1", "out12345")
        n = Doubt.objects.count()
        self.client.post("/doubts/ask/", {"course": self.course.pk, "category": "code", "title": "x", "body": "y"})
        self.assertEqual(Doubt.objects.count(), n)

    def test_visibility_privacy_and_community(self):
        self.login(self.a.username)
        public = self.ask()
        private = self.ask(title="Private one", is_private="on")
        # classmate in the same course sees the public doubt but not the private one
        self.login(self.b.username)
        self.assertEqual(self.client.get(f"/doubts/{public.pk}/").status_code, 200)
        self.assertEqual(self.client.get(f"/doubts/{private.pk}/").status_code, 404)
        # student outside the course sees neither
        self.login("out1", "out12345")
        self.assertEqual(self.client.get(f"/doubts/{public.pk}/").status_code, 404)
        # instructor sees both and they are in the unanswered queue
        self.login("instructor1", "instructor123")
        r = self.client.get("/doubts/")
        self.assertContains(r, "Servo jitters")
        self.assertContains(r, "Private one")
        self.assertEqual(self.client.get(f"/doubts/{private.pk}/").status_code, 200)

    def test_metoo_reply_accept_flow(self):
        self.login(self.a.username)
        d = self.ask()
        self.login(self.b.username)
        self.client.post(f"/doubts/{d.pk}/", {"action": "metoo"})
        self.assertEqual(d.me_too.count(), 1)
        # classmates cannot reply or resolve someone else's doubt
        self.client.post(f"/doubts/{d.pk}/", {"action": "reply", "body": "spam"})
        self.assertEqual(d.replies.count(), 0)
        self.assertEqual(self.client.post(f"/doubts/{d.pk}/", {"action": "resolve"}).status_code, 403)
        # instructor answers → leaves queue, shows in community
        self.login("instructor1", "instructor123")
        self.client.post(f"/doubts/{d.pk}/", {"action": "reply", "body": "Power the servo from a separate 5V supply."})
        d.refresh_from_db()
        self.assertTrue(d.has_staff_reply)
        self.assertEqual(d.status, "answered")
        self.login(self.b.username)
        self.assertContains(self.client.get("/doubts/?tab=community"), "Servo jitters")
        # owner accepts the best answer → resolved
        self.login(self.a.username)
        reply = d.replies.get()
        self.client.post(f"/doubts/{d.pk}/", {"action": "accept", "reply": reply.pk})
        d.refresh_from_db(); reply.refresh_from_db()
        self.assertTrue(reply.is_accepted and d.is_resolved)
        # a follow-up from the student reopens it
        self.client.post(f"/doubts/{d.pk}/", {"action": "reply", "body": "Now it twitches again"})
        d.refresh_from_db()
        self.assertFalse(d.is_resolved)

    def test_nav_badge_counts(self):
        self.login(self.a.username)
        self.ask()
        self.login("instructor1", "instructor123")
        self.assertEqual(self.client.get("/dashboard/").context["nav_doubts"], 1)
