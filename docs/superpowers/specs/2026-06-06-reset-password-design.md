# Reset Password Design

## Context

KliniAssist currently supports clinic owner and staff login through the `accounts` app. Patients remain guest records in V1 and do not have login accounts or a patient portal. The existing auth UI uses Django templates, Tailwind utilities, and the canonical `cf-*` component classes from the Neon Aqua Clinical design system.

## Goal

Add a secure password reset flow for clinic dashboard users. The reset entry point appears on the login page only. The signup page remains unchanged and does not include a reset-password link.

## Non-Goals

- Do not add patient accounts, patient portal access, or patient password reset.
- Do not add a custom reset-token model unless Django's built-in token flow proves insufficient.
- Do not add SMS reset, numeric code reset, or AI/Messenger automation.
- Do not change existing login, signup, onboarding, or dashboard URLs except for adding reset-password routes.

## Approach

Use Django's built-in password reset views:

- `PasswordResetView` for email submission.
- `PasswordResetDoneView` for the generic check-your-email page.
- `PasswordResetConfirmView` for setting a new password from the emailed link.
- `PasswordResetCompleteView` for the success page.

This keeps the implementation small and uses Django's signed, expiring, one-time password reset tokens. The flow targets the configured custom `accounts.User` model through Django's standard auth forms and email behavior.

## Routes

Add these routes under `accounts/`:

- `accounts/password-reset/` named `password_reset`.
- `accounts/password-reset/done/` named `password_reset_done`.
- `accounts/reset/<uidb64>/<token>/` named `password_reset_confirm`.
- `accounts/reset/done/` named `password_reset_complete`.

## UI

Add a "Forgot password?" link to `templates/accounts/login.html`, near the password field or sign-in action where users expect it.

Create account reset templates under `templates/accounts/`:

- `password_reset.html`
- `password_reset_done.html`
- `password_reset_confirm.html`
- `password_reset_complete.html`

The templates should reuse the existing public auth anatomy:

- `{% extends "base.html" %}`
- `cf-auth-panel`
- `cf-card`
- `cf-label`
- `cf-input`
- `cf-btn cf-btn-primary`
- existing Neon Aqua Clinical colors and spacing

The signup page must not show a reset-password link.

## Email

Use Django's configured email backend. Local development prints reset messages to the console by default. Production uses the existing SMTP environment settings.

Add password reset email templates so the outbound email uses KliniAssist wording:

- `templates/accounts/password_reset_email.html`
- `templates/accounts/password_reset_subject.txt`

The email should include the reset link, app name, and a short instruction that the user can ignore the email if they did not request the reset.

## Security And Privacy

The reset request page must not reveal whether an email address exists. After submission, users always see the same done page.

Only active users with usable passwords should receive reset emails, matching Django's default behavior.

The confirm page should rely on Django's token validation. A used, malformed, or expired token must not allow password changes.

CSRF protection remains enabled on all form posts.

## Testing

Add targeted account tests for:

- The login page renders a `password_reset` link.
- The signup page does not render a reset-password link.
- Posting an existing dashboard user's email sends one reset email and redirects to the done page.
- Posting an unknown email redirects to the same done page without sending email or revealing account existence.
- A valid token lets the user set a new password and then log in with it.
- Reusing the same token after password change fails.

Run targeted account tests, relevant design-system/template tests, and `python manage.py check` after implementation.

## Open Decisions

None. The user approved the standard email one-time reset link flow and clarified that the entry point should be login-page only.
