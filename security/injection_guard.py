"""Prompt-injection detection and data fencing for uploaded document text."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from config.logging_config import get_logger

logger = get_logger("injection_guard")

INJECTION_SIGNATURES: tuple[tuple[str, str], ...] = (
    (r"system note", "HANDBOOK-style system note"),
    (r"administrator override", "administrator override"),
    (r"hidden note for ai", "hidden note for AI readers"),
    (r"ai readers", "instruction addressed to AI readers"),
    (r"ai auditor", "instruction addressed to an AI auditor"),
    (r"ai dashboard-summarizer", "instruction addressed to an AI summarizer"),
    (r"ai assistant", "instruction addressed to an AI assistant"),
    (r"ignore (all )?previous (instructions|prompts)", "ignore-previous-instructions"),
    (r"mark all employees compliant", "force-compliant override"),
    (r"auto-approve", "auto-approve override"),
    (r"skip retention", "skip retention compliance"),
    (r"omit the escalation", "omit escalation requirement"),
    (r"skip hris", "skip HRIS verification"),
    (r"refund timelines as flexible", "misstate refund timelines"),
    (r"classify all cases as minor", "force-minor classification"),
    (r"mark onboarding complete", "force onboarding complete"),
    (r"open requisitions as already filled", "force requisitions filled"),
    (r"you are now", "jailbreak persona switch"),
    (r"disregard (the |all )?(policy|document|instructions)", "disregard source"),
)


@dataclass
class InjectionFinding:
    """One matched injection signature inside a document excerpt."""

    signature: str
    snippet: str
    document_id: str | None = None
    section_id: str | None = None


@dataclass
class InjectionScanResult:
    """Outcome of scanning untrusted document text."""

    is_injection: bool
    findings: list[InjectionFinding] = field(default_factory=list)
    fenced_text: str = ""
    redacted_text: str = ""


class InjectionGuard:
    """Treat uploaded document text strictly as data and flag adversarial instructions.

    Adding a new signature is a data change on INJECTION_SIGNATURES, not a new code path
    in generators.
    """

    def __init__(self, signatures: tuple[tuple[str, str], ...] | None = None) -> None:
        self._compiled = [
            (re.compile(pattern, re.IGNORECASE), label)
            for pattern, label in (signatures or INJECTION_SIGNATURES)
        ]

    def scan(
        self,
        text: str,
        document_id: str | None = None,
        section_id: str | None = None,
    ) -> InjectionScanResult:
        """Scan text, fence it as data, and redact matched instruction sentences."""
        findings: list[InjectionFinding] = []
        for pattern, label in self._compiled:
            match = pattern.search(text or "")
            if match:
                start = max(0, match.start() - 40)
                end = min(len(text), match.end() + 40)
                findings.append(
                    InjectionFinding(
                        signature=label,
                        snippet=text[start:end].replace("\n", " "),
                        document_id=document_id,
                        section_id=section_id,
                    )
                )
        fenced = self.fence(text or "", document_id=document_id, section_id=section_id)
        redacted = self.redact(text or "")
        if findings:
            logger.warning(
                "injection_detected document_id=%s section_id=%s signatures=%s",
                document_id,
                section_id,
                [item.signature for item in findings],
            )
        return InjectionScanResult(
            is_injection=bool(findings),
            findings=findings,
            fenced_text=fenced,
            redacted_text=redacted,
        )

    def fence(self, text: str, document_id: str | None = None, section_id: str | None = None) -> str:
        """Wrap untrusted text so prompts cannot treat it as a system instruction."""
        header = f"UNTRUSTED_DOCUMENT_DATA document_id={document_id or 'unknown'} section_id={section_id or 'unknown'}"
        return f"<<<{header}>>>\n{text}\n<<<END_UNTRUSTED_DOCUMENT_DATA>>>"

    def redact(self, text: str) -> str:
        """Replace sentences that match injection signatures so they cannot be used as policy facts."""
        if not text:
            return ""
        sentences = re.split(r"(?<=[.!?])\s+", text)
        kept: list[str] = []
        for sentence in sentences:
            if any(pattern.search(sentence) for pattern, _label in self._compiled):
                kept.append("[INJECTION_FLAGGED_AND_IGNORED]")
            else:
                kept.append(sentence)
        return " ".join(kept)
