# Phase 6: Historical Comparison — Execution Plan

---
wave: 1
depends_on: []
files_modified: []
autonomous: false
---

## Overview

Close v1 milestone gaps: HIST-01 (per-year execution records), HIST-02 (compare current to previous year), HIST-03 (copy last year's checklist and notes). Phase 7B already provides trends, find_last_year_task, and task-level last-year comparison. This phase adds structured execution records, a dedicated comparison view, and copy-from-previous-year.

**Gap Closure:** Closes gaps from v1-MILESTONE-AUDIT.md (HIST-01, HIST-02, HIST-03)

## must_haves

- [ ] User can view per-year execution records (completion date, notes, who was contacted)
- [ ] User can compare current year to previous year (task-by-task execution view)
- [ ] User can copy last year's checklist and notes to current year task
- [ ] No existing features broken

---

# Plan 06-01: Historical Record Storage and Retrieval

---
wave: 1
depends_on: []
files_modified: [app/models.py, app/routes.py, app/database.py]
autonomous: true
---

## Tasks

<task name="completion-date">
Add completion_date to TaskInstance (optional date, nullable). Add to app/models.py. In app/database.py _migrate(): add completion_date column if not in task_instance. In task update route: when status changes to "completed", set completion_date to today if null. Add completion_date field to task form for manual edit.
</task>

<task name="execution-summary">
Build execution summary per task: completion_date (or updated_at when completed), notes, note_logs (who/what from content), checklist completion. Use existing NoteLog, ChecklistItem. No new "who was contacted" model — notes/NoteLog suffice for now; user can record contacts in notes.
</task>

<task name="history-route">
Add GET /history or GET /audit-history?year=: query param. List tasks for year with execution summary: template name, due_date, status, completion_date, notes preview, checklist % complete, evidence count. Group by category. Link to each task.
</task>

<task name="history-template">
Create templates/history.html: table of per-year execution records, filter by year. Extends base.html. Add nav link to History.
</task>

## Verification

- /history?year=2025 returns 200 with task list
- Completed tasks show completion_date or updated_at
- Nav includes History link

---

# Plan 06-02: Comparison View and Copy-Previous-Year

---
wave: 2
depends_on: [06-01]
files_modified: [app/routes.py, app/trends.py, templates/]
autonomous: true
---

## Tasks

<task name="comparison-route">
Add GET /comparison?year=&baseline= (or extend /trends). Task-by-task side-by-side: for each template with instances in both years, show current-year task | baseline-year task | completion_date, notes preview, checklist %, evidence count. Reuse find_last_year_task, aggregate_by_template. Link to each task.
</task>

<task name="comparison-template">
Create templates/comparison.html: two-column or table layout, current year vs baseline year. Filter by year/baseline. Link from /trends. Add nav link to Comparison in base.html.
</task>

<task name="copy-checklist">
Add POST /tasks/{task_id}/copy-from-last-year. If find_last_year_task returns a task: copy ChecklistItem rows (text, completed=False, sort_order) to current task; append NoteLog entries (content, created_at) from last year to current task. Idempotent option: merge vs replace (default: append new items).
</task>

<task name="copy-ui">
In templates/task_detail.html: when last_year_task exists, add "Copy checklist and notes from last year" button. POST to copy-from-last-year, redirect back with success message.
</task>

## Verification

- /comparison returns 200 with year vs baseline task pairs
- Copy-from-last-year copies checklist items and notes
- Task detail shows copy button when last year task exists
