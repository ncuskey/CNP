# Plan 06-01: Historical Record Storage and Retrieval — Summary

**Status:** Complete

## Delivered

- **completion_date** — Added to TaskInstance in app/models.py; migration in app/database.py _migrate(); task update route sets completion_date when status becomes completed; task form includes completion_date field for manual edit
- **execution summary** — app/history.py: build_execution_records() per task (completion_date, notes, note_logs preview, checklist %, evidence count)
- **GET /history** — Lists tasks for year with execution summary, grouped by category, filter by year
- **templates/history.html** — Table of per-year execution records
- **Nav link** — History added to base.html

## Verification

- /history?year=2025 returns 200
- Completed tasks show completion_date or updated_at
- Nav includes History link
