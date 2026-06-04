# Technology Stack

**Analysis Date:** 2026-05-30

## Languages

**Primary:**
- Python 3.12.x - Backend logic and Django application code

**Secondary:**
- JavaScript - Alpine.js and HTMX for frontend interactivity
- CSS - Custom styles and design tokens (`static/css/kliniassist.css`)
- HTML - Django templates

## Runtime

**Environment:**
- Python 3.12.6

**Package Manager:**
- pip (via `requirements.txt`)
- Lockfile: missing (no `requirements.lock` or `Pipfile.lock` detected)

## Frameworks

**Core:**
- Django 5.2.13 - Primary web framework

**Testing:**
- pytest 8.0+ - Test runner
- pytest-django 4.8+ - Django integration for pytest
- playwright 1.45+ - E2E testing framework

**Build/Dev:**
- Tailwind CSS (CDN) - CSS framework
- HTMX 1.9.12 (CDN) - Server-side interaction framework
- Alpine.js 3.x.x (CDN) - Lightweight UI behavior framework
- Lucide Icons (CDN) - Icon set

## Key Dependencies

**Critical:**
- psycopg[binary] 3.2+ - PostgreSQL database adapter
- gunicorn 23.0+ - WSGI HTTP Server for production
- whitenoise 6.7+ - Static file serving for Django

**Infrastructure:**
- python-dotenv 1.0+ - Environment variable management
- requests 2.31+ - HTTP library for API integrations

## Configuration

**Environment:**
- Configured via `.env` file (based on `.env.example`)
- Key configs required: `SECRET_KEY`, `DEBUG`, `ALLOWED_HOSTS`, `DB_*`, `N8N_WEBHOOK_SECRET`, `ASSISTANT_N8N_WEBHOOK_URL`

**Build:**
- `manage.py` - Django task runner
- `pytest.ini` - Test configuration
- `config/settings.py` - Django project settings

## Platform Requirements

**Development:**
- Python 3.10+
- PostgreSQL or SQLite (local development defaults to SQLite)
- virtualenv (suggested in `env/`)

**Production:**
- Linux (implied by Gunicorn and PostgreSQL usage)
- PostgreSQL
- Caddy (implied by `Caddyfile` and `install_caddy.sh`)

---

*Stack analysis: 2026-05-30*
