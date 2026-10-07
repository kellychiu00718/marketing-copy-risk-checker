"""검수 파이프라인. mode: rules | llm | cascade

cascade: 규칙 층이 '확신 높은 high' 위험을 이미 찾았으면 LLM 호출을 생략한다(비용 절감).
         그렇지 않으면 규칙 결과를 힌트로 LLM이 놓친 의미 위험을 추가로 찾는다.
어느 모드든 자동 승인은 없다. 결과는 항상 '사람 확인 필요 여부'만 알려준다.
"""
from datetime import date

from .config import MAX_CHARS
from .holidays import day_context
from .llm import run_llm
from .models import Finding, needs_human_review, overall_level
from .rules import run_rules


def review(text: str, launch: date | None, mode: str = "cascade") -> dict:
    if not text.strip():
        raise ValueError("검수할 문구가 비어 있습니다.")
    if len(text) > MAX_CHARS:
        raise ValueError(f"문구는 최대 {MAX_CHARS}자까지 검수할 수 있습니다 (현재 {len(text)}자).")
    findings: list[Finding] = []
    usage ={"input_tokens": 0, "output_tokens": 0}
    llm_called = False
    error = None

    rule_findings = run_rules(text, launch) if mode in ("rules", "cascade") else []
    findings += rule_findings

    confident_high = any(f.severity == "high" and f.confidence >= 0.9 for f in rule_findings)
    if mode == "llm" or (mode == "cascade" and not confident_high):
        try:
            llm_findings, usage = run_llm(text, launch, rule_findings)
            findings += llm_findings
            llm_called = True
        except Exception as e:  # API 장애여도 규칙 결과는 돌려주고, 사람 확인으로 넘긴다.
            error = f"{type(e).__name__}: {str(e)[:160]}"

    return {
        "mode": mode,
        "level": overall_level(findings),
        "needs_human_review": needs_human_review(findings) or error is not None,
        "findings": [f.to_dict() for f in findings],
        "context": day_context(launch),
        "llm_called": llm_called,
        "usage": usage,
        "error": error,
    }
