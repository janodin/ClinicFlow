from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone
from zoneinfo import ZoneInfo

from appointments.models import Appointment
from messenger.messenger_api import send_messages
from messenger.models import MessengerSession


class Command(BaseCommand):
    help = "Send Messenger reminder messages for upcoming appointments"

    def handle(self, *args, **options):
        now = timezone.now()
        windows = [
            (timedelta(hours=23), timedelta(hours=25)),  # ~24h before
            (timedelta(minutes=30), timedelta(minutes=90)),  # ~1h before
        ]

        for min_delta, max_delta in windows:
            lower = now + min_delta
            upper = now + max_delta
            appointments = Appointment.objects.filter(
                starts_at__gte=lower,
                starts_at__lte=upper,
                source=Appointment.SOURCE_MESSENGER,
                status__in=[Appointment.STATUS_PENDING, Appointment.STATUS_CONFIRMED],
            )
            for appt in appointments:
                try:
                    conn = appt.clinic.messenger_connection
                    if not conn or not conn.is_active:
                        continue
                    session = MessengerSession.objects.filter(connection=conn).first()
                    if not session:
                        continue
                    local_start = appt.starts_at.astimezone(ZoneInfo(appt.clinic.timezone))
                    message = (
                        f"Reminder: You have an appointment for {appt.service.name} "
                        f"at {appt.clinic.name} on {local_start.strftime('%A, %B %d at %I:%M %p')}.\n"
                        f"Reply CANCEL to cancel this appointment."
                    )
                    send_messages(conn, session.psid, [{"type": "text", "text": message}])
                    self.stdout.write(self.style.SUCCESS(f"Reminder sent for {appt.reference_code}"))
                except Exception as exc:
                    self.stdout.write(self.style.ERROR(f"Failed for {appt.reference_code}: {exc}"))
