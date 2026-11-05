from django.contrib import messages
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render

from .forms import BulkGenerateForm, ForcedPasswordChangeForm, SchoolForm, UserCreateForm, UserEditForm
from .models import School, User
from .permissions import manager_required, owner_required, visible_students
from .services import bulk_create_students, credentials_csv_data_uri, random_password, username_prefix, _next_seq


def _manageable_users(actor):
    if actor.is_owner:
        return User.objects.select_related("school")
    return visible_students(actor)


def _check_can_manage(actor, target):
    if not _manageable_users(actor).filter(pk=target.pk).exists():
        raise PermissionDenied


@manager_required
def user_list(request):
    qs = _manageable_users(request.user).order_by("role", "school__name", "username")
    role, school, q = request.GET.get("role", ""), request.GET.get("school", ""), request.GET.get("q", "").strip()
    stype = request.GET.get("type", "")
    if role:
        qs = qs.filter(role=role)
    if school:
        qs = qs.filter(school_id=school)
    if stype:
        qs = qs.filter(student_type=stype)
    if q:
        qs = qs.filter(Q(username__icontains=q) | Q(first_name__icontains=q) | Q(last_name__icontains=q)
                       | Q(email__icontains=q) | Q(batch__icontains=q))
    page = Paginator(qs, 50).get_page(request.GET.get("page"))
    schools = School.objects.all() if not request.user.is_school_admin else School.objects.filter(pk=request.user.school_id)
    return render(request, "accounts/user_list.html", {
        "page": page, "roles": User.Role.choices, "types": User.StudentType.choices, "schools": schools,
        "f": {"role": role, "school": school, "q": q, "type": stype},
    })


@manager_required
def user_create(request):
    form = UserCreateForm(request.POST or None, actor=request.user,
                          initial={"school": request.user.school_id} if request.user.is_school_admin else None)
    if request.method == "POST" and form.is_valid():
        u = form.save(commit=False)
        if request.user.is_school_admin:
            u.role, u.school, u.student_type = User.Role.STUDENT, request.user.school, User.StudentType.SCHOOL
        if u.role == User.Role.STUDENT and not u.student_type:
            u.student_type = User.StudentType.SCHOOL if u.school else User.StudentType.IN_HOUSE
        if not u.username:
            prefix = username_prefix(u.student_type, u.school) if u.role == User.Role.STUDENT else u.role[:4] + "_"
            u.username = f"{prefix}{_next_seq(prefix):04d}"
        password = form.cleaned_data["password"] or random_password()
        u.set_password(password)
        u.must_change_password = not form.cleaned_data["password"]
        u.save()
        return render(request, "accounts/credentials.html", {
            "created": [(u, password)], "csv_uri": credentials_csv_data_uri([(u, password)])})
    return render(request, "accounts/user_form.html", {"form": form, "title": "Create login"})


@manager_required
def user_edit(request, pk):
    target = get_object_or_404(User, pk=pk)
    _check_can_manage(request.user, target)
    form = UserEditForm(request.POST or None, instance=target, actor=request.user)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, f"Saved {target.username}.")
        return redirect("user_list")
    return render(request, "accounts/user_form.html", {"form": form, "title": f"Edit {target.username}", "target": target})


@manager_required
def user_reset_password(request, pk):
    target = get_object_or_404(User, pk=pk)
    _check_can_manage(request.user, target)
    if request.method != "POST":
        return redirect("user_edit", pk=pk)
    password = random_password()
    target.set_password(password)
    target.must_change_password = True
    target.save(update_fields=["password", "must_change_password"])
    return render(request, "accounts/credentials.html", {
        "created": [(target, password)], "csv_uri": credentials_csv_data_uri([(target, password)]), "reset": True})


@owner_required
def user_delete(request, pk):
    target = get_object_or_404(User, pk=pk)
    if target == request.user:
        messages.error(request, "You cannot delete your own account.")
    elif request.method == "POST":
        target.delete()
        messages.success(request, f"Deleted {target.username}.")
    return redirect("user_list")


@manager_required
def bulk_generate(request):
    if not (request.user.is_owner or request.user.is_instructor or request.user.school_id):
        raise PermissionDenied
    form = BulkGenerateForm(request.POST or None, request.FILES or None, actor=request.user,
                            initial={"school": request.user.school_id} if request.user.is_school_admin else None)
    if request.method == "POST" and form.is_valid():
        from courses.models import Course
        d = form.cleaned_data
        school = d["school"]
        if request.user.is_school_admin:
            school = request.user.school
        created = bulk_create_students(
            d["rows"], d["student_type"], school=school, grade=d["grade"], batch=d["batch"],
            courses=list(Course.objects.filter(pk__in=d["course_ids"])))
        messages.success(request, f"Created {len(created)} student accounts. Download the credentials now – passwords are not shown again.")
        return render(request, "accounts/credentials.html", {"created": created, "csv_uri": credentials_csv_data_uri(created)})
    return render(request, "accounts/bulk_generate.html", {"form": form})


@owner_required
def school_list(request):
    schools = School.objects.annotate(n_students=Count("users", filter=Q(users__role=User.Role.STUDENT)))
    return render(request, "accounts/school_list.html", {"schools": schools})


@owner_required
def school_form(request, pk=None):
    school = get_object_or_404(School, pk=pk) if pk else None
    form = SchoolForm(request.POST or None, instance=school)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "School saved.")
        return redirect("school_list")
    return render(request, "accounts/user_form.html", {"form": form, "title": "Edit school" if school else "Add school"})


@login_required
def first_password(request):
    form = ForcedPasswordChangeForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        u = request.user
        u.set_password(form.cleaned_data["new_password1"])
        u.must_change_password = False
        u.save()
        update_session_auth_hash(request, u)
        messages.success(request, "Password updated. Welcome to GNR Robotics!")
        return redirect("dashboard")
    return render(request, "accounts/user_form.html", {
        "form": form, "title": "Set your new password",
        "intro": "For your security, please choose a new password before continuing."})
