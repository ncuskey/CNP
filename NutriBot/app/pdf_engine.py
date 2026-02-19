"""
PDF engine abstraction: HTML → PDF.
Tries WeasyPrint first; falls back to ReportLab if needed.
"""
from pathlib import Path
from typing import Optional

PDF_AVAILABLE = False
PDF_BACKEND = "none"


def _try_weasyprint() -> bool:
    """Try to use WeasyPrint for HTML→PDF."""
    try:
        from weasyprint import HTML
        from weasyprint import __version__  # noqa: F401
        return True
    except (ImportError, OSError):
        # OSError when WeasyPrint is installed but system libs (GTK/Pango) are missing (e.g. Windows)
        return False


def _try_reportlab() -> bool:
    """ReportLab is usually available; used as fallback."""
    try:
        from reportlab.lib.pagesizes import letter
        from reportlab.pdfgen import canvas
        return True
    except ImportError:
        return False


def _init_backend() -> tuple[bool, str]:
    """Determine which PDF backend is available."""
    if _try_weasyprint():
        return True, "weasyprint"
    if _try_reportlab():
        return True, "reportlab"
    return False, "none"


PDF_AVAILABLE, PDF_BACKEND = _init_backend()


def render_html_to_pdf(html: str, output_path: str) -> None:
    """
    Render HTML string to PDF file.
    Raises RuntimeError with install guidance if no backend available.
    """
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    if PDF_BACKEND == "weasyprint":
        from weasyprint import HTML
        from io import BytesIO
        doc = HTML(string=html)
        doc.write_pdf(path)
        return

    if PDF_BACKEND == "reportlab":
        _render_reportlab_fallback(html, str(path))
        return

    raise RuntimeError(
        "No PDF backend available. Install one:\n"
        "  pip install weasyprint   # Recommended: HTML/CSS → PDF\n"
        "  pip install reportlab    # Fallback: basic HTML rendering\n"
        "WeasyPrint may need system deps on Windows: see https://doc.courtbouillon.org/weasyprint/"
    )


def _render_reportlab_fallback(html: str, output_path: str) -> None:
    """Minimal ReportLab fallback: strip HTML and render as text."""
    import re
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas
    from reportlab.lib.units import inch

    # Strip tags
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        text = "(No content)"

    c = canvas.Canvas(output_path, pagesize=letter)
    width, height = letter
    margin = inch
    y = height - margin
    line_height = 14
    max_chars = 80

    def wrap(s: str) -> list[str]:
        words = s.split()
        lines = []
        cur = ""
        for w in words:
            if len(cur) + len(w) + 1 <= max_chars:
                cur += (" " if cur else "") + w
            else:
                if cur:
                    lines.append(cur)
                cur = w
        if cur:
            lines.append(cur)
        return lines

    for para in text.split(". "):
        para = para.strip() + "."
        for line in wrap(para):
            if y < margin:
                c.showPage()
                y = height - margin
            c.drawString(margin, y, line[:max_chars])
            y -= line_height
    c.save()


def is_pdf_available() -> bool:
    """Check if PDF generation is available."""
    return PDF_AVAILABLE


def get_pdf_backend() -> str:
    """Return current backend name."""
    return PDF_BACKEND
