"""공휴일 맥락: '위험'이 아니라 참고 정보다. (B 방향 수요 예측의 달력 변수로도 쓴다.)"""
from datetime import date, timedelta

import yaml

from .config import DATA_DIR

_DOC = yaml.safe_load(open(DATA_DIR / "holidays_ko.yaml", encoding="utf-8"))
_BY_DATE = {r["date"]: r for r in _DOC["holidays"]}
_LOCAL = {(r["month"], r["day"]): r for r in _DOC["local_holidays"]}
COVERED_YEARS = sorted({r["date"][:4] for r in _DOC["holidays"]})
VERIFIED = bool(_DOC["meta"]["verified"])


def day_context(d: date | None) -> list[str]:
    """시작일에 대한 참고 문구 목록. 데이터 범위 밖 연도는 그 사실을 알린다."""
    if d is None:
        return []
    if str(d.year) not in COVERED_YEARS:
        return [f"{d.year}년 공휴일 데이터가 없습니다 (보유: {COVERED_YEARS[0]}~{COVERED_YEARS[-1]})."]
    out: list[str] = []
    h = _BY_DATE.get(d.isoformat())
    if h:
        out.append(f"공휴일: {h['name']}")
    elif d.weekday() >= 5:
        out.append("주말")
    # 연휴 길이: 앞뒤로 주말·공휴일이 이어지는 구간
    def off(x: date) -> bool:
        return x.weekday() >= 5 or x.isoformat() in _BY_DATE
    if off(d):
        a = b = d
        while off(a - timedelta(1)):
            a -= timedelta(1)
        while off(b + timedelta(1)):
            b += timedelta(1)
        n = (b - a).days + 1
        if n >= 3:
            out.append(f"{a.month}/{a.day}~{b.month}/{b.day} {n}일 연휴 구간")
    loc = _LOCAL.get((d.month, d.day))
    if loc:
        out.append(f"{loc['region']} 지방공휴일({loc['name']}) — 해당 지역에만 적용")
    return out
