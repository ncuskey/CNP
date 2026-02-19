# Technology Stack

**Analysis Date:** 2025-02-18

## Languages

**Primary:**
- Python 3.9+ (inferred from `tuple[bool, str]` in `app/pdf_engine.py`) - Backend, routes, models, services

**Secondary:**
- HTML (Jinja2 templates in `templates/`)
- CSS (custom in `static/css/`)
- JavaScript (minimal; Bootstrap + HTMX)

## Runtime

**Environment:**
- Python 3.9+ (no `.python-version` or `pyproject.toml`; version inferred from type hints)

**Package Manager:**
- pip
- Lockfile: Not present (uses `requirements.txt` without pinned hashes)

## Frameworks

**Core:**
- FastAPI >=0.109.0 - Web framework, routing, templating
- Uvicorn[standard] >=0.27.0 - ASGI server (run via `python app.py` or `uvicorn main:app`)

**Templating:**
- Jinja2 >=3.1.0 - Server-side HTML rendering via `fastapi.templating.Jinja2Templates`

**Testing:**
- Not detected (no pytest, unittest config, or test files in app/)

**Build/Dev:**
- None (no build step; static assets served directly)

## Key Dependencies

**Critical:**
- sqlmodel >=0.0.14 - ORM (SQLAlchemy + Pydantic); models in `app/models.py`, DB in `app/database.py`
- python-multipart >=0.0.6 - Form/file upload handling for FastAPI

**PDF Generation:**
- weasyprint >=62.0 - Primary HTML→PDF backend (full CSS support); may need GTK3 on Windows
- reportlab >=4.0.0 - Fallback when WeasyPrint unavailable; basic text rendering
- Abstraction in `app/pdf_engine.py`: tries WeasyPrint first, falls back to ReportLab

**Frontend (CDN):**
- Bootstrap 5.3.3 - UI framework (`templates/base.html`: `bootstrap@5.3.3`)
- Bootstrap Icons 1.11.3 - Icon set
- HTMX 1.9.10 - Partial page updates (`templates/base.html`: `htmx.org@1.9.10`)

**Infrastructure:**
- SQLAlchemy (via SQLModel) - SQLite engine, FTS5 search in `app/search_index.py`

## Configuration

**Environment:**
- No `.env` or env-based config detected
- Paths hardcoded in `app/database.py`: `BASE_DIR`, `DATA_DIR`, `VAULT_DIR`, `INBOX_DIR`, `BACKUPS_DIR`, `DB_PATH`

**Build:**
- No build config; static files served from `static/` and `vault/` via FastAPI `StaticFiles`

## Platform Requirements

**Development:**
- Python 3.9+
- pip install -r requirements.txt
- Run: `python app.py` (starts uvicorn on 127.0.0.1:8000 with --reload)

**Production:**
- Local deployment; no cloud target
- SQLite file at `data/db.sqlite`
- Vault at `vault/` (local filesystem)

---

*Stack analysis: 2025-02-18*
