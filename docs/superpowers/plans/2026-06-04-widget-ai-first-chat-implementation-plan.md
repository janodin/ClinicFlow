# Widget AI-First Chat Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make widget `Chat with Assistant` use the shared n8n AI agent/tool flow like Messenger AI mode, while keeping the separate guided `Book an Appointment` widget flow unchanged.

**Architecture:** `widget.views.chat_step()` becomes an AI-first proxy for the chat conversation when website Assistant AI is enabled. Django still resolves the public clinic, enforces CSRF, manages short widget chat history, and returns fallback when AI is disabled or unavailable. n8n remains the model/tool orchestrator and uses existing widget-safe Django tools for services, availability, and confirmed booking.

**Tech Stack:** Django, Django sessions, Django templates, Alpine.js widget UI, pytest/Django TestCase, requests, n8n Workflow SDK TypeScript source tests.

---

## Scope Check

This plan implements one focused subsystem: widget chat behavior. It does not remove the guided booking widget flow, add a new widget mode toggle, add medical records, add payments, or replace Django templates/Alpine/n8n.

## File Structure

- Modify: `widget/views.py` - replace chat conversation state-machine routing with AI-first chat handling; keep non-chat widget booking endpoints unchanged.
- Modify: `templates/widget/widget.html` - ensure chat suggestion buttons can send natural prompts through the AI path and never reveal the old guided chat form in AI mode.
- Modify: `widget/tests.py` - replace legacy chat state-machine expectations with AI-first chat tests and keep guided widget booking tests intact.
- Modify: `tests/test_n8n_combined_bridge_source.py` - strengthen assertions that widget chat uses the shared AI core, widget context, widget tools, and explicit-confirmation prompt.
- No model or migration changes are required.

---

### Task 1: Lock AI-First Widget Chat Backend Contract

**Files:**
- Modify: `widget/tests.py`
- Modify: `widget/views.py`

- [ ] **Step 1: Write failing AI-init and AI-suggestion tests**

In `widget/tests.py`, replace the legacy chat state-machine test `test_chat_step_state_machine_skips_doctor` with these tests:

```python
    @override_settings(ASSISTANT_N8N_WEBHOOK_URL="https://n8n.example/webhook/widget", N8N_WEBHOOK_SECRET="secret")
    @patch("widget.ai_client.requests.post")
    def test_chat_step_ai_init_does_not_enter_guided_state(self, mock_post):
        ClinicAISettings.objects.create(clinic=self.clinic, is_ai_enabled=True)

        response = self.client.post(reverse("widget:chat_step", args=[self.clinic.slug]), {"action": "init"})

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["state"], "ai")
        self.assertEqual(data["next_action"], "text_input")
        self.assertIn("book", data["message"].lower())
        self.assertIn({"label": "Book an appointment", "value": "I want to book an appointment", "type": "ai_prompt"}, data["options"])
        self.assertNotIn(data["state"], ["select_service", "select_date", "select_time", "collect_info", "confirm"])
        mock_post.assert_not_called()

    @override_settings(ASSISTANT_N8N_WEBHOOK_URL="https://n8n.example/webhook/widget", N8N_WEBHOOK_SECRET="secret")
    @patch("widget.ai_client.requests.post")
    def test_chat_step_ai_book_suggestion_calls_n8n_as_natural_text(self, mock_post):
        ClinicAISettings.objects.create(clinic=self.clinic, is_ai_enabled=True)
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {"reply": "Sure, what service would you like?"}

        response = self.client.post(
            reverse("widget:chat_step", args=[self.clinic.slug]),
            {"action": "select_option", "value": "I want to book an appointment"},
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["state"], "ai")
        self.assertEqual(data["message"], "Sure, what service would you like?")
        self.assertEqual(data["options"], [])
        self.assertEqual(data["next_action"], "text_input")
        payload = mock_post.call_args.kwargs["json"]
        self.assertEqual(payload["channel"], "widget")
        self.assertEqual(payload["clinic_slug"], self.clinic.slug)
        self.assertEqual(payload["message"], "I want to book an appointment")
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
.\env\Scripts\activate; if ($?) { python -m pytest widget/tests.py::WidgetTests::test_chat_step_ai_init_does_not_enter_guided_state widget/tests.py::WidgetTests::test_chat_step_ai_book_suggestion_calls_n8n_as_natural_text -q }
```

Expected: FAIL because `chat_step?action=init` currently returns `state: greeting`, and `select_option=start_booking` can enter the Django guided state machine rather than the AI path.

- [ ] **Step 3: Add AI response helpers in `widget/views.py`**

In `widget/views.py`, replace `_chat_date_options`, `_chat_controls_for_state`, and `_assistant_message_with_widget_context` with these AI-first helpers. Keep `_widget_chat_history()` and `_save_widget_chat_history()`.

```python
WIDGET_AI_STATE = "ai"
WIDGET_AI_SUGGESTIONS = [
    {"label": "Book an appointment", "value": "I want to book an appointment", "type": "ai_prompt"},
    {"label": "Ask about services", "value": "What services are available?", "type": "ai_prompt"},
]


def _widget_ai_json(message, options=None):
    return JsonResponse({
        "state": WIDGET_AI_STATE,
        "message": message,
        "options": options or [],
        "next_action": "text_input",
    })


def _widget_ai_fallback_message(ai_settings):
    message = fallback_message_for(ai_settings)
    if "book" not in message.lower():
        message = f"{message} You can still use Book an Appointment to schedule a visit."
    return message


def _widget_ai_initial_message(clinic):
    return clinic.widget_welcome_message or "Welcome! How can we help you book an appointment today?"


def _widget_ai_message_from_action(action, value):
    text = (value or "").strip()
    if text:
        return text
    if action == "start_booking":
        return "I want to book an appointment"
    if action == "view_faqs":
        return "I have a question about the clinic"
    return ""
```

- [ ] **Step 4: Add the AI-first chat handler in `widget/views.py`**

Add this function below the helpers from Step 3:

```python
def _handle_widget_ai_chat(request, clinic, action, value):
    ai_settings, _ = ClinicAISettings.objects.get_or_create(clinic=clinic)

    if not ai_settings.is_ai_enabled:
        return _widget_ai_json(_widget_ai_fallback_message(ai_settings))

    if action == "init":
        return _widget_ai_json(_widget_ai_initial_message(clinic), WIDGET_AI_SUGGESTIONS)

    message = _widget_ai_message_from_action(action, value)
    if not message:
        return _widget_ai_json(_widget_ai_initial_message(clinic), WIDGET_AI_SUGGESTIONS)

    history = _widget_chat_history(request, clinic)
    if not request.session.session_key:
        request.session.create()

    try:
        reply = call_assistant_webhook(clinic, message, history, request.session.session_key)
    except (AssistantUnavailable, requests.RequestException, ValueError):
        reply = _widget_ai_fallback_message(ai_settings)

    history.extend([
        {"role": "user", "content": message},
        {"role": "assistant", "content": reply},
    ])
    _save_widget_chat_history(request, clinic, history)
    return _widget_ai_json(reply)
```

- [ ] **Step 5: Route `chat_step()` through the AI-first handler**

In `widget/views.py`, replace the body of `chat_step()` with this implementation:

```python
@require_POST
def chat_step(request, clinic_slug):
    clinic = _get_public_clinic_or_404(clinic_slug)
    action = request.POST.get("action", "")
    value = request.POST.get("value", "")

    return _handle_widget_ai_chat(request, clinic, action, value)
```

Remove the old `session_key = f"widget_chat_{clinic.id}"` state-machine blocks for `greeting`, `select_service`, `select_date`, `select_time`, `collect_info`, and `confirm` from `chat_step()`. The separate guided booking widget flow does not use `chat_step()` and remains in `widget_book()`, `widget_slots()`, and the existing widget form JavaScript.

- [ ] **Step 6: Run tests to verify Task 1 passes**

Run:

```powershell
.\env\Scripts\activate; if ($?) { python -m pytest widget/tests.py::WidgetTests::test_chat_step_ai_init_does_not_enter_guided_state widget/tests.py::WidgetTests::test_chat_step_ai_book_suggestion_calls_n8n_as_natural_text -q }
```

Expected: `2 passed`.

- [ ] **Step 7: Commit Task 1**

```powershell
git add widget/views.py widget/tests.py
git commit -m "feat: make widget chat ai-first"
```

---

### Task 2: Update Widget Chat Tests For AI-First Behavior

**Files:**
- Modify: `widget/tests.py`

- [ ] **Step 1: Replace obsolete chat state-machine tests**

In `widget/tests.py`, remove these tests because `chat_step()` no longer owns deterministic booking:

- `test_chat_step_rejects_short_phone_before_confirmation`
- `test_chat_step_rejects_invalid_email_before_confirmation`
- `test_chat_step_cancel_at_confirmation_resets_without_booking`

After those tests are removed, remove `_drive_chat_to_collect_info()` from `WidgetTests`; the remaining tests should not call it.

Add this test near the other AI chat tests:

```python
    @override_settings(ASSISTANT_N8N_WEBHOOK_URL="https://n8n.example/webhook/widget", N8N_WEBHOOK_SECRET="secret")
    @patch("widget.ai_client.requests.post")
    def test_chat_step_ai_history_is_passed_and_capped(self, mock_post):
        ClinicAISettings.objects.create(clinic=self.clinic, is_ai_enabled=True)
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {"reply": "Reply from AI."}
        url = reverse("widget:chat_step", args=[self.clinic.slug])

        for index in range(7):
            self.client.post(url, {"action": "text_input", "value": f"Question {index}"})

        response = self.client.post(url, {"action": "text_input", "value": "Latest question"})

        self.assertEqual(response.status_code, 200)
        payload = mock_post.call_args.kwargs["json"]
        self.assertEqual(payload["message"], "Latest question")
        self.assertLessEqual(len(payload["history"]), 10)
        self.assertIn({"role": "assistant", "content": "Reply from AI."}, payload["history"])
```

- [ ] **Step 2: Update existing AI text-input tests**

In `widget/tests.py`, update `test_chat_step_text_input_calls_n8n_when_ai_enabled` so it asserts the AI state contract:

```python
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["state"], "ai")
        self.assertEqual(data["message"], "I can help you book.")
        self.assertEqual(data["options"], [])
        self.assertEqual(data["next_action"], "text_input")
        payload = mock_post.call_args.kwargs["json"]
        self.assertEqual(payload["channel"], "widget")
        self.assertEqual(payload["clinic_slug"], self.clinic.slug)
        self.assertEqual(payload["message"], "Can I book tomorrow?")
```

Replace `test_chat_step_text_input_calls_n8n_during_select_date` and `test_chat_step_text_input_calls_n8n_during_select_time` with this single regression test proving legacy state actions still route through AI:

```python
    @override_settings(ASSISTANT_N8N_WEBHOOK_URL="https://n8n.example/webhook/widget", N8N_WEBHOOK_SECRET="secret")
    @patch("widget.ai_client.requests.post")
    def test_chat_step_legacy_guided_actions_do_not_enter_guided_state_when_ai_enabled(self, mock_post):
        ClinicAISettings.objects.create(clinic=self.clinic, is_ai_enabled=True)
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {"reply": "AI is handling booking."}
        url = reverse("widget:chat_step", args=[self.clinic.slug])

        response = self.client.post(url, {"action": "start_booking"})

        data = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(data["state"], "ai")
        self.assertEqual(data["message"], "AI is handling booking.")
        self.assertEqual(data["next_action"], "text_input")
        self.assertEqual(data["options"], [])
        payload = mock_post.call_args.kwargs["json"]
        self.assertEqual(payload["message"], "I want to book an appointment")
```

- [ ] **Step 3: Update AI-disabled fallback test**

In `widget/tests.py`, replace `test_chat_step_returns_fallback_without_n8n_when_ai_disabled` with this version. It covers both initial chat load and typed messages for AI-disabled clinics:

```python
    @override_settings(ASSISTANT_N8N_WEBHOOK_URL="https://n8n.example/webhook/widget", N8N_WEBHOOK_SECRET="secret")
    @patch("widget.ai_client.requests.post")
    def test_chat_step_returns_fallback_without_n8n_when_ai_disabled(self, mock_post):
        ClinicAISettings.objects.create(
            clinic=self.clinic,
            is_ai_enabled=False,
            instructions="Shared instructions.",
            fallback_message="AI is off. Please use the booking form.",
        )
        url = reverse("widget:chat_step", args=[self.clinic.slug])

        for post_data in ({"action": "init"}, {"action": "text_input", "value": "Hello"}):
            with self.subTest(post_data=post_data):
                response = self.client.post(url, post_data)

                self.assertEqual(response.status_code, 200)
                data = response.json()
                self.assertEqual(data["state"], "ai")
                self.assertIn("AI is off. Please use the booking form.", data["message"])
                self.assertEqual(data["options"], [])
                self.assertEqual(data["next_action"], "text_input")

        mock_post.assert_not_called()
```

Update `test_chat_step_returns_default_fallback_when_webhook_missing`:

```python
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["state"], "ai")
        self.assertIn("assistant is unavailable", data["message"])
        self.assertEqual(data["options"], [])
```

- [ ] **Step 4: Run widget tests**

Run:

```powershell
.\env\Scripts\activate; if ($?) { python -m pytest widget/tests.py -q }
```

Expected: all widget tests pass after the three named legacy `chat_step()` booking-state tests are removed, `_drive_chat_to_collect_info()` is removed, and the AI-first assertions above are applied. Guided booking tests that exercise `widget_book()` or `widget_slots()` remain in place and pass.

- [ ] **Step 5: Commit Task 2**

```powershell
git add widget/tests.py
git commit -m "test: update widget chat ai expectations"
```

---

### Task 3: Keep Widget Frontend In AI Conversation Mode

**Files:**
- Modify: `templates/widget/widget.html`
- Modify: `widget/tests.py`

- [ ] **Step 1: Add failing template contract test**

In `widget/tests.py`, add this test near `test_widget_home_loads_without_doctor_controls`:

```python
    def test_widget_chat_suggestions_route_as_ai_prompts(self):
        response = self.client.get(reverse("widget:home", args=[self.clinic.slug]))
        content = response.content.decode()

        self.assertIn("opt.type === 'ai_prompt'", content)
        self.assertIn("this.sendChatAction('text_input', opt.value);", content)
        self.assertIn("chatState !== 'collect_info'", content)
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```powershell
.\env\Scripts\activate; if ($?) { python -m pytest widget/tests.py::WidgetTests::test_widget_chat_suggestions_route_as_ai_prompts -q }
```

Expected: FAIL because `selectChatOption()` currently sends all non-FAQ/non-restart options as `select_option`.

- [ ] **Step 3: Update `selectChatOption()` in `templates/widget/widget.html`**

Replace the current `selectChatOption(opt)` body with this version:

```javascript
      selectChatOption(opt) {
        this.chatHistory.push({id: this.nextId++, role: 'user', text: opt.label});
        this.chatOptions = [];
        if (opt.value === 'restart') {
          this.chatHistory = [];
          this.sendChatAction('init');
          return;
        }
        if (opt.type === 'faq') {
          const faqId = parseInt(opt.value.split(':')[1], 10);
          const faq = this.faqs.find(f => f.id === faqId);
          if (faq) {
            this.chatHistory.push({id: this.nextId++, role: 'assistant', text: faq.answer});
          }
          this.sendChatAction('init');
          return;
        }
        if (opt.type === 'ai_prompt') {
          this.sendChatAction('text_input', opt.value);
          return;
        }
        this.sendChatAction('text_input', opt.value || opt.label);
      },
```

Do not remove the `collect_info` markup in this task. It should remain hidden because AI-first responses use `state: "ai"`, and this plan intentionally avoids extra template cleanup.

- [ ] **Step 4: Run template contract and widget tests**

Run:

```powershell
.\env\Scripts\activate; if ($?) { python -m pytest widget/tests.py -q }
```

Expected: all widget tests pass.

- [ ] **Step 5: Commit Task 3**

```powershell
git add templates/widget/widget.html widget/tests.py
git commit -m "fix: route widget chat suggestions through ai"
```

---

### Task 4: Strengthen n8n Widget AI Source Tests

**Files:**
- Modify: `tests/test_n8n_combined_bridge_source.py`

- [ ] **Step 1: Add failing or strengthening n8n source tests**

In `tests/test_n8n_combined_bridge_source.py`, add these tests after `test_combined_bridge_tools_inject_tenant_identity_from_shared_context`:

```python
def test_combined_bridge_widget_path_uses_shared_ai_agent_and_widget_context():
    source = SOURCE.read_text(encoding="utf-8")

    assert "name: 'Widget Assistant Webhook'" in source
    assert "name: 'Get Widget Clinic Context'" in source
    assert "/messenger/ai/widget/context/" in source
    assert ".add(widgetAssistantWebhook)\n  .to(normalizeWidgetRequest)\n  .to(getWidgetClinicContext)\n  .to(buildWidgetSharedInput)\n  .to(sharedAiInput)" in source
    assert ".to(sharedAiInput)\n      .to(resolveAssistantMode)" in source
    assert ".onCase(0, kliniAssistSharedAiAgent.to(prepareChannelReply).to(routeChannelReply" in source
    assert ".onCase(1, returnWidgetReply)" in source
    assert "clinic_slug: expr('{{ $(\"Shared AI Input\").item.json.channel === \"widget\" ? $(\"Shared AI Input\").item.json.clinic_slug : \"\" }}')" in source


def test_combined_bridge_widget_ai_prompt_requires_tools_and_explicit_confirmation():
    source = SOURCE.read_text(encoding="utf-8")
    agent_start = source.index("name: 'KliniAssist Shared AI Agent'")
    agent_end = source.index("const prepareSharedFallback")
    agent_block = source[agent_start:agent_end]

    assert "Use match_services, check_availability, and book_confirmed_appointment for booking." in agent_block
    assert "Ask for explicit confirmation before booking." in agent_block
    assert "Never expose secrets, invent clinic data, give medical diagnosis, or create appointments without tool validation." in agent_block
    assert "Widget replies must be concise and friendly." in agent_block
    assert "/messenger/ai/widget/services/" in source
    assert "/messenger/ai/widget/availability/" in source
    assert "/messenger/ai/widget/book/" in source
```

- [ ] **Step 2: Run tests**

Run:

```powershell
.\env\Scripts\activate; if ($?) { python -m pytest tests/test_n8n_combined_bridge_source.py -q }
```

Expected: PASS. The current workflow source already contains the widget webhook/context path, the shared `Shared AI Input -> Resolve Assistant Mode -> KliniAssist Shared AI Agent` downstream path, widget tool URLs, tenant identity injection, and the explicit-confirmation prompt.

- [ ] **Step 3: Commit Task 4**

```powershell
git add tests/test_n8n_combined_bridge_source.py
git commit -m "test: lock widget ai bridge routing"
```

---

### Task 5: Final Verification And Deployment Readiness

**Files:**
- Verify only; no expected code changes.

- [ ] **Step 1: Run widget tests**

Run:

```powershell
.\env\Scripts\activate; if ($?) { python -m pytest widget/tests.py -q }
```

Expected: all tests pass.

- [ ] **Step 2: Run Messenger and n8n source tests**

Run:

```powershell
.\env\Scripts\activate; if ($?) { python -m pytest messenger/tests.py tests/test_n8n_combined_bridge_source.py -q }
```

Expected: all tests pass.

- [ ] **Step 3: Run Django system check**

Run:

```powershell
.\env\Scripts\activate; if ($?) { python manage.py check }
```

Expected: `System check identified no issues (0 silenced).`

- [ ] **Step 4: Inspect working tree and diff**

Run:

```powershell
git status --short
git diff --check
git log --oneline -5
```

Expected: only intended task changes are committed or staged. `git diff --check` reports no whitespace errors. Existing unrelated local changes must not be reverted or included unless explicitly requested.

- [ ] **Step 5: Manual smoke test guidance**

After deployment or local server startup, smoke test:

1. Open a public widget page.
2. Click `Chat with Assistant`.
3. Confirm greeting appears with local suggestion chips.
4. Click `Book an appointment` suggestion.
5. Confirm the network request posts `action=text_input` and a natural prompt to `widget:chat_step`.
6. Confirm the reply is AI text and the chat does not display the old full-name/phone inline form unless the separate guided booking flow is used.
7. Click `Book an Appointment` from the widget home and verify the original guided service/date/time/patient form still works.

- [ ] **Step 6: Leave verification state unchanged**

No commit is required if all previous tasks are committed and no files changed during verification.
