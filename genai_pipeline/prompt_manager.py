"""Load versioned prompt templates from files (never hard-coded in generators)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from config.settings import settings
from src.errors import AppError


@dataclass(frozen=True)
class PromptTemplateFile:
    """One versioned template loaded from prompt_templates/."""

    name: str
    version: str
    system: str
    user: str
    variables: list[str]
    path: Path

    @property
    def version_label(self) -> str:
        return f"{self.name}_{self.version}"


class PromptManager:
    """Select and render prompt templates stored as JSON files."""

    def __init__(self, templates_dir: Path | None = None) -> None:
        self.templates_dir = templates_dir or settings.project_root / "prompt_templates"

    def load(self, name: str, version: str = "v1") -> PromptTemplateFile:
        """Load `{name}_{version}.json` from disk."""
        path = self.templates_dir / f"{name}_{version}.json"
        if not path.is_file():
            raise AppError(f"Prompt template not found: {path.name}", status_code=500)
        payload = json.loads(path.read_text(encoding="utf-8"))
        return PromptTemplateFile(
            name=payload["name"],
            version=payload["version"],
            system=payload["system"],
            user=payload["user"],
            variables=list(payload.get("variables") or []),
            path=path,
        )

    def render(self, template: PromptTemplateFile, **values: str) -> str:
        """Fill {{variables}} in the user template and prepend the system instructions."""
        missing = [key for key in template.variables if key not in values]
        if missing:
            raise AppError(f"Missing prompt variables: {missing}", status_code=500)
        user = template.user
        for key, value in values.items():
            user = user.replace("{{" + key + "}}", value)
        return f"{template.system}\n\n{user}"
