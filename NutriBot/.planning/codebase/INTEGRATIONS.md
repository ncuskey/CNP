# External Integrations

**Analysis Date:** 2025-02-18

## APIs & External Services

**None.** No external APIs, cloud services, or third-party SDKs. Application is fully offline/local.

## Data Storage

**Databases:**
- SQLite
  - Connection: File path `data/db.sqlite` (from `app/database.py`)
  - Client: SQLModel (SQLAlchemy) via `app/database.py`
  - FTS5 full-text search in `app/search_index.py` (falls back to LIKE if FTS5 unavailable)

**File Storage:**
- Local filesystem only
  - Vault: `vault/` - Evidence files, organized by year/category/task (`app/evidence.py`, `app/database.py`)
  - Inbox: `vault/_inbox/` - Unassigned uploads before linking to tasks
  - Audit packets: `vault/_audit_packets/` - Exported task folders (`app/export.py`)
  - Backups: `backups/` - DB and config snapshots (`app/backup.py`)

**Caching:**
- None

## Authentication & Identity

**Auth Provider:**
- Custom / None
  - No login or auth middleware
  - Review mode via cookie `review_mode` (see `templates/base.html`)
  - No OAuth, JWT, or session store

## Monitoring & Observability

**Error Tracking:**
- None

**Logging:**
- Standard Python logging; `app/search_index.py` uses `logging.getLogger(__name__)`
- Debug exception handler in `main.py` returns traceback in 500 responses (development aid)

## CI/CD & Deployment

**Hosting:**
- Local only; no cloud platform

**CI Pipeline:**
- None (scripts in `scripts/` for manual verification)

## Environment Configuration

**Required env vars:**
- None

**Secrets location:**
- Not applicable (no secrets; local-only app)

## Webhooks & Callbacks

**Incoming:**
- None

**Outgoing:**
- None

## CDN Dependencies (Frontend)

Loaded from CDN in `templates/base.html`:
- Bootstrap 5.3.3 (jsdelivr)
- Bootstrap Icons 1.11.3 (jsdelivr)
- HTMX 1.9.10 (unpkg)

Local static assets:
- `/static/css/theme.css`
- `/static/css/adminator-layout.css`
- `/vault` - Mounted as static for evidence file access

---

*Integration audit: 2025-02-18*
