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


from datetime import date, timedelta
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
