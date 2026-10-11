"""Isolated, instrumented Chromium sessions.

One :class:`BrowserSession` = one Chromium process + one egress proxy, created
per investigation and torn down afterwards. Each journey run gets a fresh
browser context. Instrumentation is attached before any page script runs.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from dataclasses import dataclass, field
from typing import Any

from playwright.async_api import (
    Browser,
    BrowserContext,
    ConsoleMessage,
    Dialog,
    Error as PlaywrightError,
    Page,
    Playwright,
    Request,
    Route,
    async_playwright,
)

from webxray.security.redaction import Redactor
from webxray.security.target_policy import EgressPolicy, Origin, TargetRejected, parse_origin
from webxray.worker.egress_proxy import EgressDecision, EgressProxy

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class ViewportConfig:
    name: str
    label: str
    width: int
    height: int
    is_mobile: bool
    has_touch: bool
    device_scale_factor: float
    user_agent: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "label": self.label,
            "width": self.width,
            "height": self.height,
            "is_mobile": self.is_mobile,
            "has_touch": self.has_touch,
            "device_scale_factor": self.device_scale_factor,
        }


_UA_SUFFIX = " WEB-X-RAY/0.1 (+authorized-investigation)"
_DESKTOP_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/153.0.0.0 Safari/537.36" + _UA_SUFFIX
)
_MOBILE_UA = (
    "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/153.0.0.0 Mobile Safari/537.36" + _UA_SUFFIX
)
_TABLET_UA = (
    "Mozilla/5.0 (Linux; Android 14; Pixel Tablet) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/153.0.0.0 Safari/537.36" + _UA_SUFFIX
)

VIEWPORTS: dict[str, ViewportConfig] = {
    "desktop": ViewportConfig("desktop", "Desktop", 1440, 900, False, False, 1, _DESKTOP_UA),
    "tablet": ViewportConfig("tablet", "Tablet", 768, 1024, True, True, 2, _TABLET_UA),
    "mobile": ViewportConfig("mobile", "Mobile", 390, 844, True, True, 3, _MOBILE_UA),
}

CHROMIUM_ARGS = [
    "--disable-quic",
    "--force-webrtc-ip-handling-policy=disable_non_proxied_udp",
    "--webrtc-ip-handling-policy=disable_non_proxied_udp",
    "--disable-background-networking",
    "--disable-component-update",
    "--disable-sync",
    "--disable-default-apps",
    "--disable-extensions",
    "--no-pings",
    "--dns-prefetch-disable",
    "--disable-features=NetworkPrediction,OptimizationHints,MediaRouter,DialMediaRouteProvider",
]

SENSITIVE_MASK_SELECTORS = [
    "input[type=password]",
    "input[autocomplete^='cc-']",
    "input[autocomplete='one-time-code']",
]


@dataclass
class NetworkEntry:
    id: int
    ts: float
    method: str
    url: str
    resource_type: str
    same_origin: bool
    is_navigation: bool
    step: str | None
    status: int | None = None
    failure: str | None = None
    duration_ms: int | None = None
    blocked_by_policy: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {k: v for k, v in self.__dict__.items()}


@dataclass
class ConsoleEntry:
    ts: float
    type: str
    text: str
    location: str | None
    step: str | None

    def as_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)


@dataclass
class Instrument:
    """Collects browser signals for one context, tagged with the active step."""

    scope: Origin
    redactor: Redactor
    started: float = field(default_factory=time.monotonic)
    step: str | None = None
    network: list[NetworkEntry] = field(default_factory=list)
    console: list[ConsoleEntry] = field(default_factory=list)
    page_errors: list[dict[str, Any]] = field(default_factory=list)
    dialogs: list[dict[str, Any]] = field(default_factory=list)
    blocked_navigations: list[dict[str, Any]] = field(default_factory=list)
    _req_ids: dict[int, NetworkEntry] = field(default_factory=dict)
    _req_start: dict[int, float] = field(default_factory=dict)
    _counter: int = 0

    def now(self) -> float:
        return round((time.monotonic() - self.started) * 1000) / 1000

    def mark(self, step: str | None) -> dict[str, int]:
        self.step = step
        return self.cursor()

    def cursor(self) -> dict[str, int]:
        return {"network": len(self.network), "console": len(self.console), "page_errors": len(self.page_errors)}

    def since(self, cursor: dict[str, int]) -> dict[str, list[dict[str, Any]]]:
        return {
            "network": [n.as_dict() for n in self.network[cursor["network"] :]],
            "console": [c.as_dict() for c in self.console[cursor["console"] :]],
            "page_errors": list(self.page_errors[cursor["page_errors"] :]),
        }

    def _same_origin(self, url: str) -> bool:
        try:
            return parse_origin(url) == self.scope
        except TargetRejected:
            return False

    # Playwright listeners ------------------------------------------------------

    def on_request(self, request: Request) -> None:
        self._counter += 1
        entry = NetworkEntry(
            id=self._counter,
            ts=self.now(),
            method=request.method,
            url=self.redactor.url(request.url)[:1000],
            resource_type=request.resource_type,
            same_origin=self._same_origin(request.url),
            is_navigation=request.is_navigation_request(),
            step=self.step,
        )
        self.network.append(entry)
        self._req_ids[id(request)] = entry
        self._req_start[id(request)] = time.monotonic()

    def _finish(self, request: Request) -> NetworkEntry | None:
        entry = self._req_ids.pop(id(request), None)
        start = self._req_start.pop(id(request), None)
        if entry is not None and start is not None:
            entry.duration_ms = int((time.monotonic() - start) * 1000)
        return entry

    async def on_request_finished(self, request: Request) -> None:
        entry = self._finish(request)
        if entry is None:
            return
        with contextlib.suppress(PlaywrightError):
            response = await request.response()
            if response is not None:
                entry.status = response.status
                if response.status == 403 and response.headers.get("x-webxray-egress") == "denied":
                    entry.blocked_by_policy = True

    def on_request_failed(self, request: Request) -> None:
        entry = self._finish(request)
        if entry is None:
            return
        entry.failure = (request.failure or "failed")[:300]
        if "ERR_TUNNEL_CONNECTION_FAILED" in entry.failure or "ERR_BLOCKED_BY_CLIENT" in entry.failure:
            entry.blocked_by_policy = True

    def on_console(self, msg: ConsoleMessage) -> None:
        loc = msg.location
        location = f"{self.redactor.url(loc.get('url', ''))}:{loc.get('lineNumber', 0)}" if loc else None
        self.console.append(
            ConsoleEntry(self.now(), msg.type, self.redactor.text(msg.text)[:2000], location, self.step)
        )

    def on_page_error(self, error: PlaywrightError) -> None:
        self.page_errors.append(
            {
                "ts": self.now(),
                "message": self.redactor.text(str(error.message))[:2000],
                "stack": self.redactor.text(str(error.stack or ""))[:4000],
                "step": self.step,
            }
        )


class BrowserSession:
    def __init__(
        self,
        policy: EgressPolicy,
        scope: Origin,
        redactor: Redactor,
        *,
        headless: bool = True,
        byte_budget: int = 512 * 1024 * 1024,
    ) -> None:
        self.policy = policy
        self.scope = scope
        self.redactor = redactor
        self.headless = headless
        self.denied: list[EgressDecision] = []
        # Additional origins top-level navigation may reach (e.g. a site's www/bare-domain
        # twin). Connections are still checked by the egress proxy either way.
        self.also_allowed: set[Origin] = set()
        self.proxy = EgressProxy(policy, byte_budget=byte_budget, on_denied=self.denied.append)
        self._pw: Playwright | None = None
        self._browser: Browser | None = None

    async def start(self) -> BrowserSession:
        await self.proxy.start()
        self._pw = await async_playwright().start()
        self._browser = await self._pw.chromium.launch(
            headless=self.headless,
            proxy={
                "server": self.proxy.server_url,
                "username": self.proxy.username,
                "password": self.proxy.password,
            },
            # Playwright adds "--proxy-bypass-list=<-loopback>", which makes
            # Chromium send loopback traffic through the proxy too. Do not
            # override it: tests assert loopback is policy-checked.
            args=CHROMIUM_ARGS,
        )
        return self

    async def close(self) -> None:
        with contextlib.suppress(Exception):
            if self._browser is not None:
                await self._browser.close()
        with contextlib.suppress(Exception):
            if self._pw is not None:
                await self._pw.stop()
        await self.proxy.stop()

    async def __aenter__(self) -> BrowserSession:
        return await self.start()

    async def __aexit__(self, *exc: object) -> None:
        await self.close()

    def drain_denied(self) -> list[EgressDecision]:
        out, self.denied[:] = list(self.denied), []
        return out

    async def new_context(
        self, viewport: ViewportConfig, storage_state: dict[str, Any] | None = None
    ) -> tuple[BrowserContext, Page, Instrument]:
        assert self._browser is not None, "BrowserSession not started"
        context = await self._browser.new_context(
            viewport={"width": viewport.width, "height": viewport.height},
            device_scale_factor=viewport.device_scale_factor,
            is_mobile=viewport.is_mobile,
            has_touch=viewport.has_touch,
            user_agent=viewport.user_agent,
            accept_downloads=False,
            service_workers="block",
            java_script_enabled=True,
            ignore_https_errors=False,
            locale="en-US",
            timezone_id="UTC",
            storage_state=storage_state,  # type: ignore[arg-type]
        )
        context.set_default_timeout(10_000)
        context.set_default_navigation_timeout(20_000)
        inst = Instrument(scope=self.scope, redactor=self.redactor)

        async def guard(route: Route, request: Request) -> None:
            # Scope guard for top-level navigations. Network-level safety is the
            # egress proxy's job; this keeps the *crawl* inside the approved origin.
            if request.is_navigation_request() and request.frame.parent_frame is None:
                try:
                    target = parse_origin(request.url)
                    in_scope = target == self.scope or target in self.also_allowed
                except TargetRejected:
                    in_scope = False
                if not in_scope:
                    inst.blocked_navigations.append(
                        {"ts": inst.now(), "url": self.redactor.url(request.url)[:500], "step": inst.step}
                    )
                    await route.abort("blockedbyclient")
                    return
            await route.continue_()

        await context.route("**/*", guard)
        context.on("request", inst.on_request)
        context.on("requestfinished", lambda r: asyncio.ensure_future(inst.on_request_finished(r)))
        context.on("requestfailed", inst.on_request_failed)

        page = await context.new_page()
        page.on("console", inst.on_console)
        page.on("pageerror", inst.on_page_error)

        def on_dialog(dialog: Dialog) -> None:
            inst.dialogs.append(
                {"ts": inst.now(), "type": dialog.type, "message": self.redactor.text(dialog.message)[:500], "step": inst.step}
            )
            asyncio.ensure_future(dialog.dismiss())

        page.on("dialog", on_dialog)

        def on_popup(popup: Page) -> None:
            # Investigations run in a single tab; popups are recorded and closed.
            inst.blocked_navigations.append({"ts": inst.now(), "url": "popup", "step": inst.step})
            asyncio.ensure_future(popup.close())

        context.on("page", lambda p: on_popup(p) if p is not page else None)
        return context, page, inst


async def screenshot(page: Page, *, full_page: bool = False) -> bytes:
    masks = [page.locator(sel) for sel in SENSITIVE_MASK_SELECTORS]
    return await page.screenshot(
        type="png", full_page=full_page, mask=masks, mask_color="#2b2b33", animations="disabled", caret="hide", timeout=15_000
    )


async def settle(page: Page, idle_ms: int = 2500) -> None:
    """Wait for the page to settle without failing on long-polling sites."""
    with contextlib.suppress(PlaywrightError):
        await page.wait_for_load_state("domcontentloaded", timeout=10_000)
    with contextlib.suppress(PlaywrightError):
        await page.wait_for_load_state("networkidle", timeout=idle_ms)
