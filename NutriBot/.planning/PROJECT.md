# BCSD Child Nutrition Ops Console

## What This Is

A local-only desktop web application for a single user (district child nutrition administrator) to manage compliance deadlines, tasks, documentation, and audit evidence for school nutrition programs. It runs entirely on a local computer with manual data entry only—no cloud services or multi-user support. The system acts as a "compliance memory and operations console" that tracks what must be done, what was done, and what evidence must be retained for audits.

## Core Value

The administrator can reliably track recurring compliance tasks, attach evidence, generate audit packets, and know what to keep or delete—without losing institutional memory when staff changes or years pass.

## Requirements

### Validated (v1.0)

- ✓ User can create recurring compliance task templates with categories, due dates, recurrence rules, and default checklists — v1.0
- ✓ User can instantiate tasks per year and track status, checklist completion, and notes — v1.0
- ✓ User can view a calendar of tasks filtered by category — v1.0
- ✓ User can see overdue tasks and upcoming deadlines on a dashboard — v1.0
- ✓ User can attach evidence files to tasks with metadata (category, evidence type, retention rule) — v1.0
- ✓ User can store evidence in structured vault folders (YYYY/Category/TaskName) — v1.0
- ✓ User can generate PDFs: verification letters, checklist packets, audit index, compliance memos — v1.0
- ✓ User can see retention guidance (safe to delete, review soon, permanent) — v1.0
- ✓ User can view historical records: what was done each year, who was contacted, previous year comparison — v1.0
- ✓ User can copy last year's checklist and notes to current year — v1.0
- ✓ User can run the app with `python app.py` (or `main.py`) with auto-created SQLite DB and vault folder — v1.0
- ✓ User can see rule-based assistant output: what's due this month, missing evidence, overdue tasks, last year summary — v1.0

### Validated (v1.1)

- ✓ User sees Adminator-based layout (sidebar, topbar, content area) — v1.1
- ✓ User sees consistent styling across all pages (cards, tables, forms) — v1.1
- ✓ User can navigate via sidebar menu (all existing routes) — v1.1
- ✓ HTMX and existing functionality work with new UI — v1.1
- ✓ UI is responsive (mobile-friendly from Adminator) — v1.1

### Validated (v1.2)

- ✓ User completes onboarding wizard (district profile, programs, deadlines, evidence defaults) — v1.2
- ✓ Onboarding saves to data/settings.json; /today redirects when incomplete; /settings edits values — v1.2
- ✓ User can list/add regulations with filters, upload PDFs, mark reviewed, seed recommended list — v1.2
- ✓ Review page shows "Regulations review due soon: N" widget; presets include Annual Regulations Review — v1.2

### Validated (v1.3)

- ✓ User can enter structured task data (monthly claim fields) on task detail — v1.3
- ✓ User can backfill data across months on template detail — v1.3
- ✓ User can view claims dashboard (reimbursement, participation, trends vs last year) — v1.3
- ✓ User can see claims snapshot on Today page; export claims CSV — v1.3
- ✓ User can enable/disable monthly claims tracking in onboarding/settings — v1.3

### Active

- [ ] (None — run `/gsd:new-milestone` to define next goals)

### Out of Scope

- Multi-user support — single administrator only
- Authentication — not required initially
- Cloud sync — local-only by design
- External APIs — manual entry only
- Mobile support — desktop web app
- Heavy frameworks — prioritize simplicity and maintainability

## Context

School nutrition programs (NSLP, SBP, etc.) have recurring compliance obligations: verification, applications, training, reporting. District administrators must track deadlines, complete checklists, retain evidence for audits, and know retention rules. Institutional knowledge is often lost when staff turnover occurs. This system captures that knowledge locally and provides structure for compliance operations.

**Technical environment:** Windows/macOS, Python 3.11+, SQLite, simple HTML/HTMX frontend. Designed for long-term maintainability by someone who can read Python and Jinja templates.

## Constraints

- **Deployment**: Local computer only — no cloud dependencies
- **Data entry**: Manual only — no external APIs or integrations
- **Database**: SQLite — single file, portable, no server
- **Backend**: Python + FastAPI
- **Frontend**: Jinja + HTMX + minimal vanilla JS — no heavy SPA frameworks
- **PDF**: WeasyPrint or ReportLab — Jinja → HTML → PDF pipeline
- **Storage**: Local filesystem — vault for evidence files
- **Run command**: Must run via `python app.py` (or `main.py`)
- **Compatibility**: Windows and macOS
- **Maintainability**: Clean, readable, modular code; no unnecessary abstraction

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| FastAPI over Flask | Modern async, automatic OpenAPI, type hints | ✓ Good |
| SQLModel or SQLAlchemy | ORM for SQLite with migrations | ✓ Good |
| HTMX for dynamic UI | Server-rendered with progressive enhancement, minimal JS | ✓ Good |
| WeasyPrint vs ReportLab | HTML/CSS to PDF (WeasyPrint) vs programmatic (ReportLab) | ✓ Good |
| Directory: /app, /templates, /static, /data, /vault | Clear separation of concerns | ✓ Good |
| Bootstrap 5 CDN (no npm) | Adminator constraint; use CDN + extracted layout | ✓ Good |

## Tech Stack (Target)

- **Backend**: Python 3.11+, FastAPI (or Flask)
- **Database**: SQLite, SQLModel or SQLAlchemy
- **Frontend**: Jinja templates, HTMX, minimal vanilla JS
- **PDF**: WeasyPrint or ReportLab
- **File storage**: Local filesystem (`/vault`)

## Data Models (Initial)

- **TaskTemplate**: name, category, recurrence_rule, default_checklist
- **TaskInstance**: template_id, year, due_date, status, notes
- **ChecklistItem**: task_id, text, completed
- **EvidenceItem**: task_id, file_path, category, evidence_type, retention_rule, keep_until, review_date
- **RetentionRule**: category, years_to_keep, description
- **Contact**: name, role, email, phone

## MVP Milestones

| M | Scope |
|---|-------|
| M1 | Project scaffold, SQLite models, basic CRUD for tasks |
| M2 | Recurring task templates, checklist system, dashboard |
| M3 | Evidence attachment + metadata, vault folder structure |
| M4 | Document generation, PDF output |
| M5 | Retention advisor, review dashboard |
| M6 | Historical comparison tools |

## Current State (v1.3 Shipped)

- **Shipped:** 2025-02-18
- **Tech stack:** Python 3.11+, FastAPI, SQLModel, SQLite, Jinja, HTMX, Bootstrap 5, WeasyPrint/ReportLab
- **Run:** `python app.py` → http://127.0.0.1:8000
- **UI:** Adminator layout (sidebar, topbar), Bootstrap 5 cards/tables/forms, HTMX for dynamic updates
- **Data:** data/settings.json (onboarding), data/reg_library.json (regulations), vault/_regulations/ (PDFs)
- **Structured data:** TaskDataField, TaskDataValue; monthly claim fields; /claims dashboard, backfill, CSV export

---
*Last updated: 2025-02-18 after v1.3 milestone completion*
