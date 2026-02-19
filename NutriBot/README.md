# BCSD Child Nutrition Ops Console

Local compliance & memory system for school nutrition programs.

## Run

```bash
pip install -r requirements.txt
python app.py
```

Then open http://127.0.0.1:8000

## Onboarding (v1.2)

On first visit to **Today** (`/today`), you'll be redirected to the onboarding wizard. Configure:

1. **District Profile** — Name, state, timezone, school year
2. **Programs Operated** — NSLP, SBP, SMP, Summer, CACFP, FFVP
3. **Operational Deadlines** — Claim deadline day, month-end close, verification window
4. **Evidence & Retention Defaults** — Retention policy, minimal audit set
5. **Data & Storage** — Confirm vault and backups paths (read-only)
6. **Seed Setup** — Optional: install preset pack, generate year plan, reindex search

Settings are stored in `data/settings.json`. You can skip for now (link on onboarding page) or complete later via **Settings** (`/settings`).

## Regulations Library (v1.2)

Track USDA and Idaho CNP regulations with local PDF snapshots and review cadence.

- **Regulations** (`/regulations`) — List with filters (authority, topic, review due soon)
- **Add Regulation** — Title, authority, topic, source URL, review frequency
- **Upload PDF** — Store local copies in `vault/_regulations/` (by authority/topic)
- **Mark Reviewed** — Sets last_reviewed, computes next_review_due
- **Seed Recommended Regs** — Adds starter list (USDA/Idaho links); upload PDFs as needed

Metadata in `data/reg_library.json`. Review page shows "Regulations review due soon: N" when any regulation is due within 30 days.

## Recurrence Rules

Templates use a simple recurrence syntax in the `recurrence_rule` field:

| Format | Example | Behavior |
|--------|---------|----------|
| `ANNUAL:MM-DD` | `ANNUAL:10-01` | One task per year on that date |
| `MONTHLY:DD` | `MONTHLY:10` | 12 tasks per year (one per month, due on day DD) |
| `ONCE:YYYY-MM-DD` | `ONCE:2026-07-15` | One-off task on that date |
| blank | — | Skip in Year Planner (or include with "include no recurrence" checked) |

## Year Planner

1. Go to **Year Planner** (`/planner`)
2. Select year, check options (include monthly, include templates without recurrence)
3. Click **Generate Plan**
4. Idempotent: safe to run repeatedly; no duplicates created

## PDF Generation (Phase 4)

Document generation (cover sheet, compliance memo, evidence index) can output PDFs.

**Install one of:**
- `pip install weasyprint` — Recommended: full HTML/CSS → PDF. On Windows, may need [GTK3 runtime](https://github.com/nicothin/weasyprint-windows).
- `pip install reportlab` — Fallback: basic text rendering if WeasyPrint unavailable.

If neither is installed, HTML preview works but PDF download will fail with install guidance.

## Phase 1–5 Complete

- **app/models.py** — + EvidenceRequirement, EvidenceItem, RetentionRule, GeneratedDocument
- **app/guidance.py** — Audit readiness, memo draft, next steps, retention explain (Phase 5)
- **app/evidence.py** — Vault storage, retention rules, missing evidence logic
- **app/export.py** — Audit packet export (task + year/category), optional include generated docs
- **app/documents.py** — Cover sheet, memo, evidence index generation
- **app/guidance.py** — Compliance Assistant v2: audit readiness score, memo drafts, task guidance, retention "Why?"
- **app/pdf_engine.py** — WeasyPrint/ReportLab abstraction for HTML→PDF
- **app/routes.py** — Evidence attach, template requirements, retention page, evidence library, export

## Phase 6A–6B: Daily Usability & Review Prep

- **Today** (`/today`) — Default landing page: today's tasks, overdue, due in 7 days, audit risk, missing evidence, recent evidence, quick actions, notification banner, Review Status widget
- **Quick Capture** (`/quick`) — Fast note, evidence attach, communication log without navigating to task
- **Evidence Inbox** (`/inbox`) — Drop files in `vault/_inbox/`, assign to tasks
- **Backups** (`/backups`) — Auto-backup once per day at startup; manual create/restore
- **Review** (`/review`) — Review Prep Mode: critical issues, category breakdown, missing evidence, memo status, export readiness
- **Review Mode** — Nav toggle; when on, highlights tasks missing required evidence, shows readiness, warning banners on task pages
- **Notifications** — Local engine: overdue, missing required, retention review due, readiness &lt;60; banner on /today and /review; dismissible
- **Export Ready** — Per task: "Export Ready" or "Incomplete for audit packet" (missing required evidence or memo)

## History & Comparison (Phase 6)

Per-year execution records and year-over-year comparison.

- **History** (`/history`) — Per-year execution records: completion date, notes, checklist %, evidence count
- **Comparison** (`/comparison`) — Task-by-task side-by-side: current year vs baseline
- **Copy from last year** — On task detail when last year task exists: copy checklist and notes

## Trends (Phase 7B)

Cross-year comparison: task completion, readiness, evidence volume, retention workload.

- **Trends** (`/trends`) — Year vs baseline (default: current vs previous year). Summary cards, category table, month table, retention workload, template links
- **Template trend** (`/trends/template/{id}`) — Instance metrics, top missing evidence types per year
- **Task detail** — "Last year comparison" when same template exists for previous year
- **Today** — "This month vs last year" widget

## Preset Library (Phase 7C)

Install curated TaskTemplates, EvidenceRequirements, and RetentionRules from preset packs. BCSD Starter Pack v1 includes ~25 templates across Verification, Claims, Training, Procurement, CEP, Reviews, Policies, and Other.

- **Presets** (`/presets`) — View available packs, preview what would be added, install
- **Preview** — Dry run: see templates/requirements/retention rules to add vs skip
- **Install** — Idempotent: safe to run multiple times; existing items (matched by name+category, etc.) are skipped

## Search (Phase 7A)

Full-text search across tasks, notes, memos, evidence, and templates. Uses SQLite FTS5 when available; falls back to SQL LIKE otherwise.

- **Search** (`/search`) — Query with filters (year, category, entity type)
- **Search admin** (`/search/admin`) — View last indexed time, counts per entity, rebuild index
- **Reindex** — POST `/search/reindex` or use admin page to rebuild the index after bulk data changes
- **Metadata** — `data/search_meta.json` stores last_indexed, counts, fts5_available

## Audit Readiness (Phase 5)

Each task has an **audit readiness score** (0–100) based on: missing required evidence (−40), no evidence (−15), overdue (−10), memo missing (−10), checklist <80% (−5). Use **Draft Compliance Memo** to generate a memo from task data. **Assistant v2** (`/assistant-v2`) offers quick queries and free-text routing (e.g. "what's due and missing evidence", "safe to delete"). **Retention Why?** explains matched rules per evidence item.

## Requirements Satisfied

- SYS-01 through SYS-04, TASK-01 through TASK-06
- EVID-01 through EVID-04 (Phase 3)
- RETN-01 through RETN-03 (Phase 3)
- ASST-01 through ASST-04
