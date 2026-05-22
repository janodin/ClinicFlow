import pytest
from django.db import IntegrityError
from accounts.models import User
from clinics.models import Clinic, ClinicGroup
from clinics.models import ClinicFAQ
from messenger.faq_matcher import match_faq
from messenger.models import MessengerConnection, MessengerSession


@pytest.mark.django_db
def test_match_faq_by_keyword():
    user = User.objects.create_user(username="owner_faq", email="owner_faq@test.com", password="pass")
    group = ClinicGroup.objects.create(name="GroupFAQ", owner=user)
    clinic = Clinic.objects.create(group=group, name="ClinicFAQ")
    faq = ClinicFAQ.objects.create(clinic=clinic, question="What are your hours?", answer="8am to 5pm")
    result = match_faq(clinic, "What are your hours")
    assert result == faq


@pytest.mark.django_db
def test_match_faq_no_match():
    user = User.objects.create_user(username="owner_faq2", email="owner_faq2@test.com", password="pass")
    group = ClinicGroup.objects.create(name="GroupFAQ2", owner=user)
    clinic = Clinic.objects.create(group=group, name="ClinicFAQ2")
    result = match_faq(clinic, "random unrelated text")
    assert result is None


@pytest.mark.django_db
def test_messenger_connection_one_per_clinic():
    user = User.objects.create_user(username="owner1", email="owner@test.com", password="pass")
    group = ClinicGroup.objects.create(name="Group", owner=user)
    clinic = Clinic.objects.create(group=group, name="Clinic")
    MessengerConnection.objects.create(clinic=clinic, page_id="123", page_access_token="abc")
    with pytest.raises(IntegrityError):
        MessengerConnection.objects.create(clinic=clinic, page_id="456", page_access_token="def")


@pytest.mark.django_db
def test_messenger_session_unique_per_psid_and_connection():
    user = User.objects.create_user(username="owner2", email="owner@test.com", password="pass")
    group = ClinicGroup.objects.create(name="Group", owner=user)
    clinic = Clinic.objects.create(group=group, name="Clinic")
    conn = MessengerConnection.objects.create(clinic=clinic, page_id="123", page_access_token="abc")
    MessengerSession.objects.create(connection=conn, psid="PSID1")
    with pytest.raises(IntegrityError):
        MessengerSession.objects.create(connection=conn, psid="PSID1")


@pytest.mark.django_db
def test_messenger_session_defaults():
    user = User.objects.create_user(username="owner3", email="owner@test.com", password="pass")
    group = ClinicGroup.objects.create(name="Group", owner=user)
    clinic = Clinic.objects.create(group=group, name="Clinic")
    conn = MessengerConnection.objects.create(clinic=clinic, page_id="123", page_access_token="abc")
    session = MessengerSession.objects.create(connection=conn, psid="PSID1")
    assert session.state == MessengerSession.STATE_GREETING
    assert session.data == {}


@pytest.mark.django_db
def test_messenger_session_reset():
    user = User.objects.create_user(username="owner3", email="owner3@test.com", password="pass")
    group = ClinicGroup.objects.create(name="Group3", owner=user)
    clinic = Clinic.objects.create(group=group, name="Clinic3")
    conn = MessengerConnection.objects.create(clinic=clinic, page_id="789", page_access_token="xyz")
    session = MessengerSession.objects.create(connection=conn, psid="PSID3", state=MessengerSession.STATE_SELECT_SERVICE, data={"service_id": 1})
    session.reset()
    assert session.state == MessengerSession.STATE_GREETING
    assert session.data == {}


import hmac
import hashlib
from unittest.mock import patch
from messenger.messenger_api import send_messages, verify_signature


class TestVerifySignature:
    def test_valid_signature(self):
        secret = "mysecret"
        payload = b'{"test":"data"}'
        expected = "sha256=" + hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
        assert verify_signature(payload, expected, secret) is True

    def test_invalid_signature(self):
        assert verify_signature(b'{}', "sha256=bad", "secret") is False

    def test_missing_prefix(self):
        assert verify_signature(b'{}', "bad", "secret") is False


class TestSendMessages:
    @pytest.mark.django_db
    @patch("messenger.messenger_api.requests.post")
    def test_send_text_message(self, mock_post):
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {"recipient_id": "123"}
        from accounts.models import User
        from clinics.models import Clinic, ClinicGroup
        from messenger.models import MessengerConnection
        user = User.objects.create_user(username="owner_api", email="owner_api@test.com", password="pass")
        group = ClinicGroup.objects.create(name="GroupAPI", owner=user)
        clinic = Clinic.objects.create(group=group, name="ClinicAPI")
        conn = MessengerConnection.objects.create(clinic=clinic, page_id="PAGE1", page_access_token="TOKEN")
        send_messages(conn, "PSID1", [{"type": "text", "text": "Hello"}])
        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        assert kwargs["json"]["message"]["text"] == "Hello"


from datetime import date, time, timedelta
from django.utils import timezone
from appointments.models import Appointment
from services.models import Service
from messenger.bot_engine import handle_message, _parse_name_phone


@pytest.mark.django_db
def test_handle_message_greeting_to_select_service():
    user = User.objects.create_user(username="owner_be", email="owner_be@test.com", password="pass")
    group = ClinicGroup.objects.create(name="GroupBE", owner=user)
    clinic = Clinic.objects.create(group=group, name="ClinicBE")
    conn = MessengerConnection.objects.create(clinic=clinic, page_id="P", page_access_token="T")
    Service.objects.create(clinic=clinic, name="Cleaning", duration_minutes=30, price=0)
    session = MessengerSession.objects.create(connection=conn, psid="S")
    actions = handle_message(session, "Book an appointment", "")
    assert any("Which service" in a.get("text", "") for a in actions)
    assert session.state == MessengerSession.STATE_SELECT_SERVICE


@pytest.mark.django_db
def test_parse_name_phone_valid():
    assert _parse_name_phone("John Doe\n09171234567") == ("John Doe", "09171234567")


def test_parse_name_phone_invalid():
    assert _parse_name_phone("only name") == (None, None)


import json
from django.urls import reverse
from django.test import Client
from django.test import override_settings


@pytest.mark.django_db
@override_settings(MESSENGER_VERIFY_TOKEN="test_token")
def test_webhook_get_verification():
    client = Client()
    url = reverse("messenger:webhook")
    resp = client.get(url, {
        "hub.mode": "subscribe",
        "hub.verify_token": "test_token",
        "hub.challenge": "CHALLENGE123",
    })
    assert resp.status_code == 200
    assert resp.content.decode() == "CHALLENGE123"


@pytest.mark.django_db
@override_settings(MESSENGER_VERIFY_TOKEN="test_token")
def test_webhook_get_invalid_token():
    client = Client()
    url = reverse("messenger:webhook")
    resp = client.get(url, {
        "hub.mode": "subscribe",
        "hub.verify_token": "bad_token",
        "hub.challenge": "CHALLENGE123",
    })
    assert resp.status_code == 403


@pytest.mark.django_db
@override_settings(MESSENGER_APP_SECRET="test_secret")
def test_webhook_post_valid_message():
    client = Client()
    user = User.objects.create_user(username="owner_wh", email="owner_wh@test.com", password="pass")
    group = ClinicGroup.objects.create(name="GroupWH", owner=user)
    clinic = Clinic.objects.create(group=group, name="ClinicWH")
    conn = MessengerConnection.objects.create(clinic=clinic, page_id="PAGE1", page_access_token="TOKEN")
    Service.objects.create(clinic=clinic, name="Cleaning", duration_minutes=30, price=0)

    payload = json.dumps({
        "object": "page",
        "entry": [{
            "id": "PAGE1",
            "time": 123,
            "messaging": [{
                "sender": {"id": "PSID1"},
                "recipient": {"id": "PAGE1"},
                "message": {"text": "Book an appointment"},
            }]
        }]
    }).encode()
    # Note: Meta webhook payload uses {"message": {"text": "..."}} structure

    import hmac, hashlib
    signature = "sha256=" + hmac.new("test_secret".encode(), payload, hashlib.sha256).hexdigest()

    url = reverse("messenger:webhook")
    resp = client.post(
        url,
        data=payload,
        content_type="application/json",
        HTTP_X_HUB_SIGNATURE_256=signature,
    )
    assert resp.status_code == 200
    session = MessengerSession.objects.get(connection=conn, psid="PSID1")
    assert session.state == MessengerSession.STATE_SELECT_SERVICE


from datetime import timedelta
from django.utils import timezone
from django.core.management import call_command
from unittest.mock import patch
from patients.models import Patient
from scheduling.models import ClinicBusinessHour


def _create_messenger_clinic(username="owner_ai", page_id="PAGEAI"):
    user = User.objects.create_user(username=username, email=f"{username}@test.com", password="pass")
    group = ClinicGroup.objects.create(name=f"Group {username}", owner=user)
    clinic = Clinic.objects.create(
        group=group,
        name=f"Clinic {username}",
        slug=f"clinic-{username}",
        address="123 Main St",
        phone="09171234567",
        email=f"{username}@clinic.test",
        timezone="Asia/Manila",
        booking_approval_mode=Clinic.APPROVAL_AUTO,
    )
    connection = MessengerConnection.objects.create(
        clinic=clinic,
        page_id=page_id,
        page_access_token=f"TOKEN-{page_id}",
    )
    return clinic, connection


@pytest.mark.django_db
def test_messenger_ai_settings_defaults_and_unique_connection():
    from messenger.models import MessengerAISettings

    clinic, connection = _create_messenger_clinic("owner_ai_settings", "PAGEAI1")

    settings = MessengerAISettings.objects.create(connection=connection)

    assert settings.connection == connection
    assert settings.is_ai_enabled is True
    assert settings.instructions == ""
    assert settings.fallback_message == ""
    assert str(settings) == f"MessengerAISettings({clinic.name})"

    with pytest.raises(IntegrityError):
        MessengerAISettings.objects.create(connection=connection)


@pytest.mark.django_db
def test_build_ai_context_returns_only_page_clinic_data():
    from messenger.ai_tools import build_ai_context
    from messenger.models import MessengerAISettings

    clinic, connection = _create_messenger_clinic("owner_ai_context", "PAGEAI2")
    other_clinic, _ = _create_messenger_clinic("owner_ai_other", "PAGEOTHER")
    Service.objects.create(
        clinic=clinic,
        name="Dental Cleaning",
        description="Routine cleaning",
        duration_minutes=30,
        price="1000.00",
        display_price=True,
    )
    Service.objects.create(clinic=other_clinic, name="Other Service", duration_minutes=30, price=0)
    ClinicFAQ.objects.create(clinic=clinic, question="Where are you located?", answer="123 Main St")
    ClinicFAQ.objects.create(clinic=other_clinic, question="Other FAQ", answer="Other answer")
    MessengerAISettings.objects.create(connection=connection, instructions="Use a friendly clinic tone.")

    result = build_ai_context("PAGEAI2")

    assert result["found"] is True
    assert result["clinic"]["id"] == clinic.id
    assert result["clinic"]["name"] == clinic.name
    assert result["clinic"]["address"] == "123 Main St"
    assert result["page_token"] == "TOKEN-PAGEAI2"
    assert result["ai"]["is_ai_enabled"] is True
    assert result["ai"]["instructions"] == "Use a friendly clinic tone."
    assert [service["name"] for service in result["services"]] == ["Dental Cleaning"]
    assert [faq["question"] for faq in result["faqs"]] == ["Where are you located?"]


@pytest.mark.django_db
def test_match_services_returns_active_matches_for_page_clinic_only():
    from messenger.ai_tools import match_services

    clinic, _ = _create_messenger_clinic("owner_ai_services", "PAGEAI3")
    other_clinic, _ = _create_messenger_clinic("owner_ai_services_other", "PAGEOTHER3")
    Service.objects.create(clinic=clinic, name="Dental Cleaning", description="Teeth cleaning", duration_minutes=30, price="1000.00")
    Service.objects.create(clinic=clinic, name="Consultation", description="General consult", duration_minutes=30, price="500.00")
    Service.objects.create(clinic=other_clinic, name="Cleaning Other", duration_minutes=30, price=0)

    result = match_services("PAGEAI3", "cleaning")

    assert result["found"] is True
    assert [match["name"] for match in result["matches"]] == ["Dental Cleaning"]


@pytest.mark.django_db
def test_check_availability_returns_requested_slot_and_alternatives():
    from messenger.ai_tools import check_availability

    clinic, _ = _create_messenger_clinic("owner_ai_availability", "PAGEAI4")
    service = Service.objects.create(clinic=clinic, name="Consultation", duration_minutes=30, price=0)
    target_date = timezone.localdate() + timedelta(days=1)
    ClinicBusinessHour.objects.create(clinic=clinic, weekday=target_date.weekday(), open_time=time(9), close_time=time(11))

    open_result = check_availability("PAGEAI4", service.id, preferred_date=target_date.isoformat())
    requested_slot = open_result["alternatives"][0]["starts_at"]

    available_result = check_availability("PAGEAI4", service.id, preferred_starts_at=requested_slot)
    assert available_result["available"] is True
    assert available_result["selected_slot"]["starts_at"] == requested_slot

    patient = Patient.objects.create(clinic=clinic, full_name="Existing Patient", phone="09999999999")
    Appointment.objects.create(
        clinic=clinic,
        patient=patient,
        service=service,
        starts_at=timezone.datetime.fromisoformat(requested_slot),
        ends_at=timezone.datetime.fromisoformat(requested_slot) + timedelta(minutes=30),
        status=Appointment.STATUS_CONFIRMED,
    )

    unavailable_result = check_availability("PAGEAI4", service.id, preferred_starts_at=requested_slot)
    assert unavailable_result["available"] is False
    assert unavailable_result["alternatives"]
    assert requested_slot not in [slot["starts_at"] for slot in unavailable_result["alternatives"]]


@pytest.mark.django_db
def test_book_confirmed_appointment_requires_confirmation_and_creates_booking():
    from messenger.ai_tools import book_confirmed_appointment, check_availability

    clinic, _ = _create_messenger_clinic("owner_ai_booking", "PAGEAI5")
    service = Service.objects.create(clinic=clinic, name="Consultation", duration_minutes=30, price=0)
    target_date = timezone.localdate() + timedelta(days=1)
    ClinicBusinessHour.objects.create(clinic=clinic, weekday=target_date.weekday(), open_time=time(9), close_time=time(10))
    slot = check_availability("PAGEAI5", service.id, preferred_date=target_date.isoformat())["alternatives"][0]

    blocked = book_confirmed_appointment(
        "PAGEAI5",
        service.id,
        slot["starts_at"],
        "Maria Santos",
        "09175551234",
        confirmed=False,
    )
    assert blocked["created"] is False
    assert blocked["error"] == "Appointment creation requires explicit user confirmation."

    result = book_confirmed_appointment(
        "PAGEAI5",
        service.id,
        slot["starts_at"],
        "Maria Santos",
        "09175551234",
        confirmed=True,
    )
    assert result["created"] is True
    assert result["appointment"]["service"] == "Consultation"
    assert result["appointment"]["status"] == Appointment.STATUS_CONFIRMED
    appointment = Appointment.objects.get(reference_code=result["appointment"]["reference_code"])
    assert appointment.source == Appointment.SOURCE_MESSENGER
    assert appointment.patient.phone == "09175551234"


@pytest.mark.django_db
def test_book_confirmed_appointment_rejects_truthy_string_confirmation():
    from messenger.ai_tools import book_confirmed_appointment, check_availability

    clinic, _ = _create_messenger_clinic("owner_ai_string_confirm", "PAGEAI10")
    service = Service.objects.create(clinic=clinic, name="Consultation", duration_minutes=30, price=0)
    target_date = timezone.localdate() + timedelta(days=1)
    ClinicBusinessHour.objects.create(clinic=clinic, weekday=target_date.weekday(), open_time=time(9), close_time=time(10))
    slot = check_availability("PAGEAI10", service.id, preferred_date=target_date.isoformat())["alternatives"][0]

    result = book_confirmed_appointment(
        "PAGEAI10",
        service.id,
        slot["starts_at"],
        "Maria Santos",
        "09175551234",
        confirmed="false",
    )

    assert result["created"] is False
    assert Appointment.objects.filter(clinic=clinic).count() == 0


@pytest.mark.django_db
@override_settings(N8N_WEBHOOK_SECRET="secret123")
def test_ai_book_endpoint_accepts_string_true_confirmation():
    """n8n sends confirmed as JSON string 'true'; Django view must normalize it."""
    from django.test import Client
    from django.urls import reverse
    import json
    from appointments.models import Appointment
    from scheduling.models import ClinicBusinessHour

    clinic, _ = _create_messenger_clinic("owner_ai_string_true", "PAGEAI12")
    service = Service.objects.create(clinic=clinic, name="Consultation", duration_minutes=30, price=0)
    target_date = timezone.localdate() + timedelta(days=1)
    ClinicBusinessHour.objects.create(clinic=clinic, weekday=target_date.weekday(), open_time=time(9), close_time=time(10))

    from messenger.ai_tools import check_availability
    slot = check_availability("PAGEAI12", service.id, preferred_date=target_date.isoformat())["alternatives"][0]

    client = Client()
    response = client.post(
        reverse("messenger:ai_book"),
        data=json.dumps({
            "page_id": "PAGEAI12",
            "service_id": service.id,
            "starts_at": slot["starts_at"],
            "full_name": "Jana Patu",
            "phone": "09358438344",
            "confirmed": "true",  # n8n sends string, not boolean
        }),
        content_type="application/json",
        HTTP_X_N8N_WEBHOOK_SECRET="secret123",
    )

    assert response.status_code == 200
    result = response.json()
    assert result["created"] is True, f"Expected booking to succeed but got: {result}"
    assert Appointment.objects.filter(clinic=clinic, source=Appointment.SOURCE_MESSENGER).count() == 1


@pytest.mark.django_db
def test_ai_tools_return_disabled_when_ai_settings_disabled():
    from messenger.ai_tools import book_confirmed_appointment, build_ai_context, check_availability, match_services
    from messenger.models import MessengerAISettings

    clinic, connection = _create_messenger_clinic("owner_ai_disabled", "PAGEAI11")
    service = Service.objects.create(clinic=clinic, name="Consultation", duration_minutes=30, price=0)
    MessengerAISettings.objects.create(
        connection=connection,
        is_ai_enabled=False,
        fallback_message="Please call the clinic.",
    )

    context = build_ai_context("PAGEAI11")
    services = match_services("PAGEAI11", "consultation")
    availability = check_availability("PAGEAI11", service.id, preferred_date=(timezone.localdate() + timedelta(days=1)).isoformat())
    booking = book_confirmed_appointment("PAGEAI11", service.id, timezone.now().isoformat(), "Name", "0917", confirmed=True)

    assert context["ai"]["is_ai_enabled"] is False
    assert services["disabled"] is True
    assert availability["disabled"] is True
    assert booking["created"] is False
    assert booking["disabled"] is True
    assert booking["fallback_message"] == "Please call the clinic."


@pytest.mark.django_db
def test_check_availability_returns_error_for_invalid_datetime_input():
    from messenger.ai_tools import check_availability

    clinic, _ = _create_messenger_clinic("owner_ai_bad_date", "PAGEAI12")
    service = Service.objects.create(clinic=clinic, name="Consultation", duration_minutes=30, price=0)

    result = check_availability("PAGEAI12", service.id, preferred_starts_at="not-a-date")

    assert result["available"] is False
    assert result["error"] == "Invalid date or time."


@pytest.mark.django_db
def test_ai_booking_reuses_patient_phone_and_prevents_double_booking():
    from messenger.ai_tools import book_confirmed_appointment, check_availability

    clinic, _ = _create_messenger_clinic("owner_ai_patient_match", "PAGEAI13")
    service = Service.objects.create(clinic=clinic, name="Consultation", duration_minutes=30, price=0)
    patient = Patient.objects.create(clinic=clinic, full_name="Existing Name", phone="09175550000")
    target_date = timezone.localdate() + timedelta(days=1)
    ClinicBusinessHour.objects.create(clinic=clinic, weekday=target_date.weekday(), open_time=time(9), close_time=time(10))
    slot = check_availability("PAGEAI13", service.id, preferred_date=target_date.isoformat())["alternatives"][0]

    first = book_confirmed_appointment(
        "PAGEAI13",
        service.id,
        slot["starts_at"],
        "Updated Name",
        "09175550000",
        confirmed=True,
    )
    second = book_confirmed_appointment(
        "PAGEAI13",
        service.id,
        slot["starts_at"],
        "Another Name",
        "09175551111",
        confirmed=True,
    )

    assert first["created"] is True
    assert Appointment.objects.get(reference_code=first["appointment"]["reference_code"]).patient == patient
    assert second["created"] is False
    assert second["error"] == "That slot is no longer available. Please choose another time."


@pytest.mark.django_db
@override_settings(N8N_WEBHOOK_SECRET="secret123")
def test_ai_context_endpoint_requires_secret_and_returns_context():
    clinic, _ = _create_messenger_clinic("owner_ai_endpoint", "PAGEAI6")
    client = Client()
    url = reverse("messenger:ai_context")

    unauthorized = client.post(url, data=json.dumps({"page_id": "PAGEAI6"}), content_type="application/json")
    assert unauthorized.status_code == 401

    response = client.post(
        url,
        data=json.dumps({"page_id": "PAGEAI6"}),
        content_type="application/json",
        HTTP_X_N8N_WEBHOOK_SECRET="secret123",
    )
    assert response.status_code == 200
    assert response.json()["clinic"]["id"] == clinic.id


@pytest.mark.django_db
@override_settings(N8N_WEBHOOK_SECRET="")
def test_ai_context_endpoint_fails_closed_when_secret_unset():
    _create_messenger_clinic("owner_ai_no_secret", "PAGEAI14")
    client = Client()

    response = client.post(
        reverse("messenger:ai_context"),
        data=json.dumps({"page_id": "PAGEAI14"}),
        content_type="application/json",
    )

    assert response.status_code == 401


@pytest.mark.django_db
@override_settings(N8N_WEBHOOK_SECRET="secret123")
def test_ai_services_endpoint_returns_matches():
    clinic, _ = _create_messenger_clinic("owner_ai_services_endpoint", "PAGEAI8")
    Service.objects.create(clinic=clinic, name="Dental Cleaning", duration_minutes=30, price=0)
    client = Client()

    response = client.post(
        reverse("messenger:ai_services"),
        data=json.dumps({"page_id": "PAGEAI8", "query": "cleaning"}),
        content_type="application/json",
        HTTP_X_N8N_WEBHOOK_SECRET="secret123",
    )

    assert response.status_code == 200
    assert [item["name"] for item in response.json()["matches"]] == ["Dental Cleaning"]


@pytest.mark.django_db
@override_settings(N8N_WEBHOOK_SECRET="secret123")
def test_ai_services_endpoint_returns_400_for_invalid_query_type():
    _create_messenger_clinic("owner_ai_bad_query", "PAGEAI15")
    client = Client()

    response = client.post(
        reverse("messenger:ai_services"),
        data=json.dumps({"page_id": "PAGEAI15", "query": {"bad": "type"}}),
        content_type="application/json",
        HTTP_X_N8N_WEBHOOK_SECRET="secret123",
    )

    assert response.status_code == 400
    assert response.json()["error"] == "Invalid request data"


@pytest.mark.django_db
@override_settings(N8N_WEBHOOK_SECRET="secret123")
def test_ai_availability_endpoint_returns_alternatives():
    clinic, _ = _create_messenger_clinic("owner_ai_availability_endpoint", "PAGEAI9")
    service = Service.objects.create(clinic=clinic, name="Consultation", duration_minutes=30, price=0)
    target_date = timezone.localdate() + timedelta(days=1)
    ClinicBusinessHour.objects.create(clinic=clinic, weekday=target_date.weekday(), open_time=time(9), close_time=time(10))
    client = Client()

    response = client.post(
        reverse("messenger:ai_availability"),
        data=json.dumps({"page_id": "PAGEAI9", "service_id": service.id, "preferred_date": target_date.isoformat()}),
        content_type="application/json",
        HTTP_X_N8N_WEBHOOK_SECRET="secret123",
    )

    assert response.status_code == 200
    assert response.json()["found"] is True
    assert response.json()["alternatives"]


@pytest.mark.django_db
@override_settings(N8N_WEBHOOK_SECRET="secret123")
def test_ai_availability_endpoint_returns_400_for_invalid_service_id_type():
    _create_messenger_clinic("owner_ai_bad_service", "PAGEAI16")
    client = Client()

    response = client.post(
        reverse("messenger:ai_availability"),
        data=json.dumps({"page_id": "PAGEAI16", "service_id": {"bad": "type"}}),
        content_type="application/json",
        HTTP_X_N8N_WEBHOOK_SECRET="secret123",
    )

    assert response.status_code == 400
    assert response.json()["error"] == "Invalid request data"


@pytest.mark.django_db
@override_settings(N8N_WEBHOOK_SECRET="secret123")
def test_ai_booking_endpoint_creates_only_after_confirmation():
    clinic, _ = _create_messenger_clinic("owner_ai_book_endpoint", "PAGEAI7")
    service = Service.objects.create(clinic=clinic, name="Consultation", duration_minutes=30, price=0)
    target_date = timezone.localdate() + timedelta(days=1)
    ClinicBusinessHour.objects.create(clinic=clinic, weekday=target_date.weekday(), open_time=time(9), close_time=time(10))
    from messenger.ai_tools import check_availability
    slot = check_availability("PAGEAI7", service.id, preferred_date=target_date.isoformat())["alternatives"][0]
    client = Client()

    response = client.post(
        reverse("messenger:ai_book"),
        data=json.dumps({
            "page_id": "PAGEAI7",
            "service_id": service.id,
            "starts_at": slot["starts_at"],
            "full_name": "Juan Dela Cruz",
            "phone": "09170000000",
            "confirmed": True,
        }),
        content_type="application/json",
        HTTP_X_N8N_WEBHOOK_SECRET="secret123",
    )

    assert response.status_code == 200
    assert response.json()["created"] is True
    assert Appointment.objects.filter(clinic=clinic, source=Appointment.SOURCE_MESSENGER).count() == 1


@pytest.mark.django_db
@patch("messenger.management.commands.send_messenger_reminders.send_messages")
def test_reminder_command_sends_message(mock_send):
    user = User.objects.create_user(username="owner_rem", email="owner_rem@test.com", password="pass")
    group = ClinicGroup.objects.create(name="GroupREM", owner=user)
    clinic = Clinic.objects.create(group=group, name="ClinicREM", timezone="Asia/Manila")
    conn = MessengerConnection.objects.create(clinic=clinic, page_id="P", page_access_token="T")
    service = Service.objects.create(clinic=clinic, name="Cleaning", duration_minutes=30, price=0)
    patient = Patient.objects.create(clinic=clinic, full_name="John", phone="09171234567")
    appt = Appointment.objects.create(
        clinic=clinic,
        patient=patient,
        service=service,
        starts_at=timezone.now() + timedelta(hours=24),
        ends_at=timezone.now() + timedelta(hours=24, minutes=30),
        source=Appointment.SOURCE_MESSENGER,
        status=Appointment.STATUS_CONFIRMED,
    )
    MessengerSession.objects.create(connection=conn, psid="PSID1")
    call_command("send_messenger_reminders")
    mock_send.assert_called_once()


@pytest.mark.django_db
@override_settings(MESSENGER_APP_SECRET="test_secret")
def test_full_booking_flow_via_webhook():
    client = Client()
    user = User.objects.create_user(username="owner_flow", email="owner_flow@test.com", password="pass")
    group = ClinicGroup.objects.create(name="GroupFlow", owner=user)
    clinic = Clinic.objects.create(group=group, name="ClinicFlow", timezone="Asia/Manila", booking_approval_mode=Clinic.APPROVAL_AUTO)
    conn = MessengerConnection.objects.create(clinic=clinic, page_id="PAGE1", page_access_token="TOKEN")
    service = Service.objects.create(clinic=clinic, name="Cleaning", duration_minutes=30, price=0)

    def send_message(text="", payload=""):
        msg = {"message": {"text": text}}
        if payload:
            msg = {"postback": {"payload": payload}}
        body = json.dumps({
            "object": "page",
            "entry": [{
                "id": "PAGE1",
                "time": 123,
                "messaging": [{
                    "sender": {"id": "PSID1"},
                    "recipient": {"id": "PAGE1"},
                    **msg,
                }]
            }]
        }).encode()
        sig = "sha256=" + hmac.new("test_secret".encode(), body, hashlib.sha256).hexdigest()
        return client.post(reverse("messenger:webhook"), data=body, content_type="application/json", HTTP_X_HUB_SIGNATURE_256=sig)

    with patch("messenger.views._send_facebook_reply") as mock_send:
        # Greeting -> select service
        resp = send_message(text="Book an appointment")
        assert resp.status_code == 200
        session = MessengerSession.objects.get(connection=conn, psid="PSID1")
        assert session.state == MessengerSession.STATE_SELECT_SERVICE

        # Select service -> select date
        resp = send_message(payload=str(service.id))
        assert resp.status_code == 200
        session.refresh_from_db()
        assert session.state == MessengerSession.STATE_SELECT_DATE

        # Select date -> select time
        resp = send_message(payload=(timezone.localdate() + timedelta(days=1)).isoformat())
        assert resp.status_code == 200
        session.refresh_from_db()
        assert session.state == MessengerSession.STATE_SELECT_TIME
