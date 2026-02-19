"""
Local offline full-text search via SQLite FTS5.
Falls back to SQL LIKE if FTS5 unavailable.
"""
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from sqlalchemy import text
from sqlmodel import Session, select

from app.database import DATA_DIR, get_engine
from app.models import (
    EvidenceItem,
    GeneratedDocument,
    NoteLog,
    TaskInstance,
    TaskTemplate,
)

SEARCH_META_PATH = DATA_DIR / "search_meta.json"
FTS_TABLE = "search_index"

log = logging.getLogger(__name__)


def fts5_available(engine) -> bool:
    """Check if SQLite FTS5 is available."""
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT fts5_version()"))
            return True
    except Exception:
        return False


def ensure_search_table(engine) -> bool:
    """Create FTS5 virtual table if not exists. Returns True if FTS5 available."""
    if not fts5_available(engine):
        log.warning("FTS5 not available; search will use LIKE fallback")
        return False
    with engine.connect() as conn:
        conn.execute(text("""
            CREATE VIRTUAL TABLE IF NOT EXISTS search_index USING fts5(
                entity_type, entity_id, task_id, category, title, content,
                tokenize='porter unicode61'
            )
        """))
        conn.commit()
    return True


def _row(entity_type: str, entity_id: int, task_id: Optional[int], category: str, title: str, content: str) -> dict:
    return {
        "entity_type": entity_type,
        "entity_id": entity_id,
        "task_id": task_id,
        "category": category,
        "title": title,
        "content": content,
    }


def rebuild_index(db: Session) -> dict[str, Any]:
    """Rebuild full search index. Returns metadata dict."""
    engine = db.get_bind()
    use_fts = fts5_available(engine)
    counts = {"task": 0, "note": 0, "memo": 0, "evidence": 0, "template": 0}

    # Always compute counts from source tables
    counts["task"] = len(list(db.exec(select(TaskInstance)).all()))
    counts["note"] = len(list(db.exec(select(NoteLog)).all()))
    counts["memo"] = len(list(db.exec(select(GeneratedDocument).where(GeneratedDocument.doc_type == "memo")).all()))
    counts["evidence"] = len(list(db.exec(select(EvidenceItem)).all()))
    counts["template"] = len(list(db.exec(select(TaskTemplate)).all()))

    if use_fts:
        ensure_search_table(engine)
        with engine.connect() as conn:
            conn.execute(text("DELETE FROM search_index"))
            conn.commit()

            # A) TaskInstance
            tasks = list(db.exec(select(TaskInstance)).all())
            for t in tasks:
                template = db.get(TaskTemplate, t.template_id)
                name = template.name if template else "Task"
                title = f"{name} {t.year}" + (f"-{t.month:02d}" if t.month else "")
                category = template.category if template else ""
                content = " ".join(filter(None, [t.notes or "", t.status, str(t.due_date or "")]))
                conn.execute(
                    text("""
                        INSERT INTO search_index (entity_type, entity_id, task_id, category, title, content)
                        VALUES (:et, :eid, :tid, :cat, :title, :content)
                    """),
                    {"et": "task", "eid": t.id, "tid": t.id, "cat": category, "title": title, "content": content},
                )

            # B) NoteLog
            notes = list(db.exec(select(NoteLog)).all())
            for n in notes:
                conn.execute(
                    text("""
                        INSERT INTO search_index (entity_type, entity_id, task_id, category, title, content)
                        VALUES ('note', :eid, :tid, '', '', :content)
                    """),
                    {"eid": n.id, "tid": n.task_id, "content": n.content or ""},
                )

            # C) GeneratedDocument (memo only)
            memos = list(db.exec(
                select(GeneratedDocument).where(GeneratedDocument.doc_type == "memo")
            ).all())
            for m in memos:
                try:
                    d = json.loads(m.content_json or "{}")
                    content = " ".join(str(d.get(k, "")) for k in ("context", "actions_taken", "decision", "risks"))
                except json.JSONDecodeError:
                    content = m.content_json or ""
                conn.execute(
                    text("""
                        INSERT INTO search_index (entity_type, entity_id, task_id, category, title, content)
                        VALUES ('memo', :eid, :tid, '', :title, :content)
                    """),
                    {"eid": m.id, "tid": m.task_id or 0, "title": m.title or "", "content": content},
                )

            # D) EvidenceItem
            items = list(db.exec(select(EvidenceItem)).all())
            for e in items:
                content = " ".join(filter(None, [e.description or "", e.original_filename or "", e.stored_filename or ""]))
                conn.execute(
                    text("""
                        INSERT INTO search_index (entity_type, entity_id, task_id, category, title, content)
                        VALUES ('evidence', :eid, :tid, :cat, :title, :content)
                    """),
                    {"eid": e.id, "tid": e.task_id, "cat": e.category or "", "title": e.original_filename or "", "content": content},
                )

            # E) TaskTemplate
            templates = list(db.exec(select(TaskTemplate)).all())
            for t in templates:
                content = " ".join(filter(None, [t.category or "", t.recurrence_rule or ""]))
                conn.execute(
                    text("""
                        INSERT INTO search_index (entity_type, entity_id, task_id, category, title, content)
                        VALUES ('template', :eid, NULL, :cat, :title, :content)
                    """),
                    {"eid": t.id, "cat": t.category or "", "title": t.name or "", "content": content},
                )

            conn.commit()

    meta = {
        "last_indexed": datetime.utcnow().isoformat(),
        "counts": counts,
        "fts5_available": use_fts,
    }
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(SEARCH_META_PATH, "w") as f:
        json.dump(meta, f, indent=2)
    return meta


def _make_snippet(text: str, query: str, max_len: int = 120) -> str:
    """Extract snippet around first match. Simple truncation + bold query."""
    if not text:
        return ""
    q_lower = query.lower()
    text_lower = text.lower()
    pos = text_lower.find(q_lower)
    if pos < 0:
        return (text[:max_len] + "…") if len(text) > max_len else text
    start = max(0, pos - 40)
    end = min(len(text), pos + len(query) + 80)
    snippet = text[start:end]
    if start > 0:
        snippet = "…" + snippet
    if end < len(text):
        snippet = snippet + "…"
    # Bold the match (will be escaped in template)
    if q_lower in snippet.lower():
        idx = snippet.lower().index(q_lower)
        match = snippet[idx : idx + len(query)]
        snippet = snippet[:idx] + match + snippet[idx + len(query) :]
    return snippet


def search(
    db: Session,
    q: str,
    year: Optional[int] = None,
    category: Optional[str] = None,
    entity: Optional[str] = None,
) -> list[dict[str, Any]]:
    """Search index. Returns list of {entity_type, entity_id, task_id, category, title, snippet}."""
    q = (q or "").strip()
    results: list[dict[str, Any]] = []

    engine = db.get_bind()
    use_fts = fts5_available(engine)

    if use_fts:
        ensure_search_table(engine)
        if not q:
            return []

        with engine.connect() as conn:
            rows: list = []
            try:
                match_term = q if " " not in q else f'"{q}"'
                rows = conn.execute(
                    text(f"""
                        SELECT entity_type, entity_id, task_id, category, title, content
                        FROM {FTS_TABLE}
                        WHERE {FTS_TABLE} MATCH :query
                    """),
                    {"query": match_term},
                ).fetchall()
            except Exception as e:
                log.warning("FTS5 search failed: %s", e)
                use_fts = False

        if use_fts:
            for row in rows:
                et, eid, tid, cat, title, content = row
                if year is not None and tid:
                    task = db.get(TaskInstance, tid)
                    if task and task.year != year:
                        continue
                if category and cat != category:
                    continue
                if entity and et != entity:
                    continue
                snippet = _make_snippet(content or title or "", q)
                results.append({
                    "entity_type": et,
                    "entity_id": eid,
                    "task_id": tid,
                    "category": cat or "",
                    "title": title or "",
                    "snippet": snippet,
                })
            return results

    # LIKE fallback
    pattern = f"%{q}%" if q else "%"
    tasks = list(db.exec(select(TaskInstance)).all())
    for t in tasks:
        template = db.get(TaskTemplate, t.template_id)
        if year and t.year != year:
            continue
        name = template.name if template else "Task"
        title = f"{name} {t.year}" + (f"-{t.month:02d}" if t.month else "")
        cat = template.category if template else ""
        if category and cat != category:
            continue
        if entity and entity != "task":
            continue
        content = " ".join(filter(None, [t.notes or "", t.status, str(t.due_date or "")]))
        if q.lower() in (title + " " + content + " " + cat).lower():
            results.append(_row("task", t.id, t.id, cat, title, content))
            results[-1]["snippet"] = _make_snippet(content or title, q)

    notes = list(db.exec(select(NoteLog)).all())
    for n in notes:
        task = db.get(TaskInstance, n.task_id)
        if year and task and task.year != year:
            continue
        if entity and entity != "note":
            continue
        if q.lower() in (n.content or "").lower():
            results.append(_row("note", n.id, n.task_id, "", "", n.content or ""))
            results[-1]["snippet"] = _make_snippet(n.content or "", q)

    memos = list(db.exec(select(GeneratedDocument).where(GeneratedDocument.doc_type == "memo")).all())
    for m in memos:
        task = db.get(TaskInstance, m.task_id) if m.task_id else None
        if year and task and task.year != year:
            continue
        if entity and entity != "memo":
            continue
        try:
            d = json.loads(m.content_json or "{}")
            content = " ".join(str(d.get(k, "")) for k in ("context", "actions_taken", "decision", "risks"))
        except json.JSONDecodeError:
            content = m.content_json or ""
        if q.lower() in (content + " " + (m.title or "")).lower():
            results.append(_row("memo", m.id, m.task_id or 0, "", m.title or "", content))
            results[-1]["snippet"] = _make_snippet(content or m.title or "", q)

    items = list(db.exec(select(EvidenceItem)).all())
    for e in items:
        task = db.get(TaskInstance, e.task_id)
        if year and task and task.year != year:
            continue
        if category and (e.category or "") != category:
            continue
        if entity and entity != "evidence":
            continue
        content = " ".join(filter(None, [e.description or "", e.original_filename or "", e.stored_filename or ""]))
        if q.lower() in (content + " " + (e.original_filename or "")).lower():
            results.append(_row("evidence", e.id, e.task_id, e.category or "", e.original_filename or "", content))
            results[-1]["snippet"] = _make_snippet(content or e.original_filename or "", q)

    templates = list(db.exec(select(TaskTemplate)).all())
    for t in templates:
        if entity and entity != "template":
            continue
        if category and (t.category or "") != category:
            continue
        content = " ".join(filter(None, [t.category or "", t.recurrence_rule or ""]))
        if q.lower() in ((t.name or "") + " " + content).lower():
            results.append(_row("template", t.id, None, t.category or "", t.name or "", content))
            results[-1]["snippet"] = _make_snippet(content or t.name or "", q)

    return results


def load_search_meta() -> dict[str, Any]:
    """Load search metadata from JSON file."""
    if not SEARCH_META_PATH.exists():
        return {"last_indexed": None, "counts": {}, "fts5_available": fts5_available(get_engine())}
    try:
        with open(SEARCH_META_PATH) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {"last_indexed": None, "counts": {}, "fts5_available": False}
