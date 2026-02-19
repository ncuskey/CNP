# Debug: HTTP 500 still

## ROOT CAUSE FOUND

**Error:** `sqlite3.ProgrammingError: Error binding parameter 1: type 'Query' is not supported`  
**Parameters:** `(Query(None),)`

**Cause:** Routes with `year: Optional[int] = Query(None)` use `year or today.year`. When the handler is invoked without FastAPI's dependency injection (e.g. direct call, or edge case in reloader), `year` can be the `Query` object itself instead of `None`. Then `year_filter = year or today.year` yields `Query(None)`, which gets passed to SQL and causes the 500.

## Fix applied
Replaced `year or today.year` with `year if isinstance(year, int) else today.year` (and equivalent for `month`) in:
- `dashboard`
- `review_page` → `build_review_data`
- `calendar_view`
- `assistant_page`
- `export_page`
- `retention_page` (year, category, evidence_type filters)
- `build_review_data` in notifications.py
