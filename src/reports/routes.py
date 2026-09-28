"""Reports routes — Phase 4, Tasks 62-63.

HTML report viewer + CSV / PDF / Excel download endpoints.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from config.settings import settings
from database.base import get_session
from src.auth.dependencies import get_current_user, require_role
from src.auth.models import User
from src.reports.service import ReportService

router = APIRouter(tags=["reports"])
templates = Jinja2Templates(directory=str(settings.project_root / "templates"))

_VALID_TYPES = {"progress", "coverage", "hallucination", "traceability", "comparison", "audit"}


@router.get("/reports", response_class=HTMLResponse)
def reports_page(
    request: Request,
    type: str = "progress",
    plan_id: int | None = None,
    session: Session = Depends(get_session),
    user: User = Depends(require_role("Admin", "Training Manager", "Reviewer", "Manager")),
) -> HTMLResponse:
    """Render the reports overview page with tabular data and optional chart."""
    report_type = type if type in _VALID_TYPES else "progress"
    service = ReportService(session)
    data = service.get_report(report_type)
    return templates.TemplateResponse(
        request=request,
        name="report_view.html",
        context={
            "user": user,
            "report_type": report_type,
            "report_title": data["title"],
            "columns": data["columns"],
            "rows": data["rows"],
            "chart_json": data.get("chart_json"),
        },
    )


@router.get("/reports/export/csv")
def export_csv(
    type: str = "progress",
    session: Session = Depends(get_session),
    user: User = Depends(require_role("Admin", "Training Manager", "Reviewer", "Manager")),
) -> Response:
    """Download report as CSV.

    Args:
        type: Report type key (progress|coverage|hallucination|traceability|comparison|audit).
    """
    report_type = type if type in _VALID_TYPES else "progress"
    service = ReportService(session)
    data = service.export_csv(report_type)
    filename = f"skillsprint_{report_type}_{_ts()}.csv"
    return Response(
        content=data,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get("/reports/export/pdf")
def export_pdf(
    type: str = "progress",
    session: Session = Depends(get_session),
    user: User = Depends(require_role("Admin", "Training Manager", "Reviewer", "Manager")),
) -> Response:
    """Download report as PDF (ReportLab).

    Args:
        type: Report type key.
    """
    report_type = type if type in _VALID_TYPES else "progress"
    service = ReportService(session)
    data = service.export_pdf(report_type)
    filename = f"skillsprint_{report_type}_{_ts()}.pdf"
    return Response(
        content=data,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get("/reports/export/excel")
def export_excel(
    type: str = "progress",
    session: Session = Depends(get_session),
    user: User = Depends(require_role("Admin", "Training Manager", "Reviewer", "Manager")),
) -> Response:
    """Download report as Excel (.xlsx).

    Args:
        type: Report type key.
    """
    report_type = type if type in _VALID_TYPES else "progress"
    service = ReportService(session)
    data = service.export_excel(report_type)
    filename = f"skillsprint_{report_type}_{_ts()}.xlsx"
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


def _ts() -> str:
    """Return a compact timestamp string for filenames."""
    from datetime import datetime
    return datetime.utcnow().strftime("%Y%m%d_%H%M%S")
