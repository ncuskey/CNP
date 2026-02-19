# Plan 09-07: Quick Capture HTMX — Summary

**Status:** Complete

## Completed

- **Task 1:** Created `templates/quick_capture_success.html` partial; updated `app/routes.py` for `quick_note`, `quick_evidence`, `quick_log` to check `request.headers.get("HX-Request")` and return partial HTML when present, RedirectResponse when absent. Preserved cookie and error handling.
- **Task 2:** Added feedback divs (`#quick-note-feedback`, `#quick-evidence-feedback`, `#quick-log-feedback`) and HTMX attributes (`hx-post`, `hx-target`, `hx-swap`, `hx-on::after-request="this.reset()"`) to all three forms in `templates/quick_capture.html`. Kept `action`/`method`/`enctype` for non-JS fallback.

## Verification

- Quick Note, Quick Evidence, Quick Log submit via HTMX; success message appears in-place; form resets
- Non-JS fallback: forms still work with normal POST and redirect
