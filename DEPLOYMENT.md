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
