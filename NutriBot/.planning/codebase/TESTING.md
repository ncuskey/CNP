# Testing Patterns

**Analysis Date:** 2025-02-18

## Test Framework

**Runner:**
- Not detected — No pytest, unittest, or test runner in `requirements.txt` or project

**Assertion Library:**
- Not applicable

**Run Commands:**
```powershell
.\scripts\restart_and_verify.ps1   # Start server, verify endpoints return 200/302
.\scripts\verify_no_500.ps1 -Port 8000   # Test existing server on port 8000
.\scripts\verify_no_500.ps1              # Uses port 9999 by default (starts fresh)
```

## Test File Organization

**Location:**
- No `tests/` directory
- No `*_test.py`, `test_*.py`, or `*_spec.py` files in the codebase

**Verification Scripts:**
- `scripts/verify_no_500.ps1` — HTTP smoke test; hits endpoints, expects 200 or 302
- `scripts/restart_and_verify.ps1` — Kills process on port 8000, starts uvicorn, runs verify script
- `scripts/verify_500_fixed.ps1` — Additional verification script

**Endpoints Tested by `verify_no_500.ps1`:**
- `/`, `/today`, `/dashboard`, `/review`, `/templates`, `/templates/new`, `/evidence`, `/retention`, `/inbox`

## Test Structure

**Suite Organization:**
- Not applicable — No automated test suites

**Patterns:**
- Manual: Start server, hit endpoints via `Invoke-WebRequest`, check status codes
- On 500: Script captures traceback from response body for debugging

## Mocking

**Framework:** Not applicable

**Patterns:**
- None

## Fixtures and Factories

**Test Data:**
- None — No fixtures or factories

**Location:**
- N/A

## Coverage

**Requirements:** None enforced

**View Coverage:**
- N/A

## Test Types

**Unit Tests:**
- None

**Integration Tests:**
- None — `verify_no_500.ps1` acts as smoke test only

**E2E Tests:**
- Manual — User runs app, tests manually in browser

## Recommendations for Adding Tests

**To add pytest:**
1. Add to `requirements.txt`: `pytest`, `pytest-asyncio`, `httpx`
2. Create `tests/` directory at project root
3. Use `TestClient` from `fastapi.testclient` for route tests
4. Override `get_db` dependency with in-memory SQLite or mock session

**Example route test:**
```python
# tests/test_routes.py
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

def test_today_returns_200():
    response = client.get("/today")
    assert response.status_code == 200

def test_root_redirects():
    response = client.get("/")
    assert response.status_code in (200, 302)
```

**Example with DB override (in-memory):**
```python
from sqlmodel import Session, create_engine, SQLModel
from app.database import get_db
from app import models  # noqa: F401

def override_get_db():
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session

app.dependency_overrides[get_db] = override_get_db
```

**Domain logic (no HTTP):**
- `app/recurrence.py` — `parse_recurrence_rule`, `compute_due_date`, `validate_recurrence_rule` are pure; easy to unit test
- `app/guidance.py` — `compute_audit_readiness` has clear inputs/outputs
- `app/planner.py` — `generate_year_plan` needs DB session; use in-memory SQLite

**Test file naming:**
- `tests/test_routes.py` — Route/HTTP tests
- `tests/test_recurrence.py` — Recurrence engine
- `tests/test_guidance.py` — Audit readiness logic
- `tests/conftest.py` — Pytest fixtures (DB session, client)

---

*Testing analysis: 2025-02-18*
