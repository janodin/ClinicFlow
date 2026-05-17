# Email Setup Guide

This project uses Django's email system for notifications (booking confirmations, reminders, and staff alerts).

## Local Development

By default, the project uses the **console email backend** so emails are printed to the terminal instead of being sent over the network:

```bash
EMAIL_BACKEND=django.core.mail.backends.console.EmailBackend
```

No external email service is required for local development.

## Production SMTP Setup

For production, configure a real SMTP provider using environment variables in your `.env` file.

### Required Environment Variables

```bash
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=smtp.example.com
EMAIL_PORT=587
EMAIL_HOST_USER=your-smtp-username
EMAIL_HOST_PASSWORD=your-smtp-password
EMAIL_USE_TLS=1
DEFAULT_FROM_EMAIL=ClinicFlow <noreply@your-domain.com>
```

- `EMAIL_BACKEND` — Use `django.core.mail.backends.smtp.EmailBackend` for SMTP.
- `EMAIL_HOST` — Your SMTP server hostname.
- `EMAIL_PORT` — Usually `587` for TLS or `465` for SSL.
- `EMAIL_HOST_USER` — SMTP username / API key.
- `EMAIL_HOST_PASSWORD` — SMTP password / API secret.
- `EMAIL_USE_TLS` — Set to `1` (recommended) for TLS on port 587.
- `DEFAULT_FROM_EMAIL` — The from address patients and staff will see.

### Provider Examples

#### SendGrid

```bash
EMAIL_HOST=smtp.sendgrid.net
EMAIL_PORT=587
EMAIL_HOST_USER=apikey
EMAIL_HOST_PASSWORD=SG.xxxxxxxxxxxxxxxxxxxx
```

#### Mailgun

```bash
EMAIL_HOST=smtp.mailgun.org
EMAIL_PORT=587
EMAIL_HOST_USER=postmaster@your-domain.com
EMAIL_HOST_PASSWORD=your-mailgun-password
```

#### AWS SES

```bash
EMAIL_HOST=email-smtp.us-east-1.amazonaws.com
EMAIL_PORT=587
EMAIL_HOST_USER=YOUR_SES_SMTP_USERNAME
EMAIL_HOST_PASSWORD=YOUR_SES_SMTP_PASSWORD
```

### SPF / DKIM

For reliable delivery in production:

- Configure **SPF** records to authorize your mail provider.
- Enable **DKIM** signing in your provider dashboard and publish the DNS records.
- Use a dedicated sending domain (e.g., `noreply@your-domain.com`) rather than a personal address.

## Testing

You can verify SMTP connectivity with Django's management command:

```bash
python manage.py sendtestemail your-email@example.com
```

For automated tests, the project uses Django's test email outbox (no real emails are sent).
