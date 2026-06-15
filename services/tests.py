import json
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.contrib.messages import get_messages
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from appointments.models import Appointment
from clinics.models import Clinic, ClinicGroup, ClinicMembership
from patients.models import Patient
from services.models import Service

User = get_user_model()


class ServiceTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username="owner@test.com", email="owner@test.com", password="pass")
        self.other_owner = User.objects.create_user(username="other@test.com", email="other@test.com", password="pass")
        self.group = ClinicGroup.objects.create(name="Test Group", owner=self.owner)
        self.clinic = Clinic.objects.create(group=self.group, name="Test Clinic", slug="test-clinic")
        ClinicMembership.objects.create(clinic=self.clinic, user=self.owner, role=ClinicMembership.ROLE_OWNER)
        self.other_group = ClinicGroup.objects.create(name="Other Group", owner=self.other_owner)
        self.other_clinic = Clinic.objects.create(group=self.other_group, name="Other Clinic", slug="other-clinic")

        self.service = Service.objects.create(
            clinic=self.clinic,
            name="Consultation",
            duration_minutes=30,
            is_active=True,
        )
        self.client = Client()
        self.client.login(username="owner@test.com", password="pass")

    def test_service_model_no_longer_exposes_pricing_fields(self):
        field_names = {field.name for field in Service._meta.get_fields()}

        self.assertNotIn("price", field_names)
        self.assertNotIn("display_price", field_names)

    def test_service_form_excludes_pricing_fields(self):
        from services.forms import ServiceForm

        form = ServiceForm(self.clinic)

        self.assertNotIn("price", form.fields)
        self.assertNotIn("display_price", form.fields)

    def test_service_edit_updates_fields(self):
        url = reverse("dashboard:edit_service", args=[self.service.id])
        response = self.client.post(
            url,
            {
                "name": "Updated Consultation",
                "description": "Updated desc",
                "duration_minutes": 45,
                "simultaneous_capacity": 1,
                "color": "#ff0000",
                "is_active": "on",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.service.refresh_from_db()
        self.assertEqual(self.service.name, "Updated Consultation")
        self.assertEqual(self.service.description, "Updated desc")
        self.assertEqual(self.service.duration_minutes, 45)
        self.assertEqual(self.service.color, "#ff0000")

    def test_service_default_color_uses_neon_aqua_primary(self):
        service = Service.objects.create(
            clinic=self.clinic,
            name="Neon Aqua Default Service",
            duration_minutes=20,
        )

        self.assertEqual(service.color, "#06b6d4")

    def test_service_default_simultaneous_capacity_is_one(self):
        service = Service.objects.create(
            clinic=self.clinic,
            name="Capacity Default Service",
            duration_minutes=20,
        )

        self.assertEqual(service.simultaneous_capacity, 1)

    def test_service_form_includes_simultaneous_capacity(self):
        from services.forms import ServiceForm

        form = ServiceForm(self.clinic)

        self.assertIn("simultaneous_capacity", form.fields)
        self.assertEqual(form.fields["simultaneous_capacity"].label, "Simultaneous capacity")
        self.assertEqual(
            form.fields["simultaneous_capacity"].help_text,
            "How many appointments for this service can run at the same time.",
        )

    def test_simultaneous_capacity_validation_rejects_zero(self):
        from services.forms import ServiceForm

        form = ServiceForm(
            self.clinic,
            {
                "name": "Invalid Capacity",
                "duration_minutes": 30,
                "simultaneous_capacity": 0,
                "color": "#06b6d4",
                "is_active": "on",
            },
        )

        self.assertFalse(form.is_valid())
        self.assertIn("simultaneous_capacity", form.errors)

    def test_simultaneous_capacity_validation_rejects_over_50(self):
        from services.forms import ServiceForm

        form = ServiceForm(
            self.clinic,
            {
                "name": "Invalid Capacity",
                "duration_minutes": 30,
                "simultaneous_capacity": 51,
                "color": "#06b6d4",
                "is_active": "on",
            },
        )

        self.assertFalse(form.is_valid())
        self.assertIn("simultaneous_capacity", form.errors)

    def test_create_service_saves_simultaneous_capacity(self):
        url = reverse("dashboard:create_service")
        response = self.client.post(
            url,
            {
                "name": "Capacity Service",
                "duration_minutes": 30,
                "simultaneous_capacity": 3,
                "color": "#ff0000",
                "is_active": "on",
            },
        )

        self.assertEqual(response.status_code, 302)
        service = self.clinic.services.get(name="Capacity Service")
        self.assertEqual(service.simultaneous_capacity, 3)

    def test_edit_service_updates_simultaneous_capacity(self):
        url = reverse("dashboard:edit_service", args=[self.service.id])
        response = self.client.post(
            url,
            {
                "name": self.service.name,
                "description": self.service.description,
                "duration_minutes": 30,
                "simultaneous_capacity": 4,
                "color": "#06b6d4",
                "is_active": "on",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.service.refresh_from_db()
        self.assertEqual(self.service.simultaneous_capacity, 4)

    def test_services_page_shows_simultaneous_capacity(self):
        self.service.simultaneous_capacity = 2
        self.service.save(update_fields=["simultaneous_capacity", "updated_at"])

        response = self.client.get(reverse("dashboard:services"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "2 at once")

    def test_services_page_places_status_tabs_before_primary_action(self):
        response = self.client.get(reverse("dashboard:services"))
        content = response.content.decode()

        self.assertEqual(response.status_code, 200)
        page_actions_index = content.index('class="cf-page-actions"')
        tabs_index = content.index("cf-tabs", page_actions_index)
        self.assertLess(page_actions_index, tabs_index)
        self.assertLess(tabs_index, content.index("Add service"))

    def test_service_archive_hides_from_active_lists(self):
        self.assertIn(self.service, self.clinic.services.filter(is_archived=False))
        url = reverse("dashboard:archive_service", args=[self.service.id])
        response = self.client.post(url)
        self.assertEqual(response.status_code, 302)
        self.service.refresh_from_db()
        self.assertTrue(self.service.is_archived)
        self.assertNotIn(self.service, self.clinic.services.filter(is_archived=False))
        self.assertIn(self.service, self.clinic.services.filter(is_archived=True))

    def test_archived_service_not_in_widget_context(self):
        self.service.is_archived = True
        self.service.save()
        from widget.views import _booking_context
        request = self.client.get("/").wsgi_request
        ctx = _booking_context(self.clinic, request)
        self.assertNotIn(self.service, ctx["services"])

    def test_duration_validation_rejects_zero(self):
        url = reverse("dashboard:edit_service", args=[self.service.id])
        response = self.client.post(
            url,
            {
                "name": self.service.name,
                "duration_minutes": 0,
                "is_active": "on",
            },
        )
        self.assertEqual(response.status_code, 302)  # form invalid redirects, but let's test model clean
        # Model clean is not triggered by ORM save unless full_clean is called.
        # Let's test the form directly.
        from services.forms import ServiceForm
        form = ServiceForm(self.clinic, {"duration_minutes": 0, "name": "X"})
        self.assertFalse(form.is_valid())
        self.assertIn("duration_minutes", form.errors)

    def test_duration_validation_rejects_over_480(self):
        from services.forms import ServiceForm
        form = ServiceForm(self.clinic, {"duration_minutes": 481, "name": "X"})
        self.assertFalse(form.is_valid())
        self.assertIn("duration_minutes", form.errors)

    def test_service_clinic_isolation(self):
        other_service = Service.objects.create(clinic=self.other_clinic, name="Other Service", duration_minutes=30)
        url = reverse("dashboard:edit_service", args=[other_service.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)
        response = self.client.post(url, {"name": "Hacked"})
        self.assertEqual(response.status_code, 404)

    def test_restore_service(self):
        self.service.is_archived = True
        self.service.save()
        url = reverse("dashboard:restore_service", args=[self.service.id])
        response = self.client.post(url)
        self.assertEqual(response.status_code, 302)
        self.service.refresh_from_db()
        self.assertFalse(self.service.is_archived)

    def test_create_service(self):
        url = reverse("dashboard:create_service")
        response = self.client.post(url, {
            "name": "New Service",
            "duration_minutes": 30,
            "simultaneous_capacity": 1,
            "color": "#ff0000",
            "is_active": "on",
        })
        self.assertEqual(response.status_code, 302)
        self.assertTrue(self.clinic.services.filter(name="New Service").exists())

    def test_create_service_htmx(self):
        url = reverse("dashboard:create_service")
        response = self.client.post(url, {
            "name": "HTMX Service",
            "duration_minutes": 30,
            "simultaneous_capacity": 1,
            "color": "#ff0000",
            "is_active": "on",
        }, HTTP_HX_REQUEST="true")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(self.clinic.services.filter(name="HTMX Service").exists())
        self.assertIn("HX-Trigger", response.headers)
        self.assertIn("HX-Retarget", response.headers)

    def test_toggle_service_htmx(self):
        url = reverse("dashboard:toggle_service", args=[self.service.id])
        response = self.client.post(url, HTTP_HX_REQUEST="true")
        self.assertEqual(response.status_code, 200)
        self.assertIn("HX-Retarget", response.headers)
        self.assertIn("HX-Trigger", response.headers)
        self.service.refresh_from_db()
        self.assertFalse(self.service.is_active)

    def test_edit_service_htmx_response(self):
        url = reverse("dashboard:edit_service", args=[self.service.id])
        response = self.client.post(url, {
            "name": "Updated via HTMX",
            "duration_minutes": 30,
            "simultaneous_capacity": 1,
            "color": "#ff0000",
            "is_active": "on",
        }, HTTP_HX_REQUEST="true")
        self.assertEqual(response.status_code, 200)
        self.assertIn("HX-Retarget", response.headers)
        self.assertIn("HX-Reswap", response.headers)
        self.assertIn("HX-Trigger", response.headers)
        self.assertIn(b"Updated via HTMX", response.content)

    def test_archive_service_htmx(self):
        url = reverse("dashboard:archive_service", args=[self.service.id])
        response = self.client.post(url, HTTP_HX_REQUEST="true")
        self.assertEqual(response.status_code, 200)
        self.assertIn("HX-Trigger", response.headers)
        self.assertIn("HX-Retarget", response.headers)
        self.service.refresh_from_db()
        self.assertTrue(self.service.is_archived)

    def test_restore_service_htmx(self):
        self.service.is_archived = True
        self.service.save()
        url = reverse("dashboard:restore_service", args=[self.service.id])
        response = self.client.post(url, HTTP_HX_REQUEST="true")
        self.assertEqual(response.status_code, 200)
        self.assertIn("HX-Trigger", response.headers)
        self.assertIn("HX-Retarget", response.headers)
        self.service.refresh_from_db()
        self.assertFalse(self.service.is_archived)

    def test_delete_archived_service_without_appointments(self):
        self.service.is_archived = True
        self.service.save(update_fields=["is_archived"])
        url = reverse("dashboard:delete_service", args=[self.service.id])

        response = self.client.post(url)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("dashboard:services"))
        self.assertFalse(Service.objects.filter(pk=self.service.pk).exists())

    def test_delete_active_service_is_blocked_until_archived(self):
        url = reverse("dashboard:delete_service", args=[self.service.id])

        response = self.client.post(url)

        self.assertEqual(response.status_code, 302)
        self.assertIn(
            "Archive this service before deleting it permanently.",
            [message.message for message in get_messages(response.wsgi_request)],
        )
        self.service.refresh_from_db()
        self.assertFalse(self.service.is_archived)

    def test_delete_service_with_appointments_is_blocked(self):
        self.service.is_archived = True
        self.service.save(update_fields=["is_archived"])
        patient = Patient.objects.create(clinic=self.clinic, full_name="Test Patient", phone="09171234567")
        starts_at = timezone.now() + timedelta(days=1)
        Appointment.objects.create(
            clinic=self.clinic,
            patient=patient,
            service=self.service,
            starts_at=starts_at,
            ends_at=starts_at + timedelta(minutes=self.service.duration_minutes),
        )
        url = reverse("dashboard:delete_service", args=[self.service.id])

        response = self.client.post(url)

        self.assertEqual(response.status_code, 302)
        self.assertIn(
            "Services with appointment history cannot be deleted. Keep it archived for records.",
            [message.message for message in get_messages(response.wsgi_request)],
        )
        self.assertTrue(Service.objects.filter(pk=self.service.pk).exists())

    def test_delete_service_requires_post(self):
        self.service.is_archived = True
        self.service.save(update_fields=["is_archived"])
        url = reverse("dashboard:delete_service", args=[self.service.id])

        response = self.client.get(url)

        self.assertEqual(response.status_code, 405)
        self.assertTrue(Service.objects.filter(pk=self.service.pk).exists())

    def test_delete_service_htmx_refreshes_service_list(self):
        self.service.is_archived = True
        self.service.save(update_fields=["is_archived"])
        url = reverse("dashboard:delete_service", args=[self.service.id])

        response = self.client.post(url, HTTP_HX_REQUEST="true")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["HX-Retarget"], "#services-list-container")
        self.assertEqual(response.headers["HX-Reswap"], "innerHTML")
        hx_trigger = json.loads(response.headers["HX-Trigger"])
        self.assertIn("toast-message", hx_trigger)
        self.assertEqual(hx_trigger["toast-message"]["message"], "Service deleted.")
        self.assertFalse(Service.objects.filter(pk=self.service.pk).exists())

    def test_create_service_duplicate_name_rejected(self):
        url = reverse("dashboard:create_service")
        response = self.client.post(url, {
            "name": "Consultation",
            "duration_minutes": 30,
            "simultaneous_capacity": 1,
            "color": "#ff0000",
        }, HTTP_HX_REQUEST="true")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "already exists")

    def test_unauthenticated_access_denied(self):
        self.client.logout()
        for url_name in ["services", "create_service", "toggle_service", "archive_service", "restore_service", "delete_service"]:
            args = [self.service.id] if url_name != "services" and url_name != "create_service" else []
            url = reverse(f"dashboard:{url_name}", args=args)
            method = "get" if url_name == "services" or url_name == "edit_service" else "post"
            response = getattr(self.client, method)(url)
            self.assertIn(response.status_code, [302, 403], f"{url_name} should redirect or deny")

    def test_service_clinic_isolation_expanded(self):
        other_service = Service.objects.create(clinic=self.other_clinic, name="Other Service", duration_minutes=30)
        for url_name in ["edit_service", "toggle_service", "archive_service", "restore_service", "delete_service"]:
            url = reverse(f"dashboard:{url_name}", args=[other_service.id])
            if url_name == "edit_service":
                self.assertEqual(self.client.get(url).status_code, 404)
            response = self.client.post(url)
            self.assertEqual(response.status_code, 404, f"{url_name} should 404 for other clinic service")
