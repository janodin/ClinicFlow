from datetime import datetime, time, timedelta, timezone as dt_timezone
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.cache import cache
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from appointments.models import Appointment
from clinics.models import Clinic, ClinicAISettings, ClinicGroup
from patients.models import Patient
from scheduling.models import ClinicBusinessHour
from scheduling.utils import generate_slots
from services.models import Service
from widget.views import _process_guest_booking

User = get_user_model()


class WidgetTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(username="testuser", email="test@test.com", password="testpass")
        self.group = ClinicGroup.objects.create(name="Test Group", owner=self.user)
        self.clinic = Clinic.objects.create(group=self.group, name="Test Clinic", slug="test-clinic", timezone="Asia/Manila")
        Service.objects.create(clinic=self.clinic, name="Dummy", duration_minutes=15)
        self.service = Service.objects.create(clinic=self.clinic, name="Consultation", duration_minutes=30)
        for wd in range(7):
            ClinicBusinessHour.objects.create(clinic=self.clinic, weekday=wd, is_open=True, open_time=time(9), close_time=time(17))
        self.client = Client()

    def test_embed_js_returns_javascript(self):
        resp = self.client.get(reverse("widget:embed_js", args=[self.clinic.slug]))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["Content-Type"], "application/javascript")
        self.assertIn("kliniassist-minimize", resp.content.decode())

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
        self.assertIn("kliniassist-minimize", content)
        self.assertIn("iframe.style.display = 'none';", content)
        self.assertIn("launcher.style.display = 'flex';", content)

    def test_embed_js_allows_microphone_for_embedded_voice_widget(self):
        response = self.client.get(reverse("widget:embed_js", args=[self.clinic.slug]))
        content = response.content.decode()

        self.assertIn("iframe.allow = 'microphone; clipboard-write';", content)

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

    def test_widget_home_hides_voice_entry_when_disabled(self):
        response = self.client.get(reverse("widget:home", args=[self.clinic.slug]))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Talk to Voice Agent")
        self.assertNotContains(response, "startVoice()")

    def test_widget_home_shows_voice_entry_when_enabled(self):
        from voice.models import VoiceAgentSettings

        VoiceAgentSettings.objects.create(clinic=self.clinic, is_enabled=True, display_name="Clinic Voice")

        response = self.client.get(reverse("widget:home", args=[self.clinic.slug]))
        content = response.content.decode()
        voice_panel_start = content.index("<div x-show=\"mode==='voice'\"")
        voice_panel_end = content.index("function widgetApp()", voice_panel_start)
        voice_panel = content[voice_panel_start:voice_panel_end]

        self.assertEqual(response.status_code, 200)
        self.assertIn("Talk to Voice Agent", content)
        self.assertIn("startVoice()", content)
        self.assertIn("Microphone access was blocked. You can still type or book manually.", content)
        self.assertIn(reverse("voice:widget_session", args=[self.clinic.slug]), content)
        self.assertNotIn(":data-lucide=\"voiceListening ? 'square' : 'mic'\"", voice_panel)
        self.assertIn('data-lucide="mic" x-show="!voiceListening"', voice_panel)
        self.assertIn('data-lucide="square" x-show="voiceListening"', voice_panel)

    def test_widget_voice_panel_does_not_show_blocked_message_before_error(self):
        from voice.models import VoiceAgentSettings

        VoiceAgentSettings.objects.create(clinic=self.clinic, is_enabled=True, display_name="Clinic Voice")

        response = self.client.get(reverse("widget:home", args=[self.clinic.slug]))
        content = response.content.decode()
        voice_panel_start = content.index("<div x-show=\"mode==='voice'\"")
        voice_panel_end = content.index("function widgetApp()", voice_panel_start)
        voice_panel = content[voice_panel_start:voice_panel_end]

        self.assertNotIn("Microphone access was blocked. You can still type or book manually.", voice_panel)
        self.assertIn("Tap the mic to speak with the assistant.", voice_panel)

    def test_widget_voice_start_session_ignores_stale_response(self):
        from voice.models import VoiceAgentSettings

        VoiceAgentSettings.objects.create(clinic=self.clinic, is_enabled=True, display_name="Clinic Voice")

        response = self.client.get(reverse("widget:home", args=[self.clinic.slug]))
        content = response.content.decode()
        start_voice_start = content.index("async startVoice()")
        start_voice_end = content.index("toggleVoiceListening()", start_voice_start)
        start_voice_block = content[start_voice_start:start_voice_end]

        self.assertIn("const stateResetVersion = this.stateResetVersion;", start_voice_block)
        self.assertIn("if (stateResetVersion !== this.stateResetVersion || this.mode !== 'voice') return;", start_voice_block)
        self.assertLess(
            start_voice_block.index("const stateResetVersion = this.stateResetVersion;"),
            start_voice_block.index("const resp = await fetch"),
        )
        self.assertLess(
            start_voice_block.index("if (stateResetVersion !== this.stateResetVersion || this.mode !== 'voice') return;"),
            start_voice_block.index("this.voiceSessionId = data.session_id;"),
        )

    def test_widget_voice_end_invalidates_pending_start_voice_response(self):
        from voice.models import VoiceAgentSettings

        VoiceAgentSettings.objects.create(clinic=self.clinic, is_enabled=True, display_name="Clinic Voice")

        response = self.client.get(reverse("widget:home", args=[self.clinic.slug]))
        content = response.content.decode()
        start_voice_start = content.index("async startVoice()")
        start_voice_end = content.index("toggleVoiceListening()", start_voice_start)
        start_voice_block = content[start_voice_start:start_voice_end]
        end_start = content.index("async endVoice()")
        end_end = content.index("get filteredFaqs()", end_start)
        end_block = content[end_start:end_end]

        self.assertIn("const stateResetVersion = this.stateResetVersion;", start_voice_block)
        self.assertIn("if (stateResetVersion !== this.stateResetVersion || this.mode !== 'voice') return;", start_voice_block)
        self.assertIn("this.stateResetVersion += 1;", end_block)
        self.assertLess(end_block.index("this.stateResetVersion += 1;"), end_block.index("const sessionId = this.voiceSessionId;"))

    def test_widget_voice_turn_ignores_stale_response_before_reply_mutation(self):
        from voice.models import VoiceAgentSettings

        VoiceAgentSettings.objects.create(clinic=self.clinic, is_enabled=True, display_name="Clinic Voice")

        response = self.client.get(reverse("widget:home", args=[self.clinic.slug]))
        content = response.content.decode()
        turn_start = content.index("async sendVoiceTurn(text)")
        turn_end = content.index("speakVoiceReply(text", turn_start)
        turn_block = content[turn_start:turn_end]

        stale_guard = "if (stateResetVersion !== this.stateResetVersion || sessionId !== this.voiceSessionId || this.mode !== 'voice') return;"
        self.assertIn("const stateResetVersion = this.stateResetVersion;", turn_block)
        self.assertIn("const sessionId = this.voiceSessionId;", turn_block)
        self.assertIn(stale_guard, turn_block)
        self.assertIn("if (stateResetVersion === this.stateResetVersion && sessionId === this.voiceSessionId && this.mode === 'voice')", turn_block)
        self.assertLess(turn_block.index("const sessionId = this.voiceSessionId;"), turn_block.index("const resp = await fetch"))
        self.assertLess(turn_block.index(stale_guard), turn_block.index("this.voiceTranscript.push({id: this.nextId++, role: 'assistant'"))
        self.assertLess(turn_block.index(stale_guard), turn_block.index("this.speakVoiceReply(data.message, stateResetVersion, sessionId, () => {"))

    def test_widget_voice_end_resets_processing_and_ignores_end_failures(self):
        from voice.models import VoiceAgentSettings

        VoiceAgentSettings.objects.create(clinic=self.clinic, is_enabled=True, display_name="Clinic Voice")

        response = self.client.get(reverse("widget:home", args=[self.clinic.slug]))
        content = response.content.decode()
        end_start = content.index("async endVoice()")
        end_end = content.index("get filteredFaqs()", end_start)
        end_block = content[end_start:end_end]

        self.assertIn("this.voiceProcessing = false;", end_block)
        self.assertIn("try {", end_block)
        self.assertIn("} catch (error) {", end_block)
        self.assertIn("// Ending is best-effort", end_block)
        self.assertLess(end_block.index("this.voiceProcessing = false;"), end_block.index("if (!sessionId) return;"))

    def test_widget_voice_recognition_errors_only_label_permission_denials_as_blocked(self):
        from voice.models import VoiceAgentSettings

        VoiceAgentSettings.objects.create(clinic=self.clinic, is_enabled=True, display_name="Clinic Voice")

        response = self.client.get(reverse("widget:home", args=[self.clinic.slug]))
        content = response.content.decode()
        listen_start = content.index("startVoiceListening({ auto = false } = {})")
        listen_end = content.index("async sendVoiceTurn(text)", listen_start)
        listen_block = content[listen_start:listen_end]

        self.assertIn("recognition.onerror = (event) => {", listen_block)
        self.assertIn("const blocked = event.error === 'not-allowed' || event.error === 'service-not-allowed';", listen_block)
        self.assertIn("this.voiceStatusLabel = blocked ? 'Microphone blocked' : 'Voice error';", listen_block)
        self.assertIn("blocked ? 'Microphone access was blocked. You can still type or book manually.' : 'Voice recognition had trouble hearing you. Please try again.'", listen_block)

    def test_widget_voice_recognition_callbacks_ignore_stale_session(self):
        from voice.models import VoiceAgentSettings

        VoiceAgentSettings.objects.create(clinic=self.clinic, is_enabled=True, display_name="Clinic Voice")

        response = self.client.get(reverse("widget:home", args=[self.clinic.slug]))
        content = response.content.decode()
        listen_start = content.index("startVoiceListening({ auto = false } = {})")
        listen_end = content.index("async sendVoiceTurn(text)", listen_start)
        listen_block = content[listen_start:listen_end]
        stale_guard = "if (stateResetVersion !== this.stateResetVersion || sessionId !== this.voiceSessionId || this.mode !== 'voice') return;"

        self.assertIn("const stateResetVersion = this.stateResetVersion;", listen_block)
        self.assertIn("const sessionId = this.voiceSessionId;", listen_block)
        self.assertGreaterEqual(listen_block.count(stale_guard), 4)
        self.assertLess(listen_block.index("const sessionId = this.voiceSessionId;"), listen_block.index("recognition.onstart = () => {"))

    def test_widget_voice_auto_loop_speaks_then_listens_after_session_and_reply(self):
        from voice.models import VoiceAgentSettings

        VoiceAgentSettings.objects.create(clinic=self.clinic, is_enabled=True, display_name="Clinic Voice")

        response = self.client.get(reverse("widget:home", args=[self.clinic.slug]))
        content = response.content.decode()
        start_voice_start = content.index("async startVoice()")
        start_voice_end = content.index("toggleVoiceListening()", start_voice_start)
        start_voice_block = content[start_voice_start:start_voice_end]
        send_turn_start = content.index("async sendVoiceTurn(text)")
        send_turn_end = content.index("speakVoiceReply(text", send_turn_start)
        send_turn_block = content[send_turn_start:send_turn_end]

        self.assertIn("voiceAutoListen: false,", content)
        self.assertIn("voiceSpeaking: false,", content)
        self.assertIn("this.voiceAutoListen = true;", start_voice_block)
        self.assertIn("this.speakVoiceReply(data.message, stateResetVersion, data.session_id, () => {", start_voice_block)
        self.assertIn("this.continueVoiceLoop(stateResetVersion, data.session_id);", start_voice_block)
        self.assertIn("this.continueVoiceLoop(stateResetVersion, this.voiceSessionId);", start_voice_block)
        self.assertIn("this.speakVoiceReply(data.message, stateResetVersion, sessionId, () => {", send_turn_block)
        self.assertIn("this.continueVoiceLoop(stateResetVersion, sessionId);", send_turn_block)

    def test_widget_voice_mic_interrupts_speech_and_blocks_duplicates_while_processing(self):
        from voice.models import VoiceAgentSettings

        VoiceAgentSettings.objects.create(clinic=self.clinic, is_enabled=True, display_name="Clinic Voice")

        response = self.client.get(reverse("widget:home", args=[self.clinic.slug]))
        content = response.content.decode()
        toggle_start = content.index("toggleVoiceListening() {")
        toggle_end = content.index("startVoiceListening", toggle_start)
        toggle_block = content[toggle_start:toggle_end]
        interrupt_start = content.index("interruptVoice()")
        interrupt_end = content.index("continueVoiceLoop", interrupt_start)
        interrupt_block = content[interrupt_start:interrupt_end]

        self.assertIn("if (this.voiceProcessing) {", toggle_block)
        self.assertIn("this.voiceStatusLabel = 'Thinking';", toggle_block)
        self.assertIn("if (this.voiceSpeaking) {", toggle_block)
        self.assertIn("this.interruptVoice();", toggle_block)
        self.assertIn("window.speechSynthesis.cancel();", interrupt_block)
        self.assertIn("this.voiceSpeaking = false;", interrupt_block)
        self.assertIn("this.startVoiceListening({ auto: false });", interrupt_block)

    def test_widget_voice_auto_listen_stops_on_end_and_uses_synthesis_callbacks(self):
        from voice.models import VoiceAgentSettings

        VoiceAgentSettings.objects.create(clinic=self.clinic, is_enabled=True, display_name="Clinic Voice")

        response = self.client.get(reverse("widget:home", args=[self.clinic.slug]))
        content = response.content.decode()
        speak_start = content.index("speakVoiceReply(text")
        speak_end = content.index("async endVoice()", speak_start)
        speak_block = content[speak_start:speak_end]
        end_start = content.index("async endVoice()")
        end_end = content.index("get filteredFaqs()", end_start)
        end_block = content[end_start:end_end]

        self.assertIn("const utterance = new window.SpeechSynthesisUtterance(text);", speak_block)
        self.assertIn("utterance.onend = finishSpeaking;", speak_block)
        self.assertIn("utterance.onerror = finishSpeaking;", speak_block)
        self.assertIn("this.voiceSpeaking = true;", speak_block)
        self.assertIn("this.voiceStatusLabel = 'Speaking';", speak_block)
        self.assertIn("this.voiceAutoListen = false;", end_block)
        self.assertIn("this.voiceSpeaking = false;", end_block)

    def test_widget_home_handles_invalid_service_query_param(self):
        response = self.client.get(reverse("widget:home", args=[self.clinic.slug]), {"service": "not-a-number"})

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "widget/widget.html")

    def test_widget_slots_handles_invalid_service_query_param(self):
        response = self.client.get(reverse("widget:slots", args=[self.clinic.slug]), {"service": "not-a-number"})

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "widget/partials/slots.html")

    def test_widget_booking_form_guards_against_in_flight_duplicate_submits(self):
        response = self.client.get(reverse("widget:home", args=[self.clinic.slug]))
        content = response.content.decode()

        form_start = content.index('<form hx-post=')
        form_end = content.index("</form>", form_start)
        form = content[form_start:form_end]
        button_start = form.index('<button type="submit"')
        button_end = form.index("</button>", button_start)
        submit_button = form[button_start:button_end]

        self.assertIn('hx-target="#booking-form-container"', form)
        self.assertIn('hx-swap="innerHTML"', form)
        self.assertIn('hx-sync="this:drop"', form)
        self.assertIn('hx-disabled-elt="find button[type=\'submit\']"', form)
        self.assertIn("Confirm Appointment", submit_button)
        self.assertIn("disabled:cursor-not-allowed", submit_button)
        self.assertIn("disabled:opacity-60", submit_button)

    def test_widget_minimize_preserves_in_memory_state(self):
        response = self.client.get(reverse("widget:home", args=[self.clinic.slug]))
        content = response.content.decode()

        minimize_start = content.index("minimize() {")
        minimize_end = content.index("startChat()", minimize_start)
        minimize_block = content[minimize_start:minimize_end]

        self.assertIn("kliniassist-minimize", minimize_block)
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

    def test_chat_api_service_payloads_do_not_include_price_fields(self):
        response = self.client.get(reverse("widget:chat_api", args=[self.clinic.slug]))

        self.assertEqual(response.status_code, 200)
        for service in response.json()["services"]:
            self.assertNotIn("price", service)
            self.assertNotIn("display_price", service)

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

    def test_widget_slots_keep_different_service_same_time_available(self):
        filling = Service.objects.create(clinic=self.clinic, name="Tooth Filling", duration_minutes=30)
        tomorrow = timezone.localdate() + timedelta(days=1)
        cleaning_slot = generate_slots(self.clinic, self.service, tomorrow)[0]
        patient = Patient.objects.create(clinic=self.clinic, full_name="Existing Patient", phone="09170000000")
        Appointment.objects.create(
            clinic=self.clinic,
            patient=patient,
            service=self.service,
            starts_at=cleaning_slot["starts_at"],
            ends_at=cleaning_slot["ends_at"],
        )

        response = self.client.get(
            reverse("widget:slots", args=[self.clinic.slug]),
            {"service": filling.id, "date": tomorrow.isoformat()},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, cleaning_slot["label"])

    def test_widget_booking_rejects_stale_same_service_slot_when_capacity_full(self):
        tomorrow = timezone.localdate() + timedelta(days=1)
        slot = generate_slots(self.clinic, self.service, tomorrow)[0]
        patient = Patient.objects.create(clinic=self.clinic, full_name="Existing Patient", phone="09170000000")
        Appointment.objects.create(
            clinic=self.clinic,
            patient=patient,
            service=self.service,
            starts_at=slot["starts_at"],
            ends_at=slot["ends_at"],
        )

        response = self.client.post(
            reverse("widget:book", args=[self.clinic.slug]),
            {
                "service": self.service.id,
                "starts_at": slot["starts_at"].isoformat(),
                "full_name": "Stale Submit",
                "phone": "09171111111",
                "email": "stale@example.com",
            },
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 409)
        self.assertContains(response, "That slot is no longer available", status_code=409)
        self.assertEqual(
            Appointment.objects.filter(clinic=self.clinic, service=self.service, starts_at=slot["starts_at"]).count(),
            1,
        )

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_widget_booking_rejection_does_not_send_confirmation_email(self):
        mail.outbox = []
        tomorrow = timezone.localdate() + timedelta(days=1)
        slot = generate_slots(self.clinic, self.service, tomorrow)[0]
        existing_patient = Patient.objects.create(
            clinic=self.clinic,
            full_name="Existing Patient",
            phone="09170000000",
            email="existing@example.com",
        )
        Appointment.objects.create(
            clinic=self.clinic,
            patient=existing_patient,
            service=self.service,
            starts_at=slot["starts_at"],
            ends_at=slot["ends_at"],
        )

        with self.captureOnCommitCallbacks(execute=True) as callbacks:
            response = self.client.post(
                reverse("widget:book", args=[self.clinic.slug]),
                {
                    "service": self.service.id,
                    "starts_at": slot["starts_at"].isoformat(),
                    "full_name": "Rejected Patient",
                    "phone": "09175550001",
                    "email": "rejected@example.com",
                },
                HTTP_HX_REQUEST="true",
            )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(callbacks, [])
        self.assertEqual(mail.outbox, [])

    def test_widget_booking_rejects_duplicate_same_patient_service_start_even_with_capacity(self):
        self.service.simultaneous_capacity = 2
        self.service.save(update_fields=["simultaneous_capacity", "updated_at"])
        tomorrow = timezone.localdate() + timedelta(days=1)
        slot = generate_slots(self.clinic, self.service, tomorrow)[0]
        payload = {
            "service": self.service.id,
            "starts_at": slot["starts_at"].isoformat(),
            "full_name": "Duplicate Patient",
            "phone": "09172222222",
            "email": "duplicate@example.com",
        }

        first = self.client.post(reverse("widget:book", args=[self.clinic.slug]), payload, HTTP_HX_REQUEST="true")
        second = self.client.post(reverse("widget:book", args=[self.clinic.slug]), payload, HTTP_HX_REQUEST="true")

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 409)
        self.assertEqual(
            Appointment.objects.filter(clinic=self.clinic, service=self.service, starts_at=slot["starts_at"]).count(),
            1,
        )

    def test_widget_date_options_use_clinic_timezone(self):
        Clinic.objects.filter(pk=self.clinic.pk).update(timezone="America/New_York")
        fixed_now = datetime(2026, 6, 2, 2, 0, tzinfo=dt_timezone.utc)

        with patch("widget.views.timezone.now", return_value=fixed_now):
            response = self.client.get(reverse("widget:home", args=[self.clinic.slug]))

        first_date = response.context["dates"][0]
        self.assertEqual(first_date.isoformat(), "2026-06-02")

    def test_widget_always_renders_reason_field(self):
        response = self.client.get(reverse("widget:home", args=[self.clinic.slug]))

        self.assertContains(response, 'name="reason"')

    def test_widget_clears_selected_slot_before_reloading_slots(self):
        response = self.client.get(reverse("widget:home", args=[self.clinic.slug]))
        content = response.content.decode()

        select_service_start = content.index("selectService(id) {")
        select_service_end = content.index("selectDate(date)", select_service_start)
        select_service_block = content[select_service_start:select_service_end]

        load_slots_start = content.index("loadSlots() {")
        load_slots_end = content.index("goToStep3()", load_slots_start)
        load_slots_block = content[load_slots_start:load_slots_end]

        self.assertIn("this.slot = '';", select_service_block)
        self.assertLess(select_service_block.index("this.slot = '';"), select_service_block.index("this.$nextTick"))
        self.assertIn("this.slot = '';", load_slots_block)
        self.assertLess(load_slots_block.index("this.slot = '';"), load_slots_block.index("htmx.ajax("))

    def test_widget_chat_initial_state_has_no_quick_button_suggestions(self):
        response = self.client.get(reverse("widget:home", args=[self.clinic.slug]))
        content = response.content.decode()

        self.assertIn("opt.type === 'ai_prompt'", content)
        self.assertIn("this.sendChatAction('text_input', opt.value);", content)
        self.assertIn("chatState !== 'collect_info'", content)
        self.assertNotIn("Book an appointment</button>", content)
        self.assertNotIn("Ask about services</button>", content)

    def test_widget_chat_help_message_is_not_swallowed_before_assistant_post(self):
        response = self.client.get(reverse("widget:home", args=[self.clinic.slug]))
        content = response.content.decode()

        send_chat_start = content.index("async sendChat()")
        send_chat_end = content.index("submitCollectInfo()", send_chat_start)
        send_chat_block = content[send_chat_start:send_chat_end]

        assistant_post = send_chat_block.index("await this.sendChatAction('text_input', text);")
        faq_branch_start = send_chat_block.index("if (/^faqs?$/.test(lowerText)")
        branch_before_post = send_chat_block[faq_branch_start:assistant_post]

        self.assertNotIn("includes('help')", send_chat_block)
        self.assertNotIn("return;", branch_before_post)

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

    def test_widget_page_prevents_document_scroll_when_chat_conversation_overflows(self):
        response = self.client.get(reverse("widget:home", args=[self.clinic.slug]))
        content = response.content.decode()

        main_start = content.index("<main")
        main_end = content.index(">", main_start)
        main_markup = content[main_start:main_end]
        conversation_start = content.index("<!-- Conversation -->")
        conversation_end = content.index("<!-- FAQs -->", conversation_start)
        conversation_markup = content[conversation_start:conversation_end]

        self.assertIn("fixed", main_markup)
        self.assertIn("inset-0", main_markup)
        self.assertIn("overflow-hidden", main_markup)
        self.assertIn("overflow-y-auto", conversation_markup)

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

    def test_widget_chat_renders_assistant_formatting_without_raw_html(self):
        response = self.client.get(reverse("widget:home", args=[self.clinic.slug]))
        content = response.content.decode()

        conversation_start = content.index("<!-- Conversation -->")
        conversation_end = content.index("<!-- FAQs -->", conversation_start)
        conversation_markup = content[conversation_start:conversation_end]
        script_start = content.index("function widgetApp()")
        script = content[script_start:]

        self.assertIn("messageBlocks(msg.text)", conversation_markup)
        self.assertIn("messageParts(block.text)", conversation_markup)
        self.assertIn("whitespace-pre-wrap", conversation_markup)
        self.assertIn("font-semibold", conversation_markup)
        self.assertIn('x-text="part.text"', conversation_markup)
        self.assertNotIn("x-html", conversation_markup)
        self.assertIn("messageParts(text) {", script)
        self.assertIn("/\\*\\*([^*]+?)\\*\\*|\\*([^*\\n]+?)\\*/g", script)

    def test_widget_chat_renders_markdown_tables_without_raw_html(self):
        response = self.client.get(reverse("widget:home", args=[self.clinic.slug]))
        content = response.content.decode()

        conversation_start = content.index("<!-- Conversation -->")
        conversation_end = content.index("<!-- FAQs -->", conversation_start)
        conversation_markup = content[conversation_start:conversation_end]
        script_start = content.index("function widgetApp()")
        script = content[script_start:]

        self.assertIn("messageBlocks(msg.text)", conversation_markup)
        self.assertIn("block.type === 'table'", conversation_markup)
        self.assertIn("<table", conversation_markup)
        self.assertIn("<thead", conversation_markup)
        self.assertIn("<tbody", conversation_markup)
        self.assertIn("parseMarkdownTable", script)
        self.assertIn("isMarkdownTableSeparator", script)
        self.assertNotIn("x-html", conversation_markup)

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

    def test_widget_chat_shows_visible_message_when_ai_fetch_fails(self):
        response = self.client.get(reverse("widget:home", args=[self.clinic.slug]))
        content = response.content.decode()

        send_chat_start = content.index("async sendChatAction(")
        send_chat_end = content.index("selectChatOption", send_chat_start)
        send_chat_block = content[send_chat_start:send_chat_end]

        self.assertIn("if (!resp.ok)", send_chat_block)
        self.assertIn("catch (error)", send_chat_block)
        self.assertIn("Sorry, I could not reach the assistant", send_chat_block)
        self.assertIn("this.chatHistory.push({id: this.nextId++, role: 'assistant'", send_chat_block)
        self.assertLess(send_chat_block.index("catch (error)"), send_chat_block.index("finally {"))

    def test_widget_chat_does_not_parse_non_json_error_response_as_json(self):
        response = self.client.get(reverse("widget:home", args=[self.clinic.slug]))
        content = response.content.decode()

        send_chat_start = content.index("async sendChatAction(")
        send_chat_end = content.index("selectChatOption", send_chat_start)
        send_chat_block = content[send_chat_start:send_chat_end]

        self.assertIn("resp.headers.get('content-type')", send_chat_block)
        self.assertIn("contentType.includes('application/json')", send_chat_block)
        self.assertIn("const assistantErrorMessage = 'Sorry, I could not reach the assistant.", send_chat_block)
        self.assertIn("throw new Error(assistantErrorMessage);", send_chat_block)
        self.assertLess(
            send_chat_block.index("if (!contentType.includes('application/json'))"),
            send_chat_block.index("const data = await resp.json();"),
        )

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

    @override_settings(ASSISTANT_N8N_WEBHOOK_URL="https://n8n.example/webhook/widget", N8N_WEBHOOK_SECRET="secret", ALLOWED_HOSTS=["clinic-widget.example.test"])
    @patch("widget.ai_client.requests.post")
    def test_chat_step_ai_payload_includes_dynamic_callback_urls(self, mock_post):
        ClinicAISettings.objects.create(clinic=self.clinic, is_ai_enabled=True)
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {"reply": "Sure, what service would you like?"}

        response = self.client.post(
            reverse("widget:chat_step", args=[self.clinic.slug]),
            {"action": "select_option", "value": "I want to book an appointment"},
            secure=True,
            HTTP_HOST="clinic-widget.example.test",
        )

        self.assertEqual(response.status_code, 200)
        payload = mock_post.call_args.kwargs["json"]
        self.assertEqual(payload["channel"], "widget")
        self.assertEqual(payload["callback_urls"], {
            "widget_ai_context_url": "https://clinic-widget.example.test/messenger/ai/widget/context/",
            "ai_gateway_reply_url": "https://clinic-widget.example.test/messenger/ai/gateway/reply/",
            "messenger_n8n_webhook_url": "https://clinic-widget.example.test/messenger/n8n-webhook/",
        })

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

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_widget_booking_sends_patient_confirmation_email(self):
        mail.outbox = []
        tomorrow = timezone.localdate() + timedelta(days=1)
        slot = generate_slots(self.clinic, self.service, tomorrow)[0]

        with self.captureOnCommitCallbacks(execute=True) as callbacks:
            response = self.client.post(
                reverse("widget:book", args=[self.clinic.slug]),
                {
                    "service": self.service.id,
                    "starts_at": slot["starts_at"].isoformat(),
                    "full_name": "Email Patient",
                    "phone": "09175550000",
                    "email": "email.patient@example.com",
                },
                HTTP_HX_REQUEST="true",
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(callbacks), 1)
        self.assertEqual(len(mail.outbox), 1)
        appointment = Appointment.objects.get(clinic=self.clinic, patient__full_name="Email Patient")
        message = mail.outbox[0]
        self.assertEqual(message.to, ["email.patient@example.com"])
        self.assertEqual(message.subject, f"Your appointment at {self.clinic.name}")
        self.assertIn(appointment.reference_code, message.body)
        self.assertIn("Email Patient", message.body)
        self.assertIn(self.clinic.name, message.body)
        self.assertIn(self.service.name, message.body)
        self.assertEqual(len(message.alternatives), 1)
        self.assertEqual(message.alternatives[0][1], "text/html")
        self.assertIn(appointment.reference_code, message.alternatives[0][0])
        self.assertIn("Your appointment has been confirmed.", message.alternatives[0][0])

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    @patch("appointments.notifications.EmailMultiAlternatives.send", side_effect=Exception("SMTP down"))
    def test_widget_booking_success_continues_when_confirmation_email_fails(self, mock_send):
        tomorrow = timezone.localdate() + timedelta(days=1)
        slot = generate_slots(self.clinic, self.service, tomorrow)[0]

        with self.captureOnCommitCallbacks(execute=True) as callbacks:
            response = self.client.post(
                reverse("widget:book", args=[self.clinic.slug]),
                {
                    "service": self.service.id,
                    "starts_at": slot["starts_at"].isoformat(),
                    "full_name": "SMTP Failure Patient",
                    "phone": "09175550002",
                    "email": "smtp.failure@example.com",
                },
                HTTP_HX_REQUEST="true",
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(callbacks), 1)
        self.assertTrue(
            Appointment.objects.filter(clinic=self.clinic, patient__full_name="SMTP Failure Patient").exists()
        )
        mock_send.assert_called_once()

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_shared_guest_booking_processor_sends_patient_confirmation_email(self):
        mail.outbox = []
        tomorrow = timezone.localdate() + timedelta(days=1)
        slot = generate_slots(self.clinic, self.service, tomorrow)[0]

        with self.captureOnCommitCallbacks(execute=True) as callbacks:
            appointment, error = _process_guest_booking(
                self.clinic,
                {
                    "service": self.service.id,
                    "starts_at": slot["starts_at"].isoformat(),
                    "full_name": "Messenger Email Patient",
                    "phone": "09175550003",
                    "email": "messenger.patient@example.com",
                },
                Appointment.SOURCE_MESSENGER,
            )

        self.assertIsNone(error)
        self.assertIsNotNone(appointment)
        self.assertEqual(appointment.source, Appointment.SOURCE_MESSENGER)
        self.assertEqual(len(callbacks), 1)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["messenger.patient@example.com"])
        self.assertIn(appointment.reference_code, mail.outbox[0].body)

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

    def test_embed_booking_success_book_another_preserves_embed_source(self):
        tomorrow = timezone.localdate() + timedelta(days=1)
        slot = generate_slots(self.clinic, self.service, tomorrow)[0]

        response = self.client.post(
            reverse("widget:book", args=[self.clinic.slug]) + "?source=embed",
            {
                "service": self.service.id,
                "starts_at": slot["starts_at"].isoformat(),
                "full_name": "Embed Again",
                "phone": "09170001234",
                "email": "again@example.com",
            },
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse("widget:home", args=[self.clinic.slug]) + "?source=embed")

    def test_widget_booking_saves_submitted_reason(self):
        tomorrow = timezone.localdate() + timedelta(days=1)
        slots = generate_slots(self.clinic, self.service, tomorrow)

        response = self.client.post(
            reverse("widget:book", args=[self.clinic.slug]),
            {
                "service": self.service.id,
                "starts_at": slots[0]["starts_at"].isoformat(),
                "full_name": "Reason Patient",
                "phone": "09171111111",
                "email": "reason@example.com",
                "reason": "Knee pain",
            },
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        appointment = Appointment.objects.get(clinic=self.clinic, patient__full_name="Reason Patient")
        self.assertEqual(appointment.reason, "Knee pain")
        self.assertEqual(appointment.patient.notes, "Knee pain")

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

    def test_embed_booking_error_back_to_booking_preserves_embed_source(self):
        tomorrow = timezone.localdate() + timedelta(days=1)
        slot = generate_slots(self.clinic, self.service, tomorrow)[0]

        response = self.client.post(
            reverse("widget:book", args=[self.clinic.slug]) + "?source=embed",
            {
                "service": self.service.id,
                "starts_at": slot["starts_at"].isoformat(),
                "full_name": "",
                "phone": "",
                "email": "",
            },
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 409)
        self.assertContains(response, reverse("widget:home", args=[self.clinic.slug]) + "?source=embed", status_code=409)

    def test_widget_booking_rejects_blank_email(self):
        tomorrow = timezone.localdate() + timedelta(days=1)
        slot = generate_slots(self.clinic, self.service, tomorrow)[0]

        resp = self.client.post(
            reverse("widget:book", args=[self.clinic.slug]),
            {
                "service": self.service.id,
                "starts_at": slot["starts_at"].isoformat(),
                "full_name": "Blank Email",
                "phone": "09170001111",
                "email": "   ",
            },
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(resp.status_code, 409)
        self.assertContains(resp, "Please provide your email address.", status_code=409)
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

    def test_widget_booking_success_does_not_disclose_existing_patient_name_matched_by_phone(self):
        Patient.objects.create(
            clinic=self.clinic,
            full_name="Private Existing Patient",
            phone="09123456789",
            email="existing@example.com",
        )
        tomorrow = timezone.localdate() + timedelta(days=1)
        slot = generate_slots(self.clinic, self.service, tomorrow)[0]

        resp = self.client.post(
            reverse("widget:book", args=[self.clinic.slug]),
            {
                "service": self.service.id,
                "starts_at": slot["starts_at"].isoformat(),
                "full_name": "Submitted Booking Name",
                "phone": "0912-345-6789",
                "email": "new@example.com",
            },
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(resp.status_code, 200)
        self.assertNotContains(resp, "Private Existing Patient")

    def test_widget_booking_rejects_oversized_guest_name_without_creating_records(self):
        tomorrow = timezone.localdate() + timedelta(days=1)
        slot = generate_slots(self.clinic, self.service, tomorrow)[0]

        resp = self.client.post(
            reverse("widget:book", args=[self.clinic.slug]),
            {
                "service": self.service.id,
                "starts_at": slot["starts_at"].isoformat(),
                "full_name": "A" * 161,
                "phone": "09170001111",
                "email": "long-name@example.com",
            },
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(resp.status_code, 409)
        self.assertContains(resp, "Please keep your full name under 160 characters.", status_code=409)
        self.assertFalse(Patient.objects.filter(clinic=self.clinic).exists())
        self.assertFalse(Appointment.objects.filter(clinic=self.clinic).exists())

    def test_widget_booking_rejects_oversized_guest_phone_without_creating_records(self):
        tomorrow = timezone.localdate() + timedelta(days=1)
        slot = generate_slots(self.clinic, self.service, tomorrow)[0]

        response = self.client.post(
            reverse("widget:book", args=[self.clinic.slug]),
            {
                "service": self.service.id,
                "starts_at": slot["starts_at"].isoformat(),
                "full_name": "Long Phone",
                "phone": "1" * 41,
                "email": "long-phone@example.com",
            },
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 409)
        self.assertContains(response, "Please keep your phone number under 40 characters.", status_code=409)
        self.assertFalse(Patient.objects.filter(clinic=self.clinic).exists())
        self.assertFalse(Appointment.objects.filter(clinic=self.clinic).exists())

    def test_widget_booking_rejects_malformed_service_without_creating_records(self):
        tomorrow = timezone.localdate() + timedelta(days=1)
        slot = generate_slots(self.clinic, self.service, tomorrow)[0]

        response = self.client.post(
            reverse("widget:book", args=[self.clinic.slug]),
            {
                "service": "not-a-number",
                "starts_at": slot["starts_at"].isoformat(),
                "full_name": "Malformed Service",
                "phone": "09170001111",
                "email": "malformed@example.com",
            },
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 409)
        self.assertContains(response, "Please choose a valid service.", status_code=409)
        self.assertFalse(Patient.objects.filter(clinic=self.clinic, full_name="Malformed Service").exists())
        self.assertFalse(Appointment.objects.filter(clinic=self.clinic).exists())

    @override_settings(WIDGET_PUBLIC_BOOKING_RATE_LIMIT=1, WIDGET_PUBLIC_BOOKING_RATE_WINDOW_SECONDS=60)
    def test_widget_booking_rate_limit_uses_ip_and_phone_without_session(self):
        cache.clear()
        tomorrow = timezone.localdate() + timedelta(days=1)
        slots = generate_slots(self.clinic, self.service, tomorrow)
        url = reverse("widget:book", args=[self.clinic.slug])

        first = self.client.post(
            url,
            {
                "service": self.service.id,
                "starts_at": slots[0]["starts_at"].isoformat(),
                "full_name": "Rate Limited Patient",
                "phone": "09170001111",
                "email": "rate@example.com",
            },
            HTTP_HX_REQUEST="true",
            REMOTE_ADDR="203.0.113.10",
        )
        second_client = Client()
        second = second_client.post(
            url,
            {
                "service": self.service.id,
                "starts_at": slots[1]["starts_at"].isoformat(),
                "full_name": "Rate Limited Patient",
                "phone": "09170001111",
                "email": "rate@example.com",
            },
            HTTP_HX_REQUEST="true",
            REMOTE_ADDR="203.0.113.10",
        )

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 429)
        self.assertContains(second, "Too many booking attempts", status_code=429)
        self.assertEqual(Appointment.objects.filter(clinic=self.clinic).count(), 1)

    @override_settings(WIDGET_PUBLIC_BOOKING_RATE_LIMIT=1, WIDGET_PUBLIC_BOOKING_RATE_WINDOW_SECONDS=60)
    def test_widget_booking_rate_limit_ignores_untrusted_forwarded_for(self):
        cache.clear()
        tomorrow = timezone.localdate() + timedelta(days=1)
        slots = generate_slots(self.clinic, self.service, tomorrow)
        url = reverse("widget:book", args=[self.clinic.slug])

        first = self.client.post(
            url,
            {
                "service": self.service.id,
                "starts_at": slots[0]["starts_at"].isoformat(),
                "full_name": "First Spoofed Patient",
                "phone": "09170001111",
                "email": "first-spoof@example.com",
            },
            HTTP_HX_REQUEST="true",
            HTTP_X_FORWARDED_FOR="198.51.100.10",
            REMOTE_ADDR="203.0.113.10",
        )
        second_client = Client()
        second = second_client.post(
            url,
            {
                "service": self.service.id,
                "starts_at": slots[1]["starts_at"].isoformat(),
                "full_name": "Second Spoofed Patient",
                "phone": "09170002222",
                "email": "second-spoof@example.com",
            },
            HTTP_HX_REQUEST="true",
            HTTP_X_FORWARDED_FOR="198.51.100.20",
            REMOTE_ADDR="203.0.113.10",
        )

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 429)
        self.assertContains(second, "Too many booking attempts", status_code=429)
        self.assertEqual(Appointment.objects.filter(clinic=self.clinic).count(), 1)

    @override_settings(WIDGET_PUBLIC_BOOKING_RATE_LIMIT=1, WIDGET_PUBLIC_BOOKING_RATE_WINDOW_SECONDS=60)
    def test_invalid_booking_does_not_consume_public_booking_rate_limit(self):
        tomorrow = timezone.localdate() + timedelta(days=1)
        slot = generate_slots(self.clinic, self.service, tomorrow)[0]
        url = reverse("widget:book", args=[self.clinic.slug])
        identity = {
            "full_name": "Invalid Then Valid",
            "phone": "09170002222",
            "email": "invalid-then-valid@example.com",
        }

        invalid = self.client.post(
            url,
            {
                **identity,
                "service": "not-a-service",
                "starts_at": slot["starts_at"].isoformat(),
            },
            HTTP_HX_REQUEST="true",
            REMOTE_ADDR="203.0.113.20",
        )
        valid = self.client.post(
            url,
            {
                **identity,
                "service": self.service.id,
                "starts_at": slot["starts_at"].isoformat(),
            },
            HTTP_HX_REQUEST="true",
            REMOTE_ADDR="203.0.113.20",
        )

        self.assertEqual(invalid.status_code, 409)
        self.assertEqual(valid.status_code, 200)
        self.assertEqual(Appointment.objects.filter(clinic=self.clinic, patient__phone="09170002222").count(), 1)

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

    def test_widget_booking_rejects_past_start_with_explicit_message(self):
        fixed_now = datetime(2026, 6, 9, 1, 0, tzinfo=dt_timezone.utc)
        past_start = timezone.make_aware(datetime(2026, 6, 2, 10, 0), timezone=timezone.get_fixed_timezone(480))

        with patch("widget.views.timezone.now", return_value=fixed_now), patch("scheduling.utils.timezone.now", return_value=fixed_now):
            response = self.client.post(
                reverse("widget:book", args=[self.clinic.slug]),
                {
                    "service": self.service.id,
                    "starts_at": past_start.isoformat(),
                    "full_name": "Past Date Patient",
                    "phone": "09170001111",
                    "email": "past@example.com",
                },
                HTTP_HX_REQUEST="true",
            )

        self.assertEqual(response.status_code, 409)
        self.assertContains(
            response,
            "Please choose today or a future appointment date/time. Previous dates and past times are not available.",
            status_code=409,
        )
        self.assertFalse(Appointment.objects.filter(clinic=self.clinic, patient__full_name="Past Date Patient").exists())

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
    def test_chat_step_clears_stale_history_when_ai_settings_change(self, mock_post):
        ai_settings = ClinicAISettings.objects.create(
            clinic=self.clinic,
            is_ai_enabled=True,
            instructions="Always reply I am not interested.",
        )
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {"reply": "I am not interested"}
        url = reverse("widget:chat_step", args=[self.clinic.slug])

        self.client.post(url, {"action": "text_input", "value": "hello"})

        ai_settings.instructions = "Use the default assistant behavior."
        ai_settings.save()
        mock_post.return_value.json.return_value = {"reply": "Hello, how can I help?"}
        response = self.client.post(url, {"action": "text_input", "value": "HELLO"})

        self.assertEqual(response.status_code, 200)
        payload = mock_post.call_args.kwargs["json"]
        self.assertEqual(payload["message"], "HELLO")
        self.assertEqual(payload["history"], [])

    @override_settings(
        ASSISTANT_N8N_WEBHOOK_URL="https://n8n.example/webhook/widget",
        N8N_WEBHOOK_SECRET="secret",
        WIDGET_AI_CHAT_HISTORY_TIMEOUT_MINUTES=30,
    )
    @patch("widget.ai_client.requests.post")
    def test_chat_step_expires_old_ai_history_before_calling_n8n(self, mock_post):
        ai_settings = ClinicAISettings.objects.create(clinic=self.clinic, is_ai_enabled=True)
        history_key = f"widget_chat_history_{self.clinic.id}_default"
        version_key = f"widget_chat_history_version_{self.clinic.id}_default"
        updated_key = f"widget_chat_history_updated_at_{self.clinic.id}_default"
        session = self.client.session
        session[history_key] = [
            {"role": "user", "content": "I want to book cleaning next Monday."},
            {"role": "assistant", "content": "Please confirm the pending appointment."},
        ]
        session[version_key] = ai_settings.updated_at.isoformat()
        session[updated_key] = (timezone.now() - timedelta(days=5)).isoformat()
        session.save()
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {"reply": "Hello, how can I help?"}

        response = self.client.post(
            reverse("widget:chat_step", args=[self.clinic.slug]),
            {"action": "text_input", "value": "hello"},
        )

        self.assertEqual(response.status_code, 200)
        payload = mock_post.call_args.kwargs["json"]
        self.assertEqual(payload["message"], "hello")
        self.assertEqual(payload["history"], [])

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

    @override_settings(DEBUG=False, ASSISTANT_N8N_WEBHOOK_URL="", N8N_WEBHOOK_SECRET="secret")
    def test_chat_step_returns_default_fallback_when_webhook_missing(self):
        from messenger.defaults import DEFAULT_AI_FALLBACK_MESSAGE

        ClinicAISettings.objects.create(clinic=self.clinic, is_ai_enabled=True, fallback_message="")

        response = self.client.post(
            reverse("widget:chat_step", args=[self.clinic.slug]),
            {"action": "text_input", "value": "Hello"},
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["state"], "ai")
        self.assertIn(DEFAULT_AI_FALLBACK_MESSAGE, data["message"])
        self.assertEqual(data["options"], [])

    @override_settings(DEBUG=True, ASSISTANT_N8N_WEBHOOK_URL="", N8N_WEBHOOK_SECRET="")
    def test_chat_step_explains_missing_assistant_webhook_in_debug(self):
        ClinicAISettings.objects.create(clinic=self.clinic, is_ai_enabled=True, fallback_message="")

        response = self.client.post(
            reverse("widget:chat_step", args=[self.clinic.slug]),
            {"action": "text_input", "value": "Hello"},
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["state"], "ai")
        self.assertIn("ASSISTANT_N8N_WEBHOOK_URL", data["message"])
        self.assertIn("N8N_WEBHOOK_SECRET", data["message"])

    @override_settings(DEBUG=False, ASSISTANT_N8N_WEBHOOK_URL="https://n8n.example/webhook/widget", N8N_WEBHOOK_SECRET="")
    @patch("widget.ai_client.requests.post")
    def test_chat_step_fails_closed_when_n8n_secret_is_missing(self, mock_post):
        ClinicAISettings.objects.create(clinic=self.clinic, is_ai_enabled=True, fallback_message="Use the booking form.")

        response = self.client.post(
            reverse("widget:chat_step", args=[self.clinic.slug]),
            {"action": "text_input", "value": "Hello"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("Use the booking form.", response.json()["message"])
        mock_post.assert_not_called()

    @override_settings(ASSISTANT_N8N_WEBHOOK_URL="https://n8n.example/webhook/widget", N8N_WEBHOOK_SECRET="secret")
    @patch("widget.ai_client.requests.post")
    def test_chat_step_uses_fallback_for_malformed_n8n_response(self, mock_post):
        ClinicAISettings.objects.create(clinic=self.clinic, is_ai_enabled=True, fallback_message="Safe fallback.")
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = []

        response = self.client.post(
            reverse("widget:chat_step", args=[self.clinic.slug]),
            {"action": "text_input", "value": "Hello"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("Safe fallback.", response.json()["message"])

    @override_settings(ASSISTANT_N8N_WEBHOOK_URL="https://n8n.example/webhook/widget", N8N_WEBHOOK_SECRET="secret")
    @patch("widget.ai_client.requests.post")
    def test_chat_step_uses_fallback_for_non_string_n8n_reply(self, mock_post):
        ClinicAISettings.objects.create(clinic=self.clinic, is_ai_enabled=True, fallback_message="Safe fallback.")
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {"reply": {"text": "hello"}}

        response = self.client.post(
            reverse("widget:chat_step", args=[self.clinic.slug]),
            {"action": "text_input", "value": "Hello"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("Safe fallback.", response.json()["message"])

    @override_settings(ASSISTANT_N8N_WEBHOOK_URL="https://n8n.example/webhook/widget", N8N_WEBHOOK_SECRET="secret")
    @patch("widget.ai_client.requests.post")
    def test_chat_step_scopes_history_and_n8n_session_by_conversation_id(self, mock_post):
        ClinicAISettings.objects.create(clinic=self.clinic, is_ai_enabled=True)
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {"reply": "Reply from AI."}
        url = reverse("widget:chat_step", args=[self.clinic.slug])

        self.client.post(url, {"action": "text_input", "value": "First", "conversation_id": "conversation-a"})
        response = self.client.post(url, {"action": "text_input", "value": "Second", "conversation_id": "conversation-b"})

        self.assertEqual(response.status_code, 200)
        payload = mock_post.call_args.kwargs["json"]
        self.assertEqual(payload["message"], "Second")
        self.assertEqual(payload["history"], [])
        self.assertEqual(payload["conversation_id"], "conversation-b")
        self.assertTrue(payload["session_id"].endswith(":conversation-b"))

    @override_settings(ASSISTANT_N8N_WEBHOOK_URL="https://n8n.example/webhook/widget", N8N_WEBHOOK_SECRET="secret", WIDGET_AI_CHAT_MAX_MESSAGE_LENGTH=12)
    @patch("widget.ai_client.requests.post")
    def test_chat_step_rejects_oversized_messages_without_calling_n8n(self, mock_post):
        ClinicAISettings.objects.create(clinic=self.clinic, is_ai_enabled=True)

        response = self.client.post(
            reverse("widget:chat_step", args=[self.clinic.slug]),
            {"action": "text_input", "value": "This is much too long"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("under 12 characters", response.json()["message"])
        mock_post.assert_not_called()

    @override_settings(ASSISTANT_N8N_WEBHOOK_URL="https://n8n.example/webhook/widget", N8N_WEBHOOK_SECRET="secret")
    @patch("widget.ai_client.requests.post")
    def test_assistant_webhook_does_not_follow_secret_bearing_redirects(self, mock_post):
        from widget.ai_client import call_assistant_webhook

        mock_post.return_value.json.return_value = {"reply": "Safe reply"}

        reply = call_assistant_webhook(self.clinic, "Hello", [], "session-1")

        self.assertEqual(reply, "Safe reply")
        self.assertFalse(mock_post.call_args.kwargs["allow_redirects"])

    @override_settings(ASSISTANT_N8N_WEBHOOK_URL="https://n8n.example/webhook/widget", N8N_WEBHOOK_SECRET="secret", WIDGET_AI_CHAT_RATE_LIMIT=1, WIDGET_AI_CHAT_RATE_WINDOW_SECONDS=60)
    @patch("widget.ai_client.requests.post")
    def test_chat_step_rate_limits_public_chat_without_calling_n8n_again(self, mock_post):
        cache.clear()
        ClinicAISettings.objects.create(clinic=self.clinic, is_ai_enabled=True)
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {"reply": "Reply from AI."}
        url = reverse("widget:chat_step", args=[self.clinic.slug])

        first = self.client.post(url, {"action": "text_input", "value": "Hello"})
        second = self.client.post(url, {"action": "text_input", "value": "Hello again"})

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 429)
        self.assertIn("Too many messages", second.json()["message"])
        self.assertEqual(mock_post.call_count, 1)

    @override_settings(ASSISTANT_N8N_WEBHOOK_URL="https://n8n.example/webhook/widget", N8N_WEBHOOK_SECRET="secret", WIDGET_AI_CHAT_RATE_LIMIT=1, WIDGET_AI_CHAT_RATE_WINDOW_SECONDS=60)
    @patch("widget.ai_client.requests.post")
    def test_chat_step_rate_limit_cannot_be_bypassed_by_rotating_conversation_id(self, mock_post):
        cache.clear()
        ClinicAISettings.objects.create(clinic=self.clinic, is_ai_enabled=True)
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {"reply": "Reply from AI."}
        url = reverse("widget:chat_step", args=[self.clinic.slug])

        first = self.client.post(url, {"action": "text_input", "value": "Hello", "conversation_id": "conversation-a"})
        second = self.client.post(url, {"action": "text_input", "value": "Hello again", "conversation_id": "conversation-b"})

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 429)
        self.assertIn("Too many messages", second.json()["message"])
        self.assertEqual(mock_post.call_count, 1)
