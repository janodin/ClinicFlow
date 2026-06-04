# Stripe Design System Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace KliniAssist's Stone-Sage visual language with the `getdesign` Stripe design system across the Django dashboard, public widget, auth, and email surfaces while preserving all booking and clinic-scoping behavior.

**Architecture:** Use a token-first migration. Replace root `DESIGN.md`, then re-skin the existing `static/css/kliniassist.css` `cf-*` implementation layer and update only the templates, model defaults, and color literals that still expose old teal/sage/slate design decisions. Keep Django templates, CDN Tailwind, HTMX, Alpine.js, Lucide, and FullCalendar; do not introduce a frontend build pipeline.

**Tech Stack:** Django 5.2, Django templates, Tailwind CDN utility layout, `static/css/kliniassist.css`, HTMX, Alpine.js, FullCalendar, Lucide icons, pytest, pytest-django.

---

## Operating Rules

- Activate the local environment before Python commands: `.\env\Scripts\activate`.
- Do not commit unless the user explicitly asks for commits. Use `git status --short` and `git diff -- <paths>` as checkpoints instead.
- Do not modify or stage unrelated dirty files such as `db.sqlite3`, `.superpowers/`, or `deploy-vps.ps1`.
- Preserve guest booking, patient phone matching, slot validation, double-booking prevention, tenant scoping, permissions, dashboard routes, HTMX targets, and widget chat behavior.
- Do not add online payments or Stripe payment functionality. This is a visual migration only.
- Model default changes are included for visual defaults only. Because they touch Django models, run `makemigrations`, `migrate`, and `check` in the model-default task.
- Ignore `.superpowers/brainstorm/**` when searching for active app design drift; those files are generated visual-companion artifacts.

## File Responsibility Map

- `DESIGN.md`: Active Stripe design reference installed by `npx getdesign@latest add stripe --force`.
- `docs/superpowers/specs/2026-06-02-stripe-design-system-migration-design.md`: Approved migration spec.
- `static/css/kliniassist.css`: Global Stripe tokens, base typography, reusable `cf-*` classes, compatibility aliases, widget/auth/gradient surfaces.
- `templates/base.html`: Global script/CSS loading and root document shell.
- `templates/dashboard/base.html`: Authenticated app shell, sidebar, topbar, search, account menu, toast container, mobile nav, global HTMX behavior.
- `templates/dashboard/*.html`: Dashboard pages using shared classes: home, appointments, calendar, patients, services, settings, business hours, unavailable dates, slot preview, profile, billing, assistant/widget settings.
- `templates/dashboard/partials/*.html`: HTMX-swapped rows, forms, modals, search results, duplicate/merge flows, FAQ rows, and patient/service/appointment details.
- `templates/widget/*.html` and `templates/widget/partials/*.html`: Public widget shell, slot list, success/error states, booking confirmation.
- `templates/accounts/login.html` and `templates/accounts/signup.html`: Auth pages using Stripe gradient/auth panel patterns.
- `templates/emails/*.html`: Inline-safe email surfaces using Stripe indigo and navy.
- `dashboard/views.py`: FullCalendar event color map.
- `clinics/models.py`: Default widget accent color and validator help text.
- `services/models.py`: Default service color.
- `clinics/migrations/*.py` and `services/migrations/*.py`: Generated migrations for visual default changes.
- `tests/test_design_system.py`: Design drift tests for Stripe tokens, typography, components, templates, and legacy cleanup.
- `dashboard/tests.py`: Calendar color assertions and existing HTMX/calendar behavior tests.
- `widget/tests.py`: Widget accent fallback and booking behavior tests.
- `services/tests.py`: Service default color assertion.

## Baseline Commands

Run from the project root.

```powershell
.\env\Scripts\activate; python manage.py check
```

```powershell
.\env\Scripts\activate; python -m pytest tests/test_design_system.py
```

```powershell
.\env\Scripts\activate; python -m pytest dashboard/tests.py widget/tests.py services/tests.py
```

```powershell
.\env\Scripts\activate; python -m pytest
```

---

### Task 1: Install Stripe DESIGN.md Source Of Truth

**Files:**
- Modify: `DESIGN.md`
- Reference: `docs/superpowers/specs/2026-06-02-stripe-design-system-migration-design.md`

**Goal:** Replace the root design-system source of truth with the `getdesign` Stripe template.

- [ ] **Step 1: Confirm the current design doc is still Stone-Sage**

Run:

```powershell
Select-String -Path "DESIGN.md" -Pattern "Stone-Sage|#365449|#533afd"
```

Expected before implementation: output includes `Stone-Sage` or `#365449`.

- [ ] **Step 2: Install the Stripe design reference**

Run:

```powershell
npx getdesign@latest add stripe --force
```

Expected: command reports that `DESIGN.md` inspired by `stripe` was installed.

- [ ] **Step 3: Verify the root design reference is Stripe-based**

Run:

```powershell
Select-String -Path "DESIGN.md" -Pattern "#533afd|Signature purple gradients|Sohne|Inter|Gradient Mesh"
```

Expected: output includes Stripe tokens or Stripe design-system language such as `#533afd`, `Sohne`, or `Gradient Mesh`.

- [ ] **Step 4: Review the diff checkpoint**

Run:

```powershell
git diff -- DESIGN.md
git status --short -- DESIGN.md
```

Expected: only `DESIGN.md` is changed by this task.

---

### Task 2: Update Design-System Tests To Assert Stripe

**Files:**
- Modify: `tests/test_design_system.py`
- Reference: `static/css/kliniassist.css`
- Reference: `templates/dashboard/base.html`
- Reference: `templates/widget/widget.html`

**Goal:** Convert design drift tests from Stone-Sage assertions to Stripe assertions before changing CSS/templates.

- [ ] **Step 1: Replace the token/font test with Stripe expectations**

In `tests/test_design_system.py`, replace `test_css_uses_stone_sage_tokens_and_aliases` with:

```python
def test_css_uses_stripe_tokens_and_typography():
    css = css_text().lower()

    expected_tokens = [
        "--cf-brand: #533afd",
        "--cf-brand-hover: #4434d4",
        "--cf-brand-strong: #2e2b8c",
        "--cf-dashboard-dark: #1c1e54",
        "--cf-ink: #0d253d",
        "--cf-muted: #64748d",
        "--cf-bg: #ffffff",
        "--cf-bg-strong: #f6f9fc",
        "--cf-surface-warm: #f6f9fc",
        "--cf-line: #e3e8ee",
        "--cf-input-line: #a8c3de",
        "--cf-focus: rgba(83, 58, 253, .22)",
    ]
    for token in expected_tokens:
        assert token in css

    assert "family=inter:wght@300;400;500;600;700;800" in css
    assert "font-family: \"inter\", sans-serif;" in css
    assert "font-feature-settings: \"ss01\";" in css
    assert "font-variant-numeric: tabular-nums;" in css
    assert "cormorant garamond" not in css
    assert "manrope" not in css
    assert "ibm plex mono" not in css
```

- [ ] **Step 2: Replace the old-color avoidance test**

In `tests/test_design_system.py`, replace `test_css_avoids_unsupported_weights_and_old_colors` with:

```python
def test_css_avoids_stone_sage_fonts_and_raw_legacy_colors():
    css = css_text().lower()

    forbidden = [
        "font-weight: 850",
        "font-weight: 750",
        "#0891b2",
        "#0f6b55",
        "#eef5f8",
        "#365449",
        "#243a33",
        "#2e493f",
        "#ebe7dd",
        "#f8f6ef",
        "stone-sage",
        "cormorant",
        "manrope",
        "ibm plex mono",
    ]
    for value in forbidden:
        assert value not in css
```

- [ ] **Step 3: Update dropdown readability assertions for Stripe values**

In `test_css_contains_readable_dropdown_select_rules`, replace the snippets that assert old muted and brand-soft values with:

```python
    for snippet in [
        "select option",
        "select option:disabled",
        "select option:checked",
        "select[multiple]",
        ".cf-menu-panel",
        ".cf-search-panel",
        ".cf-menu-row",
        ".cf-search-result",
        "background: #fff;",
        "color: var(--cf-muted);",
        "background: var(--cf-brand-soft);",
        "color: var(--cf-brand-strong);",
    ]:
        assert snippet in css
```

- [ ] **Step 4: Add component geometry assertions**

Add this test after `test_css_contains_canonical_controls_and_field_states`:

```python
def test_css_uses_stripe_component_geometry():
    css = css_text()
    button = css_rule_block(".cf-btn")
    card = css_rule_block(".cf-card,\n.soft-card")
    input_block = css_rule_block("input,\nselect,\ntextarea,\n.cf-input,\n.cf-select,\n.cf-textarea")

    assert "border-radius: var(--cf-radius-pill);" in button
    assert "font-weight: 400;" in button
    assert "border-radius: var(--cf-radius-lg);" in card
    assert "box-shadow: var(--cf-shadow-card);" in card
    assert "border-color: var(--cf-input-line);" in input_block or "border: 1px solid var(--cf-input-line);" in input_block
```

- [ ] **Step 5: Rename Stone-Sage test names without changing behavioral assertions**

Rename these test functions in `tests/test_design_system.py`:

```python
def test_task_5_appointment_modals_use_stripe_anatomy_and_singular_titles():
    ...

def test_task_5_calendar_uses_single_stripe_shell_and_accessible_modal():
    ...
```

Keep the existing assertion bodies for modal anatomy, FullCalendar IDs, HTMX hooks, and focus behavior.

- [ ] **Step 6: Run design-system tests to confirm they fail before implementation**

Run:

```powershell
.\env\Scripts\activate; python -m pytest tests/test_design_system.py -q
```

Expected: FAIL because `kliniassist.css` still contains Stone-Sage tokens/fonts and old component geometry.

---

### Task 3: Update Visual Default Tests For Widget, Service, And Calendar Colors

**Files:**
- Modify: `dashboard/tests.py`
- Modify: `widget/tests.py`
- Modify: `services/tests.py`
- Reference: `dashboard/views.py`
- Reference: `clinics/models.py`
- Reference: `services/models.py`

**Goal:** Make tests require Stripe indigo defaults and Stripe-compatible calendar event colors.

- [ ] **Step 1: Rename and update calendar color assertion**

In `dashboard/tests.py`, replace `test_calendar_events_use_stone_sage_status_colors` with:

```python
@pytest.mark.django_db
def test_calendar_events_use_stripe_status_colors(calendar_setup, client):
    clinic, service, user, patient, appointment, target_date = calendar_setup
    client.force_login(user)

    response = client.get(reverse("dashboard:calendar_events"))

    assert response.status_code == 200
    data = response.json()
    assert data[0]["backgroundColor"] == "#ededff"
    assert data[0]["borderColor"] == "#533afd"
    assert data[0]["textColor"] == "#4434d4"
```

- [ ] **Step 2: Update widget fallback assertions**

In `widget/tests.py`, replace each expected old fallback `#0891b2` in these tests with `#533afd`:

```python
def test_embed_js_uses_safe_accent_color_for_invalid_stored_value(self):
    Clinic.objects.filter(pk=self.clinic.pk).update(widget_accent_color='";alert(1)//')

    response = self.client.get(reverse("widget:embed_js", args=[self.clinic.slug]))
    content = response.content.decode()

    self.assertNotIn("alert(1)", content)
    self.assertIn("#533afd", content)


def test_safe_widget_accent_color_falls_back_for_invalid_stored_value(self):
    Clinic.objects.filter(pk=self.clinic.pk).update(widget_accent_color='";alert(1)//')
    self.clinic.refresh_from_db()
    self.assertEqual(self.clinic.safe_widget_accent_color, "#533afd")

    Clinic.objects.filter(pk=self.clinic.pk).update(widget_accent_color="#123abc")
    self.clinic.refresh_from_db()
    self.assertEqual(self.clinic.safe_widget_accent_color, "#123abc")


def test_widget_accent_color_is_escaped_in_script(self):
    dangerous = '";alert(1)//'
    Clinic.objects.filter(pk=self.clinic.pk).update(widget_accent_color=dangerous)

    response = self.client.get(reverse("widget:home", args=[self.clinic.slug]))
    content = response.content.decode()

    self.assertNotIn(dangerous, content)
    self.assertNotIn("alert(1)", content)
    self.assertIn("#533afd", content)
    self.assertIn("accentColor:", content)
```

- [ ] **Step 3: Add a service default color test**

In `services/tests.py`, add this method inside `ServiceTests`:

```python
    def test_service_default_color_uses_stripe_primary(self):
        service = Service.objects.create(
            clinic=self.clinic,
            name="Stripe Default Service",
            duration_minutes=20,
            price="300.00",
        )

        self.assertEqual(service.color, "#533afd")
```

- [ ] **Step 4: Run targeted tests to confirm they fail before implementation**

Run:

```powershell
.\env\Scripts\activate; python -m pytest dashboard/tests.py::test_calendar_events_use_stripe_status_colors widget/tests.py::WidgetTests::test_embed_js_uses_safe_accent_color_for_invalid_stored_value widget/tests.py::WidgetTests::test_safe_widget_accent_color_falls_back_for_invalid_stored_value widget/tests.py::WidgetTests::test_widget_accent_color_is_escaped_in_script services/tests.py::ServiceTests::test_service_default_color_uses_stripe_primary -q
```

Expected: FAIL because defaults and hard-coded calendar colors still use old teal/sage values.

---

### Task 4: Migrate CSS Tokens, Typography, And Core Components

**Files:**
- Modify: `static/css/kliniassist.css`
- Test: `tests/test_design_system.py`

**Goal:** Re-skin the shared `cf-*` layer to the Stripe design system while preserving existing class names.

- [ ] **Step 1: Replace the font import**

Replace the first line of `static/css/kliniassist.css` with:

```css
@import url("https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap");
```

- [ ] **Step 2: Replace `:root` with Stripe-compatible tokens**

Replace the current `:root` block with:

```css
:root {
  color-scheme: light;
  --cf-bg: #ffffff;
  --cf-bg-strong: #f6f9fc;
  --cf-surface: #ffffff;
  --cf-surface-warm: #f6f9fc;
  --cf-surface-muted: #eef3f8;
  --cf-surface-tint: #ededff;
  --cf-line: #e3e8ee;
  --cf-line-soft: #edf2f7;
  --cf-input-line: #a8c3de;
  --cf-ink: #0d253d;
  --cf-ink-secondary: #273951;
  --cf-muted: #64748d;
  --cf-faint: #7b8aa0;
  --cf-brand: #533afd;
  --cf-brand-hover: #4434d4;
  --cf-brand-strong: #2e2b8c;
  --cf-brand-soft: #ededff;
  --cf-dashboard-dark: #1c1e54;
  --cf-warm-interlude: #f5e9d4;
  --cf-ruby: #ea2261;
  --cf-magenta: #f96bee;
  --cf-lemon: #9b6829;
  --cf-info: #4434d4;
  --cf-info-soft: #ededff;
  --cf-warning: #9b6829;
  --cf-warning-soft: #fff6e7;
  --cf-danger: #b3194a;
  --cf-danger-soft: #fde8ef;
  --cf-focus: rgba(83, 58, 253, .22);
  --cf-blue: var(--cf-info);
  --cf-red: var(--cf-danger);
  --cf-amber: var(--cf-warning);
  --cf-shadow-card: 0 1px 3px rgba(0, 55, 112, .08);
  --cf-shadow-raised: 0 8px 24px rgba(0, 55, 112, .08), 0 2px 6px rgba(0, 55, 112, .04);
  --cf-shadow-subtle: 0 2px 8px rgba(0, 55, 112, .06);
  --cf-radius-xs: 4px;
  --cf-radius-sm: 6px;
  --cf-radius: 8px;
  --cf-radius-md: 8px;
  --cf-radius-lg: 12px;
  --cf-radius-shell: 16px;
  --cf-radius-pill: 9999px;
  --cf-sidebar-width: 272px;
  --cf-topbar-height: 64px;
  --cf-widget-width: 420px;
  --cf-widget-height: 650px;
  --cf-z-dropdown: 55;
  --cf-z-modal: 60;
  --cf-z-toast: 70;
  --cf-z-widget: 80;
  --cf-section-title-size: 1.375rem;
  --cf-status-pending-bg: var(--cf-warning-soft);
  --cf-status-pending-text: var(--cf-warning);
  --cf-status-confirmed-bg: var(--cf-info-soft);
  --cf-status-confirmed-text: var(--cf-info);
  --cf-status-completed-bg: #e9f7ef;
  --cf-status-completed-text: #0f766e;
  --cf-status-cancelled-bg: var(--cf-danger-soft);
  --cf-status-cancelled-text: var(--cf-danger);
  --cf-status-no-show-bg: #edf2f7;
  --cf-status-no-show-text: var(--cf-muted);
}
```

- [ ] **Step 3: Replace body typography and background**

Update the `body` rule to:

```css
body {
  min-height: 100vh;
  min-height: 100dvh;
  margin: 0;
  overflow-x: hidden;
  background:
    radial-gradient(circle at 12% 0%, rgba(249, 107, 238, .16), transparent 20rem),
    radial-gradient(circle at 82% 4%, rgba(83, 58, 253, .18), transparent 24rem),
    linear-gradient(180deg, var(--cf-bg-strong) 0%, var(--cf-bg) 48%);
  color: var(--cf-ink);
  font-family: "Inter", sans-serif;
  font-feature-settings: "ss01";
  font-size: 15px;
  font-weight: 300;
  line-height: 1.4;
  letter-spacing: 0;
}
```

- [ ] **Step 4: Update numeric typography**

Replace the current `code, .cf-mono, .cf-kpi-value` font rule with:

```css
code,
.cf-mono,
.cf-kpi-value,
.cf-tabular {
  font-family: "Inter", sans-serif;
  font-feature-settings: "ss01", "tnum";
  font-variant-numeric: tabular-nums;
}
```

- [ ] **Step 5: Update inputs to Stripe geometry**

In the combined input/select/textarea rule, use these declarations:

```css
  min-height: 2.5rem;
  border: 1px solid var(--cf-input-line);
  border-radius: var(--cf-radius-sm);
  padding: .5rem .75rem;
  background-color: var(--cf-surface);
  color: var(--cf-ink);
  font: inherit;
```

Keep existing focus, disabled, invalid, date/time, select arrow, multiple select, and option readability rules, but make the disabled option color `var(--cf-muted)` and selected option background `var(--cf-brand-soft)`.

- [ ] **Step 6: Update headings, cards, buttons, tables, badges, shell, modals, and widget classes**

Apply these exact class-level targets in `static/css/kliniassist.css`:

```css
.cf-section-title,
.cf-modal-title,
.ui-page-title {
  color: var(--cf-ink);
  font-family: "Inter", sans-serif;
  font-weight: 300;
  letter-spacing: -.02em;
}

.cf-card,
.soft-card {
  background: var(--cf-surface);
  border: 1px solid var(--cf-line);
  border-radius: var(--cf-radius-lg);
  box-shadow: var(--cf-shadow-card);
}

.cf-btn,
.ui-button {
  display: inline-flex;
  min-height: 2.5rem;
  align-items: center;
  justify-content: center;
  gap: .5rem;
  border: 1px solid transparent;
  border-radius: var(--cf-radius-pill);
  padding: .5rem 1rem;
  font-family: "Inter", sans-serif;
  font-size: .9375rem;
  font-weight: 400;
  line-height: 1;
  text-decoration: none;
  white-space: nowrap;
  cursor: pointer;
}

.cf-btn-primary,
.ui-button-primary {
  background: var(--cf-brand);
  color: #fff;
}

.cf-btn-primary:hover,
.ui-button-primary:hover {
  background: var(--cf-brand-hover);
  color: #fff;
}

.cf-btn-primary:active,
.ui-button-primary:active {
  background: var(--cf-brand-strong);
}

.cf-btn-secondary,
.ui-button-secondary {
  border-color: var(--cf-brand);
  background: var(--cf-surface);
  color: var(--cf-brand);
}

.cf-table {
  width: 100%;
  border-collapse: separate;
  border-spacing: 0;
  text-align: left;
  font-size: .875rem;
  line-height: 1.4;
}

.cf-table th,
.cf-table td {
  border-bottom: 1px solid var(--cf-line-soft);
  padding: .75rem 1rem;
}

.cf-table tbody tr:hover { background: var(--cf-bg-strong); }

.cf-badge {
  display: inline-flex;
  align-items: center;
  gap: .375rem;
  border-radius: var(--cf-radius-pill);
  padding: .25rem .5rem;
  font-size: .6875rem;
  font-weight: 400;
  line-height: 1;
  white-space: nowrap;
}
```

- [ ] **Step 7: Replace auth/brand accent CSS with Stripe gradient mesh**

Update `.cf-auth-panel` and add `.cf-gradient-mesh`:

```css
.cf-gradient-mesh,
.cf-auth-panel {
  position: relative;
  overflow: hidden;
  background:
    radial-gradient(circle at 8% 10%, rgba(245, 233, 212, .95), transparent 18rem),
    radial-gradient(circle at 32% 4%, rgba(255, 167, 118, .55), transparent 20rem),
    radial-gradient(circle at 58% 0%, rgba(185, 185, 249, .8), transparent 18rem),
    radial-gradient(circle at 78% 8%, rgba(83, 58, 253, .5), transparent 21rem),
    radial-gradient(circle at 96% 2%, rgba(234, 34, 97, .45), transparent 17rem),
    var(--cf-bg-strong);
}
```

- [ ] **Step 8: Remap compatibility aliases to Stripe and keep them temporary**

In the compatibility section, update color aliases to use Stripe tokens and keep the comment:

```css
/* Migration compatibility: temporary aliases and old Tailwind utility overrides until templates are normalized. */
.text-cyan-700,
.text-cyan-600,
.text-cyan-500 { color: var(--cf-brand) !important; }
.bg-cyan-700 { background-color: var(--cf-brand) !important; }
.bg-cyan-50 { background-color: var(--cf-brand-soft) !important; }
.border-cyan-100,
.border-cyan-200,
.border-slate-100,
.border-slate-200,
.border-slate-300 { border-color: var(--cf-line) !important; }
```

- [ ] **Step 9: Run design-system tests**

Run:

```powershell
.\env\Scripts\activate; python -m pytest tests/test_design_system.py -q
```

Expected: PASS for CSS token/typography/component tests; template cleanup tests can still fail until later tasks remove active-template legacy classes.

---

### Task 5: Migrate Visual Defaults And Generate Migrations

**Files:**
- Modify: `clinics/models.py`
- Modify: `services/models.py`
- Create: `clinics/migrations/00xx_alter_clinic_widget_accent_color.py`
- Create: `services/migrations/00xx_alter_service_color.py`
- Test: `widget/tests.py`
- Test: `services/tests.py`

**Goal:** Replace old teal defaults with Stripe indigo for new clinics and services.

- [ ] **Step 1: Change the clinic widget default and validator message**

In `clinics/models.py`, update the default and validator message to:

```python
DEFAULT_WIDGET_ACCENT_COLOR = "#533afd"

hex_color_validator = RegexValidator(
    regex=HEX_COLOR_RE,
    message="Enter a valid hex color such as #533afd.",
)
```

- [ ] **Step 2: Change the service color default**

In `services/models.py`, update the `color` field to:

```python
    color = models.CharField(max_length=7, default="#533afd")
```

- [ ] **Step 3: Generate migrations**

Run:

```powershell
.\env\Scripts\activate; python manage.py makemigrations clinics services
```

Expected: Django creates one migration for `Clinic.widget_accent_color` and one migration for `Service.color`.

- [ ] **Step 4: Apply migrations**

Run:

```powershell
.\env\Scripts\activate; python manage.py migrate
```

Expected: migrations apply without errors.

- [ ] **Step 5: Run model/default tests**

Run:

```powershell
.\env\Scripts\activate; python -m pytest widget/tests.py::WidgetTests::test_embed_js_uses_safe_accent_color_for_invalid_stored_value widget/tests.py::WidgetTests::test_safe_widget_accent_color_falls_back_for_invalid_stored_value widget/tests.py::WidgetTests::test_widget_accent_color_is_escaped_in_script services/tests.py::ServiceTests::test_service_default_color_uses_stripe_primary -q
```

Expected: PASS.

---

### Task 6: Migrate Calendar Status Colors

**Files:**
- Modify: `dashboard/views.py`
- Test: `dashboard/tests.py`

**Goal:** Replace hard-coded Stone-Sage calendar colors with Stripe-compatible status colors while keeping status meaning distinct.

- [ ] **Step 1: Replace the color map**

In `dashboard/views.py`, replace the `color_map` block in `calendar_events` with:

```python
    color_map = {
        Appointment.STATUS_PENDING: {"backgroundColor": "#fff6e7", "borderColor": "#9b6829", "textColor": "#9b6829"},
        Appointment.STATUS_CONFIRMED: {"backgroundColor": "#ededff", "borderColor": "#533afd", "textColor": "#4434d4"},
        Appointment.STATUS_COMPLETED: {"backgroundColor": "#e9f7ef", "borderColor": "#0f766e", "textColor": "#0f766e"},
        Appointment.STATUS_CANCELLED: {"backgroundColor": "#fde8ef", "borderColor": "#ea2261", "textColor": "#b3194a"},
        Appointment.STATUS_NO_SHOW: {"backgroundColor": "#edf2f7", "borderColor": "#64748d", "textColor": "#64748d"},
    }
```

- [ ] **Step 2: Run calendar color and behavior tests**

Run:

```powershell
.\env\Scripts\activate; python -m pytest dashboard/tests.py::test_calendar_events_use_stripe_status_colors dashboard/tests.py::test_calendar_events_returns_events dashboard/tests.py::test_calendar_events_title_shows_time_and_patient_only dashboard/tests.py::test_calendar_events_filters_by_service dashboard/tests.py::test_calendar_events_filters_by_status dashboard/tests.py::test_calendar_reschedule_valid dashboard/tests.py::test_calendar_reschedule_double_booking -q
```

Expected: PASS.

---

### Task 7: Migrate Dashboard Shell And Primary Operational Pages

**Files:**
- Modify: `templates/base.html`
- Modify: `templates/dashboard/base.html`
- Modify: `templates/dashboard/home.html`
- Modify: `templates/dashboard/appointments.html`
- Modify: `templates/dashboard/calendar.html`
- Modify: `templates/dashboard/patients.html`
- Modify: `templates/dashboard/services.html`
- Test: `tests/test_design_system.py`
- Test: `dashboard/tests.py`

**Goal:** Make the main authenticated dashboard feel Stripe-based without changing HTMX/Alpine/FullCalendar behavior.

- [ ] **Step 1: Preserve global assets in `templates/base.html`**

Keep these existing script/style lines intact:

```html
  <script src="https://cdn.tailwindcss.com"></script>
  <script src="https://unpkg.com/htmx.org@1.9.12"></script>
  <script defer src="https://unpkg.com/alpinejs@3.x.x/dist/cdn.min.js"></script>
  <script src="https://unpkg.com/lucide@latest"></script>
  <link rel="stylesheet" href="{% static 'css/kliniassist.css' %}">
```

Do not add a `package.json`, Tailwind config, PostCSS config, React, Next.js, or a frontend build step.

- [ ] **Step 2: Update dashboard shell classes without changing hooks**

In `templates/dashboard/base.html`, preserve these exact hooks:

```html
x-data="{ sidebarOpen: false, isDesktop: false, toasts: [], toastId: 0
id="search-results"
id="search-indicator"
id="account-menu-panel"
@toast-message.window="addToast($event.detail.message, $event.detail.type)"
:inert="!sidebarOpen && !isDesktop"
:aria-hidden="(!sidebarOpen && !isDesktop).toString()"
```

Replace old heavy/rounded visual utility choices on icons/buttons with Stripe-compatible `cf-*` or CSS-variable utilities. For example, change the brand mark wrapper from a dark sage rounded box to an indigo pill/compact square:

```html
<div class="grid h-10 w-10 place-items-center rounded-xl bg-[var(--cf-brand)] text-white shadow-[var(--cf-shadow-subtle)]">
```

- [ ] **Step 3: Replace legacy classes on the primary dashboard pages**

For each of these files, remove `text-slate-*`, `bg-slate-*`, `border-slate-*`, `text-cyan-*`, `bg-cyan-*`, `border-cyan-*`, `focus:border-cyan`, `focus:ring-cyan`, and `font-[850]`:

```text
templates/dashboard/home.html
templates/dashboard/appointments.html
templates/dashboard/calendar.html
templates/dashboard/patients.html
templates/dashboard/services.html
```

Use these replacements consistently:

```text
text-slate-500 -> text-[var(--cf-muted)] or cf-muted
text-slate-800 -> text-[var(--cf-ink)]
border-slate-200 -> border-[var(--cf-line)]
bg-slate-50 -> bg-[var(--cf-bg-strong)]
bg-cyan-700 -> bg-[var(--cf-brand)]
text-cyan-700 -> text-[var(--cf-brand)]
focus:border-cyan-500 -> focus:border-[var(--cf-brand)]
focus:ring-cyan-500/20 -> focus:ring-[var(--cf-focus)]
rounded-2xl buttons -> cf-btn or rounded-full for CTAs
```

- [ ] **Step 4: Keep dashboard page composition intact**

Do not remove these product labels and table headers from `templates/dashboard/home.html`:

```text
Today at {{ clinic.name }}
New appointment
Add patient
Needs attention
Today's schedule
Booking widget active
Time
Patient
Service
Source / payment
Status
```

- [ ] **Step 5: Keep appointment and calendar modal hooks intact**

In `templates/dashboard/appointments.html` and `templates/dashboard/calendar.html`, preserve:

```html
id="filter-form"
id="appointments-table"
id="detail-modal-body"
role="dialog"
aria-modal="true"
aria-labelledby=
@keydown.tab="trapModalFocus($event, $el)"
id="calendar"
id="calendar-loading"
id="calendar-prev"
id="calendar-next"
id="calendar-today"
data-calendar-view="dayGridMonth"
data-calendar-view="timeGridWeek"
data-calendar-view="timeGridDay"
```

- [ ] **Step 6: Run shell/page tests**

Run:

```powershell
.\env\Scripts\activate; python -m pytest tests/test_design_system.py dashboard/tests.py::test_calendar_page_uses_event_title_time_only dashboard/tests.py::test_calendar_cancel_triggers_refetch_without_table_row_target dashboard/tests.py::test_calendar_edit_triggers_refetch_without_table_row_target -q
```

Expected: PASS for dashboard shell, home, appointments, calendar, HTMX, and modal assertions.

---

### Task 8: Migrate Remaining Dashboard Pages And Partials

**Files:**
- Modify: `templates/dashboard/assistant_settings.html`
- Modify: `templates/dashboard/widget_embed.html`
- Modify: `templates/dashboard/settings.html`
- Modify: `templates/dashboard/business_hours.html`
- Modify: `templates/dashboard/unavailable_dates.html`
- Modify: `templates/dashboard/slot_preview.html`
- Modify: `templates/dashboard/profile.html`
- Modify: `templates/dashboard/billing.html`
- Modify: `templates/dashboard/partials/*.html`
- Test: `tests/test_design_system.py`
- Test: `dashboard/tests.py`

**Goal:** Remove visible legacy utilities from settings, widget embed, modals, rows, forms, and HTMX partials.

- [ ] **Step 1: Replace widget settings fallback color**

In `templates/dashboard/assistant_settings.html`, change the Alpine fallback from old teal to Stripe indigo:

```html
x-data="{urlCopied: false, scriptCopied: false, iframeCopied: false, accentColor:'{{ clinic.widget_accent_color|default:'#533afd' }}'}"
```

- [ ] **Step 2: Migrate code preview blocks in `widget_embed.html`**

Replace old slate/cyan code preview classes with Stripe dark dashboard chrome:

```html
<pre class="overflow-x-auto rounded-xl bg-[var(--cf-dashboard-dark)] p-5 text-sm text-white shadow-[var(--cf-shadow-raised)]" id="script-code">
```

Use the same class pattern for `id="iframe-code"`.

- [ ] **Step 3: Convert settings page forms and tables to `cf-*` classes**

For `business_hours.html`, `unavailable_dates.html`, and `slot_preview.html`, use these structures:

```html
<div class="cf-page">
  <div class="cf-page-header">
    <div>
      <h1 class="ui-page-title">Page Title</h1>
      <p class="cf-muted mt-2">Page description.</p>
    </div>
  </div>
  <section class="cf-card">
```

Use `cf-field`, `cf-label`, `cf-input`, `cf-select`, `cf-btn`, `cf-btn-primary`, `cf-table-wrap`, `cf-table-header`, and `cf-table` for forms and tables.

- [ ] **Step 4: Preserve partial modal anatomy**

In every dashboard partial that renders a modal, preserve these classes/attributes:

```html
class="cf-modal-backdrop"
class="cf-modal"
class="cf-modal-header"
class="cf-modal-body"
class="cf-modal-footer"
role="dialog"
aria-modal="true"
aria-labelledby=
```

- [ ] **Step 5: Remove legacy active-template utilities from dashboard templates and partials**

Run:

```powershell
rg "text-slate-|bg-slate-|border-slate-|text-cyan-|bg-cyan-|border-cyan-|focus:border-cyan|focus:ring-cyan|font-\[850\]" templates/dashboard
```

Expected after edits: no matches in `templates/dashboard/**`.

- [ ] **Step 6: Run dashboard partial and behavior tests**

Run:

```powershell
.\env\Scripts\activate; python -m pytest tests/test_design_system.py dashboard/tests.py -q
```

Expected: PASS.

---

### Task 9: Migrate Public Widget And Booking Confirmation Surfaces

**Files:**
- Modify: `templates/widget/widget.html`
- Modify: `templates/widget/partials/slots.html`
- Modify: `templates/widget/partials/booking_success.html`
- Modify: `templates/widget/partials/booking_error.html`
- Modify: `templates/widget/booking_success.html`
- Reference: `widget/views.py`
- Test: `widget/tests.py`
- Test: `tests/test_design_system.py`

**Goal:** Make the guest booking widget Stripe-based while preserving all Alpine, HTMX, booking, slot, and chat behavior.

- [ ] **Step 1: Preserve widget behavior hooks**

In `templates/widget/widget.html`, preserve these hooks exactly:

```html
x-data="widgetApp()"
id="slots-container"
id="booking-form-container"
hx-get="{% url 'widget:slots' clinic.slug %}"
hx-target="#slots-container"
hx-post="{% url 'widget:book' clinic.slug %}?source={{ booking_source }}"
hx-target="#booking-form-container"
accentColor: '{{ clinic.safe_widget_accent_color|escapejs }}'
window.parent.postMessage('kliniassist-minimize', '*')
document.body.addEventListener('htmx:beforeSwap'
```

- [ ] **Step 2: Add Stripe gradient mesh to the widget's brand-facing area**

Apply `cf-gradient-mesh` to the widget's upper/home surface and keep text readable:

```html
<section class="cf-gradient-mesh rounded-xl p-4 text-[var(--cf-ink)]">
```

Use it on the welcome/home card or success header, not on the scrollable operational form body.

- [ ] **Step 3: Replace legacy widget utility classes**

Remove these patterns from `templates/widget/**/*.html`:

```text
text-slate-
bg-slate-
border-slate-
bg-cyan-
text-cyan-
border-cyan-
focus:border-cyan
focus:ring-cyan
```

Use `cf-card`, `cf-field`, `cf-label`, `cf-input`, `cf-textarea`, `cf-btn`, `cf-btn-primary`, `cf-slot-grid`, `cf-slot-button`, `cf-muted`, `text-[var(--cf-ink)]`, `text-[var(--cf-muted)]`, and `border-[var(--cf-line)]`.

- [ ] **Step 4: Preserve selected slot and clinic accent behavior**

In `templates/widget/partials/slots.html`, keep `data-slot-value`, `x-model` compatibility, and safe clinic accent styles. Use this button shape:

```html
<button type="button"
        data-slot-value="{{ slot.starts_at.isoformat }}"
        @click="selectSlot('{{ slot.starts_at.isoformat }}')"
        class="cf-slot-button"
        :class="slot === '{{ slot.starts_at.isoformat }}' ? 'text-white border-transparent' : ''"
        :style="slot === '{{ slot.starts_at.isoformat }}' ? 'background-color:' + accentColor : ''">
```

- [ ] **Step 5: Run widget tests**

Run:

```powershell
.\env\Scripts\activate; python -m pytest widget/tests.py tests/test_design_system.py -q
```

Expected: PASS for widget behavior, accent fallback, slot partials, booking source, and design drift tests.

---

### Task 10: Migrate Auth And Email Surfaces

**Files:**
- Modify: `templates/accounts/login.html`
- Modify: `templates/accounts/signup.html`
- Modify: `templates/emails/base_email.html`
- Modify: `templates/emails/confirmation_patient.html`
- Modify: `templates/emails/new_booking_staff.html`
- Modify: `templates/emails/reminder_patient.html`
- Test: `tests/test_design_system.py`

**Goal:** Remove old teal/sage email/auth styling and apply Stripe gradient/auth and inline email tokens.

- [ ] **Step 1: Apply Stripe auth panel pattern**

In `templates/accounts/login.html` and `templates/accounts/signup.html`, use `cf-auth-panel` for the brand side/panel and `cf-btn cf-btn-primary` for primary actions. Keep form fields rendered through existing Django form widgets and preserve `csrf_token` and form action behavior.

- [ ] **Step 2: Replace old email teal with Stripe indigo**

In `templates/emails/base_email.html`, replace old teal inline CSS with:

```html
<style>
  body { margin: 0; padding: 0; background: #f6f9fc; color: #0d253d; font-family: Arial, sans-serif; }
  .wrapper { width: 100%; background: #f6f9fc; padding: 24px 0; }
  .container { max-width: 640px; margin: 0 auto; background: #ffffff; border: 1px solid #e3e8ee; border-radius: 12px; overflow: hidden; }
  .header { background: #533afd; padding: 24px 32px; text-align: center; color: #ffffff; }
  .content { padding: 32px; }
  .muted { color: #64748d; }
  .btn { display: inline-block; padding: 10px 18px; background: #533afd; color: #ffffff; text-decoration: none; border-radius: 9999px; font-weight: 400; font-size: 14px; }
  .footer { padding: 20px 32px; color: #64748d; font-size: 12px; background: #f6f9fc; }
</style>
```

- [ ] **Step 3: Verify no old email teal remains**

Run:

```powershell
rg "#0891b2|#365449|#243a33|#2e493f|Stone-Sage|text-cyan|bg-cyan" templates/accounts templates/emails
```

Expected: no matches.

---

### Task 11: Remove Active Legacy Drift And Run Full Verification

**Files:**
- Modify: `static/css/kliniassist.css`
- Modify: `tests/test_design_system.py`
- Verify: all touched files

**Goal:** Finish the migration by removing active Stone-Sage drift and verifying project behavior.

- [ ] **Step 1: Search active app files for old design values**

Run:

```powershell
rg "Stone-Sage|#365449|#243a33|#2e493f|#ebe7dd|#f8f6ef|#0891b2|Cormorant|Manrope|IBM Plex|text-cyan-|bg-cyan-|border-cyan-|focus:border-cyan|focus:ring-cyan" DESIGN.md static templates dashboard clinics services widget tests --glob "!.superpowers/**"
```

Expected: no matches except historical migration files under `clinics/migrations/**` and `services/migrations/**` that preserve old migration state.

- [ ] **Step 2: Keep or remove CSS compatibility aliases based on search results**

If `rg "text-cyan-|bg-cyan-|border-slate-|ui-page-title|ui-input|ui-select|soft-card" templates static --glob "!static/css/kliniassist.css"` returns no active template matches, remove Tailwind color compatibility aliases from `static/css/kliniassist.css` and update `test_css_preserves_temporary_migration_aliases` into:

```python
def test_active_templates_do_not_depend_on_legacy_design_aliases():
    legacy_patterns = [
        "text-cyan-",
        "bg-cyan-",
        "border-cyan-",
        "focus:border-cyan",
        "focus:ring-cyan",
        "font-[850]",
    ]
    for relative_path in [
        "templates/dashboard/base.html",
        "templates/dashboard/home.html",
        "templates/dashboard/appointments.html",
        "templates/dashboard/calendar.html",
        "templates/widget/widget.html",
        "templates/widget/partials/slots.html",
    ]:
        template = source_text(relative_path)
        for pattern in legacy_patterns:
            assert pattern not in template
```

- [ ] **Step 3: Run Django system check**

Run:

```powershell
.\env\Scripts\activate; python manage.py check
```

Expected: `System check identified no issues`.

- [ ] **Step 4: Run focused tests**

Run:

```powershell
.\env\Scripts\activate; python -m pytest tests/test_design_system.py dashboard/tests.py widget/tests.py services/tests.py -q
```

Expected: PASS.

- [ ] **Step 5: Run full test suite**

Run:

```powershell
.\env\Scripts\activate; python -m pytest -q
```

Expected: PASS.

- [ ] **Step 6: Review final diff and dirty state**

Run:

```powershell
git status --short
git diff -- DESIGN.md static/css/kliniassist.css templates/base.html templates/dashboard templates/widget templates/accounts templates/emails dashboard/views.py clinics/models.py services/models.py tests/test_design_system.py dashboard/tests.py widget/tests.py services/tests.py docs/superpowers/specs/2026-06-02-stripe-design-system-migration-design.md docs/superpowers/plans/2026-06-02-stripe-design-system-migration-implementation.md
```

Expected: diff contains only the Stripe design-system migration and the approved spec/plan docs. Existing unrelated dirty files remain untouched.
