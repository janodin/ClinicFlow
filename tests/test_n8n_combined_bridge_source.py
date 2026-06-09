import json
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


def test_combined_bridge_uses_one_shared_ai_core():
    source = SOURCE.read_text(encoding="utf-8")

    assert "name: 'KliniAssist Shared AI Agent'" in source
    assert "name: 'Shared Chat Model'" in source
    assert "name: 'Shared Conversation Memory'" in source
    assert "name: 'Clinic Messenger AI Agent'" not in source
    assert "name: 'Widget Assistant AI Agent'" not in source
    assert "name: 'Widget Chat Model'" not in source


def test_combined_bridge_uses_kliniassist_technical_namespace():
    source = SOURCE.read_text(encoding="utf-8")
    legacy_prefix = "clinic" + "flow"
    legacy_agent = "clinic" + "FlowSharedAiAgent"

    assert "path: 'kliniassist-messenger'" in source
    assert "path: 'kliniassist-widget-assistant'" in source
    assert "const kliniAssistSharedAiAgent" in source
    assert "const messengerAiReplyBranch = kliniAssistSharedAiAgent\n  .to(prepareChannelReply)" in source
    assert ".onCase(0, messengerAiReplyBranch)" in source
    assert f"path: '{legacy_prefix}-messenger'" not in source
    assert f"path: '{legacy_prefix}-widget-assistant'" not in source
    assert legacy_agent not in source


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
    assert "DJANGO_MESSENGER_AI_BOOK_URL_EXPR" in source
    assert "url: DJANGO_MESSENGER_WEBHOOK_URL_EXPR" in source
    assert "DJANGO_MESSENGER_AI_BOOK_URL_EXPR" in source
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


def test_combined_bridge_tools_inject_tenant_identity_from_shared_context():
    source = SOURCE.read_text(encoding="utf-8")
    widget_clinic_slug_expression = "clinic_slug: expr('{{ $(\"Shared AI Input\").item.json.channel === \"widget\" ? $(\"Shared AI Input\").item.json.clinic_slug : \"\" }}')"
    match_start = source.index("name: 'match_services'")
    availability_start = source.index("name: 'check_availability'")
    book_start = source.index("name: 'book_confirmed_appointment'")
    quick_replies_start = source.index("const getMessengerQuickReplies")
    match_services_tool_block = source[match_start:availability_start]
    check_availability_tool_block = source[availability_start:book_start]
    book_confirmed_appointment_tool_block = source[book_start:quick_replies_start]

    assert "clinic.example.com" not in source
    assert "fromAi('page_id'" not in source
    assert "fromAi('clinic_slug'" not in source
    assert '$("Shared AI Input").item.json.page_id' in source
    assert '$("Shared AI Input").item.json.clinic_slug' in source
    assert "/messenger/ai/book/" in source
    assert "/messenger/ai/widget/book/" in source
    assert widget_clinic_slug_expression in match_services_tool_block
    assert widget_clinic_slug_expression in check_availability_tool_block
    assert widget_clinic_slug_expression in book_confirmed_appointment_tool_block


def test_combined_bridge_messenger_booking_tool_sends_psid_from_shared_context():
    source = SOURCE.read_text(encoding="utf-8")
    book_start = source.index("name: 'book_confirmed_appointment'")
    quick_replies_start = source.index("const getMessengerQuickReplies")
    book_confirmed_appointment_tool_block = source[book_start:quick_replies_start]

    assert "psid: expr('{{ $(\"Shared AI Input\").item.json.channel === \"messenger\" ? $(\"Shared AI Input\").item.json.psid : \"\" }}')" in book_confirmed_appointment_tool_block


def test_combined_bridge_keeps_page_token_out_of_ai_prompt_context():
    source = SOURCE.read_text(encoding="utf-8")
    messenger_start = source.index("name: 'Build Messenger Shared Input'")
    widget_start = source.index("name: 'Build Widget Shared Input'")
    agent_start = source.index("name: 'KliniAssist Shared AI Agent'")
    fallback_start = source.index("const prepareSharedFallback")
    prepare_start = source.index("name: 'Prepare Channel Reply'")
    route_start = source.index("const routeChannelReply")
    messenger_block = source[messenger_start:widget_start]
    agent_block = source[agent_start:fallback_start]
    prepare_block = source[prepare_start:route_start]

    assert "const { page_token: pageToken, ...safeContext } = rawContext;" in messenger_block
    assert "access_token: pageToken || ''" in messenger_block
    assert "context: safeContext" in messenger_block
    assert "JSON.stringify($(\"Shared AI Input\").item.json.context || {})" in agent_block
    assert "access_token: shared.access_token || ''" in prepare_block
    assert "context.page_token" not in source


def test_combined_bridge_ai_http_tools_have_explicit_timeouts():
    source = SOURCE.read_text(encoding="utf-8")
    tool_names = [
        "match_services",
        "check_availability",
        "book_confirmed_appointment",
        "find_verified_appointment",
        "cancel_verified_appointment",
        "reschedule_verified_appointment",
    ]

    for index, tool_name in enumerate(tool_names):
        start = source.index(f"name: '{tool_name}'")
        end = source.index(f"name: '{tool_names[index + 1]}'") if index + 1 < len(tool_names) else source.index("const getMessengerQuickReplies")
        tool_block = source[start:end]
        assert "options: { timeout: 15000 }" in tool_block


def test_combined_bridge_widget_path_uses_shared_ai_agent_and_widget_context():
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


def test_combined_bridge_widget_ai_prompt_requires_tools_and_explicit_confirmation():
    source = SOURCE.read_text(encoding="utf-8")
    agent_start = source.index("name: 'KliniAssist Shared AI Agent'")
    agent_end = source.index("const prepareSharedFallback")
    agent_block = source[agent_start:agent_end]

    assert "Use match_services, check_availability, and book_confirmed_appointment for booking." in agent_block
    assert "Use business_hours and unavailable_dates from Clinic context JSON" in agent_block
    assert "Do not answer specific appointment availability from business_hours alone." in agent_block
    assert "Collect service, date/time, full name, phone, and email before booking." in agent_block
    assert "Ask for explicit confirmation before booking." in agent_block
    assert "Patient email required for booking" in source
    assert "Patient email if provided, otherwise blank" not in source
    assert "Never expose secrets, invent clinic data, give medical diagnosis, or create appointments without tool validation." in agent_block
    assert "Widget replies must be concise and friendly." in agent_block
    assert "/messenger/ai/widget/services/" in source
    assert "/messenger/ai/widget/availability/" in source
    assert "/messenger/ai/widget/book/" in source


def test_combined_bridge_includes_verified_appointment_management_tools():
    source = SOURCE.read_text(encoding="utf-8")
    lookup_start = source.index("name: 'find_verified_appointment'")
    cancel_start = source.index("name: 'cancel_verified_appointment'")
    reschedule_start = source.index("name: 'reschedule_verified_appointment'")
    quick_replies_start = source.index("const getMessengerQuickReplies")
    lookup_block = source[lookup_start:cancel_start]
    cancel_block = source[cancel_start:reschedule_start]
    reschedule_block = source[reschedule_start:quick_replies_start]

    assert "DJANGO_MESSENGER_AI_APPOINTMENT_LOOKUP_URL_EXPR" in lookup_block
    assert "DJANGO_WIDGET_AI_APPOINTMENT_LOOKUP_URL_EXPR" in lookup_block
    assert "KliniAssist N8N Webhook Secret" in lookup_block
    assert "DJANGO_MESSENGER_AI_APPOINTMENT_CANCEL_URL_EXPR" in cancel_block
    assert "DJANGO_WIDGET_AI_APPOINTMENT_CANCEL_URL_EXPR" in cancel_block
    assert "KliniAssist N8N Webhook Secret" in cancel_block
    assert "DJANGO_MESSENGER_AI_APPOINTMENT_RESCHEDULE_URL_EXPR" in reschedule_block
    assert "DJANGO_WIDGET_AI_APPOINTMENT_RESCHEDULE_URL_EXPR" in reschedule_block
    assert "KliniAssist N8N Webhook Secret" in reschedule_block
    for block in [lookup_block, cancel_block, reschedule_block]:
        assert "fromAi('page_id'" not in block
        assert "fromAi('clinic_slug'" not in block
        assert '$("Shared AI Input").item.json.page_id' in block
        assert '$("Shared AI Input").item.json.clinic_slug' in block


def test_combined_bridge_prompt_requires_verified_cancel_and_reschedule_confirmation():
    source = SOURCE.read_text(encoding="utf-8")
    agent_start = source.index("name: 'KliniAssist Shared AI Agent'")
    agent_end = source.index("const prepareSharedFallback")
    agent_block = source[agent_start:agent_end]

    assert "Use find_verified_appointment before canceling or rescheduling." in agent_block
    assert "Ask for appointment reference code and phone number before appointment management lookup." in agent_block
    assert "Summarize the verified appointment and requested action before mutation." in agent_block
    assert "Ask for explicit confirmation before canceling or rescheduling." in agent_block
    assert "Use cancel_verified_appointment and reschedule_verified_appointment only after explicit confirmation." in agent_block
    assert "Do not use user-supplied appointment IDs, patient IDs, clinic IDs, or service IDs for appointment management." in agent_block


def test_combined_bridge_prompt_forbids_phone_disclosure_after_failed_appointment_verification():
    source = SOURCE.read_text(encoding="utf-8")
    agent_start = source.index("name: 'KliniAssist Shared AI Agent'")
    agent_end = source.index("const prepareSharedFallback")
    agent_block = source[agent_start:agent_end]

    assert "If appointment verification fails, use only the tool error and ask the user to re-enter the reference code and phone number." in agent_block
    assert "Never reveal, correct, infer, or confirm the stored appointment phone number" in agent_block
    assert "Never say booked under" in agent_block
    assert "Appointment summaries may show patient_phone_last4 only; do not display full patient phone numbers." in agent_block


def test_combined_bridge_prompt_uses_availability_suggestion_metadata_and_hides_faq_source():
    source = SOURCE.read_text(encoding="utf-8")
    agent_start = source.index("name: 'KliniAssist Shared AI Agent'")
    agent_end = source.index("const prepareSharedFallback")
    agent_block = source[agent_start:agent_end]

    assert "If requested booking or reschedule date is before Today" in agent_block
    assert "Previous dates and past times are not available" in agent_block
    assert "Do not ask for a time, offer alternatives, or call availability for previous dates" in agent_block
    assert "Use check_availability suggestion_type metadata" in agent_block
    assert "nearest_time means the requested time is unavailable" in agent_block
    assert "next_available_date means the requested date has no slots" in agent_block
    assert "Use FAQ entries as clinic knowledge without citing the source" in agent_block
    assert "Do not say based on the FAQ, according to the FAQ, the FAQ says" in agent_block


def test_combined_bridge_prompt_includes_communication_tone_with_style_only_guardrails():
    source = SOURCE.read_text(encoding="utf-8")
    agent_start = source.index("name: 'KliniAssist Shared AI Agent'")
    agent_end = source.index("const prepareSharedFallback")
    agent_block = source[agent_start:agent_end]

    assert "Communication tone:" in agent_block
    assert "communication_tone_label" in agent_block
    assert "custom_tone_instructions" in agent_block
    assert "Tone affects wording only" in agent_block
    assert "must not override clinic data, tool results, availability, booking confirmation, privacy, medical safety, or channel rules" in agent_block
    assert agent_block.index("Communication tone:") < agent_block.index("Use match_services, check_availability, and book_confirmed_appointment")


def test_combined_bridge_memory_key_changes_when_ai_settings_change():
    source = SOURCE.read_text(encoding="utf-8")
    memory_start = source.index("name: 'Shared Conversation Memory'")
    memory_end = source.index("const matchServicesTool")
    memory_block = source[memory_start:memory_end]

    assert 'context?.ai?.settings_updated_at' in memory_block
    assert ':shared:v4:' in memory_block


def test_combined_bridge_versions_upstream_session_key_by_ai_settings():
    source = SOURCE.read_text(encoding="utf-8")
    messenger_start = source.index("name: 'Build Messenger Shared Input'")
    widget_start = source.index("name: 'Build Widget Shared Input'")
    shared_input_start = source.index("const sharedAiInput")
    messenger_block = source[messenger_start:widget_start]
    widget_block = source[widget_start:shared_input_start]

    assert "const aiVersion = safeContext.ai?.settings_updated_at || 'unversioned';" in messenger_block
    assert "session_key: source.session_key + ':ai-settings:' + aiVersion" in messenger_block
    assert "const aiVersion = context.ai?.settings_updated_at || 'unversioned';" in widget_block
    assert "session_key: source.session_key + ':ai-settings:' + aiVersion" in widget_block


def test_channel_reply_code_preserves_regex_escapes_for_n8n():
    source = SOURCE.read_text(encoding="utf-8")

    assert "jsCode: `const sharedItems = $items('Shared AI Input');" in source
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


def test_meta_messenger_events_acknowledges_only_after_signature_verification():
    source = SOURCE.read_text(encoding="utf-8")

    meta_events_start = source.index("name: 'Meta Messenger Events'")
    meta_events_end = source.index("const normalizeMessengerRequest")
    meta_events_block = source[meta_events_start:meta_events_end]

    assert "responseMode: 'responseNode'" in meta_events_block
    assert "name: 'Acknowledge Meta Messenger Event'" in source
    assert "responseBody: 'EVENT_RECEIVED'" in source
    assert source.index("name: 'Verify Meta Signature'") < source.index("name: 'Acknowledge Meta Messenger Event'")
    assert ".add(metaMessengerEvents)\n  .to(acknowledgeMetaMessengerEvent)" not in source
    assert "const metaSignatureRoute = routeMetaSignature\n  .onCase(0, messengerRouteBranch)" in source
    assert source.index("name: 'Register Messenger Turn'") < source.index("name: 'Acknowledge Meta Messenger Event'")
    assert source.index("name: 'Acknowledge Meta Messenger Event'") < source.index("name: 'Claim Messenger Turn'")


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
    assert "signature_verified" in source
    assert "duplicate_message" in source
    assert "signature_invalid" in source
    assert "Get Messenger Clinic Context" in source
    assert source.index("name: 'Verify Meta Signature'") < source.index("name: 'Get Messenger Clinic Context'")
    assert ".to(normalizeMessengerRequest)\n  .to(verifyMetaSignature)\n  .to(metaSignatureRoute)" in source


def test_meta_messenger_signature_verification_sends_message_identity_to_django():
    source = SOURCE.read_text(encoding="utf-8")
    normalize_start = source.index("name: 'Normalize Messenger Request'")
    normalize_end = source.index("const verifyMetaSignature")
    normalize_block = source[normalize_start:normalize_end]
    verify_start = source.index("name: 'Verify Meta Signature'")
    verify_end = source.index("const routeMetaSignature")
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
    assert ".onCase(3, returnInvalidMetaSignature)" in source


def test_meta_messenger_duplicate_message_is_acknowledged_without_context_lookup():
    source = SOURCE.read_text(encoding="utf-8")
    route_start = source.index("name: 'Route Meta Signature'")
    route_end = source.index("const acknowledgeMetaMessengerEvent")
    route_block = source[route_start:route_end]

    assert "duplicate_message" in route_block
    assert "$json.duplicate ? \"true\" : \"false\"" in route_block
    assert ".onCase(1, acknowledgeDuplicateMetaMessengerEvent)" in source
    assert "acknowledgeDuplicateMetaMessengerEvent.to(getMessengerClinicContext" not in source


def test_meta_messenger_registers_and_claims_turn_before_ai_context_lookup():
    source = SOURCE.read_text(encoding="utf-8")
    workflow_block = source[source.index("export default workflow"):]

    assert "DJANGO_MESSENGER_AI_TURN_REGISTER_URL_EXPR" in source
    assert "DJANGO_MESSENGER_AI_TURN_CLAIM_URL_EXPR" in source
    assert "/messenger/ai/turn/register/" in source
    assert "/messenger/ai/turn/claim/" in source
    assert "name: 'Register Messenger Turn'" in source
    assert "name: 'Route Messenger Turn Registration'" in source
    assert "name: 'Acknowledge Queued Messenger Turn'" in source
    assert "name: 'Claim Messenger Turn'" in source
    assert "name: 'Route Messenger Turn Claim'" in source
    assert source.index("name: 'Verify Meta Signature'") < source.index("name: 'Register Messenger Turn'")
    assert source.index("name: 'Register Messenger Turn'") < source.index("name: 'Claim Messenger Turn'")
    assert source.index("name: 'Claim Messenger Turn'") < source.index("name: 'Get Messenger Clinic Context'")
    assert "process_now" in source[source.index("name: 'Route Messenger Turn Registration'"):source.index("const acknowledgeQueuedMessengerTurn")]
    assert "claimed" in source[source.index("name: 'Route Messenger Turn Claim'"):source.index("const getMessengerClinicContext")]
    assert "const messengerRouteBranch = registerMessengerTurn\n  .to(routeMessengerTurnRegistration" in source
    assert "const messengerClaimBranch = claimMessengerTurn\n  .to(routeMessengerTurnClaim.onCase(0, messengerAssistantBranch));" in source
    assert "acknowledgeQueuedMessengerTurn.to(getMessengerClinicContext" not in source


def test_combined_bridge_uses_claimed_messenger_batch_as_ai_input():
    source = SOURCE.read_text(encoding="utf-8")
    messenger_start = source.index("name: 'Build Messenger Shared Input'")
    widget_start = source.index("name: 'Build Widget Shared Input'")
    messenger_block = source[messenger_start:widget_start]

    assert "$items('Claim Messenger Turn')" in messenger_block
    assert "message: claim.message || source.message" in messenger_block
    assert "turn_token: claim.turn_token || ''" in messenger_block
    assert "input_sequence: claim.input_sequence || 0" in messenger_block
    assert "turn_messages: claim.messages || []" in messenger_block
    assert "history: claim.history || []" in messenger_block
    assert "':turn:' + (claim.turn_token || 'no-turn')" in messenger_block


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
    assert ".onCase(0, completeMessengerTurn.to(prepareCurrentMessengerReply).to(sendFacebookReply))" in source
    assert ".onCase(0, sendFacebookReply)" not in workflow_block


def test_combined_bridge_mutating_messenger_tools_send_turn_metadata():
    source = SOURCE.read_text(encoding="utf-8")
    book_start = source.index("name: 'book_confirmed_appointment'")
    lookup_start = source.index("name: 'find_verified_appointment'")
    cancel_start = source.index("name: 'cancel_verified_appointment'")
    reschedule_start = source.index("name: 'reschedule_verified_appointment'")
    quick_replies_start = source.index("const getMessengerQuickReplies")
    blocks = [
        source[book_start:lookup_start],
        source[cancel_start:reschedule_start],
        source[reschedule_start:quick_replies_start],
    ]

    for block in blocks:
        assert "psid: expr('{{ $(\"Shared AI Input\").item.json.channel === \"messenger\" ? $(\"Shared AI Input\").item.json.psid : \"\" }}')" in block
        assert "turn_token: expr('{{ $(\"Shared AI Input\").item.json.channel === \"messenger\" ? $(\"Shared AI Input\").item.json.turn_token : \"\" }}')" in block
        assert "input_sequence: expr('{{ $(\"Shared AI Input\").item.json.channel === \"messenger\" ? $(\"Shared AI Input\").item.json.input_sequence : 0 }}')" in block


def test_meta_messenger_ignored_events_are_acknowledged_without_context_lookup():
    source = SOURCE.read_text(encoding="utf-8")
    normalize_start = source.index("name: 'Normalize Messenger Request'")
    normalize_end = source.index("const verifyMetaSignature")
    normalize_block = source[normalize_start:normalize_end]
    route_start = source.index("name: 'Route Meta Signature'")
    route_end = source.index("const acknowledgeMetaMessengerEvent")
    route_block = source[route_start:route_end]

    assert "const ignoredCandidates = [];" in normalize_block
    assert "ignored_event: true" in normalize_block
    assert "if (!items.length)" in normalize_block
    assert "return [];" not in normalize_block
    assert "ignored_event" in route_block
    assert "$(\"Normalize Messenger Request\").item.json.ignored_event" in route_block
    assert ".onCase(2, acknowledgeIgnoredMetaMessengerEvent)" in source
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
    assert "name: 'Complete Messenger Quick Reply Turn'" in source
    assert "name: 'Prepare Messenger Quick Replies'" in source
    assert "/messenger/n8n-webhook/" in source
    assert "messenger_response_mode" in source
    assert "should_use_quick_replies" in source
    assert "messaging.postback?.payload" in source
    assert "messaging.message?.quick_reply?.payload" in source
    assert "const messengerQuickReplyBranch = getMessengerQuickReplies\n  .to(completeMessengerQuickReplyTurn)\n  .to(prepareMessengerQuickReplies)\n  .to(sendFacebookReply);" in source
    assert "getMessengerQuickReplies\n  .to(completeMessengerTurn)" not in source
    assert ".onCase(1, messengerQuickReplyBranch)" in source
    assert "const replyItems = $items('Get Messenger Quick Replies');" in source
    shared_input_start = source.index("name: 'Build Messenger Shared Input'")
    shared_input_end = source.index("name: 'Build Widget Shared Input'")
    shared_input_block = source[shared_input_start:shared_input_end]
    quick_reply_start = source.index("name: 'Get Messenger Quick Replies'")
    quick_reply_end = source.index("name: 'Prepare Messenger Quick Replies'")
    quick_reply_block = source[quick_reply_start:quick_reply_end]
    assert "raw_message: source.message" in shared_input_block
    assert "raw_postback: source.postback" in shared_input_block
    assert "text: $json.raw_message || $json.message" in quick_reply_block
    assert "postback: $json.raw_postback || $json.postback || \"\"" in quick_reply_block
    assert "turn_token: $json.turn_token || \"\"" in quick_reply_block
    assert "input_sequence: $json.input_sequence || 0" in quick_reply_block


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
    prepare_end = source.index("const kliniAssistSharedAiAgent")
    prepare_block = source[prepare_start:prepare_end]

    assert ".slice(0, 13).map" in prepare_block
    assert "title: String(option.title || '').slice(0, 20)" in prepare_block
    assert "payload: String(option.payload || '')" in prepare_block


def test_combined_bridge_facebook_bodies_include_messaging_type_response():
    source = SOURCE.read_text(encoding="utf-8")

    assert "messaging_type: 'RESPONSE'" in source


def test_combined_bridge_uses_django_response_identity_for_messenger_quick_replies():
    source = SOURCE.read_text(encoding="utf-8")
    prepare_start = source.index("name: 'Prepare Messenger Quick Replies'")
    prepare_end = source.index("const kliniAssistSharedAiAgent")
    prepare_block = source[prepare_start:prepare_end]

    assert "$items('Resolve Assistant Mode')[0]" not in prepare_block
    assert "sources[itemIndex]" not in prepare_block
    assert "const psid = input.psid || '';" in prepare_block
    assert "if (!pageToken || !psid) { continue; }" in prepare_block


def test_combined_bridge_omits_empty_messenger_quick_replies_for_meta():
    source = SOURCE.read_text(encoding="utf-8")
    prepare_start = source.index("name: 'Prepare Messenger Quick Replies'")
    prepare_end = source.index("const kliniAssistSharedAiAgent")
    prepare_block = source[prepare_start:prepare_end]

    assert "const quickReplies = (action.options || []).slice(0, 13).map" in prepare_block
    assert "if (quickReplies.length) { message.quick_replies = quickReplies; }" in prepare_block
    assert "quick_replies: (action.options || []).slice(0, 13).map" not in prepare_block


def test_combined_bridge_messenger_ai_mode_is_independent_from_widget_ai_switch():
    source = SOURCE.read_text(encoding="utf-8")

    assert "const useAi = channel === 'messenger' ? messengerMode === 'ai' : item.context?.ai?.is_ai_enabled === true;" in source
    assert "Messenger must use messenger_response_mode. Widget keeps is_ai_enabled." in source


def test_legacy_messenger_workflow_source_is_not_checked_in():
    assert not LEGACY_SOURCE.exists()
