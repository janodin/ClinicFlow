import logging

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils.html import strip_tags


logger = logging.getLogger(__name__)


def send_patient_booking_confirmation(appointment):
    recipient = (appointment.patient.email or "").strip()
    if not recipient:
        return False

    context = {
        "appointment": appointment,
        "clinic": appointment.clinic,
        "clinic_name": appointment.clinic.name,
    }
    html_body = render_to_string("emails/confirmation_patient.html", context)
    text_body = strip_tags(html_body)
    message = EmailMultiAlternatives(
        subject=f"Your appointment at {appointment.clinic.name}",
        body=text_body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[recipient],
    )
    message.attach_alternative(html_body, "text/html")
    try:
        return message.send() == 1
    except Exception:
        logger.exception(
            "Failed to send patient booking confirmation email for appointment %s.",
            appointment.pk,
        )
        return False
