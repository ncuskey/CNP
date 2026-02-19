"""
OCR and text extraction from claim PDFs.
Extracts meal counts, reimbursement amounts, and other claim data for the claims dashboard.
"""
import re
from pathlib import Path
from typing import Any, Optional

# PyMuPDF for PDF text extraction and page rendering
import fitz  # pymupdf


def extract_text_from_pdf(file_path: Path) -> str:
    """
    Extract text from PDF. Uses PyMuPDF for embedded text.
    Falls back to OCR (pytesseract) if no text found (scanned PDFs).
    """
    if not file_path.exists() or not file_path.suffix.lower() == ".pdf":
        return ""

    try:
        doc = fitz.open(file_path)
        all_text = []
        for page_num in range(len(doc)):
            page = doc.load_page(page_num)
            text = page.get_text()
            all_text.append(text)
        doc.close()
        full_text = "\n".join(all_text).strip()

        # If very little text, try OCR (scanned PDF)
        if len(full_text.replace(" ", "")) < 50:
            full_text = _ocr_pdf(file_path) or full_text

        return full_text
    except Exception:
        return ""


def _ocr_pdf(file_path: Path) -> Optional[str]:
    """OCR scanned PDF pages using pytesseract. Requires Tesseract OCR installed on system."""
    try:
        import pytesseract
        from PIL import Image
    except ImportError:
        return None

    try:
        pytesseract.get_tesseract_version()  # Raises if Tesseract not installed
    except Exception:
        return None

    try:
        doc = fitz.open(file_path)
        all_text = []
        for page_num in range(len(doc)):
            page = doc.load_page(page_num)
            pix = page.get_pixmap(dpi=150)
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            text = pytesseract.image_to_string(img)
            all_text.append(text)
        doc.close()
        return "\n".join(all_text).strip() or None
    except Exception:
        return None


def _norm_num(s: str) -> str:
    """Normalize number string: strip commas, return digits only for ints."""
    return s.replace(",", "").strip()


def parse_claim_text(text: str) -> dict[str, Any]:
    """
    Parse extracted text into claim field values.
    Idaho CNP format: "Claim Reimbursement Total 69,911.71", "Free 9,094", "Date Received 02/02/2026".
    Returns dict suitable for save_task_data: {field_key: value}.
    """
    if not text:
        return {}

    result: dict[str, Any] = {}
    text_lower = text.lower()
    lines = text.replace("\r", "\n").split("\n")

    # --- Idaho CNP / NSLP Claim Summary format ---
    # "Net Claim Reimbursement Total 69,911.71" or "Claim Reimbursement Total 69,911.71"
    for pat in [
        r"Net\s+Claim\s+Reimbursement\s+Total\s+([\d,]+\.\d{2})",
        r"Claim\s+Reimbursement\s+Total\s+([\d,]+\.\d{2})",
        r"Current\s+Claim\s+Reimbursement\s+Total\s+([\d,]+\.\d{2})",
    ]:
        m = re.search(pat, text, re.I)
        if m:
            val = _norm_num(m.group(1))
            try:
                result["total_reimbursement"] = str(round(float(val), 2))
                break
            except ValueError:
                pass

    # NSLP section: "Free 9,094", "Reduced 2,613", "Paid 8,798" (numbers may have commas)
    for label, key in [("Free", "free_meals"), ("Reduced", "reduced_meals"), ("Paid", "paid_meals")]:
        if key not in result:
            m = re.search(rf"\b{label}\b\s+([\d,]+)(?:\s|$)", text)
            if m:
                result[key] = _norm_num(m.group(1))

    # Breakfast: sum "School Breakfast Program" Total 783 + "Severe Need" Total 4,765
    if "breakfast_meals" not in result:
        breakfast_totals = re.findall(
            r"School\s+Breakfast\s+Program(?:\s+Severe\s+Need)?\s+.*?Total\s+([\d,]+)", text, re.S
        )
        if breakfast_totals:
            total = sum(int(_norm_num(t)) for t in breakfast_totals)
            result["breakfast_meals"] = str(total)

    # ADP: Average Daily Participation - if present
    if "adp" not in result:
        m = re.search(r"\bADP\b[:\s]*([\d,]+)", text, re.I)
        if m:
            result["adp"] = _norm_num(m.group(1))

    # Dates: Idaho format has "Date\nReceived" and dates on next row: 02/02/2026, 02/02/2026, 02/03/2026
    def _parse_date(raw: str) -> str:
        if "/" in raw:
            parts = raw.split("/")
            if len(parts) == 3:
                mth, day, yr = parts[0].zfill(2), parts[1].zfill(2), parts[2]
                if len(yr) == 2:
                    yr = "20" + yr
                return f"{yr}-{mth}-{day}"
        return raw

    if "claim_submitted_date" not in result:
        m = re.search(r"Date\s+Received\s+(\d{1,2}/\d{1,2}/\d{4})", text, re.I)
        if m:
            result["claim_submitted_date"] = _parse_date(m.group(1))
    if "claim_submitted_date" not in result:
        dates = re.findall(r"(\d{1,2}/\d{1,2}/\d{4})", text)
        if dates:
            result["claim_submitted_date"] = _parse_date(dates[0])
    if "claim_approved_date" not in result:
        m = re.search(r"Date\s+(?:Accepted|Processed)\s+(\d{1,2}/\d{1,2}/\d{4})", text, re.I)
        if m:
            result["claim_approved_date"] = _parse_date(m.group(1))
    if "claim_approved_date" not in result:
        dates = re.findall(r"(\d{1,2}/\d{1,2}/\d{4})", text)
        if len(dates) >= 2:
            result["claim_approved_date"] = _parse_date(dates[1])

    # Adjustment: "Adjustment Number 0" = no adjustments; "Original" in Reason Code = no adjustments
    if "adjustments_required" not in result:
        m = re.search(r"Adjustment\s+Number\s+(\d+)", text, re.I)
        if m:
            result["adjustments_required"] = "0" if m.group(1) == "0" else "1"
    if "adjustments_required" not in result or result.get("adjustments_required") == "1":
        if re.search(r"\bOriginal\b", text, re.I):
            result["adjustments_required"] = "0"

    # --- Fallback: generic patterns ---
    if "total_reimbursement" not in result:
        for pat in [
            r"total\s*reimbursement[:\s]*\$?([\d,]+\.?\d*)",
            r"reimbursement[:\s]*\$?([\d,]+\.?\d*)",
            r"\$\s*([\d,]+\.\d{2})",
        ]:
            m = re.search(pat, text_lower, re.I)
            if m:
                val = _norm_num(m.group(1))
                try:
                    result["total_reimbursement"] = str(round(float(val), 2))
                    break
                except ValueError:
                    pass

    for line in lines:
        for label, key in [("free", "free_meals"), ("reduced", "reduced_meals"), ("paid", "paid_meals")]:
            if key not in result:
                m = re.search(rf"\b{label}\b[:\s]*([\d,]+)", line, re.I)
                if m:
                    result[key] = _norm_num(m.group(1))

    if "claim_submitted_date" not in result:
        m = re.search(r"submitted?[:\s]*(\d{1,2}/\d{1,2}/\d{4})", text_lower, re.I)
        if m:
            result["claim_submitted_date"] = _parse_date(m.group(1))
    if "claim_approved_date" not in result:
        m = re.search(r"approved?[:\s]*(\d{1,2}/\d{1,2}/\d{4})", text_lower, re.I)
        if m:
            result["claim_approved_date"] = _parse_date(m.group(1))

    return result


def extract_claim_data_from_pdf(file_path: Path) -> dict[str, Any]:
    """
    Extract text from PDF and parse into claim data dict.
    Returns {field_key: value} for TaskDataValue.
    """
    text = extract_text_from_pdf(file_path)
    return parse_claim_text(text)
