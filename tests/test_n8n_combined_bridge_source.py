from pathlib import Path


SOURCE = Path(__file__).resolve().parents[1] / "n8n_combined_messenger_widget_ai_bridge.ts"
LEGACY_SOURCE = Path(__file__).resolve().parents[1] / "messenger-workflow.ts"


def test_combined_bridge_uses_one_shared_ai_core():
    source = SOURCE.read_text(encoding="utf-8")

    assert "name: 'ClinicFlow Shared AI Agent'" in source
    assert "name: 'Shared Chat Model'" in source
    assert "name: 'Shared Conversation Memory'" in source
    assert "name: 'Clinic Messenger AI Agent'" not in source
    assert "name: 'Widget Assistant AI Agent'" not in source
    assert "name: 'Widget Chat Model'" not in source


def test_combined_bridge_tools_inject_tenant_identity_from_shared_context():
    source = SOURCE.read_text(encoding="utf-8")

    assert "clinic.example.com" not in source
    assert "fromAi('page_id'" not in source
    assert "fromAi('clinic_slug'" not in source
    assert '$("Shared AI Input").item.json.page_id' in source
    assert '$("Shared AI Input").item.json.clinic_slug' in source
    assert "/messenger/ai/book/" in source
    assert "/messenger/ai/widget/book/" in source


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

    assert "const rawBody = typeof input.rawBody === 'string' ? input.rawBody : '';" in normalize_block
    assert "if (!rawBody)" in normalize_block
    assert "let body = input.body || input;" in normalize_block
    assert "if (typeof body === 'string')" in normalize_block
    assert "body = JSON.parse(body);" in normalize_block
    assert "catch (error)" in normalize_block
    assert "for (const entry of entries)" in normalize_block
    assert "for (const messaging of messagingItems)" in normalize_block
    assert "messaging.message?.quick_reply?.payload" in normalize_block
    assert normalize_block.index("body = JSON.parse(body);") < normalize_block.index("for (const entry of entries)")


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
    prepare_end = source.index("const clinicFlowSharedAiAgent")
    prepare_block = source[prepare_start:prepare_end]

    assert ".slice(0, 13).map" in prepare_block
    assert "title: String(option.title || '').slice(0, 20)" in prepare_block
    assert "payload: String(option.payload || '')" in prepare_block


def test_combined_bridge_facebook_bodies_include_messaging_type_response():
    source = SOURCE.read_text(encoding="utf-8")

    assert "messaging_type: 'RESPONSE'" in source


def test_combined_bridge_uses_paired_items_for_messenger_quick_replies():
    source = SOURCE.read_text(encoding="utf-8")
    prepare_start = source.index("name: 'Prepare Messenger Quick Replies'")
    prepare_end = source.index("const clinicFlowSharedAiAgent")
    prepare_block = source[prepare_start:prepare_end]

    assert "$items('Resolve Assistant Mode')[0]" not in prepare_block
    assert "const sources = $items('Resolve Assistant Mode');" in prepare_block
    assert "const source = sources[itemIndex]?.json || {};" in prepare_block


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
