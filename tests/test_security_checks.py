import importlib

import pytest
from django.test import override_settings

import config.settings as project_settings
from config.security_checks import production_security_settings


def _ids(errors):
    return {error.id for error in errors}


SECURE_SECRET_KEY = "ProductionStrongValueForDjangoChecksOnly12345678901234567890"
SECURE_N8N_WEBHOOK_SECRET = "N8nWebhookValueForTestsOnly1234567890"
SECURE_MESSENGER_VERIFY_TOKEN = "MessengerVerifyValueForTestsOnly1234567890"


def _secure_settings(**overrides):
    settings = {
        "DEBUG": False,
        "SECRET_KEY": SECURE_SECRET_KEY,
        "ALLOWED_HOSTS": ["clinic.example.com"],
        "SESSION_COOKIE_SECURE": True,
        "CSRF_COOKIE_SECURE": True,
        "SECURE_SSL_REDIRECT": True,
        "SECURE_HSTS_SECONDS": 31536000,
        "N8N_WEBHOOK_SECRET": SECURE_N8N_WEBHOOK_SECRET,
        "MESSENGER_VERIFY_TOKEN": SECURE_MESSENGER_VERIFY_TOKEN,
    }
    settings.update(overrides)
    return settings


def test_production_allowed_hosts_default_is_empty(monkeypatch):
    monkeypatch.delenv("ALLOWED_HOSTS", raising=False)
    monkeypatch.delenv("DEBUG", raising=False)
    monkeypatch.setenv("DJANGO_ENV", "production")

    reloaded_settings = importlib.reload(project_settings)

    try:
        assert reloaded_settings.ALLOWED_HOSTS == []
    finally:
        monkeypatch.setenv("DJANGO_ENV", "development")
        monkeypatch.setenv("DEBUG", "1")
        importlib.reload(project_settings)


def test_production_hsts_subdomain_and_preload_defaults_are_enabled(monkeypatch):
    monkeypatch.delenv("DEBUG", raising=False)
    monkeypatch.delenv("SECURE_HSTS_INCLUDE_SUBDOMAINS", raising=False)
    monkeypatch.delenv("SECURE_HSTS_PRELOAD", raising=False)
    monkeypatch.setenv("DJANGO_ENV", "production")

    reloaded_settings = importlib.reload(project_settings)

    try:
        assert reloaded_settings.SECURE_HSTS_INCLUDE_SUBDOMAINS is True
        assert reloaded_settings.SECURE_HSTS_PRELOAD is True
    finally:
        monkeypatch.setenv("DJANGO_ENV", "development")
        monkeypatch.setenv("DEBUG", "1")
        importlib.reload(project_settings)


def test_production_embed_cookie_defaults_allow_secure_third_party_iframes(monkeypatch):
    monkeypatch.delenv("DEBUG", raising=False)
    monkeypatch.delenv("SESSION_COOKIE_SAMESITE", raising=False)
    monkeypatch.delenv("CSRF_COOKIE_SAMESITE", raising=False)
    monkeypatch.setenv("DJANGO_ENV", "production")

    reloaded_settings = importlib.reload(project_settings)

    try:
        assert reloaded_settings.SESSION_COOKIE_SAMESITE == "None"
        assert reloaded_settings.CSRF_COOKIE_SAMESITE == "None"
        assert reloaded_settings.SESSION_COOKIE_SECURE is True
        assert reloaded_settings.CSRF_COOKIE_SECURE is True
    finally:
        monkeypatch.setenv("DJANGO_ENV", "development")
        monkeypatch.setenv("DEBUG", "1")
        importlib.reload(project_settings)


@override_settings(
    DEBUG=True,
    SECRET_KEY="django-insecure-dev-clinic-booking-saas",
    ALLOWED_HOSTS=[],
    SESSION_COOKIE_SECURE=False,
    CSRF_COOKIE_SECURE=False,
    SECURE_SSL_REDIRECT=False,
    SECURE_HSTS_SECONDS=0,
    N8N_WEBHOOK_SECRET="",
    MESSENGER_VERIFY_TOKEN="",
)
def test_deploy_check_flags_insecure_settings():
    ids = _ids(production_security_settings(None))

    assert "clinic_security.E001" in ids
    assert "clinic_security.E002" in ids
    assert "clinic_security.E003" in ids
    assert "clinic_security.E004" in ids
    assert "clinic_security.E005" in ids
    assert "clinic_security.E006" in ids
    assert "clinic_security.E007" in ids
    assert "clinic_security.E008" in ids
    assert "clinic_security.E010" in ids


@override_settings(
    DEBUG=False,
    SECRET_KEY=SECURE_SECRET_KEY,
    ALLOWED_HOSTS=["clinic.example.com"],
    SESSION_COOKIE_SECURE=True,
    CSRF_COOKIE_SECURE=True,
    SECURE_SSL_REDIRECT=True,
    SECURE_HSTS_SECONDS=31536000,
    N8N_WEBHOOK_SECRET=SECURE_N8N_WEBHOOK_SECRET,
    MESSENGER_VERIFY_TOKEN=SECURE_MESSENGER_VERIFY_TOKEN,
)
def test_deploy_check_accepts_secure_settings():
    assert production_security_settings(None) == []


@override_settings(
    DEBUG=False,
    SECRET_KEY="change-me-to-a-long-random-secret",
    ALLOWED_HOSTS=["clinic.example.com"],
    SESSION_COOKIE_SECURE=True,
    CSRF_COOKIE_SECURE=True,
    SECURE_SSL_REDIRECT=True,
    SECURE_HSTS_SECONDS=31536000,
    N8N_WEBHOOK_SECRET="n8n-secret",
    MESSENGER_VERIFY_TOKEN="verify-token",
)
def test_deploy_check_rejects_placeholder_secret_key():
    ids = _ids(production_security_settings(None))

    assert "clinic_security.E002" in ids


@override_settings(
    DEBUG=False,
    SECRET_KEY="short-secret",
    ALLOWED_HOSTS=["clinic.example.com"],
    SESSION_COOKIE_SECURE=True,
    CSRF_COOKIE_SECURE=True,
    SECURE_SSL_REDIRECT=True,
    SECURE_HSTS_SECONDS=31536000,
    N8N_WEBHOOK_SECRET="n8n-secret",
    MESSENGER_VERIFY_TOKEN="verify-token",
)
def test_deploy_check_rejects_short_secret_key():
    ids = _ids(production_security_settings(None))

    assert "clinic_security.E002" in ids


@pytest.mark.parametrize(
    ("setting_name", "error_id"),
    [
        ("N8N_WEBHOOK_SECRET", "clinic_security.E008"),
        ("MESSENGER_VERIFY_TOKEN", "clinic_security.E010"),
    ],
)
def test_deploy_check_rejects_placeholder_integration_secrets(setting_name, error_id):
    with override_settings(**_secure_settings(**{setting_name: "change-me"})):
        ids = _ids(production_security_settings(None))

    assert error_id in ids
