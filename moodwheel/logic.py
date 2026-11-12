"""Privacy gate + summary statistics. The owner dashboard reads ONLY through owner_view()."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime

from .feelings import FEELING_BY_CODE, FEELINGS, GROUPS, INTENSITIES
from .periods import next_period_start, period_bounds, period_key, period_label, sort_keys
from .store import Board, Store

Tallies = dict[tuple[str, int], int]


@dataclass
class PeriodView:
    key: str
    label: str
    is_current: bool
    revealed: bool
    reason: str  # "ok" | "sealed" | "below_threshold" | "empty"
    voters: int | None = None  # only set when revealed
    tallies: Tallies = field(default_factory=dict)  # only filled when revealed


@dataclass
class OwnerView:
    board: Board
    current: PeriodView
    history: list[PeriodView]  # all non-current periods, oldest first
    opens_on: date  # first day of the next round


def _view(store: Store, board: Board, key: str, voters: int, is_current: bool) -> PeriodView:
    label = period_label(board.period_type, key)
    if is_current and board.reveal_policy == "closed":
        return PeriodView(key, label, True, False, "sealed")
    if voters <= 0:
        return PeriodView(key, label, is_current, False, "empty")
    if voters < board.min_reveal:
        return PeriodView(key, label, is_current, False, "below_threshold")
    return PeriodView(key, label, is_current, True, "ok", voters, store.tallies_for(board.id, key))


def owner_view(store: Store, board: Board, when: datetime | date | None = None) -> OwnerView:
    cur = period_key(board.period_type, when)
    counts = store.voters_by_period(board.id)
    current = _view(store, board, cur, counts.get(cur, 0), True)
    cur_start = period_bounds(board.period_type, cur)[0]
    # strictly earlier rounds only (drops "future" keys from clock skew)
    past = [k for k in sort_keys(board.period_type, counts) if period_bounds(board.period_type, k)[0] < cur_start]
    history = [_view(store, board, k, counts[k], False) for k in past]
    return OwnerView(board, current, history, next_period_start(board.period_type, when))


# ---------------------------------------------------------------- statistics
def feeling_totals(t: Tallies) -> dict[str, int]:
    out: dict[str, int] = {}
    for (f, _i), n in t.items():
        out[f] = out.get(f, 0) + n
    return out


def group_totals(t: Tallies) -> dict[str, int]:
    out = {g: 0 for g in GROUPS}
    for (f, _i), n in t.items():
        out[FEELING_BY_CODE[f].group] += n
    return out


def mood_index(t: Tallies) -> int | None:
    """-100 (all strongly negative) … +100 (all strongly positive)."""
    num = den = 0.0
    for (f, i), n in t.items():
        w = INTENSITIES[i]["weight"] * n
        num += GROUPS[FEELING_BY_CODE[f].group].sign * w
        den += w
    if den == 0:
        return None
    return int(round(100 * num / den))


def top_feelings(t: Tallies, k: int = 3) -> list[tuple[str, int]]:
    tot = feeling_totals(t)
    # ties: positive first, then neutral, then negative, then wheel order (kinder default)
    gorder = {"pos": 0, "neu": 1, "neg": 2}
    order = {f.code: (gorder[f.group], i) for i, f in enumerate(FEELINGS)}
    ranked = sorted(tot.items(), key=lambda kv: (-kv[1], order[kv[0]]))
    return [kv for kv in ranked if kv[1] > 0][:k]


def mood_word(idx: int | None) -> tuple[str, str]:
    if idx is None:
        return "—", "neu"
    if idx >= 50:
        return "อบอุ่นมาก", "pos"
    if idx >= 15:
        return "ค่อนข้างดี", "pos"
    if idx > -15:
        return "กลาง ๆ", "neu"
    if idx > -50:
        return "มีเรื่องค้างใจ", "neg"
    return "ต้องคุยกันหน่อยแล้ว", "neg"
