# Widget Header Button Spacing Design

## Goal

Reduce the visual spacing between the widget Home and Minimize buttons without changing their size, behavior, labels, icons, or accessibility.

## Current State

The widget header control group in `templates/widget/widget.html` uses `gap-2`, which creates an 8px gap between the Home and Minimize buttons.

## Approved Direction

Use `gap-1` for the header control group.

Approved reasoning:

- `gap-1` groups the buttons more tightly.
- It keeps a small 4px separation to reduce accidental taps.
- `gap-0` is too tight for adjacent Home and Minimize controls.

## Implementation Scope

Change only the header control wrapper that contains the Home and Minimize buttons:

- From `class="flex items-center gap-2"`
- To `class="flex items-center gap-1"`

Do not change other `gap-2` containers in booking steps. Do not change button dimensions, icons, labels, reset behavior, minimize behavior, chat behavior, booking behavior, storage, URLs, or server-side code.

## Testing Strategy

Update or add a widget template contract test that confirms the header control wrapper uses `gap-1` and still contains both Home and Minimize controls.

Run at minimum after implementation:

- `python -m pytest widget/tests.py::WidgetTests::test_widget_header_includes_home_and_minimize_controls -q`
- `python -m pytest tests/test_design_system.py -k widget -q`
- `python manage.py check`

## Non-Goals

- Do not change Home or Minimize behavior.
- Do not change button size or icon size.
- Do not change other widget layout gaps.
- Do not add new CSS classes or JavaScript.
