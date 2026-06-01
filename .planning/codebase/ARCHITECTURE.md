<!-- refreshed: 2026-05-30 -->
# Architecture

**Analysis Date:** 2026-05-30

## System Overview

```text
┌─────────────────────────────────────────────────────────────┐
│                      Presentation Layer                     │
├──────────────────┬──────────────────┬───────────────────────┤
│  Dashboard UI    │  Booking Widget  │   Messenger Bot       │
│  `dashboard/`    │    `widget/`     │   `messenger/`        │
└────────┬─────────┴────────┬─────────┴──────────┬────────────┘
         │                  │                     │
         ▼                  ▼                     ▼
┌─────────────────────────────────────────────────────────────┐
│                    Application Layer                        │
│         `dashboard/views.py`, `widget/views.py`             │
└─────────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────┐
│  Data Layer (PostgreSQL / SQLite)                           │
│  `clinics/models.py`, `appointments/models.py`              │
└─────────────────────────────────────────────────────────────┘
```

## Component Responsibilities

| Component | Responsibility | File |
|-----------|----------------|------|
| `accounts` | User authentication and custom user model | `accounts/models.py` |
| `clinics` | Multi-tenancy (ClinicGroup, Clinic) and membership management | `clinics/models.py` |
| `appointments` | Appointment scheduling, status tracking, and validation | `appointments/models.py` |
| `patients` | Patient records matched by phone (guest booking) | `patients/models.py` |
| `services` | Clinic service definitions and pricing | `services/models.py` |
| `scheduling` | Business hours and availability slot generation | `scheduling/utils.py` |
| `dashboard` | Staff operational dashboard and calendar | `dashboard/views.py` |
| `widget` | Embeddable booking widget and AI chat state machine | `widget/views.py` |
| `messenger` | Meta Messenger Platform integration and AI webhook | `messenger/views.py` |

## Pattern Overview

**Overall:** Monolithic Django Application with Multi-tenancy

**Key Characteristics:**
- **App-per-domain:** Each business domain (patients, clinics, appointments) is isolated into a Django app.
- **Service-Oriented Models:** Business logic for slot validation and scheduling is encapsulated in models and utility functions.
- **HTMX Interactivity:** Dynamic dashboard and widget updates without full page reloads.

## Layers

**Presentation Layer:**
- Purpose: Rendered HTML for staff and the public booking interface.
- Location: `templates/`
- Contains: Django templates, Tailwind CSS, Alpine.js, HTMX.
- Depends on: Application Layer.
- Used by: End users (Staff, Patients).

**Application Layer:**
- Purpose: Handle requests, orchestrate domain logic, and return responses.
- Location: `*/views.py`
- Contains: Function-based views (FBVs).
- Depends on: Domain/Data Layer.
- Used by: Presentation Layer.

**Domain/Data Layer:**
- Purpose: Manage persistence and enforce business rules.
- Location: `*/models.py`
- Contains: Django Models, custom Managers, and validation logic.
- Depends on: Django ORM.
- Used by: Application Layer.

## Data Flow

### Primary Request Path (Booking)

1. **Entry Point:** Patient opens widget (`widget/views.py:widget_home`).
2. **Processing:** Slot generation logic calculates availability (`scheduling/utils.py:generate_slots`).
3. **Creation:** Patient matches existing record or creates new one (`patients/models.py:find_or_create_for_booking`).
4. **Persistence:** Appointment is validated and saved (`appointments/models.py:save`).

### AI Assistant Flow

1. **Trigger:** Patient sends message in widget.
2. **Request:** Django calls n8n assistant webhook (`widget/ai_client.py:call_assistant_webhook`).
3. **Response:** Assistant reply is stored in session and returned to widget UI.

**State Management:**
- **Server-side:** Django sessions and database.
- **Client-side:** Alpine.js for UI-only state (e.g., modals, toggles).

## Key Abstractions

**Multi-tenancy:**
- Purpose: Scoping all data to a specific `Clinic`.
- Examples: `Appointment.clinic`, `Patient.clinic`, `Service.clinic`.

**Scheduling Engine:**
- Purpose: Abstracting complex date/time math for clinic availability.
- Examples: `scheduling/utils.py`.

## Entry Points

**Django Management:**
- Location: `manage.py`
- Triggers: CLI commands.
- Responsibilities: Database migrations, server execution.

**Public Widget:**
- Location: `widget/views.py:embed_js`
- Triggers: Script tag inclusion on 3rd party sites.
- Responsibilities: Injecting the booking iframe.

## Architectural Constraints

- **Multi-tenancy:** Data MUST be filtered by `Clinic`. No cross-clinic data exposure.
- **Guest Booking:** Patients do not have accounts; they are identified by `normalized_phone`.
- **Timezone Awareness:** All operations use `Asia/Manila` (Clinic default) but are stored in UTC.

## Anti-Patterns

### Logic in Templates

**What happens:** Using complex logic or data queries inside Django templates.
**Why it's wrong:** Hard to test and separates logic from the domain layer.
**Do this instead:** Use context processors or perform data fetching in views.

### Unscoped Queries

**What happens:** Querying models without filtering by `clinic`.
**Why it's wrong:** Risks leaking data between tenants.
**Do this instead:** Always filter by `request.clinic` or equivalent.

## Error Handling

**Strategy:** Fail-fast validation and HTMX-based user feedback.

**Patterns:**
- Model-level `ValidationError` for business rule violations.
- HTMX partials for rendering inline error messages.

## Cross-Cutting Concerns

**Logging:** standard Python logging in `server.log`.
**Validation:** Django Forms and Model `clean()` methods.
**Authentication:** standard Django Auth with custom `accounts.User`.

---

*Architecture analysis: 2026-05-30*
