# FAQ Response Polish Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Polish the FAQ Responses header count summary so it better matches the Neon Aqua Clinical design system while keeping the existing composer visibility copy.

**Architecture:** This is a template/CSS/test polish pass only. Keep existing FAQ forms, view context, model fields, URLs, HTMX behavior, tenant scoping, and `Visible to patients` composer copy unchanged; convert the top-right summary into one grouped capsule with two aqua-soft mini-pills.

**Tech Stack:** Django templates, Tailwind utility classes, shared `static/css/clinicflow.css`, pytest design-system tests.

**Repo Policy:** Do not commit unless the user explicitly requests a commit.

---

## File Structure

- Modify `tests/test_design_system.py`: update FAQ layout assertions to require grouped metric capsule classes while preserving the existing composer visibility copy.
- Modify `templates/dashboard/assistant_settings.html`: change summary pill markup only.
- Modify `static/css/clinicflow.css`: update FAQ summary styles so the outer capsule groups two aqua-soft mini-pills with stronger teal text.

---

### Task 1: Add Failing Design-System Tests

**Files:**
- Modify: `tests/test_design_system.py`
- Test: `tests/test_design_system.py`

- [ ] **Step 1: Update the FAQ section layout test**

In `test_faq_section_uses_split_composer_layout`, add scoped summary assertions while preserving the existing composer copy assertion:

```python
summary = div_block_containing(template, "faq_total_count")
composer = div_block_containing(template, "faq_form.is_active")

assert summary.count("cf-faq-summary-metric") == 2
assert summary.count("cf-faq-summary-separator") == 1
assert "{{ faq_total_count }} total" in summary
assert "{{ faq_visible_count }} visible" in summary
assert summary.index("{{ faq_total_count }} total") < summary.index("cf-faq-summary-separator")
assert summary.index("cf-faq-summary-separator") < summary.index("{{ faq_visible_count }} visible")
assert "cf-faq-summary-pill" not in summary
assert "Visible to patients" in composer
assert "Make this FAQ visible" not in composer
```

- [ ] **Step 2: Add CSS assertions for matching aqua metric pills**

Add this test after `test_faq_section_uses_split_composer_layout`:

```python
def test_faq_summary_metrics_use_aqua_soft_pills():
    metric_block = css_rule_block(".cf-faq-summary-metric")
    separator_block = css_rule_block(".cf-faq-summary-separator")

    assert "background: var(--cf-brand-soft);" in metric_block
    assert "color: var(--cf-brand-strong);" in metric_block
    assert "border-radius: var(--cf-radius-pill);" in metric_block
    assert "font-variant-numeric: tabular-nums;" in metric_block
    assert "background: var(--cf-input-line);" in separator_block
```

- [ ] **Step 3: Run tests to verify RED**

Run:

```powershell
.\env\Scripts\python -m pytest tests/test_design_system.py::test_faq_section_uses_split_composer_layout tests/test_design_system.py::test_faq_summary_metrics_use_aqua_soft_pills -q
```

Expected: FAIL because the template still uses the old summary pill markup and the CSS classes do not exist yet.

---

### Task 2: Update Template Summary Markup

**Files:**
- Modify: `templates/dashboard/assistant_settings.html`
- Test: `tests/test_design_system.py`

- [ ] **Step 1: Replace the summary markup**

In the FAQ header, replace:

```html
      <div class="cf-faq-summary" aria-label="FAQ response summary">
        <span class="cf-faq-summary-pill">{{ faq_total_count }} FAQ{{ faq_total_count|pluralize }}</span>
        <span class="cf-faq-summary-pill cf-faq-summary-pill-active">{{ faq_visible_count }} visible</span>
      </div>
```

With:

```html
      <div class="cf-faq-summary" aria-label="FAQ response summary">
        <span class="cf-faq-summary-metric">{{ faq_total_count }} total</span>
        <span class="cf-faq-summary-separator" aria-hidden="true"></span>
        <span class="cf-faq-summary-metric">{{ faq_visible_count }} visible</span>
      </div>
```

- [ ] **Step 2: Confirm composer checkbox copy is unchanged**

Keep this composer footer copy exactly as-is:

```html
            <span>Visible to patients</span>
```

- [ ] **Step 3: Run the template-focused test**

Run:

```powershell
.\env\Scripts\python -m pytest tests/test_design_system.py::test_faq_section_uses_split_composer_layout -q
```

Expected: PASS after the template update.

---

### Task 3: Update FAQ Summary CSS

**Files:**
- Modify: `static/css/clinicflow.css`
- Test: `tests/test_design_system.py`

- [ ] **Step 1: Replace old summary pill CSS**

Find the existing FAQ summary styles:

```css
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
```

Replace it with:

```css
.cf-faq-summary {
  display: inline-flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: flex-end;
  gap: .45rem;
  border: 1px solid var(--cf-line);
  border-radius: var(--cf-radius-pill);
  background: var(--cf-surface);
  padding: .3rem;
  box-shadow: var(--cf-shadow-card);
}

.cf-faq-summary-metric,
.cf-faq-status {
  display: inline-flex;
  align-items: center;
  gap: .35rem;
  border-radius: var(--cf-radius-pill);
  padding: .4rem .65rem;
  font-size: .75rem;
  font-weight: 600;
  line-height: 1;
  white-space: nowrap;
}

.cf-faq-summary-metric {
  border: 1px solid var(--cf-brand-soft);
  background: var(--cf-brand-soft);
  color: var(--cf-brand-strong);
  font-variant-numeric: tabular-nums;
}

.cf-faq-summary-separator {
  width: .25rem;
  height: .25rem;
  border-radius: var(--cf-radius-pill);
  background: var(--cf-input-line);
}

.cf-faq-status-visible {
  border: 1px solid var(--cf-brand-soft);
  background: var(--cf-brand-soft);
  color: var(--cf-brand-strong);
}
```

- [ ] **Step 2: Run CSS-focused tests**

Run:

```powershell
.\env\Scripts\python -m pytest tests/test_design_system.py::test_faq_summary_metrics_use_aqua_soft_pills tests/test_design_system.py::test_faq_section_uses_split_composer_layout -q
```

Expected: PASS after CSS update.

---

### Task 4: Final Verification

**Files:**
- Verify: `templates/dashboard/assistant_settings.html`
- Verify: `static/css/clinicflow.css`
- Verify: `tests/test_design_system.py`

- [ ] **Step 1: Run FAQ design-system tests**

Run:

```powershell
.\env\Scripts\python -m pytest tests/test_design_system.py -k faq -q
```

Expected: PASS.

- [ ] **Step 2: Run Django check**

Run:

```powershell
.\env\Scripts\python manage.py check
```

Expected: PASS with no system check issues.

- [ ] **Step 3: Inspect scoped diff**

Run:

```powershell
git diff -- templates/dashboard/assistant_settings.html static/css/clinicflow.css tests/test_design_system.py docs/superpowers/specs/2026-06-03-faq-responses-layout-design.md docs/superpowers/plans/2026-06-03-faq-response-polish-implementation-plan.md
```

Expected: Diff includes only the approved FAQ summary/copy polish plus spec/plan updates within these files. Note any pre-existing unrelated changes in the same files without reverting them.

---

## Self-Review Checklist

- Spec coverage: The plan covers the approved copy change and matching aqua-soft summary mini-pills.
- Red-flag scan: No forbidden vague language or unspecified implementation steps are intentionally left in this plan.
- Type and name consistency: The plan consistently uses `cf-faq-summary`, `cf-faq-summary-metric`, and `cf-faq-summary-separator`.
