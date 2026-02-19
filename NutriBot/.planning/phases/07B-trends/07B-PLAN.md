# Phase 7B: Cross-Year Insights / Trends — Execution Plan

---
wave: 1
depends_on: []
files_modified: []
autonomous: false
---

## Overview

Add cross-year insights using existing data: task completion + readiness trends, evidence volume trends, retention workload trends, "this period last year" comparisons, "what changed since last year" summaries. Additive only, no schema changes. Use existing compute_audit_readiness, compute_missing_evidence, get_missing_requirement_types.

## must_haves

- [ ] /trends loads and shows year vs baseline comparisons
- [ ] Category and month tables show deltas
- [ ] Template trend detail page works
- [ ] Task detail shows last-year comparison when available
- [ ] "This month last year" widget on /today
- [ ] No schema changes; no existing features broken

---

# Plan 07B-01: Trends Module

---
wave: 1
depends_on: []
files_modified: [app/trends.py]
autonomous: true
---

## Tasks

<task name="trends-module">
Create app/trends.py:
- def compute_task_metrics(db, task) -> dict: readiness (via compute_audit_readiness), evidence_count, missing_required_count, missing_supporting_count, has_memo, is_overdue, is_completed (status==completed)
- def aggregate_by_category(db, year) -> list[dict]: for each category, total_tasks, completion_rate, avg_readiness, pct_missing_required, avg_evidence_count, memo_coverage_rate
- def aggregate_by_month(db, year) -> list[dict]: for months 1-12, tasks_due_in_month, completion_rate, avg_readiness, missing_required_rate, evidence_added_in_month (count EvidenceItem.added_at in that month for tasks in year)
- def aggregate_by_template(db, year, template_id=None) -> dict|list: if template_id, return metrics for that template; else return list of template metrics. Include: instance_count, avg_readiness, completion_rate, avg_evidence_count, top_missing_evidence_types (top 3)
- def retention_workload(db, year) -> dict: review_soon_count (items with review_date in year range, today <= review_date <= today+60), safe_to_delete_count (keep_until < today or disposition==delete_candidate, filter by task.year)
- def find_last_year_task(db, task) -> TaskInstance|None: same template_id, year=task.year-1; if task.month set, match month; else match by nearest due_date
- def compare_years(current: dict, baseline: dict) -> dict: add delta fields (e.g. completion_rate_delta = current - baseline)
</task>

<task name="top-missing-types">
For top_missing_evidence_types: use get_missing_requirement_types per task, aggregate (evidence_type, importance) counts, return top 3 by count
</task>

<task name="evidence-by-month">
evidence_added_in_month: EvidenceItem has task_id; join to TaskInstance for year. Filter EvidenceItem.added_at by month. Use task.year to scope to correct year's tasks.
</task>

## Verification

- compute_task_metrics returns expected keys
- aggregate_by_category with sample data returns non-empty list
- find_last_year_task finds correct task for monthly and annual templates

---

# Plan 07B-02: Trends Dashboard & Template Detail Routes

---
wave: 1
depends_on: [07B-01]
files_modified: [app/routes.py]
autonomous: true
---

## Tasks

<task name="trends-route">
Add GET /trends:
- Query params: year (default current), baseline (default year-1)
- Call aggregate_by_category(db, year), aggregate_by_category(db, baseline)
- Call aggregate_by_month(db, year), aggregate_by_month(db, baseline)
- Call retention_workload(db, year)
- Compute summary cards: completion_rate, avg_readiness, missing_required_pct, memo_coverage (for year)
- Use compare_years to add deltas to category and month tables
- Render templates/trends.html
</task>

<task name="template-trend-route">
Add GET /trends/template/{template_id}:
- Query params: year, baseline
- Call aggregate_by_template(db, year, template_id), aggregate_by_template(db, baseline, template_id)
- Get list of instances for each year with metrics
- Render templates/trends_template.html with instances table, metrics, top missing types per year
</task>

## Verification

- GET /trends returns 200
- GET /trends/template/1 returns 200 with correct data

---

# Plan 07B-03: Trends UI Templates

---
wave: 1
depends_on: [07B-02]
files_modified: [templates/trends.html, templates/trends_template.html]
autonomous: true
---

## Tasks

<task name="trends-template">
Create templates/trends.html:
- Extends base.html
- Year/baseline filter form (GET /trends)
- Summary cards: completion rate, avg readiness, missing required %, memo coverage (year vs baseline, show delta)
- Category comparison table: category, year metrics, baseline metrics, delta columns
- Month comparison table: month 1-12, year vs baseline metrics, deltas
- Retention workload: review soon count, safe to delete count
- Link to template trend: /trends/template/{id} for each template in category table
</task>

<task name="trends-template-detail">
Create templates/trends_template.html:
- Template name, year/baseline params
- Metrics table (year vs baseline)
- Instances list: task link, readiness, missing required, evidence count, status
- Top missing evidence types per year
- Link back to /trends
</task>

## Verification

- Trends page renders with tables
- Template trend page shows instance list

---

# Plan 07B-04: Task Detail Last-Year Comparison

---
wave: 2
depends_on: [07B-01]
files_modified: [app/routes.py, templates/task_detail.html]
autonomous: true
---

## Tasks

<task name="last-year-context">
In task_detail route: if task has template_id, call find_last_year_task(db, task). If found, compute readiness, evidence_count, missing_types, has_memo for last year task. Pass last_year_task and last_year_metrics to template.
</task>

<task name="task-detail-widget">
In templates/task_detail.html add "Last year comparison" section (when last_year_task exists):
- Last year readiness score
- Evidence count
- Missing required types (list)
- Memo present (yes/no)
- Links: <a href="/tasks/{last_year_task.id}">Open last year task</a>
- Note: audit export folder link if exists — optional; can add path from export logic or skip for now
</task>

## Verification

- Task with same template last year shows comparison
- Task without last year equivalent shows nothing (or "No last year data")

---

# Plan 07B-05: Today "This Month Last Year" Widget

---
wave: 2
depends_on: [07B-01]
files_modified: [app/routes.py, templates/today.html]
autonomous: true
---

## Tasks

<task name="today-month-stats">
In today_page route: compute for current month (this year): tasks due, completion rate, avg readiness, missing required count. Compute same for same month last year. Pass this_month_stats and last_year_month_stats to template.
</task>

<task name="today-widget">
In templates/today.html add small widget:
- "This month vs last year" — current month stats vs same month last year (e.g. "Feb 2026: 12 tasks, 75% complete, 82 avg readiness | Feb 2025: 10 tasks, 80% complete, 78 avg readiness")
</task>

## Verification

- /today shows month comparison when data exists

---

# Plan 07B-06: Nav & Docs

---
wave: 2
depends_on: [07B-03]
files_modified: [templates/base.html, README.md, .planning/ROADMAP.md, .planning/STATE.md]
autonomous: true
---

## Tasks

<task name="nav-trends">
Add &lt;a href="/trends"&gt;Trends&lt;/a&gt; to templates/base.html nav
</task>

<task name="readme-trends">
Update README.md: add "Trends" section — /trends, year vs baseline comparison, category/month tables, template trend detail, task last-year comparison, today month widget
</task>

<task name="roadmap-state">
Update .planning/ROADMAP.md: add Phase 7B: Cross-Year Insights (Complete)
Update .planning/STATE.md: current focus = Phase 7B complete
</task>

## Verification

- Nav shows Trends link
- README documents trends
- ROADMAP/STATE updated

---

# Plan 07B-07: Exportable Comparison (Optional)

---
wave: 2
depends_on: [07B-02]
files_modified: [app/routes.py]
autonomous: true
---

## Tasks

<task name="trends-csv">
Add GET /exports/trends.csv?year=YYYY&baseline=YYYY:
- Stream CSV with category-level comparison (category, year_completion, baseline_completion, delta, year_readiness, baseline_readiness, etc.)
- Reuse StreamingResponse pattern from existing exports
</task>

## Verification

- Download trends.csv returns valid CSV

## Note

Optional; can defer if time-constrained. Plan 07B-06 is sufficient for core deliverable.

---

# Summary

| Plan    | Wave | Delivers |
|---------|------|----------|
| 07B-01  | 1    | app/trends.py (compute_task_metrics, aggregates, find_last_year_task, compare_years) |
| 07B-02  | 1    | GET /trends, GET /trends/template/{id} |
| 07B-03  | 1    | templates/trends.html, trends_template.html |
| 07B-04  | 2    | Task detail last-year comparison widget |
| 07B-05  | 2    | Today "this month last year" widget |
| 07B-06  | 2    | Nav link, README, ROADMAP/STATE |
| 07B-07  | 2    | GET /exports/trends.csv (optional) |

## Post-Implementation

- Run .\scripts\restart_and_verify.ps1
- Verify /trends with real data
- Verify task detail shows last-year when applicable
