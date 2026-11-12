"""Core logic tests: periods, security, storage, privacy guarantees, gating, concurrency, rendering."""
from __future__ import annotations

import re
import sqlite3
import threading
from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import inspect, select, func

from moodwheel import logic, security, viz
from moodwheel.feelings import FEELINGS, FEELING_BY_CODE, GROUPS, INTENSITIES
from moodwheel.periods import (
    TZ, next_period_start, period_bounds, period_key, period_label, sort_keys,
)
from moodwheel.store import (
    MAX_CODES_PER_BATCH, Store, ValidationError, VoteResult, ballots, clean_name, normalize_db_url, tallies,
)

NOV = datetime(2026, 11, 12, 10, 0, tzinfo=TZ)
DEC = datetime(2026, 12, 3, 10, 0, tzinfo=TZ)
JAN = datetime(2027, 1, 5, 10, 0, tzinfo=TZ)


import os

_BACKENDS = ["sqlite"] + (["postgres"] if os.environ.get("MW_TEST_PG") else [])


@pytest.fixture(params=_BACKENDS)
def s(request, tmp_path):
    if request.param == "sqlite":
        yield Store(f"sqlite:///{tmp_path / 't.db'}")
        return
    st_ = Store(os.environ["MW_TEST_PG"])  # e.g. postgresql://mw@/mwtest?host=/tmp&port=5433
    yield st_
    from moodwheel.store import metadata
    metadata.drop_all(st_.engine)
    st_.engine.dispose()


def new(s, **kw):
    kw.setdefault("display_name", "น้อยหน่า")
    return s.create_board(**kw)


# ------------------------------------------------------------------ catalogue
def test_feeling_catalogue_is_consistent():
    codes = [f.code for f in FEELINGS]
    assert len(codes) == len(set(codes))
    assert all(f.group in GROUPS for f in FEELINGS)
    assert all(len(f.code) <= 24 for f in FEELINGS)  # DB column width
    # each group is one contiguous run on the wheel
    groups = [f.group for f in FEELINGS]
    runs = [g for i, g in enumerate(groups) if i == 0 or g != groups[i - 1]]
    assert len(runs) == len(set(runs)) == 3


# -------------------------------------------------------------------- periods
def test_period_keys_basic():
    assert period_key("month", NOV) == "2026-11"
    assert period_key("quarter", NOV) == "2026-Q4"
    assert period_key("week", NOV) == "2026-W46"


def test_period_uses_bangkok_time():
    # 31 Oct 17:30 UTC == 1 Nov 00:30 in Bangkok → November
    assert period_key("month", datetime(2026, 10, 31, 17, 30, tzinfo=timezone.utc)) == "2026-11"
    assert period_key("month", datetime(2026, 10, 31, 16, 59, tzinfo=timezone.utc)) == "2026-10"
    # naive datetimes are treated as UTC
    assert period_key("month", datetime(2026, 10, 31, 17, 30)) == "2026-11"


def test_iso_week_year_boundary():
    assert period_key("week", date(2026, 12, 31)) == "2026-W53"
    assert period_key("week", date(2027, 1, 1)) == "2026-W53"
    assert period_key("week", date(2027, 1, 4)) == "2027-W01"


@pytest.mark.parametrize("ptype", ["week", "month", "quarter"])
def test_bounds_contain_every_day_for_three_years(ptype):
    d = date(2025, 1, 1)
    while d < date(2028, 1, 1):
        k = period_key(ptype, d)
        a, b = period_bounds(ptype, k)
        assert a <= d < b, (ptype, d, k)
        assert period_key(ptype, a) == k and period_key(ptype, b) != k
        assert period_key(ptype, b - timedelta(days=1)) == k
        d += timedelta(days=1)


def test_next_period_and_labels():
    assert next_period_start("month", NOV) == date(2026, 12, 1)
    assert next_period_start("month", datetime(2026, 12, 20, tzinfo=TZ)) == date(2027, 1, 1)
    assert next_period_start("quarter", NOV) == date(2027, 1, 1)
    assert period_label("month", "2026-11") == "พฤศจิกายน 2569"
    assert period_label("quarter", "2026-Q4") == "ไตรมาส 4/2569"
    assert "–" in period_label("week", "2026-W46")


@pytest.mark.parametrize("ptype,key", [("month", "2026-13"), ("month", "x"), ("week", "2026-11"), ("quarter", "2026-Q5")])
def test_bad_keys_rejected(ptype, key):
    with pytest.raises(ValueError):
        period_bounds(ptype, key)


def test_sort_keys_drops_garbage():
    assert sort_keys("month", ["2027-01", "bad", "2026-11", "2026-12"]) == ["2026-11", "2026-12", "2027-01"]


# ------------------------------------------------------------------- security
def test_token_formats_and_alphabet():
    for _ in range(200):
        assert re.fullmatch(r"[23456789A-HJKMNP-Z]{8}", security.new_board_id())
        assert re.fullmatch(r"[23456789A-HJKMNP-Z]{5}-[23456789A-HJKMNP-Z]{5}", security.new_code())
        assert re.fullmatch(r"([23456789A-HJKMNP-Z]{5}-){3}[23456789A-HJKMNP-Z]{5}", security.new_owner_key())


def test_normalize_and_hash():
    assert security.normalize(" abcde-fghjk ") == "ABCDEFGHJK"
    assert security.hash_code("B", "abcde-fghjk") == security.hash_code("B", "ABCDEFGHJK")
    assert security.hash_code("B1", "ABCDEFGHJK") != security.hash_code("B2", "ABCDEFGHJK")
    assert security.normalize_board_id("abcd2345") == "ABCD2345"
    assert security.normalize_board_id("ABCD") == ""
    assert security.normalize_board_id("ABCD234I") == ""  # 'I' not in alphabet
    assert security.normalize_board_id(None) == ""
    assert not security.looks_like_code("ABC")
    h = security.hash_owner_key("B", "K")
    assert security.check_owner_key("B", "k", h)
    assert not security.check_owner_key("B", "", h)
    assert not security.check_owner_key("B", "K", "")


def test_db_url_normalisation():
    assert normalize_db_url("postgres://u:p@h/db").startswith("postgresql+psycopg2://")
    assert normalize_db_url("postgresql://u:p@h/db?sslmode=require").startswith("postgresql+psycopg2://")
    assert normalize_db_url("sqlite:///x.db") == "sqlite:///x.db"


# ---------------------------------------------------------------- board CRUD
def test_create_board_defaults(s):
    cb = new(s)
    assert cb.board.mode == "invite" and cb.board.period_type == "month"
    assert cb.board.reveal_policy == "closed" and cb.board.min_reveal == 3
    assert len(cb.codes) == 10 and len(set(cb.codes)) == 10
    assert s.count_codes(cb.board.id) == 10
    assert s.get_board(cb.board.id) == cb.board
    assert s.get_board(cb.board.id.lower()) == cb.board
    assert s.verify_owner(cb.board.id, cb.owner_key)
    assert s.verify_owner(cb.board.id, cb.owner_key.lower().replace("-", ""))
    assert not s.verify_owner(cb.board.id, security.new_owner_key())
    assert not s.verify_owner("NOPE", cb.owner_key)


def test_open_board_has_no_codes(s):
    cb = new(s, mode="open", n_codes=50)
    assert cb.codes == [] and s.count_codes(cb.board.id) == 0


@pytest.mark.parametrize("kw,msg", [
    ({"display_name": "   "}, "ชื่อ"),
    ({"display_name": "ก" * 41}, "40"),
    ({"period_type": "day"}, "รอบ"),
    ({"mode": "x"}, "เชิญ"),
    ({"reveal_policy": "x"}, "เปิดผล"),
    ({"min_reveal": 2}, "3"),
    ({"min_reveal": 21}, "20"),
    ({"min_reveal": "abc"}, "ตัวเลข"),
    ({"n_codes": 0}, "โค้ด"),
    ({"n_codes": MAX_CODES_PER_BATCH + 1}, "โค้ด"),
])
def test_create_board_validation(s, kw, msg):
    with pytest.raises(ValidationError, match=msg):
        new(s, **kw)


def test_clean_name_strips_invisible_and_control_chars():
    assert clean_name("  น้อย​หน่า ‮\n\t ") == "น้อยหน่า"
    assert clean_name("👨‍👩‍👧 ครอบครัว") == "👨‍👩‍👧 ครอบครัว"  # ZWJ emoji kept
    assert clean_name(None) == ""


def test_update_settings(s):
    cb = new(s)
    b = s.update_settings(cb.board.id, display_name=" ใหม่ ", min_reveal=5, reveal_policy="live")
    assert (b.display_name, b.min_reveal, b.reveal_policy) == ("ใหม่", 5, "live")
    for kw in ({"display_name": ""}, {"min_reveal": 1}, {"reveal_policy": "no"}):
        with pytest.raises(ValidationError):
            s.update_settings(cb.board.id, **kw)
    with pytest.raises(ValidationError):
        s.update_settings("ZZZZZZZZ", min_reveal=4)


def test_codes_add_and_revoke(s):
    cb = new(s, n_codes=3)
    more = s.add_codes(cb.board.id, 4)
    assert len(more) == 4 and s.count_codes(cb.board.id) == 7
    with pytest.raises(ValidationError):
        s.add_codes(cb.board.id, 0)
    assert s.revoke_all_codes(cb.board.id) == 7
    assert s.count_codes(cb.board.id) == 0
    assert s.cast_vote(cb.board.id, ["fun"], 2, code=cb.codes[0], when=NOV) == VoteResult.INVALID_CODE


def test_code_cap_per_board(s):
    cb = new(s, n_codes=200)
    for _ in range(4):
        s.add_codes(cb.board.id, 200)
    with pytest.raises(ValidationError, match="1000"):
        s.add_codes(cb.board.id, 1)


def test_delete_board_removes_everything_and_only_that_board(s):
    a, b = new(s), new(s, display_name="อีกคน")
    s.cast_vote(a.board.id, ["fun"], 2, code=a.codes[0], when=NOV)
    s.cast_vote(b.board.id, ["fun"], 2, code=b.codes[0], when=NOV)
    s.delete_board(a.board.id)
    assert s.get_board(a.board.id) is None
    assert s.voters_by_period(a.board.id) == {} and s.tallies_for(a.board.id, "2026-11") == {}
    assert s.count_codes(a.board.id) == 0
    assert s.voters_by_period(b.board.id) == {"2026-11": 1}
    assert s.cast_vote(a.board.id, ["fun"], 2, code=a.codes[1], when=NOV) == VoteResult.BOARD_NOT_FOUND


# --------------------------------------------------------------------- voting
def test_invite_vote_once_per_period(s):
    cb = new(s)
    bid, c = cb.board.id, cb.codes[0]
    assert s.code_status(bid, c, NOV) == VoteResult.OK
    assert s.cast_vote(bid, ["admire", "fun"], 3, code=c, when=NOV) == VoteResult.OK
    assert s.code_status(bid, c, NOV) == VoteResult.ALREADY_VOTED
    assert s.cast_vote(bid, ["angry"], 1, code=c, when=NOV) == VoteResult.ALREADY_VOTED
    assert s.cast_vote(bid, ["angry"], 1, code=c.lower().replace("-", ""), when=NOV) == VoteResult.ALREADY_VOTED
    # the rejected duplicate must not have changed any counter
    assert s.tallies_for(bid, "2026-11") == {("admire", 3): 1, ("fun", 3): 1}
    assert s.voters_by_period(bid) == {"2026-11": 1}
    # next month the same code works again
    assert s.code_status(bid, c, DEC) == VoteResult.OK
    assert s.cast_vote(bid, ["angry"], 1, code=c, when=DEC) == VoteResult.OK
    assert s.voters_by_period(bid) == {"2026-11": 1, "2026-12": 1}


def test_codes_are_board_scoped(s):
    a, b = new(s), new(s)
    assert s.code_status(b.board.id, a.codes[0], NOV) == VoteResult.INVALID_CODE
    assert s.cast_vote(b.board.id, ["fun"], 1, code=a.codes[0], when=NOV) == VoteResult.INVALID_CODE


@pytest.mark.parametrize("feelings,intensity", [
    ([], 2), (None, 2), (["fun", "admire", "trust", "comfy"], 2), (["nope"], 2),
    (["fun"], 0), (["fun"], 4), (["fun"], "x"), (["fun"], None),
])
def test_invalid_ballots_rejected_without_consuming_code(s, feelings, intensity):
    cb = new(s)
    assert s.cast_vote(cb.board.id, feelings, intensity, code=cb.codes[0], when=NOV) == VoteResult.INVALID_INPUT
    assert s.code_status(cb.board.id, cb.codes[0], NOV) == VoteResult.OK
    assert s.voters_by_period(cb.board.id) == {}


def test_duplicate_feelings_are_deduped(s):
    cb = new(s)
    assert s.cast_vote(cb.board.id, ["fun", "fun", "fun"], 2, code=cb.codes[0], when=NOV) == VoteResult.OK
    assert s.tallies_for(cb.board.id, "2026-11") == {("fun", 2): 1}


@pytest.mark.parametrize("code", [None, "", "ABC", "22222-22222", "<script>"])
def test_bad_codes(s, code):
    cb = new(s)
    assert s.cast_vote(cb.board.id, ["fun"], 2, code=code, when=NOV) == VoteResult.INVALID_CODE


def test_open_board_accepts_without_code(s):
    cb = new(s, mode="open")
    for _ in range(3):
        assert s.cast_vote(cb.board.id, ["comfy"], 1, when=NOV) == VoteResult.OK
    assert s.voters_by_period(cb.board.id) == {"2026-11": 3}


def test_unknown_board(s):
    assert s.cast_vote("ZZZZZZZZ", ["fun"], 1, code="x", when=NOV) == VoteResult.BOARD_NOT_FOUND
    assert s.cast_vote("../../etc", ["fun"], 1) == VoteResult.BOARD_NOT_FOUND
    assert s.code_status("ZZZZZZZZ", "AAAAA-AAAAA") == VoteResult.BOARD_NOT_FOUND


def test_concurrent_double_submit_counts_once(s):
    cb = new(s)
    results = []
    barrier = threading.Barrier(16)

    def go():
        barrier.wait()
        results.append(s.cast_vote(cb.board.id, ["trust"], 2, code=cb.codes[0], when=NOV))

    ts = [threading.Thread(target=go) for _ in range(16)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert results.count(VoteResult.OK) == 1
    assert results.count(VoteResult.ALREADY_VOTED) == 15
    assert s.voters_by_period(cb.board.id) == {"2026-11": 1}
    assert s.tallies_for(cb.board.id, "2026-11") == {("trust", 2): 1}


def test_concurrent_distinct_voters_all_counted(s):
    cb = new(s, n_codes=40)
    barrier = threading.Barrier(40)
    out = []

    def go(c):
        barrier.wait()
        out.append(s.cast_vote(cb.board.id, ["fun", "admire"], 1, code=c, when=NOV))

    ts = [threading.Thread(target=go, args=(c,)) for c in cb.codes]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert out.count(VoteResult.OK) == 40
    assert s.voters_by_period(cb.board.id) == {"2026-11": 40}
    assert s.tallies_for(cb.board.id, "2026-11") == {("fun", 1): 40, ("admire", 1): 40}


# -------------------------------------------------------------------- privacy
def test_schema_has_no_identifying_or_linking_columns(s):
    insp = inspect(s.engine)
    forbidden = re.compile(r"time|stamp|date|ip|agent|email|user|session|name|created", re.I)
    for t in ("mw_codes", "mw_redemptions", "mw_tallies", "mw_ballots"):
        cols = [c["name"] for c in insp.get_columns(t)]
        assert not [c for c in cols if forbidden.search(c)], (t, cols)
    assert {c["name"] for c in insp.get_columns("mw_redemptions")} == {"board_id", "period_key", "code_hash"}
    assert "code_hash" not in {c["name"] for c in insp.get_columns("mw_tallies")}
    assert "feeling" not in {c["name"] for c in insp.get_columns("mw_redemptions")}


def test_votes_are_counters_not_rows(s):
    cb = new(s, n_codes=20)
    for c in cb.codes:
        s.cast_vote(cb.board.id, ["comfy"], 2, code=c, when=NOV)
    with s.engine.connect() as conn:
        assert conn.execute(select(func.count()).select_from(tallies)).scalar() == 1
        assert conn.execute(select(func.count()).select_from(ballots)).scalar() == 1


def test_secrets_never_stored_in_plaintext(tmp_path):
    path = tmp_path / "p.db"
    s = Store(f"sqlite:///{path}")
    cb = new(s)
    s.cast_vote(cb.board.id, ["fun"], 2, code=cb.codes[0], when=NOV)
    s.engine.dispose()
    con = sqlite3.connect(path)
    con.execute("PRAGMA wal_checkpoint(FULL)")
    dump = "\n".join(con.iterdump())
    con.close()
    raw = path.read_bytes().decode("latin-1")
    for secret in [cb.owner_key, *cb.codes]:
        for form in (secret, security.normalize(secret)):
            assert form not in dump and form not in raw


# ---------------------------------------------------------------- reveal gate
def _fill(s, cb, n, when, feeling="comfy", intensity=2):
    for c in cb.codes[:n]:
        assert s.cast_vote(cb.board.id, [feeling], intensity, code=c, when=when) == VoteResult.OK


def test_closed_policy_seals_current_round(s):
    cb = new(s, n_codes=10, reveal_policy="closed", min_reveal=3)
    _fill(s, cb, 8, NOV)
    v = logic.owner_view(s, cb.board, NOV)
    assert not v.current.revealed and v.current.reason == "sealed"
    assert v.current.voters is None and v.current.tallies == {}
    assert v.opens_on == date(2026, 12, 1)
    v2 = logic.owner_view(s, cb.board, DEC)  # next month: November opens
    assert [p.key for p in v2.history] == ["2026-11"]
    assert v2.history[0].revealed and v2.history[0].voters == 8
    assert v2.history[0].tallies == {("comfy", 2): 8}


def test_threshold_hides_small_rounds_even_after_they_close(s):
    cb = new(s, n_codes=10, reveal_policy="closed", min_reveal=4)
    _fill(s, cb, 3, NOV)
    h = logic.owner_view(s, cb.board, JAN).history[0]
    assert not h.revealed and h.reason == "below_threshold" and h.voters is None and h.tallies == {}


def test_live_policy(s):
    cb = new(s, n_codes=10, reveal_policy="live", min_reveal=3)
    assert logic.owner_view(s, cb.board, NOV).current.reason == "empty"
    _fill(s, cb, 2, NOV)
    cur = logic.owner_view(s, cb.board, NOV).current
    assert not cur.revealed and cur.voters is None and cur.tallies == {}
    s.cast_vote(cb.board.id, ["angry"], 3, code=cb.codes[2], when=NOV)
    cur = logic.owner_view(s, cb.board, NOV).current
    assert cur.revealed and cur.voters == 3


def test_future_rounds_from_clock_skew_are_ignored(s):
    cb = new(s, n_codes=10, reveal_policy="live")
    _fill(s, cb, 5, JAN)
    v = logic.owner_view(s, cb.board, NOV)
    assert v.history == [] and v.current.reason == "empty"


def test_stats():
    t = {("admire", 3): 2, ("angry", 1): 1, ("neutral", 2): 1}
    assert logic.group_totals(t) == {"neg": 1, "neu": 1, "pos": 2}
    idx = logic.mood_index(t)
    assert idx == round(100 * (6 - 1) / (6 + 1 + 2))
    assert logic.mood_index({}) is None
    assert logic.mood_index({("adore", 3): 5}) == 100
    assert logic.mood_index({("angry", 1): 5}) == -100
    assert logic.top_feelings(t) == [("admire", 2), ("neutral", 1), ("angry", 1)]
    for v in (None, -100, -40, 0, 30, 100):
        assert logic.mood_word(v)[1] in GROUPS


# ---------------------------------------------------------------------- viz
def test_wheel_escapes_user_text():
    out = viz.render_wheel({("fun", 1): 1}, '<script>alert(1)</script>"onload=x', seed="s")
    assert "<script" not in out and "&lt;script&gt;" in out
    assert '"onload' not in out


def test_wheel_handles_empty_and_huge_and_is_deterministic():
    assert "<svg" in viz.render_wheel(None, "x")
    big = {("fun", 3): 300, ("fun", 1): 200, ("angry", 2): 7}
    out = viz.render_wheel(big, "x", seed="b")
    assert f"+{500 - viz.MAX_DOTS_DRAWN}" in out
    assert out == viz.render_wheel(big, "x", seed="b")
    assert "\n\n" not in out.replace("\n", " ")  # single raw-HTML block for st.markdown


def test_wheel_selection_preview_and_long_names():
    out = viz.render_wheel(None, "ชื่อยาวมากมากมากมากมากมากมากมากมากมาก", selected={"angry": 3})
    assert "…" in out and "pulse" in out


def test_graphics_on_same_page_get_distinct_svg_ids():
    ids = lambda h: set(re.findall(r'id="([^"]+)"', h))
    assert not ids(viz.render_gauge(10, "a", "pos", key="x")) & ids(viz.render_gauge(10, "a", "pos", key="y"))
    t = {("fun", 1): 2}
    assert not ids(viz.render_wheel(t, "n", seed="b|k")) & ids(viz.render_wheel(t, "n", seed="b|k|h"))


def test_gauge_and_bar():
    assert "+40" in viz.render_gauge(40, "ok", "pos")
    assert "—" in viz.render_gauge(None, "—", "neu")
    assert viz.render_group_bar({"pos": 0, "neu": 0, "neg": 0}) == ""
    assert "50%" in viz.render_group_bar({"pos": 1, "neu": 0, "neg": 1})


def test_intensity_table():
    assert set(INTENSITIES) == {1, 2, 3}
    assert all(FEELING_BY_CODE[f.code] is f for f in FEELINGS)
