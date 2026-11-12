"""Global styling and small HTML building blocks (all text escaped)."""
from __future__ import annotations

import html

import streamlit as st

from .feelings import GROUPS
from .viz import FONT, INK, MUTED

esc = lambda s: html.escape(str(s), quote=True)  # noqa: E731

GLOBAL_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans+Thai:wght@400;500;600;700&family=Prompt:wght@500;600;700&display=swap');
.stApp, .stApp input, .stApp textarea, .stApp button, .stApp label, .stApp p, .stApp li, .stApp td, .stApp th {
  font-family: 'IBM Plex Sans Thai', system-ui, sans-serif;
}
.stApp h1, .stApp h2, .stApp h3, .stApp h4 { font-family: 'Prompt', 'IBM Plex Sans Thai', sans-serif; letter-spacing: -.01em; }
.block-container { padding-top: 2.2rem; padding-bottom: 4rem; max-width: 760px; }
[data-testid="stDecoration"], footer { display: none !important; }
.stApp {
  background:
    radial-gradient(1100px 500px at 110% -10%, rgba(109,74,255,.10), transparent 60%),
    radial-gradient(900px 500px at -10% 10%, rgba(47,163,107,.09), transparent 60%),
    radial-gradient(900px 600px at 50% 120%, rgba(245,184,61,.10), transparent 60%);
}
.stButton > button, .stDownloadButton > button, .stFormSubmitButton > button {
  border-radius: 999px; font-weight: 600; padding: .55rem 1.25rem;
  box-shadow: 0 1px 0 rgba(255,255,255,.6) inset, 0 6px 16px -6px rgba(42,36,64,.35);
  transition: transform .15s ease, box-shadow .15s ease;
}
.stButton > button:hover, .stDownloadButton > button:hover { transform: translateY(-1px); }
.stButton > button:active { transform: translateY(1px); box-shadow: 0 2px 6px -2px rgba(42,36,64,.35); }
[data-testid="stTabs"] button p { font-weight: 600; }
[data-testid="stExpander"] details { border-radius: 16px; }
.stTextInput input, .stNumberInput input { border-radius: 12px; }
</style>
"""


def inject_css() -> None:
    st.html(GLOBAL_CSS)


def card(inner_html: str, *, tone: str = "paper", pad: str = "22px 24px") -> None:
    bg = {
        "paper": "linear-gradient(180deg,#FFFFFF,#FBF8F3)",
        "lav": "linear-gradient(135deg,#F3EEFF,#FFFFFF 70%)",
        "pos": "linear-gradient(135deg,#E8F6EE,#FFFFFF 75%)",
        "neu": "linear-gradient(135deg,#FEF6E4,#FFFFFF 75%)",
        "neg": "linear-gradient(135deg,#FDECEC,#FFFFFF 75%)",
        "ink": "linear-gradient(135deg,#2C2A45,#3F3A66)",
    }[tone]
    color = "#FFFFFF" if tone == "ink" else INK
    st.html(
        f'<div style="font-family:{esc(FONT)};background:{bg};color:{color};border-radius:24px;padding:{pad};'
        f'border:1px solid rgba(42,36,64,.07);box-shadow:0 1px 0 #fff inset,0 18px 40px -22px rgba(42,36,64,.35),'
        f'0 3px 8px -4px rgba(42,36,64,.12);margin:4px 0 12px">{inner_html}</div>'
    )


def hero(title: str, subtitle: str, eyebrow: str = "") -> None:
    eb = (f'<div style="display:inline-block;padding:5px 12px;border-radius:999px;background:#EFE9FF;color:#5B3FD6;'
          f'font-size:.8rem;font-weight:600;margin-bottom:10px">{esc(eyebrow)}</div>') if eyebrow else ""
    st.html(
        f'<div style="font-family:{esc(FONT)};text-align:center;margin:6px 0 4px">{eb}'
        f'<div style="font-size:clamp(1.7rem,5.4vw,2.6rem);font-weight:700;line-height:1.25;color:{INK};'
        f'text-shadow:0 2px 0 #fff,0 10px 24px rgba(91,63,214,.18)">{title}</div>'
        f'<div style="color:{MUTED};margin-top:8px;font-size:1.02rem">{subtitle}</div></div>'
    )


def avatar(name: str, size: int = 64) -> str:
    initial = esc((name.strip() or "?")[0])
    return (f'<div style="width:{size}px;height:{size}px;border-radius:50%;flex:none;display:flex;align-items:center;'
            f'justify-content:center;font-size:{size*0.42:.0f}px;font-weight:700;color:#fff;'
            f'background:radial-gradient(circle at 32% 28%,#A28BFF,#6D4AFF 55%,#4027B8);'
            f'box-shadow:0 10px 22px -8px rgba(91,63,214,.65),inset 0 2px 0 rgba(255,255,255,.35)">{initial}</div>')


def anon_badge(text: str = "ไม่ระบุตัวตน 100%") -> str:
    return (f'<span style="display:inline-flex;align-items:center;gap:6px;padding:5px 12px;border-radius:999px;'
            f'background:#E8F6EE;color:#1B7148;font-weight:600;font-size:.82rem;border:1px solid #CBEBD9">'
            f'🔒 {esc(text)}</span>')


def pill(text: str, bg: str = "#F1EDE6", fg: str = INK) -> str:
    return (f'<span style="display:inline-block;padding:4px 11px;border-radius:999px;background:{bg};color:{fg};'
            f'font-size:.82rem;font-weight:500;margin:2px 4px 2px 0">{esc(text)}</span>')


def kpi_row(items: list[tuple[str, str, str]]) -> None:
    """items: (label, value, sub)"""
    cells = "".join(
        f'<div style="flex:1 1 140px;background:linear-gradient(180deg,#fff,#FAF7F2);border-radius:20px;padding:16px 18px;'
        f'border:1px solid rgba(42,36,64,.06);box-shadow:0 12px 26px -18px rgba(42,36,64,.45)">'
        f'<div style="font-size:.8rem;color:{MUTED}">{esc(label)}</div>'
        f'<div style="font-size:1.55rem;font-weight:700;color:{INK};font-family:Prompt,sans-serif;line-height:1.3">{value}</div>'
        f'<div style="font-size:.8rem;color:{MUTED}">{esc(sub)}</div></div>'
        for label, value, sub in items
    )
    st.html(f'<div style="display:flex;gap:12px;flex-wrap:wrap;font-family:{esc(FONT)};margin:4px 0 10px">{cells}</div>')


def privacy_points() -> str:
    pts = [
        ("🙈", "ไม่ถามชื่อ ไม่ต้องล็อกอิน", "ไม่เก็บอีเมล IP เบราว์เซอร์ หรือเวลาที่โหวต"),
        ("🧮", "รวมเป็นตัวเลขทันที", "คำตอบถูกบวกเข้าตัวนับ ไม่มีแถวข้อมูลรายคนให้ย้อนดู"),
        ("🔑", "โค้ดเก็บแบบ hash", "แม้แต่ฐานข้อมูลก็อ่านโค้ดกลับไม่ได้ และไม่ผูกโค้ดกับคำตอบ"),
        ("👥", "เห็นผลเมื่อคนครบ", "เจ้าของบอร์ดเห็นเฉพาะผลรวม เมื่อมีคนโหวตถึงเกณฑ์ขั้นต่ำ"),
    ]
    cells = "".join(
        f'<div style="flex:1 1 160px;padding:14px;border-radius:18px;background:rgba(255,255,255,.75);'
        f'border:1px solid rgba(42,36,64,.06)"><div style="font-size:1.5rem">{i}</div>'
        f'<div style="font-weight:600;margin:4px 0 2px">{esc(t)}</div>'
        f'<div style="font-size:.84rem;color:{MUTED}">{esc(d)}</div></div>'
        for i, t, d in pts
    )
    return f'<div style="display:flex;gap:10px;flex-wrap:wrap">{cells}</div>'


def confetti_thanks(name: str, next_round: str) -> None:
    colors = [g.color for g in GROUPS.values()] + ["#6D4AFF"]
    bits = "".join(
        f'<i style="left:{(i * 37) % 100}%;background:{colors[i % 4]};width:{8 + (i * 7) % 9}px;height:{8 + (i * 7) % 9}px;'
        f'animation-delay:{(i * 0.13) % 1.6:.2f}s;animation-duration:{2.6 + (i % 5) * 0.35:.2f}s"></i>'
        for i in range(28)
    )
    st.html(f"""
<style>
.mwty{{position:relative;overflow:hidden;border-radius:28px;padding:38px 22px 30px;text-align:center;font-family:{esc(FONT)};
  background:linear-gradient(160deg,#F3EEFF,#FFFFFF 55%,#E8F6EE);border:1px solid rgba(42,36,64,.07);
  box-shadow:0 24px 50px -26px rgba(42,36,64,.45);color:{INK}}}
.mwty i{{position:absolute;top:-20px;border-radius:50%;opacity:.5;box-shadow:inset -2px -3px 0 rgba(0,0,0,.12),inset 2px 2px 0 rgba(255,255,255,.5);
  animation:mwfall linear infinite;z-index:0}}
.mwty > div{{position:relative;z-index:1}}
@keyframes mwfall{{0%{{transform:translateY(-20px) rotate(0)}}100%{{transform:translateY(420px) rotate(540deg)}}}}
.mwty .big{{font-size:4rem;display:inline-block;animation:mwbob 2.4s ease-in-out infinite}}
@keyframes mwbob{{0%,100%{{transform:translateY(0) rotate(-4deg)}}50%{{transform:translateY(-10px) rotate(4deg)}}}}
@media (prefers-reduced-motion:reduce){{.mwty i,.mwty .big{{animation:none}}}}
</style>
<div class="mwty">{bits}
 <div class="big">💜</div>
 <div style="font-family:Prompt,sans-serif;font-size:1.6rem;font-weight:700;margin-top:6px">แปะสติกเกอร์ให้ {esc(name)} แล้ว!</div>
 <div style="color:{MUTED};margin-top:8px">คำตอบของคุณถูกบวกรวมเป็นตัวเลขทันที — ไม่มีใครรู้ว่าเป็นของคุณ</div>
 <div style="margin-top:14px">{pill('โหวตครั้งถัดไปได้ตั้งแต่ ' + next_round, '#fff')}</div>
</div>""")


def graphic(markup: str, where=None) -> None:
    """Render SVG-bearing HTML. st.html() strips <svg> (HTML-only sanitizer profile), so we use
    st.markdown(unsafe_allow_html=True). Collapsing newlines keeps the whole thing one raw HTML
    block so the Markdown parser never touches it. All dynamic text is escaped upstream."""
    (where or st).markdown(markup.replace("\n", " "), unsafe_allow_html=True)
