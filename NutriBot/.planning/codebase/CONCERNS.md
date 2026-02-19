# Codebase Concerns

**Analysis Date:** 2025-02-18

## Tech Debt

**Large routes file:**
- Issue: `app/routes.py` is ~2450 lines; all HTTP handlers in one file
- Files: `app/routes.py`
- Impact: Harder to navigate; merge conflicts when multiple features change
- Fix approach: Split into `app/routes_tasks.py`, `app/routes_evidence.py`, etc., or use APIRouter groups

**aggregate_by_month on every /today load:**
- Issue: `aggregate_by_month(db, year)` runs for current year and last year on every /today request
- Files: `app/routes.py` (today_page), `app/trends.py`
- Impact: May be slow with many tasks; O(n) over all tasks
- Fix approach: Cache by year/day; or compute only when needed

**No automated tests:**
- Issue: No pytest or unittest; only manual verification scripts
- Files: `scripts/verify_no_500.ps1`, `scripts/restart_and_verify.ps1`
- Impact: Regressions possible; refactoring risky
- Fix approach: Add pytest, TestClient for critical routes

**Inline styles across templates:**
- Issue: Multiple templates use inline `style="..."` instead of CSS classes or Bootstrap utilities
- Files: `templates/assistant_v2.html` (lines 18–19: min-width, width), `templates/base.html` (lines 24, 68, 192), `templates/calendar.html` (lines 35–41), `templates/checklist_item.html` (line 7: cursor), `templates/export.html`, `templates/docs/docs_home.html`, `templates/docs/cover_sheet.html`, `templates/memo_draft.html`, `templates/planner_result.html`, `templates/preset_preview.html`, `templates/search_admin.html`
- Impact: Inconsistent styling; harder to theme; violates separation of concerns
- Fix approach: Replace with Bootstrap utilities (e.g. `w-25`, `min-w-280`) or add classes to `static/css/theme.css`

**/export vs /exports naming:**
- Issue: Sidebar has both `/export` (audit packet export by year/category) and `/exports` (CSV downloads page); similar names cause confusion
- Files: `templates/base.html` (lines 140, 152), `app/routes.py` (lines 2182, 2408)
- Impact: Users may not distinguish between the two; onboarding friction
- Fix approach: Rename for clarity (e.g. `/export-packet` and `/exports` or `/csv-exports`); update sidebar labels to "Audit Packet" vs "CSV Exports"

## Known Bugs

- None identified in app code

## Security Considerations

**Local-only:**
- Risk: No auth; anyone with local access can use app
- Files: All routes
- Current mitigation: Designed for single-user local desktop
- Recommendations: No change if scope remains local-only

**File upload:**
- Risk: No virus scanning on uploaded evidence
- Files: `app/evidence.py`, `app/routes.py` (evidence upload)
- Current mitigation: Local filesystem
- Recommendations: Acceptable for single-user; add virus scan if multi-user

**Search LIKE fallback:**
- Risk: When FTS5 unavailable, search uses `LIKE '%{q}%'`; `q` containing `%` or `_` may cause unexpected matches
- Files: `app/search_index.py` (line 249)
- Current mitigation: FTS5 used when available; LIKE is fallback
- Recommendations: Escape `%` and `_` in `q` before LIKE pattern

## Performance Bottlenecks

**aggregate_by_month:**
- Problem: Called twice per /today (year + year-1)
- Files: `app/routes.py`, `app/trends.py`
- Cause: Iterates all tasks, computes metrics per task
- Improvement path: Cache results; or compute on-demand with lazy loading

**Search index rebuild:**
- Problem: Full rebuild scans all tasks, notes, evidence
- Files: `app/search_index.py`
- Cause: FTS5 rebuild is synchronous
- Improvement path: Background job; incremental updates

**CSV exports load all data:**
- Problem: `export_tasks_csv`, `export_evidence_csv`, `export_retention_csv` load full result sets into memory before streaming
- Files: `app/routes.py` (lines 2224–2354)
- Cause: `list(db.exec(...).all())` then iterate
- Improvement path: Use server-side cursor / chunked iteration for large datasets

## Fragile Areas

**Database migration:**
- Files: `app/database.py` `_migrate()`
- Why fragile: Manual ALTER TABLE; no migration framework
- Safe modification: Add new column checks; never remove columns without backup
- Test coverage: None

**PDF generation:**
- Files: `app/pdf_engine.py`, `app/documents.py`
- Why fragile: WeasyPrint has platform-specific dependencies (GTK on Windows)
- Safe modification: Fallback to ReportLab when WeasyPrint fails
- Test coverage: None

**Quick capture toggle (Today page):**
- Files: `templates/today.html` (lines 107, 112)
- Why fragile: Uses `onclick` + `classList.toggle('d-none')`; no ARIA; screen readers may not announce expand/collapse
- Safe modification: Add `aria-expanded`, `aria-controls`, `aria-label`; consider Bootstrap collapse component

**docs/ standalone HTML:**
- Files: `templates/docs/cover_sheet.html`, `templates/docs/memo.html`, `templates/docs/evidence_index.html`
- Why fragile: Standalone HTML (no base.html) for PDF; different structure than app pages
- Safe modification: Document pattern in STRUCTURE.md; avoid mixing app layout expectations

## Accessibility Gaps

**Quick capture panel (Today page):**
- Issue: Toggle button lacks `aria-expanded`, `aria-controls`; panel lacks `aria-hidden`; form controls in `quick_capture.html` lack `<label>` and `aria-label`
- Files: `templates/today.html`, `templates/quick_capture.html`
- Impact: Screen reader users may not understand expand/collapse state; form fields not properly associated
- Fix approach: Add `aria-expanded="false"` / `aria-controls="quick-capture-panel"` to button; `aria-hidden` on panel; add `<label for="...">` or `aria-label` to selects, textareas, file input in `quick_capture.html`

**Quick capture form controls:**
- Issue: No labels or aria-labels on task select, content textarea, file input, evidence_type select, importance select, description input
- Files: `templates/quick_capture.html`
- Impact: Assistive tech cannot announce purpose of fields
- Fix approach: Add `<label>` with `for` matching `id`, or `aria-label` on each control

## Scaling Limits

**SQLite:**
- Current capacity: Single file; acceptable for small-to-medium datasets
- Limit: Concurrent writes; large datasets
- Scaling path: Migrate to PostgreSQL if needed

**Single process:**
- Current capacity: One uvicorn worker
- Limit: No horizontal scaling
- Scaling path: Acceptable for local single-user

## Dependencies at Risk

**WeasyPrint:**
- Package: weasyprint
- Risk: GTK dependency on Windows; may fail to install
- Mitigation: ReportLab fallback in `app/pdf_engine.py`

## Missing Critical Features

- None identified

## Test Coverage Gaps

**Untested areas:**
- What's not tested: All routes, evidence upload, PDF generation, search, planner, presets, backup/restore
- Files: `app/routes.py`, `app/evidence.py`, `app/pdf_engine.py`, `app/search_index.py`, `app/planner.py`, `app/presets.py`, `app/backup.py`
- Risk: Regressions possible; refactoring risky
- Priority: High for core flows (CRUD, evidence, export)

**Verification scripts:**
- `scripts/verify_no_500.ps1`, `scripts/restart_and_verify.ps1` provide smoke tests only
- No assertions on response content; no test data isolation

---

*Concerns audit: 2025-02-18*
