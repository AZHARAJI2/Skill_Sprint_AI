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

    def ensure_runtime_dirs(self) -> None:
        """Create upload, log, and data directories if they do not exist."""
        self.upload_dir.mkdir(parents=True, exist_ok=True)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        (self.project_root / "data").mkdir(parents=True, exist_ok=True)


settings = Settings()
