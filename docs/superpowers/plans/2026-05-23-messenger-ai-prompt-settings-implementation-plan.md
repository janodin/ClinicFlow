# Messenger AI Prompt Settings Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add editable Messenger AI prompt controls to the KliniAssist Messenger settings page using the existing `MessengerAISettings` model.

**Architecture:** Reuse the existing Messenger settings dashboard route and split it into two POST forms using `_form`: one for Facebook connection credentials and one for Messenger AI behavior. Keep tenant safety in the view by deriving the `MessengerConnection` from the current clinic, never from submitted IDs. The n8n AI context endpoint already returns saved AI settings, so the implementation only needs dashboard form/view/template work and regression tests.

**Tech Stack:** Django, Django templates, pytest, Tailwind utility classes, existing KliniAssist `cf-*` and `ui-*` dashboard components.

**Git Policy:** Do not commit during execution unless the user explicitly requests commits. Use `git status` and `git diff` for review only.

---

## File Structure

- Modify: `dashboard/tests.py`
  - Add dashboard integration tests for rendering and saving Messenger AI settings.
  - Keep tests close to existing dashboard route tests because the feature is dashboard behavior.
- Modify: `messenger/forms.py`
  - Add `MessengerAISettingsForm`, a focused `ModelForm` for `is_ai_enabled`, `instructions`, and `fallback_message`.
  - Keep `MessengerConnectionForm` unchanged except for import additions.
- Modify: `dashboard/views.py`
  - Update `messenger_settings()` to instantiate both forms.
  - Save connection settings only for `_form=connection_settings`.
  - Save AI settings only for `_form=ai_settings` and only when a clinic-owned connection exists.
- Modify: `dashboard/templates/dashboard/messenger_settings.html`
  - Add hidden `_form` fields to distinguish POST actions.
  - Add the **Messenger AI Prompt** card below the Facebook Page Connection card.
  - Render disabled/informational state when no connection exists.
- Verify only: `messenger/ai_tools.py`
  - No code changes expected. Existing `build_ai_context()` already returns saved AI settings.

---

### Task 1: Add Dashboard Tests For Messenger AI Settings

**Files:**
- Modify: `dashboard/tests.py`

- [ ] **Step 1: Write failing tests**

Append these tests to `dashboard/tests.py` after the existing tests. Add the local imports inside each test to avoid broad top-level import churn.

```python

@pytest.mark.django_db
def test_messenger_settings_page_shows_ai_prompt_form(clinic_setup, client):
    from messenger.models import MessengerAISettings, MessengerConnection

    clinic, service, user = clinic_setup
    connection = MessengerConnection.objects.create(
        clinic=clinic,
        page_id="PAGE-DASH-AI",
        page_access_token="TOKEN-DASH-AI",
    )
    MessengerAISettings.objects.create(
        connection=connection,
        instructions="Use a warm clinic tone.",
        fallback_message="Please call the clinic.",
    )
    client.force_login(user)

    response = client.get(reverse("dashboard:messenger_settings"))

    assert response.status_code == 200
    assert b"Messenger AI Prompt" in response.content
    assert b"Prompt / Instructions" in response.content
    assert b"Use a warm clinic tone." in response.content
    assert b"Please call the clinic." in response.content


@pytest.mark.django_db
def test_owner_can_save_messenger_ai_settings(clinic_setup, client):
    from messenger.models import MessengerAISettings, MessengerConnection

    clinic, service, user = clinic_setup
    connection = MessengerConnection.objects.create(
        clinic=clinic,
        page_id="PAGE-DASH-SAVE",
        page_access_token="TOKEN-DASH-SAVE",
    )
    client.force_login(user)

    response = client.post(
        reverse("dashboard:messenger_settings"),
        {
            "_form": "ai_settings",
            "instructions": "Answer briefly and ask for confirmation before booking.",
            "fallback_message": "A staff member will help you soon.",
        },
    )

    assert response.status_code == 302
    assert response.url == reverse("dashboard:messenger_settings")
    settings = MessengerAISettings.objects.get(connection=connection)
    assert settings.is_ai_enabled is False
    assert settings.instructions == "Answer briefly and ask for confirmation before booking."
    assert settings.fallback_message == "A staff member will help you soon."


@pytest.mark.django_db
def test_owner_can_enable_messenger_ai_settings(clinic_setup, client):
    from messenger.models import MessengerAISettings, MessengerConnection

    clinic, service, user = clinic_setup
    connection = MessengerConnection.objects.create(
        clinic=clinic,
        page_id="PAGE-DASH-ENABLE",
        page_access_token="TOKEN-DASH-ENABLE",
    )
    client.force_login(user)

    response = client.post(
        reverse("dashboard:messenger_settings"),
        {
            "_form": "ai_settings",
            "is_ai_enabled": "on",
            "instructions": "Use a friendly clinic tone.",
            "fallback_message": "Please call us.",
        },
    )

    assert response.status_code == 302
    settings = MessengerAISettings.objects.get(connection=connection)
    assert settings.is_ai_enabled is True
    assert settings.instructions == "Use a friendly clinic tone."
    assert settings.fallback_message == "Please call us."


@pytest.mark.django_db
def test_staff_cannot_save_messenger_ai_settings(clinic_setup, client):
    from messenger.models import MessengerAISettings, MessengerConnection

    User = get_user_model()
    clinic, service, owner = clinic_setup
    staff = User.objects.create_user(username="staff@example.com", email="staff@example.com", password="password123")
    ClinicMembership.objects.create(clinic=clinic, user=staff, role=ClinicMembership.ROLE_STAFF)
    connection = MessengerConnection.objects.create(
        clinic=clinic,
        page_id="PAGE-DASH-STAFF",
        page_access_token="TOKEN-DASH-STAFF",
    )
    client.force_login(staff)

    response = client.post(
        reverse("dashboard:messenger_settings"),
        {
            "_form": "ai_settings",
            "is_ai_enabled": "on",
            "instructions": "Staff should not save this.",
            "fallback_message": "Blocked.",
        },
    )

    assert response.status_code == 403
    assert not MessengerAISettings.objects.filter(connection=connection).exists()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.\env\Scripts\python.exe -m pytest dashboard/tests.py -k "messenger_settings" -v`

Expected: FAIL. At least one failure should show missing `Messenger AI Prompt` content or the POST not creating `MessengerAISettings`.

- [ ] **Step 3: Review test diff**

Run: `git diff -- dashboard/tests.py`

Expected: Diff shows only the four new Messenger AI settings dashboard tests.

---

### Task 2: Add Messenger AI Settings Form

**Files:**
- Modify: `messenger/forms.py`

- [ ] **Step 1: Update imports and add the form**

Replace the import at the top of `messenger/forms.py`:

```python
from messenger.models import MessengerAISettings, MessengerConnection
```

Append this class after `MessengerConnectionForm`:

```python


class MessengerAISettingsForm(forms.ModelForm):
    class Meta:
        model = MessengerAISettings
        fields = ["is_ai_enabled", "instructions", "fallback_message"]
        widgets = {
            "is_ai_enabled": forms.CheckboxInput(attrs={
                "class": "h-4 w-4 rounded border-[var(--cf-line)] text-[var(--cf-brand)] focus:ring-[var(--cf-focus)]",
            }),
            "instructions": forms.Textarea(attrs={
                "class": "ui-input min-h-36",
                "placeholder": "Tell the Messenger AI how to speak, what clinic policies to follow, and what it should avoid.",
                "rows": 6,
            }),
            "fallback_message": forms.Textarea(attrs={
                "class": "ui-input min-h-24",
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
            "instructions": "Services, prices, and availability still come from KliniAssist.",
            "fallback_message": "Shown when AI replies are disabled or the AI cannot safely respond.",
        }
```

- [ ] **Step 2: Run focused dashboard tests**

Run: `.\env\Scripts\python.exe -m pytest dashboard/tests.py -k "messenger_settings" -v`

Expected: FAIL. The form exists, but the view and template do not use it yet.

- [ ] **Step 3: Review form diff**

Run: `git diff -- messenger/forms.py`

Expected: Diff shows the import update and the new `MessengerAISettingsForm` only.

---

### Task 3: Wire Messenger Settings View To Both Forms

**Files:**
- Modify: `dashboard/views.py:1226-1254`

- [ ] **Step 1: Replace `messenger_settings()` with dual-form handling**

Replace the existing `messenger_settings()` function with this implementation:

```python
@login_required
def messenger_settings(request):
    clinic = _clinic_or_redirect(request)
    membership = get_active_membership(request.user)
    if not user_can_manage_settings(membership):
        raise PermissionDenied
    from messenger.forms import MessengerAISettingsForm, MessengerConnectionForm
    from messenger.models import MessengerAISettings, MessengerConnection

    connection = getattr(clinic, "messenger_connection", None)
    ai_settings = None
    if connection:
        ai_settings, _ = MessengerAISettings.objects.get_or_create(connection=connection)

    if request.method == "POST" and request.POST.get("_form") == "connection_settings":
        form = MessengerConnectionForm(request.POST, instance=connection)
        ai_form = MessengerAISettingsForm(instance=ai_settings) if ai_settings else None
        if form.is_valid():
            connection = form.save(commit=False)
            connection.clinic = clinic
            connection.is_active = True
            connection.save()
            MessengerAISettings.objects.get_or_create(connection=connection)

            messages.success(request, "Messenger settings saved. Remember to configure the webhook in your Meta Developer Dashboard.")
            return redirect("dashboard:messenger_settings")
    elif request.method == "POST" and request.POST.get("_form") == "ai_settings":
        form = MessengerConnectionForm(instance=connection)
        if not connection:
            messages.error(request, "Save Facebook Page settings before configuring Messenger AI.")
            return redirect("dashboard:messenger_settings")
        ai_settings, _ = MessengerAISettings.objects.get_or_create(connection=connection)
        ai_form = MessengerAISettingsForm(request.POST, instance=ai_settings)
        if ai_form.is_valid():
            ai_form.save()
            messages.success(request, "Messenger AI prompt settings saved.")
            return redirect("dashboard:messenger_settings")
    else:
        form = MessengerConnectionForm(instance=connection)
        ai_form = MessengerAISettingsForm(instance=ai_settings) if ai_settings else None

    n8n_webhook_url = request.build_absolute_uri(reverse("messenger:n8n_webhook"))
    return render(request, "dashboard/messenger_settings.html", {
        "clinic": clinic,
        "connection": connection,
        "form": form,
        "ai_form": ai_form,
        "n8n_webhook_url": n8n_webhook_url,
    })
```

- [ ] **Step 2: Run focused dashboard tests**

Run: `.\env\Scripts\python.exe -m pytest dashboard/tests.py -k "messenger_settings" -v`

Expected: FAIL. POST behavior should now be closer, but the GET test still fails until the template renders the card.

- [ ] **Step 3: Review view diff**

Run: `git diff -- dashboard/views.py`

Expected: Diff shows only the `messenger_settings()` dual-form update.

---

### Task 4: Render Messenger AI Prompt Card

**Files:**
- Modify: `dashboard/templates/dashboard/messenger_settings.html`

- [ ] **Step 1: Add `_form` to the connection form**

Inside the existing connection form, immediately after `{% csrf_token %}`, add:

```django
      <input type="hidden" name="_form" value="connection_settings">
```

- [ ] **Step 2: Add Messenger AI Prompt card after the connection section**

Insert this section after the closing `</section>` for the Facebook Page Connection card and before the n8n Webhook card:

```django

  <!-- Messenger AI Prompt Card -->
  <section class="cf-card p-6">
    <div class="flex items-center gap-3 mb-4">
      <div class="cf-icon-box p-3">
        <i data-lucide="bot" class="h-5 w-5"></i>
      </div>
      <div>
        <h2 class="cf-section-title">Messenger AI Prompt</h2>
        <p class="mt-1 text-sm text-[var(--cf-muted)]">Control the instructions used by Minimax or any model connected in your n8n workflow.</p>
      </div>
    </div>

    {% if connection and ai_form %}
      <form method="post" action="{% url 'dashboard:messenger_settings' %}" class="grid gap-5">
        {% csrf_token %}
        <input type="hidden" name="_form" value="ai_settings">

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
          <label class="cf-label" for="{{ ai_form.instructions.id_for_label }}">{{ ai_form.instructions.label }}</label>
          {{ ai_form.instructions }}
          <p class="mt-1 text-xs text-[var(--cf-muted)]">Tell the Messenger AI how to speak, what clinic policies to follow, and what it should avoid. Services, prices, and availability still come from KliniAssist.</p>
          {% if ai_form.instructions.errors %}
            <p class="text-sm text-red-600 mt-1">{{ ai_form.instructions.errors.0 }}</p>
          {% endif %}
        </div>

        <div class="cf-field">
          <label class="cf-label" for="{{ ai_form.fallback_message.id_for_label }}">{{ ai_form.fallback_message.label }}</label>
          {{ ai_form.fallback_message }}
          <p class="mt-1 text-xs text-[var(--cf-muted)]">Shown when AI replies are disabled or the AI cannot safely respond.</p>
          {% if ai_form.fallback_message.errors %}
            <p class="text-sm text-red-600 mt-1">{{ ai_form.fallback_message.errors.0 }}</p>
          {% endif %}
        </div>

        <div class="pt-2">
          <button type="submit" class="cf-btn cf-btn-primary">
            <i data-lucide="save" class="h-4 w-4"></i> Save AI Prompt
          </button>
        </div>
      </form>
    {% else %}
      <div class="rounded-lg border border-[var(--cf-line)] bg-[var(--cf-surface-muted)] p-4 text-sm text-[var(--cf-muted)]">
        Save Facebook Page settings first before configuring the Messenger AI prompt.
      </div>
    {% endif %}
  </section>
```

- [ ] **Step 3: Run focused dashboard tests**

Run: `.\env\Scripts\python.exe -m pytest dashboard/tests.py -k "messenger_settings" -v`

Expected: PASS. All Messenger settings dashboard tests should pass.

- [ ] **Step 4: Review template diff**

Run: `git diff -- dashboard/templates/dashboard/messenger_settings.html`

Expected: Diff shows the `_form=connection_settings` hidden input and the new Messenger AI Prompt card.

---

### Task 5: Verify Existing n8n Context Still Returns Saved Prompt

**Files:**
- Verify: `messenger/ai_tools.py`
- Verify: `messenger/tests.py`

- [ ] **Step 1: Run existing Messenger AI context tests**

Run: `.\env\Scripts\python.exe -m pytest messenger/tests.py -k "ai_settings or build_ai_context" -v`

Expected: PASS. This confirms the saved prompt fields continue flowing to n8n context.

- [ ] **Step 2: Run full relevant test set**

Run: `.\env\Scripts\python.exe -m pytest dashboard/tests.py messenger/tests.py -v`

Expected: PASS.

- [ ] **Step 3: Run Django system check**

Run: `.\env\Scripts\python.exe manage.py check`

Expected: `System check identified no issues`.

- [ ] **Step 4: Confirm no migrations are needed**

Run: `.\env\Scripts\python.exe manage.py makemigrations --check --dry-run`

Expected: `No changes detected`.

- [ ] **Step 5: Review final working tree diff**

Run: `git diff -- dashboard/tests.py messenger/forms.py dashboard/views.py dashboard/templates/dashboard/messenger_settings.html`

Expected: Diff shows only intended Messenger AI prompt settings changes. Do not commit unless the user explicitly asks for a commit.

---

## Manual QA

- Log in as a clinic owner.
- Open Dashboard -> Messenger Settings.
- Save Page ID and Page Access Token if no active Messenger connection exists.
- Confirm the Messenger AI Prompt card appears.
- Uncheck `Enable AI replies`, enter prompt text, enter fallback text, and save.
- Confirm values remain populated after redirect.
- Check `/messenger/ai/context/` behavior through existing tests rather than manually exposing n8n secrets.

---

## Self-Review

- Spec coverage: The plan exposes AI enabled, prompt instructions, and fallback message; keeps credentials separate; derives connection from current clinic; reuses `MessengerAISettings`; preserves n8n context flow; adds permission and tenant-safety tests.
- Placeholder scan: No placeholders remain in task steps or code snippets.
- Type consistency: The form uses existing model fields `is_ai_enabled`, `instructions`, and `fallback_message`; the view passes `ai_form`; the template renders matching field names; tests query `MessengerAISettings` by clinic-owned `connection`.
- Git policy check: The plan uses diff review steps and does not instruct commits because this workspace only commits on explicit user request.
