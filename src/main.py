"""FastAPI application entry point: middleware, error handlers, routers, templates."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import ValidationError as PydanticValidationError
from sqlalchemy.exc import SQLAlchemyError

from config.logging_config import configure_logging, get_logger
from config.settings import settings
from database.migrations import create_schema
from src.auth.routes import router as auth_router
from src.dashboards.routes import router as dashboard_router
from src.documents.routes import router as document_router
from src.employees.matrix_routes import router as matrix_router
from src.employees.routes import router as employee_router
from src.errors import AppError

configure_logging()
logger = get_logger("api")
settings.ensure_runtime_dirs()
create_schema()

app = FastAPI(title="SkillSprint AI", version="0.1.0")
app.mount("/static", StaticFiles(directory=str(settings.project_root / "static")), name="static")
templates = Jinja2Templates(directory=str(settings.project_root / "templates"))

app.include_router(auth_router)
app.include_router(dashboard_router)
app.include_router(document_router)
app.include_router(employee_router)
app.include_router(matrix_router)


@app.exception_handler(AppError)
async def app_error_handler(_request: Request, exc: AppError) -> JSONResponse:
    """Convert typed application errors into JSON bodies."""
    logger.warning("api_error status=%s message=%s details=%s", exc.status_code, exc.message, exc.details)
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": exc.message, "details": exc.details},
    )


@app.exception_handler(RequestValidationError)
async def request_validation_handler(_request: Request, exc: RequestValidationError) -> JSONResponse:
    """Request body/query schema errors at the API boundary."""
    logger.warning("request_validation_error errors=%s", exc.errors())
    return JSONResponse(status_code=422, content={"error": "Validation error", "details": exc.errors()})


@app.exception_handler(PydanticValidationError)
async def pydantic_error_handler(_request: Request, exc: PydanticValidationError) -> JSONResponse:
    """Schema errors at the API boundary."""
    logger.warning("schema_error errors=%s", exc.errors())
    return JSONResponse(status_code=422, content={"error": "Validation error", "details": exc.errors()})


@app.exception_handler(SQLAlchemyError)
async def sqlalchemy_error_handler(_request: Request, exc: SQLAlchemyError) -> JSONResponse:
    """Unexpected database failures."""
    logger.error("database_error error=%s", exc)
    return JSONResponse(status_code=500, content={"error": "Database error"})


@app.exception_handler(Exception)
async def unhandled_error_handler(_request: Request, exc: Exception) -> JSONResponse:
    """Last-resort handler so clients never receive an uncaught traceback page."""
    logger.error("unhandled_error error=%s", exc)
    return JSONResponse(status_code=500, content={"error": "Internal server error"})


@app.get("/health")
def health() -> dict:
    """Liveness probe used by tests and hosting platforms."""
    return {"status": "ok", "app": settings.app_name, "company": settings.company_name}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("src.main:app", host="0.0.0.0", port=8000, reload=True)
