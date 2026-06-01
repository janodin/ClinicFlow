# Production Security Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Harden the Django clinic booking SaaS for production by closing trusted-webhook failures, improving deployment security checks, and protecting public booking integrity.

**Architecture:** Keep the current Django app structure and add small boundary checks where requests enter the system. Webhook trust stays in `messenger/views.py`, production checks stay in the `config` package, guest booking integrity stays in `widget/views.py` and `patients/models.py`, and dashboard ownership checks stay in `dashboard/views.py`.

**Tech Stack:** Django 5.2, pytest/pytest-django, PostgreSQL target with SQLite-compatible local tests, Django templates, HTMX, Alpine.js.

---

## Workspace Rules

- The worktree is already dirty with many user changes. Do not revert unrelated files.
- Use `apply_patch` for manual edits.
- Use `./env/Scripts/python.exe` on Windows for Django and pytest commands.
- Do not create git commits unless the user explicitly asks.
- If a model field changes, run `python manage.py makemigrations`, `python manage.py migrate`, and `python manage.py check`.

## File Structure

- Modify: `messenger/views.py` for n8n shared-secret checks and Messenger signature enforcement.
- Modify: `messenger/tests.py` for webhook auth/signature regression tests.
- Modify: `messenger/messenger_api.py` only if `verify_signature()` needs a missing-secret guard.
- Modify: `config/settings.py` for explicit environment parsing and secure production defaults.
- Create: `config/security_checks.py` for deploy-time security checks.
- Modify: `.env.example` for production-required security variables.
- Modify: `DEPLOYMENT.md` for production security gates.
- Modify: `patients/models.py` to prevent unauthenticated patient demographic overwrites.
- Modify: `widget/views.py` to validate booking input, derive public source server-side, and lock/recheck slot creation.
- Modify: `widget/tests.py` for booking validation, source tampering, patient matching, and widget escaping coverage.
- Modify: `clinics/models.py` to validate widget accent color at the model/form layer.
- Create: `clinics/migrations/<next>_validate_widget_accent_color.py` via `makemigrations`.
- Modify: `clinics/forms.py` only if the generated model validator error message needs a clearer form-level message.
- Modify: `templates/widget/widget.html` to remove hidden source trust and escape script-bound accent color.
- Modify: `dashboard/views.py` for shared settings permission enforcement.
- Modify: `dashboard/tests.py` for FAQ permission and widget settings validation tests.
- Create: `tests/test_security_checks.py` for deploy check regression tests.

---

### Task 1: Trusted Webhook Boundary

**Files:**
- Modify: `messenger/tests.py`
- Modify: `messenger/views.py`
- Modify: `messenger/messenger_api.py`

- [ ] **Step 1: Add failing n8n webhook tests**

Append these tests near the existing AI endpoint secret tests in `messenger/tests.py`:

```python
@pytest.mark.django_db
@override_settings(N8N_WEBHOOK_SECRET="")
def test_n8n_webhook_fails_closed_when_secret_unset():
    clinic, _connection = _create_messenger_clinic("owner_n8n_unset", "PAGE-N8N-UNSET")
    client = Client()

    response = client.post(
        reverse("messenger:n8n_webhook"),
        data=json.dumps({"page_id": "PAGE-N8N-UNSET", "psid": "PSID1", "text": "Hello"}),
        content_type="application/json",
    )

    assert response.status_code == 401


@pytest.mark.django_db
@override_settings(N8N_WEBHOOK_SECRET="secret123")
def test_n8n_webhook_rejects_invalid_secret():
    _clinic, _connection = _create_messenger_clinic("owner_n8n_bad", "PAGE-N8N-BAD")
    client = Client()

    response = client.post(
        reverse("messenger:n8n_webhook"),
        data=json.dumps({"page_id": "PAGE-N8N-BAD", "psid": "PSID1", "text": "Hello"}),
        content_type="application/json",
        HTTP_X_N8N_WEBHOOK_SECRET="wrong",
    )

    assert response.status_code == 401


@pytest.mark.django_db
@override_settings(N8N_WEBHOOK_SECRET="secret123")
def test_n8n_webhook_accepts_valid_secret():
    _clinic, connection = _create_messenger_clinic("owner_n8n_valid", "PAGE-N8N-VALID")
    client = Client()

    response = client.post(
        reverse("messenger:n8n_webhook"),
        data=json.dumps({"page_id": connection.page_id, "psid": "PSID1", "text": "Hello"}),
        content_type="application/json",
        HTTP_X_N8N_WEBHOOK_SECRET="secret123",
    )

    assert response.status_code == 200
    assert "replies" in response.json()
```

- [ ] **Step 2: Add failing Messenger signature tests**

Append these tests near `test_webhook_post_valid_message` in `messenger/tests.py`:

```python
@pytest.mark.django_db
@override_settings(MESSENGER_APP_SECRET="test_secret")
def test_webhook_post_rejects_missing_signature():
    client = Client()
    user = User.objects.create_user(username="owner_sig_missing", email="owner_sig_missing@test.com", password="pass")
    group = ClinicGroup.objects.create(name="GroupSigMissing", owner=user)
    clinic = Clinic.objects.create(group=group, name="ClinicSigMissing")
    MessengerConnection.objects.create(clinic=clinic, page_id="PAGE-SIG-MISSING", page_access_token="TOKEN")
    payload = json.dumps({"object": "page", "entry": []}).encode()

    response = client.post(reverse("messenger:webhook"), data=payload, content_type="application/json")

    assert response.status_code == 403


@pytest.mark.django_db
@override_settings(MESSENGER_APP_SECRET="test_secret")
def test_webhook_post_rejects_invalid_signature():
    client = Client()
    payload = json.dumps({"object": "page", "entry": []}).encode()

    response = client.post(
        reverse("messenger:webhook"),
        data=payload,
        content_type="application/json",
        HTTP_X_HUB_SIGNATURE_256="sha256=bad",
    )

    assert response.status_code == 403


@pytest.mark.django_db
@override_settings(MESSENGER_APP_SECRET="")
def test_webhook_post_rejects_when_app_secret_unset():
    client = Client()
    payload = json.dumps({"object": "page", "entry": []}).encode()

    response = client.post(reverse("messenger:webhook"), data=payload, content_type="application/json")

    assert response.status_code == 403
```

- [ ] **Step 3: Run the new webhook tests and confirm they fail**

Run:

```powershell
.\env\Scripts\python.exe -m pytest messenger/tests.py::test_n8n_webhook_fails_closed_when_secret_unset messenger/tests.py::test_n8n_webhook_rejects_invalid_secret messenger/tests.py::test_webhook_post_rejects_missing_signature messenger/tests.py::test_webhook_post_rejects_invalid_signature messenger/tests.py::test_webhook_post_rejects_when_app_secret_unset -q
```

Expected: at least `test_n8n_webhook_fails_closed_when_secret_unset` and the Messenger POST rejection tests fail against the current code.

- [ ] **Step 4: Make webhook auth fail closed**

Update imports and helper logic in `messenger/views.py`:

```python
from django.utils.crypto import constant_time_compare

from .messenger_api import verify_signature
```

Replace `_verify_n8n_secret()` and `_verify_ai_tool_secret()` with:

```python
def _verify_shared_secret(request):
    expected_secret = getattr(settings, "N8N_WEBHOOK_SECRET", "")
    provided_secret = request.headers.get("X-N8N-Webhook-Secret", "")
    return bool(expected_secret) and constant_time_compare(provided_secret, expected_secret)


def _verify_n8n_secret(request):
    return _verify_shared_secret(request)


def _verify_ai_tool_secret(request):
    return _verify_shared_secret(request)
```

At the start of the POST branch in `webhook()` before parsing JSON, add:

```python
    app_secret = getattr(settings, "MESSENGER_APP_SECRET", "")
    signature = request.headers.get("X-Hub-Signature-256", "")
    if not app_secret or not verify_signature(request.body, signature, app_secret):
        return HttpResponse(status=403)
```

Update `messenger/messenger_api.py` so missing values fail cleanly:

```python
def verify_signature(payload: bytes, signature: str, secret: str) -> bool:
    if not payload or not signature or not secret:
        return False
    if not signature.startswith("sha256="):
        return False
    expected = "sha256=" + hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)
```

- [ ] **Step 5: Run webhook tests again**

Run:

```powershell
.\env\Scripts\python.exe -m pytest messenger/tests.py::test_n8n_webhook_fails_closed_when_secret_unset messenger/tests.py::test_n8n_webhook_rejects_invalid_secret messenger/tests.py::test_n8n_webhook_accepts_valid_secret messenger/tests.py::test_webhook_post_rejects_missing_signature messenger/tests.py::test_webhook_post_rejects_invalid_signature messenger/tests.py::test_webhook_post_rejects_when_app_secret_unset messenger/tests.py::test_webhook_post_valid_message -q
```

Expected: all selected tests pass.

---

### Task 2: Production Settings and Deploy Checks

**Files:**
- Modify: `config/settings.py`
- Create: `config/security_checks.py`
- Create: `tests/test_security_checks.py`
- Modify: `.env.example`
- Modify: `DEPLOYMENT.md`

- [ ] **Step 1: Add failing deploy-check tests**

Create `tests/test_security_checks.py`:

```python
from django.test import override_settings

from config.security_checks import production_security_settings


def _ids(errors):
    return {error.id for error in errors}


@override_settings(
    DEBUG=True,
    SECRET_KEY="django-insecure-dev-clinic-booking-saas",
    ALLOWED_HOSTS=[],
    SESSION_COOKIE_SECURE=False,
    CSRF_COOKIE_SECURE=False,
    SECURE_SSL_REDIRECT=False,
    SECURE_HSTS_SECONDS=0,
    N8N_WEBHOOK_SECRET="",
    MESSENGER_APP_SECRET="",
    MESSENGER_VERIFY_TOKEN="",
)
def test_deploy_check_flags_insecure_settings():
    ids = _ids(production_security_settings(None))

    assert "clinic_security.E001" in ids
    assert "clinic_security.E002" in ids
    assert "clinic_security.E003" in ids
    assert "clinic_security.E004" in ids
    assert "clinic_security.E005" in ids
    assert "clinic_security.E006" in ids
    assert "clinic_security.E007" in ids
    assert "clinic_security.E008" in ids
    assert "clinic_security.E009" in ids
    assert "clinic_security.E010" in ids


@override_settings(
    DEBUG=False,
    SECRET_KEY="prod-secret-key-with-enough-entropy-for-tests",
    ALLOWED_HOSTS=["clinic.example.com"],
    SESSION_COOKIE_SECURE=True,
    CSRF_COOKIE_SECURE=True,
    SECURE_SSL_REDIRECT=True,
    SECURE_HSTS_SECONDS=31536000,
    N8N_WEBHOOK_SECRET="n8n-secret",
    MESSENGER_APP_SECRET="messenger-secret",
    MESSENGER_VERIFY_TOKEN="verify-token",
)
def test_deploy_check_accepts_secure_settings():
    assert production_security_settings(None) == []
```

- [ ] **Step 2: Run deploy-check tests and confirm they fail because the module does not exist**

Run:

```powershell
.\env\Scripts\python.exe -m pytest tests/test_security_checks.py -q
```

Expected: import failure for `config.security_checks`.

- [ ] **Step 3: Implement security checks**

Create `config/security_checks.py`:

```python
from django.conf import settings
from django.core.checks import Error, Tags, register


@register(Tags.security, deploy=True)
def production_security_settings(app_configs, **kwargs):
    errors = []
    if settings.DEBUG:
        errors.append(Error("DEBUG must be disabled in production.", id="clinic_security.E001"))
    if not settings.SECRET_KEY or settings.SECRET_KEY.startswith("django-insecure-"):
        errors.append(Error("SECRET_KEY must be a strong production secret.", id="clinic_security.E002"))
    if not settings.ALLOWED_HOSTS:
        errors.append(Error("ALLOWED_HOSTS must list production hostnames.", id="clinic_security.E003"))
    if not settings.SESSION_COOKIE_SECURE:
        errors.append(Error("SESSION_COOKIE_SECURE must be enabled in production.", id="clinic_security.E004"))
    if not settings.CSRF_COOKIE_SECURE:
        errors.append(Error("CSRF_COOKIE_SECURE must be enabled in production.", id="clinic_security.E005"))
    if not settings.SECURE_SSL_REDIRECT:
        errors.append(Error("SECURE_SSL_REDIRECT must be enabled behind HTTPS.", id="clinic_security.E006"))
    if settings.SECURE_HSTS_SECONDS <= 0:
        errors.append(Error("SECURE_HSTS_SECONDS must be positive after HTTPS is confirmed.", id="clinic_security.E007"))
    if not getattr(settings, "N8N_WEBHOOK_SECRET", ""):
        errors.append(Error("N8N_WEBHOOK_SECRET is required for trusted assistant webhooks.", id="clinic_security.E008"))
    if not getattr(settings, "MESSENGER_APP_SECRET", ""):
        errors.append(Error("MESSENGER_APP_SECRET is required for Messenger signature checks.", id="clinic_security.E009"))
    if not getattr(settings, "MESSENGER_VERIFY_TOKEN", ""):
        errors.append(Error("MESSENGER_VERIFY_TOKEN is required for Messenger webhook verification.", id="clinic_security.E010"))
    return errors
```

In `config/settings.py`, import the checks after settings are defined:

```python
import config.security_checks  # noqa: F401
```

- [ ] **Step 4: Harden settings parsing**

In `config/settings.py`, add helpers near the top:

```python
def env_bool(name, default=False):
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def env_list(name, default=""):
    return [item.strip() for item in os.getenv(name, default).split(",") if item.strip()]
```

Replace DEBUG and host/proxy settings with:

```python
DJANGO_ENV = os.getenv("DJANGO_ENV", "development")
IS_PRODUCTION = DJANGO_ENV == "production"
SECRET_KEY = os.getenv("SECRET_KEY", "django-insecure-dev-clinic-booking-saas")
DEBUG = env_bool("DEBUG", not IS_PRODUCTION)

ALLOWED_HOSTS = env_list("ALLOWED_HOSTS", "127.0.0.1,localhost,testserver")
if DEBUG:
    ALLOWED_HOSTS.extend([".ngrok-free.dev", ".ngrok.io"])

TRUST_X_FORWARDED_PROTO = env_bool("TRUST_X_FORWARDED_PROTO", False)
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https") if TRUST_X_FORWARDED_PROTO else None
USE_X_FORWARDED_HOST = env_bool("USE_X_FORWARDED_HOST", False)

SECURE_SSL_REDIRECT = env_bool("SECURE_SSL_REDIRECT", IS_PRODUCTION)
SESSION_COOKIE_SECURE = env_bool("SESSION_COOKIE_SECURE", IS_PRODUCTION)
CSRF_COOKIE_SECURE = env_bool("CSRF_COOKIE_SECURE", IS_PRODUCTION)
SECURE_HSTS_SECONDS = int(os.getenv("SECURE_HSTS_SECONDS", "31536000" if IS_PRODUCTION else "0"))
SECURE_HSTS_INCLUDE_SUBDOMAINS = env_bool("SECURE_HSTS_INCLUDE_SUBDOMAINS", False)
SECURE_HSTS_PRELOAD = env_bool("SECURE_HSTS_PRELOAD", False)
CSRF_TRUSTED_ORIGINS = env_list("CSRF_TRUSTED_ORIGINS", "")
```

Replace the auto-writing Messenger verify-token block with:

```python
MESSENGER_VERIFY_TOKEN = os.getenv("MESSENGER_VERIFY_TOKEN", "dev-messenger-verify-token" if DEBUG else "")
MESSENGER_APP_SECRET = os.getenv("MESSENGER_APP_SECRET", "")
MESSENGER_APP_ID = os.getenv("MESSENGER_APP_ID", "")
MESSENGER_SESSION_TIMEOUT_MINUTES = int(os.getenv("MESSENGER_SESSION_TIMEOUT_MINUTES", "30"))
```

- [ ] **Step 5: Update example environment and deployment docs**

Update `.env.example` to include:

```dotenv
DJANGO_ENV=production
SECRET_KEY=change-me-to-a-long-random-secret
DEBUG=0
ALLOWED_HOSTS=your-domain.com,www.your-domain.com
CSRF_TRUSTED_ORIGINS=https://your-domain.com,https://www.your-domain.com
SECURE_SSL_REDIRECT=1
SESSION_COOKIE_SECURE=1
CSRF_COOKIE_SECURE=1
SECURE_HSTS_SECONDS=31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS=0
SECURE_HSTS_PRELOAD=0
TRUST_X_FORWARDED_PROTO=1
USE_X_FORWARDED_HOST=0
MESSENGER_VERIFY_TOKEN=change-me
MESSENGER_APP_SECRET=change-me
N8N_WEBHOOK_SECRET=change-me
```

Update `DEPLOYMENT.md` with a production security checklist that includes:

```markdown
## Production Security Checklist

1. Set `DJANGO_ENV=production`, `DEBUG=0`, a strong `SECRET_KEY`, production `ALLOWED_HOSTS`, and `CSRF_TRUSTED_ORIGINS`.
2. Set `SESSION_COOKIE_SECURE=1`, `CSRF_COOKIE_SECURE=1`, `SECURE_SSL_REDIRECT=1`, and `SECURE_HSTS_SECONDS=31536000` after HTTPS is confirmed.
3. Set `MESSENGER_VERIFY_TOKEN`, `MESSENGER_APP_SECRET`, and `N8N_WEBHOOK_SECRET` before enabling Messenger/n8n routes in production.
4. Configure the reverse proxy to set `X-Forwarded-Proto https` and block direct public access to Gunicorn.
5. Run `python manage.py check --deploy` before release and treat any `clinic_security.*` error as blocking.
6. Keep `.env` out of git, rotate exposed secrets, and use secret scanning in CI.
```

- [ ] **Step 6: Run settings tests and a production deploy check**

Run:

```powershell
.\env\Scripts\python.exe -m pytest tests/test_security_checks.py -q
```

Expected: pass.

Run a deploy check with temporary secure values:

```powershell
$env:DJANGO_ENV="production"; $env:DEBUG="0"; $env:SECRET_KEY="prod-secret-key-with-enough-entropy-for-checks"; $env:ALLOWED_HOSTS="clinic.example.com"; $env:CSRF_TRUSTED_ORIGINS="https://clinic.example.com"; $env:SESSION_COOKIE_SECURE="1"; $env:CSRF_COOKIE_SECURE="1"; $env:SECURE_SSL_REDIRECT="1"; $env:SECURE_HSTS_SECONDS="31536000"; $env:N8N_WEBHOOK_SECRET="n8n-secret"; $env:MESSENGER_APP_SECRET="messenger-secret"; $env:MESSENGER_VERIFY_TOKEN="verify-token"; .\env\Scripts\python.exe manage.py check --deploy
```

Expected: no `clinic_security.*` errors.

---

### Task 3: Guest Booking Integrity

**Files:**
- Modify: `patients/models.py`
- Modify: `widget/views.py`
- Modify: `templates/widget/widget.html`
- Modify: `widget/tests.py`
- Modify: `messenger/tests.py`

- [ ] **Step 1: Add failing widget booking tests**

Append these methods to `WidgetTests` in `widget/tests.py`:

```python
    def test_widget_booking_rejects_blank_identity(self):
        tomorrow = timezone.localdate() + timedelta(days=1)
        slot = generate_slots(self.clinic, self.service, tomorrow)[0]

        response = self.client.post(
            reverse("widget:book", args=[self.clinic.slug]),
            {"service": self.service.id, "starts_at": slot["starts_at"].isoformat(), "full_name": "", "phone": ""},
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(Appointment.objects.filter(clinic=self.clinic).count(), 0)

    def test_widget_booking_rejects_short_phone(self):
        tomorrow = timezone.localdate() + timedelta(days=1)
        slot = generate_slots(self.clinic, self.service, tomorrow)[0]

        response = self.client.post(
            reverse("widget:book", args=[self.clinic.slug]),
            {"service": self.service.id, "starts_at": slot["starts_at"].isoformat(), "full_name": "Short Phone", "phone": "123"},
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(Appointment.objects.filter(clinic=self.clinic).count(), 0)

    def test_widget_booking_does_not_overwrite_existing_patient_by_phone(self):
        existing = self.clinic.patients.create(full_name="Existing Patient", phone="09123456789", email="old@example.com", notes="Original notes")
        tomorrow = timezone.localdate() + timedelta(days=1)
        slot = generate_slots(self.clinic, self.service, tomorrow)[0]

        response = self.client.post(
            reverse("widget:book", args=[self.clinic.slug]),
            {
                "service": self.service.id,
                "starts_at": slot["starts_at"].isoformat(),
                "full_name": "Attacker Longer Patient Name",
                "phone": "09123456789",
                "email": "attacker@example.com",
                "reason": "Replace notes",
            },
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        existing.refresh_from_db()
        self.assertEqual(existing.full_name, "Existing Patient")
        self.assertEqual(existing.email, "old@example.com")
        self.assertEqual(existing.notes, "Original notes")

    def test_widget_booking_ignores_tampered_source(self):
        tomorrow = timezone.localdate() + timedelta(days=1)
        slot = generate_slots(self.clinic, self.service, tomorrow)[0]

        response = self.client.post(
            reverse("widget:book", args=[self.clinic.slug]),
            {
                "service": self.service.id,
                "starts_at": slot["starts_at"].isoformat(),
                "full_name": "Source Tamper",
                "phone": "09123450000",
                "source": "staff",
            },
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        appointment = Appointment.objects.get(patient__full_name="Source Tamper")
        self.assertEqual(appointment.source, Appointment.SOURCE_CHAT_WIDGET)

    def test_widget_booking_uses_embed_source_from_query_string(self):
        tomorrow = timezone.localdate() + timedelta(days=1)
        slot = generate_slots(self.clinic, self.service, tomorrow)[0]

        response = self.client.post(
            reverse("widget:book", args=[self.clinic.slug]) + "?source=embed",
            {
                "service": self.service.id,
                "starts_at": slot["starts_at"].isoformat(),
                "full_name": "Embed Patient",
                "phone": "09123451111",
                "source": "staff",
            },
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        appointment = Appointment.objects.get(patient__full_name="Embed Patient")
        self.assertEqual(appointment.source, Appointment.SOURCE_EMBED)
```

Update `messenger/tests.py::test_ai_booking_reuses_patient_phone_and_prevents_double_booking` to assert the patient name was not overwritten:

```python
    patient.refresh_from_db()
    assert patient.full_name == "Existing Name"
```

- [ ] **Step 2: Run the new booking tests and confirm failures**

Run:

```powershell
.\env\Scripts\python.exe -m pytest widget/tests.py::WidgetTests::test_widget_booking_rejects_blank_identity widget/tests.py::WidgetTests::test_widget_booking_rejects_short_phone widget/tests.py::WidgetTests::test_widget_booking_does_not_overwrite_existing_patient_by_phone widget/tests.py::WidgetTests::test_widget_booking_ignores_tampered_source widget/tests.py::WidgetTests::test_widget_booking_uses_embed_source_from_query_string messenger/tests.py::test_ai_booking_reuses_patient_phone_and_prevents_double_booking -q
```

Expected: blank identity, source tampering, and patient overwrite assertions fail against the current code.

- [ ] **Step 3: Stop guest demographic overwrites**

In `patients/models.py`, replace `find_or_create_for_booking()` with:

```python
    @classmethod
    def find_or_create_for_booking(cls, clinic, full_name, phone, email="", notes=""):
        normalized = normalize_phone(phone)
        patient = cls.objects.filter(clinic=clinic, normalized_phone=normalized).order_by("created_at").first()
        if patient:
            return patient, False
        return cls.objects.create(clinic=clinic, full_name=full_name, phone=phone, email=email, notes=notes), True
```

- [ ] **Step 4: Validate and lock guest booking creation**

In `widget/views.py`, add imports:

```python
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import transaction

from patients.models import Patient, normalize_phone
```

Add helpers above `widget_book()`:

```python
MIN_BOOKING_PHONE_DIGITS = 7


def _public_booking_source(request):
    return Appointment.SOURCE_EMBED if request.GET.get("source") == "embed" else Appointment.SOURCE_CHAT_WIDGET


def _validate_guest_identity(full_name, phone, email):
    if not full_name:
        return "Please provide your full name."
    if len(normalize_phone(phone)) < MIN_BOOKING_PHONE_DIGITS:
        return "Please provide a valid phone number."
    if email:
        try:
            validate_email(email)
        except ValidationError:
            return "Please provide a valid email address."
    return ""
```

Change `widget_book()` POST source handling to:

```python
    if request.method == "POST":
        appointment, error = _process_guest_booking(clinic, request.POST, _public_booking_source(request))
```

Replace `_process_guest_booking()` with:

```python
def _process_guest_booking(clinic, data, source):
    full_name = (data.get("full_name") or "").strip()
    phone = (data.get("phone") or "").strip()
    email = (data.get("email") or "").strip()
    reason = (data.get("reason") or "").strip()
    identity_error = _validate_guest_identity(full_name, phone, email)
    if identity_error:
        return None, identity_error

    try:
        starts_at = datetime.fromisoformat(str(data.get("starts_at", "")))
    except (TypeError, ValueError):
        return None, "Please choose a valid appointment time."
    if timezone.is_naive(starts_at):
        starts_at = timezone.make_aware(starts_at)
    starts_at = starts_at.astimezone(dt_timezone.utc)

    try:
        service_id = data.get("service")
        with transaction.atomic():
            locked_clinic = Clinic.objects.select_for_update().get(pk=clinic.pk)
            service = get_object_or_404(locked_clinic.services.filter(is_active=True, is_archived=False), pk=service_id)
            ends_at = starts_at + timedelta(minutes=service.effective_duration())
            available = any(
                slot["starts_at"] == starts_at
                for slot in generate_slots(
                    locked_clinic,
                    service,
                    starts_at.astimezone(ZoneInfo(locked_clinic.timezone)).date(),
                )
            )
            if not available:
                return None, "That slot is no longer available. Please choose another time."
            patient, _ = Patient.find_or_create_for_booking(
                clinic=locked_clinic,
                full_name=full_name,
                phone=phone,
                email=email,
                notes=reason,
            )
            appointment = Appointment.objects.create(
                clinic=locked_clinic,
                patient=patient,
                service=service,
                starts_at=starts_at,
                ends_at=ends_at,
                status=Appointment.STATUS_CONFIRMED if locked_clinic.booking_approval_mode == Clinic.APPROVAL_AUTO else Appointment.STATUS_PENDING,
                source=source,
                reason=reason,
            )
    except ValidationError:
        return None, "That slot is no longer available. Please choose another time."

    return appointment, None
```

- [ ] **Step 5: Remove hidden source trust and preserve embed source through the form action**

In `templates/widget/widget.html`, change the booking form opening and remove the hidden `source` field:

```django
<form hx-post="{% url 'widget:book' clinic.slug %}{% if widget_source == 'embed' %}?source=embed{% endif %}" hx-target="#booking-form-container" hx-swap="innerHTML" class="space-y-3">
  {% csrf_token %}
  <input type="hidden" name="service" :value="selectedService">
```

- [ ] **Step 6: Run booking tests again**

Run:

```powershell
.\env\Scripts\python.exe -m pytest widget/tests.py messenger/tests.py::test_ai_booking_reuses_patient_phone_and_prevents_double_booking -q
```

Expected: selected widget tests and the Messenger AI patient matching test pass.

---

### Task 4: Dashboard Permission and Widget Color Safety

**Files:**
- Modify: `clinics/models.py`
- Modify: `clinics/forms.py` if needed
- Modify: `templates/widget/widget.html`
- Modify: `dashboard/views.py`
- Modify: `dashboard/tests.py`
- Modify: `widget/tests.py`
- Create: `clinics/migrations/<next>_validate_widget_accent_color.py`

- [ ] **Step 1: Add failing permission and color tests**

Append these tests to `dashboard/tests.py`:

```python
@pytest.mark.django_db
def test_staff_cannot_create_faq_directly(clinic_setup, client):
    clinic, service, owner = clinic_setup
    User = get_user_model()
    staff = User.objects.create_user(username="staff-faq@example.com", email="staff-faq@example.com", password="password123")
    ClinicMembership.objects.create(clinic=clinic, user=staff, role=ClinicMembership.ROLE_STAFF)
    client.force_login(staff)

    response = client.post(reverse("dashboard:create_faq"), {"question": "Q", "answer": "A", "is_active": "on"})

    assert response.status_code == 403
    assert clinic.faqs.count() == 0


@pytest.mark.django_db
def test_staff_cannot_edit_toggle_or_delete_faq_directly(clinic_setup, client):
    from clinics.models import ClinicFAQ

    clinic, service, owner = clinic_setup
    faq = ClinicFAQ.objects.create(clinic=clinic, question="Question", answer="Answer")
    User = get_user_model()
    staff = User.objects.create_user(username="staff-faq-actions@example.com", email="staff-faq-actions@example.com", password="password123")
    ClinicMembership.objects.create(clinic=clinic, user=staff, role=ClinicMembership.ROLE_STAFF)
    client.force_login(staff)

    edit = client.post(reverse("dashboard:edit_faq", args=[faq.id]), {"question": "Changed", "answer": "Changed", "is_active": "on"})
    toggle = client.post(reverse("dashboard:toggle_faq", args=[faq.id]))
    delete = client.post(reverse("dashboard:delete_faq", args=[faq.id]))

    assert edit.status_code == 403
    assert toggle.status_code == 403
    assert delete.status_code == 403
    faq.refresh_from_db()
    assert faq.question == "Question"
    assert faq.is_active is True


@pytest.mark.django_db
def test_widget_settings_rejects_invalid_accent_color(clinic_setup):
    from clinics.forms import WidgetSettingsForm

    clinic, service, owner = clinic_setup
    form = WidgetSettingsForm(
        data={
            "widget_accent_color": "\";alert(1)//",
            "widget_welcome_message": "Welcome",
            "widget_behavior_instructions": "Guide booking",
            "show_reason_field": "on",
        },
        instance=clinic,
    )

    assert not form.is_valid()
    assert "widget_accent_color" in form.errors
```

Append this test to `WidgetTests` in `widget/tests.py`:

```python
    def test_widget_accent_color_is_escaped_in_script(self):
        dangerous = '";alert(1)//'
        Clinic.objects.filter(pk=self.clinic.pk).update(widget_accent_color=dangerous)

        response = self.client.get(reverse("widget:home", args=[self.clinic.slug]))
        content = response.content.decode()

        self.assertNotIn(f"accentColor: '{dangerous}'", content)
        self.assertIn('accentColor:', content)
```

- [ ] **Step 2: Run permission and color tests and confirm failures**

Run:

```powershell
.\env\Scripts\python.exe -m pytest dashboard/tests.py::test_staff_cannot_create_faq_directly dashboard/tests.py::test_staff_cannot_edit_toggle_or_delete_faq_directly dashboard/tests.py::test_widget_settings_rejects_invalid_accent_color widget/tests.py::WidgetTests::test_widget_accent_color_is_escaped_in_script -q
```

Expected: FAQ permission and invalid color tests fail against the current code.

- [ ] **Step 3: Add model-level accent color validation**

In `clinics/models.py`, add the import:

```python
from django.core.validators import RegexValidator
```

Add a validator near the top:

```python
hex_color_validator = RegexValidator(
    regex=r"^#[0-9A-Fa-f]{6}$",
    message="Enter a valid hex color such as #0891b2.",
)
```

Change the `Clinic.widget_accent_color` field to:

```python
    widget_accent_color = models.CharField(max_length=7, default="#0891b2", validators=[hex_color_validator])
```

- [ ] **Step 4: Escape widget accent color in template JavaScript**

In `templates/widget/widget.html`, change the Alpine data value to:

```django
      accentColor: '{{ clinic.widget_accent_color|default:"#0891b2"|escapejs }}',
```

- [ ] **Step 5: Enforce FAQ settings permission on direct routes**

In `dashboard/views.py`, add a helper near `assistant_settings()`:

```python
def _require_settings_permission(user):
    membership = get_active_membership(user)
    if not user_can_manage_settings(membership):
        raise PermissionDenied
```

Replace the repeated permission block in `assistant_settings()` with:

```python
    _require_settings_permission(request.user)
```

Add the same line immediately after `_clinic_or_redirect(request)` in `create_faq()`, `edit_faq()`, `toggle_faq()`, and `delete_faq()`:

```python
    _require_settings_permission(request.user)
```

- [ ] **Step 6: Create and apply the color validation migration**

Run:

```powershell
.\env\Scripts\python.exe manage.py makemigrations clinics
.\env\Scripts\python.exe manage.py migrate
```

Expected: a migration alters `Clinic.widget_accent_color`; migrations apply successfully.

- [ ] **Step 7: Run permission and color tests again**

Run:

```powershell
.\env\Scripts\python.exe -m pytest dashboard/tests.py::test_staff_cannot_create_faq_directly dashboard/tests.py::test_staff_cannot_edit_toggle_or_delete_faq_directly dashboard/tests.py::test_widget_settings_rejects_invalid_accent_color widget/tests.py::WidgetTests::test_widget_accent_color_is_escaped_in_script -q
```

Expected: all selected tests pass.

---

### Task 5: Final Verification and Security Notes

**Files:**
- Modify: `TASKS.md` only if the project uses it for current security work tracking.
- No code files unless verification exposes a defect.

- [ ] **Step 1: Run targeted security test groups**

Run:

```powershell
.\env\Scripts\python.exe -m pytest messenger/tests.py widget/tests.py dashboard/tests.py tests/test_security_checks.py -q
```

Expected: all selected tests pass.

- [ ] **Step 2: Run Django checks**

Run:

```powershell
.\env\Scripts\python.exe manage.py check
```

Expected: no errors.

Run the production deploy check with temporary secure env vars:

```powershell
$env:DJANGO_ENV="production"; $env:DEBUG="0"; $env:SECRET_KEY="prod-secret-key-with-enough-entropy-for-checks"; $env:ALLOWED_HOSTS="clinic.example.com"; $env:CSRF_TRUSTED_ORIGINS="https://clinic.example.com"; $env:SESSION_COOKIE_SECURE="1"; $env:CSRF_COOKIE_SECURE="1"; $env:SECURE_SSL_REDIRECT="1"; $env:SECURE_HSTS_SECONDS="31536000"; $env:N8N_WEBHOOK_SECRET="n8n-secret"; $env:MESSENGER_APP_SECRET="messenger-secret"; $env:MESSENGER_VERIFY_TOKEN="verify-token"; .\env\Scripts\python.exe manage.py check --deploy
```

Expected: no `clinic_security.*` errors. Some built-in Django warnings may still require deployment-specific decisions such as HSTS preload or proxy configuration; record any remaining warning exactly.

- [ ] **Step 3: Check tracked secret risk without printing secret values**

Run:

```powershell
git ls-files --error-unmatch .env
```

Expected: if `.env` is tracked, report it as a blocking operational risk and recommend `git rm --cached .env` plus rotation of any exposed secrets. Do not print `.env` contents.

- [ ] **Step 4: Inspect changed files**

Run:

```powershell
git diff -- config/settings.py config/security_checks.py tests/test_security_checks.py messenger/views.py messenger/messenger_api.py messenger/tests.py patients/models.py widget/views.py widget/tests.py templates/widget/widget.html clinics/models.py clinics/forms.py dashboard/views.py dashboard/tests.py .env.example DEPLOYMENT.md docs/superpowers/specs/2026-05-31-production-security-hardening-design.md docs/superpowers/plans/2026-05-31-production-security-hardening-implementation-plan.md
```

Expected: diff contains only the security hardening changes from this plan.

- [ ] **Step 5: Report completion**

Final report must include:

- The three-agent security review themes.
- Files changed.
- Tests and checks run with pass/fail results.
- Whether `.env` is tracked and what must be rotated or removed from git.
- Any remaining deployment-only security work the code cannot enforce.
