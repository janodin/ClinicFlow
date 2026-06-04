# Widget Launcher First Embed Design

## Goal

Make the Website Booking Widget behave like common website widget integrations: embedded clinic websites should show a small bottom-right launcher first, and the full booking widget should open only after a visitor clicks it.

The change should reduce the widget's initial visual footprint on existing clinic websites while preserving the current appointment-first booking flow, guest booking behavior, AI assistant entry point, tenant scoping, and booking safeguards.

## Current State

- `widget.views.embed_js` already returns JavaScript that injects a bottom-right launcher button, creates or shows the widget iframe on click, and listens for the existing `clinicflow-minimize` parent message.
- `templates/widget/widget.html` already has a minimize button that posts `{type: 'clinicflow-minimize'}` to the parent frame.
- `templates/dashboard/assistant_settings.html` presents both a JavaScript embed snippet and a raw iframe snippet.
- The dashboard copy says the JavaScript snippet creates a floating launcher, but the raw iframe snippet shows a large fixed widget panel immediately.
- The live preview currently shows the full widget panel, which is useful for admins reviewing the opened widget experience.

## Approved Direction

Use a launcher-first JavaScript embed as the recommended/default website integration.

The selected launcher style is an icon-only aqua bubble in the bottom-right corner. Raw iframe embedding remains available only as an advanced/manual fallback for custom placements where a clinic intentionally wants to place the full panel directly.

## Runtime Behavior

The JavaScript embed should behave as follows:

- The copied default embed remains a single script tag: `<script src=".../embed.js"></script>`.
- On host page load, KliniAssist injects only a compact launcher button.
- The widget iframe is created or shown only after the visitor clicks the launcher.
- The launcher is hidden while the iframe is open.
- The widget iframe uses the existing `widget:home` route with `?source=embed` so bookings continue to be recorded as embed bookings.
- The widget's minimize button keeps sending `clinicflow-minimize` to the parent page.
- The parent script handles `clinicflow-minimize` by hiding the iframe and showing the launcher again.
- Existing widget booking, slot loading, chat, FAQ, HTMX, and Alpine behavior remain inside the iframe.

The script must not accept client-submitted clinic IDs or ownership values. The clinic is still resolved server-side from the embed URL slug.

## Launcher UI

The default launcher should be small, familiar, accessible, and aligned with the Neon Aqua Clinical visual system.

- Position: fixed bottom-right, respecting `env(safe-area-inset-bottom)` and `env(safe-area-inset-right)`.
- Size: approximately `60px` by `60px`, with a touch-friendly target on mobile.
- Shape: circular/pill bubble.
- Color: clinic `safe_widget_accent_color`, falling back to the default aqua when the stored color is invalid.
- Icon: simple calendar-style booking icon that works without text and reinforces appointment booking.
- Accessibility: real `<button>`, `aria-label="Open booking widget"`, visible focus, keyboard-click support through native button behavior.
- Motion: subtle hover/press scale only; no aggressive attention animation.
- Z-index: keep the existing `9999` embed layering, scoped to launcher and iframe elements.
- Branding: use the existing clinic accent color only; do not add launcher customization settings in this change.

## Open Widget Panel

The full widget panel should remain the existing iframe-rendered experience.

- Width remains approximately `420px` on desktop.
- Height remains constrained to the viewport and safe areas.
- On mobile, the panel should continue to fit within the viewport using the existing responsive max-width/max-height behavior.
- The panel can use the current opacity/translate open and close transitions.
- The internal widget template remains focused on booking first, with chat and FAQs available from the home screen.

## Dashboard Admin Experience

The Assistant page's `Website Booking Widget` section should make the embed behavior clear.

- The live preview should behave like the recommended embedded website experience.
- The preview starts collapsed with only the bottom-right aqua calendar launcher visible inside the preview card.
- Clicking the preview launcher opens the existing widget iframe inside the preview card.
- Clicking the widget minimize button inside the iframe should collapse the preview back to the launcher through the existing `clinicflow-minimize` postMessage flow.
- Preview copy should say: "Click the launcher to preview how patients open the widget."
- The JavaScript embed snippet should be visually and textually presented as the recommended integration.
- Recommended JavaScript copy should explain: it adds a small bottom-right booking button and opens the full widget after click.
- The raw iframe snippet should be demoted to an advanced/manual fallback.
- Iframe copy should warn that it embeds the full panel directly and is useful only for custom placements.
- Do not add new dashboard fields for launcher icon, label, position, or shape in this pass.

## Embed Options

### Recommended JavaScript Embed

Use this when a clinic wants the common website widget integration pattern.

- Initial state: compact bottom-right launcher only.
- User action: click launcher.
- Open state: full booking widget iframe appears.
- Close state: minimize returns to compact launcher.

### Advanced Iframe Fallback

Use this only when a clinic or web developer intentionally wants to place the full panel directly in a specific page location.

- Initial state: full widget panel is visible immediately.
- It should not be described as the normal floating launcher integration.
- It should be secondary to the JavaScript snippet in dashboard hierarchy and copy.

## Security And Tenant Boundaries

- Public widget and embed inputs remain untrusted.
- The script URL continues to resolve one active clinic by public slug server-side.
- The browser must not receive credentials, n8n secrets, Facebook secrets, webhook secrets, model-provider keys, or internal tenant identifiers that control ownership.
- Booking form submission still validates patient identity, service ownership, generated slot availability, and double-booking prevention server-side.
- Appointment source remains server-derived from `?source=embed` for iframe bookings launched through the JavaScript embed.

## Testing Strategy

Add or update targeted tests for:

- `embed.js` returns JavaScript with an accessible launcher button.
- `embed.js` uses `safe_widget_accent_color` and falls back safely for invalid stored colors.
- `embed.js` wires iframe creation/showing to the launcher click path and still includes `?source=embed`.
- `embed.js` handles the existing `clinicflow-minimize` message by hiding the iframe and showing the launcher.
- Dashboard Assistant settings present the JavaScript snippet as the recommended launcher-first integration.
- Dashboard Assistant settings label the iframe snippet as an advanced/full-panel fallback.

Keep existing widget booking tests for:

- Guest booking identity validation.
- Patient phone matching.
- Slot regeneration and conflict prevention.
- Clinic-scoped service lookup.
- Embed appointment source tracking.
- Widget chat and FAQ behavior.

## Non-Goals

- Do not add launcher customization settings in V1.
- Do not add patient login, patient portal, medical records, prescriptions, inventory, online payments, marketplace booking, or real AI/Messenger automation.
- Do not replace Django templates, Tailwind CSS, HTMX, Alpine.js, or the current widget UI stack.
- Do not change booking validation, slot generation, patient matching, appointment approval mode, or double-booking prevention.
- Do not expose secrets in templates, browser JavaScript, logs, tests, screenshots, or commits.
- Do not remove the raw iframe option entirely; keep it as an advanced/manual fallback.

## Success Criteria

- A clinic using the recommended embed sees only a small bottom-right aqua launcher when their website loads.
- The full booking widget opens only after a visitor clicks the launcher.
- The widget can be minimized back to the launcher.
- Dashboard copy makes the recommended JavaScript launcher embed distinct from the advanced full-panel iframe fallback.
- Existing appointment booking and tenant safety behavior remain unchanged.
