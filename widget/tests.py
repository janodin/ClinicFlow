from datetime import datetime, time, timedelta, timezone as dt_timezone
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

    def test_embed_js_returns_javascript(self):
        resp = self.client.get(reverse("widget:embed_js", args=[self.clinic.slug]))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["Content-Type"], "application/javascript")
        self.assertIn("clinicflow-minimize", resp.content.decode())

    def test_embed_js_uses_accessible_icon_only_calendar_launcher(self):
        response = self.client.get(reverse("widget:embed_js", args=[self.clinic.slug]))
        content = response.content.decode()

        self.assertIn("var launcher = document.createElement('button');", content)
        self.assertIn("launcher.setAttribute('type', 'button');", content)
        self.assertIn("launcher.setAttribute('aria-label', 'Open booking widget');", content)
        self.assertIn("launcher.setAttribute('title', 'Book an appointment');", content)
        self.assertIn('aria-hidden="true"', content)
        self.assertIn("M8 2v4", content)
        self.assertNotIn("M21 15a2", content)
        self.assertNotIn("Book now", content)
        self.assertIn("outlineColor", content)

    def test_embed_js_opens_iframe_from_launcher_click_path(self):
        response = self.client.get(reverse("widget:embed_js", args=[self.clinic.slug]))
        content = response.content.decode()

        click_index = content.index("launcher.addEventListener('click'")
        iframe_create_index = content.index("iframe = document.createElement('iframe');")
        iframe_append_index = content.index("document.body.appendChild(iframe);")
        launcher_append_index = content.index("document.body.appendChild(launcher);")

        self.assertGreater(iframe_create_index, click_index)
        self.assertGreater(iframe_append_index, click_index)
        self.assertGreater(launcher_append_index, iframe_append_index)
        self.assertIn("?source=embed", content)
        self.assertIn("launcher.style.display = 'none';", content)
        self.assertIn("clinicflow-minimize", content)
        self.assertIn("iframe.style.display = 'none';", content)
        self.assertIn("launcher.style.display = 'flex';", content)

    def test_embed_js_uses_safe_accent_color_for_invalid_stored_value(self):
        Clinic.objects.filter(pk=self.clinic.pk).update(widget_accent_color='";alert(1)//')

        response = self.client.get(reverse("widget:embed_js", args=[self.clinic.slug]))
        content = response.content.decode()

        self.assertNotIn("alert(1)", content)
        self.assertIn("#06b6d4", content)

    def test_safe_widget_accent_color_falls_back_for_invalid_stored_value(self):
        Clinic.objects.filter(pk=self.clinic.pk).update(widget_accent_color='";alert(1)//')
        self.clinic.refresh_from_db()
        self.assertEqual(self.clinic.safe_widget_accent_color, "#06b6d4")

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

    def test_widget_minimize_preserves_in_memory_state(self):
        response = self.client.get(reverse("widget:home", args=[self.clinic.slug]))
        content = response.content.decode()

        minimize_start = content.index("minimize() {")
        minimize_end = content.index("startChat()", minimize_start)
        minimize_block = content[minimize_start:minimize_end]

        self.assertIn("clinicflow-minimize", minimize_block)
        self.assertNotIn("this.mode = 'home'", minimize_block)

    def test_widget_header_includes_home_and_minimize_controls(self):
        response = self.client.get(reverse("widget:home", args=[self.clinic.slug]))
        content = response.content.decode()

        header_start = content.index("<header")
        header_end = content.index("</header>", header_start)
        header = content[header_start:header_end]

        self.assertIn('class="flex items-center gap-1"', header)
        self.assertIn('@click="goHome()"', header)
        self.assertIn('aria-label="Go to widget home"', header)
        self.assertIn('data-lucide="home"', header)
        self.assertIn('@click="minimize()"', header)
        self.assertIn('aria-label="Minimize"', header)
        self.assertLess(header.index('@click="goHome()"'), header.index('@click="minimize()"'))

    def test_widget_home_button_resets_in_memory_state(self):
        response = self.client.get(reverse("widget:home", args=[self.clinic.slug]))
        content = response.content.decode()
        selected_date = response.context["selected_date"].strftime("%Y-%m-%d")

        go_home_start = content.index("goHome() {")
        go_home_end = content.index("minimize()", go_home_start)
        go_home_block = content[go_home_start:go_home_end]

        expected_resets = [
            "this.mode = 'home';",
            "this.bookStep = 1;",
            "this.selectedService = '';",
            f"this.date = '{selected_date}';",
            "this.slot = '';",
            "this.chatTab = 'conversation';",
            "this.chatHistory = [];",
            "this.chatOptions = [];",
            "this.chatState = 'greeting';",
            "this.chatInput = '';",
            "this.faqQuery = '';",
            "this.collectInfo = { full_name: '', phone: '', email: '' };",
        ]
        for reset in expected_resets:
            with self.subTest(reset=reset):
                self.assertIn(reset, go_home_block)

        self.assertNotIn("localStorage", go_home_block)
        self.assertNotIn("sessionStorage", go_home_block)
        self.assertNotIn("fetch(", go_home_block)
        self.assertNotIn("htmx.ajax", go_home_block)
        self.assertNotIn("this.loadSlots", go_home_block)
        self.assertNotIn("this.sendChatAction", go_home_block)
        self.assertNotIn("this.startChat", go_home_block)

        minimize_start = content.index("minimize() {")
        minimize_end = content.index("startChat()", minimize_start)
        minimize_block = content[minimize_start:minimize_end]
        self.assertNotIn("goHome()", minimize_block)
        self.assertNotIn("this.mode = 'home'", minimize_block)

    def test_widget_home_reset_ignores_in_flight_chat_responses(self):
        response = self.client.get(reverse("widget:home", args=[self.clinic.slug]))
        content = response.content.decode()

        self.assertIn("stateResetVersion: 0,", content)

        go_home_start = content.index("goHome() {")
        go_home_end = content.index("minimize()", go_home_start)
        go_home_block = content[go_home_start:go_home_end]
        self.assertIn("this.stateResetVersion += 1;", go_home_block)

        send_chat_start = content.index("async sendChatAction(")
        send_chat_end = content.index("selectChatOption", send_chat_start)
        send_chat_block = content[send_chat_start:send_chat_end]

        self.assertIn("const stateResetVersion = this.stateResetVersion;", send_chat_block)
        self.assertIn("if (stateResetVersion !== this.stateResetVersion) return;", send_chat_block)
        self.assertLess(
            send_chat_block.index("const stateResetVersion = this.stateResetVersion;"),
            send_chat_block.index("const resp = await fetch"),
        )
        self.assertLess(
            send_chat_block.index("if (stateResetVersion !== this.stateResetVersion) return;"),
            send_chat_block.index("this.chatState = data.state;"),
        )

    def test_onboarding_clinic_public_widget_endpoints_are_unavailable(self):
        Clinic.objects.filter(pk=self.clinic.pk).update(requires_onboarding=True)

        cases = [
            ("get", reverse("widget:home", args=[self.clinic.slug]), {}),
            ("get", reverse("widget:slots", args=[self.clinic.slug]), {}),
            ("get", reverse("widget:embed_js", args=[self.clinic.slug]), {}),
            ("get", reverse("widget:chat_api", args=[self.clinic.slug]), {}),
            ("post", reverse("widget:chat_step", args=[self.clinic.slug]), {"action": "init"}),
            ("post", reverse("widget:book", args=[self.clinic.slug]), {}),
        ]
        for method, url, data in cases:
            with self.subTest(url=url):
                response = getattr(self.client, method)(url, data)
                self.assertEqual(response.status_code, 404)

    def test_widget_home_uses_plain_preview_background(self):
        response = self.client.get(reverse("widget:home", args=[self.clinic.slug]))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "cf-gradient-mesh")

    def test_widget_accent_color_is_escaped_in_script(self):
        dangerous = '";alert(1)//'
        Clinic.objects.filter(pk=self.clinic.pk).update(widget_accent_color=dangerous)

        response = self.client.get(reverse("widget:home", args=[self.clinic.slug]))
        content = response.content.decode()

        self.assertNotIn(dangerous, content)
        self.assertNotIn("alert(1)", content)
        self.assertIn("#06b6d4", content)
        self.assertIn("accentColor:", content)

    def test_widget_slots_returns_partial(self):
        tomorrow = (timezone.localdate() + timedelta(days=1)).isoformat()
        resp = self.client.get(reverse("widget:slots", args=[self.clinic.slug]), {"service": self.service.id, "date": tomorrow})
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, "widget/partials/slots.html")

    def test_widget_date_options_use_clinic_timezone(self):
        Clinic.objects.filter(pk=self.clinic.pk).update(timezone="America/New_York")
        fixed_now = datetime(2026, 6, 2, 2, 0, tzinfo=dt_timezone.utc)

        with patch("widget.views.timezone.now", return_value=fixed_now):
            response = self.client.get(reverse("widget:home", args=[self.clinic.slug]))

        first_date = response.context["dates"][0]
        self.assertEqual(first_date.isoformat(), "2026-06-02")

    def test_widget_renders_reason_field_when_enabled(self):
        Clinic.objects.filter(pk=self.clinic.pk).update(show_reason_field=True)

        response = self.client.get(reverse("widget:home", args=[self.clinic.slug]))

        self.assertContains(response, 'name="reason"')

    def test_widget_omits_reason_field_when_disabled(self):
        Clinic.objects.filter(pk=self.clinic.pk).update(show_reason_field=False)

        response = self.client.get(reverse("widget:home", args=[self.clinic.slug]))

        self.assertNotContains(response, 'name="reason"')

    def test_widget_chat_initial_state_has_no_quick_button_suggestions(self):
        response = self.client.get(reverse("widget:home", args=[self.clinic.slug]))
        content = response.content.decode()

        self.assertIn("opt.type === 'ai_prompt'", content)
        self.assertIn("this.sendChatAction('text_input', opt.value);", content)
        self.assertIn("chatState !== 'collect_info'", content)
        self.assertNotIn("Book an appointment</button>", content)
        self.assertNotIn("Ask about services</button>", content)

    def test_widget_chat_scrolls_conversation_container_after_ai_reply(self):
        response = self.client.get(reverse("widget:home", args=[self.clinic.slug]))
        content = response.content.decode()

        conversation_start = content.index("<!-- Conversation -->")
        conversation_end = content.index("<!-- FAQs -->", conversation_start)
        conversation_markup = content[conversation_start:conversation_end]
        self.assertIn('x-ref="chatConversation"', conversation_markup)

        send_chat_start = content.index("async sendChatAction(")
        send_chat_end = content.index("selectChatOption", send_chat_start)
        send_chat_block = content[send_chat_start:send_chat_end]
        scroll_helper_start = content.index("scrollChatConversation() {")
        scroll_helper_end = content.index("async sendChatAction(", scroll_helper_start)
        scroll_helper_block = content[scroll_helper_start:scroll_helper_end]

        self.assertIn("this.scrollChatConversation();", send_chat_block)
        self.assertIn("const container = this.$refs.chatConversation;", scroll_helper_block)
        self.assertIn("container.scrollTop = container.scrollHeight;", scroll_helper_block)
        self.assertNotIn("querySelector('.flex-1.overflow-y-auto')", scroll_helper_block)

    def test_widget_chat_renders_assistant_typing_indicator_inside_conversation(self):
        response = self.client.get(reverse("widget:home", args=[self.clinic.slug]))
        content = response.content.decode()

        conversation_start = content.index("<!-- Conversation -->")
        conversation_end = content.index("<!-- FAQs -->", conversation_start)
        conversation_markup = content[conversation_start:conversation_end]

        self.assertIn('x-show="isAssistantTyping"', conversation_markup)
        self.assertIn('role="status"', conversation_markup)
        self.assertIn('aria-live="polite"', conversation_markup)
        self.assertIn("Assistant is typing", conversation_markup)
        self.assertIn("animate-bounce", conversation_markup)

    def test_widget_chat_toggles_typing_indicator_around_ai_fetch(self):
        response = self.client.get(reverse("widget:home", args=[self.clinic.slug]))
        content = response.content.decode()

        self.assertIn("isAssistantTyping: false,", content)

        go_home_start = content.index("goHome() {")
        go_home_end = content.index("minimize()", go_home_start)
        go_home_block = content[go_home_start:go_home_end]
        self.assertIn("this.isAssistantTyping = false;", go_home_block)

        send_chat_start = content.index("async sendChatAction(")
        send_chat_end = content.index("selectChatOption", send_chat_start)
        send_chat_block = content[send_chat_start:send_chat_end]

        self.assertIn("this.isAssistantTyping = true;", send_chat_block)
        self.assertIn("try {", send_chat_block)
        self.assertIn("finally {", send_chat_block)
        self.assertIn("this.isAssistantTyping = false;", send_chat_block)
        self.assertLess(
            send_chat_block.index("this.isAssistantTyping = true;"),
            send_chat_block.index("const resp = await fetch"),
        )
        self.assertLess(
            send_chat_block.index("finally {"),
            send_chat_block.rindex("this.isAssistantTyping = false;"),
        )
        self.assertIn("this.scrollChatConversation();", send_chat_block)

    @override_settings(ASSISTANT_N8N_WEBHOOK_URL="https://n8n.example/webhook/widget", N8N_WEBHOOK_SECRET="secret")
    @patch("widget.ai_client.requests.post")
    def test_chat_step_ai_init_does_not_return_quick_button_options(self, mock_post):
        ClinicAISettings.objects.create(clinic=self.clinic, is_ai_enabled=True)

        response = self.client.post(reverse("widget:chat_step", args=[self.clinic.slug]), {"action": "init"})

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["state"], "ai")
        self.assertEqual(data["next_action"], "text_input")
        self.assertIn("book", data["message"].lower())
        self.assertEqual(data["options"], [])
        self.assertNotIn(data["state"], ["select_service", "select_date", "select_time", "collect_info", "confirm"])
        mock_post.assert_not_called()

    @override_settings(ASSISTANT_N8N_WEBHOOK_URL="https://n8n.example/webhook/widget", N8N_WEBHOOK_SECRET="secret")
    @patch("widget.ai_client.requests.post")
    def test_chat_step_ai_book_suggestion_calls_n8n_as_natural_text(self, mock_post):
        ClinicAISettings.objects.create(clinic=self.clinic, is_ai_enabled=True)
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {"reply": "Sure, what service would you like?"}

        response = self.client.post(
            reverse("widget:chat_step", args=[self.clinic.slug]),
            {"action": "select_option", "value": "I want to book an appointment"},
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["state"], "ai")
        self.assertEqual(data["message"], "Sure, what service would you like?")
        self.assertEqual(data["options"], [])
        self.assertEqual(data["next_action"], "text_input")
        payload = mock_post.call_args.kwargs["json"]
        self.assertEqual(payload["channel"], "widget")
        self.assertEqual(payload["clinic_slug"], self.clinic.slug)
        self.assertEqual(payload["message"], "I want to book an appointment")

    @override_settings(ASSISTANT_N8N_WEBHOOK_URL="https://n8n.example/webhook/widget", N8N_WEBHOOK_SECRET="secret")
    @patch("widget.ai_client.requests.post")
    def test_chat_step_ai_legacy_booking_control_maps_to_natural_text(self, mock_post):
        ClinicAISettings.objects.create(clinic=self.clinic, is_ai_enabled=True)
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {"reply": "Sure, what service would you like?"}

        response = self.client.post(
            reverse("widget:chat_step", args=[self.clinic.slug]),
            {"action": "select_option", "value": "start_booking"},
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["state"], "ai")
        payload = mock_post.call_args.kwargs["json"]
        self.assertEqual(payload["message"], "I want to book an appointment")

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

    def test_widget_booking_rejects_invalid_email(self):
        tomorrow = timezone.localdate() + timedelta(days=1)
        slot = generate_slots(self.clinic, self.service, tomorrow)[0]

        resp = self.client.post(
            reverse("widget:book", args=[self.clinic.slug]),
            {
                "service": self.service.id,
                "starts_at": slot["starts_at"].isoformat(),
                "full_name": "Invalid Email",
                "phone": "09170001111",
                "email": "not-an-email",
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
        data = response.json()
        self.assertEqual(data["state"], "ai")
        self.assertEqual(data["message"], "I can help you book.")
        self.assertEqual(data["options"], [])
        self.assertEqual(data["next_action"], "text_input")
        payload = mock_post.call_args.kwargs["json"]
        self.assertEqual(payload["channel"], "widget")
        self.assertEqual(payload["clinic_slug"], self.clinic.slug)
        self.assertEqual(payload["message"], "Can I book tomorrow?")

    @override_settings(ASSISTANT_N8N_WEBHOOK_URL="https://n8n.example/webhook/widget", N8N_WEBHOOK_SECRET="secret")
    @patch("widget.ai_client.requests.post")
    def test_chat_step_ai_history_is_passed_and_capped(self, mock_post):
        ClinicAISettings.objects.create(clinic=self.clinic, is_ai_enabled=True)
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {"reply": "Reply from AI."}
        url = reverse("widget:chat_step", args=[self.clinic.slug])

        for index in range(7):
            self.client.post(url, {"action": "text_input", "value": f"Question {index}"})

        response = self.client.post(url, {"action": "text_input", "value": "Latest question"})

        self.assertEqual(response.status_code, 200)
        payload = mock_post.call_args.kwargs["json"]
        self.assertEqual(payload["message"], "Latest question")
        self.assertLessEqual(len(payload["history"]), 10)
        self.assertIn({"role": "assistant", "content": "Reply from AI."}, payload["history"])

    @override_settings(ASSISTANT_N8N_WEBHOOK_URL="https://n8n.example/webhook/widget", N8N_WEBHOOK_SECRET="secret")
    @patch("widget.ai_client.requests.post")
    def test_chat_step_legacy_guided_actions_do_not_enter_guided_state_when_ai_enabled(self, mock_post):
        ClinicAISettings.objects.create(clinic=self.clinic, is_ai_enabled=True)
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {"reply": "AI is handling booking."}
        url = reverse("widget:chat_step", args=[self.clinic.slug])

        response = self.client.post(url, {"action": "start_booking"})

        data = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(data["state"], "ai")
        self.assertEqual(data["message"], "AI is handling booking.")
        self.assertEqual(data["next_action"], "text_input")
        self.assertEqual(data["options"], [])
        payload = mock_post.call_args.kwargs["json"]
        self.assertEqual(payload["message"], "I want to book an appointment")

    @override_settings(ASSISTANT_N8N_WEBHOOK_URL="https://n8n.example/webhook/widget", N8N_WEBHOOK_SECRET="secret")
    @patch("widget.ai_client.requests.post")
    def test_chat_step_returns_fallback_without_n8n_when_ai_disabled(self, mock_post):
        ClinicAISettings.objects.create(
            clinic=self.clinic,
            is_ai_enabled=False,
            instructions="Shared instructions.",
            fallback_message="AI is off. Please use the booking form.",
        )

        url = reverse("widget:chat_step", args=[self.clinic.slug])

        for post_data in ({"action": "init"}, {"action": "text_input", "value": "Hello"}):
            with self.subTest(post_data=post_data):
                response = self.client.post(url, post_data)

                self.assertEqual(response.status_code, 200)
                data = response.json()
                self.assertEqual(data["state"], "ai")
                self.assertIn("AI is off. Please use the booking form.", data["message"])
                self.assertEqual(data["options"], [])
                self.assertEqual(data["next_action"], "text_input")

        mock_post.assert_not_called()

    @override_settings(ASSISTANT_N8N_WEBHOOK_URL="", N8N_WEBHOOK_SECRET="secret")
    def test_chat_step_returns_default_fallback_when_webhook_missing(self):
        ClinicAISettings.objects.create(clinic=self.clinic, is_ai_enabled=True, fallback_message="")

        response = self.client.post(
            reverse("widget:chat_step", args=[self.clinic.slug]),
            {"action": "text_input", "value": "Hello"},
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["state"], "ai")
        self.assertIn("assistant is unavailable", data["message"])
        self.assertEqual(data["options"], [])
