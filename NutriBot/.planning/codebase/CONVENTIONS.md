# Coding Conventions

**Analysis Date:** 2025-02-18

## Naming Patterns

**Files:**
- Snake_case for Python modules: `search_index.py`, `pdf_engine.py`, `evidence.py`, `recurrence.py`
- Snake_case for templates: `quick_capture.html`, `task_detail.html`, `checklist_item.html`

**Functions:**
- Snake_case: `compute_audit_readiness`, `find_last_year_task`, `build_execution_records`, `get_task_display_name`
- Route handlers: `trends_page`, `task_detail`, `add_checklist_item`, `toggle_checklist`

**Variables:**
- Snake_case: `task_id`, `last_year_task`, `category_comparison`, `year_data`
- Short locals where clear: `y` for year, `b` for baseline, `tpl` for template

**Types:**
- PascalCase for SQLModel/Pydantic models: `TaskInstance`, `TaskTemplate`, `EvidenceItem`, `ChecklistItemCreate`
- UPPER_SNAKE for constants: `EVIDENCE_TYPES`, `IMPORTANCE_LEVELS`, `RETENTION_DISPOSITION`

## Code Style

**Formatting:**
- No formatter config detected (black, ruff, etc.)
- Standard Python 4-space indentation
- Line length: no enforced limit; long lines occur in routes and templates

**Linting:**
- No linter config detected
- `# noqa: F401` used in `app/database.py` for model import side effect

## Import Organization

**Order:**
1. Standard library (`datetime`, `pathlib`, `typing`, `re`, `csv`, `io`)
2. Third-party (`fastapi`, `sqlmodel`, `jinja2`, `pydantic`)
3. Local app imports (`from app.xxx import ...`)

**Example from `app/routes.py`:**
```python
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, Response, StreamingResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, select

from app.database import get_engine, init_db, INBOX_DIR, VAULT_DIR
from app.evidence import apply_retention_rule, compute_missing_evidence, ...
```

**Path Aliases:**
- None — Use `from app.xxx import` for app modules

## Error Handling

**HTTP Exceptions:**
- `raise HTTPException(404, "Task not found")` for not-found
- `raise HTTPException(400, "Invalid evidence_type or importance")` for bad request
- `raise HTTPException(400, "No file provided")` for missing required input
- Second arg is message string; status code first

**File/IO Errors:**
- `try/except FileNotFoundError` → re-raise as `HTTPException(404, str(e))` or custom message
- Example in `app/routes.py` preset install: `except FileNotFoundError: raise HTTPException(404, f"Preset pack not found: {pack_id}")`

**Validation Errors:**
- `try/except ValueError` in `app/evidence.py`, `app/recurrence.py`, `app/backup.py` for parse failures
- Planner in `app/planner.py` catches `Exception` and appends to `result["errors"]` list

**Global Exception Handler:**
- `app.py` registers `_debug_exception_handler` for uncaught `Exception`
- Returns `PlainTextResponse` with traceback for 500s (development aid)

## Logging

**Framework:** Python `logging` (minimal use)

**Patterns:**
- `logging.getLogger(__name__).warning("Search index init skipped: %s", e)` in `app/database.py`
- No structured logging; no log levels beyond warning

## Comments

**When to Comment:**
- Module docstrings at top of files describing purpose
- Function docstrings for public APIs and domain logic

**Docstrings:**
- Triple-quoted strings; describe purpose, parameters, return value
- Example from `app/guidance.py`: `compute_audit_readiness` documents heuristic rules

## Function Design

**Size:**
- Routes: 20–80 lines; some complex pages (e.g. `task_detail`) are longer
- Domain functions: focused; keep logic in modules (`app/evidence.py`, `app/guidance.py`), not routes

**Parameters:**
- `db: Session = Depends(get_db)` for DB access
- `request: Request` when template context or headers needed
- `Query(...)`, `Form(...)`, `File(...)` for request data

**Return Values:**
- `templates.TemplateResponse("template.html", {"request": request, ...})` for HTML
- `RedirectResponse(url=..., status_code=303)` for POST-redirect
- `StreamingResponse` for CSV exports
- Partial HTML for HTMX (see HTMX section)

## Module Design

**Exports:**
- Modules export functions and classes; no barrel files
- Routes import from `app.evidence`, `app.guidance`, `app.planner`, etc.

**Barrel Files:**
- None — Direct imports

---

## Jinja Conventions

**Template Inheritance:**
- Base: `templates/base.html` defines `{% block title %}`, `{% block content %}`
- Child templates: `{% extends "base.html" %}` then `{% block content %}...{% endblock %}`

**Includes:**
- Reusable fragments: `{% include "checklist_item.html" %}`, `{% include "note_item.html" %}`
- Include receives context from parent; pass `item` or `note` in loop

**Conditionals:**
- `{% if due_today %}...{% else %}...{% endif %}`
- `{% if request.cookies.get('review_mode') == '1' %}` for cookie checks
- `{{ x|default(0) }}` for safe defaults

**Loops:**
- `{% for t in due_today %}...{% endfor %}`
- `{% for item in checklist %}{% include "checklist_item.html" %}{% else %}...{% endfor %}`

**Filters:**
- `{{ value|default(0) }}`, `{{ value|urlencode }}`, `{{ "%02d"|format(t.month) }}`
- `{{ note.created_at.strftime('%Y-%m-%d %H:%M') }}` for dates

**Safe Access:**
- `task.template.name if task.template else 'Task'` for optional relations

---

## HTMX Conventions

**Script:**
- Loaded in `templates/base.html`: `https://unpkg.com/htmx.org@1.9.10`

**Form Partial Updates:**
- `hx-post="/path"` + `hx-target="#feedback-id"` + `hx-swap="innerHTML"`
- `hx-on::after-request="this.reset()"` to clear form after submit
- Example: `templates/quick_capture.html` Quick Note form

**List Append/Prepend:**
- `hx-target="#checklist-container"` + `hx-swap="beforeend"` for append
- `hx-target="#notes-container"` + `hx-swap="afterbegin"` for prepend
- `hx-on::after-request="this.reset(); document.getElementById('checklist-empty')?.remove()"` to clear and remove empty-state

**Inline Toggle:**
- `templates/checklist_item.html`: `hx-post="/checklist/{{ item.id }}/toggle"` + `hx-target="this"` + `hx-swap="outerHTML"`
- Click toggles; server returns updated partial

**Backend Detection:**
- Check `request.headers.get("HX-Request")` to distinguish HTMX from full-page POST
- If HTMX: return partial template (e.g. `quick_capture_success.html`)
- Else: return `RedirectResponse` for traditional flow
- Example: `app/routes.py` in `quick_note`, `quick_evidence`, `quick_log`

**Partial Templates:**
- `templates/checklist_item.html` — single checklist row
- `templates/note_item.html` — single note card
- `templates/quick_capture_success.html` — success message fragment

---

*Convention analysis: 2025-02-18*
