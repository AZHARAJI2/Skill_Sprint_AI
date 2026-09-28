"""Build the small Netlify site that securely proxies to the hosted FastAPI app.

Netlify hosts the public URL.  The stateful FastAPI application remains on a
Python host with PostgreSQL, as required by PROJECT_MAP.md.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "netlify_proxy_public"


def main() -> int:
    """Create a Netlify rewrite after validating the configured backend URL."""
    backend = os.getenv("SKILLSPRINT_BACKEND_URL", "").strip().rstrip("/")
    parsed = urlparse(backend)
    if parsed.scheme != "https" or not parsed.netloc:
        print(
            "SKILLSPRINT_BACKEND_URL must be the HTTPS URL of the FastAPI host, "
            "for example https://skillsprint-api.example.com",
            file=sys.stderr,
        )
        return 1

    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / "_redirects").write_text(f"/*  {backend}/:splat  200\n", encoding="utf-8")
    (OUTPUT / "index.html").write_text(
        "<!doctype html><title>SkillSprint AI</title><p>Connecting to SkillSprint AI…</p>",
        encoding="utf-8",
    )
    print(f"Created Netlify proxy for {backend}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
