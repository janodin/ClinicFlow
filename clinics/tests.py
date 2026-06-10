import pytest
from django import forms
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError

from clinics.ai_provider_validation import validate_ai_provider_base_url
from clinics.forms import AIProviderSettingsForm, SAVED_PROVIDER_SECRET_MASK
from clinics.models import Clinic, ClinicAIProviderSettings, ClinicGroup


def _create_clinic(slug="provider-clinic"):
    User = get_user_model()
    owner = User.objects.create_user(
        username=f"{slug}@example.com",
        email=f"{slug}@example.com",
        password="password123",
    )
    group = ClinicGroup.objects.create(name=f"Group {slug}", owner=owner)
    return Clinic.objects.create(group=group, name=f"Clinic {slug}", slug=slug)


@pytest.mark.django_db
def test_ai_provider_settings_defaults_and_unique_clinic():
    clinic = _create_clinic()

    settings = ClinicAIProviderSettings.objects.create(clinic=clinic)

    assert settings.provider == ClinicAIProviderSettings.PROVIDER_OPENAI
    assert settings.base_url == ClinicAIProviderSettings.OPENAI_BASE_URL
    assert settings.model == ClinicAIProviderSettings.DEFAULT_OPENAI_MODEL
    assert settings.api_key == ""
    assert settings.is_enabled is False
    assert settings.has_api_key is False
    assert settings.is_configured is False
    assert str(settings) == f"ClinicAIProviderSettings({clinic.name})"

    with pytest.raises(IntegrityError):
        ClinicAIProviderSettings.objects.create(clinic=clinic)


@pytest.mark.django_db
def test_ai_provider_settings_defaults_include_fallback_model():
    clinic = _create_clinic("provider-fallback-default")

    settings = ClinicAIProviderSettings.objects.create(clinic=clinic)

    assert settings.model == ClinicAIProviderSettings.DEFAULT_OPENAI_MODEL
    assert settings.fallback_model == ClinicAIProviderSettings.DEFAULT_OPENAI_MODEL
    assert settings.is_configured is False


def test_fallback_model_migration_copies_existing_model_and_keeps_new_default():
    import importlib
    import inspect

    from django.db import migrations

    migration = importlib.import_module("clinics.migrations.0019_clinicaiprovidersettings_fallback_model")
    add_field = next(
        operation
        for operation in migration.Migration.operations
        if isinstance(operation, migrations.AddField) and operation.name == "fallback_model"
    )
    run_python = next(
        operation for operation in migration.Migration.operations if isinstance(operation, migrations.RunPython)
    )

    assert add_field.field.default == ClinicAIProviderSettings.DEFAULT_OPENAI_MODEL
    assert run_python.reverse_code == migrations.RunPython.noop
    source = inspect.getsource(run_python.code)
    assert "fallback_model=models.F(\"model\")" in source
    assert "model__gt=\"\"" in source


@pytest.mark.django_db
def test_ai_provider_settings_configured_requires_enabled_model_base_url_and_key():
    clinic = _create_clinic("configured-provider")
    settings = ClinicAIProviderSettings.objects.create(
        clinic=clinic,
        provider=ClinicAIProviderSettings.PROVIDER_OPENAI,
        base_url=ClinicAIProviderSettings.OPENAI_BASE_URL,
        model="gpt-4o-mini",
        api_key="sk-test-key",
        is_enabled=True,
    )

    assert settings.has_api_key is True
    assert settings.is_configured is True

    settings.api_key = ""
    assert settings.is_configured is False

    settings.api_key = "sk-test-key"
    settings.model = ""
    assert settings.is_configured is False

    settings.model = "gpt-4o-mini"
    settings.base_url = ""
    assert settings.is_configured is False

    settings.base_url = ClinicAIProviderSettings.OPENAI_BASE_URL
    settings.is_enabled = False
    assert settings.is_configured is False

    settings.provider = "unsupported"
    settings.base_url = ClinicAIProviderSettings.OPENAI_BASE_URL
    settings.model = "gpt-4o-mini"
    settings.api_key = "sk-test-key"
    settings.is_enabled = True
    assert settings.is_configured is False


@pytest.mark.django_db
def test_ai_provider_settings_configured_requires_fallback_model():
    clinic = _create_clinic("provider-fallback-required")
    settings = ClinicAIProviderSettings.objects.create(
        clinic=clinic,
        provider=ClinicAIProviderSettings.PROVIDER_OPENAI,
        base_url=ClinicAIProviderSettings.OPENAI_BASE_URL,
        model="gpt-4o",
        fallback_model="gpt-4o-mini",
        api_key="sk-test-key",
        is_enabled=True,
    )

    assert settings.is_configured is True

    settings.fallback_model = ""
    assert settings.is_configured is False


@pytest.mark.django_db
def test_ai_provider_form_openai_preset_normalizes_base_url_and_keeps_saved_key():
    clinic = _create_clinic("form-openai")
    settings = ClinicAIProviderSettings.objects.create(
        clinic=clinic,
        provider=ClinicAIProviderSettings.PROVIDER_OPENAI,
        base_url="https://malicious.example/v1",
        model="gpt-4o-mini",
        api_key="sk-saved-key",
        is_enabled=True,
    )
    form = AIProviderSettingsForm(
        data={
            "provider": ClinicAIProviderSettings.PROVIDER_OPENAI,
            "base_url": "https://ignored.example/v1",
            "openai_model": "gpt-4o",
            "openai_fallback_model": "gpt-4o-mini",
            "api_key": SAVED_PROVIDER_SECRET_MASK,
            "is_enabled": "on",
        },
        instance=settings,
    )

    assert form.is_valid(), form.errors
    saved = form.save()

    assert saved.provider == ClinicAIProviderSettings.PROVIDER_OPENAI
    assert saved.base_url == ClinicAIProviderSettings.OPENAI_BASE_URL
    assert saved.model == "gpt-4o"
    assert saved.fallback_model == "gpt-4o-mini"
    assert saved.api_key == "sk-saved-key"
    assert saved.is_enabled is True


@pytest.mark.django_db
def test_ai_provider_form_custom_provider_accepts_https_base_url_and_dropdown_models(monkeypatch):
    monkeypatch.setattr(
        "clinics.ai_provider_validation.socket.getaddrinfo",
        lambda *args, **kwargs: [(None, None, None, None, ("8.8.8.8", 0))],
    )
    clinic = _create_clinic("form-custom")
    settings = ClinicAIProviderSettings.objects.create(clinic=clinic)
    form = AIProviderSettingsForm(
        data={
            "provider": ClinicAIProviderSettings.PROVIDER_OPENAI_COMPATIBLE,
            "base_url": "https://openrouter.ai/api/v1/",
            "openai_model": "gpt-4o",
            "openai_fallback_model": "gpt-4o-mini",
            "api_key": "sk-custom-key",
            "is_enabled": "on",
        },
        instance=settings,
    )

    assert form.is_valid(), form.errors
    saved = form.save()

    assert saved.provider == ClinicAIProviderSettings.PROVIDER_OPENAI_COMPATIBLE
    assert saved.base_url == "https://openrouter.ai/api/v1"
    assert saved.model == "gpt-4o"
    assert saved.fallback_model == "gpt-4o-mini"
    assert saved.api_key == "sk-custom-key"


@pytest.mark.django_db
def test_ai_provider_form_requires_new_key_when_saved_secret_when_provider_base_url_changes(monkeypatch):
    monkeypatch.setattr(
        "clinics.ai_provider_validation.socket.getaddrinfo",
        lambda *args, **kwargs: [(None, None, None, None, ("8.8.8.8", 0))],
    )
    clinic = _create_clinic("form-key-provider-change")
    settings = ClinicAIProviderSettings.objects.create(
        clinic=clinic,
        provider=ClinicAIProviderSettings.PROVIDER_OPENAI,
        base_url=ClinicAIProviderSettings.OPENAI_BASE_URL,
        model="gpt-4o-mini",
        fallback_model="gpt-4o-mini",
        api_key="sk-openai-key",
        is_enabled=False,
    )
    form = AIProviderSettingsForm(
        data={
            "provider": ClinicAIProviderSettings.PROVIDER_OPENAI_COMPATIBLE,
            "base_url": "https://openrouter.ai/api/v1",
            "openai_model": "gpt-4o-mini",
            "openai_fallback_model": "gpt-4o-mini",
            "api_key": SAVED_PROVIDER_SECRET_MASK,
        },
        instance=settings,
    )

    assert not form.is_valid()
    assert "api_key" in form.errors
    assert "Enter a new API key when changing provider or base URL." in form.errors["api_key"]


@pytest.mark.django_db
def test_ai_provider_form_requires_new_key_when_blank_key_changes_provider_base_url(monkeypatch):
    monkeypatch.setattr(
        "clinics.ai_provider_validation.socket.getaddrinfo",
        lambda *args, **kwargs: [(None, None, None, None, ("8.8.8.8", 0))],
    )
    clinic = _create_clinic("form-blank-key-provider-change")
    settings = ClinicAIProviderSettings.objects.create(
        clinic=clinic,
        provider=ClinicAIProviderSettings.PROVIDER_OPENAI,
        base_url=ClinicAIProviderSettings.OPENAI_BASE_URL,
        model="gpt-4o-mini",
        fallback_model="gpt-4o-mini",
        api_key="sk-openai-key",
        is_enabled=False,
    )
    form = AIProviderSettingsForm(
        data={
            "provider": ClinicAIProviderSettings.PROVIDER_OPENAI_COMPATIBLE,
            "base_url": "https://openrouter.ai/api/v1",
            "openai_model": "gpt-4o-mini",
            "openai_fallback_model": "gpt-4o-mini",
            "api_key": "",
        },
        instance=settings,
    )

    assert not form.is_valid()
    assert "api_key" in form.errors
    assert "Enter a new API key when changing provider or base URL." in form.errors["api_key"]


@pytest.mark.django_db
def test_ai_provider_form_keeps_saved_secret_when_provider_base_url_unchanged(monkeypatch):
    monkeypatch.setattr(
        "clinics.ai_provider_validation.socket.getaddrinfo",
        lambda *args, **kwargs: [(None, None, None, None, ("8.8.8.8", 0))],
    )
    clinic = _create_clinic("form-key-provider-unchanged")
    settings = ClinicAIProviderSettings.objects.create(
        clinic=clinic,
        provider=ClinicAIProviderSettings.PROVIDER_OPENAI_COMPATIBLE,
        base_url="https://openrouter.ai/api/v1",
        model="openrouter/auto",
        fallback_model="openrouter/fallback",
        api_key="sk-openrouter-key",
        is_enabled=False,
    )
    form = AIProviderSettingsForm(
        data={
            "provider": ClinicAIProviderSettings.PROVIDER_OPENAI_COMPATIBLE,
            "base_url": "https://openrouter.ai/api/v1/",
            "openai_model": "openrouter/auto",
            "openai_fallback_model": "openrouter/fallback",
            "api_key": SAVED_PROVIDER_SECRET_MASK,
        },
        instance=settings,
    )

    assert form.is_valid(), form.errors
    saved = form.save()
    assert saved.api_key == "sk-openrouter-key"
    assert saved.base_url == "https://openrouter.ai/api/v1"


@pytest.mark.django_db
def test_ai_provider_form_requires_dropdown_fallback_model_when_enabled(monkeypatch):
    monkeypatch.setattr(
        "clinics.ai_provider_validation.socket.getaddrinfo",
        lambda *args, **kwargs: [(None, None, None, None, ("8.8.8.8", 0))],
    )
    clinic = _create_clinic("form-fallback-required")
    settings = ClinicAIProviderSettings.objects.create(clinic=clinic)
    form = AIProviderSettingsForm(
        data={
            "provider": ClinicAIProviderSettings.PROVIDER_OPENAI_COMPATIBLE,
            "base_url": "https://api.example.com/v1",
            "openai_model": "gpt-4o",
            "openai_fallback_model": "",
            "api_key": "sk-custom-key",
            "is_enabled": "on",
        },
        instance=settings,
    )

    assert not form.is_valid()
    assert "openai_fallback_model" in form.errors


@pytest.mark.django_db
@pytest.mark.parametrize("unsafe_url", [
    "http://api.openai.com/v1",
    "https://localhost/v1",
    "https://127.0.0.1/v1",
    "https://10.0.0.5/v1",
    "https://172.16.0.5/v1",
    "https://192.168.1.5/v1",
    "https://169.254.1.5/v1",
    "https://100.64.0.1/v1",
    "https://224.0.0.1/v1",
    "https://[ff02::1]/v1",
    "https://internal/v1",
    "https://metadata/v1",
    "https://intranet/v1",
    "https://clinic.local/v1",
    "https://clinic.localhost/v1",
    "https://api.internal/v1",
    "https://127.0.0.1.nip.io/v1",
    "https://10.0.0.1.nip.io/v1",
    "https://127.0.0.1.sslip.io/v1",
    "https://127.0.0.1.lvh.me/v1",
    "https://localtest.me/v1",
    "https://0177.0.0.1/v1",
    "https://127.1/v1",
    "https://127.0.1/v1",
    "https://127.000.000.001/v1",
    "https://user:pass@api.example.com/v1",
    "https://@api.example.com/v1",
    "https://[not-ip]/v1",
    "https://api.example.com:bad/v1",
    "https://api.example.com /v1",
    "https://api.example.com\\evil/v1",
    "https://api.example.com:/v1",
    "https://api.example.com/v1?token=secret",
    "https://api.example.com/v1#fragment",
])
def test_ai_provider_form_rejects_unsafe_custom_base_urls(unsafe_url):
    slug_suffix = "".join(char if char.isalnum() else "-" for char in unsafe_url.lower()).strip("-")[:80]
    clinic = _create_clinic(f"unsafe-{slug_suffix}")
    settings = ClinicAIProviderSettings.objects.create(clinic=clinic)
    form = AIProviderSettingsForm(
        data={
            "provider": ClinicAIProviderSettings.PROVIDER_OPENAI_COMPATIBLE,
            "base_url": unsafe_url,
            "openai_model": "gpt-4o-mini",
            "openai_fallback_model": "gpt-4o-mini",
            "api_key": "sk-custom-key",
            "is_enabled": "on",
        },
        instance=settings,
    )

    assert not form.is_valid()
    assert "base_url" in form.errors


@pytest.mark.django_db
def test_ai_provider_form_invalid_base_url_reports_only_base_url_error():
    clinic = _create_clinic("unsafe-error-copy")
    settings = ClinicAIProviderSettings.objects.create(clinic=clinic)
    form = AIProviderSettingsForm(
        data={
            "provider": ClinicAIProviderSettings.PROVIDER_OPENAI_COMPATIBLE,
            "base_url": "https://127.0.0.1/v1",
            "openai_model": "gpt-4o-mini",
            "openai_fallback_model": "gpt-4o-mini",
            "api_key": "sk-custom-key",
            "is_enabled": "on",
        },
        instance=settings,
    )

    assert not form.is_valid()
    assert list(form.errors) == ["base_url"]
    assert len(form.errors["base_url"]) == 1


@pytest.mark.django_db
def test_ai_provider_form_rejects_base_url_without_scheme():
    clinic = _create_clinic("unsafe-no-scheme")
    settings = ClinicAIProviderSettings.objects.create(clinic=clinic)
    form = AIProviderSettingsForm(
        data={
            "provider": ClinicAIProviderSettings.PROVIDER_OPENAI_COMPATIBLE,
            "base_url": "api.example.com/v1",
            "openai_model": "gpt-4o-mini",
            "openai_fallback_model": "gpt-4o-mini",
            "api_key": "sk-custom-key",
            "is_enabled": "on",
        },
        instance=settings,
    )

    assert not form.is_valid()
    assert "base_url" in form.errors


@pytest.mark.parametrize("unsafe_url", [
    "https://internal/v1",
    "https://@api.example.com/v1",
])
def test_validate_ai_provider_base_url_rejects_internal_host_and_empty_userinfo(unsafe_url):
    with pytest.raises(ValidationError):
        validate_ai_provider_base_url(unsafe_url)


@pytest.mark.parametrize("unsafe_url", [
    "https://clinic.local/v1",
    "https://clinic.localhost/v1",
    "https://127.0.0.1.lvh.me/v1",
    "https://0177.0.0.1/v1",
    "https://127.1/v1",
    "https://127.0.1/v1",
    "https://127.000.000.001/v1",
    "https://api.example.com /v1",
    "https://api.example.com\\evil/v1",
    "https://api.example.com:/v1",
])
def test_validate_ai_provider_base_url_rejects_strict_malformed_hosts(unsafe_url):
    with pytest.raises(ValidationError):
        validate_ai_provider_base_url(unsafe_url)


@pytest.mark.parametrize("bad_url", [
    "https://api.example.com/v1\x00",
    "https://api.example.com/v1\x7f",
])
def test_validate_ai_provider_base_url_rejects_control_characters(bad_url):
    with pytest.raises(forms.ValidationError):
        validate_ai_provider_base_url(bad_url)


@pytest.mark.parametrize("bad_url", [
    " https://api.example.com/v1",
    "https://api.example.com/v1 ",
    "\thttps://api.example.com/v1",
    "https://api.example.com/v1\n",
])
def test_validate_ai_provider_base_url_rejects_surrounding_whitespace(bad_url):
    with pytest.raises(forms.ValidationError):
        validate_ai_provider_base_url(bad_url)


def test_validate_ai_provider_base_url_rejects_unresolved_hosts(monkeypatch):
    def fail_getaddrinfo(*args, **kwargs):
        raise OSError("DNS failed")

    monkeypatch.setattr("clinics.ai_provider_validation.socket.getaddrinfo", fail_getaddrinfo)

    with pytest.raises(forms.ValidationError):
        validate_ai_provider_base_url("https://does-not-exist-kliniassist-review.example/v1")


def test_validate_ai_provider_base_url_rejects_overlong_dns_labels():
    bad_host = f"{'a' * 64}.com"

    with pytest.raises(forms.ValidationError):
        validate_ai_provider_base_url(f"https://{bad_host}/v1")


@pytest.mark.django_db
def test_ai_provider_form_does_not_render_saved_api_key():
    clinic = _create_clinic("form-mask")
    settings = ClinicAIProviderSettings.objects.create(clinic=clinic, api_key="sk-secret-value")
    form = AIProviderSettingsForm(instance=settings)
    html = form.as_p()

    assert "sk-secret-value" not in html
    assert SAVED_PROVIDER_SECRET_MASK in html


@pytest.mark.django_db
def test_ai_provider_form_empty_settings_do_not_render_static_default_model_options():
    clinic = _create_clinic("form-empty-model-options")
    settings = ClinicAIProviderSettings.objects.create(clinic=clinic, model="", fallback_model="")

    html = AIProviderSettingsForm(instance=settings).as_p()

    assert 'value="gpt-4o-mini"' not in html
    assert 'value="gpt-4o"' not in html


@pytest.mark.django_db
def test_ai_provider_form_unconfigured_default_settings_do_not_render_static_default_model_options():
    clinic = _create_clinic("form-unconfigured-default-model-options")
    settings = ClinicAIProviderSettings.objects.create(clinic=clinic)

    html = AIProviderSettingsForm(instance=settings).as_p()

    assert settings.model == ClinicAIProviderSettings.DEFAULT_OPENAI_MODEL
    assert settings.fallback_model == ClinicAIProviderSettings.DEFAULT_OPENAI_MODEL
    assert 'value="gpt-4o-mini"' not in html
    assert 'value="gpt-4o"' not in html


@pytest.mark.django_db
def test_ai_provider_form_bound_empty_settings_keep_submitted_fetched_model_options(monkeypatch):
    monkeypatch.setattr(
        "clinics.ai_provider_validation.socket.getaddrinfo",
        lambda *args, **kwargs: [(None, None, None, None, ("8.8.8.8", 0))],
    )
    clinic = _create_clinic("form-bound-fetched-model-options")
    settings = ClinicAIProviderSettings.objects.create(clinic=clinic, model="", fallback_model="")
    form = AIProviderSettingsForm(
        data={
            "provider": ClinicAIProviderSettings.PROVIDER_OPENAI_COMPATIBLE,
            "base_url": "https://openrouter.ai/api/v1",
            "openai_model": "openrouter/auto",
            "openai_fallback_model": "anthropic/claude-3.5-sonnet",
            "api_key": "sk-custom-key",
            "is_enabled": "on",
        },
        instance=settings,
    )

    assert form.is_valid(), form.errors
    html = form.as_p()
    assert 'value="openrouter/auto"' in html
    assert 'value="anthropic/claude-3.5-sonnet"' in html


@pytest.mark.django_db
def test_ai_provider_form_accepts_fetched_model_ids_for_dropdown_fields(monkeypatch):
    monkeypatch.setattr(
        "clinics.ai_provider_validation.socket.getaddrinfo",
        lambda *args, **kwargs: [(None, None, None, None, ("8.8.8.8", 0))],
    )
    clinic = _create_clinic("form-fetched-models")
    settings = ClinicAIProviderSettings.objects.create(clinic=clinic)
    form = AIProviderSettingsForm(
        data={
            "provider": ClinicAIProviderSettings.PROVIDER_OPENAI_COMPATIBLE,
            "base_url": "https://openrouter.ai/api/v1",
            "openai_model": "openrouter/auto",
            "openai_fallback_model": "anthropic/claude-3.5-sonnet",
            "api_key": "sk-custom-key",
            "is_enabled": "on",
        },
        instance=settings,
    )

    assert form.is_valid(), form.errors
    saved = form.save()

    assert saved.model == "openrouter/auto"
    assert saved.fallback_model == "anthropic/claude-3.5-sonnet"


@pytest.mark.django_db
def test_ai_provider_form_renders_saved_fetched_model_values_as_options():
    clinic = _create_clinic("form-saved-fetched-models")
    settings = ClinicAIProviderSettings.objects.create(
        clinic=clinic,
        model="openrouter/auto",
        fallback_model="anthropic/claude-3.5-sonnet",
    )

    html = AIProviderSettingsForm(instance=settings).as_p()

    assert 'value="openrouter/auto"' in html
    assert 'value="anthropic/claude-3.5-sonnet"' in html


@pytest.mark.django_db
def test_ai_provider_form_rejects_control_characters_in_model_ids(monkeypatch):
    monkeypatch.setattr(
        "clinics.ai_provider_validation.socket.getaddrinfo",
        lambda *args, **kwargs: [(None, None, None, None, ("8.8.8.8", 0))],
    )
    clinic = _create_clinic("form-invalid-model-id")
    settings = ClinicAIProviderSettings.objects.create(clinic=clinic)
    form = AIProviderSettingsForm(
        data={
            "provider": ClinicAIProviderSettings.PROVIDER_OPENAI_COMPATIBLE,
            "base_url": "https://openrouter.ai/api/v1",
            "openai_model": "openrouter/\nauto",
            "openai_fallback_model": "anthropic/claude-3.5-sonnet",
            "api_key": "sk-custom-key",
            "is_enabled": "on",
        },
        instance=settings,
    )

    assert not form.is_valid()
    assert "openai_model" in form.errors
    assert "Enter a valid model ID." in form.errors["openai_model"]


@pytest.mark.django_db
def test_ai_provider_form_rejects_c1_control_characters_in_model_ids(monkeypatch):
    monkeypatch.setattr(
        "clinics.ai_provider_validation.socket.getaddrinfo",
        lambda *args, **kwargs: [(None, None, None, None, ("8.8.8.8", 0))],
    )
    clinic = _create_clinic("form-invalid-c1-model-id")
    settings = ClinicAIProviderSettings.objects.create(clinic=clinic)
    form = AIProviderSettingsForm(
        data={
            "provider": ClinicAIProviderSettings.PROVIDER_OPENAI_COMPATIBLE,
            "base_url": "https://openrouter.ai/api/v1",
            "openai_model": "openrouter/\x85auto",
            "openai_fallback_model": "anthropic/claude-3.5-sonnet",
            "api_key": "sk-custom-key",
            "is_enabled": "on",
        },
        instance=settings,
    )

    assert not form.is_valid()
    assert "openai_model" in form.errors
    assert "Enter a valid model ID." in form.errors["openai_model"]


@pytest.mark.django_db
def test_ai_provider_form_rejects_surrounding_c1_control_characters_in_model_ids(monkeypatch):
    monkeypatch.setattr(
        "clinics.ai_provider_validation.socket.getaddrinfo",
        lambda *args, **kwargs: [(None, None, None, None, ("8.8.8.8", 0))],
    )
    clinic = _create_clinic("form-leading-c1-model-id")
    settings = ClinicAIProviderSettings.objects.create(clinic=clinic)
    form = AIProviderSettingsForm(
        data={
            "provider": ClinicAIProviderSettings.PROVIDER_OPENAI_COMPATIBLE,
            "base_url": "https://openrouter.ai/api/v1",
            "openai_model": "\x85openrouter/auto",
            "openai_fallback_model": "anthropic/claude-3.5-sonnet",
            "api_key": "sk-custom-key",
            "is_enabled": "on",
        },
        instance=settings,
    )

    assert not form.is_valid()
    assert "openai_model" in form.errors
    assert "Enter a valid model ID." in form.errors["openai_model"]
