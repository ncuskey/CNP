# Debug: Main page 500, /today 404

## Symptoms
- **Expected:** Root `/` redirects to `/today`; `/today` shows Daily Command Center (200)
- **Actual:** Main page returns 500; `/today` returns 404
- **Reproduction:** Run `python app.py`, then visit http://127.0.0.1:8000/ or http://127.0.0.1:8000/today

## Investigation

### Routes registered
- Direct import: `from main import app` → 61 routes, including `/` and `/today` ✓
- Running server (port 8000 via `python app.py`): OpenAPI shows only ~10 routes; `/today` missing ✗

### Server comparison
| Start command | Port | /today |
|---------------|------|--------|
| `python app.py` | 8000 | 404 |
| `python -m uvicorn main:app` | 8001 | 200 |
| `python -m uvicorn main:app --reload` | 8002 | 200 |

### Root cause
When the app is started via `python app.py`, which calls `uvicorn.run("main:app", reload=True)`, the uvicorn reloader subprocess loads the application with a different module resolution context. The `main` module resolves to a different (older/cached) app instance that lacks the Phase 6 routes (`/today`, `/review`, `/dashboard`, etc.).

When started via `python -m uvicorn main:app`, module resolution is correct and all routes load.

## Fix (applied)
Change `app.py` to invoke uvicorn as a subprocess using `python -m uvicorn` instead of `uvicorn.run()`. This ensures correct module resolution when the reloader spawns.

```python
# Before: uvicorn.run("main:app", ...)  → broken module resolution
# After:  subprocess.run([sys.executable, "-m", "uvicorn", "main:app", ...])
```

**To verify:** Stop any running server (Ctrl+C), then run `python app.py` again. Visit http://127.0.0.1:8000/ — it should redirect to /today and load the Daily Command Center.
