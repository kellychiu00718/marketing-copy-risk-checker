"""감사 로그: 어떤 문구를 검수했고, 사람이 언제 어떻게 결정했는지 SQLite에 남긴다.

- 모든 조회·수정은 owner(작업 공간 코드)로 격리한다. 다른 owner의 기록은 읽을 수도, 바꿀 수도 없다.
- decision 값: None(검토 대기) | approve(게시 가능) | revise(수정 필요) | hold(보류)
- 결정이 바뀔 때마다 decisions 테이블에 한 줄씩 쌓아서 '어떻게 결정했는지' 과정을 추적한다.
"""
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from zoneinfo import ZoneInfo

from .config import DB_PATH, PUBLIC_MODE

DECISION_LABEL = {None: "검토 대기", "revise": "수정 필요", "approve": "게시 가능", "hold": "보류"}
KST = ZoneInfo("Asia/Seoul")


def _now() -> str:
    return datetime.now(KST).isoformat(timespec="seconds")


@contextmanager
def _conn():
    c = sqlite3.connect(DB_PATH, timeout=10)
    c.row_factory = sqlite3.Row
    try:
        c.execute(
            """CREATE TABLE IF NOT EXISTS reviews(
                id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, mode TEXT,
                draft TEXT, launch_date TEXT, result TEXT, decision TEXT, note TEXT)"""
        )
        cols = {r["name"] for r in c.execute("PRAGMA table_info(reviews)")}
        for name in ("parent_id INTEGER", "decided_ts TEXT", "owner TEXT", "llm_called INTEGER DEFAULT 0"):
            if name.split()[0] not in cols:  # 이전 버전 DB 마이그레이션
                c.execute(f"ALTER TABLE reviews ADD COLUMN {name}")
        c.execute(
            """CREATE TABLE IF NOT EXISTS decisions(
                id INTEGER PRIMARY KEY AUTOINCREMENT, review_id INTEGER, ts TEXT, decision TEXT, note TEXT)"""
        )
        if not PUBLIC_MODE:  # 로컬 개발: 예전 기록(owner 없음)을 'local'로 귀속
            c.execute("UPDATE reviews SET owner='local' WHERE owner IS NULL")
        yield c
        c.commit()
    except Exception:
        c.rollback()
        raise
    finally:
        c.close()


def log_review(owner: str, draft: str, launch_date: str | None, result: dict, parent_id: int | None = None) -> int:
    with _conn() as c:
        if parent_id is not None:  # 부모 카드도 같은 owner 것이어야 한다
            ok = c.execute("SELECT 1 FROM reviews WHERE id=? AND owner=?", (parent_id, owner)).fetchone()
            parent_id = parent_id if ok else None
        cur = c.execute(
            "INSERT INTO reviews(ts, mode, draft, launch_date, result, parent_id, owner, llm_called) VALUES (?,?,?,?,?,?,?,?)",
            (_now(), result["mode"], draft, launch_date, json.dumps(result, ensure_ascii=False),
             parent_id, owner, int(bool(result.get("llm_called")))),
        )
        return cur.lastrowid


def set_decision(owner: str, review_id: int, decision: str | None, note: str = "") -> bool:
    ts = _now()
    with _conn() as c:
        cur = c.execute("UPDATE reviews SET decision=?, note=?, decided_ts=? WHERE id=? AND owner=?",
                        (decision, note, ts, review_id, owner))
        if cur.rowcount == 0:
            return False
        c.execute("INSERT INTO decisions(review_id, ts, decision, note) VALUES (?,?,?,?)", (review_id, ts, decision, note))
        return True


def get(owner: str, review_id: int) -> dict | None:
    with _conn() as c:
        r = c.execute("SELECT * FROM reviews WHERE id=? AND owner=?", (review_id, owner)).fetchone()
    return _row(r) if r else None


def all_reviews(owner: str, limit: int = 200) -> list[dict]:
    with _conn() as c:
        rows = c.execute("SELECT * FROM reviews WHERE owner=? ORDER BY id DESC LIMIT ?", (owner, limit)).fetchall()
    return [_row(r) for r in rows]


def decision_trail(owner: str, review_id: int) -> list[dict]:
    with _conn() as c:
        rows = c.execute(
            "SELECT d.ts, d.decision, d.note FROM decisions d JOIN reviews r ON r.id=d.review_id "
            "WHERE d.review_id=? AND r.owner=? ORDER BY d.id", (review_id, owner)).fetchall()
    return [dict(r) for r in rows]


def llm_calls_today(owner: str | None = None) -> int:
    """오늘(KST) AI를 실제로 호출한 검수 수. owner=None이면 전체(서비스 전체 상한용)."""
    today = datetime.now(KST).date().isoformat()
    q, args = "SELECT COUNT(*) FROM reviews WHERE llm_called=1 AND ts LIKE ?", [today + "%"]
    if owner:
        q += " AND owner=?"
        args.append(owner)
    with _conn() as c:
        return c.execute(q, args).fetchone()[0]


def delete_all(owner: str) -> int:
    """내 작업 공간의 모든 기록 삭제(개인정보 삭제 요청용). 삭제한 검수 수를 돌려준다."""
    with _conn() as c:
        ids = [r["id"] for r in c.execute("SELECT id FROM reviews WHERE owner=?", (owner,))]
        for i in ids:
            c.execute("DELETE FROM decisions WHERE review_id=?", (i,))
        c.execute("DELETE FROM reviews WHERE owner=?", (owner,))
        return len(ids)


def _row(r: sqlite3.Row) -> dict:
    d = dict(r)
    d["result"] = json.loads(d["result"]) if d.get("result") else {}
    return d
