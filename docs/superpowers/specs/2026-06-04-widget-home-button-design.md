# Widget Home Button Design

## Goal

Add a Home button beside the widget minimize button so patients can intentionally return to the widget home screen and start over.

This is separate from minimize behavior. Minimize should continue preserving the current in-progress booking or chat state when the same iframe is reopened.

## Current State

The widget header in `templates/widget/widget.html` currently has one control: the Minimize button. The widget home screen is available only at initial load or through flow-specific restart links.

The recent minimize behavior intentionally stopped resetting `mode` to `home`, so patients need a separate explicit control when they want to abandon the current in-progress booking or chat and return to the widget home choices.

## Approved Direction

Add a compact icon-only Home button immediately before the Minimize button in the widget header.

Approved choices:

- Home means start over.
- Home resets current booking and chat UI draft state.
- Minimize remains state-preserving.
- Do not add browser storage, server-side drafts, model changes, or URL changes.

## Header UI

The header control group should contain two touch-friendly buttons:

- Home: `aria-label="Go to widget home"`, Lucide `home` icon.
- Minimize: existing `aria-label="Minimize"`, Lucide `minus` icon.

Both controls should keep the existing compact widget style:

- `min-h-10 min-w-10`
- Rounded geometry compatible with the current header.
- No text label in the header, to avoid crowding clinic names on mobile.
- Readable icon color through the existing header `accentForeground()` contrast behavior.

## Home Behavior

Add a `goHome()` method to the widget Alpine state.

Clicking Home should reset in-progress frontend state and show the home screen:

- `mode = 'home'`
- `bookStep = 1`
- `selectedService = ''`
- `date = '{{ selected_date|date:"Y-m-d" }}'`
- `slot = ''`
- `chatTab = 'conversation'`
- `chatHistory = []`
- `chatOptions = []`
- `chatState = 'greeting'`
- `chatInput = ''`
- `faqQuery = ''`
- `collectInfo = { full_name: '', phone: '', email: '' }`

The Home button should not call booking, chat, slot, or persistence endpoints. It is a local UI reset only.

FAQ accordion open states are not part of the reset contract for the first version. The Home action only needs to reset `faqQuery` and show the home screen.

## Minimize Behavior

Minimize must remain separate from Home.

- `minimize()` continues to post `{type: 'kliniassist-minimize'}` to the parent frame.
- `minimize()` must not set `mode = 'home'`.
- `minimize()` must not call `goHome()`.
- Reopening the same iframe after minimize should preserve the current screen and typed values.

## Security And Tenant Boundaries

The change is frontend-only and does not alter tenant scoping or booking authority.

- Public clinic resolution remains server-side through `clinic_slug`.
- Appointment creation still uses existing server-side booking validation.
- No client-submitted clinic, service, patient, source, price, status, or ownership values become trusted because of this change.
- No patient draft data is persisted to browser storage, server sessions, or the database.

## Testing Strategy

Add or update targeted widget template contract tests:

- The widget header contains a Home button with `aria-label="Go to widget home"` and a Lucide `home` icon.
- The Home button calls `goHome()`.
- The `goHome()` method resets booking state, chat state, typed chat input, FAQ query, and collect-info fields.
- The existing minimize regression still proves `minimize()` posts `kliniassist-minimize` and does not reset `mode` to `home`.

Run at minimum after implementation:

- `python -m pytest widget/tests.py::WidgetTests::test_widget_header_includes_home_and_minimize_controls -q`
- `python -m pytest widget/tests.py::WidgetTests::test_widget_home_button_resets_in_memory_state -q`
- `python -m pytest widget/tests.py::WidgetTests::test_widget_minimize_preserves_in_memory_state -q`
- `python -m pytest tests/test_design_system.py -k widget -q`
- `python manage.py check`

The full `widget/tests.py` suite may still contain unrelated AI-first chat failures in the current dirty worktree. Those failures are not part of this Home button design unless they directly involve the new header control or `goHome()` behavior.

## Non-Goals

- Do not change appointment creation, slot validation, patient matching, or double-booking prevention.
- Do not change AI assistant behavior or n8n integration.
- Do not add persistent drafts.
- Do not add a confirmation modal before returning home in the first version.
- Do not change the launcher-first embed behavior.
- Do not introduce React, Next.js, or a separate frontend.
