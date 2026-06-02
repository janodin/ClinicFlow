from django.conf import settings
from django.core.checks import Error, Tags, register


_WEAK_SECRET_MARKERS = (
    "change-me",
    "changeme",
    "placeholder",
    "secret-key",
    "dev-clinic-booking-saas",
)


def _is_weak_secret(value, min_length=32):
    normalized = (value or "").strip().lower()
    return not normalized or len(normalized) < min_length or any(marker in normalized for marker in _WEAK_SECRET_MARKERS)


def _is_weak_secret_key(secret_key):
    return (
        _is_weak_secret(secret_key, min_length=50)
        or (secret_key or "").startswith("django-insecure-")
    )


@register(Tags.security, deploy=True)
def production_security_settings(app_configs, **kwargs):
    errors = []
    if settings.DEBUG:
        errors.append(Error("DEBUG must be disabled in production.", id="clinic_security.E001"))
    if _is_weak_secret_key(settings.SECRET_KEY):
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
    if _is_weak_secret(getattr(settings, "N8N_WEBHOOK_SECRET", "")):
        errors.append(Error("N8N_WEBHOOK_SECRET is required for trusted assistant webhooks.", id="clinic_security.E008"))
    if _is_weak_secret(getattr(settings, "MESSENGER_VERIFY_TOKEN", "")):
        errors.append(Error("MESSENGER_VERIFY_TOKEN is required for Messenger webhook verification.", id="clinic_security.E010"))
    return errors
