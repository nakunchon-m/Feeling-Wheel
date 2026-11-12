"""Voting periods ("rounds"). Each voter may vote once per board per period.

All periods are computed in Asia/Bangkok time so that a "month" flips at local midnight.
"""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Asia/Bangkok")

PERIOD_TYPES: dict[str, str] = {
    "week": "ทุกสัปดาห์",
    "month": "ทุกเดือน",
    "quarter": "ทุก 3 เดือน",
}
DEFAULT_PERIOD = "month"

TH_MONTHS = [
    "มกราคม", "กุมภาพันธ์", "มีนาคม", "เมษายน", "พฤษภาคม", "มิถุนายน",
    "กรกฎาคม", "สิงหาคม", "กันยายน", "ตุลาคม", "พฤศจิกายน", "ธันวาคม",
]
TH_MONTHS_SHORT = [
    "ม.ค.", "ก.พ.", "มี.ค.", "เม.ย.", "พ.ค.", "มิ.ย.",
    "ก.ค.", "ส.ค.", "ก.ย.", "ต.ค.", "พ.ย.", "ธ.ค.",
]

_RE_WEEK = re.compile(r"^(\d{4})-W(\d{2})$")
_RE_MONTH = re.compile(r"^(\d{4})-(\d{2})$")
_RE_QUARTER = re.compile(r"^(\d{4})-Q([1-4])$")


def now_local() -> datetime:
    return datetime.now(TZ)


def _local_date(dt: datetime | date | None) -> date:
    if dt is None:
        return now_local().date()
    if isinstance(dt, datetime):
        if dt.tzinfo is None:  # treat naive datetimes as UTC (server clocks)
            dt = dt.replace(tzinfo=ZoneInfo("UTC"))
        return dt.astimezone(TZ).date()
    return dt


def period_key(period_type: str, when: datetime | date | None = None) -> str:
    d = _local_date(when)
    if period_type == "week":
        y, w, _ = d.isocalendar()
        return f"{y}-W{w:02d}"
    if period_type == "month":
        return f"{d.year}-{d.month:02d}"
    if period_type == "quarter":
        return f"{d.year}-Q{(d.month - 1) // 3 + 1}"
    raise ValueError(f"unknown period type: {period_type!r}")


def period_bounds(period_type: str, key: str) -> tuple[date, date]:
    """Return (first_day, first_day_of_next_period) for a period key."""
    if period_type == "week":
        m = _RE_WEEK.match(key)
        if not m:
            raise ValueError(key)
        start = date.fromisocalendar(int(m[1]), int(m[2]), 1)
        return start, start + timedelta(days=7)
    if period_type == "month":
        m = _RE_MONTH.match(key)
        if not m or not 1 <= int(m[2]) <= 12:
            raise ValueError(key)
        y, mo = int(m[1]), int(m[2])
        start = date(y, mo, 1)
        end = date(y + 1, 1, 1) if mo == 12 else date(y, mo + 1, 1)
        return start, end
    if period_type == "quarter":
        m = _RE_QUARTER.match(key)
        if not m:
            raise ValueError(key)
        y, q = int(m[1]), int(m[2])
        start = date(y, 3 * (q - 1) + 1, 1)
        end = date(y + 1, 1, 1) if q == 4 else date(y, 3 * q + 1, 1)
        return start, end
    raise ValueError(f"unknown period type: {period_type!r}")


def next_period_start(period_type: str, when: datetime | date | None = None) -> date:
    return period_bounds(period_type, period_key(period_type, when))[1]


def th_date(d: date, short: bool = False) -> str:
    months = TH_MONTHS_SHORT if short else TH_MONTHS
    return f"{d.day} {months[d.month - 1]} {d.year + 543}"


def period_label(period_type: str, key: str) -> str:
    start, end = period_bounds(period_type, key)
    if period_type == "month":
        return f"{TH_MONTHS[start.month - 1]} {start.year + 543}"
    if period_type == "quarter":
        q = (start.month - 1) // 3 + 1
        return f"ไตรมาส {q}/{start.year + 543}"
    last = end - timedelta(days=1)
    return f"{th_date(start, short=True)} – {th_date(last, short=True)}"


def sort_keys(period_type: str, keys) -> list[str]:
    """Chronological sort that tolerates foreign/invalid keys (they are dropped)."""
    good = []
    for k in keys:
        try:
            good.append((period_bounds(period_type, k)[0], k))
        except ValueError:
            continue
    return [k for _, k in sorted(good)]
