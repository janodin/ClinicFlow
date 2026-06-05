# VPS Deployment Notes

1. Create a Python virtual environment and install `requirements.txt`.
2. Configure PostgreSQL and copy `.env.example` to your real environment.
3. Run `python manage.py migrate` and `python manage.py collectstatic`.
4. Run the app with Gunicorn behind Nginx.
5. Add a cron job for reminders:

```bash
*/15 * * * * /path/to/venv/bin/python /path/to/app/manage.py send_due_notifications
```

Static files can be served by Nginx. Media files start on local VPS storage in V1.

## Production Security Checklist

1. Set `DJANGO_ENV=production`, `DEBUG=0`, a strong `SECRET_KEY`, production `ALLOWED_HOSTS`, and `CSRF_TRUSTED_ORIGINS`.
2. Set `SESSION_COOKIE_SECURE=1`, `CSRF_COOKIE_SECURE=1`, `SECURE_SSL_REDIRECT=1`, `SECURE_HSTS_SECONDS=31536000`, `SECURE_HSTS_INCLUDE_SUBDOMAINS=1`, and `SECURE_HSTS_PRELOAD=1` after HTTPS is confirmed for all subdomains.
3. Set `MESSENGER_VERIFY_TOKEN`, `MESSENGER_APP_SECRET`, and `N8N_WEBHOOK_SECRET` to unique long random values before enabling Messenger/n8n routes; copied `.env.example` placeholders fail deploy checks.
4. Set `META_MESSENGER_N8N_WEBHOOK_URL` to the active n8n Messenger webhook ending in `/webhook/kliniassist-messenger`.
5. Set `ASSISTANT_N8N_WEBHOOK_URL` to the active n8n widget assistant webhook ending in `/webhook/kliniassist-widget-assistant`.
6. Configure the reverse proxy to set `X-Forwarded-Proto https` and block direct public access to Gunicorn.
7. Run `python manage.py check --deploy` before release and treat all warnings/errors as blocking unless the deployment runbook explicitly documents why a specific warning is accepted.
8. Keep `.env` out of git, rotate exposed secrets, and use secret scanning in CI.

Example production deploy check using placeholder values. Replace each placeholder with a unique long random value before running it:

```powershell
$env:DJANGO_ENV="production"; $env:DEBUG="0"; $env:SECRET_KEY="replace-with-a-unique-50-plus-character-secret-key"; $env:ALLOWED_HOSTS="clinic.example.com"; $env:CSRF_TRUSTED_ORIGINS="https://clinic.example.com"; $env:SESSION_COOKIE_SECURE="1"; $env:CSRF_COOKIE_SECURE="1"; $env:SECURE_SSL_REDIRECT="1"; $env:SECURE_HSTS_SECONDS="31536000"; $env:SECURE_HSTS_INCLUDE_SUBDOMAINS="1"; $env:SECURE_HSTS_PRELOAD="1"; $env:N8N_WEBHOOK_SECRET="replace-with-a-unique-32-plus-character-secret"; $env:MESSENGER_APP_SECRET="replace-with-a-unique-32-plus-character-secret"; $env:MESSENGER_VERIFY_TOKEN="replace-with-a-unique-32-plus-character-token"; $env:META_MESSENGER_N8N_WEBHOOK_URL="https://157-90-164-203.nip.io/webhook/kliniassist-messenger"; $env:ASSISTANT_N8N_WEBHOOK_URL="https://157-90-164-203.nip.io/webhook/kliniassist-widget-assistant"; .\env\Scripts\python.exe manage.py check --deploy
```
