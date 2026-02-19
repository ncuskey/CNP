"""
FastAPI routes for BCSD Child Nutrition Ops Console.
"""
import json
import calendar
import csv
import io
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, Response, StreamingResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, select

from app.database import get_engine, init_db, INBOX_DIR, VAULT_DIR, BACKUPS_DIR
from app.evidence import (
    apply_retention_rule,
    compute_missing_evidence,
    delete_inbox_file,
    get_evidence_types,
    get_orphaned_evidence,
    get_orphaned_files,
    get_task_display_name,
    list_inbox_files,
    move_orphaned_to_untracked,
    move_to_trash,
    seed_retention_rules,
    store_evidence_file,
    store_evidence_from_inbox,
)
from app.models import (
    ChecklistItem,
    EvidenceItem,
    EvidenceRequirement,
    NoteLog,
    RetentionRule,
    TaskDataField,
    TaskDataValue,
    TaskInstance,
    TaskTemplate,
    EVIDENCE_TYPES,
    IMPORTANCE_LEVELS,
)
from app.documents import (
    build_cover_sheet_context,
    build_evidence_index_context,
    build_memo_context,
    get_or_create_memo_doc,
    load_memo_content,
    save_memo_content,
    write_pdf_and_register,
)
from app.pdf_engine import get_pdf_backend, is_pdf_available
from app.guidance import (
    compute_audit_readiness,
    enrich_task_instance,
    generate_memo_draft,
    get_missing_requirement_types,
    retention_explain,
    task_next_steps,
)
from app.planner import generate_year_plan
from app.recurrence import validate_recurrence_rule
from app.backup import create_backup, list_backups, restore_backup
from app.notifications import build_review_data, get_notifications, is_export_ready
from app.search_index import load_search_meta, rebuild_index, search
from app.presets import install_pack, list_available_packs, load_preset_pack, preview_install
from app.history import build_comparison_pairs, build_execution_records
from app.trends import (
    aggregate_by_category,
    aggregate_by_month,
    aggregate_by_template,
    compare_years,
    compute_task_metrics,
    find_last_year_task,
    retention_workload,
)
from app.task_data import (
    get_claim_fields_for_template,
    get_task_values,
    save_task_data,
    ensure_claim_fields,
    save_backfill_data,
)
from app.claims_trends import (
    get_monthly_claim_data,
    compute_participation_metrics,
    compare_to_last_year,
    find_monthly_claim_template,
)
from app.settings_store import (
    load_settings,
    save_settings,
    is_onboarding_complete,
    load_reg_library,
    add_reg,
    get_reg,
    update_reg,
    delete_reg,
    compute_next_review_due,
    regs_due_soon_count,
    ensure_regulations_dirs,
    REGULATIONS_DIR,
    REG_TRASH_DIR,
)

router = APIRouter()

BASE_DIR = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

MAX_UPLOAD_BYTES = 100 * 1024 * 1024  # 100 MB


def _check_upload_size(content: bytes) -> None:
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, f"File exceeds {MAX_UPLOAD_BYTES // (1024 * 1024)} MB limit")


def get_db():
    """Dependency: yield DB session."""
    engine = get_engine()
    init_db(engine)
    with Session(engine) as session:
        yield session


# --- Trends ---
@router.get("/trends/template/{template_id}", response_class=HTMLResponse)
def trends_template_page(
    template_id: int,
    request: Request,
    db: Session = Depends(get_db),
    year: Optional[int] = Query(None),
    baseline: Optional[int] = Query(None),
):
    """Template trend detail: instances, metrics, top missing types."""
    today = date.today()
    y = year if isinstance(year, int) else today.year
    b = baseline if isinstance(baseline, int) else y - 1
    year_data = aggregate_by_template(db, y, template_id)
    baseline_data = aggregate_by_template(db, b, template_id)
    if isinstance(year_data, list):
        year_data = {"template_name": "", "instances": [], "instance_count": 0, "completion_rate": 0, "avg_readiness": 0, "avg_evidence_count": 0, "top_missing_evidence_types": []}
    if isinstance(baseline_data, list):
        baseline_data = {"template_name": "", "instances": [], "instance_count": 0, "completion_rate": 0, "avg_readiness": 0, "avg_evidence_count": 0, "top_missing_evidence_types": []}
    template = db.get(TaskTemplate, template_id)
    if not template:
        raise HTTPException(404, "Template not found")
    return templates.TemplateResponse(
        "trends_template.html",
        {
            "request": request,
            "template": template,
            "template_id": template_id,
            "year": y,
            "baseline": b,
            "year_data": year_data,
            "baseline_data": baseline_data,
        },
    )


@router.get("/trends", response_class=HTMLResponse)
def trends_page(
    request: Request,
    db: Session = Depends(get_db),
    year: Optional[int] = Query(None),
    baseline: Optional[int] = Query(None),
):
    """Trends dashboard: year vs baseline comparisons."""
    today = date.today()
    y = year if isinstance(year, int) else today.year
    b = baseline if isinstance(baseline, int) else y - 1
    cat_year = aggregate_by_category(db, y)
    cat_baseline = aggregate_by_category(db, b)
    month_year = aggregate_by_month(db, y)
    month_baseline = aggregate_by_month(db, b)
    workload = retention_workload(db, y)

    cat_baseline_map = {r["category"]: r for r in cat_baseline}
    category_comparison = []
    for c in cat_year:
        base = cat_baseline_map.get(c["category"], {})
        row = compare_years(c, base)
        row["baseline_completion_rate"] = base.get("completion_rate", 0)
        row["baseline_avg_readiness"] = base.get("avg_readiness", 0)
        category_comparison.append(row)

    month_baseline_map = {r["month"]: r for r in month_baseline}
    month_comparison = []
    for m in month_year:
        base = month_baseline_map.get(m["month"], {})
        row = compare_years(m, base)
        row["baseline_tasks_due"] = base.get("tasks_due", 0)
        month_comparison.append(row)

    tasks_year = list(db.exec(select(TaskInstance).where(TaskInstance.year == y)).all())
    n = len(tasks_year)
    if n > 0:
        completed = sum(1 for t in tasks_year if t.status == "completed")
        missing_req = 0
        with_memo = 0
        total_readiness = 0
        for t in tasks_year:
            t.template = db.get(TaskTemplate, t.template_id)
            m = compute_task_metrics(db, t)
            if m["missing_required_count"] > 0:
                missing_req += 1
            if m["has_memo"]:
                with_memo += 1
            total_readiness += m["readiness"]
        summary = {
            "completion_rate": round(completed / n * 100, 1),
            "avg_readiness": round(total_readiness / n, 1),
            "missing_required_pct": round(missing_req / n * 100, 1),
            "memo_coverage": round(with_memo / n * 100, 1),
        }
    else:
        summary = {"completion_rate": 0, "avg_readiness": 0, "missing_required_pct": 0, "memo_coverage": 0}

    tasks_baseline = list(db.exec(select(TaskInstance).where(TaskInstance.year == b)).all())
    nb = len(tasks_baseline)
    if nb > 0:
        completed_b = sum(1 for t in tasks_baseline if t.status == "completed")
        missing_req_b = 0
        with_memo_b = 0
        total_readiness_b = 0
        for t in tasks_baseline:
            t.template = db.get(TaskTemplate, t.template_id)
            m = compute_task_metrics(db, t)
            if m["missing_required_count"] > 0:
                missing_req_b += 1
            if m["has_memo"]:
                with_memo_b += 1
            total_readiness_b += m["readiness"]
        summary_baseline = {
            "completion_rate": round(completed_b / nb * 100, 1),
            "avg_readiness": round(total_readiness_b / nb, 1),
            "missing_required_pct": round(missing_req_b / nb * 100, 1),
            "memo_coverage": round(with_memo_b / nb * 100, 1),
        }
    else:
        summary_baseline = {"completion_rate": 0, "avg_readiness": 0, "missing_required_pct": 0, "memo_coverage": 0}

    summary_delta = compare_years(summary, summary_baseline)

    template_list = aggregate_by_template(db, y, None)
    years = sorted({t.year for t in db.exec(select(TaskInstance)).all()}, reverse=True) or [today.year]
    return templates.TemplateResponse(
        "trends.html",
        {
            "request": request,
            "year": y,
            "baseline": b,
            "summary": summary,
            "summary_baseline": summary_baseline,
            "summary_delta": summary_delta,
            "category_comparison": category_comparison,
            "month_comparison": month_comparison,
            "workload": workload,
            "template_list": template_list,
            "years": years,
        },
    )


# --- History (Phase 6) ---
@router.get("/history", response_class=HTMLResponse)
def history_page(
    request: Request,
    db: Session = Depends(get_db),
    year: Optional[int] = Query(None),
):
    """Per-year execution records: completion date, notes, checklist %, evidence."""
    today = date.today()
    y = year if isinstance(year, int) else today.year
    records = build_execution_records(db, y)
    years = sorted({t.year for t in db.exec(select(TaskInstance)).all()}, reverse=True) or [today.year]
    return templates.TemplateResponse(
        "history.html",
        {
            "request": request,
            "year": y,
            "records": records,
            "years": years,
        },
    )


@router.get("/comparison", response_class=HTMLResponse)
def comparison_page(
    request: Request,
    db: Session = Depends(get_db),
    year: Optional[int] = Query(None),
    baseline: Optional[int] = Query(None),
):
    """Task-by-task comparison: current year vs baseline year."""
    today = date.today()
    y = year if isinstance(year, int) else today.year
    b = baseline if isinstance(baseline, int) else y - 1
    pairs = build_comparison_pairs(db, y, b)
    years = sorted({t.year for t in db.exec(select(TaskInstance)).all()}, reverse=True) or [today.year]
    return templates.TemplateResponse(
        "comparison.html",
        {
            "request": request,
            "year": y,
            "baseline": b,
            "pairs": pairs,
            "years": years,
        },
    )


# --- Presets ---
@router.get("/presets/{pack_id}/preview", response_class=HTMLResponse)
def preset_preview_page(
    pack_id: str,
    request: Request,
    db: Session = Depends(get_db),
):
    """Preview what would be added when installing a preset pack."""
    try:
        pack = load_preset_pack(pack_id)
    except FileNotFoundError:
        raise HTTPException(404, f"Preset pack not found: {pack_id}")
    summary = preview_install(db, pack)
    return templates.TemplateResponse(
        "preset_preview.html",
        {
            "request": request,
            "pack": pack,
            "pack_id": pack_id,
            "summary": summary,
        },
    )


@router.post("/presets/{pack_id}/install")
def preset_install(
    pack_id: str,
    db: Session = Depends(get_db),
):
    """Install a preset pack. Idempotent."""
    try:
        pack = load_preset_pack(pack_id)
    except FileNotFoundError:
        raise HTTPException(404, f"Preset pack not found: {pack_id}")
    result = install_pack(db, pack)
    params = "&".join(f"{k}={v}" for k, v in result.items())
    return RedirectResponse(url=f"/presets?installed=1&{params}", status_code=303)


@router.get("/presets", response_class=HTMLResponse)
def presets_page(request: Request):
    """Preset Library: view and install preset packs."""
    packs: list[dict] = []
    for name in list_available_packs():
        try:
            pack = load_preset_pack(name)
            packs.append({
                "id": name,
                "name": pack.get("name", name),
                "description": pack.get("description", ""),
                "version": pack.get("version", ""),
            })
        except (FileNotFoundError, Exception):
            pass
    return templates.TemplateResponse(
        "presets.html",
        {
            "request": request,
            "packs": packs,
            "installed": request.query_params.get("installed") == "1",
            "result": {
                "added_templates": request.query_params.get("added_templates"),
                "skipped_templates": request.query_params.get("skipped_templates"),
                "added_requirements": request.query_params.get("added_requirements"),
                "skipped_requirements": request.query_params.get("skipped_requirements"),
                "added_retention_rules": request.query_params.get("added_retention_rules"),
                "skipped_retention_rules": request.query_params.get("skipped_retention_rules"),
            },
        },
    )


# --- Search ---
@router.post("/search/reindex")
def search_reindex(db: Session = Depends(get_db)):
    """Rebuild full-text search index."""
    rebuild_index(db)
    return RedirectResponse(url="/search/admin?reindexed=1", status_code=303)


@router.get("/search/admin", response_class=HTMLResponse)
def search_admin_page(request: Request):
    """Search admin: last indexed, counts, reindex button."""
    meta = load_search_meta()
    return templates.TemplateResponse(
        "search_admin.html",
        {
            "request": request,
            "meta": meta,
            "reindexed": request.query_params.get("reindexed") == "1",
        },
    )


@router.get("/search", response_class=HTMLResponse)
def search_page(
    request: Request,
    db: Session = Depends(get_db),
    q: Optional[str] = Query(None),
    year: Optional[int] = Query(None),
    category: Optional[str] = Query(None),
    entity: Optional[str] = Query(None),
):
    """Full-text search across tasks, notes, memos, evidence, templates."""
    results = []
    if q and q.strip():
        results = search(db, q.strip(), year=year, category=category, entity=entity)
    # Group by entity_type
    grouped: dict[str, list] = {}
    for r in results:
        et = r.get("entity_type", "other")
        if et not in grouped:
            grouped[et] = []
        grouped[et].append(r)
    categories = list({t.category for t in db.exec(select(TaskTemplate)).all()})
    years = sorted({t.year for t in db.exec(select(TaskInstance)).all()}, reverse=True) or [date.today().year]
    return templates.TemplateResponse(
        "search.html",
        {
            "request": request,
            "q": q or "",
            "year": year,
            "category": category,
            "entity": entity,
            "results": results,
            "grouped": grouped,
            "categories": categories,
            "years": years,
        },
    )


# --- Onboarding ---
@router.get("/onboarding", response_class=HTMLResponse)
def onboarding_page(request: Request):
    """Onboarding wizard. Redirect to /today if already complete."""
    if is_onboarding_complete():
        return RedirectResponse(url="/today", status_code=302)
    settings = load_settings()
    return templates.TemplateResponse(
        "onboarding.html",
        {
            "request": request,
            "settings": settings,
            "vault_path": str(VAULT_DIR.resolve()),
            "backups_path": str(BACKUPS_DIR.resolve()),
        },
    )


@router.post("/onboarding/save")
def onboarding_save(
    request: Request,
    db: Session = Depends(get_db),
    onboarding_complete: Optional[str] = Form(None),
    district_name: Optional[str] = Form(""),
    state: Optional[str] = Form("Idaho"),
    timezone: Optional[str] = Form("America/Boise"),
    current_school_year: Optional[str] = Form(""),
    nslp: Optional[str] = Form(None),
    sbp: Optional[str] = Form(None),
    smp: Optional[str] = Form(None),
    summer: Optional[str] = Form(None),
    cacfp: Optional[str] = Form(None),
    ffvp: Optional[str] = Form(None),
    monthly_claim_internal_deadline_day: Optional[int] = Form(15),
    month_end_close_day: Optional[int] = Form(28),
    verification_window_start: Optional[str] = Form("10-01"),
    verification_complete_deadline: Optional[str] = Form("11-15"),
    default_retention_policy: Optional[str] = Form(""),
    default_minimal_audit_set: Optional[str] = Form(""),
    enable_monthly_claims_tracking: Optional[str] = Form(None),
):
    """Save onboarding data to settings.json."""
    settings = load_settings()
    settings["district_name"] = district_name or ""
    settings["state"] = state or "Idaho"
    settings["timezone"] = timezone or "America/Boise"
    settings["current_school_year"] = current_school_year or ""
    settings["programs"] = {
        "NSLP": nslp == "on",
        "SBP": sbp == "on",
        "SMP": smp == "on",
        "Summer": summer == "on",
        "CACFP": cacfp == "on",
        "FFVP": ffvp == "on",
    }
    settings["monthly_claim_internal_deadline_day"] = monthly_claim_internal_deadline_day or 15
    settings["month_end_close_day"] = month_end_close_day or 28
    settings["verification_window_start"] = verification_window_start or "10-01"
    settings["verification_complete_deadline"] = verification_complete_deadline or "11-15"
    settings["default_retention_policy"] = default_retention_policy or ""
    settings["default_minimal_audit_set"] = default_minimal_audit_set or ""
    settings["enable_monthly_claims_tracking"] = enable_monthly_claims_tracking == "on" or enable_monthly_claims_tracking == "1"
    settings["onboarding_complete"] = onboarding_complete == "1"
    save_settings(settings)
    if settings.get("enable_monthly_claims_tracking"):
        tpl = find_monthly_claim_template(db)
        if tpl:
            ensure_claim_fields(db, tpl.id)
    resp = RedirectResponse(url="/today", status_code=303)
    return resp


@router.get("/onboarding/skip")
def onboarding_skip(request: Request):
    """Skip onboarding for now. Sets cookie to avoid redirect for 7 days."""
    resp = RedirectResponse(url="/today", status_code=303)
    resp.set_cookie("onboarding_skipped", "1", max_age=86400 * 7)
    return resp


# --- Settings (edit onboarding) ---
@router.get("/settings", response_class=HTMLResponse)
def settings_page(request: Request):
    """Edit district/program settings (onboarding answers)."""
    settings = load_settings()
    return templates.TemplateResponse(
        "settings.html",
        {
            "request": request,
            "settings": settings,
            "vault_path": str(VAULT_DIR.resolve()),
            "backups_path": str(BACKUPS_DIR.resolve()),
        },
    )


@router.post("/settings/save")
def settings_save(
    db: Session = Depends(get_db),
    district_name: Optional[str] = Form(""),
    state: Optional[str] = Form("Idaho"),
    timezone: Optional[str] = Form("America/Boise"),
    current_school_year: Optional[str] = Form(""),
    nslp: Optional[str] = Form(None),
    sbp: Optional[str] = Form(None),
    smp: Optional[str] = Form(None),
    summer: Optional[str] = Form(None),
    cacfp: Optional[str] = Form(None),
    ffvp: Optional[str] = Form(None),
    monthly_claim_internal_deadline_day: Optional[int] = Form(15),
    month_end_close_day: Optional[int] = Form(28),
    verification_window_start: Optional[str] = Form("10-01"),
    verification_complete_deadline: Optional[str] = Form("11-15"),
    default_retention_policy: Optional[str] = Form(""),
    default_minimal_audit_set: Optional[str] = Form(""),
    enable_monthly_claims_tracking: Optional[str] = Form(None),
):
    """Save settings."""
    settings = load_settings()
    settings["district_name"] = district_name or ""
    settings["state"] = state or "Idaho"
    settings["timezone"] = timezone or "America/Boise"
    settings["current_school_year"] = current_school_year or ""
    settings["programs"] = {
        "NSLP": nslp == "on",
        "SBP": sbp == "on",
        "SMP": smp == "on",
        "Summer": summer == "on",
        "CACFP": cacfp == "on",
        "FFVP": ffvp == "on",
    }
    settings["monthly_claim_internal_deadline_day"] = monthly_claim_internal_deadline_day or 15
    settings["month_end_close_day"] = month_end_close_day or 28
    settings["verification_window_start"] = verification_window_start or "10-01"
    settings["verification_complete_deadline"] = verification_complete_deadline or "11-15"
    settings["default_retention_policy"] = default_retention_policy or ""
    settings["default_minimal_audit_set"] = default_minimal_audit_set or ""
    settings["enable_monthly_claims_tracking"] = enable_monthly_claims_tracking == "on" or enable_monthly_claims_tracking == "1"
    save_settings(settings)
    if settings.get("enable_monthly_claims_tracking"):
        tpl = find_monthly_claim_template(db)
        if tpl:
            ensure_claim_fields(db, tpl.id)
    return RedirectResponse(url="/settings?saved=1", status_code=303)


# --- Regulations Library ---
REG_TOPICS = [
    "Retention", "Verification", "Civil Rights", "Administrative Review",
    "Procurement", "Professional Standards", "Other",
]
REG_AUTHORITIES = ["USDA", "Idaho CNP"]

SEED_REGS = [
    {"title": "USDA Record-Keeping Requirements", "authority": "USDA", "topic": "Retention", "source_url": "https://www.fns.usda.gov/cn/recordkeeping-requirements"},
    {"title": "Idaho Timelines, Reporting, and Recordkeeping", "authority": "Idaho CNP", "topic": "Retention", "source_url": "https://www.sde.idaho.gov/cnp/"},
    {"title": "Idaho Verification PDF", "authority": "Idaho CNP", "topic": "Verification", "source_url": "https://www.sde.idaho.gov/cnp/"},
    {"title": "USDA Beginning Verification Before Oct 1", "authority": "USDA", "topic": "Verification", "source_url": "https://www.fns.usda.gov/cn/verification"},
    {"title": "USDA Civil Rights Training resource", "authority": "USDA", "topic": "Civil Rights", "source_url": "https://www.fns.usda.gov/civil-rights"},
    {"title": "USDA Administrative Review Guidance & Tools", "authority": "USDA", "topic": "Administrative Review", "source_url": "https://www.fns.usda.gov/cn/administrative-review"},
    {"title": "Idaho Administrative Review PDF", "authority": "Idaho CNP", "topic": "Administrative Review", "source_url": "https://www.sde.idaho.gov/cnp/"},
    {"title": "USDA Procurement Regulations hub", "authority": "USDA", "topic": "Procurement", "source_url": "https://www.fns.usda.gov/cn/procurement"},
    {"title": "USDA Reminder Procurement Requirements", "authority": "USDA", "topic": "Procurement", "source_url": "https://www.fns.usda.gov/cn/procurement"},
    {"title": "USDA Professional Standards Guide", "authority": "USDA", "topic": "Professional Standards", "source_url": "https://www.fns.usda.gov/professional-standards"},
    {"title": "Idaho School Nutrition Reference Guide hub", "authority": "Idaho CNP", "topic": "Other", "source_url": "https://www.sde.idaho.gov/cnp/"},
]


@router.get("/regulations", response_class=HTMLResponse)
def regulations_page(
    request: Request,
    authority: Optional[str] = Query(None),
    topic: Optional[str] = Query(None),
    due: Optional[str] = Query(None),
):
    """Regulations library list with filters."""
    regs = load_reg_library()
    today = date.today()
    cutoff = today + timedelta(days=30)
    for r in regs:
        due_str = r.get("next_review_due")
        r["_due_soon"] = False
        if due_str:
            try:
                d = datetime.strptime(due_str, "%Y-%m-%d").date()
                r["_due_soon"] = today <= d <= cutoff
            except (ValueError, TypeError):
                pass
    if authority:
        regs = [r for r in regs if r.get("authority") == authority]
    if topic:
        regs = [r for r in regs if r.get("topic") == topic]
    if due == "soon":
        regs = [r for r in regs if r.get("_due_soon")]
    return templates.TemplateResponse(
        "regulations.html",
        {
            "request": request,
            "regs": regs,
            "authorities": REG_AUTHORITIES,
            "topics": REG_TOPICS,
            "regs_due_soon_count": regs_due_soon_count(),
        },
    )


@router.get("/regulations/new", response_class=HTMLResponse)
def regulations_new_page(request: Request):
    """Add new regulation form."""
    return templates.TemplateResponse(
        "regulations_new.html",
        {"request": request, "authorities": REG_AUTHORITIES, "topics": REG_TOPICS},
    )


@router.post("/regulations/create")
def regulations_create(
    title: str = Form(...),
    authority: str = Form(...),
    topic: str = Form(...),
    source_url: Optional[str] = Form(""),
    effective_date: Optional[str] = Form(""),
    review_frequency_days: int = Form(365),
    notes: Optional[str] = Form(""),
):
    """Create new regulation entry."""
    now = datetime.now().strftime("%Y-%m-%d")
    reg = {
        "title": title.strip(),
        "authority": authority,
        "topic": topic,
        "source_url": source_url or "",
        "local_file_path": "",
        "effective_date": effective_date or "",
        "last_reviewed": "",
        "review_frequency_days": review_frequency_days,
        "next_review_due": "",
        "notes": notes or "",
        "tags": [],
    }
    add_reg(reg)
    return RedirectResponse(url=f"/regulations", status_code=303)


@router.get("/regulations/{reg_id}", response_class=HTMLResponse)
def regulations_detail_page(request: Request, reg_id: str):
    """Regulation detail with upload."""
    reg = get_reg(reg_id)
    if not reg:
        raise HTTPException(404, "Regulation not found")
    return templates.TemplateResponse(
        "regulations_detail.html",
        {"request": request, "reg": reg},
    )


@router.post("/regulations/{reg_id}/upload")
def regulations_upload(
    reg_id: str,
    file: UploadFile = File(...),
):
    """Upload PDF to vault/_regulations/ and link to regulation."""
    reg = get_reg(reg_id)
    if not reg:
        raise HTTPException(404, "Regulation not found")
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(400, "PDF file required")
    ensure_regulations_dirs()
    subdir = f"{reg.get('authority', 'Other')}/{reg.get('topic', 'Other')}".replace(" ", "_")
    dest_dir = REGULATIONS_DIR / subdir
    dest_dir.mkdir(parents=True, exist_ok=True)
    safe_name = "".join(c for c in file.filename if c.isalnum() or c in "._- ") or "document.pdf"
    dest_path = dest_dir / safe_name
    content = file.file.read()
    _check_upload_size(content)
    with open(dest_path, "wb") as f:
        f.write(content)
    rel_path = f"_regulations/{subdir}/{safe_name}"
    update_reg(reg_id, {"local_file_path": rel_path})
    return RedirectResponse(url=f"/regulations/{reg_id}?uploaded=1", status_code=303)


@router.post("/regulations/{reg_id}/reviewed")
def regulations_reviewed(reg_id: str):
    """Mark regulation as reviewed. Sets last_reviewed=now, recomputes next_review_due."""
    reg = get_reg(reg_id)
    if not reg:
        raise HTTPException(404, "Regulation not found")
    now = datetime.now().strftime("%Y-%m-%d")
    freq = reg.get("review_frequency_days", 365)
    next_due = compute_next_review_due(now, freq)
    update_reg(reg_id, {"last_reviewed": now, "next_review_due": next_due or ""})
    return RedirectResponse(url=f"/regulations/{reg_id}?reviewed=1", status_code=303)


@router.post("/regulations/{reg_id}/delete")
def regulations_delete(reg_id: str):
    """Move file to _trash and remove record."""
    reg = get_reg(reg_id)
    if not reg:
        raise HTTPException(404, "Regulation not found")
    local_path = reg.get("local_file_path")
    if local_path:
        full = VAULT_DIR / local_path
        if full.exists():
            REG_TRASH_DIR.mkdir(parents=True, exist_ok=True)
            import shutil
            trash_name = f"{reg_id}_{full.name}"
            shutil.move(str(full), str(REG_TRASH_DIR / trash_name))
    delete_reg(reg_id)
    return RedirectResponse(url="/regulations?deleted=1", status_code=303)


@router.post("/regulations/seed")
def regulations_seed():
    """Seed recommended regs (starter list with links, no PDFs)."""
    regs = load_reg_library()
    existing_titles = {r.get("title", "") for r in regs}
    for s in SEED_REGS:
        if s["title"] in existing_titles:
            continue
        reg = {
            "title": s["title"],
            "authority": s["authority"],
            "topic": s["topic"],
            "source_url": s.get("source_url", ""),
            "local_file_path": "",
            "effective_date": "",
            "last_reviewed": "",
            "review_frequency_days": 365,
            "next_review_due": "",
            "notes": "",
            "tags": [],
        }
        add_reg(reg)
        existing_titles.add(s["title"])
    return RedirectResponse(url="/regulations?seeded=1", status_code=303)


# --- Root redirect to Today ---
@router.get("/")
def root():
    """Redirect to Daily Command Center."""
    return RedirectResponse(url="/today", status_code=302)


# --- Daily Command Center (new default) ---
@router.get("/today", response_class=HTMLResponse)
def today_page(
    request: Request,
    db: Session = Depends(get_db),
):
    """Daily Command Center: today's tasks, audit risk, missing evidence, recent evidence, quick actions."""
    if not is_onboarding_complete() and request.cookies.get("onboarding_skipped") != "1":
        return RedirectResponse(url="/onboarding", status_code=302)
    today = date.today()
    year_filter = today.year

    q = select(TaskInstance).where(TaskInstance.year == year_filter).order_by(
        TaskInstance.due_date.asc().nullslast(), TaskInstance.month.asc().nullslast()
    )
    instances = list(db.exec(q).all())
    for inst in instances:
        enrich_task_instance(inst, db)

    due_today = [t for t in instances if t.due_date == today and t.status != "completed"]
    overdue = [t for t in instances if t.due_date and t.due_date < today and t.status != "completed"]
    due_in_7 = [t for t in instances if t.due_date and today < t.due_date <= today + timedelta(days=7) and t.status != "completed"]
    audit_risk = [t for t in instances if getattr(t, "readiness", {}).get("score", 100) < 60]
    missing_required = [t for t in instances if getattr(t, "missing_req", 0) > 0]

    cutoff = datetime.utcnow() - timedelta(days=7)
    recent_evidence = list(db.exec(
        select(EvidenceItem).where(EvidenceItem.added_at >= cutoff).order_by(EvidenceItem.added_at.desc())
    ).all())
    for e in recent_evidence:
        e.task = db.get(TaskInstance, e.task_id)
        if e.task:
            object.__setattr__(e.task, "template", db.get(TaskTemplate, e.task.template_id))
    recent_evidence = [e for e in recent_evidence if e.task]

    tasks_for_quick = list(db.exec(
        select(TaskInstance).where(TaskInstance.year == year_filter).order_by(
            TaskInstance.updated_at.desc()
        ).limit(50)
    ).all())
    for t in tasks_for_quick:
        object.__setattr__(t, "template", db.get(TaskTemplate, t.template_id))

    notifications = get_notifications(db, year_filter)
    readiness_avg = round(sum(inst.readiness.get("score", 100) for inst in instances) / len(instances), 1) if instances else 100

    month_year = aggregate_by_month(db, year_filter)
    month_last = aggregate_by_month(db, year_filter - 1)
    this_month_stats = next((m for m in month_year if m["month"] == today.month), {"tasks_due": 0, "completion_rate": 0, "avg_readiness": 0})
    last_year_month_stats = next((m for m in month_last if m["month"] == today.month), {"tasks_due": 0, "completion_rate": 0, "avg_readiness": 0})

    claims_snapshot = None
    if load_settings().get("enable_monthly_claims_tracking", True):
        claim_data = get_monthly_claim_data(db, year_filter)
        claim_by_month = {d["month"]: d for d in claim_data if d.get("month")}
        last_year_claim = get_monthly_claim_data(db, year_filter - 1)
        last_year_by_month = {d["month"]: d for d in last_year_claim if d.get("month")}
        curr = claim_by_month.get(today.month, {})
        prev_month = today.month - 1 if today.month > 1 else 12
        prev_year = year_filter if today.month > 1 else year_filter - 1
        prev = get_monthly_claim_data(db, prev_year)
        prev_by_month = {d["month"]: d for d in prev if d.get("month")}
        prev_m = prev_by_month.get(prev_month, {})
        last_y = last_year_by_month.get(today.month, {})
        curr_r = curr.get("reimbursement", 0) or 0
        prev_r = prev_m.get("reimbursement", 0) or 0
        ly_r = last_y.get("reimbursement", 0) or 0
        pct_vs_last_month = ((curr_r - prev_r) / prev_r * 100) if prev_r else None
        pct_vs_last_year = ((curr_r - ly_r) / ly_r * 100) if ly_r else None
        claims_snapshot = {
            "current": curr_r,
            "last_month": prev_r,
            "last_year": ly_r,
            "pct_vs_last_month": round(pct_vs_last_month, 0) if pct_vs_last_month is not None else None,
            "pct_vs_last_year": round(pct_vs_last_year, 0) if pct_vs_last_year is not None else None,
        }

    return templates.TemplateResponse(
        "today.html",
        {
            "request": request,
            "onboarding_incomplete": not is_onboarding_complete(),
            "due_today": due_today,
            "overdue": overdue,
            "due_in_7": due_in_7,
            "audit_risk": audit_risk,
            "missing_required": missing_required,
            "recent_evidence": recent_evidence,
            "tasks_for_quick": tasks_for_quick,
            "evidence_types": EVIDENCE_TYPES,
            "importance_levels": IMPORTANCE_LEVELS,
            "notifications": notifications,
            "critical_count": notifications["critical_count"],
            "readiness_avg": readiness_avg,
            "this_month_stats": this_month_stats,
            "last_year_month_stats": last_year_month_stats,
            "claims_snapshot": claims_snapshot,
        },
    )


# --- Review Prep Mode ---
@router.get("/review", response_class=HTMLResponse)
def review_page(
    request: Request,
    db: Session = Depends(get_db),
    year: Optional[int] = Query(None),
):
    """Review Prep Mode: if state review happened tomorrow, what is missing?"""
    y = year if isinstance(year, int) else None
    data = build_review_data(db, y)
    notifications = get_notifications(db, data["year"])
    return templates.TemplateResponse(
        "review.html",
        {
            "request": request,
            **data,
            "notifications": notifications,
            "regs_due_soon_count": regs_due_soon_count(),
        },
    )


@router.get("/review-mode")
def review_mode_toggle(
    request: Request,
    on: Optional[str] = Query(None),
):
    """Toggle Review Mode. Sets cookie. Redirects to referer or /today."""
    ref = request.headers.get("referer", "/today")
    resp = RedirectResponse(url=ref, status_code=302)
    if on == "1":
        resp.set_cookie("review_mode", "1", max_age=86400 * 7)  # 7 days
    elif on == "0":
        resp.delete_cookie("review_mode")
    return resp


# --- Dashboard (full) ---
@router.get("/dashboard", response_class=HTMLResponse)
def dashboard(
    request: Request,
    db: Session = Depends(get_db),
    year: Optional[int] = Query(None),
    category: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    missing_required: Optional[str] = Query(None),
    audit_risk: Optional[str] = Query(None),
):
    """Dashboard: overdue, due soon, completed this month, filters."""
    today = date.today()
    year_filter = year if isinstance(year, int) else today.year

    q = select(TaskInstance).where(TaskInstance.year == year_filter).order_by(
        TaskInstance.due_date.asc().nullslast(), TaskInstance.month.asc().nullslast()
    )
    instances = list(db.exec(q).all())
    for inst in instances:
        enrich_task_instance(inst, db)
    if category:
        instances = [t for t in instances if t.template and t.template.category == category]
    if status:
        instances = [t for t in instances if t.status == status]
    if missing_required == "yes":
        instances = [t for t in instances if getattr(t, "missing_req", 0) > 0]
    if audit_risk == "yes":
        instances = [t for t in instances if getattr(t, "readiness", {}).get("score", 100) < 60]

    # Sections
    overdue = [t for t in instances if t.due_date and t.due_date < today and t.status != "completed"]
    due_soon_14 = [t for t in instances if t.due_date and today <= t.due_date <= today + timedelta(days=14) and t.status != "completed"]
    due_soon_30 = [t for t in instances if t.due_date and today + timedelta(days=14) < t.due_date <= today + timedelta(days=30) and t.status != "completed"]
    completed_this_month = [t for t in instances if t.status == "completed" and t.updated_at and t.updated_at.month == today.month and t.updated_at.year == today.year]
    other = [t for t in instances if t not in overdue and t not in due_soon_14 and t not in due_soon_30 and t not in completed_this_month]

    # Group all tasks by category -> template name -> [tasks] for expandable hierarchy
    all_tasks = overdue + due_soon_14 + due_soon_30 + completed_this_month + other
    tasks_grouped: dict[str, dict[str, list]] = {}
    for t in all_tasks:
        cat = (t.template.category if t.template else "") or "Uncategorized"
        tpl_name = (t.template.name if t.template else "Unknown")
        tasks_grouped.setdefault(cat, {}).setdefault(tpl_name, []).append(t)
    # Sort tasks within each template by due_date, month
    for cat in tasks_grouped:
        for tpl_name in tasks_grouped[cat]:
            tasks_grouped[cat][tpl_name].sort(
                key=lambda x: (x.due_date or date.max, x.month or 0)
            )
    # Ordered list of (category, [(template_name, tasks), ...])
    tasks_by_category: list[tuple[str, list[tuple[str, list]]]] = []
    for cat in sorted(tasks_grouped.keys()):
        templates_list = [
            (tpl_name, tasks_grouped[cat][tpl_name])
            for tpl_name in sorted(tasks_grouped[cat].keys())
        ]
        tasks_by_category.append((cat, templates_list))

    # Categories and years for filters
    categories = list({t.category for t in db.exec(select(TaskTemplate)).all()})
    year_rows = db.exec(select(TaskInstance.year).distinct()).all()
    years = sorted({(r[0] if isinstance(r, (tuple, list)) else r) for r in year_rows if r is not None}, reverse=True) or [today.year]

    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "overdue": overdue,
            "due_soon_14": due_soon_14,
            "due_soon_30": due_soon_30,
            "completed_this_month": completed_this_month,
            "other": other,
            "tasks_by_category": tasks_by_category,
            "categories": categories,
            "years": years,
            "year_filter": year_filter,
            "category_filter": category,
            "status_filter": status,
            "missing_required_filter": missing_required,
            "audit_risk_filter": audit_risk,
        },
    )


# --- Task Templates ---
@router.get("/templates", response_class=HTMLResponse)
def list_templates(request: Request, db: Session = Depends(get_db)):
    """List all task templates."""
    items = list(db.exec(select(TaskTemplate).order_by(TaskTemplate.name)).all())
    return templates.TemplateResponse(
        "templates_list.html",
        {"request": request, "templates": items},
    )


@router.get("/templates/new", response_class=HTMLResponse)
def new_template_form(request: Request):
    """Form to create a new task template."""
    return templates.TemplateResponse("template_form.html", {"request": request})


@router.post("/templates", response_class=HTMLResponse)
def create_template(
    request: Request,
    db: Session = Depends(get_db),
    name: str = Form(...),
    category: str = Form(...),
    recurrence_rule: str = Form(""),
    default_checklist: str = Form(""),
):
    """Create a new task template. Validates recurrence_rule."""
    valid, err = validate_recurrence_rule(recurrence_rule)
    if not valid:
        return templates.TemplateResponse(
            "template_form.html",
            {
                "request": request,
                "error": err,
                "name": name,
                "category": category,
                "recurrence_rule": recurrence_rule,
                "default_checklist": default_checklist,
            },
        )
    template = TaskTemplate(
        name=name,
        category=category,
        recurrence_rule=recurrence_rule.strip() or "",
        default_checklist=default_checklist,
    )
    db.add(template)
    db.commit()
    return RedirectResponse(url="/templates", status_code=303)


@router.get("/templates/{template_id}", response_class=HTMLResponse)
def template_detail(request: Request, template_id: int, db: Session = Depends(get_db)):
    """Template detail: evidence requirements editor."""
    template = db.get(TaskTemplate, template_id)
    if not template:
        raise HTTPException(404, "Template not found")
    reqs = list(db.exec(
        select(EvidenceRequirement).where(EvidenceRequirement.template_id == template_id)
    ).all())
    data_fields = get_claim_fields_for_template(db, template_id)
    return templates.TemplateResponse(
        "template_detail.html",
        {
            "request": request,
            "template": template,
            "requirements": reqs,
            "evidence_types": EVIDENCE_TYPES,
            "importance_levels": IMPORTANCE_LEVELS,
            "data_fields": data_fields,
        },
    )


@router.post("/templates/{template_id}/requirements")
def add_evidence_requirement(
    template_id: int,
    db: Session = Depends(get_db),
    evidence_type: str = Form(...),
    importance: str = Form(...),
    description: str = Form(""),
):
    """Add evidence requirement to template."""
    template = db.get(TaskTemplate, template_id)
    if not template:
        raise HTTPException(404, "Template not found")
    if evidence_type not in EVIDENCE_TYPES or importance not in IMPORTANCE_LEVELS:
        raise HTTPException(400, "Invalid type or importance")
    r = EvidenceRequirement(
        template_id=template_id,
        evidence_type=evidence_type,
        importance=importance,
        description=description,
    )
    db.add(r)
    db.commit()
    return RedirectResponse(url=f"/templates/{template_id}", status_code=303)


@router.post("/requirements/{req_id}/delete")
def delete_evidence_requirement(req_id: int, db: Session = Depends(get_db)):
    """Remove evidence requirement."""
    r = db.get(EvidenceRequirement, req_id)
    if not r:
        raise HTTPException(404, "Requirement not found")
    tid = r.template_id
    db.delete(r)
    db.commit()
    return RedirectResponse(url=f"/templates/{tid}", status_code=303)


@router.post("/templates/{template_id}/requirements/preset")
def preset_minimal_audit(template_id: int, db: Session = Depends(get_db)):
    """Seed minimal audit set: required submission/approval/calculation/source_data, supporting communication."""
    template = db.get(TaskTemplate, template_id)
    if not template:
        raise HTTPException(404, "Template not found")
    existing = {r.evidence_type for r in db.exec(
        select(EvidenceRequirement).where(EvidenceRequirement.template_id == template_id)
    ).all()}
    presets = [
        ("submission", "required", "Submission document"),
        ("approval", "required", "Approval/sign-off"),
        ("calculation", "required", "Calculation/supporting data"),
        ("source_data", "required", "Source data"),
        ("communication", "supporting", "Related communication"),
    ]
    for et, imp, desc in presets:
        if et not in existing:
            db.add(EvidenceRequirement(template_id=template_id, evidence_type=et, importance=imp, description=desc))
            existing.add(et)
    db.commit()
    return RedirectResponse(url=f"/templates/{template_id}", status_code=303)


@router.get("/templates/{template_id}/backfill", response_class=HTMLResponse)
def template_backfill_page(
    request: Request,
    template_id: int,
    db: Session = Depends(get_db),
    year: Optional[int] = Query(None),
):
    """Backfill structured data for all task instances of template."""
    template = db.get(TaskTemplate, template_id)
    if not template:
        raise HTTPException(404, "Template not found")
    data_fields = get_claim_fields_for_template(db, template_id)
    if not data_fields:
        raise HTTPException(400, "Template has no structured data fields")
    today = date.today()
    y = year if isinstance(year, int) else today.year
    instances = list(db.exec(
        select(TaskInstance).where(
            TaskInstance.template_id == template_id,
            TaskInstance.year == y,
        ).order_by(TaskInstance.month.asc().nullslast())
    ).all())
    task_values_map = {}
    for inst in instances:
        task_values_map[inst.id] = get_task_values(db, inst.id)
    return templates.TemplateResponse(
        "template_backfill.html",
        {
            "request": request,
            "template": template,
            "data_fields": data_fields,
            "instances": instances,
            "task_values_map": task_values_map,
            "year": y,
        },
    )


@router.post("/templates/{template_id}/backfill/save")
async def template_backfill_save(
    request: Request,
    template_id: int,
    db: Session = Depends(get_db),
):
    """Save backfill updates."""
    template = db.get(TaskTemplate, template_id)
    if not template:
        raise HTTPException(404, "Template not found")
    form = await request.form()
    updates = []
    for key, value in form.items():
        if key.startswith("task_") and "__" in key:
            rest = key[5:]
            task_id_str, field_key = rest.split("__", 1)
            try:
                task_id = int(task_id_str)
                updates.append({"task_id": task_id, "field_key": field_key, "value": value})
            except ValueError:
                pass
    save_backfill_data(db, updates)
    return RedirectResponse(url=f"/templates/{template_id}/backfill?saved=1", status_code=303)


# --- Task Instances ---
@router.get("/tasks/new", response_class=HTMLResponse)
def new_task_form(request: Request, db: Session = Depends(get_db)):
    """Form to create a new task instance (from template)."""
    templates_list = db.exec(select(TaskTemplate).order_by(TaskTemplate.name)).all()
    from datetime import datetime
    current_year = datetime.now().year
    return templates.TemplateResponse(
        "task_form.html",
        {"request": request, "templates": templates_list, "current_year": current_year},
    )


@router.post("/tasks")
def create_task(
    db: Session = Depends(get_db),
    template_id: int = Form(...),
    year: int = Form(...),
    due_date: Optional[str] = Form(None),
):
    """Create a new task instance."""
    due = date.fromisoformat(due_date) if due_date else None
    task = TaskInstance(template_id=template_id, year=year, due_date=due)
    db.add(task)
    db.commit()
    db.refresh(task)
    return RedirectResponse(url=f"/tasks/{task.id}", status_code=303)


@router.get("/tasks/{task_id}", response_class=HTMLResponse)
def task_detail(request: Request, task_id: int, db: Session = Depends(get_db)):
    """Task detail page: checklist, notes, evidence, edit."""
    task = db.get(TaskInstance, task_id)
    if not task:
        raise HTTPException(404, "Task not found")
    task.template = db.get(TaskTemplate, task.template_id)
    checklist = list(db.exec(
        select(ChecklistItem).where(ChecklistItem.task_id == task_id).order_by(ChecklistItem.sort_order)
    ).all())
    notes = list(db.exec(
        select(NoteLog).where(NoteLog.task_id == task_id).order_by(NoteLog.created_at.desc())
    ).all())
    evidence = list(db.exec(
        select(EvidenceItem).where(EvidenceItem.task_id == task_id).order_by(EvidenceItem.added_at.desc())
    ).all())
    missing_req, missing_sup = compute_missing_evidence(db, task, task.template)
    readiness = compute_audit_readiness(db, task_id)
    next_steps = task_next_steps(db, task_id)
    missing_types = get_missing_requirement_types(db, task, task.template)
    export_ready = is_export_ready(db, task_id)
    last_year_task = find_last_year_task(db, task) if task.template_id else None
    last_year_metrics = None
    if last_year_task:
        last_year_metrics = compute_task_metrics(db, last_year_task)
        last_year_metrics["missing_types"] = get_missing_requirement_types(db, last_year_task, db.get(TaskTemplate, last_year_task.template_id))
    if task.template_id and task.template and task.template.name == "Monthly Claim Submission":
        ensure_claim_fields(db, task.template_id)
    data_fields = get_claim_fields_for_template(db, task.template_id) if task.template_id else []
    task_values = get_task_values(db, task_id)
    resp = templates.TemplateResponse(
        "task_detail.html",
        {
            "request": request,
            "task": task,
            "checklist": checklist,
            "notes": notes,
            "evidence": evidence,
            "missing_required": missing_req,
            "missing_supporting": missing_sup,
            "evidence_types": EVIDENCE_TYPES,
            "importance_levels": IMPORTANCE_LEVELS,
            "readiness": readiness,
            "next_steps": next_steps,
            "missing_types": missing_types,
            "export_ready": export_ready,
            "last_year_task": last_year_task,
            "last_year_metrics": last_year_metrics,
            "data_fields": data_fields,
            "task_values": task_values,
            "get_evidence_types": get_evidence_types,
        },
    )
    resp.set_cookie("last_task_id", str(task_id), max_age=86400 * 7)
    return resp


@router.post("/tasks/{task_id}/data/save")
async def save_task_data_route(
    request: Request,
    task_id: int,
    db: Session = Depends(get_db),
):
    """Save structured task data (partial save supported)."""
    task = db.get(TaskInstance, task_id)
    if not task:
        raise HTTPException(404, "Task not found")
    form = await request.form()
    data = dict(form)
    fields = get_claim_fields_for_template(db, task.template_id)
    field_keys = {f.field_key for f in fields}
    for k in list(data.keys()):
        if k not in field_keys or k.startswith("_"):
            data.pop(k, None)
    for f in fields:
        if f.data_type == "bool" and f.field_key not in data:
            data[f.field_key] = False
    save_task_data(db, task_id, data)
    return RedirectResponse(url=f"/tasks/{task_id}?saved=1", status_code=303)


@router.post("/tasks/{task_id}/update", response_class=HTMLResponse)
def update_task(
    request: Request,
    task_id: int,
    db: Session = Depends(get_db),
    due_date: Optional[str] = Form(None),
    status: str = Form(...),
    notes: str = Form(""),
    completion_date: Optional[str] = Form(None),
):
    """Update task fields."""
    task = db.get(TaskInstance, task_id)
    if not task:
        raise HTTPException(404, "Task not found")
    if due_date:
        task.due_date = date.fromisoformat(due_date)
    prev_status = task.status
    task.status = status
    task.notes = notes
    if completion_date:
        task.completion_date = date.fromisoformat(completion_date)
    elif status == "completed" and prev_status != "completed" and not task.completion_date:
        task.completion_date = date.today()
    elif status != "completed":
        task.completion_date = None
    from datetime import datetime
    task.updated_at = datetime.utcnow()
    db.add(task)
    db.commit()
    db.refresh(task)
    task.template = db.get(TaskTemplate, task.template_id)
    checklist = list(db.exec(
        select(ChecklistItem).where(ChecklistItem.task_id == task_id).order_by(ChecklistItem.sort_order)
    ).all())
    notes_list = list(db.exec(
        select(NoteLog).where(NoteLog.task_id == task_id).order_by(NoteLog.created_at.desc())
    ).all())
    evidence = list(db.exec(
        select(EvidenceItem).where(EvidenceItem.task_id == task_id).order_by(EvidenceItem.added_at.desc())
    ).all())
    missing_req, missing_sup = compute_missing_evidence(db, task, task.template)
    readiness = compute_audit_readiness(db, task_id)
    next_steps = task_next_steps(db, task_id)
    missing_types = get_missing_requirement_types(db, task, task.template)
    export_ready = is_export_ready(db, task_id)
    last_year_task = find_last_year_task(db, task) if task.template_id else None
    last_year_metrics = None
    if last_year_task:
        last_year_metrics = compute_task_metrics(db, last_year_task)
        last_year_metrics["missing_types"] = get_missing_requirement_types(db, last_year_task, db.get(TaskTemplate, last_year_task.template_id))
    if task.template_id and task.template and task.template.name == "Monthly Claim Submission":
        ensure_claim_fields(db, task.template_id)
    data_fields = get_claim_fields_for_template(db, task.template_id) if task.template_id else []
    task_values = get_task_values(db, task_id)
    return templates.TemplateResponse(
        "task_detail.html",
        {
            "request": request,
            "task": task,
            "checklist": checklist,
            "notes": notes_list,
            "evidence": evidence,
            "missing_required": missing_req,
            "missing_supporting": missing_sup,
            "evidence_types": EVIDENCE_TYPES,
            "importance_levels": IMPORTANCE_LEVELS,
            "readiness": readiness,
            "next_steps": next_steps,
            "last_year_task": last_year_task,
            "last_year_metrics": last_year_metrics,
            "missing_types": missing_types,
            "export_ready": export_ready,
            "data_fields": data_fields,
            "task_values": task_values,
            "get_evidence_types": get_evidence_types,
        },
    )


@router.post("/tasks/{task_id}/copy-from-last-year")
def copy_from_last_year(task_id: int, db: Session = Depends(get_db)):
    """Copy checklist items and notes from last year's task to current task."""
    task = db.get(TaskInstance, task_id)
    if not task:
        raise HTTPException(404, "Task not found")
    last_year_task = find_last_year_task(db, task) if task.template_id else None
    if not last_year_task:
        raise HTTPException(400, "No last year task found for this template")
    checklist_src = list(db.exec(
        select(ChecklistItem).where(ChecklistItem.task_id == last_year_task.id).order_by(ChecklistItem.sort_order)
    ).all())
    notes_src = list(db.exec(
        select(NoteLog).where(NoteLog.task_id == last_year_task.id).order_by(NoteLog.created_at.desc())
    ).all())
    existing = list(db.exec(select(ChecklistItem).where(ChecklistItem.task_id == task_id)).all())
    max_sort = max((c.sort_order for c in existing), default=0)
    for c in checklist_src:
        new_item = ChecklistItem(task_id=task_id, text=c.text, completed=False, sort_order=max_sort + 1)
        max_sort += 1
        db.add(new_item)
    for n in notes_src:
        new_note = NoteLog(task_id=task_id, content=f"[Copied from {task.year - 1}] {n.content}")
        db.add(new_note)
    db.commit()
    return RedirectResponse(url=f"/tasks/{task_id}?copied=1", status_code=303)


# --- Evidence ---
@router.post("/tasks/{task_id}/evidence/upload-bulk")
async def attach_evidence_bulk(
    request: Request,
    task_id: int,
    db: Session = Depends(get_db),
    files: list[UploadFile] = File(...),
    importance: str = Form(...),
    description: str = Form(""),
    category_override: str = Form(""),
):
    """Attach multiple evidence files to task. Shared types/importance; description uses filename if empty."""
    task = db.get(TaskInstance, task_id)
    if not task:
        raise HTTPException(404, "Task not found")
    template = db.get(TaskTemplate, task.template_id)
    form = await request.form()
    types_list = form.getlist("evidence_types")
    if not types_list and evidence_type:
        types_list = [evidence_type]
    if not types_list:
        raise HTTPException(400, "Select at least one evidence type")
    for t in types_list:
        if t not in EVIDENCE_TYPES:
            raise HTTPException(400, f"Invalid evidence type: {t}")
    if importance not in IMPORTANCE_LEVELS:
        raise HTTPException(400, "Invalid importance")
    import tempfile
    cat = category_override.strip() or (template.category if template else "")
    for file in files:
        if not file.filename:
            continue
        safe_filename = _sanitize_upload_filename(file.filename)
        content = await file.read()
        _check_upload_size(content)
        with tempfile.NamedTemporaryFile(delete=False, suffix=Path(safe_filename).suffix) as tmp:
            tmp.write(content)
            tmp_path = Path(tmp.name)
        try:
            dest_path, stored_fn, rel_path = store_evidence_file(task, template, tmp_path, safe_filename)
        finally:
            tmp_path.unlink(missing_ok=True)
        now = datetime.utcnow()
        primary_type = types_list[0]
        keep_until, review_date, rule_id, _ = apply_retention_rule(db, cat or "Other", primary_type, importance, now)
        desc = description.strip() or safe_filename
        item = EvidenceItem(
            task_id=task_id,
            category=cat,
            evidence_type=primary_type,
            evidence_types_json=json.dumps(types_list),
            importance=importance,
            description=desc,
            original_filename=file.filename,
            stored_filename=stored_fn,
            file_path=rel_path,
            retention_rule_id=rule_id,
            keep_until=keep_until,
            review_date=review_date,
        )
        db.add(item)
    db.commit()
    resp = RedirectResponse(url=f"/tasks/{task_id}#evidence", status_code=303)
    resp.set_cookie("last_task_id", str(task_id), max_age=86400 * 7)
    return resp


@router.post("/tasks/{task_id}/evidence")
async def attach_evidence(
    request: Request,
    task_id: int,
    db: Session = Depends(get_db),
    file: UploadFile = File(...),
    evidence_type: Optional[str] = Form(None),
    importance: str = Form(...),
    description: str = Form(""),
    category_override: str = Form(""),
):
    """Attach evidence file to task. Copies into vault, applies retention rule."""
    task = db.get(TaskInstance, task_id)
    if not task:
        raise HTTPException(404, "Task not found")
    template = db.get(TaskTemplate, task.template_id)
    form = await request.form()
    types_list = form.getlist("evidence_types")
    if not types_list and evidence_type:
        types_list = [evidence_type]
    if not types_list:
        raise HTTPException(400, "Select at least one evidence type")
    for t in types_list:
        if t not in EVIDENCE_TYPES:
            raise HTTPException(400, f"Invalid evidence type: {t}")
    if importance not in IMPORTANCE_LEVELS:
        raise HTTPException(400, "Invalid importance")
    if not file.filename:
        raise HTTPException(400, "No file provided")
    safe_filename = _sanitize_upload_filename(file.filename)
    import tempfile
    content = file.file.read()
    _check_upload_size(content)
    with tempfile.NamedTemporaryFile(delete=False, suffix=Path(safe_filename).suffix) as tmp:
        tmp.write(content)
        tmp_path = Path(tmp.name)
    try:
        dest_path, stored_fn, rel_path = store_evidence_file(task, template, tmp_path, safe_filename)
    finally:
        tmp_path.unlink(missing_ok=True)
    cat = category_override.strip() or (template.category if template else "")
    now = datetime.utcnow()
    primary_type = types_list[0]
    keep_until, review_date, rule_id, _ = apply_retention_rule(db, cat or "Other", primary_type, importance, now)
    item = EvidenceItem(
        task_id=task_id,
        category=cat,
        evidence_type=primary_type,
        evidence_types_json=json.dumps(types_list),
        importance=importance,
        description=description,
        original_filename=safe_filename,
        stored_filename=stored_fn,
        file_path=rel_path,
        retention_rule_id=rule_id,
        keep_until=keep_until,
        review_date=review_date,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    resp = RedirectResponse(url=f"/tasks/{task_id}#evidence", status_code=303)
    resp.set_cookie("last_task_id", str(task_id), max_age=86400 * 7)
    return resp


@router.post("/evidence/{item_id}/delete")
def delete_evidence(item_id: int, db: Session = Depends(get_db)):
    """Remove evidence. Moves file to _trash, deletes record."""
    item = db.get(EvidenceItem, item_id)
    if not item:
        raise HTTPException(404, "Evidence not found")
    move_to_trash(item.file_path)
    db.delete(item)
    db.commit()
    return RedirectResponse(url=f"/tasks/{item.task_id}#evidence", status_code=303)


@router.get("/evidence/{item_id}/explain", response_class=HTMLResponse)
def evidence_explain(request: Request, item_id: int, db: Session = Depends(get_db)):
    """Explain retention status: matched rule, rationale, suggested edits."""
    explain = retention_explain(db, item_id)
    if "error" in explain:
        raise HTTPException(404, explain["error"])
    return templates.TemplateResponse(
        "evidence_explain.html",
        {"request": request, "get_evidence_types": get_evidence_types, **explain},
    )


@router.post("/tasks/{task_id}/evidence/extract")
def extract_claim_from_evidence(
    task_id: int,
    evidence_item_id: int = Form(...),
    db: Session = Depends(get_db),
):
    """Extract claim data (meal counts, reimbursement, etc.) from a PDF evidence file via OCR/text extraction."""
    from app.ocr_extract import extract_claim_data_from_pdf
    from app.task_data import get_claim_fields_for_template, save_task_data

    task = db.get(TaskInstance, task_id)
    task.template = db.get(TaskTemplate, task.template_id) if task else None
    if not task:
        raise HTTPException(404, "Task not found")
    item = db.get(EvidenceItem, evidence_item_id)
    if not item or item.task_id != task_id:
        raise HTTPException(404, "Evidence not found")
    if not item.file_path:
        raise HTTPException(400, "Evidence has no file")
    if not item.original_filename.lower().endswith(".pdf"):
        raise HTTPException(400, "Only PDF files can be extracted")
    if task.template and task.template.name == "Monthly Claim Submission":
        ensure_claim_fields(db, task.template_id)
    fields = get_claim_fields_for_template(db, task.template_id)
    if not fields:
        raise HTTPException(400, "This task has no claim data fields")
    full_path = VAULT_DIR / item.file_path
    if not full_path.exists():
        raise HTTPException(404, "File not found in vault")
    data = extract_claim_data_from_pdf(full_path)
    if data:
        save_task_data(db, task_id, data)
    return RedirectResponse(url=f"/tasks/{task_id}?extracted=1#evidence", status_code=303)


# --- Checklist ---
@router.post("/tasks/{task_id}/checklist", response_class=HTMLResponse)
def add_checklist_item(
    request: Request,
    task_id: int,
    db: Session = Depends(get_db),
    text: str = Form(...),
):
    """Add a checklist item to a task."""
    task = db.get(TaskInstance, task_id)
    if not task:
        raise HTTPException(404, "Task not found")
    items = db.exec(select(ChecklistItem).where(ChecklistItem.task_id == task_id)).all()
    sort_order = max((c.sort_order for c in items), default=0) + 1
    item = ChecklistItem(task_id=task_id, text=text, sort_order=sort_order)
    db.add(item)
    db.commit()
    db.refresh(item)
    return templates.TemplateResponse(
        "checklist_item.html",
        {"request": request, "item": item},
    )


@router.post("/checklist/{item_id}/toggle", response_class=HTMLResponse)
def toggle_checklist(
    request: Request,
    item_id: int,
    db: Session = Depends(get_db),
):
    """Toggle checklist item completed state. HTMX partial response."""
    item = db.get(ChecklistItem, item_id)
    if not item:
        raise HTTPException(404, "Checklist item not found")
    item.completed = not item.completed
    db.add(item)
    db.commit()
    db.refresh(item)
    return templates.TemplateResponse(
        "checklist_item.html",
        {"request": request, "item": item},
    )


# --- Notes ---
@router.post("/tasks/{task_id}/notes", response_class=HTMLResponse)
def add_note(
    request: Request,
    task_id: int,
    db: Session = Depends(get_db),
    content: str = Form(...),
):
    """Add a timestamped note to a task."""
    task = db.get(TaskInstance, task_id)
    if not task:
        raise HTTPException(404, "Task not found")
    note = NoteLog(task_id=task_id, content=content)
    db.add(note)
    db.commit()
    db.refresh(note)
    return templates.TemplateResponse(
        "note_item.html",
        {"request": request, "note": note},
    )


# --- Quick Capture ---
@router.get("/quick", response_class=HTMLResponse)
def quick_capture_page(request: Request, db: Session = Depends(get_db)):
    """Quick Capture panel page."""
    today = date.today()
    tasks_for_quick = list(db.exec(
        select(TaskInstance).where(TaskInstance.year == today.year).order_by(
            TaskInstance.updated_at.desc()
        ).limit(50)
    ).all())
    for t in tasks_for_quick:
        t.template = db.get(TaskTemplate, t.template_id)
    return templates.TemplateResponse(
        "quick_capture_page.html",
        {
            "request": request,
            "tasks_for_quick": tasks_for_quick,
            "evidence_types": EVIDENCE_TYPES,
            "importance_levels": IMPORTANCE_LEVELS,
        },
    )


@router.post("/quick/note")
def quick_note(
    request: Request,
    db: Session = Depends(get_db),
    task_id: int = Form(...),
    content: str = Form(...),
):
    """Quick add note to task."""
    task = db.get(TaskInstance, task_id)
    if not task:
        raise HTTPException(404, "Task not found")
    note = NoteLog(task_id=task_id, content=content.strip())
    db.add(note)
    db.commit()
    if request.headers.get("HX-Request"):
        resp = templates.TemplateResponse(
            "quick_capture_success.html",
            {"request": request, "message": "Note added.", "task_id": task_id, "anchor": "notes"},
        )
    else:
        resp = RedirectResponse(url=f"/tasks/{task_id}#notes", status_code=303)
    resp.set_cookie("last_task_id", str(task_id), max_age=86400 * 7)
    return resp


@router.post("/quick/evidence")
async def quick_evidence(
    request: Request,
    db: Session = Depends(get_db),
    task_id: int = Form(...),
    file: UploadFile = File(...),
    evidence_type: Optional[str] = Form(None),
    importance: str = Form(...),
    description: str = Form(""),
):
    """Quick attach evidence to task."""
    task = db.get(TaskInstance, task_id)
    if not task:
        raise HTTPException(404, "Task not found")
    template = db.get(TaskTemplate, task.template_id)
    form = await request.form()
    types_list = form.getlist("evidence_types")
    if not types_list and evidence_type:
        types_list = [evidence_type]
    if not types_list:
        raise HTTPException(400, "Select at least one evidence type")
    for t in types_list:
        if t not in EVIDENCE_TYPES:
            raise HTTPException(400, f"Invalid evidence type: {t}")
    if importance not in IMPORTANCE_LEVELS:
        raise HTTPException(400, "Invalid importance")
    if not file.filename:
        raise HTTPException(400, "No file provided")
    safe_filename = _sanitize_upload_filename(file.filename)
    import tempfile
    content = file.file.read()
    _check_upload_size(content)
    with tempfile.NamedTemporaryFile(delete=False, suffix=Path(safe_filename).suffix) as tmp:
        tmp.write(content)
        tmp_path = Path(tmp.name)
    try:
        dest_path, stored_fn, rel_path = store_evidence_file(task, template, tmp_path, safe_filename)
    finally:
        tmp_path.unlink(missing_ok=True)
    cat = template.category if template else ""
    now = datetime.utcnow()
    primary_type = types_list[0]
    keep_until, review_date, rule_id, _ = apply_retention_rule(db, cat or "Other", primary_type, importance, now)
    item = EvidenceItem(
        task_id=task_id,
        category=cat,
        evidence_type=primary_type,
        evidence_types_json=json.dumps(types_list),
        importance=importance,
        description=description,
        original_filename=safe_filename,
        stored_filename=stored_fn,
        file_path=rel_path,
        retention_rule_id=rule_id,
        keep_until=keep_until,
        review_date=review_date,
    )
    db.add(item)
    db.commit()
    if request.headers.get("HX-Request"):
        resp = templates.TemplateResponse(
            "quick_capture_success.html",
            {"request": request, "message": "Evidence attached.", "task_id": task_id, "anchor": "evidence"},
        )
    else:
        resp = RedirectResponse(url=f"/tasks/{task_id}#evidence", status_code=303)
    resp.set_cookie("last_task_id", str(task_id), max_age=86400 * 7)
    return resp


@router.post("/quick/log")
def quick_log(
    request: Request,
    db: Session = Depends(get_db),
    task_id: int = Form(...),
    content: str = Form(...),
):
    """Quick log (communication entry) - stores as NoteLog with prefix."""
    task = db.get(TaskInstance, task_id)
    if not task:
        raise HTTPException(404, "Task not found")
    prefixed = f"[Communication] {content.strip()}"
    note = NoteLog(task_id=task_id, content=prefixed)
    db.add(note)
    db.commit()
    if request.headers.get("HX-Request"):
        resp = templates.TemplateResponse(
            "quick_capture_success.html",
            {"request": request, "message": "Log added.", "task_id": task_id, "anchor": "notes"},
        )
    else:
        resp = RedirectResponse(url=f"/tasks/{task_id}#notes", status_code=303)
    resp.set_cookie("last_task_id", str(task_id), max_age=86400 * 7)
    return resp


# --- Year Planner ---
@router.get("/planner", response_class=HTMLResponse)
def planner_page(request: Request, db: Session = Depends(get_db)):
    """Year Planner: generate task instances for a year."""
    from datetime import datetime
    current_year = datetime.now().year
    return templates.TemplateResponse(
        "planner.html",
        {"request": request, "current_year": current_year},
    )


@router.post("/planner/generate", response_class=HTMLResponse)
def planner_generate(
    request: Request,
    db: Session = Depends(get_db),
    year: int = Form(...),
    include_monthly: Optional[str] = Form("true"),
    include_no_recurrence: Optional[str] = Form(None),
):
    """Generate year plan. Idempotent - no duplicates."""
    inc_monthly = (include_monthly or "true").lower() == "true"
    inc_no_recur = (include_no_recurrence or "").lower() == "true"
    result = generate_year_plan(db, year, inc_monthly, inc_no_recur)
    return templates.TemplateResponse(
        "planner_result.html",
        {"request": request, "year": year, "result": result},
    )


# --- Calendar ---
@router.get("/calendar", response_class=HTMLResponse)
def calendar_view(
    request: Request,
    db: Session = Depends(get_db),
    year: Optional[int] = Query(None),
    month: Optional[int] = Query(None),
    category: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
):
    """Month calendar view with tasks on each day."""
    today = date.today()
    y = year if isinstance(year, int) else today.year
    m = month if isinstance(month, int) else today.month
    cal = calendar.Calendar(firstweekday=6)  # Sunday first
    weeks = cal.monthdatescalendar(y, m)

    first_day = date(y, m, 1)
    last_day = date(y, m, calendar.monthrange(y, m)[1])

    q = select(TaskInstance).where(
        TaskInstance.due_date.isnot(None),
        TaskInstance.due_date >= first_day,
        TaskInstance.due_date <= last_day,
    )
    instances = list(db.exec(q).all())
    for inst in instances:
        enrich_task_instance(inst, db, include_readiness=False)

    if category:
        instances = [t for t in instances if t.template and t.template.category == category]
    if status:
        instances = [t for t in instances if t.status == status]

    # Map date -> tasks
    tasks_by_date = {}
    for t in instances:
        d = t.due_date
        if not d and t.month:
            d = date(y, t.month, 1)
        if d:
            tasks_by_date.setdefault(d, []).append(t)

    categories = list({t.category for t in db.exec(select(TaskTemplate)).all()})
    month_name = calendar.month_name[m]

    return templates.TemplateResponse(
        "calendar.html",
        {
            "request": request,
            "year": y,
            "month": m,
            "month_name": month_name,
            "weeks": weeks,
            "tasks_by_date": tasks_by_date,
            "categories": categories,
            "category_filter": category,
            "status_filter": status,
        },
    )


# --- Compliance Assistant ---
@router.get("/assistant", response_class=HTMLResponse)
def assistant_page(
    request: Request,
    db: Session = Depends(get_db),
    query: Optional[str] = Query(None),
    days: Optional[int] = Query(None),
    year: Optional[int] = Query(None),
    template_id: Optional[int] = Query(None),
):
    """Rule-based compliance assistant. Predefined queries."""
    today = date.today()
    y = year if isinstance(year, int) else today.year
    results = None
    query_name = None

    if query == "due_7":
        query_name = "Due in next 7 days"
        end = today + timedelta(days=7)
        q = select(TaskInstance).where(
            TaskInstance.due_date >= today,
            TaskInstance.due_date <= end,
            TaskInstance.status != "completed",
        )
        results = list(db.exec(q).all())
    elif query == "due_14":
        query_name = "Due in next 14 days"
        end = today + timedelta(days=14)
        q = select(TaskInstance).where(
            TaskInstance.due_date >= today,
            TaskInstance.due_date <= end,
            TaskInstance.status != "completed",
        )
        results = list(db.exec(q).all())
    elif query == "due_30":
        query_name = "Due in next 30 days"
        end = today + timedelta(days=30)
        q = select(TaskInstance).where(
            TaskInstance.due_date >= today,
            TaskInstance.due_date <= end,
            TaskInstance.status != "completed",
        )
        results = list(db.exec(q).all())
    elif query == "overdue":
        query_name = "Overdue"
        q = select(TaskInstance).where(
            TaskInstance.due_date < today,
            TaskInstance.status != "completed",
        )
        results = list(db.exec(q).all())
    elif query == "by_year":
        query_name = f"All tasks for {y} by category"
        q = select(TaskInstance).where(TaskInstance.year == y).order_by(
            TaskInstance.due_date.asc().nullslast()
        )
        results = list(db.exec(q).all())
    elif query == "last_year":
        if template_id:
            tpl = db.get(TaskTemplate, template_id)
            prev_year = today.year - 1
            query_name = f"Last year's tasks for {tpl.name if tpl else 'template'}"
            q = select(TaskInstance).where(
                TaskInstance.template_id == template_id,
                TaskInstance.year == prev_year,
            ).order_by(TaskInstance.due_date.asc().nullslast())
            results = list(db.exec(q).all())
        else:
            query_name = None
            results = None
    elif query == "missing_required":
        query_name = "Tasks missing required evidence"
        all_tasks = list(db.exec(select(TaskInstance)).all())
        results = []
        for t in all_tasks:
            t.template = db.get(TaskTemplate, t.template_id)
            mr, _ = compute_missing_evidence(db, t, t.template)
            if mr > 0:
                results.append(t)
    elif query == "missing_any":
        query_name = "Tasks with no evidence"
        all_tasks = list(db.exec(select(TaskInstance)).all())
        results = []
        for t in all_tasks:
            t.template = db.get(TaskTemplate, t.template_id)
            items = list(db.exec(select(EvidenceItem).where(EvidenceItem.task_id == t.id)).all())
            if not items:
                results.append(t)
    elif query == "evidence_recent_7":
        query_name = "Evidence added in last 7 days"
        cutoff = datetime.utcnow() - timedelta(days=7)
        results = list(db.exec(
            select(EvidenceItem).where(EvidenceItem.added_at >= cutoff).order_by(EvidenceItem.added_at.desc())
        ).all())
        for e in results:
            e.task = db.get(TaskInstance, e.task_id)
            if e.task:
                e.task.template = db.get(TaskTemplate, e.task.template_id)
    elif query == "evidence_recent_30":
        query_name = "Evidence added in last 30 days"
        cutoff = datetime.utcnow() - timedelta(days=30)
        results = list(db.exec(
            select(EvidenceItem).where(EvidenceItem.added_at >= cutoff).order_by(EvidenceItem.added_at.desc())
        ).all())
        for e in results:
            e.task = db.get(TaskInstance, e.task_id)
            if e.task:
                e.task.template = db.get(TaskTemplate, e.task.template_id)

    if results is not None:
        for inst in results:
            inst.template = db.get(TaskTemplate, inst.template_id)
        if query == "by_year":
            # Group by category
            by_cat = {}
            for t in results:
                cat = t.template.category if t.template else "Other"
                by_cat.setdefault(cat, []).append(t)
            results = by_cat

    return templates.TemplateResponse(
        "assistant.html",
        {
            "request": request,
            "query": query,
            "query_name": query_name,
            "results": results,
            "current_year": today.year,
            "year_param": y,
            "template_id": template_id,
            "get_evidence_types": get_evidence_types,
        },
    )


# --- Assistant v2 (guided prompts + free-text routing) ---
def _route_ask_to_query(ask: str) -> Optional[str]:
    """Map free-text to deterministic query intent."""
    if not ask or not ask.strip():
        return None
    s = ask.strip().lower()
    if "due" in s and "overdue" not in s:
        return "due_soon_missing"
    if "overdue" in s:
        return "overdue"
    if "missing" in s or "evidence" in s:
        return "missing_required"
    if "audit" in s or "risk" in s:
        return "audit_risk"
    if "delete" in s or "purge" in s or "safe" in s:
        return "safe_to_delete"
    if "recent" in s or "added" in s:
        return "evidence_recent_30"
    return None


@router.get("/assistant-v2", response_class=HTMLResponse)
def assistant_v2_page(
    request: Request,
    db: Session = Depends(get_db),
    query: Optional[str] = Query(None),
    ask: Optional[str] = Query(None),
    days: Optional[int] = Query(30),
    category: Optional[str] = Query(None),
):
    """Assistant v2: quick queries + free-text routing. Deterministic, no LLM."""
    today = date.today()
    resolved_query = query
    if not resolved_query and ask:
        resolved_query = _route_ask_to_query(ask)

    results = None
    results_evidence = None
    query_name = None

    if resolved_query == "due_soon_missing":
        query_name = "Due soon and missing required evidence"
        end = today + timedelta(days=30)
        q = select(TaskInstance).where(
            TaskInstance.due_date >= today,
            TaskInstance.due_date <= end,
            TaskInstance.status != "completed",
        )
        tasks = list(db.exec(q).all())
        results = []
        for t in tasks:
            t.template = db.get(TaskTemplate, t.template_id)
            mr, _ = compute_missing_evidence(db, t, t.template)
            if mr > 0:
                results.append(t)
    elif resolved_query == "overdue":
        query_name = "Overdue tasks"
        q = select(TaskInstance).where(
            TaskInstance.due_date < today,
            TaskInstance.status != "completed",
        )
        results = list(db.exec(q).all())
    elif resolved_query == "missing_required":
        query_name = "Tasks missing required evidence"
        all_tasks = list(db.exec(select(TaskInstance)).all())
        results = []
        for t in all_tasks:
            t.template = db.get(TaskTemplate, t.template_id)
            mr, _ = compute_missing_evidence(db, t, t.template)
            if mr > 0:
                results.append(t)
    elif resolved_query == "audit_risk":
        query_name = "Audit risk (readiness < 60)"
        all_tasks = list(db.exec(select(TaskInstance)).all())
        results = []
        for t in all_tasks:
            t.template = db.get(TaskTemplate, t.template_id)
            r = compute_audit_readiness(db, t.id)
            if r["score"] < 60:
                t.readiness_score = r["score"]
                results.append(t)
    elif resolved_query == "safe_to_delete":
        query_name = "Safe to delete this quarter"
        seed_retention_rules(db)
        items = list(db.exec(select(EvidenceItem).order_by(EvidenceItem.added_at.desc())).all())
        for e in items:
            e.task = db.get(TaskInstance, e.task_id)
            if e.task:
                e.task.template = db.get(TaskTemplate, e.task.template_id)
        results_evidence = [e for e in items if (e.keep_until and e.keep_until < today) or e.disposition == "delete_candidate"]
        if category:
            results_evidence = [e for e in results_evidence if e.category == category]
    elif resolved_query == "evidence_recent_30":
        query_name = f"Evidence added in last {days or 30} days"
        cutoff = datetime.utcnow() - timedelta(days=days or 30)
        items = list(db.exec(
            select(EvidenceItem).where(EvidenceItem.added_at >= cutoff).order_by(EvidenceItem.added_at.desc())
        ).all())
        for e in items:
            e.task = db.get(TaskInstance, e.task_id)
            if e.task:
                e.task.template = db.get(TaskTemplate, e.task.template_id)
        results_evidence = items
        if category:
            results_evidence = [e for e in results_evidence if e.category == category]

    if results is not None:
        for t in results:
            t.template = db.get(TaskTemplate, t.template_id)
    if results_evidence is not None and results is None:
        results = None  # Use results_evidence for evidence table

    categories = list({t.category for t in db.exec(select(TaskTemplate)).all()})

    return templates.TemplateResponse(
        "assistant_v2.html",
        {
            "request": request,
            "query": resolved_query,
            "query_name": query_name,
            "results": results,
            "results_evidence": results_evidence,
            "ask": ask or "",
            "days": days or 30,
            "categories": categories,
            "category_filter": category,
            "get_evidence_types": get_evidence_types,
        },
    )


# --- Retention Advisor ---
@router.get("/retention", response_class=HTMLResponse)
def retention_page(
    request: Request,
    db: Session = Depends(get_db),
    category: Optional[str] = Query(None),
    evidence_type: Optional[str] = Query(None),
    year: Optional[int] = Query(None),
):
    """Retention review dashboard: safe to delete, review soon, keep."""
    seed_retention_rules(db)
    today = date.today()
    cutoff_review = today + timedelta(days=60)
    items = list(db.exec(select(EvidenceItem).order_by(EvidenceItem.added_at.desc())).all())
    for e in items:
        e.task = db.get(TaskInstance, e.task_id)
        if e.task:
            e.task.template = db.get(TaskTemplate, e.task.template_id)
    if category and isinstance(category, str):
        items = [e for e in items if e.category == category]
    if evidence_type and isinstance(evidence_type, str):
        items = [e for e in items if evidence_type in get_evidence_types(e)]
    if year and isinstance(year, int):
        items = [e for e in items if e.task and e.task.year == year]
    safe_to_delete = [e for e in items if (e.keep_until and e.keep_until < today) or e.disposition == "delete_candidate"]
    review_soon = [e for e in items if e.review_date and today <= e.review_date <= cutoff_review and e.disposition != "delete_candidate"]
    keep = [e for e in items if e not in safe_to_delete and e not in review_soon]
    categories = list({e.category for e in items if e.category})
    return templates.TemplateResponse(
        "retention.html",
        {
            "request": request,
            "safe_to_delete": safe_to_delete,
            "review_soon": review_soon,
            "keep": keep,
            "categories": categories,
            "category_filter": category,
            "evidence_type_filter": evidence_type,
            "year_filter": year,
            "evidence_types": EVIDENCE_TYPES,
        },
    )


@router.post("/retention/bulk-action")
async def retention_bulk_action(
    request: Request,
    db: Session = Depends(get_db),
    disposition: Optional[str] = Form(None),
    review_date: Optional[str] = Form(None),
    keep_until: Optional[str] = Form(None),
):
    """Bulk update disposition, review_date, or keep_until for selected evidence items."""
    form = await request.form()
    raw = form.getlist("item_id")
    ids = [int(x) for x in raw if str(x).isdigit() and int(x) > 0]
    if not ids:
        return RedirectResponse(url="/retention", status_code=303)
    if len(ids) > 500:
        raise HTTPException(400, "Too many items selected (max 500)")
    for iid in ids:
        item = db.get(EvidenceItem, iid)
        if not item:
            continue
        if disposition and disposition in ("keep", "review", "delete_candidate"):
            item.disposition = disposition
        if review_date:
            try:
                item.review_date = date.fromisoformat(review_date)
            except ValueError:
                pass
        if keep_until:
            try:
                item.keep_until = date.fromisoformat(keep_until)
            except ValueError:
                pass
        db.add(item)
    db.commit()
    return RedirectResponse(url="/retention", status_code=303)


# --- Vault Hygiene ---
@router.get("/hygiene", response_class=HTMLResponse)
def hygiene_page(
    request: Request,
    db: Session = Depends(get_db),
    year: Optional[int] = Query(None),
):
    """Vault hygiene: orphaned evidence records and orphaned files."""
    today = date.today()
    y = year if isinstance(year, int) else today.year
    orphaned_evidence = get_orphaned_evidence(db, y)
    orphaned_files = get_orphaned_files(db, y)
    for e in orphaned_evidence:
        e.task = db.get(TaskInstance, e.task_id)
        if e.task:
            e.task.template = db.get(TaskTemplate, e.task.template_id)
    rel_paths = [str(p.relative_to(VAULT_DIR)).replace("\\", "/") for p in orphaned_files]
    return templates.TemplateResponse(
        "hygiene.html",
        {
            "request": request,
            "orphaned_evidence": orphaned_evidence,
            "orphaned_files": rel_paths,
            "year": y,
        },
    )


@router.post("/hygiene/move-orphaned-files")
async def hygiene_move_orphaned(
    request: Request,
    db: Session = Depends(get_db),
):
    """Move orphaned files to vault/_untracked/."""
    form = await request.form()
    raw = form.getlist("path")
    paths = [p for p in raw if p and isinstance(p, str)]
    if not paths:
        orphaned = get_orphaned_files(db, None)
        paths = [str(p.relative_to(VAULT_DIR)).replace("\\", "/") for p in orphaned]
    moved = move_orphaned_to_untracked(paths)
    return RedirectResponse(url=f"/hygiene?moved={moved}", status_code=303)


@router.post("/hygiene/mark-missing-evidence")
async def hygiene_mark_missing(
    request: Request,
    db: Session = Depends(get_db),
    item_id: Optional[int] = Form(None),
):
    """Mark evidence item(s) as missing (disposition=missing)."""
    form = await request.form()
    raw = form.getlist("item_id")
    ids = [int(x) for x in raw if str(x).isdigit()]
    if item_id is not None:
        ids.append(item_id)
    for iid in ids:
        item = db.get(EvidenceItem, iid)
        if item:
            item.disposition = "missing"
            db.add(item)
    db.commit()
    return RedirectResponse(url="/hygiene", status_code=303)


@router.post("/evidence/{item_id}/disposition")
def set_evidence_disposition(
    item_id: int,
    db: Session = Depends(get_db),
    disposition: str = Form(...),
    review_date: Optional[str] = Form(None),
    keep_until: Optional[str] = Form(None),
):
    """Update evidence disposition, review_date, or keep_until."""
    item = db.get(EvidenceItem, item_id)
    if not item:
        raise HTTPException(404, "Evidence not found")
    if disposition in ("keep", "review", "delete_candidate"):
        item.disposition = disposition
    if review_date:
        item.review_date = date.fromisoformat(review_date)
    if keep_until:
        item.keep_until = date.fromisoformat(keep_until)
    db.add(item)
    db.commit()
    return RedirectResponse(url=f"/retention", status_code=303)


# --- Evidence Library ---
@router.get("/evidence", response_class=HTMLResponse)
def evidence_library(
    request: Request,
    db: Session = Depends(get_db),
    category: Optional[str] = Query(None),
    evidence_type: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
):
    """Searchable evidence library."""
    items = list(db.exec(select(EvidenceItem).order_by(EvidenceItem.added_at.desc())).all())
    for e in items:
        e.task = db.get(TaskInstance, e.task_id)
        if e.task:
            e.task.template = db.get(TaskTemplate, e.task.template_id)
    if category:
        items = [e for e in items if e.category == category]
    if evidence_type:
        items = [e for e in items if evidence_type in get_evidence_types(e)]
    if search:
        s = search.lower()
        items = [e for e in items if s in (e.description or "").lower() or s in (e.original_filename or "").lower()]
    return templates.TemplateResponse(
        "evidence_library.html",
        {
            "request": request,
            "items": items,
            "categories": list({e.category for e in items if e.category}),
            "category_filter": category,
        "evidence_type_filter": evidence_type,
        "search": search,
        "evidence_types": EVIDENCE_TYPES,
        "get_evidence_types": get_evidence_types,
        },
    )


# --- Evidence Inbox ---
@router.get("/inbox", response_class=HTMLResponse)
def inbox_page(request: Request, db: Session = Depends(get_db)):
    """Evidence inbox: files in vault/_inbox/ not yet assigned."""
    files = list_inbox_files()
    today = date.today()
    tasks = list(db.exec(
        select(TaskInstance).where(TaskInstance.year == today.year).order_by(
            TaskInstance.updated_at.desc()
        ).limit(100)
    ).all())
    for t in tasks:
        t.template = db.get(TaskTemplate, t.template_id)
    return templates.TemplateResponse(
        "inbox.html",
        {
            "request": request,
            "inbox_files": files,
            "tasks": tasks,
            "evidence_types": EVIDENCE_TYPES,
            "importance_levels": IMPORTANCE_LEVELS,
        },
    )


def _validate_inbox_filename(filename: str) -> None:
    """Reject filenames that could escape the inbox directory."""
    if not filename or ".." in filename or "/" in filename or "\\" in filename:
        raise HTTPException(400, "Invalid filename")


def _sanitize_upload_filename(filename: str) -> str:
    """Strip directory components from an upload filename."""
    return Path(filename).name


@router.get("/inbox/assign", response_class=HTMLResponse)
def inbox_assign_form(
    request: Request,
    filename: str = Query(...),
    db: Session = Depends(get_db),
):
    """Form to assign inbox file to task."""
    from urllib.parse import unquote
    filename = unquote(filename)
    _validate_inbox_filename(filename)
    inbox_path = INBOX_DIR / filename
    if not inbox_path.exists():
        raise HTTPException(404, "File not found in inbox")
    today = date.today()
    tasks = list(db.exec(
        select(TaskInstance).where(TaskInstance.year == today.year).order_by(
            TaskInstance.updated_at.desc()
        ).limit(100)
    ).all())
    for t in tasks:
        t.template = db.get(TaskTemplate, t.template_id)
    return templates.TemplateResponse(
        "inbox_assign.html",
        {
            "request": request,
            "filename": filename,
            "tasks": tasks,
            "evidence_types": EVIDENCE_TYPES,
            "importance_levels": IMPORTANCE_LEVELS,
        },
    )


@router.post("/inbox/assign")
async def inbox_assign(
    request: Request,
    db: Session = Depends(get_db),
    filename: str = Form(...),
    task_id: int = Form(...),
    evidence_type: Optional[str] = Form(None),
    importance: str = Form(...),
    description: str = Form(""),
):
    """Assign inbox file to task. Moves to vault, creates EvidenceItem."""
    task = db.get(TaskInstance, task_id)
    if not task:
        raise HTTPException(404, "Task not found")
    template = db.get(TaskTemplate, task.template_id)
    form = await request.form()
    types_list = form.getlist("evidence_types")
    if not types_list and evidence_type:
        types_list = [evidence_type]
    if not types_list:
        raise HTTPException(400, "Select at least one evidence type")
    for t in types_list:
        if t not in EVIDENCE_TYPES:
            raise HTTPException(400, f"Invalid evidence type: {t}")
    if importance not in IMPORTANCE_LEVELS:
        raise HTTPException(400, "Invalid importance")
    _validate_inbox_filename(filename)
    try:
        dest_path, stored_fn, rel_path = store_evidence_from_inbox(task, template, filename)
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))
    cat = template.category if template else ""
    now = datetime.utcnow()
    primary_type = types_list[0]
    keep_until, review_date, rule_id, _ = apply_retention_rule(db, cat or "Other", primary_type, importance, now)
    item = EvidenceItem(
        task_id=task_id,
        category=cat,
        evidence_type=primary_type,
        evidence_types_json=json.dumps(types_list),
        importance=importance,
        description=description,
        original_filename=stored_fn,
        stored_filename=stored_fn,
        file_path=rel_path,
        retention_rule_id=rule_id,
        keep_until=keep_until,
        review_date=review_date,
    )
    db.add(item)
    db.commit()
    resp = RedirectResponse(url=f"/tasks/{task_id}#evidence", status_code=303)
    resp.set_cookie("last_task_id", str(task_id), max_age=86400 * 7)
    return resp


@router.post("/inbox/assign-bulk")
async def inbox_assign_bulk(
    request: Request,
    db: Session = Depends(get_db),
    task_id: int = Form(...),
    evidence_type: Optional[str] = Form(None),
    importance: str = Form("supporting"),
    description: str = Form(""),
):
    """Assign multiple inbox files to a task. Returns summary of successes and failures."""
    task = db.get(TaskInstance, task_id)
    if not task:
        raise HTTPException(404, "Task not found")
    template = db.get(TaskTemplate, task.template_id)
    form = await request.form()
    types_list = form.getlist("evidence_types")
    if not types_list and evidence_type:
        types_list = [evidence_type]
    if not types_list:
        types_list = ["other"]
    for t in types_list:
        if t not in EVIDENCE_TYPES:
            raise HTTPException(400, f"Invalid evidence type: {t}")
    if importance not in IMPORTANCE_LEVELS:
        raise HTTPException(400, "Invalid importance")
    filenames = form.getlist("filename")
    assigned = 0
    failures: list[str] = []
    for filename in filenames:
        if not filename or not filename.strip():
            continue
        try:
            _validate_inbox_filename(filename.strip())
            dest_path, stored_fn, rel_path = store_evidence_from_inbox(task, template, filename.strip())
        except FileNotFoundError:
            failures.append(filename)
            continue
        cat = template.category if template else ""
        now = datetime.utcnow()
        primary_type = types_list[0]
        keep_until, review_date, rule_id, _ = apply_retention_rule(db, cat or "Other", primary_type, importance, now)
        item = EvidenceItem(
            task_id=task_id,
            category=cat,
            evidence_type=primary_type,
            evidence_types_json=json.dumps(types_list),
            importance=importance,
            description=description,
            original_filename=stored_fn,
            stored_filename=stored_fn,
            file_path=rel_path,
            retention_rule_id=rule_id,
            keep_until=keep_until,
            review_date=review_date,
        )
        db.add(item)
        assigned += 1
    db.commit()
    params = f"assigned_count={assigned}&failed_count={len(failures)}"
    if failures:
        from urllib.parse import quote
        params += "&failures=" + quote(",".join(failures))
    resp = RedirectResponse(url=f"/inbox?{params}", status_code=303)
    resp.set_cookie("last_task_id", str(task_id), max_age=86400 * 7)
    return resp


@router.post("/inbox/delete")
def inbox_delete(filename: str = Form(...)):
    """Delete file from inbox."""
    _validate_inbox_filename(filename)
    if delete_inbox_file(filename):
        return RedirectResponse(url="/inbox", status_code=303)
    raise HTTPException(404, "File not found in inbox")


# --- Backups ---
@router.get("/backups", response_class=HTMLResponse)
def backups_page(request: Request):
    """List backups, create, restore."""
    backups = list_backups()
    return templates.TemplateResponse(
        "backups.html",
        {"request": request, "backups": backups},
    )


@router.post("/backups/create")
def backups_create():
    """Create manual backup."""
    path = create_backup()
    return RedirectResponse(url=f"/backups?created={path.name}", status_code=303)


@router.post("/backups/restore")
def backups_restore(backup_name: str = Form(...)):
    """Restore from backup. WARNING: overwrites current DB."""
    from app.database import BACKUPS_DIR
    backup_path = BACKUPS_DIR / backup_name
    if not backup_path.exists() or not backup_path.is_dir():
        raise HTTPException(404, "Backup not found")
    try:
        restore_backup(backup_path)
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))
    return RedirectResponse(url="/today?restored=1", status_code=303)


# --- Audit Packet Export ---
@router.post("/tasks/{task_id}/export")
def export_task_audit_packet(
    task_id: int,
    db: Session = Depends(get_db),
    include_nice_to_have: bool = Form(False),
    include_generated: bool = Form(False),
):
    """Export task audit packet: folder + index.html."""
    from app.export import export_task_packet
    task = db.get(TaskInstance, task_id)
    if not task:
        raise HTTPException(404, "Task not found")
    task.template = db.get(TaskTemplate, task.template_id)
    evidence = list(db.exec(select(EvidenceItem).where(EvidenceItem.task_id == task_id)).all())
    out_path = export_task_packet(task, evidence, db, include_nice_to_have, include_generated)
    return RedirectResponse(url=f"/tasks/{task_id}?exported={out_path.name}", status_code=303)


# --- Document Generation ---
@router.get("/tasks/{task_id}/docs", response_class=HTMLResponse)
def docs_home(request: Request, task_id: int, db: Session = Depends(get_db)):
    """Document generation hub for a task."""
    task = db.get(TaskInstance, task_id)
    if not task:
        raise HTTPException(404, "Task not found")
    task.template = db.get(TaskTemplate, task.template_id)
    return templates.TemplateResponse(
        "docs/docs_home.html",
        {
            "request": request,
            "task": task,
            "pdf_available": is_pdf_available(),
            "pdf_backend": get_pdf_backend(),
        },
    )


@router.get("/tasks/{task_id}/docs/cover", response_class=HTMLResponse)
def docs_cover_html(request: Request, task_id: int, db: Session = Depends(get_db)):
    """Preview cover sheet as HTML."""
    task = db.get(TaskInstance, task_id)
    if not task:
        raise HTTPException(404, "Task not found")
    task.template = db.get(TaskTemplate, task.template_id)
    ctx = build_cover_sheet_context(db, task, task.template)
    html = templates.env.get_template("docs/cover_sheet.html").render(**ctx)
    return HTMLResponse(content=html)


@router.post("/tasks/{task_id}/docs/cover/pdf")
def docs_cover_pdf(task_id: int, db: Session = Depends(get_db)):
    """Generate cover sheet PDF, save to vault, add as EvidenceItem."""
    task = db.get(TaskInstance, task_id)
    if not task:
        raise HTTPException(404, "Task not found")
    task.template = db.get(TaskTemplate, task.template_id)
    ctx = build_cover_sheet_context(db, task, task.template)
    html = templates.env.get_template("docs/cover_sheet.html").render(**ctx)
    dest, rel_path = write_pdf_and_register(
        html, task, task.template, "cover_sheet", "cover_sheet", db, evidence_type="other"
    )
    return RedirectResponse(url=f"/vault/{rel_path}", status_code=303)


@router.get("/tasks/{task_id}/docs/memo/edit", response_class=HTMLResponse)
def docs_memo_edit(request: Request, task_id: int, db: Session = Depends(get_db)):
    """Edit memo form."""
    task = db.get(TaskInstance, task_id)
    if not task:
        raise HTTPException(404, "Task not found")
    task.template = db.get(TaskTemplate, task.template_id)
    memo_doc = get_or_create_memo_doc(db, task_id)
    content = load_memo_content(memo_doc)
    ctx = build_memo_context(db, task, task.template, content)
    content = ctx  # use full context for form defaults
    return templates.TemplateResponse(
        "docs/memo_edit.html",
        {"request": request, "task": task, "content": content},
    )


@router.post("/tasks/{task_id}/docs/memo/save")
def docs_memo_save(
    task_id: int,
    db: Session = Depends(get_db),
    date: str = Form(""),
    context: str = Form(""),
    actions_taken: str = Form(""),
    decision: str = Form(""),
    risks: str = Form(""),
):
    """Save memo content to DB."""
    task = db.get(TaskInstance, task_id)
    if not task:
        raise HTTPException(404, "Task not found")
    content = {"date": date or "", "context": context, "actions_taken": actions_taken, "decision": decision, "risks": risks}
    save_memo_content(db, task_id, content)
    return RedirectResponse(url=f"/tasks/{task_id}/docs/memo/edit", status_code=303)


@router.get("/tasks/{task_id}/docs/memo", response_class=HTMLResponse)
def docs_memo_html(request: Request, task_id: int, db: Session = Depends(get_db)):
    """Preview memo as HTML."""
    task = db.get(TaskInstance, task_id)
    if not task:
        raise HTTPException(404, "Task not found")
    task.template = db.get(TaskTemplate, task.template_id)
    memo_doc = get_or_create_memo_doc(db, task_id)
    content = load_memo_content(memo_doc)
    ctx = build_memo_context(db, task, task.template, content)
    html = templates.env.get_template("docs/memo.html").render(**ctx)
    return HTMLResponse(content=html)


@router.post("/tasks/{task_id}/docs/memo/pdf")
def docs_memo_pdf(task_id: int, db: Session = Depends(get_db)):
    """Generate memo PDF, save to vault, add as EvidenceItem."""
    task = db.get(TaskInstance, task_id)
    if not task:
        raise HTTPException(404, "Task not found")
    task.template = db.get(TaskTemplate, task.template_id)
    memo_doc = get_or_create_memo_doc(db, task_id)
    content = load_memo_content(memo_doc)
    ctx = build_memo_context(db, task, task.template, content)
    html = templates.env.get_template("docs/memo.html").render(**ctx)
    dest, rel_path = write_pdf_and_register(
        html, task, task.template, "memo", "compliance_memo", db, evidence_type="communication"
    )
    return RedirectResponse(url=f"/vault/{rel_path}", status_code=303)


@router.get("/tasks/{task_id}/docs/evidence", response_class=HTMLResponse)
def docs_evidence_html(request: Request, task_id: int, db: Session = Depends(get_db)):
    """Preview evidence index as HTML."""
    task = db.get(TaskInstance, task_id)
    if not task:
        raise HTTPException(404, "Task not found")
    task.template = db.get(TaskTemplate, task.template_id)
    ctx = build_evidence_index_context(db, task, task.template)
    ctx["base_url"] = "/vault"  # for links in HTML preview
    html = templates.env.get_template("docs/evidence_index.html").render(**ctx)
    return HTMLResponse(content=html)


@router.post("/tasks/{task_id}/docs/evidence/pdf")
def docs_evidence_pdf(task_id: int, db: Session = Depends(get_db)):
    """Generate evidence index PDF, save to vault, add as EvidenceItem."""
    task = db.get(TaskInstance, task_id)
    if not task:
        raise HTTPException(404, "Task not found")
    task.template = db.get(TaskTemplate, task.template_id)
    ctx = build_evidence_index_context(db, task, task.template)
    ctx["base_url"] = None  # no links in PDF
    html = templates.env.get_template("docs/evidence_index.html").render(**ctx)
    dest, rel_path = write_pdf_and_register(
        html, task, task.template, "evidence_index", "evidence_index", db, evidence_type="source_data"
    )
    return RedirectResponse(url=f"/vault/{rel_path}", status_code=303)


# --- Memo Draft ---
@router.get("/tasks/{task_id}/memo/draft", response_class=HTMLResponse)
def memo_draft_page(
    request: Request,
    task_id: int,
    db: Session = Depends(get_db),
    include_more: Optional[str] = Query(None),
):
    """Show draft compliance memo from task data. User can edit and save."""
    task = db.get(TaskInstance, task_id)
    if not task:
        raise HTTPException(404, "Task not found")
    task.template = db.get(TaskTemplate, task.template_id)
    draft = generate_memo_draft(db, task_id, include_more_detail=(include_more or "").lower() == "true")
    return templates.TemplateResponse(
        "memo_draft.html",
        {"request": request, "task": task, "draft": draft},
    )


@router.post("/tasks/{task_id}/memo/draft/save")
def memo_draft_save(
    task_id: int,
    db: Session = Depends(get_db),
    date: str = Form(""),
    context: str = Form(""),
    actions_taken: str = Form(""),
    decision: str = Form(""),
    risks: str = Form(""),
):
    """Save draft to memo storage, redirect to memo edit."""
    task = db.get(TaskInstance, task_id)
    if not task:
        raise HTTPException(404, "Task not found")
    content = {"date": date or "", "context": context, "actions_taken": actions_taken, "decision": decision, "risks": risks}
    save_memo_content(db, task_id, content)
    return RedirectResponse(url=f"/tasks/{task_id}/docs/memo/edit", status_code=303)


# --- Claims Dashboard ---
@router.get("/claims", response_class=HTMLResponse)
def claims_page(
    request: Request,
    db: Session = Depends(get_db),
    year: Optional[int] = Query(None),
):
    """Claims dashboard: monthly reimbursement, participation, trends."""
    today = date.today()
    y = year if isinstance(year, int) else today.year
    data = get_monthly_claim_data(db, y)
    metrics = compute_participation_metrics(db, y)
    comparison = compare_to_last_year(db, y)
    last_year_data = get_monthly_claim_data(db, y - 1)
    last_by_month = {d["month"]: d for d in last_year_data}
    return templates.TemplateResponse(
        "claims.html",
        {
            "request": request,
            "year": y,
            "data": data,
            "metrics": metrics,
            "comparison": comparison,
            "last_by_month": last_by_month,
        },
    )


@router.get("/exports/claims.csv")
def export_claims_csv(
    db: Session = Depends(get_db),
    year: Optional[int] = Query(None),
):
    """Stream claims CSV."""
    today = date.today()
    y = year if isinstance(year, int) else today.year
    data = get_monthly_claim_data(db, y)
    headers = ["year", "month", "reimbursement", "free_meals", "reduced_meals", "paid_meals", "breakfast_meals", "adp"]
    rows = [[d["year"], d["month"] or "", d["reimbursement"], d["free_meals"], d["reduced_meals"], d["paid_meals"], d["breakfast_meals"], d["adp"]] for d in data]
    return StreamingResponse(
        _csv_stream(rows, headers),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=claims_{y}.csv"},
    )


# --- CSV Exports ---
@router.get("/exports", response_class=HTMLResponse)
def exports_page(
    request: Request,
    db: Session = Depends(get_db),
    year: Optional[int] = Query(None),
    category: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    evidence_type: Optional[str] = Query(None),
):
    """CSV exports page: tasks, evidence, retention."""
    today = date.today()
    y = year if isinstance(year, int) else today.year
    categories = list({t.category for t in db.exec(select(TaskTemplate)).all()})
    evidence_types = list(EVIDENCE_TYPES)
    return templates.TemplateResponse(
        "exports.html",
        {
            "request": request,
            "year": y,
            "category": category,
            "status": status,
            "evidence_type": evidence_type,
            "categories": categories,
            "evidence_types": evidence_types,
        },
    )


_CSV_INJECTION_CHARS = frozenset(("=", "+", "-", "@", "\t", "\r"))


def _csv_safe(val: object) -> str:
    """Prefix formula-triggering characters to prevent CSV injection."""
    s = str(val)
    if s and s[0] in _CSV_INJECTION_CHARS:
        return "'" + s
    return s


def _csv_stream(rows: list, headers: list[str]):
    """Yield CSV lines as bytes."""
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(headers)
    yield buf.getvalue().encode("utf-8")
    buf.seek(0)
    buf.truncate(0)
    for row in rows:
        w.writerow(row)
        yield buf.getvalue().encode("utf-8")
        buf.seek(0)
        buf.truncate(0)


@router.get("/exports/tasks.csv")
def export_tasks_csv(
    db: Session = Depends(get_db),
    year: Optional[int] = Query(None),
    category: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
):
    """Stream tasks CSV."""
    today = date.today()
    y = year if isinstance(year, int) else today.year
    q = select(TaskInstance).where(TaskInstance.year == y)
    instances = list(db.exec(q).all())
    headers = ["task_id", "title", "category", "due_date", "status", "readiness_score", "missing_required_count", "missing_supporting_count", "has_memo", "evidence_count"]
    rows = []
    for t in instances:
        t.template = db.get(TaskTemplate, t.template_id)
        r = compute_audit_readiness(db, t.id)
        mr, ms = compute_missing_evidence(db, t, t.template)
        ev_count = len(list(db.exec(select(EvidenceItem).where(EvidenceItem.task_id == t.id)).all()))
        title = f"{t.template.name if t.template else 'Task'}" + (f" - {t.year}-{t.month:02d}" if t.month else f" ({t.year})")
        rows.append([
            t.id,
            _csv_safe(title),
            _csv_safe(t.template.category if t.template else ""),
            str(t.due_date) if t.due_date else "",
            _csv_safe(t.status),
            r.get("score", 0),
            r.get("required_missing_count", mr),
            r.get("supporting_missing_count", ms),
            "yes" if r.get("has_memo") else "no",
            ev_count,
        ])
    if category and isinstance(category, str):
        rows = [r for r in rows if r[2] == category]
    if status and isinstance(status, str):
        rows = [r for r in rows if r[4] == status]
    return StreamingResponse(
        _csv_stream(rows, headers),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=tasks.csv"},
    )


@router.get("/exports/evidence.csv")
def export_evidence_csv(
    db: Session = Depends(get_db),
    year: Optional[int] = Query(None),
    category: Optional[str] = Query(None),
    evidence_type: Optional[str] = Query(None),
):
    """Stream evidence CSV."""
    today = date.today()
    y = year if isinstance(year, int) else today.year
    items = list(db.exec(select(EvidenceItem).order_by(EvidenceItem.added_at.desc())).all())
    for e in items:
        e.task = db.get(TaskInstance, e.task_id)
        if e.task:
            e.task.template = db.get(TaskTemplate, e.task.template_id)
    items = [e for e in items if e.task and e.task.year == y]
    if category and isinstance(category, str):
        items = [e for e in items if e.category == category]
    if evidence_type and isinstance(evidence_type, str):
        items = [e for e in items if evidence_type in get_evidence_types(e)]
    headers = ["evidence_id", "task_id", "task_title", "category", "evidence_type", "importance", "original_filename", "stored_filename", "added_at", "keep_until", "review_date", "disposition"]
    rows = []
    for e in items:
        task_title = f"{e.task.template.name if e.task and e.task.template else 'Task'}" + (f" - {e.task.year}-{e.task.month:02d}" if e.task and e.task.month else f" ({e.task.year})" if e.task else "")
        rows.append([
            e.id,
            e.task_id,
            _csv_safe(task_title),
            _csv_safe(e.category),
            _csv_safe(",".join(get_evidence_types(e))),
            _csv_safe(e.importance),
            _csv_safe(e.original_filename),
            _csv_safe(e.stored_filename),
            str(e.added_at) if e.added_at else "",
            str(e.keep_until) if e.keep_until else "",
            str(e.review_date) if e.review_date else "",
            _csv_safe(e.disposition),
        ])
    return StreamingResponse(
        _csv_stream(rows, headers),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=evidence.csv"},
    )


@router.get("/exports/retention.csv")
def export_retention_csv(
    db: Session = Depends(get_db),
    year: Optional[int] = Query(None),
):
    """Stream retention CSV (review soon + safe to delete)."""
    seed_retention_rules(db)
    today = date.today()
    y = year if isinstance(year, int) else today.year
    cutoff_review = today + timedelta(days=60)
    items = list(db.exec(select(EvidenceItem).order_by(EvidenceItem.added_at.desc())).all())
    for e in items:
        e.task = db.get(TaskInstance, e.task_id)
        if e.task:
            e.task.template = db.get(TaskTemplate, e.task.template_id)
    safe = [e for e in items if ((e.keep_until and e.keep_until < today) or e.disposition == "delete_candidate") and e.task and e.task.year == y]
    review = [e for e in items if e.review_date and today <= e.review_date <= cutoff_review and e.disposition != "delete_candidate" and e.task and e.task.year == y]
    combined = safe + review
    headers = ["evidence_id", "task_id", "task_title", "category", "evidence_type", "original_filename", "keep_until", "review_date", "disposition", "status"]
    rows = []
    for e in combined:
        task_title = f"{e.task.template.name if e.task and e.task.template else 'Task'}" + (f" ({e.task.year})" if e.task else "")
        status = "safe_to_delete" if e in safe else "review_soon"
        rows.append([
            e.id,
            e.task_id,
            task_title,
            e.category,
            ",".join(get_evidence_types(e)),
            e.original_filename,
            str(e.keep_until) if e.keep_until else "",
            str(e.review_date) if e.review_date else "",
            e.disposition,
            status,
        ])
    return StreamingResponse(
        _csv_stream(rows, headers),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=retention.csv"},
    )


@router.get("/exports/trends.csv")
def export_trends_csv(
    db: Session = Depends(get_db),
    year: Optional[int] = Query(None),
    baseline: Optional[int] = Query(None),
):
    """Stream trends CSV: category-level comparison (year vs baseline)."""
    today = date.today()
    y = year if isinstance(year, int) else today.year
    b = baseline if isinstance(baseline, int) else y - 1
    cat_year = aggregate_by_category(db, y)
    cat_baseline = aggregate_by_category(db, b)
    cat_baseline_map = {r["category"]: r for r in cat_baseline}
    rows = []
    for c in cat_year:
        base = cat_baseline_map.get(c["category"], {})
        row = compare_years(c, base)
        row["baseline_completion_rate"] = base.get("completion_rate", 0)
        row["baseline_avg_readiness"] = base.get("avg_readiness", 0)
        row["baseline_total_tasks"] = base.get("total_tasks", 0)
        rows.append([
            row.get("category", ""),
            y,
            b,
            row.get("total_tasks", 0),
            row.get("completion_rate", 0),
            row.get("avg_readiness", 0),
            row.get("pct_missing_required", 0),
            row.get("avg_evidence_count", 0),
            row.get("memo_coverage_rate", 0),
            row.get("completion_rate_delta", ""),
            row.get("avg_readiness_delta", ""),
            row.get("pct_missing_required_delta", ""),
            row.get("avg_evidence_count_delta", ""),
            row.get("memo_coverage_rate_delta", ""),
            row.get("baseline_total_tasks", 0),
            row.get("baseline_completion_rate", 0),
            row.get("baseline_avg_readiness", 0),
        ])
    headers = [
        "category", "year", "baseline", "total_tasks", "completion_rate", "avg_readiness",
        "pct_missing_required", "avg_evidence_count", "memo_coverage_rate",
        "completion_rate_delta", "avg_readiness_delta", "pct_missing_required_delta",
        "avg_evidence_count_delta", "memo_coverage_rate_delta",
        "baseline_total_tasks", "baseline_completion_rate", "baseline_avg_readiness",
    ]
    return StreamingResponse(
        _csv_stream(rows, headers),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=trends.csv"},
    )


@router.get("/export", response_class=HTMLResponse)
def export_page(
    request: Request,
    db: Session = Depends(get_db),
    year: Optional[int] = Query(None),
    category: Optional[str] = Query(None),
):
    """Export year/category audit packet."""
    today = date.today()
    y = year if isinstance(year, int) else today.year
    categories = list({t.category for t in db.exec(select(TaskTemplate)).all()})
    return templates.TemplateResponse(
        "export.html",
        {"request": request, "year": y, "category": category, "categories": categories, "error": None},
    )


@router.post("/export")
def export_year_category(
    request: Request,
    db: Session = Depends(get_db),
    year: int = Form(...),
    category: str = Form(...),
    include_generated: bool = Form(False),
):
    """Export year+category audit packet."""
    from app.export import export_year_category_packet
    try:
        out_path = export_year_category_packet(db, year, category, include_generated)
        return RedirectResponse(url=f"/export?year={year}&category={category}&exported={out_path.name}", status_code=303)
    except ValueError as e:
        return templates.TemplateResponse(
            "export.html",
            {
                "request": request,
                "year": year,
                "category": category,
                "categories": list({t.category for t in db.exec(select(TaskTemplate)).all()}),
                "error": str(e),
            },
        )
