"""
Claims trend engine: monthly claim data aggregation and participation metrics.
"""
from datetime import date
from typing import Any

from sqlmodel import Session, select

from app.models import TaskDataField, TaskDataValue, TaskInstance, TaskTemplate


def find_monthly_claim_template(db: Session) -> TaskTemplate | None:
    """Find Monthly Claim Submission template."""
    return db.exec(
        select(TaskTemplate).where(
            TaskTemplate.name == "Monthly Claim Submission",
            TaskTemplate.category == "Claims",
        )
    ).first()


def get_monthly_claim_data(db: Session, year: int) -> list[dict[str, Any]]:
    """Returns list of months with totals: {month, year, reimbursement, meals, adp, ...}."""
    tpl = find_monthly_claim_template(db)
    if not tpl:
        return []

    instances = list(db.exec(
        select(TaskInstance).where(
            TaskInstance.template_id == tpl.id,
            TaskInstance.year == year,
        ).order_by(TaskInstance.month.asc().nullslast())
    ).all())

    result = []
    for inst in instances:
        vals = db.exec(
            select(TaskDataValue).where(TaskDataValue.task_id == inst.id)
        ).all()
        v = {x.field_key: x.value_text for x in vals}

        def _float(k: str) -> float:
            try:
                v_f = float(v.get(k) or 0)
                return v_f if 0 <= v_f <= 1_000_000_000 else 0.0
            except (ValueError, TypeError):
                return 0.0

        def _int(k: str) -> int:
            try:
                return int(float(v.get(k) or 0))
            except (ValueError, TypeError):
                return 0

        reimbursement = _float("total_reimbursement")
        free = _int("free_meals")
        reduced = _int("reduced_meals")
        paid = _int("paid_meals")
        breakfast = _int("breakfast_meals")
        adp = _int("adp")
        total_meals = free + reduced + paid

        result.append({
            "month": inst.month,
            "year": year,
            "task_id": inst.id,
            "reimbursement": reimbursement,
            "free_meals": free,
            "reduced_meals": reduced,
            "paid_meals": paid,
            "breakfast_meals": breakfast,
            "total_meals": total_meals,
            "adp": adp,
            "claim_submitted_date": v.get("claim_submitted_date") or "",
            "claim_approved_date": v.get("claim_approved_date") or "",
            "adjustments_required": (v.get("adjustments_required") or "").strip() in ("1", "true", "yes"),
        })
    return result


def compute_participation_metrics(db: Session, year: int) -> dict[str, Any]:
    """Meals total, reimbursement per meal, participation trend."""
    data = get_monthly_claim_data(db, year)
    total_reimbursement = sum(d["reimbursement"] for d in data)
    total_meals = sum(d["total_meals"] for d in data)
    adps = [d["adp"] for d in data if d["adp"] > 0]
    avg_adp = sum(adps) / len(adps) if adps else 0
    reimbursement_per_meal = total_reimbursement / total_meals if total_meals else 0
    return {
        "total_reimbursement": total_reimbursement,
        "total_meals": total_meals,
        "avg_adp": round(avg_adp, 1),
        "reimbursement_per_meal": round(reimbursement_per_meal, 2),
        "months_with_data": len([d for d in data if d["total_meals"] > 0 or d["reimbursement"] > 0]),
    }


def compare_to_last_year(db: Session, year: int) -> dict[str, Any]:
    """Compare current year to last year."""
    this_year = get_monthly_claim_data(db, year)
    last_year = get_monthly_claim_data(db, year - 1)
    this_metrics = compute_participation_metrics(db, year)
    last_metrics = compute_participation_metrics(db, year - 1)

    reimb_diff = this_metrics["total_reimbursement"] - last_metrics["total_reimbursement"]
    meals_diff = this_metrics["total_meals"] - last_metrics["total_meals"]
    reimb_pct = (reimb_diff / last_metrics["total_reimbursement"] * 100) if last_metrics["total_reimbursement"] else 0
    meals_pct = (meals_diff / last_metrics["total_meals"] * 100) if last_metrics["total_meals"] else 0

    return {
        "this_year": this_metrics,
        "last_year": last_metrics,
        "reimbursement_diff": reimb_diff,
        "reimbursement_pct": round(reimb_pct, 1),
        "meals_diff": meals_diff,
        "meals_pct": round(meals_pct, 1),
        "this_data": this_year,
        "last_data": last_year,
    }
