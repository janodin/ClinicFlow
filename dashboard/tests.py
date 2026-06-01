import pytest
from datetime import time, timedelta, timezone as dt_timezone
from zoneinfo import ZoneInfo
from django.urls import reverse

from clinics.models import Clinic, ClinicGroup, ClinicMembership
from patients.models import Patient
from services.models import Service
from appointments.models import Appointment
from django.contrib.auth import get_user_model
from django.utils import timezone
from scheduling.models import ClinicBusinessHour, UnavailableDate


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
    patient = Patient.objects.create(clinic=clinic, full_name="Test Patient", phone="09170001111")
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
def test_settings_page_does_not_show_blocked_times(clinic_setup, client):
    clinic, service, user = clinic_setup
    client.force_login(user)

    response = client.get(reverse("dashboard:settings"))

    assert response.status_code == 200
    assert b"Blocked Times" not in response.content
    assert b"Add Blocked Time" not in response.content
    assert b"Unavailable Dates" in response.content


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
def test_calendar_page_uses_event_title_time_only(calendar_setup, client):
    clinic, service, user, patient, appointment, target_date = calendar_setup
    client.force_login(user)

    response = client.get(reverse("dashboard:calendar"))

    assert response.status_code == 200
    assert b"displayEventTime: false" in response.content


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
    assert "already has an appointment" in response.json()["error"].lower()


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
def test_messenger_settings_page_shows_ai_prompt_form(clinic_setup, client):
    from clinics.models import ClinicAISettings
    from messenger.defaults import DEFAULT_MESSENGER_AI_PROMPT
    from messenger.models import MessengerConnection

    clinic, service, user = clinic_setup
    connection = MessengerConnection.objects.create(
        clinic=clinic,
        page_id="PAGE-DASH-AI",
        page_access_token="TOKEN-DASH-AI",
    )
    ClinicAISettings.objects.create(
        clinic=clinic,
        instructions="Use a warm clinic tone.",
        fallback_message="Please call the clinic.",
    )
    client.force_login(user)

    response = client.get(reverse("dashboard:messenger_settings"))

    assert response.status_code == 200
    assert b"Shared AI Prompt" in response.content
    assert b"Prompt / Instructions" in response.content
    assert b'name="is_ai_enabled"' in response.content
    assert b'name="instructions"' in response.content
    assert b'name="fallback_message"' in response.content
    assert b"Restore default prompt" in response.content
    assert DEFAULT_MESSENGER_AI_PROMPT.splitlines()[0].encode() in response.content
    assert b"Use a warm clinic tone." in response.content
    assert b"Please call the clinic." in response.content


@pytest.mark.django_db
def test_messenger_settings_page_shows_empty_ai_prompt_form_without_settings(clinic_setup, client):
    from clinics.models import ClinicAISettings
    from messenger.defaults import DEFAULT_MESSENGER_AI_PROMPT
    from messenger.models import MessengerConnection

    clinic, service, user = clinic_setup
    connection = MessengerConnection.objects.create(
        clinic=clinic,
        page_id="PAGE-DASH-AI-NO-SETTINGS",
        page_access_token="TOKEN-DASH-AI-NO-SETTINGS",
    )
    client.force_login(user)

    response = client.get(reverse("dashboard:messenger_settings"))

    assert response.status_code == 200
    assert b"Shared AI Prompt" in response.content
    assert b'name="instructions"' in response.content
    assert DEFAULT_MESSENGER_AI_PROMPT.splitlines()[0].encode() in response.content
    assert ClinicAISettings.objects.filter(clinic=clinic).exists()


@pytest.mark.django_db
def test_owner_can_save_messenger_connection_app_credentials(clinic_setup, client):
    from messenger.models import MessengerConnection

    clinic, service, user = clinic_setup
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
def test_messenger_settings_page_does_not_render_saved_secrets(clinic_setup, client):
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


@pytest.mark.django_db
def test_owner_can_save_messenger_ai_settings(clinic_setup, client):
    from clinics.models import ClinicAISettings
    from messenger.models import MessengerConnection

    clinic, service, user = clinic_setup
    connection = MessengerConnection.objects.create(
        clinic=clinic,
        page_id="PAGE-DASH-SAVE",
        page_access_token="TOKEN-DASH-SAVE",
    )
    client.force_login(user)

    response = client.post(
        reverse("dashboard:messenger_settings"),
        {
            "_form": "ai_settings",
            "instructions": "Answer briefly and ask for confirmation before booking.",
            "fallback_message": "A staff member will help you soon.",
        },
    )

    assert response.status_code == 302
    assert response.url == reverse("dashboard:messenger_settings")
    settings = ClinicAISettings.objects.get(clinic=clinic)
    assert settings.is_ai_enabled is False
    assert settings.instructions == "Answer briefly and ask for confirmation before booking."
    assert settings.fallback_message == "A staff member will help you soon."


@pytest.mark.django_db
def test_owner_can_enable_messenger_ai_settings(clinic_setup, client):
    from clinics.models import ClinicAISettings
    from messenger.models import MessengerConnection

    clinic, service, user = clinic_setup
    connection = MessengerConnection.objects.create(
        clinic=clinic,
        page_id="PAGE-DASH-ENABLE",
        page_access_token="TOKEN-DASH-ENABLE",
    )
    client.force_login(user)

    response = client.post(
        reverse("dashboard:messenger_settings"),
        {
            "_form": "ai_settings",
            "is_ai_enabled": "on",
            "instructions": "Use a friendly clinic tone.",
            "fallback_message": "Please call us.",
        },
    )

    assert response.status_code == 302
    settings = ClinicAISettings.objects.get(clinic=clinic)
    assert settings.is_ai_enabled is True
    assert settings.instructions == "Use a friendly clinic tone."
    assert settings.fallback_message == "Please call us."


@pytest.mark.django_db
def test_staff_cannot_save_messenger_ai_settings(clinic_setup, client):
    from clinics.models import ClinicAISettings
    from messenger.models import MessengerConnection

    User = get_user_model()
    clinic, service, owner = clinic_setup
    staff = User.objects.create_user(username="staff@example.com", email="staff@example.com", password="password123")
    ClinicMembership.objects.create(clinic=clinic, user=staff, role=ClinicMembership.ROLE_STAFF)
    connection = MessengerConnection.objects.create(
        clinic=clinic,
        page_id="PAGE-DASH-STAFF",
        page_access_token="TOKEN-DASH-STAFF",
    )
    settings = ClinicAISettings.objects.create(
        clinic=clinic,
        is_ai_enabled=False,
        instructions="Existing owner instructions.",
        fallback_message="Existing fallback.",
    )
    client.force_login(staff)

    response = client.post(
        reverse("dashboard:messenger_settings"),
        {
            "_form": "ai_settings",
            "is_ai_enabled": "on",
            "instructions": "Staff should not save this.",
            "fallback_message": "Blocked.",
        },
    )

    assert response.status_code == 403
    settings.refresh_from_db()
    assert settings.is_ai_enabled is False
    assert settings.instructions == "Existing owner instructions."
    assert settings.fallback_message == "Existing fallback."


@pytest.mark.django_db
def test_owner_can_save_messenger_ai_settings_is_scoped_to_current_clinic(client):
    from clinics.models import ClinicAISettings
    from messenger.models import MessengerConnection

    User = get_user_model()
    owner_a = User.objects.create_user(username="owner-a@example.com", email="owner-a@example.com", password="password123")
    group_a = ClinicGroup.objects.create(name="Clinic A Group", owner=owner_a)
    clinic_a = Clinic.objects.create(group=group_a, name="Clinic A", slug="clinic-a")
    ClinicMembership.objects.create(clinic=clinic_a, user=owner_a, role=ClinicMembership.ROLE_OWNER)
    connection_a = MessengerConnection.objects.create(
        clinic=clinic_a,
        page_id="PAGE-DASH-A-ISO",
        page_access_token="TOKEN-DASH-A-ISO",
    )
    settings_a = ClinicAISettings.objects.create(
        clinic=clinic_a,
        is_ai_enabled=False,
        instructions="Clinic A original instructions.",
        fallback_message="Clinic A original fallback.",
    )

    owner_b = User.objects.create_user(username="owner-b@example.com", email="owner-b@example.com", password="password123")
    group_b = ClinicGroup.objects.create(name="Clinic B Group", owner=owner_b)
    clinic_b = Clinic.objects.create(group=group_b, name="Clinic B", slug="clinic-b")
    ClinicMembership.objects.create(clinic=clinic_b, user=owner_b, role=ClinicMembership.ROLE_OWNER)
    connection_b = MessengerConnection.objects.create(
        clinic=clinic_b,
        page_id="PAGE-DASH-B-ISO",
        page_access_token="TOKEN-DASH-B-ISO",
    )
    settings_b = ClinicAISettings.objects.create(
        clinic=clinic_b,
        is_ai_enabled=False,
        instructions="Clinic B original instructions.",
        fallback_message="Clinic B original fallback.",
    )
    client.force_login(owner_b)

    response = client.post(
        reverse("dashboard:messenger_settings"),
        {
            "_form": "ai_settings",
            "is_ai_enabled": "on",
            "instructions": "Clinic B updated instructions.",
            "fallback_message": "Clinic B updated fallback.",
        },
    )

    assert response.status_code == 302
    settings_a.refresh_from_db()
    settings_b.refresh_from_db()
    assert settings_a.is_ai_enabled is False
    assert settings_a.instructions == "Clinic A original instructions."
    assert settings_a.fallback_message == "Clinic A original fallback."
    assert settings_b.is_ai_enabled is True
    assert settings_b.instructions == "Clinic B updated instructions."
    assert settings_b.fallback_message == "Clinic B updated fallback."


@pytest.mark.django_db
def test_owner_can_save_shared_ai_settings_without_messenger_connection(clinic_setup, client):
    from clinics.models import ClinicAISettings

    clinic, service, user = clinic_setup
    client.force_login(user)

    response = client.post(
        reverse("dashboard:messenger_settings"),
        {
            "_form": "ai_settings",
            "is_ai_enabled": "on",
            "instructions": "Shared website and Messenger instructions.",
            "fallback_message": "Shared fallback.",
        },
    )

    assert response.status_code == 302
    settings = ClinicAISettings.objects.get(clinic=clinic)
    assert settings.is_ai_enabled is True
    assert settings.instructions == "Shared website and Messenger instructions."
    assert settings.fallback_message == "Shared fallback."


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
def test_widget_settings_rejects_invalid_accent_color(clinic_setup):
    from clinics.forms import WidgetSettingsForm

    clinic, service, owner = clinic_setup
    form = WidgetSettingsForm(
        data={
            "widget_accent_color": '";alert(1)//',
            "widget_welcome_message": "Welcome",
            "widget_behavior_instructions": "Guide booking",
            "show_reason_field": "on",
        },
        instance=clinic,
    )

    assert not form.is_valid()
    assert "widget_accent_color" in form.errors
