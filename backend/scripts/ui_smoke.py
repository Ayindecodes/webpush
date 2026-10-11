"""Dashboard smoke check: visit every screen at desktop and mobile widths.

Fails on console errors, failed /api requests, uncaught page errors, or
horizontal overflow at mobile width. Screenshots go to .data/ui-smoke/.

Usage: python scripts/ui_smoke.py --email you@example.com --password ... [--base http://localhost:3000]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from playwright.async_api import async_playwright

OUT = Path(__file__).resolve().parents[2] / ".data" / "ui-smoke"
VIEWPORTS = {"desktop": (1440, 900), "mobile": (390, 844)}
IGNORED_CONSOLE = ("[HMR]", "[Fast Refresh]", "Download the React DevTools")


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://localhost:3000")
    ap.add_argument("--email", required=True)
    ap.add_argument("--password", required=True)
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    problems: list[str] = []

    async with async_playwright() as pw:
        browser = await pw.chromium.launch()
        ctx = await browser.new_context()
        r = await ctx.request.post(f"{args.base}/api/auth/login", data={"email": args.email, "password": args.password})
        if r.status != 200:
            print("login failed", r.status, await r.text())
            return 2
        invs = await (await ctx.request.get(f"{args.base}/api/investigations?limit=1")).json()
        finds = await (await ctx.request.get(f"{args.base}/api/findings?classification=confirmed_defect&limit=1")).json()
        projects = await (await ctx.request.get(f"{args.base}/api/projects")).json()
        pages = ["/", "/investigations", "/investigations/new", "/findings", "/journeys", "/projects", "/integrations", "/settings"]
        if invs:
            pages += [f"/investigations/{invs[0]['id']}", f"/investigations/{invs[0]['id']}/report"]
        if finds:
            pages.append(f"/findings/{finds[0]['id']}")
        if projects:
            pages.append(f"/projects/{projects[0]['id']}")

        for vname, (w, h) in VIEWPORTS.items():
            for path in pages:
                page = await ctx.new_page()
                await page.set_viewport_size({"width": w, "height": h})
                errors: list[str] = []
                page.on("console", lambda m, e=errors: e.append(m.text) if m.type == "error" and not m.text.startswith(IGNORED_CONSOLE) else None)
                page.on("pageerror", lambda exc, e=errors: e.append(f"pageerror: {exc}"))
                page.on("response", lambda resp, e=errors: e.append(f"HTTP {resp.status} {resp.url}") if "/api/" in resp.url and resp.status >= 400 else None)
                await page.goto(f"{args.base}{path}", wait_until="networkidle", timeout=60_000)
                await page.wait_for_timeout(1200)
                overflow = await page.evaluate("document.documentElement.scrollWidth - window.innerWidth")
                name = (path.strip("/").replace("/", "_") or "overview")[:80]
                await page.screenshot(path=str(OUT / f"{vname}-{name}.png"), full_page=False)
                status = "ok"
                if errors:
                    status = "ERRORS"
                    problems += [f"{vname} {path}: {e}" for e in errors[:5]]
                if vname == "mobile" and overflow > 1:
                    status = "OVERFLOW"
                    problems.append(f"{vname} {path}: horizontal overflow {overflow}px")
                print(f"{vname:7} {path:60} {status}")
                await page.close()
        await browser.close()

    (OUT / "result.json").write_text(json.dumps({"problems": problems}, indent=2), encoding="utf-8")
    if problems:
        print("\nPROBLEMS:\n" + "\n".join(problems))
        return 1
    print("\nAll screens rendered without console errors, failed API calls, or mobile overflow.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
