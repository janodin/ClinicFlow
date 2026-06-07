# Profile Password Change Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let authenticated dashboard users change their password from `My Profile` by entering their current password and a validated new password.

**Architecture:** Use Django's built-in `PasswordChangeForm` wrapped in an app-specific form class for design-system styling. Handle the POST in the existing `dashboard.profile` view, call `update_session_auth_hash()` after saving, and render the form inside the existing profile page.

**Tech Stack:** Django, django.contrib.auth forms/session auth hash, Django templates, Tailwind utility classes, pytest.

---

## File Structure

- Modify `accounts/forms.py`: import `PasswordChangeForm` and add `AppPasswordChangeForm` with `cf-input` styling and password autocomplete attributes.
- Modify `accounts/tests.py`: add a focused form styling test for the new form wrapper.
- Modify `dashboard/views.py`: import `update_session_auth_hash` and `AppPasswordChangeForm`; update `profile()` to process password-change POSTs.
- Modify `dashboard/tests.py`: add profile password-change behavior tests for success, wrong current password, and mismatched new password.
- Modify `templates/dashboard/profile.html`: add a password-change card below the read-only profile details.
- Modify `tests/test_design_system.py`: add a static contract test that the profile page uses the canonical card/button/error classes for password change.

No URL, model, migration, or patient-account changes are needed.

### Task 1: Add AppPasswordChangeForm

**Files:**
- Modify: `accounts/tests.py`
- Modify: `accounts/forms.py`

- [ ] **Step 1: Write the failing form styling test**

Append this test near the existing password reset tests in `accounts/tests.py`:

```python
@pytest.mark.django_db
def test_password_change_form_uses_design_system_classes():
    from accounts.forms import AppPasswordChangeForm

    user = get_user_model().objects.create_user(
        username="owner@example.com",
        email="owner@example.com",
        password="OldStrongPass!2026",
    )

    form = AppPasswordChangeForm(user)

    assert form.fields["old_password"].widget.attrs["class"] == "cf-input"
    assert form.fields["old_password"].widget.attrs["autocomplete"] == "current-password"
    assert form.fields["new_password1"].widget.attrs["class"] == "cf-input"
    assert form.fields["new_password1"].widget.attrs["autocomplete"] == "new-password"
    assert form.fields["new_password2"].widget.attrs["class"] == "cf-input"
    assert form.fields["new_password2"].widget.attrs["autocomplete"] == "new-password"
```

- [ ] **Step 2: Run the test to verify RED**

Run: `.\env\Scripts\python.exe -m pytest accounts/tests.py::test_password_change_form_uses_design_system_classes -q`

Expected: FAIL because `accounts.forms.AppPasswordChangeForm` does not exist yet.

- [ ] **Step 3: Add the minimal form implementation**

In `accounts/forms.py`, change the auth forms import to:

```python
from django.contrib.auth.forms import AuthenticationForm, PasswordChangeForm, PasswordResetForm, SetPasswordForm
```

Add this class after `AppSetPasswordForm`:

```python
class AppPasswordChangeForm(PasswordChangeForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["old_password"].label = "Current password"
        self.fields["old_password"].widget.attrs.update(
            {
                "class": _INPUT,
                "placeholder": "Enter your current password",
                "autocomplete": "current-password",
            }
        )
        self.fields["new_password1"].label = "New password"
        self.fields["new_password1"].widget.attrs.update(
            {
                "class": _INPUT,
                "placeholder": "Create a new password",
                "autocomplete": "new-password",
            }
        )
        self.fields["new_password2"].label = "Confirm new password"
        self.fields["new_password2"].widget.attrs.update(
            {
                "class": _INPUT,
                "placeholder": "Confirm your new password",
                "autocomplete": "new-password",
            }
        )
```

- [ ] **Step 4: Run the test to verify GREEN**

Run: `.\env\Scripts\python.exe -m pytest accounts/tests.py::test_password_change_form_uses_design_system_classes -q`

Expected: PASS.

### Task 2: Add Profile Password-Change Behavior

**Files:**
- Modify: `dashboard/tests.py`
- Modify: `tests/test_design_system.py`
- Modify: `dashboard/views.py`
- Modify: `templates/dashboard/profile.html`

- [ ] **Step 1: Write failing dashboard behavior tests**

Append these tests near other profile/dashboard tests in `dashboard/tests.py`:

```python
@pytest.mark.django_db
def test_profile_password_change_updates_password_and_keeps_session(clinic_setup, client):
    clinic, service, user = clinic_setup
    client.force_login(user)

    response = client.post(
        reverse("dashboard:profile"),
        {
            "old_password": "password123",
            "new_password1": "NewStrongPass!2026",
            "new_password2": "NewStrongPass!2026",
        },
        follow=True,
    )

    user.refresh_from_db()
    assert response.status_code == 200
    assert user.check_password("NewStrongPass!2026")
    assert b"Password updated successfully." in response.content
    assert client.get(reverse("dashboard:home")).status_code == 200


@pytest.mark.django_db
def test_profile_password_change_requires_current_password(clinic_setup, client):
    clinic, service, user = clinic_setup
    client.force_login(user)

    response = client.post(
        reverse("dashboard:profile"),
        {
            "old_password": "wrong-password",
            "new_password1": "NewStrongPass!2026",
            "new_password2": "NewStrongPass!2026",
        },
    )

    user.refresh_from_db()
    assert response.status_code == 200
    assert user.check_password("password123")
    assert not user.check_password("NewStrongPass!2026")
    assert "Your old password was entered incorrectly" in response.content.decode()


@pytest.mark.django_db
def test_profile_password_change_rejects_mismatched_new_passwords(clinic_setup, client):
    clinic, service, user = clinic_setup
    client.force_login(user)

    response = client.post(
        reverse("dashboard:profile"),
        {
            "old_password": "password123",
            "new_password1": "NewStrongPass!2026",
            "new_password2": "DifferentStrongPass!2026",
        },
    )

    content = response.content.decode()
    user.refresh_from_db()
    assert response.status_code == 200
    assert user.check_password("password123")
    assert "password fields" in content
    assert "match" in content
```

- [ ] **Step 2: Write the failing template contract test**

Append this test near the other dashboard template tests in `tests/test_design_system.py`:

```python
def test_profile_page_contains_password_change_card():
    template = source_text("templates/dashboard/profile.html")

    assert "Change password" in template
    assert "password_form.old_password" in template
    assert "password_form.new_password1" in template
    assert "password_form.new_password2" in template
    assert "cf-btn cf-btn-primary" in template
    assert "cf-error" in template
```

- [ ] **Step 3: Run tests to verify RED**

Run: `.\env\Scripts\python.exe -m pytest dashboard/tests.py::test_profile_password_change_updates_password_and_keeps_session dashboard/tests.py::test_profile_password_change_requires_current_password dashboard/tests.py::test_profile_password_change_rejects_mismatched_new_passwords tests/test_design_system.py::test_profile_page_contains_password_change_card -q`

Expected: FAIL because the profile view ignores POST password fields and the template has no password-change card.

- [ ] **Step 4: Add the minimal view implementation**

In `dashboard/views.py`, change the auth import to:

```python
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.decorators import login_required
```

Add this app form import near other form imports:

```python
from accounts.forms import AppPasswordChangeForm
```

Replace `profile()` with:

```python
@login_required
def profile(request):
    clinic = _clinic_or_redirect(request)
    if request.method == "POST":
        password_form = AppPasswordChangeForm(request.user, request.POST)
        if password_form.is_valid():
            password_form.save()
            update_session_auth_hash(request, request.user)
            messages.success(request, "Password updated successfully.")
            return redirect("dashboard:profile")
    else:
        password_form = AppPasswordChangeForm(request.user)
    return render(request, "dashboard/profile.html", {"clinic": clinic, "password_form": password_form})
```

- [ ] **Step 5: Add the password-change card to the profile template**

In `templates/dashboard/profile.html`, add this section after the existing read-only profile details card:

```html
  <section class="cf-card">
    <div class="max-w-2xl">
      <h2 class="text-lg font-semibold text-[var(--cf-ink)]">Change password</h2>
      <p class="mt-1 text-sm text-[var(--cf-muted)]">Use your current password to set a new account password.</p>
    </div>

    <form method="post" class="mt-5 grid gap-5 md:grid-cols-2" novalidate>
      {% csrf_token %}
      <div class="cf-field md:col-span-2">
        <label for="{{ password_form.old_password.id_for_label }}" class="cf-label">{{ password_form.old_password.label }}</label>
        {{ password_form.old_password }}
        {% if password_form.old_password.errors %}<p class="cf-error">{{ password_form.old_password.errors.0 }}</p>{% endif %}
      </div>
      <div class="cf-field">
        <label for="{{ password_form.new_password1.id_for_label }}" class="cf-label">{{ password_form.new_password1.label }}</label>
        {{ password_form.new_password1 }}
        {% if password_form.new_password1.errors %}<p class="cf-error">{{ password_form.new_password1.errors.0 }}</p>{% endif %}
      </div>
      <div class="cf-field">
        <label for="{{ password_form.new_password2.id_for_label }}" class="cf-label">{{ password_form.new_password2.label }}</label>
        {{ password_form.new_password2 }}
        {% if password_form.new_password2.errors %}<p class="cf-error">{{ password_form.new_password2.errors.0 }}</p>{% endif %}
      </div>
      <div class="md:col-span-2 flex justify-end">
        <button type="submit" class="cf-btn cf-btn-primary">Update password</button>
      </div>
    </form>
  </section>
```

- [ ] **Step 6: Run tests to verify GREEN**

Run: `.\env\Scripts\python.exe -m pytest dashboard/tests.py::test_profile_password_change_updates_password_and_keeps_session dashboard/tests.py::test_profile_password_change_requires_current_password dashboard/tests.py::test_profile_password_change_rejects_mismatched_new_passwords tests/test_design_system.py::test_profile_page_contains_password_change_card -q`

Expected: PASS.

### Task 3: Final Verification

**Files:**
- Verify: `accounts/forms.py`
- Verify: `dashboard/views.py`
- Verify: `templates/dashboard/profile.html`
- Verify: `accounts/tests.py`
- Verify: `dashboard/tests.py`
- Verify: `tests/test_design_system.py`

- [ ] **Step 1: Run targeted account tests**

Run: `.\env\Scripts\python.exe -m pytest accounts/tests.py::test_password_change_form_uses_design_system_classes accounts/tests.py::test_password_reset_request_sends_email_for_existing_dashboard_user accounts/tests.py::test_password_reset_confirm_changes_password -q`

Expected: PASS.

- [ ] **Step 2: Run targeted dashboard password-change tests**

Run: `.\env\Scripts\python.exe -m pytest dashboard/tests.py::test_profile_password_change_updates_password_and_keeps_session dashboard/tests.py::test_profile_password_change_requires_current_password dashboard/tests.py::test_profile_password_change_rejects_mismatched_new_passwords -q`

Expected: PASS.

- [ ] **Step 3: Run targeted design-system tests**

Run: `.\env\Scripts\python.exe -m pytest tests/test_design_system.py::test_dashboard_pages_use_canonical_page_header_anatomy tests/test_design_system.py::test_profile_page_contains_password_change_card -q`

Expected: PASS.

- [ ] **Step 4: Run Django system check**

Run: `.\env\Scripts\python.exe manage.py check`

Expected: `System check identified no issues`.

- [ ] **Step 5: Inspect the diff**

Run: `git diff -- accounts/forms.py accounts/tests.py dashboard/views.py dashboard/tests.py templates/dashboard/profile.html tests/test_design_system.py docs/superpowers/plans/2026-06-07-profile-password-change.md`

Expected: diff only contains the password-change feature, tests, and this plan. Do not commit unless the user explicitly asks.

## Self-Review

- Spec coverage: The plan adds authenticated in-account password change, requires the current password, validates new passwords through Django, keeps the user logged in, renders inline errors, and leaves public reset/password signup/patient behavior untouched.
- Placeholder scan: No `TBD`, `TODO`, incomplete edge handling, or unspecified tests remain.
- Type/name consistency: `AppPasswordChangeForm`, `password_form`, `dashboard:profile`, `old_password`, `new_password1`, and `new_password2` are named consistently across tests, view, and template.
