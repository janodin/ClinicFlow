# Widget Launcher First Embed Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the recommended website widget integration load as a small bottom-right icon-only launcher and open the full booking widget only after visitor click.

**Architecture:** Keep Django as the server-rendered source of truth. Polish the existing `embed_js` script path, keep iframe booking and minimize messaging unchanged, and update dashboard copy so JavaScript is the recommended launcher-first embed while raw iframe is an advanced full-panel fallback.

**Tech Stack:** Django, Django templates, Tailwind utility classes, Alpine.js copy buttons, pytest, existing KliniAssist `cf-*` design classes.

---

## Commit Rule

Do not commit during execution unless the user explicitly asks for commits. This project's `AGENTS.md` and OpenCode instructions require explicit commit permission.

## File Structure

- Modify: `widget/tests.py` - add focused regression tests for accessible launcher UI and click-scoped iframe behavior.
- Modify: `widget/views.py` - update only `embed_js` launcher attributes/icon/focus styling; preserve source URL, iframe open/minimize behavior, and safe accent handling.
- Modify: `dashboard/tests.py` - add dashboard content tests for launcher-first copy on Assistant settings and the dedicated widget embed page.
- Modify: `templates/dashboard/assistant_settings.html` - clarify live preview and present JavaScript as recommended launcher-first embed; demote iframe to advanced fallback.
- Modify: `templates/dashboard/widget_embed.html` - keep the legacy/dedicated embed page consistent with the same recommended/advanced distinction.
- Do not modify models or migrations.

## Task 1: Polish The Runtime Launcher

**Files:**
- Modify: `widget/tests.py:41-55`
- Modify: `widget/views.py:175-217`

- [ ] **Step 1: Add failing widget launcher tests**

Add these methods immediately after `test_embed_js_returns_javascript` in `widget/tests.py`:

```python
    def test_embed_js_uses_accessible_icon_only_calendar_launcher(self):
        response = self.client.get(reverse("widget:embed_js", args=[self.clinic.slug]))
        content = response.content.decode()

        self.assertIn("var launcher = document.createElement('button');", content)
        self.assertIn("launcher.setAttribute('type', 'button');", content)
        self.assertIn("launcher.setAttribute('aria-label', 'Open booking widget');", content)
        self.assertIn("launcher.setAttribute('title', 'Book an appointment');", content)
        self.assertIn('aria-hidden="true"', content)
        self.assertIn("M8 2v4", content)
        self.assertNotIn("M21 15a2", content)
        self.assertNotIn("Book now", content)
        self.assertIn("outlineColor", content)

    def test_embed_js_opens_iframe_from_launcher_click_path(self):
        response = self.client.get(reverse("widget:embed_js", args=[self.clinic.slug]))
        content = response.content.decode()

        click_index = content.index("launcher.addEventListener('click'")
        iframe_create_index = content.index("iframe = document.createElement('iframe');")
        iframe_append_index = content.index("document.body.appendChild(iframe);")
        launcher_append_index = content.index("document.body.appendChild(launcher);")

        self.assertGreater(iframe_create_index, click_index)
        self.assertGreater(iframe_append_index, click_index)
        self.assertGreater(launcher_append_index, iframe_append_index)
        self.assertIn("?source=embed", content)
        self.assertIn("launcher.style.display = 'none';", content)
        self.assertIn("kliniassist-minimize", content)
        self.assertIn("iframe.style.display = 'none';", content)
        self.assertIn("launcher.style.display = 'flex';", content)
```

- [ ] **Step 2: Run widget tests to verify the new accessibility/icon test fails**

Run:

```powershell
.\env\Scripts\activate; if ($?) { python -m pytest widget/tests.py::WidgetTests::test_embed_js_uses_accessible_icon_only_calendar_launcher widget/tests.py::WidgetTests::test_embed_js_opens_iframe_from_launcher_click_path -q }
```

Expected: `test_embed_js_uses_accessible_icon_only_calendar_launcher` fails because the current launcher has no `type` attribute, no title, no calendar icon path, and no focus outline handling. `test_embed_js_opens_iframe_from_launcher_click_path` may already pass because the click path exists.

- [ ] **Step 3: Replace `embed_js` with the polished launcher implementation**

Replace `widget/views.py` `embed_js` with this function:

```python
def embed_js(request, clinic_slug):
    clinic = get_object_or_404(Clinic, slug=clinic_slug, is_active=True)
    src = request.build_absolute_uri(reverse("widget:home", args=[clinic.slug])) + "?source=embed"
    accent = clinic.safe_widget_accent_color
    body = f"""
(function() {{
  var accent = {json.dumps(accent)};
  var src = {json.dumps(src)};
  var iframe;
  var launcher = document.createElement('button');
  launcher.setAttribute('type', 'button');
  launcher.setAttribute('aria-label', 'Open booking widget');
  launcher.setAttribute('title', 'Book an appointment');
  launcher.innerHTML = '<svg aria-hidden="true" focusable="false" xmlns="http://www.w3.org/2000/svg" width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M8 2v4"/><path d="M16 2v4"/><rect width="18" height="18" x="3" y="4" rx="2"/><path d="M3 10h18"/><path d="M8 14h.01"/><path d="M12 14h.01"/><path d="M16 14h.01"/></svg>';
  launcher.style.cssText = 'position:fixed;bottom:max(16px, env(safe-area-inset-bottom));right:max(16px, env(safe-area-inset-right));width:60px;height:60px;border-radius:50%;border:none;z-index:9999;background:' + accent + ';color:white;cursor:pointer;box-shadow:0 10px 24px rgba(8,51,68,0.22);display:flex;align-items:center;justify-content:center;transition:transform .2s, box-shadow .2s;outline:3px solid transparent;outline-offset:3px;';
  launcher.addEventListener('mouseenter', function() {{ launcher.style.transform = 'scale(1.05)'; }});
  launcher.addEventListener('mouseleave', function() {{ launcher.style.transform = 'scale(1)'; }});
  launcher.addEventListener('focus', function() {{ launcher.style.outlineColor = 'rgba(8,51,68,0.35)'; }});
  launcher.addEventListener('blur', function() {{ launcher.style.outlineColor = 'transparent'; }});
  launcher.addEventListener('click', function() {{
    if (!iframe) {{
      iframe = document.createElement('iframe');
      iframe.src = src;
      iframe.style.cssText = 'position:fixed;bottom:max(16px, env(safe-area-inset-bottom));right:max(16px, env(safe-area-inset-right));width:420px;max-width:calc(100vw - 32px - env(safe-area-inset-right));height:680px;max-height:calc(100dvh - 32px - env(safe-area-inset-bottom));border:none;z-index:9999;background:transparent;border-radius:24px;box-shadow:0 20px 50px rgba(0,0,0,0.2);opacity:0;transform:translateY(20px);transition:opacity .3s, transform .3s;';
      iframe.allow = 'clipboard-write';
      document.body.appendChild(iframe);
      requestAnimationFrame(function() {{ iframe.style.opacity = '1'; iframe.style.transform = 'translateY(0)'; }});
    }} else {{
      iframe.style.display = 'block';
      requestAnimationFrame(function() {{ iframe.style.opacity = '1'; iframe.style.transform = 'translateY(0)'; }});
    }}
    launcher.style.display = 'none';
  }});
  document.body.appendChild(launcher);
  window.addEventListener('message', function(e) {{
    if (e.data && e.data.type === 'kliniassist-minimize') {{
      if (iframe) {{
        iframe.style.opacity = '0';
        iframe.style.transform = 'translateY(20px)';
        setTimeout(function() {{ iframe.style.display = 'none'; }}, 300);
      }}
      launcher.style.display = 'flex';
    }}
  }});
}})();
"""
    return HttpResponse(body, content_type="application/javascript")
```

- [ ] **Step 4: Run widget launcher tests to verify they pass**

Run:

```powershell
.\env\Scripts\activate; if ($?) { python -m pytest widget/tests.py::WidgetTests::test_embed_js_returns_javascript widget/tests.py::WidgetTests::test_embed_js_uses_accessible_icon_only_calendar_launcher widget/tests.py::WidgetTests::test_embed_js_opens_iframe_from_launcher_click_path widget/tests.py::WidgetTests::test_embed_js_uses_safe_accent_color_for_invalid_stored_value -q }
```

Expected: all 4 selected tests pass.

## Task 2: Clarify Assistant Page Embed Hierarchy

**Files:**
- Modify: `dashboard/tests.py:686-699`
- Modify: `templates/dashboard/assistant_settings.html:105-176`

- [ ] **Step 1: Add failing Assistant page copy test**

Add this test after `test_assistant_settings_page_creates_default_shared_ai_settings` in `dashboard/tests.py`:

```python
@pytest.mark.django_db
def test_assistant_settings_page_explains_launcher_first_embed_options(clinic_setup, client):
    clinic, service, user = clinic_setup
    client.force_login(user)

    response = client.get(reverse("dashboard:assistant_settings"))
    content = response.content.decode()

    assert response.status_code == 200
    assert "Preview shows the full widget after a visitor opens the bottom-right launcher." in content
    assert "Recommended JavaScript launcher" in content
    assert "Adds a small bottom-right booking button" in content
    assert "full widget opens after click" in content
    assert "&lt;script src=" in content
    assert "Advanced iframe fallback" in content
    assert "Embeds the full panel directly" in content
    assert "visible immediately" in content
    assert "&lt;iframe src=" in content
```

- [ ] **Step 2: Run Assistant page copy test to verify it fails**

Run:

```powershell
.\env\Scripts\activate; if ($?) { python -m pytest dashboard/tests.py::test_assistant_settings_page_explains_launcher_first_embed_options -q }
```

Expected: FAIL because the current page says only `JavaScript`, `Iframe`, and `This is how patients will see your widget on your website.`

- [ ] **Step 3: Update Assistant page preview and embed copy**

In `templates/dashboard/assistant_settings.html`, replace the live preview note at line 111 with:

```html
          <p class="mt-2 text-xs text-[var(--cf-muted)]">Preview shows the full widget after a visitor opens the bottom-right launcher.</p>
```

Then replace the embed grid from the `<div class="grid gap-5 md:grid-cols-2">` opening through its matching closing `</div>` before the `<!-- Embed -->` section closes with:

```html
      <div class="grid gap-5 md:grid-cols-[minmax(0,1.1fr)_minmax(0,.9fr)]">
        <!-- JavaScript Embed -->
        <div class="rounded-lg border border-[var(--cf-brand-soft)] bg-[var(--cf-surface)] p-4 shadow-sm">
          <div class="mb-2 flex flex-wrap items-center gap-2">
            <i data-lucide="file-code" class="h-4 w-4 text-[var(--cf-brand)]"></i>
            <p class="text-sm font-semibold text-[var(--cf-ink)]">Recommended JavaScript launcher</p>
            <span class="cf-badge cf-badge-info">Recommended</span>
          </div>
          <p class="text-xs text-[var(--cf-muted)] mb-3">Paste before the closing <code class="rounded bg-[var(--cf-surface-muted)] px-1 py-0.5 text-[var(--cf-blue)]">&lt;/body&gt;</code> tag. Adds a small bottom-right booking button. The full widget opens after click.</p>
          <div class="relative">
            <pre class="whitespace-pre-wrap break-words rounded-lg bg-[var(--cf-ink)] p-4 pr-24 text-xs text-[var(--cf-brand-soft)]" id="script-code">&lt;script src="{{ script_url }}"&gt;&lt;/script&gt;</pre>
            <button @click="navigator.clipboard.writeText(document.getElementById('script-code').innerText).then(() => {scriptCopied=true; setTimeout(() => scriptCopied=false, 2000)})" class="absolute right-2 top-2 inline-flex items-center gap-1 rounded-md bg-white/10 px-2 py-1 text-xs font-bold text-white hover:bg-white/20" type="button">
              <i data-lucide="copy" class="h-3 w-3" x-show="!scriptCopied"></i>
              <i data-lucide="check" class="h-3 w-3" x-show="scriptCopied" x-cloak></i>
              <span x-show="!scriptCopied">Copy</span>
              <span x-show="scriptCopied" x-cloak>Copied</span>
            </button>
          </div>
        </div>

        <!-- Iframe Embed -->
        <div class="rounded-lg border border-[var(--cf-line)] bg-[var(--cf-surface-muted)] p-4">
          <div class="flex items-center gap-2 mb-2">
            <i data-lucide="frame" class="h-4 w-4 text-[var(--cf-muted)]"></i>
            <p class="text-sm font-semibold text-[var(--cf-ink)]">Advanced iframe fallback</p>
          </div>
          <p class="text-xs text-[var(--cf-muted)] mb-3">Embeds the full panel directly and can be visible immediately. Use only for custom placements where you intentionally want the widget panel shown.</p>
          <div class="relative">
            <pre class="whitespace-pre-wrap break-words rounded-lg bg-[var(--cf-ink)] p-4 pr-24 text-xs text-[var(--cf-brand-soft)]" id="iframe-code">&lt;iframe src="{{ iframe_url }}" style="position:fixed;bottom:max(16px, env(safe-area-inset-bottom));right:max(16px, env(safe-area-inset-right));width:420px;max-width:calc(100vw - 32px - env(safe-area-inset-right));height:680px;max-height:calc(100dvh - 32px - env(safe-area-inset-bottom));border:none;z-index:9999;background:transparent;border-radius:24px;box-shadow:0 20px 50px rgba(0,0,0,0.2);" allow="clipboard-write"&gt;&lt;/iframe&gt;</pre>
            <button @click="navigator.clipboard.writeText(document.getElementById('iframe-code').innerText).then(() => {iframeCopied=true; setTimeout(() => iframeCopied=false, 2000)})" class="absolute right-2 top-2 inline-flex items-center gap-1 rounded-md bg-white/10 px-2 py-1 text-xs font-bold text-white hover:bg-white/20" type="button">
              <i data-lucide="copy" class="h-3 w-3" x-show="!iframeCopied"></i>
              <i data-lucide="check" class="h-3 w-3" x-show="iframeCopied" x-cloak></i>
              <span x-show="!iframeCopied">Copy</span>
              <span x-show="iframeCopied" x-cloak>Copied</span>
            </button>
          </div>
        </div>
      </div>
```

- [ ] **Step 4: Run Assistant page copy test to verify it passes**

Run:

```powershell
.\env\Scripts\activate; if ($?) { python -m pytest dashboard/tests.py::test_assistant_settings_page_explains_launcher_first_embed_options dashboard/tests.py::test_assistant_settings_page_shows_shared_ai_prompt_form -q }
```

Expected: both selected tests pass.

## Task 3: Keep Dedicated Widget Embed Page Consistent

**Files:**
- Modify: `dashboard/tests.py:1325-1338`
- Modify: `templates/dashboard/widget_embed.html:1-36`

- [ ] **Step 1: Add failing dedicated embed page copy test**

Add this test immediately before `test_widget_embed_iframe_uses_embed_source_and_responsive_dimensions` in `dashboard/tests.py`:

```python
@pytest.mark.django_db
def test_widget_embed_page_explains_recommended_launcher_and_advanced_iframe(clinic_setup, client):
    clinic, service, user = clinic_setup
    client.force_login(user)

    response = client.get(reverse("dashboard:widget_embed"))
    content = response.content.decode()

    assert response.status_code == 200
    assert "Recommended JavaScript launcher" in content
    assert "Adds a small bottom-right booking button" in content
    assert "full widget opens after click" in content
    assert "&lt;script src=" in content
    assert "Advanced iframe fallback" in content
    assert "Embeds the full panel directly" in content
    assert "visible immediately" in content
    assert "&lt;iframe src=" in content
```

- [ ] **Step 2: Run dedicated embed page copy test to verify it fails**

Run:

```powershell
.\env\Scripts\activate; if ($?) { python -m pytest dashboard/tests.py::test_widget_embed_page_explains_recommended_launcher_and_advanced_iframe -q }
```

Expected: FAIL because the current page uses `JavaScript Embed (Recommended)` and `Iframe Embed` copy without the launcher-first/full-panel distinction.

- [ ] **Step 3: Replace the dedicated widget embed template**

Replace the entire content of `templates/dashboard/widget_embed.html` with:

```html
{% extends "dashboard/base.html" %}
{% block title %}Widget Embed{% endblock %}
{% block content %}
<div class="cf-page" x-data="{copied: ''}">
  <div class="cf-page-header">
    <div>
      <h1 class="cf-page-title ui-page-title">Widget Embed</h1>
      <p class="cf-page-description">Copy the recommended launcher script or use the advanced iframe fallback for custom placements.</p>
    </div>
  </div>
  <section class="cf-card p-6 border border-[var(--cf-brand-soft)]">
    <div class="flex flex-wrap items-center gap-2">
      <h2 class="cf-section-title">Recommended JavaScript launcher</h2>
      <span class="cf-badge cf-badge-info">Recommended</span>
    </div>
    <p class="cf-muted mt-2 text-sm">Adds a small bottom-right booking button. The full widget opens after click.</p>
    <div class="relative mt-4">
      <pre class="overflow-x-auto rounded-xl bg-[var(--cf-dashboard-dark)] p-5 text-sm text-white shadow-[var(--cf-shadow-raised)]" id="script-code">&lt;script src="{{ script_url }}"&gt;&lt;/script&gt;</pre>
      <button @click="navigator.clipboard.writeText(document.getElementById('script-code').innerText).then(() => {copied='script'; setTimeout(() => copied='', 2000)})" class="absolute right-3 top-3 rounded-xl bg-white/10 px-3 py-1.5 text-xs font-bold text-white hover:bg-white/20">Copy</button>
      <span x-show="copied==='script'" x-transition class="absolute right-3 top-12 rounded-lg bg-green-600 px-2 py-1 text-xs font-bold text-white">Copied!</span>
    </div>
  </section>
  <section class="cf-card p-6">
    <h2 class="cf-section-title">Advanced iframe fallback</h2>
    <p class="cf-muted mt-2 text-sm">Embeds the full panel directly and can be visible immediately. Use only for custom placements where you intentionally want the widget panel shown.</p>
    <div class="relative mt-4">
      <pre class="overflow-x-auto rounded-xl bg-[var(--cf-dashboard-dark)] p-5 text-sm text-white shadow-[var(--cf-shadow-raised)]" id="iframe-code">&lt;iframe src="{{ iframe_url }}" style="position:fixed;bottom:max(16px, env(safe-area-inset-bottom));right:max(16px, env(safe-area-inset-right));width:420px;max-width:calc(100vw - 32px - env(safe-area-inset-right));height:680px;max-height:calc(100dvh - 32px - env(safe-area-inset-bottom));border:none;z-index:9999;background:transparent;border-radius:24px;box-shadow:0 20px 50px rgba(0,0,0,0.2);" allow="clipboard-write"&gt;&lt;/iframe&gt;</pre>
      <button @click="navigator.clipboard.writeText(document.getElementById('iframe-code').innerText).then(() => {copied='iframe'; setTimeout(() => copied='', 2000)})" class="absolute right-3 top-3 rounded-xl bg-white/10 px-3 py-1.5 text-xs font-bold text-white hover:bg-white/20">Copy</button>
      <span x-show="copied==='iframe'" x-transition class="absolute right-3 top-12 rounded-lg bg-green-600 px-2 py-1 text-xs font-bold text-white">Copied!</span>
    </div>
  </section>
  <section class="cf-card p-6">
    <h2 class="cf-section-title">Preview</h2>
    <p class="cf-muted mt-2 text-sm">Preview shows the full widget after a visitor opens the bottom-right launcher.</p>
    <div class="mt-4 overflow-hidden rounded-xl border border-[var(--cf-line)] shadow-[var(--cf-shadow-raised)]" style="max-width:420px;">
      <iframe src="{{ iframe_url }}" style="width:100%;height:500px;border:none;" allow="clipboard-write"></iframe>
    </div>
  </section>
</div>
{% endblock %}
```

- [ ] **Step 4: Run dedicated embed page tests to verify they pass**

Run:

```powershell
.\env\Scripts\activate; if ($?) { python -m pytest dashboard/tests.py::test_widget_embed_page_explains_recommended_launcher_and_advanced_iframe dashboard/tests.py::test_widget_embed_iframe_uses_embed_source_and_responsive_dimensions -q }
```

Expected: both selected tests pass.

## Task 4: Targeted Regression Verification

**Files:**
- No edits expected.

- [ ] **Step 1: Run targeted widget, dashboard, and design-system checks**

Run:

```powershell
.\env\Scripts\activate; if ($?) { python -m pytest widget/tests.py::WidgetTests::test_embed_js_returns_javascript widget/tests.py::WidgetTests::test_embed_js_uses_accessible_icon_only_calendar_launcher widget/tests.py::WidgetTests::test_embed_js_opens_iframe_from_launcher_click_path widget/tests.py::WidgetTests::test_embed_js_uses_safe_accent_color_for_invalid_stored_value dashboard/tests.py::test_assistant_settings_page_explains_launcher_first_embed_options dashboard/tests.py::test_assistant_settings_page_shows_shared_ai_prompt_form dashboard/tests.py::test_widget_embed_page_explains_recommended_launcher_and_advanced_iframe dashboard/tests.py::test_widget_embed_iframe_uses_embed_source_and_responsive_dimensions tests/test_design_system.py::test_mobile_responsive_calendar_and_widget_use_safe_viewports tests/test_design_system.py::test_mobile_responsive_dynamic_text_has_wrapping_guards -q }
```

Expected: all selected tests pass.

- [ ] **Step 2: Run Django system check**

Run:

```powershell
.\env\Scripts\activate; if ($?) { python manage.py check }
```

Expected: `System check identified no issues`.

- [ ] **Step 3: Inspect the final diff**

Run:

```powershell
git diff -- widget/views.py widget/tests.py dashboard/tests.py templates/dashboard/assistant_settings.html templates/dashboard/widget_embed.html docs/superpowers/specs/2026-06-03-widget-launcher-first-embed-design.md docs/superpowers/plans/2026-06-03-widget-launcher-first-embed-implementation-plan.md
```

Expected: diff is limited to the approved launcher-first embed spec, implementation plan, widget runtime polish, tests, and dashboard copy updates.

## Requirements Traceability

- Small bottom-right icon-only launcher: Task 1.
- Full widget opens only after click: Task 1.
- Minimize returns to launcher: Task 1.
- JavaScript embed is recommended/default in dashboard copy: Tasks 2 and 3.
- Raw iframe remains advanced/manual full-panel fallback: Tasks 2 and 3.
- Existing booking and tenant safety behavior unchanged: Task 1 preserves `?source=embed`; Task 4 runs existing source/safe-viewport tests; no model, booking, service, patient, slot, or appointment logic changes.
