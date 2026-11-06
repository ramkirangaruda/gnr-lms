from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import path

from accounts import views as a
from courses import doubts as dq
from courses import views as c
from portal import views as p

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", p.home, name="home"),
    path("dashboard/", p.dashboard, name="dashboard"),

    # auth
    path("login/", auth_views.LoginView.as_view(template_name="accounts/login.html", redirect_authenticated_user=True), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("password/", auth_views.PasswordChangeView.as_view(template_name="accounts/password_change.html",
                                                             success_url="/dashboard/"), name="password_change"),
    path("welcome/password/", a.first_password, name="first_password"),

    # people
    path("users/", a.user_list, name="user_list"),
    path("users/new/", a.user_create, name="user_create"),
    path("users/generate/", a.bulk_generate, name="bulk_generate"),
    path("users/<int:pk>/", a.user_edit, name="user_edit"),
    path("users/<int:pk>/reset-password/", a.user_reset_password, name="user_reset_password"),
    path("users/<int:pk>/delete/", a.user_delete, name="user_delete"),
    path("schools/", a.school_list, name="school_list"),
    path("schools/new/", a.school_form, name="school_create"),
    path("schools/<int:pk>/", a.school_form, name="school_edit"),
    path("students/", c.students_overview, name="students_overview"),
    path("students/<int:pk>/", c.student_report, name="student_report"),

    # courses
    path("courses/", c.course_list, name="course_list"),
    path("courses/new/", c.course_form, name="course_create"),
    path("courses/<slug:slug>/", c.course_detail, name="course_detail"),
    path("courses/<slug:slug>/edit/", c.course_form, name="course_edit"),
    path("courses/<slug:slug>/delete/", c.course_delete, name="course_delete"),
    path("courses/<slug:slug>/students/", c.course_students, name="course_students"),
    path("courses/<slug:slug>/report/", c.course_report, name="course_report"),
    path("courses/<slug:slug>/lessons/new/", c.lesson_form, name="lesson_create"),
    path("courses/<slug:slug>/lessons/bunny-upload/", c.lesson_bunny_upload, name="lesson_bunny_upload"),
    path("courses/<slug:slug>/lessons/<int:pk>/", c.lesson_detail, name="lesson_detail"),
    path("courses/<slug:slug>/lessons/<int:pk>/edit/", c.lesson_form, name="lesson_edit"),
    path("courses/<slug:slug>/lessons/<int:pk>/delete/", c.lesson_delete, name="lesson_delete"),
    path("courses/<slug:slug>/quizzes/new/", c.quiz_form, name="quiz_create"),
    path("courses/<slug:slug>/quizzes/<int:pk>/edit/", c.quiz_form, name="quiz_edit"),
    path("courses/<slug:slug>/quizzes/<int:pk>/manage/", c.quiz_manage, name="quiz_manage"),
    path("courses/<slug:slug>/quizzes/<int:pk>/", c.quiz_take, name="quiz_take"),
    path("courses/<slug:slug>/quizzes/<int:pk>/result/<int:attempt>/", c.quiz_result, name="quiz_result"),
    path("courses/<slug:slug>/ask/", dq.doubt_create, name="doubt_create"),

    # doubts & certificates
    path("doubts/", dq.doubt_list, name="doubt_list"),
    path("doubts/ask/", dq.doubt_ask, name="doubt_ask"),
    path("doubts/similar/", dq.doubt_similar, name="doubt_similar"),
    path("doubts/<int:pk>/", dq.doubt_detail, name="doubt_detail"),
    path("certificates/", c.certificate_list, name="certificate_list"),
    path("certificates/issue/", c.certificate_issue, name="certificate_issue"),
    path("certificates/<uuid:code>/", c.certificate_view, name="certificate_view"),
    path("verify/<uuid:code>/", c.certificate_verify, name="certificate_verify"),

    # portal content
    path("newsletters/", p.newsletter_list, name="newsletter_list"),
    path("newsletters/new/", p.newsletter_form, name="newsletter_create"),
    path("newsletters/<int:pk>/", p.newsletter_detail, name="newsletter_detail"),
    path("newsletters/<int:pk>/edit/", p.newsletter_form, name="newsletter_edit"),
    path("gallery/", p.gallery, name="gallery"),
    path("gallery/new/", p.gallery_form, name="gallery_create"),
    path("gallery/<int:pk>/edit/", p.gallery_form, name="gallery_edit"),
    path("competitions/", p.competition_list, name="competition_list"),
    path("competitions/new/", p.competition_form, name="competition_create"),
    path("competitions/<int:pk>/", p.competition_detail, name="competition_detail"),
    path("competitions/<int:pk>/edit/", p.competition_form, name="competition_edit"),
]

if settings.DEBUG or settings.STORAGES["default"]["BACKEND"].endswith("FileSystemStorage"):
    # In production nginx serves /media/ directly; this is a fallback.
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

admin.site.site_header = "GNR Robotics LMS – Admin"
