# Neon Aqua Theme Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Do not commit unless the user explicitly requests it.

**Goal:** Repaint ClinicFlow from the current indigo/navy design system to the approved neon aqua clinical theme across CSS, docs, widget defaults, emails, calendar colors, and tests.

**Architecture:** Keep the existing Django template and Tailwind CDN architecture unchanged. Centralize the visual change in `static/css/clinicflow.css` tokens and update only hardcoded color defaults/assertions that bypass those tokens.

**Tech Stack:** Django, Django templates, Tailwind utility classes, CSS custom properties, pytest.

---

## File Structure

- Modify `DESIGN.md`: rename and document the new neon aqua clinical design language and token values.
- Modify `static/css/clinicflow.css`: replace indigo/purple/navy token values, gradients, shadows, compatibility aliases, and glow treatments with aqua/cyan values.
- Modify `clinics/models.py`: change `DEFAULT_WIDGET_ACCENT_COLOR` and validator copy to the new aqua brand value.
- Modify `services/models.py`: change the default service color to the new aqua brand value.
- Modify `templates/dashboard/assistant_settings.html`: change the Alpine fallback color from indigo to aqua.
- Modify `templates/emails/base_email.html`: change hardcoded email colors to aqua/teal/ice surfaces.
- Modify `dashboard/views.py`: update FullCalendar confirmed/info colors to aqua values while preserving other appointment status semantics.
- Modify `services/tests.py`: update service default color expectations.
- Modify `tests/test_design_system.py`: update token expectations, forbidden legacy color checks, and copy where needed.

## Task 1: Lock Theme Tests First

**Files:**
- Modify: `tests/test_design_system.py`

- [ ] **Step 1: Update token expectations**

Replace the `expected_tokens` list in `test_css_uses_stripe_tokens_and_typography` with the new aqua theme tokens:

```python
    expected_tokens = [
        "--cf-brand: #06b6d4",
        "--cf-brand-hover: #0891b2",
        "--cf-brand-strong: #0e7490",
        "--cf-dashboard-dark: #052f3a",
        "--cf-ink: #083344",
        "--cf-muted: #527486",
        "--cf-bg: #ffffff",
        "--cf-bg-strong: #f0fdff",
        "--cf-surface-warm: #f0fdff",
        "--cf-line: #d5f3f8",
        "--cf-input-line: #8ed8e8",
        "--cf-focus: rgba(6, 182, 212, .24)",
    ]
```

- [ ] **Step 2: Rename test intent**

Rename `test_css_uses_stripe_tokens_and_typography` to:

```python
def test_css_uses_neon_aqua_tokens_and_typography():
```

- [ ] **Step 3: Keep legacy color guardrails relevant**

Keep the forbidden old stone-sage and raw legacy colors. Add the old indigo theme colors to the forbidden list so the repaint is comprehensive:

```python
        "#533afd",
        "#4434d4",
        "#2e2b8c",
        "#1c1e54",
        "#ededff",
```

- [ ] **Step 4: Run failing design tests**

Run: `./env/Scripts/python -m pytest tests/test_design_system.py -q`

Expected: fail because production CSS/docs/templates still contain old indigo values.

## Task 2: Repaint CSS Tokens And Global Effects

**Files:**
- Modify: `static/css/clinicflow.css`

- [ ] **Step 1: Replace root tokens**

Replace the token block with these values while preserving variable names:

```css
  --cf-bg: #ffffff;
  --cf-bg-strong: #f0fdff;
  --cf-surface: #ffffff;
  --cf-surface-warm: #f0fdff;
  --cf-surface-muted: #e6faff;
  --cf-surface-tint: #ecfeff;
  --cf-line: #d5f3f8;
  --cf-line-soft: #e6faff;
  --cf-input-line: #8ed8e8;
  --cf-ink: #083344;
  --cf-ink-secondary: #164e63;
  --cf-muted: #527486;
  --cf-faint: #6b8fa0;
  --cf-brand: #06b6d4;
  --cf-brand-hover: #0891b2;
  --cf-brand-strong: #0e7490;
  --cf-brand-soft: #ecfeff;
  --cf-dashboard-dark: #052f3a;
  --cf-warm-interlude: #e0fbff;
  --cf-ruby: #ea2261;
  --cf-magenta: #22d3ee;
  --cf-lemon: #0f766e;
  --cf-info: #0891b2;
  --cf-info-soft: #ecfeff;
  --cf-warning: #9b6829;
  --cf-warning-soft: #fff6e7;
  --cf-danger: #b3194a;
  --cf-danger-soft: #fde8ef;
  --cf-focus: rgba(6, 182, 212, .24);
```

- [ ] **Step 2: Replace body gradient**

Use a cool aqua glow backdrop:

```css
  background:
    radial-gradient(circle at 12% 0%, rgba(34, 211, 238, .20), transparent 20rem),
    radial-gradient(circle at 82% 4%, rgba(6, 182, 212, .18), transparent 24rem),
    linear-gradient(180deg, var(--cf-bg-strong) 0%, var(--cf-bg) 48%);
```

- [ ] **Step 3: Replace blue shadow tints**

Use teal/cyan shadow color values for card and raised shadows:

```css
  --cf-shadow-card: 0 1px 3px rgba(8, 51, 68, .08);
  --cf-shadow-raised: 0 8px 24px rgba(8, 51, 68, .10), 0 2px 6px rgba(8, 51, 68, .05);
  --cf-shadow-subtle: 0 2px 8px rgba(8, 51, 68, .07);
```

- [ ] **Step 4: Update hardcoded CSS values**

Replace remaining old indigo hardcoded CSS colors in `clinicflow.css` with token equivalents or aqua values:

```text
#533afd -> #06b6d4
#4434d4 -> #0891b2
#2e2b8c -> #0e7490
#1c1e54 -> #052f3a
#0d253d -> #083344
#ededff -> #ecfeff
rgba(83, 58, 253, .22) -> rgba(6, 182, 212, .24)
```

- [ ] **Step 5: Update gradient mesh**

Change the marketing/widget glow mesh from lavender/indigo/ruby toward white, ice cyan, aqua, and deep teal while keeping danger ruby only for error semantics.

## Task 3: Update Hardcoded App Defaults

**Files:**
- Modify: `clinics/models.py`
- Modify: `templates/dashboard/assistant_settings.html`
- Modify: `templates/emails/base_email.html`
- Modify: `dashboard/views.py`

- [ ] **Step 1: Widget default accent**

In `clinics/models.py`, change:

```python
DEFAULT_WIDGET_ACCENT_COLOR = "#06b6d4"
```

and update the validator message example to `#06b6d4`.

- [ ] **Step 2: Assistant settings fallback**

In `templates/dashboard/assistant_settings.html`, change the fallback in `x-data` to:

```html
accentColor:'{{ clinic.widget_accent_color|default:'#06b6d4' }}'
```

- [ ] **Step 3: Email base colors**

In `templates/emails/base_email.html`, use the aqua theme values:

```css
body { margin: 0; padding: 0; background: #f0fdff; color: #083344; font-family: Arial, sans-serif; }
.wrapper { width: 100%; background: #f0fdff; padding: 24px 0; }
.container { max-width: 640px; margin: 0 auto; background: #ffffff; border: 1px solid #d5f3f8; border-radius: 12px; overflow: hidden; }
.header { background: #06b6d4; padding: 24px 32px; text-align: center; color: #ffffff; }
.detail-row { margin: 0 0 10px; padding-bottom: 10px; border-bottom: 1px solid #d5f3f8; color: #083344; }
.detail-label { color: #527486; font-weight: 700; }
.muted { color: #527486; }
.btn { display: inline-block; padding: 10px 18px; background: #06b6d4; color: #ffffff; text-decoration: none; border-radius: 9999px; font-weight: 400; font-size: 14px; }
.footer { padding: 20px 32px; color: #527486; font-size: 12px; background: #f0fdff; }
```

- [ ] **Step 4: Calendar confirmed colors**

In `dashboard/views.py`, change `Appointment.STATUS_CONFIRMED` in `color_map` to:

```python
Appointment.STATUS_CONFIRMED: {"backgroundColor": "#ecfeff", "borderColor": "#06b6d4", "textColor": "#0e7490"},
```

## Task 4: Update Design Documentation

**Files:**
- Modify: `DESIGN.md`
- Modify: `docs/superpowers/specs/2026-06-02-neon-aqua-theme-design.md` only if implementation discovers a necessary adjustment.

- [ ] **Step 1: Rename design identity**

Change the frontmatter name and description from Stripe/indigo to Neon Aqua Clinical.

- [ ] **Step 2: Update color tokens**

Replace the frontmatter color token values with the aqua palette from the approved spec.

- [ ] **Step 3: Update narrative sections**

Rewrite the overview and key characteristics so they describe:

```text
cool white clinical surfaces, deep teal/navy operational shell, electric aqua CTAs, ice-cyan highlights, and subtle cyan glow accents inspired by illuminated setup imagery.
```

- [ ] **Step 4: Remove inaccurate indigo/Stripe claims**

Search `DESIGN.md` for `Stripe`, `indigo`, `lavender`, `electric indigo`, and `#533afd`; replace or remove claims that no longer apply.

## Task 5: Run Verification And Fix Drift

**Files:**
- Modify only files with failing assertions or discovered old hardcoded colors.

- [ ] **Step 1: Search old colors**

Run:

```powershell
rg "#533afd|#4434d4|#2e2b8c|#1c1e54|#0d253d|#ededff|rgba\(83, 58, 253" .
```

Expected: no old theme values in active source files. If matches remain in historical docs that should be updated, update them; if matches remain in migrations because of historical defaults, leave them unless Django requires a new migration.

- [ ] **Step 2: Run targeted tests**

Run:

```powershell
./env/Scripts/python -m pytest tests/test_design_system.py -q
```

Expected: pass.

- [ ] **Step 3: Run Django check**

Run:

```powershell
./env/Scripts/python manage.py check
```

Expected: `System check identified no issues`.

- [ ] **Step 4: Check migrations only if needed**

Run:

```powershell
./env/Scripts/python manage.py makemigrations --check --dry-run
```

Expected: ideally `No changes detected`. If Django detects a default change migration for `Clinic.widget_accent_color`, create the migration with `makemigrations` and include it in the final summary.

## Self-Review

- Spec coverage: CSS tokens/effects, docs, widget defaults, assistant fallback, email, calendar, and tests are covered.
- Placeholder scan: no placeholder instructions are present.
- Type consistency: existing variable names and field names are preserved.
