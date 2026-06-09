import pytest
from django.db import IntegrityError
from accounts.models import User
from clinics.models import Clinic, ClinicGroup
from clinics.models import ClinicFAQ
from messenger.faq_matcher import match_faq
from messenger.models import MessengerConnection, MessengerProcessedMessage, MessengerSession


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
def test_messenger_connection_page_id_unique_when_configured():
    user = User.objects.create_user(username="owner_page_unique", email="owner_page_unique@test.com", password="pass")
    group = ClinicGroup.objects.create(name="GroupPageUnique", owner=user)
    clinic_a = Clinic.objects.create(group=group, name="ClinicPageUniqueA", slug="clinic-page-unique-a")
    clinic_b = Clinic.objects.create(group=group, name="ClinicPageUniqueB", slug="clinic-page-unique-b")
    MessengerConnection.objects.create(clinic=clinic_a, page_id="PAGE-UNIQUE", page_access_token="abc")

    with pytest.raises(IntegrityError):
        MessengerConnection.objects.create(clinic=clinic_b, page_id="PAGE-UNIQUE", page_access_token="def")


@pytest.mark.django_db
def test_messenger_connection_admin_form_does_not_render_saved_secrets():
    from messenger.admin import MessengerConnectionAdminForm

    user = User.objects.create_user(username="owner_admin_secret", email="owner_admin_secret@test.com", password="pass")
    group = ClinicGroup.objects.create(name="GroupAdminSecret", owner=user)
    clinic = Clinic.objects.create(group=group, name="ClinicAdminSecret")
    connection = MessengerConnection.objects.create(
        clinic=clinic,
        app_secret="ADMIN-APP-SECRET",
        page_id="PAGE-ADMIN-SECRET",
        page_access_token="ADMIN-PAGE-TOKEN",
    )

    html = MessengerConnectionAdminForm(instance=connection).as_p()

    assert "ADMIN-APP-SECRET" not in html
    assert "ADMIN-PAGE-TOKEN" not in html


def test_default_ai_prompt_hides_faq_source_and_uses_suggestion_metadata():
    from messenger.defaults import DEFAULT_MESSENGER_AI_PROMPT

    assert "Do not say based on the FAQ" in DEFAULT_MESSENGER_AI_PROMPT
    assert "Answer FAQ-backed information as normal clinic information." in DEFAULT_MESSENGER_AI_PROMPT
    assert "Use check_availability suggestion_type metadata" in DEFAULT_MESSENGER_AI_PROMPT
    assert "nearest_time means the requested time is unavailable" in DEFAULT_MESSENGER_AI_PROMPT
    assert "next_available_date means the requested date has no slots" in DEFAULT_MESSENGER_AI_PROMPT
    assert "For booking, collect service, date/time, full name, phone, and email" in DEFAULT_MESSENGER_AI_PROMPT
    assert "Before booking, summarize service, local date/time, full name, phone, and email" in DEFAULT_MESSENGER_AI_PROMPT


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
import requests
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

    def test_missing_payload(self):
        assert verify_signature(b"", "sha256=bad", "secret") is False

    def test_missing_signature(self):
        assert verify_signature(b"{}", "", "secret") is False

    def test_missing_secret(self):
        assert verify_signature(b"{}", "sha256=bad", "") is False


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
        assert kwargs["json"]["messaging_type"] == "RESPONSE"
        assert kwargs["json"]["message"]["text"] == "Hello"

    @pytest.mark.django_db
    @patch("messenger.messenger_api.requests.post")
    def test_send_quick_replies_uses_meta_safe_payload(self, mock_post):
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {"recipient_id": "123"}
        user = User.objects.create_user(username="owner_api_qr", email="owner_api_qr@test.com", password="pass")
        group = ClinicGroup.objects.create(name="GroupAPIQR", owner=user)
        clinic = Clinic.objects.create(group=group, name="ClinicAPIQR")
        conn = MessengerConnection.objects.create(clinic=clinic, page_id="PAGE-API-QR", page_access_token="TOKEN")

        send_messages(conn, "PSID1", [{
            "type": "quick_replies",
            "text": "Choose a service",
            "options": [{"title": "Very long consultation service", "payload": 123}]
            + [{"title": f"Option {i}", "payload": i} for i in range(2, 15)],
        }])

        body = mock_post.call_args.kwargs["json"]
        assert body["messaging_type"] == "RESPONSE"
        assert body["recipient"] == {"id": "PSID1"}
        assert body["message"]["text"] == "Choose a service"
        assert len(body["message"]["quick_replies"]) == 13
        assert body["message"]["quick_replies"][0] == {
            "content_type": "text",
            "title": "Very long consultati",
            "payload": "123",
        }

    @pytest.mark.django_db
    @patch("messenger.messenger_api.requests.post")
    def test_send_empty_quick_replies_as_text_only(self, mock_post):
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {"recipient_id": "123"}
        user = User.objects.create_user(username="owner_api_empty_qr", email="owner_api_empty_qr@test.com", password="pass")
        group = ClinicGroup.objects.create(name="GroupAPIEmptyQR", owner=user)
        clinic = Clinic.objects.create(group=group, name="ClinicAPIEmptyQR")
        conn = MessengerConnection.objects.create(clinic=clinic, page_id="PAGE-API-EMPTY-QR", page_access_token="TOKEN")

        send_messages(conn, "PSID1", [{"type": "quick_replies", "text": "Choose a service", "options": []}])

        body = mock_post.call_args.kwargs["json"]
        assert body["message"] == {"text": "Choose a service"}

    @pytest.mark.django_db
    @patch("messenger.messenger_api.requests.post")
    def test_send_messages_does_not_log_page_access_token_on_failure(self, mock_post, caplog):
        user = User.objects.create_user(username="owner_api_log", email="owner_api_log@test.com", password="pass")
        group = ClinicGroup.objects.create(name="GroupAPILog", owner=user)
        clinic = Clinic.objects.create(group=group, name="ClinicAPILog")
        conn = MessengerConnection.objects.create(clinic=clinic, page_id="PAGE-LOG", page_access_token="SECRET-TOKEN")
        mock_post.return_value.raise_for_status.side_effect = requests.HTTPError(
            "500 Server Error for url: https://graph.facebook.com/v18.0/me/messages?access_token=SECRET-TOKEN"
        )

        send_messages(conn, "PSID1", [{"type": "text", "text": "Hello"}])

        assert "SECRET-TOKEN" not in caplog.text


@patch("messenger.views.requests.post")
def test_direct_facebook_sender_omits_empty_quick_replies(mock_post):
    from messenger.views import _send_facebook_reply

    _send_facebook_reply("TOKEN", "PSID1", [{"type": "quick_replies", "text": "Choose a service", "options": []}])

    body = mock_post.call_args.kwargs["json"]
    assert body["message"] == {"text": "Choose a service"}


from datetime import date, time, timedelta
from django.utils import timezone
from appointments.models import Appointment
from services.models import Service
from messenger import bot_engine
from messenger.bot_engine import handle_message, _parse_name_phone


def _assert_next_step_quick_replies(actions):
    quick_reply = next(
        action
        for action in actions
        if action.get("type") == "quick_replies" and action.get("text") == "What would you like to do next?"
    )
    assert [option["payload"] for option in quick_reply["options"]] == [
        "start_booking",
        "view_faqs",
        "clinic_info",
    ]


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
def test_messenger_quick_reply_date_options_respect_meta_limit():
    user = User.objects.create_user(username="owner_be_qr_limit", email="owner_be_qr_limit@test.com", password="pass")
    group = ClinicGroup.objects.create(name="GroupBEQRLimit", owner=user)
    clinic = Clinic.objects.create(group=group, name="ClinicBEQRLimit")
    conn = MessengerConnection.objects.create(clinic=clinic, page_id="P-QR-LIMIT", page_access_token="T")
    service = Service.objects.create(clinic=clinic, name="Cleaning", duration_minutes=30, price=0)
    session = MessengerSession.objects.create(
        connection=conn,
        psid="S-QR-LIMIT",
        state=MessengerSession.STATE_SELECT_DATE,
        data={"service_id": service.id},
    )

    actions = handle_message(session, "not a date", "")

    quick_reply = next(action for action in actions if action.get("type") == "quick_replies")
    assert quick_reply["text"] == "What date works for you?"
    assert len(quick_reply["options"]) == 13


@pytest.mark.django_db
def test_service_quick_reply_titles_are_meta_safe():
    user = User.objects.create_user(username="owner_be_qr_title", email="owner_be_qr_title@test.com", password="pass")
    group = ClinicGroup.objects.create(name="GroupBEQRTitle", owner=user)
    clinic = Clinic.objects.create(group=group, name="ClinicBEQRTitle")
    conn = MessengerConnection.objects.create(clinic=clinic, page_id="P-QR-TITLE", page_access_token="T")
    service = Service.objects.create(clinic=clinic, name="Very long consultation service", duration_minutes=30, price=0)
    session = MessengerSession.objects.create(connection=conn, psid="S-QR-TITLE", state=MessengerSession.STATE_SELECT_SERVICE)

    actions = handle_message(session, "unknown", "")

    quick_reply = next(action for action in actions if action.get("type") == "quick_replies")
    assert quick_reply["options"] == [{"title": "Very long consultati", "payload": str(service.id)}]


@pytest.mark.django_db
def test_faq_quick_reply_payload_returns_selected_answer_from_greeting_state():
    user = User.objects.create_user(username="owner_be_faq_payload", email="owner_be_faq_payload@test.com", password="pass")
    group = ClinicGroup.objects.create(name="GroupBEFAQPayload", owner=user)
    clinic = Clinic.objects.create(group=group, name="ClinicBEFAQPayload")
    conn = MessengerConnection.objects.create(clinic=clinic, page_id="P-FAQ-PAYLOAD", page_access_token="T")
    faq = ClinicFAQ.objects.create(clinic=clinic, question="What are your hours?", answer="8am to 5pm")
    session = MessengerSession.objects.create(connection=conn, psid="S-FAQ-PAYLOAD")

    actions = handle_message(session, "", f"faq:{faq.id}")

    assert actions[0] == {"type": "text", "text": "Q: What are your hours?\nA: 8am to 5pm"}
    _assert_next_step_quick_replies(actions)
    assert session.state == MessengerSession.STATE_GREETING


@pytest.mark.django_db
def test_view_faqs_without_faqs_returns_next_step_quick_replies():
    user = User.objects.create_user(username="owner_be_no_faqs", email="owner_be_no_faqs@test.com", password="pass")
    group = ClinicGroup.objects.create(name="GroupBENoFAQs", owner=user)
    clinic = Clinic.objects.create(group=group, name="ClinicBENoFAQs")
    conn = MessengerConnection.objects.create(clinic=clinic, page_id="P-NO-FAQS", page_access_token="T")
    session = MessengerSession.objects.create(connection=conn, psid="S-NO-FAQS")

    actions = handle_message(session, "", "view_faqs")

    assert actions[0] == {"type": "text", "text": "Here are some frequently asked questions:"}
    assert actions[1] == {"type": "text", "text": "No FAQs available right now."}
    _assert_next_step_quick_replies(actions)
    assert session.state == MessengerSession.STATE_GREETING


@pytest.mark.django_db
def test_clinic_info_returns_next_step_quick_replies():
    user = User.objects.create_user(username="owner_be_info", email="owner_be_info@test.com", password="pass")
    group = ClinicGroup.objects.create(name="GroupBEInfo", owner=user)
    clinic = Clinic.objects.create(
        group=group,
        name="ClinicBEInfo",
        address="123 Main St",
        phone="09171234567",
        email="info@test.com",
        timezone="Asia/Manila",
    )
    conn = MessengerConnection.objects.create(clinic=clinic, page_id="P-INFO", page_access_token="T")
    session = MessengerSession.objects.create(connection=conn, psid="S-INFO")

    actions = handle_message(session, "", "clinic_info")

    assert actions[0]["type"] == "text"
    assert "*ClinicBEInfo*" in actions[0]["text"]
    assert "Address: 123 Main St" in actions[0]["text"]
    _assert_next_step_quick_replies(actions)
    assert session.state == MessengerSession.STATE_GREETING


@pytest.mark.django_db
def test_select_service_without_active_services_returns_next_steps_not_empty_quick_replies():
    user = User.objects.create_user(username="owner_be_no_services", email="owner_be_no_services@test.com", password="pass")
    group = ClinicGroup.objects.create(name="GroupBENoServices", owner=user)
    clinic = Clinic.objects.create(group=group, name="ClinicBENoServices")
    conn = MessengerConnection.objects.create(clinic=clinic, page_id="P-NO-SERVICES", page_access_token="T")
    session = MessengerSession.objects.create(
        connection=conn,
        psid="S-NO-SERVICES",
        state=MessengerSession.STATE_SELECT_SERVICE,
    )

    actions = handle_message(session, "unknown", "")

    assert not [
        action
        for action in actions
        if action.get("type") == "quick_replies" and action.get("options") == []
    ]
    _assert_next_step_quick_replies(actions)
    assert session.state == MessengerSession.STATE_GREETING


@pytest.mark.django_db
def test_date_quick_reply_returns_time_options_without_reusing_date_as_time():
    user = User.objects.create_user(username="owner_be_date_payload", email="owner_be_date_payload@test.com", password="pass")
    group = ClinicGroup.objects.create(name="GroupBEDatePayload", owner=user)
    clinic = Clinic.objects.create(group=group, name="ClinicBEDatePayload", timezone="Asia/Manila")
    conn = MessengerConnection.objects.create(clinic=clinic, page_id="P-DATE-PAYLOAD", page_access_token="T")
    service = Service.objects.create(clinic=clinic, name="Cleaning", duration_minutes=30, price=0)
    target_date = timezone.localdate() + timedelta(days=2)
    ClinicBusinessHour.objects.create(clinic=clinic, weekday=target_date.weekday(), open_time=time(9), close_time=time(10))
    session = MessengerSession.objects.create(
        connection=conn,
        psid="S-DATE-PAYLOAD",
        state=MessengerSession.STATE_SELECT_DATE,
        data={"service_id": service.id},
    )

    actions = handle_message(session, "", target_date.isoformat())

    assert actions[0]["type"] == "quick_replies"
    assert actions[0]["text"] == "Here are the available times:"
    assert session.state == MessengerSession.STATE_SELECT_TIME


@pytest.mark.django_db
def test_select_date_with_no_future_slots_returns_next_steps_and_resets_session():
    user = User.objects.create_user(username="owner_be_no_date_slots", email="owner_be_no_date_slots@test.com", password="pass")
    group = ClinicGroup.objects.create(name="GroupBENoDateSlots", owner=user)
    clinic = Clinic.objects.create(group=group, name="ClinicBENoDateSlots", timezone="Asia/Manila")
    conn = MessengerConnection.objects.create(clinic=clinic, page_id="P-NO-DATE-SLOTS", page_access_token="T")
    service = Service.objects.create(clinic=clinic, name="Cleaning", duration_minutes=30, price=0)
    target_date = timezone.localdate() + timedelta(days=1)
    session = MessengerSession.objects.create(
        connection=conn,
        psid="S-NO-DATE-SLOTS",
        state=MessengerSession.STATE_SELECT_DATE,
        data={"service_id": service.id},
    )

    actions = handle_message(session, "", target_date.isoformat())

    assert actions[0] == {"type": "text", "text": "Sorry, no slots are available in the near future."}
    _assert_next_step_quick_replies(actions)
    session.refresh_from_db()
    assert session.state == MessengerSession.STATE_GREETING
    assert session.data == {}


@pytest.mark.django_db
def test_select_time_with_no_future_slots_returns_next_steps_and_resets_session():
    user = User.objects.create_user(username="owner_be_no_time_slots", email="owner_be_no_time_slots@test.com", password="pass")
    group = ClinicGroup.objects.create(name="GroupBENoTimeSlots", owner=user)
    clinic = Clinic.objects.create(group=group, name="ClinicBENoTimeSlots", timezone="Asia/Manila")
    conn = MessengerConnection.objects.create(clinic=clinic, page_id="P-NO-TIME-SLOTS", page_access_token="T")
    service = Service.objects.create(clinic=clinic, name="Cleaning", duration_minutes=30, price=0)
    target_date = timezone.localdate() + timedelta(days=1)
    session = MessengerSession.objects.create(
        connection=conn,
        psid="S-NO-TIME-SLOTS",
        state=MessengerSession.STATE_SELECT_TIME,
        data={"service_id": service.id, "date": target_date.isoformat()},
    )

    actions = handle_message(session, "", "")

    assert actions[0] == {"type": "text", "text": "Sorry, no slots are available in the near future."}
    _assert_next_step_quick_replies(actions)
    session.refresh_from_db()
    assert session.state == MessengerSession.STATE_GREETING
    assert session.data == {}


@pytest.mark.django_db
def test_confirmed_booking_returns_booked_text_and_next_step_quick_replies():
    from scheduling.utils import generate_slots

    user = User.objects.create_user(username="owner_be_booked_next", email="owner_be_booked_next@test.com", password="pass")
    group = ClinicGroup.objects.create(name="GroupBEBookedNext", owner=user)
    clinic = Clinic.objects.create(
        group=group,
        name="ClinicBEBookedNext",
        timezone="Asia/Manila",
        booking_approval_mode=Clinic.APPROVAL_AUTO,
    )
    conn = MessengerConnection.objects.create(clinic=clinic, page_id="P-BOOKED-NEXT", page_access_token="T")
    service = Service.objects.create(clinic=clinic, name="Cleaning", duration_minutes=30, price=0)
    target_date = timezone.localdate() + timedelta(days=1)
    ClinicBusinessHour.objects.create(clinic=clinic, weekday=target_date.weekday(), open_time=time(9), close_time=time(10))
    slot = generate_slots(clinic, service, target_date)[0]
    session = MessengerSession.objects.create(
        connection=conn,
        psid="S-BOOKED-NEXT",
        state=MessengerSession.STATE_CONFIRM,
        data={
            "service_id": service.id,
            "date": target_date.isoformat(),
            "starts_at": slot["starts_at"].isoformat(),
            "full_name": "Maria Santos",
            "phone": "09175551234",
            "email": "maria@example.com",
        },
    )

    actions = handle_message(session, "", "confirm")

    assert actions[0]["type"] == "text"
    assert "Your appointment is confirmed!" in actions[0]["text"]
    assert "Reply CANCEL to cancel this appointment." in actions[0]["text"]
    _assert_next_step_quick_replies(actions)
    session.refresh_from_db()
    assert session.state == MessengerSession.STATE_GREETING
    assert session.data == {}


@pytest.mark.django_db
def test_confirm_slot_conflict_without_alternatives_returns_next_steps_and_resets_session():
    user = User.objects.create_user(username="owner_be_confirm_conflict", email="owner_be_confirm_conflict@test.com", password="pass")
    group = ClinicGroup.objects.create(name="GroupBEConfirmConflict", owner=user)
    clinic = Clinic.objects.create(
        group=group,
        name="ClinicBEConfirmConflict",
        timezone="Asia/Manila",
        booking_approval_mode=Clinic.APPROVAL_AUTO,
    )
    conn = MessengerConnection.objects.create(clinic=clinic, page_id="P-CONFIRM-CONFLICT", page_access_token="T")
    service = Service.objects.create(clinic=clinic, name="Cleaning", duration_minutes=30, price=0)
    target_date = timezone.localdate() + timedelta(days=1)
    starts_at = timezone.datetime.combine(target_date, time(9)).isoformat()
    session = MessengerSession.objects.create(
        connection=conn,
        psid="S-CONFIRM-CONFLICT",
        state=MessengerSession.STATE_CONFIRM,
        data={
            "service_id": service.id,
            "date": target_date.isoformat(),
            "starts_at": starts_at,
            "full_name": "Maria Santos",
            "phone": "09175551234",
            "email": "maria@example.com",
        },
    )

    actions = handle_message(session, "", "confirm")

    assert actions[0] == {"type": "text", "text": "That slot is no longer available. Please choose another time."}
    _assert_next_step_quick_replies(actions)
    session.refresh_from_db()
    assert session.state == MessengerSession.STATE_GREETING
    assert session.data == {}


@pytest.mark.django_db
def test_booked_state_restart_returns_service_selection():
    user = User.objects.create_user(username="owner_be_booked_restart", email="owner_be_booked_restart@test.com", password="pass")
    group = ClinicGroup.objects.create(name="GroupBEBookedRestart", owner=user)
    clinic = Clinic.objects.create(group=group, name="ClinicBEBookedRestart")
    conn = MessengerConnection.objects.create(clinic=clinic, page_id="P-BOOKED-RESTART", page_access_token="T")
    service = Service.objects.create(clinic=clinic, name="Cleaning", duration_minutes=30, price=0)
    session = MessengerSession.objects.create(connection=conn, psid="S-BOOKED-RESTART", state=MessengerSession.STATE_BOOKED)

    actions = handle_message(session, "", "restart")

    assert actions == [{
        "type": "quick_replies",
        "text": "Which service would you like to book?",
        "options": [{"title": "Cleaning", "payload": str(service.id)}],
    }]
    session.refresh_from_db()
    assert session.state == MessengerSession.STATE_SELECT_SERVICE


@pytest.mark.django_db
def test_booked_state_message_returns_next_step_quick_replies():
    user = User.objects.create_user(username="owner_be_booked_message", email="owner_be_booked_message@test.com", password="pass")
    group = ClinicGroup.objects.create(name="GroupBEBookedMessage", owner=user)
    clinic = Clinic.objects.create(group=group, name="ClinicBEBookedMessage")
    conn = MessengerConnection.objects.create(clinic=clinic, page_id="P-BOOKED-MESSAGE", page_access_token="T")
    session = MessengerSession.objects.create(connection=conn, psid="S-BOOKED-MESSAGE", state=MessengerSession.STATE_BOOKED)

    actions = handle_message(session, "thanks", "")

    assert actions[0] == {"type": "text", "text": "Thanks for using our booking service!"}
    _assert_next_step_quick_replies(actions)
    session.refresh_from_db()
    assert session.state == MessengerSession.STATE_GREETING


@pytest.mark.django_db
def test_parse_name_phone_valid():
    assert _parse_name_phone("John Doe\n09171234567") == ("John Doe", "09171234567")


def test_parse_name_phone_invalid():
    assert _parse_name_phone("only name") == (None, None)


def test_parse_name_phone_email_valid():
    assert bot_engine._parse_name_phone_email("John Doe\n09171234567\njohn@example.com") == (
        "John Doe",
        "09171234567",
        "john@example.com",
    )


def test_parse_name_phone_email_invalid():
    assert bot_engine._parse_name_phone_email("John Doe\n09171234567") == (None, None, None)
    assert bot_engine._parse_name_phone_email("John Doe\n09171234567\nnot-an-email") == (None, None, None)


@pytest.mark.django_db
def test_collect_info_requires_name_phone_and_email():
    user = User.objects.create_user(username="owner_be_collect_email", email="owner_be_collect_email@test.com", password="pass")
    group = ClinicGroup.objects.create(name="GroupBECollectEmail", owner=user)
    clinic = Clinic.objects.create(group=group, name="ClinicBECollectEmail")
    conn = MessengerConnection.objects.create(clinic=clinic, page_id="P-COLLECT-EMAIL", page_access_token="T")
    session = MessengerSession.objects.create(
        connection=conn,
        psid="S-COLLECT-EMAIL",
        state=MessengerSession.STATE_COLLECT_INFO,
        data={"service_id": 1, "date": "2026-01-01", "starts_at": timezone.now().isoformat()},
    )

    actions = handle_message(session, "Maria Santos\n09175551234", "")

    assert actions == [{
        "type": "text",
        "text": "Please provide your full name, phone number, and email.\n\nExample:\nJohn Doe\n09171234567\njohn@example.com",
    }]
    session.refresh_from_db()
    assert session.state == MessengerSession.STATE_COLLECT_INFO
    assert "email" not in session.data


@pytest.mark.django_db
def test_collect_info_stores_email_before_confirm():
    user = User.objects.create_user(username="owner_be_store_email", email="owner_be_store_email@test.com", password="pass")
    group = ClinicGroup.objects.create(name="GroupBEStoreEmail", owner=user)
    clinic = Clinic.objects.create(group=group, name="ClinicBEStoreEmail")
    conn = MessengerConnection.objects.create(clinic=clinic, page_id="P-STORE-EMAIL", page_access_token="T")
    service = Service.objects.create(clinic=clinic, name="Cleaning", duration_minutes=30, price=0)
    session = MessengerSession.objects.create(
        connection=conn,
        psid="S-STORE-EMAIL",
        state=MessengerSession.STATE_COLLECT_INFO,
        data={"service_id": service.id, "date": "2026-01-01", "starts_at": timezone.now().isoformat()},
    )

    handle_message(session, "Maria Santos\n09175551234\nmaria@example.com", "")

    session.refresh_from_db()
    assert session.state == MessengerSession.STATE_CONFIRM
    assert session.data["full_name"] == "Maria Santos"
    assert session.data["phone"] == "09175551234"
    assert session.data["email"] == "maria@example.com"


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
@override_settings(MESSENGER_VERIFY_TOKEN="")
def test_webhook_get_fails_closed_when_verify_token_unset():
    client = Client()
    url = reverse("messenger:webhook")
    response = client.get(url, {
        "hub.mode": "subscribe",
        "hub.verify_token": "",
        "hub.challenge": "CHALLENGE123",
    })

    assert response.status_code == 403


@pytest.mark.django_db
@override_settings(MESSENGER_APP_SECRET="test_secret")
def test_webhook_post_valid_message():
    client = Client()
    user = User.objects.create_user(username="owner_wh", email="owner_wh@test.com", password="pass")
    group = ClinicGroup.objects.create(name="GroupWH", owner=user)
    clinic = Clinic.objects.create(group=group, name="ClinicWH")
    conn = MessengerConnection.objects.create(
        clinic=clinic,
        app_secret="test_secret",
        page_id="PAGE1",
        page_access_token="TOKEN",
    )
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


@pytest.mark.django_db
@override_settings(MESSENGER_APP_SECRET="test_secret")
def test_direct_webhook_rejects_malformed_signed_payload_shape():
    client = Client()
    clinic, connection = _create_messenger_clinic("owner_direct_bad_shape", "PAGE-DIRECT-BAD-SHAPE")
    connection.app_secret = "test_secret"
    connection.save(update_fields=["app_secret"])
    payload = json.dumps({"object": "page", "entry": "not-a-list"}).encode()
    signature = "sha256=" + hmac.new("test_secret".encode(), payload, hashlib.sha256).hexdigest()

    response = client.post(
        reverse("messenger:webhook"),
        data=payload,
        content_type="application/json",
        HTTP_X_HUB_SIGNATURE_256=signature,
    )

    assert response.status_code == 403
    assert not MessengerSession.objects.exists()


@pytest.mark.django_db
@override_settings(MESSENGER_APP_SECRET="test_secret")
def test_direct_webhook_ignores_delivery_events_without_creating_session():
    client = Client()
    clinic, connection = _create_messenger_clinic("owner_direct_delivery_event", "PAGE-DIRECT-DELIVERY")
    connection.app_secret = "test_secret"
    connection.save(update_fields=["app_secret"])
    payload = json.dumps({
        "object": "page",
        "entry": [{
            "id": "PAGE-DIRECT-DELIVERY",
            "time": 123,
            "messaging": [{
                "sender": {"id": "PSID1"},
                "recipient": {"id": "PAGE-DIRECT-DELIVERY"},
                "delivery": {"mids": ["mid.1"], "watermark": 123},
            }],
        }],
    }).encode()
    signature = "sha256=" + hmac.new("test_secret".encode(), payload, hashlib.sha256).hexdigest()

    with patch("messenger.views._send_facebook_reply") as mock_send:
        response = client.post(
            reverse("messenger:webhook"),
            data=payload,
            content_type="application/json",
            HTTP_X_HUB_SIGNATURE_256=signature,
        )

    assert response.status_code == 200
    assert not MessengerSession.objects.filter(connection=connection, psid="PSID1").exists()
    mock_send.assert_not_called()


@pytest.mark.django_db
@override_settings(MESSENGER_APP_SECRET="test_secret")
def test_direct_webhook_dedupes_replayed_message_mid():
    client = Client()
    clinic, connection = _create_messenger_clinic("owner_direct_dedupe", "PAGE-DIRECT-DEDUPE")
    connection.app_secret = "test_secret"
    connection.save(update_fields=["app_secret"])
    Service.objects.create(clinic=clinic, name="Cleaning", duration_minutes=30, price=0)
    payload = json.dumps({
        "object": "page",
        "entry": [{
            "id": "PAGE-DIRECT-DEDUPE",
            "time": 123,
            "messaging": [{
                "sender": {"id": "PSID1"},
                "recipient": {"id": "PAGE-DIRECT-DEDUPE"},
                "message": {"mid": "mid-replayed", "text": "Book an appointment"},
            }],
        }],
    }).encode()
    signature = "sha256=" + hmac.new("test_secret".encode(), payload, hashlib.sha256).hexdigest()

    with patch("messenger.views._send_facebook_reply") as mock_send:
        first = client.post(reverse("messenger:webhook"), data=payload, content_type="application/json", HTTP_X_HUB_SIGNATURE_256=signature)
        second = client.post(reverse("messenger:webhook"), data=payload, content_type="application/json", HTTP_X_HUB_SIGNATURE_256=signature)

    assert first.status_code == 200
    assert second.status_code == 200
    assert mock_send.call_count == 1
    assert MessengerSession.objects.filter(connection=connection, psid="PSID1").exists()


@pytest.mark.django_db
@override_settings(MESSENGER_APP_SECRET="test_secret")
def test_direct_webhook_reads_meta_quick_reply_payload_for_service_selection():
    client = Client()
    clinic, conn = _create_messenger_clinic("owner_direct_qr_payload", "PAGE-DIRECT-QR")
    conn.app_secret = "test_secret"
    conn.save(update_fields=["app_secret"])
    service = Service.objects.create(clinic=clinic, name="Cleaning", duration_minutes=30, price=0)

    def post_meta_message(message):
        payload = json.dumps({
            "object": "page",
            "entry": [{
                "id": "PAGE-DIRECT-QR",
                "time": 123,
                "messaging": [{
                    "sender": {"id": "PSID1"},
                    "recipient": {"id": "PAGE-DIRECT-QR"},
                    "message": message,
                }],
            }],
        }).encode()
        signature = "sha256=" + hmac.new("test_secret".encode(), payload, hashlib.sha256).hexdigest()
        return client.post(
            reverse("messenger:webhook"),
            data=payload,
            content_type="application/json",
            HTTP_X_HUB_SIGNATURE_256=signature,
        )

    with patch("messenger.views._send_facebook_reply"):
        assert post_meta_message({"text": "Book an appointment"}).status_code == 200
        session = MessengerSession.objects.get(connection=conn, psid="PSID1")
        assert session.state == MessengerSession.STATE_SELECT_SERVICE

        response = post_meta_message({"text": "Cleaning", "quick_reply": {"payload": str(service.id)}})

    assert response.status_code == 200
    session.refresh_from_db()
    assert session.state == MessengerSession.STATE_SELECT_DATE
    assert session.data["service_id"] == service.id


@pytest.mark.django_db
@override_settings(MESSENGER_APP_SECRET="test_secret")
def test_direct_webhook_does_not_emit_quick_replies_when_messenger_mode_is_ai():
    from clinics.models import ClinicAISettings

    client = Client()
    clinic, connection = _create_messenger_clinic("owner_direct_ai_mode", "PAGE-DIRECT-AI-MODE")
    connection.app_secret = "test_secret"
    connection.save(update_fields=["app_secret"])
    ClinicAISettings.objects.create(
        clinic=clinic,
        is_ai_enabled=False,
        messenger_response_mode=ClinicAISettings.MESSENGER_MODE_AI,
        fallback_message="AI mode is unavailable right now.",
    )
    payload = json.dumps({
        "object": "page",
        "entry": [{
            "id": "PAGE-DIRECT-AI-MODE",
            "time": 123,
            "messaging": [{
                "sender": {"id": "PSID1"},
                "recipient": {"id": "PAGE-DIRECT-AI-MODE"},
                "message": {"text": "Book an appointment"},
            }],
        }],
    }).encode()
    signature = "sha256=" + hmac.new("test_secret".encode(), payload, hashlib.sha256).hexdigest()

    with patch("messenger.views._send_facebook_reply") as mock_send:
        response = client.post(
            reverse("messenger:webhook"),
            data=payload,
            content_type="application/json",
            HTTP_X_HUB_SIGNATURE_256=signature,
        )

    assert response.status_code == 200
    assert not MessengerSession.objects.filter(connection=connection, psid="PSID1").exists()
    mock_send.assert_not_called()


@pytest.mark.django_db
def test_webhook_post_uses_connection_app_secret():
    client = Client()
    user = User.objects.create_user(username="owner_wh_app", email="owner_wh_app@test.com", password="pass")
    group = ClinicGroup.objects.create(name="GroupWHApp", owner=user)
    clinic = Clinic.objects.create(group=group, name="ClinicWHApp")
    conn = MessengerConnection.objects.create(
        clinic=clinic,
        app_secret="clinic-app-secret",
        page_id="PAGE-APP-SECRET",
        page_access_token="TOKEN",
    )
    Service.objects.create(clinic=clinic, name="Cleaning", duration_minutes=30, price=0)

    payload = json.dumps({
        "object": "page",
        "entry": [{
            "id": "PAGE-APP-SECRET",
            "time": 123,
            "messaging": [{
                "sender": {"id": "PSID1"},
                "recipient": {"id": "PAGE-APP-SECRET"},
                "message": {"text": "Book an appointment"},
            }]
        }]
    }).encode()
    signature = "sha256=" + hmac.new("clinic-app-secret".encode(), payload, hashlib.sha256).hexdigest()

    resp = client.post(
        reverse("messenger:webhook"),
        data=payload,
        content_type="application/json",
        HTTP_X_HUB_SIGNATURE_256=signature,
    )

    assert resp.status_code == 200
    assert MessengerSession.objects.get(connection=conn, psid="PSID1").state == MessengerSession.STATE_SELECT_SERVICE


@pytest.mark.django_db
@override_settings(MESSENGER_APP_SECRET="legacy-meta-app-secret")
def test_webhook_post_accepts_global_secret_when_connection_secret_missing():
    client = Client()
    user = User.objects.create_user(username="owner_wh_global", email="owner_wh_global@test.com", password="pass")
    group = ClinicGroup.objects.create(name="GroupWHGlobal", owner=user)
    clinic = Clinic.objects.create(group=group, name="ClinicWHGlobal")
    conn = MessengerConnection.objects.create(
        clinic=clinic,
        page_id="PAGE-GLOBAL-SECRET",
        page_access_token="TOKEN",
    )
    Service.objects.create(clinic=clinic, name="Cleaning", duration_minutes=30, price=0)

    payload = json.dumps({
        "object": "page",
        "entry": [{
            "id": "PAGE-GLOBAL-SECRET",
            "time": 123,
            "messaging": [{
                "sender": {"id": "PSID1"},
                "recipient": {"id": "PAGE-GLOBAL-SECRET"},
                "message": {"text": "Book an appointment"},
            }]
        }]
    }).encode()
    signature = "sha256=" + hmac.new("legacy-meta-app-secret".encode(), payload, hashlib.sha256).hexdigest()

    resp = client.post(
        reverse("messenger:webhook"),
        data=payload,
        content_type="application/json",
        HTTP_X_HUB_SIGNATURE_256=signature,
    )

    assert resp.status_code == 200
    assert MessengerSession.objects.get(connection=conn, psid="PSID1").state == MessengerSession.STATE_SELECT_SERVICE


@pytest.mark.django_db
def test_webhook_post_rejects_signature_from_other_clinic_app_secret():
    client = Client()
    user = User.objects.create_user(username="owner_wh_cross", email="owner_wh_cross@test.com", password="pass")
    group = ClinicGroup.objects.create(name="GroupWHCross", owner=user)
    clinic_a = Clinic.objects.create(group=group, name="ClinicWHCrossA", slug="clinic-wh-cross-a")
    clinic_b = Clinic.objects.create(group=group, name="ClinicWHCrossB", slug="clinic-wh-cross-b")
    MessengerConnection.objects.create(
        clinic=clinic_a,
        app_secret="clinic-a-secret",
        page_id="PAGE-CROSS-A",
        page_access_token="TOKEN-A",
    )
    MessengerConnection.objects.create(
        clinic=clinic_b,
        app_secret="clinic-b-secret",
        page_id="PAGE-CROSS-B",
        page_access_token="TOKEN-B",
    )
    payload = json.dumps({
        "object": "page",
        "entry": [{
            "id": "PAGE-CROSS-A",
            "time": 123,
            "messaging": [{
                "sender": {"id": "PSID1"},
                "recipient": {"id": "PAGE-CROSS-A"},
                "message": {"text": "Book an appointment"},
            }]
        }]
    }).encode()
    signature = "sha256=" + hmac.new("clinic-b-secret".encode(), payload, hashlib.sha256).hexdigest()

    resp = client.post(
        reverse("messenger:webhook"),
        data=payload,
        content_type="application/json",
        HTTP_X_HUB_SIGNATURE_256=signature,
    )

    assert resp.status_code == 403
    assert not MessengerSession.objects.exists()


@pytest.mark.django_db
def test_webhook_post_ignores_messages_for_unverified_page_in_signed_payload():
    client = Client()
    user = User.objects.create_user(username="owner_wh_mixed", email="owner_wh_mixed@test.com", password="pass")
    group = ClinicGroup.objects.create(name="GroupWHMixed", owner=user)
    clinic_a = Clinic.objects.create(group=group, name="ClinicWHMixedA", slug="clinic-wh-mixed-a")
    clinic_b = Clinic.objects.create(group=group, name="ClinicWHMixedB", slug="clinic-wh-mixed-b")
    conn_a = MessengerConnection.objects.create(
        clinic=clinic_a,
        app_secret="clinic-a-secret",
        page_id="PAGE-MIXED-A",
        page_access_token="TOKEN-A",
    )
    conn_b = MessengerConnection.objects.create(
        clinic=clinic_b,
        app_secret="clinic-b-secret",
        page_id="PAGE-MIXED-B",
        page_access_token="TOKEN-B",
    )
    Service.objects.create(clinic=clinic_a, name="Clinic A Service", duration_minutes=30, price=0)
    Service.objects.create(clinic=clinic_b, name="Clinic B Service", duration_minutes=30, price=0)
    payload = json.dumps({
        "object": "page",
        "entry": [{
            "id": "PAGE-MIXED-A",
            "time": 123,
            "messaging": [{
                "sender": {"id": "PSID-B"},
                "recipient": {"id": "PAGE-MIXED-B"},
                "message": {"text": "Book an appointment"},
            }]
        }]
    }).encode()
    signature = "sha256=" + hmac.new("clinic-a-secret".encode(), payload, hashlib.sha256).hexdigest()

    resp = client.post(
        reverse("messenger:webhook"),
        data=payload,
        content_type="application/json",
        HTTP_X_HUB_SIGNATURE_256=signature,
    )

    assert resp.status_code == 403
    assert not MessengerSession.objects.filter(connection=conn_a).exists()
    assert not MessengerSession.objects.filter(connection=conn_b).exists()


@pytest.mark.django_db
def test_webhook_post_rejects_malformed_json_without_signature_before_parsing():
    client = Client()

    response = client.post(
        reverse("messenger:webhook"),
        data=b"{not-json",
        content_type="application/json",
    )

    assert response.status_code == 403


@pytest.mark.django_db
def test_webhook_post_does_not_process_recipient_for_different_verified_secret():
    client = Client()
    user = User.objects.create_user(username="owner_wh_mixed", email="owner_wh_mixed@test.com", password="pass")
    group = ClinicGroup.objects.create(name="GroupWHMixed", owner=user)
    clinic_a = Clinic.objects.create(group=group, name="ClinicWHMixedA", slug="clinic-wh-mixed-a")
    clinic_b = Clinic.objects.create(group=group, name="ClinicWHMixedB", slug="clinic-wh-mixed-b")
    MessengerConnection.objects.create(
        clinic=clinic_a,
        app_secret="clinic-a-secret",
        page_id="PAGE-MIXED-A",
        page_access_token="TOKEN-A",
    )
    connection_b = MessengerConnection.objects.create(
        clinic=clinic_b,
        app_secret="clinic-b-secret",
        page_id="PAGE-MIXED-B",
        page_access_token="TOKEN-B",
    )
    Service.objects.create(clinic=clinic_b, name="Cleaning", duration_minutes=30, price=0)
    payload = json.dumps({
        "object": "page",
        "entry": [{
            "id": "PAGE-MIXED-A",
            "time": 123,
            "messaging": [{
                "sender": {"id": "PSID-MIXED"},
                "recipient": {"id": "PAGE-MIXED-B"},
                "message": {"text": "Book an appointment"},
            }]
        }]
    }).encode()
    signature = "sha256=" + hmac.new("clinic-a-secret".encode(), payload, hashlib.sha256).hexdigest()

    response = client.post(
        reverse("messenger:webhook"),
        data=payload,
        content_type="application/json",
        HTTP_X_HUB_SIGNATURE_256=signature,
    )

    assert response.status_code == 403
    assert not MessengerSession.objects.filter(connection=connection_b, psid="PSID-MIXED").exists()


@pytest.mark.django_db
def test_webhook_post_rejects_shared_secret_entry_recipient_mismatch():
    client = Client()
    user = User.objects.create_user(username="owner_wh_shared", email="owner_wh_shared@test.com", password="pass")
    group = ClinicGroup.objects.create(name="GroupWHShared", owner=user)
    clinic_a = Clinic.objects.create(group=group, name="ClinicWHSharedA", slug="clinic-wh-shared-a")
    clinic_b = Clinic.objects.create(group=group, name="ClinicWHSharedB", slug="clinic-wh-shared-b")
    MessengerConnection.objects.create(clinic=clinic_a, app_secret="shared-secret", page_id="PAGE-SHARED-A", page_access_token="TOKEN-A")
    MessengerConnection.objects.create(clinic=clinic_b, app_secret="shared-secret", page_id="PAGE-SHARED-B", page_access_token="TOKEN-B")
    Service.objects.create(clinic=clinic_b, name="Cleaning", duration_minutes=30, price=0)
    payload = json.dumps({
        "object": "page",
        "entry": [{
            "id": "PAGE-SHARED-A",
            "time": 123,
            "messaging": [{
                "sender": {"id": "PSID1"},
                "recipient": {"id": "PAGE-SHARED-B"},
                "message": {"text": "Book an appointment"},
            }],
        }],
    }).encode()
    signature = "sha256=" + hmac.new("shared-secret".encode(), payload, hashlib.sha256).hexdigest()

    response = client.post(
        reverse("messenger:webhook"),
        data=payload,
        content_type="application/json",
        HTTP_X_HUB_SIGNATURE_256=signature,
    )

    assert response.status_code == 403
    assert not MessengerSession.objects.exists()


@pytest.mark.django_db
def test_webhook_post_rejects_missing_recipient_id():
    client = Client()
    user = User.objects.create_user(username="owner_wh_missing_recipient", email="owner_wh_missing_recipient@test.com", password="pass")
    group = ClinicGroup.objects.create(name="GroupWHMissingRecipient", owner=user)
    clinic = Clinic.objects.create(group=group, name="ClinicWHMissingRecipient")
    MessengerConnection.objects.create(
        clinic=clinic,
        app_secret="clinic-app-secret",
        page_id="PAGE-MISSING-RECIPIENT",
        page_access_token="TOKEN",
    )
    Service.objects.create(clinic=clinic, name="Cleaning", duration_minutes=30, price=0)
    payload = json.dumps({
        "object": "page",
        "entry": [{
            "id": "PAGE-MISSING-RECIPIENT",
            "time": 123,
            "messaging": [{
                "sender": {"id": "PSID1"},
                "message": {"text": "Book an appointment"},
            }],
        }],
    }).encode()
    signature = "sha256=" + hmac.new("clinic-app-secret".encode(), payload, hashlib.sha256).hexdigest()

    response = client.post(
        reverse("messenger:webhook"),
        data=payload,
        content_type="application/json",
        HTTP_X_HUB_SIGNATURE_256=signature,
    )

    assert response.status_code == 403
    assert not MessengerSession.objects.exists()


@pytest.mark.django_db
@override_settings(MESSENGER_APP_SECRET="test_secret")
def test_webhook_post_rejects_missing_signature():
    client = Client()
    payload = json.dumps({"object": "page", "entry": []}).encode()

    resp = client.post(
        reverse("messenger:webhook"),
        data=payload,
        content_type="application/json",
    )

    assert resp.status_code == 403


@pytest.mark.django_db
@override_settings(MESSENGER_APP_SECRET="test_secret")
def test_webhook_post_rejects_invalid_signature():
    client = Client()
    payload = json.dumps({"object": "page", "entry": []}).encode()

    resp = client.post(
        reverse("messenger:webhook"),
        data=payload,
        content_type="application/json",
        HTTP_X_HUB_SIGNATURE_256="sha256=bad",
    )

    assert resp.status_code == 403


@pytest.mark.django_db
@override_settings(MESSENGER_APP_SECRET="")
def test_webhook_post_rejects_when_app_secret_unset():
    client = Client()
    payload = json.dumps({"object": "page", "entry": []}).encode()

    resp = client.post(
        reverse("messenger:webhook"),
        data=payload,
        content_type="application/json",
    )

    assert resp.status_code == 403


from datetime import timedelta
from django.utils import timezone
from django.core.management import call_command
from unittest.mock import patch
from patients.models import Patient
from scheduling.models import ClinicBusinessHour, UnavailableDate


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
    from messenger.defaults import DEFAULT_MESSENGER_AI_PROMPT
    from messenger.models import MessengerAISettings

    clinic, connection = _create_messenger_clinic("owner_ai_settings", "PAGEAI1")

    settings = MessengerAISettings.objects.create(connection=connection)

    assert settings.connection == connection
    assert settings.is_ai_enabled is True
    assert settings.instructions == DEFAULT_MESSENGER_AI_PROMPT
    assert settings.fallback_message == ""
    assert str(settings) == f"MessengerAISettings({clinic.name})"

    with pytest.raises(IntegrityError):
        MessengerAISettings.objects.create(connection=connection)


@pytest.mark.django_db
def test_clinic_ai_settings_defaults_and_unique_clinic():
    from clinics.models import ClinicAISettings
    from messenger.defaults import DEFAULT_AI_FALLBACK_MESSAGE, DEFAULT_MESSENGER_AI_PROMPT

    clinic, connection = _create_messenger_clinic("owner_clinic_ai_defaults", "PAGE-CLINIC-AI")
    settings = ClinicAISettings.objects.create(clinic=clinic)

    assert settings.clinic == clinic
    assert settings.is_ai_enabled is True
    assert settings.messenger_response_mode == ClinicAISettings.MESSENGER_MODE_QUICK_REPLIES
    assert settings.safe_messenger_response_mode == ClinicAISettings.MESSENGER_MODE_QUICK_REPLIES
    assert settings.instructions == DEFAULT_MESSENGER_AI_PROMPT
    assert settings.fallback_message == DEFAULT_AI_FALLBACK_MESSAGE
    assert str(settings) == f"ClinicAISettings({clinic.name})"

    with pytest.raises(IntegrityError):
        ClinicAISettings.objects.create(clinic=clinic)


@pytest.mark.django_db
def test_clinic_ai_settings_invalid_messenger_response_mode_fails_closed():
    from clinics.models import ClinicAISettings

    clinic, _connection = _create_messenger_clinic("owner_clinic_ai_bad_mode", "PAGE-CLINIC-AI-BAD-MODE")
    settings = ClinicAISettings.objects.create(clinic=clinic)

    settings.messenger_response_mode = "invalid-mode"

    assert settings.safe_messenger_response_mode == ClinicAISettings.MESSENGER_MODE_QUICK_REPLIES


@pytest.mark.django_db
def test_clinic_ai_settings_tone_defaults_and_invalid_tone_fails_closed():
    from clinics.models import ClinicAISettings

    clinic, _connection = _create_messenger_clinic("owner_ai_tone_defaults", "PAGE-AI-TONE-DEFAULTS")

    settings = ClinicAISettings.objects.create(clinic=clinic)

    assert settings.communication_tone == ClinicAISettings.TONE_PROFESSIONAL
    assert settings.safe_communication_tone == ClinicAISettings.TONE_PROFESSIONAL
    assert settings.communication_tone_label == "Professional"
    assert settings.custom_tone_instructions == ""

    ClinicAISettings.objects.filter(pk=settings.pk).update(communication_tone="unsafe-tone")
    settings.refresh_from_db()

    assert settings.safe_communication_tone == ClinicAISettings.TONE_PROFESSIONAL
    assert settings.communication_tone_label == "Professional"


@pytest.mark.django_db
def test_clinic_ai_settings_manager_copies_messenger_values():
    from clinics.models import ClinicAISettings
    from messenger.models import MessengerAISettings

    clinic, connection = _create_messenger_clinic("owner_clinic_ai_copy", "PAGE-CLINIC-COPY")
    MessengerAISettings.objects.create(
        connection=connection,
        is_ai_enabled=False,
        instructions="Copied shared instructions.",
        fallback_message="Copied fallback.",
    )

    settings = ClinicAISettings.objects.create_from_messenger_settings(connection.ai_settings)

    assert settings.clinic == clinic
    assert settings.is_ai_enabled is False
    assert settings.instructions == "Copied shared instructions."
    assert settings.fallback_message == "Copied fallback."


@pytest.mark.django_db
def test_build_ai_context_uses_default_prompt_when_settings_missing():
    from messenger.ai_tools import build_ai_context
    from messenger.defaults import DEFAULT_AI_FALLBACK_MESSAGE, DEFAULT_MESSENGER_AI_PROMPT

    _clinic, _connection = _create_messenger_clinic("owner_ai_default_context", "PAGEAI_DEFAULT")

    result = build_ai_context("PAGEAI_DEFAULT")

    assert result["found"] is True
    assert result["ai"]["instructions"] == DEFAULT_MESSENGER_AI_PROMPT
    assert result["ai"]["fallback_message"] == DEFAULT_AI_FALLBACK_MESSAGE


@pytest.mark.django_db
def test_build_ai_context_uses_default_fallback_when_message_blank():
    from clinics.models import ClinicAISettings
    from messenger.ai_tools import build_ai_context
    from messenger.defaults import DEFAULT_AI_FALLBACK_MESSAGE

    clinic, _connection = _create_messenger_clinic("owner_ai_blank_fallback_context", "PAGEAI_BLANK_FALLBACK")
    ClinicAISettings.objects.create(clinic=clinic, fallback_message="")

    result = build_ai_context("PAGEAI_BLANK_FALLBACK")

    assert result["found"] is True
    assert result["ai"]["fallback_message"] == DEFAULT_AI_FALLBACK_MESSAGE


@pytest.mark.django_db
def test_build_ai_context_marks_messenger_ai_disabled_for_quick_reply_mode():
    from clinics.models import ClinicAISettings
    from messenger.ai_tools import build_ai_context

    clinic, _connection = _create_messenger_clinic("owner_ai_quick_mode", "PAGEAI-QUICK-MODE")
    ClinicAISettings.objects.create(
        clinic=clinic,
        is_ai_enabled=True,
        messenger_response_mode=ClinicAISettings.MESSENGER_MODE_QUICK_REPLIES,
    )

    result = build_ai_context("PAGEAI-QUICK-MODE")

    assert result["found"] is True
    assert result["ai"]["messenger_response_mode"] == ClinicAISettings.MESSENGER_MODE_QUICK_REPLIES
    assert "is_messenger_ai_enabled" not in result["ai"]


@pytest.mark.django_db
def test_build_ai_context_marks_messenger_ai_enabled_for_ai_mode():
    from clinics.models import ClinicAISettings
    from messenger.ai_tools import build_ai_context

    clinic, _connection = _create_messenger_clinic("owner_ai_mode_context", "PAGEAI-MODE-CONTEXT")
    ClinicAISettings.objects.create(
        clinic=clinic,
        is_ai_enabled=True,
        messenger_response_mode=ClinicAISettings.MESSENGER_MODE_AI,
    )

    result = build_ai_context("PAGEAI-MODE-CONTEXT")

    assert result["found"] is True
    assert result["ai"]["messenger_response_mode"] == ClinicAISettings.MESSENGER_MODE_AI
    assert "is_messenger_ai_enabled" not in result["ai"]


@pytest.mark.django_db
def test_build_ai_context_returns_messenger_response_mode_independent_from_ai_enabled():
    from clinics.models import ClinicAISettings
    from messenger.ai_tools import build_ai_context

    clinic, _connection = _create_messenger_clinic("owner_ai_mode_context", "PAGE-AI-MODE-CONTEXT")
    ClinicAISettings.objects.create(
        clinic=clinic,
        is_ai_enabled=False,
        messenger_response_mode=ClinicAISettings.MESSENGER_MODE_AI,
        instructions="Messenger can use AI while website Assistant is off.",
    )

    result = build_ai_context("PAGE-AI-MODE-CONTEXT")

    assert result["found"] is True
    assert result["ai"]["is_ai_enabled"] is False
    assert result["ai"]["messenger_response_mode"] == ClinicAISettings.MESSENGER_MODE_AI
    assert "is_messenger_ai_enabled" not in result["ai"]


@pytest.mark.django_db
def test_build_ai_context_defaults_messenger_response_mode_to_quick_replies():
    from clinics.models import ClinicAISettings
    from messenger.ai_tools import build_ai_context

    _clinic, _connection = _create_messenger_clinic("owner_ai_mode_default_context", "PAGE-AI-MODE-DEFAULT")

    result = build_ai_context("PAGE-AI-MODE-DEFAULT")

    assert result["found"] is True
    assert result["ai"]["messenger_response_mode"] == ClinicAISettings.MESSENGER_MODE_QUICK_REPLIES


@pytest.mark.django_db
def test_build_widget_ai_context_uses_shared_clinic_settings():
    from clinics.models import ClinicAISettings
    from messenger.ai_tools import build_widget_ai_context

    clinic, connection = _create_messenger_clinic("owner_widget_context", "PAGE-WIDGET-CONTEXT")
    Service.objects.create(clinic=clinic, name="Checkup", duration_minutes=30, price=500)
    ClinicFAQ.objects.create(clinic=clinic, question="Hours?", answer="9 AM to 5 PM")
    ClinicAISettings.objects.create(
        clinic=clinic,
        is_ai_enabled=False,
        instructions="Shared instructions.",
        fallback_message="Shared fallback.",
    )

    context = build_widget_ai_context(clinic.slug)

    assert context["found"] is True
    assert context["clinic"]["id"] == clinic.id
    assert context["ai"]["is_ai_enabled"] is False
    assert context["ai"]["instructions"] == "Shared instructions."
    assert context["ai"]["fallback_message"] == "Shared fallback."
    assert context["services"][0]["name"] == "Checkup"
    assert context["faqs"][0]["question"] == "Hours?"


@pytest.mark.django_db
def test_ai_contexts_include_business_hours_and_unavailable_dates():
    from messenger.ai_tools import build_ai_context, build_widget_ai_context

    clinic, _connection = _create_messenger_clinic("owner_ai_schedule_context", "PAGE-AI-SCHEDULE-CONTEXT")
    ClinicBusinessHour.objects.create(
        clinic=clinic,
        weekday=5,
        is_open=True,
        open_time=time(9),
        close_time=time(15),
        break_start=time(12),
        break_end=time(13),
    )
    ClinicBusinessHour.objects.create(
        clinic=clinic,
        weekday=6,
        is_open=True,
        open_time=time(10),
        close_time=time(14),
    )
    unavailable_date = timezone.localdate() + timedelta(days=10)
    UnavailableDate.objects.create(clinic=clinic, date=unavailable_date, reason="Holiday")

    messenger_context = build_ai_context("PAGE-AI-SCHEDULE-CONTEXT")
    widget_context = build_widget_ai_context(clinic.slug)

    for context in [messenger_context, widget_context]:
        assert context["business_hours"][5] == {
            "weekday": 5,
            "day": "Saturday",
            "is_open": True,
            "open_time": "09:00",
            "close_time": "15:00",
            "break_start": "12:00",
            "break_end": "13:00",
        }
        assert context["business_hours"][6]["day"] == "Sunday"
        assert context["business_hours"][6]["is_open"] is True
        assert context["business_hours"][0]["day"] == "Monday"
        assert context["business_hours"][0]["is_open"] is False
        assert context["unavailable_dates"] == [
            {"date": unavailable_date.isoformat(), "reason": "Holiday"}
        ]


@pytest.mark.django_db
def test_ai_contexts_include_shared_communication_tone_fields():
    from clinics.models import ClinicAISettings
    from messenger.ai_tools import build_ai_context, build_widget_ai_context

    clinic, _connection = _create_messenger_clinic("owner_ai_tone_context", "PAGE-AI-TONE-CONTEXT")
    ClinicAISettings.objects.create(
        clinic=clinic,
        communication_tone=ClinicAISettings.TONE_EMPATHETIC,
        custom_tone_instructions="Use reassuring language for anxious patients.",
    )

    messenger_context = build_ai_context("PAGE-AI-TONE-CONTEXT")
    widget_context = build_widget_ai_context(clinic.slug)

    for context in [messenger_context, widget_context]:
        assert context["ai"]["communication_tone"] == ClinicAISettings.TONE_EMPATHETIC
        assert context["ai"]["communication_tone_label"] == "Empathetic"
        assert context["ai"]["custom_tone_instructions"] == "Use reassuring language for anxious patients."


@pytest.mark.django_db
def test_ai_context_settings_timestamp_changes_when_tone_changes():
    from clinics.models import ClinicAISettings
    from messenger.ai_tools import build_ai_context

    clinic, _connection = _create_messenger_clinic("owner_ai_tone_timestamp", "PAGE-AI-TONE-TIMESTAMP")
    settings = ClinicAISettings.objects.create(
        clinic=clinic,
        communication_tone=ClinicAISettings.TONE_PROFESSIONAL,
    )
    original_timestamp = build_ai_context("PAGE-AI-TONE-TIMESTAMP")["ai"]["settings_updated_at"]

    settings.communication_tone = ClinicAISettings.TONE_FRIENDLY
    settings.custom_tone_instructions = "Use approachable wording."
    settings.save()
    settings.refresh_from_db()

    updated_timestamp = build_ai_context("PAGE-AI-TONE-TIMESTAMP")["ai"]["settings_updated_at"]

    assert updated_timestamp == settings.updated_at.isoformat()
    assert updated_timestamp != original_timestamp


@pytest.mark.django_db
def test_ai_contexts_expose_settings_timestamp_for_memory_versioning():
    from clinics.models import ClinicAISettings
    from messenger.ai_tools import build_ai_context, build_widget_ai_context

    clinic, _connection = _create_messenger_clinic("owner_ai_memory_version", "PAGE-AI-MEMORY-VERSION")
    settings = ClinicAISettings.objects.create(
        clinic=clinic,
        is_ai_enabled=True,
        messenger_response_mode=ClinicAISettings.MESSENGER_MODE_AI,
        instructions="Always reply I am not interested.",
    )

    messenger_context = build_ai_context("PAGE-AI-MEMORY-VERSION")
    widget_context = build_widget_ai_context(clinic.slug)

    assert messenger_context["ai"]["settings_updated_at"] == settings.updated_at.isoformat()
    assert widget_context["ai"]["settings_updated_at"] == settings.updated_at.isoformat()


@pytest.mark.django_db
@override_settings(N8N_WEBHOOK_SECRET="secret")
def test_widget_ai_context_endpoint_requires_secret(client):
    clinic, connection = _create_messenger_clinic("owner_widget_secret", "PAGE-WIDGET-SECRET")

    response = client.post(
        reverse("messenger:widget_ai_context"),
        data=json.dumps({"clinic_slug": clinic.slug}),
        content_type="application/json",
    )

    assert response.status_code == 401


@pytest.mark.django_db
def test_build_ai_context_returns_only_page_clinic_data():
    from clinics.models import ClinicAISettings
    from messenger.ai_tools import build_ai_context

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
    ClinicAISettings.objects.create(clinic=clinic, instructions="Use a friendly clinic tone.")

    result = build_ai_context("PAGEAI2")

    assert result["found"] is True
    assert result["clinic"]["id"] == clinic.id
    assert result["clinic"]["name"] == clinic.name
    assert result["clinic"]["address"] == "123 Main St"
    assert result["page_token"] == "TOKEN-PAGEAI2"
    assert result["ai"]["is_ai_enabled"] is True
    assert result["ai"]["instructions"] == "Use a friendly clinic tone."
    assert result["current_time"]["timezone"] == "Asia/Manila"
    assert result["current_time"]["today"]
    assert result["current_time"]["now"]
    assert [service["name"] for service in result["services"]] == ["Dental Cleaning"]
    assert [faq["question"] for faq in result["faqs"]] == ["Where are you located?"]


@pytest.mark.django_db
def test_build_ai_context_ignores_active_connection_without_page_token():
    from messenger.ai_tools import build_ai_context

    _clinic, connection = _create_messenger_clinic("owner_ai_context_blank_token", "PAGEAI-BLANK-TOKEN")
    connection.page_access_token = ""
    connection.save(update_fields=["page_access_token"])

    result = build_ai_context("PAGEAI-BLANK-TOKEN")

    assert result == {"found": False}


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
def test_check_availability_returns_all_requested_date_slots():
    from messenger.ai_tools import check_availability
    from scheduling.utils import generate_slots

    clinic, _ = _create_messenger_clinic("owner_ai_all_times", "PAGEAI-ALL-TIMES")
    service = Service.objects.create(clinic=clinic, name="Tooth Extraction", duration_minutes=30, price=0)
    target_date = timezone.localdate() + timedelta(days=1)
    ClinicBusinessHour.objects.create(clinic=clinic, weekday=target_date.weekday(), open_time=time(9), close_time=time(12))

    generated_slots = generate_slots(clinic, service, target_date)
    result = check_availability("PAGEAI-ALL-TIMES", service.id, preferred_date=target_date.isoformat())

    assert len(generated_slots) == 6
    assert result["suggestion_type"] == "requested_date"
    assert [slot["starts_at"] for slot in result["alternatives"]] == [
        slot["starts_at"].isoformat() for slot in generated_slots
    ]


@pytest.mark.django_db
def test_check_availability_returns_requested_slot_and_alternatives():
    from messenger.ai_tools import check_availability

    clinic, _ = _create_messenger_clinic("owner_ai_availability", "PAGEAI4")
    service = Service.objects.create(clinic=clinic, name="Consultation", duration_minutes=30, price=0)
    target_date = timezone.localdate() + timedelta(days=1)
    ClinicBusinessHour.objects.create(clinic=clinic, weekday=target_date.weekday(), open_time=time(9), close_time=time(11))

    open_result = check_availability("PAGEAI4", service.id, preferred_date=target_date.isoformat())
    assert open_result["suggestion_type"] == "requested_date"
    assert open_result["requested_date"] == target_date.isoformat()
    assert open_result["suggested_date"] == target_date.isoformat()
    requested_slot = open_result["alternatives"][0]["starts_at"]

    available_result = check_availability("PAGEAI4", service.id, preferred_starts_at=requested_slot)
    assert available_result["available"] is True
    assert available_result["selected_slot"]["starts_at"] == requested_slot
    assert available_result["suggestion_type"] == "requested_date"
    assert available_result["requested_date"] == target_date.isoformat()
    assert available_result["suggested_date"] == target_date.isoformat()

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
def test_check_availability_marks_nearest_time_when_requested_slot_is_taken():
    from messenger.ai_tools import check_availability

    clinic, _ = _create_messenger_clinic("owner_ai_nearest_time", "PAGEAI-NEAREST-TIME")
    service = Service.objects.create(clinic=clinic, name="Consultation", duration_minutes=30, price=0)
    target_date = timezone.localdate() + timedelta(days=1)
    ClinicBusinessHour.objects.create(clinic=clinic, weekday=target_date.weekday(), open_time=time(9), close_time=time(11))
    open_result = check_availability("PAGEAI-NEAREST-TIME", service.id, preferred_date=target_date.isoformat())
    requested_slot = open_result["alternatives"][1]["starts_at"]
    patient = Patient.objects.create(clinic=clinic, full_name="Existing Patient", phone="09999999999")
    Appointment.objects.create(
        clinic=clinic,
        patient=patient,
        service=service,
        starts_at=timezone.datetime.fromisoformat(requested_slot),
        ends_at=timezone.datetime.fromisoformat(requested_slot) + timedelta(minutes=30),
        status=Appointment.STATUS_CONFIRMED,
    )

    unavailable_result = check_availability("PAGEAI-NEAREST-TIME", service.id, preferred_starts_at=requested_slot)

    assert unavailable_result["available"] is False
    assert unavailable_result["suggestion_type"] == "nearest_time"
    assert unavailable_result["requested_date"] == target_date.isoformat()
    assert unavailable_result["suggested_date"] == target_date.isoformat()
    assert requested_slot not in [slot["starts_at"] for slot in unavailable_result["alternatives"]]
    assert {slot["local_starts_at"][:10] for slot in unavailable_result["alternatives"][:2]} == {target_date.isoformat()}


@pytest.mark.django_db
def test_check_availability_suggests_first_future_date_when_requested_date_has_no_slots():
    from messenger.ai_tools import check_availability

    clinic, _ = _create_messenger_clinic("owner_ai_next_available_date", "PAGEAI-NEXT-DATE")
    service = Service.objects.create(clinic=clinic, name="Consultation", duration_minutes=30, price=0)
    requested_date = timezone.localdate() + timedelta(days=1)
    next_available_date = requested_date + timedelta(days=1)
    ClinicBusinessHour.objects.create(clinic=clinic, weekday=next_available_date.weekday(), open_time=time(9), close_time=time(10))

    result = check_availability("PAGEAI-NEXT-DATE", service.id, preferred_date=requested_date.isoformat())

    assert result["available"] is False
    assert result["suggestion_type"] == "next_available_date"
    assert result["requested_date"] == requested_date.isoformat()
    assert result["suggested_date"] == next_available_date.isoformat()
    assert result["alternatives"]
    assert {slot["local_starts_at"][:10] for slot in result["alternatives"]} == {next_available_date.isoformat()}


@pytest.mark.django_db
def test_check_widget_availability_returns_shared_suggestion_metadata():
    from messenger.ai_tools import check_widget_availability

    clinic, _ = _create_messenger_clinic("owner_widget_next_available_date", "PAGE-WIDGET-NEXT-DATE")
    service = Service.objects.create(clinic=clinic, name="Consultation", duration_minutes=30, price=0)
    requested_date = timezone.localdate() + timedelta(days=1)
    next_available_date = requested_date + timedelta(days=1)
    ClinicBusinessHour.objects.create(clinic=clinic, weekday=next_available_date.weekday(), open_time=time(9), close_time=time(10))

    result = check_widget_availability(clinic.slug, service.id, preferred_date=requested_date.isoformat())

    assert result["found"] is True
    assert result["available"] is False
    assert result["suggestion_type"] == "next_available_date"
    assert result["requested_date"] == requested_date.isoformat()
    assert result["suggested_date"] == next_available_date.isoformat()
    assert {slot["local_starts_at"][:10] for slot in result["alternatives"]} == {next_available_date.isoformat()}


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
        email="maria@example.com",
    )
    assert result["created"] is True
    assert result["appointment"]["service"] == "Consultation"
    assert result["appointment"]["status"] == Appointment.STATUS_CONFIRMED
    appointment = Appointment.objects.get(reference_code=result["appointment"]["reference_code"])
    assert appointment.source == Appointment.SOURCE_MESSENGER
    assert appointment.patient.phone == "09175551234"


@pytest.mark.django_db
def test_book_confirmed_appointment_masks_phone_in_ai_tool_response():
    import json
    from messenger.ai_tools import book_confirmed_appointment, check_availability

    clinic, _ = _create_messenger_clinic("owner_ai_booking_masked_phone", "PAGEAI-MASKED-PHONE")
    service = Service.objects.create(clinic=clinic, name="Consultation", duration_minutes=30, price=0)
    target_date = timezone.localdate() + timedelta(days=1)
    ClinicBusinessHour.objects.create(clinic=clinic, weekday=target_date.weekday(), open_time=time(9), close_time=time(10))
    slot = check_availability("PAGEAI-MASKED-PHONE", service.id, preferred_date=target_date.isoformat())["alternatives"][0]

    result = book_confirmed_appointment(
        "PAGEAI-MASKED-PHONE",
        service.id,
        slot["starts_at"],
        "Maria Santos",
        "09175551234",
        confirmed=True,
        email="maria@example.com",
    )

    assert result["created"] is True
    appointment_payload = result["appointment"]
    assert appointment_payload["patient_phone_last4"] == "1234"
    assert "patient_phone" not in appointment_payload
    assert "09175551234" not in json.dumps(result)


@pytest.mark.django_db
def test_book_confirmed_appointment_rejects_missing_email():
    from messenger.ai_tools import book_confirmed_appointment, check_availability

    clinic, _ = _create_messenger_clinic("owner_ai_booking_email_required", "PAGEAI-EMAIL-REQUIRED")
    service = Service.objects.create(clinic=clinic, name="Consultation", duration_minutes=30, price=0)
    target_date = timezone.localdate() + timedelta(days=1)
    ClinicBusinessHour.objects.create(clinic=clinic, weekday=target_date.weekday(), open_time=time(9), close_time=time(10))
    slot = check_availability("PAGEAI-EMAIL-REQUIRED", service.id, preferred_date=target_date.isoformat())["alternatives"][0]

    result = book_confirmed_appointment(
        "PAGEAI-EMAIL-REQUIRED",
        service.id,
        slot["starts_at"],
        "Maria Santos",
        "09175551234",
        confirmed=True,
    )

    assert result["created"] is False
    assert result["error"] == "Please provide your email address."
    assert Appointment.objects.filter(clinic=clinic).count() == 0


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
            "email": "jana@example.com",
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
def test_widget_ai_tools_return_disabled_when_website_ai_settings_disabled():
    from clinics.models import ClinicAISettings
    from messenger.ai_tools import book_widget_confirmed_appointment, build_ai_context, check_widget_availability, match_widget_services

    clinic, connection = _create_messenger_clinic("owner_ai_disabled", "PAGEAI11")
    service = Service.objects.create(clinic=clinic, name="Consultation", duration_minutes=30, price=0)
    ClinicAISettings.objects.create(
        clinic=clinic,
        is_ai_enabled=False,
        fallback_message="Please call the clinic.",
    )

    context = build_ai_context("PAGEAI11")
    services = match_widget_services(clinic.slug, "consultation")
    availability = check_widget_availability(clinic.slug, service.id, preferred_date=(timezone.localdate() + timedelta(days=1)).isoformat())
    booking = book_widget_confirmed_appointment(clinic.slug, service.id, timezone.now().isoformat(), "Name", "0917", confirmed=True)

    assert context["ai"]["is_ai_enabled"] is False
    assert services["disabled"] is True
    assert availability["disabled"] is True
    assert booking["created"] is False
    assert booking["disabled"] is True
    assert booking["fallback_message"] == "Please call the clinic."


@pytest.mark.django_db
def test_messenger_ai_tools_work_when_messenger_mode_is_ai_and_website_ai_disabled():
    from clinics.models import ClinicAISettings
    from messenger.ai_tools import book_confirmed_appointment, check_availability, match_services

    clinic, _connection = _create_messenger_clinic("owner_messenger_ai_independent", "PAGEAI-INDEPENDENT")
    service = Service.objects.create(clinic=clinic, name="Consultation", description="General consult", duration_minutes=30, price=0)
    target_date = timezone.localdate() + timedelta(days=1)
    ClinicBusinessHour.objects.create(clinic=clinic, weekday=target_date.weekday(), open_time=time(9), close_time=time(10))
    ClinicAISettings.objects.create(
        clinic=clinic,
        is_ai_enabled=False,
        messenger_response_mode=ClinicAISettings.MESSENGER_MODE_AI,
        fallback_message="Please call the clinic.",
    )

    services = match_services("PAGEAI-INDEPENDENT", "consult")
    availability = check_availability("PAGEAI-INDEPENDENT", service.id, preferred_date=target_date.isoformat())

    assert services.get("disabled") is not True
    assert [match["name"] for match in services["matches"]] == ["Consultation"]
    assert availability.get("disabled") is not True
    assert availability["available"] is True

    booking = book_confirmed_appointment(
        "PAGEAI-INDEPENDENT",
        service.id,
        availability["alternatives"][0]["starts_at"],
        "Maria Santos",
        "09175551234",
        confirmed=True,
        email="maria@example.com",
    )

    assert services["found"] is True
    assert booking["created"] is True
    assert Appointment.objects.filter(clinic=clinic, source=Appointment.SOURCE_MESSENGER).count() == 1


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
        email="updated@example.com",
    )
    second = book_confirmed_appointment(
        "PAGEAI13",
        service.id,
        slot["starts_at"],
        "Another Name",
        "09175551111",
        confirmed=True,
        email="another@example.com",
    )

    assert first["created"] is True
    assert Appointment.objects.get(reference_code=first["appointment"]["reference_code"]).patient == patient
    patient.refresh_from_db()
    assert patient.full_name == "Existing Name"
    assert second["created"] is False
    assert second["error"] == "That slot is no longer available. Please choose another time."


@pytest.mark.django_db
def test_find_verified_appointment_matches_reference_and_normalized_phone():
    from messenger.ai_tools import find_verified_appointment

    clinic, _connection = _create_messenger_clinic("owner_appt_lookup", "PAGE-APPT-LOOKUP")
    service = Service.objects.create(clinic=clinic, name="Consultation", duration_minutes=30, price=0)
    patient = Patient.objects.create(clinic=clinic, full_name="Maria Santos", phone="09175551234")
    starts_at = timezone.now() + timedelta(days=1)
    appointment = Appointment.objects.create(
        clinic=clinic,
        patient=patient,
        service=service,
        starts_at=starts_at,
        ends_at=starts_at + timedelta(minutes=30),
        status=Appointment.STATUS_CONFIRMED,
        source=Appointment.SOURCE_STAFF,
    )

    result = find_verified_appointment("PAGE-APPT-LOOKUP", appointment.reference_code.lower(), "(0917) 555-1234")

    assert result["found"] is True
    assert result["appointment"]["reference_code"] == appointment.reference_code
    assert result["appointment"]["service_id"] == service.id
    assert result["appointment"]["service"] == "Consultation"
    assert result["appointment"]["status"] == Appointment.STATUS_CONFIRMED
    assert result["appointment"]["starts_at"] == starts_at.isoformat()
    assert result["appointment"]["local_starts_at"]
    assert result["appointment"]["patient_name"] == "Maria Santos"
    assert result["appointment"]["patient_phone_last4"] == "1234"
    assert result["appointment"]["local_date_label"]
    assert result["appointment"]["local_time_label"]
    appointment.refresh_from_db()
    assert appointment.status == Appointment.STATUS_CONFIRMED
    assert appointment.starts_at == starts_at
    assert appointment.ends_at == starts_at + timedelta(minutes=30)
    assert appointment.service == service
    assert appointment.patient == patient


@pytest.mark.django_db
def test_find_widget_verified_appointment_matches_pending_appointment_without_mutation():
    from messenger.ai_tools import find_widget_verified_appointment

    clinic, _connection = _create_messenger_clinic("owner_widget_appt_lookup", "PAGE-WIDGET-APPT-LOOKUP")
    service = Service.objects.create(clinic=clinic, name="Consultation", duration_minutes=30, price=0)
    patient = Patient.objects.create(clinic=clinic, full_name="Maria Santos", phone="09175551234")
    starts_at = timezone.now() + timedelta(days=1)
    appointment = Appointment.objects.create(
        clinic=clinic,
        patient=patient,
        service=service,
        starts_at=starts_at,
        ends_at=starts_at + timedelta(minutes=30),
        status=Appointment.STATUS_PENDING,
    )

    result = find_widget_verified_appointment(clinic.slug, appointment.reference_code, "09175551234")

    assert result["found"] is True
    assert result["appointment"]["reference_code"] == appointment.reference_code
    assert result["appointment"]["status"] == Appointment.STATUS_PENDING
    assert result["appointment"]["service_id"] == service.id
    assert result["appointment"]["starts_at"] == starts_at.isoformat()
    assert result["appointment"]["local_starts_at"]
    appointment.refresh_from_db()
    assert appointment.status == Appointment.STATUS_PENDING
    assert appointment.starts_at == starts_at
    assert appointment.ends_at == starts_at + timedelta(minutes=30)
    assert appointment.service == service
    assert appointment.patient == patient


@pytest.mark.django_db
def test_find_verified_appointment_rejects_wrong_phone_and_cross_clinic():
    from messenger.ai_tools import find_verified_appointment

    clinic, _connection = _create_messenger_clinic("owner_appt_lookup_scope", "PAGE-APPT-LOOKUP-SCOPE")
    other_clinic, _other_connection = _create_messenger_clinic("owner_appt_lookup_other", "PAGE-APPT-LOOKUP-OTHER")
    service = Service.objects.create(clinic=clinic, name="Consultation", duration_minutes=30, price=0)
    patient = Patient.objects.create(clinic=clinic, full_name="Maria Santos", phone="09175551234")
    starts_at = timezone.now() + timedelta(days=1)
    appointment = Appointment.objects.create(
        clinic=clinic,
        patient=patient,
        service=service,
        starts_at=starts_at,
        ends_at=starts_at + timedelta(minutes=30),
        status=Appointment.STATUS_CONFIRMED,
    )

    wrong_phone = find_verified_appointment("PAGE-APPT-LOOKUP-SCOPE", appointment.reference_code, "09170000000")
    wrong_page = find_verified_appointment("PAGE-APPT-LOOKUP-OTHER", appointment.reference_code, "09175551234")

    assert wrong_phone == {"found": False, "error": "Appointment not found. Please check the reference code and phone number."}
    assert wrong_page == {"found": False, "error": "Appointment not found. Please check the reference code and phone number."}
    assert other_clinic.appointments.count() == 0


@pytest.mark.django_db
def test_find_verified_appointment_rejects_missing_identity_and_ineligible_statuses():
    from messenger.ai_tools import find_verified_appointment

    clinic, _connection = _create_messenger_clinic("owner_appt_lookup_status", "PAGE-APPT-LOOKUP-STATUS")
    service = Service.objects.create(clinic=clinic, name="Consultation", duration_minutes=30, price=0)
    patient = Patient.objects.create(clinic=clinic, full_name="Maria Santos", phone="09175551234")
    missing = find_verified_appointment("PAGE-APPT-LOOKUP-STATUS", "", "")
    assert missing == {"found": False, "error": "Please provide the appointment reference code and phone number."}

    status_cases = [
        (Appointment.STATUS_CANCELLED, timezone.now() + timedelta(days=1), "This appointment cannot be changed through the assistant."),
        (Appointment.STATUS_COMPLETED, timezone.now() + timedelta(days=2), "This appointment cannot be changed through the assistant."),
        (Appointment.STATUS_NO_SHOW, timezone.now() + timedelta(days=3), "This appointment cannot be changed through the assistant."),
        (Appointment.STATUS_CONFIRMED, timezone.now() - timedelta(days=1), "Past appointments cannot be changed through the assistant."),
    ]
    for status, starts_at, expected_error in status_cases:
        appointment = Appointment.objects.create(
            clinic=clinic,
            patient=patient,
            service=service,
            starts_at=starts_at,
            ends_at=starts_at + timedelta(minutes=30),
            status=status,
        )
        result = find_verified_appointment("PAGE-APPT-LOOKUP-STATUS", appointment.reference_code, "09175551234")
        assert result == {"found": False, "error": expected_error}


@pytest.mark.django_db
def test_find_widget_verified_appointment_respects_website_ai_disabled():
    from clinics.models import ClinicAISettings
    from messenger.ai_tools import find_widget_verified_appointment

    clinic, _connection = _create_messenger_clinic("owner_widget_appt_lookup_disabled", "PAGE-WIDGET-APPT-DISABLED")
    ClinicAISettings.objects.create(clinic=clinic, is_ai_enabled=False, fallback_message="Please call us.")

    result = find_widget_verified_appointment(clinic.slug, "CF-TEST", "09175551234")

    assert result["found"] is False
    assert result["disabled"] is True
    assert result["fallback_message"] == "Please call us."
    assert result["error"] == "AI is disabled for this clinic."


@pytest.mark.django_db
def test_cancel_verified_appointment_requires_confirmation():
    from messenger.ai_tools import cancel_verified_appointment

    clinic, _connection = _create_messenger_clinic("owner_appt_cancel_confirm", "PAGE-APPT-CANCEL-CONFIRM")
    service = Service.objects.create(clinic=clinic, name="Consultation", duration_minutes=30, price=0)
    patient = Patient.objects.create(clinic=clinic, full_name="Maria Santos", phone="09175551234")
    starts_at = timezone.now() + timedelta(days=1)
    appointment = Appointment.objects.create(
        clinic=clinic,
        patient=patient,
        service=service,
        starts_at=starts_at,
        ends_at=starts_at + timedelta(minutes=30),
        status=Appointment.STATUS_CONFIRMED,
    )

    result = cancel_verified_appointment("PAGE-APPT-CANCEL-CONFIRM", appointment.reference_code, "09175551234", confirmed=False)

    appointment.refresh_from_db()
    assert result == {"cancelled": False, "error": "Appointment change requires explicit user confirmation."}
    assert appointment.status == Appointment.STATUS_CONFIRMED


@pytest.mark.django_db
def test_cancel_verified_appointment_cancels_future_verified_appointment_and_stores_reason():
    from messenger.ai_tools import cancel_verified_appointment

    clinic, _connection = _create_messenger_clinic("owner_appt_cancel", "PAGE-APPT-CANCEL")
    service = Service.objects.create(clinic=clinic, name="Consultation", duration_minutes=30, price=0)
    patient = Patient.objects.create(clinic=clinic, full_name="Maria Santos", phone="09175551234")
    starts_at = timezone.now() + timedelta(days=1)
    appointment = Appointment.objects.create(
        clinic=clinic,
        patient=patient,
        service=service,
        starts_at=starts_at,
        ends_at=starts_at + timedelta(minutes=30),
        status=Appointment.STATUS_PENDING,
        source=Appointment.SOURCE_PHONE,
    )

    result = cancel_verified_appointment(
        "PAGE-APPT-CANCEL",
        appointment.reference_code,
        "09175551234",
        confirmed=True,
        reason="Patient requested through assistant.",
    )

    appointment.refresh_from_db()
    assert result["cancelled"] is True
    assert result["appointment"]["reference_code"] == appointment.reference_code
    assert result["appointment"]["status"] == Appointment.STATUS_CANCELLED
    assert appointment.status == Appointment.STATUS_CANCELLED
    assert appointment.cancellation_reason == "Patient requested through assistant."
    assert appointment.source == Appointment.SOURCE_PHONE


@pytest.mark.django_db
def test_cancel_verified_appointment_handles_non_string_reason_safely():
    from messenger.ai_tools import cancel_verified_appointment

    clinic, _connection = _create_messenger_clinic("owner_appt_cancel_reason", "PAGE-APPT-CANCEL-REASON")
    service = Service.objects.create(clinic=clinic, name="Consultation", duration_minutes=30, price=0)
    patient = Patient.objects.create(clinic=clinic, full_name="Maria Santos", phone="09175551234")
    starts_at = timezone.now() + timedelta(days=1)
    appointment = Appointment.objects.create(
        clinic=clinic,
        patient=patient,
        service=service,
        starts_at=starts_at,
        ends_at=starts_at + timedelta(minutes=30),
        status=Appointment.STATUS_CONFIRMED,
    )

    result = cancel_verified_appointment(
        "PAGE-APPT-CANCEL-REASON",
        appointment.reference_code,
        "09175551234",
        confirmed=True,
        reason=123,
    )

    appointment.refresh_from_db()
    assert result["cancelled"] is True
    assert appointment.status == Appointment.STATUS_CANCELLED
    assert appointment.cancellation_reason == "123"


@pytest.mark.django_db
def test_cancel_verified_appointment_wrong_page_does_not_mutate():
    from messenger.ai_tools import cancel_verified_appointment

    clinic, _connection = _create_messenger_clinic("owner_appt_cancel_tenant", "PAGE-APPT-CANCEL-TENANT")
    _other_clinic, _other_connection = _create_messenger_clinic("owner_appt_cancel_tenant_other", "PAGE-APPT-CANCEL-TENANT-OTHER")
    service = Service.objects.create(clinic=clinic, name="Consultation", duration_minutes=30, price=0)
    patient = Patient.objects.create(clinic=clinic, full_name="Maria Santos", phone="09175551234")
    starts_at = timezone.now() + timedelta(days=1)
    appointment = Appointment.objects.create(
        clinic=clinic,
        patient=patient,
        service=service,
        starts_at=starts_at,
        ends_at=starts_at + timedelta(minutes=30),
        status=Appointment.STATUS_CONFIRMED,
    )

    result = cancel_verified_appointment(
        "PAGE-APPT-CANCEL-TENANT-OTHER",
        appointment.reference_code,
        "09175551234",
        confirmed=True,
    )

    appointment.refresh_from_db()
    assert result == {"cancelled": False, "error": "Appointment not found. Please check the reference code and phone number."}
    assert appointment.status == Appointment.STATUS_CONFIRMED


@pytest.mark.django_db
def test_reschedule_verified_appointment_requires_confirmation():
    from zoneinfo import ZoneInfo
    from messenger.ai_tools import reschedule_verified_appointment

    clinic, _connection = _create_messenger_clinic("owner_appt_reschedule_confirm", "PAGE-APPT-RESCHEDULE-CONFIRM")
    service = Service.objects.create(clinic=clinic, name="Consultation", duration_minutes=30, price=0)
    patient = Patient.objects.create(clinic=clinic, full_name="Maria Santos", phone="09175551234")
    clinic_tz = ZoneInfo(clinic.timezone)
    target_date = timezone.now().astimezone(clinic_tz).date() + timedelta(days=1)
    ClinicBusinessHour.objects.create(clinic=clinic, weekday=target_date.weekday(), open_time=time(9), close_time=time(12))
    starts_at = timezone.make_aware(timezone.datetime.combine(target_date, time(9)), clinic_tz)
    appointment = Appointment.objects.create(
        clinic=clinic,
        patient=patient,
        service=service,
        starts_at=starts_at,
        ends_at=starts_at + timedelta(minutes=30),
        status=Appointment.STATUS_CONFIRMED,
    )
    requested_start = timezone.make_aware(timezone.datetime.combine(target_date, time(10)), clinic_tz)

    result = reschedule_verified_appointment(
        "PAGE-APPT-RESCHEDULE-CONFIRM",
        appointment.reference_code,
        "09175551234",
        requested_start.isoformat(),
        confirmed=False,
    )

    appointment.refresh_from_db()
    assert result == {"rescheduled": False, "error": "Appointment change requires explicit user confirmation."}
    assert appointment.starts_at == starts_at


@pytest.mark.django_db
def test_reschedule_verified_appointment_moves_same_service_and_preserves_identity_fields():
    from zoneinfo import ZoneInfo
    from messenger.ai_tools import reschedule_verified_appointment

    clinic, _connection = _create_messenger_clinic("owner_appt_reschedule", "PAGE-APPT-RESCHEDULE")
    service = Service.objects.create(clinic=clinic, name="Consultation", duration_minutes=30, price=0)
    patient = Patient.objects.create(clinic=clinic, full_name="Maria Santos", phone="09175551234")
    clinic_tz = ZoneInfo(clinic.timezone)
    target_date = timezone.now().astimezone(clinic_tz).date() + timedelta(days=1)
    ClinicBusinessHour.objects.create(clinic=clinic, weekday=target_date.weekday(), open_time=time(9), close_time=time(12))
    original_start = timezone.make_aware(timezone.datetime.combine(target_date, time(9)), clinic_tz)
    new_start = timezone.make_aware(timezone.datetime.combine(target_date, time(10)), clinic_tz)
    appointment = Appointment.objects.create(
        clinic=clinic,
        patient=patient,
        service=service,
        starts_at=original_start,
        ends_at=original_start + timedelta(minutes=30),
        status=Appointment.STATUS_PENDING,
        source=Appointment.SOURCE_STAFF,
    )
    original_reference = appointment.reference_code

    result = reschedule_verified_appointment(
        "PAGE-APPT-RESCHEDULE",
        appointment.reference_code,
        "09175551234",
        new_start.isoformat(),
        confirmed=True,
    )

    appointment.refresh_from_db()
    assert result["rescheduled"] is True
    assert result["appointment"]["reference_code"] == original_reference
    assert appointment.starts_at == new_start
    assert appointment.ends_at == new_start + timedelta(minutes=30)
    assert appointment.service == service
    assert appointment.patient == patient
    assert appointment.source == Appointment.SOURCE_STAFF
    assert appointment.status == Appointment.STATUS_PENDING
    assert appointment.reference_code == original_reference


@pytest.mark.django_db
def test_reschedule_verified_appointment_rejects_overlap_and_past_time():
    from zoneinfo import ZoneInfo
    from messenger.ai_tools import reschedule_verified_appointment

    clinic, _connection = _create_messenger_clinic("owner_appt_reschedule_reject", "PAGE-APPT-RESCHEDULE-REJECT")
    service = Service.objects.create(clinic=clinic, name="Consultation", duration_minutes=30, price=0)
    patient = Patient.objects.create(clinic=clinic, full_name="Maria Santos", phone="09175551234")
    other_patient = Patient.objects.create(clinic=clinic, full_name="Other Patient", phone="09170000000")
    clinic_tz = ZoneInfo(clinic.timezone)
    target_date = timezone.now().astimezone(clinic_tz).date() + timedelta(days=1)
    ClinicBusinessHour.objects.create(clinic=clinic, weekday=target_date.weekday(), open_time=time(9), close_time=time(12))
    original_start = timezone.make_aware(timezone.datetime.combine(target_date, time(9)), clinic_tz)
    occupied_start = timezone.make_aware(timezone.datetime.combine(target_date, time(10)), clinic_tz)
    appointment = Appointment.objects.create(
        clinic=clinic,
        patient=patient,
        service=service,
        starts_at=original_start,
        ends_at=original_start + timedelta(minutes=30),
        status=Appointment.STATUS_CONFIRMED,
    )
    Appointment.objects.create(
        clinic=clinic,
        patient=other_patient,
        service=service,
        starts_at=occupied_start,
        ends_at=occupied_start + timedelta(minutes=30),
        status=Appointment.STATUS_CONFIRMED,
    )

    overlap = reschedule_verified_appointment(
        "PAGE-APPT-RESCHEDULE-REJECT",
        appointment.reference_code,
        "09175551234",
        occupied_start.isoformat(),
        confirmed=True,
    )
    past = reschedule_verified_appointment(
        "PAGE-APPT-RESCHEDULE-REJECT",
        appointment.reference_code,
        "09175551234",
        (timezone.now() - timedelta(hours=1)).isoformat(),
        confirmed=True,
    )

    appointment.refresh_from_db()
    assert overlap == {"rescheduled": False, "error": "This slot is not available."}
    assert past == {"rescheduled": False, "error": "Cannot reschedule to the past."}
    assert appointment.starts_at == original_start


@pytest.mark.django_db
def test_reschedule_widget_verified_appointment_uses_clinic_slug_and_preserves_identity():
    from zoneinfo import ZoneInfo
    from messenger.ai_tools import reschedule_widget_verified_appointment

    clinic, _connection = _create_messenger_clinic("owner_widget_appt_reschedule", "PAGE-WIDGET-APPT-RESCHEDULE")
    service = Service.objects.create(clinic=clinic, name="Consultation", duration_minutes=30, price=0)
    patient = Patient.objects.create(clinic=clinic, full_name="Maria Santos", phone="09175551234")
    clinic_tz = ZoneInfo(clinic.timezone)
    target_date = timezone.now().astimezone(clinic_tz).date() + timedelta(days=1)
    ClinicBusinessHour.objects.create(clinic=clinic, weekday=target_date.weekday(), open_time=time(9), close_time=time(12))
    original_start = timezone.make_aware(timezone.datetime.combine(target_date, time(9)), clinic_tz)
    new_start = timezone.make_aware(timezone.datetime.combine(target_date, time(10)), clinic_tz)
    appointment = Appointment.objects.create(
        clinic=clinic,
        patient=patient,
        service=service,
        starts_at=original_start,
        ends_at=original_start + timedelta(minutes=30),
        status=Appointment.STATUS_CONFIRMED,
        source=Appointment.SOURCE_CHAT_WIDGET,
    )

    result = reschedule_widget_verified_appointment(
        clinic.slug,
        appointment.reference_code,
        "09175551234",
        new_start.isoformat(),
        confirmed=True,
    )

    appointment.refresh_from_db()
    assert result["rescheduled"] is True
    assert result["appointment"]["reference_code"] == appointment.reference_code
    assert appointment.starts_at == new_start
    assert appointment.ends_at == new_start + timedelta(minutes=30)
    assert appointment.service == service
    assert appointment.patient == patient
    assert appointment.source == Appointment.SOURCE_CHAT_WIDGET
    assert appointment.status == Appointment.STATUS_CONFIRMED


@pytest.mark.django_db
def test_cancel_widget_verified_appointment_rechecks_phone_before_mutating():
    from messenger.ai_tools import cancel_widget_verified_appointment

    clinic, _connection = _create_messenger_clinic("owner_widget_appt_cancel", "PAGE-WIDGET-APPT-CANCEL")
    service = Service.objects.create(clinic=clinic, name="Consultation", duration_minutes=30, price=0)
    patient = Patient.objects.create(clinic=clinic, full_name="Maria Santos", phone="09175551234")
    starts_at = timezone.now() + timedelta(days=1)
    appointment = Appointment.objects.create(
        clinic=clinic,
        patient=patient,
        service=service,
        starts_at=starts_at,
        ends_at=starts_at + timedelta(minutes=30),
        status=Appointment.STATUS_CONFIRMED,
    )

    result = cancel_widget_verified_appointment(clinic.slug, appointment.reference_code, "09170000000", confirmed=True)

    appointment.refresh_from_db()
    assert result == {"cancelled": False, "error": "Appointment not found. Please check the reference code and phone number."}
    assert appointment.status == Appointment.STATUS_CONFIRMED


@pytest.mark.django_db
def test_widget_ai_booking_uses_chat_widget_source():
    from messenger.ai_tools import book_widget_confirmed_appointment, check_availability

    clinic, _ = _create_messenger_clinic("owner_widget_ai_source", "PAGEAI-WIDGET-SOURCE")
    service = Service.objects.create(clinic=clinic, name="Consultation", duration_minutes=30, price=0)
    target_date = timezone.localdate() + timedelta(days=1)
    ClinicBusinessHour.objects.create(clinic=clinic, weekday=target_date.weekday(), open_time=time(9), close_time=time(10))
    slot = check_availability("PAGEAI-WIDGET-SOURCE", service.id, preferred_date=target_date.isoformat())["alternatives"][0]

    result = book_widget_confirmed_appointment(
        clinic.slug,
        service.id,
        slot["starts_at"],
        "Widget AI Patient",
        "09170001111",
        confirmed=True,
        email="widget@example.com",
    )

    assert result["created"] is True
    appointment = Appointment.objects.get(reference_code=result["appointment"]["reference_code"])
    assert appointment.source == Appointment.SOURCE_CHAT_WIDGET


@pytest.mark.django_db
@override_settings(N8N_WEBHOOK_SECRET="secret123")
def test_ai_appointment_endpoints_require_secret(client):
    body = {
        "page_id": "PAGE",
        "clinic_slug": "clinic-slug",
        "reference_code": "CF-TEST",
        "phone": "09175551234",
        "starts_at": timezone.now().isoformat(),
        "confirmed": "true",
        "reason": "Requested in chat.",
    }

    for url_name in [
        "messenger:ai_appointment_lookup",
        "messenger:ai_appointment_cancel",
        "messenger:ai_appointment_reschedule",
        "messenger:widget_ai_appointment_lookup",
        "messenger:widget_ai_appointment_cancel",
        "messenger:widget_ai_appointment_reschedule",
    ]:
        response = client.post(
            reverse(url_name),
            data=json.dumps(body),
            content_type="application/json",
        )

        assert response.status_code == 401


@pytest.mark.django_db
@override_settings(N8N_WEBHOOK_SECRET="secret123")
def test_ai_appointment_cancel_endpoint_accepts_string_true_confirmation(client):
    clinic, _connection = _create_messenger_clinic("owner_ai_endpoint_cancel", "PAGE-AI-ENDPOINT-CANCEL")
    service = Service.objects.create(clinic=clinic, name="Consultation", duration_minutes=30, price=0)
    patient = Patient.objects.create(clinic=clinic, full_name="Maria Santos", phone="09175551234")
    starts_at = timezone.now() + timedelta(days=1)
    appointment = Appointment.objects.create(
        clinic=clinic,
        patient=patient,
        service=service,
        starts_at=starts_at,
        ends_at=starts_at + timedelta(minutes=30),
        status=Appointment.STATUS_CONFIRMED,
    )

    response = client.post(
        reverse("messenger:ai_appointment_cancel"),
        data=json.dumps({
            "page_id": "PAGE-AI-ENDPOINT-CANCEL",
            "reference_code": appointment.reference_code,
            "phone": "09175551234",
            "confirmed": "true",
            "reason": "Requested in chat.",
        }),
        content_type="application/json",
        HTTP_X_N8N_WEBHOOK_SECRET="secret123",
    )

    appointment.refresh_from_db()
    assert response.status_code == 200
    assert response.json()["cancelled"] is True
    assert appointment.status == Appointment.STATUS_CANCELLED


@pytest.mark.django_db
@override_settings(N8N_WEBHOOK_SECRET="secret123")
def test_ai_appointment_reschedule_endpoint_accepts_string_true_confirmation(client):
    from zoneinfo import ZoneInfo

    clinic, _connection = _create_messenger_clinic("owner_ai_endpoint_reschedule", "PAGE-AI-ENDPOINT-RESCHEDULE")
    service = Service.objects.create(clinic=clinic, name="Consultation", duration_minutes=30, price=0)
    patient = Patient.objects.create(clinic=clinic, full_name="Maria Santos", phone="09175551234")
    clinic_tz = ZoneInfo(clinic.timezone)
    target_date = timezone.now().astimezone(clinic_tz).date() + timedelta(days=1)
    ClinicBusinessHour.objects.create(clinic=clinic, weekday=target_date.weekday(), open_time=time(9), close_time=time(12))
    original_start = timezone.make_aware(timezone.datetime.combine(target_date, time(9)), clinic_tz)
    new_start = timezone.make_aware(timezone.datetime.combine(target_date, time(10)), clinic_tz)
    appointment = Appointment.objects.create(
        clinic=clinic,
        patient=patient,
        service=service,
        starts_at=original_start,
        ends_at=original_start + timedelta(minutes=30),
        status=Appointment.STATUS_CONFIRMED,
    )

    response = client.post(
        reverse("messenger:ai_appointment_reschedule"),
        data=json.dumps({
            "page_id": "PAGE-AI-ENDPOINT-RESCHEDULE",
            "reference_code": appointment.reference_code,
            "phone": "09175551234",
            "starts_at": new_start.isoformat(),
            "confirmed": "true",
        }),
        content_type="application/json",
        HTTP_X_N8N_WEBHOOK_SECRET="secret123",
    )

    appointment.refresh_from_db()
    assert response.status_code == 200
    assert response.json()["rescheduled"] is True
    assert appointment.starts_at == new_start


@pytest.mark.django_db
@override_settings(N8N_WEBHOOK_SECRET="secret123")
def test_widget_ai_appointment_cancel_endpoint_accepts_string_true_confirmation(client):
    clinic, _connection = _create_messenger_clinic("owner_widget_endpoint_cancel", "PAGE-WIDGET-ENDPOINT-CANCEL")
    service = Service.objects.create(clinic=clinic, name="Consultation", duration_minutes=30, price=0)
    patient = Patient.objects.create(clinic=clinic, full_name="Maria Santos", phone="09175551234")
    starts_at = timezone.now() + timedelta(days=1)
    appointment = Appointment.objects.create(
        clinic=clinic,
        patient=patient,
        service=service,
        starts_at=starts_at,
        ends_at=starts_at + timedelta(minutes=30),
        status=Appointment.STATUS_CONFIRMED,
    )

    response = client.post(
        reverse("messenger:widget_ai_appointment_cancel"),
        data=json.dumps({
            "clinic_slug": clinic.slug,
            "reference_code": appointment.reference_code,
            "phone": "09175551234",
            "confirmed": "true",
            "reason": "Requested in widget chat.",
        }),
        content_type="application/json",
        HTTP_X_N8N_WEBHOOK_SECRET="secret123",
    )

    appointment.refresh_from_db()
    assert response.status_code == 200
    assert response.json()["cancelled"] is True
    assert appointment.status == Appointment.STATUS_CANCELLED


@pytest.mark.django_db
@override_settings(N8N_WEBHOOK_SECRET="secret123")
def test_widget_ai_appointment_reschedule_endpoint_uses_clinic_slug(client):
    from zoneinfo import ZoneInfo

    clinic, _connection = _create_messenger_clinic("owner_widget_endpoint_reschedule", "PAGE-WIDGET-ENDPOINT-RESCHEDULE")
    service = Service.objects.create(clinic=clinic, name="Consultation", duration_minutes=30, price=0)
    patient = Patient.objects.create(clinic=clinic, full_name="Maria Santos", phone="09175551234")
    clinic_tz = ZoneInfo(clinic.timezone)
    target_date = timezone.now().astimezone(clinic_tz).date() + timedelta(days=1)
    ClinicBusinessHour.objects.create(clinic=clinic, weekday=target_date.weekday(), open_time=time(9), close_time=time(12))
    original_start = timezone.make_aware(timezone.datetime.combine(target_date, time(9)), clinic_tz)
    new_start = timezone.make_aware(timezone.datetime.combine(target_date, time(10)), clinic_tz)
    appointment = Appointment.objects.create(
        clinic=clinic,
        patient=patient,
        service=service,
        starts_at=original_start,
        ends_at=original_start + timedelta(minutes=30),
        status=Appointment.STATUS_CONFIRMED,
    )

    response = client.post(
        reverse("messenger:widget_ai_appointment_reschedule"),
        data=json.dumps({
            "clinic_slug": clinic.slug,
            "reference_code": appointment.reference_code,
            "phone": "09175551234",
            "starts_at": new_start.isoformat(),
            "confirmed": "true",
        }),
        content_type="application/json",
        HTTP_X_N8N_WEBHOOK_SECRET="secret123",
    )

    appointment.refresh_from_db()
    assert response.status_code == 200
    assert response.json()["rescheduled"] is True
    assert appointment.starts_at == new_start


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
@override_settings(N8N_WEBHOOK_SECRET="")
def test_n8n_webhook_fails_closed_when_secret_unset():
    _clinic, _connection = _create_messenger_clinic("owner_n8n_no_secret", "PAGE-N8N-NO-SECRET")
    client = Client()

    response = client.post(
        reverse("messenger:n8n_webhook"),
        data=json.dumps({"page_id": "PAGE-N8N-NO-SECRET", "psid": "PSID1", "text": "Hello"}),
        content_type="application/json",
    )

    assert response.status_code == 401


@pytest.mark.django_db
@override_settings(N8N_WEBHOOK_SECRET="secret123")
def test_n8n_webhook_rejects_invalid_secret():
    _clinic, _connection = _create_messenger_clinic("owner_n8n_bad_secret", "PAGE-N8N-BAD-SECRET")
    client = Client()

    response = client.post(
        reverse("messenger:n8n_webhook"),
        data=json.dumps({"page_id": "PAGE-N8N-BAD-SECRET", "psid": "PSID1", "text": "Hello"}),
        content_type="application/json",
        HTTP_X_N8N_WEBHOOK_SECRET="wrong",
    )

    assert response.status_code == 401


@pytest.mark.django_db
@override_settings(N8N_WEBHOOK_SECRET="secret123")
def test_n8n_webhook_rejects_non_object_json_without_creating_session():
    _clinic, _connection = _create_messenger_clinic("owner_n8n_bad_shape", "PAGE-N8N-BAD-SHAPE")
    client = Client()

    response = client.post(
        reverse("messenger:n8n_webhook"),
        data=json.dumps([]),
        content_type="application/json",
        HTTP_X_N8N_WEBHOOK_SECRET="secret123",
    )

    assert response.status_code == 400
    assert response.json() == {"error": "Invalid request data"}
    assert not MessengerSession.objects.exists()


@pytest.mark.django_db
@override_settings(N8N_WEBHOOK_SECRET="secret123")
def test_n8n_webhook_accepts_valid_secret():
    clinic, _connection = _create_messenger_clinic("owner_n8n_good_secret", "PAGE-N8N-GOOD-SECRET")
    Service.objects.create(clinic=clinic, name="Consultation", duration_minutes=30, price=0)
    client = Client()

    response = client.post(
        reverse("messenger:n8n_webhook"),
        data=json.dumps({"page_id": "PAGE-N8N-GOOD-SECRET", "psid": "PSID1", "text": "Book an appointment"}),
        content_type="application/json",
        HTTP_X_N8N_WEBHOOK_SECRET="secret123",
    )

    assert response.status_code == 200
    assert "replies" in response.json()


@pytest.mark.django_db
@override_settings(N8N_WEBHOOK_SECRET="secret123")
def test_n8n_webhook_returns_quick_replies_when_messenger_mode_is_quick_replies():
    from clinics.models import ClinicAISettings

    clinic, _connection = _create_messenger_clinic("owner_n8n_quick_mode", "PAGE-N8N-QUICK-MODE")
    ClinicAISettings.objects.create(clinic=clinic, messenger_response_mode=ClinicAISettings.MESSENGER_MODE_QUICK_REPLIES)
    Service.objects.create(clinic=clinic, name="Consultation", duration_minutes=30, price=0)
    client = Client()

    response = client.post(
        reverse("messenger:n8n_webhook"),
        data=json.dumps({"page_id": "PAGE-N8N-QUICK-MODE", "psid": "PSID1", "text": "Book an appointment"}),
        content_type="application/json",
        HTTP_X_N8N_WEBHOOK_SECRET="secret123",
    )

    assert response.status_code == 200
    assert response.json()["page_token"] == "TOKEN-PAGE-N8N-QUICK-MODE"
    assert response.json()["page_id"] == "PAGE-N8N-QUICK-MODE"
    assert response.json()["psid"] == "PSID1"
    assert any(reply["type"] == "quick_replies" for reply in response.json()["replies"])
    assert MessengerSession.objects.filter(connection__page_id="PAGE-N8N-QUICK-MODE", psid="PSID1").exists()


@pytest.mark.django_db
@override_settings(N8N_WEBHOOK_SECRET="secret123")
def test_n8n_webhook_no_services_returns_next_steps_not_empty_quick_replies():
    from clinics.models import ClinicAISettings

    clinic, _connection = _create_messenger_clinic("owner_n8n_no_services", "PAGE-N8N-NO-SERVICES")
    ClinicAISettings.objects.create(clinic=clinic, messenger_response_mode=ClinicAISettings.MESSENGER_MODE_QUICK_REPLIES)
    client = Client()

    response = client.post(
        reverse("messenger:n8n_webhook"),
        data=json.dumps({"page_id": "PAGE-N8N-NO-SERVICES", "psid": "PSID1", "text": "Book an appointment"}),
        content_type="application/json",
        HTTP_X_N8N_WEBHOOK_SECRET="secret123",
    )

    assert response.status_code == 200
    replies = response.json()["replies"]
    assert not [reply for reply in replies if reply.get("type") == "quick_replies" and reply.get("options") == []]
    _assert_next_step_quick_replies(replies)


@pytest.mark.django_db
@override_settings(N8N_WEBHOOK_SECRET="secret123")
def test_n8n_webhook_does_not_emit_quick_replies_when_messenger_mode_is_ai():
    from clinics.models import ClinicAISettings

    clinic, _connection = _create_messenger_clinic("owner_n8n_ai_mode", "PAGE-N8N-AI-MODE")
    ClinicAISettings.objects.create(
        clinic=clinic,
        messenger_response_mode=ClinicAISettings.MESSENGER_MODE_AI,
        fallback_message="AI mode is unavailable right now.",
    )
    Service.objects.create(clinic=clinic, name="Consultation", duration_minutes=30, price=0)
    client = Client()

    response = client.post(
        reverse("messenger:n8n_webhook"),
        data=json.dumps({"page_id": "PAGE-N8N-AI-MODE", "psid": "PSID1", "text": "Book an appointment"}),
        content_type="application/json",
        HTTP_X_N8N_WEBHOOK_SECRET="secret123",
    )

    assert response.status_code == 200
    assert response.json() == {
        "replies": [{"type": "text", "text": "AI mode is unavailable right now."}],
        "page_token": "TOKEN-PAGE-N8N-AI-MODE",
    }
    assert not MessengerSession.objects.filter(connection__page_id="PAGE-N8N-AI-MODE", psid="PSID1").exists()


@pytest.mark.django_db
@override_settings(N8N_WEBHOOK_SECRET="secret123")
def test_n8n_webhook_does_not_run_quick_reply_engine_in_ai_mode():
    from clinics.models import ClinicAISettings
    from messenger.ai_tools import DEFAULT_AI_FALLBACK_MESSAGE

    clinic, _connection = _create_messenger_clinic("owner_n8n_ai_mode", "PAGE-N8N-AI-MODE")
    ClinicAISettings.objects.create(
        clinic=clinic,
        is_ai_enabled=True,
        messenger_response_mode=ClinicAISettings.MESSENGER_MODE_AI,
    )
    client = Client()

    response = client.post(
        reverse("messenger:n8n_webhook"),
        data=json.dumps({"page_id": "PAGE-N8N-AI-MODE", "psid": "PSID1", "text": "Book an appointment"}),
        content_type="application/json",
        HTTP_X_N8N_WEBHOOK_SECRET="secret123",
    )

    assert response.status_code == 200
    assert response.json() == {
        "replies": [{"type": "text", "text": DEFAULT_AI_FALLBACK_MESSAGE}],
        "page_token": "TOKEN-PAGE-N8N-AI-MODE",
    }
    assert not MessengerSession.objects.exists()


@pytest.mark.django_db
@override_settings(N8N_WEBHOOK_SECRET="secret123")
def test_n8n_webhook_rejects_stale_quick_reply_turn_before_session_mutation():
    clinic, _connection = _create_messenger_clinic("owner_n8n_quick_stale_turn", "PAGE-N8N-QUICK-STALE-TURN")
    Service.objects.create(clinic=clinic, name="Consultation", duration_minutes=30, price=0)
    client = Client()
    stale_turn = _post_ai_turn_register(
        client,
        "PAGE-N8N-QUICK-STALE-TURN",
        "PSID1",
        "mid-quick-stale-one",
        "Book an appointment",
    ).json()
    _post_ai_turn_register(
        client,
        "PAGE-N8N-QUICK-STALE-TURN",
        "PSID1",
        "mid-quick-stale-two",
        "Actually cleaning",
    )

    response = client.post(
        reverse("messenger:n8n_webhook"),
        data=json.dumps({
            "page_id": "PAGE-N8N-QUICK-STALE-TURN",
            "psid": "PSID1",
            "text": "Book an appointment",
            "turn_token": stale_turn["turn_token"],
            "input_sequence": stale_turn["input_sequence"],
        }),
        content_type="application/json",
        HTTP_X_N8N_WEBHOOK_SECRET="secret123",
    )

    assert response.status_code == 200
    assert response.json() == {
        "replies": [],
        "page_token": "",
        "page_id": "PAGE-N8N-QUICK-STALE-TURN",
        "psid": "PSID1",
        "stale": True,
    }
    assert not MessengerSession.objects.filter(connection__page_id="PAGE-N8N-QUICK-STALE-TURN", psid="PSID1").exists()


@pytest.mark.django_db
@override_settings(N8N_WEBHOOK_SECRET="secret123")
def test_n8n_webhook_uses_messenger_ai_mode_when_website_ai_is_disabled():
    from clinics.models import ClinicAISettings
    from messenger.ai_tools import DEFAULT_AI_FALLBACK_MESSAGE

    clinic, _connection = _create_messenger_clinic("owner_n8n_ai_mode_disabled", "PAGE-N8N-AI-DISABLED")
    Service.objects.create(clinic=clinic, name="Consultation", duration_minutes=30, price=0)
    ClinicAISettings.objects.create(
        clinic=clinic,
        is_ai_enabled=False,
        messenger_response_mode=ClinicAISettings.MESSENGER_MODE_AI,
    )
    client = Client()

    response = client.post(
        reverse("messenger:n8n_webhook"),
        data=json.dumps({"page_id": "PAGE-N8N-AI-DISABLED", "psid": "PSID1", "text": "Book an appointment"}),
        content_type="application/json",
        HTTP_X_N8N_WEBHOOK_SECRET="secret123",
    )

    assert response.status_code == 200
    assert response.json() == {
        "replies": [{"type": "text", "text": DEFAULT_AI_FALLBACK_MESSAGE}],
        "page_token": "TOKEN-PAGE-N8N-AI-DISABLED",
    }
    assert not MessengerSession.objects.filter(connection__page_id="PAGE-N8N-AI-DISABLED", psid="PSID1").exists()


@pytest.mark.django_db
@override_settings(N8N_WEBHOOK_SECRET="secret123")
def test_n8n_webhook_ignores_inactive_clinic_connection():
    clinic, _connection = _create_messenger_clinic("owner_n8n_inactive_clinic", "PAGE-N8N-INACTIVE")
    clinic.is_active = False
    clinic.save(update_fields=["is_active"])
    client = Client()

    response = client.post(
        reverse("messenger:n8n_webhook"),
        data=json.dumps({"page_id": "PAGE-N8N-INACTIVE", "psid": "PSID1", "text": "Book an appointment"}),
        content_type="application/json",
        HTTP_X_N8N_WEBHOOK_SECRET="secret123",
    )

    assert response.status_code == 200
    assert response.json() == {"replies": [], "page_token": ""}
    assert not MessengerSession.objects.exists()


@pytest.mark.django_db
@override_settings(N8N_WEBHOOK_SECRET="secret123")
def test_n8n_webhook_ignores_active_connection_without_page_token():
    clinic, connection = _create_messenger_clinic("owner_n8n_blank_token", "PAGE-N8N-BLANK-TOKEN")
    connection.page_access_token = ""
    connection.save(update_fields=["page_access_token"])
    Service.objects.create(clinic=clinic, name="Consultation", duration_minutes=30, price=0)
    client = Client()

    response = client.post(
        reverse("messenger:n8n_webhook"),
        data=json.dumps({"page_id": "PAGE-N8N-BLANK-TOKEN", "psid": "PSID1", "text": "Book an appointment"}),
        content_type="application/json",
        HTTP_X_N8N_WEBHOOK_SECRET="secret123",
    )

    assert response.status_code == 200
    assert response.json() == {"replies": [], "page_token": ""}
    assert not MessengerSession.objects.exists()


@pytest.mark.django_db
@override_settings(N8N_WEBHOOK_SECRET="secret123")
def test_meta_signature_verification_endpoint_accepts_valid_per_clinic_secret():
    _clinic, _connection = _create_messenger_clinic("owner_meta_verify", "PAGE-META-VERIFY")
    _connection.app_secret = "meta-app-secret"
    _connection.save(update_fields=["app_secret"])
    raw_body = json.dumps({
        "object": "page",
        "entry": [{"id": "PAGE-META-VERIFY", "messaging": []}],
    })
    signature = "sha256=" + hmac.new("meta-app-secret".encode(), raw_body.encode(), hashlib.sha256).hexdigest()
    client = Client()

    response = client.post(
        reverse("messenger:meta_signature_verify"),
        data=json.dumps({
            "page_id": "PAGE-META-VERIFY",
            "raw_body": raw_body,
            "signature": signature,
        }),
        content_type="application/json",
        HTTP_X_N8N_WEBHOOK_SECRET="secret123",
    )

    assert response.status_code == 200
    assert response.json() == {"verified": True}


@pytest.mark.django_db
@override_settings(N8N_WEBHOOK_SECRET="secret123")
def test_meta_signature_verification_does_not_consume_turn_registration_dedupe():
    _clinic, connection = _create_messenger_clinic("owner_meta_dedupe", "PAGE-META-DEDUPE")
    connection.app_secret = "meta-app-secret"
    connection.save(update_fields=["app_secret"])
    raw_body = json.dumps({
        "object": "page",
        "entry": [{"id": "PAGE-META-DEDUPE", "messaging": [{
            "sender": {"id": "PSID1"},
            "recipient": {"id": "PAGE-META-DEDUPE"},
            "message": {"mid": "mid-meta-dedupe", "text": "Hello"},
        }]}],
    })
    signature = "sha256=" + hmac.new("meta-app-secret".encode(), raw_body.encode(), hashlib.sha256).hexdigest()
    client = Client()
    payload = {
        "page_id": "PAGE-META-DEDUPE",
        "raw_body": raw_body,
        "signature": signature,
        "psid": "PSID1",
        "message_id": "mid-meta-dedupe",
    }

    first_verify = client.post(reverse("messenger:meta_signature_verify"), data=json.dumps(payload), content_type="application/json", HTTP_X_N8N_WEBHOOK_SECRET="secret123")
    second_verify = client.post(reverse("messenger:meta_signature_verify"), data=json.dumps(payload), content_type="application/json", HTTP_X_N8N_WEBHOOK_SECRET="secret123")
    first_register = _post_ai_turn_register(client, "PAGE-META-DEDUPE", "PSID1", "mid-meta-dedupe", "Hello")
    second_register = _post_ai_turn_register(client, "PAGE-META-DEDUPE", "PSID1", "mid-meta-dedupe", "Hello")

    assert first_verify.status_code == 200
    assert first_verify.json() == {"verified": True, "duplicate": False}
    assert second_verify.status_code == 200
    assert second_verify.json() == {"verified": True, "duplicate": False}
    assert not MessengerProcessedMessage.objects.filter(connection=connection).exists()
    assert first_register.status_code == 200
    assert first_register.json()["registered"] is True
    assert first_register.json()["process_now"] is True
    assert second_register.status_code == 200
    assert second_register.json() == {
        "registered": False,
        "duplicate": True,
        "process_now": False,
        "superseded_previous": False,
    }


def _post_ai_turn_register(client, page_id, psid, message_id, message, postback=""):
    return client.post(
        reverse("messenger:ai_turn_register"),
        data=json.dumps({
            "page_id": page_id,
            "psid": psid,
            "message_id": message_id,
            "message": message,
            "postback": postback,
        }),
        content_type="application/json",
        HTTP_X_N8N_WEBHOOK_SECRET="secret123",
    )


def _post_ai_turn_claim(client, page_id, psid, turn_token):
    return client.post(
        reverse("messenger:ai_turn_claim"),
        data=json.dumps({"page_id": page_id, "psid": psid, "turn_token": turn_token}),
        content_type="application/json",
        HTTP_X_N8N_WEBHOOK_SECRET="secret123",
    )


def _post_ai_turn_complete(client, page_id, psid, turn_token, input_sequence, reply_text="Reply"):
    return client.post(
        reverse("messenger:ai_turn_complete"),
        data=json.dumps({
            "page_id": page_id,
            "psid": psid,
            "turn_token": turn_token,
            "input_sequence": input_sequence,
            "reply_text": reply_text,
        }),
        content_type="application/json",
        HTTP_X_N8N_WEBHOOK_SECRET="secret123",
    )


@pytest.mark.django_db
@override_settings(N8N_WEBHOOK_SECRET="secret123")
def test_ai_turn_register_claims_first_messenger_message_for_processing():
    from messenger.models import MessengerConversation, MessengerInboundMessage

    _clinic, _connection = _create_messenger_clinic("owner_ai_turn_first", "PAGE-AI-TURN-FIRST")
    client = Client()

    response = _post_ai_turn_register(client, "PAGE-AI-TURN-FIRST", "PSID1", "mid-turn-1", "June 15")

    assert response.status_code == 200
    data = response.json()
    assert data["registered"] is True
    assert data["duplicate"] is False
    assert data["process_now"] is True
    assert data["superseded_previous"] is False
    assert data["input_sequence"] == 1
    assert data["messages"] == [{"sequence": 1, "text": "June 15", "postback": ""}]
    assert "June 15" in data["message"]

    conversation = MessengerConversation.objects.get(connection__page_id="PAGE-AI-TURN-FIRST", psid="PSID1")
    assert conversation.last_sequence == 1
    assert conversation.completed_sequence == 0
    assert conversation.active_turn_token == data["turn_token"]
    assert MessengerInboundMessage.objects.get(conversation=conversation).sequence == 1

    claim = _post_ai_turn_claim(client, "PAGE-AI-TURN-FIRST", "PSID1", data["turn_token"])

    assert claim.status_code == 200
    assert claim.json()["claimed"] is True
    assert claim.json()["input_sequence"] == 1
    assert claim.json()["messages"] == [{"sequence": 1, "text": "June 15", "postback": ""}]


@pytest.mark.django_db
@override_settings(N8N_WEBHOOK_SECRET="secret123")
def test_ai_turn_new_message_supersedes_in_flight_turn_and_coalesces_pending_messages():
    from messenger.models import MessengerConversation

    _clinic, _connection = _create_messenger_clinic("owner_ai_turn_supersede", "PAGE-AI-TURN-SUPERSEDE")
    client = Client()
    first = _post_ai_turn_register(client, "PAGE-AI-TURN-SUPERSEDE", "PSID1", "mid-turn-date", "June 15").json()

    second_response = _post_ai_turn_register(client, "PAGE-AI-TURN-SUPERSEDE", "PSID1", "mid-turn-service", "Cleaning")

    assert second_response.status_code == 200
    second = second_response.json()
    assert second["registered"] is True
    assert second["duplicate"] is False
    assert second["process_now"] is True
    assert second["superseded_previous"] is True
    assert second["input_sequence"] == 2
    assert [item["text"] for item in second["messages"]] == ["June 15", "Cleaning"]
    assert "June 15" in second["message"]
    assert "Cleaning" in second["message"]

    stale_claim = _post_ai_turn_claim(client, "PAGE-AI-TURN-SUPERSEDE", "PSID1", first["turn_token"])
    stale_complete = _post_ai_turn_complete(
        client,
        "PAGE-AI-TURN-SUPERSEDE",
        "PSID1",
        first["turn_token"],
        first["input_sequence"],
        "What service would you like?",
    )
    current_claim = _post_ai_turn_claim(client, "PAGE-AI-TURN-SUPERSEDE", "PSID1", second["turn_token"])
    current_complete = _post_ai_turn_complete(
        client,
        "PAGE-AI-TURN-SUPERSEDE",
        "PSID1",
        second["turn_token"],
        second["input_sequence"],
        "What time works for Cleaning on June 15?",
    )

    assert stale_claim.status_code == 200
    assert stale_claim.json() == {"claimed": False, "stale": True, "has_pending": True}
    assert stale_complete.status_code == 200
    assert stale_complete.json() == {"send_reply": False, "stale": True, "has_pending": True}
    assert current_claim.status_code == 200
    assert current_claim.json()["claimed"] is True
    assert [item["text"] for item in current_claim.json()["messages"]] == ["June 15", "Cleaning"]
    assert current_complete.status_code == 200
    assert current_complete.json() == {"send_reply": True, "stale": False, "has_pending": False}

    conversation = MessengerConversation.objects.get(connection__page_id="PAGE-AI-TURN-SUPERSEDE", psid="PSID1")
    assert conversation.completed_sequence == 2
    assert conversation.active_turn_token == ""
    assert conversation.history[-2:] == [
        {"role": "user", "content": "June 15\nCleaning"},
        {"role": "assistant", "content": "What time works for Cleaning on June 15?"},
    ]


@pytest.mark.django_db
@override_settings(N8N_WEBHOOK_SECRET="secret123")
def test_ai_turn_payload_redacts_prior_history_phone_numbers():
    _clinic, _connection = _create_messenger_clinic("owner_ai_turn_redact_phone", "PAGE-AI-TURN-REDACT-PHONE")
    client = Client()
    first = _post_ai_turn_register(
        client,
        "PAGE-AI-TURN-REDACT-PHONE",
        "PSID1",
        "mid-turn-phone-booking",
        "Book for Maria Santos, phone 09175551234",
    ).json()
    _post_ai_turn_complete(
        client,
        "PAGE-AI-TURN-REDACT-PHONE",
        "PSID1",
        first["turn_token"],
        first["input_sequence"],
        "Booked under 09175551234.",
    )

    response = _post_ai_turn_register(
        client,
        "PAGE-AI-TURN-REDACT-PHONE",
        "PSID1",
        "mid-turn-cancel-wrong-phone",
        "Cancel CF-SPY1LWYH. My phone is 123445667788.",
    )

    assert response.status_code == 200
    data = response.json()
    assert "09175551234" not in data["message"]
    assert "09175551234" not in json.dumps(data["history"])
    assert "[phone redacted]" in data["message"]
    assert "123445667788" in data["message"]


@pytest.mark.django_db
@override_settings(N8N_WEBHOOK_SECRET="secret123")
def test_ai_turn_register_dedupes_replayed_message_without_restarting_processing():
    from messenger.models import MessengerConversation, MessengerInboundMessage

    _clinic, _connection = _create_messenger_clinic("owner_ai_turn_duplicate", "PAGE-AI-TURN-DUP")
    client = Client()
    first = _post_ai_turn_register(client, "PAGE-AI-TURN-DUP", "PSID1", "mid-turn-dup", "June 15").json()

    duplicate_response = _post_ai_turn_register(client, "PAGE-AI-TURN-DUP", "PSID1", "mid-turn-dup", "June 15")

    assert duplicate_response.status_code == 200
    assert duplicate_response.json() == {
        "registered": False,
        "duplicate": True,
        "process_now": False,
        "superseded_previous": False,
    }
    conversation = MessengerConversation.objects.get(connection__page_id="PAGE-AI-TURN-DUP", psid="PSID1")
    assert conversation.last_sequence == 1
    assert conversation.active_turn_token == first["turn_token"]
    assert MessengerInboundMessage.objects.filter(conversation=conversation).count() == 1


@pytest.mark.django_db
@override_settings(N8N_WEBHOOK_SECRET="secret123")
def test_ai_turn_register_isolated_by_page_and_psid():
    from messenger.models import MessengerConversation

    _clinic, _connection = _create_messenger_clinic("owner_ai_turn_isolated", "PAGE-AI-TURN-ISOLATED")
    client = Client()

    psid_one = _post_ai_turn_register(client, "PAGE-AI-TURN-ISOLATED", "PSID1", "mid-psid-1", "June 15").json()
    psid_two = _post_ai_turn_register(client, "PAGE-AI-TURN-ISOLATED", "PSID2", "mid-psid-2", "Cleaning").json()

    assert psid_one["process_now"] is True
    assert psid_two["process_now"] is True
    assert psid_one["input_sequence"] == 1
    assert psid_two["input_sequence"] == 1
    assert psid_one["turn_token"] != psid_two["turn_token"]
    assert MessengerConversation.objects.filter(connection__page_id="PAGE-AI-TURN-ISOLATED").count() == 2


@pytest.mark.django_db
@override_settings(N8N_WEBHOOK_SECRET="secret123")
def test_stale_messenger_turn_metadata_blocks_appointment_mutations():
    from zoneinfo import ZoneInfo
    from messenger.ai_tools import (
        book_confirmed_appointment,
        cancel_verified_appointment,
        check_availability,
        reschedule_verified_appointment,
    )

    clinic, _connection = _create_messenger_clinic("owner_ai_turn_stale_tools", "PAGE-AI-TURN-STALE-TOOLS")
    service = Service.objects.create(clinic=clinic, name="Consultation", duration_minutes=30, price=0)
    clinic_tz = ZoneInfo(clinic.timezone)
    target_date = timezone.now().astimezone(clinic_tz).date() + timedelta(days=1)
    ClinicBusinessHour.objects.create(clinic=clinic, weekday=target_date.weekday(), open_time=time(9), close_time=time(12))
    client = Client()
    stale_turn = _post_ai_turn_register(
        client,
        "PAGE-AI-TURN-STALE-TOOLS",
        "PSID1",
        "mid-stale-tool-date",
        "June 15",
    ).json()
    _post_ai_turn_register(
        client,
        "PAGE-AI-TURN-STALE-TOOLS",
        "PSID1",
        "mid-stale-tool-service",
        "Cleaning",
    )
    stale_error = "This Messenger request was superseded by a newer user message. Please use the latest conversation turn."

    slot = check_availability("PAGE-AI-TURN-STALE-TOOLS", service.id, preferred_date=target_date.isoformat())["alternatives"][0]
    booking = book_confirmed_appointment(
        "PAGE-AI-TURN-STALE-TOOLS",
        service.id,
        slot["starts_at"],
        "Maria Santos",
        "09175551234",
        confirmed=True,
        email="maria@example.com",
        psid="PSID1",
        turn_token=stale_turn["turn_token"],
        input_sequence=stale_turn["input_sequence"],
    )
    assert booking == {"created": False, "error": stale_error}
    assert Appointment.objects.filter(clinic=clinic).count() == 0

    patient = Patient.objects.create(clinic=clinic, full_name="Maria Santos", phone="09175551234")
    original_start = timezone.make_aware(timezone.datetime.combine(target_date, time(10)), clinic_tz)
    appointment = Appointment.objects.create(
        clinic=clinic,
        patient=patient,
        service=service,
        starts_at=original_start,
        ends_at=original_start + timedelta(minutes=30),
        status=Appointment.STATUS_CONFIRMED,
    )
    cancel = cancel_verified_appointment(
        "PAGE-AI-TURN-STALE-TOOLS",
        appointment.reference_code,
        "09175551234",
        confirmed=True,
        psid="PSID1",
        turn_token=stale_turn["turn_token"],
        input_sequence=stale_turn["input_sequence"],
    )
    assert cancel == {"cancelled": False, "error": stale_error}
    appointment.refresh_from_db()
    assert appointment.status == Appointment.STATUS_CONFIRMED

    new_start = timezone.make_aware(timezone.datetime.combine(target_date, time(11)), clinic_tz)
    reschedule = reschedule_verified_appointment(
        "PAGE-AI-TURN-STALE-TOOLS",
        appointment.reference_code,
        "09175551234",
        new_start.isoformat(),
        confirmed=True,
        psid="PSID1",
        turn_token=stale_turn["turn_token"],
        input_sequence=stale_turn["input_sequence"],
    )
    assert reschedule == {"rescheduled": False, "error": stale_error}
    appointment.refresh_from_db()
    assert appointment.starts_at == original_start


@pytest.mark.django_db
@override_settings(N8N_WEBHOOK_SECRET="secret123")
def test_meta_signature_verification_rejects_message_identity_not_in_signed_body():
    _clinic, connection = _create_messenger_clinic("owner_meta_identity_mismatch", "PAGE-META-IDENTITY")
    connection.app_secret = "meta-app-secret"
    connection.save(update_fields=["app_secret"])
    raw_body = json.dumps({
        "object": "page",
        "entry": [{"id": "PAGE-META-IDENTITY", "messaging": [{
            "sender": {"id": "PSID-SIGNED"},
            "recipient": {"id": "PAGE-META-IDENTITY"},
            "message": {"mid": "mid-signed", "text": "Hello"},
        }]}],
    })
    signature = "sha256=" + hmac.new("meta-app-secret".encode(), raw_body.encode(), hashlib.sha256).hexdigest()
    client = Client()

    response = client.post(
        reverse("messenger:meta_signature_verify"),
        data=json.dumps({
            "page_id": "PAGE-META-IDENTITY",
            "raw_body": raw_body,
            "signature": signature,
            "psid": "PSID-TAMPERED",
            "message_id": "mid-tampered",
        }),
        content_type="application/json",
        HTTP_X_N8N_WEBHOOK_SECRET="secret123",
    )

    assert response.status_code == 200
    assert response.json() == {"verified": False, "duplicate": False}
    assert not MessengerProcessedMessage.objects.filter(connection=connection).exists()


@pytest.mark.django_db
@override_settings(N8N_WEBHOOK_SECRET="secret123", MESSENGER_APP_SECRET="legacy-meta-app-secret")
def test_meta_signature_verification_endpoint_accepts_global_secret_when_connection_secret_missing():
    _clinic, _connection = _create_messenger_clinic("owner_meta_global_secret", "PAGE-META-GLOBAL")
    raw_body = json.dumps({
        "object": "page",
        "entry": [{
            "id": "PAGE-META-GLOBAL",
            "messaging": [{"recipient": {"id": "PAGE-META-GLOBAL"}}],
        }],
    })
    signature = "sha256=" + hmac.new("legacy-meta-app-secret".encode(), raw_body.encode(), hashlib.sha256).hexdigest()
    client = Client()

    response = client.post(
        reverse("messenger:meta_signature_verify"),
        data=json.dumps({
            "page_id": "PAGE-META-GLOBAL",
            "raw_body": raw_body,
            "signature": signature,
        }),
        content_type="application/json",
        HTTP_X_N8N_WEBHOOK_SECRET="secret123",
    )

    assert response.status_code == 200
    assert response.json() == {"verified": True}


@pytest.mark.django_db
@override_settings(N8N_WEBHOOK_SECRET="secret123")
def test_meta_signature_verification_endpoint_rejects_invalid_signature():
    _clinic, _connection = _create_messenger_clinic("owner_meta_verify_bad", "PAGE-META-BAD")
    _connection.app_secret = "meta-app-secret"
    _connection.save(update_fields=["app_secret"])
    client = Client()

    response = client.post(
        reverse("messenger:meta_signature_verify"),
        data=json.dumps({
            "page_id": "PAGE-META-BAD",
            "raw_body": json.dumps({"object": "page", "entry": [{"id": "PAGE-META-BAD"}]}),
            "signature": "sha256=bad",
        }),
        content_type="application/json",
        HTTP_X_N8N_WEBHOOK_SECRET="secret123",
    )

    assert response.status_code == 200
    assert response.json() == {"verified": False}


@pytest.mark.django_db
@override_settings(N8N_WEBHOOK_SECRET="secret123")
def test_meta_signature_verification_rejects_invalid_signature_before_raw_body_shape():
    _clinic, connection = _create_messenger_clinic("owner_meta_malformed", "PAGE-META-MALFORMED")
    connection.app_secret = "meta-app-secret"
    connection.save(update_fields=["app_secret"])
    client = Client()

    with patch("messenger.views.json.loads", wraps=json.loads) as mock_loads:
        response = client.post(
            reverse("messenger:meta_signature_verify"),
            data=json.dumps({
                "page_id": "PAGE-META-MALFORMED",
                "raw_body": "not-json",
                "signature": "sha256=bad",
            }),
            content_type="application/json",
            HTTP_X_N8N_WEBHOOK_SECRET="secret123",
        )

    assert response.status_code == 200
    assert response.json() == {"verified": False}
    assert "not-json" not in [call.args[0] for call in mock_loads.call_args_list]


@pytest.mark.django_db
@override_settings(N8N_WEBHOOK_SECRET="secret123")
def test_meta_signature_verification_rejects_signed_cross_page_payload():
    _clinic, connection = _create_messenger_clinic("owner_meta_cross_page", "PAGE-META-A")
    connection.app_secret = "shared-meta-secret"
    connection.save(update_fields=["app_secret"])
    raw_body = json.dumps({
        "object": "page",
        "entry": [
            {"id": "PAGE-META-A", "messaging": []},
            {"id": "PAGE-META-B", "messaging": [{"recipient": {"id": "PAGE-META-B"}}]},
        ],
    })
    signature = "sha256=" + hmac.new("shared-meta-secret".encode(), raw_body.encode(), hashlib.sha256).hexdigest()
    client = Client()

    response = client.post(
        reverse("messenger:meta_signature_verify"),
        data=json.dumps({
            "page_id": "PAGE-META-A",
            "raw_body": raw_body,
            "signature": signature,
        }),
        content_type="application/json",
        HTTP_X_N8N_WEBHOOK_SECRET="secret123",
    )

    assert response.status_code == 200
    assert response.json() == {"verified": False}


@pytest.mark.django_db
@override_settings(N8N_WEBHOOK_SECRET="secret123")
def test_meta_signature_verification_rejects_missing_recipient_id_in_message():
    _clinic, connection = _create_messenger_clinic("owner_meta_missing_recipient", "PAGE-META-MISSING-RECIPIENT")
    connection.app_secret = "meta-app-secret"
    connection.save(update_fields=["app_secret"])
    raw_body = json.dumps({
        "object": "page",
        "entry": [{
            "id": "PAGE-META-MISSING-RECIPIENT",
            "messaging": [{"sender": {"id": "PSID1"}, "message": {"text": "Hi"}}],
        }],
    })
    signature = "sha256=" + hmac.new("meta-app-secret".encode(), raw_body.encode(), hashlib.sha256).hexdigest()
    client = Client()

    response = client.post(
        reverse("messenger:meta_signature_verify"),
        data=json.dumps({
            "page_id": "PAGE-META-MISSING-RECIPIENT",
            "raw_body": raw_body,
            "signature": signature,
        }),
        content_type="application/json",
        HTTP_X_N8N_WEBHOOK_SECRET="secret123",
    )

    assert response.status_code == 200
    assert response.json() == {"verified": False}


@pytest.mark.django_db
@override_settings(N8N_WEBHOOK_SECRET="secret123")
def test_meta_signature_verification_rejects_non_object_request_body():
    client = Client()

    response = client.post(
        reverse("messenger:meta_signature_verify"),
        data=json.dumps([]),
        content_type="application/json",
        HTTP_X_N8N_WEBHOOK_SECRET="secret123",
    )

    assert response.status_code == 400
    assert response.json() == {"error": "Invalid request data"}


@pytest.mark.django_db
@override_settings(N8N_WEBHOOK_SECRET="secret123")
def test_meta_signature_verification_endpoint_returns_false_for_authorized_bad_input():
    client = Client()

    invalid_json = client.post(
        reverse("messenger:meta_signature_verify"),
        data="not json",
        content_type="application/json",
        HTTP_X_N8N_WEBHOOK_SECRET="secret123",
    )
    invalid_types = client.post(
        reverse("messenger:meta_signature_verify"),
        data=json.dumps({"page_id": "PAGE", "raw_body": {"bad": "type"}, "signature": "sha256=bad"}),
        content_type="application/json",
        HTTP_X_N8N_WEBHOOK_SECRET="secret123",
    )
    invalid_shape = client.post(
        reverse("messenger:meta_signature_verify"),
        data=json.dumps(["not", "an", "object"]),
        content_type="application/json",
        HTTP_X_N8N_WEBHOOK_SECRET="secret123",
    )

    assert invalid_json.status_code == 200
    assert invalid_json.json() == {"verified": False}
    assert invalid_types.status_code == 200
    assert invalid_types.json() == {"verified": False}
    assert invalid_shape.status_code == 400
    assert invalid_shape.json() == {"error": "Invalid request data"}


@pytest.mark.django_db
@override_settings(N8N_WEBHOOK_SECRET="secret123")
def test_meta_signature_verification_endpoint_returns_false_for_malformed_signed_raw_body():
    _clinic, connection = _create_messenger_clinic("owner_meta_bad_raw_shape", "PAGE-META-BAD-RAW")
    connection.app_secret = "meta-app-secret"
    connection.save(update_fields=["app_secret"])
    raw_body = json.dumps({
        "object": "page",
        "entry": [{
            "id": "PAGE-META-BAD-RAW",
            "messaging": [{"recipient": "bad-type"}],
        }],
    })
    signature = "sha256=" + hmac.new("meta-app-secret".encode(), raw_body.encode(), hashlib.sha256).hexdigest()
    client = Client()

    response = client.post(
        reverse("messenger:meta_signature_verify"),
        data=json.dumps({
            "page_id": "PAGE-META-BAD-RAW",
            "raw_body": raw_body,
            "signature": signature,
        }),
        content_type="application/json",
        HTTP_X_N8N_WEBHOOK_SECRET="secret123",
    )

    assert response.status_code == 200
    assert response.json() == {"verified": False}


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
    assert response.json()["available"] is True
    assert response.json()["suggestion_type"] == "requested_date"
    assert response.json()["requested_date"] == target_date.isoformat()
    assert response.json()["suggested_date"] == target_date.isoformat()
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
            "email": "juan@example.com",
            "confirmed": True,
        }),
        content_type="application/json",
        HTTP_X_N8N_WEBHOOK_SECRET="secret123",
    )

    assert response.status_code == 200
    assert response.json()["created"] is True
    assert Appointment.objects.filter(clinic=clinic, source=Appointment.SOURCE_MESSENGER).count() == 1


@pytest.mark.django_db
@override_settings(N8N_WEBHOOK_SECRET="secret123")
def test_ai_booking_endpoint_persists_messenger_psid():
    clinic, _ = _create_messenger_clinic("owner_ai_book_psid", "PAGEAI-PSID")
    service = Service.objects.create(clinic=clinic, name="Consultation", duration_minutes=30, price=0)
    target_date = timezone.localdate() + timedelta(days=1)
    ClinicBusinessHour.objects.create(clinic=clinic, weekday=target_date.weekday(), open_time=time(9), close_time=time(10))
    from messenger.ai_tools import check_availability
    slot = check_availability("PAGEAI-PSID", service.id, preferred_date=target_date.isoformat())["alternatives"][0]
    client = Client()

    response = client.post(
        reverse("messenger:ai_book"),
        data=json.dumps({
            "page_id": "PAGEAI-PSID",
            "service_id": service.id,
            "starts_at": slot["starts_at"],
            "full_name": "PSID Patient",
            "phone": "09170000001",
            "email": "psid@example.com",
            "confirmed": True,
            "psid": "PSID-RIGHT",
        }),
        content_type="application/json",
        HTTP_X_N8N_WEBHOOK_SECRET="secret123",
    )

    assert response.status_code == 200
    appointment = Appointment.objects.get(clinic=clinic, patient__full_name="PSID Patient")
    assert appointment.messenger_psid == "PSID-RIGHT"


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
        messenger_psid="PSID1",
    )
    MessengerSession.objects.create(connection=conn, psid="PSID1")
    call_command("send_messenger_reminders")
    mock_send.assert_called_once()


@pytest.mark.django_db
@patch("messenger.management.commands.send_messenger_reminders.send_messages")
def test_reminder_command_uses_appointment_psid_and_is_idempotent(mock_send):
    user = User.objects.create_user(username="owner_rem_psid", email="owner_rem_psid@test.com", password="pass")
    group = ClinicGroup.objects.create(name="GroupREMPSID", owner=user)
    clinic = Clinic.objects.create(group=group, name="ClinicREMPSID", timezone="Asia/Manila")
    conn = MessengerConnection.objects.create(clinic=clinic, page_id="P-PSID", page_access_token="T")
    service = Service.objects.create(clinic=clinic, name="Cleaning", duration_minutes=30, price=0)
    patient = Patient.objects.create(clinic=clinic, full_name="John", phone="09171234567")
    Appointment.objects.create(
        clinic=clinic,
        patient=patient,
        service=service,
        starts_at=timezone.now() + timedelta(hours=24),
        ends_at=timezone.now() + timedelta(hours=24, minutes=30),
        source=Appointment.SOURCE_MESSENGER,
        status=Appointment.STATUS_CONFIRMED,
        messenger_psid="PSID-RIGHT",
    )
    MessengerSession.objects.create(connection=conn, psid="PSID-WRONG")
    MessengerSession.objects.create(connection=conn, psid="PSID-RIGHT")

    call_command("send_messenger_reminders")
    call_command("send_messenger_reminders")

    mock_send.assert_called_once()
    assert mock_send.call_args.args[1] == "PSID-RIGHT"


@pytest.mark.django_db
@patch("messenger.management.commands.send_messenger_reminders.send_messages")
def test_reminder_command_does_not_mark_failed_send_as_sent(mock_send):
    mock_send.return_value = False
    user = User.objects.create_user(username="owner_rem_fail", email="owner_rem_fail@test.com", password="pass")
    group = ClinicGroup.objects.create(name="GroupREMFail", owner=user)
    clinic = Clinic.objects.create(group=group, name="ClinicREMFail", timezone="Asia/Manila")
    MessengerConnection.objects.create(clinic=clinic, page_id="P-FAIL", page_access_token="T")
    service = Service.objects.create(clinic=clinic, name="Cleaning", duration_minutes=30, price=0)
    patient = Patient.objects.create(clinic=clinic, full_name="John", phone="09171234567")
    appointment = Appointment.objects.create(
        clinic=clinic,
        patient=patient,
        service=service,
        starts_at=timezone.now() + timedelta(hours=24),
        ends_at=timezone.now() + timedelta(hours=24, minutes=30),
        source=Appointment.SOURCE_MESSENGER,
        status=Appointment.STATUS_CONFIRMED,
        messenger_psid="PSID-FAIL",
    )

    call_command("send_messenger_reminders")

    appointment.refresh_from_db()
    assert appointment.messenger_reminder_24h_sent_at is None


@pytest.mark.django_db
def test_messenger_cancel_only_cancels_matching_psid():
    from messenger.bot_engine import handle_message

    clinic, conn = _create_messenger_clinic("owner_cancel_psid", "PAGE-CANCEL-PSID")
    service = Service.objects.create(clinic=clinic, name="Consultation", duration_minutes=30, price=0)
    patient_one = Patient.objects.create(clinic=clinic, full_name="One", phone="09170000001")
    patient_two = Patient.objects.create(clinic=clinic, full_name="Two", phone="09170000002")
    first_start = timezone.now() + timedelta(days=1)
    second_start = timezone.now() + timedelta(days=2)
    appointment_one = Appointment.objects.create(
        clinic=clinic,
        patient=patient_one,
        service=service,
        starts_at=first_start,
        ends_at=first_start + timedelta(minutes=30),
        source=Appointment.SOURCE_MESSENGER,
        status=Appointment.STATUS_CONFIRMED,
        messenger_psid="PSID-ONE",
    )
    appointment_two = Appointment.objects.create(
        clinic=clinic,
        patient=patient_two,
        service=service,
        starts_at=second_start,
        ends_at=second_start + timedelta(minutes=30),
        source=Appointment.SOURCE_MESSENGER,
        status=Appointment.STATUS_CONFIRMED,
        messenger_psid="PSID-TWO",
    )
    session = MessengerSession.objects.create(connection=conn, psid="PSID-TWO")

    handle_message(session, "cancel", "")

    appointment_one.refresh_from_db()
    appointment_two.refresh_from_db()
    assert appointment_one.status == Appointment.STATUS_CONFIRMED
    assert appointment_two.status == Appointment.STATUS_CANCELLED


@pytest.mark.django_db
@patch("messenger.views.requests.post")
def test_direct_facebook_reply_logs_http_failures_without_token(mock_post, caplog):
    from messenger.views import _send_facebook_reply

    mock_post.return_value.raise_for_status.side_effect = requests.HTTPError(
        "400 Client Error for token SECRET-PAGE-TOKEN"
    )

    _send_facebook_reply("SECRET-PAGE-TOKEN", "PSID1", [{"type": "text", "text": "Hello"}])

    assert "Failed to send Messenger reply" in caplog.text
    assert "SECRET-PAGE-TOKEN" not in caplog.text


@patch("messenger.views.requests.post")
def test_direct_facebook_reply_uses_meta_safe_quick_reply_body(mock_post):
    from messenger.views import _send_facebook_reply

    _send_facebook_reply("PAGE-TOKEN", "PSID1", [{
        "type": "quick_replies",
        "text": "Choose a service",
        "options": [{"title": "Very long consultation service", "payload": 123}]
        + [{"title": f"Option {i}", "payload": i} for i in range(2, 15)],
    }])

    body = mock_post.call_args.kwargs["json"]
    assert body == {
        "messaging_type": "RESPONSE",
        "recipient": {"id": "PSID1"},
        "message": {
            "text": "Choose a service",
            "quick_replies": [{
                "content_type": "text",
                "title": "Very long consultati",
                "payload": "123",
            }] + [
                {"content_type": "text", "title": f"Option {i}", "payload": str(i)}
                for i in range(2, 14)
            ],
        },
    }


@pytest.mark.django_db
@override_settings(MESSENGER_APP_SECRET="test_secret")
def test_full_booking_flow_via_webhook():
    client = Client()
    user = User.objects.create_user(username="owner_flow", email="owner_flow@test.com", password="pass")
    group = ClinicGroup.objects.create(name="GroupFlow", owner=user)
    clinic = Clinic.objects.create(group=group, name="KliniAssist", timezone="Asia/Manila", booking_approval_mode=Clinic.APPROVAL_AUTO)
    conn = MessengerConnection.objects.create(
        clinic=clinic,
        app_secret="test_secret",
        page_id="PAGE1",
        page_access_token="TOKEN",
    )
    service = Service.objects.create(clinic=clinic, name="Cleaning", duration_minutes=30, price=0)
    target_date = timezone.localdate() + timedelta(days=1)
    ClinicBusinessHour.objects.create(clinic=clinic, weekday=target_date.weekday(), open_time=time(9), close_time=time(10))

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
        resp = send_message(payload=target_date.isoformat())
        assert resp.status_code == 200
        session.refresh_from_db()
        assert session.state == MessengerSession.STATE_SELECT_TIME
