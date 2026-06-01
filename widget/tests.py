from datetime import time, timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from appointments.models import Appointment
from clinics.models import Clinic, ClinicAISettings, ClinicGroup
from patients.models import Patient
from scheduling.models import ClinicBusinessHour
from scheduling.utils import generate_slots
from services.models import Service

User = get_user_model()


class WidgetTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="testuser", email="test@test.com", password="testpass")
        self.group = ClinicGroup.objects.create(name="Test Group", owner=self.user)
        self.clinic = Clinic.objects.create(group=self.group, name="Test Clinic", slug="test-clinic", timezone="Asia/Manila")
        Service.objects.create(clinic=self.clinic, name="Dummy", duration_minutes=15)
        self.service = Service.objects.create(clinic=self.clinic, name="Consultation", duration_minutes=30, price=500)
        for wd in range(7):
            ClinicBusinessHour.objects.create(clinic=self.clinic, weekday=wd, is_open=True, open_time=time(9), close_time=time(17))
        self.client = Client()

    def _drive_chat_to_collect_info(self):
        url = reverse("widget:chat_step", args=[self.clinic.slug])
        self.client.post(url, {"action": "init"})
        self.client.post(url, {"action": "select_option", "value": "start_booking"})
        self.client.post(url, {"action": "select_option", "value": str(self.service.id)})
        tomorrow = (timezone.localdate() + timedelta(days=1)).isoformat()
        data = self.client.post(url, {"action": "select_option", "value": tomorrow}).json()
        slot_value = data["options"][0]["value"]
        self.client.post(url, {"action": "select_option", "value": slot_value})
        return url

    def test_embed_js_returns_javascript(self):
        resp = self.client.get(reverse("widget:embed_js", args=[self.clinic.slug]))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["Content-Type"], "application/javascript")
        self.assertIn("clinicflow-minimize", resp.content.decode())

    def test_embed_js_uses_safe_accent_color_for_invalid_stored_value(self):
        Clinic.objects.filter(pk=self.clinic.pk).update(widget_accent_color='";alert(1)//')

        response = self.client.get(reverse("widget:embed_js", args=[self.clinic.slug]))
        content = response.content.decode()

        self.assertNotIn("alert(1)", content)
        self.assertIn("#0891b2", content)

    def test_safe_widget_accent_color_falls_back_for_invalid_stored_value(self):
        Clinic.objects.filter(pk=self.clinic.pk).update(widget_accent_color='";alert(1)//')
        self.clinic.refresh_from_db()
        self.assertEqual(self.clinic.safe_widget_accent_color, "#0891b2")

        Clinic.objects.filter(pk=self.clinic.pk).update(widget_accent_color="#123abc")
        self.clinic.refresh_from_db()
        self.assertEqual(self.clinic.safe_widget_accent_color, "#123abc")

    def test_widget_home_loads_without_doctor_controls(self):
        resp = self.client.get(reverse("widget:home", args=[self.clinic.slug]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, self.clinic.name)
        self.assertContains(resp, self.service.name)
        self.assertNotContains(resp, "Doctor")
        self.assertNotContains(resp, "First available")

    def test_widget_accent_color_is_escaped_in_script(self):
        dangerous = '";alert(1)//'
        Clinic.objects.filter(pk=self.clinic.pk).update(widget_accent_color=dangerous)

        response = self.client.get(reverse("widget:home", args=[self.clinic.slug]))
        content = response.content.decode()

        self.assertNotIn(dangerous, content)
        self.assertNotIn("alert(1)", content)
        self.assertIn("#0891b2", content)
        self.assertIn("accentColor:", content)

    def test_widget_slots_returns_partial(self):
        tomorrow = (timezone.localdate() + timedelta(days=1)).isoformat()
        resp = self.client.get(reverse("widget:slots", args=[self.clinic.slug]), {"service": self.service.id, "date": tomorrow})
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, "widget/partials/slots.html")

    def test_chat_step_state_machine_skips_doctor(self):
        url = reverse("widget:chat_step", args=[self.clinic.slug])
        self.client.post(url, {"action": "init"})
        self.client.post(url, {"action": "select_option", "value": "start_booking"})
        resp = self.client.post(url, {"action": "select_option", "value": str(self.service.id)})
        self.assertEqual(resp.json()["state"], "select_date")

        tomorrow = (timezone.localdate() + timedelta(days=1)).isoformat()
        resp = self.client.post(url, {"action": "select_option", "value": tomorrow})
        data = resp.json()
        self.assertEqual(data["state"], "select_time")
        self.assertTrue(data["options"])

        slot_value = data["options"][0]["value"]
        self.assertEqual(self.client.post(url, {"action": "select_option", "value": slot_value}).json()["state"], "collect_info")
        self.assertEqual(self.client.post(url, {"action": "submit_info", "full_name": "Chat Patient", "phone": "09111111111"}).json()["state"], "confirm")
        data = self.client.post(url, {"action": "select_option", "value": "confirm"}).json()
        self.assertEqual(data["state"], "booked")
        appt = Appointment.objects.get(clinic=self.clinic, patient__full_name="Chat Patient")
        self.assertEqual(appt.source, Appointment.SOURCE_CHAT_WIDGET)

    def test_chat_step_rejects_short_phone_before_confirmation(self):
        url = self._drive_chat_to_collect_info()

        response = self.client.post(
            url,
            {"action": "submit_info", "full_name": "Short Phone", "phone": "123456"},
        )

        data = response.json()
        self.assertEqual(data["state"], "collect_info")
        self.assertEqual(data["next_action"], "submit_info")
        self.assertIn("valid phone", data["message"])
        self.assertFalse(Appointment.objects.filter(clinic=self.clinic).exists())

    def test_chat_step_rejects_invalid_email_before_confirmation(self):
        url = self._drive_chat_to_collect_info()

        response = self.client.post(
            url,
            {
                "action": "submit_info",
                "full_name": "Invalid Email",
                "phone": "09170001111",
                "email": "not-an-email",
            },
        )

        data = response.json()
        self.assertEqual(data["state"], "collect_info")
        self.assertEqual(data["next_action"], "submit_info")
        self.assertIn("valid email", data["message"])
        self.assertFalse(Appointment.objects.filter(clinic=self.clinic).exists())

    def test_booking_via_widget_sets_chat_widget_source(self):
        tomorrow = timezone.localdate() + timedelta(days=1)
        slot = generate_slots(self.clinic, self.service, tomorrow)[0]
        resp = self.client.post(
            reverse("widget:book", args=[self.clinic.slug]),
            {
                "service": self.service.id,
                "starts_at": slot["starts_at"].isoformat(),
                "full_name": "John Doe",
                "phone": "09123456789",
                "email": "john@example.com",
                "source": "chat_widget",
            },
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(resp.status_code, 200)
        appt = Appointment.objects.get(clinic=self.clinic, patient__full_name="John Doe")
        self.assertEqual(appt.source, Appointment.SOURCE_CHAT_WIDGET)

    def test_booking_via_embed_sets_embed_source(self):
        tomorrow = timezone.localdate() + timedelta(days=1)
        slot = generate_slots(self.clinic, self.service, tomorrow)[0]
        resp = self.client.post(
            reverse("widget:book", args=[self.clinic.slug]) + "?source=embed",
            {
                "service": self.service.id,
                "starts_at": slot["starts_at"].isoformat(),
                "full_name": "Jane Doe",
                "phone": "09987654321",
                "email": "jane@example.com",
            },
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(resp.status_code, 200)
        appt = Appointment.objects.get(clinic=self.clinic, patient__full_name="Jane Doe")
        self.assertEqual(appt.source, Appointment.SOURCE_EMBED)

    def test_widget_booking_rejects_blank_identity(self):
        tomorrow = timezone.localdate() + timedelta(days=1)
        slot = generate_slots(self.clinic, self.service, tomorrow)[0]

        resp = self.client.post(
            reverse("widget:book", args=[self.clinic.slug]),
            {
                "service": self.service.id,
                "starts_at": slot["starts_at"].isoformat(),
                "full_name": "   ",
                "phone": "   ",
                "email": "",
            },
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(resp.status_code, 409)
        self.assertFalse(Patient.objects.filter(clinic=self.clinic).exists())
        self.assertFalse(Appointment.objects.filter(clinic=self.clinic).exists())

    def test_widget_booking_rejects_short_phone(self):
        tomorrow = timezone.localdate() + timedelta(days=1)
        slot = generate_slots(self.clinic, self.service, tomorrow)[0]

        resp = self.client.post(
            reverse("widget:book", args=[self.clinic.slug]),
            {
                "service": self.service.id,
                "starts_at": slot["starts_at"].isoformat(),
                "full_name": "Short Phone",
                "phone": "123456",
                "email": "short@example.com",
            },
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(resp.status_code, 409)
        self.assertFalse(Patient.objects.filter(clinic=self.clinic).exists())
        self.assertFalse(Appointment.objects.filter(clinic=self.clinic).exists())

    def test_widget_booking_does_not_overwrite_existing_patient_by_phone(self):
        patient = Patient.objects.create(
            clinic=self.clinic,
            full_name="Existing Patient",
            phone="09123456789",
            email="existing@example.com",
            notes="Existing notes",
        )
        tomorrow = timezone.localdate() + timedelta(days=1)
        slot = generate_slots(self.clinic, self.service, tomorrow)[0]

        resp = self.client.post(
            reverse("widget:book", args=[self.clinic.slug]),
            {
                "service": self.service.id,
                "starts_at": slot["starts_at"].isoformat(),
                "full_name": "Tampered Patient Name",
                "phone": "0912-345-6789",
                "email": "new@example.com",
                "reason": "New notes",
            },
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(resp.status_code, 200)
        appointment = Appointment.objects.get(clinic=self.clinic)
        self.assertEqual(appointment.patient, patient)
        patient.refresh_from_db()
        self.assertEqual(patient.full_name, "Existing Patient")
        self.assertEqual(patient.email, "existing@example.com")
        self.assertEqual(patient.notes, "Existing notes")

    def test_widget_booking_ignores_tampered_source(self):
        tomorrow = timezone.localdate() + timedelta(days=1)
        slot = generate_slots(self.clinic, self.service, tomorrow)[0]

        resp = self.client.post(
            reverse("widget:book", args=[self.clinic.slug]),
            {
                "service": self.service.id,
                "starts_at": slot["starts_at"].isoformat(),
                "full_name": "Source Tamper",
                "phone": "09123456789",
                "email": "source@example.com",
                "source": "embed",
            },
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(resp.status_code, 200)
        appointment = Appointment.objects.get(clinic=self.clinic, patient__full_name="Source Tamper")
        self.assertEqual(appointment.source, Appointment.SOURCE_CHAT_WIDGET)

    def test_widget_booking_uses_embed_source_from_query_string(self):
        tomorrow = timezone.localdate() + timedelta(days=1)
        slot = generate_slots(self.clinic, self.service, tomorrow)[0]

        resp = self.client.post(
            reverse("widget:book", args=[self.clinic.slug]) + "?source=embed",
            {
                "service": self.service.id,
                "starts_at": slot["starts_at"].isoformat(),
                "full_name": "Embed Source",
                "phone": "09123456789",
                "email": "embed@example.com",
            },
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(resp.status_code, 200)
        appointment = Appointment.objects.get(clinic=self.clinic, patient__full_name="Embed Source")
        self.assertEqual(appointment.source, Appointment.SOURCE_EMBED)

    def test_widget_booking_rejects_cross_clinic_service_tampering(self):
        other_group = ClinicGroup.objects.create(name="Other Group", owner=self.user)
        other_clinic = Clinic.objects.create(group=other_group, name="Other Clinic", slug="other-clinic", timezone="Asia/Manila")
        other_service = Service.objects.create(clinic=other_clinic, name="Other Consultation", duration_minutes=30)
        for wd in range(7):
            ClinicBusinessHour.objects.create(clinic=other_clinic, weekday=wd, is_open=True, open_time=time(9), close_time=time(17))
        tomorrow = timezone.localdate() + timedelta(days=1)
        slot = generate_slots(other_clinic, other_service, tomorrow)[0]

        response = self.client.post(
            reverse("widget:book", args=[self.clinic.slug]),
            {
                "service": other_service.id,
                "starts_at": slot["starts_at"].isoformat(),
                "full_name": "Cross Clinic Tamper",
                "phone": "09170001111",
                "email": "tamper@example.com",
            },
            HTTP_HX_REQUEST="true",
        )

        self.assertIn(response.status_code, (404, 409))
        self.assertFalse(Appointment.objects.filter(clinic__in=[self.clinic, other_clinic]).exists())
        self.assertFalse(Patient.objects.filter(clinic__in=[self.clinic, other_clinic], full_name="Cross Clinic Tamper").exists())

    @override_settings(ASSISTANT_N8N_WEBHOOK_URL="https://n8n.example/webhook/widget", N8N_WEBHOOK_SECRET="secret")
    @patch("widget.ai_client.requests.post")
    def test_chat_step_text_input_calls_n8n_when_ai_enabled(self, mock_post):
        ClinicAISettings.objects.create(
            clinic=self.clinic,
            is_ai_enabled=True,
            instructions="Shared instructions.",
            fallback_message="Fallback response.",
        )
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {"reply": "I can help you book."}

        response = self.client.post(
            reverse("widget:chat_step", args=[self.clinic.slug]),
            {"action": "text_input", "value": "Can I book tomorrow?"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["message"], "I can help you book.")
        payload = mock_post.call_args.kwargs["json"]
        self.assertEqual(payload["channel"], "widget")
        self.assertEqual(payload["clinic_slug"], self.clinic.slug)
        self.assertEqual(payload["message"], "Can I book tomorrow?")

    @override_settings(ASSISTANT_N8N_WEBHOOK_URL="https://n8n.example/webhook/widget", N8N_WEBHOOK_SECRET="secret")
    @patch("widget.ai_client.requests.post")
    def test_chat_step_text_input_calls_n8n_during_select_date(self, mock_post):
        ClinicAISettings.objects.create(clinic=self.clinic, is_ai_enabled=True)
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {"reply": "AI can help with dates."}
        url = reverse("widget:chat_step", args=[self.clinic.slug])
        self.client.post(url, {"action": "init"})
        self.client.post(url, {"action": "select_option", "value": "start_booking"})
        self.client.post(url, {"action": "select_option", "value": str(self.service.id)})

        response = self.client.post(url, {"action": "text_input", "value": "hi"})

        data = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(data["state"], "select_date")
        self.assertEqual(data["message"], "AI can help with dates.")
        self.assertNotEqual(data["message"], "What date works for you?")
        self.assertEqual(data["next_action"], "select_option")
        self.assertTrue(data["options"])
        mock_post.assert_called_once()
        payload = mock_post.call_args.kwargs["json"]
        self.assertIn("hi", payload["message"])
        self.assertIn("select_date", payload["message"])
        self.assertIn(self.service.name, payload["message"])

    @override_settings(ASSISTANT_N8N_WEBHOOK_URL="https://n8n.example/webhook/widget", N8N_WEBHOOK_SECRET="secret")
    @patch("widget.ai_client.requests.post")
    def test_chat_step_text_input_calls_n8n_during_select_time(self, mock_post):
        ClinicAISettings.objects.create(clinic=self.clinic, is_ai_enabled=True)
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {"reply": "AI can answer about this date."}
        url = reverse("widget:chat_step", args=[self.clinic.slug])
        selected_date = (timezone.localdate() + timedelta(days=1)).isoformat()
        self.client.post(url, {"action": "init"})
        self.client.post(url, {"action": "select_option", "value": "start_booking"})
        self.client.post(url, {"action": "select_option", "value": str(self.service.id)})
        self.client.post(url, {"action": "select_option", "value": selected_date})

        response = self.client.post(url, {"action": "text_input", "value": "what date is this"})

        data = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(data["state"], "select_time")
        self.assertEqual(data["message"], "AI can answer about this date.")
        self.assertNotEqual(data["message"], "Here are the available times:")
        self.assertEqual(data["next_action"], "select_option")
        self.assertTrue(data["options"])
        self.assertIn("AM", data["options"][0]["label"])
        mock_post.assert_called_once()
        payload = mock_post.call_args.kwargs["json"]
        self.assertIn("what date is this", payload["message"])
        self.assertIn("select_time", payload["message"])
        self.assertIn(selected_date, payload["message"])

    @override_settings(ASSISTANT_N8N_WEBHOOK_URL="https://n8n.example/webhook/widget", N8N_WEBHOOK_SECRET="secret")
    @patch("widget.ai_client.requests.post")
    def test_chat_step_returns_fallback_without_n8n_when_ai_disabled(self, mock_post):
        ClinicAISettings.objects.create(
            clinic=self.clinic,
            is_ai_enabled=False,
            instructions="Shared instructions.",
            fallback_message="AI is off. Please use the booking form.",
        )

        response = self.client.post(
            reverse("widget:chat_step", args=[self.clinic.slug]),
            {"action": "text_input", "value": "Hello"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["message"], "AI is off. Please use the booking form.")
        mock_post.assert_not_called()

    @override_settings(ASSISTANT_N8N_WEBHOOK_URL="", N8N_WEBHOOK_SECRET="secret")
    def test_chat_step_returns_default_fallback_when_webhook_missing(self):
        ClinicAISettings.objects.create(clinic=self.clinic, is_ai_enabled=True, fallback_message="")

        response = self.client.post(
            reverse("widget:chat_step", args=[self.clinic.slug]),
            {"action": "text_input", "value": "Hello"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("assistant is unavailable", response.json()["message"])
