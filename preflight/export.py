"""기록 내보내기: CSV / Excel / Markdown(Notion에 붙여넣기용).

CSV·Excel은 사용자가 입력한 문구가 그대로 셀에 들어간다. '=' '+' '-' '@'로 시작하면 Excel이 수식으로
실행할 수 있어(수식 주입) 앞에 작은따옴표를 붙여 텍스트로 고정한다.
"""
import io

import pandas as pd

from .store import DECISION_LABEL

LEVEL_LABEL = {"clear": "문제 신호 없음", "low": "참고", "medium": "담당자 확인 권장", "high": "게시 전 반드시 확인"}
COLUMNS = ["번호", "검수 일시", "시작 예정일", "캠페인 문구", "위험도", "주요 발견", "결정", "결정 메모", "결정 일시"]
_FORMULA_START = ("=", "+", "-", "@", "\t", "\r")


def neutralize(v):
    """수식으로 해석될 수 있는 문자열 앞에 ' 를 붙인다."""
    if isinstance(v, str) and v.startswith(_FORMULA_START):
        return "'" + v
    return v


def to_frame(rows: list[dict]) -> pd.DataFrame:
    out = []
    for r in rows:
        res = r["result"]
        found = " / ".join(
            f"[{f['category']}] {f['evidence_quote']}" for f in res.get("findings", [])
        ) or "-"
        out.append([
            r["id"], r["ts"].replace("T", " "), r["launch_date"] or "", r["draft"],
            LEVEL_LABEL.get(res.get("level", "clear"), ""), found,
            DECISION_LABEL.get(r["decision"], "검토 대기"), r["note"] or "",
            (r["decided_ts"] or "").replace("T", " "),
        ])
    return pd.DataFrame(out, columns=COLUMNS)


def _safe(df: pd.DataFrame) -> pd.DataFrame:
    return df.map(neutralize)


def to_csv(df: pd.DataFrame) -> bytes:
    return _safe(df).to_csv(index=False).encode("utf-8-sig")  # BOM: Excel에서 한글 깨짐 방지


def to_xlsx(df: pd.DataFrame) -> bytes:
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as w:
        _safe(df).to_excel(w, index=False, sheet_name="검수 기록")
        ws = w.sheets["검수 기록"]
        for col, width in zip("ABCDEFGHI", (6, 20, 12, 40, 18, 50, 12, 30, 20)):
            ws.column_dimensions[col].width = width
    return buf.getvalue()


def to_markdown(df: pd.DataFrame) -> str:
    esc = lambda s: str(s).replace("|", "\\|").replace("\n", " ")  # noqa: E731
    lines = ["| " + " | ".join(df.columns) + " |", "|" + "---|" * len(df.columns)]
    lines += ["| " + " | ".join(esc(v) for v in row) + " |" for row in df.itertuples(index=False)]
    return "\n".join(lines)
