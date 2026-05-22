# Messenger AI Agent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Django-side AI tool endpoints for a natural-language n8n Facebook Messenger agent that can answer clinic questions and book appointments after text confirmation.

**Architecture:** n8n owns the AI conversation and Facebook message sending. Django exposes secure tool endpoints for clinic context, service matching, availability lookup, and confirmed appointment creation. Existing booking and scheduling utilities remain the source of truth for clinic scoping, patient matching, slot validation, and double-booking prevention.

**Tech Stack:** Django, pytest, Django ORM, existing `messenger`, `clinics`, `services`, `scheduling`, `patients`, and `appointments` apps.

---

## File Structure

- Modify: `messenger/models.py` to add `MessengerAISettings`.
- Modify: `messenger/admin.py` to expose AI settings in admin.
- Modify: `messenger/urls.py` to add n8n AI tool endpoints.
- Create: `messenger/ai_tools.py` for focused service functions used by views and tests.
- Modify: `messenger/views.py` to add JSON endpoints while preserving legacy webhooks.
- Create: `messenger/migrations/0006_messengeraisettings.py` via `makemigrations`.
- Modify: `messenger/tests.py` to cover model, context, service matching, availability, booking confirmation, and cross-clinic safety.

## Task 1: AI Settings Model

**Files:**
- Modify: `messenger/models.py`
- Modify: `messenger/admin.py`
- Create: `messenger/migrations/0006_messengeraisettings.py`
- Test: `messenger/tests.py`

- [ ] **Step 1: Write failing tests**

Add tests that create a `MessengerAISettings` object through a `MessengerConnection`, assert defaults, and assert one settings row per connection.

- [ ] **Step 2: Run test to verify it fails**

Run: `./env/Scripts/python -m pytest messenger/tests.py -k "ai_settings" -v`

Expected: FAIL because `MessengerAISettings` does not exist.

- [ ] **Step 3: Implement model and admin**

Add `MessengerAISettings` with fields `connection`, `is_ai_enabled`, `instructions`, and `fallback_message`. Register it in admin.

- [ ] **Step 4: Create and apply migration**

Run:

```bash
./env/Scripts/python manage.py makemigrations messenger
./env/Scripts/python manage.py migrate
```

Expected: migration succeeds and database applies it.

- [ ] **Step 5: Run test to verify it passes**

Run: `./env/Scripts/python -m pytest messenger/tests.py -k "ai_settings" -v`

Expected: PASS.

## Task 2: Context and Service Tool Functions

**Files:**
- Create: `messenger/ai_tools.py`
- Test: `messenger/tests.py`

- [ ] **Step 1: Write failing tests**

Add tests for resolving an active page to clinic context, including clinic info, services, FAQs, AI settings, and excluding other clinics.

- [ ] **Step 2: Run test to verify it fails**

Run: `./env/Scripts/python -m pytest messenger/tests.py -k "ai_context or ai_service" -v`

Expected: FAIL because helper functions do not exist.

- [ ] **Step 3: Implement helpers**

Create functions:

```python
def get_connection_for_page(page_id): ...
def build_ai_context(page_id): ...
def match_services(page_id, query): ...
```

Return JSON-serializable dictionaries only.

- [ ] **Step 4: Run tests**

Run: `./env/Scripts/python -m pytest messenger/tests.py -k "ai_context or ai_service" -v`

Expected: PASS.

## Task 3: Availability Tool

**Files:**
- Modify: `messenger/ai_tools.py`
- Test: `messenger/tests.py`

- [ ] **Step 1: Write failing tests**

Add tests that create business hours and a service, then assert requested slot availability and nearest alternative suggestions.

- [ ] **Step 2: Run test to verify it fails**

Run: `./env/Scripts/python -m pytest messenger/tests.py -k "ai_availability" -v`

Expected: FAIL because availability helper does not exist.

- [ ] **Step 3: Implement availability helper**

Create `check_availability(page_id, service_id, preferred_starts_at=None, preferred_date=None)` using `generate_slots()`. Return availability, selected slot, and up to three nearest alternatives.

- [ ] **Step 4: Run tests**

Run: `./env/Scripts/python -m pytest messenger/tests.py -k "ai_availability" -v`

Expected: PASS.

## Task 4: Confirmed Booking Tool

**Files:**
- Modify: `messenger/ai_tools.py`
- Test: `messenger/tests.py`

- [ ] **Step 1: Write failing tests**

Add tests that booking fails without confirmation, succeeds with confirmation, creates a Messenger-source appointment, and rejects unavailable slots.

- [ ] **Step 2: Run test to verify it fails**

Run: `./env/Scripts/python -m pytest messenger/tests.py -k "ai_booking" -v`

Expected: FAIL because booking helper does not exist.

- [ ] **Step 3: Implement booking helper**

Create `book_confirmed_appointment(...)` that requires confirmation, calls `_process_guest_booking()`, and returns a JSON-serializable result.

- [ ] **Step 4: Run tests**

Run: `./env/Scripts/python -m pytest messenger/tests.py -k "ai_booking" -v`

Expected: PASS.

## Task 5: n8n Tool Endpoints

**Files:**
- Modify: `messenger/views.py`
- Modify: `messenger/urls.py`
- Test: `messenger/tests.py`

- [ ] **Step 1: Write failing endpoint tests**

Add client tests for `/messenger/ai/context/`, `/messenger/ai/services/`, `/messenger/ai/availability/`, and `/messenger/ai/book/`. Include unauthorized request tests using `N8N_WEBHOOK_SECRET`.

- [ ] **Step 2: Run test to verify it fails**

Run: `./env/Scripts/python -m pytest messenger/tests.py -k "ai_endpoint" -v`

Expected: FAIL because URLs and views do not exist.

- [ ] **Step 3: Implement endpoints**

Add CSRF-exempt POST-only views that validate `X-N8N-Webhook-Secret`, parse JSON, call `ai_tools`, and return `JsonResponse`.

- [ ] **Step 4: Run endpoint tests**

Run: `./env/Scripts/python -m pytest messenger/tests.py -k "ai_endpoint" -v`

Expected: PASS.

## Task 6: Verification

**Files:**
- No new files expected.

- [ ] **Step 1: Run Django checks**

Run: `./env/Scripts/python manage.py check`

Expected: `System check identified no issues`.

- [ ] **Step 2: Run Messenger tests**

Run: `./env/Scripts/python -m pytest messenger/tests.py -v`

Expected: PASS or identify pre-existing legacy test failures before changing them.

- [ ] **Step 3: Run migration check**

Run: `./env/Scripts/python manage.py makemigrations --check --dry-run`

Expected: `No changes detected`.

- [ ] **Step 4: Commit implementation**

Stage only intended source, migration, and tests. Do not stage `db.sqlite3`, local n8n exports, or shell scripts.
