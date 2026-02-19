# Plan 06-02: Comparison View and Copy-Previous-Year — Summary

**Status:** Complete

## Delivered

- **GET /comparison** — Task-by-task side-by-side: year vs baseline; uses build_comparison_pairs() from app/history.py; find_baseline_task() in app/trends.py
- **templates/comparison.html** — Table layout, year/baseline filters, link from /trends
- **Nav link** — Comparison added to base.html
- **POST /tasks/{id}/copy-from-last-year** — Copies ChecklistItem (text, completed=False) and NoteLog (content with "[Copied from YYYY]" prefix) from last year task
- **Copy button** — In task_detail.html when last_year_task exists; success message on redirect

## Verification

- /comparison returns 200
- Copy-from-last-year copies checklist items and notes
- Task detail shows copy button when last year task exists
