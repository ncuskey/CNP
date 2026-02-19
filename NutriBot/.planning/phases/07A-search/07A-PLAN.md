# Phase 7A: Local Offline Search — Execution Plan

---
wave: 1
depends_on: []
files_modified: []
autonomous: false
---

## Overview

Add local, offline full-text search across tasks, notes, memos, evidence, and templates. Use SQLite FTS5 for fast search; fallback to SQL LIKE if FTS5 unavailable. No embeddings, no LLM, no external APIs. Minimal dependencies.

## must_haves

- [ ] /search returns results quickly (<1s typical)
- [ ] Finds matches in notes, memo text, evidence descriptions, filenames, task titles, template names
- [ ] Filters work (year, category, entity type)
- [ ] Nav search bar works
- [ ] Reindex works and is safe
- [ ] No existing schema migrations required (FTS is separate virtual table)
- [ ] "Search from here" shortcuts on task detail, evidence, retention

---

# Plan 07A-01: FTS5 Search Index Module

---
wave: 1
depends_on: []
files_modified: [app/search_index.py, app/database.py]
autonomous: true
---

## Tasks

<task name="fts5-module">
Create app/search_index.py:
- def fts5_available(engine) -> bool: execute "SELECT fts5_version();" or try CREATE VIRTUAL TABLE; return True if succeeds
- def ensure_search_table(engine): create FTS5 virtual table search_index if not exists
  - Columns: entity_type TEXT, entity_id INTEGER, task_id INTEGER, category TEXT, title TEXT, content TEXT
  - FTS5: CREATE VIRTUAL TABLE IF NOT EXISTS search_index USING fts5(entity_type, entity_id, task_id, category, title, content, tokenize='porter unicode61')
- def rebuild_index(db): DELETE FROM search_index (or DROP + CREATE), then INSERT from all sources (see index-sources task)
- def search(db, q, year?, category?, entity?): if FTS5 available, use MATCH; else fallback to LIKE across content columns
</task>

<task name="index-sources">
Index content from:
A) TaskInstance: entity_type=task, entity_id=task.id, task_id=task.id, title = template.name + " " + year/month, category from template, content = notes + " " + status + " " + str(due_date or "")
B) NoteLog: entity_type=note, entity_id=id, task_id, content = note content
C) GeneratedDocument (memo only): entity_type=memo, entity_id=id, task_id, content = concatenate context, actions_taken, decision, risks from content_json
D) EvidenceItem: entity_type=evidence, entity_id=id, task_id, title=original_filename, content=description + stored_filename
E) TaskTemplate: entity_type=template, entity_id=id, task_id=NULL, title=name, content=category + " " + recurrence_rule
For tasks: join TaskInstance with TaskTemplate for name/category. Include task_id for task/note/memo/evidence.
</task>

<task name="search-meta">
Store metadata in data/search_meta.json (no schema change):
- last_indexed: ISO datetime
- counts: {task: N, note: N, memo: N, evidence: N, template: N}
- fts5_available: bool
Write after rebuild_index. Create data/ if needed.
</task>

<task name="init-hook">
In app/database.py init_db or startup: after SQLModel.create_all, call ensure_search_table(engine). If FTS5 unavailable, log warning; search will use LIKE fallback.
</task>

<task name="like-fallback">
Implement LIKE fallback in search(): when FTS5 unavailable, query each source table with WHERE content LIKE '%q%' OR title LIKE '%q%', union results. Apply year/category/entity filters. Return same result shape as FTS5 path.
</task>

## Verification

- Run app; no errors. Check data/search_meta.json after first reindex.
- If FTS5 works: search for a known task name returns result.
- If FTS5 disabled (e.g. mock): LIKE fallback returns results.

---

# Plan 07A-02: Search Routes & Admin

---
wave: 1
depends_on: [07A-01]
files_modified: [app/routes.py]
autonomous: true
---

## Tasks

<task name="search-route">
Add GET /search in app/routes.py:
- Query params: q (required for search), year, category, entity (task|note|memo|evidence|template)
- If q empty: render search page with empty results
- Call search_index.search(db, q, year, category, entity)
- Return results grouped by entity_type
- Pass to templates/search.html
</task>

<task name="search-admin-route">
Add GET /search/admin:
- Render simple page showing: last_indexed, counts per entity, fts5_available
- Link/button to trigger reindex
- Use data/search_meta.json; if missing, show "Never indexed"
</task>

<task name="reindex-route">
Add POST /search/reindex:
- Call search_index.rebuild_index(db)
- Redirect to /search/admin?reindexed=1
- Safe to call repeatedly
</task>

## Verification

- GET /search?q=verification returns results
- GET /search/admin shows metadata
- POST /search/reindex completes, redirects, admin shows updated last_indexed

---

# Plan 07A-03: Search UI Template

---
wave: 1
depends_on: [07A-02]
files_modified: [templates/search.html]
autonomous: true
---

## Tasks

<task name="search-template">
Create templates/search.html:
- Extends base.html
- Search form: input name=q, value from query param; filters: year, category, entity dropdown
- Form action GET /search (preserve filters in URL)
- Results section: grouped by entity_type (Tasks, Notes, Memos, Evidence, Templates)
</task>

<task name="result-rows">
Each result row shows:
- title/snippet (~120 chars around match, safe HTML escape)
- link: for task/note/memo/evidence -> /tasks/{task_id}; for template -> /templates/{id}
- entity type badge
</task>

<task name="snippets">
Use search_index.snippet() or manual truncation: extract ~120 chars around first match. Escape HTML (Jinja | e). If FTS5 highlight available, use it; else bold the query term in snippet via simple replace (case-insensitive, escaped).
</task>

## Verification

- Search "verification", see results with snippets
- Click result link, navigates to correct page
- Filters apply correctly

---

# Plan 07A-04: Global Search Bar & Shortcuts

---
wave: 2
depends_on: [07A-03]
files_modified: [templates/base.html, templates/task_detail.html, templates/evidence_library.html, templates/retention.html]
autonomous: true
---

## Tasks

<task name="nav-search-bar">
In templates/base.html nav, add search form (before or after first nav link):
- &lt;form method="get" action="/search" style="display:inline;"&gt;
- &lt;input type="search" name="q" placeholder="Search..." value="{{ request.query_params.get('q', '') }}"&gt;
- &lt;button type="submit"&gt;Search&lt;/button&gt;
- Keep current query in input when on /search page (pass q to base or use request.query_params in block)
</task>

<task name="task-detail-shortcut">
On templates/task_detail.html, add "Search related" link:
- href="/search?q={{ task.template.name | urlencode }}&category={{ task.template.category | urlencode }}"
- Or simpler: /search?q={{ task.template.name | urlencode }}
</task>

<task name="evidence-shortcut">
On templates/evidence_library.html, add small "Search evidence" link that prefills: /search?entity=evidence (or add to existing filter UI)
</task>

<task name="retention-shortcut">
On templates/retention.html, add "Search: delete candidate" and "Search: review soon" links:
- /search?q=delete%20candidate
- /search?q=review%20soon
</task>

## Verification

- Type in nav search, submit, results shown
- Task detail "Search related" opens search with task name
- Retention shortcuts open search with relevant terms

---

# Plan 07A-05: Incremental Index Updates (Optional)

---
wave: 2
depends_on: [07A-01]
files_modified: [app/search_index.py, app/routes.py, app/documents.py]
autonomous: true
---

## Tasks

<task name="update-index-fn">
In app/search_index.py add:
- def update_index_row(conn, entity_type, entity_id, task_id, category, title, content): INSERT OR REPLACE into search_index (FTS5 uses rowid; we need DELETE + INSERT for entity_id match, or use content as unique key)
- Simpler: def delete_from_index(conn, entity_type, entity_id): DELETE FROM search_index WHERE entity_type=? AND entity_id=?
- def insert_into_index(conn, entity_type, entity_id, task_id, category, title, content): INSERT
- FTS5 virtual tables don't have UNIQUE; use rowid. To "update": DELETE WHERE entity_type=? AND entity_id=? then INSERT.
</task>

<task name="hook-tasks">
After task create/update in routes: call update_index_row for task. After note create: update for note. After evidence attach: update for evidence. After memo save (documents.save_memo_content): update for memo. After template create/update: update for template.
</task>

<task name="hook-deletes">
When deleting task, note, evidence, template: call delete_from_index. (Soft deletes may not apply; only hard deletes.)
</task>

## Verification

- Create new task, run search for its name, appears without full reindex (if incremental hooked)
- Full reindex still works

## Note

Incremental updates can be deferred. Reindex on demand is acceptable. Mark this plan as optional; implement if time permits.

---

# Plan 07A-06: Nav Link & Docs

---
wave: 2
depends_on: [07A-04]
files_modified: [templates/base.html, README.md, .planning/ROADMAP.md, .planning/STATE.md]
autonomous: true
---

## Tasks

<task name="nav-search-link">
Ensure Search is discoverable: add &lt;a href="/search"&gt;Search&lt;/a&gt; in nav if not already covered by search bar. (Search bar submits to /search; link to /search for empty search is fine.)
</task>

<task name="readme-search">
Update README.md: add "Search" section noting FTS5 full-text search, /search/reindex for rebuild, data/search_meta.json for status.
</task>

<task name="roadmap-state">
Update .planning/ROADMAP.md: add Phase 7A: Local Offline Search (Complete).
Update .planning/STATE.md: current focus = Phase 7A complete.
</task>

## Verification

- Nav has Search
- README documents search
- ROADMAP/STATE updated

---

# Summary

| Plan    | Wave | Delivers |
|---------|------|----------|
| 07A-01  | 1    | FTS5 index module, rebuild, LIKE fallback |
| 07A-02  | 1    | GET /search, /search/admin, POST /search/reindex |
| 07A-03  | 1    | Search UI template with filters, snippets |
| 07A-04  | 2    | Global search bar, "Search from here" shortcuts |
| 07A-05  | 2    | Incremental index updates (optional) |
| 07A-06  | 2    | Nav link, README, ROADMAP/STATE |

## Post-Implementation

- Run .\scripts\restart_and_verify.ps1
- Test search with real data
- Verify FTS5 or LIKE fallback works
