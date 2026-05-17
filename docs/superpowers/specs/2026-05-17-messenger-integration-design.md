# Messenger Integration Design

**Date:** 2026-05-17  
**Status:** Approved  
**Scope:** Enable patients to book appointments entirely via Facebook Messenger using a conversational bot flow, without leaving the chat or linking out to web widgets.

---

## 1. Goals

- Allow patients to book appointments through Facebook Messenger as a fully standalone channel.
- Support quick-reply guided booking (service → date → time → patient details → confirm).
- Support free-text FAQ and clinic-info queries via keyword matching against existing `ClinicFAQ` records.
- Send automated confirmation and reminder messages via Messenger.
- Keep clinic data tenant-isolated: each clinic connects its own Facebook Page.
- Reuse existing booking logic (`_process_guest_booking`, `generate_slots`, `Patient.find_or_create_for_booking`) without duplication.

## 2. Non-Goals

- No web handoff or deep-linking to the public booking widget.
- No human handoff or dashboard inbox for staff to reply to patients.
- No NLP/AI model for free-text parsing — keyword matching only.
- No general marketing broadcasts; only appointment-specific transactional messages.
- No changes to the existing web widget, embed, or chat widget behavior.

## 3. Architecture

### 3.1 New App: `messenger`

A new Django app that owns all Facebook Messenger integration code. It is isolated from `widget` and `appointments` except through shared utility imports.

| File | Responsibility |
|------|----------------|
| `messenger/models.py` | `MessengerConnection` (clinic ↔ Page mapping) and `MessengerSession` (per-PSID conversation state) |
| `messenger/views.py` | Webhook endpoint (`GET` verification, `POST` inbound message handling) |
| `messenger/messenger_api.py` | Thin `requests`-based wrapper around Meta Send API |
| `messenger/bot_engine.py` | State machine that maps messages to next step and builds reply payloads |
| `messenger/faq_matcher.py` | Keyword-based matcher against `ClinicFAQ` for free-text info queries |
| `messenger/management/commands/send_messenger_reminders.py` | Cron-able command for sending reminder messages |
| `messenger/urls.py` | Public webhook route |
| `messenger/tests.py` | Unit and integration tests for bot engine, webhook, and API wrapper |

### 3.2 Dashboard Extensions

| File | Responsibility |
|------|----------------|
| `dashboard/views.py` (additions) | `messenger_settings` view, OAuth callback handler |
| `dashboard/templates/dashboard/messenger_settings.html` | Settings UI: connect status, Page info, disconnect button, webhook/token display |
| `dashboard/urls.py` (additions) | `/dashboard/settings/messenger/`, `/dashboard/messenger/callback/` |

### 3.3 Settings

New settings in `config/settings.py`:

```python
MESSENGER_VERIFY_TOKEN = os.getenv("MESSENGER_VERIFY_TOKEN", "")
MESSENGER_APP_SECRET = os.getenv("MESSENGER_APP_SECRET", "")
MESSENGER_APP_ID = os.getenv("MESSENGER_APP_ID", "")
MESSENGER_SESSION_TIMEOUT_MINUTES = int(os.getenv("MESSENGER_SESSION_TIMEOUT_MINUTES", "30"))
```

## 4. Data Model

### 4.1 `MessengerConnection`

One per clinic. Maps the clinic to a Facebook Page.

```python
class MessengerConnection(models.Model):
    clinic = models.OneToOneField(Clinic, on_delete=models.CASCADE, related_name="messenger_connection")
    page_id = models.CharField(max_length=64)
    page_access_token = models.CharField(max_length=512)  # encrypted at application level if desired
    is_active = models.BooleanField(default=True)
    connected_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
```

### 4.2 `MessengerSession`

One per patient conversation (identified by PSID).

```python
class MessengerSession(models.Model):
    STATE_GREETING = "greeting"
    STATE_SELECT_SERVICE = "select_service"
    STATE_SELECT_DATE = "select_date"
    STATE_SELECT_TIME = "select_time"
    STATE_COLLECT_INFO = "collect_info"
    STATE_CONFIRM = "confirm"
    STATE_BOOKED = "booked"
    STATE_FAQ = "faq"
    STATE_CHOICES = [...]

    connection = models.ForeignKey(MessengerConnection, on_delete=models.CASCADE, related_name="sessions")
    psid = models.CharField(max_length=64, db_index=True)
    state = models.CharField(max_length=32, choices=STATE_CHOICES, default=STATE_GREETING)
    data = models.JSONField(default=dict, blank=True)
    last_activity_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [("connection", "psid")]
```

The `data` JSONField stores:
- `service_id`
- `date` (ISO date string)
- `starts_at` (ISO datetime string)
- `full_name`
- `phone`
- `email`

No patient identity mapping beyond PSID. Booking reuses `Patient.find_or_create_for_booking` via phone matching, just like the web widget.

## 5. Bot Flow & State Machine

States:

1. **`greeting`** — Welcome message + quick-reply options: "Book an appointment", "View FAQs", "Clinic info". "Clinic info" returns the clinic's address, phone, email, and timezone from the `Clinic` model.
2. **`select_service`** — Quick-reply buttons for active services.
3. **`select_date`** — Quick-reply buttons for next 14 days.
4. **`select_time`** — Calls `generate_slots()` and shows available times as quick-replies. If no slots, suggests next available date.
5. **`collect_info`** — Asks for full name and phone number. Patient replies with free text (e.g., "John Doe\n09171234567"). The bot splits by newline; the first non-empty line is `full_name`, the second is `phone`. If fewer than two lines, or if the phone fails a basic digit check, the bot repeats the request with an example.
6. **`confirm`** — Displays booking summary with "Confirm" / "Cancel" quick-replies.
7. **`booked`** — Confirms booking, shows reference code. Offers "Book another" or "Done".
8. **`faq`** — Matches free-text against `ClinicFAQ` keywords. Falls back to greeting menu if no match.

**Session timeout:** If `last_activity_at` is older than `MESSENGER_SESSION_TIMEOUT_MINUTES` (default 30), any new message resets state to `greeting` and clears `data`.

**Free-text handling:**
- In `greeting`/`faq`: keyword matching for "book", "appointment", "faq", "hours", "price", "location", "contact", "address", "cancel".
- In `collect_info`: expects structured text and extracts name + phone.
- Unrecognized text in any state falls back to a helpful message with quick-reply options.

**Cancel handling:** At any time, if the patient sends "cancel" (and is not in `collect_info` gathering input), the bot checks for a pending/confirmed appointment created via Messenger in the next 7 days. If found, it cancels it (status → `cancelled`) and confirms. If no appointment is found, it says so and returns to `greeting`.

## 6. Webhook Handling

**Endpoint:** `POST /messenger/webhook/`  
**Public:** No Django auth; secured via signature verification.

### 6.1 GET Verification

Meta sends `hub.mode=subscribe`, `hub.verify_token`, `hub.challenge`. We validate `hub.verify_token == settings.MESSENGER_VERIFY_TOKEN` and return `hub.challenge`.

### 6.2 POST Message Processing

1. Read `X-Hub-Signature-256` header and verify HMAC-SHA256 using `settings.MESSENGER_APP_SECRET`. Return `403` if invalid.
2. Parse JSON payload.
3. For each `entry.messaging` item:
   - Extract `sender.id` (PSID) and `recipient.id` (Page ID).
   - Extract `message.text` or `postback.payload`.
   - Look up `MessengerConnection` by `recipient.id`. Skip if not found or `is_active=False`.
   - Load or create `MessengerSession` for this PSID + connection.
   - If session timed out, reset to `greeting` and clear `data`.
   - Call `bot_engine.handle_message(session, text, postback)`.
   - `bot_engine` returns a list of reply actions.
   - Call `messenger_api.send_messages(connection, psid, actions)`.
   - Save `session.state`, `session.data`, `session.last_activity_at`.

### 6.3 Error Handling

- If Send API call fails (e.g., token expired), log the error and send a single fallback text: "Sorry, something went wrong. Please try again later."
- If `generate_slots` returns no slots, the bot suggests the next available date.
- If `_process_guest_booking` fails (e.g., slot taken), the bot informs the patient and returns to `select_time`.

## 7. OAuth Flow & Dashboard Settings

### 7.1 Connection Setup

1. Clinic owner navigates to **Settings → Messenger**.
2. Clicks **"Connect Facebook Page"**.
3. Redirected to Meta OAuth dialog: `https://www.facebook.com/v18.0/dialog/oauth?client_id={app_id}&redirect_uri={callback}&scope=pages_messaging,pages_read_engagement`.
4. User selects Page and approves.
5. Meta redirects to `/dashboard/messenger/callback/?code={code}`.
6. Backend:
   - Exchanges `code` for a short-lived User Access Token.
   - Uses `/me/accounts` to get Pages and their long-lived Page Access Tokens.
   - Stores `page_id` and `page_access_token` in `MessengerConnection`.
7. Staff must subscribe the Page webhook in Meta Developer dashboard (documented in UI).

### 7.2 Settings UI Fields

- Connection status badge
- Connected Page name + ID
- "Disconnect" button (sets `is_active=False`, clears token)
- Webhook URL display (read-only)
- Verify token display (read-only, for Meta setup)

### 7.3 Disconnect Behavior

- Sets `is_active=False`.
- Existing `MessengerSession` records are retained for history.
- New incoming messages are ignored (skipped in webhook handler).
- Reconnecting creates a new token or reactivates the existing connection.

## 8. Reminders & Notifications

### 8.1 Confirmation Message

Sent immediately after a successful Messenger booking:

> Your appointment for {service} at {clinic} is confirmed.
> Date: {date} at {time}
> Reference: {reference_code}
> Reply CANCEL to cancel this appointment.

### 8.2 Reminder Messages

Sent proactively before upcoming appointments:

- **Timing:** Hardcoded for V1: 24 hours and 1 hour before `starts_at`. Per-clinic timing will be added when the notification settings system is built (see TASKS.md).
- **Content:**
  > Reminder: You have an appointment for {service} at {clinic} on {date} at {time}.
  > Reply CANCEL to cancel this appointment.
- **How:** `python manage.py send_messenger_reminders`
  - Queries appointments with `source=Appointment.SOURCE_MESSENGER`.
  - Checks if reminder timing matches clinic settings.
  - Sends via `messenger_api` only if the patient's PSID is known (stored in `MessengerSession`).
  - Skips cancelled or past appointments.

### 8.3 Scope Limit

Only appointment-specific transactional messages. No marketing broadcasts to comply with Meta's 24-hour + message tags policy.

## 9. Security & Tenant Isolation

- **Webhook signature verification:** Every inbound webhook is HMAC-verified using `MESSENGER_APP_SECRET`.
- **Page-scoped lookup:** `MessengerConnection` is looked up by Page ID, so messages are routed only to the correct clinic.
- **Token storage:** Page Access Tokens are stored in the database. In production, consider encrypting them (e.g., Django's `django-cryptography` or field-level encryption).
- **No cross-clinic exposure:** The bot engine always operates within the `connection.clinic` scope. Slot generation and patient creation use clinic-filtered queries.
- **CSRF:** Dashboard settings views use standard Django CSRF protection. The public webhook bypasses CSRF (no session) and relies on signature verification instead.

## 10. Testing Strategy

- **Unit tests:**
  - `bot_engine.handle_message` for every state transition.
  - `faq_matcher` keyword matching accuracy.
  - `messenger_api` payload formatting.
- **Integration tests:**
  - Webhook GET verification.
  - Webhook POST with mocked Meta payload and signature.
  - Full booking flow via simulated messages.
- **Command tests:**
  - `send_messenger_reminders` finds the right appointments and sends correct messages.
- **No Playwright needed** for Messenger (API-driven), but existing web widget tests must still pass.

## 11. Dependencies

No new Python packages required. The implementation uses:
- `requests` (already in the virtual environment, used by Playwright and other packages)
- `hmac` and `hashlib` (stdlib) for signature verification

If token encryption is desired later, `django-cryptography` can be added as an optional enhancement.

## 12. Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| Meta API changes | Keep `messenger_api.py` thin; changes are localized to one file. |
| Token expiration | OAuth reconnect flow in dashboard; disconnect + reconnect is one click. |
| Webhook signature bypass | Always verify `X-Hub-Signature-256` before processing payload. |
| Patient confusion between web and Messenger | Booking source is tracked (`SOURCE_MESSENGER`); staff sees the channel in appointment list. |
| Rate limits | Meta Send API has generous limits for transactional messages; reminders are batched in the management command. |

## 13. Open Questions

None at this time. All clarifying questions have been answered.

---

**Next Step:** Write implementation plan using the `writing-plans` skill.
