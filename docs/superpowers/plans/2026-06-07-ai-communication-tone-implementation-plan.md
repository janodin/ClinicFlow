# AI Communication Tone Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add structured shared AI communication tone controls using safe presets plus optional custom tone notes for the website Assistant and Messenger AI mode.

**Architecture:** Store tone on `ClinicAISettings`, expose it through the existing Messenger and widget AI context payloads, and inject it into the shared n8n AI Agent prompt as style-only guidance. Django remains authoritative for tenant scoping, settings permissions, form validation, and booking safety; n8n remains the shared model/tool orchestrator.

**Tech Stack:** Django models/forms/templates/migrations, pytest, Django Test Client, n8n Workflow SDK TypeScript source tests.

---

## Scope Check

This plan implements one focused subsystem: shared AI communication tone configuration. It does not add a new provider, channel-specific tone overrides, patient accounts, medical records, payments, or AI moderation infrastructure.

## File Structure

- Modify: `clinics/models.py` - add tone choices, tone fields, fail-closed runtime helpers on `ClinicAISettings`.
- Create: `clinics/migrations/0016_clinicaisettings_communication_tone.py` - add `communication_tone` and `custom_tone_instructions` to existing clinic AI settings rows with safe defaults.
- Modify: `clinics/forms.py` - expose tone fields on `SharedAISettingsForm` with dashboard-safe widgets and validation.
- Modify: `templates/dashboard/assistant_settings.html` - render the Communication Tone block in the approved order.
- Modify: `messenger/ai_tools.py` - include tone fields in the shared AI context payload for Messenger and widget channels.
- Modify: `messenger/tests.py` - cover model defaults, fail-closed tone behavior, and AI context payload fields.
- Modify: `dashboard/tests.py` - cover dashboard rendering, form validation, saving, permissions, and clinic scoping.
- Modify: `n8n_combined_messenger_widget_ai_bridge.ts` - inject tone into the shared AI Agent prompt with style-only precedence rules.
- Modify: `tests/test_n8n_combined_bridge_source.py` - assert the n8n prompt consumes tone and preserves safety precedence.

Do not commit during execution unless the user explicitly asks for commits. Use status and diff checkpoints instead.

---

### Task 1: Model, Migration, And AI Context Payload

**Files:**
- Modify: `clinics/models.py`
- Create: `clinics/migrations/0016_clinicaisettings_communication_tone.py`
- Modify: `messenger/ai_tools.py`
- Test: `messenger/tests.py`

- [ ] **Step 1: Add failing model and AI context tests**

Add these tests in `messenger/tests.py` near the existing `ClinicAISettings` and AI context tests:

```python
@pytest.mark.django_db
def test_clinic_ai_settings_tone_defaults_and_invalid_tone_fails_closed():
    from clinics.models import ClinicAISettings

    clinic, _connection = _create_messenger_clinic("owner_ai_tone_defaults", "PAGE-AI-TONE-DEFAULTS")

    settings = ClinicAISettings.objects.create(clinic=clinic)

    assert settings.communication_tone == ClinicAISettings.TONE_PROFESSIONAL
    assert settings.safe_communication_tone == ClinicAISettings.TONE_PROFESSIONAL
    assert settings.communication_tone_label == "Professional"
    assert settings.custom_tone_instructions == ""

    ClinicAISettings.objects.filter(pk=settings.pk).update(communication_tone="unsafe-tone")
    settings.refresh_from_db()

    assert settings.safe_communication_tone == ClinicAISettings.TONE_PROFESSIONAL
    assert settings.communication_tone_label == "Professional"


@pytest.mark.django_db
def test_ai_contexts_include_shared_communication_tone_fields():
    from clinics.models import ClinicAISettings
    from messenger.ai_tools import build_ai_context, build_widget_ai_context

    clinic, _connection = _create_messenger_clinic("owner_ai_tone_context", "PAGE-AI-TONE-CONTEXT")
    ClinicAISettings.objects.create(
        clinic=clinic,
        communication_tone=ClinicAISettings.TONE_EMPATHETIC,
        custom_tone_instructions="Use reassuring language for anxious patients.",
    )

    messenger_context = build_ai_context("PAGE-AI-TONE-CONTEXT")
    widget_context = build_widget_ai_context(clinic.slug)

    for context in [messenger_context, widget_context]:
        assert context["ai"]["communication_tone"] == ClinicAISettings.TONE_EMPATHETIC
        assert context["ai"]["communication_tone_label"] == "Empathetic"
        assert context["ai"]["custom_tone_instructions"] == "Use reassuring language for anxious patients."


@pytest.mark.django_db
def test_ai_context_settings_timestamp_changes_when_tone_changes():
    from clinics.models import ClinicAISettings
    from messenger.ai_tools import build_ai_context

    clinic, _connection = _create_messenger_clinic("owner_ai_tone_timestamp", "PAGE-AI-TONE-TIMESTAMP")
    settings = ClinicAISettings.objects.create(
        clinic=clinic,
        communication_tone=ClinicAISettings.TONE_PROFESSIONAL,
    )
    original_timestamp = build_ai_context("PAGE-AI-TONE-TIMESTAMP")["ai"]["settings_updated_at"]

    settings.communication_tone = ClinicAISettings.TONE_FRIENDLY
    settings.custom_tone_instructions = "Use approachable wording."
    settings.save()
    settings.refresh_from_db()

    updated_timestamp = build_ai_context("PAGE-AI-TONE-TIMESTAMP")["ai"]["settings_updated_at"]

    assert updated_timestamp == settings.updated_at.isoformat()
    assert updated_timestamp != original_timestamp
```

- [ ] **Step 2: Run tests and confirm they fail for missing tone fields**

Run:

```powershell
.\env\Scripts\python -m pytest messenger/tests.py -k "communication_tone or tone_context" -q
```

Expected: FAIL with errors that `ClinicAISettings` has no `communication_tone`, `safe_communication_tone`, or `communication_tone_label`.

- [ ] **Step 3: Add tone choices, fields, and helpers to `ClinicAISettings`**

In `clinics/models.py`, replace the start of `ClinicAISettings` with this version while preserving existing fields:

```python
class ClinicAISettings(TimeStampedModel):
    MESSENGER_MODE_QUICK_REPLIES = "quick_replies"
    MESSENGER_MODE_AI = "ai"
    MESSENGER_RESPONSE_MODE_CHOICES = [
        (MESSENGER_MODE_QUICK_REPLIES, "Quick replies"),
        (MESSENGER_MODE_AI, "AI mode"),
    ]

    TONE_PROFESSIONAL = "professional"
    TONE_WARM = "warm"
    TONE_EMPATHETIC = "empathetic"
    TONE_CONCISE = "concise"
    TONE_FRIENDLY = "friendly"
    COMMUNICATION_TONE_CHOICES = [
        (TONE_PROFESSIONAL, "Professional"),
        (TONE_WARM, "Warm"),
        (TONE_EMPATHETIC, "Empathetic"),
        (TONE_CONCISE, "Concise"),
        (TONE_FRIENDLY, "Friendly"),
    ]

    clinic = models.OneToOneField(Clinic, on_delete=models.CASCADE, related_name="ai_settings")
    is_ai_enabled = models.BooleanField(default=True)
    messenger_response_mode = models.CharField(
        max_length=24,
        choices=MESSENGER_RESPONSE_MODE_CHOICES,
        default=MESSENGER_MODE_QUICK_REPLIES,
    )
    communication_tone = models.CharField(
        max_length=24,
        choices=COMMUNICATION_TONE_CHOICES,
        default=TONE_PROFESSIONAL,
    )
    custom_tone_instructions = models.TextField(blank=True, default="", max_length=500)
    instructions = models.TextField(blank=True, default=DEFAULT_MESSENGER_AI_PROMPT)
    fallback_message = models.TextField(blank=True, default=DEFAULT_AI_FALLBACK_MESSAGE)

    objects = ClinicAISettingsManager()

    class Meta:
        verbose_name = "Clinic AI Settings"
        verbose_name_plural = "Clinic AI Settings"

    @property
    def safe_messenger_response_mode(self):
        valid_modes = {choice[0] for choice in self.MESSENGER_RESPONSE_MODE_CHOICES}
        if self.messenger_response_mode in valid_modes:
            return self.messenger_response_mode
        return self.MESSENGER_MODE_QUICK_REPLIES

    @property
    def safe_communication_tone(self):
        valid_tones = {choice[0] for choice in self.COMMUNICATION_TONE_CHOICES}
        if self.communication_tone in valid_tones:
            return self.communication_tone
        return self.TONE_PROFESSIONAL

    @property
    def communication_tone_label(self):
        labels = dict(self.COMMUNICATION_TONE_CHOICES)
        return labels[self.safe_communication_tone]

    def __str__(self):
        return f"ClinicAISettings({self.clinic.name})"
```

- [ ] **Step 4: Generate and verify the migration**

Run:

```powershell
.\env\Scripts\python manage.py makemigrations clinics
```

Expected: creates `clinics/migrations/0016_clinicaisettings_communication_tone.py`.

The migration operations should match this structure:

```python
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("clinics", "0015_alter_clinicaisettings_instructions"),
    ]

    operations = [
        migrations.AddField(
            model_name="clinicaisettings",
            name="communication_tone",
            field=models.CharField(
                choices=[
                    ("professional", "Professional"),
                    ("warm", "Warm"),
                    ("empathetic", "Empathetic"),
                    ("concise", "Concise"),
                    ("friendly", "Friendly"),
                ],
                default="professional",
                max_length=24,
            ),
        ),
        migrations.AddField(
            model_name="clinicaisettings",
            name="custom_tone_instructions",
            field=models.TextField(blank=True, default="", max_length=500),
        ),
    ]
```

- [ ] **Step 5: Add tone fields to the AI payload helper**

In `messenger/ai_tools.py`, update `_ai_payload_for_clinic()` to return tone fields:

```python
def _ai_payload_for_clinic(clinic):
    ai_settings = get_or_create_clinic_ai_settings(clinic)
    return {
        "is_ai_enabled": ai_settings.is_ai_enabled,
        "messenger_response_mode": ai_settings.safe_messenger_response_mode,
        "communication_tone": ai_settings.safe_communication_tone,
        "communication_tone_label": ai_settings.communication_tone_label,
        "custom_tone_instructions": ai_settings.custom_tone_instructions,
        "instructions": ai_settings.instructions or DEFAULT_MESSENGER_AI_PROMPT,
        "fallback_message": ai_settings.fallback_message or DEFAULT_AI_FALLBACK_MESSAGE,
        "settings_updated_at": ai_settings.updated_at.isoformat(),
    }
```

- [ ] **Step 6: Run model and context tests**

Run:

```powershell
.\env\Scripts\python -m pytest messenger/tests.py -k "communication_tone or tone_context or clinic_ai_settings or ai_contexts_expose_settings_timestamp" -q
```

Expected: PASS for the selected tests.

- [ ] **Step 7: Check migration status**

Run:

```powershell
.\env\Scripts\python manage.py makemigrations --check --dry-run
```

Expected: `No changes detected`.

- [ ] **Step 8: Diff checkpoint**

Run:

```powershell
git diff -- clinics/models.py clinics/migrations/0016_clinicaisettings_communication_tone.py messenger/ai_tools.py messenger/tests.py
```

Expected: diff contains only model tone fields, migration, AI context payload changes, and related tests.

---

### Task 2: Dashboard Form And Assistant Settings UX

**Files:**
- Modify: `clinics/forms.py`
- Modify: `templates/dashboard/assistant_settings.html`
- Test: `dashboard/tests.py`

- [ ] **Step 1: Add failing dashboard form and render tests**

Update `test_assistant_settings_page_shows_shared_ai_prompt_form()` in `dashboard/tests.py` to create tone values and assert the UI renders them:

```python
ClinicAISettings.objects.create(
    clinic=clinic,
    is_ai_enabled=False,
    communication_tone=ClinicAISettings.TONE_WARM,
    custom_tone_instructions="Use calm wording and avoid slang.",
    instructions="Use a warm clinic tone.",
    fallback_message="Please call the clinic.",
)
```

Add these assertions to the same test after the existing shared assistant assertions:

```python
assert b"Communication Tone" in response.content
assert b'name="communication_tone"' in response.content
assert b'value="professional"' in response.content
assert b'value="warm"' in response.content
assert b'value="empathetic"' in response.content
assert b'value="concise"' in response.content
assert b'value="friendly"' in response.content
assert b'name="custom_tone_instructions"' in response.content
assert b"Tone affects wording only" in response.content
assert b"Use calm wording and avoid slang." in response.content
```

Add this new form validation test near `test_shared_ai_settings_form_exposes_messenger_response_mode()`:

```python
@pytest.mark.django_db
def test_shared_ai_settings_form_exposes_communication_tone_fields_and_validates_choice(clinic_setup):
    from clinics.forms import SharedAISettingsForm
    from clinics.models import ClinicAISettings

    clinic, service, owner = clinic_setup
    settings = ClinicAISettings.objects.create(clinic=clinic)

    form = SharedAISettingsForm(instance=settings)

    assert "communication_tone" in form.fields
    assert "custom_tone_instructions" in form.fields
    assert dict(form.fields["communication_tone"].choices) == {
        ClinicAISettings.TONE_PROFESSIONAL: "Professional",
        ClinicAISettings.TONE_WARM: "Warm",
        ClinicAISettings.TONE_EMPATHETIC: "Empathetic",
        ClinicAISettings.TONE_CONCISE: "Concise",
        ClinicAISettings.TONE_FRIENDLY: "Friendly",
    }

    invalid = SharedAISettingsForm(
        data={
            "is_ai_enabled": "on",
            "messenger_response_mode": ClinicAISettings.MESSENGER_MODE_AI,
            "communication_tone": "unsafe-tone",
            "custom_tone_instructions": "Use calm wording.",
            "instructions": "Use a friendly clinic tone.",
            "fallback_message": "Please call us.",
        },
        instance=settings,
    )
    assert not invalid.is_valid()
    assert "communication_tone" in invalid.errors

    too_long = SharedAISettingsForm(
        data={
            "is_ai_enabled": "on",
            "messenger_response_mode": ClinicAISettings.MESSENGER_MODE_AI,
            "communication_tone": ClinicAISettings.TONE_FRIENDLY,
            "custom_tone_instructions": "x" * 501,
            "instructions": "Use a friendly clinic tone.",
            "fallback_message": "Please call us.",
        },
        instance=settings,
    )
    assert not too_long.is_valid()
    assert "custom_tone_instructions" in too_long.errors
```

- [ ] **Step 2: Run tests and confirm they fail for missing form/template fields**

Run:

```powershell
.\env\Scripts\python -m pytest dashboard/tests.py -k "communication_tone or shared_ai_settings_form or shared_ai_prompt_form" -q
```

Expected: FAIL because `SharedAISettingsForm` and `assistant_settings.html` do not expose tone fields yet.

- [ ] **Step 3: Add fields to `SharedAISettingsForm`**

In `clinics/forms.py`, replace `SharedAISettingsForm.Meta` with:

```python
class SharedAISettingsForm(forms.ModelForm):
    class Meta:
        model = ClinicAISettings
        fields = [
            "is_ai_enabled",
            "messenger_response_mode",
            "communication_tone",
            "custom_tone_instructions",
            "instructions",
            "fallback_message",
        ]
        widgets = {
            "is_ai_enabled": forms.CheckboxInput(attrs={"class": _CHECKBOX}),
            "messenger_response_mode": forms.RadioSelect(attrs={"class": _CHECKBOX}),
            "communication_tone": forms.Select(attrs={"class": _SELECT}),
            "custom_tone_instructions": forms.Textarea(attrs={
                "class": _TEXTAREA,
                "rows": 2,
                "maxlength": 500,
            }),
            "instructions": forms.Textarea(attrs={
                "class": _TEXTAREA,
                "rows": 8,
            }),
            "fallback_message": forms.Textarea(attrs={
                "class": _TEXTAREA,
                "rows": 3,
            }),
        }
        labels = {
            "is_ai_enabled": "Enable AI replies",
            "messenger_response_mode": "Messenger response mode",
            "communication_tone": "Communication tone",
            "custom_tone_instructions": "Custom tone notes",
            "instructions": "Prompt / Instructions",
            "fallback_message": "Fallback message",
        }
        help_texts = {
            "communication_tone": "Sets the assistant's patient-facing style for website Assistant and Messenger AI mode.",
            "custom_tone_instructions": "Optional style-only notes. Tone cannot override services, prices, availability, booking rules, or safety checks.",
            "instructions": "Used by the website Assistant and Messenger AI mode for broader clinic policies. Services, prices, and availability still come from KliniAssist.",
            "fallback_message": "Shown when AI replies are disabled or unavailable.",
        }
```

- [ ] **Step 4: Render Communication Tone in the assistant settings template**

In `templates/dashboard/assistant_settings.html`, insert this block after the Messenger Response Mode card and before the existing Prompt / Instructions field:

```html
      <div class="cf-card border border-[var(--cf-line)] bg-[var(--cf-surface-muted)] p-4 shadow-none">
        <div class="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <h3 class="cf-section-title text-lg">Communication Tone</h3>
            <p class="mt-1 text-sm text-[var(--cf-muted)]">Choose how the shared Assistant sounds in the website Assistant and Messenger AI mode.</p>
          </div>
          <span class="cf-badge cf-badge-info self-start">Shared</span>
        </div>
        <div class="mt-4 grid gap-4 md:grid-cols-[minmax(0,.45fr)_minmax(0,.55fr)]">
          <div class="cf-field">
            <label class="cf-label" for="{{ ai_form.communication_tone.id_for_label }}">{{ ai_form.communication_tone.label }}</label>
            {{ ai_form.communication_tone }}
            {% if ai_form.communication_tone.errors %}
              <p class="text-sm text-red-600 mt-1">{{ ai_form.communication_tone.errors.0 }}</p>
            {% endif %}
          </div>
          <div class="cf-field">
            <label class="cf-label" for="{{ ai_form.custom_tone_instructions.id_for_label }}">{{ ai_form.custom_tone_instructions.label }}</label>
            {{ ai_form.custom_tone_instructions }}
            {% if ai_form.custom_tone_instructions.errors %}
              <p class="text-sm text-red-600 mt-1">{{ ai_form.custom_tone_instructions.errors.0 }}</p>
            {% endif %}
          </div>
        </div>
        <p class="mt-3 text-xs text-[var(--cf-muted)]">Tone affects wording only. Services, prices, availability, booking rules, and safety checks still come from KliniAssist.</p>
      </div>
```

Update the existing Prompt / Instructions help copy in the same template to:

```html
        <p class="mt-1 text-xs text-[var(--cf-muted)]">Use this for broader assistant behavior and clinic policies. Tone is controlled above. Services, prices, and availability still come from KliniAssist.</p>
```

- [ ] **Step 5: Update existing assistant settings POST tests to submit tone fields**

In each `dashboard/tests.py` POST to `reverse("dashboard:assistant_settings")` with `_form: "ai_settings"`, add these keys unless the test intentionally uses a different tone:

```python
"communication_tone": ClinicAISettings.TONE_PROFESSIONAL,
"custom_tone_instructions": "",
```

For `test_owner_can_save_assistant_ai_settings()`, use a non-default tone and assert it persists:

```python
"communication_tone": ClinicAISettings.TONE_WARM,
"custom_tone_instructions": "Keep replies reassuring and plain.",
```

Add these assertions after refreshing settings:

```python
assert settings.communication_tone == ClinicAISettings.TONE_WARM
assert settings.custom_tone_instructions == "Keep replies reassuring and plain."
```

For `test_staff_cannot_save_assistant_ai_settings()`, add existing tone values to the setup:

```python
communication_tone=ClinicAISettings.TONE_CONCISE,
custom_tone_instructions="Existing tone notes.",
```

Add these blocked-save assertions:

```python
assert settings.communication_tone == ClinicAISettings.TONE_CONCISE
assert settings.custom_tone_instructions == "Existing tone notes."
```

For `test_owner_can_save_assistant_ai_settings_is_scoped_to_current_clinic()`, set different initial tone values on both clinics and assert only clinic B changes:

```python
communication_tone=ClinicAISettings.TONE_CONCISE,
custom_tone_instructions="Clinic A original tone.",
```

```python
communication_tone=ClinicAISettings.TONE_PROFESSIONAL,
custom_tone_instructions="Clinic B original tone.",
```

Submit clinic B values:

```python
"communication_tone": ClinicAISettings.TONE_EMPATHETIC,
"custom_tone_instructions": "Clinic B updated tone.",
```

Assert:

```python
assert settings_a.communication_tone == ClinicAISettings.TONE_CONCISE
assert settings_a.custom_tone_instructions == "Clinic A original tone."
assert settings_b.communication_tone == ClinicAISettings.TONE_EMPATHETIC
assert settings_b.custom_tone_instructions == "Clinic B updated tone."
```

- [ ] **Step 6: Run dashboard tests**

Run:

```powershell
.\env\Scripts\python -m pytest dashboard/tests.py -k "assistant" -q
```

Expected: PASS for selected Assistant settings tests.

- [ ] **Step 7: Diff checkpoint**

Run:

```powershell
git diff -- clinics/forms.py templates/dashboard/assistant_settings.html dashboard/tests.py
```

Expected: diff contains only shared Assistant tone form, template, and dashboard test changes.

---

### Task 3: Shared n8n Prompt Tone Injection

**Files:**
- Modify: `n8n_combined_messenger_widget_ai_bridge.ts`
- Test: `tests/test_n8n_combined_bridge_source.py`

- [ ] **Step 1: Add failing n8n source prompt test**

Add this test near the other shared AI Agent prompt tests in `tests/test_n8n_combined_bridge_source.py`:

```python
def test_combined_bridge_prompt_includes_communication_tone_with_style_only_guardrails():
    source = SOURCE.read_text(encoding="utf-8")
    agent_start = source.index("name: 'KliniAssist Shared AI Agent'")
    agent_end = source.index("const prepareSharedFallback")
    agent_block = source[agent_start:agent_end]

    assert "Communication tone:" in agent_block
    assert "communication_tone_label" in agent_block
    assert "custom_tone_instructions" in agent_block
    assert "Tone affects wording only" in agent_block
    assert "must not override clinic data, tool results, availability, booking confirmation, privacy, medical safety, or channel rules" in agent_block
    assert agent_block.index("Communication tone:") < agent_block.index("Use match_services, check_availability, and book_confirmed_appointment")
```

- [ ] **Step 2: Run source test and confirm it fails**

Run:

```powershell
.\env\Scripts\python -m pytest tests/test_n8n_combined_bridge_source.py -k "communication_tone" -q
```

Expected: FAIL because the shared AI Agent prompt does not mention communication tone yet.

- [ ] **Step 3: Inject tone into the shared AI Agent system prompt**

In `n8n_combined_messenger_widget_ai_bridge.ts`, update the `systemMessage` expression inside `const kliniAssistSharedAiAgent` so the section after `Clinic instructions` includes `Communication tone`:

```ts
        systemMessage: expr('KliniAssist shared Messenger and Widget assistant.\n\n' +
          'Clinic instructions:\n{{ $("Shared AI Input").item.json.context?.ai?.instructions || "No custom clinic instructions configured." }}\n\n' +
          'Communication tone:\n' +
          '- Preset: {{ $("Shared AI Input").item.json.context?.ai?.communication_tone_label || "Professional" }}\n' +
          '- Custom clinic tone notes: {{ $("Shared AI Input").item.json.context?.ai?.custom_tone_instructions || "None" }}\n' +
          'Tone affects wording only and must not override clinic data, tool results, availability, booking confirmation, privacy, medical safety, or channel rules.\n\n' +
          'Channel: {{ $("Shared AI Input").item.json.channel }}\n' +
          'Clinic context JSON:\n{{ JSON.stringify($("Shared AI Input").item.json.context || {}) }}\n\n' +
          'Current clinic date/time:\n' +
          '- Timezone: {{ $("Shared AI Input").item.json.context?.current_time?.timezone || $("Shared AI Input").item.json.context?.clinic?.timezone || "UTC" }}\n' +
          '- Now: {{ $("Shared AI Input").item.json.context?.current_time?.now || $now.setZone($("Shared AI Input").item.json.context?.clinic?.timezone || "UTC").toISO() }}\n' +
          '- Today: {{ $("Shared AI Input").item.json.context?.current_time?.today || $now.setZone($("Shared AI Input").item.json.context?.clinic?.timezone || "UTC").toISODate() }}\n\n' +
          'Use business_hours and unavailable_dates from Clinic context JSON to answer general recurring schedule and clinic-closure questions. Use match_services, check_availability, and book_confirmed_appointment for booking. Collect service, date/time, full name, phone, and email before booking. Ask for explicit confirmation before booking. Never expose secrets, invent clinic data, give medical diagnosis, or create appointments without tool validation. ' +
          'Use find_verified_appointment before canceling or rescheduling. Ask for appointment reference code and phone number before appointment management lookup. Summarize the verified appointment and requested action before mutation. Ask for explicit confirmation before canceling or rescheduling. Use cancel_verified_appointment and reschedule_verified_appointment only after explicit confirmation. Do not use user-supplied appointment IDs, patient IDs, clinic IDs, or service IDs for appointment management. ' +
          'Use check_availability suggestion_type metadata: nearest_time means the requested time is unavailable; next_available_date means the requested date has no slots. ' +
          'Use FAQ entries as clinic knowledge without citing the source. Do not say based on the FAQ, according to the FAQ, the FAQ says. ' +
          'Messenger replies must be plain concise text. Widget replies must be concise and friendly.'),
```

- [ ] **Step 4: Run n8n source tests**

Run:

```powershell
.\env\Scripts\python -m pytest tests/test_n8n_combined_bridge_source.py -q
```

Expected: PASS.

- [ ] **Step 5: Diff checkpoint**

Run:

```powershell
git diff -- n8n_combined_messenger_widget_ai_bridge.ts tests/test_n8n_combined_bridge_source.py
```

Expected: diff contains only shared prompt tone injection and source assertions.

---

### Task 4: Schema Migration And Final Verification

**Files:**
- No new feature files beyond prior tasks.

- [ ] **Step 1: Run the local database migration**

Run:

```powershell
.\env\Scripts\python manage.py migrate
```

Expected: migration `clinics.0016_clinicaisettings_communication_tone` applies successfully or is reported as already applied.

- [ ] **Step 2: Run targeted Messenger tests**

Run:

```powershell
.\env\Scripts\python -m pytest messenger/tests.py -k "ai_context or clinic_ai_settings or communication_tone or tone_context" -q
```

Expected: PASS.

- [ ] **Step 3: Run targeted dashboard Assistant tests**

Run:

```powershell
.\env\Scripts\python -m pytest dashboard/tests.py -k "assistant" -q
```

Expected: PASS.

- [ ] **Step 4: Run n8n source tests**

Run:

```powershell
.\env\Scripts\python -m pytest tests/test_n8n_combined_bridge_source.py -q
```

Expected: PASS.

- [ ] **Step 5: Verify migration state**

Run:

```powershell
.\env\Scripts\python manage.py makemigrations --check --dry-run
```

Expected: `No changes detected`.

- [ ] **Step 6: Run Django system checks**

Run:

```powershell
.\env\Scripts\python manage.py check
```

Expected: `System check identified no issues`.

- [ ] **Step 7: Final worktree review checkpoint**

Run:

```powershell
git status --short
git diff -- clinics/models.py clinics/forms.py messenger/ai_tools.py templates/dashboard/assistant_settings.html messenger/tests.py dashboard/tests.py n8n_combined_messenger_widget_ai_bridge.ts tests/test_n8n_combined_bridge_source.py clinics/migrations/0016_clinicaisettings_communication_tone.py
```

Expected: changed files match the file structure in this plan. Existing unrelated worktree changes must remain untouched.
