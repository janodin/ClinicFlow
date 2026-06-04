# Assistant Appointment Management Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add safe cancel and same-service reschedule support to Messenger AI mode and widget `Chat with Assistant` using reference code plus phone verification.

**Architecture:** Django remains the authority for all appointment lookup and mutation. n8n only collects patient-provided reference, phone, requested time, reason, and confirmation, while Django resolves clinic context from `page_id` or `clinic_slug`, verifies ownership, rechecks eligibility, locks the clinic row for mutations, and applies existing slot validation.

**Tech Stack:** Django, Django ORM transactions, pytest, n8n Workflow SDK TypeScript source tests, Facebook Messenger/n8n shared webhook secret tooling.

---

## Scope

This plan implements the approved design in `docs/superpowers/specs/2026-06-04-assistant-appointment-management-design.md`.

The work covers:

- Messenger AI mode appointment lookup, cancellation, and rescheduling.
- Widget `Chat with Assistant` appointment lookup, cancellation, and rescheduling.
- Reference code plus normalized phone verification.
- Future `pending` and `confirmed` appointments only.
- Same-service rescheduling only.
- Explicit confirmation before mutation.
- n8n shared AI agent tools and prompt constraints.

The work does not cover:

- Deterministic Messenger quick-reply rescheduling.
- Patient accounts or portal flows.
- Service-change rescheduling.
- Model or migration changes.

## File Structure

- Modify `messenger/ai_tools.py`: add verification helpers and public tool functions for Messenger and widget appointment management.
- Modify `messenger/views.py`: expose the new AI tool functions through existing secret-protected JSON endpoint wrapper.
- Modify `messenger/urls.py`: add Messenger and widget endpoint routes matching the existing AI tool route style.
- Modify `messenger/tests.py`: add direct tool tests and endpoint tests.
- Modify `n8n_combined_messenger_widget_ai_bridge.ts`: add shared appointment-management HTTP request tools and update the shared AI prompt/tools list.
- Modify `tests/test_n8n_combined_bridge_source.py`: add source-lock tests for the new n8n tools and prompt rules.

## Execution Notes

Run commands from the repository root on Windows PowerShell.

Activate the virtual environment before Python commands:

```powershell
.\env\Scripts\activate
```

This environment requires explicit user approval before creating git commits. Commit commands are included for workers in environments where commits have been authorized; otherwise skip commit steps and leave changes in the worktree.

### Task 1: Verified Appointment Lookup Tool

**Files:**
- Modify: `messenger/tests.py`
- Modify: `messenger/ai_tools.py`

- [ ] **Step 1: Add failing lookup tests**

Append these tests near the existing AI tool tests in `messenger/tests.py`, after `test_ai_booking_reuses_patient_phone_and_prevents_double_booking` and before widget booking source tests.

```python
@pytest.mark.django_db
def test_find_verified_appointment_matches_reference_and_normalized_phone():
    from messenger.ai_tools import find_verified_appointment

    clinic, _connection = _create_messenger_clinic("owner_appt_lookup", "PAGE-APPT-LOOKUP")
    service = Service.objects.create(clinic=clinic, name="Consultation", duration_minutes=30, price=0)
    patient = Patient.objects.create(clinic=clinic, full_name="Maria Santos", phone="09175551234")
    starts_at = timezone.now() + timedelta(days=1)
    appointment = Appointment.objects.create(
        clinic=clinic,
        patient=patient,
        service=service,
        starts_at=starts_at,
        ends_at=starts_at + timedelta(minutes=30),
        status=Appointment.STATUS_CONFIRMED,
        source=Appointment.SOURCE_STAFF,
    )

    result = find_verified_appointment("PAGE-APPT-LOOKUP", appointment.reference_code.lower(), "(0917) 555-1234")

    assert result["found"] is True
    assert result["appointment"]["reference_code"] == appointment.reference_code
    assert result["appointment"]["service_id"] == service.id
    assert result["appointment"]["service"] == "Consultation"
    assert result["appointment"]["status"] == Appointment.STATUS_CONFIRMED
    assert result["appointment"]["patient_name"] == "Maria Santos"
    assert result["appointment"]["patient_phone_last4"] == "1234"
    assert result["appointment"]["local_date_label"]
    assert result["appointment"]["local_time_label"]


@pytest.mark.django_db
def test_find_verified_appointment_rejects_wrong_phone_and_cross_clinic():
    from messenger.ai_tools import find_verified_appointment

    clinic, _connection = _create_messenger_clinic("owner_appt_lookup_scope", "PAGE-APPT-LOOKUP-SCOPE")
    other_clinic, _other_connection = _create_messenger_clinic("owner_appt_lookup_other", "PAGE-APPT-LOOKUP-OTHER")
    service = Service.objects.create(clinic=clinic, name="Consultation", duration_minutes=30, price=0)
    patient = Patient.objects.create(clinic=clinic, full_name="Maria Santos", phone="09175551234")
    starts_at = timezone.now() + timedelta(days=1)
    appointment = Appointment.objects.create(
        clinic=clinic,
        patient=patient,
        service=service,
        starts_at=starts_at,
        ends_at=starts_at + timedelta(minutes=30),
        status=Appointment.STATUS_CONFIRMED,
    )

    wrong_phone = find_verified_appointment("PAGE-APPT-LOOKUP-SCOPE", appointment.reference_code, "09170000000")
    wrong_page = find_verified_appointment("PAGE-APPT-LOOKUP-OTHER", appointment.reference_code, "09175551234")

    assert wrong_phone == {"found": False, "error": "Appointment not found. Please check the reference code and phone number."}
    assert wrong_page == {"found": False, "error": "Appointment not found. Please check the reference code and phone number."}
    assert other_clinic.appointments.count() == 0


@pytest.mark.django_db
def test_find_verified_appointment_rejects_missing_identity_and_ineligible_statuses():
    from messenger.ai_tools import find_verified_appointment

    clinic, _connection = _create_messenger_clinic("owner_appt_lookup_status", "PAGE-APPT-LOOKUP-STATUS")
    service = Service.objects.create(clinic=clinic, name="Consultation", duration_minutes=30, price=0)
    patient = Patient.objects.create(clinic=clinic, full_name="Maria Santos", phone="09175551234")
    missing = find_verified_appointment("PAGE-APPT-LOOKUP-STATUS", "", "")
    assert missing == {"found": False, "error": "Please provide the appointment reference code and phone number."}

    status_cases = [
        (Appointment.STATUS_CANCELLED, timezone.now() + timedelta(days=1), "This appointment cannot be changed through the assistant."),
        (Appointment.STATUS_COMPLETED, timezone.now() + timedelta(days=2), "This appointment cannot be changed through the assistant."),
        (Appointment.STATUS_NO_SHOW, timezone.now() + timedelta(days=3), "This appointment cannot be changed through the assistant."),
        (Appointment.STATUS_CONFIRMED, timezone.now() - timedelta(days=1), "Past appointments cannot be changed through the assistant."),
    ]
    for status, starts_at, expected_error in status_cases:
        appointment = Appointment.objects.create(
            clinic=clinic,
            patient=patient,
            service=service,
            starts_at=starts_at,
            ends_at=starts_at + timedelta(minutes=30),
            status=status,
        )
        result = find_verified_appointment("PAGE-APPT-LOOKUP-STATUS", appointment.reference_code, "09175551234")
        assert result == {"found": False, "error": expected_error}


@pytest.mark.django_db
def test_find_widget_verified_appointment_respects_website_ai_disabled():
    from clinics.models import ClinicAISettings
    from messenger.ai_tools import find_widget_verified_appointment

    clinic, _connection = _create_messenger_clinic("owner_widget_appt_lookup_disabled", "PAGE-WIDGET-APPT-DISABLED")
    ClinicAISettings.objects.create(clinic=clinic, is_ai_enabled=False, fallback_message="Please call us.")

    result = find_widget_verified_appointment(clinic.slug, "CF-TEST", "09175551234")

    assert result["found"] is False
    assert result["disabled"] is True
    assert result["fallback_message"] == "Please call us."
    assert result["error"] == "AI is disabled for this clinic."
```

- [ ] **Step 2: Run lookup tests and verify failure**

Run:

```powershell
.\env\Scripts\activate; if ($?) { python -m pytest messenger/tests.py -k "find_verified_appointment" -q }
```

Expected: FAIL with import errors for `find_verified_appointment` and `find_widget_verified_appointment`.

- [ ] **Step 3: Add lookup implementation**

Modify imports at the top of `messenger/ai_tools.py`.

```python
from django.core.exceptions import ValidationError
from django.db import transaction
from patients.models import normalize_phone
from scheduling.utils import generate_slots, validate_slot
```

Replace the existing `from scheduling.utils import generate_slots` import with the combined import above.

Add this helper block after `_parse_datetime()` in `messenger/ai_tools.py`.

```python
APPOINTMENT_LOOKUP_ERROR = "Appointment not found. Please check the reference code and phone number."
CONFIRMATION_REQUIRED_ERROR = "Appointment change requires explicit user confirmation."


def _parse_clinic_datetime(clinic, value):
    if not value:
        return None
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if timezone.is_naive(parsed):
        parsed = timezone.make_aware(parsed, ZoneInfo(clinic.timezone))
    return parsed.astimezone(dt_timezone.utc)


def _validation_error_text(error):
    if hasattr(error, "messages"):
        return " ".join(str(message) for message in error.messages)
    return str(error)


def _appointment_summary(clinic, appointment):
    local_start = appointment.starts_at.astimezone(ZoneInfo(clinic.timezone))
    digits = normalize_phone(appointment.patient.phone)
    return {
        "reference_code": appointment.reference_code,
        "service_id": appointment.service_id,
        "service": appointment.service.name,
        "status": appointment.status,
        "starts_at": appointment.starts_at.isoformat(),
        "local_starts_at": local_start.isoformat(),
        "patient_name": appointment.patient.full_name,
        "patient_phone_last4": digits[-4:] if len(digits) >= 4 else digits,
        "local_date_label": local_start.strftime("%A, %B %d"),
        "local_time_label": local_start.strftime("%I:%M %p").lstrip("0"),
    }


def _verified_appointment_for_clinic(clinic, reference_code, phone):
    reference = (reference_code or "").strip().upper()
    normalized_phone = normalize_phone(phone)
    if not reference or not normalized_phone:
        return None, "Please provide the appointment reference code and phone number."

    appointment = (
        clinic.appointments.select_related("patient", "service")
        .filter(reference_code__iexact=reference, patient__normalized_phone=normalized_phone)
        .first()
    )
    if not appointment:
        return None, APPOINTMENT_LOOKUP_ERROR
    if appointment.starts_at <= timezone.now():
        return None, "Past appointments cannot be changed through the assistant."
    if appointment.status not in {Appointment.STATUS_PENDING, Appointment.STATUS_CONFIRMED}:
        return None, "This appointment cannot be changed through the assistant."
    return appointment, ""


def _find_verified_appointment_for_clinic(clinic, reference_code, phone):
    appointment, error = _verified_appointment_for_clinic(clinic, reference_code, phone)
    if error:
        return {"found": False, "error": error}
    return {"found": True, "appointment": _appointment_summary(clinic, appointment)}
```

Add these public functions after `check_widget_availability()` in `messenger/ai_tools.py`.

```python
def find_verified_appointment(page_id, reference_code, phone):
    connection = get_connection_for_page(page_id)
    if not connection:
        return {"found": False, "error": APPOINTMENT_LOOKUP_ERROR}
    return _find_verified_appointment_for_clinic(connection.clinic, reference_code, phone)


def find_widget_verified_appointment(clinic_slug, reference_code, phone):
    clinic = get_clinic_for_slug(clinic_slug)
    if not clinic:
        return {"found": False, "error": APPOINTMENT_LOOKUP_ERROR}
    disabled = _website_ai_disabled_response_for_clinic(clinic)
    if disabled:
        return {**disabled, "found": False, "error": "AI is disabled for this clinic."}
    return _find_verified_appointment_for_clinic(clinic, reference_code, phone)
```

- [ ] **Step 4: Run lookup tests and verify pass**

Run:

```powershell
.\env\Scripts\activate; if ($?) { python -m pytest messenger/tests.py -k "find_verified_appointment" -q }
```

Expected: PASS for the lookup tests.

- [ ] **Step 5: Commit lookup work if commits are authorized**

Run only if the user explicitly authorized commits:

```powershell
git status --short; if ($?) { git diff -- messenger/tests.py messenger/ai_tools.py }; if ($?) { git add messenger/tests.py messenger/ai_tools.py }; if ($?) { git commit -m "feat: add assistant appointment lookup tool" }
```

Expected: one commit containing only `messenger/tests.py` and `messenger/ai_tools.py` lookup changes.

### Task 2: Verified Appointment Cancellation Tool

**Files:**
- Modify: `messenger/tests.py`
- Modify: `messenger/ai_tools.py`

- [ ] **Step 1: Add failing cancel tests**

Append these tests near the lookup tests in `messenger/tests.py`.

```python
@pytest.mark.django_db
def test_cancel_verified_appointment_requires_confirmation():
    from messenger.ai_tools import cancel_verified_appointment

    clinic, _connection = _create_messenger_clinic("owner_appt_cancel_confirm", "PAGE-APPT-CANCEL-CONFIRM")
    service = Service.objects.create(clinic=clinic, name="Consultation", duration_minutes=30, price=0)
    patient = Patient.objects.create(clinic=clinic, full_name="Maria Santos", phone="09175551234")
    starts_at = timezone.now() + timedelta(days=1)
    appointment = Appointment.objects.create(
        clinic=clinic,
        patient=patient,
        service=service,
        starts_at=starts_at,
        ends_at=starts_at + timedelta(minutes=30),
        status=Appointment.STATUS_CONFIRMED,
    )

    result = cancel_verified_appointment("PAGE-APPT-CANCEL-CONFIRM", appointment.reference_code, "09175551234", confirmed=False)

    appointment.refresh_from_db()
    assert result == {"cancelled": False, "error": "Appointment change requires explicit user confirmation."}
    assert appointment.status == Appointment.STATUS_CONFIRMED


@pytest.mark.django_db
def test_cancel_verified_appointment_cancels_future_verified_appointment_and_stores_reason():
    from messenger.ai_tools import cancel_verified_appointment

    clinic, _connection = _create_messenger_clinic("owner_appt_cancel", "PAGE-APPT-CANCEL")
    service = Service.objects.create(clinic=clinic, name="Consultation", duration_minutes=30, price=0)
    patient = Patient.objects.create(clinic=clinic, full_name="Maria Santos", phone="09175551234")
    starts_at = timezone.now() + timedelta(days=1)
    appointment = Appointment.objects.create(
        clinic=clinic,
        patient=patient,
        service=service,
        starts_at=starts_at,
        ends_at=starts_at + timedelta(minutes=30),
        status=Appointment.STATUS_PENDING,
        source=Appointment.SOURCE_PHONE,
    )

    result = cancel_verified_appointment(
        "PAGE-APPT-CANCEL",
        appointment.reference_code,
        "09175551234",
        confirmed=True,
        reason="Patient requested through assistant.",
    )

    appointment.refresh_from_db()
    assert result["cancelled"] is True
    assert result["appointment"]["reference_code"] == appointment.reference_code
    assert result["appointment"]["status"] == Appointment.STATUS_CANCELLED
    assert appointment.status == Appointment.STATUS_CANCELLED
    assert appointment.cancellation_reason == "Patient requested through assistant."
    assert appointment.source == Appointment.SOURCE_PHONE


@pytest.mark.django_db
def test_cancel_widget_verified_appointment_rechecks_phone_before_mutating():
    from messenger.ai_tools import cancel_widget_verified_appointment

    clinic, _connection = _create_messenger_clinic("owner_widget_appt_cancel", "PAGE-WIDGET-APPT-CANCEL")
    service = Service.objects.create(clinic=clinic, name="Consultation", duration_minutes=30, price=0)
    patient = Patient.objects.create(clinic=clinic, full_name="Maria Santos", phone="09175551234")
    starts_at = timezone.now() + timedelta(days=1)
    appointment = Appointment.objects.create(
        clinic=clinic,
        patient=patient,
        service=service,
        starts_at=starts_at,
        ends_at=starts_at + timedelta(minutes=30),
        status=Appointment.STATUS_CONFIRMED,
    )

    result = cancel_widget_verified_appointment(clinic.slug, appointment.reference_code, "09170000000", confirmed=True)

    appointment.refresh_from_db()
    assert result == {"cancelled": False, "error": "Appointment not found. Please check the reference code and phone number."}
    assert appointment.status == Appointment.STATUS_CONFIRMED
```

- [ ] **Step 2: Run cancel tests and verify failure**

Run:

```powershell
.\env\Scripts\activate; if ($?) { python -m pytest messenger/tests.py -k "cancel_verified_appointment" -q }
```

Expected: FAIL with import errors for `cancel_verified_appointment` and `cancel_widget_verified_appointment`.

- [ ] **Step 3: Add cancel implementation**

Add these functions after the lookup public functions in `messenger/ai_tools.py`.

```python
def cancel_verified_appointment(page_id, reference_code, phone, confirmed, reason=""):
    connection = get_connection_for_page(page_id)
    if not connection:
        return {"cancelled": False, "error": APPOINTMENT_LOOKUP_ERROR}
    return _cancel_verified_appointment_for_clinic(connection.clinic, reference_code, phone, confirmed, reason)


def cancel_widget_verified_appointment(clinic_slug, reference_code, phone, confirmed, reason=""):
    clinic = get_clinic_for_slug(clinic_slug)
    if not clinic:
        return {"cancelled": False, "error": APPOINTMENT_LOOKUP_ERROR}
    disabled = _website_ai_disabled_response_for_clinic(clinic)
    if disabled:
        return {**disabled, "cancelled": False, "error": "AI is disabled for this clinic."}
    return _cancel_verified_appointment_for_clinic(clinic, reference_code, phone, confirmed, reason)


def _cancel_verified_appointment_for_clinic(clinic, reference_code, phone, confirmed, reason=""):
    if confirmed is not True:
        return {"cancelled": False, "error": CONFIRMATION_REQUIRED_ERROR}

    with transaction.atomic():
        locked_clinic = Clinic.objects.select_for_update().get(pk=clinic.pk)
        appointment, error = _verified_appointment_for_clinic(locked_clinic, reference_code, phone)
        if error:
            return {"cancelled": False, "error": error}
        if not appointment.can_transition_to(Appointment.STATUS_CANCELLED):
            return {"cancelled": False, "error": "This appointment cannot be cancelled through the assistant."}
        appointment.status = Appointment.STATUS_CANCELLED
        appointment.cancellation_reason = (reason or "").strip()[:500]
        appointment.save(update_fields=["status", "cancellation_reason", "updated_at"])
        return {"cancelled": True, "appointment": _appointment_summary(locked_clinic, appointment)}
```

- [ ] **Step 4: Run cancel tests and verify pass**

Run:

```powershell
.\env\Scripts\activate; if ($?) { python -m pytest messenger/tests.py -k "cancel_verified_appointment" -q }
```

Expected: PASS for cancel tests.

- [ ] **Step 5: Commit cancel work if commits are authorized**

Run only if the user explicitly authorized commits:

```powershell
git status --short; if ($?) { git diff -- messenger/tests.py messenger/ai_tools.py }; if ($?) { git add messenger/tests.py messenger/ai_tools.py }; if ($?) { git commit -m "feat: add assistant appointment cancellation tool" }
```

Expected: one commit containing only cancel-related changes.

### Task 3: Verified Appointment Reschedule Tool

**Files:**
- Modify: `messenger/tests.py`
- Modify: `messenger/ai_tools.py`

- [ ] **Step 1: Add failing reschedule tests**

Append these tests near the lookup and cancel tests in `messenger/tests.py`.

```python
@pytest.mark.django_db
def test_reschedule_verified_appointment_requires_confirmation():
    from zoneinfo import ZoneInfo
    from messenger.ai_tools import reschedule_verified_appointment

    clinic, _connection = _create_messenger_clinic("owner_appt_reschedule_confirm", "PAGE-APPT-RESCHEDULE-CONFIRM")
    service = Service.objects.create(clinic=clinic, name="Consultation", duration_minutes=30, price=0)
    patient = Patient.objects.create(clinic=clinic, full_name="Maria Santos", phone="09175551234")
    clinic_tz = ZoneInfo(clinic.timezone)
    target_date = timezone.now().astimezone(clinic_tz).date() + timedelta(days=1)
    ClinicBusinessHour.objects.create(clinic=clinic, weekday=target_date.weekday(), open_time=time(9), close_time=time(12))
    starts_at = timezone.make_aware(timezone.datetime.combine(target_date, time(9)), clinic_tz)
    appointment = Appointment.objects.create(
        clinic=clinic,
        patient=patient,
        service=service,
        starts_at=starts_at,
        ends_at=starts_at + timedelta(minutes=30),
        status=Appointment.STATUS_CONFIRMED,
    )
    requested_start = timezone.make_aware(timezone.datetime.combine(target_date, time(10)), clinic_tz)

    result = reschedule_verified_appointment(
        "PAGE-APPT-RESCHEDULE-CONFIRM",
        appointment.reference_code,
        "09175551234",
        requested_start.isoformat(),
        confirmed=False,
    )

    appointment.refresh_from_db()
    assert result == {"rescheduled": False, "error": "Appointment change requires explicit user confirmation."}
    assert appointment.starts_at == starts_at


@pytest.mark.django_db
def test_reschedule_verified_appointment_moves_same_service_and_preserves_identity_fields():
    from zoneinfo import ZoneInfo
    from messenger.ai_tools import reschedule_verified_appointment

    clinic, _connection = _create_messenger_clinic("owner_appt_reschedule", "PAGE-APPT-RESCHEDULE")
    service = Service.objects.create(clinic=clinic, name="Consultation", duration_minutes=30, price=0)
    patient = Patient.objects.create(clinic=clinic, full_name="Maria Santos", phone="09175551234")
    clinic_tz = ZoneInfo(clinic.timezone)
    target_date = timezone.now().astimezone(clinic_tz).date() + timedelta(days=1)
    ClinicBusinessHour.objects.create(clinic=clinic, weekday=target_date.weekday(), open_time=time(9), close_time=time(12))
    original_start = timezone.make_aware(timezone.datetime.combine(target_date, time(9)), clinic_tz)
    new_start = timezone.make_aware(timezone.datetime.combine(target_date, time(10)), clinic_tz)
    appointment = Appointment.objects.create(
        clinic=clinic,
        patient=patient,
        service=service,
        starts_at=original_start,
        ends_at=original_start + timedelta(minutes=30),
        status=Appointment.STATUS_PENDING,
        source=Appointment.SOURCE_STAFF,
    )
    original_reference = appointment.reference_code

    result = reschedule_verified_appointment(
        "PAGE-APPT-RESCHEDULE",
        appointment.reference_code,
        "09175551234",
        new_start.isoformat(),
        confirmed=True,
    )

    appointment.refresh_from_db()
    assert result["rescheduled"] is True
    assert result["appointment"]["reference_code"] == original_reference
    assert appointment.starts_at == new_start
    assert appointment.ends_at == new_start + timedelta(minutes=30)
    assert appointment.service == service
    assert appointment.patient == patient
    assert appointment.source == Appointment.SOURCE_STAFF
    assert appointment.status == Appointment.STATUS_PENDING
    assert appointment.reference_code == original_reference


@pytest.mark.django_db
def test_reschedule_verified_appointment_rejects_overlap_and_past_time():
    from zoneinfo import ZoneInfo
    from messenger.ai_tools import reschedule_verified_appointment

    clinic, _connection = _create_messenger_clinic("owner_appt_reschedule_reject", "PAGE-APPT-RESCHEDULE-REJECT")
    service = Service.objects.create(clinic=clinic, name="Consultation", duration_minutes=30, price=0)
    patient = Patient.objects.create(clinic=clinic, full_name="Maria Santos", phone="09175551234")
    other_patient = Patient.objects.create(clinic=clinic, full_name="Other Patient", phone="09170000000")
    clinic_tz = ZoneInfo(clinic.timezone)
    target_date = timezone.now().astimezone(clinic_tz).date() + timedelta(days=1)
    ClinicBusinessHour.objects.create(clinic=clinic, weekday=target_date.weekday(), open_time=time(9), close_time=time(12))
    original_start = timezone.make_aware(timezone.datetime.combine(target_date, time(9)), clinic_tz)
    occupied_start = timezone.make_aware(timezone.datetime.combine(target_date, time(10)), clinic_tz)
    appointment = Appointment.objects.create(
        clinic=clinic,
        patient=patient,
        service=service,
        starts_at=original_start,
        ends_at=original_start + timedelta(minutes=30),
        status=Appointment.STATUS_CONFIRMED,
    )
    Appointment.objects.create(
        clinic=clinic,
        patient=other_patient,
        service=service,
        starts_at=occupied_start,
        ends_at=occupied_start + timedelta(minutes=30),
        status=Appointment.STATUS_CONFIRMED,
    )

    overlap = reschedule_verified_appointment(
        "PAGE-APPT-RESCHEDULE-REJECT",
        appointment.reference_code,
        "09175551234",
        occupied_start.isoformat(),
        confirmed=True,
    )
    past = reschedule_verified_appointment(
        "PAGE-APPT-RESCHEDULE-REJECT",
        appointment.reference_code,
        "09175551234",
        (timezone.now() - timedelta(hours=1)).isoformat(),
        confirmed=True,
    )

    appointment.refresh_from_db()
    assert overlap == {"rescheduled": False, "error": "This slot is not available."}
    assert past == {"rescheduled": False, "error": "Cannot reschedule to the past."}
    assert appointment.starts_at == original_start
```

- [ ] **Step 2: Run reschedule tests and verify failure**

Run:

```powershell
.\env\Scripts\activate; if ($?) { python -m pytest messenger/tests.py -k "reschedule_verified_appointment" -q }
```

Expected: FAIL with import errors for `reschedule_verified_appointment`.

- [ ] **Step 3: Add reschedule implementation**

Add these functions after the cancel functions in `messenger/ai_tools.py`.

```python
def reschedule_verified_appointment(page_id, reference_code, phone, starts_at, confirmed):
    connection = get_connection_for_page(page_id)
    if not connection:
        return {"rescheduled": False, "error": APPOINTMENT_LOOKUP_ERROR}
    return _reschedule_verified_appointment_for_clinic(connection.clinic, reference_code, phone, starts_at, confirmed)


def reschedule_widget_verified_appointment(clinic_slug, reference_code, phone, starts_at, confirmed):
    clinic = get_clinic_for_slug(clinic_slug)
    if not clinic:
        return {"rescheduled": False, "error": APPOINTMENT_LOOKUP_ERROR}
    disabled = _website_ai_disabled_response_for_clinic(clinic)
    if disabled:
        return {**disabled, "rescheduled": False, "error": "AI is disabled for this clinic."}
    return _reschedule_verified_appointment_for_clinic(clinic, reference_code, phone, starts_at, confirmed)


def _reschedule_verified_appointment_for_clinic(clinic, reference_code, phone, starts_at, confirmed):
    if confirmed is not True:
        return {"rescheduled": False, "error": CONFIRMATION_REQUIRED_ERROR}

    try:
        new_starts_at = _parse_clinic_datetime(clinic, starts_at)
    except (ValueError, TypeError):
        return {"rescheduled": False, "error": "Invalid date or time."}
    if not new_starts_at:
        return {"rescheduled": False, "error": "Invalid date or time."}
    if new_starts_at <= timezone.now():
        return {"rescheduled": False, "error": "Cannot reschedule to the past."}

    with transaction.atomic():
        locked_clinic = Clinic.objects.select_for_update().get(pk=clinic.pk)
        appointment, error = _verified_appointment_for_clinic(locked_clinic, reference_code, phone)
        if error:
            return {"rescheduled": False, "error": error}
        duration = appointment.service.effective_duration()
        new_ends_at = new_starts_at + timedelta(minutes=duration)
        try:
            validate_slot(locked_clinic, new_starts_at, new_ends_at, exclude_appointment=appointment)
        except ValidationError as exc:
            return {"rescheduled": False, "error": _validation_error_text(exc)}
        appointment.starts_at = new_starts_at
        appointment.ends_at = new_ends_at
        appointment.save(update_fields=["starts_at", "ends_at", "updated_at"])
        return {"rescheduled": True, "appointment": _appointment_summary(locked_clinic, appointment)}
```

- [ ] **Step 4: Run reschedule tests and verify pass**

Run:

```powershell
.\env\Scripts\activate; if ($?) { python -m pytest messenger/tests.py -k "reschedule_verified_appointment" -q }
```

Expected: PASS for reschedule tests.

- [ ] **Step 5: Commit reschedule work if commits are authorized**

Run only if the user explicitly authorized commits:

```powershell
git status --short; if ($?) { git diff -- messenger/tests.py messenger/ai_tools.py }; if ($?) { git add messenger/tests.py messenger/ai_tools.py }; if ($?) { git commit -m "feat: add assistant appointment reschedule tool" }
```

Expected: one commit containing only reschedule-related changes.

### Task 4: Secret-Protected Django AI Endpoints

**Files:**
- Modify: `messenger/tests.py`
- Modify: `messenger/views.py`
- Modify: `messenger/urls.py`

- [ ] **Step 1: Add failing endpoint tests**

Append these tests near existing AI endpoint secret tests in `messenger/tests.py`.

```python
@pytest.mark.django_db
@override_settings(N8N_WEBHOOK_SECRET="secret123")
def test_ai_appointment_lookup_endpoint_requires_secret(client):
    response = client.post(
        reverse("messenger:ai_appointment_lookup"),
        data=json.dumps({"page_id": "PAGE", "reference_code": "CF-TEST", "phone": "09175551234"}),
        content_type="application/json",
    )

    assert response.status_code == 401


@pytest.mark.django_db
@override_settings(N8N_WEBHOOK_SECRET="secret123")
def test_ai_appointment_cancel_endpoint_accepts_string_true_confirmation(client):
    clinic, _connection = _create_messenger_clinic("owner_ai_endpoint_cancel", "PAGE-AI-ENDPOINT-CANCEL")
    service = Service.objects.create(clinic=clinic, name="Consultation", duration_minutes=30, price=0)
    patient = Patient.objects.create(clinic=clinic, full_name="Maria Santos", phone="09175551234")
    starts_at = timezone.now() + timedelta(days=1)
    appointment = Appointment.objects.create(
        clinic=clinic,
        patient=patient,
        service=service,
        starts_at=starts_at,
        ends_at=starts_at + timedelta(minutes=30),
        status=Appointment.STATUS_CONFIRMED,
    )

    response = client.post(
        reverse("messenger:ai_appointment_cancel"),
        data=json.dumps({
            "page_id": "PAGE-AI-ENDPOINT-CANCEL",
            "reference_code": appointment.reference_code,
            "phone": "09175551234",
            "confirmed": "true",
            "reason": "Requested in chat.",
        }),
        content_type="application/json",
        HTTP_X_N8N_WEBHOOK_SECRET="secret123",
    )

    appointment.refresh_from_db()
    assert response.status_code == 200
    assert response.json()["cancelled"] is True
    assert appointment.status == Appointment.STATUS_CANCELLED


@pytest.mark.django_db
@override_settings(N8N_WEBHOOK_SECRET="secret123")
def test_widget_ai_appointment_reschedule_endpoint_uses_clinic_slug(client):
    from zoneinfo import ZoneInfo

    clinic, _connection = _create_messenger_clinic("owner_widget_endpoint_reschedule", "PAGE-WIDGET-ENDPOINT-RESCHEDULE")
    service = Service.objects.create(clinic=clinic, name="Consultation", duration_minutes=30, price=0)
    patient = Patient.objects.create(clinic=clinic, full_name="Maria Santos", phone="09175551234")
    clinic_tz = ZoneInfo(clinic.timezone)
    target_date = timezone.now().astimezone(clinic_tz).date() + timedelta(days=1)
    ClinicBusinessHour.objects.create(clinic=clinic, weekday=target_date.weekday(), open_time=time(9), close_time=time(12))
    original_start = timezone.make_aware(timezone.datetime.combine(target_date, time(9)), clinic_tz)
    new_start = timezone.make_aware(timezone.datetime.combine(target_date, time(10)), clinic_tz)
    appointment = Appointment.objects.create(
        clinic=clinic,
        patient=patient,
        service=service,
        starts_at=original_start,
        ends_at=original_start + timedelta(minutes=30),
        status=Appointment.STATUS_CONFIRMED,
    )

    response = client.post(
        reverse("messenger:widget_ai_appointment_reschedule"),
        data=json.dumps({
            "clinic_slug": clinic.slug,
            "reference_code": appointment.reference_code,
            "phone": "09175551234",
            "starts_at": new_start.isoformat(),
            "confirmed": "true",
        }),
        content_type="application/json",
        HTTP_X_N8N_WEBHOOK_SECRET="secret123",
    )

    appointment.refresh_from_db()
    assert response.status_code == 200
    assert response.json()["rescheduled"] is True
    assert appointment.starts_at == new_start
```

- [ ] **Step 2: Run endpoint tests and verify failure**

Run:

```powershell
.\env\Scripts\activate; if ($?) { python -m pytest messenger/tests.py -k "ai_appointment" -q }
```

Expected: FAIL with missing URL names or missing view functions.

- [ ] **Step 3: Add view imports and endpoint functions**

Update the `from .ai_tools import (...)` block in `messenger/views.py` to include these names.

```python
    cancel_verified_appointment,
    cancel_widget_verified_appointment,
    find_verified_appointment,
    find_widget_verified_appointment,
    reschedule_verified_appointment,
    reschedule_widget_verified_appointment,
```

Add these endpoint functions after `ai_book()` in `messenger/views.py`.

```python
@csrf_exempt
@require_http_methods(["POST"])
def ai_appointment_lookup(request):
    return _ai_tool_response(request, lambda data: find_verified_appointment(
        data.get("page_id", ""),
        data.get("reference_code", ""),
        data.get("phone", ""),
    ))


@csrf_exempt
@require_http_methods(["POST"])
def ai_appointment_cancel(request):
    return _ai_tool_response(request, lambda data: cancel_verified_appointment(
        data.get("page_id", ""),
        data.get("reference_code", ""),
        data.get("phone", ""),
        _normalize_confirmed(data.get("confirmed", False)),
        data.get("reason", ""),
    ))


@csrf_exempt
@require_http_methods(["POST"])
def ai_appointment_reschedule(request):
    return _ai_tool_response(request, lambda data: reschedule_verified_appointment(
        data.get("page_id", ""),
        data.get("reference_code", ""),
        data.get("phone", ""),
        data.get("starts_at", ""),
        _normalize_confirmed(data.get("confirmed", False)),
    ))
```

Add these endpoint functions after `widget_ai_book()` in `messenger/views.py`.

```python
@csrf_exempt
@require_http_methods(["POST"])
def widget_ai_appointment_lookup(request):
    return _ai_tool_response(request, lambda data: find_widget_verified_appointment(
        data.get("clinic_slug", ""),
        data.get("reference_code", ""),
        data.get("phone", ""),
    ))


@csrf_exempt
@require_http_methods(["POST"])
def widget_ai_appointment_cancel(request):
    return _ai_tool_response(request, lambda data: cancel_widget_verified_appointment(
        data.get("clinic_slug", ""),
        data.get("reference_code", ""),
        data.get("phone", ""),
        _normalize_confirmed(data.get("confirmed", False)),
        data.get("reason", ""),
    ))


@csrf_exempt
@require_http_methods(["POST"])
def widget_ai_appointment_reschedule(request):
    return _ai_tool_response(request, lambda data: reschedule_widget_verified_appointment(
        data.get("clinic_slug", ""),
        data.get("reference_code", ""),
        data.get("phone", ""),
        data.get("starts_at", ""),
        _normalize_confirmed(data.get("confirmed", False)),
    ))
```

- [ ] **Step 4: Add URL routes**

Add these routes to `messenger/urls.py` after the existing AI booking routes.

```python
    path("ai/appointment/lookup/", views.ai_appointment_lookup, name="ai_appointment_lookup"),
    path("ai/appointment/cancel/", views.ai_appointment_cancel, name="ai_appointment_cancel"),
    path("ai/appointment/reschedule/", views.ai_appointment_reschedule, name="ai_appointment_reschedule"),
    path("ai/widget/appointment/lookup/", views.widget_ai_appointment_lookup, name="widget_ai_appointment_lookup"),
    path("ai/widget/appointment/cancel/", views.widget_ai_appointment_cancel, name="widget_ai_appointment_cancel"),
    path("ai/widget/appointment/reschedule/", views.widget_ai_appointment_reschedule, name="widget_ai_appointment_reschedule"),
```

- [ ] **Step 5: Run endpoint tests and verify pass**

Run:

```powershell
.\env\Scripts\activate; if ($?) { python -m pytest messenger/tests.py -k "ai_appointment" -q }
```

Expected: PASS for endpoint tests.

- [ ] **Step 6: Commit endpoint work if commits are authorized**

Run only if the user explicitly authorized commits:

```powershell
git status --short; if ($?) { git diff -- messenger/tests.py messenger/views.py messenger/urls.py }; if ($?) { git add messenger/tests.py messenger/views.py messenger/urls.py }; if ($?) { git commit -m "feat: expose assistant appointment management endpoints" }
```

Expected: one commit containing only endpoint-related changes.

### Task 5: Shared n8n Appointment Management Tools

**Files:**
- Modify: `tests/test_n8n_combined_bridge_source.py`
- Modify: `n8n_combined_messenger_widget_ai_bridge.ts`

- [ ] **Step 1: Add failing n8n source tests**

Append these tests after `test_combined_bridge_widget_ai_prompt_requires_tools_and_explicit_confirmation()` in `tests/test_n8n_combined_bridge_source.py`.

```python
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
    assert "/messenger/ai/appointment/cancel/" in cancel_block
    assert "/messenger/ai/widget/appointment/cancel/" in cancel_block
    assert "/messenger/ai/appointment/reschedule/" in reschedule_block
    assert "/messenger/ai/widget/appointment/reschedule/" in reschedule_block
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
```

- [ ] **Step 2: Run n8n source tests and verify failure**

Run:

```powershell
.\env\Scripts\activate; if ($?) { python -m pytest tests/test_n8n_combined_bridge_source.py -k "appointment_management or verified_cancel" -q }
```

Expected: FAIL because the new tool names and prompt strings are not in the workflow source.

- [ ] **Step 3: Add n8n tool definitions**

In `n8n_combined_messenger_widget_ai_bridge.ts`, add these tool definitions after `bookConfirmedAppointmentTool` and before `getMessengerQuickReplies`.

```typescript
const findVerifiedAppointmentTool = tool({
  type: 'n8n-nodes-base.httpRequestTool',
  version: 4.4,
  config: {
    name: 'find_verified_appointment',
    position: [2176, 1040],
    parameters: {
      method: 'POST',
      url: expr(`{{ $("Shared AI Input").item.json.channel === "messenger" ? "${DJANGO_BASE_URL}/messenger/ai/appointment/lookup/" : "${DJANGO_BASE_URL}/messenger/ai/widget/appointment/lookup/" }}`),
      authentication: 'genericCredentialType',
      genericAuthType: 'httpHeaderAuth',
      sendHeaders: true,
      headerParameters: { parameters: [{ name: 'Content-Type', value: 'application/json' }] },
      sendBody: true,
      specifyBody: 'json',
      jsonBody: {
        page_id: expr('{{ $("Shared AI Input").item.json.channel === "messenger" ? $("Shared AI Input").item.json.page_id : "" }}'),
        clinic_slug: expr('{{ $("Shared AI Input").item.json.channel === "widget" ? $("Shared AI Input").item.json.clinic_slug : "" }}'),
        reference_code: fromAi('reference_code', 'Appointment reference code provided by the patient'),
        phone: fromAi('phone', 'Patient phone number for verification'),
      },
      options: {},
      optimizeResponse: true,
    },
    credentials: { httpHeaderAuth: newCredential('KliniAssist N8N Webhook Secret', N8N_WEBHOOK_CREDENTIAL_ID) },
  },
  output: [{ found: false, error: 'Appointment not found. Please check the reference code and phone number.' }],
});

const cancelVerifiedAppointmentTool = tool({
  type: 'n8n-nodes-base.httpRequestTool',
  version: 4.4,
  config: {
    name: 'cancel_verified_appointment',
    position: [2304, 1040],
    parameters: {
      method: 'POST',
      url: expr(`{{ $("Shared AI Input").item.json.channel === "messenger" ? "${DJANGO_BASE_URL}/messenger/ai/appointment/cancel/" : "${DJANGO_BASE_URL}/messenger/ai/widget/appointment/cancel/" }}`),
      authentication: 'genericCredentialType',
      genericAuthType: 'httpHeaderAuth',
      sendHeaders: true,
      headerParameters: { parameters: [{ name: 'Content-Type', value: 'application/json' }] },
      sendBody: true,
      specifyBody: 'json',
      jsonBody: {
        page_id: expr('{{ $("Shared AI Input").item.json.channel === "messenger" ? $("Shared AI Input").item.json.page_id : "" }}'),
        clinic_slug: expr('{{ $("Shared AI Input").item.json.channel === "widget" ? $("Shared AI Input").item.json.clinic_slug : "" }}'),
        reference_code: fromAi('reference_code', 'Appointment reference code provided by the patient'),
        phone: fromAi('phone', 'Patient phone number for verification'),
        confirmed: fromAi('confirmed', 'Boolean true only after the user explicitly confirms the cancellation summary'),
        reason: fromAi('reason', 'Cancellation reason if the patient provided one, otherwise blank'),
      },
      options: {},
      optimizeResponse: true,
    },
    credentials: { httpHeaderAuth: newCredential('KliniAssist N8N Webhook Secret', N8N_WEBHOOK_CREDENTIAL_ID) },
  },
  output: [{ cancelled: false, error: 'Appointment change requires explicit user confirmation.' }],
});

const rescheduleVerifiedAppointmentTool = tool({
  type: 'n8n-nodes-base.httpRequestTool',
  version: 4.4,
  config: {
    name: 'reschedule_verified_appointment',
    position: [2432, 1040],
    parameters: {
      method: 'POST',
      url: expr(`{{ $("Shared AI Input").item.json.channel === "messenger" ? "${DJANGO_BASE_URL}/messenger/ai/appointment/reschedule/" : "${DJANGO_BASE_URL}/messenger/ai/widget/appointment/reschedule/" }}`),
      authentication: 'genericCredentialType',
      genericAuthType: 'httpHeaderAuth',
      sendHeaders: true,
      headerParameters: { parameters: [{ name: 'Content-Type', value: 'application/json' }] },
      sendBody: true,
      specifyBody: 'json',
      jsonBody: {
        page_id: expr('{{ $("Shared AI Input").item.json.channel === "messenger" ? $("Shared AI Input").item.json.page_id : "" }}'),
        clinic_slug: expr('{{ $("Shared AI Input").item.json.channel === "widget" ? $("Shared AI Input").item.json.clinic_slug : "" }}'),
        reference_code: fromAi('reference_code', 'Appointment reference code provided by the patient'),
        phone: fromAi('phone', 'Patient phone number for verification'),
        starts_at: fromAi('starts_at', 'Confirmed new appointment start time as clinic-local ISO 8601 datetime with timezone offset'),
        confirmed: fromAi('confirmed', 'Boolean true only after the user explicitly confirms the reschedule summary'),
      },
      options: {},
      optimizeResponse: true,
    },
    credentials: { httpHeaderAuth: newCredential('KliniAssist N8N Webhook Secret', N8N_WEBHOOK_CREDENTIAL_ID) },
  },
  output: [{ rescheduled: false, error: 'Appointment change requires explicit user confirmation.' }],
});
```

- [ ] **Step 4: Attach tools to the shared AI agent**

Update the `tools` array inside `kliniAssistSharedAiAgent`.

```typescript
tools: [
  matchServicesTool,
  checkAvailabilityTool,
  bookConfirmedAppointmentTool,
  findVerifiedAppointmentTool,
  cancelVerifiedAppointmentTool,
  rescheduleVerifiedAppointmentTool,
],
```

- [ ] **Step 5: Update the shared AI prompt**

In the shared AI agent `systemMessage`, replace the current single booking sentence with this text.

```typescript
'Use match_services, check_availability, and book_confirmed_appointment for booking. Ask for explicit confirmation before booking. ' +
'For appointment cancellation and rescheduling: Ask for appointment reference code and phone number before appointment management lookup. ' +
'Use find_verified_appointment before canceling or rescheduling. Summarize the verified appointment and requested action before mutation. ' +
'Ask for explicit confirmation before canceling or rescheduling. Use cancel_verified_appointment and reschedule_verified_appointment only after explicit confirmation. ' +
'For reschedule availability checks, use only the service_id returned by find_verified_appointment, never a user-supplied service ID. ' +
'Do not use user-supplied appointment IDs, patient IDs, clinic IDs, or service IDs for appointment management. ' +
'Never expose secrets, invent clinic data, give medical diagnosis, or create or change appointments without tool validation. Messenger replies must be plain concise text. Widget replies must be concise and friendly.'
```

- [ ] **Step 6: Run n8n source tests and verify pass**

Run:

```powershell
.\env\Scripts\activate; if ($?) { python -m pytest tests/test_n8n_combined_bridge_source.py -q }
```

Expected: PASS for all n8n combined bridge source tests.

- [ ] **Step 7: Commit n8n work if commits are authorized**

Run only if the user explicitly authorized commits:

```powershell
git status --short; if ($?) { git diff -- tests/test_n8n_combined_bridge_source.py n8n_combined_messenger_widget_ai_bridge.ts }; if ($?) { git add tests/test_n8n_combined_bridge_source.py n8n_combined_messenger_widget_ai_bridge.ts }; if ($?) { git commit -m "feat: add assistant appointment management tools to n8n bridge" }
```

Expected: one commit containing only n8n source and source-test changes.

### Task 6: Regression Verification

**Files:**
- No code files changed in this task.

- [ ] **Step 1: Run targeted Messenger tests**

Run:

```powershell
.\env\Scripts\activate; if ($?) { python -m pytest messenger/tests.py -q }
```

Expected: PASS. If failures appear, fix root causes without weakening tests.

- [ ] **Step 2: Run widget tests**

Run:

```powershell
.\env\Scripts\activate; if ($?) { python -m pytest widget/tests.py -q }
```

Expected: PASS. Existing guided booking and AI chat behavior remain unchanged.

- [ ] **Step 3: Run n8n bridge source tests**

Run:

```powershell
.\env\Scripts\activate; if ($?) { python -m pytest tests/test_n8n_combined_bridge_source.py -q }
```

Expected: PASS. The shared bridge contains the new tools and prompt rules.

- [ ] **Step 4: Run Django system check**

Run:

```powershell
.\env\Scripts\activate; if ($?) { python manage.py check }
```

Expected: `System check identified no issues (0 silenced).`

- [ ] **Step 5: Inspect final diff**

Run:

```powershell
git status --short; if ($?) { git diff -- messenger/ai_tools.py messenger/views.py messenger/urls.py messenger/tests.py n8n_combined_messenger_widget_ai_bridge.ts tests/test_n8n_combined_bridge_source.py }
```

Expected: diff includes only the assistant appointment-management implementation and tests. Existing unrelated worktree changes remain untouched.

- [ ] **Step 6: Final commit if commits are authorized and previous tasks were not committed**

Run only if the user explicitly authorized commits and task-level commits were skipped:

```powershell
git status --short; if ($?) { git add messenger/ai_tools.py messenger/views.py messenger/urls.py messenger/tests.py n8n_combined_messenger_widget_ai_bridge.ts tests/test_n8n_combined_bridge_source.py docs/superpowers/specs/2026-06-04-assistant-appointment-management-design.md docs/superpowers/plans/2026-06-04-assistant-appointment-management-implementation-plan.md }; if ($?) { git commit -m "feat: add assistant appointment management" }
```

Expected: one commit containing only the feature implementation, tests, spec, and plan.
