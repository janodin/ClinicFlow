# Assistant Live Preview Launcher Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the Assistant page live preview start with the launcher icon and open the widget iframe only after the admin clicks it.

**Architecture:** Keep this change entirely in the dashboard template and dashboard tests. Use Alpine state inside the existing Website Booking Widget card to mirror the public launcher/open/minimize behavior in a contained preview box, while the public `embed.js`, booking widget iframe, and booking internals remain unchanged.

**Tech Stack:** Django templates, Alpine.js, Tailwind utility classes, existing ClinicFlow `cf-*` design classes, pytest.

---

## Commit Rule

Do not commit during execution unless the user explicitly asks for commits.

## File Structure

- Modify: `dashboard/tests.py` - update the Assistant settings launcher embed test to assert the interactive live preview controls and copy.
- Modify: `templates/dashboard/assistant_settings.html` - replace the always-visible iframe live preview with a contained launcher-first preview using existing `iframe_url` and Alpine state.
- Do not modify `widget/views.py`, `widget/widget.html`, models, migrations, booking logic, public embed behavior, or appointment source behavior.

## Task 1: Interactive Assistant Live Preview

**Files:**
- Modify: `dashboard/tests.py:752-769`
- Modify: `templates/dashboard/assistant_settings.html:106-145`

- [ ] **Step 1: Write the failing dashboard preview test**

In `dashboard/tests.py`, update `test_assistant_settings_page_explains_launcher_first_embed_options` so it includes these assertions and no longer asserts the old preview sentence:

```python
@pytest.mark.django_db
def test_assistant_settings_page_explains_launcher_first_embed_options(clinic_setup, client):
    clinic, service, user = clinic_setup
    client.force_login(user)

    response = client.get(reverse("dashboard:assistant_settings"))
    content = response.content.decode()

    assert response.status_code == 200
    assert "previewOpen: false" in content
    assert "@click=\"previewOpen = true\"" in content
    assert "@click=\"previewOpen = false\"" in content
    assert "clinicflow-minimize" in content
    assert "Click the launcher to preview how patients open the widget." in content
    assert "aria-label=\"Open booking widget preview\"" in content
    assert "Book an appointment" in content
    assert "Recommended JavaScript launcher" in content
    assert "Adds a small bottom-right booking button" in content
    assert "full widget opens after click" in content
    assert "&lt;script src=" in content
    assert "Advanced iframe fallback" in content
    assert "Embeds the full panel directly" in content
    assert "visible immediately" in content
    assert "&lt;iframe src=" in content
    assert "Preview shows the full widget after a visitor opens the bottom-right launcher." not in content
```

- [ ] **Step 2: Run the preview test to verify it fails**

Run:

```powershell
.\env\Scripts\activate; if ($?) { python -m pytest dashboard/tests.py::test_assistant_settings_page_explains_launcher_first_embed_options -q }
```

Expected: FAIL because the current Assistant preview still renders the iframe immediately and still uses the old preview sentence.

- [ ] **Step 3: Update the Website Booking Widget Alpine state**

In `templates/dashboard/assistant_settings.html`, update the `Website Booking Widget` section opening `x-data` from:

```html
<section class="cf-card p-6" x-data="{urlCopied: false, scriptCopied: false, iframeCopied: false, accentColor:'{{ clinic.widget_accent_color|default:'#06b6d4' }}'}" x-init="const input=$el.querySelector('input[name=widget_accent_color]'); if(input){input.addEventListener('input',e=>accentColor=e.target.value); accentColor=input.value;}">
```

to:

```html
<section class="cf-card p-6" x-data="{urlCopied: false, scriptCopied: false, iframeCopied: false, previewOpen: false, accentColor:'{{ clinic.widget_accent_color|default:'#06b6d4' }}'}" x-init="const input=$el.querySelector('input[name=widget_accent_color]'); if(input){input.addEventListener('input',e=>accentColor=e.target.value); accentColor=input.value;} window.addEventListener('message', event => { if (event.data && event.data.type === 'clinicflow-minimize') { previewOpen = false; } });">
```

- [ ] **Step 4: Replace the live preview markup**

In `templates/dashboard/assistant_settings.html`, replace the current live preview block:

```html
        <div>
          <p class="cf-kpi-label mb-2">Live Preview</p>
          <div class="overflow-hidden rounded-lg border border-[var(--cf-line)]">
            <iframe src="{{ iframe_url }}" class="h-[420px] sm:h-[520px]" style="width:100%;border:none;" allow="clipboard-write"></iframe>
          </div>
          <p class="mt-2 text-xs text-[var(--cf-muted)]">Preview shows the full widget after a visitor opens the bottom-right launcher.</p>
        </div>
```

with:

```html
        <div>
          <p class="cf-kpi-label mb-2">Live Preview</p>
          <div class="relative h-[420px] overflow-hidden rounded-lg border border-[var(--cf-line)] bg-[var(--cf-surface-muted)] sm:h-[520px]">
            <div class="absolute inset-0 bg-[radial-gradient(circle_at_top_right,rgba(6,182,212,.16),transparent_38%),linear-gradient(135deg,#ffffff,#f0fdff)]"></div>
            <div class="relative z-10 flex h-full flex-col justify-between p-4">
              <div>
                <p class="text-xs font-semibold uppercase tracking-[0.12em] text-[var(--cf-muted)]">Clinic website preview</p>
                <div class="mt-3 h-3 w-32 rounded-full bg-[var(--cf-line)]"></div>
                <div class="mt-2 h-2 w-44 rounded-full bg-[var(--cf-line)]/70"></div>
              </div>

              <button x-show="!previewOpen" x-transition @click="previewOpen = true" type="button" class="absolute bottom-4 right-4 grid h-[60px] w-[60px] place-items-center rounded-full text-white shadow-[0_10px_24px_rgba(8,51,68,.22)] transition hover:scale-105 focus:outline focus:outline-3 focus:outline-offset-4 focus:outline-[rgba(8,51,68,.35)]" :style="'background-color:' + accentColor" aria-label="Open booking widget preview" title="Book an appointment">
                <i data-lucide="calendar-days" class="h-7 w-7" aria-hidden="true"></i>
              </button>

              <div x-show="previewOpen" x-transition class="absolute inset-0 bg-transparent">
                <button @click="previewOpen = false" type="button" class="absolute right-3 top-3 z-20 rounded-full bg-white/90 px-3 py-1.5 text-xs font-semibold text-[var(--cf-ink)] shadow-sm ring-1 ring-[var(--cf-line)] hover:bg-white">
                  Minimize preview
                </button>
                <iframe src="{{ iframe_url }}" class="h-full w-full" style="border:none;" allow="clipboard-write"></iframe>
              </div>
            </div>
          </div>
          <p class="mt-2 text-xs text-[var(--cf-muted)]">Click the launcher to preview how patients open the widget.</p>
        </div>
```

- [ ] **Step 5: Run the updated preview test to verify it passes**

Run:

```powershell
.\env\Scripts\activate; if ($?) { python -m pytest dashboard/tests.py::test_assistant_settings_page_explains_launcher_first_embed_options -q }
```

Expected: selected test passes.

- [ ] **Step 6: Run targeted dashboard/design-system regression tests**

Run:

```powershell
.\env\Scripts\activate; if ($?) { python -m pytest dashboard/tests.py::test_assistant_settings_page_explains_launcher_first_embed_options dashboard/tests.py::test_assistant_settings_page_shows_shared_ai_prompt_form tests/test_design_system.py::test_mobile_responsive_calendar_and_widget_use_safe_viewports tests/test_design_system.py::test_mobile_responsive_dynamic_text_has_wrapping_guards -q }
```

Expected: all selected tests pass.

## Requirements Traceability

- Preview starts with only launcher icon: Task 1, Steps 1 and 4.
- Clicking launcher opens iframe inside preview: Task 1, Steps 1 and 4.
- Minimize returns to launcher: Task 1, Steps 1, 3, and 4.
- Preview uses existing `iframe_url`: Task 1, Step 4.
- No public embed/runtime booking changes: File Structure and Task 1 scope.
