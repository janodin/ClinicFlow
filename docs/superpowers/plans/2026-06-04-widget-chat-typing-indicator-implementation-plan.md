# Widget Chat Typing Indicator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an assistant typing indicator to the public booking widget chat while AI responses are loading.

**Architecture:** Keep the feature entirely inside the existing widget Django template and Alpine.js component. Add one Alpine boolean, render one assistant-style indicator bubble inside the existing conversation scroll container, and reuse the `chatConversation` ref for scroll-to-bottom behavior.

**Tech Stack:** Django templates, Alpine.js, Tailwind CSS utility classes, Django `TestCase`.

---

## File Structure

- Modify `templates/widget/widget.html`: add typing indicator markup, `isAssistantTyping` state, state reset handling, and a small scroll helper used by `sendChatAction()`.
- Modify `widget/tests.py`: add template regression coverage for typing indicator markup and request lifecycle behavior.
- Read `docs/superpowers/specs/2026-06-04-widget-chat-typing-indicator-design.md` before implementation.

## Task 1: Add Failing Typing Indicator Template Tests

**Files:**
- Modify: `widget/tests.py`

- [ ] **Step 1: Insert the failing tests after `test_widget_chat_scrolls_conversation_container_after_ai_reply`**

Add this code:

```python
    def test_widget_chat_renders_assistant_typing_indicator_inside_conversation(self):
        response = self.client.get(reverse("widget:home", args=[self.clinic.slug]))
        content = response.content.decode()

        conversation_start = content.index("<!-- Conversation -->")
        conversation_end = content.index("<!-- FAQs -->", conversation_start)
        conversation_markup = content[conversation_start:conversation_end]

        self.assertIn('x-show="isAssistantTyping"', conversation_markup)
        self.assertIn('role="status"', conversation_markup)
        self.assertIn('aria-live="polite"', conversation_markup)
        self.assertIn("Assistant is typing", conversation_markup)
        self.assertIn("animate-bounce", conversation_markup)

    def test_widget_chat_toggles_typing_indicator_around_ai_fetch(self):
        response = self.client.get(reverse("widget:home", args=[self.clinic.slug]))
        content = response.content.decode()

        self.assertIn("isAssistantTyping: false,", content)

        go_home_start = content.index("goHome() {")
        go_home_end = content.index("minimize()", go_home_start)
        go_home_block = content[go_home_start:go_home_end]
        self.assertIn("this.isAssistantTyping = false;", go_home_block)

        send_chat_start = content.index("async sendChatAction(")
        send_chat_end = content.index("selectChatOption", send_chat_start)
        send_chat_block = content[send_chat_start:send_chat_end]

        self.assertIn("this.isAssistantTyping = true;", send_chat_block)
        self.assertIn("try {", send_chat_block)
        self.assertIn("finally {", send_chat_block)
        self.assertIn("this.isAssistantTyping = false;", send_chat_block)
        self.assertLess(
            send_chat_block.index("this.isAssistantTyping = true;"),
            send_chat_block.index("const resp = await fetch"),
        )
        self.assertLess(
            send_chat_block.index("finally {"),
            send_chat_block.rindex("this.isAssistantTyping = false;"),
        )
        self.assertIn("this.scrollChatConversation();", send_chat_block)
```

- [ ] **Step 2: Run the new tests and verify they fail**

Run:

```powershell
.\env\Scripts\activate; if ($?) { python manage.py test widget.tests.WidgetTests.test_widget_chat_renders_assistant_typing_indicator_inside_conversation widget.tests.WidgetTests.test_widget_chat_toggles_typing_indicator_around_ai_fetch }
```

Expected: both tests fail because `isAssistantTyping`, the indicator markup, and `try/finally` lifecycle are not implemented yet.

## Task 2: Implement Typing Indicator in the Widget Template

**Files:**
- Modify: `templates/widget/widget.html`

- [ ] **Step 1: Add the typing indicator markup inside the conversation container**

Inside `templates/widget/widget.html`, insert this block after the `chatHistory` template and before the `chatOptions` block:

```html
          <div x-show="isAssistantTyping" class="flex justify-start" role="status" aria-live="polite">
            <div class="max-w-[85%] rounded-2xl border border-[var(--cf-line)] bg-white px-4 py-3 text-sm text-[var(--cf-ink)]">
              <span class="sr-only">Assistant is typing</span>
              <span class="inline-flex items-center gap-1" aria-hidden="true">
                <span class="h-1.5 w-1.5 animate-bounce rounded-full bg-[var(--cf-muted)]"></span>
                <span class="h-1.5 w-1.5 animate-bounce rounded-full bg-[var(--cf-muted)] [animation-delay:120ms]"></span>
                <span class="h-1.5 w-1.5 animate-bounce rounded-full bg-[var(--cf-muted)] [animation-delay:240ms]"></span>
              </span>
            </div>
          </div>
```

- [ ] **Step 2: Add typing state to the Alpine component**

Add this property after `chatInput: '',`:

```javascript
      isAssistantTyping: false,
```

- [ ] **Step 3: Reset typing state when returning home**

Add this line inside `goHome()` after `this.chatInput = '';`:

```javascript
        this.isAssistantTyping = false;
```

- [ ] **Step 4: Add a reusable chat scroll helper**

Insert this method before `sendChatAction(action, value, extra) {`:

```javascript
      scrollChatConversation() {
        this.$nextTick(() => {
          const container = this.$refs.chatConversation;
          if (container) container.scrollTop = container.scrollHeight;
        });
      },
```

- [ ] **Step 5: Wrap `sendChatAction()` request handling in `try/finally`**

Replace the body of `sendChatAction(action, value, extra) { ... }` with this implementation:

```javascript
      async sendChatAction(action, value, extra) {
        const stateResetVersion = this.stateResetVersion;
        const formData = new FormData();
        formData.append('action', action);
        if (value !== undefined && value !== null) formData.append('value', value);
        if (extra) {
          if (extra.full_name) formData.append('full_name', extra.full_name);
          if (extra.phone) formData.append('phone', extra.phone);
          if (extra.email) formData.append('email', extra.email);
        }
        this.isAssistantTyping = true;
        this.scrollChatConversation();
        try {
          const resp = await fetch('{% url "widget:chat_step" clinic.slug %}', {
            method: 'POST',
            body: formData,
            headers: {'X-CSRFToken': document.querySelector('[name=csrfmiddlewaretoken]').value}
          });
          const data = await resp.json();
          if (stateResetVersion !== this.stateResetVersion) return;
          this.chatState = data.state;
          this.chatOptions = data.options || [];
          if (data.message) {
            this.chatHistory.push({id: this.nextId++, role: 'assistant', text: data.message});
          }
        } finally {
          if (stateResetVersion === this.stateResetVersion) {
            this.isAssistantTyping = false;
            this.scrollChatConversation();
          }
        }
      },
```

- [ ] **Step 6: Remove the old inline scroll block**

The old block should no longer exist because `scrollChatConversation()` replaces it:

```javascript
        this.$nextTick(() => {
          const container = this.$refs.chatConversation;
          if (container) container.scrollTop = container.scrollHeight;
        });
```

## Task 3: Verify the Implementation

**Files:**
- Verify: `widget/tests.py`
- Verify: `templates/widget/widget.html`

- [ ] **Step 1: Run the new targeted tests**

Run:

```powershell
.\env\Scripts\activate; if ($?) { python manage.py test widget.tests.WidgetTests.test_widget_chat_renders_assistant_typing_indicator_inside_conversation widget.tests.WidgetTests.test_widget_chat_toggles_typing_indicator_around_ai_fetch }
```

Expected: both tests pass.

- [ ] **Step 2: Run the existing widget test module**

Run:

```powershell
.\env\Scripts\activate; if ($?) { python manage.py test widget }
```

Expected: all widget tests pass.

- [ ] **Step 3: Run Django system checks**

Run:

```powershell
.\env\Scripts\activate; if ($?) { python manage.py check }
```

Expected: `System check identified no issues (0 silenced).`

- [ ] **Step 4: Inspect the final diff without committing**

Run:

```powershell
git diff -- templates/widget/widget.html widget/tests.py docs/superpowers/specs/2026-06-04-widget-chat-typing-indicator-design.md docs/superpowers/plans/2026-06-04-widget-chat-typing-indicator-implementation-plan.md
```

Expected: only the typing indicator feature, regression tests, design spec, and implementation plan are changed. Do not create a git commit unless the user explicitly asks for one.

## Self-Review

- Spec coverage: the plan covers the in-conversation indicator, Alpine state, scroll behavior, stale reset behavior, no schema/backend changes, and widget test verification.
- Placeholder scan: no placeholder tasks or undefined implementation details remain.
- Type consistency: the state property is consistently named `isAssistantTyping`, and the scroll helper is consistently named `scrollChatConversation()`.
