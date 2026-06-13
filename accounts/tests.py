import re
from datetime import time

import pytest
from django.contrib.auth import get_user_model
from django.core import mail
from django.urls import reverse

from clinics.models import Clinic, ClinicGroup, ClinicMembership
from patients.models import Patient
from scheduling.models import ClinicBusinessHour
from services.models import Service


def _onboarding_post_data():
    data = {
        "address": "123 Demo Street",
        "phone": "09170001111",
        "email": "frontdesk@example.com",
        "timezone": "Asia/Manila",
        "default_appointment_duration": "45",
        "booking_approval_mode": Clinic.APPROVAL_MANUAL,
        "service_name": "Dental Cleaning",
        "service_duration_minutes": "45",
    }
    for weekday in range(7):
        data[f"open_time_{weekday}"] = "09:00"
        data[f"close_time_{weekday}"] = "17:00"
        if weekday < 5:
            data[f"is_open_{weekday}"] = "on"
            data[f"break_start_{weekday}"] = "12:00"
            data[f"break_end_{weekday}"] = "13:00"
    return data


def _password_reset_path_from_email(message):
    match = re.search(r"http://testserver(?P<path>/accounts/reset/[^\s]+)", message.body)
    assert match, message.body
    return match.group("path")


def _dashboard_user(email="owner@example.com", password="OldStrongPass!2026"):
    User = get_user_model()
    user = User.objects.create_user(username=email, email=email, password=password)
    group = ClinicGroup.objects.create(name="Demo Clinic", owner=user)
    clinic = Clinic.objects.create(group=group, name="Demo Clinic", slug="demo-clinic")
    ClinicMembership.objects.create(clinic=clinic, user=user, role=ClinicMembership.ROLE_OWNER)
    return user, clinic


@pytest.mark.django_db
def test_signup_requires_password_confirmation(client):
    response = client.post(
        reverse("accounts:signup"),
        {
            "full_name": "Demo User",
            "email": "demo@example.com",
            "clinic_name": "Demo Clinic",
            "timezone": "Asia/Manila",
            "password": "password12345",
            "password_confirm": "different12345",
            "terms_accepted": "on",
        },
    )

    assert response.status_code == 200
    assert b"Passwords do not match." in response.content
    assert get_user_model().objects.count() == 0


@pytest.mark.django_db
def test_signup_requires_terms_acceptance(client):
    response = client.post(
        reverse("accounts:signup"),
        {
            "full_name": "Demo User",
            "email": "demo@example.com",
            "clinic_name": "Demo Clinic",
            "timezone": "Asia/Manila",
            "password": "Str0ngSignupPass!2026",
            "password_confirm": "Str0ngSignupPass!2026",
        },
    )

    assert response.status_code == 200
    assert b"You must accept the terms and privacy policy." in response.content
    assert get_user_model().objects.count() == 0


@pytest.mark.django_db
def test_signup_saves_timezone_consent_and_requires_onboarding(client):
    response = client.post(
        reverse("accounts:signup"),
        {
            "full_name": "Demo User",
            "email": "Demo@Example.com",
            "clinic_name": "Demo Clinic",
            "timezone": "Pacific/Kiritimati",
            "password": "Str0ngSignupPass!2026",
            "password_confirm": "Str0ngSignupPass!2026",
            "terms_accepted": "on",
        },
    )

    assert response.status_code == 302
    assert response.url == reverse("accounts:onboarding")
    user = get_user_model().objects.get(email="demo@example.com")
    assert user.terms_accepted_at is not None
    clinic = Clinic.objects.get(slug="demo-clinic")
    assert clinic.timezone == "Pacific/Kiritimati"
    assert clinic.requires_onboarding is True


@pytest.mark.django_db
def test_login_page_links_to_password_reset(client):
    response = client.get(reverse("accounts:login"))

    assert response.status_code == 200
    assert reverse("accounts:password_reset").encode() in response.content
    assert b"Forgot password?" in response.content


@pytest.mark.django_db
def test_signup_page_does_not_link_to_password_reset(client):
    response = client.get(reverse("accounts:signup"))

    assert response.status_code == 200
    assert reverse("accounts:password_reset").encode() not in response.content
    assert b"Forgot password?" not in response.content


@pytest.mark.django_db
def test_password_reset_request_sends_email_for_existing_dashboard_user(client, settings):
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    mail.outbox = []
    _dashboard_user()

    response = client.post(reverse("accounts:password_reset"), {"email": "owner@example.com"})

    assert response.status_code == 302
    assert response.url == reverse("accounts:password_reset_done")
    assert len(mail.outbox) == 1
    assert "Reset your KliniAssist password" in mail.outbox[0].subject
    assert "/accounts/reset/" in mail.outbox[0].body


@pytest.mark.django_db
def test_password_reset_request_for_unknown_email_is_generic(client, settings):
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    mail.outbox = []

    response = client.post(reverse("accounts:password_reset"), {"email": "unknown@example.com"})

    assert response.status_code == 302
    assert response.url == reverse("accounts:password_reset_done")
    assert len(mail.outbox) == 0


@pytest.mark.django_db
def test_password_reset_request_for_patient_email_is_generic(client, settings):
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    mail.outbox = []
    _user, clinic = _dashboard_user()
    Patient.objects.create(
        clinic=clinic,
        full_name="Guest Patient",
        phone="09170001111",
        email="patient@example.com",
    )

    response = client.post(reverse("accounts:password_reset"), {"email": "patient@example.com"})

    assert response.status_code == 302
    assert response.url == reverse("accounts:password_reset_done")
    assert len(mail.outbox) == 0


@pytest.mark.django_db
def test_password_reset_confirm_changes_password(client, settings):
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    mail.outbox = []
    user, _clinic = _dashboard_user()
    client.post(reverse("accounts:password_reset"), {"email": "owner@example.com"})
    reset_path = _password_reset_path_from_email(mail.outbox[0])

    response = client.get(reset_path)
    assert response.status_code == 302
    confirm_path = response["Location"]
    response = client.post(
        confirm_path,
        {
            "new_password1": "NewStrongPass!2026",
            "new_password2": "NewStrongPass!2026",
        },
    )

    assert response.status_code == 302
    assert response.url == reverse("accounts:password_reset_complete")
    user.refresh_from_db()
    assert user.check_password("NewStrongPass!2026")
    assert client.login(username="owner@example.com", password="NewStrongPass!2026")


@pytest.mark.django_db
def test_password_reset_token_cannot_be_reused(client, settings):
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    mail.outbox = []
    _dashboard_user()
    client.post(reverse("accounts:password_reset"), {"email": "owner@example.com"})
    reset_path = _password_reset_path_from_email(mail.outbox[0])
    confirm_path = client.get(reset_path)["Location"]
    client.post(
        confirm_path,
        {
            "new_password1": "NewStrongPass!2026",
            "new_password2": "NewStrongPass!2026",
        },
    )

    response = client.get(reset_path)

    assert response.status_code == 200
    assert b"This password reset link is invalid or has already been used." in response.content


@pytest.mark.django_db
def test_password_change_form_uses_design_system_classes():
    from accounts.forms import AppPasswordChangeForm

    user = get_user_model().objects.create_user(
        username="owner@example.com",
        email="owner@example.com",
        password="OldStrongPass!2026",
    )

    form = AppPasswordChangeForm(user)

    assert form.fields["old_password"].widget.attrs["class"] == "cf-input"
    assert form.fields["old_password"].widget.attrs["autocomplete"] == "current-password"
    assert form.fields["new_password1"].widget.attrs["class"] == "cf-input"
    assert form.fields["new_password1"].widget.attrs["autocomplete"] == "new-password"
    assert form.fields["new_password2"].widget.attrs["class"] == "cf-input"
    assert form.fields["new_password2"].widget.attrs["autocomplete"] == "new-password"


@pytest.mark.django_db
def test_onboarding_requires_login(client):
    response = client.get(reverse("accounts:onboarding"))

    assert response.status_code == 302
    assert reverse("accounts:login") in response.url


@pytest.mark.django_db
def test_onboarding_requires_owner_role(client):
    User = get_user_model()
    owner = User.objects.create_user(
        username="owner@example.com",
        email="owner@example.com",
        password="password123",
    )
    staff_user = User.objects.create_user(
        username="staff@example.com",
        email="staff@example.com",
        password="password123",
    )
    group = ClinicGroup.objects.create(name="Demo Clinic", owner=owner)
    clinic = Clinic.objects.create(group=group, name="Demo Clinic", slug="demo-clinic")
    ClinicMembership.objects.create(clinic=clinic, user=staff_user, role=ClinicMembership.ROLE_STAFF)
    client.force_login(staff_user)

    response = client.get(reverse("accounts:onboarding"))

    assert response.status_code == 403


@pytest.mark.django_db
def test_onboarding_saves_clinic_service_hours_and_clears_flag(client):
    User = get_user_model()
    user = User.objects.create_user(
        username="owner@example.com",
        email="owner@example.com",
        password="password123",
    )
    group = ClinicGroup.objects.create(name="Demo Clinic", owner=user)
    clinic = Clinic.objects.create(
        group=group,
        name="Demo Clinic",
        slug="demo-clinic",
        requires_onboarding=True,
    )
    ClinicMembership.objects.create(clinic=clinic, user=user, role=ClinicMembership.ROLE_OWNER)
    Service.objects.create(clinic=clinic, name="General Consultation", duration_minutes=30)
    client.force_login(user)

    response = client.post(reverse("accounts:onboarding"), _onboarding_post_data())

    assert response.status_code == 302
    assert response.url == reverse("dashboard:home")
    clinic.refresh_from_db()
    assert clinic.requires_onboarding is False
    assert clinic.address == "123 Demo Street"
    assert clinic.phone == "09170001111"
    assert clinic.email == "frontdesk@example.com"
    assert clinic.timezone == "Asia/Manila"
    assert clinic.default_appointment_duration == 45
    assert clinic.booking_approval_mode == Clinic.APPROVAL_MANUAL
    service = clinic.services.get(name="Dental Cleaning")
    assert service.name == "Dental Cleaning"
    assert service.duration_minutes == 45
    assert service.is_active is True
    assert service.is_archived is False
    assert not clinic.services.filter(name="General Consultation").exists()
    business_hours = {
        business_hour.weekday: business_hour
        for business_hour in ClinicBusinessHour.objects.filter(clinic=clinic)
    }
    assert set(business_hours) == set(range(7))
    for weekday in range(5):
        business_hour = business_hours[weekday]
        assert business_hour.is_open is True
        assert business_hour.open_time == time(9, 0)
        assert business_hour.close_time == time(17, 0)
        assert business_hour.break_start == time(12, 0)
        assert business_hour.break_end == time(13, 0)
    for weekday in range(5, 7):
        assert business_hours[weekday].is_open is False


@pytest.mark.django_db
def test_onboarding_business_hours_table_uses_scoped_headers(client):
    User = get_user_model()
    user = User.objects.create_user(
        username="owner@example.com",
        email="owner@example.com",
        password="password123",
    )
    group = ClinicGroup.objects.create(name="Demo Clinic", owner=user)
    clinic = Clinic.objects.create(
        group=group,
        name="Demo Clinic",
        slug="demo-clinic",
        requires_onboarding=True,
    )
    ClinicMembership.objects.create(clinic=clinic, user=user, role=ClinicMembership.ROLE_OWNER)
    Service.objects.create(clinic=clinic, name="General Consultation", duration_minutes=30)
    client.force_login(user)

    response = client.get(reverse("accounts:onboarding"))

    assert response.status_code == 200
    assert b'<th scope="col" class="p-4">Day</th>' in response.content
    assert b'<th scope="col">Open</th>' in response.content
    assert b'<th scope="col">Hours</th>' in response.content
    assert b'<th scope="col">Break</th>' in response.content
    assert b'<th scope="row" class="p-4 font-semibold text-[var(--cf-ink)]">Monday</th>' in response.content


@pytest.mark.django_db
def test_completed_onboarding_post_redirects_without_overwriting_clinic_data(client):
    User = get_user_model()
    user = User.objects.create_user(
        username="owner@example.com",
        email="owner@example.com",
        password="password123",
    )
    group = ClinicGroup.objects.create(name="Demo Clinic", owner=user)
    clinic = Clinic.objects.create(
        group=group,
        name="Demo Clinic",
        slug="demo-clinic",
        address="Existing address",
        phone="09998887777",
        email="existing@example.com",
        timezone="Pacific/Kiritimati",
        default_appointment_duration=30,
        booking_approval_mode=Clinic.APPROVAL_AUTO,
        requires_onboarding=False,
    )
    ClinicMembership.objects.create(clinic=clinic, user=user, role=ClinicMembership.ROLE_OWNER)
    service = Service.objects.create(clinic=clinic, name="Existing Service", duration_minutes=30)
    client.force_login(user)

    response = client.post(reverse("accounts:onboarding"), _onboarding_post_data())

    assert response.status_code == 302
    assert response.url == reverse("dashboard:home")
    clinic.refresh_from_db()
    service.refresh_from_db()
    assert clinic.address == "Existing address"
    assert clinic.phone == "09998887777"
    assert clinic.email == "existing@example.com"
    assert clinic.timezone == "Pacific/Kiritimati"
    assert clinic.default_appointment_duration == 30
    assert clinic.booking_approval_mode == Clinic.APPROVAL_AUTO
    assert clinic.requires_onboarding is False
    assert service.name == "Existing Service"
    assert service.duration_minutes == 30


@pytest.mark.django_db
def test_onboarding_duplicate_service_name_returns_form_error_without_clearing_flag(client):
    User = get_user_model()
    user = User.objects.create_user(
        username="owner@example.com",
        email="owner@example.com",
        password="password123",
    )
    group = ClinicGroup.objects.create(name="Demo Clinic", owner=user)
    clinic = Clinic.objects.create(
        group=group,
        name="Demo Clinic",
        slug="demo-clinic",
        requires_onboarding=True,
    )
    ClinicMembership.objects.create(clinic=clinic, user=user, role=ClinicMembership.ROLE_OWNER)
    Service.objects.create(clinic=clinic, name="General Consultation", duration_minutes=30)
    Service.objects.create(clinic=clinic, name="Dental Cleaning", duration_minutes=60)
    client.force_login(user)

    response = client.post(reverse("accounts:onboarding"), _onboarding_post_data())

    assert response.status_code == 200
    assert b"A service with this name already exists." in response.content
    clinic.refresh_from_db()
    assert clinic.requires_onboarding is True


@pytest.mark.django_db
def test_onboarding_archived_duplicate_service_name_returns_form_error_without_clearing_flag(client):
    User = get_user_model()
    user = User.objects.create_user(
        username="owner@example.com",
        email="owner@example.com",
        password="password123",
    )
    group = ClinicGroup.objects.create(name="Demo Clinic", owner=user)
    clinic = Clinic.objects.create(
        group=group,
        name="Demo Clinic",
        slug="demo-clinic",
        requires_onboarding=True,
    )
    ClinicMembership.objects.create(clinic=clinic, user=user, role=ClinicMembership.ROLE_OWNER)
    Service.objects.create(clinic=clinic, name="General Consultation", duration_minutes=30)
    Service.objects.create(
        clinic=clinic,
        name="Dental Cleaning",
        duration_minutes=60,
        is_archived=True,
    )
    client.force_login(user)

    response = client.post(reverse("accounts:onboarding"), _onboarding_post_data())

    assert response.status_code == 200
    assert b"A service with this name already exists." in response.content
    clinic.refresh_from_db()
    assert clinic.requires_onboarding is True


@pytest.mark.django_db
def test_onboarding_allows_duplicate_service_name_in_another_clinic(client):
    User = get_user_model()
    user = User.objects.create_user(
        username="owner@example.com",
        email="owner@example.com",
        password="password123",
    )
    other_owner = User.objects.create_user(
        username="other@example.com",
        email="other@example.com",
        password="password123",
    )
    group = ClinicGroup.objects.create(name="Demo Clinic", owner=user)
    clinic = Clinic.objects.create(
        group=group,
        name="Demo Clinic",
        slug="demo-clinic",
        requires_onboarding=True,
    )
    other_group = ClinicGroup.objects.create(name="Other Clinic", owner=other_owner)
    other_clinic = Clinic.objects.create(group=other_group, name="Other Clinic", slug="other-clinic")
    ClinicMembership.objects.create(clinic=clinic, user=user, role=ClinicMembership.ROLE_OWNER)
    Service.objects.create(clinic=clinic, name="General Consultation", duration_minutes=30)
    Service.objects.create(clinic=other_clinic, name="Dental Cleaning", duration_minutes=60)
    client.force_login(user)

    response = client.post(reverse("accounts:onboarding"), _onboarding_post_data())

    assert response.status_code == 302
    assert response.url == reverse("dashboard:home")
    clinic.refresh_from_db()
    assert clinic.requires_onboarding is False
    service = clinic.services.get(name="Dental Cleaning")
    assert service.duration_minutes == 45


@pytest.mark.django_db
def test_onboarding_rejects_close_time_before_open_time_without_clearing_flag(client):
    User = get_user_model()
    user = User.objects.create_user(
        username="owner@example.com",
        email="owner@example.com",
        password="password123",
    )
    group = ClinicGroup.objects.create(name="Demo Clinic", owner=user)
    clinic = Clinic.objects.create(
        group=group,
        name="Demo Clinic",
        slug="demo-clinic",
        requires_onboarding=True,
    )
    ClinicMembership.objects.create(clinic=clinic, user=user, role=ClinicMembership.ROLE_OWNER)
    Service.objects.create(clinic=clinic, name="General Consultation", duration_minutes=30)
    client.force_login(user)
    data = _onboarding_post_data()
    data["open_time_0"] = "17:00"
    data["close_time_0"] = "09:00"

    response = client.post(reverse("accounts:onboarding"), data)

    assert response.status_code == 200
    assert b"Close time must be after open time." in response.content
    clinic.refresh_from_db()
    assert clinic.requires_onboarding is True


@pytest.mark.django_db
def test_onboarding_rejects_unpaired_break_time_without_clearing_flag(client):
    User = get_user_model()
    user = User.objects.create_user(
        username="owner@example.com",
        email="owner@example.com",
        password="password123",
    )
    group = ClinicGroup.objects.create(name="Demo Clinic", owner=user)
    clinic = Clinic.objects.create(
        group=group,
        name="Demo Clinic",
        slug="demo-clinic",
        requires_onboarding=True,
    )
    ClinicMembership.objects.create(clinic=clinic, user=user, role=ClinicMembership.ROLE_OWNER)
    Service.objects.create(clinic=clinic, name="General Consultation", duration_minutes=30)
    client.force_login(user)
    data = _onboarding_post_data()
    data.pop("break_end_0")

    response = client.post(reverse("accounts:onboarding"), data)

    assert response.status_code == 200
    assert b"Break start and end times must be provided together." in response.content
    clinic.refresh_from_db()
    assert clinic.requires_onboarding is True
