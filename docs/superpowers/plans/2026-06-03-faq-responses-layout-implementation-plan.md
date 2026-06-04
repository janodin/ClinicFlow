# FAQ Responses Layout Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Redesign the dashboard FAQ Responses section into an approved split composer plus FAQ card list layout with icon-only Edit/Delete controls.

**Architecture:** Keep the existing Django view, form, HTMX partial replacement, and delete modal behavior. Add explicit FAQ counts to the Assistant Settings context, update the FAQ section template structure, promote the row partial into a card, and add focused FAQ layout classes in `static/css/clinicflow.css`.

**Tech Stack:** Django views/templates, HTMX, Alpine.js, Tailwind utility classes, shared `cf-*` CSS layer, pytest design-system tests.

**Repo Policy:** Do not commit unless the user explicitly requests a commit.

---

## File Structure

- Modify `tests/test_design_system.py`: update FAQ-specific regression tests before implementation to capture the new split layout, icon-only Edit/Delete controls, accessibility labels, and wrapping guards.
- Modify `dashboard/views.py`: provide `faq_total_count` and `faq_visible_count` in the Assistant Settings template context, including invalid FAQ-create renders.
- Modify `templates/dashboard/assistant_settings.html`: replace the current flat FAQ section with the approved split composer/list layout while keeping the existing form action, CSRF, and fields.
- Modify `templates/dashboard/partials/faq_row.html`: convert each row into a card, preserve `id="faq-row-{{ faq.id }}"`, preserve HTMX targets, keep inline edit, use icon-only Edit/Delete, and keep visibility explicit.
- Modify `static/css/clinicflow.css`: add focused `cf-faq-*` component classes for the section header, responsive split layout, composer panel, card rows, status badges, and icon actions.

---

### Task 1: Add Failing FAQ Design-System Tests

**Files:**
- Modify: `tests/test_design_system.py`
- Test: `tests/test_design_system.py`

- [ ] **Step 1: Replace the old FAQ accessibility/action tests**

Replace the current `test_task_3_faq_row_controls_are_accessible` and `test_faq_row_actions_use_comfortable_compact_size` with these tests:

```python
def test_faq_section_uses_split_composer_layout():
    template = source_text("templates/dashboard/assistant_settings.html")

    assert "cf-faq-shell" in template
    assert "cf-faq-header" in template
    assert "cf-faq-layout" in template
    assert "cf-faq-composer" in template
    assert "cf-faq-list" in template
    assert "{{ faq_total_count }}" in template
    assert "{{ faq_visible_count }}" in template
    assert "Patient-facing assistant copy" in template
    assert "Visible to patients" in template


def test_faq_row_controls_are_accessible_icon_actions():
    template = partial_text("faq_row.html")

    assert "for=\"faq-question-{{ faq.id }}\"" in template
    assert "id=\"faq-question-{{ faq.id }}\"" in template
    assert "for=\"faq-answer-{{ faq.id }}\"" in template
    assert "id=\"faq-answer-{{ faq.id }}\"" in template
    assert "aria-label=\"{% if faq.is_active %}Hide FAQ from patients{% else %}Show FAQ to patients{% endif %}\"" in template
    assert "aria-label=\"Edit FAQ\"" in template
    assert "title=\"Edit FAQ\"" in template
    assert "aria-label=\"Delete FAQ\"" in template
    assert "title=\"Delete FAQ\"" in template
    assert "data-lucide=\"pencil\"" in template
    assert "data-lucide=\"trash-2\"" in template
    assert "cf-faq-icon-action" in template
    assert "aria-hidden=\"true\"></i>Edit" not in template
    assert "aria-hidden=\"true\"></i>Delete" not in template
    assert "{% if faq.is_active %}Visible{% else %}Hidden{% endif %}" in template


def test_faq_icon_actions_use_accessible_compact_size():
    stylesheet = css_text()
    template = partial_text("faq_row.html")
    action_block = css_rule_block(".cf-faq-icon-action")
    icon_block = css_rule_block(".cf-faq-icon-action svg")

    assert "cf-faq-icon-actions" in template
    assert "width: 2rem;" in action_block
    assert "height: 2rem;" in action_block
    assert "border-radius: var(--cf-radius-pill);" in action_block
    assert "width: .95rem;" in icon_block
    assert "height: .95rem;" in icon_block
    assert ".cf-faq-delete-action" in stylesheet
    assert "color: var(--cf-danger);" in css_rule_block(".cf-faq-delete-action")
```

- [ ] **Step 2: Update the mobile wrapping regression**

In `test_mobile_responsive_dynamic_text_has_wrapping_guards`, replace the old FAQ row layout assertion:

```python
assert "flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between" in faq_row
```

With these assertions:

```python
assert "cf-faq-card" in faq_row
assert "min-w-0" in faq_row
assert "break-words" in faq_row
assert "whitespace-pre-wrap" in faq_row
assert "cf-faq-layout" in assistant_settings
```

- [ ] **Step 3: Run tests to verify they fail before implementation**

Run:

```powershell
.\env\Scripts\python -m pytest tests/test_design_system.py::test_faq_section_uses_split_composer_layout tests/test_design_system.py::test_faq_row_controls_are_accessible_icon_actions tests/test_design_system.py::test_faq_icon_actions_use_accessible_compact_size tests/test_design_system.py::test_mobile_responsive_dynamic_text_has_wrapping_guards -q
```

Expected: FAIL because the templates and CSS do not yet contain the new `cf-faq-*` layout and icon-action classes.

---

### Task 2: Provide FAQ Counts In The View Context

**Files:**
- Modify: `dashboard/views.py`
- Test: `tests/test_design_system.py`

- [ ] **Step 1: Add a small context helper near `assistant_settings`**

Add this helper above `assistant_settings`:

```python
def _assistant_settings_context(request, clinic, *, widget_form=None, faq_form=None):
    faqs = clinic.faqs.all()
    iframe_url = _embedded_iframe_url(request, clinic)
    script_url = request.build_absolute_uri(reverse("widget:embed_js", args=[clinic.slug]))
    return {
        "clinic": clinic,
        "widget_form": widget_form or WidgetSettingsForm(instance=clinic),
        "faq_form": faq_form or ClinicFAQForm(),
        "faqs": faqs,
        "faq_total_count": faqs.count(),
        "faq_visible_count": faqs.filter(is_active=True).count(),
        "iframe_url": iframe_url,
        "script_url": script_url,
    }
```

- [ ] **Step 2: Use the helper in `assistant_settings`**

Replace the context-building block at the end of `assistant_settings` with:

```python
    return render(
        request,
        "dashboard/assistant_settings.html",
        _assistant_settings_context(request, clinic, widget_form=widget_form, faq_form=faq_form),
    )
```

- [ ] **Step 3: Use the helper for invalid FAQ creation**

Replace the invalid `create_faq` render line with:

```python
    return render(request, "dashboard/assistant_settings.html", _assistant_settings_context(request, clinic, faq_form=form))
```

- [ ] **Step 4: Run a Django check**

Run:

```powershell
.\env\Scripts\python manage.py check
```

Expected: PASS with no system check issues.

---

### Task 3: Implement The Split FAQ Section Template

**Files:**
- Modify: `templates/dashboard/assistant_settings.html`
- Test: `tests/test_design_system.py`

- [ ] **Step 1: Replace the current FAQ `<section>` block**

Replace lines beginning with:

```html
  <section class="cf-card p-6">
    <h2 class="cf-section-title">FAQ Responses</h2>
```

Through the matching closing `</section>` for FAQ Responses with:

```html
  <section class="cf-card cf-faq-shell">
    <div class="cf-faq-header">
      <div class="min-w-0">
        <p class="cf-eyebrow">
          <span class="cf-faq-header-icon"><i data-lucide="message-circle-question" class="h-4 w-4" aria-hidden="true"></i></span>
          Patient-facing assistant copy
        </p>
        <h2 class="cf-section-title mt-2">FAQ Responses</h2>
        <p class="cf-page-description max-w-2xl">Create short answers that appear in the booking widget and help patients self-serve common questions before booking.</p>
      </div>
      <div class="cf-faq-summary" aria-label="FAQ response summary">
        <span class="cf-faq-summary-pill">{{ faq_total_count }} FAQ{{ faq_total_count|pluralize }}</span>
        <span class="cf-faq-summary-pill cf-faq-summary-pill-active">{{ faq_visible_count }} visible</span>
      </div>
    </div>

    <div class="cf-faq-layout">
      <form method="post" action="{% url 'dashboard:create_faq' %}" class="cf-faq-composer">
        {% csrf_token %}
        <div class="cf-faq-composer-header">
          <div class="cf-icon-box cf-faq-composer-icon">
            <i data-lucide="plus-circle" class="h-5 w-5" aria-hidden="true"></i>
          </div>
          <div class="min-w-0">
            <h3 class="text-base font-semibold text-[var(--cf-ink)]">Add FAQ</h3>
            <p class="text-sm text-[var(--cf-muted)]">Keep answers direct and patient-friendly.</p>
          </div>
        </div>

        <div class="cf-field">
          <label for="{{ faq_form.question.id_for_label }}" class="cf-label">{{ faq_form.question.label }}</label>
          {{ faq_form.question }}
          {% if faq_form.question.errors %}<p class="cf-error">{{ faq_form.question.errors.0 }}</p>{% endif %}
        </div>

        <div class="cf-field">
          <label for="{{ faq_form.answer.id_for_label }}" class="cf-label">{{ faq_form.answer.label }}</label>
          {{ faq_form.answer }}
          {% if faq_form.answer.errors %}<p class="cf-error">{{ faq_form.answer.errors.0 }}</p>{% endif %}
        </div>

        <div class="cf-faq-composer-footer">
          <label class="cf-faq-checkbox-row">
            {{ faq_form.is_active }}
            <span>Visible to patients</span>
          </label>
          {% if faq_form.is_active.errors %}<p class="cf-error">{{ faq_form.is_active.errors.0 }}</p>{% endif %}
          <button class="cf-btn cf-btn-primary" type="submit">
            <i data-lucide="plus-circle" class="h-4 w-4" aria-hidden="true"></i>Add FAQ
          </button>
        </div>
      </form>

      <div class="cf-faq-list">
        <div class="cf-faq-list-header">
          <p class="cf-kpi-label">Current responses</p>
          <p class="text-xs text-[var(--cf-muted)]">Inline edit stays in-row.</p>
        </div>

        {% if faqs %}
          <div class="grid gap-3">
            {% for faq in faqs %}
              {% include "dashboard/partials/faq_row.html" with faq=faq faq_form=None %}
            {% endfor %}
          </div>
        {% else %}
          <div class="cf-empty-state cf-faq-empty-state">
            <div class="cf-icon-box h-12 w-12 mb-3">
              <i data-lucide="message-circle-question" class="h-6 w-6" aria-hidden="true"></i>
            </div>
            <p class="cf-section-title">No FAQs yet</p>
            <p class="mt-1 text-sm text-[var(--cf-muted)]">Add common questions to help patients book faster.</p>
          </div>
        {% endif %}
      </div>
    </div>
  </section>
```

- [ ] **Step 2: Run the section layout test**

Run:

```powershell
.\env\Scripts\python -m pytest tests/test_design_system.py::test_faq_section_uses_split_composer_layout -q
```

Expected: PASS after Task 2 and this template change are complete.

---

### Task 4: Convert FAQ Row Partial Into A Card With Icon Actions

**Files:**
- Modify: `templates/dashboard/partials/faq_row.html`
- Test: `tests/test_design_system.py`

- [ ] **Step 1: Replace the outer row view/edit structure**

Replace the current top-level `<div id="faq-row-{{ faq.id }}" class="py-3" ...>` through the end of the action cluster, keeping the existing delete modal after it, with this structure:

```html
<article id="faq-row-{{ faq.id }}" class="cf-faq-card {% if not faq.is_active %}cf-faq-card-muted{% endif %}"
         x-data="{ editing: {{ editing|default:False|yesno:'true,false' }}, deleting: false, myId: {{ faq.id }} }"
         @faq-edit-start.window="if ($event.detail.id !== myId) editing = false">
  <div class="min-w-0">
    <!-- View Mode -->
    <div x-show="!editing">
      <div class="flex items-start gap-3">
        <span class="cf-faq-question-icon" aria-hidden="true">Q</span>
        <div class="min-w-0 flex-1">
          <div class="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
            <p class="min-w-0 break-words text-sm font-semibold text-[var(--cf-ink)]">{{ faq.question }}</p>
            <span class="cf-faq-status {% if faq.is_active %}cf-faq-status-visible{% else %}cf-faq-status-hidden{% endif %}">
              <i data-lucide="{% if faq.is_active %}eye{% else %}eye-off{% endif %}" class="h-3 w-3 shrink-0" aria-hidden="true"></i>
              {% if faq.is_active %}Visible{% else %}Hidden{% endif %}
            </span>
          </div>
          <p class="mt-2 break-words text-sm text-[var(--cf-muted)] whitespace-pre-wrap">{{ faq.answer }}</p>
        </div>
      </div>
    </div>

    <!-- Edit Mode -->
    <form x-show="editing"
          hx-post="{% url 'dashboard:edit_faq' faq.id %}"
          hx-target="#faq-row-{{ faq.id }}"
          hx-swap="outerHTML"
          class="w-full space-y-3">
      {% csrf_token %}
      <div class="cf-field">
        <label for="faq-question-{{ faq.id }}" class="cf-label">Question</label>
        <input id="faq-question-{{ faq.id }}" type="text" name="question"
               value="{% if faq_form %}{{ faq_form.question.value|default:'' }}{% else %}{{ faq.question }}{% endif %}"
               class="cf-input"
               required>
        {% if faq_form and faq_form.question.errors %}
          <p class="cf-error">{{ faq_form.question.errors.0 }}</p>
        {% endif %}
      </div>

      <div class="cf-field">
        <label for="faq-answer-{{ faq.id }}" class="cf-label">Answer</label>
        <textarea id="faq-answer-{{ faq.id }}" name="answer" rows="3"
                  class="cf-textarea"
                  required>{% if faq_form %}{{ faq_form.answer.value|default:'' }}{% else %}{{ faq.answer }}{% endif %}</textarea>
        {% if faq_form and faq_form.answer.errors %}
          <p class="cf-error">{{ faq_form.answer.errors.0 }}</p>
        {% endif %}
      </div>

      <div class="flex flex-wrap items-center gap-2">
        <button class="cf-btn cf-btn-sm cf-btn-primary" type="submit">
          <i data-lucide="save" class="h-4 w-4" aria-hidden="true"></i>Save Changes
        </button>
        <button @click.prevent="editing = false" class="cf-btn cf-btn-sm cf-btn-ghost text-[var(--cf-muted)]" type="button">
          <i data-lucide="x-circle" class="h-4 w-4" aria-hidden="true"></i>Cancel
        </button>
      </div>
    </form>
  </div>

  <!-- Actions (View Mode) -->
  <div class="cf-row-actions cf-row-actions-start cf-faq-card-actions" x-show="!editing">
    <button hx-post="{% url 'dashboard:toggle_faq' faq.id %}"
            hx-target="#faq-row-{{ faq.id }}"
            hx-swap="outerHTML"
            hx-headers='{"X-CSRFToken": "{{ csrf_token }}"}'
            class="cf-btn cf-btn-xs {% if faq.is_active %}cf-btn-muted{% else %}cf-btn-secondary{% endif %}"
            type="button"
            aria-label="{% if faq.is_active %}Hide FAQ from patients{% else %}Show FAQ to patients{% endif %}"
            title="{% if faq.is_active %}Hide from patients{% else %}Show to patients{% endif %}">
      <i data-lucide="{% if faq.is_active %}eye-off{% else %}eye{% endif %}" class="h-3 w-3 shrink-0" aria-hidden="true"></i>{% if faq.is_active %}Hide{% else %}Show{% endif %}
    </button>
    <div class="cf-faq-icon-actions">
      <button @click="$dispatch('faq-edit-start', {id: myId}); editing = true" class="cf-icon-btn cf-faq-icon-action cf-faq-edit-action" type="button" aria-label="Edit FAQ" title="Edit FAQ">
        <i data-lucide="pencil" class="h-4 w-4" aria-hidden="true"></i>
      </button>
      <button @click="deleting = true" class="cf-icon-btn cf-faq-icon-action cf-faq-delete-action" type="button" aria-label="Delete FAQ" title="Delete FAQ">
        <i data-lucide="trash-2" class="h-4 w-4" aria-hidden="true"></i>
      </button>
    </div>
  </div>
```

- [ ] **Step 2: Update the top-level closing tag**

Because the outer element is now an `<article>`, replace the final closing tag of the partial from:

```html
</div>
```

To:

```html
</article>
```

Keep the delete modal markup inside the article so it still has access to Alpine state.

- [ ] **Step 3: Run FAQ row tests**

Run:

```powershell
.\env\Scripts\python -m pytest tests/test_design_system.py::test_faq_row_controls_are_accessible_icon_actions tests/test_design_system.py::test_mobile_responsive_dynamic_text_has_wrapping_guards -q
```

Expected: PASS after this partial change and Task 1 test updates are complete.

---

### Task 5: Add FAQ Layout CSS

**Files:**
- Modify: `static/css/clinicflow.css`
- Test: `tests/test_design_system.py`

- [ ] **Step 1: Add FAQ component styles after the form/error styles**

Insert this CSS after the existing `.cf-form-error` block:

```css
.cf-faq-shell {
  display: grid;
  gap: 1.25rem;
}

.cf-faq-header {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-start;
  justify-content: space-between;
  gap: 1rem;
}

.cf-faq-header-icon {
  display: inline-grid;
  width: 1.75rem;
  height: 1.75rem;
  place-items: center;
  border: 1px solid var(--cf-line);
  border-radius: var(--cf-radius-pill);
  background: var(--cf-brand-soft);
  color: var(--cf-brand);
}

.cf-faq-summary {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: .5rem;
}

.cf-faq-summary-pill,
.cf-faq-status {
  display: inline-flex;
  align-items: center;
  gap: .35rem;
  border-radius: var(--cf-radius-pill);
  padding: .35rem .6rem;
  font-size: .75rem;
  font-weight: 500;
  line-height: 1;
  white-space: nowrap;
}

.cf-faq-summary-pill {
  border: 1px solid var(--cf-line);
  background: var(--cf-surface);
  color: var(--cf-muted);
}

.cf-faq-summary-pill-active,
.cf-faq-status-visible {
  border: 1px solid var(--cf-brand-soft);
  background: var(--cf-brand-soft);
  color: var(--cf-brand-strong);
}

.cf-faq-layout {
  display: grid;
  grid-template-columns: minmax(260px, .82fr) minmax(0, 1.18fr);
  align-items: flex-start;
  gap: 1.125rem;
}

.cf-faq-composer {
  display: grid;
  gap: 1rem;
  border: 1px solid var(--cf-line);
  border-radius: var(--cf-radius-lg);
  background: var(--cf-bg-strong);
  padding: 1rem;
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, .85);
}

.cf-faq-composer-header {
  display: flex;
  align-items: center;
  gap: .75rem;
}

.cf-faq-composer-icon {
  width: 2.25rem;
  height: 2.25rem;
  border: 1px solid var(--cf-line);
  border-radius: var(--cf-radius-lg);
  flex-shrink: 0;
}

.cf-faq-composer-footer {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: .75rem;
}

.cf-faq-checkbox-row {
  display: inline-flex;
  align-items: center;
  gap: .5rem;
  color: var(--cf-ink-secondary);
  font-size: .875rem;
  cursor: pointer;
}

.cf-faq-list {
  display: grid;
  min-width: 0;
  gap: .75rem;
}

.cf-faq-list-header {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: .5rem;
}

.cf-faq-card {
  display: grid;
  min-width: 0;
  gap: .75rem;
  border: 1px solid var(--cf-line);
  border-radius: var(--cf-radius-lg);
  background: var(--cf-surface);
  padding: .875rem;
  box-shadow: var(--cf-shadow-card);
}

.cf-faq-question-icon {
  display: inline-grid;
  width: 1.75rem;
  height: 1.75rem;
  place-items: center;
  border-radius: var(--cf-radius-pill);
  background: var(--cf-brand-soft);
  color: var(--cf-brand);
  font-size: .8125rem;
  font-weight: 600;
  flex-shrink: 0;
}

.cf-faq-card-muted .cf-faq-question-icon,
.cf-faq-status-hidden {
  background: var(--cf-status-no-show-bg);
  color: var(--cf-status-no-show-text);
}

.cf-faq-card-actions {
  justify-content: space-between;
  border-top: 1px solid var(--cf-line-soft);
  padding-top: .75rem;
}

.cf-faq-icon-actions {
  display: inline-flex;
  align-items: center;
  gap: .5rem;
}

.cf-faq-icon-action {
  width: 2rem;
  height: 2rem;
  border-radius: var(--cf-radius-pill);
}

.cf-faq-icon-action svg {
  width: .95rem;
  height: .95rem;
}

.cf-faq-edit-action {
  border-color: var(--cf-line);
  color: var(--cf-brand);
}

.cf-faq-edit-action:hover {
  border-color: var(--cf-brand);
  background: var(--cf-brand);
  color: #fff;
}

.cf-faq-delete-action {
  border-color: rgba(179, 25, 74, .22);
  color: var(--cf-danger);
}

.cf-faq-delete-action:hover {
  border-color: var(--cf-danger);
  background: var(--cf-danger-soft);
  color: var(--cf-danger);
}

.cf-faq-empty-state {
  min-height: 16rem;
  border: 1px dashed var(--cf-line);
  border-radius: var(--cf-radius-lg);
  background: var(--cf-surface);
}

@media (max-width: 1024px) {
  .cf-faq-layout { grid-template-columns: 1fr; }
}

@media (max-width: 640px) {
  .cf-faq-header,
  .cf-faq-list-header,
  .cf-faq-card-actions {
    align-items: stretch;
  }

  .cf-faq-summary,
  .cf-faq-icon-actions {
    justify-content: flex-start;
  }

  .cf-faq-composer-footer {
    align-items: stretch;
  }

  .cf-faq-composer-footer .cf-btn {
    width: 100%;
  }
}
```

- [ ] **Step 2: Run the FAQ CSS test**

Run:

```powershell
.\env\Scripts\python -m pytest tests/test_design_system.py::test_faq_icon_actions_use_accessible_compact_size -q
```

Expected: PASS after CSS is added.

---

### Task 6: Final Targeted Verification

**Files:**
- Verify: `dashboard/views.py`
- Verify: `templates/dashboard/assistant_settings.html`
- Verify: `templates/dashboard/partials/faq_row.html`
- Verify: `static/css/clinicflow.css`
- Verify: `tests/test_design_system.py`

- [ ] **Step 1: Run the FAQ design-system tests**

Run:

```powershell
.\env\Scripts\python -m pytest tests/test_design_system.py -k faq -q
```

Expected: PASS.

- [ ] **Step 2: Run the mobile wrapping regression**

Run:

```powershell
.\env\Scripts\python -m pytest tests/test_design_system.py::test_mobile_responsive_dynamic_text_has_wrapping_guards -q
```

Expected: PASS.

- [ ] **Step 3: Run Django system checks**

Run:

```powershell
.\env\Scripts\python manage.py check
```

Expected: PASS with no system check issues.

- [ ] **Step 4: Inspect final diff**

Run:

```powershell
git diff -- dashboard/views.py templates/dashboard/assistant_settings.html templates/dashboard/partials/faq_row.html static/css/clinicflow.css tests/test_design_system.py docs/superpowers/specs/2026-06-03-faq-responses-layout-design.md docs/superpowers/plans/2026-06-03-faq-responses-layout-implementation-plan.md
```

Expected: Diff only contains the approved FAQ Responses layout design, implementation plan, and related test updates.

---

## Self-Review Checklist

- Spec coverage: The plan covers the split composer/list layout, icon-only Edit/Delete, explicit visibility, responsive behavior, preserved HTMX row replacement, preserved form fields, and targeted tests.
- Red-flag scan: No forbidden vague language or unspecified implementation steps are intentionally left in this plan.
- Type and name consistency: The plan consistently uses `faq_total_count`, `faq_visible_count`, `cf-faq-layout`, `cf-faq-composer`, `cf-faq-card`, and `cf-faq-icon-action`.
