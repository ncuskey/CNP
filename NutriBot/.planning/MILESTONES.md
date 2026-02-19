# Project Milestones: BCSD Child Nutrition Ops Console

## v1.3 Structured Data & Claims (Shipped: 2025-02-18)

**Delivered:** Structured data entry tied to tasks; Monthly Claims tracking with data entry UI, backfill mode, claims dashboard, Today widget, CSV export, onboarding toggle.

**Phases completed:** 11-18 (8 plans total)

**Key accomplishments:**

- TaskDataField, TaskDataValue models; claim fields on Monthly Claim Submission template
- Structured Data section on task detail; POST /tasks/{id}/data/save
- Backfill mode on template detail; GET/POST /templates/{id}/backfill
- app/claims_trends.py: get_monthly_claim_data, compute_participation_metrics, compare_to_last_year
- GET /claims dashboard; Today page Claims Snapshot; GET /exports/claims.csv
- Onboarding/settings: Enable monthly claims tracking (default yes)

**Stats:**

- 8 phases, 8 plans
- app/task_data.py, app/claims_trends.py, app/models.py (TaskDataField, TaskDataValue)
- templates/claims.html, template_backfill.html, task_detail.html, today.html, exports.html

**Archives:**

- [milestones/v1.3-ROADMAP.md](milestones/v1.3-ROADMAP.md)
- [milestones/v1.3-REQUIREMENTS.md](milestones/v1.3-REQUIREMENTS.md)
- [milestones/v1.3-MILESTONE-AUDIT.md](milestones/v1.3-MILESTONE-AUDIT.md)

**What's next:** Run `/gsd:new-milestone` to define v1.4 or v2.0 goals.

---

## v1.2 Onboarding & Regulations (Shipped: 2025-02-18)

**Delivered:** Onboarding wizard for district/program settings; Regulations & Requirements Library with local PDF snapshots and review cadence; integration with presets and review page.

**Phases completed:** 10 (3 plans total)

**Key accomplishments:**

- Onboarding wizard: district profile, programs, deadlines, evidence defaults; saves to data/settings.json
- /today redirects to /onboarding when incomplete (with skip); /settings edits values after completion
- Regulations library: list with filters (authority, topic, due=soon), add, upload PDF, mark reviewed, seed
- Review page: "Regulations review due soon: N" widget linking to /regulations?due=soon
- Presets: "Annual Regulations Review" task template in BCSD Starter Pack
- Sidebar nav: Regulations, Settings links

**Stats:**

- 1 phase, 3 plans
- app/routes.py, app/settings_store.py, templates/onboarding.html, settings.html, regulations*.html
- data/settings.json, data/reg_library.json, vault/_regulations/

**Archives:**

- [milestones/v1.2-ROADMAP.md](milestones/v1.2-ROADMAP.md)
- [milestones/v1.2-REQUIREMENTS.md](milestones/v1.2-REQUIREMENTS.md)
- [milestones/v1.2-MILESTONE-AUDIT.md](milestones/v1.2-MILESTONE-AUDIT.md)

**What's next:** Run `/gsd:new-milestone` to define v1.3 or v2.0 goals.

---

## v1.1 UI Refresh (Shipped: 2025-02-18)

**Delivered:** Adminator-based UI with Bootstrap 5 layout, sidebar/topbar, and migrated pages; HTMX (checklist, notes, quick capture) preserved and enhanced.

**Phases completed:** 8-9 (9 plans total)

**Key accomplishments:**

- Adminator layout: base.html with sidebar, topbar, main content; theme.css and adminator-layout.css
- All NutriBot pages migrated to Bootstrap cards, tables, forms
- HTMX checklist toggle, notes add, quick capture (all three forms) with in-place updates
- Responsive layout (sidebar collapses on mobile)
- Quick capture gap closure: HX-Request support, feedback divs, form reset

**Stats:**

- 2 phases, 9 plans
- templates/base.html, 28+ page templates, static/css, app/routes.py updates

**Archives:**

- [milestones/v1.1-ROADMAP.md](milestones/v1.1-ROADMAP.md)
- [milestones/v1.1-REQUIREMENTS.md](milestones/v1.1-REQUIREMENTS.md)
- [milestones/v1.1-MILESTONE-AUDIT.md](milestones/v1.1-MILESTONE-AUDIT.md)

**What's next:** Run `/gsd-new-milestone` to define v1.2 or v2.0 goals.

---

## v1.0 MVP (Shipped: 2025-02-18)

**Delivered:** Full compliance memory system — recurring tasks, evidence vault, PDF generation, retention advisor, historical comparison, search, trends, presets.

**Phases completed:** 1-7 (13 phase groups, 50+ plans total)

**Key accomplishments:**

- Project scaffold with FastAPI, SQLModel, SQLite; run via `python app.py`
- Recurring task templates, checklists, calendar, dashboard, assistant summaries
- Evidence vault with metadata, vault folder structure, searchable library
- PDF generation (cover sheet, memo, evidence index) via WeasyPrint/ReportLab
- Retention advisor with keep_until, review_date, retention dashboard
- Historical records: completion_date, GET /history, GET /comparison, copy-from-last-year
- Daily usability: Today, Quick Capture, Inbox, Backups
- Review prep, bulk operations, CSV exports, local search, trends, preset library

**Stats:**

- 13 phases, 50+ plans
- Python/FastAPI, Jinja, HTMX

**Archives:**

- [milestones/v1-ROADMAP.md](milestones/v1-ROADMAP.md)
- [milestones/v1-REQUIREMENTS.md](milestones/v1-REQUIREMENTS.md)
- [milestones/v1-MILESTONE-AUDIT.md](milestones/v1-MILESTONE-AUDIT.md)

**What's next:** Run `/gsd:new-milestone` to define v1.1 or v2.0 goals.

---
