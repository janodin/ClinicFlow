from pathlib import Path


SOURCE = Path(__file__).resolve().parents[1] / "n8n_combined_messenger_widget_ai_bridge.ts"


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

    assert "fromAi('page_id'" not in source
    assert "fromAi('clinic_slug'" not in source
    assert '$("Shared AI Input").item.json.page_id' in source
    assert '$("Shared AI Input").item.json.clinic_slug' in source
    assert "/messenger/ai/book/" in source
    assert "/messenger/ai/widget/book/" in source


def test_channel_reply_code_preserves_regex_escapes_for_n8n():
    source = SOURCE.read_text(encoding="utf-8")

    assert "jsCode: `const input = $input.first().json || {};" in source
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
