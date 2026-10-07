"""1단계 규칙 층: 날짜 캘린더 + 어휘 + 최상급 표현 + 검수 우회 시도. 빠르고 설명 가능하지만 문맥은 모른다.

Finding.confidence(규칙)는 확률이 아니라 '규칙 일치 가중치'다. 화면에는 숫자로 보여주지 않는다.
cascade가 LLM 호출을 건너뛸지(확실한 high 규칙 일치) 판단하는 내부 기준으로만 쓴다.
"""
import re
from datetime import date

import yaml

from .config import DATA_DIR
from .models import Finding


def _load(name: str):
    with open(DATA_DIR / name, encoding="utf-8") as f:
        return yaml.safe_load(f)


CALENDAR = _load("calendar_ko.yaml")
LEXICON = _load("lexicon.yaml")["categories"]


def _snippet(text: str, start: int, end: int, pad: int = 12) -> str:
    return text[max(0, start - pad): end + pad].replace("\n", " ")


def check_calendar(text: str, launch: date | None) -> list[Finding]:
    out: list[Finding] = []
    for e in CALENDAR:
        sev = "high" if e["kind"] == "memorial" else "medium"
        if launch and (launch.month, launch.day) == (e["month"], e["day"]):
            out.append(Finding(
                "역사·기념일 시점", sev, f"예정 시작일 {e['month']}월 {e['day']}일",
                f"예정 시작일이 {e['name']}({e['month']}/{e['day']})와 같은 날입니다.",
                "일정 변경 또는 문구·소재가 이 날의 의미와 충돌하지 않는지 담당자 확인.",
                0.95, "rule"))
        for kw in e["keywords"]:
            i = text.find(kw)
            if i >= 0:
                out.append(Finding(
                    "역사·기념일 언급", sev, _snippet(text, i, i + len(kw)),
                    f"문구에 {e['name']} 관련 표현('{kw}')이 있습니다.",
                    "맥락(추모·기념 목적인지, 판촉 목적인지)을 담당자가 확인.",
                    0.9, "rule"))
                break
    return out


def _first_term(text: str, terms: list[str]):
    for t in terms:
        i = text.find(t)
        if i >= 0:
            return t, i
    return None


def check_lexicon(text: str) -> list[Finding]:
    out: list[Finding] = []

    mil = LEXICON["military_imagery"]
    hit = _first_term(text, mil["terms"])
    if hit:
        t, i = hit
        out.append(Finding(
            mil["label"], mil["severity"], _snippet(text, i, i + len(t)),
            f"'{t}' 표현이 있습니다. 관용 표현일 수 있어 단독으로는 낮은 위험.",
            "추모일·기념일과 같은 시기에 쓰이지 않는지 확인.", 0.6, "rule"))

    el = LEXICON["election_linked"]
    hit = _first_term(text, el["terms"])
    if hit:
        t, i = hit
        out.append(Finding(
            el["label"], el["severity"], _snippet(text, i, i + len(t)),
            f"'{t}' 등 선거와 연결된 표현이 있습니다.",
            "선거 연계 혜택·소재는 게시 전에 법무 확인을 거치세요.", 0.7, "rule"))

    sup = LEXICON["superlative_claim"]
    win = sup.get("evidence_window", 40)
    for p in sup["patterns"]:
        m = re.search(p, text)
        if not m:
            continue
        around = text[max(0, m.start() - win): m.end() + win]
        if any(k in around for k in sup["evidence_markers"]):
            continue  # 가까운 곳에 근거 표기가 있으면 통과
        out.append(Finding(
            sup["label"], sup["severity"], _snippet(text, m.start(), m.end()),
            f"'{m.group(0)}' 단정·최상급 표현 근처에 근거(기준·조사·출처) 표기가 없습니다.",
            "근거 문구를 병기하거나 표현을 완화. 법무·표시광고 확인 필요.", 0.8, "rule"))
        break

    inj = LEXICON["injection_attempt"]
    for p in inj["patterns"]:
        m = re.search(p, text)
        if m:
            out.append(Finding(
                inj["label"], inj["severity"], _snippet(text, m.start(), m.end()),
                "문구 안에 AI에게 내리는 지시처럼 보이는 표현이 있습니다. 검수 대상이 아닌 내용이 섞였을 수 있습니다.",
                "문구를 다시 확인하고, 의도한 내용이 아니면 지시문을 지운 뒤 재검수하세요.", 0.85, "rule"))
            break
    return out


def run_rules(text: str, launch: date | None) -> list[Finding]:
    cal = check_calendar(text, launch)
    lex = check_lexicon(text)
    findings = cal + lex
    mil = [f for f in lex if f.category == LEXICON["military_imagery"]["label"]]
    if mil and any(f.severity == "high" for f in cal):
        findings.append(Finding(
            "결합 위험(추모일 × 군사 연상)", "high", mil[0].evidence_quote,
            "추모·기념일과 군사·무기 연상 표현이 같은 활동에 함께 쓰였습니다.",
            "소재 변경 또는 일정 조정을 우선 검토하고 담당 임원 확인을 거치세요.",
            0.95, "rule"))
    return findings
