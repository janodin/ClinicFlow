# Signup Onboarding Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Harden clinic-owner signup and add a first-run onboarding flow that collects the operational clinic fields needed before a new workspace is useful.

**Architecture:** Keep signup short and focused on account/tenant bootstrap, then redirect the new owner to an authenticated onboarding page. Store consent on the user, mark newly created clinics as requiring onboarding, and clear that flag after the owner saves contact, service, scheduling, and booking settings.

**Tech Stack:** Django forms/views/models/templates, Django migrations, pytest, HTMX/Tailwind-compatible templates.

---

## File Structure

- Modify: `accounts/models.py` - store owner terms/privacy consent timestamp.
- Modify: `clinics/models.py` - mark clinics that still need first-run onboarding.
- Modify: `accounts/forms.py` - add signup validation fields and `FirstRunOnboardingForm`.
- Modify: `accounts/views.py` - make signup atomic, redirect to onboarding, implement onboarding save.
- Modify: `accounts/urls.py` - add `onboarding/` route.
- Create: `templates/accounts/onboarding.html` - first-run clinic setup form.
- Modify: `tests/test_flows.py` - update current signup happy-path expectations.
- Modify: `accounts/tests.py` - add focused signup/onboarding validation tests.
- Create: model migrations for `accounts.User.terms_accepted_at` and `clinics.Clinic.requires_onboarding`.

## Task 1: Signup Validation Tests

**Files:**
- Modify: `accounts/tests.py`
- Modify: `tests/test_flows.py`

- [ ] **Step 1: Write failing tests for strengthened signup**

Add tests like:

```python
import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from clinics.models import Clinic


@pytest.mark.django_db
def test_signup_requires_password_confirmation(client):
    response = client.post(
        reverse("accounts:signup"),
        {
            "full_name": "Demo User",
            "email": "demo@example.com",
            "clinic_name": "Demo Clinic",
            "timezone": "Asia/Manila",
            "password": "password12345",
            "password_confirm": "different12345",
            "terms_accepted": "on",
        },
    )

    assert response.status_code == 200
    assert b"Passwords do not match." in response.content
    assert get_user_model().objects.count() == 0


@pytest.mark.django_db
def test_signup_requires_terms_acceptance(client):
    response = client.post(
        reverse("accounts:signup"),
        {
            "full_name": "Demo User",
            "email": "demo@example.com",
            "clinic_name": "Demo Clinic",
            "timezone": "Asia/Manila",
            "password": "password12345",
            "password_confirm": "password12345",
        },
    )

    assert response.status_code == 200
    assert b"You must accept the terms and privacy policy." in response.content
    assert get_user_model().objects.count() == 0


@pytest.mark.django_db
def test_signup_saves_timezone_consent_and_requires_onboarding(client):
    response = client.post(
        reverse("accounts:signup"),
        {
            "full_name": "Demo User",
            "email": "Demo@Example.com",
            "clinic_name": "Demo Clinic",
            "timezone": "Pacific/Kiritimati",
            "password": "password12345",
            "password_confirm": "password12345",
            "terms_accepted": "on",
        },
    )

    assert response.status_code == 302
    assert response.url == reverse("accounts:onboarding")
    user = get_user_model().objects.get(email="demo@example.com")
    assert user.terms_accepted_at is not None
    clinic = Clinic.objects.get(slug="demo-clinic")
    assert clinic.timezone == "Pacific/Kiritimati"
    assert clinic.requires_onboarding is True
```

- [ ] **Step 2: Update existing flow test data**

In `tests/test_flows.py::test_signup_creates_usable_clinic`, post the new required fields and expect redirect to onboarding:

```python
"timezone": "Asia/Manila",
"password_confirm": "password123",
"terms_accepted": "on",
```

Expected redirect:

```python
assert response.status_code == 302
assert response.url == reverse("accounts:onboarding")
```

- [ ] **Step 3: Run tests and verify RED**

Run: `python -m pytest accounts/tests.py tests/test_flows.py::test_signup_creates_usable_clinic -q`

Expected: FAIL because `timezone`, `password_confirm`, `terms_accepted_at`, `requires_onboarding`, and `accounts:onboarding` do not exist yet.

## Task 2: Signup Model/Form/View Implementation

**Files:**
- Modify: `accounts/models.py`
- Modify: `clinics/models.py`
- Modify: `accounts/forms.py`
- Modify: `accounts/views.py`
- Modify: `accounts/urls.py`
- Create: migrations under `accounts/migrations/` and `clinics/migrations/`

- [ ] **Step 1: Add model fields**

In `accounts/models.py`:

```python
from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    """Clinic owner/staff login user. Patients remain guest records in V1."""

    terms_accepted_at = models.DateTimeField(blank=True, null=True)

    def display_name(self):
        return self.get_full_name() or self.email or self.username
```

In `clinics/models.py`, add to `Clinic`:

```python
requires_onboarding = models.BooleanField(default=False)
```

- [ ] **Step 2: Generate migrations**

Run: `python manage.py makemigrations accounts clinics`

Expected: new migrations for `terms_accepted_at` and `requires_onboarding`.

- [ ] **Step 3: Implement signup form validation**

In `accounts/forms.py`, add timezone choices, password confirmation, terms checkbox, and call Django password validators:

```python
from zoneinfo import available_timezones

from django.contrib.auth.password_validation import validate_password

_TIMEZONE_CHOICES = sorted([(tz, tz) for tz in available_timezones()])

class SignUpForm(forms.Form):
    full_name = forms.CharField(...)
    email = forms.EmailField(...)
    clinic_name = forms.CharField(...)
    timezone = forms.ChoiceField(choices=_TIMEZONE_CHOICES, initial="Asia/Manila", widget=forms.Select(attrs={"class": "cf-select"}))
    password = forms.CharField(..., min_length=8)
    password_confirm = forms.CharField(label="Confirm password", widget=forms.PasswordInput(attrs={"class": _INPUT, "placeholder": "Confirm your password"}))
    terms_accepted = forms.BooleanField(error_messages={"required": "You must accept the terms and privacy policy."}, widget=forms.CheckboxInput(attrs={"class": "cf-checkbox"}))

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get("password")
        password_confirm = cleaned_data.get("password_confirm")
        email = cleaned_data.get("email")
        if password and password_confirm and password != password_confirm:
            self.add_error("password_confirm", "Passwords do not match.")
        if password:
            user = User(username=email or "", email=email or "")
            try:
                validate_password(password, user)
            except forms.ValidationError as exc:
                self.add_error("password", exc)
        return cleaned_data
```

Also make clinic slug generation robust for punctuation-only names by falling back to `clinic` when `slugify(name)` is empty.

- [ ] **Step 4: Implement atomic signup and redirect**

In `accounts/views.py`, use `transaction.atomic()`, set `terms_accepted_at=timezone.now()`, set `clinic.timezone`, mark `requires_onboarding=True`, and redirect to `accounts:onboarding`.

```python
with transaction.atomic():
    user = User.objects.create_user(..., terms_accepted_at=timezone.now())
    group = ClinicGroup.objects.create(...)
    clinic = Clinic.objects.create(
        group=group,
        name=form.cleaned_data["clinic_name"],
        slug=form.cleaned_data["clinic_slug"],
        email=user.email,
        timezone=form.cleaned_data["timezone"],
        requires_onboarding=True,
    )
```

Add `path("onboarding/", views.onboarding, name="onboarding")` to `accounts/urls.py`. Add a placeholder authenticated `onboarding` view returning the template context so signup redirect resolves before Task 4 fills behavior.

- [ ] **Step 5: Run tests and verify GREEN for signup**

Run: `python -m pytest accounts/tests.py::test_signup_requires_password_confirmation accounts/tests.py::test_signup_requires_terms_acceptance accounts/tests.py::test_signup_saves_timezone_consent_and_requires_onboarding tests/test_flows.py::test_signup_creates_usable_clinic -q`

Expected: PASS.

## Task 3: First-Run Onboarding Tests

**Files:**
- Modify: `accounts/tests.py`

- [ ] **Step 1: Write failing onboarding tests**

Add tests for owner-only access and successful setup:

```python
from decimal import Decimal

from clinics.models import ClinicGroup, ClinicMembership
from scheduling.models import ClinicBusinessHour
from services.models import Service


@pytest.mark.django_db
def test_onboarding_requires_login(client):
    response = client.get(reverse("accounts:onboarding"))

    assert response.status_code == 302
    assert reverse("accounts:login") in response.url


@pytest.mark.django_db
def test_onboarding_saves_clinic_service_hours_and_clears_flag(client):
    User = get_user_model()
    user = User.objects.create_user(username="owner@example.com", email="owner@example.com", password="password123")
    group = ClinicGroup.objects.create(name="Demo Clinic", owner=user)
    clinic = Clinic.objects.create(group=group, name="Demo Clinic", slug="demo-clinic", requires_onboarding=True)
    ClinicMembership.objects.create(clinic=clinic, user=user, role=ClinicMembership.ROLE_OWNER)
    Service.objects.create(clinic=clinic, name="General Consultation", duration_minutes=30, price=0)
    client.force_login(user)

    response = client.post(
        reverse("accounts:onboarding"),
        {
            "address": "123 Demo Street",
            "phone": "09170001111",
            "email": "frontdesk@example.com",
            "timezone": "Asia/Manila",
            "default_appointment_duration": "45",
            "booking_approval_mode": Clinic.APPROVAL_MANUAL,
            "service_name": "Dental Cleaning",
            "service_duration_minutes": "45",
            "service_price": "800.00",
            "is_open_0": "on",
            "open_time_0": "09:00",
            "close_time_0": "17:00",
            "break_start_0": "12:00",
            "break_end_0": "13:00",
            "is_open_1": "on",
            "open_time_1": "09:00",
            "close_time_1": "17:00",
            "break_start_1": "12:00",
            "break_end_1": "13:00",
            "is_open_2": "on",
            "open_time_2": "09:00",
            "close_time_2": "17:00",
            "break_start_2": "12:00",
            "break_end_2": "13:00",
            "is_open_3": "on",
            "open_time_3": "09:00",
            "close_time_3": "17:00",
            "break_start_3": "12:00",
            "break_end_3": "13:00",
            "is_open_4": "on",
            "open_time_4": "09:00",
            "close_time_4": "17:00",
            "break_start_4": "12:00",
            "break_end_4": "13:00",
            "open_time_5": "09:00",
            "close_time_5": "17:00",
            "open_time_6": "09:00",
            "close_time_6": "17:00",
        },
    )

    assert response.status_code == 302
    assert response.url == reverse("dashboard:home")
    clinic.refresh_from_db()
    assert clinic.requires_onboarding is False
    assert clinic.address == "123 Demo Street"
    assert clinic.phone == "09170001111"
    assert clinic.email == "frontdesk@example.com"
    assert clinic.default_appointment_duration == 45
    assert clinic.booking_approval_mode == Clinic.APPROVAL_MANUAL
    service = clinic.services.get()
    assert service.name == "Dental Cleaning"
    assert service.duration_minutes == 45
    assert service.price == Decimal("800.00")
    assert clinic.business_hours.filter(is_open=True).count() == 5
```

- [ ] **Step 2: Run tests and verify RED**

Run: `python -m pytest accounts/tests.py::test_onboarding_requires_login accounts/tests.py::test_onboarding_saves_clinic_service_hours_and_clears_flag -q`

Expected: FAIL because onboarding view/form/template behavior is not implemented.

## Task 4: First-Run Onboarding Implementation

**Files:**
- Modify: `accounts/forms.py`
- Modify: `accounts/views.py`
- Create: `templates/accounts/onboarding.html`

- [ ] **Step 1: Add onboarding form**

Create `FirstRunOnboardingForm(forms.Form)` in `accounts/forms.py` with clinic contact fields, service fields, booking approval mode, and validation for seven business-hour rows. Use the same POST field names as dashboard settings: `is_open_0`, `open_time_0`, `close_time_0`, `break_start_0`, `break_end_0` through weekday `6`.

- [ ] **Step 2: Implement onboarding view**

In `accounts/views.py`, add `@login_required def onboarding(request):` that:

```python
membership = get_active_membership(request.user)
if not membership:
    return redirect("accounts:signup")
if membership.role != ClinicMembership.ROLE_OWNER:
    raise PermissionDenied
clinic = membership.clinic
service = clinic.services.filter(is_archived=False).order_by("created_at", "id").first()
```

On valid POST, update clinic, update/create first service, replace business-hour rows with validated rows, set `clinic.requires_onboarding = False`, save, show success message, redirect to `dashboard:home`.

- [ ] **Step 3: Add onboarding template**

Create `templates/accounts/onboarding.html` using existing `base.html`, `cf-card`, `cf-input`, `cf-select`, `cf-checkbox`, and the Neon Aqua Clinical auth surface. Include sections for clinic contact, first service, booking behavior, and business hours.

- [ ] **Step 4: Run onboarding tests and verify GREEN**

Run: `python -m pytest accounts/tests.py::test_onboarding_requires_login accounts/tests.py::test_onboarding_saves_clinic_service_hours_and_clears_flag -q`

Expected: PASS.

## Task 5: Migration, Regression, and System Verification

**Files:**
- Modify if needed: `templates/privacy_policy.html`
- Modify if needed: `tests/test_design_system.py`

- [ ] **Step 1: Update privacy copy if owner data collection changed**

If signup/onboarding now collects owner consent and clinic contact data, update `templates/privacy_policy.html` to mention account owner and clinic workspace information.

- [ ] **Step 2: Run migrations locally**

Run: `python manage.py migrate`

Expected: all migrations apply.

- [ ] **Step 3: Run Django checks**

Run: `python manage.py check`

Expected: no issues.

- [ ] **Step 4: Run focused pytest suite**

Run: `python -m pytest accounts/tests.py tests/test_flows.py -q`

Expected: PASS.

- [ ] **Step 5: Run design/template checks if template assertions fail or onboarding template impacts auth design**

Run: `python -m pytest tests/test_design_system.py -q`

Expected: PASS or update tests only for intentional copy/template changes.

## Self-Review

- Spec coverage: signup hardening, required timezone/confirm-password/consent, atomic tenant creation, first-run onboarding, clinic operational fields, tests, migrations, and privacy impact are covered.
- Placeholder scan: no `TBD`, `TODO`, or unspecified implementation steps remain.
- Type consistency: fields match existing models (`Clinic`, `Service`, `ClinicBusinessHour`, `ClinicMembership`) and new fields are named consistently as `terms_accepted_at` and `requires_onboarding`.
