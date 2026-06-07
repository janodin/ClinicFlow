# Reset Password Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a secure login-page-only password reset flow for clinic dashboard users.

**Architecture:** Use Django's built-in password reset class-based views with KliniAssist-specific forms and templates. Keep patients guest-only and add no new database models or migrations.

**Tech Stack:** Django 5.2, custom `accounts.User`, Django templates, Tailwind CSS, `cf-*` design-system classes, pytest.

**Commit Rule:** Do not commit unless the user explicitly requests a commit. Use git diff/status checkpoints instead.

---

## File Structure

- Modify `accounts/forms.py`: add styled password reset and set-password forms that reuse the existing `cf-input` class.
- Modify `accounts/views.py`: add small wrapper classes around Django's password reset views.
- Modify `accounts/urls.py`: add reset request, done, confirm, and complete routes under `accounts/`.
- Modify `accounts/tests.py`: add behavior tests for login-only entry point, generic reset request behavior, valid token reset, and token reuse rejection.
- Modify `tests/test_design_system.py`: add a template contract test for the new auth reset pages and login-only reset entry point.
- Modify `templates/accounts/login.html`: add the only visible reset-password entry link.
- Leave `templates/accounts/signup.html` unchanged except for tests asserting it has no reset link.
- Create `templates/accounts/password_reset.html`: request email page.
- Create `templates/accounts/password_reset_done.html`: generic check-email page.
- Create `templates/accounts/password_reset_confirm.html`: new password form and invalid-token state.
- Create `templates/accounts/password_reset_complete.html`: success page.
- Create `templates/accounts/password_reset_email.html`: plain-text reset email body with KliniAssist wording.
- Create `templates/accounts/password_reset_subject.txt`: reset email subject.

---

### Task 1: Add Failing Password Reset Behavior Tests

**Files:**
- Modify: `accounts/tests.py`
- Modify: `tests/test_design_system.py`

- [ ] **Step 1: Add account reset tests**

In `accounts/tests.py`, add `import re` near the top and add `from django.core import mail` with the Django imports:

```python
import re
from decimal import Decimal
from datetime import time

import pytest
from django.contrib.auth import get_user_model
from django.core import mail
from django.urls import reverse
```

Add this helper after `_onboarding_post_data()`:

```python
def _password_reset_path_from_email(message):
    match = re.search(r"http://testserver(?P<path>/accounts/reset/[^\s]+)", message.body)
    assert match, message.body
    return match.group("path")
```

Add these tests after the existing signup tests and before the onboarding tests:

```python
@pytest.mark.django_db
def test_login_page_links_to_password_reset(client):
    response = client.get(reverse("accounts:login"))

    assert response.status_code == 200
    assert reverse("accounts:password_reset").encode() in response.content
    assert b"Forgot password?" in response.content


@pytest.mark.django_db
def test_signup_page_does_not_link_to_password_reset(client):
    response = client.get(reverse("accounts:signup"))

    assert response.status_code == 200
    assert reverse("accounts:password_reset").encode() not in response.content
    assert b"Forgot password?" not in response.content


@pytest.mark.django_db
def test_password_reset_request_sends_email_for_existing_dashboard_user(client, settings):
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    mail.outbox = []
    User = get_user_model()
    User.objects.create_user(
        username="owner@example.com",
        email="owner@example.com",
        password="OldStrongPass!2026",
    )

    response = client.post(reverse("accounts:password_reset"), {"email": "owner@example.com"})

    assert response.status_code == 302
    assert response.url == reverse("accounts:password_reset_done")
    assert len(mail.outbox) == 1
    assert "Reset your KliniAssist password" in mail.outbox[0].subject
    assert "/accounts/reset/" in mail.outbox[0].body


@pytest.mark.django_db
def test_password_reset_request_for_unknown_email_is_generic(client, settings):
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    mail.outbox = []

    response = client.post(reverse("accounts:password_reset"), {"email": "unknown@example.com"})

    assert response.status_code == 302
    assert response.url == reverse("accounts:password_reset_done")
    assert len(mail.outbox) == 0


@pytest.mark.django_db
def test_password_reset_confirm_changes_password(client, settings):
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    mail.outbox = []
    User = get_user_model()
    user = User.objects.create_user(
        username="owner@example.com",
        email="owner@example.com",
        password="OldStrongPass!2026",
    )
    client.post(reverse("accounts:password_reset"), {"email": "owner@example.com"})
    reset_path = _password_reset_path_from_email(mail.outbox[0])

    response = client.get(reset_path)
    assert response.status_code == 302
    confirm_path = response["Location"]
    response = client.post(
        confirm_path,
        {
            "new_password1": "NewStrongPass!2026",
            "new_password2": "NewStrongPass!2026",
        },
    )

    assert response.status_code == 302
    assert response.url == reverse("accounts:password_reset_complete")
    user.refresh_from_db()
    assert user.check_password("NewStrongPass!2026")
    assert client.login(username="owner@example.com", password="NewStrongPass!2026")


@pytest.mark.django_db
def test_password_reset_token_cannot_be_reused(client, settings):
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    mail.outbox = []
    User = get_user_model()
    User.objects.create_user(
        username="owner@example.com",
        email="owner@example.com",
        password="OldStrongPass!2026",
    )
    client.post(reverse("accounts:password_reset"), {"email": "owner@example.com"})
    reset_path = _password_reset_path_from_email(mail.outbox[0])
    confirm_path = client.get(reset_path)["Location"]
    client.post(
        confirm_path,
        {
            "new_password1": "NewStrongPass!2026",
            "new_password2": "NewStrongPass!2026",
        },
    )

    response = client.get(reset_path)

    assert response.status_code == 200
    assert b"This password reset link is invalid or has already been used." in response.content
```

- [ ] **Step 2: Add design-system template contract test**

In `tests/test_design_system.py`, add this test after `test_auth_public_and_widget_mobile_contracts`:

```python
def test_password_reset_templates_follow_auth_shell_contract():
    login = source_text("templates/accounts/login.html")
    signup = source_text("templates/accounts/signup.html")
    reset_templates = [
        "templates/accounts/password_reset.html",
        "templates/accounts/password_reset_done.html",
        "templates/accounts/password_reset_confirm.html",
        "templates/accounts/password_reset_complete.html",
    ]

    assert "{% url 'accounts:password_reset' %}" in login
    assert "{% url 'accounts:password_reset' %}" not in signup

    for relative_path in reset_templates:
        template = source_text(relative_path)
        assert "{% extends \"base.html\" %}" in template
        assert "cf-auth-panel" in template
        assert "cf-card" in template
        assert "cf-btn cf-btn-primary" in template
```

- [ ] **Step 3: Run account tests to verify failure**

Run:

```powershell
.\env\Scripts\python.exe -m pytest accounts/tests.py -q
```

Expected: fails with `NoReverseMatch` for `accounts:password_reset` because routes do not exist yet.

- [ ] **Step 4: Run the new design test to verify failure**

Run:

```powershell
.\env\Scripts\python.exe -m pytest tests/test_design_system.py::test_password_reset_templates_follow_auth_shell_contract -q
```

Expected: fails because the login link and reset templates do not exist yet.

- [ ] **Step 5: Checkpoint diff**

Run:

```powershell
git diff -- accounts/tests.py tests/test_design_system.py
```

Expected: diff only contains the new tests and helper/import additions.

---

### Task 2: Add Password Reset Forms, Views, And Routes

**Files:**
- Modify: `accounts/forms.py`
- Modify: `accounts/views.py`
- Modify: `accounts/urls.py`

- [ ] **Step 1: Add styled reset forms**

In `accounts/forms.py`, change the auth form import to include Django's reset forms:

```python
from django.contrib.auth.forms import AuthenticationForm, PasswordResetForm, SetPasswordForm
```

Add these classes after `LoginForm` and before `FirstRunOnboardingForm`:

```python
class AppPasswordResetForm(PasswordResetForm):
    email = forms.EmailField(
        label="Email address",
        widget=forms.EmailInput(
            attrs={
                "class": _INPUT,
                "placeholder": "you@clinic.com",
                "autocomplete": "email",
            }
        ),
    )


class AppSetPasswordForm(SetPasswordForm):
    new_password1 = forms.CharField(
        label="New password",
        strip=False,
        widget=forms.PasswordInput(
            attrs={
                "class": _INPUT,
                "placeholder": "Create a new password",
                "autocomplete": "new-password",
            }
        ),
    )
    new_password2 = forms.CharField(
        label="Confirm new password",
        strip=False,
        widget=forms.PasswordInput(
            attrs={
                "class": _INPUT,
                "placeholder": "Confirm your new password",
                "autocomplete": "new-password",
            }
        ),
    )
```

- [ ] **Step 2: Add password reset views**

In `accounts/views.py`, change the auth views import to:

```python
from django.contrib.auth.views import (
    LoginView,
    LogoutView,
    PasswordResetCompleteView,
    PasswordResetConfirmView,
    PasswordResetDoneView,
    PasswordResetView,
)
```

Add this import with the other Django imports:

```python
from django.urls import reverse_lazy
```

Change the local forms import to:

```python
from .forms import AppPasswordResetForm, AppSetPasswordForm, FirstRunOnboardingForm, LoginForm, SignUpForm
```

Add these classes after `AppLogoutView` and before `signup`:

```python
class AppPasswordResetView(PasswordResetView):
    template_name = "accounts/password_reset.html"
    form_class = AppPasswordResetForm
    email_template_name = "accounts/password_reset_email.html"
    subject_template_name = "accounts/password_reset_subject.txt"
    success_url = reverse_lazy("accounts:password_reset_done")


class AppPasswordResetDoneView(PasswordResetDoneView):
    template_name = "accounts/password_reset_done.html"


class AppPasswordResetConfirmView(PasswordResetConfirmView):
    template_name = "accounts/password_reset_confirm.html"
    form_class = AppSetPasswordForm
    success_url = reverse_lazy("accounts:password_reset_complete")


class AppPasswordResetCompleteView(PasswordResetCompleteView):
    template_name = "accounts/password_reset_complete.html"
```

- [ ] **Step 3: Add reset routes**

In `accounts/urls.py`, replace `urlpatterns` with:

```python
urlpatterns = [
    path("signup/", views.signup, name="signup"),
    path("onboarding/", views.onboarding, name="onboarding"),
    path("login/", views.EmailLoginView.as_view(), name="login"),
    path("logout/", views.AppLogoutView.as_view(), name="logout"),
    path("password-reset/", views.AppPasswordResetView.as_view(), name="password_reset"),
    path("password-reset/done/", views.AppPasswordResetDoneView.as_view(), name="password_reset_done"),
    path("reset/<uidb64>/<token>/", views.AppPasswordResetConfirmView.as_view(), name="password_reset_confirm"),
    path("reset/done/", views.AppPasswordResetCompleteView.as_view(), name="password_reset_complete"),
]
```

- [ ] **Step 4: Run tests to verify the next failure**

Run:

```powershell
.\env\Scripts\python.exe -m pytest accounts/tests.py -q
```

Expected: failures now move from `NoReverseMatch` to missing template errors and/or missing login-page link.

- [ ] **Step 5: Checkpoint diff**

Run:

```powershell
git diff -- accounts/forms.py accounts/views.py accounts/urls.py
```

Expected: diff only contains styled forms, reset view wrappers, and reset routes.

---

### Task 3: Add Login Entry Point, Reset Pages, And Email Templates

**Files:**
- Modify: `templates/accounts/login.html`
- Create: `templates/accounts/password_reset.html`
- Create: `templates/accounts/password_reset_done.html`
- Create: `templates/accounts/password_reset_confirm.html`
- Create: `templates/accounts/password_reset_complete.html`
- Create: `templates/accounts/password_reset_email.html`
- Create: `templates/accounts/password_reset_subject.txt`

- [ ] **Step 1: Add the login-page-only reset link**

In `templates/accounts/login.html`, replace the password field block:

```html
        <div>
          <label for="{{ form.password.id_for_label }}" class="cf-label">{{ form.password.label }}</label>
          {{ form.password }}
        </div>
```

with:

```html
        <div>
          <div class="flex items-center justify-between gap-3">
            <label for="{{ form.password.id_for_label }}" class="cf-label">{{ form.password.label }}</label>
            <a class="text-xs font-bold text-[var(--cf-brand-strong)] transition-colors hover:text-[var(--cf-dashboard-dark)]" href="{% url 'accounts:password_reset' %}">Forgot password?</a>
          </div>
          {{ form.password }}
        </div>
```

Do not add any reset-password link to `templates/accounts/signup.html`.

- [ ] **Step 2: Create the reset request page**

Create `templates/accounts/password_reset.html`:

```html
{% extends "base.html" %}
{% block title %}Reset password{% endblock %}
{% block body %}
<div class="cf-auth-panel flex min-h-dvh items-start sm:items-center justify-center px-4 py-6 sm:py-8">
  <div class="w-full max-w-md">
    <div class="mb-8 text-center">
      <div class="inline-flex items-center gap-3 text-xl font-black text-[var(--cf-ink)]">
        <span class="grid h-10 w-10 place-items-center rounded-2xl bg-[var(--cf-brand-soft)] text-[var(--cf-brand)]">
          <i data-lucide="activity" class="h-5 w-5"></i>
        </span>
        KliniAssist
      </div>
      <h1 class="mt-6 text-3xl font-light leading-tight text-[var(--cf-ink)]">Reset your password.</h1>
      <p class="mt-3 text-base leading-7 text-[var(--cf-muted)]">Enter your dashboard email and we will send a secure reset link.</p>
    </div>

    <div class="cf-card bg-[var(--cf-bg)] p-8">
      <h2 class="text-xl font-black text-[var(--cf-ink)]">Password reset</h2>
      <p class="mt-1.5 text-sm text-[var(--cf-muted)]">If the email matches an active dashboard account, a reset link will be sent.</p>

      <form method="post" class="mt-6 space-y-4">
        {% csrf_token %}
        <div>
          <label for="{{ form.email.id_for_label }}" class="cf-label">{{ form.email.label }}</label>
          {{ form.email }}
          {% if form.email.errors %}
            <p class="mt-1 text-xs text-[var(--cf-status-cancelled-text)]">{{ form.email.errors.0 }}</p>
          {% endif %}
        </div>
        <button class="cf-btn cf-btn-primary min-h-11 w-full"><i data-lucide="mail" class="h-4 w-4"></i>Send Reset Link</button>
        <p class="text-center text-sm text-[var(--cf-muted)]">
          Remember your password?
          <a class="font-bold text-[var(--cf-brand-strong)] transition-colors hover:text-[var(--cf-dashboard-dark)]" href="{% url 'accounts:login' %}">Sign in</a>
        </p>
      </form>
    </div>

    <p class="mt-6 text-center text-xs text-[var(--cf-muted)]">Appointment-first clinic SaaS</p>
  </div>
</div>
{% endblock %}
```

- [ ] **Step 3: Create the reset done page**

Create `templates/accounts/password_reset_done.html`:

```html
{% extends "base.html" %}
{% block title %}Check your email{% endblock %}
{% block body %}
<div class="cf-auth-panel flex min-h-dvh items-start sm:items-center justify-center px-4 py-6 sm:py-8">
  <div class="w-full max-w-md">
    <div class="mb-8 text-center">
      <div class="inline-flex items-center gap-3 text-xl font-black text-[var(--cf-ink)]">
        <span class="grid h-10 w-10 place-items-center rounded-2xl bg-[var(--cf-brand-soft)] text-[var(--cf-brand)]">
          <i data-lucide="activity" class="h-5 w-5"></i>
        </span>
        KliniAssist
      </div>
      <h1 class="mt-6 text-3xl font-light leading-tight text-[var(--cf-ink)]">Check your email.</h1>
      <p class="mt-3 text-base leading-7 text-[var(--cf-muted)]">If the email matches an active dashboard account, you will receive a secure password reset link shortly.</p>
    </div>

    <div class="cf-card bg-[var(--cf-bg)] p-8 text-center">
      <div class="mx-auto grid h-12 w-12 place-items-center rounded-2xl bg-[var(--cf-brand-soft)] text-[var(--cf-brand)]">
        <i data-lucide="mail-check" class="h-6 w-6"></i>
      </div>
      <h2 class="mt-4 text-xl font-black text-[var(--cf-ink)]">Reset link sent if eligible</h2>
      <p class="mt-2 text-sm leading-6 text-[var(--cf-muted)]">For security, we show this same message whether or not an account exists for that email.</p>
      <a class="cf-btn cf-btn-primary mt-6 min-h-11 w-full" href="{% url 'accounts:login' %}"><i data-lucide="log-in" class="h-4 w-4"></i>Back to Sign In</a>
    </div>

    <p class="mt-6 text-center text-xs text-[var(--cf-muted)]">Appointment-first clinic SaaS</p>
  </div>
</div>
{% endblock %}
```

- [ ] **Step 4: Create the reset confirm page**

Create `templates/accounts/password_reset_confirm.html`:

```html
{% extends "base.html" %}
{% block title %}Set new password{% endblock %}
{% block body %}
<div class="cf-auth-panel flex min-h-dvh items-start sm:items-center justify-center px-4 py-6 sm:py-8">
  <div class="w-full max-w-md">
    <div class="mb-8 text-center">
      <div class="inline-flex items-center gap-3 text-xl font-black text-[var(--cf-ink)]">
        <span class="grid h-10 w-10 place-items-center rounded-2xl bg-[var(--cf-brand-soft)] text-[var(--cf-brand)]">
          <i data-lucide="activity" class="h-5 w-5"></i>
        </span>
        KliniAssist
      </div>
      <h1 class="mt-6 text-3xl font-light leading-tight text-[var(--cf-ink)]">Set a new password.</h1>
      <p class="mt-3 text-base leading-7 text-[var(--cf-muted)]">Choose a strong password for your clinic dashboard account.</p>
    </div>

    <div class="cf-card bg-[var(--cf-bg)] p-8">
      {% if validlink %}
        <h2 class="text-xl font-black text-[var(--cf-ink)]">New password</h2>
        <p class="mt-1.5 text-sm text-[var(--cf-muted)]">Enter and confirm your new password.</p>

        <form method="post" class="mt-6 space-y-4">
          {% csrf_token %}
          {% if form.non_field_errors %}
            <div class="rounded-[var(--cf-radius-md)] bg-[var(--cf-status-cancelled-bg)] p-3 text-sm text-[var(--cf-status-cancelled-text)]">
              {{ form.non_field_errors.0 }}
            </div>
          {% endif %}
          <div>
            <label for="{{ form.new_password1.id_for_label }}" class="cf-label">{{ form.new_password1.label }}</label>
            {{ form.new_password1 }}
            {% if form.new_password1.errors %}
              <p class="mt-1 text-xs text-[var(--cf-status-cancelled-text)]">{{ form.new_password1.errors.0 }}</p>
            {% endif %}
          </div>
          <div>
            <label for="{{ form.new_password2.id_for_label }}" class="cf-label">{{ form.new_password2.label }}</label>
            {{ form.new_password2 }}
            {% if form.new_password2.errors %}
              <p class="mt-1 text-xs text-[var(--cf-status-cancelled-text)]">{{ form.new_password2.errors.0 }}</p>
            {% endif %}
          </div>
          <button class="cf-btn cf-btn-primary min-h-11 w-full"><i data-lucide="key-round" class="h-4 w-4"></i>Update Password</button>
        </form>
      {% else %}
        <div class="text-center">
          <div class="mx-auto grid h-12 w-12 place-items-center rounded-2xl bg-[var(--cf-status-cancelled-bg)] text-[var(--cf-status-cancelled-text)]">
            <i data-lucide="triangle-alert" class="h-6 w-6"></i>
          </div>
          <h2 class="mt-4 text-xl font-black text-[var(--cf-ink)]">Reset link unavailable</h2>
          <p class="mt-2 text-sm leading-6 text-[var(--cf-muted)]">This password reset link is invalid or has already been used.</p>
          <a class="cf-btn cf-btn-primary mt-6 min-h-11 w-full" href="{% url 'accounts:password_reset' %}"><i data-lucide="mail" class="h-4 w-4"></i>Request New Link</a>
        </div>
      {% endif %}
    </div>

    <p class="mt-6 text-center text-xs text-[var(--cf-muted)]">Appointment-first clinic SaaS</p>
  </div>
</div>
{% endblock %}
```

- [ ] **Step 5: Create the reset complete page**

Create `templates/accounts/password_reset_complete.html`:

```html
{% extends "base.html" %}
{% block title %}Password updated{% endblock %}
{% block body %}
<div class="cf-auth-panel flex min-h-dvh items-start sm:items-center justify-center px-4 py-6 sm:py-8">
  <div class="w-full max-w-md">
    <div class="mb-8 text-center">
      <div class="inline-flex items-center gap-3 text-xl font-black text-[var(--cf-ink)]">
        <span class="grid h-10 w-10 place-items-center rounded-2xl bg-[var(--cf-brand-soft)] text-[var(--cf-brand)]">
          <i data-lucide="activity" class="h-5 w-5"></i>
        </span>
        KliniAssist
      </div>
      <h1 class="mt-6 text-3xl font-light leading-tight text-[var(--cf-ink)]">Password updated.</h1>
      <p class="mt-3 text-base leading-7 text-[var(--cf-muted)]">You can now sign in to your clinic dashboard with your new password.</p>
    </div>

    <div class="cf-card bg-[var(--cf-bg)] p-8 text-center">
      <div class="mx-auto grid h-12 w-12 place-items-center rounded-2xl bg-[var(--cf-brand-soft)] text-[var(--cf-brand)]">
        <i data-lucide="check" class="h-6 w-6"></i>
      </div>
      <h2 class="mt-4 text-xl font-black text-[var(--cf-ink)]">Your password has been changed</h2>
      <p class="mt-2 text-sm leading-6 text-[var(--cf-muted)]">Use the new password the next time you access KliniAssist.</p>
      <a class="cf-btn cf-btn-primary mt-6 min-h-11 w-full" href="{% url 'accounts:login' %}"><i data-lucide="log-in" class="h-4 w-4"></i>Sign In</a>
    </div>

    <p class="mt-6 text-center text-xs text-[var(--cf-muted)]">Appointment-first clinic SaaS</p>
  </div>
</div>
{% endblock %}
```

- [ ] **Step 6: Create the reset email templates**

Create `templates/accounts/password_reset_email.html`:

```django
You're receiving this email because a password reset was requested for your KliniAssist dashboard account.

Open this secure link to choose a new password:
{{ protocol }}://{{ domain }}{% url 'accounts:password_reset_confirm' uidb64=uid token=token %}

If you did not request this reset, you can ignore this email.

KliniAssist
```

Create `templates/accounts/password_reset_subject.txt`:

```text
Reset your KliniAssist password
```

- [ ] **Step 7: Run account tests**

Run:

```powershell
.\env\Scripts\python.exe -m pytest accounts/tests.py -q
```

Expected: account tests pass. If a password strength assertion fails, keep the test password strong and do not weaken password validators.

- [ ] **Step 8: Run targeted design tests**

Run:

```powershell
.\env\Scripts\python.exe -m pytest tests/test_design_system.py::test_password_reset_templates_follow_auth_shell_contract tests/test_design_system.py::test_labeled_cf_buttons_include_supplemental_lucide_icons tests/test_design_system.py::test_public_auth_and_widget_button_labels_preserve_original_casing tests/test_design_system.py::test_auth_public_and_widget_mobile_contracts -q
```

Expected: selected design-system tests pass.

- [ ] **Step 9: Checkpoint diff**

Run:

```powershell
git diff -- templates/accounts/login.html templates/accounts/password_reset.html templates/accounts/password_reset_done.html templates/accounts/password_reset_confirm.html templates/accounts/password_reset_complete.html templates/accounts/password_reset_email.html templates/accounts/password_reset_subject.txt
```

Expected: diff shows only the login reset link and new reset/email templates. `templates/accounts/signup.html` should not appear in this diff.

---

### Task 4: Final Verification

**Files:**
- Verify: `accounts/tests.py`
- Verify: `tests/test_design_system.py`
- Verify: Django project configuration

- [ ] **Step 1: Run all account tests**

Run:

```powershell
.\env\Scripts\python.exe -m pytest accounts/tests.py -q
```

Expected: all account tests pass.

- [ ] **Step 2: Run relevant design-system tests**

Run:

```powershell
.\env\Scripts\python.exe -m pytest tests/test_design_system.py::test_visible_brand_copy_uses_kliniassist tests/test_design_system.py::test_password_reset_templates_follow_auth_shell_contract tests/test_design_system.py::test_labeled_cf_buttons_include_supplemental_lucide_icons tests/test_design_system.py::test_public_auth_and_widget_button_labels_preserve_original_casing tests/test_design_system.py::test_auth_public_and_widget_mobile_contracts -q
```

Expected: selected design-system tests pass.

- [ ] **Step 3: Run Django system check**

Run:

```powershell
.\env\Scripts\python.exe manage.py check
```

Expected: `System check identified no issues`.

- [ ] **Step 4: Inspect final diff**

Run:

```powershell
git diff -- accounts/forms.py accounts/views.py accounts/urls.py accounts/tests.py tests/test_design_system.py templates/accounts/login.html templates/accounts/password_reset.html templates/accounts/password_reset_done.html templates/accounts/password_reset_confirm.html templates/accounts/password_reset_complete.html templates/accounts/password_reset_email.html templates/accounts/password_reset_subject.txt docs/superpowers/specs/2026-06-06-reset-password-design.md docs/superpowers/plans/2026-06-06-reset-password-implementation-plan.md
```

Expected: diff is limited to password reset implementation, tests, and approved planning documents.

- [ ] **Step 5: Confirm no schema work is needed**

Do not run `makemigrations` because this plan does not change Django models. If implementation changes models unexpectedly, stop and revise the plan before continuing.

---

## Spec Coverage Review

- Login-page-only entry point: Task 1 and Task 3 test and implement the login link; signup remains unchanged.
- Django built-in reset views: Task 2 implements `PasswordResetView`, `PasswordResetDoneView`, `PasswordResetConfirmView`, and `PasswordResetCompleteView` wrappers.
- Styled templates: Task 3 creates reset pages using `cf-auth-panel`, `cf-card`, `cf-input`, and `cf-btn cf-btn-primary`.
- KliniAssist reset email: Task 3 creates subject and body templates.
- Non-enumerating request behavior: Task 1 tests both existing and unknown email submissions.
- Valid token reset and token reuse rejection: Task 1 tests both behaviors.
- No patient portal, SMS reset, or custom token model: no task adds these.
