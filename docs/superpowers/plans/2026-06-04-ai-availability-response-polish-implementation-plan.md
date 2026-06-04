# AI Availability Response Polish Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Messenger AI mode and widget chat suggest nearest same-day times or the first next available date when requested slots are unavailable, and stop FAQ-backed answers from citing FAQ as the source.

**Architecture:** Keep Django as the deterministic availability source and expose clear suggestion metadata through the existing shared availability tool response. Keep n8n as the model orchestration layer and update only the shared agent prompt so both Messenger and widget channels inherit the same reply rules.

**Tech Stack:** Django, pytest, n8n Workflow SDK source file, PowerShell, existing virtualenv at `env/`.

---

## Scope Check

The approved spec covers one subsystem: AI booking response quality for unavailable slots and FAQ phrasing. It touches one shared Django tool contract plus prompt guidance in Django defaults and the combined n8n bridge.

## File Structure

- Modify `messenger/tests.py`: add regression tests for availability suggestion metadata and default prompt rules.
- Modify `messenger/ai_tools.py`: compute `suggestion_type`, `requested_date`, and `suggested_date` in `_check_availability_for_clinic()`.
- Modify `messenger/defaults.py`: update `DEFAULT_MESSENGER_AI_PROMPT` with natural FAQ and `suggestion_type` instructions.
- Modify `tests/test_n8n_combined_bridge_source.py`: lock shared n8n agent prompt rules.
- Modify `n8n_combined_messenger_widget_ai_bridge.ts`: update shared AI agent system message.
- Create `clinics/migrations/0014_update_ai_prompt_default.py`: generated migration for updated `ClinicAISettings.instructions` default.
- Create `messenger/migrations/0010_update_ai_prompt_default.py`: generated migration for updated `MessengerAISettings.instructions` default.

## Task 1: Add Django Availability Contract Tests

**Files:**
- Modify: `messenger/tests.py`
- Test: `messenger/tests.py`

- [ ] **Step 1: Add failing tests after `test_check_availability_returns_requested_slot_and_alternatives`**

Insert this block immediately after the existing `test_check_availability_returns_requested_slot_and_alternatives()` test:

```python

@pytest.mark.django_db
def test_check_availability_marks_nearest_time_when_requested_slot_is_taken():
    from messenger.ai_tools import check_availability

    clinic, _ = _create_messenger_clinic("owner_ai_nearest_time", "PAGEAI-NEAREST-TIME")
    service = Service.objects.create(clinic=clinic, name="Consultation", duration_minutes=30, price=0)
    target_date = timezone.localdate() + timedelta(days=1)
    ClinicBusinessHour.objects.create(clinic=clinic, weekday=target_date.weekday(), open_time=time(9), close_time=time(11))
    open_result = check_availability("PAGEAI-NEAREST-TIME", service.id, preferred_date=target_date.isoformat())
    requested_slot = open_result["alternatives"][1]["starts_at"]
    patient = Patient.objects.create(clinic=clinic, full_name="Existing Patient", phone="09999999999")
    Appointment.objects.create(
        clinic=clinic,
        patient=patient,
        service=service,
        starts_at=timezone.datetime.fromisoformat(requested_slot),
        ends_at=timezone.datetime.fromisoformat(requested_slot) + timedelta(minutes=30),
        status=Appointment.STATUS_CONFIRMED,
    )

    unavailable_result = check_availability("PAGEAI-NEAREST-TIME", service.id, preferred_starts_at=requested_slot)

    assert unavailable_result["available"] is False
    assert unavailable_result["suggestion_type"] == "nearest_time"
    assert unavailable_result["requested_date"] == target_date.isoformat()
    assert unavailable_result["suggested_date"] == target_date.isoformat()
    assert requested_slot not in [slot["starts_at"] for slot in unavailable_result["alternatives"]]
    assert {slot["local_starts_at"][:10] for slot in unavailable_result["alternatives"][:2]} == {target_date.isoformat()}


@pytest.mark.django_db
def test_check_availability_suggests_first_future_date_when_requested_date_has_no_slots():
    from messenger.ai_tools import check_availability

    clinic, _ = _create_messenger_clinic("owner_ai_next_available_date", "PAGEAI-NEXT-DATE")
    service = Service.objects.create(clinic=clinic, name="Consultation", duration_minutes=30, price=0)
    requested_date = timezone.localdate() + timedelta(days=1)
    next_available_date = requested_date + timedelta(days=1)
    ClinicBusinessHour.objects.create(clinic=clinic, weekday=next_available_date.weekday(), open_time=time(9), close_time=time(10))

    result = check_availability("PAGEAI-NEXT-DATE", service.id, preferred_date=requested_date.isoformat())

    assert result["available"] is False
    assert result["suggestion_type"] == "next_available_date"
    assert result["requested_date"] == requested_date.isoformat()
    assert result["suggested_date"] == next_available_date.isoformat()
    assert result["alternatives"]
    assert {slot["local_starts_at"][:10] for slot in result["alternatives"]} == {next_available_date.isoformat()}


@pytest.mark.django_db
def test_check_widget_availability_returns_shared_suggestion_metadata():
    from messenger.ai_tools import check_widget_availability

    clinic, _ = _create_messenger_clinic("owner_widget_next_available_date", "PAGE-WIDGET-NEXT-DATE")
    service = Service.objects.create(clinic=clinic, name="Consultation", duration_minutes=30, price=0)
    requested_date = timezone.localdate() + timedelta(days=1)
    next_available_date = requested_date + timedelta(days=1)
    ClinicBusinessHour.objects.create(clinic=clinic, weekday=next_available_date.weekday(), open_time=time(9), close_time=time(10))

    result = check_widget_availability(clinic.slug, service.id, preferred_date=requested_date.isoformat())

    assert result["found"] is True
    assert result["available"] is False
    assert result["suggestion_type"] == "next_available_date"
    assert result["requested_date"] == requested_date.isoformat()
    assert result["suggested_date"] == next_available_date.isoformat()
    assert {slot["local_starts_at"][:10] for slot in result["alternatives"]} == {next_available_date.isoformat()}
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
.\env\Scripts\activate; if ($?) { python -m pytest messenger/tests.py::test_check_availability_marks_nearest_time_when_requested_slot_is_taken messenger/tests.py::test_check_availability_suggests_first_future_date_when_requested_date_has_no_slots messenger/tests.py::test_check_widget_availability_returns_shared_suggestion_metadata -q }
```

Expected: FAIL because `suggestion_type`, `requested_date`, and `suggested_date` are not present yet, and date-level unavailable responses still report `available: true` when future alternatives exist.

## Task 2: Implement Availability Suggestion Metadata

**Files:**
- Modify: `messenger/ai_tools.py`
- Test: `messenger/tests.py`

- [ ] **Step 1: Replace `_check_availability_for_clinic()` with metadata-aware logic**

In `messenger/ai_tools.py`, replace the full `_check_availability_for_clinic()` function with:

```python
def _check_availability_for_clinic(clinic, service_id, preferred_starts_at=None, preferred_date=None):
    service = clinic.services.filter(pk=service_id, is_active=True, is_archived=False).first()
    if not service:
        return {
            "found": True,
            "available": False,
            "error": "Service not found.",
            "selected_slot": None,
            "alternatives": [],
            "suggestion_type": "none",
            "requested_date": None,
            "suggested_date": None,
        }

    try:
        requested_start = _parse_datetime(preferred_starts_at) if preferred_starts_at else None
        if requested_start:
            target_date = requested_start.astimezone(ZoneInfo(clinic.timezone)).date()
        elif preferred_date:
            target_date = date.fromisoformat(str(preferred_date))
        else:
            target_date = _clinic_localdate(clinic) + timedelta(days=1)
    except (ValueError, TypeError):
        return {
            "found": True,
            "available": False,
            "error": "Invalid date or time.",
            "selected_slot": None,
            "alternatives": [],
            "suggestion_type": "none",
            "requested_date": None,
            "suggested_date": None,
        }

    raw_slots = generate_slots(clinic, service, target_date)
    selected = None
    if requested_start:
        selected = next((slot for slot in raw_slots if slot["starts_at"] == requested_start), None)

    alternatives = []
    suggestion_type = "none"
    suggested_date = None

    if selected:
        alternatives = [slot for slot in raw_slots if slot["starts_at"] != requested_start]
        if alternatives:
            suggestion_type = "requested_date"
            suggested_date = target_date
    elif requested_start:
        alternatives = sorted(raw_slots, key=lambda slot: abs(slot["starts_at"] - requested_start))
        if alternatives:
            suggestion_type = "nearest_time"
            suggested_date = target_date
    else:
        alternatives = raw_slots
        if alternatives:
            suggestion_type = "requested_date"
            suggested_date = target_date

    search_date = target_date
    if alternatives:
        while len(alternatives) < 3 and search_date < target_date + timedelta(days=14):
            search_date += timedelta(days=1)
            alternatives.extend(generate_slots(clinic, service, search_date))
    elif not selected:
        while search_date < target_date + timedelta(days=14):
            search_date += timedelta(days=1)
            future_slots = generate_slots(clinic, service, search_date)
            if future_slots:
                alternatives = future_slots
                suggestion_type = "next_available_date"
                suggested_date = search_date
                break

    return {
        "found": True,
        "available": selected is not None or (
            requested_start is None and suggestion_type == "requested_date" and bool(alternatives)
        ),
        "selected_slot": _slot_payload(clinic, selected) if selected else None,
        "alternatives": [_slot_payload(clinic, slot) for slot in alternatives[:3]],
        "suggestion_type": suggestion_type,
        "requested_date": target_date.isoformat(),
        "suggested_date": suggested_date.isoformat() if suggested_date else None,
    }
```

- [ ] **Step 2: Run targeted availability tests**

Run:

```powershell
.\env\Scripts\activate; if ($?) { python -m pytest messenger/tests.py::test_check_availability_returns_requested_slot_and_alternatives messenger/tests.py::test_check_availability_marks_nearest_time_when_requested_slot_is_taken messenger/tests.py::test_check_availability_suggests_first_future_date_when_requested_date_has_no_slots messenger/tests.py::test_check_widget_availability_returns_shared_suggestion_metadata messenger/tests.py::test_ai_availability_endpoint_returns_alternatives -q }
```

Expected: PASS.

- [ ] **Step 3: Inspect the diff for this task**

Run:

```powershell
git diff -- messenger/ai_tools.py messenger/tests.py
```

Expected: diff only contains the availability metadata tests and `_check_availability_for_clinic()` change from this task plus pre-existing unrelated local edits in the same files. Do not revert pre-existing edits.

## Task 3: Add Django Default Prompt Rules

**Files:**
- Modify: `messenger/tests.py`
- Modify: `messenger/defaults.py`
- Test: `messenger/tests.py`

- [ ] **Step 1: Add a failing prompt regression test after `test_clinic_ai_settings_defaults_and_unique_clinic`**

Insert this test after `test_clinic_ai_settings_defaults_and_unique_clinic()`:

```python

def test_default_ai_prompt_hides_faq_source_and_uses_suggestion_metadata():
    from messenger.defaults import DEFAULT_MESSENGER_AI_PROMPT

    assert "Do not say based on the FAQ" in DEFAULT_MESSENGER_AI_PROMPT
    assert "Answer FAQ-backed information as normal clinic information." in DEFAULT_MESSENGER_AI_PROMPT
    assert "Use check_availability suggestion_type metadata" in DEFAULT_MESSENGER_AI_PROMPT
    assert "nearest_time means the requested time is unavailable" in DEFAULT_MESSENGER_AI_PROMPT
    assert "next_available_date means the requested date has no slots" in DEFAULT_MESSENGER_AI_PROMPT
```

- [ ] **Step 2: Run prompt test to verify it fails**

Run:

```powershell
.\env\Scripts\activate; if ($?) { python -m pytest messenger/tests.py::test_default_ai_prompt_hides_faq_source_and_uses_suggestion_metadata -q }
```

Expected: FAIL because the default prompt does not contain the new FAQ and metadata rules.

- [ ] **Step 3: Update `DEFAULT_MESSENGER_AI_PROMPT`**

In `messenger/defaults.py`, replace the `Rules:` block with this exact block while keeping the opening paragraph and fallback constant intact:

```python
Rules:
- Only answer using clinic context, active services, FAQs, current clinic date/time above, and tool results.
- Use FAQ entries as clinic knowledge, but do not say based on the FAQ, according to the FAQ, the FAQ says, or similar source-citation phrasing. Answer FAQ-backed information as normal clinic information.
- Treat the Current clinic date/time above as the only source of truth for today, tomorrow, next week, weekdays, month names, and other relative dates.
- Do not infer the current date/year from model knowledge, previous conversation memory, or user corrections unless the user gives an explicit absolute appointment date.
- Interpret relative dates in the clinic timezone. Tomorrow means the calendar date after Today in the clinic timezone. Next week means the next calendar week after Today.
- When calling tools, convert dates to clinic-local ISO values. Use preferred_date as YYYY-MM-DD. Use preferred_starts_at only when the user gave a specific time, and include the clinic timezone offset when possible.
- Mirror the user's language. If the user speaks Tagalog or Taglish, reply in natural Tagalog/Taglish with a similar mix. Do not say booking must continue in English. If the user speaks English, reply in English.
- If information is missing, say you do not have that information and offer the clinic phone/email if available.
- For booking, collect service, date/time, full name, and phone in normal conversation.
- Use match_services when service intent is unclear or when you need the numeric service_id.
- Before saying any date/time is available, unavailable, fully booked, open, closed, or before offering alternatives, call check_availability in the current turn and base the claim only on its result.
- If the user asks what times are available for a service/date but no exact time, call check_availability with service_id and preferred_date, and leave preferred_starts_at blank.
- If the user asks about another date after a previous unavailable reply, call check_availability again for the new date. Do not reuse old availability results.
- If requested time is unavailable, offer only nearest alternatives returned by check_availability. Do not invent alternatives.
- Use check_availability suggestion_type metadata: nearest_time means the requested time is unavailable and returned alternatives should be offered as nearby same-day options; next_available_date means the requested date has no slots and returned alternatives should be offered as the next available date/times; requested_date means returned alternatives are open slots for the requested date; none means no alternatives were found.
- If check_availability returns alternatives, present those alternatives instead of saying the whole date has no slots.
- When the user selects an alternative slot from a previous result, call check_availability again for that exact date/time before asking for final confirmation.
- Before booking, summarize service, local date/time, full name, and phone, then ask the user to confirm.
- Call book_confirmed_appointment only after the user explicitly confirms the summary.
- Keep replies concise and friendly."""
```

- [ ] **Step 4: Run prompt test to verify it passes**

Run:

```powershell
.\env\Scripts\activate; if ($?) { python -m pytest messenger/tests.py::test_default_ai_prompt_hides_faq_source_and_uses_suggestion_metadata -q }
```

Expected: PASS.

## Task 4: Add n8n Shared Prompt Source Lock

**Files:**
- Modify: `tests/test_n8n_combined_bridge_source.py`
- Modify: `n8n_combined_messenger_widget_ai_bridge.ts`
- Test: `tests/test_n8n_combined_bridge_source.py`

- [ ] **Step 1: Add failing n8n source test after `test_combined_bridge_widget_ai_prompt_requires_tools_and_explicit_confirmation`**

Insert this test after `test_combined_bridge_widget_ai_prompt_requires_tools_and_explicit_confirmation()`:

```python

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
```

- [ ] **Step 2: Run n8n source test to verify it fails**

Run:

```powershell
.\env\Scripts\activate; if ($?) { python -m pytest tests/test_n8n_combined_bridge_source.py::test_combined_bridge_prompt_uses_availability_suggestion_metadata_and_hides_faq_source -q }
```

Expected: FAIL because the combined bridge prompt does not contain the new source-locked strings.

- [ ] **Step 3: Update shared n8n agent system message**

In `n8n_combined_messenger_widget_ai_bridge.ts`, replace the single long rule string at the end of the `systemMessage` expression with these concatenated rule strings:

```typescript
          'Use match_services, check_availability, and book_confirmed_appointment for booking. Ask for explicit confirmation before booking.\n' +
          'Use check_availability suggestion_type metadata: nearest_time means the requested time is unavailable and returned alternatives should be offered as nearby same-day options; next_available_date means the requested date has no slots and returned alternatives should be offered as the next available date/times; requested_date means returned alternatives are open slots for the requested date; none means no alternatives were found.\n' +
          'Use FAQ entries as clinic knowledge without citing the source. Do not say based on the FAQ, according to the FAQ, the FAQ says, or similar source-citation phrasing.\n' +
          'Never expose secrets, invent clinic data, give medical diagnosis, or create appointments without tool validation. Messenger replies must be plain concise text. Widget replies must be concise and friendly.'),
```

The updated prompt must still keep these existing source-test strings intact:

```text
Use match_services, check_availability, and book_confirmed_appointment for booking.
Ask for explicit confirmation before booking.
Never expose secrets, invent clinic data, give medical diagnosis, or create appointments without tool validation.
Widget replies must be concise and friendly.
```

- [ ] **Step 4: Run n8n source tests**

Run:

```powershell
.\env\Scripts\activate; if ($?) { python -m pytest tests/test_n8n_combined_bridge_source.py::test_combined_bridge_widget_ai_prompt_requires_tools_and_explicit_confirmation tests/test_n8n_combined_bridge_source.py::test_combined_bridge_prompt_uses_availability_suggestion_metadata_and_hides_faq_source -q }
```

Expected: PASS.

## Task 5: Generate Prompt Default Migrations

**Files:**
- Create: `clinics/migrations/0014_update_ai_prompt_default.py`
- Create: `messenger/migrations/0010_update_ai_prompt_default.py`
- Test: Django migration system

- [ ] **Step 1: Generate named migrations for default prompt changes**

Run:

```powershell
.\env\Scripts\activate; if ($?) { python manage.py makemigrations clinics messenger --name update_ai_prompt_default }
```

Expected: output includes both migration files:

```text
Migrations for 'clinics':
  clinics\migrations\0014_update_ai_prompt_default.py
    ~ Alter field instructions on clinicaisettings
Migrations for 'messenger':
  messenger\migrations\0010_update_ai_prompt_default.py
    ~ Alter field instructions on messengeraisettings
```

- [ ] **Step 2: Apply migrations to the local development database**

Run:

```powershell
.\env\Scripts\activate; if ($?) { python manage.py migrate }
```

Expected: migrations apply successfully and output ends with `OK` for any unapplied migrations.

- [ ] **Step 3: Inspect generated migrations**

Run:

```powershell
git diff -- clinics/migrations/0014_update_ai_prompt_default.py messenger/migrations/0010_update_ai_prompt_default.py
```

Expected: migrations only alter `instructions` defaults and do not alter tables, indexes, relationships, or data rows.

## Task 6: Final Verification

**Files:**
- Verify: `messenger/tests.py`
- Verify: `tests/test_n8n_combined_bridge_source.py`
- Verify: `widget/tests.py`
- Verify: Django system checks

- [ ] **Step 1: Run focused regression tests**

Run:

```powershell
.\env\Scripts\activate; if ($?) { python -m pytest messenger/tests.py::test_check_availability_returns_requested_slot_and_alternatives messenger/tests.py::test_check_availability_marks_nearest_time_when_requested_slot_is_taken messenger/tests.py::test_check_availability_suggests_first_future_date_when_requested_date_has_no_slots messenger/tests.py::test_check_widget_availability_returns_shared_suggestion_metadata messenger/tests.py::test_default_ai_prompt_hides_faq_source_and_uses_suggestion_metadata tests/test_n8n_combined_bridge_source.py::test_combined_bridge_prompt_uses_availability_suggestion_metadata_and_hides_faq_source -q }
```

Expected: PASS.

- [ ] **Step 2: Run broader affected tests**

Run:

```powershell
.\env\Scripts\activate; if ($?) { python -m pytest messenger/tests.py tests/test_n8n_combined_bridge_source.py widget/tests.py -q }
```

Expected: PASS.

- [ ] **Step 3: Run Django system check**

Run:

```powershell
.\env\Scripts\activate; if ($?) { python manage.py check }
```

Expected: `System check identified no issues`.

- [ ] **Step 4: Review final diff and status**

Run:

```powershell
git status --short
```

Run:

```powershell
git diff -- messenger/ai_tools.py messenger/defaults.py messenger/tests.py tests/test_n8n_combined_bridge_source.py n8n_combined_messenger_widget_ai_bridge.ts clinics/migrations/0014_update_ai_prompt_default.py messenger/migrations/0010_update_ai_prompt_default.py docs/superpowers/specs/2026-06-04-ai-availability-response-polish-design.md docs/superpowers/plans/2026-06-04-ai-availability-response-polish-implementation-plan.md
```

Expected: changed files match this plan. Do not commit unless the user explicitly asks for a commit.
