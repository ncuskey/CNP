# Phase 9: Page Migration & Polish — Execution Plan

---
wave: 1
depends_on: [08]
files_modified: []
autonomous: false
---

## Overview

Apply Adminator/Bootstrap 5 styling to all NutriBot pages. Replace inline styles with Bootstrap card, table, form classes. Ensure HTMX (checklist, notes, quick capture) continues to work. Verify all routes return 200.

**Depends on:** Phase 8 (base layout complete)

## must_haves

- [ ] Today, task detail, dashboard, review use Bootstrap cards/tables/forms
- [ ] Trends, history, comparison use Bootstrap styling
- [ ] Forms (templates, tasks, evidence) use Bootstrap form components
- [ ] Tables (evidence, retention, exports) use Bootstrap table styling
- [ ] HTMX (checklist toggle, notes add, quick capture) works
- [ ] All routes return 200; no regressions

---

# Plan 09-01: Today + Task Detail + HTMX Partials

---
wave: 1
depends_on: [08-02]
files_modified: [templates/today.html, templates/task_detail.html, templates/checklist_item.html, templates/note_item.html]
autonomous: true
---

## Tasks

<task name="today-migration">
Migrate `templates/today.html` to Bootstrap. Replace inline stat divs with `card card-body`; grid with `row col-md-6`; lists with `list-group`; Quick Actions with `btn btn-primary`; Quick Capture panel with `card` or `collapse`. Remove inline styles. Keep all links and logic.
</task>

<task name="task-detail-migration">
Migrate `templates/task_detail.html` to Bootstrap. Review alert → `alert alert-warning`; last year block → `card`; form → `form`, `mb-3`, `form-label`, `form-control`, `form-select`, `btn btn-primary`; guidance → `card`. Preserve all `hx-*` attributes. Evidence section → `table table-striped`.
</task>

<task name="checklist-note-partials">
Update `checklist_item.html` and `note_item.html` with Bootstrap classes. Keep `hx-post`, `hx-trigger`, `hx-target`, `hx-swap` unchanged. Use `list-group-item` or `form-check`; preserve `.completed` styling.
</task>

## Verification

- GET /today returns 200; cards render
- GET /tasks/{id} returns 200; HTMX add-checklist, add-notes, checklist toggle work

---

# Plan 09-02: Dashboard + Review

---
wave: 1
depends_on: [08-02]
files_modified: [templates/dashboard.html, templates/review.html]
autonomous: true
---

## Tasks

<task name="dashboard-migration">
Migrate `templates/dashboard.html`. Filter form → `row g-2`, `form-select`, `form-check`, `btn`; tables → `table table-striped table-hover`; status → `badge bg-secondary|warning|success`; links → `btn btn-sm btn-outline-primary`.
</task>

<task name="review-migration">
Migrate `templates/review.html`. Critical list → `list-group`; tables → `table table-striped`; color spans → `text-danger` or `badge`. Keep notification_banner.
</task>

## Verification

- GET /dashboard returns 200; filters and tables styled
- GET /review returns 200; tables and lists styled

---

# Plan 09-03: Trends + History + Comparison

---
wave: 2
depends_on: [09-01, 09-02]
files_modified: [templates/trends.html, templates/history.html, templates/comparison.html]
autonomous: true
---

## Tasks

<task name="trends-history-comparison">
Migrate `trends.html`, `history.html`, `comparison.html`. Filter forms → `form-select`, `btn`; stat blocks → `card card-body`; tables → `table table-striped`. Remove inline styles.
</task>

## Verification

- GET /trends, /history, /comparison return 200 with Bootstrap styling

---

# Plan 09-04: Forms + Templates Pages

---
wave: 2
depends_on: [09-01]
files_modified: [templates/template_form.html, templates/task_form.html, templates/templates_list.html, templates/template_detail.html]
autonomous: true
---

## Tasks

<task name="form-pages">
Migrate `template_form.html`, `task_form.html` to Bootstrap: `form`, `mb-3`, `form-label`, `form-control`, `form-select`, `btn btn-primary`.
</task>

<task name="templates-pages">
Migrate `templates_list.html`, `template_detail.html` with Bootstrap cards, tables, forms as applicable.
</task>

## Verification

- GET /templates, /templates/new, /tasks/new return 200; forms use Bootstrap

---

# Plan 09-05: Table Pages

---
wave: 3
depends_on: [09-03, 09-04]
files_modified: [templates/evidence_library.html, templates/retention.html, templates/exports.html]
autonomous: true
---

## Tasks

<task name="table-pages">
Migrate `evidence_library.html`, `retention.html`, `exports.html`: `table table-striped table-hover`, `card` wrappers, `btn btn-sm`.
</task>

## Verification

- GET /evidence, /retention, /exports return 200 with Bootstrap tables

---

# Plan 09-06: Misc Pages + Verification

---
wave: 3
depends_on: [09-04]
files_modified: [templates/quick_capture.html, templates/quick_capture_page.html, templates/inbox.html, templates/backups.html, templates/presets.html, templates/planner.html, templates/calendar.html, templates/assistant.html, templates/assistant_v2.html, templates/hygiene.html, templates/export.html, templates/search.html]
autonomous: true
---

## Tasks

<task name="misc-pages">
Migrate `quick_capture.html`, `quick_capture_page.html`, `inbox.html`, `backups.html`, `presets.html`, `planner.html`, `calendar.html`, `assistant.html`, `assistant_v2.html`, `hygiene.html`, `export.html`, `search.html` with Bootstrap card/form/table/button classes. Preserve Quick capture HTMX.
</task>

<task name="verification">
Verify key routes return 200. Fix any 500 or template errors. Document failures if any.
</task>

## Verification

- GET /quick, /inbox, /backups, /presets, /planner, /calendar, /assistant, /assistant-v2, /hygiene, /export, /search return 200
- No 500s on main user flows
