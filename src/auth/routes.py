"""Auth HTTP routes: login form, JSON login, current user, logout."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from sqlalchemy.orm import Session

from config.settings import settings
from database.base import get_session
from src.auth.dependencies import get_current_user
from src.auth.models import User
from src.auth.service import AuthService
from src.errors import AppError

router = APIRouter(tags=["auth"])
templates = Jinja2Templates(directory=str(settings.project_root / "templates"))


class LoginBody(BaseModel):
    """JSON login payload."""

    username: str
    password: str


@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request) -> HTMLResponse:
    """Render the login form."""
    return templates.TemplateResponse("login.html", {"request": request, "error": None})


@router.post("/login")
def login_form(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    session: Session = Depends(get_session),
):
    """Form login used by the web UI; sets an HTTP-only cookie."""
    try:
        service = AuthService(session)
        user = service.authenticate(username, password)
        token = service.issue_token(user)
    except AppError as exc:
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "error": exc.message},
            status_code=401,
        )
    response = RedirectResponse(url="/dashboard", status_code=303)
    response.set_cookie("skillsprint_token", token, httponly=True, samesite="lax")
    return response


@router.post("/api/login")
def login_api(body: LoginBody, session: Session = Depends(get_session)) -> dict:
    """JSON login for API clients and tests."""
    service = AuthService(session)
    user = service.authenticate(body.username, body.password)
    token = service.issue_token(user)
    return {"access_token": token, "token_type": "bearer", "role": user.app_role, "username": user.username}


@router.post("/logout")
def logout() -> RedirectResponse:
    """Clear the session cookie."""
    response = RedirectResponse(url="/login", status_code=303)
    response.delete_cookie("skillsprint_token")
    return response


@router.get("/api/me")
def me(user: User = Depends(get_current_user)) -> dict:
    """Return the authenticated principal."""
    return {"username": user.username, "role": user.app_role, "employee_id": user.employee_id}
