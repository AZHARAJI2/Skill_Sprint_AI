"""Search routes — Phase 4, Task 61."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from config.settings import settings
from database.base import get_session
from src.auth.dependencies import get_current_user, require_role
from src.auth.models import User
from src.search.service import SearchService

router = APIRouter(tags=["search"])
templates = Jinja2Templates(directory=str(settings.project_root / "templates"))


@router.get("/search", response_class=HTMLResponse)
def search_page(
    request: Request,
    q: str = "",
    entity: str = "",
    department: str = "",
    session: Session = Depends(get_session),
    user: User = Depends(require_role("Admin", "Training Manager", "Reviewer", "Manager", "Employee")),
) -> HTMLResponse:
    """Render search results page with cross-entity filtering."""
    service = SearchService(session)
    departments = service.available_departments()
    results = {"employees": [], "documents": [], "modules": [], "plans": [], "requirements": []}
    total = 0

    if q:
        results = service.search(q, entity=entity, department=department)
        total = sum(len(v) for v in results.values())

    return templates.TemplateResponse(
        request=request,
        name="search.html",
        context={
            "user": user,
            "query": q,
            "entity": entity,
            "department": department,
            "departments": departments,
            "results": results,
            "total_results": total,
        },
    )


@router.get("/api/search")
def search_api(
    q: str = "",
    entity: str = "",
    department: str = "",
    limit: int = 20,
    session: Session = Depends(get_session),
    user: User = Depends(require_role("Admin", "Training Manager", "Reviewer", "Manager", "Employee")),
) -> dict:
    """JSON search API for programmatic access."""
    service = SearchService(session)
    results = service.search(q, entity=entity, department=department, limit=limit)
    total = sum(len(v) for v in results.values())
    return {"query": q, "total": total, "results": results}
