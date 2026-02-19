"""
Local notification engine. Computes alerts on page load.
No background daemon. No email/cloud.
"""
from datetime import date, datetime, timedelta
from typing import Any

from sqlmodel import Session, select

from app.evidence import compute_missing_evidence
from app.models import EvidenceItem, GeneratedDocument, TaskInstance, TaskTemplate
from app.guidance import compute_audit_readiness, enrich_task_instance


def get_notifications(db: Session, year: int | None = None) -> dict[str, Any]:
    """
    Compute notifications: overdue, missing required, retention review due,
    readiness < 60, safe to delete, review within 30 days.
    """
    today = date.today()
    y = year or today.year

    q = select(TaskInstance).where(TaskInstance.year == y)
    tasks = list(db.exec(q).all())
    for t in tasks:
        enrich_task_instance(t, db)

    overdue = [t for t in tasks if t.due_date and t.due_date < today and t.status != "completed"]
    missing_req = [t for t in tasks if getattr(t, "missing_req", 0) > 0]
    readiness_low = [t for t in tasks if getattr(t, "readiness", {}).get("score", 100) < 60]

    items = list(db.exec(select(EvidenceItem).order_by(EvidenceItem.added_at.desc())).all())
    for e in items:
        e.task = db.get(TaskInstance, e.task_id)
        if e.task:
            object.__setattr__(e.task, "template", db.get(TaskTemplate, e.task.template_id))

    cutoff_review_30 = today + timedelta(days=30)
    safe_to_delete = [e for e in items if (e.keep_until and e.keep_until < today) or e.disposition == "delete_candidate"]
    review_within_30 = [e for e in items if e.review_date and today <= e.review_date <= cutoff_review_30 and e.disposition != "delete_candidate"]

    critical_task_ids = set(t.id for t in overdue + missing_req + readiness_low)
    critical_count = len(critical_task_ids)

    return {
        "overdue": overdue,
        "missing_required": missing_req,
        "readiness_low": readiness_low,
        "safe_to_delete": safe_to_delete,
        "review_within_30": review_within_30,
        "critical_count": critical_count,
        "retention_safe_count": len(safe_to_delete),
        "retention_review_count": len(review_within_30),
    }


def is_export_ready(db: Session, task_id: int) -> bool:
    """True if task has required evidence and memo. Used for audit packet export readiness."""
    task = db.get(TaskInstance, task_id)
    if not task:
        return False
    template = db.get(TaskTemplate, task.template_id)
    missing_req, _ = compute_missing_evidence(db, task, template)
    if missing_req > 0:
        return False
    memo = db.exec(
        select(GeneratedDocument).where(
            GeneratedDocument.task_id == task_id,
            GeneratedDocument.doc_type == "memo",
        )
    ).first()
    has_memo = bool(memo and memo.content_json and memo.content_json.strip() not in ("{}", ""))
    return has_memo


def build_review_data(db: Session, year: int | None = None) -> dict[str, Any]:
    """
    Build data for Review Prep Mode page.
    Sections: critical issues, category breakdown, missing evidence detail, memo status, export readiness.
    """
    today = date.today()
    y = year if isinstance(year, int) else today.year

    q = select(TaskInstance).where(TaskInstance.year == y).order_by(
        TaskInstance.due_date.asc().nullslast()
    )
    tasks = list(db.exec(q).all())
    for t in tasks:
        enrich_task_instance(t, db)
        object.__setattr__(t, "missing_types", [])
        if getattr(t, "template", None):
            from app.guidance import get_missing_requirement_types
            object.__setattr__(t, "missing_types", [et for et, _ in get_missing_requirement_types(db, t, t.template)])
        object.__setattr__(t, "has_memo", getattr(t, "readiness", {}).get("has_memo", False))
        object.__setattr__(t, "export_ready", is_export_ready(db, t.id))

    # Critical: missing required, overdue not completed, readiness < 60
    critical = [t for t in tasks if (t.missing_req > 0) or (t.due_date and t.due_date < today and t.status != "completed") or (t.readiness.get("score", 100) < 60)]

    # Category breakdown
    by_cat: dict[str, dict] = {}
    for t in tasks:
        cat = t.template.category if t.template else "Other"
        if cat not in by_cat:
            by_cat[cat] = {"tasks": [], "total": 0, "missing_req": 0, "overdue": 0, "scores": []}
        by_cat[cat]["tasks"].append(t)
        by_cat[cat]["total"] += 1
        if t.missing_req > 0:
            by_cat[cat]["missing_req"] += 1
        if t.due_date and t.due_date < today and t.status != "completed":
            by_cat[cat]["overdue"] += 1
        by_cat[cat]["scores"].append(t.readiness.get("score", 100))
    for cat, d in by_cat.items():
        d["avg_score"] = round(sum(d["scores"]) / len(d["scores"]), 1) if d["scores"] else 100

    # Missing evidence detail (tasks with missing required)
    missing_detail = [t for t in tasks if t.missing_req > 0]

    # Memo status (tasks missing memo)
    missing_memo = [t for t in tasks if not t.has_memo]

    # Export incomplete (missing required OR missing memo)
    export_incomplete = [t for t in tasks if not t.export_ready]

    return {
        "critical": critical,
        "by_category": by_cat,
        "missing_detail": missing_detail,
        "missing_memo": missing_memo,
        "export_incomplete": export_incomplete,
        "tasks": tasks,
        "year": y,
        "today": today,
    }
