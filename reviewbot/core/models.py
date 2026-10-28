"""Core data models and contracts for ReviewBot CLI."""

from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any


class FixStatus(str, Enum):
    """Status of an AI-generated fix."""
    PROPOSED = "proposed"
    UNCHANGED = "unchanged"
    FAILED = "failed"


@dataclass
class Issue:
    """Represents a code issue detected by static analysis (Work 2)."""
    file: str
    line: int
    tool: str
    code: str
    message: str
    severity: str = "error"

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Issue":
        """Safely build an Issue instance from raw dictionary input."""
        return cls(
            file=str(data.get("file", "")).strip(),
            line=int(data.get("line", 1) or 1),
            tool=str(data.get("tool", "unknown")).strip(),
            code=str(data.get("code", "")).strip(),
            message=str(data.get("message", "")).strip(),
            severity=str(data.get("severity", "error")).strip().lower(),
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert Issue to dictionary format."""
        return asdict(self)


@dataclass
class FixResult:
    """Represents the structured result of a fix proposal sent to Work 4."""
    file: str
    issue_codes: list[str] = field(default_factory=list)
    explanation: str = ""
    original_code: str = ""
    fixed_code: str = ""
    patch: str = ""
    status: str = FixStatus.PROPOSED.value

    def to_dict(self) -> dict[str, Any]:
        """Serialize FixResult to standard dictionary contract expected by Work 4."""
        return {
            "file": self.file,
            "issue_codes": self.issue_codes,
            "explanation": self.explanation,
            "original_code": self.original_code,
            "fixed_code": self.fixed_code,
            "patch": self.patch,
            "status": self.status,
        }
