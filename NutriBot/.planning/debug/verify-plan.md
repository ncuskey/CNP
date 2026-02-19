# Verification Plan: 500 Fixed

## Root cause (confirmed)
- Port 8000 was serving **old code** (wrong working directory or stale process)
- Old code: `/` = dashboard (500), `/today` = 404
- Fix: Run server from project root so `main:app` loads correctly

## Verification (run from project root)

### Option A: Full restart + verify
```powershell
.\scripts\restart_and_verify.ps1
```
- Kills any process on port 8000
- Starts server with correct working directory
- Runs 8-endpoint test
- **Expected:** "VERIFIED: All endpoints return 200 or 302"

### Option B: Test existing server
```powershell
.\scripts\verify_no_500.ps1 -Port 8000
```
- Tests whatever is running on 8000
- If 500: shows traceback (if debug handler active)

### Option C: Manual
1. Stop server (Ctrl+C)
2. `cd c:\Users\ncuskey\Desktop\NutriBot`
3. `python -m uvicorn main:app --reload`
4. Visit http://127.0.0.1:8000/ — should redirect to /today, show Daily Command Center

## Verified (2024-02-18)
- `restart_and_verify.ps1` run twice: both passed
- All 8 endpoints: /, /today, /dashboard, /review, /templates, /evidence, /retention, /inbox → 200 or 302
