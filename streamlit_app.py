import hashlib
import json
import re
import secrets
from datetime import date

import streamlit as st
from streamlit_sortables import sort_items

from preflight import store
from preflight.config import DAILY_LLM_LIMIT_GLOBAL, DAILY_LLM_LIMIT_PER_WORKSPACE, MAX_CHARS, PUBLIC_MODE
from preflight.export import LEVEL_LABEL, to_csv, to_frame, to_markdown, to_xlsx
from preflight.pipeline import review
from preflight.store import DECISION_LABEL

st.set_page_config(page_title="Marketing Copywriting Risk Checker", page_icon="✅", layout="wide")

LEVEL_ICON = {"clear": "🟢", "low": "🟡", "medium": "🟠", "high": "🔴"}
DECISION_ICON = {None: "🕓", "revise": "✏️", "approve": "✅", "hold": "⏸"}
SEV_RANK = {"low": 1, "medium": 2, "high": 3}
MODES = {
    "cascade": ("추천 (규칙 + AI)", "먼저 정해진 규칙으로 확인하고, 규칙으로 판단하기 어려운 부분만 AI가 읽습니다. 속도와 꼼꼼함의 균형이 가장 좋아요."),
    "rules": ("빠른 확인 (AI 없이 규칙만)", "AI를 쓰지 않아 바로 끝나요. 대신 말의 뉘앙스나 문맥은 보지 못합니다."),
    "llm": ("꼼꼼한 확인 (AI가 전부 읽기)", "AI가 항상 문구 전체를 읽어요. 가장 꼼꼼하지만 조금 느리고 사용 비용이 듭니다."),
}

# 설명 글자 대비(WCAG AA 4.5:1) 보정 + 보드 색(라이트/다크). 보드는 iframe이라 prefers-color-scheme으로 따로 맞춘다.
st.markdown(
    """<style>
[data-testid="stCaptionContainer"] { color: #555866 !important; }
@media (prefers-color-scheme: dark) { [data-testid="stCaptionContainer"] { color: #b9bcc8 !important; } }
/* 반응형: 좁은 화면(휴대폰)에서는 제목을 줄이고 여백을 좁히며, 표는 가로로 밀어서 볼 수 있게 한다. */
@media (max-width: 640px) {
  [data-testid="stMainBlockContainer"] { padding: 2.5rem 1rem 3rem !important; }
  h1 { font-size: 1.65rem !important; line-height: 1.25 !important; }
  [data-testid="stTabs"] button { padding-left: 0.4rem !important; padding-right: 0.4rem !important; }
  [data-testid="stTabs"] button p { font-size: 0.9rem !important; }
  [data-testid="stDataFrame"] { overflow-x: auto; }
}
</style>""",
    unsafe_allow_html=True,
)
BOARD_CSS = """
.sortable-component { display: flex; flex-direction: row; gap: 10px; align-items: flex-start; }
.sortable-container { flex: 1 1 0; min-width: 0; background: #f3f4f7; border-radius: 8px; padding: 6px; min-height: 150px; }
.sortable-container-header { font-weight: 600; font-size: 0.9rem; padding: 4px 6px 8px; color: #262730; }
.sortable-item { background: #ffffff; color: #262730; border: 1px solid #c9ccd6; border-radius: 6px;
                 font-size: 0.82rem; line-height: 1.35; margin: 0 0 6px 0; padding: 7px 9px; white-space: normal; }
.sortable-container:not(:has(.sortable-item))::after { content: "여기로 끌어 놓기"; display: block; color: #5d6070;
                 font-size: 0.8rem; padding: 14px 6px; text-align: center; }
/* 좁은 화면: 4열을 2×2로 접어 카드 글자가 세로로 쪼개지지 않게 한다. */
@media (max-width: 560px) {
  .sortable-component { flex-wrap: wrap; }
  .sortable-container { flex: 1 1 calc(50% - 10px); min-width: calc(50% - 10px); }
}
@media (prefers-color-scheme: dark) {
  .sortable-container { background: #262833; }
  .sortable-container-header { color: #f0f1f5; }
  .sortable-item { background: #1a1c24; color: #f0f1f5; border-color: #4a4d5c; }
  .sortable-container:not(:has(.sortable-item))::after { color: #b9bcc8; }
}
"""

_MD_SPECIAL = re.compile(r"([\\`*_{}\[\]()#+\-.!|>~<])")


def md(s: object) -> str:
    """사용자 입력·AI 출력을 마크다운으로 해석하지 않도록 특수문자를 이스케이프(링크·외부 이미지 삽입 방지)."""
    return _MD_SPECIAL.sub(r"\\\1", str(s))


def get_owner() -> str:
    """local: 'local' 고정. public: URL의 작업 공간 코드(없으면 새로 발급)로 사용자별 기록을 격리한다."""
    if not PUBLIC_MODE:
        return "local"
    code = st.query_params.get("w", "")
    if not re.fullmatch(r"[A-Za-z0-9_-]{8,32}", code or ""):
        code = secrets.token_urlsafe(9)
        st.query_params["w"] = code
    return code


OWNER = get_owner()

with st.sidebar:
    st.markdown("### 사용 방법")
    st.markdown("1. **검수하기** 탭에 문구를 넣고 검수\n2. 결과를 보고 **결정**을 기록\n3. **보드** 탭에서 카드를 끌어 상태를 바꾸고 수정\n4. **기록** 탭에서 지난 결정을 보고 파일로 내려받기")
    st.caption("이 도구는 게시·발송을 하지 않습니다. 결정은 이 도구 안에 기록만 됩니다.")
    used = store.llm_calls_today(OWNER)
    st.caption(f"오늘 AI 검수 사용: {used} / {DAILY_LLM_LIMIT_PER_WORKSPACE}회")
    if PUBLIC_MODE:
        st.markdown("**내 작업 공간**")
        st.code(OWNER, language=None)
        st.caption("이 페이지 주소(URL)를 북마크하면 내 기록을 다시 볼 수 있어요. 주소를 아는 사람은 누구나 같은 기록을 볼 수 있으니, 팀원에게만 공유하고 민감한 정보는 넣지 마세요.")
    dev = st.toggle("개발자 모드", help="검수 결과의 원본 데이터(JSON)와 사용량을 보여줍니다. 일반 사용에는 필요 없어요.")

st.title("Marketing Copywriting Risk Checker")
st.caption("캠페인 문구 사전 검수 보조 도구 (프로토타입) · 최종 판단은 항상 사람이 합니다 · 개인 포트폴리오 프로젝트이며 특정 기업의 공식 도구가 아닙니다")


def render_findings(res: dict) -> None:
    if res["error"]:
        st.warning(f"AI 판독에 실패해 규칙 결과만 보여드려요. 사람이 직접 확인해 주세요. ({md(res['error'])})")
    if not res["findings"]:
        st.info("자동 점검에서 걸린 항목이 없습니다. '안전하다'는 보증은 아니에요.")
    for f in sorted(res["findings"], key=lambda x: -SEV_RANK[x["severity"]]):
        with st.container(border=True):
            if f["source"] == "rule":
                who = "규칙 일치"
            else:
                who = f"AI 판단 · AI 자체 확신도 {f['confidence']:.0%}"
            st.markdown(f"**{LEVEL_ICON[f['severity']]} {md(f['category'])}** · {who}")
            st.markdown(f"> {md(f['evidence_quote'])}")
            st.markdown(md(f["rationale"]))
            st.markdown(f"**제안:** {md(f['suggestion'])}")
    if any(f["source"] == "llm" for f in res["findings"]):
        st.caption("※ AI 확신도는 AI가 스스로 매긴 값이며 정확한 확률이 아닙니다.")
    if dev:
        st.caption(f"모드 {res['mode']} · AI 호출 {'예' if res['llm_called'] else '아니오'} · 토큰 {res['usage']['input_tokens']}/{res['usage']['output_tokens']}")
        with st.expander("원본 데이터 (JSON)"):
            st.code(json.dumps(res, ensure_ascii=False, indent=2), language="json")


def headline(res: dict) -> None:
    st.subheader(f"{LEVEL_ICON[res['level']]} {LEVEL_LABEL[res['level']]}")
    n = len(res["findings"])
    st.caption(f"확인할 항목 {n}건" + (" · 아래에서 근거를 확인하고 결정을 기록하세요" if n else ""))
    if res.get("context"):
        st.caption("📅 시작일 참고: " + " · ".join(res["context"]))


def run_review(text: str, launch: date, mode: str, parent_id: int | None = None) -> int | None:
    st.session_state["limit_note"] = None
    if mode != "rules" and (
        store.llm_calls_today(OWNER) >= DAILY_LLM_LIMIT_PER_WORKSPACE or store.llm_calls_today() >= DAILY_LLM_LIMIT_GLOBAL
    ):
        mode = "rules"
        st.session_state["limit_note"] = "오늘 AI 사용 한도에 도달해 규칙만으로 검수했어요. 내일 다시 AI 검수를 쓸 수 있습니다."
    try:
        with st.spinner("검수 중… (보통 5~15초)"):
            res = review(text.strip(), launch, mode)
    except ValueError as e:
        st.error(str(e))
        return None
    st.session_state["res"] = res
    st.session_state["rid"] = store.log_review(OWNER, text.strip(), launch.isoformat(), res, parent_id)
    return st.session_state["rid"]


tab_check, tab_board, tab_log = st.tabs(["① 검수하기", "② 보드", "③ 기록 · 내보내기"])

# ───────────────────────── ① 검수하기 ─────────────────────────
with tab_check:
    left, right = st.columns([1, 1.3], gap="large")
    with left:
        text = st.text_area(
            "캠페인 문구 / 이벤트 이름", height=170, max_chars=MAX_CHARS,
            placeholder="예: 여름 한정 시원한 신메뉴 출시 기념 이벤트",
            help=f"최대 {MAX_CHARS}자까지 입력할 수 있어요. 한글·영문·숫자·띄어쓰기 모두 1자로 셉니다.",
        )
        launch = st.date_input("캠페인 / 이벤트 예정 시작일", value=date.today(),
                               help="추모일·공휴일과 겹치는지 확인하는 데 쓰입니다.")
        with st.expander("검수 방식 선택 (선택 사항 · 기본값 추천)"):
            mode = st.radio(
                "검수 방식", list(MODES), format_func=lambda k: MODES[k][0],
                captions=[v[1] for v in MODES.values()], label_visibility="collapsed",
            )
        if st.button("검수하기", type="primary", disabled=not text.strip(), width="stretch"):
            if run_review(text, launch, mode):
                st.rerun()  # 사이드바의 '오늘 AI 검수 사용' 횟수가 이번 검수까지 반영되도록 다시 그린다.
        if not text.strip():
            st.caption("문구를 먼저 입력하면 '검수하기' 버튼이 켜져요.")

    with right:
        res = st.session_state.get("res")
        rid = st.session_state.get("rid")
        cur_row = store.get(OWNER, rid) if rid else None
        if not res or not cur_row:
            st.info("문구를 입력하고 '검수하기'를 눌러 보세요.")
        else:
            if st.session_state.get("limit_note"):
                st.warning(st.session_state["limit_note"])
            headline(res)
            cur = cur_row["decision"]
            st.markdown(f"**이 결과를 보고 어떻게 하시겠어요?** (현재 상태: {DECISION_ICON[cur]} {DECISION_LABEL[cur]})")
            st.markdown(
                "- ✅ **게시 가능** — 이대로 내보내도 된다고 기록해요\n"
                "- ✏️ **수정 필요** — 고쳐야 할 카드로 표시해요 (보드의 '수정 필요' 열)\n"
                "- ⏸ **보류** — 결정을 잠시 미뤄요"
            )
            # 카드마다 폼과 메모 입력칸의 key를 따로 둔다. key가 같으면 앞 카드의 메모가 그대로 남는다.
            with st.form(f"decision_form_{rid}", border=False):
                note = st.text_area("결정 메모 (선택)", height=80, max_chars=300, key=f"note_{rid}",
                                    placeholder="예: 날짜를 하루 미루기로 함 / 법무팀 확인 후 게시 예정")
                c1, c2, c3 = st.columns(3)
                pick = None
                if c1.form_submit_button("✅ 게시 가능", width="stretch"):
                    pick = "approve"
                if c2.form_submit_button("✏️ 수정 필요", width="stretch"):
                    pick = "revise"
                if c3.form_submit_button("⏸ 보류", width="stretch"):
                    pick = "hold"
            if pick:
                if store.set_decision(OWNER, rid, pick, note.strip()):
                    st.success(f"'{DECISION_LABEL[pick]}'(으)로 기록했어요. '② 보드'와 '③ 기록' 탭에서 볼 수 있습니다.")
                else:
                    st.error("기록하지 못했어요. 다시 시도해 주세요.")
            st.divider()
            st.markdown("**근거 자세히 보기**")
            render_findings(res)

# ───────────────────────── ② 보드 ─────────────────────────
with tab_board:
    rows = store.all_reviews(OWNER, 40)
    if not rows:
        st.info("아직 검수한 카드가 없어요. '① 검수하기'에서 먼저 검수해 보세요.")
    else:
        st.caption("카드를 끌어서 다른 열에 놓으면 상태가 바뀌고 기록됩니다. 끌기 어려우면 아래 '카드 상세'에서 상태를 고를 수 있어요. 최근 40개까지 보여요.")
        by_id = {r["id"]: r for r in rows}
        cols = [(None, "🕓 검토 대기"), ("revise", "✏️ 수정 필요"), ("approve", "✅ 게시 가능"), ("hold", "⏸ 보류")]

        def card(r: dict) -> str:
            t = r["draft"].replace("\n", " ")
            return f"#{r['id']} {LEVEL_ICON[r['result'].get('level', 'clear')]} {t[:22]}{'…' if len(t) > 22 else ''}"

        board = [{"header": h, "items": [card(r) for r in rows if r["decision"] == k]} for k, h in cols]
        # 카드 구성이 바뀌면 key도 바꿔서 보드를 새로 그린다. key가 고정이면 탭을 오가거나 결정을 기록한 뒤에도 옛 배치가 남는다.
        board_sig = hashlib.md5(json.dumps(board, ensure_ascii=False).encode()).hexdigest()[:8]
        moved = sort_items(board, multi_containers=True, direction="horizontal", key=f"board_{board_sig}", custom_style=BOARD_CSS)
        changed = False
        for (k, _), cont in zip(cols, moved):
            for it in cont["items"]:
                m = re.match(r"#(\d+)", it)
                rid_ = int(m.group(1)) if m else None
                if rid_ in by_id and by_id[rid_]["decision"] != k:
                    store.set_decision(OWNER, rid_, k, "보드에서 이동")
                    changed = True
        if changed:
            st.rerun()

        st.divider()
        st.markdown("#### 카드 상세 · 수정")
        pid = st.selectbox(
            "카드 선택", [r["id"] for r in rows],
            format_func=lambda i: f"#{i} · {DECISION_LABEL[by_id[i]['decision']]} · {by_id[i]['draft'][:30]}",
        )
        sel = by_id[pid]
        d1, d2 = st.columns([1.2, 1], gap="large")
        with d1:
            headline(sel["result"])
            render_findings(sel["result"])
        with d2:
            st.markdown("**문구 수정 후 다시 검수**")
            new_text = st.text_area("수정할 문구", value=sel["draft"], height=140, max_chars=MAX_CHARS, key=f"edit_{pid}")
            new_date = st.date_input("캠페인 / 이벤트 예정 시작일", value=date.fromisoformat(sel["launch_date"]) if sel["launch_date"] else date.today(), key=f"date_{pid}")
            if st.button("수정해서 다시 검수 (새 카드로 저장)", key=f"redo_{pid}", width="stretch", disabled=not new_text.strip()):
                if run_review(new_text, new_date, "cascade", parent_id=pid):
                    st.success("새 카드를 '검토 대기'에 만들었어요. 원래 카드는 그대로 남아 있습니다.")
                    st.rerun()
            st.markdown("**상태 바꾸기** (끌어서 옮기기 어려울 때)")
            keys = [None, "revise", "approve", "hold"]
            s1, s2 = st.columns([2, 1])
            new_state = s1.selectbox("상태", keys, index=keys.index(sel["decision"]), key=f"state_{pid}",
                                     format_func=lambda k: f"{DECISION_ICON[k]} {DECISION_LABEL[k]}", label_visibility="collapsed")
            if s2.button("저장", key=f"save_state_{pid}", width="stretch", disabled=new_state == sel["decision"]):
                store.set_decision(OWNER, pid, new_state, "상세 화면에서 변경")
                st.rerun()
            trail = store.decision_trail(OWNER, pid)
            if trail:
                st.markdown("**결정 기록**")
                for t in trail:
                    st.caption(f"{t['ts'][5:16].replace('T', ' ')} · {DECISION_ICON[t['decision']]} {DECISION_LABEL[t['decision']]}" + (f" — {md(t['note'])}" if t["note"] else ""))
            if sel.get("parent_id"):
                st.caption(f"↩︎ #{sel['parent_id']} 카드를 수정해서 만든 카드예요.")

# ───────────────────────── ③ 기록 · 내보내기 ─────────────────────────
with tab_log:
    rows = store.all_reviews(OWNER, 500)
    if not rows:
        st.info("아직 기록이 없어요.")
    else:
        f1, f2 = st.columns(2)
        pick_dec = f1.multiselect("결정으로 거르기", list(DECISION_LABEL.values()), default=list(DECISION_LABEL.values()))
        pick_lv = f2.multiselect("위험도로 거르기", list(LEVEL_LABEL.values()), default=list(LEVEL_LABEL.values()))
        shown = [r for r in rows
                 if DECISION_LABEL[r["decision"]] in pick_dec and LEVEL_LABEL[r["result"].get("level", "clear")] in pick_lv]
        df = to_frame(shown)
        st.caption(f"{len(shown)}건 (전체 {len(rows)}건)")
        st.dataframe(df, width="stretch", hide_index=True)
        st.markdown("**내보내기**")
        e1, e2, e3 = st.columns(3)
        e1.download_button("📄 CSV (Excel·Google 스프레드시트용)", to_csv(df), "campaign_preflight_log.csv", "text/csv", width="stretch")
        e2.download_button("📊 Excel (.xlsx)", to_xlsx(df), "campaign_preflight_log.xlsx",
                           "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", width="stretch")
        e3.download_button("📝 Markdown (Notion에 붙여넣기용)", to_markdown(df), "campaign_preflight_log.md", "text/markdown", width="stretch")
        st.caption("Notion: Markdown 파일을 열어 내용을 복사해 Notion 페이지에 붙여넣으면 표로 들어가요. Google Drive: CSV나 Excel 파일을 업로드하면 됩니다.")

    with st.expander("내 기록 모두 삭제"):
        st.caption("이 작업 공간에 저장된 문구·결정 기록을 모두 지웁니다. 되돌릴 수 없어요. 내려받은 파일은 영향이 없습니다.")
        ok = st.checkbox("삭제하면 되돌릴 수 없다는 것을 이해했어요", key="del_ok")
        if st.button("모든 기록 삭제", disabled=not ok):
            n = store.delete_all(OWNER)
            st.session_state.pop("res", None)
            st.session_state.pop("rid", None)
            st.success(f"{n}건을 삭제했어요.")
            st.rerun()
