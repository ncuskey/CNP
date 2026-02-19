# Phase 7C: Preset Library — Execution Plan

---
wave: 1
depends_on: []
files_modified: []
autonomous: false
---

## Overview

Add a local Preset Library to seed TaskTemplates, EvidenceRequirements, and RetentionRules. BCSD-only, editable, idempotent, no cloud, no schema changes. Start with "BCSD Starter Pack v1".

## must_haves

- [ ] /presets page exists with pack list
- [ ] Preview shows correct counts (templates, requirements, retention rules to add vs skip)
- [ ] Install works and is idempotent (no duplicates on repeated install)
- [ ] Templates appear in /templates; requirements visible on template detail
- [ ] No schema changes required

---

# Plan 07C-01: Preset Pack JSON & Module

---
wave: 1
depends_on: []
files_modified: [data/presets/bcsd_starter_pack_v1.json, app/presets.py]
autonomous: true
---

## Tasks

<task name="preset-json">
Create data/presets/bcsd_starter_pack_v1.json:
- Schema: { "name": "BCSD Starter Pack v1", "version": "1", "description": "...", "templates": [...], "retention_rules": [...] }
- Each template: { "name", "category", "recurrence_rule", "default_checklist": ["item1", "item2"], "evidence_requirements": [{ "evidence_type", "importance", "description" }] }
- Include ~20–35 templates across categories: Verification, Claims, Training, Procurement, CEP, Reviews, Policies, Other
- Use recurrence format: ANNUAL:MM-DD, MONTHLY:DD per app/recurrence.py
- Minimal audit set per template: submission, approval, calculation, source_data (required); communication (supporting)
- Category-specific: Training + training (required); Procurement + policy/other; CEP + source_data
- retention_rules: list of { "category", "evidence_type", "importance", "years_to_keep", "is_permanent", "description" } — align with seed_retention_rules defaults, add any extras
</task>

<task name="preset-templates-list">
Include templates (examples; adjust as needed):
- Monthly Claim Submission (MONTHLY:10) Claims
- Month-End Close / Reconciliation (MONTHLY:15) Claims
- Annual Verification Window Start (ANNUAL:10-01) Verification
- Verification Follow-up Deadline (ANNUAL:10-20) Verification
- Verification Final Submission (ANNUAL:11-15) Verification
- Civil Rights Training (ANNUAL:09-01) Training
- HACCP/SOP Review (ANNUAL:08-15) Reviews
- Wellness Policy Review (ANNUAL:04-01) Policies
- CEP ISP Calculation Snapshot (ANNUAL:04-15) CEP
- Procurement Plan Review (ANNUAL:05-01) Procurement
- On-site Review Prep (ANNUAL:01-15) Reviews
- Equipment/Inventory Check (ANNUAL:06-01) Other
- Summer Feeding Planning Kickoff (ANNUAL:02-01) Other
- Free/Reduced Application Process Review (ANNUAL:08-01) Policies
- Plus additional to reach ~20–35 total
</task>

<task name="presets-module">
Create app/presets.py:
- PRESETS_DIR = BASE_DIR / "data" / "presets"
- def load_preset_pack(name: str) -> dict: load JSON from data/presets/{name}.json, return parsed dict
- def find_template(db, name, category) -> TaskTemplate|None: select where name=? and category=?
- def find_or_create_template(db, name, category, recurrence_rule, default_checklist) -> (TaskTemplate, created: bool)
- def ensure_requirements(db, template_id, reqs: list) -> (added: int, skipped: int): for each req, check exists by (template_id, evidence_type, importance, description); insert if not
- def ensure_retention_rules(db, rules: list) -> (added: int, skipped: int): match on (category, evidence_type, importance, years_to_keep, is_permanent, description)
- def preview_install(db, pack: dict) -> dict: { templates_to_add, templates_to_skip, requirements_to_add, requirements_to_skip, retention_to_add, retention_to_skip, notes }
- def install_pack(db, pack: dict) -> dict: { added_templates, skipped_templates, added_requirements, skipped_requirements, added_retention_rules, skipped_retention_rules }
- Call seed_retention_rules(db) before installing pack retention rules if table empty
</task>

<task name="default-checklist-format">
default_checklist in JSON: list of strings. When storing in TaskTemplate, join with "\n" (newline) per existing convention.
</task>

## Verification

- load_preset_pack("bcsd_starter_pack_v1") returns valid dict
- preview_install on empty DB shows all templates as to_add
- install_pack creates templates; second run shows all skipped

---

# Plan 07C-02: Preset Routes & UI

---
wave: 1
depends_on: [07C-01]
files_modified: [app/routes.py, templates/presets.html, templates/preset_preview.html]
autonomous: true
---

## Tasks

<task name="presets-route">
Add GET /presets in app/routes.py:
- List available packs: scan data/presets/*.json or hardcode ["bcsd_starter_pack_v1"] for now
- For each pack: load name, description from JSON
- Render templates/presets.html with packs list
</task>

<task name="preview-route">
Add GET /presets/{pack_id}/preview:
- pack_id = bcsd_starter_pack_v1 (no .json)
- Load pack via load_preset_pack(pack_id)
- Call preview_install(db, pack)
- Render templates/preset_preview.html with summary: templates to add/skip, requirements counts, retention to add/skip, idempotency notes
</task>

<task name="install-route">
Add POST /presets/{pack_id}/install:
- Load pack, call install_pack(db, pack)
- Redirect to /presets?installed=1&added_templates=N&... with result summary in query params
- Or render presets.html with success message and counts
</task>

<task name="presets-template">
Create templates/presets.html:
- Extends base.html
- Title: Preset Library
- For each pack: name, description, [Preview Install] link, [Install] button (form POST)
- Link to /presets/{pack_id}/preview for preview
</task>

<task name="preview-template">
Create templates/preset_preview.html:
- Shows: templates to add (names), templates to skip (names), requirements to add/skip counts, retention rules to add/skip
- [Install] button that POSTs to /presets/{pack_id}/install
- [Back to Presets] link
</task>

## Verification

- GET /presets returns 200
- GET /presets/bcsd_starter_pack_v1/preview shows correct counts
- POST /presets/bcsd_starter_pack_v1/install creates data; second install skips all

---

# Plan 07C-03: Nav & Docs

---
wave: 2
depends_on: [07C-02]
files_modified: [templates/base.html, README.md, .planning/ROADMAP.md, .planning/STATE.md]
autonomous: true
---

## Tasks

<task name="nav-presets">
Add &lt;a href="/presets"&gt;Presets&lt;/a&gt; to templates/base.html nav
</task>

<task name="readme-presets">
Update README.md: add "Preset Library" section — /presets, BCSD Starter Pack v1, preview/install, idempotent
</task>

<task name="roadmap-state">
Update .planning/ROADMAP.md: add Phase 7C: Preset Library (Complete)
Update .planning/STATE.md: current focus = Phase 7C complete
</task>

## Verification

- Nav shows Presets link
- README documents preset usage
- ROADMAP/STATE updated

---

# Summary

| Plan    | Wave | Delivers |
|---------|------|----------|
| 07C-01  | 1    | Preset JSON, app/presets.py (load, preview, install, matching) |
| 07C-02  | 1    | GET /presets, /presets/{id}/preview, POST /presets/{id}/install, templates |
| 07C-03  | 2    | Nav link, README, ROADMAP/STATE |

## Post-Implementation

- Run .\scripts\restart_and_verify.ps1
- Install BCSD Starter Pack, verify templates in /templates
- Re-run install, verify no duplicates
