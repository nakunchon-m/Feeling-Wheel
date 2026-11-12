"""End-to-end UI flows with Streamlit's AppTest (runs app.py headlessly)."""
from __future__ import annotations

import os
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from moodwheel.periods import period_key
from moodwheel.store import Store

APP = str(Path(__file__).resolve().parents[1] / "app.py")


@pytest.fixture
def db(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path / 'ui.db'}"
    monkeypatch.setenv("DATABASE_URL", url)
    monkeypatch.setenv("APP_URL", "https://example.streamlit.app")
    return Store(url)


def run(**qp) -> AppTest:
    at = AppTest.from_file(APP, default_timeout=30)
    for k, v in qp.items():
        at.query_params[k] = v
    at.run()
    assert not at.exception, [e.message for e in at.exception]
    return at


def texts(at) -> str:
    parts = []
    for coll in (at.markdown, at.caption, at.error, at.warning, at.info, at.success, at.subheader, at.code):
        parts += [getattr(e, "value", "") or "" for e in coll]
    parts += [h.proto.body for h in at.get("html")]
    return "\n".join(map(str, parts))


def click(at, key):
    at.button(key=key).click().run()
    assert not at.exception, [e.message for e in at.exception]
    return at


# ----------------------------------------------------------------------- home
def test_home_renders(db):
    at = run()
    t = texts(at)
    assert "ช่วงนี้คุณคิดอย่างไรกับฉัน?" in t
    assert "<svg" in t  # demo wheel
    assert len(at.tabs) == 3


def test_create_board_flow(db):
    at = run()
    at.text_input(key="c_name").input("น้อยหน่า").run()
    click(at, "c_submit")
    created = at.session_state["created"]
    assert created.board.display_name == "น้อยหน่า" and len(created.codes) == 10
    t = texts(at)
    assert created.owner_key in t
    assert f"https://example.streamlit.app/?b={created.board.id}&k=" in t
    assert at.button(key="cr_done").disabled
    at.checkbox(key="cr_ack").check().run()
    assert not at.button(key="cr_done").disabled
    click(at, "cr_done")
    assert at.query_params["b"] == [created.board.id] or at.query_params["b"] == created.board.id
    assert "created" not in at.session_state


def test_create_board_validation_message(db):
    at = run()
    click(at, "c_submit")  # empty name
    assert any("ชื่อ" in e.value for e in at.error)


def test_create_open_board(db):
    at = run()
    at.text_input(key="c_name").input("เปิด").run()
    at.radio(key="c_mode").set_value("open").run()
    click(at, "c_submit")
    cb = at.session_state["created"]
    assert cb.board.mode == "open" and cb.codes == []
    assert f"https://example.streamlit.app/?b={cb.board.id}" in texts(at)


def test_join_tab_parses_links(db):
    cb = db.create_board("ก", n_codes=2)
    at = run()
    at.text_input(key="join_link").input(f"https://x.streamlit.app/?b={cb.board.id.lower()}&c={cb.codes[0]}").run()
    click(at, "join_go")
    qp = at.query_params
    assert cb.board.id in str(qp["b"])
    at = run()
    at.text_input(key="join_link").input("not a link").run()
    click(at, "join_go")
    assert at.error


# ----------------------------------------------------------------------- vote
def _vote(at, picks=("fun",), group="pos", intensity=3):
    at.pills(key=f"pick_{group}").set_value(list(picks)).run()
    at.segmented_control(key="intensity").set_value(intensity).run()
    return click(at, "vote_submit")


def test_invite_vote_via_link_then_duplicate_blocked(db):
    cb = db.create_board("น้อยหน่า", n_codes=3)
    bid, code = cb.board.id, cb.codes[0]
    at = run(b=bid, c=code)
    assert "น้อยหน่า" in texts(at) and "ไม่ระบุตัวตน" in texts(at)
    _vote(at, ["fun", "admire"])
    assert "แปะสติกเกอร์ให้ น้อยหน่า แล้ว" in texts(at)
    pk = period_key("month")
    assert db.voters_by_period(bid) == {pk: 1}
    assert db.tallies_for(bid, pk) == {("fun", 3): 1, ("admire", 3): 1}
    # fresh browser session, same personal link → blocked
    at2 = run(b=bid, c=code)
    assert "โหวตในรอบนี้แล้ว" in texts(at2)
    assert not [b for b in at2.button if b.key == "vote_submit"]


def test_invite_code_typed_manually_lowercase(db):
    cb = db.create_board("ก", n_codes=1)
    at = run(b=cb.board.id)
    assert at.text_input(key="gate_code")
    at.text_input(key="gate_code").input(cb.codes[0].lower().replace("-", " ")).run()
    click(at, "gate_go")
    _vote(at, ["comfy"], intensity=1)
    assert db.voters_by_period(cb.board.id)


def test_invalid_code_and_lockout(db):
    cb = db.create_board("ก", n_codes=1)
    at = run(b=cb.board.id, c="22222-22222")
    assert any("ไม่ถูกต้อง" in e.value for e in at.error)
    for _ in range(10):
        at.text_input(key="gate_code").input("AAAAA-AAAAA").run()
        if not [b for b in at.button if b.key == "gate_go"]:
            break
        click(at, "gate_go")
    assert any("หลายครั้ง" in e.value for e in at.error)


def test_too_many_feelings_disables_submit(db):
    cb = db.create_board("ก", mode="open")
    at = run(b=cb.board.id)
    at.pills(key="pick_pos").set_value(["fun", "admire", "trust", "comfy"]).run()
    assert at.button(key="vote_submit").disabled
    assert any("สูงสุด 3" in w.value for w in at.warning)
    at.pills(key="pick_pos").set_value([]).run()
    assert at.button(key="vote_submit").disabled  # nothing chosen


def test_cross_group_selection_counts_toward_limit(db):
    cb = db.create_board("ก", mode="open")
    at = run(b=cb.board.id)
    at.pills(key="pick_pos").set_value(["fun", "admire"]).run()
    at.pills(key="pick_neg").set_value(["angry", "hurt"]).run()
    assert at.button(key="vote_submit").disabled


def test_open_board_one_vote_per_session(db):
    cb = db.create_board("ก", mode="open")
    at = run(b=cb.board.id)
    _vote(at, ["angry"], group="neg", intensity=3)
    assert "แปะสติกเกอร์" in texts(at)
    at.run()  # rerun same session: still thank-you, no ballot
    assert not [b for b in at.button if b.key == "vote_submit"]
    assert db.voters_by_period(cb.board.id) == {period_key("month"): 1}


def test_revoked_code_mid_ballot(db):
    cb = db.create_board("ก", n_codes=1)
    at = run(b=cb.board.id, c=cb.codes[0])
    db.revoke_all_codes(cb.board.id)
    _vote(at)
    assert any("ยกเลิก" in e.value for e in at.error)
    assert db.voters_by_period(cb.board.id) == {}


def test_unknown_and_malformed_board(db):
    for bid in ("ZZZZZZZZ", "../../x", "<b>", ""):
        at = run(b=bid) if bid else run()
        if bid:
            assert "ไม่พบบอร์ดนี้" in texts(at)


def test_xss_in_name_is_escaped_everywhere(db):
    cb = db.create_board('<img src=x onerror=alert(1)>', mode="open")
    at = run(b=cb.board.id)
    t = texts(at)
    assert "<img src=x" not in t and "&lt;img src=x" in t


# ---------------------------------------------------------------------- owner
def test_owner_link_logs_in_and_strips_key(db):
    cb = db.create_board("น้อยหน่า", n_codes=5)
    at = run(b=cb.board.id, k=cb.owner_key)
    assert at.session_state[f"owner:{cb.board.id}"] is True
    assert "k" not in at.query_params
    assert "ผลรอบนี้ถูกปิดผนึก" in texts(at)


def test_owner_wrong_key(db):
    cb = db.create_board("ก", n_codes=1)
    at = run(b=cb.board.id, k="AAAAA-AAAAA-AAAAA-AAAAA")
    assert any("ไม่ถูกต้อง" in e.value for e in at.error)
    assert "k" not in at.query_params
    assert at.text_input(key="ol_key")


def test_owner_login_form(db):
    cb = db.create_board("ก", n_codes=1)
    at = run(b=cb.board.id, owner="1")
    at.text_input(key="ol_key").input(cb.owner_key.lower()).run()
    click(at, "ol_go")
    assert at.session_state[f"owner:{cb.board.id}"] is True


def test_owner_sealed_does_not_leak_count(db):
    cb = db.create_board("ก", n_codes=5, reveal_policy="closed")
    for c in cb.codes:
        db.cast_vote(cb.board.id, ["fun"], 2, code=c)
    at = run(b=cb.board.id, k=cb.owner_key)
    t = texts(at)
    assert "ปิดผนึก" in t and "5 คน" not in t


def test_owner_live_results_and_below_threshold(db):
    cb = db.create_board("ก", n_codes=6, reveal_policy="live", min_reveal=4)
    for c in cb.codes[:3]:
        db.cast_vote(cb.board.id, ["fun"], 2, code=c)
    at = run(b=cb.board.id, k=cb.owner_key)
    t = texts(at)
    assert "ยังไม่ถึงเกณฑ์" in t and "3 คน" not in t
    db.cast_vote(cb.board.id, ["angry"], 3, code=cb.codes[3])
    at = run(b=cb.board.id, k=cb.owner_key)
    html_bodies = [h.proto.body for h in at.get("html")]
    assert any("4 คน" in b for b in html_bodies)
    assert "<svg" in texts(at)


def test_owner_generate_and_revoke_codes(db):
    cb = db.create_board("ก", n_codes=2)
    at = run(b=cb.board.id, k=cb.owner_key)
    at.number_input(key="more_n").set_value(3).run()
    click(at, "more_go")
    new = at.session_state[f"new_codes:{cb.board.id}"]
    assert len(new) == 3 and db.count_codes(cb.board.id) == 5
    click(at, "revoke_go")
    assert db.count_codes(cb.board.id) == 0


def test_owner_settings_and_delete(db):
    cb = db.create_board("ก", n_codes=2)
    at = run(b=cb.board.id, k=cb.owner_key)
    at.text_input(key="set_name").input("ใหม่").run()
    at.radio(key="set_pol").set_value("live").run()
    click(at, "set_save")
    assert db.get_board(cb.board.id).display_name == "ใหม่"
    assert db.get_board(cb.board.id).reveal_policy == "live"
    assert at.button(key="del_go").disabled
    at.text_input(key="del_confirm").input(cb.board.id.lower()).run()
    click(at, "del_go")
    assert db.get_board(cb.board.id) is None


def test_owner_of_one_board_cannot_open_another(db):
    a = db.create_board("ก", n_codes=1)
    b = db.create_board("ข", n_codes=1)
    at = run(b=a.board.id, k=a.owner_key)
    at.query_params.clear()
    at.query_params["b"] = b.board.id
    at.query_params["owner"] = "1"
    at.run()
    assert at.text_input(key="ol_key")  # still asks for b's key
    assert not at.session_state[f"owner:{b.board.id}"] if f"owner:{b.board.id}" in at.session_state else True


def test_ephemeral_db_warning_on_hosted_sqlite(db):
    at = run()  # APP_URL is a streamlit.app host and DATABASE_URL is sqlite in this fixture
    assert any("DATABASE_URL" in w.value for w in at.warning)


def test_no_warning_with_postgres_url(db, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@localhost:1/x")  # never connected: home doesn't hit DB
    at = AppTest.from_file(APP, default_timeout=30)
    at.run()
    assert not any("DATABASE_URL" in w.value for w in at.warning)
