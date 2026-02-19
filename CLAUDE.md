# CLAUDE.md — AI Assistant Guide for CNP

This file provides AI assistants (Claude Code and similar tools) with the context, conventions, and workflows needed to work effectively in this repository.

---

## Repository Overview

| Field | Value |
|---|---|
| **Repository** | `ncuskey/CNP` |
| **Status** | Active |
| **Remote** | `http://local_proxy@127.0.0.1:44727/git/ncuskey/CNP` |

> **Note:** This repository was created on 2026-02-19. See sections below for current structure and conventions.

---

## Codebase Structure

```
CNP/
├── CLAUDE.md              # This file
├── requirements.txt       # Python dependencies
└── src/
    └── google_drive.py    # GoogleDriveClient — list, download, upload via Drive API v3
```

### `src/google_drive.py`

`GoogleDriveClient` authenticates with Google Drive using OAuth 2.0 and exposes:

| Method | Description |
|---|---|
| `list_files(query, page_size, fields)` | List/search files; auto-paginates |
| `download_file(file_id)` | Download binary content of a regular file |
| `export_file(file_id, mime_type)` | Export a Google Workspace doc (Docs/Sheets/Slides) |
| `upload_file(local_path, name, mime_type, parent_folder_id)` | Upload a new file |
| `update_file(file_id, local_path, mime_type)` | Replace content of an existing file |

**Authentication setup:**
1. Create a project in the [Google Cloud Console](https://console.cloud.google.com/).
2. Enable the **Google Drive API**.
3. Create **OAuth 2.0 Client ID** credentials (Desktop app type).
4. Download the client secrets JSON and save it as `credentials.json` in the project root.
5. On first run, a browser window will open for user consent. The granted token is cached in `token.json`.

---

## Development Workflow

### Branch Naming Convention

All AI-assisted feature branches must follow this pattern:

```
claude/<task-slug>-<session-id>
```

Example: `claude/claude-md-mlto3q4axb089pj6-PoJFX`

- The branch name **must** start with `claude/` and end with the matching session ID.
- Pushing to branches that do not match this pattern will result in a `403` error.

### Daily Workflow

```bash
# 1. Start from the correct branch
git checkout claude/<branch-name>

# 2. Make changes, then stage and commit
git add <specific-files>
git commit -m "Short imperative description of change"

# 3. Push to remote
git push -u origin claude/<branch-name>
```

### Commit Message Style

- Use the **imperative mood** in the subject line: `Add`, `Fix`, `Remove`, `Update`, `Refactor`.
- Keep the subject line under 72 characters.
- Add a blank line + body paragraph for non-trivial changes explaining *why*, not *what*.
- Do not use emoji unless the project style explicitly requires it.

Example:
```
Add user authentication module

Implements JWT-based login and logout endpoints. Chose JWT over
session cookies to support stateless horizontal scaling.
```

### Git Push Retry Policy

If `git push` fails due to a network error, retry with exponential backoff:

| Attempt | Wait before retry |
|---|---|
| 1st retry | 2 s |
| 2nd retry | 4 s |
| 3rd retry | 8 s |
| 4th retry | 16 s |

Do **not** retry on `403` errors — those indicate a permissions or branch-name issue.

### What NOT to Do

- Never push to `main` or `master` directly.
- Never use `git push --force` unless explicitly instructed.
- Never commit secrets, `.env` files, or credentials.
- Never use `git add -A` or `git add .` blindly — stage only the intended files.
- Never amend a previous commit after a pre-commit hook failure; create a new commit instead.

---

## Testing

_No test framework has been configured yet. Update this section when tests are added._

Install dependencies before running anything:

```bash
pip install -r requirements.txt
```

---

## Code Conventions

**Language:** Python 3.11+

General rules that apply regardless of language:
- Prefer editing existing files over creating new ones.
- Avoid over-engineering: implement only what the current task requires.
- Do not add docstrings, comments, or type annotations to code that was not changed.
- Delete unused code rather than commenting it out or adding `_unused` suffixes.
- Do not introduce backwards-compatibility shims; change the code directly.

---

## Security

- Validate inputs only at system boundaries (user input, external APIs).
- Do not introduce command injection, XSS, SQL injection, or other OWASP Top 10 vulnerabilities.
- If insecure code is noticed during a task, fix it immediately.
- Treat any file containing secrets as out-of-bounds for commits.

---

## Updating This File

When significant project changes occur, update the relevant sections:
- New directory structure → update **Codebase Structure**
- New test runner or linter → update **Testing**
- New language or framework → update **Code Conventions**
- Change in branch strategy → update **Development Workflow**

Keep this file current so AI assistants always have accurate context.
