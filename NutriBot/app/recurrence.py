"""
Recurrence engine for computing due dates from template rules.
Supports: ANNUAL:MM-DD, MONTHLY:DD, MONTHLY:NEXT:DD, ONCE:YYYY-MM-DD
"""
import re
from datetime import date
from typing import Optional


def parse_recurrence_rule(rule: Optional[str]) -> tuple[str, Optional[dict]]:
    """
    Parse recurrence rule. Returns (rule_type, params) or ("", None) if invalid/blank.
    rule_type: "ANNUAL", "MONTHLY", "ONCE", or ""
    params: {"month": M, "day": D} for ANNUAL; {"day": D} for MONTHLY; {"date": date} for ONCE
    """
    if not rule or not rule.strip():
        return "", None

    rule = rule.strip().upper()

    # ANNUAL:MM-DD
    m = re.match(r"^ANNUAL:(\d{1,2})-(\d{1,2})$", rule)
    if m:
        month, day = int(m.group(1)), int(m.group(2))
        if 1 <= month <= 12 and 1 <= day <= 31:
            return "ANNUAL", {"month": month, "day": day}
        return "", None

    # MONTHLY:DD — due on day DD of the same month
    m = re.match(r"^MONTHLY:(\d{1,2})$", rule)
    if m:
        day = int(m.group(1))
        if 1 <= day <= 31:
            return "MONTHLY", {"day": day}
        return "", None

    # MONTHLY:NEXT:DD — due on day DD of the following month (e.g., Jan claim due Feb 10)
    m = re.match(r"^MONTHLY:NEXT:(\d{1,2})$", rule)
    if m:
        day = int(m.group(1))
        if 1 <= day <= 31:
            return "MONTHLY_NEXT", {"day": day}
        return "", None

    # ONCE:YYYY-MM-DD
    m = re.match(r"^ONCE:(\d{4})-(\d{1,2})-(\d{1,2})$", rule)
    if m:
        try:
            d = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            return "ONCE", {"date": d}
        except ValueError:
            return "", None

    return "", None


def compute_due_date(rule: Optional[str], year: int, month: Optional[int] = None) -> Optional[date]:
    """
    Compute due date for a given year (and optionally month for MONTHLY).
    - ANNUAL:MM-DD -> date(year, MM, DD)
    - MONTHLY:DD -> date(year, month, DD) if month provided; else None
    - ONCE:YYYY-MM-DD -> that exact date (year param ignored)
    - blank -> None
    """
    rule_type, params = parse_recurrence_rule(rule)
    if not params:
        return None

    if rule_type == "ANNUAL":
        return date(year, params["month"], params["day"])
    if rule_type == "MONTHLY":
        if month is not None and 1 <= month <= 12:
            # Handle day overflow (e.g., day 31 in Feb)
            day = min(params["day"], 28 if month == 2 else (30 if month in (4, 6, 9, 11) else 31))
            return date(year, month, day)
        return None
    if rule_type == "MONTHLY_NEXT":
        if month is not None and 1 <= month <= 12:
            # Due on day DD of the following month (Jan claim → Feb 10)
            next_month = month + 1 if month < 12 else 1
            next_year = year if month < 12 else year + 1
            day = min(params["day"], 28 if next_month == 2 else (30 if next_month in (4, 6, 9, 11) else 31))
            return date(next_year, next_month, day)
        return None
    if rule_type == "ONCE":
        return params["date"]
    return None


def validate_recurrence_rule(rule: Optional[str]) -> tuple[bool, str]:
    """
    Validate recurrence rule. Returns (valid, error_message).
    """
    if not rule or not rule.strip():
        return True, ""  # blank is allowed

    rule_type, params = parse_recurrence_rule(rule)
    if rule_type:
        return True, ""

    # Provide helpful error
    r = (rule or "").strip().upper()
    if r.startswith("ANNUAL:"):
        return False, "ANNUAL format: ANNUAL:MM-DD (e.g., ANNUAL:10-01)"
    if r.startswith("MONTHLY:"):
        return False, "MONTHLY format: MONTHLY:DD or MONTHLY:NEXT:DD (e.g., MONTHLY:10, MONTHLY:NEXT:10)"
    if r.startswith("ONCE:"):
        return False, "ONCE format: ONCE:YYYY-MM-DD (e.g., ONCE:2026-07-15)"
    return False, "Supported: ANNUAL:MM-DD, MONTHLY:DD, MONTHLY:NEXT:DD, ONCE:YYYY-MM-DD (or blank)"


def get_monthly_due_dates(rule: Optional[str], year: int) -> list[tuple[int, date]]:
    """
    For MONTHLY or MONTHLY_NEXT rules, return list of (month, due_date) for all 12 months.
    Returns [] if not a MONTHLY rule.
    - MONTHLY:DD → due on day DD of same month
    - MONTHLY:NEXT:DD → due on day DD of following month (Jan claim → Feb 10)
    """
    rule_type, params = parse_recurrence_rule(rule)
    if rule_type not in ("MONTHLY", "MONTHLY_NEXT") or not params:
        return []

    result = []
    day = params["day"]
    for month in range(1, 13):
        try:
            d = compute_due_date(rule, year, month)
            if d:
                result.append((month, d))
        except (ValueError, TypeError):
            pass
    return result
