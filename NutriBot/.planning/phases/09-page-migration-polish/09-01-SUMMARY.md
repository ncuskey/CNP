# Plan 09-01: Today + Task Detail + HTMX Partials — Summary

**Status:** Complete

## Completed

- today.html: Bootstrap cards, row/col layout, list-group, btn btn-primary, Quick Capture in card with d-none toggle
- task_detail.html: alert alert-warning, card for last year block, form with form-control/form-select, checklist/notes in cards, evidence table, export form
- checklist_item.html: list-group-item, form-check-input, preserved hx-* attributes
- note_item.html: card, card-body, text-muted for time

## Verification

- GET /today returns 200; cards render
- GET /tasks/{id} returns 200; HTMX add-checklist, add-notes, checklist toggle work
