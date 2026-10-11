"""WEB X-RAY identity generator — the Browse mark and the drawn wordmark.

All marks are constructed geometrically (no fonts), so one source produces the
production SVGs, the favicon/app icons, the wordmark module used by the web app,
and the brand board.

    python brand/generate.py            # brand/out/*.svg, web assets, brand/board.html
    python brand/generate.py --render   # also renders brand/board.png + apple-icon.png (Playwright)
"""

from __future__ import annotations

import argparse
import math
from dataclasses import dataclass, field
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "out"

# --------------------------------------------------------------------------- primitives


def fmt(v: float) -> str:
    return f"{v:.2f}".rstrip("0").rstrip(".")


@dataclass
class Shape:
    """A list of filled primitives in one coordinate space."""

    items: list[str] = field(default_factory=list)

    def poly(self, pts: list[tuple[float, float]]) -> None:
        self.items.append('<path d="M' + " L".join(f"{fmt(x)} {fmt(y)}" for x, y in pts) + 'Z"/>')

    def rect(self, x: float, y: float, w: float, h: float, r: float = 0) -> None:
        extra = f' rx="{fmt(r)}"' if r else ""
        self.items.append(f'<rect x="{fmt(x)}" y="{fmt(y)}" width="{fmt(w)}" height="{fmt(h)}"{extra}/>')

    def stroke(self, d: str, width: float) -> None:
        self.items.append(f'<path d="{d}" fill="none" stroke="currentColor" stroke-width="{fmt(width)}" stroke-linecap="butt" stroke-linejoin="miter"/>')

    def circle(self, cx: float, cy: float, r: float, width: float | None = None) -> None:
        if width:
            self.items.append(f'<circle cx="{fmt(cx)}" cy="{fmt(cy)}" r="{fmt(r)}" fill="none" stroke="currentColor" stroke-width="{fmt(width)}"/>')
        else:
            self.items.append(f'<circle cx="{fmt(cx)}" cy="{fmt(cy)}" r="{fmt(r)}"/>')

    def svg(self, tx: float = 0, ty: float = 0, scale: float = 1) -> str:
        return f'<g transform="translate({fmt(tx)} {fmt(ty)}) scale({fmt(scale)})">' + "".join(self.items) + "</g>"


def diagonal(s: Shape, x0: float, y0: float, x1: float, y1: float, t: float, ya: float | None = None, yb: float | None = None, dx: float = 0) -> None:
    """Diagonal stroke of perpendicular weight ``t`` with *horizontal* terminals.

    (x0,y0)-(x1,y1) is the centreline; optionally only the slice ya..yb is drawn,
    shifted horizontally by ``dx``.
    """
    ya = y0 if ya is None else ya
    yb = y1 if yb is None else yb
    length = math.hypot(x1 - x0, y1 - y0)
    half = t * length / abs(y1 - y0) / 2  # half horizontal thickness

    def cx(y: float) -> float:
        return x0 + (x1 - x0) * (y - y0) / (y1 - y0)

    s.poly([(cx(ya) - half + dx, ya), (cx(ya) + half + dx, ya), (cx(yb) + half + dx, yb), (cx(yb) - half + dx, yb)])


def half_width(t: float, dx: float, dy: float) -> float:
    return t * math.hypot(dx, dy) / abs(dy) / 2


# --------------------------------------------------------------------------- wordmark

CAP = 20.0  # cap height
T = 3.5  # stroke weight (17.5% of cap height)
TRACK = 2.9  # letter spacing
WORD = 7.5  # word space
SLIT = 2.9  # scan-slit height in the wordmark X (same proportion family as the symbol)
SHIFT = 2.0  # horizontal offset of the X's lower half


def glyph_W(s: Shape) -> float:
    w = 24.5
    h = half_width(T, 4.6, CAP)
    a_top, v1, peak, v2, d_top = h, 6.4, w / 2, w - 6.4, w - h
    diagonal(s, a_top, 0, v1, CAP, T)
    diagonal(s, v1, CAP, peak, 6.0, T)
    diagonal(s, peak, 6.0, v2, CAP, T)
    diagonal(s, v2, CAP, d_top, 0, T)
    return w


def glyph_E(s: Shape) -> float:
    s.rect(0, 0, T, CAP)
    s.rect(0, 0, 12.4, T)
    s.rect(0, (CAP - T) / 2, 10.8, T)
    s.rect(0, CAP - T, 12.4, T)
    return 12.4


def glyph_B(s: Shape) -> float:
    s.rect(0, 0, T, CAP)
    top, mid, bot = T / 2, 9.6, CAP - T / 2
    r1, r2 = (mid - top) / 2, (bot - mid) / 2
    x1, x2 = 7.4, 8.2
    s.stroke(f"M0 {fmt(top)} H{fmt(x1)} A{fmt(r1)} {fmt(r1)} 0 0 1 {fmt(x1)} {fmt(mid)} H0 "
             f"M0 {fmt(mid)} H{fmt(x2)} A{fmt(r2)} {fmt(r2)} 0 0 1 {fmt(x2)} {fmt(bot)} H0", T)
    return x2 + r2 + T / 2


def glyph_X(s: Shape, slit: bool = True) -> float:
    w = 17.0
    h = half_width(T, w, CAP)
    ga, gb = CAP / 2 - SLIT / 2, CAP / 2 + SLIT / 2
    for x0, x1 in ((h, w - h), (w - h, h)):
        if slit:
            diagonal(s, x0, 0, x1, CAP, T, 0, ga, -SHIFT / 2)
            diagonal(s, x0, 0, x1, CAP, T, gb, CAP, SHIFT / 2)
        else:
            diagonal(s, x0, 0, x1, CAP, T)
    return w + (SHIFT / 2 if slit else 0)


def glyph_hyphen(s: Shape) -> float:
    s.rect(0, CAP / 2 + 0.6 - T * 0.9 / 2, 6.6, T * 0.9)
    return 6.6


def glyph_R(s: Shape) -> float:
    s.rect(0, 0, T, CAP)
    top, mid = T / 2, 11.0
    r = (mid - top) / 2
    x1 = 7.6
    s.stroke(f"M0 {fmt(top)} H{fmt(x1)} A{fmt(r)} {fmt(r)} 0 0 1 {fmt(x1)} {fmt(mid)} H0", T)
    w = 14.6
    h = half_width(T, 6.0, CAP - mid)
    diagonal(s, x1 - 1.2, mid - T / 2, w - h, CAP, T)
    return w


def glyph_A(s: Shape) -> float:
    w = 17.6
    h = half_width(T, w / 2, CAP)
    c, k = w / 2, h * 0.32
    diagonal(s, c - k, 0, h, CAP, T)
    diagonal(s, c + k, 0, w - h, CAP, T)
    s.rect(3.2, 13.0, w - 6.4, T * 0.9)
    return w


def glyph_Y(s: Shape) -> float:
    w = 17.4
    c, jy = w / 2, 10.6
    h = half_width(T, c, jy)
    diagonal(s, h, 0, c, jy, T)
    diagonal(s, w - h, 0, c, jy, T)
    s.rect(c - T / 2, jy - 0.4, T, CAP - jy + 0.4)
    return w


def wordmark(slit: bool = True) -> tuple[Shape, float]:
    s = Shape()
    x = 0.0
    seq: list[object] = [glyph_W, glyph_E, glyph_B, WORD, "X", glyph_hyphen, glyph_R, glyph_A, glyph_Y]
    for i, g in enumerate(seq):
        if isinstance(g, float):
            x += g - TRACK
            continue
        sub = Shape()
        width = glyph_X(sub, slit) if g == "X" else g(sub)  # type: ignore[operator]
        s.items.append(sub.svg(x, 0))
        x += width + (TRACK if i < len(seq) - 1 else 0)
    return s, x


# --------------------------------------------------------------------------- colour


def oklch_to_hex(l: float, c: float, h: float) -> str:
    """OKLCH -> sRGB hex (for rasters/favicons where CSS colour functions are unavailable)."""
    a, b = c * math.cos(math.radians(h)), c * math.sin(math.radians(h))
    l_ = l + 0.3963377774 * a + 0.2158037573 * b
    m_ = l - 0.1055613458 * a - 0.0638541728 * b
    s_ = l - 0.0894841775 * a - 1.2914855480 * b
    lc, mc, sc = l_ ** 3, m_ ** 3, s_ ** 3
    rgb = (
        4.0767416621 * lc - 3.3077115913 * mc + 0.2309699292 * sc,
        -1.2684380046 * lc + 2.6097574011 * mc - 0.3413193965 * sc,
        -0.0041960863 * lc - 0.7034186147 * mc + 1.7076147010 * sc,
    )

    def enc(x: float) -> int:
        x = min(1.0, max(0.0, x))
        x = 12.92 * x if x <= 0.0031308 else 1.055 * x ** (1 / 2.4) - 0.055
        return round(x * 255)

    return "#" + "".join(f"{enc(v):02x}" for v in rgb)


# Brand + palette (mirrors web/src/styles/theme.css)
PALETTE = {
    "Brand · dark UI": (0.76, 0.115, 205),
    "Brand · light UI": (0.52, 0.105, 212),
    "Ink": (0.22, 0.012, 250),
    "Night": (0.155, 0.006, 250),
    "Success": (0.76, 0.14, 155),
    "Warning": (0.83, 0.135, 80),
    "Danger": (0.7, 0.17, 25),
}
BRAND_HEX = oklch_to_hex(0.52, 0.105, 212)
BRAND_FG_HEX = "#ffffff"


# --------------------------------------------------------------------------- the Browse mark (24-unit grid)
#
# A globe (the web) crossed by an address bar, with a cursor resting on the
# bar: WEB X-RAY browsing the internet on your behalf. Single ink by default;
# the cursor can carry the brand colour in two-tone use. Animated while an
# investigation runs: the globe turns, a scan sweeps the address bar, and the
# cursor glides and clicks. Static otherwise.

STROKE = 1.9
GLOBE = (12.0, 12.0, 9.1)  # cx, cy, r
MERIDIAN_RX = 3.9
BAR = (1.3, 9.15, 21.4, 5.7, 2.85)  # x, y, w, h, radius
CURSOR_POINTS = [(0, 0), (0, 11), (2.7, 8.5), (4.6, 12.6), (6.6, 11.7), (4.8, 7.7), (8.4, 7.5)]
CURSOR_ORIGIN = (13.4, 11.3)
CURSOR_SCALE = 0.72
CURSOR_GAP = 2.6  # knockout around the cursor, in units


def cursor_path() -> str:
    ox, oy = CURSOR_ORIGIN
    return "M" + " L".join(f"{fmt(ox + x * CURSOR_SCALE)} {fmt(oy + y * CURSOR_SCALE)}" for x, y in CURSOR_POINTS) + "Z"


def bar_rect(extra: str = "") -> str:
    x, y, w, h, r = BAR
    return f'<rect x="{fmt(x)}" y="{fmt(y)}" width="{fmt(w)}" height="{fmt(h)}" rx="{fmt(r)}"{extra}/>'


def lens_mark(pfx: str = "m", cursor_fill: str = "currentColor") -> str:
    """Single-ink mark with knockouts (bar hides globe lines; a gap separates the cursor)."""
    cx, cy, r = GLOBE
    cur = cursor_path()
    gap = f'<path d="{cur}" fill="#000" stroke="#000" stroke-width="{fmt(CURSOR_GAP)}" stroke-linejoin="round"/>'
    defs = (
        f'<defs><mask id="{pfx}g" maskUnits="userSpaceOnUse" x="0" y="0" width="24" height="24">'
        f'<rect width="24" height="24" fill="#fff"/>{bar_rect(" fill=\"#000\"")}{gap}</mask>'
        f'<mask id="{pfx}b" maskUnits="userSpaceOnUse" x="0" y="0" width="24" height="24">'
        f'<rect width="24" height="24" fill="#fff"/>{gap}</mask></defs>'
    )
    return (
        defs
        + f'<g fill="none" stroke="currentColor" stroke-width="{fmt(STROKE)}" mask="url(#{pfx}g)">'
        f'<circle cx="{fmt(cx)}" cy="{fmt(cy)}" r="{fmt(r)}"/>'
        f'<ellipse cx="{fmt(cx)}" cy="{fmt(cy)}" rx="{fmt(MERIDIAN_RX)}" ry="{fmt(r)}"/></g>'
        f'<g mask="url(#{pfx}b)">{bar_rect(f" fill=\"none\" stroke=\"currentColor\" stroke-width=\"{fmt(STROKE)}\"")}</g>'
        f'<path d="{cur}" fill="{cursor_fill}" stroke="{cursor_fill}" stroke-width="0.8" stroke-linejoin="round"/>'
    )


def app_icon(fill: str = BRAND_HEX, ink: str = BRAND_FG_HEX, radius: float = 5.6) -> str:
    """Full-bleed brand tile with the mark in the foreground colour (favicon, PWA, apple-touch)."""
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">'
            f'<rect width="24" height="24" rx="{fmt(radius)}" fill="{fill}"/>'
            f'<g transform="translate(2.5 2.5) scale(.79)" color="{ink}">{lens_mark("ai")}</g></svg>')


def svg_doc(body: str, w: float, h: float, extra: str = "") -> str:
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {fmt(w)} {fmt(h)}" fill="currentColor"{extra}>'
            f"{body}</svg>")


def lockup_svg(cursor_fill: str = "currentColor", pfx: str = "lk") -> tuple[str, float, float]:
    """Mark + wordmark. Mark height = 1.55 x cap height; gap = 0.5 x cap height."""
    wm, wm_w = wordmark(slit=False)
    mark_h = CAP * 1.55
    gap = CAP * 0.5
    body = (f'<g transform="scale({fmt(mark_h / 24)})">{lens_mark(pfx, cursor_fill)}</g>'
            + wm.svg(mark_h + gap, (mark_h - CAP) / 2))
    return body, mark_h + gap + wm_w, mark_h


# --------------------------------------------------------------------------- outputs

WEB = HERE.parent / "web"


def write_outputs() -> None:
    OUT.mkdir(exist_ok=True)
    for old in OUT.glob("*.svg"):
        old.unlink()
    wm, wm_w = wordmark(slit=False)
    lk, lw, lh = lockup_svg()
    lk2, _, _ = lockup_svg(BRAND_HEX, "lk2")
    files = {
        "mark.svg": svg_doc(lens_mark(), 24, 24),
        "mark-two-tone.svg": svg_doc(lens_mark("t", BRAND_HEX), 24, 24),
        "app-icon.svg": app_icon(),
        "wordmark.svg": svg_doc(wm.svg(), wm_w, CAP),
        "logo.svg": svg_doc(lk, lw, lh),
        "logo-two-tone.svg": svg_doc(lk2, lw, lh),
    }
    for name, content in files.items():
        (OUT / name).write_text(content + "\n", encoding="utf-8")

    # Web app assets: favicon + geometry module (single source of truth for the React components).
    (WEB / "src" / "app" / "icon.svg").write_text(app_icon() + "\n", encoding="utf-8")
    inner = "".join(wm.items)
    cx, cy, r = GLOBE
    x, y, w, h, br = BAR
    ts = (
        "// Generated by brand/generate.py — do not edit by hand.\n"
        f"export const WORDMARK_WIDTH = {fmt(wm_w)};\n"
        f"export const WORDMARK_HEIGHT = {fmt(CAP)};\n"
        f"export const WORDMARK_SVG = {inner!r};\n"
        f"export const STROKE = {fmt(STROKE)};\n"
        f"export const GLOBE = {{ cx: {fmt(cx)}, cy: {fmt(cy)}, r: {fmt(r)}, meridianRx: {fmt(MERIDIAN_RX)} }};\n"
        f"export const BAR = {{ x: {fmt(x)}, y: {fmt(y)}, w: {fmt(w)}, h: {fmt(h)}, r: {fmt(br)} }};\n"
        f"export const CURSOR_PATH = {cursor_path()!r};\n"
        f"export const CURSOR_GAP = {fmt(CURSOR_GAP)};\n"
    )
    (WEB / "src" / "components" / "brand" / "geometry.ts").write_text(ts, encoding="utf-8")
    (HERE / "board.html").write_text(board_html(), encoding="utf-8")


BOARD_CSS = """
body{margin:0;font:14px/1.5 system-ui,Segoe UI,sans-serif;background:#f6f7f9;color:#1c2128}
.b{max-width:1180px;margin:0 auto;padding:48px} h1{font-size:13px;letter-spacing:.16em;text-transform:uppercase;margin:0 0 4px}
p.l{color:#5b6573;max-width:760px;margin:0 0 32px} .g{display:grid;gap:16px;grid-template-columns:repeat(3,1fr)}
.c{background:#fff;border:1px solid #e3e6ea;border-radius:12px;padding:28px;display:flex;flex-direction:column;gap:16px;min-height:200px}
.c.d{background:#111418;color:#eef1f4;border-color:#111418} .lb{font-size:11px;letter-spacing:.12em;text-transform:uppercase;color:#7a8492;font-weight:600}
.art{flex:1;display:flex;align-items:center;justify-content:center;gap:22px;flex-wrap:wrap}
.w2{grid-column:span 2} .w3{grid-column:span 3} figure{margin:0;display:flex;flex-direction:column;align-items:center;gap:6px}
figcaption{font-size:11px;color:#7a8492} .sw{display:flex;flex-direction:column;gap:4px;font-size:12px}
.chip{width:100%;height:56px;border-radius:8px;border:1px solid #0001} code{font-size:11px;color:#5b6573}
.pal{display:grid;grid-template-columns:repeat(7,1fr);gap:12px}
"""


def board_html() -> str:
    lk, lw, lh = lockup_svg(pfx="b1")
    lk2, _, _ = lockup_svg(BRAND_HEX, "b2")
    lkd, _, _ = lockup_svg(oklch_to_hex(0.76, 0.115, 205), "b3")
    wm, wm_w = wordmark(slit=False)
    swatches = "".join(
        f"<div class='sw'><div class='chip' style='background:{oklch_to_hex(*v)}'></div><b>{k}</b>"
        f"<code>oklch({v[0]} {v[1]} {v[2]})</code><code>{oklch_to_hex(*v)}</code></div>"
        for k, v in PALETTE.items()
    )
    sizes = "".join(
        "<figure>" + app_icon().replace("<svg ", f"<svg width={n} height={n} ").replace('id="ai', f'id="ai{n}').replace("#ai", f"#ai{n}")
        + f"<figcaption>{n}px</figcaption></figure>"
        for n in (16, 24, 32, 48, 64, 128)
    )
    mk = lambda p, c, extra: svg_doc(lens_mark(p, c), 24, 24, extra)  # noqa: E731
    return (
        "<!doctype html><html><head><meta charset='utf-8'><title>WEB X-RAY — Browse identity</title>"
        f"<style>{BOARD_CSS}</style></head><body><div class='b'>"
        "<h1>WEB X-RAY · Browse identity</h1>"
        "<p class='l'>A globe — the web — crossed by an address bar, with a cursor resting on the bar: WEB X-RAY browsing "
        "the internet on your behalf. In the product it animates only while an investigation is running (the globe turns, "
        "a scan sweeps the bar, the cursor clicks). One brand colour, Lens Teal, on cool neutrals.</p><div class='g'>"
        f"<div class='c w2'><div class='lb'>Primary logo · two-tone</div><div class='art'>{svg_doc(lk2, lw, lh, ' style=\"height:56px;color:#1c2128\"')}</div></div>"
        f"<div class='c'><div class='lb'>Mark · ink / brand</div><div class='art'>{mk('x1', 'currentColor', ' width=\"84\" height=\"84\" style=\"color:#1c2128\"')}{mk('x2', 'currentColor', f' width=\"84\" height=\"84\" style=\"color:{BRAND_HEX}\"')}</div></div>"
        f"<div class='c d w2'><div class='lb'>Primary logo · dark</div><div class='art'>{svg_doc(lkd, lw, lh, ' style=\"height:56px;color:#eef1f4\"')}</div></div>"
        f"<div class='c'><div class='lb'>Monochrome</div><div class='art'>{svg_doc(lk, lw, lh, ' style=\"height:34px;color:#000\"')}</div></div>"
        f"<div class='c w3'><div class='lb'>App icon / favicon at real size</div><div class='art'>{sizes}</div></div>"
        f"<div class='c w3'><div class='lb'>Palette</div><div class='pal'>{swatches}</div></div>"
        "</div></div></body></html>"
    )


def render() -> None:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": 1180, "height": 900})
        page.goto((HERE / "board.html").as_uri())
        page.wait_for_timeout(800)
        page.screenshot(path=str(HERE / "board.png"), full_page=True)
        icon = browser.new_page(viewport={"width": 180, "height": 180})
        icon.set_content("<body style='margin:0'>" + app_icon(radius=0).replace("<svg ", "<svg width=180 height=180 ") + "</body>")
        icon.screenshot(path=str(WEB / "src" / "app" / "apple-icon.png"))
        browser.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--render", action="store_true")
    args = ap.parse_args()
    write_outputs()
    if args.render:
        render()
    print("wrote brand/out, web/src/app/icon.svg, web/src/components/brand/geometry.ts, brand/board.html")
