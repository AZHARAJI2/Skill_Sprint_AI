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
        self.cookie_secure: bool = os.getenv("SKILLSPRINT_COOKIE_SECURE", "false").strip().lower() in {"1", "true", "yes"}
        self.jwt_algorithm: str = "HS256"
        self.access_token_expire_minutes: int = int(os.getenv("SKILLSPRINT_TOKEN_MINUTES", "480"))
        self.database_url: str = os.getenv(
            "SKILLSPRINT_DATABASE_URL",
            f"sqlite:///{(self.project_root / 'data' / 'skillsprint.db').as_posix()}",
        )
        # Hosted PostgreSQL services commonly provide either postgres:// or
        # postgresql:// URLs.  Normalize both to the installed Psycopg 3
        # dialect so deployment is a configuration change, not a code change.
        if self.database_url.startswith("postgres://"):
            self.database_url = "postgresql+psycopg://" + self.database_url.removeprefix("postgres://")
        elif self.database_url.startswith("postgresql://"):
            self.database_url = "postgresql+psycopg://" + self.database_url.removeprefix("postgresql://")
        self.upload_dir: Path = Path(os.getenv("SKILLSPRINT_UPLOAD_DIR", self.project_root / "data" / "uploads"))
        self.log_dir: Path = Path(os.getenv("SKILLSPRINT_LOG_DIR", self.project_root / "logs"))
        self.max_upload_bytes: int = int(os.getenv("SKILLSPRINT_MAX_UPLOAD_BYTES", str(20 * 1024 * 1024)))
        self.allowed_extensions: frozenset[str] = frozenset({".pdf", ".docx", ".txt", ".md", ".csv"})
        self.sample_documents_dir: Path = self.project_root / "sample_documents"
        self.matrix_csv_path: Path = self.project_root / "role_matrix" / "role_requirement_matrix_seed.csv"
        # Pipeline 1 defaults to Command Code. It exposes an OpenAI-compatible
        # API and lets the operator choose a supported model through one key.
        self.genai_provider: str = os.getenv("SKILLSPRINT_GENAI_PROVIDER", "commandcode").strip().lower()
        if self.genai_provider not in {"commandcode", "deepseek", "gemini"}:
            raise ValueError("SKILLSPRINT_GENAI_PROVIDER must be 'commandcode', 'deepseek', or 'gemini'.")
        # Command Code documents CMD_API_KEY in its curl examples. The longer
        # spelling is accepted as a clearer backend-host secret name.
        self.command_code_api_key: str | None = os.getenv("CMD_API_KEY") or os.getenv("COMMAND_CODE_API_KEY")
        self.command_code_model: str = os.getenv(
            "COMMAND_CODE_MODEL", "deepseek/deepseek-v4-flash-fast"
        ).strip() or "deepseek/deepseek-v4-flash-fast"
        self.command_code_base_url: str = os.getenv(
            "COMMAND_CODE_BASE_URL", "https://api.commandcode.ai/provider/v1"
        ).strip()
        # Command Code may need longer than a short request budget for a full,
        # source-grounded plan. Operators can set a positive timeout for a
        # hosting policy; zero keeps the provider response uncut.
        configured_command_code_timeout = float(os.getenv("SKILLSPRINT_COMMAND_CODE_TIMEOUT_SECONDS", "0"))
        self.command_code_request_timeout_seconds: float | None = (
            configured_command_code_timeout if configured_command_code_timeout > 0 else None
        )
        self.command_code_zero_data_retention: bool = os.getenv(
            "SKILLSPRINT_COMMAND_CODE_ZDR", "false"
        ).strip().lower() in {"1", "true", "yes"}
        self.deepseek_api_key: str | None = os.getenv("DEEPSEEK_API_KEY")
        self.deepseek_model: str = os.getenv("DEEPSEEK_MODEL", "deepseek-flash").strip() or "deepseek-flash"
        self.deepseek_base_url: str = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com").strip()
        # Prevent a hung TCP connection while allowing a complete stage-group
        # response from the direct-provider compatibility path.
        configured_deepseek_timeout = float(os.getenv("SKILLSPRINT_DEEPSEEK_TIMEOUT_SECONDS", "45"))
        self.deepseek_request_timeout_seconds: float | None = (
            configured_deepseek_timeout if configured_deepseek_timeout > 0 else None
        )
        self.gemini_api_key: str | None = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        # gemini-2.5-flash is not available to newly created Gemini API keys.
        # Migrate that legacy value automatically so an old terminal/.env
        # setting cannot silently keep plan generation broken.
        configured_model = os.getenv("GEMINI_MODEL", "gemini-3.8-flash").strip()
        self.gemini_model: str = (
            "gemini-3.8-flash"
            if configured_model in {"", "gemini-2.5-flash", "models/gemini-2.5-flash"}
            else configured_model
        )
        self.gemini_thinking_budget: int = int(os.getenv("GEMINI_THINKING_BUDGET", "0"))
        # Three stage groups run in parallel; zero explicitly permits an
        # unrestricted diagnostic/live-evidence run.
        configured_gemini_timeout = float(os.getenv("SKILLSPRINT_GEMINI_TIMEOUT_SECONDS", "45"))
        self.gemini_request_timeout_seconds: float | None = (
            configured_gemini_timeout if configured_gemini_timeout > 0 else None
        )
        # Do not replace a slow but valid GenAI plan with an incomplete review
        # draft merely because a local deadline elapsed. Set a positive value
        # only when an operator intentionally wants that behavior.
        configured_plan_timeout = float(os.getenv("SKILLSPRINT_PLAN_TIMEOUT_SECONDS", "0"))
        self.plan_generation_timeout_seconds: float | None = (
            configured_plan_timeout if configured_plan_timeout > 0 else None
        )
        # Project Map permits at most three generation attempts.  Defaulting
        # to 2 avoids a third full-latency retry (~25 s) on transient failures;
        # set SKILLSPRINT_GENAI_MAX_RETRIES=3 to restore the hard cap.
        self.genai_max_retries: int = int(os.getenv("SKILLSPRINT_GENAI_MAX_RETRIES", "2"))
        self.genai_retry_backoff_seconds: float = float(
            os.getenv("SKILLSPRINT_GENAI_RETRY_BACKOFF_SECONDS", "0.4")
        )
        # A complete plan already has one source-grounded call per stage group.
        # Extra wording-only calls are opt-in so a free-tier key is not exhausted
        # before the required generation calls complete.
        self.genai_enable_enrichment: bool = os.getenv(
            "SKILLSPRINT_ENABLE_GENAI_ENRICHMENT", "false"
        ).strip().lower() in {"1", "true", "yes"}
        # Three independent stage groups are generated concurrently. This
        # reduces wall-clock time without changing the complete-plan schema.
        self.genai_parallel_workers: int = max(1, min(3, int(os.getenv("SKILLSPRINT_GENAI_PARALLEL_WORKERS", "3"))))
        # Prompt budget controls. They reduce repeated source context in each
        # concurrent stage request while retaining every cited requirement in
        # the Python skeleton and final validation inputs.
        # 20 excerpts × 260 chars ≈ 5 200 chars of source context per stage
        # call.  This is enough for source grounding while keeping each
        # parallel prompt short and reducing Gemini input-token cost.
        self.genai_max_prompt_excerpts: int = max(
            1, min(40, int(os.getenv("SKILLSPRINT_MAX_PROMPT_EXCERPTS", "20")))
        )
        self.genai_excerpt_char_limit: int = max(
            160, min(1000, int(os.getenv("SKILLSPRINT_SOURCE_EXCERPT_CHARS", "260")))
        )
        # Allow the provider enough room for detailed, complete learning
        # language across all three stage groups.
        self.genai_stage_output_tokens: int = max(
            4096, min(8192, int(os.getenv("SKILLSPRINT_STAGE_OUTPUT_TOKENS", "5120")))
        )

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
