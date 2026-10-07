from dataclasses import asdict, dataclass

from .config import REVIEW_THRESHOLD, SEVERITY_RANK


@dataclass
class Finding:
    category: str
    severity: str  # low | medium | high
    evidence_quote: str
    rationale: str
    suggestion: str
    confidence: float
    source: str  # rule | llm

    def to_dict(self) -> dict:
        return asdict(self)


def overall_level(findings: list[Finding]) -> str:
    if not findings:
        return "clear"
    top = max(SEVERITY_RANK[f.severity] for f in findings)
    return {1: "low", 2: "medium", 3: "high"}[top]


def needs_human_review(findings: list[Finding]) -> bool:
    return any(SEVERITY_RANK[f.severity] >= SEVERITY_RANK[REVIEW_THRESHOLD] for f in findings)
