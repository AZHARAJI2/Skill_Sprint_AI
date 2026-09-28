"""Application configuration loaded from environment variables with safe defaults."""

from __future__ import annotations

import os
from pathlib import Path


class Settings:
    """Runtime settings for SkillSprint AI.

    Values come from environment variables so secrets are never committed.
    SQLite is the default store; PostgreSQL is a connection-string swap.
    """

    def __init__(self) -> None:
        self.project_root: Path = Path(__file__).resolve().parent.parent
        self.app_name: str = "SkillSprint AI"
        self.company_name: str = "NovaCart"
        self.secret_key: str = os.getenv("SKILLSPRINT_SECRET_KEY", "dev-secret-change-for-evaluation")
        self.jwt_algorithm: str = "HS256"
        self.access_token_expire_minutes: int = int(os.getenv("SKILLSPRINT_TOKEN_MINUTES", "480"))
        self.database_url: str = os.getenv(
            "SKILLSPRINT_DATABASE_URL",
            f"sqlite:///{(self.project_root / 'data' / 'skillsprint.db').as_posix()}",
        )
        self.upload_dir: Path = Path(os.getenv("SKILLSPRINT_UPLOAD_DIR", self.project_root / "data" / "uploads"))
        self.log_dir: Path = Path(os.getenv("SKILLSPRINT_LOG_DIR", self.project_root / "logs"))
        self.max_upload_bytes: int = int(os.getenv("SKILLSPRINT_MAX_UPLOAD_BYTES", str(20 * 1024 * 1024)))
        self.allowed_extensions: frozenset[str] = frozenset({".pdf", ".docx", ".txt", ".md", ".csv"})
        self.sample_documents_dir: Path = self.project_root / "sample_documents"
        self.matrix_csv_path: Path = self.project_root / "role_matrix" / "role_requirement_matrix_seed.csv"
        self.gemini_api_key: str | None = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        self.gemini_model: str = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
        self.gemini_thinking_budget: int = int(os.getenv("GEMINI_THINKING_BUDGET", "0"))
        self.gemini_request_timeout_seconds: float = float(
            # Gemini rejects manually configured request deadlines below 10 seconds.
            os.getenv("SKILLSPRINT_GEMINI_TIMEOUT_SECONDS", "10")
        )
        self.groq_api_key: str | None = os.getenv("GROQ_API_KEY")
        self.groq_model: str = os.getenv("GROQ_MODEL", "openai/gpt-oss-20b")
        self.groq_request_timeout_seconds: float = float(
            os.getenv("SKILLSPRINT_GROQ_TIMEOUT_SECONDS", "20")
        )
        # One complete plan call has a strict end-to-end budget.  A second
        # attempt is reserved only for malformed structured output.
        self.plan_generation_timeout_seconds: float = float(
            os.getenv("SKILLSPRINT_PLAN_TIMEOUT_SECONDS", "25")
        )
        self.genai_max_retries: int = int(os.getenv("SKILLSPRINT_GENAI_MAX_RETRIES", "2"))
        self.genai_retry_backoff_seconds: float = float(
            os.getenv("SKILLSPRINT_GENAI_RETRY_BACKOFF_SECONDS", "1")
        )
        # A complete plan already has one source-grounded call per stage group.
        # Extra wording-only calls are opt-in so a free-tier key is not exhausted
        # before the required generation calls complete.
        self.genai_enable_enrichment: bool = os.getenv(
            "SKILLSPRINT_ENABLE_GENAI_ENRICHMENT", "false"
        ).strip().lower() in {"1", "true", "yes"}

        # -----------------------------------------------------------------------
        # Progress-tracking configuration (SRS Steps 17, 18, 50, 53, 54)
        # Stage offsets in calendar days from employee joining_date.
        # An item is overdue when today - joining_date > stage offset (days).
        # Override via environment variables to avoid code changes during evaluation.
        # -----------------------------------------------------------------------
        self.stage_duration_days: dict[str, int] = {
            "Day 1": int(os.getenv("SKILLSPRINT_STAGE_DAY1", "1")),
            "Week 1": int(os.getenv("SKILLSPRINT_STAGE_WEEK1", "7")),
            "Week 2": int(os.getenv("SKILLSPRINT_STAGE_WEEK2", "14")),
            "First 30 Days": int(os.getenv("SKILLSPRINT_STAGE_30", "30")),
            "First 60 Days": int(os.getenv("SKILLSPRINT_STAGE_60", "60")),
            "First 90 Days": int(os.getenv("SKILLSPRINT_STAGE_90", "90")),
        }
        # Step 54 status thresholds (percent of overall_pct)
        self.progress_behind_threshold: int = int(os.getenv("SKILLSPRINT_BEHIND_THRESHOLD", "30"))
        self.progress_attention_quiz_min: int = int(os.getenv("SKILLSPRINT_ATTENTION_QUIZ_MIN", "60"))
        self.progress_assessment_required_pct: int = int(os.getenv("SKILLSPRINT_ASSESS_REQUIRED_PCT", "80"))
        # Minimum passing score for quizzes (Step 53)
        self.quiz_pass_score: int = int(os.getenv("SKILLSPRINT_QUIZ_PASS_SCORE", "70"))

    def ensure_runtime_dirs(self) -> None:
        """Create upload, log, and data directories if they do not exist."""
        self.upload_dir.mkdir(parents=True, exist_ok=True)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        (self.project_root / "data").mkdir(parents=True, exist_ok=True)


settings = Settings()
