# Required Appointment Email Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Require a valid patient email address for every appointment create/edit path without changing the patient database schema.

**Architecture:** Enforce the rule at the existing booking validation boundaries. Public widget, embed, Messenger AI, and widget AI booking helpers are covered by `_process_guest_booking()` and `_validate_guest_identity()`. Staff dashboard add/edit and calendar modal edit are covered by `StaffAppointmentForm`.

**Tech Stack:** Django forms/views/templates, Django TestCase, pytest, Django templates, HTMX widget booking.

---

## File Structure

- Modify `widget/views.py`: add required-email validation in `_validate_guest_identity()` so all callers of `_process_guest_booking()` reject blank email.
- Modify `templates/widget/widget.html`: mark the direct public booking email input as required.
- Modify `tests/test_design_system.py`: update the widget markup contract for the new `required` attribute.
- Modify `widget/tests.py`: add a regression test for blank email rejection in public booking.
- Modify `appointments/forms.py`: make `GuestBookingForm.email` and `StaffAppointmentForm.patient_email` required.
- Modify `appointments/tests.py`: add a regression test for staff form blank email rejection and update archived-service test data.
- Modify `tests/test_domain.py`: add valid email data to staff form tests that exercise unrelated slot validation.
- Modify `dashboard/tests.py`: give the calendar fixture patient an email so calendar edit continues testing calendar behavior, not email validation.

No migrations are needed because `Patient.email` remains `blank=True`.

---

### Task 1: Public Booking Requires Email

**Files:**
- Modify: `widget/tests.py`
- Modify: `widget/views.py`
- Modify: `templates/widget/widget.html`
- Modify: `tests/test_design_system.py`

- [ ] **Step 1: Add the failing widget booking test**

In `widget/tests.py`, insert this test after `test_widget_booking_rejects_short_phone` and before `test_widget_booking_rejects_invalid_email`:

```python
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
```

- [ ] **Step 2: Run the widget test and verify it fails**

Run:

```powershell
.\env\Scripts\activate; python -m pytest widget/tests.py::WidgetTests::test_widget_booking_rejects_blank_email -q
```

Expected: FAIL because the current server validation allows a blank email and creates the appointment.

- [ ] **Step 3: Require email in shared public booking validation**

In `widget/views.py`, replace `_validate_guest_identity()` with:

```python
def _validate_guest_identity(full_name, phone, email):
    if not full_name or not phone:
        return "Please provide your full name and phone number."
    if len(normalize_phone(phone)) < MIN_BOOKING_PHONE_DIGITS:
        return "Please enter a valid phone number."
    if not email:
        return "Please provide your email address."
    try:
        validate_email(email)
    except ValidationError:
        return "Please enter a valid email address."
    return ""
```

- [ ] **Step 4: Mark the direct widget email input as required**

In `templates/widget/widget.html`, change the direct booking email input on the Step 3 form from:

```html
<div class="cf-field"><label for="widget-email" class="cf-label">Email</label><input id="widget-email" name="email" type="email" autocomplete="email" class="cf-input"></div>
```

to:

```html
<div class="cf-field"><label for="widget-email" class="cf-label">Email</label><input id="widget-email" name="email" type="email" required autocomplete="email" class="cf-input"></div>
```

Do not change the chat `collectInfo.email` field in this task; that field is not currently an appointment submission form.

- [ ] **Step 5: Update the widget markup contract test**

In `tests/test_design_system.py`, change:

```python
    assert "name=\"email\" type=\"email\" autocomplete=\"email\"" in widget
```

to:

```python
    assert "name=\"email\" type=\"email\" required autocomplete=\"email\"" in widget
```

- [ ] **Step 6: Run widget-focused verification**

Run:

```powershell
.\env\Scripts\activate; python -m pytest widget/tests.py::WidgetTests::test_widget_booking_rejects_blank_email widget/tests.py::WidgetTests::test_widget_booking_rejects_invalid_email tests/test_design_system.py::test_widget_mobile_embedding_contracts -q
```

Expected: PASS. The blank email test must return `409`; invalid email must still return `409`; the widget design contract must match the new required email input.

---

### Task 2: Staff Appointment Form Requires Email

**Files:**
- Modify: `appointments/tests.py`
- Modify: `appointments/forms.py`
- Modify: `tests/test_domain.py`
- Modify: `dashboard/tests.py`

- [ ] **Step 1: Add the failing staff form test**

In `appointments/tests.py`, insert this test after `test_staff_form_excludes_archived_services`:

```python
    def test_staff_form_requires_patient_email(self):
        target_date = timezone.localdate() + timedelta(days=1)
        ClinicBusinessHour.objects.create(
            clinic=self.clinic,
            weekday=target_date.weekday(),
            is_open=True,
            open_time=time(9),
            close_time=time(17),
        )

        form = StaffAppointmentForm(
            self.clinic,
            data={
                "patient_name": "New Patient",
                "patient_phone": "09172222222",
                "patient_email": "",
                "date": target_date.isoformat(),
                "time": "09:00",
                "service": self.service.id,
                "status": Appointment.STATUS_PENDING,
                "payment_state": Appointment.PAYMENT_UNPAID,
                "source": Appointment.SOURCE_STAFF,
                "reason": "",
            },
        )

        self.assertFalse(form.is_valid())
        self.assertIn("patient_email", form.errors)
```

- [ ] **Step 2: Run the staff form test and verify it fails**

Run:

```powershell
.\env\Scripts\activate; python -m pytest appointments/tests.py::AppointmentInvariantTests::test_staff_form_requires_patient_email -q
```

Expected: FAIL because the current `StaffAppointmentForm.patient_email` field is optional and the form is valid when the slot is available.

- [ ] **Step 3: Require email in appointment forms**

In `appointments/forms.py`, change:

```python
    email = forms.EmailField(required=False, widget=forms.EmailInput(attrs={"class": _INPUT, "placeholder": "patient@email.com"}))
```

to:

```python
    email = forms.EmailField(widget=forms.EmailInput(attrs={"class": _INPUT, "placeholder": "patient@email.com"}))
```

Also change:

```python
    patient_email = forms.EmailField(required=False, widget=forms.EmailInput(attrs={"class": _INPUT, "placeholder": "patient@email.com"}))
```

to:

```python
    patient_email = forms.EmailField(widget=forms.EmailInput(attrs={"class": _INPUT, "placeholder": "patient@email.com"}))
```

- [ ] **Step 4: Update unrelated staff form tests with valid emails**

In `appointments/tests.py`, inside `test_staff_form_excludes_archived_services`, change the posted `patient_email` from:

```python
                "patient_email": "",
```

to:

```python
                "patient_email": "new.patient@example.com",
```

In `tests/test_domain.py`, inside `test_staff_form_validates_slot_availability`, add this field to the `StaffAppointmentForm` data dict after `patient_phone`:

```python
        "patient_email": "new@example.com",
```

In `tests/test_domain.py`, inside `test_staff_form_rejects_unavailable_date`, add this field to the `StaffAppointmentForm` data dict after `patient_phone`:

```python
        "patient_email": "new@example.com",
```

In `dashboard/tests.py`, update the `calendar_setup` fixture patient creation from:

```python
    patient = Patient.objects.create(clinic=clinic, full_name="Test Patient", phone="09170001111")
```

to:

```python
    patient = Patient.objects.create(
        clinic=clinic,
        full_name="Test Patient",
        phone="09170001111",
        email="test.patient@example.com",
    )
```

- [ ] **Step 5: Run staff-focused verification**

Run:

```powershell
.\env\Scripts\activate; python -m pytest appointments/tests.py::AppointmentInvariantTests::test_staff_form_requires_patient_email appointments/tests.py::AppointmentInvariantTests::test_staff_form_excludes_archived_services tests/test_domain.py::test_staff_form_validates_slot_availability tests/test_domain.py::test_staff_form_rejects_unavailable_date dashboard/tests.py::test_calendar_edit_triggers_refetch_without_table_row_target -q
```

Expected: PASS. The new blank email test must fail validation on `patient_email`; unrelated slot/service/calendar tests must still exercise their original behavior.

---

### Task 3: Final Verification

**Files:**
- Verify only; no file edits expected.

- [ ] **Step 1: Run all appointment and widget tests touched by this change**

Run:

```powershell
.\env\Scripts\activate; python -m pytest appointments/tests.py widget/tests.py tests/test_domain.py::test_staff_form_validates_slot_availability tests/test_domain.py::test_staff_form_rejects_unavailable_date dashboard/tests.py::test_calendar_edit_triggers_refetch_without_table_row_target tests/test_design_system.py::test_widget_mobile_embedding_contracts -q
```

Expected: PASS.

- [ ] **Step 2: Run Django system checks**

Run:

```powershell
.\env\Scripts\activate; python manage.py check
```

Expected: `System check identified no issues`.

- [ ] **Step 3: Review the diff**

Run:

```powershell
git diff -- appointments/forms.py widget/views.py templates/widget/widget.html tests/test_design_system.py widget/tests.py appointments/tests.py tests/test_domain.py dashboard/tests.py docs/superpowers/specs/2026-06-04-required-appointment-email-design.md docs/superpowers/plans/2026-06-04-required-appointment-email-implementation-plan.md
```

Expected: Diff contains only required email validation, required widget markup, tests, and the approved docs. Do not commit unless the user explicitly asks for a commit.

---

## Self-Review

- Spec coverage: Public widget/embed booking is covered by Task 1. Messenger and widget AI booking helpers are covered through `_process_guest_booking()` in Task 1. Staff dashboard add/edit and calendar modal edit are covered by `StaffAppointmentForm` in Task 2. Existing patient records without email remain allowed because no model or migration changes are planned.
- Placeholder scan: No placeholders remain; each code change and verification command is explicit.
- Type consistency: Field names match the existing code: `email`, `patient_email`, `_validate_guest_identity`, `StaffAppointmentForm`, and `Patient.objects.create`.
