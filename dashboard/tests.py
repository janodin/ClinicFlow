import csv
import io
import json
import re
import pytest
from datetime import time, timedelta, timezone as dt_timezone
from zoneinfo import ZoneInfo
from django.contrib import messages
from django.contrib.messages import get_messages
from django.contrib.auth import get_user_model
from django.contrib.messages.storage.fallback import FallbackStorage
from django.http import HttpResponse
from django.test import RequestFactory, override_settings
from django.urls import reverse
from requests import RequestException
from unittest.mock import patch

from clinics.models import Clinic, ClinicGroup, ClinicMembership
from patients.models import Patient
from services.models import Service
from appointments.models import Appointment, AppointmentNote
from django.utils import timezone
from scheduling.models import ClinicBusinessHour, UnavailableDate
from dashboard.middleware import HtmxMessagesMiddleware


@pytest.fixture
def clinic_setup(db):
    User = get_user_model()
    user = User.objects.create_user(username="owner@example.com", email="owner@example.com", password="password123")
    group = ClinicGroup.objects.create(name="Demo Clinic", owner=user)
    clinic = Clinic.objects.create(group=group, name="Demo Clinic", slug="demo-clinic")
    ClinicMembership.objects.create(clinic=clinic, user=user, role=ClinicMembership.ROLE_OWNER)
    service = Service.objects.create(clinic=clinic, name="General Consultation", duration_minutes=30)
    return clinic, service, user


@pytest.fixture
def calendar_setup(clinic_setup):
    clinic, service, user = clinic_setup
    target_date = timezone.localdate() + timedelta(days=1)
    ClinicBusinessHour.objects.create(
        clinic=clinic,
        weekday=target_date.weekday(),
        is_open=True,
        open_time=time(9),
        close_time=time(17),
        break_start=time(12),
        break_end=time(13),
    )
    patient = Patient.objects.create(
        clinic=clinic,
        full_name="Test Patient",
        phone="09170001111",
        email="test.patient@example.com",
    )
    starts_at = timezone.make_aware(timezone.datetime.combine(target_date, time(10)))
    appointment = Appointment.objects.create(
        clinic=clinic,
        patient=patient,
        service=service,
        starts_at=starts_at,
        ends_at=starts_at + timedelta(minutes=30),
        status=Appointment.STATUS_CONFIRMED,
    )
    return clinic, service, user, patient, appointment, target_date


@pytest.mark.django_db
def test_viewer_cannot_update_appointment_status_or_payment(calendar_setup, client):
    clinic, _service, _user, _patient, appointment, _target_date = calendar_setup
    User = get_user_model()
    viewer = User.objects.create_user(username="appointment-viewer@example.com", email="appointment-viewer@example.com")
    ClinicMembership.objects.create(clinic=clinic, user=viewer, role="viewer")
    client.force_login(viewer)

    response = client.post(
        reverse("dashboard:update_appointment", args=[appointment.id]),
        {
            "status": Appointment.STATUS_COMPLETED,
            "payment_state": Appointment.PAYMENT_PAID_AT_CLINIC,
        },
        HTTP_HX_REQUEST="true",
    )

    assert response.status_code == 403
    appointment.refresh_from_db()
    assert appointment.status == Appointment.STATUS_CONFIRMED
    assert appointment.payment_state != Appointment.PAYMENT_PAID_AT_CLINIC


@pytest.mark.django_db
def test_viewer_cannot_add_appointment_note(calendar_setup, client):
    clinic, _service, _user, _patient, appointment, _target_date = calendar_setup
    User = get_user_model()
    viewer = User.objects.create_user(username="appointment-note-viewer@example.com", email="appointment-note-viewer@example.com")
    ClinicMembership.objects.create(clinic=clinic, user=viewer, role="viewer")
    client.force_login(viewer)

    response = client.post(
        reverse("dashboard:add_appointment_note", args=[appointment.id]),
        {"body": "Viewer should not write notes."},
        HTTP_HX_REQUEST="true",
    )

    assert response.status_code == 403
    assert not AppointmentNote.objects.filter(appointment=appointment).exists()


@pytest.mark.django_db
def test_viewer_appointment_detail_hides_daily_ops_forms(calendar_setup, client):
    clinic, _service, _user, _patient, appointment, _target_date = calendar_setup
    User = get_user_model()
    viewer = User.objects.create_user(username="appointment-detail-viewer@example.com", email="appointment-detail-viewer@example.com")
    ClinicMembership.objects.create(clinic=clinic, user=viewer, role="viewer")
    client.force_login(viewer)

    response = client.get(reverse("dashboard:appointment_detail", args=[appointment.id]))

    assert response.status_code == 200
    assert b"Appointment Details" in response.content
    assert reverse("dashboard:update_appointment", args=[appointment.id]).encode() not in response.content
    assert reverse("dashboard:add_appointment_note", args=[appointment.id]).encode() not in response.content
    assert reverse("dashboard:appointment_yakap_ledger", args=[appointment.id]).encode() not in response.content


@pytest.mark.django_db
def test_viewer_cannot_create_patient(clinic_setup, client):
    clinic, _service, _user = clinic_setup
    User = get_user_model()
    viewer = User.objects.create_user(username="patient-create-viewer@example.com", email="patient-create-viewer@example.com")
    ClinicMembership.objects.create(clinic=clinic, user=viewer, role="viewer")
    client.force_login(viewer)

    response = client.post(
        reverse("dashboard:create_patient"),
        {"full_name": "Viewer Created", "phone": "09170009999", "email": "viewer@example.com"},
    )

    assert response.status_code == 403
    assert not Patient.objects.filter(clinic=clinic, full_name="Viewer Created").exists()


@pytest.mark.django_db
def test_viewer_cannot_edit_patient(clinic_setup, client):
    clinic, _service, _user = clinic_setup
    patient = Patient.objects.create(clinic=clinic, full_name="Original Patient", phone="09170008888")
    User = get_user_model()
    viewer = User.objects.create_user(username="patient-edit-viewer@example.com", email="patient-edit-viewer@example.com")
    ClinicMembership.objects.create(clinic=clinic, user=viewer, role="viewer")
    client.force_login(viewer)

    response = client.post(
        reverse("dashboard:patient_edit", args=[patient.id]),
        {"full_name": "Edited By Viewer", "phone": "09170007777", "email": "viewer@example.com"},
    )

    assert response.status_code == 403
    patient.refresh_from_db()
    assert patient.full_name == "Original Patient"
    assert patient.phone == "09170008888"


@pytest.mark.django_db
def test_viewer_cannot_merge_patients(clinic_setup, client):
    clinic, service, _user = clinic_setup
    primary = Patient.objects.create(clinic=clinic, full_name="Primary Patient", phone="09170006666")
    duplicate = Patient.objects.create(clinic=clinic, full_name="Duplicate Patient", phone="09170005555")
    starts_at = timezone.now() + timedelta(days=1)
    appointment = Appointment.objects.create(
        clinic=clinic,
        patient=duplicate,
        service=service,
        starts_at=starts_at,
        ends_at=starts_at + timedelta(minutes=30),
    )
    User = get_user_model()
    viewer = User.objects.create_user(username="patient-merge-viewer@example.com", email="patient-merge-viewer@example.com")
    ClinicMembership.objects.create(clinic=clinic, user=viewer, role="viewer")
    client.force_login(viewer)

    response = client.post(
        reverse("dashboard:patient_merge"),
        {"primary_id": primary.id, "duplicate_id": duplicate.id},
    )

    assert response.status_code == 403
    assert Patient.objects.filter(pk=duplicate.pk).exists()
    appointment.refresh_from_db()
    assert appointment.patient == duplicate


@pytest.mark.django_db
def test_patient_merge_rejects_overlapping_appointment_without_partial_move(clinic_setup, client):
    clinic, service_a, user = clinic_setup
    service_b = Service.objects.create(clinic=clinic, name="Tooth Filling", duration_minutes=30)
    primary = Patient.objects.create(clinic=clinic, full_name="Primary Patient", phone="09170006666")
    duplicate = Patient.objects.create(clinic=clinic, full_name="Duplicate Patient", phone="09170005555")
    target_start = timezone.now() + timedelta(days=1)
    earlier_start = target_start - timedelta(hours=1)
    earlier_duplicate_appointment = Appointment.objects.create(
        clinic=clinic,
        patient=duplicate,
        service=service_b,
        starts_at=earlier_start,
        ends_at=earlier_start + timedelta(minutes=30),
        status=Appointment.STATUS_CONFIRMED,
    )
    primary_appointment = Appointment.objects.create(
        clinic=clinic,
        patient=primary,
        service=service_a,
        starts_at=target_start,
        ends_at=target_start + timedelta(minutes=30),
        status=Appointment.STATUS_CONFIRMED,
    )
    duplicate_appointment = Appointment.objects.create(
        clinic=clinic,
        patient=duplicate,
        service=service_b,
        starts_at=target_start,
        ends_at=target_start + timedelta(minutes=30),
        status=Appointment.STATUS_CONFIRMED,
    )
    client.force_login(user)
    client.raise_request_exception = False

    response = client.post(
        reverse("dashboard:patient_merge"),
        {"primary_id": primary.id, "duplicate_id": duplicate.id},
        HTTP_HX_REQUEST="true",
    )

    assert response.status_code != 500
    assert b"cf-error" in response.content
    assert b"active appointment" in response.content
    assert Patient.objects.filter(pk=duplicate.pk).exists()
    primary_appointment.refresh_from_db()
    duplicate_appointment.refresh_from_db()
    earlier_duplicate_appointment.refresh_from_db()
    assert primary_appointment.patient == primary
    assert duplicate_appointment.patient == duplicate
    assert earlier_duplicate_appointment.patient == duplicate


@pytest.mark.django_db
def test_search_patients(clinic_setup, client):
    clinic, service, user = clinic_setup
    client.force_login(user)
    Patient.objects.create(clinic=clinic, full_name="John Doe", phone="09170001111")
    response = client.get(reverse("dashboard:search") + "?q=john")
    assert response.status_code == 200
    assert b"John Doe" in response.content


@pytest.mark.django_db
def test_search_appointments(clinic_setup, client):
    clinic, service, user = clinic_setup
    client.force_login(user)
    patient = Patient.objects.create(clinic=clinic, full_name="Jane Doe", phone="09170002222")
    starts_at = timezone.now() + timezone.timedelta(days=1)
    Appointment.objects.create(clinic=clinic, patient=patient, service=service, starts_at=starts_at, ends_at=starts_at + timezone.timedelta(minutes=30))
    response = client.get(reverse("dashboard:search") + "?q=jane")
    assert response.status_code == 200
    assert b"Jane Doe" in response.content


@pytest.mark.django_db
def test_search_services_uses_effective_duration_without_price(clinic_setup, client):
    clinic, _service, user = clinic_setup
    clinic.default_appointment_duration = 45
    clinic.save(update_fields=["default_appointment_duration", "updated_at"])
    Service.objects.create(clinic=clinic, name="Default Duration Service", duration_minutes=None)
    client.force_login(user)

    response = client.get(reverse("dashboard:search") + "?q=default")

    assert response.status_code == 200
    assert b"Default Duration Service" in response.content
    assert b"45 min" in response.content
    assert b"None min" not in response.content
    assert b"\xe2\x82\xb1" not in response.content


@pytest.mark.django_db
def test_settings_page_does_not_show_blocked_times(clinic_setup, client):
    clinic, service, user = clinic_setup
    client.force_login(user)

    response = client.get(reverse("dashboard:settings"))

    assert response.status_code == 200
    assert b"Blocked Times" not in response.content
    assert b"Add Blocked Time" not in response.content
    assert b"Unavailable Dates" in response.content


@pytest.mark.django_db
def test_settings_business_hours_missing_rows_render_closed(clinic_setup, client):
    clinic, service, user = clinic_setup
    client.force_login(user)
    ClinicBusinessHour.objects.create(
        clinic=clinic,
        weekday=0,
        is_open=True,
        open_time=time(9),
        close_time=time(17),
    )

    response = client.get(reverse("dashboard:settings") + "?tab=hours")

    html = response.content.decode()
    saturday_checkbox = re.search(r'<input[^>]+name="is_open_5"[^>]*>', html).group(0)
    sunday_checkbox = re.search(r'<input[^>]+name="is_open_6"[^>]*>', html).group(0)
    assert "checked" not in saturday_checkbox
    assert "checked" not in sunday_checkbox


@pytest.mark.django_db
def test_settings_slot_preview_post_keeps_preview_tab_visible(clinic_setup, client):
    clinic, service, user = clinic_setup
    client.force_login(user)

    response = client.post(
        reverse("dashboard:settings"),
        {"service": service.id, "date": (timezone.localdate() + timedelta(days=1)).isoformat()},
    )

    assert response.status_code == 200
    assert 'x-data="{tab: \'preview\'}"' in response.content.decode()


@pytest.mark.django_db
def test_settings_slot_preview_lists_only_active_unarchived_services(clinic_setup, client):
    clinic, service, user = clinic_setup
    Service.objects.create(clinic=clinic, name="Inactive Service", duration_minutes=30, is_active=False)
    Service.objects.create(clinic=clinic, name="Archived Service", duration_minutes=30, is_archived=True)
    client.force_login(user)

    response = client.get(reverse("dashboard:settings") + "?tab=preview")
    content = response.content.decode()
    select = content[content.index('id="settings-slot-service"'):content.index("</select>", content.index('id="settings-slot-service"'))]

    assert service.name in select
    assert "Inactive Service" not in select
    assert "Archived Service" not in select


@pytest.mark.django_db
def test_settings_slot_preview_handles_invalid_service_and_date(clinic_setup, client):
    _clinic, _service, user = clinic_setup
    client.force_login(user)

    response = client.post(reverse("dashboard:settings"), {"service": "not-a-number", "date": "not-a-date"})

    assert response.status_code == 200


@pytest.mark.django_db
def test_slot_preview_handles_invalid_service_and_date(clinic_setup, client):
    _clinic, _service, user = clinic_setup
    client.force_login(user)

    response = client.post(reverse("dashboard:slot_preview"), {"service": "not-a-number", "date": "not-a-date"})

    assert response.status_code == 200


@pytest.mark.django_db
def test_profile_password_change_updates_password_and_keeps_session(clinic_setup, client):
    clinic, service, user = clinic_setup
    client.force_login(user)

    response = client.post(
        reverse("dashboard:profile"),
        {
            "old_password": "password123",
            "new_password1": "NewStrongPass!2026",
            "new_password2": "NewStrongPass!2026",
        },
        follow=True,
    )

    user.refresh_from_db()
    assert response.status_code == 200
    assert user.check_password("NewStrongPass!2026")
    assert b"Password updated successfully." in response.content
    assert client.get(reverse("dashboard:home")).status_code == 200


@pytest.mark.django_db
def test_profile_password_change_requires_current_password(clinic_setup, client):
    clinic, service, user = clinic_setup
    client.force_login(user)

    response = client.post(
        reverse("dashboard:profile"),
        {
            "old_password": "wrong-password",
            "new_password1": "NewStrongPass!2026",
            "new_password2": "NewStrongPass!2026",
        },
    )

    user.refresh_from_db()
    assert response.status_code == 200
    assert user.check_password("password123")
    assert not user.check_password("NewStrongPass!2026")
    assert "Your old password was entered incorrectly" in response.content.decode()


@pytest.mark.django_db
def test_profile_password_change_rejects_mismatched_new_passwords(clinic_setup, client):
    clinic, service, user = clinic_setup
    client.force_login(user)

    response = client.post(
        reverse("dashboard:profile"),
        {
            "old_password": "password123",
            "new_password1": "NewStrongPass!2026",
            "new_password2": "DifferentStrongPass!2026",
        },
    )

    content = response.content.decode()
    user.refresh_from_db()
    assert response.status_code == 200
    assert user.check_password("password123")
    assert "password fields" in content
    assert "match" in content


@pytest.mark.django_db
def test_patients_list_orders_latest_created_first(clinic_setup, client):
    clinic, service, user = clinic_setup
    client.force_login(user)
    older = Patient.objects.create(clinic=clinic, full_name="Amy Older", phone="09170003333")
    newer = Patient.objects.create(clinic=clinic, full_name="Zara Newer", phone="09170004444")

    response = client.get(reverse("dashboard:patients"))

    assert response.status_code == 200
    assert list(response.context["patients"]) == [newer, older]


@pytest.mark.django_db
def test_patients_page_paginates_ten_patients(clinic_setup, client):
    clinic, service, user = clinic_setup
    client.force_login(user)

    for index in range(11):
        Patient.objects.create(
            clinic=clinic,
            full_name=f"Paged Patient {index:02d}",
            phone=f"0917001{index:04d}",
        )

    response = client.get(reverse("dashboard:patients"))
    page_obj = response.context["page_obj"]

    assert response.status_code == 200
    assert page_obj.paginator.per_page == 10
    assert len(page_obj.object_list) == 10
    assert page_obj.paginator.num_pages == 2
    assert list(response.context["patients"]) == list(page_obj)


@pytest.mark.django_db
def test_patients_pagination_encodes_search_query(clinic_setup, client):
    clinic, service, user = clinic_setup
    client.force_login(user)

    for index in range(11):
        Patient.objects.create(
            clinic=clinic,
            full_name=f"Ana & Bob {index:02d}",
            phone=f"0917002{index:04d}",
        )

    response = client.get(reverse("dashboard:patients"), {"q": "Ana & Bob"})
    content = response.content.decode()

    assert response.status_code == 200
    assert "?page=2&q=Ana%20%26%20Bob" in content


@pytest.mark.django_db
def test_calendar_events_returns_events(calendar_setup, client):
    clinic, service, user, patient, appointment, target_date = calendar_setup
    client.force_login(user)
    response = client.get(reverse("dashboard:calendar_events"))
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["id"] == appointment.id


@pytest.mark.django_db
def test_calendar_events_title_shows_time_and_patient_only(calendar_setup, client):
    clinic, service, user, patient, appointment, target_date = calendar_setup
    client.force_login(user)

    response = client.get(reverse("dashboard:calendar_events"))

    assert response.status_code == 200
    data = response.json()
    assert data[0]["title"] == "10:00 am Test Patient"


@pytest.mark.django_db
def test_calendar_events_include_status_metadata_and_editable_flag(calendar_setup, client):
    clinic, service, user, patient, appointment, target_date = calendar_setup
    client.force_login(user)

    response = client.get(reverse("dashboard:calendar_events"))

    assert response.status_code == 200
    data = response.json()
    assert data[0]["extendedProps"]["status"] == appointment.status
    assert data[0]["editable"] is True


@pytest.mark.django_db
def test_calendar_events_mark_completed_and_cancelled_as_not_editable(calendar_setup, client):
    clinic, service, user, patient, appointment, target_date = calendar_setup
    client.force_login(user)

    for blocked_status in [Appointment.STATUS_COMPLETED, Appointment.STATUS_CANCELLED]:
        appointment.status = blocked_status
        appointment.save(update_fields=["status"])

        response = client.get(reverse("dashboard:calendar_events"))

        assert response.status_code == 200
        data = response.json()
        assert data[0]["extendedProps"]["status"] == blocked_status
        assert data[0]["editable"] is False


@pytest.mark.django_db
def test_calendar_events_use_neon_aqua_status_colors(calendar_setup, client):
    clinic, service, user, patient, appointment, target_date = calendar_setup
    pending_start = appointment.starts_at + timedelta(hours=1)
    no_show_start = appointment.starts_at + timedelta(hours=2)
    Appointment.objects.create(
        clinic=clinic,
        patient=patient,
        service=service,
        starts_at=pending_start,
        ends_at=pending_start + timedelta(minutes=30),
        status=Appointment.STATUS_PENDING,
    )
    Appointment.objects.create(
        clinic=clinic,
        patient=patient,
        service=service,
        starts_at=no_show_start,
        ends_at=no_show_start + timedelta(minutes=30),
        status=Appointment.STATUS_NO_SHOW,
    )
    client.force_login(user)

    response = client.get(reverse("dashboard:calendar_events"))

    assert response.status_code == 200
    data = response.json()

    def contrast_ratio(foreground, background):
        def luminance(hex_color):
            channels = [int(hex_color[i : i + 2], 16) / 255 for i in (1, 3, 5)]
            adjusted = [channel / 12.92 if channel <= 0.03928 else ((channel + 0.055) / 1.055) ** 2.4 for channel in channels]
            return 0.2126 * adjusted[0] + 0.7152 * adjusted[1] + 0.0722 * adjusted[2]

        lighter, darker = sorted([luminance(foreground), luminance(background)], reverse=True)
        return (lighter + 0.05) / (darker + 0.05)

    events_by_status = {event["className"].replace("status-", "", 1): event for event in data}
    expected_colors = {
        Appointment.STATUS_PENDING: {"backgroundColor": "#fff6e7", "borderColor": "#80531f", "textColor": "#80531f"},
        Appointment.STATUS_CONFIRMED: {"backgroundColor": "#ecfeff", "borderColor": "#06b6d4", "textColor": "#0e7490"},
        Appointment.STATUS_NO_SHOW: {"backgroundColor": "#edf2f7", "borderColor": "#4a5870", "textColor": "#4a5870"},
    }
    for status, expected in expected_colors.items():
        event = events_by_status[status]
        assert event["backgroundColor"] == expected["backgroundColor"]
        assert event["borderColor"] == expected["borderColor"]
        assert event["textColor"] == expected["textColor"]
        assert contrast_ratio(event["textColor"], event["backgroundColor"]) >= 4.5


@pytest.mark.django_db
def test_calendar_page_uses_event_title_time_only(calendar_setup, client):
    clinic, service, user, patient, appointment, target_date = calendar_setup
    client.force_login(user)

    response = client.get(reverse("dashboard:calendar"))

    assert response.status_code == 200
    assert b"displayEventTime: false" in response.content


@pytest.mark.django_db
def test_calendar_page_uses_clinic_timezone_and_posts_start_str(calendar_setup, client):
    clinic, _service, user, _patient, _appointment, _target_date = calendar_setup
    clinic.timezone = "America/Los_Angeles"
    clinic.save(update_fields=["timezone"])
    client.force_login(user)

    response = client.get(reverse("dashboard:calendar"))
    content = response.content.decode()

    assert response.status_code == 200
    assert "timeZone: 'America/Los_Angeles'" in content
    assert "formData.append('starts_at', info.event.startStr)" in content
    assert ".toISOString()" not in content


@pytest.mark.django_db
def test_calendar_events_emit_clinic_local_iso_datetimes(clinic_setup, client):
    clinic, service, user = clinic_setup
    clinic.timezone = "America/Los_Angeles"
    clinic.save(update_fields=["timezone"])
    clinic_tz = ZoneInfo(clinic.timezone)
    patient = Patient.objects.create(clinic=clinic, full_name="Late Patient", phone="09170001112")
    local_start = timezone.datetime(2026, 1, 10, 23, 30, tzinfo=clinic_tz)
    appointment = Appointment.objects.create(
        clinic=clinic,
        patient=patient,
        service=service,
        starts_at=local_start,
        ends_at=local_start + timedelta(minutes=30),
    )
    client.force_login(user)

    response = client.get(reverse("dashboard:calendar_events"))

    assert response.status_code == 200
    event = response.json()[0]
    assert event["id"] == appointment.id
    assert event["start"].startswith("2026-01-10T23:30:00")
    assert event["start"].endswith("-08:00")


@pytest.mark.django_db
def test_appointments_page_uses_html_safe_alpine_focus_selector(clinic_setup, client):
    clinic, service, user = clinic_setup
    client.force_login(user)

    response = client.get(reverse("dashboard:appointments"))
    content = response.content.decode()

    assert response.status_code == 200
    assert 'tabindex=\\"-1\\"' not in content
    assert "[tabindex]:not([tabindex='-1'])" in content


@pytest.mark.django_db
def test_appointments_page_uses_status_dropdown_instead_of_inline_status_links(clinic_setup, client):
    clinic, service, user = clinic_setup
    client.force_login(user)

    response = client.get(reverse("dashboard:appointments") + f"?status={Appointment.STATUS_CONFIRMED}")
    content = response.content.decode()

    assert response.status_code == 200
    assert '<label for="filter-status" class="cf-label">Status</label>' in content
    assert '<select id="filter-status" name="status"' in content
    assert '<option value="">All Statuses</option>' in content
    assert '<option value="confirmed" selected>Confirmed</option>' in content
    assert '<input type="hidden" name="status"' not in content
    assert ':href="statusHref(' not in content
    assert ">All Status</a>" not in content


@pytest.mark.django_db
def test_appointments_page_search_filters_by_appointment_fields(clinic_setup, client):
    clinic, service, user = clinic_setup
    client.force_login(user)
    target_date = timezone.localdate() + timedelta(days=1)
    base_start = timezone.make_aware(timezone.datetime.combine(target_date, time(9)))
    root_canal = Service.objects.create(clinic=clinic, name="Root Canal", duration_minutes=45)
    name_patient = Patient.objects.create(clinic=clinic, full_name="Mina Santos", phone="09170003333")
    phone_patient = Patient.objects.create(clinic=clinic, full_name="Phone Match", phone="09171234567")
    service_patient = Patient.objects.create(clinic=clinic, full_name="Service Match", phone="09170004444")
    reference_patient = Patient.objects.create(clinic=clinic, full_name="Reference Match", phone="09170005555")
    other_patient = Patient.objects.create(clinic=clinic, full_name="Unrelated Patient", phone="09170006666")
    name_match = Appointment.objects.create(
        clinic=clinic,
        patient=name_patient,
        service=service,
        starts_at=base_start,
        ends_at=base_start + timedelta(minutes=30),
    )
    phone_match = Appointment.objects.create(
        clinic=clinic,
        patient=phone_patient,
        service=service,
        starts_at=base_start + timedelta(hours=1),
        ends_at=base_start + timedelta(hours=1, minutes=30),
    )
    service_match = Appointment.objects.create(
        clinic=clinic,
        patient=service_patient,
        service=root_canal,
        starts_at=base_start + timedelta(hours=2),
        ends_at=base_start + timedelta(hours=2, minutes=45),
    )
    reference_match = Appointment.objects.create(
        clinic=clinic,
        patient=reference_patient,
        service=service,
        starts_at=base_start + timedelta(hours=3),
        ends_at=base_start + timedelta(hours=3, minutes=30),
        reference_code="CF-LOOKUP1",
    )
    Appointment.objects.create(
        clinic=clinic,
        patient=other_patient,
        service=service,
        starts_at=base_start + timedelta(hours=4),
        ends_at=base_start + timedelta(hours=4, minutes=30),
    )
    other_group = ClinicGroup.objects.create(name="Other Clinic Group", owner=user)
    other_clinic = Clinic.objects.create(group=other_group, name="Other Clinic", slug="other-clinic")
    other_service = Service.objects.create(clinic=other_clinic, name="Other Root Canal", duration_minutes=30)
    other_clinic_patient = Patient.objects.create(clinic=other_clinic, full_name="Mina Outside", phone="09170007777")
    Appointment.objects.create(
        clinic=other_clinic,
        patient=other_clinic_patient,
        service=other_service,
        starts_at=base_start,
        ends_at=base_start + timedelta(minutes=30),
    )

    for query, expected in [
        ("mina", name_match),
        ("1234567", phone_match),
        ("root", service_match),
        ("lookup1", reference_match),
    ]:
        response = client.get(reverse("dashboard:appointments"), {"q": query})

        assert response.status_code == 200
        assert response.context["search_query"] == query
        assert list(response.context["appointments"]) == [expected]


@pytest.mark.django_db
def test_appointments_page_paginates_ten_appointments(clinic_setup, client):
    clinic, service, user = clinic_setup
    patient = Patient.objects.create(clinic=clinic, full_name="Paged Patient", phone="09170005555")
    starts_at = timezone.now() + timedelta(days=1)
    for index in range(11):
        appointment_start = starts_at + timedelta(hours=index)
        Appointment.objects.create(
            clinic=clinic,
            patient=patient,
            service=service,
            starts_at=appointment_start,
            ends_at=appointment_start + timedelta(minutes=30),
        )
    client.force_login(user)

    response = client.get(reverse("dashboard:appointments"))
    page_obj = response.context["page_obj"]

    assert response.status_code == 200
    assert page_obj.paginator.per_page == 10
    assert len(page_obj.object_list) == 10
    assert page_obj.paginator.num_pages == 2


@pytest.mark.django_db
def test_appointments_pagination_encodes_search_query(clinic_setup, client):
    clinic, service, user = clinic_setup
    starts_at = timezone.now() + timedelta(days=1)
    for index in range(11):
        patient = Patient.objects.create(
            clinic=clinic,
            full_name=f"Alice &status=cancelled Patient {index:02d}",
            phone=f"0917010{index:04d}",
        )
        appointment_start = starts_at + timedelta(hours=index)
        Appointment.objects.create(
            clinic=clinic,
            patient=patient,
            service=service,
            starts_at=appointment_start,
            ends_at=appointment_start + timedelta(minutes=30),
        )
    client.force_login(user)

    response = client.get(reverse("dashboard:appointments"), {"q": "Alice &status=cancelled"})
    content = response.content.decode()

    assert response.status_code == 200
    assert "q=Alice%20%26status%3Dcancelled" in content
    assert "q=Alice &amp;status=cancelled" not in content


@pytest.mark.django_db
def test_appointments_page_rejects_invalid_service_filter(clinic_setup, client):
    clinic, _service, user = clinic_setup
    client.force_login(user)

    response = client.get(reverse("dashboard:appointments"), {"service": "not-a-number"})

    assert response.status_code == 400
    assert b"Invalid service filter." in response.content


@pytest.mark.django_db
def test_appointments_export_rejects_invalid_service_filter(clinic_setup, client):
    clinic, _service, user = clinic_setup
    client.force_login(user)

    response = client.get(reverse("dashboard:export_csv"), {"service": "not-a-number"})

    assert response.status_code == 400
    assert b"Invalid service filter." in response.content


@pytest.mark.django_db
def test_appointments_export_escapes_csv_formula_cells(clinic_setup, client):
    clinic, _service, user = clinic_setup
    patient = Patient.objects.create(clinic=clinic, full_name='=HYPERLINK("https://evil.test","x")', phone="@SUM(1,1)123")
    service = Service.objects.create(clinic=clinic, name="+Danger Service", duration_minutes=30)
    starts_at = timezone.now() + timedelta(days=1)
    Appointment.objects.create(
        clinic=clinic,
        patient=patient,
        service=service,
        starts_at=starts_at,
        ends_at=starts_at + timedelta(minutes=30),
    )
    client.force_login(user)

    response = client.get(reverse("dashboard:export_csv"))
    rows = list(csv.reader(io.StringIO(response.content.decode())))

    assert response.status_code == 200
    assert rows[1][1].startswith("'=")
    assert rows[1][2].startswith("'@")
    assert rows[1][3].startswith("'+")


@pytest.mark.django_db
def test_appointments_date_filter_uses_clinic_timezone(clinic_setup, client):
    clinic, service, user = clinic_setup
    clinic.timezone = "America/Los_Angeles"
    clinic.save(update_fields=["timezone"])
    clinic_tz = ZoneInfo(clinic.timezone)
    patient = Patient.objects.create(clinic=clinic, full_name="Boundary Patient", phone="09170002222")
    included = Appointment.objects.create(
        clinic=clinic,
        patient=patient,
        service=service,
        starts_at=timezone.datetime(2026, 1, 10, 23, 30, tzinfo=clinic_tz),
        ends_at=timezone.datetime(2026, 1, 11, 0, 0, tzinfo=clinic_tz),
    )
    Appointment.objects.create(
        clinic=clinic,
        patient=patient,
        service=service,
        starts_at=timezone.datetime(2026, 1, 11, 0, 30, tzinfo=clinic_tz),
        ends_at=timezone.datetime(2026, 1, 11, 1, 0, tzinfo=clinic_tz),
    )
    client.force_login(user)

    response = client.get(reverse("dashboard:appointments"), {"date_from": "2026-01-10", "date_to": "2026-01-10"})

    assert response.status_code == 200
    assert list(response.context["appointments"]) == [included]


@pytest.mark.django_db
def test_export_date_filter_and_csv_times_use_clinic_timezone(clinic_setup, client):
    clinic, service, user = clinic_setup
    clinic.timezone = "America/Los_Angeles"
    clinic.save(update_fields=["timezone"])
    clinic_tz = ZoneInfo(clinic.timezone)
    patient = Patient.objects.create(clinic=clinic, full_name="CSV Patient", phone="09170003333")
    included = Appointment.objects.create(
        clinic=clinic,
        patient=patient,
        service=service,
        starts_at=timezone.datetime(2026, 1, 10, 23, 30, tzinfo=clinic_tz),
        ends_at=timezone.datetime(2026, 1, 11, 0, 0, tzinfo=clinic_tz),
    )
    Appointment.objects.create(
        clinic=clinic,
        patient=patient,
        service=service,
        starts_at=timezone.datetime(2026, 1, 11, 0, 30, tzinfo=clinic_tz),
        ends_at=timezone.datetime(2026, 1, 11, 1, 0, tzinfo=clinic_tz),
    )
    client.force_login(user)

    response = client.get(reverse("dashboard:export_csv"), {"date_from": "2026-01-10", "date_to": "2026-01-10"})
    rows = list(csv.reader(io.StringIO(response.content.decode())))

    assert response.status_code == 200
    assert len(rows) == 2
    assert rows[1][0] == str(included.id)
    assert rows[1][4] == "2026-01-10"
    assert rows[1][5] == "23:30"


@pytest.mark.django_db
def test_viewer_cannot_export_appointments_csv(clinic_setup, client):
    clinic, _service, _user = clinic_setup
    User = get_user_model()
    viewer = User.objects.create_user(username="appointment-export-viewer@example.com", email="appointment-export-viewer@example.com")
    ClinicMembership.objects.create(clinic=clinic, user=viewer, role="viewer")
    client.force_login(viewer)

    response = client.get(reverse("dashboard:export_csv"))

    assert response.status_code == 403


@pytest.mark.django_db
def test_calendar_page_uses_html_safe_alpine_focus_selector(calendar_setup, client):
    clinic, service, user, patient, appointment, target_date = calendar_setup
    client.force_login(user)

    response = client.get(reverse("dashboard:calendar"))
    content = response.content.decode()

    assert response.status_code == 200
    assert 'tabindex=\\"-1\\"' not in content
    assert "[tabindex]:not([tabindex='-1'])" in content


@pytest.mark.django_db
def test_calendar_events_filters_by_service(calendar_setup, client):
    clinic, service, user, patient, appointment, target_date = calendar_setup
    other_service = Service.objects.create(clinic=clinic, name="Other Service", duration_minutes=30)
    other_start = appointment.starts_at + timedelta(hours=1)
    Appointment.objects.create(clinic=clinic, patient=patient, service=other_service, starts_at=other_start, ends_at=other_start + timedelta(minutes=30))
    client.force_login(user)
    response = client.get(reverse("dashboard:calendar_events") + f"?service={service.id}")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["id"] == appointment.id


@pytest.mark.django_db
def test_calendar_events_rejects_invalid_service_filter(calendar_setup, client):
    clinic, service, user, patient, appointment, target_date = calendar_setup
    client.force_login(user)

    response = client.get(reverse("dashboard:calendar_events") + "?service=not-a-number")

    assert response.status_code == 400
    assert response.json()["error"] == "Invalid service filter."


@pytest.mark.django_db
def test_calendar_events_rejects_out_of_range_service_filter(calendar_setup, client):
    clinic, service, user, patient, appointment, target_date = calendar_setup
    client.force_login(user)

    response = client.get(reverse("dashboard:calendar_events") + "?service=999999999999999999999999999999")

    assert response.status_code == 400
    assert response.json()["error"] == "Invalid service filter."


@pytest.mark.django_db
def test_calendar_events_filters_by_status(calendar_setup, client):
    clinic, service, user, patient, appointment, target_date = calendar_setup
    other_start = appointment.starts_at + timedelta(hours=1)
    Appointment.objects.create(
        clinic=clinic,
        patient=patient,
        service=service,
        starts_at=other_start,
        ends_at=other_start + timedelta(minutes=30),
        status=Appointment.STATUS_PENDING,
    )
    client.force_login(user)

    response = client.get(reverse("dashboard:calendar_events") + f"?status={Appointment.STATUS_CONFIRMED}")

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["id"] == appointment.id


@pytest.mark.django_db
def test_calendar_events_detail_url_marks_calendar_source(calendar_setup, client):
    clinic, service, user, patient, appointment, target_date = calendar_setup
    client.force_login(user)

    response = client.get(reverse("dashboard:calendar_events"))

    assert response.status_code == 200
    data = response.json()
    assert "source=calendar" in data[0]["url"]


@pytest.mark.django_db
def test_calendar_cancel_triggers_refetch_without_table_row_target(calendar_setup, client):
    clinic, service, user, patient, appointment, target_date = calendar_setup
    client.force_login(user)

    response = client.post(
        reverse("dashboard:appointment_cancel", args=[appointment.id]),
        {"modal_source": "calendar"},
        HTTP_HX_REQUEST="true",
    )

    assert response.status_code == 200
    trigger = response.headers["HX-Trigger"]
    assert "calendar-refetch" in trigger
    assert "close-calendar-modal" in trigger
    assert "HX-Retarget" not in response.headers


@pytest.mark.django_db
def test_htmx_cancel_refreshes_filtered_appointments_list(calendar_setup, client):
    clinic, _service, user, patient, appointment, _target_date = calendar_setup
    client.force_login(user)
    current_url = reverse("dashboard:appointments") + f"?status={Appointment.STATUS_CONFIRMED}"

    response = client.post(
        reverse("dashboard:appointment_cancel", args=[appointment.id]),
        HTTP_HX_REQUEST="true",
        HTTP_HX_CURRENT_URL=current_url,
    )

    appointment.refresh_from_db()
    assert appointment.status == Appointment.STATUS_CANCELLED
    assert response.headers["HX-Retarget"] == "#appointments-table"
    assert b"No appointments found" in response.content
    assert patient.full_name.encode() not in response.content


@pytest.mark.django_db
def test_patient_history_cancel_refreshes_patient_detail(calendar_setup, client):
    _clinic, _service, user, _patient, appointment, _target_date = calendar_setup
    client.force_login(user)

    response = client.post(
        reverse("dashboard:appointment_cancel", args=[appointment.id]),
        {"modal_source": "patient"},
        HTTP_HX_REQUEST="true",
    )

    assert response.headers["HX-Retarget"] == "#patient-detail-content"
    assert b"Contact Details" in response.content
    assert b"Cancelled" in response.content


@pytest.mark.django_db
def test_yakap_cancel_does_not_target_missing_appointment_row(calendar_setup, client):
    _clinic, _service, user, _patient, appointment, _target_date = calendar_setup
    client.force_login(user)

    response = client.post(
        reverse("dashboard:appointment_cancel", args=[appointment.id]),
        {"modal_source": "yakap"},
        HTTP_HX_REQUEST="true",
    )

    assert response.headers.get("HX-Refresh") == "true"
    assert "HX-Retarget" not in response.headers


@pytest.mark.django_db
def test_calendar_edit_triggers_refetch_without_table_row_target(calendar_setup, client):
    clinic, service, user, patient, appointment, target_date = calendar_setup
    client.force_login(user)

    response = client.post(
        reverse("dashboard:appointment_edit", args=[appointment.id]),
        {
            "patient_name": patient.full_name,
            "patient_phone": patient.phone,
            "patient_email": patient.email,
            "service": service.id,
            "date": target_date.isoformat(),
            "time": "10:00",
            "status": Appointment.STATUS_CONFIRMED,
            "payment_state": Appointment.PAYMENT_UNPAID,
            "source": Appointment.SOURCE_STAFF,
            "reason": "",
            "modal_source": "calendar",
        },
        HTTP_HX_REQUEST="true",
    )

    assert response.status_code == 200
    trigger = response.headers["HX-Trigger"]
    assert "calendar-refetch" in trigger
    assert "HX-Retarget" not in response.headers
    assert b"Appointment Details" in response.content


@pytest.mark.django_db
def test_appointment_edit_rejects_invalid_status_transition(calendar_setup, client):
    clinic, service, user, patient, appointment, target_date = calendar_setup
    appointment.status = Appointment.STATUS_COMPLETED
    appointment.save(update_fields=["status"])
    client.force_login(user)

    response = client.post(
        reverse("dashboard:appointment_edit", args=[appointment.id]),
        {
            "patient_name": patient.full_name,
            "patient_phone": patient.phone,
            "patient_email": patient.email,
            "service": service.id,
            "date": target_date.isoformat(),
            "time": "10:00",
            "status": Appointment.STATUS_PENDING,
            "payment_state": Appointment.PAYMENT_UNPAID,
            "source": Appointment.SOURCE_STAFF,
            "reason": "",
        },
        HTTP_HX_REQUEST="true",
    )

    assert response.status_code == 200
    assert b"Cannot change status" in response.content
    appointment.refresh_from_db()
    assert appointment.status == Appointment.STATUS_COMPLETED


@pytest.mark.django_db
def test_calendar_reschedule_valid(calendar_setup, client):
    clinic, service, user, patient, appointment, target_date = calendar_setup
    client.force_login(user)
    new_start = appointment.starts_at + timedelta(hours=1)
    response = client.post(reverse("dashboard:calendar_reschedule"), {"appointment_id": appointment.id, "starts_at": new_start.isoformat()})
    assert response.status_code == 200
    assert response.json()["success"] is True
    appointment.refresh_from_db()
    assert appointment.starts_at == new_start


@pytest.mark.django_db
def test_calendar_reschedule_rejects_missing_start_time(calendar_setup, client):
    clinic, service, user, patient, appointment, target_date = calendar_setup
    client.force_login(user)
    client.raise_request_exception = False

    response = client.post(reverse("dashboard:calendar_reschedule"), {"appointment_id": appointment.id})

    assert response.status_code in {200, 400}
    payload = response.json()
    assert payload["success"] is False
    assert "invalid date/time" in payload["error"].lower() or "required" in payload["error"].lower()


@pytest.mark.django_db
def test_htmx_reschedule_refreshes_filtered_appointments_list(calendar_setup, client):
    clinic, _service, user, patient, appointment, target_date = calendar_setup
    new_date = target_date + timedelta(days=1)
    ClinicBusinessHour.objects.create(
        clinic=clinic,
        weekday=new_date.weekday(),
        is_open=True,
        open_time=time(9),
        close_time=time(17),
    )
    client.force_login(user)
    current_url = reverse("dashboard:appointments") + f"?date_from={target_date.isoformat()}&date_to={target_date.isoformat()}"

    response = client.post(
        reverse("dashboard:appointment_reschedule", args=[appointment.id]),
        {"new_date": new_date.isoformat(), "new_time": "10:00"},
        HTTP_HX_REQUEST="true",
        HTTP_HX_CURRENT_URL=current_url,
    )

    appointment.refresh_from_db()
    assert appointment.starts_at.date() == new_date
    assert response.headers["HX-Retarget"] == "#appointments-table"
    assert b"No appointments found" in response.content
    assert patient.full_name.encode() not in response.content


@pytest.mark.django_db
def test_manual_appointment_reschedule_rejects_past_start(calendar_setup, client):
    clinic, _service, user, _patient, appointment, _target_date = calendar_setup
    original_start = appointment.starts_at
    clinic_tz = ZoneInfo(clinic.timezone)
    past_date = timezone.now().astimezone(clinic_tz).date() - timedelta(days=1)
    ClinicBusinessHour.objects.update_or_create(
        clinic=clinic,
        weekday=past_date.weekday(),
        defaults={"is_open": True, "open_time": time(9), "close_time": time(17)},
    )
    client.force_login(user)

    response = client.post(
        reverse("dashboard:appointment_reschedule", args=[appointment.id]),
        {"new_date": past_date.isoformat(), "new_time": "10:00"},
        HTTP_HX_REQUEST="true",
    )

    assert response.status_code == 200
    assert b"future" in response.content.lower()
    appointment.refresh_from_db()
    assert appointment.starts_at == original_start


@pytest.mark.django_db
def test_appointment_reschedule_rejects_same_patient_overlap(calendar_setup, client):
    clinic, _service, user, patient, appointment, target_date = calendar_setup
    other_service = Service.objects.create(clinic=clinic, name="Tooth Filling", duration_minutes=30)
    target_start = timezone.make_aware(timezone.datetime.combine(target_date, time(11)))
    Appointment.objects.bulk_create([
        Appointment(
            clinic=clinic,
            patient=patient,
            service=other_service,
            starts_at=target_start,
            ends_at=target_start + timedelta(minutes=30),
            status=Appointment.STATUS_CONFIRMED,
            reference_code="CF-PATOVER1",
        )
    ])
    client.force_login(user)
    client.raise_request_exception = False

    response = client.post(
        reverse("dashboard:appointment_reschedule", args=[appointment.id]),
        {"new_date": target_date.isoformat(), "new_time": "11:00"},
        HTTP_HX_REQUEST="true",
    )

    assert response.status_code == 200
    assert b"This patient already has an active appointment at that time." in response.content


@pytest.mark.django_db
def test_calendar_reschedule_outside_hours(calendar_setup, client):
    clinic, service, user, patient, appointment, target_date = calendar_setup
    client.force_login(user)
    new_start = timezone.make_aware(timezone.datetime.combine(target_date, time(18)))
    response = client.post(reverse("dashboard:calendar_reschedule"), {"appointment_id": appointment.id, "starts_at": new_start.isoformat()})
    assert response.json()["success"] is False
    assert "outside working hours" in response.json()["error"].lower()


@pytest.mark.django_db
def test_calendar_reschedule_overlaps_break(calendar_setup, client):
    clinic, service, user, patient, appointment, target_date = calendar_setup
    client.force_login(user)
    new_start = timezone.make_aware(timezone.datetime.combine(target_date, time(12, 15)))
    response = client.post(reverse("dashboard:calendar_reschedule"), {"appointment_id": appointment.id, "starts_at": new_start.isoformat()})
    assert response.json()["success"] is False
    assert "break" in response.json()["error"].lower()


@pytest.mark.django_db
def test_calendar_reschedule_double_booking(calendar_setup, client):
    clinic, service, user, patient, appointment, target_date = calendar_setup
    other_patient = Patient.objects.create(clinic=clinic, full_name="Other Patient", phone="09170002222")
    other_start = appointment.starts_at + timedelta(hours=4)
    Appointment.objects.create(clinic=clinic, patient=other_patient, service=service, starts_at=other_start, ends_at=other_start + timedelta(minutes=30))
    client.force_login(user)
    response = client.post(reverse("dashboard:calendar_reschedule"), {"appointment_id": appointment.id, "starts_at": other_start.isoformat()})
    assert response.json()["success"] is False
    assert "fully booked" in response.json()["error"].lower()


@pytest.mark.django_db
def test_calendar_reschedule_allows_overlap_with_different_service(calendar_setup, client):
    clinic, service, user, patient, appointment, target_date = calendar_setup
    other_service = Service.objects.create(clinic=clinic, name="Tooth Filling", duration_minutes=30)
    other_patient = Patient.objects.create(clinic=clinic, full_name="Other Patient", phone="09170002222")
    other_start = appointment.starts_at + timedelta(hours=4)
    Appointment.objects.create(
        clinic=clinic,
        patient=other_patient,
        service=other_service,
        starts_at=other_start,
        ends_at=other_start + timedelta(minutes=30),
    )
    client.force_login(user)

    response = client.post(
        reverse("dashboard:calendar_reschedule"),
        {"appointment_id": appointment.id, "starts_at": other_start.isoformat()},
    )

    assert response.json()["success"] is True
    appointment.refresh_from_db()
    assert appointment.starts_at == other_start


@pytest.mark.django_db
def test_calendar_reschedule_cross_clinic_isolation(calendar_setup, client):
    clinic, service, user, patient, appointment, target_date = calendar_setup
    other_user = get_user_model().objects.create_user(username="other@example.com", email="other@example.com", password="password123")
    other_group = ClinicGroup.objects.create(name="Other Clinic", owner=other_user)
    other_clinic = Clinic.objects.create(group=other_group, name="Other Clinic", slug="other-clinic")
    ClinicMembership.objects.create(clinic=other_clinic, user=other_user, role=ClinicMembership.ROLE_OWNER)
    client.force_login(other_user)
    response = client.post(reverse("dashboard:calendar_reschedule"), {"appointment_id": appointment.id, "starts_at": (appointment.starts_at + timedelta(hours=1)).isoformat()})
    assert response.status_code == 404


@pytest.mark.django_db
def test_appointment_detail_returns_partial(calendar_setup, client):
    clinic, service, user, patient, appointment, target_date = calendar_setup
    client.force_login(user)
    response = client.get(reverse("dashboard:appointment_detail", args=[appointment.id]))
    assert response.status_code == 200
    assert b"Appointment Details" in response.content
    assert b"Test Patient" in response.content


@pytest.mark.django_db
def test_appointment_detail_rejects_unsafe_mode(calendar_setup, client):
    clinic, service, user, patient, appointment, target_date = calendar_setup
    client.force_login(user)

    response = client.get(reverse("dashboard:appointment_detail", args=[appointment.id]) + "?mode='};alert(1);//")

    assert response.status_code == 200
    assert b"alert(1)" not in response.content
    assert b"mode: 'detail'" in response.content


@pytest.mark.django_db
def test_delete_appointment_requires_post(calendar_setup, client):
    clinic, service, user, patient, appointment, target_date = calendar_setup
    client.force_login(user)

    response = client.get(reverse("dashboard:delete_appointment", args=[appointment.id]))

    assert response.status_code == 405
    assert Appointment.objects.filter(pk=appointment.pk).exists()


@pytest.mark.django_db
def test_delete_appointment_removes_appointment_and_notes(calendar_setup, client):
    clinic, service, user, patient, appointment, target_date = calendar_setup
    note = AppointmentNote.objects.create(appointment=appointment, author=user, body="Mistaken booking")
    client.force_login(user)

    response = client.post(reverse("dashboard:delete_appointment", args=[appointment.id]))

    assert response.status_code == 302
    assert not Appointment.objects.filter(pk=appointment.pk).exists()
    assert not AppointmentNote.objects.filter(pk=note.pk).exists()


@pytest.mark.django_db
def test_htmx_delete_appointment_refreshes_appointments_table(calendar_setup, client):
    clinic, service, user, patient, appointment, target_date = calendar_setup
    client.force_login(user)

    response = client.post(
        reverse("dashboard:delete_appointment", args=[appointment.id]),
        HTTP_HX_REQUEST="true",
    )

    assert response.status_code == 200
    assert not Appointment.objects.filter(pk=appointment.pk).exists()
    assert b"Appointments" in response.content
    assert "appointmentDeleted" in response.headers["HX-Trigger"]
    assert "Appointment deleted." in response.headers["HX-Trigger"]


@pytest.mark.django_db
def test_htmx_delete_appointment_ignores_malformed_current_filter_url(calendar_setup, client):
    clinic, service, user, patient, appointment, target_date = calendar_setup
    client.force_login(user)
    client.raise_request_exception = False

    response = client.post(
        reverse("dashboard:delete_appointment", args=[appointment.id]),
        HTTP_HX_REQUEST="true",
        HTTP_HX_CURRENT_URL="https://testserver/appointments/?service=not-a-number",
    )

    assert response.status_code == 200
    assert not Appointment.objects.filter(pk=appointment.pk).exists()
    assert b"Appointments" in response.content
    assert "appointmentDeleted" in response.headers["HX-Trigger"]


@pytest.mark.django_db
def test_calendar_delete_appointment_triggers_refetch_and_close(calendar_setup, client):
    clinic, service, user, patient, appointment, target_date = calendar_setup
    client.force_login(user)

    response = client.post(
        reverse("dashboard:delete_appointment", args=[appointment.id]),
        {"modal_source": "calendar"},
        HTTP_HX_REQUEST="true",
    )

    assert response.status_code == 200
    assert not Appointment.objects.filter(pk=appointment.pk).exists()
    trigger = response.headers["HX-Trigger"]
    assert "calendar-refetch" in trigger
    assert "close-calendar-modal" in trigger
    assert "Appointment deleted." in trigger
    assert "HX-Retarget" not in response.headers


@pytest.mark.django_db
def test_patient_history_delete_appointment_refreshes_patient_detail(calendar_setup, client):
    clinic, service, user, patient, appointment, target_date = calendar_setup
    client.force_login(user)

    response = client.post(
        reverse("dashboard:delete_appointment", args=[appointment.id]),
        {"modal_source": "patient"},
        HTTP_HX_REQUEST="true",
    )

    assert response.status_code == 200
    assert not Appointment.objects.filter(pk=appointment.pk).exists()
    assert b"Contact Details" in response.content
    assert b"No visits yet" in response.content
    assert "appointmentDeleted" in response.headers["HX-Trigger"]


@pytest.mark.django_db
def test_delete_appointment_cross_clinic_isolation(calendar_setup, client):
    clinic, service, user, patient, appointment, target_date = calendar_setup
    other_user = get_user_model().objects.create_user(username="delete-other@example.com", email="delete-other@example.com", password="password123")
    other_group = ClinicGroup.objects.create(name="Other Delete Clinic", owner=other_user)
    other_clinic = Clinic.objects.create(group=other_group, name="Other Delete Clinic", slug="other-delete-clinic")
    ClinicMembership.objects.create(clinic=other_clinic, user=other_user, role=ClinicMembership.ROLE_OWNER)
    client.force_login(other_user)

    response = client.post(reverse("dashboard:delete_appointment", args=[appointment.id]))

    assert response.status_code == 404
    assert Appointment.objects.filter(pk=appointment.pk).exists()


@pytest.mark.django_db
def test_htmx_status_update_shows_errors_without_success_toast(calendar_setup, client):
    clinic, service, user, patient, appointment, target_date = calendar_setup
    appointment.status = Appointment.STATUS_COMPLETED
    appointment.save(update_fields=["status"])
    client.force_login(user)

    response = client.post(
        reverse("dashboard:update_appointment", args=[appointment.id]),
        {"status": Appointment.STATUS_PENDING, "payment_state": Appointment.PAYMENT_UNPAID},
        HTTP_HX_REQUEST="true",
    )

    assert response.status_code == 200
    assert b"Cannot change status" in response.content
    assert "Appointment updated." not in response.headers.get("HX-Trigger", "")


@pytest.mark.django_db
def test_update_appointment_reactivating_cancelled_checks_capacity(clinic_setup, client):
    clinic, service, user = clinic_setup
    target_start = timezone.now() + timedelta(days=1)
    cancelled_patient = Patient.objects.create(clinic=clinic, full_name="Cancelled Patient", phone="09170006666")
    active_patient = Patient.objects.create(clinic=clinic, full_name="Active Patient", phone="09170005555")
    cancelled_appointment = Appointment.objects.create(
        clinic=clinic,
        patient=cancelled_patient,
        service=service,
        starts_at=target_start,
        ends_at=target_start + timedelta(minutes=30),
        status=Appointment.STATUS_CANCELLED,
    )
    Appointment.objects.create(
        clinic=clinic,
        patient=active_patient,
        service=service,
        starts_at=target_start,
        ends_at=target_start + timedelta(minutes=30),
        status=Appointment.STATUS_CONFIRMED,
    )
    client.force_login(user)

    response = client.post(
        reverse("dashboard:update_appointment", args=[cancelled_appointment.id]),
        {"status": Appointment.STATUS_PENDING, "payment_state": Appointment.PAYMENT_UNPAID},
        HTTP_HX_REQUEST="true",
    )

    assert response.status_code == 200
    cancelled_appointment.refresh_from_db()
    assert cancelled_appointment.status == Appointment.STATUS_CANCELLED


@pytest.mark.django_db
def test_htmx_invalid_note_submission_keeps_errors_without_success_toast(calendar_setup, client):
    clinic, service, user, patient, appointment, target_date = calendar_setup
    client.force_login(user)

    response = client.post(
        reverse("dashboard:add_appointment_note", args=[appointment.id]),
        {"body": "", "modal_source": ""},
        HTTP_HX_REQUEST="true",
    )

    assert response.status_code == 200
    assert appointment.notes.count() == 0
    assert b"This field is required" in response.content
    assert "Note added." not in response.headers.get("HX-Trigger", "")


def _htmx_request_with_message_storage():
    request = RequestFactory().get("/hx/", HTTP_HX_REQUEST="true")
    request.session = {}
    request._messages = FallbackStorage(request)
    return request


def test_htmx_messages_middleware_preserves_message_types_and_all_messages():
    def get_response(request):
        messages.warning(request, "Slots almost full.")
        messages.info(request, "Schedule refreshed.")
        return HttpResponse("")

    response = HtmxMessagesMiddleware(get_response)(_htmx_request_with_message_storage())

    payload = json.loads(response.headers["HX-Trigger"])
    assert payload["toast-message"] == [
        {"message": "Slots almost full.", "type": "warning"},
        {"message": "Schedule refreshed.", "type": "info"},
    ]


@pytest.mark.django_db
def test_calendar_reschedule_unavailable_date(calendar_setup, client):
    clinic, service, user, patient, appointment, target_date = calendar_setup
    UnavailableDate.objects.create(clinic=clinic, date=target_date, reason="Holiday")
    client.force_login(user)
    response = client.post(reverse("dashboard:calendar_reschedule"), {"appointment_id": appointment.id, "starts_at": (appointment.starts_at + timedelta(hours=1)).isoformat()})
    assert response.json()["success"] is False
    assert "not available" in response.json()["error"].lower()


@pytest.mark.django_db
def test_calendar_reschedule_accepts_utc_iso_string(calendar_setup, client):
    clinic, service, user, patient, appointment, target_date = calendar_setup
    client.force_login(user)
    new_start = timezone.make_aware(timezone.datetime.combine(target_date, time(11)))
    utc_start = new_start.astimezone(dt_timezone.utc)
    response = client.post(reverse("dashboard:calendar_reschedule"), {"appointment_id": appointment.id, "starts_at": utc_start.isoformat().replace("+00:00", "Z")})
    assert response.json()["success"] is True
    appointment.refresh_from_db()
    local_start = appointment.starts_at.astimezone(ZoneInfo(clinic.timezone))
    assert local_start.hour == 11


@pytest.mark.django_db
def test_assistant_settings_page_shows_shared_ai_prompt_form(clinic_setup, client):
    from clinics.models import ClinicAISettings
    from messenger.defaults import DEFAULT_AI_FALLBACK_MESSAGE, DEFAULT_MESSENGER_AI_PROMPT

    clinic, service, user = clinic_setup
    ClinicAISettings.objects.create(
        clinic=clinic,
        is_ai_enabled=False,
        communication_tone=ClinicAISettings.TONE_WARM,
        custom_tone_instructions="Use calm wording and avoid slang.",
        instructions="Use a warm clinic tone.",
        fallback_message="Please call the clinic.",
    )
    client.force_login(user)

    response = client.get(reverse("dashboard:assistant_settings"))

    assert response.status_code == 200
    assert b">Assistant</h1>" in response.content
    assert b"Patient Assistant" not in response.content
    assert b"Shared Assistant Settings" in response.content
    assert b"Used by both the website Assistant and Facebook Messenger" in response.content
    assert b"Prompt / Instructions" in response.content
    assert b"Communication Tone" in response.content
    assert b"md:grid-cols-[minmax(0,.45fr)_minmax(0,.55fr)] items-start" in response.content
    assert b'name="communication_tone"' in response.content
    assert b'value="professional"' in response.content
    assert b'value="warm"' in response.content
    assert b'value="empathetic"' in response.content
    assert b'value="concise"' in response.content
    assert b'value="friendly"' in response.content
    assert b'name="custom_tone_instructions"' in response.content
    assert b'class="cf-textarea cf-textarea-compact"' in response.content
    assert b"Tone affects wording only" in response.content
    assert b'name="is_ai_enabled"' in response.content
    assert b'name="instructions"' in response.content
    assert b'name="fallback_message"' in response.content
    assert b"Restore default prompt" in response.content
    assert b"Restore default fallback" in response.content
    assert DEFAULT_MESSENGER_AI_PROMPT.splitlines()[0].encode() in response.content
    assert DEFAULT_AI_FALLBACK_MESSAGE.encode() in response.content
    assert b"Use a warm clinic tone." in response.content
    assert b"Use calm wording and avoid slang." in response.content
    assert b"Please call the clinic." in response.content
    assert b"Website Booking Widget" not in response.content
    assert b'name="widget_accent_color"' not in response.content
    assert b'name="widget_welcome_message"' not in response.content
    assert b"Recommended JavaScript launcher" not in response.content
    assert b"Advanced iframe fallback" not in response.content
    assert b"widget_behavior_instructions" not in response.content


@pytest.mark.django_db
def test_assistant_settings_page_creates_default_shared_ai_settings(clinic_setup, client):
    from clinics.models import ClinicAISettings
    from messenger.defaults import DEFAULT_AI_FALLBACK_MESSAGE, DEFAULT_MESSENGER_AI_PROMPT

    clinic, service, user = clinic_setup
    client.force_login(user)

    response = client.get(reverse("dashboard:assistant_settings"))

    assert response.status_code == 200
    assert b"Shared Assistant Settings" in response.content
    assert DEFAULT_MESSENGER_AI_PROMPT.splitlines()[0].encode() in response.content
    assert DEFAULT_AI_FALLBACK_MESSAGE.encode() in response.content
    settings = ClinicAISettings.objects.get(clinic=clinic)
    assert settings.fallback_message == DEFAULT_AI_FALLBACK_MESSAGE


@pytest.mark.django_db
def test_shared_ai_settings_form_exposes_messenger_response_mode(clinic_setup):
    from clinics.forms import SharedAISettingsForm
    from clinics.models import ClinicAISettings

    clinic, service, owner = clinic_setup
    settings = ClinicAISettings.objects.create(clinic=clinic)

    form = SharedAISettingsForm(instance=settings)

    assert "messenger_response_mode" in form.fields
    assert dict(form.fields["messenger_response_mode"].choices) == {
        ClinicAISettings.MESSENGER_MODE_QUICK_REPLIES: "Quick replies",
        ClinicAISettings.MESSENGER_MODE_AI: "AI mode",
    }

    invalid = SharedAISettingsForm(
        data={
            "is_ai_enabled": "on",
            "messenger_response_mode": "invalid-mode",
            "communication_tone": ClinicAISettings.TONE_PROFESSIONAL,
            "custom_tone_instructions": "",
            "instructions": "Use a friendly clinic tone.",
            "fallback_message": "Please call us.",
        },
        instance=settings,
    )
    assert not invalid.is_valid()
    assert "messenger_response_mode" in invalid.errors


@pytest.mark.django_db
def test_shared_ai_settings_form_exposes_communication_tone_fields_and_validates_choice(clinic_setup):
    from clinics.forms import SharedAISettingsForm
    from clinics.models import ClinicAISettings

    clinic, service, owner = clinic_setup
    settings = ClinicAISettings.objects.create(clinic=clinic)

    form = SharedAISettingsForm(instance=settings)

    assert "communication_tone" in form.fields
    assert "custom_tone_instructions" in form.fields
    assert form.fields["custom_tone_instructions"].widget.attrs["class"] == "cf-textarea cf-textarea-compact"
    assert dict(form.fields["communication_tone"].choices) == {
        ClinicAISettings.TONE_PROFESSIONAL: "Professional",
        ClinicAISettings.TONE_WARM: "Warm",
        ClinicAISettings.TONE_EMPATHETIC: "Empathetic",
        ClinicAISettings.TONE_CONCISE: "Concise",
        ClinicAISettings.TONE_FRIENDLY: "Friendly",
    }

    invalid = SharedAISettingsForm(
        data={
            "is_ai_enabled": "on",
            "messenger_response_mode": ClinicAISettings.MESSENGER_MODE_AI,
            "communication_tone": "unsafe-tone",
            "custom_tone_instructions": "Use calm wording.",
            "instructions": "Use a friendly clinic tone.",
            "fallback_message": "Please call us.",
        },
        instance=settings,
    )
    assert not invalid.is_valid()
    assert "communication_tone" in invalid.errors

    too_long = SharedAISettingsForm(
        data={
            "is_ai_enabled": "on",
            "messenger_response_mode": ClinicAISettings.MESSENGER_MODE_AI,
            "communication_tone": ClinicAISettings.TONE_FRIENDLY,
            "custom_tone_instructions": "x" * 501,
            "instructions": "Use a friendly clinic tone.",
            "fallback_message": "Please call us.",
        },
        instance=settings,
    )
    assert not too_long.is_valid()
    assert "custom_tone_instructions" in too_long.errors


@pytest.mark.django_db
def test_assistant_settings_page_shows_messenger_response_mode_control(clinic_setup, client):
    from clinics.models import ClinicAISettings

    clinic, service, user = clinic_setup
    ClinicAISettings.objects.create(clinic=clinic)
    client.force_login(user)

    response = client.get(reverse("dashboard:assistant_settings"))

    assert response.status_code == 200
    assert b"Messenger Response Mode" in response.content
    assert b'name="messenger_response_mode"' in response.content
    assert b'value="quick_replies"' in response.content
    assert b'value="ai"' in response.content
    assert b"Use guided buttons for Messenger booking. No AI tokens are consumed." in response.content
    assert b"Use AI for Messenger conversations and booking. No quick-reply buttons are shown." in response.content
    assert b"This affects Facebook Messenger only. Messenger AI mode is independent from the website Assistant switch." in response.content
    assert b"AI mode only takes over when AI replies are enabled" not in response.content
    assert b"You can choose a Messenger mode now. It will apply after Facebook Messenger is connected." in response.content


@pytest.mark.django_db
def test_voice_agent_nav_link_and_page_render_for_owner(clinic_setup, client):
    from voice.models import VoiceAgentSettings

    clinic, service, user = clinic_setup
    VoiceAgentSettings.objects.create(clinic=clinic, is_enabled=False, display_name="Clinic Voice")
    client.force_login(user)

    response = client.get(reverse("dashboard:voice_agent"))
    content = response.content.decode()

    assert response.status_code == 200
    assert ">Voice Agent</h1>" in content
    assert "Configure and test the website voice assistant" in content
    assert "Test Live" in content
    assert "Conversation Transcript" in content
    assert "Ready to test" in content
    assert 'name="display_name"' in content
    assert 'name="is_enabled"' in content
    assert reverse("dashboard:assistant_settings") in content
    assert reverse("dashboard:voice_agent") in content


@pytest.mark.django_db
def test_voice_agent_settings_save_is_clinic_scoped(clinic_setup, client):
    from voice.models import VoiceAgentSettings

    clinic, service, user = clinic_setup
    client.force_login(user)

    response = client.post(
        reverse("dashboard:voice_agent"),
        {
            "is_enabled": "on",
            "display_name": "Welcome Voice",
            "voice_label": VoiceAgentSettings.VOICE_WARM,
            "welcome_message": "Hello, I can help you book.",
            "provider": VoiceAgentSettings.PROVIDER_BROWSER,
            "is_test_mode_enabled": "on",
        },
    )

    assert response.status_code == 302
    settings = VoiceAgentSettings.objects.get(clinic=clinic)
    assert settings.is_enabled is True
    assert settings.display_name == "Welcome Voice"
    assert settings.voice_label == VoiceAgentSettings.VOICE_WARM
    assert settings.welcome_message == "Hello, I can help you book."
    assert settings.provider == VoiceAgentSettings.PROVIDER_BROWSER


@pytest.mark.django_db
def test_staff_cannot_manage_voice_agent_settings(clinic_setup, client):
    from django.contrib.auth import get_user_model
    from clinics.models import ClinicMembership

    clinic, service, owner = clinic_setup
    User = get_user_model()
    staff = User.objects.create_user(username="voice-staff@example.com", email="voice-staff@example.com", password="password123")
    ClinicMembership.objects.create(clinic=clinic, user=staff, role=ClinicMembership.ROLE_STAFF)
    client.force_login(staff)

    response = client.get(reverse("dashboard:voice_agent"))

    assert response.status_code == 403


@pytest.mark.django_db
def test_booking_widget_page_shows_full_configuration(clinic_setup, client):
    clinic, service, user = clinic_setup
    clinic.widget_accent_color = "#0891b2"
    clinic.widget_welcome_message = "Book online in a few steps."
    clinic.save(update_fields=["widget_accent_color", "widget_welcome_message"])
    client.force_login(user)

    response = client.get(reverse("dashboard:widget_embed"))
    content = response.content.decode()

    assert response.status_code == 200
    assert ">Booking Widget</h1>" in content
    assert "Customize your website booking widget appearance, preview, public link, and embed code." in content
    assert 'name="widget_accent_color"' in content
    assert 'name="widget_welcome_message"' in content
    assert "Book online in a few steps." in content
    assert "previewOpen: false" in content
    assert "@click=\"previewOpen = true\"" in content
    assert "window.addEventListener('message'" in content
    assert "kliniassist-minimize" in content
    assert "x-show=\"previewOpen\" x-transition x-cloak" in content
    assert "Click the launcher to preview how patients open the widget." in content
    assert "aria-label=\"Open booking widget preview\"" in content
    assert "Book an appointment" in content
    assert "Share Your Widget" in content
    assert reverse("widget:home", args=[clinic.slug]) in content
    assert "Recommended JavaScript launcher" in content
    assert "Adds a small bottom-right booking button" in content
    assert "full widget opens after click" in content
    assert "&lt;script src=" in content
    assert "Advanced iframe fallback" in content
    assert "Embeds the full panel directly" in content
    assert "visible immediately" in content
    assert "&lt;iframe src=" in content
    assert 'allow="microphone; clipboard-write"' in content


@pytest.mark.django_db
def test_messenger_settings_links_to_assistant_without_ai_prompt_form(clinic_setup, client):
    from clinics.models import ClinicAISettings
    from messenger.defaults import DEFAULT_MESSENGER_AI_PROMPT
    from messenger.models import MessengerConnection

    clinic, service, user = clinic_setup
    MessengerConnection.objects.create(
        clinic=clinic,
        page_id="PAGE-DASH-AI-LINK",
        page_access_token="TOKEN-DASH-AI-LINK",
    )
    ClinicAISettings.objects.create(
        clinic=clinic,
        instructions="This prompt should not render on Messenger settings.",
        fallback_message="This fallback should not render on Messenger settings.",
    )
    client.force_login(user)

    response = client.get(reverse("dashboard:messenger_settings"))

    assert response.status_code == 200
    assert b"Shared Assistant" in response.content
    assert b"Open Assistant" in response.content
    assert b"Patient Assistant" not in response.content
    assert reverse("dashboard:assistant_settings").encode() in response.content
    assert b"Shared AI Prompt" not in response.content
    assert b'name="instructions"' not in response.content
    assert b'name="fallback_message"' not in response.content
    assert b"This prompt should not render" not in response.content
    assert b"This fallback should not render" not in response.content
    assert DEFAULT_MESSENGER_AI_PROMPT.splitlines()[0].encode() not in response.content


@pytest.mark.django_db
@patch("messenger.messenger_api.requests.get")
def test_owner_can_save_messenger_connection_app_credentials(mock_get, clinic_setup, client):
    from messenger.models import MessengerConnection

    clinic, service, user = clinic_setup
    mock_get.return_value.json.return_value = {"id": "PAGE-DASH-CREDS", "name": "Demo Clinic Facebook"}
    mock_get.return_value.raise_for_status.return_value = None
    client.force_login(user)

    response = client.post(
        reverse("dashboard:messenger_settings"),
        {
            "_form": "connection_settings",
            "app_id": "1234567890",
            "app_secret": "APP-SECRET-DASH",
            "page_id": "PAGE-DASH-CREDS",
            "page_access_token": "PAGE-TOKEN-DASH",
        },
    )

    assert response.status_code == 302
    connection = MessengerConnection.objects.get(clinic=clinic)
    assert connection.app_id == "1234567890"
    assert connection.app_secret == "APP-SECRET-DASH"
    assert connection.page_id == "PAGE-DASH-CREDS"
    assert connection.page_access_token == "PAGE-TOKEN-DASH"


@pytest.mark.django_db
@patch("messenger.messenger_api.requests.get")
def test_owner_save_messenger_connection_fetches_and_displays_page_name(mock_get, clinic_setup, client):
    from messenger.models import MessengerConnection

    clinic, service, user = clinic_setup
    mock_get.return_value.json.return_value = {"id": "PAGE-DASH-CREDS", "name": "Demo Clinic Facebook"}
    mock_get.return_value.raise_for_status.return_value = None
    client.force_login(user)

    response = client.post(
        reverse("dashboard:messenger_settings"),
        {
            "_form": "connection_settings",
            "app_id": "1234567890",
            "app_secret": "APP-SECRET-DASH",
            "page_id": "PAGE-DASH-CREDS",
            "page_access_token": "PAGE-TOKEN-DASH",
        },
    )

    assert response.status_code == 302
    connection = MessengerConnection.objects.get(clinic=clinic)
    assert connection.page_name == "Demo Clinic Facebook"
    mock_get.assert_called_once_with(
        "https://graph.facebook.com/v18.0/me",
        params={"fields": "id,name"},
        headers={"Authorization": "Bearer PAGE-TOKEN-DASH"},
        timeout=10,
        allow_redirects=False,
    )

    page = client.get(reverse("dashboard:messenger_settings"))
    assert b"Demo Clinic Facebook" in page.content
    assert b"App ID" in page.content
    assert b"Page ID" in page.content


@pytest.mark.django_db
@patch("messenger.messenger_api.requests.get")
def test_messenger_connection_rejects_page_id_mismatch_from_meta(mock_get, clinic_setup, client):
    from messenger.models import MessengerConnection

    clinic, service, user = clinic_setup
    mock_get.return_value.json.return_value = {"id": "PAGE-FROM-META", "name": "Wrong Facebook Page"}
    mock_get.return_value.raise_for_status.return_value = None
    client.force_login(user)

    response = client.post(
        reverse("dashboard:messenger_settings"),
        {
            "_form": "connection_settings",
            "app_id": "1234567890",
            "app_secret": "APP-SECRET-DASH",
            "page_id": "PAGE-SUBMITTED",
            "page_access_token": "PAGE-TOKEN-DASH",
        },
    )

    assert response.status_code == 200
    assert b"does not match the Page Access Token" in response.content
    assert not MessengerConnection.objects.filter(clinic=clinic).exists()


@pytest.mark.django_db
@patch("messenger.messenger_api.requests.get")
def test_messenger_connection_saves_with_warning_when_page_name_fetch_fails(mock_get, clinic_setup, client):
    from messenger.models import MessengerConnection

    clinic, service, user = clinic_setup
    mock_get.side_effect = RequestException("Meta unavailable")
    client.force_login(user)

    response = client.post(
        reverse("dashboard:messenger_settings"),
        {
            "_form": "connection_settings",
            "app_id": "1234567890",
            "app_secret": "APP-SECRET-DASH",
            "page_id": "PAGE-DASH-CREDS",
            "page_access_token": "PAGE-TOKEN-DASH",
        },
        follow=True,
    )

    assert response.status_code == 200
    connection = MessengerConnection.objects.get(clinic=clinic)
    assert connection.page_name == ""
    rendered_messages = [message.message for message in get_messages(response.wsgi_request)]
    assert "Messenger settings saved, but the Facebook Page name could not be refreshed." in rendered_messages


@pytest.mark.django_db
def test_messenger_settings_page_masks_saved_secrets_with_reveal_controls(clinic_setup, client):
    from messenger.models import MessengerConnection

    clinic, service, user = clinic_setup
    MessengerConnection.objects.create(
        clinic=clinic,
        app_id="1234567890",
        app_secret="APP-SECRET-HIDDEN",
        page_id="PAGE-DASH-HIDDEN",
        page_access_token="PAGE-TOKEN-HIDDEN",
    )
    client.force_login(user)

    response = client.get(reverse("dashboard:messenger_settings"))

    assert response.status_code == 200
    assert b'name="app_id"' in response.content
    assert b'name="app_secret"' in response.content
    assert b'name="page_access_token"' in response.content
    assert b"APP-SECRET-HIDDEN" not in response.content
    assert b"PAGE-TOKEN-HIDDEN" not in response.content
    assert response.content.count(b'value="************"') == 2
    assert b'data-secret-field="app_secret"' in response.content
    assert b'data-secret-field="page_access_token"' in response.content


@pytest.mark.django_db
def test_messenger_settings_active_connection_shows_page_block_without_setup_helper(clinic_setup, client):
    from messenger.models import MessengerConnection

    clinic, service, user = clinic_setup
    MessengerConnection.objects.create(
        clinic=clinic,
        app_id="1234567890",
        page_id="PAGE-DASH-CONNECTED",
        page_name="GrowKit",
        page_access_token="PAGE-TOKEN-CONNECTED",
    )
    client.force_login(user)

    response = client.get(reverse("dashboard:messenger_settings"))

    assert response.status_code == 200
    content = response.content.decode()
    page_block_start = content.index('class="cf-messenger-page-strip"')
    page_block_end = content.index('<form id="messenger-connection-form"')
    page_block = content[page_block_start:page_block_end]
    summary_start = page_block.index("cf-messenger-page-summary")
    details_start = page_block.index("cf-messenger-page-details")

    assert "GrowKit" in page_block
    assert "Facebook Page:" in page_block
    assert "App ID:" in page_block
    assert "1234567890" in page_block
    assert "Page ID:" in page_block
    assert "PAGE-DASH-CONNECTED" in page_block
    assert "cf-messenger-page-icon" not in page_block
    assert summary_start < details_start
    assert b"Enter your Facebook Page details for the n8n workflow." not in response.content


@pytest.mark.django_db
@override_settings(STORAGES={
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
})
def test_messenger_settings_shows_django_meta_callback_and_n8n_worker_url(clinic_setup, client, settings):
    clinic, service, user = clinic_setup
    settings.META_MESSENGER_N8N_WEBHOOK_URL = "https://157-90-164-203.nip.io/webhook/kliniassist-messenger"
    client.force_login(user)

    response = client.get(reverse("dashboard:messenger_settings"), secure=True)

    assert response.status_code == 200
    content = response.content.decode()
    meta_label_index = content.index("Meta Callback URL")
    n8n_label_index = content.index("n8n Worker Webhook URL")

    assert "https://testserver/messenger/webhook/" in content[meta_label_index:n8n_label_index]
    assert "https://157-90-164-203.nip.io/webhook/kliniassist-messenger" in content[n8n_label_index:]


@pytest.mark.django_db
def test_owner_can_reveal_saved_messenger_secret(clinic_setup, client):
    from messenger.models import MessengerConnection

    clinic, service, user = clinic_setup
    MessengerConnection.objects.create(
        clinic=clinic,
        app_id="1234567890",
        app_secret="APP-SECRET-REVEAL",
        page_id="PAGE-DASH-REVEAL",
        page_access_token="PAGE-TOKEN-REVEAL",
    )
    client.force_login(user)

    response = client.post(reverse("dashboard:messenger_secret_reveal"), {"field": "app_secret"})
    token_response = client.post(reverse("dashboard:messenger_secret_reveal"), {"field": "page_access_token"})

    assert response.status_code == 200
    assert response.json() == {"value": "APP-SECRET-REVEAL"}
    assert token_response.status_code == 200
    assert token_response.json() == {"value": "PAGE-TOKEN-REVEAL"}


@pytest.mark.django_db
@patch("messenger.messenger_api.requests.get")
def test_messenger_settings_mask_submission_keeps_saved_secrets(mock_get, clinic_setup, client):
    from messenger.models import MessengerConnection

    clinic, service, user = clinic_setup
    mock_get.return_value.json.return_value = {"id": "PAGE-DASH-UNCHANGED", "name": "Demo Clinic Facebook"}
    mock_get.return_value.raise_for_status.return_value = None
    connection = MessengerConnection.objects.create(
        clinic=clinic,
        app_id="1234567890",
        app_secret="APP-SECRET-UNCHANGED",
        page_id="PAGE-DASH-UNCHANGED",
        page_access_token="PAGE-TOKEN-UNCHANGED",
    )
    client.force_login(user)

    response = client.post(
        reverse("dashboard:messenger_settings"),
        {
            "_form": "connection_settings",
            "app_id": "1234567890",
            "app_secret": "************",
            "page_id": "PAGE-DASH-UNCHANGED",
            "page_access_token": "************",
        },
    )

    assert response.status_code == 302
    connection.refresh_from_db()
    assert connection.app_secret == "APP-SECRET-UNCHANGED"
    assert connection.page_access_token == "PAGE-TOKEN-UNCHANGED"


@pytest.mark.django_db
def test_messenger_settings_rejects_incomplete_active_connection(clinic_setup, client):
    from messenger.models import MessengerConnection

    clinic, service, user = clinic_setup
    client.force_login(user)

    response = client.post(
        reverse("dashboard:messenger_settings"),
        {
            "_form": "connection_settings",
            "app_id": "1234567890",
            "app_secret": "APP-SECRET",
            "page_id": "",
            "page_access_token": "",
        },
    )

    assert response.status_code == 200
    assert b"Facebook Page ID is required" in response.content
    assert b"Page Access Token is required" in response.content
    assert not MessengerConnection.objects.filter(clinic=clinic, is_active=True).exists()


@pytest.mark.django_db
def test_messenger_settings_treats_incomplete_active_connection_as_not_configured(clinic_setup, client):
    from messenger.models import MessengerConnection

    clinic, service, user = clinic_setup
    MessengerConnection.objects.create(
        clinic=clinic,
        app_id="1234567890",
        page_id="PAGE-DASH-INCOMPLETE",
        page_access_token="",
        is_active=True,
    )
    client.force_login(user)

    response = client.get(reverse("dashboard:messenger_settings"))

    assert response.status_code == 200
    content = response.content.decode()
    assert "Not Configured" in content
    assert "Connected" not in content
    assert "Enter your Facebook Page details for the n8n workflow." in content


@pytest.mark.django_db
def test_staff_cannot_reveal_saved_messenger_secret(clinic_setup, client):
    from messenger.models import MessengerConnection

    User = get_user_model()
    clinic, service, owner = clinic_setup
    staff = User.objects.create_user(username="staff-secret@example.com", email="staff-secret@example.com", password="password123")
    ClinicMembership.objects.create(clinic=clinic, user=staff, role=ClinicMembership.ROLE_STAFF)
    MessengerConnection.objects.create(
        clinic=clinic,
        app_id="1234567890",
        app_secret="APP-SECRET-BLOCKED",
        page_id="PAGE-DASH-BLOCKED",
        page_access_token="PAGE-TOKEN-BLOCKED",
    )
    client.force_login(staff)

    response = client.post(reverse("dashboard:messenger_secret_reveal"), {"field": "app_secret"})

    assert response.status_code == 403


@pytest.mark.django_db
def test_owner_can_save_assistant_ai_settings(clinic_setup, client):
    from clinics.models import ClinicAISettings

    clinic, service, user = clinic_setup
    client.force_login(user)

    response = client.post(
        reverse("dashboard:assistant_settings"),
        {
            "_form": "ai_settings",
            "messenger_response_mode": ClinicAISettings.MESSENGER_MODE_QUICK_REPLIES,
            "communication_tone": ClinicAISettings.TONE_WARM,
            "custom_tone_instructions": "Keep replies reassuring and plain.",
            "instructions": "Answer briefly and ask for confirmation before booking.",
            "fallback_message": "A staff member will help you soon.",
        },
    )

    assert response.status_code == 302
    assert response.url == reverse("dashboard:assistant_settings")
    settings = ClinicAISettings.objects.get(clinic=clinic)
    assert settings.is_ai_enabled is False
    assert settings.messenger_response_mode == ClinicAISettings.MESSENGER_MODE_QUICK_REPLIES
    assert settings.communication_tone == ClinicAISettings.TONE_WARM
    assert settings.custom_tone_instructions == "Keep replies reassuring and plain."
    assert settings.instructions == "Answer briefly and ask for confirmation before booking."
    assert settings.fallback_message == "A staff member will help you soon."


@pytest.mark.django_db
def test_owner_can_save_booking_widget_settings_from_widget_page(clinic_setup, client):
    clinic, service, user = clinic_setup
    client.force_login(user)

    response = client.post(
        reverse("dashboard:widget_embed"),
        {
            "widget_accent_color": "#0e7490",
            "widget_welcome_message": "Choose a service and time online.",
        },
    )

    assert response.status_code == 302
    assert response.url == reverse("dashboard:widget_embed")
    clinic.refresh_from_db()
    assert clinic.widget_accent_color == "#0e7490"
    assert clinic.widget_welcome_message == "Choose a service and time online."


@pytest.mark.django_db
def test_staff_cannot_save_booking_widget_settings(clinic_setup, client):
    User = get_user_model()
    clinic, service, owner = clinic_setup
    clinic.widget_accent_color = "#06b6d4"
    clinic.widget_welcome_message = "Original widget welcome."
    clinic.save(update_fields=["widget_accent_color", "widget_welcome_message"])
    staff = User.objects.create_user(username="widget-staff@example.com", email="widget-staff@example.com", password="password123")
    ClinicMembership.objects.create(clinic=clinic, user=staff, role=ClinicMembership.ROLE_STAFF)
    client.force_login(staff)

    response = client.post(
        reverse("dashboard:widget_embed"),
        {
            "widget_accent_color": "#0e7490",
            "widget_welcome_message": "Staff should not save this.",
        },
    )

    assert response.status_code == 403
    clinic.refresh_from_db()
    assert clinic.widget_accent_color == "#06b6d4"
    assert clinic.widget_welcome_message == "Original widget welcome."


@pytest.mark.django_db
def test_booking_widget_settings_save_is_scoped_to_current_clinic(client):
    User = get_user_model()
    owner_a = User.objects.create_user(username="widget-owner-a@example.com", email="widget-owner-a@example.com", password="password123")
    group_a = ClinicGroup.objects.create(name="Widget A Group", owner=owner_a)
    clinic_a = Clinic.objects.create(
        group=group_a,
        name="Widget A",
        slug="widget-a",
        widget_accent_color="#06b6d4",
        widget_welcome_message="Clinic A original.",
    )
    ClinicMembership.objects.create(clinic=clinic_a, user=owner_a, role=ClinicMembership.ROLE_OWNER)

    owner_b = User.objects.create_user(username="widget-owner-b@example.com", email="widget-owner-b@example.com", password="password123")
    group_b = ClinicGroup.objects.create(name="Widget B Group", owner=owner_b)
    clinic_b = Clinic.objects.create(
        group=group_b,
        name="Widget B",
        slug="widget-b",
        widget_accent_color="#0891b2",
        widget_welcome_message="Clinic B original.",
    )
    ClinicMembership.objects.create(clinic=clinic_b, user=owner_b, role=ClinicMembership.ROLE_OWNER)
    client.force_login(owner_b)

    response = client.post(
        reverse("dashboard:widget_embed"),
        {
            "widget_accent_color": "#0e7490",
            "widget_welcome_message": "Clinic B updated widget.",
        },
    )

    assert response.status_code == 302
    clinic_a.refresh_from_db()
    clinic_b.refresh_from_db()
    assert clinic_a.widget_accent_color == "#06b6d4"
    assert clinic_a.widget_welcome_message == "Clinic A original."
    assert clinic_b.widget_accent_color == "#0e7490"
    assert clinic_b.widget_welcome_message == "Clinic B updated widget."


@pytest.mark.django_db
def test_owner_can_enable_assistant_ai_settings(clinic_setup, client):
    from clinics.models import ClinicAISettings

    clinic, service, user = clinic_setup
    client.force_login(user)

    response = client.post(
        reverse("dashboard:assistant_settings"),
        {
            "_form": "ai_settings",
            "is_ai_enabled": "on",
            "messenger_response_mode": ClinicAISettings.MESSENGER_MODE_AI,
            "communication_tone": ClinicAISettings.TONE_PROFESSIONAL,
            "custom_tone_instructions": "",
            "instructions": "Use a friendly clinic tone.",
            "fallback_message": "Please call us.",
        },
    )

    assert response.status_code == 302
    settings = ClinicAISettings.objects.get(clinic=clinic)
    assert settings.is_ai_enabled is True
    assert settings.messenger_response_mode == ClinicAISettings.MESSENGER_MODE_AI
    assert settings.instructions == "Use a friendly clinic tone."
    assert settings.fallback_message == "Please call us."


@pytest.mark.django_db
def test_owner_can_save_messenger_ai_mode_independent_from_website_assistant(clinic_setup, client):
    from clinics.models import ClinicAISettings

    clinic, service, user = clinic_setup
    client.force_login(user)

    response = client.post(
        reverse("dashboard:assistant_settings"),
        {
            "_form": "ai_settings",
            "messenger_response_mode": ClinicAISettings.MESSENGER_MODE_AI,
            "communication_tone": ClinicAISettings.TONE_PROFESSIONAL,
            "custom_tone_instructions": "",
            "instructions": "Use a friendly clinic tone.",
            "fallback_message": "Please call us.",
        },
    )

    assert response.status_code == 302
    settings = ClinicAISettings.objects.get(clinic=clinic)
    assert settings.is_ai_enabled is False
    assert settings.messenger_response_mode == ClinicAISettings.MESSENGER_MODE_AI
    assert settings.instructions == "Use a friendly clinic tone."
    assert settings.fallback_message == "Please call us."


@pytest.mark.django_db
def test_staff_cannot_save_assistant_ai_settings(clinic_setup, client):
    from clinics.models import ClinicAISettings

    User = get_user_model()
    clinic, service, owner = clinic_setup
    staff = User.objects.create_user(username="staff@example.com", email="staff@example.com", password="password123")
    ClinicMembership.objects.create(clinic=clinic, user=staff, role=ClinicMembership.ROLE_STAFF)
    settings = ClinicAISettings.objects.create(
        clinic=clinic,
        is_ai_enabled=False,
        messenger_response_mode=ClinicAISettings.MESSENGER_MODE_QUICK_REPLIES,
        communication_tone=ClinicAISettings.TONE_CONCISE,
        custom_tone_instructions="Existing tone notes.",
        instructions="Existing owner instructions.",
        fallback_message="Existing fallback.",
    )
    client.force_login(staff)

    response = client.post(
        reverse("dashboard:assistant_settings"),
        {
            "_form": "ai_settings",
            "is_ai_enabled": "on",
            "messenger_response_mode": ClinicAISettings.MESSENGER_MODE_AI,
            "communication_tone": ClinicAISettings.TONE_PROFESSIONAL,
            "custom_tone_instructions": "",
            "instructions": "Staff should not save this.",
            "fallback_message": "Blocked.",
        },
    )

    assert response.status_code == 403
    settings.refresh_from_db()
    assert settings.is_ai_enabled is False
    assert settings.messenger_response_mode == ClinicAISettings.MESSENGER_MODE_QUICK_REPLIES
    assert settings.communication_tone == ClinicAISettings.TONE_CONCISE
    assert settings.custom_tone_instructions == "Existing tone notes."
    assert settings.instructions == "Existing owner instructions."
    assert settings.fallback_message == "Existing fallback."


@pytest.mark.django_db
def test_owner_can_save_assistant_ai_settings_is_scoped_to_current_clinic(client):
    from clinics.models import ClinicAISettings

    User = get_user_model()
    owner_a = User.objects.create_user(username="owner-a@example.com", email="owner-a@example.com", password="password123")
    group_a = ClinicGroup.objects.create(name="Clinic A Group", owner=owner_a)
    clinic_a = Clinic.objects.create(group=group_a, name="Clinic A", slug="clinic-a")
    ClinicMembership.objects.create(clinic=clinic_a, user=owner_a, role=ClinicMembership.ROLE_OWNER)
    settings_a = ClinicAISettings.objects.create(
        clinic=clinic_a,
        is_ai_enabled=False,
        messenger_response_mode=ClinicAISettings.MESSENGER_MODE_QUICK_REPLIES,
        communication_tone=ClinicAISettings.TONE_CONCISE,
        custom_tone_instructions="Clinic A original tone.",
        instructions="Clinic A original instructions.",
        fallback_message="Clinic A original fallback.",
    )

    owner_b = User.objects.create_user(username="owner-b@example.com", email="owner-b@example.com", password="password123")
    group_b = ClinicGroup.objects.create(name="Clinic B Group", owner=owner_b)
    clinic_b = Clinic.objects.create(group=group_b, name="Clinic B", slug="clinic-b")
    ClinicMembership.objects.create(clinic=clinic_b, user=owner_b, role=ClinicMembership.ROLE_OWNER)
    settings_b = ClinicAISettings.objects.create(
        clinic=clinic_b,
        is_ai_enabled=False,
        messenger_response_mode=ClinicAISettings.MESSENGER_MODE_QUICK_REPLIES,
        communication_tone=ClinicAISettings.TONE_PROFESSIONAL,
        custom_tone_instructions="Clinic B original tone.",
        instructions="Clinic B original instructions.",
        fallback_message="Clinic B original fallback.",
    )
    client.force_login(owner_b)

    response = client.post(
        reverse("dashboard:assistant_settings"),
        {
            "_form": "ai_settings",
            "is_ai_enabled": "on",
            "messenger_response_mode": ClinicAISettings.MESSENGER_MODE_AI,
            "communication_tone": ClinicAISettings.TONE_EMPATHETIC,
            "custom_tone_instructions": "Clinic B updated tone.",
            "instructions": "Clinic B updated instructions.",
            "fallback_message": "Clinic B updated fallback.",
        },
    )

    assert response.status_code == 302
    settings_a.refresh_from_db()
    settings_b.refresh_from_db()
    assert settings_a.is_ai_enabled is False
    assert settings_a.messenger_response_mode == ClinicAISettings.MESSENGER_MODE_QUICK_REPLIES
    assert settings_a.communication_tone == ClinicAISettings.TONE_CONCISE
    assert settings_a.custom_tone_instructions == "Clinic A original tone."
    assert settings_a.instructions == "Clinic A original instructions."
    assert settings_a.fallback_message == "Clinic A original fallback."
    assert settings_b.is_ai_enabled is True
    assert settings_b.messenger_response_mode == ClinicAISettings.MESSENGER_MODE_AI
    assert settings_b.communication_tone == ClinicAISettings.TONE_EMPATHETIC
    assert settings_b.custom_tone_instructions == "Clinic B updated tone."
    assert settings_b.instructions == "Clinic B updated instructions."
    assert settings_b.fallback_message == "Clinic B updated fallback."


@pytest.mark.django_db
def test_owner_can_save_assistant_ai_settings_without_messenger_connection(clinic_setup, client):
    from clinics.models import ClinicAISettings

    clinic, service, user = clinic_setup
    client.force_login(user)

    response = client.post(
        reverse("dashboard:assistant_settings"),
        {
            "_form": "ai_settings",
            "is_ai_enabled": "on",
            "messenger_response_mode": ClinicAISettings.MESSENGER_MODE_AI,
            "communication_tone": ClinicAISettings.TONE_PROFESSIONAL,
            "custom_tone_instructions": "",
            "instructions": "Shared website and Messenger instructions.",
            "fallback_message": "Shared fallback.",
        },
    )

    assert response.status_code == 302
    settings = ClinicAISettings.objects.get(clinic=clinic)
    assert settings.is_ai_enabled is True
    assert settings.messenger_response_mode == ClinicAISettings.MESSENGER_MODE_AI
    assert settings.instructions == "Shared website and Messenger instructions."
    assert settings.fallback_message == "Shared fallback."


@pytest.mark.django_db
def test_assistant_settings_page_shows_ai_provider_form_without_secret(clinic_setup, client):
    from clinics.models import ClinicAIProviderSettings

    clinic, service, owner = clinic_setup
    ClinicAIProviderSettings.objects.create(
        clinic=clinic,
        provider=ClinicAIProviderSettings.PROVIDER_OPENAI,
        model="gpt-4o",
        fallback_model="gpt-4o-mini",
        api_key="sk-dashboard-secret",
    )
    client.force_login(owner)

    response = client.get(reverse("dashboard:assistant_settings"))
    content = response.content.decode()

    assert response.status_code == 200
    assert 'data-section="ai-provider-settings"' in content
    assert "AI Provider" in content
    assert "Clinic-owned" in content
    assert 'data-ai-provider-layout="responsive-grid"' in content
    assert 'data-ai-provider-field="provider"' in content
    assert 'data-ai-provider-field="base-url"' in content
    assert 'data-ai-provider-field="api-key"' in content
    assert 'data-ai-provider-field="primary-model"' in content
    assert 'data-ai-provider-field="fallback-model"' in content
    assert "OpenAI" in content
    assert "Base URL" in content
    assert "Primary model" in content
    assert "Fallback model" in content
    assert "API key" in content
    assert 'name="openai_model"' in content
    assert 'name="openai_fallback_model"' in content
    assert 'data-ai-provider-models-url="' in content
    assert reverse("dashboard:ai_provider_models") in content
    assert 'data-ai-provider-model-status' in content
    assert 'data-ai-provider-model-status role="status" aria-live="polite"' in content
    assert content.index('data-ai-provider-model-status') < content.index('data-ai-provider-layout="responsive-grid"')
    assert re.search(
        r'<div class="mb-4 flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">.*?'
        r'<span class="cf-badge cf-badge-info self-start[^"]*" data-ai-provider-model-status role="status" aria-live="polite">',
        content,
        re.DOTALL,
    )
    assert 'data-model-combobox="primary"' in content
    assert 'data-model-combobox="fallback"' in content
    assert 'data-model-search="primary"' in content
    assert 'data-model-search="fallback"' in content
    assert 'data-model-options="primary"' in content
    assert 'data-model-options="fallback"' in content
    assert 'type="hidden" name="openai_model"' in content
    assert 'type="hidden" name="openai_fallback_model"' in content
    assert 'data-model-value="primary"' in content
    assert 'data-model-value="fallback"' in content
    assert 'id="ai-provider-primary-model-search"' in content
    assert 'data-model-search="primary" value="gpt-4o"' in content
    assert 'name="openai_model" value="gpt-4o"' in content
    assert 'id="ai-provider-fallback-model-search"' in content
    assert 'data-model-search="fallback" value="gpt-4o-mini"' in content
    assert 'name="openai_fallback_model" value="gpt-4o-mini"' in content
    assert "Provider model discovery" not in content
    assert 'data-ai-provider-model-fetch' not in content
    assert "Fetch models" not in content
    assert "Enable clinic-owned AI provider" not in content
    assert "When disabled, the Assistant falls back to the platform default behavior." not in content
    assert "Fallback routing" not in content
    assert "Active routing" not in content
    assert 'name="is_enabled"' not in content
    assert "setStatus(error.message" not in content
    assert "error.message ||" not in content
    assert "Custom model ID" not in content
    assert "Custom fallback model ID" not in content
    assert 'name="custom_model"' not in content
    assert 'name="custom_fallback_model"' not in content
    assert "const modelFetchDebounceMs = 500;" in content
    assert "let modelFetchTimer = null;" in content
    assert "scheduleModelFetch()" in content
    assert "window.setTimeout(fetchProviderModels" in content
    assert "renderModelOptions('primary')" in content
    assert "renderModelOptions('fallback')" in content
    assert "selectModel(role, modelId)" in content
    assert "data-model-option" in content
    assert "clearModelSelections()" in content
    assert "fetchedModels = [];" in content
    assert "initialModelValues" in content
    assert 'role="combobox"' in content
    assert 'aria-autocomplete="list"' in content
    assert 'aria-controls="ai-provider-primary-model-options"' in content
    assert 'aria-controls="ai-provider-fallback-model-options"' in content
    assert "button.setAttribute('role', 'option')" in content
    assert "button.addEventListener('click'" in content
    assert "button.setAttribute('aria-selected'" in content
    assert "button.tabIndex = -1" in content or "button.setAttribute('tabindex', '-1')" in content
    assert "aria-activedescendant" in content
    assert "let activeOptionIndexes" in content
    assert "event.key === 'ArrowDown'" in content
    assert "event.key === 'ArrowUp'" in content
    assert "setActiveOption(role" in content
    assert "event.key === 'Enter'" in content
    assert "event.preventDefault()" in content
    assert "selectModel(role, models[0].id)" in content
    assert "event.key === 'Escape'" in content
    assert 'aria-expanded="false"' in content
    assert "setAttribute('aria-expanded', 'false')" in content
    assert "controls[role].value.value = controls[role].search.value" not in content
    assert "setStatus(error.message" not in content
    assert "error.message ||" not in content
    assert "retries only if the primary model fails" in content
    assert "gpt-4o-mini" in content
    assert "gpt-4o" in content
    assert "sk-dashboard-secret" not in content
    assert "************" in content


@pytest.mark.django_db
def test_ai_provider_model_search_executes_keyboard_selection_and_clears_stale_values(clinic_setup, client):
    from playwright.sync_api import sync_playwright

    clinic, service, owner = clinic_setup
    client.force_login(owner)
    response = client.get(reverse("dashboard:assistant_settings"))
    content = response.content.decode()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.route(
                f"**{reverse('dashboard:ai_provider_models')}",
                lambda route: route.fulfill(
                    status=200,
                    content_type="application/json",
                    body=json.dumps(
                        {
                            "success": True,
                            "models": [
                                {"id": "provider/model-a", "label": "provider/model-a"},
                                {"id": "provider/model-b", "label": "provider/model-b"},
                                {"id": "anthropic/claude", "label": "anthropic/claude"},
                            ],
                        }
                    ),
                ),
            )
            page.set_content(content.replace("<head>", '<head><base href="http://testserver/">', 1))
            page.locator('[name="api_key"]').fill("sk-playwright-key")
            page.wait_for_function("document.querySelector('[data-ai-provider-model-status]').textContent.includes('Fetched 3 models')")
            assert page.locator('[data-ai-provider-model-status]').text_content() == "Fetched 3 models."

            primary = page.locator('[data-model-search="primary"]')
            primary.fill("model")
            primary.press("ArrowDown")
            primary.press("ArrowDown")
            primary.press("Enter")
            assert page.locator('[data-model-value="primary"]').input_value() == "provider/model-b"
            assert primary.input_value() == "provider/model-b"

            primary.fill("not-a-real-model")
            assert page.locator('[data-model-value="primary"]').input_value() == ""

            primary.fill("model")
            primary.press("ArrowDown")
            primary.press("Enter")
            assert page.locator('[data-model-value="primary"]').input_value() == "provider/model-a"

            page.locator('[name="api_key"]').fill("sk-changed-key")
            assert page.locator('[data-model-value="primary"]').input_value() == ""
        finally:
            browser.close()


@pytest.mark.django_db
def test_ai_provider_model_search_preserves_saved_values_missing_from_fetched_models(clinic_setup, client):
    from clinics.models import ClinicAIProviderSettings
    from playwright.sync_api import sync_playwright

    clinic, service, owner = clinic_setup
    ClinicAIProviderSettings.objects.create(
        clinic=clinic,
        provider=ClinicAIProviderSettings.PROVIDER_OPENAI,
        model="legacy/primary",
        fallback_model="legacy/fallback",
        api_key="sk-saved-key",
    )
    client.force_login(owner)
    response = client.get(reverse("dashboard:assistant_settings"))
    content = response.content.decode()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.route(
                f"**{reverse('dashboard:ai_provider_models')}",
                lambda route: route.fulfill(
                    status=200,
                    content_type="application/json",
                    body=json.dumps(
                        {
                            "success": True,
                            "models": [{"id": "provider/model-a", "label": "provider/model-a"}],
                        }
                    ),
                ),
            )
            page.set_content(content.replace("<head>", '<head><base href="http://testserver/">', 1))
            page.wait_for_function("document.querySelector('[data-ai-provider-model-status]').textContent.includes('Fetched 1 model')")

            assert page.locator('[data-model-value="primary"]').input_value() == "legacy/primary"
            assert page.locator('[data-model-search="primary"]').input_value() == "legacy/primary"
            assert page.locator('[data-model-value="fallback"]').input_value() == "legacy/fallback"
            assert page.locator('[data-model-search="fallback"]').input_value() == "legacy/fallback"
        finally:
            browser.close()


@pytest.mark.django_db
def test_ai_provider_model_options_overlay_does_not_stretch_provider_column(clinic_setup, client):
    from playwright.sync_api import sync_playwright

    clinic, service, owner = clinic_setup
    client.force_login(owner)
    response = client.get(reverse("dashboard:assistant_settings"))
    content = response.content.decode()
    models = [{"id": f"provider/model-{index:02d}", "label": f"provider/model-{index:02d}"} for index in range(30)]

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": 1400, "height": 900})
            page.route(
                f"**{reverse('dashboard:ai_provider_models')}",
                lambda route: route.fulfill(
                    status=200,
                    content_type="application/json",
                    body=json.dumps({"success": True, "models": models}),
                ),
            )
            page.set_content(content.replace("<head>", '<head><base href="http://testserver/">', 1))
            page.add_style_tag(content="""
                [data-ai-provider-layout] { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; align-items: stretch; }
                [data-ai-provider-field="provider"] { order: 1; }
                [data-ai-provider-field="primary-model"] { order: 2; }
                [data-ai-provider-field="base-url"] { order: 3; }
                [data-ai-provider-field="fallback-model"] { order: 4; }
                [data-ai-provider-field="api-key"] { order: 5; }
                [data-ai-provider-field] { min-height: 0; }
                .hidden { display: none !important; }
                .relative { position: relative; }
                .absolute { position: absolute; }
                .left-0 { left: 0; }
                .right-0 { right: 0; }
                .top-full { top: 100%; }
                .z-30 { z-index: 30; }
                .max-h-56 { max-height: 224px; }
                .overflow-y-auto { overflow-y: auto; }
                .block { display: block; }
                .w-full { width: 100%; }
                .cf-input, .cf-select { box-sizing: border-box; display: block; height: 40px; width: 100%; }
            """)
            page.locator('[name="api_key"]').fill("sk-playwright-key")
            page.wait_for_function("document.querySelector('[data-ai-provider-model-status]').textContent.includes('Fetched 30 models')")

            provider_height_before = page.locator('[data-ai-provider-field="provider"]').evaluate("element => element.getBoundingClientRect().height")
            primary = page.locator('[data-model-search="primary"]')
            primary.fill("model")
            page.wait_for_function('!document.querySelector(\'[data-model-options="primary"]\').classList.contains("hidden")')
            provider_height_after = page.locator('[data-ai-provider-field="provider"]').evaluate("element => element.getBoundingClientRect().height")

            assert provider_height_after <= provider_height_before + 8
        finally:
            browser.close()


@pytest.mark.django_db
def test_assistant_settings_empty_ai_provider_does_not_render_static_default_models(clinic_setup, client):
    clinic, service, owner = clinic_setup
    client.force_login(owner)

    response = client.get(reverse("dashboard:assistant_settings"))
    content = response.content.decode()

    assert response.status_code == 200
    assert "Provider model discovery" not in content
    assert "Fetch models" not in content
    assert 'data-model-combobox="primary"' in content
    assert 'data-model-combobox="fallback"' in content
    assert 'value="gpt-4o-mini"' not in content
    assert 'value="gpt-4o"' not in content
    assert "Models will load after provider details are entered." in content


@pytest.mark.django_db
def test_assistant_settings_marks_api_key_post_parameter_sensitive(clinic_setup, monkeypatch):
    from dashboard import views

    clinic, service, owner = clinic_setup
    request = RequestFactory().post(
        "/dashboard/assistant/",
        {
            "_form": "unused",
            "api_key": "sk-dashboard-secret",
        },
    )
    request.user = owner

    def checked_clinic(request, allow_missing=False):
        assert getattr(request, "sensitive_post_parameters", None) == ("api_key",)
        return clinic

    def fake_render(request, template_name, context, *args, **kwargs):
        return HttpResponse("ok")

    monkeypatch.setattr(views, "_clinic_or_redirect", checked_clinic)
    monkeypatch.setattr(views, "render", fake_render)

    response = views.assistant_settings(request)

    assert response.status_code == 200


@pytest.mark.django_db
def test_ai_provider_models_marks_api_key_sensitive(clinic_setup, monkeypatch):
    from clinics.models import ClinicAIProviderSettings
    from dashboard import views

    clinic, service, owner = clinic_setup
    request = RequestFactory().post(
        "/dashboard/assistant/provider-models/",
        {
            "provider": ClinicAIProviderSettings.PROVIDER_OPENAI,
            "api_key": "sk-live-key",
        },
    )
    request.user = owner

    def checked_clinic(request, allow_missing=False):
        assert getattr(request, "sensitive_post_parameters", None) == ("api_key",)
        return clinic

    def fake_fetch(base_url, api_key, *, clinic_id=None, provider=""):
        return ["gpt-4o"]

    monkeypatch.setattr(views, "_clinic_or_redirect", checked_clinic)
    monkeypatch.setattr(views, "fetch_available_models", fake_fetch)

    response = views.ai_provider_models(request)

    has_sensitive_api_key_marker = False
    wrapped = views.ai_provider_models
    while wrapped is not None:
        if getattr(wrapped, "sensitive_variables", None) == ("api_key",):
            has_sensitive_api_key_marker = True
            break
        wrapped = getattr(wrapped, "__wrapped__", None)

    assert response.status_code == 200
    assert has_sensitive_api_key_marker


@pytest.mark.django_db
def test_ai_provider_models_requires_login(client):
    response = client.post(reverse("dashboard:ai_provider_models"), {"provider": "openai", "api_key": "sk-key"})

    assert response.status_code == 302
    assert reverse("accounts:login") in response["Location"] or "/login" in response["Location"]


@pytest.mark.django_db
def test_ai_provider_models_rejects_get(clinic_setup, client):
    clinic, service, owner = clinic_setup
    client.force_login(owner)

    response = client.get(reverse("dashboard:ai_provider_models"))

    assert response.status_code == 405


@pytest.mark.django_db
def test_ai_provider_models_rejects_unsupported_provider(clinic_setup, client):
    clinic, service, owner = clinic_setup
    client.force_login(owner)

    response = client.post(
        reverse("dashboard:ai_provider_models"),
        {"provider": "unsupported", "api_key": "sk-key"},
    )

    assert response.status_code == 400
    assert response.json() == {"success": False, "error": "Choose a supported AI provider."}


@pytest.mark.django_db
def test_owner_can_fetch_ai_provider_models_from_entered_key(clinic_setup, client, monkeypatch):
    from clinics.models import ClinicAIProviderSettings

    clinic, service, owner = clinic_setup
    client.force_login(owner)

    def fake_fetch(base_url, api_key, *, clinic_id=None, provider=""):
        assert base_url == ClinicAIProviderSettings.OPENAI_BASE_URL
        assert api_key == "sk-live-key"
        assert clinic_id == clinic.id
        assert provider == ClinicAIProviderSettings.PROVIDER_OPENAI
        return ["gpt-4o", "gpt-4o-mini"]

    monkeypatch.setattr("dashboard.views.fetch_available_models", fake_fetch)

    response = client.post(
        reverse("dashboard:ai_provider_models"),
        {
            "provider": ClinicAIProviderSettings.PROVIDER_OPENAI,
            "base_url": "https://ignored.example/v1",
            "api_key": "sk-live-key",
        },
    )
    payload = response.json()

    assert response.status_code == 200
    assert payload == {
        "success": True,
        "models": [
            {"id": "gpt-4o", "label": "gpt-4o"},
            {"id": "gpt-4o-mini", "label": "gpt-4o-mini"},
        ],
    }
    assert "sk-live-key" not in response.content.decode()


@pytest.mark.django_db
def test_staff_cannot_fetch_ai_provider_models(clinic_setup, client):
    from clinics.models import ClinicAIProviderSettings

    User = get_user_model()
    clinic, service, owner = clinic_setup
    staff = User.objects.create_user(username="staff-models@example.com", email="staff-models@example.com", password="password123")
    ClinicMembership.objects.create(clinic=clinic, user=staff, role=ClinicMembership.ROLE_STAFF)
    client.force_login(staff)

    response = client.post(
        reverse("dashboard:ai_provider_models"),
        {
            "provider": ClinicAIProviderSettings.PROVIDER_OPENAI,
            "api_key": "sk-live-key",
        },
    )

    assert response.status_code == 403


@pytest.mark.django_db
def test_ai_provider_models_rejects_unsafe_base_url_before_network(clinic_setup, client, monkeypatch):
    from clinics.models import ClinicAIProviderSettings

    clinic, service, owner = clinic_setup
    client.force_login(owner)

    def fail_fetch(*args, **kwargs):
        pytest.fail("fetch_available_models should not run for unsafe base URLs")

    monkeypatch.setattr("dashboard.views.fetch_available_models", fail_fetch)

    response = client.post(
        reverse("dashboard:ai_provider_models"),
        {
            "provider": ClinicAIProviderSettings.PROVIDER_OPENAI_COMPATIBLE,
            "base_url": "https://127.0.0.1/v1",
            "api_key": "sk-live-key",
        },
    )
    payload = response.json()

    assert response.status_code == 400
    assert payload == {"success": False, "error": "Enter a valid provider base URL."}


@pytest.mark.django_db
def test_ai_provider_models_mask_uses_only_active_clinic_saved_key(client, monkeypatch):
    from clinics.forms import SAVED_PROVIDER_SECRET_MASK
    from clinics.models import ClinicAIProviderSettings

    monkeypatch.setattr(
        "clinics.ai_provider_validation.socket.getaddrinfo",
        lambda *args, **kwargs: [(None, None, None, None, ("8.8.8.8", 0))],
    )
    User = get_user_model()
    owner_a = User.objects.create_user(username="models-a@example.com", email="models-a@example.com", password="password123")
    group_a = ClinicGroup.objects.create(name="Models A Group", owner=owner_a)
    clinic_a = Clinic.objects.create(group=group_a, name="Models A", slug="models-a")
    ClinicMembership.objects.create(clinic=clinic_a, user=owner_a, role=ClinicMembership.ROLE_OWNER)
    ClinicAIProviderSettings.objects.create(clinic=clinic_a, api_key="sk-a")

    owner_b = User.objects.create_user(username="models-b@example.com", email="models-b@example.com", password="password123")
    group_b = ClinicGroup.objects.create(name="Models B Group", owner=owner_b)
    clinic_b = Clinic.objects.create(group=group_b, name="Models B", slug="models-b")
    ClinicMembership.objects.create(clinic=clinic_b, user=owner_b, role=ClinicMembership.ROLE_OWNER)
    ClinicAIProviderSettings.objects.create(
        clinic=clinic_b,
        provider=ClinicAIProviderSettings.PROVIDER_OPENAI_COMPATIBLE,
        base_url="https://openrouter.ai/api/v1",
        api_key="sk-b",
    )
    client.force_login(owner_b)

    def fake_fetch(base_url, api_key, *, clinic_id=None, provider=""):
        assert api_key == "sk-b"
        assert clinic_id == clinic_b.id
        return ["provider/model"]

    monkeypatch.setattr("dashboard.views.fetch_available_models", fake_fetch)

    response = client.post(
        reverse("dashboard:ai_provider_models"),
        {
            "provider": ClinicAIProviderSettings.PROVIDER_OPENAI_COMPATIBLE,
            "base_url": "https://openrouter.ai/api/v1",
            "api_key": SAVED_PROVIDER_SECRET_MASK,
        },
    )

    assert response.status_code == 200
    content = response.content.decode()
    assert "provider/model" in content
    assert "sk-a" not in content
    assert "sk-b" not in content


@pytest.mark.django_db
def test_ai_provider_models_mask_rejects_changed_compatible_base_url(clinic_setup, client, monkeypatch):
    from clinics.forms import SAVED_PROVIDER_SECRET_MASK
    from clinics.models import ClinicAIProviderSettings

    monkeypatch.setattr(
        "clinics.ai_provider_validation.socket.getaddrinfo",
        lambda *args, **kwargs: [(None, None, None, None, ("8.8.8.8", 0))],
    )
    clinic, service, owner = clinic_setup
    ClinicAIProviderSettings.objects.create(
        clinic=clinic,
        provider=ClinicAIProviderSettings.PROVIDER_OPENAI_COMPATIBLE,
        base_url="https://openrouter.ai/api/v1",
        api_key="sk-openrouter",
    )
    client.force_login(owner)

    def fail_fetch(*args, **kwargs):
        pytest.fail("fetch_available_models should not run when masked key changes provider base URL")

    monkeypatch.setattr("dashboard.views.fetch_available_models", fail_fetch)

    response = client.post(
        reverse("dashboard:ai_provider_models"),
        {
            "provider": ClinicAIProviderSettings.PROVIDER_OPENAI_COMPATIBLE,
            "base_url": "https://api.other-provider.example/v1",
            "api_key": SAVED_PROVIDER_SECRET_MASK,
        },
    )
    payload = response.json()

    assert response.status_code == 400
    assert payload == {"success": False, "error": "Enter an API key before fetching models."}
    assert "sk-openrouter" not in response.content.decode()


@pytest.mark.django_db
def test_ai_provider_models_blank_key_uses_saved_key_when_provider_base_url_match(clinic_setup, client, monkeypatch):
    from clinics.models import ClinicAIProviderSettings

    monkeypatch.setattr(
        "clinics.ai_provider_validation.socket.getaddrinfo",
        lambda *args, **kwargs: [(None, None, None, None, ("8.8.8.8", 0))],
    )
    clinic, service, owner = clinic_setup
    ClinicAIProviderSettings.objects.create(
        clinic=clinic,
        provider=ClinicAIProviderSettings.PROVIDER_OPENAI_COMPATIBLE,
        base_url="https://openrouter.ai/api/v1",
        api_key="sk-openrouter-key",
    )
    client.force_login(owner)

    def fake_fetch(base_url, api_key, *, clinic_id=None, provider=""):
        assert base_url == "https://openrouter.ai/api/v1"
        assert api_key == "sk-openrouter-key"
        assert clinic_id == clinic.id
        return ["provider/model"]

    monkeypatch.setattr("dashboard.views.fetch_available_models", fake_fetch)

    response = client.post(
        reverse("dashboard:ai_provider_models"),
        {
            "provider": ClinicAIProviderSettings.PROVIDER_OPENAI_COMPATIBLE,
            "base_url": "https://openrouter.ai/api/v1/",
            "api_key": "",
        },
    )

    assert response.status_code == 200
    assert response.json()["models"] == [{"id": "provider/model", "label": "provider/model"}]
    assert "sk-openrouter-key" not in response.content.decode()


@pytest.mark.django_db
def test_ai_provider_models_returns_generic_error_without_secret(clinic_setup, client, monkeypatch):
    from clinics.models import ClinicAIProviderSettings
    from messenger.ai_provider_client import AIProviderError

    clinic, service, owner = clinic_setup
    client.force_login(owner)

    def fake_fetch(base_url, api_key, *, clinic_id=None, provider=""):
        raise AIProviderError("AI provider model fetch failed.")

    monkeypatch.setattr("dashboard.views.fetch_available_models", fake_fetch)

    response = client.post(
        reverse("dashboard:ai_provider_models"),
        {
            "provider": ClinicAIProviderSettings.PROVIDER_OPENAI,
            "api_key": "sk-bad-key",
        },
    )
    payload = response.json()

    assert response.status_code == 400
    assert payload == {"success": False, "error": "Could not fetch models from this provider. Check the base URL and API key."}
    assert "sk-bad-key" not in response.content.decode()


@pytest.mark.django_db
def test_owner_can_save_ai_provider_settings_from_assistant_page(clinic_setup, client):
    from clinics.models import ClinicAIProviderSettings

    clinic, service, owner = clinic_setup
    client.force_login(owner)

    response = client.post(
        reverse("dashboard:assistant_settings"),
        {
            "_form": "ai_provider_settings",
            "provider": ClinicAIProviderSettings.PROVIDER_OPENAI,
            "base_url": "https://ignored.example/v1",
            "openai_model": "gpt-4o",
            "openai_fallback_model": "gpt-4o-mini",
            "api_key": "sk-owner-provider-key",
        },
    )

    assert response.status_code == 302
    settings = ClinicAIProviderSettings.objects.get(clinic=clinic)
    assert settings.provider == ClinicAIProviderSettings.PROVIDER_OPENAI
    assert settings.base_url == ClinicAIProviderSettings.OPENAI_BASE_URL
    assert settings.model == "gpt-4o"
    assert settings.fallback_model == "gpt-4o-mini"
    assert settings.api_key == "sk-owner-provider-key"
    assert settings.is_configured is True


@pytest.mark.django_db
def test_ai_provider_fallback_model_errors_render_on_assistant_page(client, monkeypatch, clinic_setup):
    from clinics.models import ClinicAIProviderSettings

    monkeypatch.setattr(
            "clinics.ai_provider_validation.socket.getaddrinfo",
        lambda *args, **kwargs: [(None, None, None, None, ("8.8.8.8", 0))],
    )

    clinic, service, owner = clinic_setup
    client.force_login(owner)

    response = client.post(
        reverse("dashboard:assistant_settings"),
        {
            "_form": "ai_provider_settings",
            "provider": ClinicAIProviderSettings.PROVIDER_OPENAI_COMPATIBLE,
            "base_url": "https://openrouter.ai/api/v1",
            "openai_model": "gpt-4o",
            "openai_fallback_model": "",
            "api_key": "sk-provider-key",
        },
    )
    content = response.content.decode()

    assert response.status_code == 200
    assert "Fallback model is required." in content


@pytest.mark.django_db
def test_staff_cannot_save_ai_provider_settings(clinic_setup, client):
    from clinics.models import ClinicAIProviderSettings

    User = get_user_model()
    clinic, service, owner = clinic_setup
    staff = User.objects.create_user(username="staff-provider@example.com", email="staff-provider@example.com", password="password123")
    ClinicMembership.objects.create(clinic=clinic, user=staff, role=ClinicMembership.ROLE_STAFF)
    settings = ClinicAIProviderSettings.objects.create(
        clinic=clinic,
        provider=ClinicAIProviderSettings.PROVIDER_OPENAI,
        model="gpt-4o-mini",
        fallback_model="gpt-4o",
        api_key="sk-original-key",
    )
    client.force_login(staff)

    response = client.post(
        reverse("dashboard:assistant_settings"),
        {
            "_form": "ai_provider_settings",
            "provider": ClinicAIProviderSettings.PROVIDER_OPENAI,
            "base_url": ClinicAIProviderSettings.OPENAI_BASE_URL,
            "openai_model": "gpt-4o",
            "openai_fallback_model": "gpt-4o-mini",
            "api_key": "sk-staff-key",
        },
    )

    assert response.status_code == 403
    settings.refresh_from_db()
    assert settings.model == "gpt-4o-mini"
    assert settings.fallback_model == "gpt-4o"
    assert settings.api_key == "sk-original-key"


@pytest.mark.django_db
def test_ai_provider_settings_save_is_scoped_to_current_clinic(client, monkeypatch):
    from clinics.models import ClinicAIProviderSettings

    monkeypatch.setattr(
            "clinics.ai_provider_validation.socket.getaddrinfo",
        lambda *args, **kwargs: [(None, None, None, None, ("8.8.8.8", 0))],
    )

    User = get_user_model()
    owner_a = User.objects.create_user(username="provider-a@example.com", email="provider-a@example.com", password="password123")
    group_a = ClinicGroup.objects.create(name="Provider A Group", owner=owner_a)
    clinic_a = Clinic.objects.create(group=group_a, name="Provider A", slug="provider-a")
    ClinicMembership.objects.create(clinic=clinic_a, user=owner_a, role=ClinicMembership.ROLE_OWNER)
    settings_a = ClinicAIProviderSettings.objects.create(clinic=clinic_a, api_key="sk-a", model="gpt-4o-mini", fallback_model="gpt-4o")

    owner_b = User.objects.create_user(username="provider-b@example.com", email="provider-b@example.com", password="password123")
    group_b = ClinicGroup.objects.create(name="Provider B Group", owner=owner_b)
    clinic_b = Clinic.objects.create(group=group_b, name="Provider B", slug="provider-b")
    ClinicMembership.objects.create(clinic=clinic_b, user=owner_b, role=ClinicMembership.ROLE_OWNER)
    settings_b = ClinicAIProviderSettings.objects.create(clinic=clinic_b, api_key="sk-b", model="gpt-4o-mini", fallback_model="gpt-4o")
    client.force_login(owner_b)

    response = client.post(
        reverse("dashboard:assistant_settings"),
        {
            "_form": "ai_provider_settings",
            "provider": ClinicAIProviderSettings.PROVIDER_OPENAI_COMPATIBLE,
            "base_url": "https://openrouter.ai/api/v1",
            "openai_model": "gpt-4o",
            "openai_fallback_model": "gpt-4o-mini",
            "api_key": "sk-b-new",
        },
    )

    assert response.status_code == 302
    settings_a.refresh_from_db()
    settings_b.refresh_from_db()
    assert settings_a.api_key == "sk-a"
    assert settings_a.model == "gpt-4o-mini"
    assert settings_a.fallback_model == "gpt-4o"
    assert settings_b.api_key == "sk-b-new"
    assert settings_b.model == "gpt-4o"
    assert settings_b.fallback_model == "gpt-4o-mini"


@pytest.mark.django_db
def test_staff_cannot_create_faq_directly(clinic_setup, client):
    clinic, service, owner = clinic_setup
    User = get_user_model()
    staff = User.objects.create_user(username="staff-faq@example.com", email="staff-faq@example.com", password="password123")
    ClinicMembership.objects.create(clinic=clinic, user=staff, role=ClinicMembership.ROLE_STAFF)
    client.force_login(staff)

    response = client.post(reverse("dashboard:create_faq"), {"question": "Q", "answer": "A", "is_active": "on"})

    assert response.status_code == 403
    assert clinic.faqs.count() == 0


@pytest.mark.django_db
def test_staff_cannot_edit_toggle_or_delete_faq_directly(clinic_setup, client):
    from clinics.models import ClinicFAQ

    clinic, service, owner = clinic_setup
    faq = ClinicFAQ.objects.create(clinic=clinic, question="Question", answer="Answer")
    User = get_user_model()
    staff = User.objects.create_user(username="staff-faq-actions@example.com", email="staff-faq-actions@example.com", password="password123")
    ClinicMembership.objects.create(clinic=clinic, user=staff, role=ClinicMembership.ROLE_STAFF)
    client.force_login(staff)

    edit = client.post(reverse("dashboard:edit_faq", args=[faq.id]), {"question": "Changed", "answer": "Changed", "is_active": "on"})
    toggle = client.post(reverse("dashboard:toggle_faq", args=[faq.id]))
    delete = client.post(reverse("dashboard:delete_faq", args=[faq.id]))

    assert edit.status_code == 403
    assert toggle.status_code == 403
    assert delete.status_code == 403
    faq.refresh_from_db()
    assert faq.question == "Question"
    assert faq.is_active is True


@pytest.mark.django_db
def test_owner_edit_faq_preserves_visibility_when_status_not_posted(clinic_setup, client):
    from clinics.models import ClinicFAQ

    clinic, service, owner = clinic_setup
    faq = ClinicFAQ.objects.create(clinic=clinic, question="Question", answer="Answer", is_active=True)
    client.force_login(owner)

    response = client.post(reverse("dashboard:edit_faq", args=[faq.id]), {"question": "Changed", "answer": "Changed answer"})

    assert response.status_code == 302
    faq.refresh_from_db()
    assert faq.question == "Changed"
    assert faq.answer == "Changed answer"
    assert faq.is_active is True


@pytest.mark.django_db
def test_widget_settings_form_excludes_unused_behavior_instructions(clinic_setup):
    from clinics.forms import WidgetSettingsForm

    clinic, service, owner = clinic_setup

    form = WidgetSettingsForm(instance=clinic)

    assert "widget_behavior_instructions" not in form.fields


@pytest.mark.django_db
def test_widget_settings_no_longer_exposes_reason_field_toggle(clinic_setup, client):
    from django.core.exceptions import FieldDoesNotExist
    from clinics.forms import WidgetSettingsForm

    clinic, service, owner = clinic_setup
    client.force_login(owner)

    with pytest.raises(FieldDoesNotExist):
        Clinic._meta.get_field("show_reason_field")

    form = WidgetSettingsForm(instance=clinic)
    assert "show_reason_field" not in form.fields

    response = client.get(reverse("dashboard:assistant_settings"))

    assert response.status_code == 200
    assert b'show_reason_field' not in response.content


@pytest.mark.django_db
def test_widget_settings_rejects_invalid_accent_color(clinic_setup):
    from clinics.forms import WidgetSettingsForm

    clinic, service, owner = clinic_setup
    form = WidgetSettingsForm(
        data={
            "widget_accent_color": '";alert(1)//',
            "widget_welcome_message": "Welcome",
        },
        instance=clinic,
    )

    assert not form.is_valid()
    assert "widget_accent_color" in form.errors


@pytest.mark.django_db
def test_completed_appointment_cannot_be_cancelled_directly(calendar_setup, client):
    clinic, service, user, patient, appointment, target_date = calendar_setup
    appointment.status = Appointment.STATUS_COMPLETED
    appointment.save(update_fields=["status", "updated_at"])
    client.force_login(user)

    response = client.post(reverse("dashboard:appointment_cancel", args=[appointment.id]))

    assert response.status_code == 302
    appointment.refresh_from_db()
    assert appointment.status == Appointment.STATUS_COMPLETED


@pytest.mark.django_db
def test_htmx_cancel_error_stays_visible_without_success_trigger(calendar_setup, client):
    clinic, service, user, patient, appointment, target_date = calendar_setup
    appointment.status = Appointment.STATUS_COMPLETED
    appointment.save(update_fields=["status", "updated_at"])
    client.force_login(user)

    response = client.post(
        reverse("dashboard:appointment_cancel", args=[appointment.id]),
        HTTP_HX_REQUEST="true",
    )

    assert response.status_code == 200
    assert b"Cannot cancel this appointment" in response.content
    assert "Appointment cancelled." not in response.headers.get("HX-Trigger", "")


@pytest.mark.django_db
def test_cancelled_appointment_cannot_be_rescheduled_directly(calendar_setup, client):
    clinic, service, user, patient, appointment, target_date = calendar_setup
    original_start = appointment.starts_at
    appointment.status = Appointment.STATUS_CANCELLED
    appointment.save(update_fields=["status", "updated_at"])
    client.force_login(user)

    response = client.post(
        reverse("dashboard:appointment_reschedule", args=[appointment.id]),
        {"new_date": target_date.isoformat(), "new_time": "11:00"},
    )

    assert response.status_code == 302
    appointment.refresh_from_db()
    assert appointment.starts_at == original_start
    assert appointment.status == Appointment.STATUS_CANCELLED


@pytest.mark.django_db
def test_dashboard_routes_without_clinic_membership_do_not_500(client):
    User = get_user_model()
    user = User.objects.create_user(username="no-clinic@example.com", email="no-clinic@example.com", password="password123")
    client.force_login(user)
    client.raise_request_exception = False

    response = client.get(reverse("dashboard:appointments"))

    assert response.status_code in {302, 403}


@pytest.mark.django_db
def test_save_business_hours_rejects_close_before_open(clinic_setup, client):
    clinic, service, user = clinic_setup
    target_weekday = 0
    existing = ClinicBusinessHour.objects.create(
        clinic=clinic,
        weekday=target_weekday,
        is_open=True,
        open_time=time(9),
        close_time=time(17),
    )
    client.force_login(user)
    data = {}
    for weekday in range(7):
        data[f"is_open_{weekday}"] = "on"
        data[f"open_time_{weekday}"] = "09:00"
        data[f"close_time_{weekday}"] = "17:00"
        data[f"break_start_{weekday}"] = ""
        data[f"break_end_{weekday}"] = ""
    data[f"open_time_{target_weekday}"] = "17:00"
    data[f"close_time_{target_weekday}"] = "09:00"

    response = client.post(reverse("dashboard:save_business_hours"), data)

    assert response.status_code == 302
    existing.refresh_from_db()
    assert existing.open_time == time(9)
    assert existing.close_time == time(17)


@pytest.mark.django_db
def test_widget_embed_page_explains_recommended_launcher_and_advanced_iframe(clinic_setup, client):
    clinic, service, user = clinic_setup
    client.force_login(user)

    response = client.get(reverse("dashboard:widget_embed"))
    content = response.content.decode()

    assert response.status_code == 200
    assert ">Booking Widget</h1>" in content
    assert "Recommended JavaScript launcher" in content
    assert "Adds a small bottom-right booking button" in content
    assert "full widget opens after click" in content
    assert "&lt;script src=" in content
    assert "Advanced iframe fallback" in content
    assert "Embeds the full panel directly" in content
    assert "visible immediately" in content
    assert "&lt;iframe src=" in content


@pytest.mark.django_db
def test_widget_embed_iframe_uses_embed_source_and_responsive_dimensions(clinic_setup, client):
    clinic, service, user = clinic_setup
    client.force_login(user)

    response = client.get(reverse("dashboard:widget_embed"))
    content = response.content.decode()

    assert response.status_code == 200
    assert "?source=embed" in content
    assert "bottom:max(16px, env(safe-area-inset-bottom))" in content
    assert "right:max(16px, env(safe-area-inset-right))" in content
    assert "max-width:calc(100vw - 32px - env(safe-area-inset-right))" in content
    assert "max-height:calc(100dvh - 32px - env(safe-area-inset-bottom))" in content
    assert 'allow="microphone; clipboard-write"' in content
