from datetime import time, timedelta

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from appointments.models import Appointment
from clinics.models import Clinic, ClinicGroup
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

    def test_embed_js_returns_javascript(self):
        resp = self.client.get(reverse("widget:embed_js", args=[self.clinic.slug]))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["Content-Type"], "application/javascript")
        self.assertIn("clinicflow-minimize", resp.content.decode())

    def test_widget_home_loads_without_doctor_controls(self):
        resp = self.client.get(reverse("widget:home", args=[self.clinic.slug]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, self.clinic.name)
        self.assertContains(resp, self.service.name)
        self.assertNotContains(resp, "Doctor")
        self.assertNotContains(resp, "First available")

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

    def test_booking_via_widget_sets_chat_widget_source(self):
        tomorrow = timezone.localdate() + timedelta(days=1)
        slot = generate_slots(self.clinic, self.service, tomorrow)[0]
        resp = self.client.post(reverse("public_booking:book", args=[self.clinic.slug]), {
            "service": self.service.id,
            "starts_at": slot["starts_at"].isoformat(),
            "full_name": "John Doe",
            "phone": "09123456789",
            "email": "john@example.com",
            "source": "chat_widget",
        })
        self.assertEqual(resp.status_code, 200)
        appt = Appointment.objects.get(clinic=self.clinic, patient__full_name="John Doe")
        self.assertEqual(appt.source, Appointment.SOURCE_CHAT_WIDGET)

    def test_booking_via_embed_sets_embed_source(self):
        tomorrow = timezone.localdate() + timedelta(days=1)
        slot = generate_slots(self.clinic, self.service, tomorrow)[0]
        resp = self.client.post(reverse("public_booking:book", args=[self.clinic.slug]), {
            "service": self.service.id,
            "starts_at": slot["starts_at"].isoformat(),
            "full_name": "Jane Doe",
            "phone": "09987654321",
            "email": "jane@example.com",
            "source": "embed",
        })
        self.assertEqual(resp.status_code, 200)
        appt = Appointment.objects.get(clinic=self.clinic, patient__full_name="Jane Doe")
        self.assertEqual(appt.source, Appointment.SOURCE_EMBED)
