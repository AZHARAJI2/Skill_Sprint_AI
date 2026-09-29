"""Measure one complete production plan run against the configured live provider.

This is an operator evidence tool, never a mocked test.  It calls the same
``PlanGenerationService`` and independent Python validation used by the API,
then writes an evidence JSON only after a live provider attempt.  A zero exit
status means a complete, non-fallback plan finished in the SRS 30-second
budget.  API keys are read only from the environment and are never persisted.

PowerShell example:
    $env:SKILLSPRINT_GENAI_PROVIDER = "commandcode"
    $env:CMD_API_KEY = "<your-key>"
    python -m scripts.benchmark_live_plan --employee-code EMP-001
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from config.logging_config import configure_logging
from config.settings import settings
from database.base import SessionLocal
from src.employees.service import EmployeeService
from src.errors import AppError
from src.plans.dependencies import get_genai_provider
from src.plans.models import GenerationMetadata
from src.plans.service import PlanGenerationService
from src.plans.validation_service import PlanValidationService

SRS_LIMIT_MS = 30_000


def assess_run(*, elapsed_ms: float, generation_status: str | None, recovered: bool) -> dict:
    """Return an auditable pass/fail outcome without hiding partial output."""
    # ``None`` is the normal successful status for a complete GeneratedPlan.
    # Only an explicit failed-after-retries marker or assembler recovery makes
    # the plan incomplete for live-GenAI performance evidence.
    complete = generation_status != "failed_after_retries" and not recovered
    within_budget = elapsed_ms <= SRS_LIMIT_MS
    return {
        "srs_limit_ms": SRS_LIMIT_MS,
        "elapsed_ms": round(elapsed_ms, 1),
        "within_30_seconds": within_budget,
        "complete_live_genai_plan": complete,
        "passed": complete and within_budget,
    }


def _latest_metadata(session, plan_id: int) -> GenerationMetadata | None:
    return (
        session.query(GenerationMetadata)
        .filter(GenerationMetadata.plan_id == plan_id)
        .order_by(GenerationMetadata.id.desc())
        .first()
    )


def _write_evidence(path: Path, evidence: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(evidence, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def run(employee_code: str, out_path: Path) -> tuple[dict, int]:
    """Generate and validate one employee plan with wall-clock measurement."""
    configure_logging()
    started_at = datetime.now(timezone.utc)
    session = SessionLocal()
    evidence: dict = {
        "benchmark_version": "1.0",
        "started_at_utc": started_at.isoformat(),
        "employee_code": employee_code,
        "provider": settings.genai_provider,
        "configured_model": (
            settings.command_code_model if settings.genai_provider == "commandcode"
            else settings.deepseek_model if settings.genai_provider == "deepseek"
            else settings.gemini_model
        ),
        "api_key_persisted": False,
    }
    try:
        employee = EmployeeService(session).employees.get_by_code(employee_code)
        if employee is None:
            evidence.update({"status": "configuration_error", "error": f"Employee not found: {employee_code}"})
            _write_evidence(out_path, evidence)
            return evidence, 2

        clock_start = time.perf_counter()
        plan = PlanGenerationService(session, provider=get_genai_provider()).generate_for_employee(
            employee.id,
            actor="live-plan-benchmark",
        )
        validation = PlanValidationService(session).validate(plan.id, actor="live-plan-benchmark")
        session.commit()
        elapsed_ms = (time.perf_counter() - clock_start) * 1000
        metadata = _latest_metadata(session, plan.id)
        log_payload = metadata.log_payload or {} if metadata else {}
        result = assess_run(
            elapsed_ms=elapsed_ms,
            generation_status=(plan.structured_json or {}).get("generation_status"),
            recovered=bool(log_payload.get("recovered_from_assembler")),
        )
        evidence.update(
            {
                "finished_at_utc": datetime.now(timezone.utc).isoformat(),
                "status": (
                    "passed"
                    if result["passed"]
                    else "completed_over_srs"
                    if result["complete_live_genai_plan"]
                    else "failed"
                ),
                "plan": {
                    "id": plan.id,
                    "role_id": plan.role_id,
                    "model_used": plan.model_used,
                    "generation_status": (plan.structured_json or {}).get("generation_status"),
                    "retry_count": metadata.retry_count if metadata else None,
                    "provider_response_time_ms": metadata.response_time_ms if metadata else None,
                    "recovered_from_assembler": log_payload.get("recovered_from_assembler"),
                },
                "validation": {
                    "overall_status": validation.overall_status,
                    "coverage_score": validation.coverage_score,
                    "traceability_score": validation.traceability_score,
                    "missing_count": validation.missing_count,
                    "unsupported_count": validation.unsupported_count,
                },
                "result": result,
            }
        )
        _write_evidence(out_path, evidence)
        return evidence, 0 if result["passed"] else 1
    except AppError as exc:
        session.rollback()
        evidence.update(
            {
                "finished_at_utc": datetime.now(timezone.utc).isoformat(),
                "status": "provider_or_generation_error",
                "error": str(exc),
                "status_code": exc.status_code,
                "details": exc.details,
            }
        )
        _write_evidence(out_path, evidence)
        return evidence, 1
    finally:
        session.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Benchmark one complete live GenAI plan against the 30-second SRS target.")
    parser.add_argument("--employee-code", default="EMP-001", help="Existing employee code; default is the first seeded employee.")
    parser.add_argument(
        "--out",
        type=Path,
        default=settings.project_root / "reports" / "d7_live_plan_benchmark.json",
        help="Evidence JSON output path.",
    )
    args = parser.parse_args(argv)
    evidence, exit_code = run(args.employee_code, args.out)
    print(f"Benchmark status: {evidence['status']}")
    if evidence.get("result"):
        print(f"Elapsed: {evidence['result']['elapsed_ms']} ms; passed: {evidence['result']['passed']}")
    print(f"Evidence: {args.out}")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
