"""Scope-bounded website discovery.

Only GET navigations happen here; nothing is clicked or submitted. Links that
look state-destroying (logout, delete, unsubscribe, …) are never followed.
"""

from __future__ import annotations

import re
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

from playwright.async_api import Error as PlaywrightError, Page
from sqlalchemy import select

from webxray.db import session_scope
from webxray.models import Page as PageRow
from webxray.security.target_policy import Origin, TargetRejected, parse_origin
from webxray.worker.browser import BrowserSession, Instrument, screenshot, settle
from webxray.worker.dom import INVENTORY_JS
from webxray.worker.recorder import Recorder

TRACKING_PARAMS = re.compile(r"^(utm_\w+|gclid|fbclid|mc_cid|mc_eid|_ga|ref|ref_src)$", re.I)
SKIP_LINK = re.compile(
    r"(log-?out|sign-?out|logoff|log_off|/delete|/remove|/destroy|unsubscribe|/cancel|deactivate|/__)", re.I
)
NON_HTML_EXT = re.compile(
    r"\.(pdf|zip|gz|tar|rar|7z|dmg|exe|msi|png|jpe?g|gif|webp|svg|ico|mp4|mp3|webm|woff2?|ttf|css|js|json|xml|csv)$",
    re.I,
)


def normalize_url(href: str, base: str | None = None) -> str | None:
    """Canonical form used for dedupe: no fragment, no tracking params, sorted query."""
    try:
        url = urljoin(base, href) if base else href
        parts = urlsplit(url)
    except ValueError:
        return None
    if parts.scheme.lower() not in {"http", "https"} or not parts.hostname:
        return None
    try:
        origin = parse_origin(url)
    except TargetRejected:
        return None
    path = re.sub(r"/{2,}", "/", parts.path or "/")
    if len(path) > 1 and path.endswith("/"):
        path = path[:-1]
    query = urlencode(
        sorted((k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if not TRACKING_PARAMS.match(k))
    )
    return urlunsplit((origin.scheme, str(origin).split("://", 1)[1], path, query, ""))


def path_of(url: str) -> str:
    return urlsplit(url).path or "/"


_LOGIN = re.compile(r"\b(log ?in|sign ?in)\b", re.I)
_REGISTER = re.compile(r"\b(sign ?up|register|create (an |your )?account|join)\b", re.I)
_ADD_TO_CART = re.compile(r"\badd to (cart|bag|basket)\b", re.I)
_ONBOARDING = re.compile(r"(onboard|welcome|setup|get-?started|getting-?started)", re.I)


def classify(url: str, inv: dict[str, Any]) -> str:
    path = path_of(url).lower()
    heading = " ".join(inv.get("h1") or []) + " " + (inv.get("title") or "")
    pw = int(inv.get("passwordFields") or 0)
    buttons = " | ".join(b.get("text", "") for b in inv.get("buttons", []))
    if pw >= 2 or (pw >= 1 and (_REGISTER.search(path) or _REGISTER.search(heading))):
        return "register"
    if pw == 1:
        return "login"
    if _ONBOARDING.search(path):
        return "onboarding"
    if re.search(r"checkout", path) or re.search(r"\bcheckout\b", heading, re.I):
        return "checkout"
    if re.search(r"/(cart|basket|bag)(/|$)", path) or re.search(r"\b(your )?(cart|basket|bag)\b", " ".join(inv.get("h1") or []), re.I):
        return "cart"
    if _ADD_TO_CART.search(buttons):
        return "product"
    if re.search(r"confirm|thank", path):
        return "confirmation"
    if re.search(r"/(account|profile|settings|preferences)", path):
        return "account"
    if re.search(r"/orders?(/|$)", path):
        return "orders"
    if re.search(r"/(products?|shop|catalog|collections?|store)(/|$)", path):
        return "listing"
    if re.search(r"/(help|faq|support|contact)", path):
        return "support"
    if path == "/":
        return "home"
    return "content"


@dataclass
class CrawlLimits:
    max_pages: int = 25
    max_depth: int = 3
    max_query_variants: int = 3
    include_paths: list[str] = field(default_factory=list)
    exclude_paths: list[str] = field(default_factory=list)
    deadline: float | None = None  # time.monotonic() deadline for the whole investigation


@dataclass
class PageSignals:
    http_errors: list[dict[str, Any]] = field(default_factory=list)
    failed_requests: list[dict[str, Any]] = field(default_factory=list)
    blocked_requests: list[dict[str, Any]] = field(default_factory=list)
    console_errors: list[dict[str, Any]] = field(default_factory=list)
    page_errors: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class CrawledPage:
    url: str
    final_url: str
    status: int | None
    title: str
    depth: int
    classification: str
    auth_state: str
    inventory: dict[str, Any]
    screenshot_id: Any
    network_evidence_id: Any
    console_evidence_id: Any
    signals: PageSignals
    internal_links: list[str]


@dataclass
class CrawlReport:
    pages: list[CrawledPage] = field(default_factory=list)
    skipped: list[dict[str, str]] = field(default_factory=list)
    stopped_reason: str | None = None
    redirects: dict[str, str] = field(default_factory=dict)


def compact_inventory(inv: dict[str, Any]) -> dict[str, Any]:
    return {
        "h1": inv.get("h1", []),
        "headings": inv.get("headings", [])[:12],
        "forms": [
            {
                "index": f["index"],
                "action": f["action"],
                "method": f["method"],
                "fields": [
                    {k: fld.get(k) for k in ("type", "name", "label", "required", "autocomplete")}
                    for fld in f["fields"]
                ],
                "submits": [s["text"] for s in f["submits"]],
            }
            for f in inv.get("forms", [])
        ],
        "buttons": sorted({b["text"] for b in inv.get("buttons", []) if b.get("text")})[:40],
        "nav_links": sorted({lnk["text"] for lnk in inv.get("links", []) if lnk.get("inNav") and lnk.get("text")})[:30],
        "link_count": len(inv.get("links", [])),
        "password_fields": inv.get("passwordFields", 0),
        "captcha": inv.get("captcha", False),
        "overflow_x": inv.get("overflowX", 0),
        "alerts": inv.get("alerts", [])[:5],
    }


class Crawler:
    def __init__(self, session: BrowserSession, recorder: Recorder, scope: Origin, limits: CrawlLimits) -> None:
        self.session = session
        self.recorder = recorder
        self.scope = scope
        self.limits = limits

    def in_scope(self, url: str) -> bool:
        try:
            if parse_origin(url) != self.scope:
                return False
        except TargetRejected:
            return False
        path = path_of(url)
        if any(path.startswith(p) for p in self.limits.exclude_paths):
            return False
        if self.limits.include_paths and not any(path.startswith(p) for p in self.limits.include_paths):
            return False
        return True

    async def crawl(
        self,
        page: Page,
        inst: Instrument,
        seeds: list[str],
        auth_state: str,
        *,
        on_page: Any = None,
    ) -> CrawlReport:
        report = CrawlReport()
        visited: set[str] = set()
        queued: set[str] = set()
        variants: dict[str, set[str]] = {}
        queue: deque[tuple[str, int, str | None]] = deque()

        def enqueue(url: str, depth: int, src: str | None) -> None:
            if url in queued or url in visited:
                return
            if depth > self.limits.max_depth:
                report.skipped.append({"url": url, "reason": "max depth"})
                return
            if not self.in_scope(url):
                report.skipped.append({"url": url, "reason": "out of scope"})
                return
            if SKIP_LINK.search(path_of(url)):
                report.skipped.append({"url": url, "reason": "potentially state-changing link (not followed)"})
                return
            if NON_HTML_EXT.search(path_of(url)):
                return
            key = path_of(url)
            seen = variants.setdefault(key, set())
            if url not in seen and len(seen) >= self.limits.max_query_variants:
                report.skipped.append({"url": url, "reason": "query-variant limit for this path"})
                return
            seen.add(url)
            queued.add(url)
            queue.append((url, depth, src))

        for seed in seeds:
            n = normalize_url(seed)
            if n:
                enqueue(n, 0, None)

        while queue:
            if len(report.pages) >= self.limits.max_pages:
                report.stopped_reason = f"page limit ({self.limits.max_pages}) reached"
                break
            if self.limits.deadline and time.monotonic() > self.limits.deadline:
                report.stopped_reason = "time budget exhausted"
                break
            await self.recorder.checkpoint()
            url, depth, src = queue.popleft()
            if url in visited:
                continue
            visited.add(url)
            result = await self._visit(page, inst, url, depth, src, auth_state, report, visited)
            if result is None:
                continue
            report.pages.append(result)
            if on_page is not None:
                await on_page(result)
            for link in result.internal_links:
                enqueue(link, depth + 1, url)

        if queue and not report.stopped_reason:
            report.stopped_reason = "queue exhausted"
        if not queue and not report.stopped_reason:
            report.stopped_reason = "all reachable in-scope links visited"
        return report

    async def _visit(
        self,
        page: Page,
        inst: Instrument,
        url: str,
        depth: int,
        src: str | None,
        auth_state: str,
        report: CrawlReport,
        visited: set[str],
    ) -> CrawledPage | None:
        rec = self.recorder
        await rec.action(f"Visiting {path_of(url)}", current_url=url)
        cursor = inst.mark(f"crawl:{path_of(url)}")
        t0 = time.monotonic()
        status: int | None = None
        try:
            response = await page.goto(url, wait_until="domcontentloaded")
            status = response.status if response else None
        except PlaywrightError as exc:
            await rec.event("navigation", f"Navigation to {url} failed: {str(exc).splitlines()[0][:200]}", level="warn", page_url=url)
            return None
        await settle(page)
        load_ms = int((time.monotonic() - t0) * 1000)
        final = normalize_url(page.url) or url
        if final != url:
            report.redirects[url] = final
            await rec.event("navigation", f"{path_of(url)} redirected to {path_of(final)}", page_url=url, data={"from": url, "to": final, "auth_state": auth_state})
            if not self.in_scope(final) or final in visited:
                return None
            visited.add(final)
        try:
            inv: dict[str, Any] = await page.evaluate(INVENTORY_JS)
        except PlaywrightError as exc:
            await rec.event("navigation", f"Could not inspect {url}: {str(exc)[:200]}", level="warn", page_url=url)
            return None

        classification = classify(final, inv)
        shot = await screenshot(page)
        title = rec.redactor.text(inv.get("title") or "")[:300]
        shot_id = await rec.evidence(
            "screenshot", shot, label=f"{title or path_of(final)} ({auth_state})", content_type="image/png",
            meta={"url": final, "viewport": inv.get("viewport"), "auth_state": auth_state, "masked": True},
        )
        await rec.update(current_url=final, current_title=title, latest_screenshot_id=shot_id)

        window = inst.since(cursor)
        signals = PageSignals()
        denied = self.session.drain_denied()
        for n in window["network"]:
            if n.get("blocked_by_policy"):
                host = urlsplit(n["url"]).hostname or ""
                reason = next((d.reason for d in denied if d.host == host), "blocked by egress policy")
                signals.blocked_requests.append({**n, "reason": reason})
            elif n.get("failure") and "ERR_ABORTED" not in (n.get("failure") or ""):
                signals.failed_requests.append(n)
            elif (n.get("status") or 0) >= 400 and n.get("same_origin"):
                signals.http_errors.append(n)
        matched_hosts = {urlsplit(b["url"]).hostname for b in signals.blocked_requests}
        for d in denied:
            if d.host not in matched_hosts:
                signals.blocked_requests.append({"url": f"{d.host}:{d.port}", "reason": d.reason, "method": d.method})
        signals.console_errors = [c for c in window["console"] if c["type"] == "error"]
        signals.page_errors = window["page_errors"]

        network_eid = console_eid = None
        if signals.http_errors or signals.failed_requests or signals.blocked_requests:
            network_eid = await rec.evidence(
                "network_log", {"page": final, "requests": window["network"]},
                label=f"Network activity on {path_of(final)}", meta={"url": final, "auth_state": auth_state},
            )
        if signals.console_errors or signals.page_errors:
            console_eid = await rec.evidence(
                "console_log", {"page": final, "console": window["console"], "page_errors": window["page_errors"]},
                label=f"Console output on {path_of(final)}", meta={"url": final, "auth_state": auth_state},
            )

        internal: list[str] = []
        for link in inv.get("links", []):
            n = normalize_url(link.get("href", ""))
            if n and n not in internal:
                try:
                    if parse_origin(n) == self.scope:
                        internal.append(n)
                except TargetRejected:
                    pass

        compact = compact_inventory(inv)
        compact["internal_links"] = internal[:150]
        async with session_scope() as s:
            existing = await s.scalar(
                select(PageRow.id).where(
                    PageRow.investigation_id == rec.investigation_id,
                    PageRow.url == final,
                    PageRow.auth_state == auth_state,
                )
            )
            if existing is None:
                s.add(
                    PageRow(
                        org_id=rec.org_id, project_id=rec.project_id, investigation_id=rec.investigation_id,
                        url=final, final_url=final, title=title, status_code=status, depth=depth,
                        auth_state=auth_state, classification=classification, discovered_from=src,
                        inventory=rec.redactor.deep(compact), screenshot_id=shot_id,
                        console_error_count=len(signals.console_errors) + len(signals.page_errors),
                        failed_request_count=len(signals.http_errors) + len(signals.failed_requests) + len(signals.blocked_requests),
                        load_ms=load_ms,
                    )
                )
        level = "warn" if (status or 0) >= 400 else "info"
        issues = []
        if signals.http_errors:
            issues.append(f"{len(signals.http_errors)} HTTP error(s)")
        if signals.console_errors or signals.page_errors:
            issues.append(f"{len(signals.console_errors) + len(signals.page_errors)} console error(s)")
        if signals.blocked_requests:
            issues.append(f"{len(signals.blocked_requests)} request(s) blocked by egress policy")
        await rec.event(
            "navigation",
            f"Visited {path_of(final)} ({status}) · {classification}" + (f" · {', '.join(issues)}" if issues else ""),
            level=level, page_url=final, evidence_id=shot_id,
            data={"status": status, "classification": classification, "depth": depth, "auth_state": auth_state, "load_ms": load_ms},
        )
        for b in signals.blocked_requests:
            await rec.event("policy", f"Egress policy blocked a request to {b.get('url')}: {b.get('reason', 'denied')}", level="warn", page_url=final, data=b)

        return CrawledPage(
            url=url, final_url=final, status=status, title=title, depth=depth, classification=classification,
            auth_state=auth_state, inventory=inv, screenshot_id=shot_id, network_evidence_id=network_eid,
            console_evidence_id=console_eid, signals=signals, internal_links=internal,
        )
