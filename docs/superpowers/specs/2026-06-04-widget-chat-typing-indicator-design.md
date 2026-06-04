# Widget Chat Typing Indicator Design

## Goal

Show a lightweight assistant typing indicator in the booking widget chat while the AI response request is in flight, so users know the assistant is working and the latest chat position stays visible.

## Scope

- Add a typing indicator only to the public booking widget conversation tab.
- Use the existing Django template, Tailwind utility classes, and Alpine.js state in `templates/widget/widget.html`.
- Do not add typewriter text animation, a separate frontend framework, persistent state, or backend schema changes.

## Behavior

- When `sendChatAction()` starts a request, set an Alpine boolean named `isAssistantTyping` to `true`.
- Render an assistant-style chat bubble below current messages while `isAssistantTyping` is true.
- The bubble should contain accessible text `Assistant is typing` plus three animated dots for visual feedback.
- Scroll the existing `chatConversation` container after the indicator appears and after the final assistant message is rendered.
- Hide the indicator when the request finishes, errors, or is ignored because the widget state was reset.

## UI Treatment

- Match the existing assistant message bubble: left aligned, white background, teal ink, and `var(--cf-line)` border.
- Keep the animation subtle and lightweight using existing Tailwind animation utilities where possible.
- Preserve accessible text contrast and avoid motion-heavy effects.

## Error Handling

- Use `try`/`finally` around the fetch flow so the indicator clears even if the request fails.
- Preserve the existing stale response guard with `stateResetVersion` so home resets do not reintroduce old responses or stuck loading UI.

## Testing

- Add a widget template regression test that verifies the typing state exists, is toggled around `fetch`, renders inside the conversation area, and is cleared in a `finally` path.
- Run `python manage.py test widget` and `python manage.py check` after implementation.
