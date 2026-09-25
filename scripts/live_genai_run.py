"""Live Gemini run harness — proves Pipeline 1 against the real Gemini API.

This is an *operator tool*, not a test. It exists because the automated suite uses
``ScriptedProvider`` so CI never depends on a live key (see ``tests/conftest.py``).
D4 requires evidence of a real model call, so this script exercises the production
path — ``PlanGenerationService.generate_for_employee`` over the real seeded SQLite
database — and records what Gemini actually returned.

Usage (PowerShell):
    $env:GEMINI_API_KEY = "<your-key>"
    python -m scripts.live_genai_run

The key is read from the environment only. It is never written to disk, never
logged, and never included in the evidence artifact.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.orm import Session

from config.logging_config import configure_logging, get_logger
from config.settings import settings
from database.base import SessionLocal
from genai_pipeline.base_provider import GenerationConfig
from genai_pipeline.gemini_provider import GeminiProvider
from genai_pipeline.prompt_manager import PromptManager
from schemas.plan_schema import GeneratedPlan
from src.documents.repository import ChunkRepository, DocumentRepository
from src.employees.service import EmployeeService
from src.errors import AppError
from src.plans.models import GenerationMetadata
from src.plans.service import PlanGenerationService

logger = get_logger("live_genai_run")

RAW_SAMPLE_CHAR_LIMIT = 1200


class LiveGenAIRun:
    """Drive real Gemini generation across all ten roles and capture evidence."""

    def __init__(self, session: Session, provider: GeminiProvider) -> None:
        self.session = session
        self.provider = provider
        self.service = PlanGenerationService(session, provider=provider)
        self.employees = EmployeeService(session)
        self.prompts = PromptManager()

    def discover_employees(self) -> list[tuple[int, str, str]]:
        """Return (employee_id, employee_code, role_title) for every seeded demo employee."""
        found: list[tuple[int, str, str]] = []
        for employee in self.employees.list_employees():
            role = employee.role
            if role is None:
                continue
            found.append((employee.id, employee.employee_code, role.title))
        return found

    def run_role(self, employee_id: int, employee_code: str, role_title: str) -> dict:
        """Generate one plan through the production service and read back its telemetry."""
        started = datetime.now(timezone.utc)
        plan = self.service.generate_for_employee(employee_id, actor="live-genai-run")
        self.session.commit()
        metadata = self._latest_metadata(plan.id)
        record = metadata.log_payload or {} if metadata else {}
        elapsed = (datetime.now(timezone.utc) - started).total_seconds() * 1000
        result = {
            "employee_id": employee_id,
            "employee_code": employee_code,
            "role_title": role_title,
            "plan_id": plan.id,
            "prompt_version": plan.prompt_version,
            "model_used": plan.model_used,
            "retry_count": metadata.retry_count if metadata else None,
            "provider_response_time_ms": metadata.response_time_ms if metadata else None,
            "wall_clock_ms": round(elapsed, 1),
            "recovered_from_assembler": record.get("recovered_from_assembler"),
            "grounding_flag_count": record.get("grounding_flag_count"),
            "item_counts": self._item_counts(plan.structured_json),
            "status": "generated",
        }
        logger.info(
            "live_run role=%s model=%s retries=%s recovered=%s wall_ms=%.0f",
            role_title,
            result["model_used"],
            result["retry_count"],
            result["recovered_from_assembler"],
            elapsed,
        )
        return result

    def capture_raw_sample(self) -> dict:
        """Make one direct Gemini call through the real provider and keep the raw text.

        This is the proof-of-life artifact: a genuine, unedited Gemini response body.
        """
        template = self.prompts.load("onboarding_plan", "v1")
        service_block = self._small_source_block()
        prompt = self.prompts.render(
            template,
            employee_json=json.dumps(
                {
                    "employee_code": "LIVE-SAMPLE",
                    "name": "Live Sample",
                    "role_title": "Software Engineer",
                    "department": "Engineering",
                    "experience_level": "Beginner",
                    "location": "Amman",
                    "joining_date": "2026-09-01",
                    "reporting_manager": "Engineering Lead",
                    "competencies": ["Policy Awareness"],
                }
            ),
            requirements_json=json.dumps(
                [
                    {
                        "requirement_id": "R001",
                        "requirement_text": "Complete information security awareness training.",
                        "mandatory": True,
                        "priority": "High",
                        "due_stage": "Week 1",
                        "source_document_id": "POL-03",
                        "source_section_id": "1.1",
                        "competency": "Policy Awareness",
                    }
                ]
            ),
            source_chunks_block=service_block,
            role_title="Software Engineer",
        )
        try:
            response = self.provider.generate(prompt, schema=None, config=GenerationConfig(temperature=0.0))
        except AppError as exc:
            logger.error("live_raw_sample_failed status=%s details=%s", exc.status_code, exc.details)
            return {"captured": False, "error": str(exc), "status_code": exc.status_code}
        return {
            "captured": True,
            "model_name": response.model_name,
            "response_time_ms": response.response_time_ms,
            "raw_text_head": response.raw_text[:RAW_SAMPLE_CHAR_LIMIT],
            "raw_text_length": len(response.raw_text),
            "parses_as_json": isinstance(response.parsed, dict),
            "prompt_version": template.version_label,
        }

    def execute(self, roles_limit: int | None = None) -> dict:
        """Run every role, capture a raw sample, and return the evidence document."""
        employees = self.discover_employees()
        if roles_limit is not None:
            employees = employees[:roles_limit]
        runs: list[dict] = []
        failures: list[dict] = []
        for employee_id, code, role_title in employees:
            try:
                runs.append(self.run_role(employee_id, code, role_title))
            except Exception as exc:  # noqa: BLE001 - a single role must not abort the run
                self.session.rollback()
                logger.error("live_run_failed role=%s error=%s", role_title, exc)
                failures.append(
                    {
                        "role_title": role_title,
                        "employee_code": code,
                        "error": str(exc),
                        "type": type(exc).__name__,
                        "status_code": getattr(exc, "status_code", None),
                    }
                )
        gemini_backed = [r for r in runs if r["recovered_from_assembler"] is False]
        return {
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "sdk": "google-genai",
            "sdk_version": self._sdk_version(),
            "model": self.provider.model,
            "api_key_source": "GEMINI_API_KEY environment variable (never persisted)",
            "roles_attempted": len(employees),
            "roles_generated": len(runs),
            "roles_failed": len(failures),
            "roles_with_gemini_contribution": len(gemini_backed),
            "all_gemini_backed": bool(runs) and len(gemini_backed) == len(runs),
            "total_retry_count": sum(int(r.get("retry_count") or 0) for r in runs),
            "mean_wall_clock_ms": round(
                sum(float(r["wall_clock_ms"]) for r in runs) / len(runs), 1
            ) if runs else 0.0,
            "runs": runs,
            "failures": failures,
            "raw_gemini_sample": self.capture_raw_sample(),
        }

    def write_evidence(self, evidence: dict, out_path: Path) -> Path:
        """Persist the evidence document as pretty JSON."""
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(evidence, indent=2, ensure_ascii=False), encoding="utf-8")
        return out_path

    def _latest_metadata(self, plan_id: int) -> GenerationMetadata | None:
        rows = (
            self.session.query(GenerationMetadata)
            .filter(GenerationMetadata.plan_id == plan_id)
            .order_by(GenerationMetadata.id.desc())
            .all()
        )
        return rows[0] if rows else None

    @staticmethod
    def _item_counts(structured: dict) -> dict:
        return {
            "modules": len(structured.get("modules") or []),
            "checklists": len(structured.get("checklists") or []),
            "tasks": len(structured.get("tasks") or []),
            "quizzes": len(structured.get("quizzes") or []),
            "assessments": len(structured.get("assessments") or []),
            "stages_used": len(structured.get("stages_used") or []),
        }

    def _small_source_block(self) -> str:
        """Fence a small real chunk from the corpus so the sample prompt is source-grounded."""
        chunks = ChunkRepository(self.session).list_all()[:2]
        guard = self.service.assembler.injection_guard
        blocks: list[str] = []
        for chunk in chunks:
            text = (chunk.content or "")[:400]
            blocks.append(
                guard.scan(
                    text,
                    document_id=chunk.document_id,
                    section_id=chunk.section_id or "0",
                ).fenced_text
            )
        return "\n\n".join(blocks) or "UNTRUSTED_DOCUMENT_DATA: (empty)"

    @staticmethod
    def _sdk_version() -> str:
        try:
            from google import genai

            return getattr(genai, "__version__", "unknown")
        except Exception:  # noqa: BLE001
            return "unavailable"


def main(argv: list[str] | None = None) -> int:
    """Entry point: require a live key, run the pipeline, write D4 evidence."""
    parser = argparse.ArgumentParser(description="Run Pipeline 1 against the live Gemini API.")
    parser.add_argument("--roles", type=int, default=None, help="Limit to the first N roles (smoke test).")
    parser.add_argument(
        "--out",
        type=Path,
        default=settings.project_root / "reports" / "d4_live_genai_run.json",
        help="Where to write the evidence JSON.",
    )
    args = parser.parse_args(argv)

    configure_logging()
    if not settings.gemini_api_key:
        print(
            "GEMINI_API_KEY is not set. Export it first, e.g.\n"
            '  $env:GEMINI_API_KEY = "<your-key>"\n'
            "Refusing to run: a live-run artifact must contain real model output.",
            file=sys.stderr,
        )
        return 2

    provider = GeminiProvider()
    print(f"Model: {provider.model}")
    print(f"Roles to generate: {args.roles if args.roles else 'all seeded demo employees'}")

    session = SessionLocal()
    try:
        runner = LiveGenAIRun(session, provider)
        evidence = runner.execute(roles_limit=args.roles)
        path = runner.write_evidence(evidence, args.out)
    finally:
        session.close()

    print()
    print(f"Generated : {evidence['roles_generated']}/{evidence['roles_attempted']}")
    print(f"Failures  : {evidence['roles_failed']}")
    print(f"Gemini-backed (not assembler fallback): {evidence['roles_with_gemini_contribution']}")
    print(f"Total retries: {evidence['total_retry_count']}   mean wall clock: {evidence['mean_wall_clock_ms']} ms")
    print(f"Raw Gemini sample captured: {evidence['raw_gemini_sample'].get('captured')}")
    print(f"Evidence written to: {path}")
    return 0 if evidence["roles_generated"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
