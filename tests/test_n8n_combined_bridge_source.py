import json
import re
import subprocess
from pathlib import Path


SOURCE = Path(__file__).resolve().parents[1] / "n8n_combined_messenger_widget_ai_bridge.ts"
LEGACY_SOURCE = Path(__file__).resolve().parents[1] / "messenger-workflow.ts"


def _extract_prepare_channel_reply_js(source):
    prepare_start = source.index("name: 'Prepare Channel Reply'")
    js_start = source.index("jsCode: `", prepare_start) + len("jsCode: `")
    js_end = source.index("`,\n    },", js_start)
    return source[js_start:js_end]


def _run_prepare_channel_reply(agent_output, channel="messenger"):
    source = SOURCE.read_text(encoding="utf-8")
    js_code = _extract_prepare_channel_reply_js(source)
    shared_items = json.dumps([
        {
            "json": {
                "channel": channel,
                "psid": "PSID123",
                "access_token": "PAGE_TOKEN",
                "context": {},
            }
        }
    ])
    input_items = json.dumps([{"json": {"output": agent_output}}])
    wrapper = f"""
const MESSENGER_FALLBACK = 'Messenger fallback';
const WIDGET_FALLBACK = 'Widget fallback';
const sharedItems = {shared_items};
const inputItems = {input_items};
const $items = (name) => name === 'Shared AI Input' ? sharedItems : [];
const $input = {{ all: () => inputItems }};
const code = `{js_code}`;
const result = Function('$items', '$input', code)($items, $input);
process.stdout.write(JSON.stringify(result));
"""

    result = subprocess.run(
        ["node", "-e", wrapper],
        text=True,
        capture_output=True,
        check=True,
    )
    return json.loads(result.stdout)[0]["json"]["reply_text"]


def _extract_django_ai_gateway_block(source):
    gateway_start = source.index("name: 'Call Django AI Gateway'")
    gateway_end = source.index("const attachDjangoAiGatewayInput")
    return source[gateway_start:gateway_end]


def _extract_django_ai_gateway_payload_expression(source):
    gateway_block = _extract_django_ai_gateway_block(source)
    match = re.search(
        r"jsonBody:\s*expr\((?P<quote>['\"`])(?P<payload>.*?)(?P=quote)\)",
        gateway_block,
        re.DOTALL,
    )
    assert match is not None
    return match.group("payload")


def _assert_gateway_payload_identity_fields(gateway_block):
    expected_fields = [
        'channel: $json.channel',
        'page_id: $json.page_id || ""',
        'psid: $json.psid || ""',
        'turn_token: $json.turn_token || ""',
        'input_sequence: $json.input_sequence || 0',
        'clinic_slug: $json.clinic_slug || ""',
        'message: $json.message || ""',
        'history: $json.history || []',
        'context: $json.context || {}',
    ]
    for expected_field in expected_fields:
        assert expected_field in gateway_block


def test_combined_bridge_uses_django_ai_gateway_for_clinic_owned_model_calls():
    source = SOURCE.read_text(encoding="utf-8")

    assert "name: 'Call Django AI Gateway'" in source
    assert "DJANGO_AI_GATEWAY_REPLY_URL_EXPR" in source
    assert "/messenger/ai/gateway/reply/" in source
    assert "const messengerAiReplyBranch = callDjangoAiGateway\n  .to(attachDjangoAiGatewayInput)\n  .to(resolveDjangoAiGatewayRoute)\n  .to(djangoAiGatewayResponseRoute)" in source
    assert "name: 'Shared Chat Model'" not in source
    assert "name: 'Shared Conversation Memory'" not in source
    assert "name: 'KliniAssist Shared AI Agent'" not in source
    assert "newCredential('OpenAI account'" not in source
    assert "deepseek-ai/DeepSeek-V4-Flash" not in source


def test_combined_bridge_does_not_send_provider_models_to_n8n_gateway_payload():
    source = SOURCE.read_text(encoding="utf-8")
    gateway_payload = _extract_django_ai_gateway_payload_expression(source)
    provider_model_key_pattern = r"[\{,]\s*[\"']?(fallback_model|primary_model|provider_model|model)[\"']?\s*:"

    assert "Shared Chat Model" not in source
    assert "OpenAI account" not in source
    assert "deepseek-ai/DeepSeek-V4-Flash" not in source
    assert re.search(provider_model_key_pattern, gateway_payload) is None


def test_combined_bridge_routes_provider_gateway_fallbacks_to_forced_quick_replies():
    source = SOURCE.read_text(encoding="utf-8")
    route_start = source.index("const routeDjangoAiGatewayResponse")
    route_end = source.index("const prepareSharedFallback")
    route_node_block = source[route_start:route_end]
    branch_start = source.index("const djangoAiGatewayResponseRoute")
    branch_end = source.index("const messengerAiReplyBranch")
    route_branch_block = source[branch_start:branch_end]

    assert "name: 'Resolve Django AI Gateway Route'" in source
    assert "const providerFallbackErrors = new Set(['ai_provider_unconfigured', 'ai_provider_error', 'empty_provider_reply', 'tool_loop_exceeded']);" in source
    assert "force_quick_replies: providerFallback" in source
    assert "name: 'Get Forced Messenger Quick Replies'" in source
    assert "force_quick_replies: true" in source
    assert "const sourceItems = $items('Route Django AI Gateway Response', 0);" in source
    assert "const forcedMessengerQuickReplyBranch = getForcedMessengerQuickReplies" in source
    assert "outputKey: 'forced_quick_replies'" in route_node_block
    assert "outputKey: 'channel_reply'" in route_node_block
    assert ".onCase(0, forcedMessengerQuickReplyBranch)" in route_branch_block
    assert ".onCase(1, prepareChannelReply.to(sharedChannelReplyRoute))" in route_branch_block


def test_n8n_sync_script_validates_gateway_route_instead_of_old_prompt_phrases():
    script = (SOURCE.parents[0] / "scripts" / "sync-n8n-workflow.mjs").read_text(encoding="utf-8")

    assert "Previous dates and past times are not available" not in script
    assert "Do not ask for a time, offer alternatives, or call availability for previous dates" not in script
    assert "Call Django AI Gateway" in script
    assert "/messenger/ai/gateway/reply/" in script
    assert "Shared Chat Model" in script
    assert "OpenAI account" in script


def test_combined_bridge_uses_kliniassist_technical_namespace():
    source = SOURCE.read_text(encoding="utf-8")
    legacy_prefix = "clinic" + "flow"
    legacy_agent = "clinic" + "FlowSharedAiAgent"

    assert "path: 'kliniassist-messenger'" in source
    assert "path: 'kliniassist-widget-assistant'" in source
    assert "const callDjangoAiGateway" in source
    assert "const messengerAiReplyBranch = callDjangoAiGateway\n  .to(attachDjangoAiGatewayInput)\n  .to(resolveDjangoAiGatewayRoute)\n  .to(djangoAiGatewayResponseRoute)" in source
    assert ".onCase(0, messengerAiReplyBranch)" in source
    assert f"path: '{legacy_prefix}-messenger'" not in source
    assert f"path: '{legacy_prefix}-widget-assistant'" not in source
    assert legacy_agent not in source
    assert "const kliniAssistSharedAiAgent" not in source


def test_combined_bridge_uses_flat_route_branch_constants_for_sdk_parser():
    source = SOURCE.read_text(encoding="utf-8")
    workflow_block = source[source.index("export default workflow"):]

    assert "const messengerAiReplyBranch =" in source
    assert "const messengerRouteBranch =" in source
    assert "const metaSignatureRoute =" in source
    assert ".to(routeMetaSignature\n    .onCase" not in workflow_block
    assert ".to(metaSignatureRoute)" in workflow_block
    assert ".add(widgetAssistantWebhook)" in workflow_block


def test_combined_bridge_builds_django_urls_from_one_base_url_constant():
    source = SOURCE.read_text(encoding="utf-8")

    assert "process.env.DJANGO_BASE_URL" not in source
    assert "$env.DJANGO_BASE_URL" not in source
    assert "$env" not in source
    assert "process.env" not in source
    assert "const DJANGO_BASE_URL_FALLBACK =" in source
    assert "const DJANGO_BASE_URL_EXPR =" in source
    assert "$vars.DJANGO_BASE_URL" in source
    assert "DJANGO_MESSENGER_WEBHOOK_URL_EXPR" in source
    assert "DJANGO_AI_GATEWAY_REPLY_URL_EXPR" in source
    assert "url: DJANGO_MESSENGER_WEBHOOK_URL_EXPR" in source
    assert "url: DJANGO_AI_GATEWAY_REPLY_URL_EXPR" in source
    assert source.count("https://178-105-83-211.nip.io") == 1
    assert "https://157-90-164-203.nip.io" not in source


def test_meta_webhook_verification_delegates_token_check_to_django():
    source = SOURCE.read_text(encoding="utf-8")
    verify_start = source.index("const verifyMetaChallenge")
    verify_end = source.index("const returnVerificationResponse")
    verify_block = source[verify_start:verify_end]
    response_start = source.index("name: 'Return Verification Response'")
    response_end = source.index("const metaMessengerEvents")
    response_block = source[response_start:response_end]

    assert "process.env.MESSENGER_VERIFY_TOKEN" not in source
    assert "$vars.MESSENGER_VERIFY_TOKEN" not in response_block
    assert "$env.MESSENGER_VERIFY_TOKEN" not in response_block
    assert "const expectedToken" not in verify_block
    assert "type: 'n8n-nodes-base.httpRequest'" in verify_block
    assert "DJANGO_MESSENGER_WEBHOOK_URL_EXPR" in verify_block
    assert "method: 'GET'" in verify_block
    assert "sendQuery: true" in verify_block
    assert "hub.mode" in verify_block
    assert "hub.verify_token" in verify_block
    assert "hub.challenge" in verify_block
    assert "fullResponse: true" in verify_block
    assert "neverError: true" in verify_block
    assert "responseFormat: 'text'" in verify_block
    assert "output: [{ statusCode: 200, data: '123456789' }]" in verify_block
    assert "$json.data" in response_block
    assert "$json.body" in response_block
    assert "$json.statusCode" in response_block


def test_combined_bridge_gateway_payload_uses_shared_context_identity():
    source = SOURCE.read_text(encoding="utf-8")
    gateway_block = _extract_django_ai_gateway_block(source)

    assert "clinic.example.com" not in source
    assert "fromAi('page_id'" not in source
    assert "fromAi('clinic_slug'" not in source
    assert "name: 'match_services'" not in source
    assert "name: 'check_availability'" not in source
    assert "name: 'book_confirmed_appointment'" not in source
    assert "/messenger/ai/book/" not in source
    assert "/messenger/ai/widget/book/" not in source
    _assert_gateway_payload_identity_fields(gateway_block)


def test_combined_bridge_gateway_payload_sends_messenger_turn_identity():
    source = SOURCE.read_text(encoding="utf-8")
    gateway_block = _extract_django_ai_gateway_block(source)

    assert 'psid: $json.psid || ""' in gateway_block
    assert 'turn_token: $json.turn_token || ""' in gateway_block
    assert 'input_sequence: $json.input_sequence || 0' in gateway_block
    assert "name: 'book_confirmed_appointment'" not in source


def test_combined_bridge_keeps_page_token_out_of_ai_prompt_context():
    source = SOURCE.read_text(encoding="utf-8")
    messenger_start = source.index("name: 'Build Messenger Shared Input'")
    widget_start = source.index("name: 'Build Widget Shared Input'")
    gateway_block = _extract_django_ai_gateway_block(source)
    prepare_start = source.index("name: 'Prepare Channel Reply'")
    route_start = source.index("const routeChannelReply")
    messenger_block = source[messenger_start:widget_start]
    prepare_block = source[prepare_start:route_start]

    assert "const { page_token: pageToken, page_token_available: pageTokenAvailable, ...safeContext } = rawContext;" in messenger_block
    assert "access_token: pageToken || input.access_token || ''" in messenger_block
    assert "context: safeContext" in messenger_block
    assert 'context: $json.context || {}' in gateway_block
    assert "access_token" not in gateway_block
    assert "page_token" not in gateway_block
    assert "access_token: shared.access_token || ''" in prepare_block
    assert "context.page_token" not in gateway_block
    assert "context.page_token" not in prepare_block


def test_combined_bridge_keeps_clinic_provider_secret_out_of_n8n_payloads():
    source = SOURCE.read_text(encoding="utf-8")
    gateway_start = source.index("name: 'Call Django AI Gateway'")
    gateway_end = source.index("const prepareSharedFallback")
    gateway_block = source[gateway_start:gateway_end]

    assert "api_key" not in source
    assert "provider_api_key" not in source
    assert "Authorization" not in gateway_block
    assert "KliniAssist N8N Webhook Secret" in gateway_block
    assert 'context: $json.context || {}' in gateway_block


def test_combined_bridge_django_ai_gateway_has_explicit_timeout_and_no_n8n_ai_tools():
    source = SOURCE.read_text(encoding="utf-8")
    gateway_block = _extract_django_ai_gateway_block(source)
    tool_names = [
        "match_services",
        "check_availability",
        "book_confirmed_appointment",
        "find_verified_appointment",
        "cancel_verified_appointment",
        "reschedule_verified_appointment",
    ]

    assert "options: { response: { response: { neverError: true, responseFormat: 'json' } }, timeout: 30000 }" in gateway_block
    assert "n8n-nodes-base.httpRequestTool" not in source
    for tool_name in tool_names:
        assert f"name: '{tool_name}'" not in source


def test_combined_bridge_widget_path_uses_shared_ai_gateway_and_widget_context():
    source = SOURCE.read_text(encoding="utf-8")
    workflow_block = source[source.index("export default workflow"):]
    widget_start = workflow_block.index(".add(widgetAssistantWebhook)")
    widget_block = workflow_block[widget_start:]
    widget_shared_input_chain = ".add(widgetAssistantWebhook)\n  .to(normalizeWidgetRequest)\n  .to(getWidgetClinicContext)\n  .to(buildWidgetSharedInput)\n  .to(sharedAiInput)"
    assistant_route_start = source.index("const assistantModeRoute")
    export_start = source.index("export default workflow")
    assistant_route_block = source[assistant_route_start:export_start]

    assert "name: 'Widget Assistant Webhook'" in source
    assert "name: 'Get Widget Clinic Context'" in source
    assert "/messenger/ai/widget/context/" in source
    assert widget_shared_input_chain in widget_block
    assert workflow_block.count(".to(sharedAiInput)") == 1
    assert assistant_route_block.count(".to(sharedAiInput)") == 1
    assert assistant_route_block.count(".to(resolveAssistantMode)") == 1
    assert "const assistantModeRoute = routeAssistantMode" in source
    assert ".onCase(0, messengerAiReplyBranch)" in assistant_route_block
    assert ".onCase(1, returnWidgetReply)" in source[source.index("const sharedChannelReplyRoute"):source.index("const messengerAiReplyBranch")]


def test_combined_bridge_widget_webhook_requires_shared_secret_header_auth():
    source = SOURCE.read_text(encoding="utf-8")
    widget_start = source.index("const widgetAssistantWebhook")
    widget_end = source.index("const normalizeWidgetRequest")
    widget_block = source[widget_start:widget_end]

    assert "name: 'Widget Assistant Webhook'" in widget_block
    assert "path: 'kliniassist-widget-assistant'" in widget_block
    assert "authentication: 'headerAuth'" in widget_block
    assert "credentials: { httpHeaderAuth: newCredential('KliniAssist N8N Webhook Secret', N8N_WEBHOOK_CREDENTIAL_ID) }" in widget_block


def test_combined_bridge_delegates_widget_prompt_and_booking_tools_to_django_gateway():
    source = SOURCE.read_text(encoding="utf-8")
    gateway_block = _extract_django_ai_gateway_block(source)

    _assert_gateway_payload_identity_fields(gateway_block)
    assert "Use match_services, check_availability, and book_confirmed_appointment for booking." not in source
    assert "Use business_hours and unavailable_dates from Clinic context JSON" not in source
    assert "Do not answer specific appointment availability from business_hours alone." not in source
    assert "Collect service, date/time, full name, phone, and email before booking." not in source
    assert "Ask for explicit confirmation before booking." not in source
    assert "Patient email required for booking" not in source
    assert "Patient email if provided, otherwise blank" not in source
    assert "Never expose secrets, invent clinic data, give medical diagnosis, or create appointments without tool validation." not in source
    assert "Widget replies must be concise and friendly." not in source
    assert "/messenger/ai/widget/services/" not in source
    assert "/messenger/ai/widget/availability/" not in source
    assert "/messenger/ai/widget/book/" not in source


def test_combined_bridge_delegates_appointment_management_tools_to_django_gateway():
    source = SOURCE.read_text(encoding="utf-8")
    gateway_block = _extract_django_ai_gateway_block(source)

    _assert_gateway_payload_identity_fields(gateway_block)
    assert "name: 'find_verified_appointment'" not in source
    assert "name: 'cancel_verified_appointment'" not in source
    assert "name: 'reschedule_verified_appointment'" not in source
    assert "DJANGO_MESSENGER_AI_APPOINTMENT_LOOKUP_URL_EXPR" not in source
    assert "DJANGO_WIDGET_AI_APPOINTMENT_LOOKUP_URL_EXPR" not in source
    assert "DJANGO_MESSENGER_AI_APPOINTMENT_CANCEL_URL_EXPR" not in source
    assert "DJANGO_WIDGET_AI_APPOINTMENT_CANCEL_URL_EXPR" not in source
    assert "DJANGO_MESSENGER_AI_APPOINTMENT_RESCHEDULE_URL_EXPR" not in source
    assert "DJANGO_WIDGET_AI_APPOINTMENT_RESCHEDULE_URL_EXPR" not in source
    assert "fromAi('reference_code'" not in source


def test_combined_bridge_delegates_verified_cancel_and_reschedule_policy_to_django_gateway():
    source = SOURCE.read_text(encoding="utf-8")
    gateway_block = _extract_django_ai_gateway_block(source)

    _assert_gateway_payload_identity_fields(gateway_block)
    assert "Use find_verified_appointment before canceling or rescheduling." not in source
    assert "Ask for appointment reference code and phone number before appointment management lookup." not in source
    assert "Summarize the verified appointment and requested action before mutation." not in source
    assert "Ask for explicit confirmation before canceling or rescheduling." not in source
    assert "Use cancel_verified_appointment and reschedule_verified_appointment only after explicit confirmation." not in source
    assert "Do not use user-supplied appointment IDs, patient IDs, clinic IDs, or service IDs for appointment management." not in source


def test_combined_bridge_delegates_phone_disclosure_policy_to_django_gateway():
    source = SOURCE.read_text(encoding="utf-8")
    gateway_block = _extract_django_ai_gateway_block(source)

    _assert_gateway_payload_identity_fields(gateway_block)
    assert "If appointment verification fails, use only the tool error and ask the user to re-enter the reference code and phone number." not in source
    assert "Never reveal, correct, infer, or confirm the stored appointment phone number" not in source
    assert "Appointment summaries may show patient_phone_last4 only; do not display full patient phone numbers." not in source


def test_combined_bridge_delegates_availability_and_faq_policy_to_django_gateway():
    source = SOURCE.read_text(encoding="utf-8")
    gateway_block = _extract_django_ai_gateway_block(source)

    _assert_gateway_payload_identity_fields(gateway_block)
    assert "If requested booking or reschedule date is before Today" not in source
    assert "Previous dates and past times are not available" not in source
    assert "Do not ask for a time, offer alternatives, or call availability for previous dates" not in source
    assert "Use check_availability suggestion_type metadata" not in source
    assert "nearest_time means the requested time is unavailable" not in source
    assert "next_available_date means the requested date has no slots" not in source
    assert "Use FAQ entries as clinic knowledge without citing the source" not in source
    assert "Do not say based on the FAQ, according to the FAQ, the FAQ says" not in source


def test_combined_bridge_delegates_communication_tone_policy_to_django_gateway_context():
    source = SOURCE.read_text(encoding="utf-8")
    gateway_block = _extract_django_ai_gateway_block(source)

    _assert_gateway_payload_identity_fields(gateway_block)
    assert "Communication tone:" not in source
    assert "communication_tone_label" not in source
    assert "custom_tone_instructions" not in source
    assert "Tone affects wording only" not in source
    assert "must not override clinic data, tool results, availability, booking confirmation, privacy, medical safety, or channel rules" not in source


def test_combined_bridge_does_not_keep_n8n_conversation_memory():
    source = SOURCE.read_text(encoding="utf-8")

    assert "name: 'Shared Conversation Memory'" not in source
    assert "memory(" not in source
    assert ':shared:v4:' not in source


def test_combined_bridge_versions_upstream_session_key_by_ai_settings():
    source = SOURCE.read_text(encoding="utf-8")
    messenger_start = source.index("name: 'Build Messenger Shared Input'")
    widget_start = source.index("name: 'Build Widget Shared Input'")
    shared_input_start = source.index("const sharedAiInput")
    messenger_block = source[messenger_start:widget_start]
    widget_block = source[widget_start:shared_input_start]

    assert "const aiVersion = safeContext.ai?.settings_updated_at || 'unversioned';" in messenger_block
    assert "session_key: input.session_key + ':ai-settings:' + aiVersion" in messenger_block
    assert "const aiVersion = context.ai?.settings_updated_at || 'unversioned';" in widget_block
    assert "session_key: source.session_key + ':ai-settings:' + aiVersion" in widget_block


def test_channel_reply_code_preserves_regex_escapes_for_n8n():
    source = SOURCE.read_text(encoding="utf-8")

    assert "name: 'Prepare Channel Reply'" in source
    assert "<think[\\\\s\\\\S]*?<\\\\/think>" in source
    assert "<\\\\/?think>" in source


def test_channel_reply_strips_plain_text_internal_reasoning_before_messenger_send():
    reply = _run_prepare_channel_reply(
        """
Let me check the details. The user wants to book a Dental Cleaning appointment on January 2, 2026 at 10:00 AM.

Wait - the current clinic date is June 9, 2026. January 2, 2026 is before today.

January 2, 2026 is before June 9, 2026, so it is a previous date. I'll let the user know.

I understand you'd like to book a Dental Cleaning appointment. However, January 2, 2026 is already past. Appointments can only be scheduled for today or a future date.

Would you like to book for a different date?
"""
    )

    assert reply.startswith("I understand you'd like to book")
    assert "Appointments can only be scheduled for today or a future date" in reply
    assert "Let me check" not in reply
    assert "The user wants" not in reply
    assert "Wait -" not in reply
    assert "I'll let the user know" not in reply


def test_channel_reply_keeps_user_facing_verification_instructions():
    reply = _run_prepare_channel_reply(
        """
I need to verify your appointment before I can reschedule it.

Please send the reference code and phone number used for the booking.
"""
    )

    assert reply.startswith("I need to verify your appointment")
    assert "Please send the reference code" in reply


def test_channel_reply_redacts_failed_appointment_verification_phone_numbers():
    source = SOURCE.read_text(encoding="utf-8")
    prepare_start = source.index("name: 'Prepare Channel Reply'")
    prepare_end = source.index("const routeChannelReply")
    prepare_block = source[prepare_start:prepare_end]

    assert "function redactPhoneLikeText" in prepare_block
    assert "function isFailedAppointmentVerificationReply" in prepare_block
    assert "text = redactPhoneLikeText(text);" in prepare_block
    assert "replace(/\\\\+?\\\\d[\\\\d\\\\s().-]{7,}\\\\d/g" in prepare_block
    assert "replace(/\\\\D/g" in prepare_block
    assert "booked under" in prepare_block
    assert "doesn't match" in prepare_block
    assert "unable to verify" in prepare_block
    assert "belongs to" in prepare_block
    assert "reschedul" in prepare_block
    assert "[phone redacted]" in prepare_block


def test_channel_reply_preserves_phone_numbers_in_booking_confirmation_summary():
    reply = _run_prepare_channel_reply(
        """
Appointment Summary

- Service: Dental Cleaning
- Date & Time: June 12, 2026, 9:00 AM
- Full Name: Production QA Test Patient
- Phone: 0917-123-4567
- Email: qa.production.test@example.com

Please let me know if everything looks correct and you'd like to confirm the booking.
""",
        channel="widget",
    )

    assert "0917-123-4567" in reply
    assert "[phone redacted]" not in reply


def test_channel_reply_still_redacts_failed_appointment_lookup_phone_numbers():
    reply = _run_prepare_channel_reply(
        """
I couldn't verify the appointment. The appointment booked under 0917-123-4567 does not match the reference code provided.

Please re-enter the reference code and phone number used for the booking.
""",
        channel="widget",
    )

    assert "[phone redacted]" in reply
    assert "0917-123-4567" not in reply


def test_meta_messenger_events_acknowledges_only_after_signature_verification():
    source = SOURCE.read_text(encoding="utf-8")

    meta_events_start = source.index("name: 'Meta Messenger Events'")
    meta_events_end = source.index("const normalizeMessengerRequest")
    meta_events_block = source[meta_events_start:meta_events_end]

    assert "responseMode: 'responseNode'" in meta_events_block
    assert "name: 'Acknowledge Meta Messenger Event'" in source
    assert "responseBody: 'EVENT_RECEIVED'" in source
    assert source.index("name: 'Verify Meta Signature'") < source.index("name: 'Prepare Meta Webhook Response'")
    assert source.index("name: 'Verify Meta Signature'") < source.index("name: 'Acknowledge Meta Messenger Event'")
    assert source.index("name: 'Acknowledge Meta Messenger Event'") < source.index("name: 'Expand Messenger Processable Events'")
    assert source.index("name: 'Acknowledge Meta Messenger Event'") < source.index("name: 'Register Messenger Turn'")
    assert ".add(metaMessengerEvents)\n  .to(acknowledgeMetaMessengerEvent)" not in source
    assert "const metaSignatureRoute = routeMetaWebhookResponse\n  .onCase(0, acknowledgeMetaMessengerEvent.to(messengerRouteBranch))\n  .onCase(1, returnInvalidMetaSignature);" in source


def test_meta_messenger_post_uses_single_response_node_before_per_item_processing():
    source = SOURCE.read_text(encoding="utf-8")
    post_start = source.index("const metaMessengerEvents")
    widget_start = source.index("const widgetAssistantWebhook")
    post_block = source[post_start:widget_start]

    assert "const prepareMetaWebhookResponse" in post_block
    assert "const expandMessengerProcessableEvents" in post_block
    assert "name: 'Acknowledge Duplicate Meta Messenger Event'" not in post_block
    assert "name: 'Acknowledge Ignored Meta Messenger Event'" not in post_block
    assert "name: 'Acknowledge Queued Messenger Turn'" not in post_block
    assert post_block.count("type: 'n8n-nodes-base.respondToWebhook'") == 2
    assert "processable_events" in post_block
    assert "verified && !duplicate && !ignored_event" in post_block


def test_meta_messenger_events_verify_signature_before_context_lookup():
    source = SOURCE.read_text(encoding="utf-8")
    meta_events_start = source.index("name: 'Meta Messenger Events'")
    meta_events_end = source.index("const acknowledgeMetaMessengerEvent")
    meta_events_block = source[meta_events_start:meta_events_end]

    assert "name: 'Verify Meta Signature'" in source
    assert "/messenger/meta/verify-signature/" in source
    assert "options: { rawBody: true }" in meta_events_block
    assert "raw_body" in source
    assert "X-Hub-Signature-256" in source
    assert "Prepare Meta Webhook Response" in source
    assert "Route Meta Webhook Response" in source
    assert "Expand Messenger Processable Events" in source
    assert "invalid_signature" in source
    assert "Get Messenger Clinic Context" in source
    assert source.index("name: 'Prepare Meta Webhook Response'") < source.index("name: 'Route Meta Webhook Response'")
    assert source.index("name: 'Route Meta Webhook Response'") < source.index("name: 'Acknowledge Meta Messenger Event'")
    assert source.index("name: 'Acknowledge Meta Messenger Event'") < source.index("name: 'Expand Messenger Processable Events'")
    assert source.index("name: 'Expand Messenger Processable Events'") < source.index("name: 'Register Messenger Turn'")
    assert source.index("name: 'Verify Meta Signature'") < source.index("name: 'Get Messenger Clinic Context'")
    assert ".to(normalizeMessengerRequest)\n  .to(verifyMetaSignature)\n  .to(prepareMetaWebhookResponse)\n  .to(metaSignatureRoute)" in source


def test_meta_messenger_signature_verification_sends_message_identity_to_django():
    source = SOURCE.read_text(encoding="utf-8")
    normalize_start = source.index("name: 'Normalize Messenger Request'")
    normalize_end = source.index("const verifyMetaSignature")
    normalize_block = source[normalize_start:normalize_end]
    verify_start = source.index("name: 'Verify Meta Signature'")
    verify_end = source.index("const prepareMetaWebhookResponse")
    verify_block = source[verify_start:verify_end]

    assert "message_id" in normalize_block
    assert "messaging.message?.mid" in normalize_block
    assert "messaging.postback?.mid" in normalize_block
    assert "message_id: $json.message_id" in verify_block
    assert "psid: $json.psid" in verify_block


def test_meta_messenger_invalid_signature_returns_403_without_acknowledging_event():
    source = SOURCE.read_text(encoding="utf-8")
    invalid_start = source.index("const returnInvalidMetaSignature")
    invalid_end = source.index("const widgetAssistantWebhook")
    invalid_block = source[invalid_start:invalid_end]

    assert "type: 'n8n-nodes-base.respondToWebhook'" in invalid_block
    assert "responseCode: 403" in invalid_block
    assert "Invalid signature" in invalid_block
    assert "const metaSignatureRoute = routeMetaWebhookResponse" in source
    assert ".onCase(1, returnInvalidMetaSignature)" in source


def test_meta_messenger_duplicate_message_is_acknowledged_without_context_lookup():
    source = SOURCE.read_text(encoding="utf-8")
    prepare_start = source.index("name: 'Prepare Meta Webhook Response'")
    route_start = source.index("name: 'Route Meta Webhook Response'")
    prepare_block = source[prepare_start:route_start]

    assert "const processableEvents = [];" in prepare_block
    assert "const duplicate = verification.duplicate === true;" in prepare_block
    assert "if (verified && !duplicate && !ignored_event)" in prepare_block
    assert "processable_events: processableEvents" in prepare_block
    assert "name: 'Acknowledge Duplicate Meta Messenger Event'" not in source
    assert ".onCase(1, acknowledgeDuplicateMetaMessengerEvent)" not in source
    assert "acknowledgeDuplicateMetaMessengerEvent.to(getMessengerClinicContext" not in source


def test_meta_messenger_registers_and_claims_turn_before_ai_context_lookup():
    source = SOURCE.read_text(encoding="utf-8")
    workflow_block = source[source.index("export default workflow"):]

    assert "DJANGO_MESSENGER_AI_TURN_REGISTER_URL_EXPR" in source
    assert "DJANGO_MESSENGER_AI_TURN_CLAIM_URL_EXPR" in source
    assert "/messenger/ai/turn/register/" in source
    assert "/messenger/ai/turn/claim/" in source
    assert "name: 'Expand Messenger Processable Events'" in source
    assert "name: 'Register Messenger Turn'" in source
    assert "name: 'Route Messenger Turn Registration'" in source
    assert "name: 'Acknowledge Queued Messenger Turn'" not in source
    assert "name: 'Claim Messenger Turn'" in source
    assert "name: 'Route Messenger Turn Claim'" in source
    assert source.index("name: 'Verify Meta Signature'") < source.index("name: 'Expand Messenger Processable Events'")
    assert source.index("name: 'Expand Messenger Processable Events'") < source.index("name: 'Register Messenger Turn'")
    assert source.index("name: 'Register Messenger Turn'") < source.index("name: 'Claim Messenger Turn'")
    assert source.index("name: 'Claim Messenger Turn'") < source.index("name: 'Get Messenger Clinic Context'")
    assert "process_now" in source[source.index("name: 'Route Messenger Turn Registration'"):source.index("const claimMessengerTurn")]
    assert "claimed" in source[source.index("name: 'Route Messenger Turn Claim'"):source.index("const getMessengerClinicContext")]
    assert "const messengerRouteBranch = expandMessengerProcessableEvents\n  .to(registerMessengerTurn" in source
    assert "routeMessengerTurnRegistration.onCase(0, messengerClaimBranch)" in source
    assert "const messengerClaimBranch = claimMessengerTurn\n  .to(attachMessengerTurnClaim)\n  .to(routeMessengerTurnClaim.onCase(0, messengerAssistantBranch));" in source
    assert ".onCase(1, acknowledgeQueuedMessengerTurn)" not in source
    assert "acknowledgeQueuedMessengerTurn.to(getMessengerClinicContext" not in source


def test_combined_bridge_uses_claimed_messenger_batch_as_ai_input():
    source = SOURCE.read_text(encoding="utf-8")
    claim_start = source.index("name: 'Attach Messenger Turn Claim'")
    route_claim_start = source.index("name: 'Route Messenger Turn Claim'")
    messenger_start = source.index("name: 'Build Messenger Shared Input'")
    widget_start = source.index("name: 'Build Widget Shared Input'")
    claim_block = source[claim_start:route_claim_start]
    messenger_block = source[messenger_start:widget_start]

    assert "$items('Route Messenger Turn Registration', 0)" in claim_block
    assert "$items('Expand Messenger Processable Events')" not in messenger_block
    assert "$items('Claim Messenger Turn')" not in messenger_block
    assert "message: claim.message || input.message" in messenger_block
    assert "turn_token: claim.turn_token || input.turn_token || ''" in messenger_block
    assert "input_sequence: claim.input_sequence || input.input_sequence || 0" in messenger_block
    assert "turn_messages: claim.messages || input.turn_messages || []" in messenger_block
    assert "history: claim.history || input.history || []" in messenger_block
    assert "':turn:' + (claim.turn_token || input.turn_token || 'no-turn')" in messenger_block


def test_combined_bridge_completes_messenger_turn_before_facebook_send():
    source = SOURCE.read_text(encoding="utf-8")
    workflow_block = source[source.index("export default workflow"):]
    complete_start = source.index("name: 'Complete Messenger Turn'")
    prepare_current_start = source.index("name: 'Prepare Current Messenger Reply'")
    send_start = source.index("name: 'Send Facebook Reply'")
    complete_block = source[complete_start:prepare_current_start]
    prepare_current_block = source[prepare_current_start:send_start]

    assert "DJANGO_MESSENGER_AI_TURN_COMPLETE_URL_EXPR" in source
    assert "/messenger/ai/turn/complete/" in source
    assert "reply_text: $json.reply_text" in complete_block
    assert "turn_token: $json.turn_token" in complete_block
    assert "input_sequence: $json.input_sequence" in complete_block
    assert "completion.send_reply" in prepare_current_block
    assert ".onCase(0, completeMessengerTurn.to(authorizeMessengerSend).to(prepareCurrentMessengerReply).to(sendFacebookReply))" in source
    assert ".onCase(0, sendFacebookReply)" not in workflow_block


def test_combined_bridge_gateway_payload_sends_turn_metadata_for_server_side_mutations():
    source = SOURCE.read_text(encoding="utf-8")
    gateway_block = _extract_django_ai_gateway_block(source)

    assert 'psid: $json.psid || ""' in gateway_block
    assert 'turn_token: $json.turn_token || ""' in gateway_block
    assert 'input_sequence: $json.input_sequence || 0' in gateway_block
    assert "name: 'book_confirmed_appointment'" not in source
    assert "name: 'cancel_verified_appointment'" not in source
    assert "name: 'reschedule_verified_appointment'" not in source


def test_meta_messenger_ignored_events_are_acknowledged_without_context_lookup():
    source = SOURCE.read_text(encoding="utf-8")
    normalize_start = source.index("name: 'Normalize Messenger Request'")
    normalize_end = source.index("const verifyMetaSignature")
    normalize_block = source[normalize_start:normalize_end]
    prepare_start = source.index("name: 'Prepare Meta Webhook Response'")
    route_start = source.index("name: 'Route Meta Webhook Response'")
    prepare_block = source[prepare_start:route_start]

    assert "const ignoredCandidates = [];" in normalize_block
    assert "ignored_event: true" in normalize_block
    assert "if (!items.length)" in normalize_block
    assert "return [];" not in normalize_block
    assert "const ignored_event = source.ignored_event === true;" in prepare_block
    assert "if (verified && !duplicate && !ignored_event)" in prepare_block
    assert "processable_events: processableEvents" in prepare_block
    assert "name: 'Acknowledge Ignored Meta Messenger Event'" not in source
    assert ".onCase(2, acknowledgeIgnoredMetaMessengerEvent)" not in source
    assert "acknowledgeIgnoredMetaMessengerEvent.to(getMessengerClinicContext" not in source


def test_meta_messenger_normalizer_parses_raw_string_body_for_routing():
    source = SOURCE.read_text(encoding="utf-8")
    normalize_start = source.index("name: 'Normalize Messenger Request'")
    normalize_end = source.index("const verifyMetaSignature")
    normalize_block = source[normalize_start:normalize_end]

    assert "const inputItem = $input.first();" in normalize_block
    assert "let rawBody = typeof input.rawBody === 'string' ? input.rawBody : '';" in normalize_block
    assert "let body = input.body || input;" in normalize_block
    assert "if (typeof body === 'string')" in normalize_block
    assert "body = JSON.parse(body);" in normalize_block
    assert "catch (error)" in normalize_block
    assert "for (const entry of entries)" in normalize_block
    assert "for (const messaging of messagingItems)" in normalize_block
    assert "messaging.message?.quick_reply?.payload" in normalize_block
    assert normalize_block.index("body = JSON.parse(body);") < normalize_block.index("for (const entry of entries)")


def test_meta_messenger_normalizer_decodes_binary_raw_body_for_signature_verification():
    source = SOURCE.read_text(encoding="utf-8")
    normalize_start = source.index("name: 'Normalize Messenger Request'")
    normalize_end = source.index("const verifyMetaSignature")
    normalize_block = source[normalize_start:normalize_end]

    assert "typeof inputItem.binary?.data?.data === 'string'" in normalize_block
    assert "Buffer.from(inputItem.binary.data.data, 'base64').toString('utf8')" in normalize_block
    assert "if (!rawBody) {\n  return [];\n}" not in normalize_block


def test_combined_bridge_routes_messenger_quick_replies_without_ai_agent():
    source = SOURCE.read_text(encoding="utf-8")

    assert "name: 'Resolve Assistant Mode'" in source
    assert "name: 'Route Assistant Mode'" in source
    assert "name: 'Get Messenger Quick Replies'" in source
    assert "name: 'Attach Messenger Quick Replies Input'" in source
    assert "name: 'Complete Messenger Quick Reply Turn'" in source
    assert "name: 'Prepare Messenger Quick Replies'" in source
    assert "/messenger/n8n-webhook/" in source
    assert "messenger_response_mode" in source
    assert "should_use_quick_replies" in source
    assert "messaging.postback?.payload" in source
    assert "messaging.message?.quick_reply?.payload" in source
    assert "const messengerQuickReplyBranch = getMessengerQuickReplies\n  .to(attachMessengerQuickRepliesInput)\n  .to(completeMessengerQuickReplyTurn)\n  .to(authorizeMessengerQuickReplySend)\n  .to(prepareMessengerQuickReplies)\n  .to(sendFacebookReply);" in source
    assert "getMessengerQuickReplies\n  .to(completeMessengerTurn)" not in source
    assert ".onCase(1, messengerQuickReplyBranch)" in source
    assert "const replyItems = $items('Attach Messenger Quick Replies Input');" in source
    shared_input_start = source.index("name: 'Build Messenger Shared Input'")
    shared_input_end = source.index("name: 'Build Widget Shared Input'")
    shared_input_block = source[shared_input_start:shared_input_end]
    quick_reply_start = source.index("name: 'Get Messenger Quick Replies'")
    quick_reply_end = source.index("name: 'Prepare Messenger Quick Replies'")
    quick_reply_block = source[quick_reply_start:quick_reply_end]
    assert "raw_message: source.raw_message" not in shared_input_block
    assert "raw_postback: source.raw_postback" not in shared_input_block
    assert "$items('Route Assistant Mode', 1)" in quick_reply_block
    assert "text: $json.raw_message || $json.message" in quick_reply_block
    assert "postback: $json.raw_postback || $json.postback || \"\"" in quick_reply_block
    assert "turn_token: $json.turn_token || \"\"" in quick_reply_block
    assert "input_sequence: $json.input_sequence || 0" in quick_reply_block


def test_complete_messenger_quick_reply_turn_uses_current_item_identity():
    source = SOURCE.read_text(encoding="utf-8")
    complete_start = source.index("name: 'Complete Messenger Quick Reply Turn'")
    prepare_current_start = source.index("name: 'Prepare Current Messenger Reply'")
    complete_block = source[complete_start:prepare_current_start]

    assert 'page_id: $json.page_id' in complete_block
    assert 'psid: $json.psid' in complete_block
    assert 'turn_token: $json.turn_token' in complete_block
    assert 'input_sequence: $json.input_sequence || 0' in complete_block
    assert 'reply_text: (($json.replies || []).map((reply) => reply.text || "").filter(Boolean).join("\\\\n"))' in complete_block
    assert '$("Shared AI Input").item' not in complete_block
    assert '$json.reply_text ||' not in complete_block


def test_combined_bridge_facebook_send_errors_are_not_silenced():
    source = SOURCE.read_text(encoding="utf-8")
    send_start = source.index("name: 'Send Facebook Reply'")
    send_end = source.index("const returnWidgetReply")
    send_block = source[send_start:send_end]

    assert "responseFormat: 'json'" in send_block
    assert "neverError: true" not in send_block


def test_combined_bridge_caps_messenger_quick_replies_for_meta_limit():
    source = SOURCE.read_text(encoding="utf-8")
    prepare_start = source.index("name: 'Prepare Messenger Quick Replies'")
    prepare_end = source.index("const callDjangoAiGateway")
    prepare_block = source[prepare_start:prepare_end]

    assert ".slice(0, 13).map" in prepare_block
    assert "title: String(option.title || '').slice(0, 20)" in prepare_block
    assert "payload: String(option.payload || '')" in prepare_block


def test_combined_bridge_facebook_bodies_include_messaging_type_response():
    source = SOURCE.read_text(encoding="utf-8")

    assert "messaging_type: 'RESPONSE'" in source


def test_combined_bridge_authorizes_messenger_turn_immediately_before_facebook_send():
    source = SOURCE.read_text(encoding="utf-8")

    assert "DJANGO_MESSENGER_AI_TURN_AUTHORIZE_SEND_URL_EXPR" in source
    assert "/messenger/ai/turn/authorize-send/" in source
    assert "name: 'Authorize Messenger Send'" in source
    assert "name: 'Authorize Messenger Quick Reply Send'" in source
    assert "name: 'Authorize Forced Messenger Quick Reply Send'" in source
    assert "const sharedChannelReplyRoute = routeChannelReply\n  .onCase(0, completeMessengerTurn.to(authorizeMessengerSend).to(prepareCurrentMessengerReply).to(sendFacebookReply))" in source
    assert "const messengerQuickReplyBranch = getMessengerQuickReplies\n  .to(attachMessengerQuickRepliesInput)\n  .to(completeMessengerQuickReplyTurn)\n  .to(authorizeMessengerQuickReplySend)\n  .to(prepareMessengerQuickReplies)\n  .to(sendFacebookReply)" in source
    assert "const forcedMessengerQuickReplyBranch = getForcedMessengerQuickReplies\n  .to(attachForcedMessengerQuickRepliesInput)\n  .to(completeForcedMessengerQuickReplyTurn)\n  .to(authorizeForcedMessengerQuickReplySend)\n  .to(prepareForcedMessengerQuickReplies)\n  .to(sendFacebookReply)" in source


def test_combined_bridge_uses_django_response_identity_for_messenger_quick_replies():
    source = SOURCE.read_text(encoding="utf-8")
    prepare_start = source.index("name: 'Prepare Messenger Quick Replies'")
    prepare_end = source.index("const callDjangoAiGateway")
    prepare_block = source[prepare_start:prepare_end]

    assert "$items('Resolve Assistant Mode')[0]" not in prepare_block
    assert "sources[itemIndex]" not in prepare_block
    assert "const psid = input.psid || '';" in prepare_block
    assert "if (!pageToken || !psid) { continue; }" in prepare_block


def test_combined_bridge_omits_empty_messenger_quick_replies_for_meta():
    source = SOURCE.read_text(encoding="utf-8")
    prepare_start = source.index("name: 'Prepare Messenger Quick Replies'")
    prepare_end = source.index("const callDjangoAiGateway")
    prepare_block = source[prepare_start:prepare_end]

    assert "const quickReplies = (action.options || []).slice(0, 13).map" in prepare_block
    assert "if (quickReplies.length) { message.quick_replies = quickReplies; }" in prepare_block
    assert "quick_replies: (action.options || []).slice(0, 13).map" not in prepare_block


def test_combined_bridge_messenger_ai_mode_is_independent_from_widget_ai_switch():
    source = SOURCE.read_text(encoding="utf-8")

    assert "const useAi = channel === 'messenger' ? messengerMode === 'ai' : item.context?.ai?.is_ai_enabled === true;" in source
    assert "Messenger must use messenger_response_mode. Widget keeps is_ai_enabled." in source


def test_combined_bridge_carries_messenger_identity_after_turn_filters():
    source = SOURCE.read_text(encoding="utf-8")
    build_start = source.index("name: 'Build Messenger Shared Input'")
    widget_start = source.index("name: 'Build Widget Shared Input'")
    build_block = source[build_start:widget_start]
    claim_start = source.index("name: 'Claim Messenger Turn'")
    claim_route_start = source.index("name: 'Route Messenger Turn Claim'")
    claim_block = source[claim_start:claim_route_start]
    context_start = source.index("name: 'Get Messenger Clinic Context'")
    context_end = source.index("const getWidgetClinicContext")
    context_block = source[context_start:context_end]

    assert "name: 'Attach Messenger Turn Registration'" in source
    assert "name: 'Attach Messenger Turn Claim'" in source
    assert "name: 'Attach Messenger Context'" in source
    assert 'page_id: $json.page_id' in claim_block
    assert 'psid: $json.psid' in claim_block
    assert 'turn_token: $json.turn_token || ""' in claim_block
    assert 'page_id: $json.page_id' in context_block
    assert "$items('Route Messenger Turn Registration', 0)" in claim_block
    assert "$items('Route Messenger Turn Claim', 0)" in context_block
    assert "$('Expand Messenger Processable Events')" not in claim_block
    assert "$('Expand Messenger Processable Events')" not in context_block
    assert "$items('Expand Messenger Processable Events')" not in build_block
    assert "$items('Claim Messenger Turn')" not in build_block
    assert "const rawContext = input.context || {};" in build_block
    assert "const claim = input.claim || {};" in build_block
    assert "...input" in build_block


def test_combined_bridge_reply_paths_use_current_item_after_assistant_mode_filter():
    source = SOURCE.read_text(encoding="utf-8")
    gateway_block = _extract_django_ai_gateway_block(source)
    quick_start = source.index("name: 'Complete Messenger Quick Reply Turn'")
    quick_end = source.index("name: 'Prepare Messenger Quick Replies'")
    quick_complete_block = source[quick_start:quick_end]
    prepare_start = source.index("name: 'Prepare Channel Reply'")
    route_start = source.index("const routeChannelReply")
    prepare_block = source[prepare_start:route_start]
    complete_start = source.index("name: 'Complete Messenger Turn'")
    current_start = source.index("name: 'Prepare Current Messenger Reply'")
    complete_block = source[complete_start:current_start]
    current_end = source.index("const sendFacebookReply")
    current_block = source[current_start:current_end]

    assert "name: 'Attach Django AI Gateway Input'" in source
    assert "name: 'Attach Messenger Quick Replies Input'" in source
    assert '$("Shared AI Input").item' not in gateway_block
    assert '$("Shared AI Input").item' not in quick_complete_block
    assert '$("Shared AI Input").item' not in complete_block
    assert "$items('Shared AI Input')" not in prepare_block
    assert "$items('Prepare Channel Reply')" not in current_block
    assert "$items('Route Assistant Mode', 0)" in source
    assert "$items('Route Assistant Mode', 1)" in source
    assert "$items('Route Channel Reply', 0)" in current_block
    assert 'channel: $json.channel' in gateway_block
    assert 'page_id: $json.page_id || ""' in gateway_block
    assert 'turn_token: $json.turn_token || ""' in gateway_block
    assert 'reply_text: $json.reply_text || ""' in complete_block


def test_legacy_messenger_workflow_source_is_not_checked_in():
    assert not LEGACY_SOURCE.exists()
