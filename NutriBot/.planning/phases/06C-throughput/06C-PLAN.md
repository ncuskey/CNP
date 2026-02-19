# Phase 6C: Throughput Improvements — Execution Plan

---
wave: 1
depends_on: []
files_modified: []
autonomous: false
---

## Overview

Additive throughput features: bulk inbox assignment, bulk evidence upload, last-task shortcut, CSV exports, bulk retention actions, vault hygiene tools. No schema changes. No refactors of core models.

## must_haves

- [ ] Can bulk assign multiple inbox files to one task in one action
- [ ] Can bulk upload multiple evidence files on task detail
- [ ] CSV exports (tasks, evidence, retention) download correctly with readiness/missing metrics
- [ ] Retention page supports bulk actions (keep, delete candidate, review date, keep until)
- [ ] Hygiene page identifies orphaned evidence records and orphaned files safely
- [ ] last_task_id cookie defaults task dropdowns
- [ ] Nav includes Exports and Hygiene links
- [ ] No schema breakage; app remains fast

---

# Plan 06C-01: Bulk Inbox Assignment

---
wave: 1
depends_on: []
files_modified: [app/routes.py, app/evidence.py, templates/inbox.html, templates/inbox_assign_bulk.html]
autonomous: true
---

## Tasks

<task name="inbox-bulk-route">
Add POST /inbox/assign-bulk route in app/routes.py.
- Accept: filenames (list via Form, e.g. filename=1.pdf&filename=2.pdf), task_id, evidence_type (default other), importance (default supporting), description (optional)
- For each filename: call store_evidence_from_inbox, create EvidenceItem, apply retention rule (reuse logic from inbox_assign)
- Collect successes and failures; return RedirectResponse to /inbox with query params: assigned_count=N&failed_count=M&failures=name1,name2
- On any FileNotFoundError for a file, skip that file, add to failures list, continue with others
</task>

<task name="inbox-bulk-ui">
Update templates/inbox.html:
- Add checkbox column; each row gets &lt;input type="checkbox" name="filename" value="{{ f.name }}"&gt;
- Add "Assign Selected" button that POSTs to /inbox/assign-bulk with selected filenames
- Add form wrapping table with action="/inbox/assign-bulk" method="post"
- Include task dropdown, evidence_type (default other), importance (default supporting), description
- Reuse task list from inbox_assign (need to pass tasks to inbox_page)
</task>

<task name="inbox-page-tasks">
Update inbox_page route to load tasks for current year (same query as inbox_assign_form) and pass to template so bulk form has task dropdown.
</task>

<task name="inbox-result-summary">
Display result summary on /inbox when query params assigned_count or failed_count present: "Assigned N files. Failed: M (list)."
</task>

## Verification

- Select 2+ files, assign to task, all appear on task evidence section
- If one file missing from inbox, others still assign; failures shown

---

# Plan 06C-02: Bulk Evidence Upload on Task Detail

---
wave: 1
depends_on: []
files_modified: [app/routes.py, templates/task_detail.html]
autonomous: true
---

## Tasks

<task name="bulk-upload-route">
Add POST /tasks/{task_id}/evidence/upload-bulk in app/routes.py.
- Accept: files (list of UploadFile via File(...) with multiple=True or Form file upload with multiple), evidence_type, importance, description (optional)
- For each file: use store_evidence_file (from temp copy), create EvidenceItem, apply retention rule (same as attach_evidence)
- Shared evidence_type/importance; if description empty, use filename as description
- Redirect to /tasks/{task_id}#evidence
</task>

<task name="bulk-upload-form">
Update task detail evidence section in templates/task_detail.html:
- Add second form for bulk upload: &lt;input type="file" name="files" multiple&gt; with evidence_type, importance, description
- Form action POST /tasks/{task_id}/evidence/upload-bulk
- Keep existing single-file upload form
</task>

## Verification

- Upload 3 files at once on task detail; all 3 appear as EvidenceItems

---

# Plan 06C-03: Last-Task Shortcut Cookie

---
wave: 1
depends_on: []
files_modified: [app/routes.py, templates/inbox_assign.html, templates/inbox.html, templates/quick_capture.html, templates/task_detail.html]
autonomous: true
---

## Tasks

<task name="set-last-task-cookie">
In routes that render task detail or task selection:
- task_detail: set cookie last_task_id={task_id} when viewing task (Response or RedirectResponse)
- quick_evidence, quick_capture_page: set cookie when task selected or form submitted
- inbox_assign_form, inbox_page: set cookie when assign form submitted
Use Response.set_cookie("last_task_id", str(task_id), max_age=86400*7)
</task>

<task name="default-task-dropdown">
In templates with task dropdown (inbox_assign.html, inbox.html bulk form, quick_capture.html):
- Read request.cookies.get("last_task_id")
- If present and matches a task id in the list, add selected to that option
- Jinja: {% for t in tasks %} &lt;option value="{{ t.id }}" {% if request.cookies.get('last_task_id')|int == t.id %}selected{% endif %}&gt;
</task>

<task name="cookie-on-view-task">
Ensure task_detail route sets cookie. Use Response or add to TemplateResponse - FastAPI TemplateResponse supports .set_cookie. Check: templates.TemplateResponse(...) returns response; we need to set cookie. Use response.set_cookie() after creating TemplateResponse, before returning.
</task>

## Verification

- View task 5, then open inbox assign; task 5 pre-selected in dropdown

---

# Plan 06C-04: CSV Exports

---
wave: 2
depends_on: [06C-01, 06C-02]
files_modified: [app/routes.py, templates/exports.html]
autonomous: true
---

## Tasks

<task name="exports-page">
Add GET /exports route. Render templates/exports.html with year filter, category/status filters for tasks, category/evidence_type for evidence. Page has buttons/links to download:
- Tasks CSV (year, category, status filters)
- Evidence CSV (year, category, evidence_type filters)
- Retention CSV (year filter)
</task>

<task name="tasks-csv">
Add GET /exports/tasks.csv. Query params: year, category, status.
- Stream CSV: task_id, title, category, due_date, status, readiness_score, missing_required_count, missing_supporting_count, has_memo, evidence_count
- Use StreamingResponse, csv module, generator. Compute readiness via compute_audit_readiness.
- Content-Disposition: attachment; filename="tasks.csv"
</task>

<task name="evidence-csv">
Add GET /exports/evidence.csv. Query params: year, category, evidence_type.
- Stream CSV: evidence_id, task_id, task_title, category, evidence_type, importance, original_filename, stored_filename, added_at, keep_until, review_date, disposition
- Join with TaskInstance, TaskTemplate for task_title
</task>

<task name="retention-csv">
Add GET /exports/retention.csv. Query params: year.
- Stream CSV of evidence in "review soon" and "safe to delete" (reuse retention_page logic: safe_to_delete, review_soon)
- Same columns as evidence CSV or subset
</task>

<task name="streaming-response">
Use FastAPI StreamingResponse with csv.writer and a generator that yields rows. No external deps.
</task>

## Verification

- Download tasks.csv, evidence.csv, retention.csv; open in Excel; columns correct, data present

---

# Plan 06C-05: Bulk Retention Actions

---
wave: 2
depends_on: []
files_modified: [app/routes.py, templates/retention.html]
autonomous: true
---

## Tasks

<task name="bulk-action-route">
Add POST /retention/bulk-action route.
- Accept: item_ids (list via Form, e.g. item_id=1&item_id=2), disposition (optional), review_date (optional), keep_until (optional)
- For each item_id: get EvidenceItem, update disposition/review_date/keep_until if provided (nullable)
- Redirect to /retention
</task>

<task name="retention-checkboxes">
Update templates/retention.html:
- Add checkbox column to each table (safe_to_delete, review_soon, keep)
- Checkbox: &lt;input type="checkbox" name="item_id" value="{{ e.id }}"&gt;
- Add bulk action form above or below tables: select disposition (Mark Keep, Mark Delete Candidate), or Set Review Date (date input), or Set Keep Until (date input)
- Form POSTs to /retention/bulk-action with selected item_ids and chosen action fields
- Use one form wrapping all three tables or separate forms; simplest: one form with all checkboxes, one set of action inputs
</task>

<task name="bulk-form-ui">
Bulk form: dropdown/buttons for action (Keep, Delete Candidate, Set Review Date, Set Keep Until). If Set Review Date: show date input. If Set Keep Until: show date input. Submit applies to all selected items.
</task>

## Verification

- Select 2 items, Mark Keep; both updated. Select 2, Set Review Date; both get date.

---

# Plan 06C-06: Vault Hygiene Tools

---
wave: 2
depends_on: []
files_modified: [app/routes.py, app/evidence.py, templates/hygiene.html]
autonomous: true
---

## Tasks

<task name="hygiene-page">
Add GET /hygiene route. Query param: year (optional, to limit scan).
- Orphaned evidence: EvidenceItem records where VAULT_DIR/file_path does not exist
- Orphaned files: walk vault (exclude _inbox, _trash, _audit_packets, _untracked); collect paths; find files not in any EvidenceItem.file_path
- Render templates/hygiene.html with two sections: orphaned evidence list, orphaned files list
</task>

<task name="move-orphaned-files">
Add POST /hygiene/move-orphaned-files. Accept: paths (list) or scan and move all. Move orphaned files to vault/_untracked/{year}/ or vault/_untracked/unknown/. Create _untracked dir. Do not delete.
</task>

<task name="mark-missing-evidence">
Add POST /hygiene/mark-missing-evidence. Accept: item_id or item_ids (list).
- Set EvidenceItem.disposition = "missing" (model allows any string; no schema change)
- Or append to description if disposition is reserved for retention. Safer: use disposition="missing" since field is free-form str.
</task>

<task name="hygiene-actions">
UI: For orphaned evidence: "Mark as missing" button per item (POST mark-missing-evidence). For orphaned files: "Move to _untracked" button (POST move-orphaned-files). "Open folder" link that opens file explorer - use file:// URL or instruct user; browser may not open local paths. Provide path as text for copy.
</task>

<task name="vault-walk">
In app/evidence.py add get_orphaned_evidence(db, year?) and get_orphaned_files(db, year?). Walk VAULT_DIR, exclude _inbox, _trash, _audit_packets, _untracked. Compare with EvidenceItem.file_path.
</task>

## Verification

- Delete a file from vault; hygiene shows orphaned evidence. Add file to vault not in DB; hygiene shows orphaned file. Move orphaned files; they appear in _untracked.

---

# Plan 06C-07: Nav and Final Integration

---
wave: 2
depends_on: [06C-04, 06C-06]
files_modified: [templates/base.html]
autonomous: true
---

## Tasks

<task name="nav-exports">
Add &lt;a href="/exports"&gt;Exports&lt;/a&gt; to templates/base.html nav (after Export or near it).
</task>

<task name="nav-hygiene">
Add &lt;a href="/hygiene"&gt;Hygiene&lt;/a&gt; to templates/base.html nav.
</task>

<task name="route-order">
Ensure /exports and /exports/tasks.csv etc. are ordered correctly: specific paths before parameterized. /exports/tasks.csv before /exports/{x} if any.
</task>

## Verification

- Nav shows Exports and Hygiene; both links work.

---

# Summary

| Plan    | Wave | Delivers |
|---------|------|----------|
| 06C-01  | 1    | Bulk inbox assignment |
| 06C-02  | 1    | Bulk evidence upload on task |
| 06C-03  | 1    | last_task_id cookie |
| 06C-04  | 2    | CSV exports (tasks, evidence, retention) |
| 06C-05  | 2    | Bulk retention actions |
| 06C-06  | 2    | Vault hygiene page |
| 06C-07  | 2    | Nav links |

## Post-Implementation

- Update .planning/ROADMAP.md: add Phase 6C complete
- Update .planning/STATE.md: current focus, decisions
- Run .\scripts\restart_and_verify.ps1 to confirm no regressions
