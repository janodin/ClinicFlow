# AI Availability Response Polish Design

## Goal

Improve KliniAssist booking replies in both Messenger AI mode and the website `Chat with Assistant` widget so unavailable appointment requests produce useful nearby suggestions, and clinic knowledge replies sound natural without citing FAQ as the source.

## Current State

Both AI channels use the combined n8n bridge and the same Django booking tools:

- Messenger AI mode calls `/messenger/ai/availability/` through the shared `check_availability` tool.
- Widget chat calls `/messenger/ai/widget/availability/` through the same shared `check_availability` tool.
- Both endpoints delegate to `messenger.ai_tools._check_availability_for_clinic()`.

The availability tool already returns alternatives, but the response does not explicitly distinguish nearest same-day time suggestions from next available date suggestions. The n8n prompt also gives booking rules, but it does not explicitly ban phrases like `based on the FAQ`.

## Approved Direction

Use Django as the source of truth for suggestion ordering and add prompt guidance so the AI presents the tool results naturally.

This keeps appointment availability deterministic, tenant-scoped, and shared across both channels while avoiding duplicated booking logic in n8n.

## Availability Behavior

When the user asks for a specific service and exact time:

- The AI must call `check_availability` with `preferred_starts_at`.
- If the requested time is available, the tool returns `available: true` and `selected_slot`.
- If the requested time is unavailable but the requested date has other slots, the tool returns the nearest same-day slots first.
- The AI should say the requested time is unavailable and offer those nearest times.

When the requested date has no slots:

- The tool searches forward for the first future date with available slots.
- The tool returns slots from that next available date as alternatives.
- The AI should say there are no slots on the requested date and suggest the returned next available date/time options.

When no future slots exist in the configured search window:

- The tool returns no alternatives.
- The AI should say no slots are available in the near future and suggest contacting the clinic or trying another date.

## Tool Response Contract

Extend `check_availability` and `check_widget_availability` responses with metadata that the AI can follow directly:

```json
{
  "found": true,
  "available": false,
  "selected_slot": null,
  "alternatives": [
    {
      "starts_at": "2026-06-05T01:30:00+00:00",
      "ends_at": "2026-06-05T02:00:00+00:00",
      "local_starts_at": "2026-06-05T09:30:00+08:00",
      "local_ends_at": "2026-06-05T10:00:00+08:00",
      "label": "9:30 AM"
    }
  ],
  "suggestion_type": "nearest_time|next_available_date|requested_date|none",
  "requested_date": "2026-06-05",
  "suggested_date": "2026-06-05"
}
```

`suggestion_type` meanings:

- `nearest_time`: exact requested time was unavailable, but nearby same-day slots exist.
- `next_available_date`: requested date has no slots, so alternatives come from the first future date with slots.
- `requested_date`: no exact time was requested and the alternatives are open slots for the requested/default date.
- `none`: no alternatives were found.

The existing fields remain intact so current n8n workflow behavior and tests do not lose compatibility.

## Natural FAQ Replies

Clinic FAQ entries remain part of the clinic context. The assistant should use them as clinic knowledge but not announce the source.

The shared AI prompt and default clinic AI prompt should instruct:

- Do not say `based on the FAQ`, `according to the FAQ`, `the FAQ says`, or similar source-citation phrasing.
- Answer FAQ-backed information as normal clinic information.
- If the clinic context does not contain the requested information, say the clinic has not provided that information and offer clinic contact details if available.

This applies to both Messenger AI mode and widget chat because both receive the same default instructions through Django context and the shared n8n agent prompt.

## Safety And Tenant Scoping

- Keep all clinic resolution in the existing Django endpoints.
- Keep service lookup clinic-scoped through the active Messenger page or widget clinic slug.
- Do not let n8n or the AI invent slot suggestions.
- Do not create appointments from alternatives until the user chooses one and explicitly confirms the summarized booking.
- Preserve `_process_guest_booking()` as the final booking gate for slot validation, patient matching, and double-booking prevention.

## Testing Strategy

Add or update regression tests for:

- `check_availability` returns `suggestion_type: nearest_time` and nearest same-day alternatives when an exact requested slot is unavailable but same-day slots remain.
- `check_availability` returns `suggestion_type: next_available_date` and alternatives from the first future available date when the requested date has no slots.
- `check_widget_availability` uses the same shared behavior.
- The default AI prompt bans FAQ source-citation phrasing.
- The combined n8n bridge shared agent prompt bans FAQ source-citation phrasing and tells the model how to use `suggestion_type`.

Run at minimum:

- `python -m pytest messenger/tests.py tests/test_n8n_combined_bridge_source.py`
- `python -m pytest widget/tests.py`
- `python manage.py check`

## Non-Goals

- Do not add patient accounts, patient portals, medical records, prescriptions, inventory, payments, or marketplace booking.
- Do not change the separate deterministic widget `Book an Appointment` flow.
- Do not add rich slot cards or Messenger buttons for AI replies.
- Do not move clinic availability rules into n8n.
- Do not expose FAQ labels, internal source labels, secrets, page tokens, or webhook credentials to patients.
