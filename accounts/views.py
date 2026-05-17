from datetime import time

from django.contrib import messages
from django.contrib.auth import get_user_model, login
from django.contrib.auth.views import LoginView, LogoutView
from django.shortcuts import redirect, render
from django.urls import reverse

from clinics.models import Clinic, ClinicGroup, ClinicMembership
from services.models import Service
from scheduling.models import ClinicBusinessHour, Weekday

from .forms import LoginForm, SignUpForm


User = get_user_model()


class EmailLoginView(LoginView):
    template_name = "accounts/login.html"
    authentication_form = LoginForm

    def get_success_url(self):
        return super().get_success_url()


class AppLogoutView(LogoutView):
    pass


def signup(request):
    if request.method == "POST":
        form = SignUpForm(request.POST)
        if form.is_valid():
            full_name = form.cleaned_data["full_name"]
            first_name, _, last_name = full_name.partition(" ")
            user = User.objects.create_user(
                username=form.cleaned_data["email"],
                email=form.cleaned_data["email"],
                password=form.cleaned_data["password"],
                first_name=first_name,
                last_name=last_name,
            )
            group = ClinicGroup.objects.create(name=form.cleaned_data["clinic_name"], owner=user)
            clinic = Clinic.objects.create(group=group, name=form.cleaned_data["clinic_name"], slug=form.cleaned_data["clinic_slug"], email=user.email)
            ClinicMembership.objects.create(clinic=clinic, user=user, role=ClinicMembership.ROLE_OWNER)
            service = Service.objects.create(clinic=clinic, name="General Consultation", duration_minutes=30, price=0)
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
            return redirect("dashboard:home")
    else:
        form = SignUpForm()
    return render(request, "accounts/signup.html", {"form": form})
