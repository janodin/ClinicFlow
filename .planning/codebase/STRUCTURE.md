# Codebase Structure

**Analysis Date:** 2026-05-30

## Directory Layout

```
[project-root]/
├── accounts/          # User authentication and custom User model
├── appointments/      # Appointment management and logic
├── clinics/           # Multi-tenant entities (ClinicGroup, Clinic)
├── config/            # Django project settings and root URLs
├── dashboard/         # Staff dashboard, calendar, and operational views
├── doctors/           # Legacy (kept for migration compatibility)
├── messenger/         # Messenger API integration
├── patients/          # Patient records and guest matching
├── scheduling/        # Business hours and availability utilities
├── services/          # Service definitions and pricing
├── widget/            # Embeddable booking widget and AI client
├── static/            # Global static assets (CSS, images)
├── templates/         # Global HTML templates
├── tests/             # Pytest and Playwright test suites
├── media/             # User-uploaded files (logos, etc.)
├── env/               # Python virtual environment
└── manage.py          # Django management script
```

## Directory Purposes

**`config/`:**
- Purpose: Central configuration for the Django project.
- Contains: `settings.py`, `urls.py`, `wsgi.py`, `asgi.py`.

**`dashboard/`:**
- Purpose: The core SaaS interface for clinic staff.
- Contains: Views for calendar management, appointment listing, and settings.

**`widget/`:**
- Purpose: Public-facing booking interface and AI chat.
- Contains: Specialized views for Iframe embedding and AI state management.

**`scheduling/`:**
- Purpose: Pure business logic for clinic availability.
- Contains: `utils.py` for generating time slots based on business hours and existing appointments.

## Key File Locations

**Entry Points:**
- `manage.py`: Main CLI entry point.
- `config/urls.py`: Root URL routing.
- `widget/views.py:embed_js`: Public widget entry point.

**Configuration:**
- `config/settings.py`: Main application settings.
- `.env`: Environment variables (local dev).

**Core Logic:**
- `appointments/models.py`: Appointment state and validation.
- `scheduling/utils.py`: Availability calculation engine.
- `patients/models.py`: Guest record matching logic.

**Testing:**
- `tests/`: Project-wide tests.
- `pytest.ini`: Test configuration.

## Naming Conventions

**Files:**
- Standard Django: `models.py`, `views.py`, `urls.py`, `admin.py`.
- Utilities: `utils.py`.

**Directories:**
- App names should be plural (e.g., `clinics`, `patients`).

## Where to Add New Code

**New Feature (Internal):**
- Primary code: Create a new app or add to `dashboard/`.
- Templates: `templates/dashboard/`.

**New Public Component:**
- Implementation: `widget/` or a new specialized app.
- Templates: `templates/widget/`.

**Utilities:**
- Shared helpers: Create a `utils.py` in the relevant app or a shared `core/` app if needed.

## Special Directories

**`.planning/`:**
- Purpose: GSD planning artifacts and codebase mapping.
- Committed: Yes.

**`static/`:**
- Purpose: Source static files.
- Compiled to `staticfiles/` during deployment.

---

*Structure analysis: 2026-05-30*
