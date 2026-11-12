"""Persistence layer (SQLAlchemy Core — works on SQLite locally and PostgreSQL in the cloud).

PRIVACY BY DESIGN — what is (and is NOT) stored
------------------------------------------------
mw_boards       board settings + SHA-256 of the owner key
mw_codes        SHA-256 of each invite code (codes themselves are never stored)
mw_redemptions  (board, period, code-hash) → only "this code was used this round"
mw_tallies      (board, period, feeling, intensity) → a COUNTER, not a row per vote
mw_ballots      (board, period) → number of voters (a counter)

There is no table with one row per vote, no timestamp, no IP, no user agent, no name,
and no column that connects a code to a feeling. Votes are merged into counters the
moment they arrive, so "who chose what" cannot be reconstructed from the app's data.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum

from sqlalchemy import (
    Column, Integer, MetaData, SmallInteger, String, Table, create_engine, delete, event,
    func, insert, select, update,
)
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError

from . import security
from .feelings import FEELING_BY_CODE, INTENSITIES, MAX_FEELINGS_PER_VOTE
from .periods import PERIOD_TYPES, now_local, period_key

MIN_REVEAL_FLOOR = 3
MIN_REVEAL_CEIL = 20
MAX_CODES_PER_BATCH = 200
MAX_CODES_PER_BOARD = 1000
NAME_MAX = 40
MODES = ("invite", "open")
REVEAL_POLICIES = ("closed", "live")

metadata = MetaData()

boards = Table(
    "mw_boards", metadata,
    Column("id", String(16), primary_key=True),
    Column("display_name", String(80), nullable=False),
    Column("period_type", String(10), nullable=False),
    Column("mode", String(10), nullable=False),
    Column("min_reveal", Integer, nullable=False),
    Column("reveal_policy", String(10), nullable=False),
    Column("owner_key_hash", String(64), nullable=False),
    Column("created_on", String(10), nullable=False),  # date only (YYYY-MM-DD)
)
codes = Table(
    "mw_codes", metadata,
    Column("board_id", String(16), primary_key=True),
    Column("code_hash", String(64), primary_key=True),
)
redemptions = Table(
    "mw_redemptions", metadata,
    Column("board_id", String(16), primary_key=True),
    Column("period_key", String(12), primary_key=True),
    Column("code_hash", String(64), primary_key=True),
)
tallies = Table(
    "mw_tallies", metadata,
    Column("board_id", String(16), primary_key=True),
    Column("period_key", String(12), primary_key=True),
    Column("feeling", String(24), primary_key=True),
    Column("intensity", SmallInteger, primary_key=True),
    Column("n", Integer, nullable=False),
)
ballots = Table(
    "mw_ballots", metadata,
    Column("board_id", String(16), primary_key=True),
    Column("period_key", String(12), primary_key=True),
    Column("n", Integer, nullable=False),
)


class VoteResult(str, Enum):
    OK = "ok"
    ALREADY_VOTED = "already_voted"
    INVALID_CODE = "invalid_code"
    BOARD_NOT_FOUND = "board_not_found"
    INVALID_INPUT = "invalid_input"


@dataclass(frozen=True)
class Board:
    id: str
    display_name: str
    period_type: str
    mode: str
    min_reveal: int
    reveal_policy: str
    created_on: str


@dataclass(frozen=True)
class CreatedBoard:
    board: Board
    owner_key: str
    codes: list[str]


class ValidationError(ValueError):
    """Raised with a Thai, user-facing message."""


_WS = re.compile(r"\s+")


def clean_name(name: str | None) -> str:
    if name is None:
        return ""
    s = unicodedata.normalize("NFC", str(name))
    # drop control / format chars (incl. zero-width & bidi overrides), keep ZWJ for emoji
    s = "".join(ch for ch in s if ch == "‍" or unicodedata.category(ch) not in ("Cc", "Cf", "Cs", "Co"))
    s = _WS.sub(" ", s).strip()
    return s


def normalize_db_url(url: str) -> str:
    url = url.strip()
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        url = "postgresql+psycopg2://" + url[len("postgresql://"):]
    return url


def make_engine(url: str) -> Engine:
    url = normalize_db_url(url)
    if url.startswith("sqlite"):
        eng = create_engine(url, connect_args={"check_same_thread": False, "timeout": 30})

        @event.listens_for(eng, "connect")
        def _pragmas(dbapi_conn, _):  # pragma: no cover - trivial
            cur = dbapi_conn.cursor()
            if ":memory:" not in url:
                cur.execute("PRAGMA journal_mode=WAL")
            cur.execute("PRAGMA busy_timeout=30000")
            cur.close()

        return eng
    if url.startswith("postgresql"):
        return create_engine(url, pool_pre_ping=True, pool_recycle=280, pool_size=5, max_overflow=5)
    raise ValueError("รองรับเฉพาะ SQLite และ PostgreSQL")


def _upsert_increment(conn, table: Table, keys: dict, by: int = 1) -> None:
    dialect = conn.dialect.name
    if dialect == "postgresql":
        from sqlalchemy.dialects.postgresql import insert as d_insert
    elif dialect == "sqlite":
        from sqlalchemy.dialects.sqlite import insert as d_insert
    else:  # pragma: no cover
        raise RuntimeError(f"unsupported database: {dialect}")
    stmt = d_insert(table).values(**keys, n=by)
    stmt = stmt.on_conflict_do_update(index_elements=list(keys), set_={"n": table.c.n + by})
    conn.execute(stmt)


def _row_to_board(r) -> Board:
    return Board(r.id, r.display_name, r.period_type, r.mode, int(r.min_reveal), r.reveal_policy, r.created_on)


class Store:
    def __init__(self, engine: Engine | str):
        self.engine = make_engine(engine) if isinstance(engine, str) else engine
        metadata.create_all(self.engine)

    # ------------------------------------------------------------------ boards
    def create_board(
        self,
        display_name: str,
        period_type: str = "month",
        mode: str = "invite",
        min_reveal: int = MIN_REVEAL_FLOOR,
        reveal_policy: str = "closed",
        n_codes: int = 10,
        today: date | None = None,
    ) -> CreatedBoard:
        name = clean_name(display_name)
        if not name:
            raise ValidationError("กรุณาใส่ชื่อที่จะให้คนอื่นเห็น")
        if len(name) > NAME_MAX:
            raise ValidationError(f"ชื่อยาวได้ไม่เกิน {NAME_MAX} ตัวอักษร")
        if period_type not in PERIOD_TYPES:
            raise ValidationError("รอบการโหวตไม่ถูกต้อง")
        if mode not in MODES:
            raise ValidationError("รูปแบบการเชิญไม่ถูกต้อง")
        if reveal_policy not in REVEAL_POLICIES:
            raise ValidationError("รูปแบบการเปิดผลไม่ถูกต้อง")
        min_reveal = self._check_min_reveal(min_reveal)
        n_codes = int(n_codes) if mode == "invite" else 0
        if mode == "invite" and not 1 <= n_codes <= MAX_CODES_PER_BATCH:
            raise ValidationError(f"จำนวนโค้ดเชิญต้องอยู่ระหว่าง 1–{MAX_CODES_PER_BATCH}")

        owner_key = security.new_owner_key()
        created = (today or now_local().date()).isoformat()
        for _ in range(5):  # board-id collision is astronomically rare, but be safe
            bid = security.new_board_id()
            try:
                with self.engine.begin() as conn:
                    conn.execute(insert(boards).values(
                        id=bid, display_name=name, period_type=period_type, mode=mode,
                        min_reveal=min_reveal, reveal_policy=reveal_policy,
                        owner_key_hash=security.hash_owner_key(bid, owner_key), created_on=created,
                    ))
                    new_codes = self._insert_codes(conn, bid, n_codes)
                board = Board(bid, name, period_type, mode, min_reveal, reveal_policy, created)
                return CreatedBoard(board, owner_key, new_codes)
            except IntegrityError:
                continue
        raise RuntimeError("could not allocate a board id")  # pragma: no cover

    @staticmethod
    def _check_min_reveal(v) -> int:
        try:
            v = int(v)
        except (TypeError, ValueError):
            raise ValidationError("เกณฑ์ขั้นต่ำต้องเป็นตัวเลข") from None
        if not MIN_REVEAL_FLOOR <= v <= MIN_REVEAL_CEIL:
            raise ValidationError(f"เกณฑ์ขั้นต่ำต้องอยู่ระหว่าง {MIN_REVEAL_FLOOR}–{MIN_REVEAL_CEIL} คน")
        return v

    def get_board(self, board_id: str) -> Board | None:
        bid = security.normalize_board_id(board_id)
        if not bid:
            return None
        with self.engine.connect() as conn:
            r = conn.execute(select(boards).where(boards.c.id == bid)).first()
        return _row_to_board(r) if r else None

    def verify_owner(self, board_id: str, key: str) -> bool:
        bid = security.normalize_board_id(board_id)
        if not bid:
            return False
        with self.engine.connect() as conn:
            h = conn.execute(select(boards.c.owner_key_hash).where(boards.c.id == bid)).scalar()
        return security.check_owner_key(bid, key, h or "")

    def update_settings(self, board_id: str, *, display_name=None, min_reveal=None, reveal_policy=None) -> Board:
        vals = {}
        if display_name is not None:
            name = clean_name(display_name)
            if not name or len(name) > NAME_MAX:
                raise ValidationError(f"ชื่อต้องมี 1–{NAME_MAX} ตัวอักษร")
            vals["display_name"] = name
        if min_reveal is not None:
            vals["min_reveal"] = self._check_min_reveal(min_reveal)
        if reveal_policy is not None:
            if reveal_policy not in REVEAL_POLICIES:
                raise ValidationError("รูปแบบการเปิดผลไม่ถูกต้อง")
            vals["reveal_policy"] = reveal_policy
        if vals:
            with self.engine.begin() as conn:
                conn.execute(update(boards).where(boards.c.id == board_id).values(**vals))
        b = self.get_board(board_id)
        if b is None:
            raise ValidationError("ไม่พบบอร์ดนี้")
        return b

    def delete_board(self, board_id: str) -> None:
        with self.engine.begin() as conn:
            for t in (tallies, ballots, redemptions, codes, boards):
                col = t.c.id if t is boards else t.c.board_id
                conn.execute(delete(t).where(col == board_id))

    # ------------------------------------------------------------------- codes
    def _insert_codes(self, conn, board_id: str, n: int) -> list[str]:
        out: list[str] = []
        seen: set[str] = set()
        while len(out) < n:
            c = security.new_code()
            h = security.hash_code(board_id, c)
            if h in seen:
                continue
            seen.add(h)
            out.append(c)
        if out:
            conn.execute(insert(codes), [{"board_id": board_id, "code_hash": security.hash_code(board_id, c)} for c in out])
        return out

    def count_codes(self, board_id: str) -> int:
        with self.engine.connect() as conn:
            return int(conn.execute(select(func.count()).select_from(codes).where(codes.c.board_id == board_id)).scalar() or 0)

    def add_codes(self, board_id: str, n: int) -> list[str]:
        n = int(n)
        if not 1 <= n <= MAX_CODES_PER_BATCH:
            raise ValidationError(f"สร้างได้ครั้งละ 1–{MAX_CODES_PER_BATCH} โค้ด")
        if self.count_codes(board_id) + n > MAX_CODES_PER_BOARD:
            raise ValidationError(f"บอร์ดหนึ่งมีโค้ดได้ไม่เกิน {MAX_CODES_PER_BOARD} โค้ด — ลองยกเลิกโค้ดเก่าก่อน")
        with self.engine.begin() as conn:
            return self._insert_codes(conn, board_id, n)

    def revoke_all_codes(self, board_id: str) -> int:
        with self.engine.begin() as conn:
            res = conn.execute(delete(codes).where(codes.c.board_id == board_id))
            return int(res.rowcount or 0)

    def code_status(self, board_id: str, code: str, when: datetime | None = None) -> VoteResult:
        """Pre-check a code before showing the ballot (does not consume it)."""
        board = self.get_board(board_id)
        if board is None:
            return VoteResult.BOARD_NOT_FOUND
        if not security.looks_like_code(code):
            return VoteResult.INVALID_CODE
        h = security.hash_code(board.id, code)
        pk = period_key(board.period_type, when)
        with self.engine.connect() as conn:
            if conn.execute(select(codes.c.code_hash).where(codes.c.board_id == board.id, codes.c.code_hash == h)).first() is None:
                return VoteResult.INVALID_CODE
            used = conn.execute(select(redemptions.c.code_hash).where(
                redemptions.c.board_id == board.id, redemptions.c.period_key == pk, redemptions.c.code_hash == h)).first()
        return VoteResult.ALREADY_VOTED if used else VoteResult.OK

    # ------------------------------------------------------------------- votes
    def cast_vote(self, board_id: str, feelings, intensity, code: str | None = None,
                  when: datetime | None = None) -> VoteResult:
        try:
            chosen = list(dict.fromkeys(feelings or []))  # dedupe, keep order
            intensity = int(intensity)
        except (TypeError, ValueError):
            return VoteResult.INVALID_INPUT
        if not 1 <= len(chosen) <= MAX_FEELINGS_PER_VOTE:
            return VoteResult.INVALID_INPUT
        if any(c not in FEELING_BY_CODE for c in chosen) or intensity not in INTENSITIES:
            return VoteResult.INVALID_INPUT

        board = self.get_board(board_id)
        if board is None:
            return VoteResult.BOARD_NOT_FOUND
        pk = period_key(board.period_type, when)

        try:
            with self.engine.begin() as conn:
                if board.mode == "invite":
                    if not security.looks_like_code(code):
                        return VoteResult.INVALID_CODE
                    h = security.hash_code(board.id, code)
                    exists = conn.execute(select(codes.c.code_hash).where(
                        codes.c.board_id == board.id, codes.c.code_hash == h)).first()
                    if exists is None:
                        return VoteResult.INVALID_CODE
                    # The primary key makes this atomic: a second insert for the same
                    # (board, period, code) fails even under concurrent requests.
                    conn.execute(insert(redemptions).values(board_id=board.id, period_key=pk, code_hash=h))
                for f in chosen:
                    _upsert_increment(conn, tallies, {"board_id": board.id, "period_key": pk,
                                                      "feeling": f, "intensity": intensity})
                _upsert_increment(conn, ballots, {"board_id": board.id, "period_key": pk})
        except IntegrityError:
            return VoteResult.ALREADY_VOTED
        return VoteResult.OK

    # ------------------------------------------------------------- raw reads
    # NOTE: the UI must go through logic.owner_view(), which applies the privacy
    # threshold. These raw readers are for that function and for tests.
    def voters_by_period(self, board_id: str) -> dict[str, int]:
        with self.engine.connect() as conn:
            rows = conn.execute(select(ballots.c.period_key, ballots.c.n).where(ballots.c.board_id == board_id)).all()
        return {r.period_key: int(r.n) for r in rows}

    def tallies_for(self, board_id: str, pk: str) -> dict[tuple[str, int], int]:
        with self.engine.connect() as conn:
            rows = conn.execute(select(tallies.c.feeling, tallies.c.intensity, tallies.c.n).where(
                tallies.c.board_id == board_id, tallies.c.period_key == pk)).all()
        return {(r.feeling, int(r.intensity)): int(r.n) for r in rows
                if r.feeling in FEELING_BY_CODE and int(r.intensity) in INTENSITIES}
