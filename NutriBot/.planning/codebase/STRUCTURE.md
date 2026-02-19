# Codebase Structure

**Analysis Date:** 2025-02-18

## Directory Layout

```
NutriBot/
├── app/                         # Application code
│   ├── __init__.py
│   ├── backup.py                # Backup create/restore
│   ├── database.py               # DB init, session, migration, paths
│   ├── documents.py              # Cover sheet, memo, evidence index
│   ├── evidence.py               # Evidence storage, retention, vault
│   ├── export.py                 # Audit packet export
│   ├── guidance.py               # Audit readiness, memo draft, next steps
│   ├── history.py                # Execution records, comparison
│   ├── models.py                 # SQLModel tables
│   ├── notifications.py          # Review data, export readiness
│   ├── pdf_engine.py             # WeasyPrint/ReportLab abstraction
│   ├── planner.py                # Year planner generation
│   ├── presets.py                # Preset pack install
│   ├── recurrence.py             # Recurrence rule parsing
│   ├── routes.py                 # All HTTP routes (~70+ handlers)
│   ├── schemas.py                # Pydantic schemas (if any)
│   └── search_index.py           # FTS5 search
├── templates/                    # Jinja2 HTML templates
│   ├── base.html                 # Layout: sidebar, topbar, HTMX, Bootstrap
│   ├── today.html
│   ├── dashboard.html
│   ├── review.html
│   ├── trends.html
│   ├── trends_template.html
│   ├── history.html
│   ├── comparison.html
│   ├── search.html
│   ├── search_admin.html
│   ├── task_detail.html
│   ├── task_form.html
│   ├── task_row.html
│   ├── template_detail.html
│   ├── template_form.html
│   ├── templates_list.html
│   ├── template_row.html
│   ├── checklist_item.html       # HTMX partial
│   ├── note_item.html            # HTMX partial
│   ├── quick_capture_page.html
│   ├── quick_capture.html        # HTMX forms
│   ├── quick_capture_success.html # HTMX partial
│   ├── notification_banner.html  # Include
│   ├── planner.html
│   ├── planner_result.html
│   ├── calendar.html
│   ├── assistant.html
│   ├── assistant_v2.html
│   ├── evidence_library.html
│   ├── evidence_explain.html
│   ├── retention.html
│   ├── inbox.html
│   ├── inbox_assign.html
│   ├── hygiene.html
│   ├── backups.html
│   ├── presets.html
│   ├── preset_preview.html
│   ├── exports.html
│   ├── export.html
│   ├── memo_draft.html
│   └── docs/
│       ├── docs_home.html
│       ├── cover_sheet.html
│       ├── memo.html
│       ├── memo_edit.html
│       └── evidence_index.html
├── static/                       # Static assets
│   └── css/
│       ├── theme.css
│       └── adminator-layout.css
├── data/                         # SQLite DB, search metadata (generated)
│   ├── db.sqlite
│   ├── search_meta.json
│   └── presets/                  # Preset pack JSON files
│       └── bcsd_starter_pack_v1.json
├── vault/                        # Evidence files (generated)
│   ├── _inbox/                   # Unassigned uploads
│   ├── _trash/                   # Deleted evidence
│   ├── _untracked/               # Orphaned files moved here
│   └── {category}/{year}/...     # Task evidence by category/year
├── backups/                      # Backup archives (generated)
├── main.py                       # FastAPI app entry
├── app.py                        # Launch script (python app.py)
├── requirements.txt
├── scripts/
│   ├── restart_and_verify.ps1
│   ├── verify_no_500.ps1
│   └── verify_500_fixed.ps1
└── .planning/
    └── codebase/
        ├── ARCHITECTURE.md
        ├── STRUCTURE.md
        ├── STACK.md
        ├── INTEGRATIONS.md
        ├── CONVENTIONS.md
        ├── TESTING.md
        └── CONCERNS.md
```

## Directory Purposes

**app/:**
- Purpose: All application logic
- Contains: Python modules, no subpackages
- Key files: `app/routes.py`, `app/models.py`, `app/database.py`, `app/evidence.py`, `app/guidance.py`, `app/trends.py`, `app/history.py`, `app/documents.py`, `app/export.py`

**templates/:**
- Purpose: Jinja2 HTML templates
- Contains: `.html` files; most extend `base.html`
- Key files: `templates/base.html`, `templates/task_detail.html`, `templates/today.html`, `templates/trends.html`, `templates/history.html`, `templates/comparison.html`
- Partials: `templates/checklist_item.html`, `templates/note_item.html`, `templates/quick_capture_success.html`, `templates/notification_banner.html`

**static/:**
- Purpose: CSS and static assets
- Contains: `static/css/theme.css`, `static/css/adminator-layout.css`
- Served at: `/static` (mounted in `main.py`)

**data/:**
- Purpose: SQLite DB, search metadata, preset pack definitions
- Key files: `data/db.sqlite`, `data/search_meta.json`, `data/presets/*.json`
- Generated: Yes (db.sqlite, search_meta.json)
- Committed: data/presets/ yes; db.sqlite, search_meta.json no (gitignore)

**vault/:**
- Purpose: Evidence files, inbox, trash, untracked
- Structure: `vault/_inbox/`, `vault/_trash/`, `vault/_untracked/`, `vault/{category}/{year}/...`
- Served at: `/vault` (mounted in `main.py`)
- Generated: Yes
- Committed: No

**backups/:**
- Purpose: Backup archives
- Generated: Yes
- Committed: No

## Key File Locations

**Entry Points:**
- `main.py`: FastAPI app, lifespan, router, static mounts
- `app.py`: Launches uvicorn with reload

**Configuration:**
- `app/database.py`: Paths (BASE_DIR, DATA_DIR, VAULT_DIR, INBOX_DIR, BACKUPS_DIR, DB_PATH)
- `requirements.txt`: Dependencies

**Core Logic:**
- `app/routes.py`: All HTTP handlers
- `app/models.py`: Data models
- `app/evidence.py`: Evidence vault, retention rules
- `app/guidance.py`: Audit readiness, memo draft
- `app/trends.py`: Cross-year trends
- `app/history.py`: Execution records
- `app/documents.py`: Cover sheet, memo, evidence index
- `app/export.py`: Audit packet export
- `app/planner.py`: Year planner
- `app/presets.py`: Preset pack install
- `app/search_index.py`: FTS5 search

**Testing:**
- `scripts/verify_no_500.ps1`: Manual endpoint verification
- `scripts/restart_and_verify.ps1`, `scripts/verify_500_fixed.ps1`

## Naming Conventions

**Files:**
- Snake_case: `search_index.py`, `pdf_engine.py`, `quick_capture_page.html`

**Directories:**
- Lowercase: `app`, `templates`, `data`, `vault`, `static`, `backups`

**Templates:**
- Page: `{feature}.html` (e.g., `today.html`, `dashboard.html`)
- Partials: `{entity}_item.html`, `{entity}_row.html` (e.g., `checklist_item.html`, `note_item.html`)

## Where to Add New Code

**New Route:**
- Add to `app/routes.py` (or split into `app/routes_*.py` if file grows)

**New Domain Logic:**
- New module in `app/` (e.g., `app/new_module.py`)
- Import in `app/routes.py`

**New Page Template:**
- Add to `templates/`, extend `base.html` via `{% extends "base.html" %}` and `{% block content %}`

**New HTMX Partial:**
- Add partial template (e.g., `templates/my_partial.html`)
- Route returns `templates.TemplateResponse("my_partial.html", {...})`
- Use `hx-post`, `hx-target`, `hx-swap` in calling template

**New Static Asset:**
- Add to `static/css/` or `static/js/`
- Reference as `/static/css/filename.css` or `/static/js/filename.js`
- Add link/script in `templates/base.html` if global

**Preset Pack:**
- Add JSON to `data/presets/{pack_id}.json`
- Use `list_available_packs()` and `load_preset_pack()` from `app/presets.py`

## Special Directories

**data/:**
- Purpose: SQLite DB, search_meta.json, preset pack definitions
- Generated: db.sqlite, search_meta.json
- Committed: presets/ yes; db.sqlite, search_meta.json no

**vault/:**
- Purpose: Evidence files, inbox, trash, untracked
- Generated: Yes
- Committed: No

**backups/:**
- Purpose: Backup archives
- Generated: Yes
- Committed: No

---

*Structure analysis: 2025-02-18*
