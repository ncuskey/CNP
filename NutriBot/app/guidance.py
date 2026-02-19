"""
Compliance Assistant v2: deterministic guidance, audit readiness, memo drafts.
No LLM, no internet. Local-first.
"""
from datetime import date, datetime, timedelta
from typing import Any, Optional

from sqlmodel import Session, select

from app.evidence import compute_missing_evidence, get_evidence_types, get_task_display_name
from app.models import (
    ChecklistItem,
    EvidenceItem,
    EvidenceRequirement,
    GeneratedDocument,
    NoteLog,
    RetentionRule,
    TaskInstance,
    TaskTemplate,
)


def enrich_task_instance(inst: TaskInstance, db: Session, include_readiness: bool = True) -> None:
    """Attach template, missing_req, missing_sup, readiness (runtime attrs) for Jinja templates."""
    template = db.get(TaskTemplate, inst.template_id)
    mr, ms = compute_missing_evidence(db, inst, template)
    object.__setattr__(inst, "template", template)
    object.__setattr__(inst, "missing_req", mr)
    object.__setattr__(inst, "missing_sup", ms)
    if include_readiness:
        object.__setattr__(inst, "readiness", compute_audit_readiness(db, inst.id))


def compute_audit_readiness(db: Session, task_id: int) -> dict[str, Any]:
    """
    Compute audit readiness score 0-100 and reasons.
    Heuristic (documented):
    - Start at 100
    - Subtract 40 if missing any REQUIRED evidence
    - Subtract 15 if no evidence at all
    - Subtract 10 if overdue and not completed
    - Subtract 10 if memo missing (no memo doc or empty content)
    - Subtract 5 if checklist < 80% completed
    - Clamp 0-100
    """
    task = db.get(TaskInstance, task_id)
    if not task:
        return {"score": 0, "reasons": ["Task not found"]}
    template = db.get(TaskTemplate, task.template_id)
    missing_req, missing_sup = compute_missing_evidence(db, task, template)

    score = 100
    reasons: list[str] = []

    # Required evidence
    if missing_req > 0:
        score -= 40
        reasons.append(f"Missing {missing_req} required evidence type(s)")
    # No evidence at all
    evidence_count = db.exec(select(EvidenceItem).where(EvidenceItem.task_id == task_id)).all()
    if not list(evidence_count):
        score -= 15
        reasons.append("No evidence attached")
    # Overdue and not completed
    today = date.today()
    is_overdue = bool(task.due_date and task.due_date < today and task.status != "completed")
    if is_overdue:
        score -= 10
        reasons.append("Overdue and not completed")
    # Memo missing
    memo_doc = db.exec(
        select(GeneratedDocument).where(
            GeneratedDocument.task_id == task_id,
            GeneratedDocument.doc_type == "memo",
        )
    ).first()
    has_memo = bool(memo_doc and memo_doc.content_json and memo_doc.content_json.strip() not in ("{}", ""))
    if not has_memo:
        score -= 10
        reasons.append("Compliance memo not saved or empty")
    # Checklist < 80%
    checklist = list(db.exec(
        select(ChecklistItem).where(ChecklistItem.task_id == task_id)
    ).all())
    checklist_total = len(checklist)
    checklist_completed = sum(1 for c in checklist if c.completed)
    checklist_pct = (checklist_completed / checklist_total * 100) if checklist_total else 100
    if checklist_total > 0 and checklist_pct < 80:
        score -= 5
        reasons.append(f"Checklist {checklist_completed}/{checklist_total} ({int(checklist_pct)}%) completed")

    score = max(0, min(100, score))
    if score >= 80 and not reasons:
        reasons.append("Task appears audit-ready")
    elif score >= 60 and reasons:
        reasons.insert(0, "Some improvements needed")
    elif score < 60:
        reasons.insert(0, "Audit risk — address items below")

    return {
        "score": score,
        "reasons": reasons,
        "required_missing_count": missing_req,
        "supporting_missing_count": missing_sup,
        "checklist_completion_pct": round(checklist_pct, 1) if checklist_total else 100,
        "checklist_completed": checklist_completed,
        "checklist_total": checklist_total,
        "has_memo": has_memo,
        "is_overdue": is_overdue,
    }


def generate_memo_draft(
    db: Session, task_id: int, include_more_detail: bool = False
) -> dict[str, str]:
    """
    Generate a compliance memo draft from task data.
    Returns {context, actions_taken, decision, risks} for memo form.
    """
    task = db.get(TaskInstance, task_id)
    if not task:
        return {"context": "", "actions_taken": "", "decision": "", "risks": "", "date": date.today().isoformat()}
    template = db.get(TaskTemplate, task.template_id)
    missing_req, missing_sup = compute_missing_evidence(db, task, template)
    display_name = get_task_display_name(task, template)

    # Context
    context_parts = [
        f"Task: {template.name if template else 'Task'} ({display_name})",
        f"Category: {template.category if template else 'Other'}",
        f"Due date: {task.due_date or 'Not set'}",
    ]
    if missing_req > 0 or missing_sup > 0:
        context_parts.append(f"Missing evidence: {missing_req} required, {missing_sup} supporting")
    context = "\n".join(context_parts)

    # Actions taken
    checklist = list(db.exec(
        select(ChecklistItem).where(ChecklistItem.task_id == task_id).order_by(ChecklistItem.sort_order)
    ).all())
    notes = list(db.exec(
        select(NoteLog).where(NoteLog.task_id == task_id).order_by(NoteLog.created_at.desc())
    ).all())
    evidence = list(db.exec(
        select(EvidenceItem).where(EvidenceItem.task_id == task_id).order_by(EvidenceItem.added_at.desc())
    ).all())

    actions = []
    for c in checklist:
        if c.completed:
            actions.append(f"✓ {c.text}")
    for n in notes:
        content = n.content[:300] + "..." if len(n.content) > 300 and not include_more_detail else n.content
        actions.append(f"[{n.created_at.strftime('%Y-%m-%d')}] {content}")
    for e in evidence:
        types_str = ", ".join(get_evidence_types(e))
        actions.append(f"Evidence: {types_str} — {e.original_filename}")
    actions_taken = "\n".join(actions) if actions else "No actions recorded yet."

    # Decision/Outcome
    if task.status == "completed":
        completed_date = task.updated_at.strftime("%Y-%m-%d") if task.updated_at else "N/A"
        decision = f"Task marked completed on {completed_date}."
    else:
        decision = "In progress."

    # Risks/Follow-ups
    risks = []
    if missing_req > 0:
        reqs = list(db.exec(
            select(EvidenceRequirement).where(
                EvidenceRequirement.template_id == task.template_id,
                EvidenceRequirement.importance == "required",
            )
        ).all())
        items = list(db.exec(select(EvidenceItem).where(EvidenceItem.task_id == task_id)).all())
        have_types = set()
        for e in items:
            have_types.update(get_evidence_types(e))
        for r in reqs:
            if r.evidence_type not in have_types:
                risks.append(f"Attach required {r.evidence_type} evidence")
    if task.due_date and task.due_date < date.today() and task.status != "completed":
        risks.append("Task is overdue — complete and document.")
    risks_text = "\n".join(risks) if risks else "None identified."

    return {
        "context": context,
        "actions_taken": actions_taken,
        "decision": decision,
        "risks": risks_text,
        "date": date.today().isoformat(),
    }


def task_next_steps(db: Session, task_id: int) -> list[str]:
    """Return actionable suggestions for the task."""
    task = db.get(TaskInstance, task_id)
    if not task:
        return ["Task not found"]
    template = db.get(TaskTemplate, task.template_id)
    missing_req, missing_sup = compute_missing_evidence(db, task, template)

    steps = []
    today = date.today()

    if task.due_date and task.due_date < today and task.status != "completed":
        steps.append("Complete this overdue task or update due date.")

    if missing_req > 0:
        reqs = list(db.exec(
            select(EvidenceRequirement).where(
                EvidenceRequirement.template_id == task.template_id,
                EvidenceRequirement.importance == "required",
            )
        ).all())
        items = list(db.exec(select(EvidenceItem).where(EvidenceItem.task_id == task_id)).all())
        have_types = set()
        for e in items:
            have_types.update(get_evidence_types(e))
        for r in reqs:
            if r.evidence_type not in have_types:
                steps.append(f"Attach required evidence: {r.evidence_type}")

    if missing_sup > 0:
        steps.append(f"Add {missing_sup} supporting evidence type(s) to strengthen audit readiness.")

    memo_doc = db.exec(
        select(GeneratedDocument).where(
            GeneratedDocument.task_id == task_id,
            GeneratedDocument.doc_type == "memo",
        )
    ).first()
    if not memo_doc or not (memo_doc.content_json and memo_doc.content_json.strip() not in ("{}", "")):
        steps.append("Draft and save a compliance memo.")

    checklist = list(db.exec(select(ChecklistItem).where(ChecklistItem.task_id == task_id)).all())
    completed = sum(1 for c in checklist if c.completed)
    if checklist and completed < len(checklist):
        steps.append(f"Complete remaining checklist items ({completed}/{len(checklist)} done).")

    if not steps:
        steps.append("Task appears on track. Keep evidence current and review retention dates.")

    return steps


def retention_explain(db: Session, evidence_item_id: int) -> dict[str, Any]:
    """
    Explain why an evidence item has its retention status.
    Returns: matched_rule, disposition_rationale, keep_until_logic, suggested_edits.
    """
    item = db.get(EvidenceItem, evidence_item_id)
    if not item:
        return {"error": "Evidence not found"}

    task = db.get(TaskInstance, item.task_id)
    if task:
        task.template = db.get(TaskTemplate, task.template_id)
    result: dict[str, Any] = {
        "item": item,
        "task": task,
        "matched_rule": None,
        "disposition_rationale": "",
        "keep_until_logic": "",
        "review_date_logic": "",
        "suggested_edits": [],
    }

    rule = db.get(RetentionRule, item.retention_rule_id) if item.retention_rule_id else None
    result["matched_rule"] = rule

    today = date.today()

    # Find best matching rule if none linked (e.g. old evidence)
    if not rule and item.category:
        rules = list(db.exec(select(RetentionRule).where(RetentionRule.category == item.category)).all())
        best = None
        best_score = -1
        for r in rules:
            score = 0
            if r.evidence_type and r.evidence_type in get_evidence_types(item):
                score += 2
            elif not r.evidence_type:
                score += 1
            if r.importance and r.importance == item.importance:
                score += 2
            elif not r.importance:
                score += 1
            if score > best_score:
                best_score = score
                best = r
        result["matched_rule"] = best
        rule = best

    if rule:
        result["keep_until_logic"] = (
            f"Rule '{rule.description}' (category={rule.category})"
            + (f", type={rule.evidence_type}" if rule.evidence_type else ", any type")
            + (f", importance={rule.importance}" if rule.importance else "")
        )
        if rule.is_permanent:
            result["keep_until_logic"] += " → Permanent retention."
            result["disposition_rationale"] = "Marked permanent in retention rules."
        elif rule.years_to_keep:
            result["keep_until_logic"] += f" → Keep {rule.years_to_keep} years."
            if item.keep_until:
                result["review_date_logic"] = f"Review 60 days before {item.keep_until}."
            result["disposition_rationale"] = (
                f"Keep until {item.keep_until}. Review by {item.review_date}."
                if item.keep_until and item.review_date
                else "Dates applied from rule."
            )
    else:
        result["keep_until_logic"] = "No retention rule matched this category."
        result["disposition_rationale"] = "Add a RetentionRule for this category to get automatic dates."

    # Disposition rationale
    if item.disposition == "delete_candidate":
        result["disposition_rationale"] += " Manually marked as delete candidate."
    elif item.keep_until and item.keep_until < today:
        result["disposition_rationale"] += " Retention period passed — safe to delete per rule."
    elif item.review_date and today <= item.review_date <= today + timedelta(days=60):
        result["disposition_rationale"] += " Within review window — decide keep or delete."

    result["suggested_edits"] = [
        "Edit RetentionRule in database to change years_to_keep or is_permanent.",
        "Use disposition form to mark keep/review/delete_candidate.",
    ]

    return result


def get_missing_requirement_types(
    db: Session, task: TaskInstance, template: Optional[TaskTemplate]
) -> list[tuple[str, str]]:
    """Return list of (evidence_type, importance) that are missing."""
    if not template:
        return []
    reqs = list(db.exec(
        select(EvidenceRequirement).where(EvidenceRequirement.template_id == template.id)
    ).all())
    items = list(db.exec(select(EvidenceItem).where(EvidenceItem.task_id == task.id)).all())
    have = set()
    for e in items:
        for et in get_evidence_types(e):
            have.add((et, e.importance))
    missing = []
    for r in reqs:
        if r.importance == "required":
            if (r.evidence_type, "required") not in have:
                missing.append((r.evidence_type, "required"))
        elif r.importance == "supporting":
            if (r.evidence_type, "supporting") not in have and (r.evidence_type, "required") not in have:
                missing.append((r.evidence_type, "supporting"))
    return missing
