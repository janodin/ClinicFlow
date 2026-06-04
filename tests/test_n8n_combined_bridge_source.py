from pathlib import Path


SOURCE = Path(__file__).resolve().parents[1] / "n8n_combined_messenger_widget_ai_bridge.ts"
LEGACY_SOURCE = Path(__file__).resolve().parents[1] / "messenger-workflow.ts"


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
    assert ".onCase(0, kliniAssistSharedAiAgent.to(prepareChannelReply).to(routeChannelReply" in source
    assert f"path: '{legacy_prefix}-messenger'" not in source
    assert f"path: '{legacy_prefix}-widget-assistant'" not in source
    assert legacy_agent not in source


def test_combined_bridge_django_base_url_can_target_local_development():
    source = SOURCE.read_text(encoding="utf-8")

    assert "process.env.DJANGO_BASE_URL" not in source
    assert "const DJANGO_BASE_URL_EXPR" in source
    assert "$env.DJANGO_BASE_URL" in source
    assert "https://178-105-83-211.nip.io" in source
    assert ".replace(/\\\\/$/, \"\")" in source


def test_meta_webhook_verification_uses_n8n_env_expression_not_process_env():
    source = SOURCE.read_text(encoding="utf-8")
    verify_start = source.index("name: 'Verify Meta Challenge'")
    verify_end = source.index("const returnVerificationResponse")
    verify_block = source[verify_start:verify_end]

    assert "process.env.MESSENGER_VERIFY_TOKEN" not in verify_block
    assert "{{ $env.MESSENGER_VERIFY_TOKEN || \"\" }}" in verify_block


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


def test_combined_bridge_widget_path_uses_shared_ai_agent_and_widget_context():
    source = SOURCE.read_text(encoding="utf-8")
    workflow_block = source[source.index("export default workflow"):]
    widget_start = workflow_block.index(".add(widgetAssistantWebhook)")
    widget_block = workflow_block[widget_start:]
    widget_shared_input_chain = ".add(widgetAssistantWebhook)\n  .to(normalizeWidgetRequest)\n  .to(getWidgetClinicContext)\n  .to(buildWidgetSharedInput)\n  .to(sharedAiInput)"
    shared_downstream_chain = ".to(sharedAiInput)\n      .to(resolveAssistantMode)\n      .to(routeAssistantMode"
    shared_route_start = workflow_block.index(shared_downstream_chain)
    shared_route_block = workflow_block[shared_route_start:widget_start]

    assert "name: 'Widget Assistant Webhook'" in source
    assert "name: 'Get Widget Clinic Context'" in source
    assert "/messenger/ai/widget/context/" in source
    assert widget_shared_input_chain in widget_block
    assert workflow_block.count(".to(sharedAiInput)") == 2
    assert workflow_block.count(".to(resolveAssistantMode)") == 1
    assert workflow_block.count(".to(routeAssistantMode") == 1
    assert ".onCase(0, kliniAssistSharedAiAgent.to(prepareChannelReply).to(routeChannelReply" in shared_route_block
    assert ".onCase(1, returnWidgetReply)" in shared_route_block


def test_combined_bridge_widget_ai_prompt_requires_tools_and_explicit_confirmation():
    source = SOURCE.read_text(encoding="utf-8")
    agent_start = source.index("name: 'KliniAssist Shared AI Agent'")
    agent_end = source.index("const prepareSharedFallback")
    agent_block = source[agent_start:agent_end]

    assert "Use match_services, check_availability, and book_confirmed_appointment for booking." in agent_block
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

    assert "/messenger/ai/appointment/lookup/" in lookup_block
    assert "/messenger/ai/widget/appointment/lookup/" in lookup_block
    assert "KliniAssist N8N Webhook Secret" in lookup_block
    assert "/messenger/ai/appointment/cancel/" in cancel_block
    assert "/messenger/ai/widget/appointment/cancel/" in cancel_block
    assert "KliniAssist N8N Webhook Secret" in cancel_block
    assert "/messenger/ai/appointment/reschedule/" in reschedule_block
    assert "/messenger/ai/widget/appointment/reschedule/" in reschedule_block
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


def test_combined_bridge_prompt_uses_availability_suggestion_metadata_and_hides_faq_source():
    source = SOURCE.read_text(encoding="utf-8")
    agent_start = source.index("name: 'KliniAssist Shared AI Agent'")
    agent_end = source.index("const prepareSharedFallback")
    agent_block = source[agent_start:agent_end]

    assert "Use check_availability suggestion_type metadata" in agent_block
    assert "nearest_time means the requested time is unavailable" in agent_block
    assert "next_available_date means the requested date has no slots" in agent_block
    assert "Use FAQ entries as clinic knowledge without citing the source" in agent_block
    assert "Do not say based on the FAQ, according to the FAQ, the FAQ says" in agent_block


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

    assert "const aiVersion = context.ai?.settings_updated_at || 'unversioned';" in messenger_block
    assert "session_key: source.session_key + ':ai-settings:' + aiVersion" in messenger_block
    assert "const aiVersion = context.ai?.settings_updated_at || 'unversioned';" in widget_block
    assert "session_key: source.session_key + ':ai-settings:' + aiVersion" in widget_block


def test_channel_reply_code_preserves_regex_escapes_for_n8n():
    source = SOURCE.read_text(encoding="utf-8")

    assert "jsCode: `const sharedItems = $items('Shared AI Input');" in source
    assert "<think[\\\\s\\\\S]*?<\\\\/think>" in source
    assert "<\\\\/?think>" in source


def test_meta_messenger_events_uses_explicit_webhook_ack_before_shared_ai_path():
    source = SOURCE.read_text(encoding="utf-8")

    meta_events_start = source.index("name: 'Meta Messenger Events'")
    meta_events_end = source.index("const normalizeMessengerRequest")
    meta_events_block = source[meta_events_start:meta_events_end]

    assert "responseMode: 'responseNode'" in meta_events_block
    assert "name: 'Acknowledge Meta Messenger Event'" in source
    assert "responseBody: 'EVENT_RECEIVED'" in source
    assert ".add(metaMessengerEvents)\n  .to(acknowledgeMetaMessengerEvent)\n  .to(normalizeMessengerRequest)" in source


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
    assert "signature_invalid" in source
    assert "Get Messenger Clinic Context" in source
    assert source.index("name: 'Verify Meta Signature'") < source.index("name: 'Get Messenger Clinic Context'")
    assert ".to(normalizeMessengerRequest)\n  .to(verifyMetaSignature)\n  .to(routeMetaSignature" in source


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
    assert "name: 'Prepare Messenger Quick Replies'" in source
    assert "/messenger/n8n-webhook/" in source
    assert "messenger_response_mode" in source
    assert "should_use_quick_replies" in source
    assert "messaging.postback?.payload" in source
    assert "messaging.message?.quick_reply?.payload" in source
    assert ".onCase(1, getMessengerQuickReplies.to(prepareMessengerQuickReplies).to(sendFacebookReply))" in source


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


def test_legacy_messenger_workflow_handles_quick_reply_payload_and_messaging_type():
    source = LEGACY_SOURCE.read_text(encoding="utf-8")

    assert "msg.message?.quick_reply?.payload" in source
    assert "messaging_type: 'RESPONSE'" in source
    assert "$input.first()" not in source
    assert "$('Format Django Payload').first()" not in source
    assert "return $input.all().map" in source
    assert "payloadItems[itemIndex]?.json?.psid" not in source
    assert "const psid = djangoResponse.psid || '';" in source
    assert "if (!pageToken || !psid) { continue; }" in source
    assert "if (quickReplies.length)" in source
    assert "message.quick_replies = quickReplies" in source
