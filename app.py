"""ช่วงนี้คุณคิดอย่างไรกับฉัน? — anonymous mood wheel (Streamlit).

Routes (query params)
  /                         home: create a board · open a link · owner login
  /?b=BOARD                 voting page (open boards, or invite boards → asks for code)
  /?b=BOARD&c=CODE          voting page with personal invite code pre-filled
  /?b=BOARD&owner=1         owner login for that board
  /?b=BOARD&k=OWNERKEY      private owner link (key is removed from the URL after login)
"""
from __future__ import annotations

import os
from urllib.parse import parse_qs, urlparse

import altair as alt
import pandas as pd
import streamlit as st

from moodwheel import logic, security, ui, viz
from moodwheel.feelings import FEELING_BY_CODE, FEELINGS, GROUPS, INTENSITIES, MAX_FEELINGS_PER_VOTE, describe, feelings_in
from moodwheel.periods import PERIOD_TYPES, next_period_start, period_key, period_label, th_date
from moodwheel.store import (
    MAX_CODES_PER_BATCH, MIN_REVEAL_CEIL, MIN_REVEAL_FLOOR, NAME_MAX, Store, ValidationError, VoteResult,
)

APP_TITLE = "ช่วงนี้คิดยังไงกับฉัน"
MAX_FAILS = 10
GROUP_HEART = {"pos": "💚", "neu": "💛", "neg": "❤️"}

st.set_page_config(page_title=APP_TITLE, page_icon="💜", layout="centered", initial_sidebar_state="collapsed")
ui.inject_css()


# ---------------------------------------------------------------- infrastructure
def _secret(name: str) -> str | None:
    val = os.environ.get(name)
    if val:
        return val
    try:
        v = st.secrets.get(name)
        return str(v) if v else None
    except Exception:  # no secrets.toml at all
        return None


@st.cache_resource(show_spinner=False)
def get_store(url: str) -> Store:
    return Store(url)


def store() -> Store:
    return get_store(_secret("DATABASE_URL") or "sqlite:///moodwheel.db")


def base_url() -> str:
    u = _secret("APP_URL")
    if not u:
        try:
            u = st.context.url
        except Exception:
            u = None
    if not u:
        return "http://localhost:8501"
    p = urlparse(u)
    path = p.path.split("/~/+")[0]  # Streamlit Cloud internal iframe path
    return f"{p.scheme}://{p.netloc}{path}".rstrip("/")


def vote_link(bid: str, code: str | None = None) -> str:
    return f"{base_url()}/?b={bid}" + (f"&c={security.normalize(code)}" if code else "")


def owner_link(bid: str, key: str | None = None) -> str:
    return f"{base_url()}/?b={bid}" + (f"&k={security.normalize(key)}" if key else "&owner=1")


def go(**params) -> None:
    st.query_params.clear()
    for k, v in params.items():
        if v is not None:
            st.query_params[k] = v
    st.rerun()


def ss_inc(key: str) -> int:
    st.session_state[key] = st.session_state.get(key, 0) + 1
    return st.session_state[key]


def parse_link(text: str) -> tuple[str, str]:
    """Accept a full link, '?b=..&c=..', or a bare board id. Returns (board_id, code)."""
    text = (text or "").strip()
    if "b=" in text:
        q = parse_qs(urlparse(text if "://" in text else "http://x/" + text.lstrip("/")).query)
        return security.normalize_board_id(q.get("b", [""])[0]), security.normalize((q.get("c") or q.get("k") or [""])[0])
    return security.normalize_board_id(text), ""


def codes_text(name: str, bid: str, codes: list[str]) -> str:
    lines = [f"โค้ดเชิญสำหรับบอร์ด: {name} ({bid})",
             "ส่งให้ 1 คน / 1 โค้ด — แต่ละโค้ดโหวตได้ 1 ครั้งต่อรอบ", ""]
    lines += [f"{c}\t{vote_link(bid, c)}" for c in codes]
    return "\n".join(lines) + "\n"


def footer() -> None:
    st.html(f'<div style="text-align:center;color:{viz.MUTED};font-size:.8rem;margin-top:36px;font-family:{viz.FONT}">'
            f'💜 ไม่ระบุตัวตน · ไม่เก็บข้อมูลส่วนบุคคล · โอเพนซอร์ส</div>')


def demo_tallies() -> dict:
    data = {("admire", 2): 3, ("comfy", 1): 4, ("fun", 3): 2, ("trust", 2): 2, ("miss", 1): 2, ("grateful", 3): 2,
            ("worried", 1): 2, ("neutral", 1): 3, ("curious", 2): 1, ("annoyed", 1): 2, ("annoyed", 3): 1,
            ("hurt", 2): 2, ("weary", 1): 1, ("fresh", 3): 1, ("adore", 2): 2}
    return data


# ------------------------------------------------------------------------- home
def page_home() -> None:
    created = st.session_state.get("created")
    if created is not None:
        page_created(created)
        return

    ui.hero("ช่วงนี้คุณคิดอย่างไรกับฉัน?",
            "ให้เพื่อน ๆ แปะสติกเกอร์ความรู้สึกถึงคุณ แบบไม่ระบุตัวตน — จริง ๆ",
            eyebrow="💜 anonymous mood wheel")
    ui.graphic(viz.render_wheel(demo_tallies(), "น้อยหน่า", seed="demo", show_counts=False))
    st.caption("ภาพตัวอย่าง — แต่ละจุดคือสติกเกอร์ 1 ดวง ยิ่งใหญ่ยิ่งรู้สึกมาก")

    t_create, t_join, t_owner = st.tabs(["✨ สร้างบอร์ดของฉัน", "🗳️ ฉันได้รับลิงก์/โค้ด", "📊 ดูผลบอร์ดของฉัน"])
    with t_create:
        create_form()
    with t_join:
        st.write("วางลิงก์ที่ได้รับ หรือพิมพ์รหัสบอร์ด 8 ตัว")
        link = st.text_input("ลิงก์หรือรหัสบอร์ด", key="join_link", placeholder="https://…/?b=XXXXXXXX&c=XXXXX-XXXXX")
        code = st.text_input("โค้ดเชิญ (ถ้ามี)", key="join_code", placeholder="XXXXX-XXXXX")
        if st.button("ไปหน้าโหวต →", key="join_go", type="primary"):
            bid, c = parse_link(link)
            c = security.normalize(code) or c
            if not bid:
                st.error("รูปแบบลิงก์หรือรหัสบอร์ดไม่ถูกต้อง")
            elif store().get_board(bid) is None:
                st.error("ไม่พบบอร์ดนี้ — อาจถูกลบไปแล้ว หรือพิมพ์ผิด")
            else:
                go(b=bid, c=c or None)
    with t_owner:
        st.write("ใช้ **รหัสบอร์ด** และ **กุญแจเจ้าของ** ที่ได้ตอนสร้างบอร์ด (หรือวางลิงก์ส่วนตัวของเจ้าของ)")
        link = st.text_input("รหัสบอร์ด หรือ ลิงก์ส่วนตัวของเจ้าของ", key="own_link")
        key = st.text_input("กุญแจเจ้าของ", key="own_key", type="password", placeholder="XXXXX-XXXXX-XXXXX-XXXXX")
        if st.button("เข้าดูผล →", key="own_go", type="primary"):
            bid, k_from_link = parse_link(link)
            owner_login(bid, key or k_from_link)

    with st.expander("🔒 ไม่ระบุตัวตนจริงไหม? ทำงานยังไง"):
        st.html(ui.privacy_points())
        st.markdown(
            "- เจ้าของบอร์ดจะ **ไม่เห็นว่าใครใช้โค้ดไหนโหวต** และไม่เห็นจำนวนคนโหวตจนกว่าจะถึงเกณฑ์ขั้นต่ำ\n"
            "- ไม่มีช่องพิมพ์ข้อความอิสระ เพื่อไม่ให้จำสำนวนการเขียนได้\n"
            "- ตำแหน่งสติกเกอร์ในวงล้อเป็นการสุ่ม ไม่บอกลำดับว่าใครมาก่อน-หลัง\n"
            "- ข้อจำกัดที่ควรรู้: ถ้ามีคนโหวตน้อยมาก หรือเจ้าของถามทีละคนว่า 'โหวตยัง' ก็อาจเดาได้ "
            "ระบบจึงใช้เกณฑ์ขั้นต่ำและโหมด 'เปิดผลเมื่อจบรอบ' เป็นค่าเริ่มต้น"
        )
    footer()


def create_form() -> None:
    ephemeral_db_warning()
    name = st.text_input("ชื่อที่จะแสดง", max_chars=NAME_MAX, key="c_name", placeholder="เช่น น้อยหน่า")
    c1, c2 = st.columns(2)
    with c1:
        period = st.selectbox("โหวตได้คนละ 1 ครั้ง…", list(PERIOD_TYPES), index=list(PERIOD_TYPES).index("month"),
                              format_func=lambda k: PERIOD_TYPES[k], key="c_period")
    with c2:
        k = st.number_input("เปิดผลเมื่อมีคนโหวตอย่างน้อย (คน)", MIN_REVEAL_FLOOR, MIN_REVEAL_CEIL, MIN_REVEAL_FLOOR,
                            key="c_k", help="ยิ่งมาก ยิ่งเดายากว่าใครตอบอะไร")
    mode = st.radio(
        "วิธีเชิญ",
        ["invite", "open"],
        format_func=lambda m: {"invite": "🔐 โค้ดส่วนตัว (แนะนำ) — กันโหวตซ้ำได้จริง 1 คน/รอบ",
                               "open": "🔗 ลิงก์เดียวแชร์ได้ทุกคน — สะดวก แต่กันโหวตซ้ำได้แค่ในหน้าต่างเดียวกัน"}[m],
        key="c_mode",
    )
    n_codes = 10
    if mode == "invite":
        n_codes = st.number_input("จำนวนโค้ดเชิญ (1 คน : 1 โค้ด)", 1, MAX_CODES_PER_BATCH, 10, key="c_n",
                                  help="เพิ่มได้ภายหลัง")
    policy = st.radio(
        "การเปิดผล",
        ["closed", "live"],
        format_func=lambda p: {"closed": "🛡️ เปิดผลเมื่อจบแต่ละรอบ (ปลอดภัยที่สุด)",
                               "live": "⚡ ดูผลรอบปัจจุบันได้ทันทีเมื่อถึงเกณฑ์ (เดาได้ง่ายขึ้นถ้าคอยดูทีละคน)"}[p],
        key="c_policy",
    )
    if st.button("✨ สร้างบอร์ด", type="primary", key="c_submit", width="stretch"):
        try:
            created = store().create_board(name, period, mode, int(k), policy, int(n_codes))
        except ValidationError as e:
            st.error(str(e))
            return
        st.session_state["created"] = created
        st.session_state[f"owner:{created.board.id}"] = True
        st.rerun()


def page_created(created) -> None:
    b = created.board
    ui.hero("บอร์ดพร้อมแล้ว 🎉", f"ช่วงนี้คุณคิดอย่างไรกับ <b>{ui.esc(b.display_name)}</b>?")
    ui.card(
        '<div style="font-weight:700;font-size:1.05rem">⚠️ เก็บกุญแจเจ้าของไว้ให้ดี — จะแสดงครั้งเดียว</div>'
        f'<div style="color:{viz.MUTED};font-size:.9rem;margin-top:4px">ระบบเก็บแบบ hash จึงกู้คืนไม่ได้ '
        "ถ้าหายต้องสร้างบอร์ดใหม่ · ห้ามส่งกุญแจนี้ให้คนอื่น</div>",
        tone="neu",
    )
    st.text_input("รหัสบอร์ด", b.id, disabled=True, key="cr_bid")
    st.markdown("**🔑 กุญแจเจ้าของ** (กดไอคอนมุมขวาของกล่องเพื่อคัดลอก)")
    st.code(created.owner_key, language=None)
    st.markdown("**ลิงก์ส่วนตัวของเจ้าของ** (เปิดแล้วเข้าดูผลได้เลย — เก็บไว้คนเดียว)")
    st.code(owner_link(b.id, created.owner_key), language=None)

    if b.mode == "open":
        st.markdown("**ลิงก์สำหรับแชร์ให้เพื่อน**")
        st.code(vote_link(b.id), language=None)
        txt = (f"บอร์ด: {b.display_name} ({b.id})\nลิงก์โหวต: {vote_link(b.id)}\n"
               f"กุญแจเจ้าของ (ห้ามแชร์): {created.owner_key}\nลิงก์เจ้าของ (ห้ามแชร์): {owner_link(b.id, created.owner_key)}\n")
    else:
        st.markdown(f"**ลิงก์เชิญส่วนตัว {len(created.codes)} ลิงก์** — ส่งให้ 1 คนต่อ 1 ลิงก์")
        st.dataframe(pd.DataFrame({"โค้ด": created.codes, "ลิงก์ส่วนตัว": [vote_link(b.id, c) for c in created.codes]}),
                     hide_index=True, width="stretch",
                     column_config={"ลิงก์ส่วนตัว": st.column_config.LinkColumn()})
        st.download_button("⬇️ ดาวน์โหลดลิงก์เชิญ (.txt)", codes_text(b.display_name, b.id, created.codes),
                           file_name=f"invite-codes-{b.id}.txt", mime="text/plain", key="cr_dl_codes")
        txt = (f"บอร์ด: {b.display_name} ({b.id})\nกุญแจเจ้าของ (ห้ามแชร์): {created.owner_key}\n"
               f"ลิงก์เจ้าของ (ห้ามแชร์): {owner_link(b.id, created.owner_key)}\n")
    st.download_button("🔑 ดาวน์โหลดกุญแจเจ้าของ (.txt)", txt, file_name=f"owner-key-{b.id}.txt", mime="text/plain",
                       key="cr_dl_key")
    st.divider()
    ok = st.checkbox("ฉันบันทึกกุญแจเจ้าของ" + (" และลิงก์เชิญ" if b.mode == "invite" else "") + "แล้ว", key="cr_ack")
    if st.button("ไปหน้าผลของฉัน →", type="primary", disabled=not ok, key="cr_done"):
        st.session_state.pop("created", None)
        go(b=b.id, owner="1")


# ------------------------------------------------------------------------- vote
def page_vote(bid: str, url_code: str) -> None:
    s = store()
    board = s.get_board(bid)
    if board is None:
        ui.hero("ไม่พบบอร์ดนี้ 🫥", "ลิงก์อาจพิมพ์ผิด หรือเจ้าของลบบอร์ดไปแล้ว")
        if st.button("← กลับหน้าแรก", key="nf_home"):
            go()
        return

    pk = period_key(board.period_type)
    next_round = th_date(next_period_start(board.period_type))
    voted_key = f"voted:{board.id}:{pk}"

    ui.card(
        f'<div style="display:flex;gap:16px;align-items:center">{ui.avatar(board.display_name)}'
        f'<div style="min-width:0"><div style="color:{viz.MUTED};font-size:.92rem">ช่วงนี้คุณคิดอย่างไรกับ</div>'
        f'<div style="font-family:Prompt,sans-serif;font-size:1.6rem;font-weight:700;line-height:1.25;word-break:break-word">'
        f'{ui.esc(board.display_name)}?</div>'
        f'<div style="margin-top:6px">{ui.anon_badge()} '
        f'{ui.pill("รอบ " + period_label(board.period_type, pk))}</div></div></div>'
    )

    if st.session_state.get(voted_key):
        ui.confetti_thanks(board.display_name, next_round)
        st.html(f'<div style="margin-top:10px">{ui.privacy_points()}</div>')
        footer()
        return

    code = ""
    if board.mode == "invite":
        code = st.session_state.get(f"code:{board.id}", "")
        if not code:
            code = invite_gate(s, board, url_code, next_round)
            if not code:
                footer()
                return

    ballot(s, board, code, voted_key, next_round)
    footer()


def invite_gate(s: Store, board, url_code: str, next_round: str) -> str:
    """Return a verified code, or '' after rendering the code form / messages."""
    fails_key = "fail:code"
    if st.session_state.get(fails_key, 0) >= MAX_FAILS:
        st.error("ใส่โค้ดผิดหลายครั้งเกินไป — ปิดหน้านี้แล้วเปิดลิงก์ที่ได้รับใหม่อีกครั้ง")
        return ""

    def check(c: str) -> str:
        res = s.code_status(board.id, c)
        if res == VoteResult.OK:
            st.session_state[f"code:{board.id}"] = security.normalize(c)
            return security.normalize(c)
        if res == VoteResult.ALREADY_VOTED:
            ui.card(f'<div style="font-size:1.6rem">⏳</div><div style="font-weight:700;font-size:1.1rem">โค้ดนี้โหวตในรอบนี้แล้ว</div>'
                    f'<div style="color:{viz.MUTED}">โหวตครั้งถัดไปได้ตั้งแต่ <b>{ui.esc(next_round)}</b></div>', tone="neu")
            return "-"
        ss_inc(fails_key)
        st.error("โค้ดไม่ถูกต้อง หรือถูกยกเลิกแล้ว — ตรวจสอบกับคนที่ส่งลิงก์ให้คุณ")
        return ""

    if url_code and not st.session_state.get(f"urlcode_tried:{board.id}"):
        st.session_state[f"urlcode_tried:{board.id}"] = True
        got = check(url_code)
        if got == "-":
            return ""
        if got:
            return got

    st.write("บอร์ดนี้ใช้ **โค้ดเชิญส่วนตัว** (โค้ดใช้แค่กันโหวตซ้ำ ไม่ผูกกับคำตอบของคุณ)")
    typed = st.text_input("โค้ดเชิญ", key="gate_code", placeholder="XXXXX-XXXXX", max_chars=20)
    if st.button("ยืนยันโค้ด", type="primary", key="gate_go"):
        got = check(typed)
        if got and got != "-":
            st.rerun()
    return ""


def ballot(s: Store, board, code: str, voted_key: str, next_round: str) -> None:
    preview = st.empty()

    st.markdown("#### เลือกความรู้สึก (ได้สูงสุด 3 อย่าง)")
    picks: list[str] = []
    for gcode in ("pos", "neu", "neg"):
        g = GROUPS[gcode]
        opts = [f.code for f in feelings_in(gcode)]
        chosen = st.pills(
            f"{GROUP_HEART[gcode]} {g.label}",
            opts, selection_mode="multi", format_func=lambda c: describe(c), key=f"pick_{gcode}",
        ) or []
        picks += chosen

    intensity = st.segmented_control(
        "รู้สึกแค่ไหน", list(INTENSITIES), default=2, format_func=lambda i: INTENSITIES[i]["label"],
        key="intensity", required=True,
    ) or 2

    too_many = len(picks) > MAX_FEELINGS_PER_VOTE
    ui.graphic(where=preview, markup=viz.render_wheel(None, board.display_name, seed=board.id,
                                  selected={p: intensity for p in picks[:MAX_FEELINGS_PER_VOTE]}, show_counts=False))
    if picks and not too_many:
        st.html('<div style="font-size:.95rem">คำตอบของคุณ: ' +
                "".join(ui.pill(describe(p, intensity), GROUPS[FEELING_BY_CODE[p].group].tint) for p in picks) + "</div>")
    if too_many:
        st.warning(f"เลือกได้สูงสุด {MAX_FEELINGS_PER_VOTE} อย่าง — ตอนนี้เลือกไว้ {len(picks)} อย่าง")
    if board.mode == "open":
        st.caption("🔗 ลิงก์แบบเปิด: โปรดโหวตคนละ 1 ครั้งต่อรอบ เพื่อความยุติธรรม")
    st.caption("🔒 ส่งแล้วแก้ไขไม่ได้ · ไม่มีการเก็บชื่อ เวลา หรือข้อมูลอุปกรณ์")

    if st.button("💜 แปะสติกเกอร์", type="primary", disabled=(not picks or too_many), key="vote_submit",
                 width="stretch"):
        res = s.cast_vote(board.id, picks, intensity, code=code or None)
        if res in (VoteResult.OK, VoteResult.ALREADY_VOTED):
            st.session_state[voted_key] = True
            st.rerun()
        elif res == VoteResult.INVALID_CODE:
            st.session_state.pop(f"code:{board.id}", None)
            st.error("โค้ดนี้ถูกยกเลิกแล้ว — ติดต่อคนที่ส่งลิงก์ให้คุณ")
        elif res == VoteResult.BOARD_NOT_FOUND:
            st.error("บอร์ดนี้ถูกลบไปแล้ว")
        else:
            st.error("ข้อมูลไม่ถูกต้อง ลองเลือกใหม่อีกครั้ง")


# ------------------------------------------------------------------------ owner
def owner_login(bid: str, key: str) -> None:
    if st.session_state.get("fail:owner", 0) >= MAX_FAILS:
        st.error("ลองผิดหลายครั้งเกินไป — ปิดหน้านี้แล้วลองใหม่ภายหลัง")
        return
    bid = security.normalize_board_id(bid)
    if bid and key and store().verify_owner(bid, key):
        st.session_state[f"owner:{bid}"] = True
        go(b=bid, owner="1")
    else:
        ss_inc("fail:owner")
        st.error("รหัสบอร์ดหรือกุญแจเจ้าของไม่ถูกต้อง")


def page_owner(bid: str, url_key: str) -> None:
    s = store()
    bid = security.normalize_board_id(bid)
    board = s.get_board(bid) if bid else None
    if board is None:
        ui.hero("ไม่พบบอร์ดนี้ 🫥", "อาจถูกลบไปแล้ว หรือรหัสไม่ถูกต้อง")
        if st.button("← กลับหน้าแรก", key="onf_home"):
            go()
        return
    auth_key = f"owner:{board.id}"
    if url_key and not st.session_state.get(auth_key):
        owner_login(board.id, url_key)  # success → redirects without the key in the URL
        st.query_params.pop("k", None)  # failed: drop the bad key so it isn't retried on every rerun
        st.query_params["owner"] = "1"
    if url_key and st.session_state.get(auth_key):
        go(b=board.id, owner="1")
    if not st.session_state.get(auth_key):
        ui.hero("เข้าดูผลของฉัน", f"บอร์ด <b>{ui.esc(board.display_name)}</b> · {ui.esc(board.id)}")
        key = st.text_input("กุญแจเจ้าของ", type="password", key="ol_key", placeholder="XXXXX-XXXXX-XXXXX-XXXXX")
        if st.button("เข้าสู่ระบบ", type="primary", key="ol_go"):
            owner_login(board.id, key)
        return
    dashboard(s, board)


def show_results(pv: logic.PeriodView, board, *, seed_suffix: str = "") -> None:
    t = pv.tallies
    idx = logic.mood_index(t)
    word, wg = logic.mood_word(idx)
    tops = logic.top_feelings(t, 3)
    tied = [c for c, n in logic.top_feelings(t, len(FEELINGS)) if tops and n == tops[0][1]]
    if len(tied) > 1:  # don't crown one feeling arbitrarily
        top_val, top_sub = " ".join(FEELING_BY_CODE[c].emoji for c in tied), f"เท่ากัน {len(tied)} อย่าง · อย่างละ {tops[0][1]} ครั้ง"
    elif tops:
        top_val, top_sub = ui.esc(describe(tops[0][0])), f"{tops[0][1]} ครั้ง"
    else:
        top_val, top_sub = "—", ""
    ui.kpi_row([
        ("ผู้ร่วมโหวต", f"{pv.voters} คน", pv.label),
        ("ความรู้สึกอันดับ 1", top_val, top_sub),
        ("ดัชนีความรู้สึก", f"{idx:+d}" if idx is not None else "—", word),
    ])
    ui.graphic(viz.render_wheel(t, board.display_name, seed=f"{board.id}|{pv.key}{seed_suffix}"))
    c1, c2 = st.columns([1, 1])
    with c1:
        ui.graphic(viz.render_gauge(idx, word, wg, key=f"{pv.key}{seed_suffix}"))
    with c2:
        st.markdown("**สัดส่วนความรู้สึก**")
        st.html(viz.render_group_bar(logic.group_totals(t)))
        if tops:
            st.markdown("**ยอดนิยม**")
            st.html("".join(ui.pill(f"{describe(c)} · {n}", GROUPS[FEELING_BY_CODE[c].group].tint) for c, n in tops))
    st.caption("วางเมาส์/แตะที่ช่องในวงล้อเพื่อดูจำนวนแยกตามระดับความรู้สึก · ตำแหน่งจุดเป็นการสุ่ม")


def ephemeral_db_warning() -> None:
    """On a hosted deploy without DATABASE_URL, SQLite lives on a disk that is wiped on every reboot."""
    using_sqlite = not _secret("DATABASE_URL") or _secret("DATABASE_URL").startswith("sqlite")
    host = urlparse(base_url()).hostname or ""
    if using_sqlite and host not in ("localhost", "127.0.0.1"):
        st.warning("⚠️ แอปนี้ยังไม่ได้ตั้งค่า DATABASE_URL — ข้อมูลจะหายเมื่อแอปรีสตาร์ต "
                   "ให้ผู้ดูแลแอปตั้งค่าฐานข้อมูล PostgreSQL ตามคู่มือใน README")


def dashboard(s: Store, board) -> None:
    ephemeral_db_warning()
    view = logic.owner_view(s, board)
    top = st.columns([5, 1])
    with top[0]:
        ui.card(
            f'<div style="display:flex;gap:14px;align-items:center">{ui.avatar(board.display_name, 54)}<div>'
            f'<div style="color:{viz.MUTED};font-size:.88rem">แดชบอร์ดของ</div>'
            f'<div style="font-family:Prompt,sans-serif;font-size:1.4rem;font-weight:700">{ui.esc(board.display_name)}</div>'
            f'<div>{ui.pill("รอบ: " + PERIOD_TYPES[board.period_type])}{ui.pill("เกณฑ์ ≥ " + str(board.min_reveal) + " คน")}'
            f'{ui.pill("🔐 โค้ดส่วนตัว" if board.mode == "invite" else "🔗 ลิงก์เปิด")}</div></div></div>', pad="16px 20px")
    with top[1]:
        st.write("")
        if st.button("ออก", key="logout"):
            st.session_state.pop(f"owner:{board.id}", None)
            go()

    t_now, t_hist, t_links, t_set = st.tabs(["📊 ผลล่าสุด", "🗓️ ย้อนหลัง", "🔗 ลิงก์ & โค้ด", "⚙️ ตั้งค่า"])

    with t_now:
        cur = view.current
        if cur.revealed:
            st.subheader(f"รอบนี้ · {cur.label}")
            show_results(cur, board)
        else:
            msg = {
                "sealed": ("🔒", "ผลรอบนี้ถูกปิดผนึก", f"จะเปิดให้ดูวันที่ {th_date(view.opens_on)} (ถ้ามีคนโหวตถึง {board.min_reveal} คน) "
                           "— ระหว่างนี้ระบบไม่บอกแม้แต่จำนวนคนโหวต เพื่อไม่ให้เดาได้ว่าใครตอบอะไร"),
                "below_threshold": ("👥", "ยังไม่ถึงเกณฑ์", f"ต้องมีคนโหวตอย่างน้อย {board.min_reveal} คน ผลจึงจะแสดง "
                                    "(ระบบไม่บอกจำนวนจริงเพื่อปกป้องผู้โหวต)"),
                "empty": ("👥", "ยังไม่ถึงเกณฑ์", f"ต้องมีคนโหวตอย่างน้อย {board.min_reveal} คน ผลจึงจะแสดง "
                          "(ระบบไม่บอกจำนวนจริงเพื่อปกป้องผู้โหวต)"),
            }[cur.reason]
            ui.card(f'<div style="font-size:2rem">{msg[0]}</div><div style="font-weight:700;font-size:1.15rem">{msg[1]} · {ui.esc(cur.label)}</div>'
                    f'<div style="color:{viz.MUTED};margin-top:4px">{ui.esc(msg[2])}</div>', tone="lav")
            last = next((p for p in reversed(view.history) if p.revealed), None)
            if last:
                st.subheader(f"ผลรอบที่แล้ว · {last.label}")
                show_results(last, board)
            else:
                ui.graphic(viz.render_wheel(None, board.display_name, seed=board.id, show_counts=False))
                st.caption("วงล้อจะมีสติกเกอร์เมื่อเปิดผลได้ — ชวนเพื่อนด้วยลิงก์ในแท็บ “ลิงก์ & โค้ด”")

    with t_hist:
        revealed = [p for p in view.history + ([view.current] if view.current.revealed else []) if p.revealed]
        if not revealed:
            st.info("ยังไม่มีรอบที่เปิดผลได้")
        else:
            rows = []
            for p in revealed:
                gt = logic.group_totals(p.tallies)
                tot = sum(gt.values()) or 1
                for gc in ("pos", "neu", "neg"):
                    rows.append({"รอบ": p.label, "order": p.key, "กลุ่ม": GROUPS[gc].label, "สัดส่วน": gt[gc] / tot})
            df = pd.DataFrame(rows)
            order = [p.label for p in revealed]
            chart = alt.Chart(df).mark_bar(cornerRadiusTopLeft=6, cornerRadiusTopRight=6).encode(
                x=alt.X("รอบ:N", sort=order, title=None, axis=alt.Axis(labelAngle=0)),
                y=alt.Y("สัดส่วน:Q", stack="normalize", axis=alt.Axis(format="%"), title=None),
                color=alt.Color("กลุ่ม:N", scale=alt.Scale(domain=[GROUPS[g].label for g in ("pos", "neu", "neg")],
                                                          range=[GROUPS[g].color for g in ("pos", "neu", "neg")]),
                                legend=alt.Legend(orient="top", title=None)),
                order=alt.Order("กลุ่ม:N"),
                tooltip=["รอบ", "กลุ่ม", alt.Tooltip("สัดส่วน:Q", format=".0%")],
            ).properties(height=260).configure_view(strokeWidth=0).configure(font="IBM Plex Sans Thai")
            st.altair_chart(chart, width="stretch")
            pick = st.selectbox("ดูวงล้อของรอบ", [p.key for p in revealed][::-1],
                                format_func=lambda k: period_label(board.period_type, k), key="hist_pick")
            pv = next(p for p in revealed if p.key == pick)
            show_results(pv, board, seed_suffix="|h")
        hidden = [p for p in view.history if not p.revealed]
        if hidden:
            st.caption("รอบที่ไม่ถึงเกณฑ์ (จะไม่เปิดผลเพื่อปกป้องผู้โหวต): " + ", ".join(p.label for p in hidden))

    with t_links:
        if board.mode == "open":
            st.markdown("**ลิงก์โหวตสำหรับแชร์**")
            st.code(vote_link(board.id), language=None)
        else:
            n = s.count_codes(board.id)
            st.markdown(f"**โค้ดเชิญที่ใช้งานได้: {n} โค้ด** — ระบบเก็บโค้ดแบบ hash จึงแสดงซ้ำไม่ได้ "
                        "และ *ไม่มีทางรู้ว่าโค้ดไหนโหวตแล้ว* (ตั้งใจออกแบบให้เป็นแบบนี้)")
            new = st.session_state.get(f"new_codes:{board.id}")
            if new:
                ui.card("<b>โค้ดใหม่ — บันทึกเดี๋ยวนี้ (แสดงครั้งเดียว)</b>", tone="neu", pad="12px 18px")
                st.dataframe(pd.DataFrame({"โค้ด": new, "ลิงก์ส่วนตัว": [vote_link(board.id, c) for c in new]}),
                             hide_index=True, width="stretch",
                             column_config={"ลิงก์ส่วนตัว": st.column_config.LinkColumn()})
                st.download_button("⬇️ ดาวน์โหลดโค้ดใหม่ (.txt)", codes_text(board.display_name, board.id, new),
                                   file_name=f"invite-codes-{board.id}.txt", key="dl_new")
                if st.button("บันทึกแล้ว ซ่อนรายการ", key="hide_new"):
                    st.session_state.pop(f"new_codes:{board.id}", None)
                    st.rerun()
            c1, c2 = st.columns([2, 1])
            with c1:
                more = st.number_input("สร้างโค้ดเพิ่ม", 1, MAX_CODES_PER_BATCH, 5, key="more_n")
            with c2:
                st.write("")
                if st.button("➕ สร้าง", key="more_go"):
                    try:
                        st.session_state[f"new_codes:{board.id}"] = s.add_codes(board.id, int(more))
                        st.rerun()
                    except ValidationError as e:
                        st.error(str(e))
            with st.expander("ยกเลิกโค้ดทั้งหมด"):
                st.write("โค้ดเดิมทุกอันจะใช้ไม่ได้ทันที (ผลโหวตที่มีอยู่ยังอยู่ครบ) แล้วค่อยสร้างโค้ดใหม่ส่งไปแทน")
                if st.button("ยกเลิกโค้ดทั้งหมด", key="revoke_go"):
                    gone = s.revoke_all_codes(board.id)
                    st.session_state.pop(f"new_codes:{board.id}", None)
                    st.success(f"ยกเลิกแล้ว {gone} โค้ด")
        st.markdown("**ลิงก์เข้าหน้าผล** (ต้องใช้กุญแจเจ้าของ)")
        st.code(owner_link(board.id), language=None)

    with t_set:
        nm = st.text_input("ชื่อที่แสดง", board.display_name, max_chars=NAME_MAX, key="set_name")
        k = st.number_input("เกณฑ์ขั้นต่ำก่อนเปิดผล (คน)", MIN_REVEAL_FLOOR, MIN_REVEAL_CEIL, board.min_reveal, key="set_k")
        pol = st.radio("การเปิดผล", ["closed", "live"], index=["closed", "live"].index(board.reveal_policy),
                       format_func=lambda p: {"closed": "🛡️ เปิดผลเมื่อจบแต่ละรอบ", "live": "⚡ ดูรอบปัจจุบันได้เมื่อถึงเกณฑ์"}[p],
                       key="set_pol")
        st.caption(f"รอบการโหวต ({PERIOD_TYPES[board.period_type]}) และวิธีเชิญ เปลี่ยนไม่ได้หลังสร้างบอร์ด เพื่อให้กติกาคงที่")
        if st.button("บันทึกการตั้งค่า", type="primary", key="set_save"):
            try:
                s.update_settings(board.id, display_name=nm, min_reveal=int(k), reveal_policy=pol)
                st.success("บันทึกแล้ว")
                st.rerun()
            except ValidationError as e:
                st.error(str(e))
        st.divider()
        with st.expander("🗑️ ลบบอร์ดและข้อมูลทั้งหมดถาวร"):
            st.write("ลบผลโหวต โค้ด และบอร์ดนี้ทั้งหมด กู้คืนไม่ได้")
            confirm = st.text_input(f"พิมพ์รหัสบอร์ด {board.id} เพื่อยืนยัน", key="del_confirm")
            if st.button("ลบถาวร", key="del_go", disabled=security.normalize(confirm) != board.id):
                s.delete_board(board.id)
                st.session_state.pop(f"owner:{board.id}", None)
                go()


# ----------------------------------------------------------------------- router
def main() -> None:
    qp = st.query_params
    raw_b = qp.get("b")
    if not raw_b:
        page_home()
        return
    bid = security.normalize_board_id(raw_b)
    if qp.get("owner") or qp.get("k"):
        page_owner(bid, qp.get("k") or "")
    else:
        page_vote(bid, qp.get("c") or "")


main()
