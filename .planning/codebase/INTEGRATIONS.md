# External Integrations

**Analysis Date:** 2026-05-30

## APIs & External Services

**Social Messaging:**
- Meta Messenger (Facebook Graph API v18.0) - Used for patient communication and booking via Messenger
  - SDK/Client: `requests` (manual implementation in `messenger/messenger_api.py`)
  - Auth: `MESSENGER_APP_SECRET`, `MESSENGER_APP_ID`, `MESSENGER_VERIFY_TOKEN` (via connection-specific tokens stored in DB)

**AI & Automation:**
- n8n - Used for AI Assistant workflows and message processing
  - SDK/Client: `requests` (manual implementation in `widget/ai_client.py`)
  - Auth: `X-N8N-Webhook-Secret` (configured via `N8N_WEBHOOK_SECRET`)
  - Integration: Bidirectional via webhooks (`ASSISTANT_N8N_WEBHOOK_URL` and Django endpoints in `messenger/views.py`)

## Data Storage

**Databases:**
- PostgreSQL (Production)
  - Connection: `DB_HOST`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`
  - Client: `psycopg` (via Django ORM)
- SQLite (Local Development)
  - Connection: `db.sqlite3` file

**File Storage:**
- Local filesystem (via `django.core.files.storage.FileSystemStorage`)
- Static files served by WhiteNoise (`whitenoise.storage.CompressedManifestStaticFilesStorage`)

**Caching:**
- None detected (uses default Django session caching in DB)

## Authentication & Identity

**Auth Provider:**
- Custom (Django built-in auth)
  - Implementation: Session-based auth with custom user model `accounts.User`

## Monitoring & Observability

**Error Tracking:**
- None detected

**Logs:**
- Standard Python logging configured in `settings.py` (defaults to console)
- File logs detected: `server.log` (in root)

## CI/CD & Deployment

**Hosting:**
- Self-hosted (implied by `install_docker.sh`, `install_caddy.sh`, `deploy_app.sh`)

**CI Pipeline:**
- None detected

## Environment Configuration

**Required env vars:**
- `SECRET_KEY`
- `DEBUG`
- `ALLOWED_HOSTS`
- `DB_ENGINE`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT`
- `N8N_WEBHOOK_SECRET`
- `ASSISTANT_N8N_WEBHOOK_URL`

**Secrets location:**
- `.env` file (local development)
- Environment variables (production)

## Webhooks & Callbacks

**Incoming:**
- `/messenger/webhook/` - Facebook Messenger webhook
- `/messenger/n8n-webhook/` - Shared n8n message processor
- `/messenger/ai/context/`, `/messenger/ai/services/`, etc. - Tool endpoints for n8n AI

**Outgoing:**
- Meta Graph API (`https://graph.facebook.com/v18.0/me/messages`)
- n8n assistant webhook (configured via `ASSISTANT_N8N_WEBHOOK_URL`)

---

*Integration audit: 2026-05-30*
