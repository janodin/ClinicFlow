from datetime import timedelta

from django.contrib.auth import get_user_model
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
            price="500.00",
            is_active=True,
            display_price=True,
        )
        self.client = Client()
        self.client.login(username="owner@test.com", password="pass")

    def test_service_edit_updates_fields(self):
        url = reverse("dashboard:edit_service", args=[self.service.id])
        response = self.client.post(
            url,
            {
                "name": "Updated Consultation",
                "description": "Updated desc",
                "duration_minutes": 45,
                "price": "750.00",
                "color": "#ff0000",
                "is_active": "on",
                "display_price": "on",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.service.refresh_from_db()
        self.assertEqual(self.service.name, "Updated Consultation")
        self.assertEqual(self.service.duration_minutes, 45)
        self.assertEqual(str(self.service.price), "750.00")
        self.assertEqual(self.service.color, "#ff0000")

    def test_service_default_color_uses_neon_aqua_primary(self):
        service = Service.objects.create(
            clinic=self.clinic,
            name="Neon Aqua Default Service",
            duration_minutes=20,
            price="300.00",
        )

        self.assertEqual(service.color, "#06b6d4")

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
                "price": self.service.price,
                "is_active": "on",
            },
        )
        self.assertEqual(response.status_code, 302)  # form invalid redirects, but let's test model clean
        # Model clean is not triggered by ORM save unless full_clean is called.
        # Let's test the form directly.
        from services.forms import ServiceForm
        form = ServiceForm(self.clinic, {"duration_minutes": 0, "name": "X", "price": "1"})
        self.assertFalse(form.is_valid())
        self.assertIn("duration_minutes", form.errors)

    def test_duration_validation_rejects_over_480(self):
        from services.forms import ServiceForm
        form = ServiceForm(self.clinic, {"duration_minutes": 481, "name": "X", "price": "1"})
        self.assertFalse(form.is_valid())
        self.assertIn("duration_minutes", form.errors)

    def test_display_price_false_hides_price_in_widget_context(self):
        self.service.display_price = False
        self.service.save()
        from widget.views import _booking_context
        request = self.client.get("/").wsgi_request
        ctx = _booking_context(self.clinic, request)
        svc = ctx["services"].filter(pk=self.service.pk).first()
        self.assertIsNotNone(svc)
        self.assertFalse(svc.display_price)

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
            "price": "100.00",
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
            "price": "100.00",
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
            "price": "100.00",
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
        self.assertIn("Service deleted.", response.headers["HX-Trigger"])
        self.assertFalse(Service.objects.filter(pk=self.service.pk).exists())

    def test_create_service_duplicate_name_rejected(self):
        url = reverse("dashboard:create_service")
        response = self.client.post(url, {
            "name": "Consultation",
            "duration_minutes": 30,
            "price": "100.00",
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
