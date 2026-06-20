from messenger.ai_reply_formatting import format_ai_reply


def test_messenger_formats_availability_table_as_plain_text_options():
    raw = """<think>Need to call the availability tool.</think>
I should verify clinic slots before replying.

<b>Here are the **available** options:</b>

| Time | Status |
| --- | --- |
| 9:00 AM | Available |
| 9:30 AM | Available |

Please choose *one* option."""

    assert format_ai_reply(raw, "messenger") == (
        "Here are the available options:\n\n"
        "1. Time: 9:00 AM; Status: Available\n"
        "2. Time: 9:30 AM; Status: Available\n\n"
        "Please choose one option."
    )


def test_widget_preserves_safe_markdown_and_tables_but_strips_html():
    raw = """<b>Please confirm:</b>

**Service:** Dental Cleaning

| Field | Value |
| --- | --- |
| Date/time | June 24, 2026 at 9:00 AM |
| Patient | Maria Santos |"""

    assert format_ai_reply(raw, "widget") == """Please confirm:

**Service:** Dental Cleaning

| Field | Value |
| --- | --- |
| Date/time | June 24, 2026 at 9:00 AM |
| Patient | Maria Santos |"""


def test_escaped_html_is_not_reintroduced_after_cleanup():
    raw = "&lt;script&gt;alert(1)&lt;/script&gt;Please confirm"

    assert format_ai_reply(raw, "widget") == "Please confirm"


def test_patient_facing_reschedule_cta_is_not_stripped_as_reasoning():
    raw = "Need to reschedule? Reply here and we can help."

    assert format_ai_reply(raw, "messenger") == "Need to reschedule? Reply here and we can help."


def test_voice_flattens_booking_confirmation_into_spoken_sentence():
    raw = """# BOOKING CONFIRMATION

**Service:** Dental Cleaning
**Date/time:** June 24, 2026 at 9:00 AM
**Patient:** Maria Santos

| Field | Value |
| --- | --- |
| Reminder | Arrive 10 minutes early |

- Bring your ID."""

    assert format_ai_reply(raw, "voice") == (
        "Service: Dental Cleaning. "
        "Date/time: June 24, 2026 at 9:00 AM. "
        "Patient: Maria Santos. "
        "Reminder: Arrive 10 minutes early. "
        "Bring your ID."
    )


def test_messenger_field_value_table_becomes_summary_lines():
    raw = """Please confirm these details:

| Field | Value |
| --- | --- |
| Service | Dental Cleaning |
| Date/time | June 24, 2026 at 9:00 AM |
| Patient | Maria Santos |"""

    assert format_ai_reply(raw, "messenger") == """Please confirm these details:

Service: Dental Cleaning
Date/time: June 24, 2026 at 9:00 AM
Patient: Maria Santos"""


def test_messenger_reply_is_capped_after_formatting():
    raw = "<think>Internal notes.</think>**" + ("A" * 2100) + "**"

    result = format_ai_reply(raw, "messenger")

    assert len(result) == 1900
    assert result.endswith("...")
    assert "Internal notes" not in result
    assert "**" not in result
