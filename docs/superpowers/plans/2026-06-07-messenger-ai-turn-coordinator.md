# Messenger AI Turn Coordinator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prevent Messenger users from receiving stale or out-of-order AI replies when they send multiple messages while a prior AI response is generating.

**Architecture:** Django owns Messenger AI turn state per `(connection, psid)` using database rows and row locks. n8n registers every verified inbound message, claims one coalesced batch at a time, checks whether a reply is still current before sending, and passes turn identity into mutating appointment tools.

**Tech Stack:** Django, PostgreSQL-compatible ORM transactions, pytest, n8n Workflow SDK source tests.

---

### Task 1: Backend Turn State

**Files:**
- Modify: `messenger/models.py`
- Modify: `messenger/views.py`
- Modify: `messenger/urls.py`
- Create: `messenger/migrations/0013_messenger_ai_turn_coordinator.py`
- Test: `messenger/tests.py`

- [ ] **Step 1: Write failing tests** for registering a first message as `process_now`, registering a second distinct message as `queued`, claiming an ordered batch, suppressing a stale completion, and allowing different PSIDs to process independently.
- [ ] **Step 2: Run targeted tests** with `./env/Scripts/python -m pytest messenger/tests.py -k "ai_turn or stale_turn" -q` and confirm failures are caused by missing routes/models.
- [ ] **Step 3: Add models** `MessengerConversation`, `MessengerInboundMessage`, and `MessengerAITurn` with clinic-scoped foreign keys through `MessengerConnection`, unique `(connection, psid)`, unique `(conversation, message_id)`, and monotonic per-conversation `sequence`.
- [ ] **Step 4: Add endpoints** `ai_turn_register`, `ai_turn_claim`, and `ai_turn_complete`, all protected by `N8N_WEBHOOK_SECRET`, with `transaction.atomic()` and `select_for_update()` on the conversation row.
- [ ] **Step 5: Verify tests pass** and run `./env/Scripts/python manage.py check`.

### Task 2: Stale Mutating Tool Protection

**Files:**
- Modify: `messenger/views.py`
- Modify: `messenger/ai_tools.py`
- Test: `messenger/tests.py`

- [ ] **Step 1: Write failing tests** showing `book_confirmed_appointment`, `cancel_verified_appointment`, and `reschedule_verified_appointment` reject stale Messenger turn metadata when a newer message arrived.
- [ ] **Step 2: Run targeted tests** with `./env/Scripts/python -m pytest messenger/tests.py -k "stale_turn" -q` and confirm failures are caused by missing stale-turn validation.
- [ ] **Step 3: Add a shared validator** that accepts blank turn metadata for non-Messenger or legacy calls but rejects stale Messenger calls when `turn_token` and `input_sequence` are provided and no longer current.
- [ ] **Step 4: Wire validator into mutating Messenger AI endpoints** before booking, cancel, or reschedule mutation code runs.
- [ ] **Step 5: Verify targeted tests pass**.

### Task 3: n8n Workflow Source Integration

**Files:**
- Modify: `n8n_combined_messenger_widget_ai_bridge.ts`
- Modify: `tests/test_n8n_combined_bridge_source.py`

- [ ] **Step 1: Write failing source tests** proving the workflow calls register after signature verification, acknowledges queued turns without AI, claims a coalesced batch before AI, checks completion before Facebook send, and sends turn metadata to mutating tools.
- [ ] **Step 2: Run source tests** with `./env/Scripts/python -m pytest tests/test_n8n_combined_bridge_source.py -q` and confirm expected failures.
- [ ] **Step 3: Add n8n constants and HTTP nodes** for `/messenger/ai/turn/register/`, `/messenger/ai/turn/claim/`, and `/messenger/ai/turn/complete/`.
- [ ] **Step 4: Route only `process_now` registrations into AI**; route `queued` registrations to the existing Meta acknowledgement only.
- [ ] **Step 5: Feed `claim.messages` as the AI text** and include `turn_token` and `input_sequence` in mutating tool bodies.
- [ ] **Step 6: Check completion before send** and only call Facebook when Django returns `send_reply: true`.
- [ ] **Step 7: Verify source tests pass**.

### Task 4: Final Verification

**Files:**
- No new files.

- [ ] **Step 1: Run migrations generation/check** with `./env/Scripts/python manage.py makemigrations --check --dry-run` after the manual migration is present.
- [ ] **Step 2: Run targeted Messenger tests** with `./env/Scripts/python -m pytest messenger/tests.py -k "turn or meta_signature or appointment" -q`.
- [ ] **Step 3: Run n8n source tests** with `./env/Scripts/python -m pytest tests/test_n8n_combined_bridge_source.py -q`.
- [ ] **Step 4: Run Django checks** with `./env/Scripts/python manage.py check`.
