"""Feeling catalogue for the mood wheel.

Order matters: it defines the clockwise layout of the wheel, starting at 12 o'clock
(negative on the right, neutral at the bottom, positive on the left — like the KKP poster).
Codes are stable identifiers stored in the database; never rename an existing code.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Group:
    code: str
    label: str
    sign: int  # +1 / 0 / -1, used for the mood index
    color: str  # main sticker colour
    light: str  # highlight for the 3D gradient
    dark: str  # shade for the 3D gradient
    tint: str  # soft wedge background


@dataclass(frozen=True)
class Feeling:
    code: str
    label: str
    emoji: str
    group: str
    short: str | None = None  # shorter label for the wheel

    @property
    def wheel_label(self) -> str:
        return self.short or self.label


GROUPS: dict[str, Group] = {
    "neg": Group("neg", "ไม่ดี", -1, "#E5484D", "#FF8A8E", "#B42328", "#FDECEC"),
    "neu": Group("neu", "เฉย ๆ", 0, "#F5B83D", "#FFD98A", "#C98A0E", "#FEF6E4"),
    "pos": Group("pos", "ดีนะ", 1, "#2FA36B", "#6FD6A0", "#1B7148", "#E8F6EE"),
}

FEELINGS: list[Feeling] = [
    # --- ไม่ดี (negative) ---
    Feeling("annoyed", "หงุดหงิด", "😤", "neg"),
    Feeling("angry", "โกรธ", "😠", "neg"),
    Feeling("hurt", "น้อยใจ", "🥲", "neg"),
    Feeling("disappointed", "ผิดหวัง", "😞", "neg"),
    Feeling("uneasy", "อึดอัด", "😬", "neg"),
    Feeling("confused", "ไม่เข้าใจ", "😕", "neg"),
    Feeling("weary", "เหนื่อยใจ", "😮‍💨", "neg"),
    # --- เฉย ๆ (neutral) ---
    Feeling("worried", "เป็นห่วง", "🫶", "neu"),
    Feeling("considerate", "เกรงใจ", "🙇", "neu"),
    Feeling("distant", "ห่าง ๆ กันไป", "🌫️", "neu", "ห่าง ๆ"),
    Feeling("curious", "อยากรู้จักมากขึ้น", "🤔", "neu", "อยากรู้จัก"),
    Feeling("neutral", "เฉย ๆ", "😐", "neu"),
    # --- ดีนะ (positive) ---
    Feeling("fresh", "สดชื่น", "✨", "pos"),
    Feeling("fun", "สนุกด้วย", "😄", "pos"),
    Feeling("comfy", "สบายใจ", "😌", "pos"),
    Feeling("trust", "ไว้ใจ", "🤝", "pos"),
    Feeling("admire", "ชื่นชม", "👏", "pos"),
    Feeling("proud", "ภูมิใจในตัวเธอ", "🏅", "pos", "ภูมิใจ"),
    Feeling("grateful", "ขอบคุณ", "🙏", "pos"),
    Feeling("miss", "คิดถึง", "🌙", "pos"),
    Feeling("adore", "เอ็นดู", "💗", "pos"),
]

FEELING_BY_CODE: dict[str, Feeling] = {f.code: f for f in FEELINGS}

INTENSITIES: dict[int, dict] = {
    1: {"label": "นิดหน่อย", "short": "นิด", "weight": 1.0, "radius": 6.5},
    2: {"label": "ค่อนข้าง", "short": "กลาง", "weight": 2.0, "radius": 9.0},
    3: {"label": "มาก ๆ", "short": "มาก", "weight": 3.0, "radius": 12.0},
}

MAX_FEELINGS_PER_VOTE = 3


def feelings_in(group_code: str) -> list[Feeling]:
    return [f for f in FEELINGS if f.group == group_code]


def describe(code: str, intensity: int | None = None) -> str:
    f = FEELING_BY_CODE[code]
    base = f"{f.emoji} {f.label}"
    if intensity:
        return f"{base}{INTENSITIES[intensity]['label']}"
    return base
