from urllib.parse import urlparse

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


def _has_invalid_n8n_webhook_url(value, expected_path, legacy_slug):
    normalized = (value or "").strip().lower()
    if not normalized or legacy_slug in normalized:
        return True
    parsed = urlparse(normalized)
    hostname = parsed.hostname or ""
    if parsed.scheme != "https" or not hostname:
        return True
    if hostname in {"localhost", "127.0.0.1"} or hostname.endswith(".example"):
        return True
    return parsed.path != expected_path or bool(parsed.query or parsed.fragment)


def _has_invalid_assistant_webhook_url(value):
    return _has_invalid_n8n_webhook_url(value, "/webhook/kliniassist-widget-assistant", "clinicflow-widget-assistant")


def _has_invalid_meta_messenger_webhook_url(value):
    return _has_invalid_n8n_webhook_url(value, "/webhook/kliniassist-messenger", "clinicflow-messenger")


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
    if _has_invalid_assistant_webhook_url(getattr(settings, "ASSISTANT_N8N_WEBHOOK_URL", "")):
        errors.append(Error("ASSISTANT_N8N_WEBHOOK_URL must point to the kliniassist-widget-assistant n8n webhook.", id="clinic_security.E009"))
    if _is_weak_secret(getattr(settings, "MESSENGER_VERIFY_TOKEN", "")):
        errors.append(Error("MESSENGER_VERIFY_TOKEN is required for Messenger webhook verification.", id="clinic_security.E010"))
    if _has_invalid_meta_messenger_webhook_url(getattr(settings, "META_MESSENGER_N8N_WEBHOOK_URL", "")):
        errors.append(Error("META_MESSENGER_N8N_WEBHOOK_URL must point to the kliniassist-messenger n8n webhook.", id="clinic_security.E011"))
    return errors
