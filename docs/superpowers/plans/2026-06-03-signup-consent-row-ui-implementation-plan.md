# Signup Consent Row UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the signup consent checkbox so it follows the existing Neon Aqua Clinical auth UI instead of rendering as a stacked form field.

**Architecture:** Keep the signup form and field definitions unchanged. Special-case only the `terms_accepted` field in `templates/accounts/signup.html`, rendering it as a soft bordered inline checkbox row while all other fields remain in the existing loop layout.

**Tech Stack:** Django template, Tailwind utility classes, existing `cf-*` CSS classes, pytest template assertions.

---

## File Structure

- Modify: `templates/accounts/signup.html` - special-case the consent checkbox row.
- Modify: `tests/test_design_system.py` - add a focused template regression test.

## Task 1: Consent Checkbox Row

**Files:**
- Modify: `templates/accounts/signup.html`
- Modify: `tests/test_design_system.py`

- [ ] **Step 1: Write the failing test**

Add a focused test to `tests/test_design_system.py`:

```python
def test_signup_terms_checkbox_uses_inline_soft_consent_row():
    template = source_text("templates/accounts/signup.html")

    assert "field.name == 'terms_accepted'" in template
    assert "rounded-[var(--cf-radius-md)] border border-[var(--cf-line)] bg-[var(--cf-surface-muted)]" in template
    assert "flex items-start gap-3" in template
    assert "text-sm leading-5 text-[var(--cf-muted)]" in template
```

- [ ] **Step 2: Run test to verify RED**

Run: `python -m pytest tests/test_design_system.py::test_signup_terms_checkbox_uses_inline_soft_consent_row -q`

Expected: FAIL because the template still renders every field with the generic stacked label.

- [ ] **Step 3: Implement the minimal template change**

In `templates/accounts/signup.html`, inside `{% for field in form %}`, branch on `terms_accepted`:

```django
{% if field.name == 'terms_accepted' %}
  <div class="rounded-[var(--cf-radius-md)] border border-[var(--cf-line)] bg-[var(--cf-surface-muted)] px-4 py-3">
    <label for="{{ field.id_for_label }}" class="flex items-start gap-3 cursor-pointer">
      <span class="mt-0.5 shrink-0">{{ field }}</span>
      <span class="text-sm leading-5 text-[var(--cf-muted)] normal-case tracking-normal">{{ field.label }}</span>
    </label>
    {% if field.errors %}
      <p class="mt-2 text-xs text-[var(--cf-status-cancelled-text)]">{{ field.errors.0 }}</p>
    {% endif %}
  </div>
{% else %}
  ...existing stacked field rendering...
{% endif %}
```

- [ ] **Step 4: Run focused verification**

Run: `python -m pytest tests/test_design_system.py::test_signup_terms_checkbox_uses_inline_soft_consent_row tests/test_design_system.py::test_public_auth_and_widget_button_labels_preserve_original_casing accounts/tests.py::test_signup_requires_terms_acceptance -q`

Expected: PASS.

## Self-Review

- Scope coverage: The plan only changes the consent checkbox rendering, matching the approved scope.
- Placeholder scan: No placeholders or deferred steps remain.
- Type consistency: Uses existing `field.name`, `field.id_for_label`, and `field.label` template APIs.
