"""공휴일 데이터 생성기: 법정 공휴일 규칙 → data/holidays_ko.yaml (연도별 실제 날짜).

규칙 출처: 나무위키 '공휴일/대한민국' (2026-10-06 KST 열람; 공휴일에 관한 법률 제2·3조 인용).
  ※ 2차 출처이므로 공개 배포 전 한국천문연구원 월력요항·법령 원문으로 대조해야 한다.
음력 변환: korean-lunar-calendar. 임시공휴일은 정부가 수시 지정하므로 이 파일에 없다.

사용: .venv/bin/python scripts/build_holidays.py [시작연도 끝연도]   (기본 2026 2028)
"""
import sys
from datetime import date, timedelta
from pathlib import Path

import yaml
from korean_lunar_calendar import KoreanLunarCalendar

YEARS = range(int(sys.argv[1]), int(sys.argv[2]) + 1) if len(sys.argv) == 3 else range(2026, 2029)
OUT = Path(__file__).resolve().parent.parent / "data" / "holidays_ko.yaml"


def lunar(y: int, m: int, d: int) -> date:
    c = KoreanLunarCalendar()
    c.setLunarDate(y, m, d, False)
    return date.fromisoformat(c.SolarIsoFormat())


def is_weekend(d: date) -> bool:
    return d.weekday() >= 5


def build_year(y: int) -> list[dict]:
    # name, date, substitutable(일반 공휴일 규칙)
    singles: list[tuple[str, date, bool]] = [
        ("신정", date(y, 1, 1), False),
        ("삼일절", date(y, 3, 1), True),
        ("부처님오신날", lunar(y, 4, 8), True),
        ("어린이날", date(y, 5, 5), True),
        ("현충일", date(y, 6, 6), False),
        ("광복절", date(y, 8, 15), True),
        ("개천절", date(y, 10, 3), True),
        ("한글날", date(y, 10, 9), True),
        ("성탄절", date(y, 12, 25), True),
    ]
    if y >= 2026:  # 2026년부터 공휴일 (나무위키: 노동절 신규, 제헌절 재지정)
        singles += [("노동절", date(y, 5, 1), True), ("제헌절", date(y, 7, 17), True)]
    if y == 2026:  # 제9회 전국동시지방선거 (공직선거법 제34조 임기만료 선거일 = 공휴일)
        singles.append(("지방선거일", date(2026, 6, 3), False))

    seollal = lunar(y, 1, 1)
    chuseok = lunar(y, 8, 15)
    blocks = {
        "설날 연휴": [seollal - timedelta(1), seollal, seollal + timedelta(1)],
        "추석 연휴": [chuseok - timedelta(1), chuseok, chuseok + timedelta(1)],
    }

    base: dict[date, list[str]] = {}
    for n, d, _ in singles:
        base.setdefault(d, []).append(n)
    for n, days in blocks.items():
        for d in days:
            base.setdefault(d, []).append(n)

    # 대체공휴일: 날짜별로 최대 1일. 설날·추석은 '일요일 또는 다른 공휴일과 겹침'(토요일은 제외).
    need: list[tuple[date, str]] = []  # (대체 기준일(블록은 마지막 날), 이름)
    for d, names in base.items():
        ordinary = [n for n, dd, sub in singles if dd == d and sub]
        if ordinary and (is_weekend(d) or len(names) > 1):
            need.append((d, ordinary[0]))
    for n, days in blocks.items():
        overlap = any(d.weekday() == 6 or len(base[d]) > 1 for d in days)
        if overlap:
            need.append((days[-1], n))

    taken = set(base)
    subs: list[dict] = []
    for d, n in sorted(need):
        s = d + timedelta(1)
        while is_weekend(s) or s in taken:
            s += timedelta(1)
        taken.add(s)
        subs.append({"date": s.isoformat(), "name": f"대체공휴일({n})", "type": "substitute"})

    rows = [{"date": d.isoformat(), "name": " / ".join(names),
             "type": "election" if "지방선거일" in names else "holiday"}
            for d, names in sorted(base.items())]
    return sorted(rows + subs, key=lambda r: r["date"])


def main() -> None:
    doc = {
        "meta": {
            "source": "나무위키 '공휴일/대한민국' (2026-10-06 KST 열람) + 공휴일에 관한 법률 제2·3조 인용분",
            "verified": False,
            "note": "임시공휴일은 정부 지정 시 추가됨(이 목록에 없음). 공개 배포 전 한국천문연구원 월력요항으로 대조.",
            "generator": "scripts/build_holidays.py",
        },
        "local_holidays": [  # 지방공휴일: 해당 지역 공무원에게만 적용, 전국 공휴일 아님
            {"month": 4, "day": 3, "name": "제주 4·3 희생자 추념일", "region": "제주특별자치도", "since": 2018},
            {"month": 5, "day": 18, "name": "5·18민주화운동 기념일", "region": "광주광역시", "since": 2020},
        ],
        "holidays": [r for y in YEARS for r in build_year(y)],
    }
    OUT.write_text(yaml.safe_dump(doc, allow_unicode=True, sort_keys=False), encoding="utf-8")
    print(f"wrote {OUT} ({len(doc['holidays'])} rows, {YEARS.start}-{YEARS.stop - 1})")


if __name__ == "__main__":
    main()
