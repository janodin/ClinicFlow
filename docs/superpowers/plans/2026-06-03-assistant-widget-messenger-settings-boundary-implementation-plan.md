# Assistant Widget And Messenger Settings Boundary Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move shared AI prompt/settings ownership to the existing Assistant settings route, keep widget-only controls in the widget section, and make Messenger settings own only Facebook channel setup.

**Architecture:** This is a dashboard form/view/template cleanup. Keep `ClinicAISettings` and `ClinicFAQ` as the shared assistant data source, keep `Clinic` widget fields for website-only widget settings, and keep `MessengerConnection` for Facebook channel credentials. Do not change booking validation, n8n tool endpoints, widget runtime behavior, Messenger runtime behavior, or database schema.

**Tech Stack:** Django views/forms/templates, pytest, Django auth/permissions, Tailwind/`cf-*` dashboard classes, HTMX/Alpine already present in templates.

**Repository rule:** Do not commit during execution unless the user explicitly requests a commit.

---

## File Structure

- Modify: `clinics/forms.py` - add a neutral shared AI settings form and remove the unused widget behavior field from the widget settings form.
- Modify: `messenger/forms.py` - remove the dashboard AI settings form that is named for Messenger but edits `ClinicAISettings`.
- Modify: `dashboard/views.py` - make `assistant_settings` own shared AI settings, remove AI prompt handling from `messenger_settings`, and keep all settings permission checks clinic-scoped.
- Modify: `templates/dashboard/assistant_settings.html` - retitle the page as Assistant, add the shared AI settings card, keep the widget-only section, and remove the unused widget behavior field.
- Modify: `dashboard/templates/dashboard/messenger_settings.html` - remove the shared AI prompt form and replace it with a link card to Assistant settings.
- Modify: `templates/dashboard/base.html` - rename the sidebar link from Booking Widget to Assistant.
- Modify: `dashboard/tests.py` - update dashboard tests to assert the new ownership boundaries and preserve tenant/permission behavior.

No model files change. Do not run `makemigrations`; there is no schema change.

---

### Task 1: Write Failing Ownership And Permission Tests

**Files:**
- Modify: `dashboard/tests.py`

- [ ] **Step 1: Replace the old Messenger-owned AI prompt page tests**

In `dashboard/tests.py`, replace `test_messenger_settings_page_shows_ai_prompt_form` and `test_messenger_settings_page_shows_empty_ai_prompt_form_without_settings` with these tests:

```python
@pytest.mark.django_db
def test_assistant_settings_page_shows_shared_ai_prompt_form(clinic_setup, client):
    from clinics.models import ClinicAISettings
    from messenger.defaults import DEFAULT_MESSENGER_AI_PROMPT

    clinic, service, user = clinic_setup
    ClinicAISettings.objects.create(
        clinic=clinic,
        is_ai_enabled=False,
        instructions="Use a warm clinic tone.",
        fallback_message="Please call the clinic.",
    )
    client.force_login(user)

    response = client.get(reverse("dashboard:assistant_settings"))

    assert response.status_code == 200
    assert b">Assistant</h1>" in response.content
    assert b"Patient Assistant" not in response.content
    assert b"Shared Assistant Settings" in response.content
    assert b"Used by both the website Assistant and Facebook Messenger" in response.content
    assert b"Prompt / Instructions" in response.content
    assert b'name="is_ai_enabled"' in response.content
    assert b'name="instructions"' in response.content
    assert b'name="fallback_message"' in response.content
    assert b"Restore default prompt" in response.content
    assert DEFAULT_MESSENGER_AI_PROMPT.splitlines()[0].encode() in response.content
    assert b"Use a warm clinic tone." in response.content
    assert b"Please call the clinic." in response.content
    assert b"Website Booking Widget" in response.content
    assert b"widget_behavior_instructions" not in response.content


@pytest.mark.django_db
def test_assistant_settings_page_creates_default_shared_ai_settings(clinic_setup, client):
    from clinics.models import ClinicAISettings
    from messenger.defaults import DEFAULT_MESSENGER_AI_PROMPT

    clinic, service, user = clinic_setup
    client.force_login(user)

    response = client.get(reverse("dashboard:assistant_settings"))

    assert response.status_code == 200
    assert b"Shared Assistant Settings" in response.content
    assert DEFAULT_MESSENGER_AI_PROMPT.splitlines()[0].encode() in response.content
    assert ClinicAISettings.objects.filter(clinic=clinic).exists()


@pytest.mark.django_db
def test_messenger_settings_links_to_patient_assistant_without_ai_prompt_form(clinic_setup, client):
    from clinics.models import ClinicAISettings
    from messenger.defaults import DEFAULT_MESSENGER_AI_PROMPT
    from messenger.models import MessengerConnection

    clinic, service, user = clinic_setup
    MessengerConnection.objects.create(
        clinic=clinic,
        page_id="PAGE-DASH-AI-LINK",
        page_access_token="TOKEN-DASH-AI-LINK",
    )
    ClinicAISettings.objects.create(
        clinic=clinic,
        instructions="This prompt should not render on Messenger settings.",
        fallback_message="This fallback should not render on Messenger settings.",
    )
    client.force_login(user)

    response = client.get(reverse("dashboard:messenger_settings"))

    assert response.status_code == 200
    assert b"Shared Assistant" in response.content
    assert b"Open Assistant" in response.content
    assert b"Patient Assistant" not in response.content
    assert reverse("dashboard:assistant_settings").encode() in response.content
    assert b"Shared AI Prompt" not in response.content
    assert b'name="instructions"' not in response.content
    assert b'name="fallback_message"' not in response.content
    assert b"This prompt should not render" not in response.content
    assert b"This fallback should not render" not in response.content
    assert DEFAULT_MESSENGER_AI_PROMPT.splitlines()[0].encode() not in response.content
```

- [ ] **Step 2: Replace Messenger AI save tests with Assistant AI save tests**

In `dashboard/tests.py`, replace these tests:

- `test_owner_can_save_messenger_ai_settings`
- `test_owner_can_enable_messenger_ai_settings`
- `test_staff_cannot_save_messenger_ai_settings`
- `test_owner_can_save_messenger_ai_settings_is_scoped_to_current_clinic`
- `test_owner_can_save_shared_ai_settings_without_messenger_connection`

Use this replacement code:

```python
@pytest.mark.django_db
def test_owner_can_save_assistant_ai_settings(clinic_setup, client):
    from clinics.models import ClinicAISettings

    clinic, service, user = clinic_setup
    client.force_login(user)

    response = client.post(
        reverse("dashboard:assistant_settings"),
        {
            "_form": "ai_settings",
            "instructions": "Answer briefly and ask for confirmation before booking.",
            "fallback_message": "A staff member will help you soon.",
        },
    )

    assert response.status_code == 302
    assert response.url == reverse("dashboard:assistant_settings")
    settings = ClinicAISettings.objects.get(clinic=clinic)
    assert settings.is_ai_enabled is False
    assert settings.instructions == "Answer briefly and ask for confirmation before booking."
    assert settings.fallback_message == "A staff member will help you soon."


@pytest.mark.django_db
def test_owner_can_enable_assistant_ai_settings(clinic_setup, client):
    from clinics.models import ClinicAISettings

    clinic, service, user = clinic_setup
    client.force_login(user)

    response = client.post(
        reverse("dashboard:assistant_settings"),
        {
            "_form": "ai_settings",
            "is_ai_enabled": "on",
            "instructions": "Use a friendly clinic tone.",
            "fallback_message": "Please call us.",
        },
    )

    assert response.status_code == 302
    settings = ClinicAISettings.objects.get(clinic=clinic)
    assert settings.is_ai_enabled is True
    assert settings.instructions == "Use a friendly clinic tone."
    assert settings.fallback_message == "Please call us."


@pytest.mark.django_db
def test_staff_cannot_save_assistant_ai_settings(clinic_setup, client):
    from clinics.models import ClinicAISettings

    User = get_user_model()
    clinic, service, owner = clinic_setup
    staff = User.objects.create_user(username="staff@example.com", email="staff@example.com", password="password123")
    ClinicMembership.objects.create(clinic=clinic, user=staff, role=ClinicMembership.ROLE_STAFF)
    settings = ClinicAISettings.objects.create(
        clinic=clinic,
        is_ai_enabled=False,
        instructions="Existing owner instructions.",
        fallback_message="Existing fallback.",
    )
    client.force_login(staff)

    response = client.post(
        reverse("dashboard:assistant_settings"),
        {
            "_form": "ai_settings",
            "is_ai_enabled": "on",
            "instructions": "Staff should not save this.",
            "fallback_message": "Blocked.",
        },
    )

    assert response.status_code == 403
    settings.refresh_from_db()
    assert settings.is_ai_enabled is False
    assert settings.instructions == "Existing owner instructions."
    assert settings.fallback_message == "Existing fallback."


@pytest.mark.django_db
def test_owner_can_save_assistant_ai_settings_is_scoped_to_current_clinic(client):
    from clinics.models import ClinicAISettings

    User = get_user_model()
    owner_a = User.objects.create_user(username="owner-a@example.com", email="owner-a@example.com", password="password123")
    group_a = ClinicGroup.objects.create(name="Clinic A Group", owner=owner_a)
    clinic_a = Clinic.objects.create(group=group_a, name="Clinic A", slug="clinic-a")
    ClinicMembership.objects.create(clinic=clinic_a, user=owner_a, role=ClinicMembership.ROLE_OWNER)
    settings_a = ClinicAISettings.objects.create(
        clinic=clinic_a,
        is_ai_enabled=False,
        instructions="Clinic A original instructions.",
        fallback_message="Clinic A original fallback.",
    )

    owner_b = User.objects.create_user(username="owner-b@example.com", email="owner-b@example.com", password="password123")
    group_b = ClinicGroup.objects.create(name="Clinic B Group", owner=owner_b)
    clinic_b = Clinic.objects.create(group=group_b, name="Clinic B", slug="clinic-b")
    ClinicMembership.objects.create(clinic=clinic_b, user=owner_b, role=ClinicMembership.ROLE_OWNER)
    settings_b = ClinicAISettings.objects.create(
        clinic=clinic_b,
        is_ai_enabled=False,
        instructions="Clinic B original instructions.",
        fallback_message="Clinic B original fallback.",
    )
    client.force_login(owner_b)

    response = client.post(
        reverse("dashboard:assistant_settings"),
        {
            "_form": "ai_settings",
            "is_ai_enabled": "on",
            "instructions": "Clinic B updated instructions.",
            "fallback_message": "Clinic B updated fallback.",
        },
    )

    assert response.status_code == 302
    settings_a.refresh_from_db()
    settings_b.refresh_from_db()
    assert settings_a.is_ai_enabled is False
    assert settings_a.instructions == "Clinic A original instructions."
    assert settings_a.fallback_message == "Clinic A original fallback."
    assert settings_b.is_ai_enabled is True
    assert settings_b.instructions == "Clinic B updated instructions."
    assert settings_b.fallback_message == "Clinic B updated fallback."


@pytest.mark.django_db
def test_owner_can_save_assistant_ai_settings_without_messenger_connection(clinic_setup, client):
    from clinics.models import ClinicAISettings

    clinic, service, user = clinic_setup
    client.force_login(user)

    response = client.post(
        reverse("dashboard:assistant_settings"),
        {
            "_form": "ai_settings",
            "is_ai_enabled": "on",
            "instructions": "Shared website and Messenger instructions.",
            "fallback_message": "Shared fallback.",
        },
    )

    assert response.status_code == 302
    settings = ClinicAISettings.objects.get(clinic=clinic)
    assert settings.is_ai_enabled is True
    assert settings.instructions == "Shared website and Messenger instructions."
    assert settings.fallback_message == "Shared fallback."
```

- [ ] **Step 3: Add a widget form boundary test**

Add this test near `test_widget_settings_rejects_invalid_accent_color`:

```python
@pytest.mark.django_db
def test_widget_settings_form_excludes_unused_behavior_instructions(clinic_setup):
    from clinics.forms import WidgetSettingsForm

    clinic, service, owner = clinic_setup

    form = WidgetSettingsForm(instance=clinic)

    assert "widget_behavior_instructions" not in form.fields
```

- [ ] **Step 4: Update the existing invalid accent color test data**

Change `test_widget_settings_rejects_invalid_accent_color` so the posted data no longer includes `widget_behavior_instructions`:

```python
form = WidgetSettingsForm(
    data={
        "widget_accent_color": '";alert(1)//',
        "widget_welcome_message": "Welcome",
        "show_reason_field": "on",
    },
    instance=clinic,
)
```

- [ ] **Step 5: Run the new/changed tests and confirm they fail**

Run:

```powershell
.\env\Scripts\activate; if ($?) { python -m pytest dashboard/tests.py::test_assistant_settings_page_shows_shared_ai_prompt_form dashboard/tests.py::test_assistant_settings_page_creates_default_shared_ai_settings dashboard/tests.py::test_messenger_settings_links_to_patient_assistant_without_ai_prompt_form dashboard/tests.py::test_owner_can_save_assistant_ai_settings dashboard/tests.py::test_owner_can_enable_assistant_ai_settings dashboard/tests.py::test_staff_cannot_save_assistant_ai_settings dashboard/tests.py::test_owner_can_save_assistant_ai_settings_is_scoped_to_current_clinic dashboard/tests.py::test_owner_can_save_assistant_ai_settings_without_messenger_connection dashboard/tests.py::test_widget_settings_form_excludes_unused_behavior_instructions dashboard/tests.py::test_widget_settings_rejects_invalid_accent_color -q }
```

Expected: FAIL because `assistant_settings` does not render or save the shared AI form yet, Messenger still renders the shared AI prompt form, and `WidgetSettingsForm` still contains `widget_behavior_instructions`.

---

### Task 2: Add Shared Assistant Form And Move AI Save Handling To Assistant Settings

**Files:**
- Modify: `clinics/forms.py`
- Modify: `messenger/forms.py`
- Modify: `dashboard/views.py`

- [ ] **Step 1: Add `SharedAISettingsForm` and remove the unused widget field from `WidgetSettingsForm`**

In `clinics/forms.py`, update the model import and form classes to match this structure:

```python
from .models import Clinic, ClinicAISettings, ClinicFAQ
```

```python
class WidgetSettingsForm(forms.ModelForm):
    class Meta:
        model = Clinic
        fields = [
            "widget_accent_color",
            "widget_welcome_message",
            "show_reason_field",
        ]
        widgets = {
            "widget_accent_color": forms.TextInput(attrs={"type": "color", "class": _COLOR}),
            "widget_welcome_message": forms.Textarea(attrs={"class": _TEXTAREA, "placeholder": "Welcome message shown in the widget", "rows": 3}),
            "show_reason_field": forms.CheckboxInput(attrs={"class": _CHECKBOX}),
        }


class SharedAISettingsForm(forms.ModelForm):
    class Meta:
        model = ClinicAISettings
        fields = ["is_ai_enabled", "instructions", "fallback_message"]
        widgets = {
            "is_ai_enabled": forms.CheckboxInput(attrs={"class": _CHECKBOX}),
            "instructions": forms.Textarea(attrs={
                "class": _TEXTAREA,
                "placeholder": "Tell the shared assistant how to speak, what clinic policies to follow, and what it should avoid.",
                "rows": 8,
            }),
            "fallback_message": forms.Textarea(attrs={
                "class": _TEXTAREA,
                "placeholder": "Example: Our team will help you shortly. Please call the clinic for urgent concerns.",
                "rows": 3,
            }),
        }
        labels = {
            "is_ai_enabled": "Enable AI replies",
            "instructions": "Prompt / Instructions",
            "fallback_message": "Fallback message",
        }
        help_texts = {
            "instructions": "Used by both the website Assistant and Facebook Messenger. Services, prices, and availability still come from ClinicFlow.",
            "fallback_message": "Shown in both channels when AI replies are disabled or unavailable.",
        }
```

- [ ] **Step 2: Remove the Messenger-named AI form**

In `messenger/forms.py`, remove this import:

```python
from clinics.models import ClinicAISettings
```

Delete the entire `MessengerAISettingsForm` class. Keep `SAVED_SECRET_MASK`, `SavedSecretPasswordInput`, and `MessengerConnectionForm` unchanged.

- [ ] **Step 3: Update dashboard view imports**

In `dashboard/views.py`, change the imports near the top to include the new shared form and model:

```python
from clinics.forms import ClinicFAQForm, ClinicSettingsForm, SharedAISettingsForm, WidgetSettingsForm
from clinics.models import Clinic, ClinicAISettings, ClinicMembership
from messenger.defaults import DEFAULT_MESSENGER_AI_PROMPT
```

- [ ] **Step 4: Add a helper for Assistant settings template context**

Add this helper above `assistant_settings` in `dashboard/views.py`:

```python
def _assistant_settings_context(request, clinic, *, widget_form=None, ai_form=None, faq_form=None):
    ai_settings, _ = ClinicAISettings.objects.get_or_create(clinic=clinic)
    iframe_url = _embedded_iframe_url(request, clinic)
    script_url = request.build_absolute_uri(reverse("widget:embed_js", args=[clinic.slug]))
    return {
        "clinic": clinic,
        "widget_form": widget_form or WidgetSettingsForm(instance=clinic),
        "ai_form": ai_form or SharedAISettingsForm(instance=ai_settings),
        "faq_form": faq_form or ClinicFAQForm(),
        "faqs": clinic.faqs.all(),
        "iframe_url": iframe_url,
        "script_url": script_url,
        "default_ai_prompt": DEFAULT_MESSENGER_AI_PROMPT,
    }
```

- [ ] **Step 5: Replace `assistant_settings` view with shared AI handling**

Replace the current `assistant_settings` function in `dashboard/views.py` with:

```python
@login_required
def assistant_settings(request):
    clinic = _clinic_or_redirect(request)
    _require_settings_permission(request.user)

    ai_settings, _ = ClinicAISettings.objects.get_or_create(clinic=clinic)
    widget_form = WidgetSettingsForm(instance=clinic)
    ai_form = SharedAISettingsForm(instance=ai_settings)
    post_form = request.POST.get("_form")

    if request.method == "POST" and post_form == "ai_settings":
        ai_form = SharedAISettingsForm(request.POST, instance=ai_settings)
        if ai_form.is_valid():
            ai_form.save()
            messages.success(request, "Shared assistant settings saved.")
            return redirect("dashboard:assistant_settings")
    elif request.method == "POST" and post_form == "widget_settings":
        widget_form = WidgetSettingsForm(request.POST, instance=clinic)
        if widget_form.is_valid():
            widget_form.save()
            messages.success(request, "Widget settings saved.")
            return redirect("dashboard:assistant_settings")

    return render(
        request,
        "dashboard/assistant_settings.html",
        _assistant_settings_context(request, clinic, widget_form=widget_form, ai_form=ai_form),
    )
```

- [ ] **Step 6: Fix invalid FAQ render context**

In `create_faq`, replace the invalid form render return with:

```python
return render(
    request,
    "dashboard/assistant_settings.html",
    _assistant_settings_context(request, clinic, faq_form=form),
)
```

- [ ] **Step 7: Remove shared AI handling from `messenger_settings`**

In `dashboard/views.py`, replace `messenger_settings` with:

```python
@login_required
def messenger_settings(request):
    clinic = _clinic_or_redirect(request)
    membership = get_active_membership(request.user)
    if not user_can_manage_settings(membership):
        raise PermissionDenied
    from messenger.forms import MessengerConnectionForm
    from messenger.messenger_api import fetch_page_profile

    connection = getattr(clinic, "messenger_connection", None)
    post_form = request.POST.get("_form")

    if request.method == "POST" and post_form not in {None, "", "connection_settings"}:
        messages.error(request, "Shared assistant settings are managed from Assistant.")
        return redirect("dashboard:assistant_settings")

    if request.method == "POST":
        form = MessengerConnectionForm(request.POST, instance=connection)
        if form.is_valid():
            candidate = form.save(commit=False)
            candidate.clinic = clinic
            candidate.is_active = True
            page_name_warning = False

            profile = fetch_page_profile(candidate.page_access_token)
            if profile:
                meta_page_id = profile.get("id", "")
                if candidate.page_id and meta_page_id and candidate.page_id != meta_page_id:
                    form.add_error("page_id", "The Facebook Page ID does not match the Page Access Token.")
                else:
                    if meta_page_id and not candidate.page_id:
                        candidate.page_id = meta_page_id
                    candidate.page_name = profile.get("name", "")
            elif candidate.page_access_token:
                page_name_warning = True

            if not form.errors:
                connection = candidate
                connection.save()

                if page_name_warning:
                    messages.warning(request, "Messenger settings saved, but the Facebook Page name could not be refreshed.")
                else:
                    messages.success(request, "Messenger settings saved. Remember to configure the webhook in your Meta Developer Dashboard.")
                return redirect("dashboard:messenger_settings")
    else:
        form = MessengerConnectionForm(instance=connection)

    n8n_webhook_url = request.build_absolute_uri(reverse("messenger:n8n_webhook"))
    return render(request, "dashboard/messenger_settings.html", {
        "clinic": clinic,
        "connection": connection,
        "form": form,
        "n8n_webhook_url": n8n_webhook_url,
    })
```

- [ ] **Step 8: Run targeted tests for form/view behavior**

Run:

```powershell
.\env\Scripts\activate; if ($?) { python -m pytest dashboard/tests.py::test_owner_can_save_assistant_ai_settings dashboard/tests.py::test_owner_can_enable_assistant_ai_settings dashboard/tests.py::test_staff_cannot_save_assistant_ai_settings dashboard/tests.py::test_owner_can_save_assistant_ai_settings_is_scoped_to_current_clinic dashboard/tests.py::test_owner_can_save_assistant_ai_settings_without_messenger_connection dashboard/tests.py::test_widget_settings_form_excludes_unused_behavior_instructions dashboard/tests.py::test_widget_settings_rejects_invalid_accent_color -q }
```

Expected: form/view save tests PASS; page rendering tests may still fail until templates are updated in the next tasks.

---

### Task 3: Update Assistant Page Template

**Files:**
- Modify: `templates/dashboard/assistant_settings.html`
- Modify: `templates/dashboard/base.html`

- [ ] **Step 1: Update the sidebar label**

In `templates/dashboard/base.html`, change the setup nav label from:

```django
{% include "dashboard/partials/nav_link.html" with url_name="dashboard:assistant_settings" icon="message-circle" label="Booking Widget" %}
```

to:

```django
{% include "dashboard/partials/nav_link.html" with url_name="dashboard:assistant_settings" icon="message-circle" label="Assistant" %}
```

- [ ] **Step 2: Replace the page header and add the shared AI card**

In `templates/dashboard/assistant_settings.html`, change the header block to:

```django
  <div class="cf-page-header">
    <div>
      <h1 class="cf-page-title ui-page-title">Assistant</h1>
      <p class="cf-page-description">Manage the shared AI prompt, FAQs, and website booking widget experience.</p>
    </div>
  </div>
```

Immediately after that header, add this shared AI settings card:

```django
  <section class="cf-card p-6">
    <div class="flex items-center gap-3 mb-4">
      <div class="cf-icon-box p-3">
        <i data-lucide="bot" class="h-5 w-5"></i>
      </div>
      <div>
        <h2 class="cf-section-title">Shared Assistant Settings</h2>
        <p class="mt-1 text-sm text-[var(--cf-muted)]">Used by both the website Assistant and Facebook Messenger.</p>
      </div>
    </div>

    <form method="post" action="{% url 'dashboard:assistant_settings' %}" class="grid gap-5">
      {% csrf_token %}
      <input type="hidden" name="_form" value="ai_settings">
      <textarea id="default-ai-prompt-value" class="hidden" aria-hidden="true">{{ default_ai_prompt }}</textarea>

      <div>
        <label class="flex items-center gap-2 cursor-pointer">
          {{ ai_form.is_ai_enabled }}
          <span class="text-sm font-semibold text-[var(--cf-ink)]">{{ ai_form.is_ai_enabled.label }}</span>
        </label>
        {% if ai_form.is_ai_enabled.errors %}
          <p class="text-sm text-red-600 mt-1">{{ ai_form.is_ai_enabled.errors.0 }}</p>
        {% endif %}
      </div>

      <div class="cf-field">
        <div class="mb-1 flex flex-wrap items-center justify-between gap-2">
          <label class="cf-label" for="{{ ai_form.instructions.id_for_label }}">{{ ai_form.instructions.label }}</label>
          <button
            type="button"
            class="cf-btn cf-btn-secondary cf-btn-sm"
            @click="const field = document.getElementById('{{ ai_form.instructions.id_for_label }}'); const source = document.getElementById('default-ai-prompt-value'); if (field && source) { field.value = source.value; field.focus(); }"
          >
            <i data-lucide="rotate-ccw" class="h-4 w-4"></i> Restore default prompt
          </button>
        </div>
        {{ ai_form.instructions }}
        <p class="mt-1 text-xs text-[var(--cf-muted)]">Tell the assistant how to speak, what clinic policies to follow, and what it should avoid. Services, prices, and availability still come from ClinicFlow.</p>
        {% if ai_form.instructions.errors %}
          <p class="text-sm text-red-600 mt-1">{{ ai_form.instructions.errors.0 }}</p>
        {% endif %}
      </div>

      <div class="cf-field">
        <label class="cf-label" for="{{ ai_form.fallback_message.id_for_label }}">{{ ai_form.fallback_message.label }}</label>
        {{ ai_form.fallback_message }}
        <p class="mt-1 text-xs text-[var(--cf-muted)]">Shown in both channels when AI replies are disabled or unavailable.</p>
        {% if ai_form.fallback_message.errors %}
          <p class="text-sm text-red-600 mt-1">{{ ai_form.fallback_message.errors.0 }}</p>
        {% endif %}
      </div>

      <div class="pt-2">
        <button type="submit" class="cf-btn cf-btn-primary">
          <i data-lucide="save" class="h-4 w-4"></i> Save Assistant Settings
        </button>
      </div>
    </form>
  </section>
```

- [ ] **Step 3: Rename the widget-only section**

In the existing widget section, change:

```django
<h2 class="cf-section-title">Widget Settings</h2>
<p class="mt-2 text-sm text-[var(--cf-muted)]">Customize appearance, preview, and share your booking widget.</p>
```

to:

```django
<h2 class="cf-section-title">Website Booking Widget</h2>
<p class="mt-2 text-sm text-[var(--cf-muted)]">Customize website-only appearance, preview, and embed settings.</p>
```

- [ ] **Step 4: Remove the unused widget behavior field from the template**

Delete this block from `templates/dashboard/assistant_settings.html`:

```django
          <div class="cf-field">
            <label for="{{ widget_form.widget_behavior_instructions.id_for_label }}" class="cf-label">{{ widget_form.widget_behavior_instructions.label }}</label>
            {{ widget_form.widget_behavior_instructions }}
            {% if widget_form.widget_behavior_instructions.errors %}<p class="mt-1 text-xs text-[var(--cf-red)]">{{ widget_form.widget_behavior_instructions.errors.0 }}</p>{% endif %}
          </div>
```

- [ ] **Step 5: Update FAQ copy to show shared ownership**

Change the FAQ section heading area from:

```django
    <h2 class="cf-section-title">FAQ Responses</h2>
```

to:

```django
    <h2 class="cf-section-title">FAQ Responses</h2>
    <p class="mt-2 text-sm text-[var(--cf-muted)]">Used by both the website Assistant and Facebook Messenger to answer common patient questions.</p>
```

Change the empty state copy from:

```django
<p class="mt-1 text-sm text-[var(--cf-muted)]">Add common questions above to help patients book faster.</p>
```

to:

```django
<p class="mt-1 text-sm text-[var(--cf-muted)]">Add common questions above to help patients self-serve before booking.</p>
```

- [ ] **Step 6: Run assistant page rendering tests**

Run:

```powershell
.\env\Scripts\activate; if ($?) { python -m pytest dashboard/tests.py::test_assistant_settings_page_shows_shared_ai_prompt_form dashboard/tests.py::test_assistant_settings_page_creates_default_shared_ai_settings dashboard/tests.py::test_widget_settings_form_excludes_unused_behavior_instructions -q }
```

Expected: PASS.

---

### Task 4: Update Messenger Settings Template Boundary

**Files:**
- Modify: `dashboard/templates/dashboard/messenger_settings.html`

- [ ] **Step 1: Remove the shared AI prompt card**

Delete the full block beginning with:

```django
  <!-- Shared AI Prompt Card -->
  <section class="cf-card p-6">
```

and ending with the matching closing `</section>` before the final `</div>` and `<script>` block.

- [ ] **Step 2: Add a cross-link card to Assistant settings**

In the same location where the shared AI prompt card was removed, add:

```django
  <section class="cf-card p-6">
    <div class="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
      <div class="flex items-start gap-3">
        <div class="cf-icon-box p-3">
          <i data-lucide="bot" class="h-5 w-5"></i>
        </div>
        <div>
          <h2 class="cf-section-title">Shared Assistant</h2>
          <p class="mt-1 text-sm text-[var(--cf-muted)]">AI prompt, fallback message, and FAQs are shared by Facebook Messenger and the website Assistant.</p>
          <p class="mt-2 text-xs text-[var(--cf-muted)]">Manage shared assistant behavior from Assistant settings. Messenger-specific credentials stay on this page.</p>
        </div>
      </div>
      <a href="{% url 'dashboard:assistant_settings' %}" class="cf-btn cf-btn-secondary shrink-0">
        <i data-lucide="settings" class="h-4 w-4"></i> Open Assistant
      </a>
    </div>
  </section>
```

- [ ] **Step 3: Run Messenger page boundary tests**

Run:

```powershell
.\env\Scripts\activate; if ($?) { python -m pytest dashboard/tests.py::test_messenger_settings_links_to_patient_assistant_without_ai_prompt_form dashboard/tests.py::test_owner_can_save_messenger_connection_app_credentials dashboard/tests.py::test_owner_save_messenger_connection_fetches_and_displays_page_name dashboard/tests.py::test_messenger_connection_rejects_page_id_mismatch_from_meta dashboard/tests.py::test_messenger_connection_saves_with_warning_when_page_name_fetch_fails dashboard/tests.py::test_messenger_settings_page_masks_saved_secrets_with_reveal_controls dashboard/tests.py::test_owner_can_reveal_saved_messenger_secret dashboard/tests.py::test_messenger_settings_mask_submission_keeps_saved_secrets dashboard/tests.py::test_staff_cannot_reveal_saved_messenger_secret -q }
```

Expected: PASS. The credential tests confirm Messenger page behavior remains intact after removing the shared AI form.

---

### Task 5: Full Targeted Verification

**Files:**
- No source edits expected.

- [ ] **Step 1: Run all dashboard tests**

Run:

```powershell
.\env\Scripts\activate; if ($?) { python -m pytest dashboard/tests.py -q }
```

Expected: PASS.

- [ ] **Step 2: Run widget AI tests to confirm runtime shared settings are unchanged**

Run:

```powershell
.\env\Scripts\activate; if ($?) { python -m pytest widget/tests.py -q }
```

Expected: PASS.

- [ ] **Step 3: Run Messenger AI context tests to confirm runtime shared settings are unchanged**

Run:

```powershell
.\env\Scripts\activate; if ($?) { python -m pytest messenger/tests.py::test_build_ai_context_uses_default_prompt_when_settings_missing messenger/tests.py::test_build_widget_ai_context_uses_shared_clinic_settings messenger/tests.py::test_build_ai_context_returns_only_page_clinic_data -q }
```

Expected: PASS.

- [ ] **Step 4: Run Django system check**

Run:

```powershell
.\env\Scripts\activate; if ($?) { python manage.py check }
```

Expected: `System check identified no issues`.

- [ ] **Step 5: Inspect diff before reporting**

Run:

```powershell
git diff -- clinics/forms.py messenger/forms.py dashboard/views.py templates/dashboard/assistant_settings.html dashboard/templates/dashboard/messenger_settings.html templates/dashboard/base.html dashboard/tests.py
```

Expected: diff only contains the settings boundary cleanup described in this plan. Do not commit unless the user explicitly asks for a commit.

---

## Spec Coverage Checklist

- Shared assistant settings move to `dashboard:assistant_settings`: Task 2 and Task 3.
- FAQs remain shared and copy reflects both channels: Task 3.
- Widget-only section keeps accent, welcome message, reason field, preview, and embed snippets: Task 3.
- Messenger page keeps only channel connection/setup and links to Assistant: Task 2 and Task 4.
- No duplicate shared AI prompt forms: Task 2 and Task 4.
- `widget_behavior_instructions` removed from visible widget settings: Task 1, Task 2, and Task 3.
- No database schema change: file structure and Task 5.
- Tenant and permission safety preserved: Task 1 and Task 2.
- Runtime n8n/widget/Messenger behavior unchanged: Task 5.
