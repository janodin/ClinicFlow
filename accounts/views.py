from datetime import time

from django.contrib import messages
from django.contrib.auth import get_user_model, login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import (
    LoginView,
    LogoutView,
    PasswordResetCompleteView,
    PasswordResetConfirmView,
    PasswordResetDoneView,
    PasswordResetView,
)
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.shortcuts import redirect, render
from django.urls import reverse_lazy
from django.utils import timezone

from clinics.models import Clinic, ClinicGroup, ClinicMembership
from clinics.tenant import get_active_membership
from services.models import Service
from scheduling.models import ClinicBusinessHour, Weekday

from .forms import AppPasswordResetForm, AppSetPasswordForm, FirstRunOnboardingForm, LoginForm, SignUpForm


User = get_user_model()


class EmailLoginView(LoginView):
    template_name = "accounts/login.html"
    authentication_form = LoginForm

    def get_success_url(self):
        return super().get_success_url()


class AppLogoutView(LogoutView):
    pass


class AppPasswordResetView(PasswordResetView):
    template_name = "accounts/password_reset.html"
    form_class = AppPasswordResetForm
    email_template_name = "accounts/password_reset_email.html"
    subject_template_name = "accounts/password_reset_subject.txt"
    success_url = reverse_lazy("accounts:password_reset_done")


class AppPasswordResetDoneView(PasswordResetDoneView):
    template_name = "accounts/password_reset_done.html"


class AppPasswordResetConfirmView(PasswordResetConfirmView):
    template_name = "accounts/password_reset_confirm.html"
    form_class = AppSetPasswordForm
    success_url = reverse_lazy("accounts:password_reset_complete")


class AppPasswordResetCompleteView(PasswordResetCompleteView):
    template_name = "accounts/password_reset_complete.html"


def signup(request):
    if request.method == "POST":
        form = SignUpForm(request.POST)
        if form.is_valid():
            full_name = form.cleaned_data["full_name"]
            first_name, _, last_name = full_name.partition(" ")
            with transaction.atomic():
                user = User.objects.create_user(
                    username=form.cleaned_data["email"],
                    email=form.cleaned_data["email"],
                    password=form.cleaned_data["password"],
                    first_name=first_name,
                    last_name=last_name,
                    terms_accepted_at=timezone.now(),
                )
                group = ClinicGroup.objects.create(name=form.cleaned_data["clinic_name"], owner=user)
                clinic = Clinic.objects.create(
                    group=group,
                    name=form.cleaned_data["clinic_name"],
                    slug=form.cleaned_data["clinic_slug"],
                    email=user.email,
                    timezone=form.cleaned_data["timezone"],
                    requires_onboarding=True,
                )
                ClinicMembership.objects.create(clinic=clinic, user=user, role=ClinicMembership.ROLE_OWNER)
                Service.objects.create(clinic=clinic, name="General Consultation", duration_minutes=30)
                for weekday in range(0, 5):
                    ClinicBusinessHour.objects.create(
                        clinic=clinic,
                        weekday=weekday,
                        open_time=time(9, 0),
                        close_time=time(17, 0),
                        break_start=time(12, 0),
                        break_end=time(13, 0),
                    )
            messages.success(request, "Your clinic workspace is ready.")
            login(request, user)
            return redirect("accounts:onboarding")
    else:
        form = SignUpForm()
    return render(request, "accounts/signup.html", {"form": form})


@login_required
def onboarding(request):
    membership = get_active_membership(request.user)
    if not membership:
        return redirect("accounts:signup")
    if membership.role != ClinicMembership.ROLE_OWNER:
        raise PermissionDenied

    clinic = membership.clinic
    if not clinic.requires_onboarding:
        return redirect("dashboard:home")

    service = clinic.services.filter(is_archived=False).order_by("created_at", "id").first()
    if request.method == "POST":
        form = FirstRunOnboardingForm(request.POST, clinic=clinic, service=service)
        if form.is_valid():
            with transaction.atomic():
                clinic.address = form.cleaned_data["address"]
                clinic.phone = form.cleaned_data["phone"]
                clinic.email = form.cleaned_data["email"]
                clinic.timezone = form.cleaned_data["timezone"]
                clinic.default_appointment_duration = form.cleaned_data["default_appointment_duration"]
                clinic.booking_approval_mode = form.cleaned_data["booking_approval_mode"]
                clinic.requires_onboarding = False
                clinic.save(update_fields=[
                    "address",
                    "phone",
                    "email",
                    "timezone",
                    "default_appointment_duration",
                    "booking_approval_mode",
                    "requires_onboarding",
                    "updated_at",
                ])

                if service is None:
                    service = Service(clinic=clinic)
                service.name = form.cleaned_data["service_name"]
                service.duration_minutes = form.cleaned_data["service_duration_minutes"]
                service.is_active = True
                service.is_archived = False
                service.save()

                for row in form.business_hour_rows:
                    ClinicBusinessHour.objects.update_or_create(
                        clinic=clinic,
                        weekday=row["weekday"],
                        defaults={
                            "is_open": row["is_open"],
                            "open_time": row["open_time"],
                            "close_time": row["close_time"],
                            "break_start": row["break_start"],
                            "break_end": row["break_end"],
                        },
                    )
            messages.success(request, "Your clinic setup is complete.")
            return redirect("dashboard:home")
    else:
        form = FirstRunOnboardingForm(clinic=clinic, service=service)

    weekday_rows = [
        {
            "weekday": weekday,
            "label": label,
            "is_open": form[f"is_open_{weekday}"],
            "open_time": form[f"open_time_{weekday}"],
            "close_time": form[f"close_time_{weekday}"],
            "break_start": form[f"break_start_{weekday}"],
            "break_end": form[f"break_end_{weekday}"],
        }
        for weekday, label in Weekday.choices
    ]
    return render(request, "accounts/onboarding.html", {"form": form, "clinic": clinic, "weekday_rows": weekday_rows})
