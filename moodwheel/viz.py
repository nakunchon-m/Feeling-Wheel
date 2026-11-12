"""Hand-built SVG infographics: the mood wheel (sticker board), the mood gauge and bars.

Everything returns an HTML string for st.html(). All user-supplied text is escaped.
CSS classes and SVG ids are prefixed with a per-render uid so several graphics can live
on one page without clashing.
"""
from __future__ import annotations

import hashlib
import html
import math
import random
import unicodedata

from .feelings import FEELINGS, GROUPS, INTENSITIES

FONT = "'Prompt','IBM Plex Sans Thai',system-ui,sans-serif"
INK = "#24233A"
MUTED = "#7A7890"
LINE = "#E4DED4"

# wheel geometry (viewBox 0 0 700 700)
VB = 700
C = VB / 2
R_CENTER = 86
R_GROUP = 156
R_DOT_IN = 168
R_DOT_OUT = 262
R_OUT = 338
N = len(FEELINGS)
STEP = 2 * math.pi / N
MAX_DOTS_DRAWN = 42


def esc(s) -> str:
    return html.escape(str(s), quote=True)


def _uid(*parts) -> str:
    return "mw" + hashlib.sha1("|".join(map(str, parts)).encode()).hexdigest()[:8]


def _pt(r: float, a: float) -> tuple[float, float]:
    """Polar → cartesian, angle measured clockwise from 12 o'clock."""
    return C + r * math.sin(a), C - r * math.cos(a)


def _sector(r1: float, r2: float, a1: float, a2: float) -> str:
    large = 1 if (a2 - a1) > math.pi else 0
    x1, y1 = _pt(r2, a1)
    x2, y2 = _pt(r2, a2)
    x3, y3 = _pt(r1, a2)
    x4, y4 = _pt(r1, a1)
    return (f"M{x1:.2f},{y1:.2f} A{r2},{r2} 0 {large} 1 {x2:.2f},{y2:.2f} "
            f"L{x3:.2f},{y3:.2f} A{r1},{r1} 0 {large} 0 {x4:.2f},{y4:.2f} Z")


def _text_width(s: str, fs: float) -> float:
    base = sum(1 for ch in s if unicodedata.category(ch) not in ("Mn", "Me", "Cf"))
    return base * fs * 0.56


def _fit(s: str, max_w: float, fs: float, min_fs: float = 9) -> tuple[str, float]:
    while fs > min_fs and _text_width(s, fs) > max_w:
        fs -= 0.5
    if _text_width(s, fs) <= max_w:
        return s, fs
    out = s
    while out and _text_width(out + "…", fs) > max_w:
        out = out[:-1]
    return out + "…", fs


def _tangent_text(text: str, r: float, a: float, fs: float, weight: int, fill: str, cls: str = "") -> str:
    x, y = _pt(r, a)
    deg = math.degrees(a)
    if 90 < deg % 360 < 270:
        deg += 180
    return (f'<text x="{x:.1f}" y="{y:.1f}" font-size="{fs:.1f}" font-weight="{weight}" fill="{fill}" '
            f'text-anchor="middle" dominant-baseline="central" class="{cls}" '
            f'transform="rotate({deg:.2f} {x:.1f} {y:.1f})">{esc(text)}</text>')


def _face(cx: float, cy: float, r: float, group: str, uid: str) -> str:
    g = GROUPS[group]
    eye_y = cy - r * 0.18
    ex = r * 0.34
    if group == "pos":
        mouth = f"M{cx - r*0.4:.1f},{cy + r*0.18:.1f} Q{cx:.1f},{cy + r*0.62:.1f} {cx + r*0.4:.1f},{cy + r*0.18:.1f}"
    elif group == "neg":
        mouth = f"M{cx - r*0.38:.1f},{cy + r*0.46:.1f} Q{cx:.1f},{cy + r*0.08:.1f} {cx + r*0.38:.1f},{cy + r*0.46:.1f}"
    else:
        mouth = f"M{cx - r*0.34:.1f},{cy + r*0.32:.1f} L{cx + r*0.34:.1f},{cy + r*0.32:.1f}"
    brows = ""
    if group == "neg":
        brows = (f'<path d="M{cx-ex-r*0.18:.1f},{eye_y-r*0.30:.1f} L{cx-ex+r*0.16:.1f},{eye_y-r*0.16:.1f} '
                 f'M{cx+ex+r*0.18:.1f},{eye_y-r*0.30:.1f} L{cx+ex-r*0.16:.1f},{eye_y-r*0.16:.1f}" '
                 f'stroke="{g.dark}" stroke-width="{r*0.1:.1f}" stroke-linecap="round"/>')
    return (f'<g filter="url(#{uid}-shadow)">'
            f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r:.1f}" fill="url(#{uid}-g-{group})"/>'
            f'<ellipse cx="{cx - r*0.3:.1f}" cy="{cy - r*0.42:.1f}" rx="{r*0.36:.1f}" ry="{r*0.18:.1f}" fill="#fff" opacity=".35"/>'
            f'<circle cx="{cx-ex:.1f}" cy="{eye_y:.1f}" r="{r*0.1:.1f}" fill="{g.dark}"/>'
            f'<circle cx="{cx+ex:.1f}" cy="{eye_y:.1f}" r="{r*0.1:.1f}" fill="{g.dark}"/>'
            f'{brows}<path d="{mouth}" stroke="{g.dark}" stroke-width="{r*0.11:.1f}" fill="none" stroke-linecap="round"/>'
            f"</g>")


def _defs(uid: str) -> str:
    grads = "".join(
        f'<radialGradient id="{uid}-g-{g.code}" cx="50%" cy="50%" fx="34%" fy="28%" r="70%">'
        f'<stop offset="0%" stop-color="{g.light}"/><stop offset="55%" stop-color="{g.color}"/>'
        f'<stop offset="100%" stop-color="{g.dark}"/></radialGradient>'
        for g in GROUPS.values()
    )
    return (
        "<defs>" + grads +
        f'<radialGradient id="{uid}-paper" cx="50%" cy="40%" r="65%"><stop offset="0%" stop-color="#FFFFFF"/>'
        f'<stop offset="100%" stop-color="#F7F3EC"/></radialGradient>'
        f'<radialGradient id="{uid}-core" cx="50%" cy="35%" r="70%"><stop offset="0%" stop-color="#FFFFFF"/>'
        f'<stop offset="100%" stop-color="#EFE9DF"/></radialGradient>'
        f'<filter id="{uid}-shadow" x="-50%" y="-50%" width="200%" height="200%">'
        f'<feDropShadow dx="0" dy="1.6" stdDeviation="1.4" flood-color="#2A2440" flood-opacity=".28"/></filter>'
        f'<filter id="{uid}-lift" x="-20%" y="-20%" width="140%" height="140%">'
        f'<feDropShadow dx="0" dy="10" stdDeviation="12" flood-color="#2A2440" flood-opacity=".16"/></filter>'
        "</defs>"
    )


def _place_dots(sizes: list[float], a1: float, a2: float, rng: random.Random):
    placed: list[tuple[float, float, float]] = []
    for s in sizes:
        best, best_gap = None, -1e9
        for _ in range(260):
            pad_r = s + 3
            r = math.sqrt(rng.uniform((R_DOT_IN + pad_r) ** 2, (R_DOT_OUT - pad_r) ** 2))
            pad_a = (s + 3) / r
            if a2 - a1 <= 2 * pad_a:
                a = (a1 + a2) / 2
            else:
                a = rng.uniform(a1 + pad_a, a2 - pad_a)
            x, y = _pt(r, a)
            gap = min((math.hypot(x - px, y - py) - (s + ps) for px, py, ps in placed), default=99)
            if gap >= 1.5:
                best = (x, y, s)
                break
            if gap > best_gap:
                best, best_gap = (x, y, s), gap
        placed.append(best)
    return placed


def _css(uid: str) -> str:
    return f"""
<style>
.{uid}-stage{{perspective:1600px;display:flex;justify-content:center;padding:6px 0 2px}}
.{uid}-board{{width:100%;max-width:620px;transform:rotateX(9deg) rotateZ(-1.2deg);transform-style:preserve-3d;
  transition:transform .8s cubic-bezier(.2,.8,.2,1);animation:{uid}-in 1s cubic-bezier(.2,.8,.2,1) both}}
.{uid}-board:hover{{transform:rotateX(0deg) rotateZ(0deg)}}
.{uid}-board svg{{width:100%;height:auto;display:block;overflow:visible}}
.{uid}-w{{transition:filter .25s, opacity .25s}}
.{uid}-w:hover{{filter:brightness(.96) saturate(1.35)}}
.{uid}-dot{{transform-box:fill-box;transform-origin:center;animation:{uid}-pop .55s cubic-bezier(.2,1.7,.45,1) both;
  animation-delay:var(--d)}}
.{uid}-pulse{{transform-box:fill-box;transform-origin:center;animation:{uid}-pulse 1.6s ease-in-out infinite}}
.{uid}-spin{{transform-box:fill-box;transform-origin:center;animation:{uid}-spin 18s linear infinite}}
@keyframes {uid}-in{{from{{opacity:0;transform:rotateX(28deg) rotateZ(-10deg) scale(.92)}}}}
@keyframes {uid}-pop{{0%{{transform:scale(0);opacity:0}}100%{{transform:scale(1);opacity:1}}}}
@keyframes {uid}-pulse{{0%,100%{{transform:scale(1);opacity:.95}}50%{{transform:scale(1.18);opacity:.65}}}}
@keyframes {uid}-spin{{to{{transform:rotate(360deg)}}}}
@media (prefers-reduced-motion:reduce){{.{uid}-board,.{uid}-dot,.{uid}-pulse,.{uid}-spin{{animation:none!important;transform:none!important}}}}
</style>"""


def render_wheel(
    tallies: dict[tuple[str, int], int] | None,
    name: str,
    *,
    seed: str = "",
    selected: dict[str, int] | None = None,
    show_counts: bool = True,
) -> str:
    """Sticker-board wheel. ``tallies`` maps (feeling, intensity) → count.
    ``selected`` maps feeling → intensity for the live preview on the voting page."""
    tallies = tallies or {}
    selected = selected or {}
    uid = _uid("wheel", seed, sorted(tallies.items()), sorted(selected.items()), name)
    parts: list[str] = [_defs(uid)]

    # backboard
    parts.append(f'<circle cx="{C}" cy="{C}" r="{R_OUT + 6}" fill="url(#{uid}-paper)" filter="url(#{uid}-lift)"/>')

    # group spans
    spans: dict[str, tuple[float, float]] = {}
    for i, f in enumerate(FEELINGS):
        a1, a2 = i * STEP, (i + 1) * STEP
        s = spans.get(f.group)
        spans[f.group] = (a1, a2) if s is None else (s[0], a2)

    # outer wedges + labels + dots
    for i, f in enumerate(FEELINGS):
        g = GROUPS[f.group]
        a1, a2 = i * STEP, (i + 1) * STEP
        mid = (a1 + a2) / 2
        n_tot = sum(tallies.get((f.code, k), 0) for k in INTENSITIES)
        is_sel = f.code in selected
        fill = g.color if is_sel else g.tint
        op = ".30" if is_sel else ("1" if i % 2 else ".72")
        tip = f"{f.emoji} {f.label}"
        if show_counts and tallies:
            detail = " · ".join(f"{INTENSITIES[k]['label']} {tallies.get((f.code, k), 0)}"
                                for k in INTENSITIES if tallies.get((f.code, k), 0))
            tip += f" — {n_tot} ครั้ง" + (f" ({detail})" if detail else "")
        parts.append(
            f'<path class="{uid}-w" d="{_sector(R_GROUP, R_OUT, a1, a2)}" fill="{fill}" fill-opacity="{op}" '
            f'stroke="{LINE}" stroke-width="1.2"><title>{esc(tip)}</title></path>'
        )
        lbl, fs = _fit(f.wheel_label, (R_OUT - 48) * STEP * 0.94, 16.5, 11)
        parts.append(f'<text x="0" y="0" font-size="21" text-anchor="middle" dominant-baseline="central" '
                     f'transform="translate({_pt(R_OUT - 19, mid)[0]:.1f} {_pt(R_OUT - 19, mid)[1]:.1f})">{f.emoji}</text>')
        parts.append(_tangent_text(lbl, R_OUT - 48, mid, fs, 600 if is_sel else 500, INK if is_sel else "#4A4860"))
        if show_counts and n_tot:
            bx, by = _pt(R_DOT_IN + 2, mid)
            parts.append(f'<g><circle cx="{bx:.1f}" cy="{by:.1f}" r="11.5" fill="#fff" stroke="{g.color}" stroke-width="1.4"/>'
                         f'<text x="{bx:.1f}" y="{by:.1f}" font-size="11.5" font-weight="700" fill="{g.dark}" '
                         f'text-anchor="middle" dominant-baseline="central">{n_tot}</text></g>')

        # stickers
        sizes: list[float] = []
        for k in sorted(INTENSITIES, reverse=True):
            sizes += [INTENSITIES[k]["radius"]] * tallies.get((f.code, k), 0)
        extra = max(0, len(sizes) - MAX_DOTS_DRAWN)
        sizes = sizes[:MAX_DOTS_DRAWN]
        if sizes:
            area = 0.5 * STEP * (R_DOT_OUT**2 - R_DOT_IN**2) * 0.5
            need = sum(math.pi * (s + 1.5) ** 2 for s in sizes)
            scale = min(1.0, math.sqrt(area / need))
            sizes = [max(3.2, s * scale) for s in sizes]
            rng = random.Random(f"{seed}|{f.code}|{len(sizes)}")
            dots = _place_dots(sizes, a1, a2, rng)
            order = list(range(len(dots)))
            rng.shuffle(order)
            for j, (x, y, s) in zip(order, dots):
                parts.append(
                    f'<g class="{uid}-dot" style="--d:{0.25 + j * 0.035:.2f}s">'
                    f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{s:.1f}" fill="url(#{uid}-g-{f.group})" stroke="#fff" '
                    f'stroke-width="{1.2 if s < 8 else 1.6}" filter="url(#{uid}-shadow)"><title>{esc(tip)}</title></circle>'
                    f'<ellipse cx="{x - s*0.3:.1f}" cy="{y - s*0.38:.1f}" rx="{s*0.34:.1f}" ry="{s*0.18:.1f}" fill="#fff" opacity=".55"/>'
                    f"</g>"
                )
            if extra:
                ex, ey = _pt(R_DOT_OUT - 4, mid)
                parts.append(f'<text x="{ex:.1f}" y="{ey:.1f}" font-size="11" font-weight="700" fill="{g.dark}" '
                             f'text-anchor="middle" dominant-baseline="central">+{extra}</text>')
        if is_sel:
            s = INTENSITIES[selected[f.code]]["radius"] + 3
            px, py = _pt((R_DOT_IN + R_DOT_OUT) / 2, mid)
            parts.append(
                f'<g class="{uid}-pulse"><circle cx="{px:.1f}" cy="{py:.1f}" r="{s + 5:.1f}" fill="none" '
                f'stroke="{g.color}" stroke-width="2" stroke-dasharray="4 3"/>'
                f'<circle cx="{px:.1f}" cy="{py:.1f}" r="{s:.1f}" fill="url(#{uid}-g-{f.group})" stroke="#fff" '
                f'stroke-width="2" filter="url(#{uid}-shadow)"/>'
                f'<ellipse cx="{px - s*0.3:.1f}" cy="{py - s*0.38:.1f}" rx="{s*0.34:.1f}" ry="{s*0.18:.1f}" fill="#fff" opacity=".55"/></g>'
            )

    # inner group ring
    for code, (a1, a2) in spans.items():
        g = GROUPS[code]
        mid = (a1 + a2) / 2
        parts.append(f'<path d="{_sector(R_CENTER, R_GROUP, a1, a2)}" fill="#FFFFFF" stroke="{LINE}" stroke-width="1.4"/>')
        fx, fy = _pt((R_CENTER + R_GROUP) / 2 - 2, mid)
        fy -= 9
        parts.append(_face(fx, fy, 19, code, uid))
        parts.append(f'<text x="{fx:.1f}" y="{fy + 31:.1f}" font-size="16" font-weight="700" fill="{g.dark}" '
                     f'text-anchor="middle" dominant-baseline="central">{esc(g.label)}</text>')

    # centre
    nm, nfs = _fit(name, R_CENTER * 1.66, 27, 12)
    parts.append(f'<circle cx="{C}" cy="{C}" r="{R_CENTER}" fill="url(#{uid}-core)" stroke="{LINE}" stroke-width="1.4"/>')
    parts.append(f'<circle class="{uid}-spin" cx="{C}" cy="{C}" r="{R_CENTER - 8}" fill="none" stroke="#D8CFF5" '
                 f'stroke-width="1.5" stroke-dasharray="2 7" stroke-linecap="round"/>')
    parts.append(f'<text x="{C}" y="{C - 36}" font-size="17" text-anchor="middle" dominant-baseline="central">💜</text>')
    parts.append(f'<text x="{C}" y="{C - 13}" font-size="12.5" fill="{MUTED}" text-anchor="middle" '
                 f'dominant-baseline="central">ช่วงนี้คุณคิดอย่างไรกับ</text>')
    parts.append(f'<text x="{C}" y="{C + 20}" font-size="{nfs:.1f}" font-weight="700" fill="{INK}" '
                 f'text-anchor="middle" dominant-baseline="central">{esc(nm)}?</text>')

    svg = (f'<svg viewBox="-8 -8 {VB + 16} {VB + 16}" xmlns="http://www.w3.org/2000/svg" role="img" '
           f'aria-label="วงล้อความรู้สึกต่อ {esc(name)}" font-family="{esc(FONT)}">' + "".join(parts) + "</svg>")
    return _css(uid) + f'<div class="{uid}-stage"><div class="{uid}-board">{svg}</div></div>'


def render_gauge(index: int | None, word: str, group: str, key: str = "") -> str:
    uid = _uid("gauge", index, word, key)  # key keeps SVG ids unique when two gauges share a page
    cx, cy, r = 150, 138, 108
    segs = []
    n = 60
    for i in range(n):
        t1, t2 = i / n, (i + 1) / n
        a1, a2 = math.pi * (1 - t1), math.pi * (1 - t2)
        col = _lerp_color(t1)
        x1, y1 = cx + r * math.cos(a1), cy - r * math.sin(a1)
        x2, y2 = cx + r * math.cos(a2), cy - r * math.sin(a2)
        segs.append(f'<path d="M{x1:.2f},{y1:.2f} A{r},{r} 0 0 1 {x2:.2f},{y2:.2f}" stroke="{col}" '
                    f'stroke-width="22" fill="none"/>')
    v = 0 if index is None else max(-100, min(100, index))
    ang = math.pi * (1 - (v + 100) / 200)
    nx, ny = cx + (r - 28) * math.cos(ang), cy - (r - 28) * math.sin(ang)
    g = GROUPS[group]
    shown = "—" if index is None else f"{index:+d}"
    return f"""
<style>.{uid}-n{{transform-origin:{cx}px {cy}px;animation:{uid}-sw 1.3s cubic-bezier(.3,1.6,.5,1) both}}
@keyframes {uid}-sw{{from{{transform:rotate(-90deg)}}}}
@media (prefers-reduced-motion:reduce){{.{uid}-n{{animation:none}}}}</style>
<svg viewBox="0 0 300 190" xmlns="http://www.w3.org/2000/svg" style="width:100%;max-width:320px;display:block;margin:auto"
 font-family="{esc(FONT)}" role="img" aria-label="ดัชนีความรู้สึก {esc(shown)}">
<defs><filter id="{uid}-s"><feDropShadow dx="0" dy="3" stdDeviation="3" flood-opacity=".22"/></filter>
<radialGradient id="{uid}-k" fx="35%" fy="30%"><stop offset="0%" stop-color="#5A587A"/><stop offset="100%" stop-color="{INK}"/></radialGradient></defs>
<g filter="url(#{uid}-s)" stroke-linecap="butt">{''.join(segs)}</g>
<text x="{cx - r}" y="{cy + 22}" font-size="10" fill="{MUTED}" text-anchor="middle">-100</text>
<text x="{cx + r}" y="{cy + 22}" font-size="10" fill="{MUTED}" text-anchor="middle">+100</text>
<g class="{uid}-n"><line x1="{cx}" y1="{cy}" x2="{nx:.1f}" y2="{ny:.1f}" stroke="{INK}" stroke-width="5" stroke-linecap="round"/>
<circle cx="{cx}" cy="{cy}" r="13" fill="url(#{uid}-k)" filter="url(#{uid}-s)"/></g>
<text x="{cx}" y="{cy + 38}" font-size="26" font-weight="700" fill="{g.dark}" text-anchor="middle">{esc(shown)}</text>
</svg><div style="text-align:center;font-family:{esc(FONT)};font-weight:600;color:{g.dark};margin-top:-2px">{esc(word)}</div>"""


def _lerp_color(t: float) -> str:
    stops = [(0.0, (229, 72, 77)), (0.5, (245, 184, 61)), (1.0, (47, 163, 107))]
    for (t1, c1), (t2, c2) in zip(stops, stops[1:]):
        if t <= t2:
            u = (t - t1) / (t2 - t1)
            return "#%02X%02X%02X" % tuple(int(a + (b - a) * u) for a, b in zip(c1, c2))
    return "#2FA36B"


def render_group_bar(group_totals: dict[str, int]) -> str:
    total = sum(group_totals.values())
    if total <= 0:
        return ""
    segs, legend = [], []
    for code in ("pos", "neu", "neg"):
        g = GROUPS[code]
        n = group_totals.get(code, 0)
        pct = 100 * n / total
        if n:
            segs.append(f'<div title="{esc(g.label)} {pct:.0f}%" style="width:{pct:.3f}%;background:linear-gradient(180deg,{g.light},{g.color} 60%,{g.dark});'
                        f'height:100%"></div>')
        legend.append(f'<span style="display:inline-flex;align-items:center;gap:6px;margin-right:14px">'
                      f'<i style="width:10px;height:10px;border-radius:50%;background:{g.color};display:inline-block"></i>'
                      f'{esc(g.label)} <b>{pct:.0f}%</b></span>')
    return (f'<div style="font-family:{esc(FONT)};color:{INK}">'
            f'<div style="display:flex;height:16px;border-radius:999px;overflow:hidden;box-shadow:inset 0 1px 2px rgba(0,0,0,.15),0 4px 10px rgba(42,36,64,.10)">'
            + "".join(segs) + f'</div><div style="margin-top:8px;font-size:.9rem;color:{MUTED}">' + "".join(legend) + "</div></div>")
