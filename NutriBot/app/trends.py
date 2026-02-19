"""
Cross-year insights: trends, comparisons, last-year metrics.
Uses existing compute_audit_readiness, compute_missing_evidence, get_missing_requirement_types.
"""
from collections import Counter
from datetime import date, datetime, timedelta
from typing import Any, Optional

from sqlmodel import Session, select

from app.guidance import compute_audit_readiness, get_missing_requirement_types
from app.evidence import compute_missing_evidence
from app.models import EvidenceItem, GeneratedDocument, TaskInstance, TaskTemplate


def compute_task_metrics(db: Session, task: TaskInstance) -> dict[str, Any]:
    """Compute metrics for a task: readiness, evidence_count, missing counts, has_memo, is_overdue, is_completed."""
    readiness = compute_audit_readiness(db, task.id)
    template = db.get(TaskTemplate, task.template_id)
    missing_req, missing_sup = compute_missing_evidence(db, task, template)
    evidence_count = len(list(db.exec(select(EvidenceItem).where(EvidenceItem.task_id == task.id)).all()))
    return {
        "readiness": readiness.get("score", 0),
        "evidence_count": evidence_count,
        "missing_required_count": missing_req,
        "missing_supporting_count": missing_sup,
        "has_memo": readiness.get("has_memo", False),
        "is_overdue": readiness.get("is_overdue", False),
        "is_completed": task.status == "completed",
    }


def _tasks_for_year(db: Session, year: int) -> list[TaskInstance]:
    """Get all tasks for a year with templates attached (single batch query for templates)."""
    tasks = list(db.exec(select(TaskInstance).where(TaskInstance.year == year)).all())
    template_ids = {t.template_id for t in tasks}
    if template_ids:
        tpl_map = {tpl.id: tpl for tpl in db.exec(select(TaskTemplate).where(TaskTemplate.id.in_(template_ids))).all()}
    else:
        tpl_map = {}
    for t in tasks:
        t.template = tpl_map.get(t.template_id)
    return tasks


def _task_in_month(task: TaskInstance, month: int) -> bool:
    """True if task is due in the given month (1-12)."""
    if task.month is not None:
        return task.month == month
    if task.due_date:
        return task.due_date.month == month
    return False


def aggregate_by_category(db: Session, year: int) -> list[dict[str, Any]]:
    """Aggregate metrics by category for a year."""
    tasks = _tasks_for_year(db, year)
    by_cat: dict[str, list[dict]] = {}
    for t in tasks:
        cat = t.template.category if t.template else "Other"
        if cat not in by_cat:
            by_cat[cat] = []
        m = compute_task_metrics(db, t)
        m["task"] = t
        by_cat[cat].append(m)

    result = []
    for cat, metrics_list in by_cat.items():
        n = len(metrics_list)
        completed = sum(1 for m in metrics_list if m["is_completed"])
        missing_req = sum(1 for m in metrics_list if m["missing_required_count"] > 0)
        with_memo = sum(1 for m in metrics_list if m["has_memo"])
        result.append({
            "category": cat,
            "total_tasks": n,
            "completion_rate": round(completed / n * 100, 1) if n else 0,
            "avg_readiness": round(sum(m["readiness"] for m in metrics_list) / n, 1) if n else 0,
            "pct_missing_required": round(missing_req / n * 100, 1) if n else 0,
            "avg_evidence_count": round(sum(m["evidence_count"] for m in metrics_list) / n, 1) if n else 0,
            "memo_coverage_rate": round(with_memo / n * 100, 1) if n else 0,
        })
    return sorted(result, key=lambda x: x["category"])


def aggregate_by_month(db: Session, year: int) -> list[dict[str, Any]]:
    """Aggregate metrics by month (1-12) for a year."""
    tasks = _tasks_for_year(db, year)
    task_ids = {t.id for t in tasks}
    evidence_by_month: dict[int, int] = {m: 0 for m in range(1, 13)}
    for e in db.exec(select(EvidenceItem)).all():
        if e.task_id not in task_ids:
            continue
        if e.added_at:
            if e.added_at.year == year:
                evidence_by_month[e.added_at.month] += 1

    result = []
    for month in range(1, 13):
        month_tasks = [t for t in tasks if _task_in_month(t, month)]
        n = len(month_tasks)
        if n == 0:
            result.append({
                "month": month,
                "tasks_due": 0,
                "completion_rate": 0,
                "avg_readiness": 0,
                "missing_required_rate": 0,
                "evidence_added": evidence_by_month[month],
            })
            continue
        completed = sum(1 for t in month_tasks if t.status == "completed")
        metrics_list = [compute_task_metrics(db, t) for t in month_tasks]
        missing_req = sum(1 for m in metrics_list if m["missing_required_count"] > 0)
        result.append({
            "month": month,
            "tasks_due": n,
            "completion_rate": round(completed / n * 100, 1),
            "avg_readiness": round(sum(m["readiness"] for m in metrics_list) / n, 1),
            "missing_required_rate": round(missing_req / n * 100, 1),
            "evidence_added": evidence_by_month[month],
        })
    return result


def aggregate_by_template(
    db: Session,
    year: int,
    template_id: Optional[int] = None,
) -> dict[str, Any] | list[dict[str, Any]]:
    """Aggregate by template. If template_id given, return single dict; else list of all templates."""
    tasks = _tasks_for_year(db, year)
    if template_id:
        tasks = [t for t in tasks if t.template_id == template_id]
        if not tasks:
            return {
                "template_id": template_id,
                "template_name": "",
                "instance_count": 0,
                "avg_readiness": 0,
                "completion_rate": 0,
                "avg_evidence_count": 0,
                "top_missing_evidence_types": [],
                "instances": [],
            }
        template = db.get(TaskTemplate, template_id)
        metrics_list = [compute_task_metrics(db, t) for t in tasks]
        n = len(tasks)
        completed = sum(1 for t in tasks if t.status == "completed")
        missing_counts: Counter = Counter()
        for t in tasks:
            for et, imp in get_missing_requirement_types(db, t, template):
                missing_counts[(et, imp)] += 1
        top_missing = [f"{et} ({imp})" for (et, imp), _ in missing_counts.most_common(3)]
        instances = []
        for t, m in zip(tasks, metrics_list):
            t.template = template
            instances.append({
                "task": t,
                "readiness": m["readiness"],
                "missing_required": m["missing_required_count"],
                "evidence_count": m["evidence_count"],
                "status": t.status,
            })
        return {
            "template_id": template_id,
            "template_name": template.name if template else "",
            "instance_count": n,
            "avg_readiness": round(sum(m["readiness"] for m in metrics_list) / n, 1),
            "completion_rate": round(completed / n * 100, 1),
            "avg_evidence_count": round(sum(m["evidence_count"] for m in metrics_list) / n, 1),
            "top_missing_evidence_types": top_missing,
            "instances": instances,
        }

    by_tpl: dict[int, list[TaskInstance]] = {}
    for t in tasks:
        tid = t.template_id
        if tid not in by_tpl:
            by_tpl[tid] = []
        by_tpl[tid].append(t)

    result = []
    for tid, tlist in by_tpl.items():
        tpl = db.get(TaskTemplate, tid)
        metrics_list = [compute_task_metrics(db, t) for t in tlist]
        n = len(tlist)
        completed = sum(1 for t in tlist if t.status == "completed")
        missing_counts: Counter = Counter()
        for t in tlist:
            for et, imp in get_missing_requirement_types(db, t, tpl):
                missing_counts[(et, imp)] += 1
        top_missing = [f"{et} ({imp})" for (et, imp), _ in missing_counts.most_common(3)]
        result.append({
            "template_id": tid,
            "template_name": tpl.name if tpl else "",
            "category": tpl.category if tpl else "",
            "instance_count": n,
            "avg_readiness": round(sum(m["readiness"] for m in metrics_list) / n, 1),
            "completion_rate": round(completed / n * 100, 1),
            "avg_evidence_count": round(sum(m["evidence_count"] for m in metrics_list) / n, 1),
            "top_missing_evidence_types": top_missing,
        })
    return sorted(result, key=lambda x: (x.get("category", ""), x.get("template_name", "")))


def retention_workload(db: Session, year: int) -> dict[str, int]:
    """Count review_soon and safe_to_delete items. safe_to_delete filtered by task.year."""
    today = date.today()
    cutoff = today + timedelta(days=60)
    items = list(db.exec(select(EvidenceItem)).all())
    review_soon = 0
    safe_to_delete = 0
    for e in items:
        task = db.get(TaskInstance, e.task_id)
        if not task:
            continue
        if e.review_date and today <= e.review_date <= cutoff and e.disposition != "delete_candidate":
            review_soon += 1
        if (e.keep_until and e.keep_until < today) or e.disposition == "delete_candidate":
            if task.year == year:
                safe_to_delete += 1
    return {"review_soon_count": review_soon, "safe_to_delete_count": safe_to_delete}


def find_baseline_task(db: Session, task: TaskInstance, baseline_year: int) -> Optional[TaskInstance]:
    """Find baseline year's task: same template, baseline_year. If monthly, match month; else nearest due_date."""
    if task.year == baseline_year:
        return task
    if task.month is not None:
        found = db.exec(
            select(TaskInstance).where(
                TaskInstance.template_id == task.template_id,
                TaskInstance.year == baseline_year,
                TaskInstance.month == task.month,
            )
        ).first()
        return found
    candidates = list(db.exec(
        select(TaskInstance).where(
            TaskInstance.template_id == task.template_id,
            TaskInstance.year == baseline_year,
            TaskInstance.month.is_(None),
        )
    ).all())
    if not candidates:
        return None
    if len(candidates) == 1:
        return candidates[0]
    ref_date = task.due_date or date(baseline_year, 6, 15)
    best = min(candidates, key=lambda t: abs((t.due_date or date(baseline_year, 1, 1)) - ref_date))
    return best


def find_last_year_task(db: Session, task: TaskInstance) -> Optional[TaskInstance]:
    """Find last year's task: same template, year-1. If monthly, match month; else nearest due_date."""
    return find_baseline_task(db, task, task.year - 1)


def compare_years(current: dict[str, Any], baseline: dict[str, Any]) -> dict[str, Any]:
    """Add delta fields to current based on baseline."""
    out = dict(current)
    for key in ("completion_rate", "avg_readiness", "pct_missing_required", "avg_evidence_count", "memo_coverage_rate",
                "tasks_due", "missing_required_rate", "evidence_added"):
        if key in current and key in baseline:
            c = current.get(key) or 0
            b = baseline.get(key) or 0
            out[f"{key}_delta"] = round(c - b, 1)
    return out
