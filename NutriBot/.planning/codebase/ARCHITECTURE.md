# Architecture

**Analysis Date:** 2025-02-18

## Pattern Overview

**Overall:** Request–Response MVC with FastAPI; server-rendered HTML + HTMX for progressive enhancement.

**Key Characteristics:**
- Single-process, synchronous DB access (SQLModel/SQLite)
- No SPA; Jinja2 templates render full HTML
- HTMX for targeted DOM updates (checklist toggle, add checklist, add notes, quick capture)
- No authentication layer; local single-user
- Static mounts: `/static` (CSS), `/vault` (evidence files)

## Layers

**Routes:**
- Purpose: HTTP handlers, request/response, form handling
- Location: `app/routes.py`
- Contains: ~70+ route handlers (GET/POST)
- Depends on: app modules (evidence, documents, guidance, trends, history, etc.)
- Used by: FastAPI app in `main.py`

**Models:**
- Purpose: Data persistence, SQLModel tables
- Location: `app/models.py`
- Contains: TaskTemplate, TaskInstance, ChecklistItem, NoteLog, EvidenceItem, EvidenceRequirement, RetentionRule, GeneratedDocument
- Depends on: SQLModel only
- Used by: All app modules

**Domain Modules:**
- Purpose: Business logic (evidence, documents, guidance, trends, history, etc.)
- Location: `app/*.py` (evidence.py, documents.py, guidance.py, trends.py, history.py, planner.py, presets.py, search_index.py, backup.py, export.py, notifications.py, recurrence.py)
- Contains: Functions, no classes; stateless operations
- Depends on: app.models, app.database
- Used by: app/routes.py

**Templates:**
- Purpose: HTML rendering
- Location: `templates/`
- Contains: Jinja2 templates extending `base.html`
- Depends on: Context passed from routes
- Used by: routes via Jinja2Templates (directory: `BASE_DIR / "templates"`)

## Data Flow

**Request → Response (full page):**
1. Request hits FastAPI router in `app/routes.py`
2. `get_db()` yields SQLModel Session
3. Route calls domain functions (e.g., `compute_audit_readiness`, `build_execution_records`)
4. Domain functions query DB, return dicts
5. Route renders template with context: `templates.TemplateResponse("template.html", {"request": request, ...})`
6. HTMLResponse returned

**Request → Response (HTMX partial):**
1. HTMX sends POST with `HX-Request` header
2. Route checks `request.headers.get("HX-Request")` to decide response type
3. If HTMX: return partial template (e.g., `checklist_item.html`, `note_item.html`, `quick_capture_success.html`)
4. If normal: return RedirectResponse
5. HTMX swaps response into target DOM element

**State Management:**
- No client-side state; server holds all state in SQLite
- Cookies: `review_mode`, `last_task_id` for UX
- sessionStorage: `notifications_dismissed` for notification banner

## Key Abstractions

**get_db:**
- Purpose: FastAPI dependency yielding SQLModel Session
- Location: `app/routes.py`
- Pattern: Generator-based dependency injection

**compute_audit_readiness / compute_missing_evidence:**
- Purpose: Audit readiness scoring, missing evidence logic
- Location: `app/guidance.py`, `app/evidence.py`
- Used by: routes, trends, notifications

**find_last_year_task / find_baseline_task:**
- Purpose: Cross-year task matching
- Location: `app/trends.py`
- Used by: routes, history

**store_evidence_file / store_evidence_from_inbox:**
- Purpose: Copy files into vault, return paths for EvidenceItem
- Location: `app/evidence.py`
- Used by: routes (attach evidence, inbox assign)

## Entry Points

**main.py:**
- Location: `main.py`
- Triggers: `uvicorn main:app`
- Responsibilities: Lifespan (init_db, seed_retention_rules, auto-backup), exception handler, static mounts (`/static`, `/vault`)

**app.py:**
- Location: `app.py`
- Triggers: `python app.py` (wraps uvicorn)
- Responsibilities: Launch uvicorn with reload on port 8000

## FastAPI Routes (Key Patterns)

**Full-page GET (server-rendered):**
- `/` → Redirect to `/today`
- `/today` → `templates/today.html` (Daily Command Center)
- `/dashboard` → `templates/dashboard.html`
- `/review` → `templates/review.html`
- `/trends` → `templates/trends.html`
- `/history` → `templates/history.html`
- `/comparison` → `templates/comparison.html`
- `/search` → `templates/search.html`
- `/templates`, `/templates/new`, `/templates/{id}` → template CRUD
- `/tasks/new`, `/tasks/{id}` → task CRUD
- `/quick` → `templates/quick_capture_page.html`
- `/planner`, `/calendar`, `/assistant`, `/assistant-v2`
- `/evidence`, `/retention`, `/inbox`, `/backups`, `/presets`
- `/hygiene`, `/exports`, `/export`
- `/tasks/{id}/docs`, `/tasks/{id}/docs/memo/edit`, `/tasks/{id}/memo/draft`

**POST with full-page re-render:**
- `/tasks/{id}/update` → re-renders `task_detail.html`
- `/templates`, `/tasks`, `/inbox/assign`, `/presets/{id}/install` → RedirectResponse

**HTMX partial responses:**
- `POST /tasks/{id}/checklist` → returns `templates/checklist_item.html` (hx-target: #checklist-container, hx-swap: beforeend)
- `POST /checklist/{id}/toggle` → returns `templates/checklist_item.html` (hx-target: this, hx-swap: outerHTML)
- `POST /tasks/{id}/notes` → returns `templates/note_item.html` (hx-target: #notes-container, hx-swap: afterbegin)
- `POST /quick/note`, `POST /quick/evidence`, `POST /quick/log` → returns `templates/quick_capture_success.html` when HX-Request

**Streaming:**
- `/exports/tasks.csv`, `/exports/evidence.csv`, `/exports/retention.csv`, `/exports/trends.csv` → StreamingResponse

## Jinja Templates

**Base layout:**
- `templates/base.html` — Sidebar, topbar, search form, `{% block content %}`; loads Bootstrap 5, Bootstrap Icons, HTMX 1.9.10, `static/css/theme.css`, `static/css/adminator-layout.css`

**Page templates (extend base.html):**
- `templates/today.html`, `templates/dashboard.html`, `templates/review.html`
- `templates/trends.html`, `templates/trends_template.html`, `templates/history.html`, `templates/comparison.html`
- `templates/search.html`, `templates/search_admin.html`
- `templates/task_detail.html`, `templates/task_form.html`, `templates/template_form.html`, `templates/template_detail.html`, `templates/templates_list.html`
- `templates/quick_capture_page.html`, `templates/planner.html`, `templates/planner_result.html`, `templates/calendar.html`
- `templates/assistant.html`, `templates/assistant_v2.html`
- `templates/evidence_library.html`, `templates/evidence_explain.html`, `templates/retention.html`, `templates/inbox.html`, `templates/inbox_assign.html`
- `templates/hygiene.html`, `templates/backups.html`, `templates/presets.html`, `templates/preset_preview.html`
- `templates/exports.html`, `templates/export.html`
- `templates/memo_draft.html`
- `templates/docs/docs_home.html`, `templates/docs/cover_sheet.html`, `templates/docs/memo.html`, `templates/docs/memo_edit.html`, `templates/docs/evidence_index.html`

**Partial templates (HTMX targets / includes):**
- `templates/checklist_item.html` — HTMX: hx-post, hx-trigger=click, hx-target=this, hx-swap=outerHTML
- `templates/note_item.html` — Rendered by add_note route
- `templates/quick_capture_success.html` — Success message for quick capture
- `templates/notification_banner.html` — Include for critical/retention alerts
- `templates/task_row.html`, `templates/template_row.html` — Row fragments (if used)

## HTMX Usage

**Pattern:** Forms and elements use `hx-post`, `hx-target`, `hx-swap`, `hx-on::after-request` for progressive enhancement. Fallback: `action`/`method` for non-JS.

**Files with HTMX:**
- `templates/task_detail.html` — Checklist add, notes add
- `templates/checklist_item.html` — Toggle completed
- `templates/quick_capture.html` — Quick note, evidence, log forms

**HX-Request detection:** Routes for `/quick/note`, `/quick/evidence`, `/quick/log` check `request.headers.get("HX-Request")` to return partial vs redirect.

## Error Handling

**Strategy:** HTTPException for 404s; generic Exception handler returns traceback in response for 500s.

**Patterns:**
- `raise HTTPException(404, "Task not found")` in routes
- `_debug_exception_handler` in `main.py` returns full traceback for debugging

## Cross-Cutting Concerns

**Logging:** Minimal; `app/database.py` logs search index init warnings
**Validation:** Pydantic via FastAPI Form/Query; `app/recurrence.py` validates recurrence rules
**Authentication:** None

---

*Architecture analysis: 2025-02-18*
