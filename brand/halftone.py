"""Generate the halftone dot textures used on the landing page.

True halftone: dots on a grid whose radius follows a soft falloff field, rendered
to transparent PNGs so they can sit on any paper/ink background.

    python brand/halftone.py      (needs Playwright)
"""

from __future__ import annotations

import math
from pathlib import Path

from playwright.sync_api import sync_playwright

OUT = Path(__file__).resolve().parents[1] / "web" / "public" / "landing"


def field_hero(x: float, y: float) -> float:
    """Soft cloud on the right, fading left and down (behind the hero illustration)."""
    d = math.hypot((x - 0.78) / 0.42, (y - 0.42) / 0.62)
    return max(0.0, 1.0 - d) ** 1.35


def field_band(x: float, y: float) -> float:
    """Left-weighted band (behind section headlines)."""
    d = math.hypot((x - 0.12) / 0.55, (y - 0.5) / 0.75)
    return max(0.0, 1.0 - d) ** 1.25


def halftone_svg(w: int, h: int, step: float, field, color: str) -> str:
    dots = []
    rows, cols = int(h / step), int(w / step)
    for r in range(rows):
        for c in range(cols):
            # Offset every other row for a classic halftone lattice.
            x = c * step + (step / 2 if r % 2 else 0)
            y = r * step
            v = field(x / w, y / h)
            # Deterministic dithering noise so the edge breaks up like print.
            n = (math.sin(c * 12.9898 + r * 78.233) * 43758.5453) % 1.0
            v = v * (0.82 + 0.36 * n)
            if v < 0.05:
                continue
            radius = min(step * 0.48, step * 0.5 * v)
            dots.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{radius:.2f}"/>')
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" '
            f'fill="{color}">{"".join(dots)}</svg>')


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    jobs = {
        "halftone-hero.png": (1600, 1000, 7.0, field_hero, "#b5ad9d"),
        "halftone-band.png": (1400, 900, 7.0, field_band, "#c2baa9"),
        "halftone-dark.png": (1400, 700, 7.0, field_hero, "#3a3d44"),
    }
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        for name, (w, h, step, field, color) in jobs.items():
            page = browser.new_page(viewport={"width": w, "height": h})
            page.set_content(f"<body style='margin:0;background:transparent'>{halftone_svg(w, h, step, field, color)}</body>")
            page.screenshot(path=str(OUT / name), omit_background=True)
            page.close()
        browser.close()
    print("wrote", ", ".join(jobs))


if __name__ == "__main__":
    main()
