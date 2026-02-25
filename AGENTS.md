# AGENTS.md

## Cursor Cloud specific instructions

### Services

- **NutriBot** (FastAPI + SQLite): The main web application. See `CLAUDE.md` for full structure.
- **Google Drive scripts**: Optional utility for mirroring Google Drive folders. Requires OAuth `credentials.json` (not needed for NutriBot).

### Running NutriBot

```bash
cd NutriBot
uvicorn main:app --host 127.0.0.1 --port 8000 --reload
```

The app auto-creates its SQLite database at `NutriBot/data/db.sqlite` on first startup. No migrations needed.

### Gotchas

- **FTS5 not available**: The SQLite bundled with the system Python may lack FTS5 support. The app gracefully falls back to `LIKE`-based search. This warning at startup is expected and non-blocking.
- **WeasyPrint system deps**: HTML-to-PDF generation requires `libpango-1.0-0`, `libpangocairo-1.0-0`, `libcairo2`, and `libgdk-pixbuf-2.0-0`. These are installed via the system package manager (not pip). If missing, the app falls back to ReportLab for basic PDF generation.
- **Tesseract OCR**: OCR extraction requires the `tesseract-ocr` system package. If missing, OCR features degrade gracefully.
- **PATH**: pip installs user-level scripts to `~/.local/bin`. Ensure this is on `PATH` (the update script handles this).
- **No test framework or linter** is configured. Validate code via `python3 -m py_compile <file>`.
- **Google Drive credentials** (`credentials.json`, `token.json`) are not committed and are only needed for the Drive scripts, not for NutriBot.
