from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone
from zoneinfo import ZoneInfo

from appointments.models import Appointment
from messenger.messenger_api import send_messages


class Command(BaseCommand):
    help = "Send Messenger reminder messages for upcoming appointments"

    def handle(self, *args, **options):
        now = timezone.now()
        windows = [
            ("messenger_reminder_24h_sent_at", timedelta(hours=23), timedelta(hours=25)),  # ~24h before
            ("messenger_reminder_1h_sent_at", timedelta(minutes=30), timedelta(minutes=90)),  # ~1h before
        ]

        for sent_field, min_delta, max_delta in windows:
            lower = now + min_delta
            upper = now + max_delta
            appointments = Appointment.objects.filter(
                starts_at__gte=lower,
                starts_at__lte=upper,
                source=Appointment.SOURCE_MESSENGER,
                messenger_psid__gt="",
                status__in=[Appointment.STATUS_PENDING, Appointment.STATUS_CONFIRMED],
                clinic__is_active=True,
                clinic__requires_onboarding=False,
                clinic__messenger_connection__is_active=True,
                clinic__messenger_connection__page_access_token__gt="",
                **{f"{sent_field}__isnull": True},
            )
            for appt in appointments:
                try:
                    conn = appt.clinic.messenger_connection
                    if not conn or not conn.is_active or not conn.page_access_token:
                        continue
                    local_start = appt.starts_at.astimezone(ZoneInfo(appt.clinic.timezone))
                    message = (
                        f"Reminder: You have an appointment for {appt.service.name} "
                        f"at {appt.clinic.name} on {local_start.strftime('%A, %B %d at %I:%M %p')}.\n"
                        f"Reply CANCEL to cancel this appointment."
                    )
                    sent = send_messages(conn, appt.messenger_psid, [{"type": "text", "text": message}])
                    if not sent:
                        self.stdout.write(self.style.ERROR(f"Failed for appointment {appt.pk}: Messenger send failed"))
                        continue
                    setattr(appt, sent_field, now)
                    appt.save(update_fields=[sent_field, "updated_at"])
                    self.stdout.write(self.style.SUCCESS(f"Reminder sent for appointment {appt.pk}"))
                except Exception as exc:
                    self.stdout.write(self.style.ERROR(f"Failed for appointment {appt.pk}: {exc.__class__.__name__}"))
