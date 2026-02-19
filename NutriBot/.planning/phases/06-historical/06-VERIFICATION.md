# Phase 6: Historical Comparison — Verification

---
status: passed
must_haves_verified: 4/4
---

## must_haves

- [x] User can view per-year execution records (completion date, notes, who was contacted)
- [x] User can compare current year to previous year (task-by-task execution view)
- [x] User can copy last year's checklist and notes to current year task
- [x] No existing features broken

## Verification

| Check | Result |
|-------|--------|
| GET /history returns 200 | ✓ |
| History shows completion_date, notes, checklist %, evidence | ✓ |
| GET /comparison returns 200 | ✓ |
| Comparison shows task pairs year vs baseline | ✓ |
| Copy-from-last-year copies checklist + notes | ✓ |
| Task detail shows copy button when last_year_task exists | ✓ |
| Restart and verify script passes | ✓ |
