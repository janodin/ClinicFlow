# Sidebar Nav Background Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Update only the dashboard sidebar nav item hover and active background colors to the approved deeper teal glass treatment.

**Architecture:** This is a CSS-only visual refinement protected by the existing design-system regression test. The dashboard templates and sidebar shell remain unchanged; `tests/test_design_system.py` locks the intended CSS declarations.

**Tech Stack:** Django templates, Tailwind utility classes, canonical `static/css/clinicflow.css`, pytest design-system tests.

---

### Task 1: Sidebar Nav Background Tokens

**Files:**
- Modify: `tests/test_design_system.py:348-362`
- Modify: `static/css/clinicflow.css:685-726`

- [ ] **Step 1: Update the design-system test expectation**

In `tests/test_design_system.py`, change `test_dashboard_sidebar_uses_neon_aqua_shell_treatment` so the hover and active background assertions expect the approved deeper teal treatment while keeping existing sidebar shell expectations.

```python
def test_dashboard_sidebar_uses_neon_aqua_shell_treatment():
    css = css_text()
    sidebar = css_rule_block(".cf-sidebar")
    hover = css_rule_block(".cf-nav-link:hover")
    active = css_rule_block(".cf-nav-link-active")

    assert "linear-gradient(180deg, #0f667c 0%, #0b7f99 54%, #0c5f58 100%)" in sidebar
    assert "radial-gradient(circle at 18% 0%, rgba(165, 243, 252, .28), transparent 15rem)" in sidebar
    assert "border-right: 1px solid rgba(34, 211, 238, .22);" in sidebar
    assert "box-shadow: inset -1px 0 0 rgba(165, 243, 252, .18), 10px 0 28px rgba(8, 51, 68, .12);" in sidebar
    assert "color: rgba(207, 250, 254, .76) !important;" in css
    assert "background: rgba(5, 47, 58, .18);" in hover
    assert "border-color: rgba(125, 211, 252, .22);" in hover
    assert "background: linear-gradient(90deg, rgba(5, 47, 58, .34), rgba(8, 145, 178, .18));" in active
    assert "box-shadow: inset 3px 0 0 var(--cf-brand), 0 0 20px rgba(6, 182, 212, .16);" in active
```

- [ ] **Step 2: Run the targeted test to verify it fails before CSS changes**

Run:

```powershell
.\env\Scripts\python -m pytest tests/test_design_system.py::test_dashboard_sidebar_uses_neon_aqua_shell_treatment -q
```

Expected: `FAILED` because `static/css/clinicflow.css` still has the old hover and active background declarations.

- [ ] **Step 3: Update the sidebar nav CSS**

In `static/css/clinicflow.css`, update only the `.cf-nav-link:hover` and `.cf-nav-link-active` `background` declarations while preserving existing text, border, and shadow treatment.

```css
.cf-nav-link:hover {
  background: rgba(5, 47, 58, .18);
  border-color: rgba(125, 211, 252, .22);
  color: #fff;
}

.cf-nav-link-active {
  background: linear-gradient(90deg, rgba(5, 47, 58, .34), rgba(8, 145, 178, .18));
  border-color: rgba(125, 211, 252, .28);
  color: #fff;
  box-shadow: inset 3px 0 0 var(--cf-brand), 0 0 20px rgba(6, 182, 212, .16);
}
```

- [ ] **Step 4: Run the targeted test to verify it passes**

Run:

```powershell
.\env\Scripts\python -m pytest tests/test_design_system.py::test_dashboard_sidebar_uses_neon_aqua_shell_treatment -q
```

Expected: `1 passed`.

- [ ] **Step 5: Run Django checks**

Run:

```powershell
.\env\Scripts\python manage.py check
```

Expected: `System check identified no issues`.
