"""Checkout journey: product → add to cart → cart → checkout → place order.

Each step declares an expected outcome and records what was actually
observed. A click is never treated as success by itself; the following state
must be verified. Order submission is a consequential action and only happens
when the investigation carries an explicit sandbox-payment approval.
"""

from __future__ import annotations

import asyncio
import re
import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from playwright.async_api import Error as PlaywrightError, Page

from webxray.db import session_scope
from webxray.models import BrowserRun
from webxray.worker.browser import BrowserSession, Instrument, ViewportConfig, screenshot, settle
from webxray.worker.crawler import CrawledPage, path_of
from webxray.worker.dom import (
    HIT_TEST_JS,
    INVENTORY_JS,
    OVERFLOW_JS,
    PROBE_INSTALL_JS,
    PROBE_READ_JS,
    SCROLL_TO_BOTTOM_JS,
)
from webxray.worker.locators import LocatorSpec, find_by_role, label_spec, resolve
from webxray.worker.recorder import Recorder

ADD_TO_CART = r"\badd to (cart|bag|basket)\b"
CART_LINK = r"\b(cart|basket|bag)\b"
CHECKOUT_ENTRY = r"^\s*(proceed to checkout|checkout|check out|continue to checkout)\b"
SUBMIT_ORDER = r"^\s*(place (your )?order|pay( now)?|complete (purchase|order)|submit order|confirm (order|purchase)|buy now)\b"
ADDED_TEXT = re.compile(r"added to (your )?(cart|bag|basket)", re.I)
EMPTY_CART = re.compile(r"(cart|basket|bag) is empty|no items in your (cart|basket|bag)", re.I)
CONFIRM_URL = re.compile(r"(confirm|success|thank|receipt|complete)", re.I)
CONFIRM_TEXT = re.compile(
    r"(order (is |has been )?(confirmed|placed|complete|received)|thank you for your (order|purchase)|order confirmed)", re.I
)

# Deterministic, obviously fake data. Card values are the sandbox test card and
# are only typed when order submission is approved.
CHECKOUT_VALUES: dict[str, str] = {
    "name": "WEBXRAY Tester",
    "street-address": "1 Test Street",
    "address-level2": "Testville",
    "postal-code": "94105",
    "tel": "+1 555 0100",
    "cc-name": "WEBXRAY Tester",
    "cc-number": "4242 4242 4242 4242",
    "cc-exp": "12/34",
    "cc-csc": "123",
}
PAYMENT_PURPOSES = {"cc-number", "cc-exp", "cc-csc", "cc-name"}


def checkout_purpose(f: dict[str, Any]) -> str | None:
    ac = (f.get("autocomplete") or "").lower().split()
    ac_last = ac[-1] if ac else ""
    known = {
        "email", "name", "street-address", "address-line1", "address-level2", "postal-code", "country",
        "country-name", "tel", "cc-number", "cc-exp", "cc-csc", "cc-name", "given-name", "family-name",
    }
    if ac_last in known:
        return {"address-line1": "street-address", "country-name": "country"}.get(ac_last, ac_last)
    blob = " ".join(str(f.get(k) or "") for k in ("name", "label", "placeholder", "id")).lower()
    for pattern, purpose in [
        (r"e-?mail", "email"),
        (r"card.?(number|no)|\bcard\b", "cc-number"),
        (r"expir|mm ?/ ?yy", "cc-exp"),
        (r"cvc|cvv|security code", "cc-csc"),
        (r"(street|address)", "street-address"),
        (r"\bcity|town", "address-level2"),
        (r"postal|zip|postcode", "postal-code"),
        (r"country", "country"),
        (r"phone|\btel", "tel"),
        (r"name", "name"),
    ]:
        if re.search(pattern, blob):
            return purpose
    return None


@dataclass
class CheckoutPlan:
    product_url: str
    product_title: str
    cart_url: str | None

    def as_dict(self) -> dict[str, Any]:
        return {"product_url": self.product_url, "product_title": self.product_title, "cart_url": self.cart_url}


def plan_checkout(pages: list[CrawledPage]) -> CheckoutPlan | None:
    products = [p for p in pages if p.classification == "product"]
    if not products:
        return None
    products.sort(key=lambda p: (p.auth_state != "authenticated", p.depth, p.final_url))
    cart = next((p for p in pages if p.classification == "cart"), None)
    return CheckoutPlan(products[0].final_url, products[0].title, cart.final_url if cart else None)


@dataclass
class StepResult:
    key: str
    name: str
    expected: str
    status: str = "pending"  # passed | failed | skipped | error
    observed: str = ""
    started_at: float = 0.0
    ended_at: float = 0.0
    evidence: dict[str, Any] = field(default_factory=dict)
    data: dict[str, Any] = field(default_factory=dict)
    signals: dict[str, int] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "key": self.key, "name": self.name, "expected": self.expected, "status": self.status,
            "observed": self.observed, "started_at": self.started_at, "ended_at": self.ended_at,
            "evidence": {k: str(v) for k, v in self.evidence.items() if v}, "data": self.data, "signals": self.signals,
        }


class StepFailed(Exception):
    pass


@dataclass
class RunResult:
    run_id: uuid.UUID
    viewport: ViewportConfig
    attempt: int
    status: str
    failure_step: str | None
    steps: list[StepResult]
    observations: dict[str, Any]
    network: list[dict[str, Any]]
    console: list[dict[str, Any]]
    page_errors: list[dict[str, Any]]
    step_windows: dict[str, dict[str, list[dict[str, Any]]]]

    def step(self, key: str) -> StepResult | None:
        return next((s for s in self.steps if s.key == key), None)


class CheckoutRun:
    def __init__(
        self,
        session: BrowserSession,
        rec: Recorder,
        plan: CheckoutPlan,
        definition: dict[str, Any],
        *,
        viewport: ViewportConfig,
        attempt: int,
        journey_id: uuid.UUID,
        storage_state: dict[str, Any] | None,
        allow_submit: bool,
    ) -> None:
        self.session = session
        self.rec = rec
        self.plan = plan
        self.definition = definition
        # Locators are resolved per viewport: responsive layouts can expose different controls.
        self.resolved: dict[str, Any] = definition.setdefault("resolved", {}).setdefault(viewport.name, {})
        self.viewport = viewport
        self.attempt = attempt
        self.journey_id = journey_id
        self.storage_state = storage_state
        self.allow_submit = allow_submit
        self.steps: list[StepResult] = []
        self.observations: dict[str, Any] = {}
        self.step_windows: dict[str, dict[str, list[dict[str, Any]]]] = {}
        self.run_id = uuid.uuid4()
        self.page: Page
        self.inst: Instrument

    # ------------------------------------------------------------------ helpers

    async def _shot(self, label: str, *, clip: dict[str, float] | None = None) -> uuid.UUID | None:
        try:
            if clip:
                masks = [self.page.locator("input[type=password]"), self.page.locator("input[autocomplete^='cc-']")]
                data = await self.page.screenshot(type="png", clip=clip, mask=masks, animations="disabled", caret="hide")  # type: ignore[arg-type]
            else:
                data = await screenshot(self.page)
        except PlaywrightError:
            return None
        eid = await self.rec.evidence(
            "screenshot", data, label=f"{self.viewport.label} #{self.attempt}: {label}", content_type="image/png",
            run_id=self.run_id, meta={"url": self.page.url, "viewport": self.viewport.as_dict(), "masked": True, "clip": clip},
        )
        if not clip:
            try:
                title = await self.page.title()
            except PlaywrightError:
                title = ""
            await self.rec.update(latest_screenshot_id=eid, current_url=self.page.url, current_title=title)
        return eid

    async def _inventory(self) -> dict[str, Any]:
        return await self.page.evaluate(INVENTORY_JS)

    async def _step(self, key: str, name: str, expected: str, fn: Any, *, blocking: bool = True) -> StepResult:
        await self.rec.checkpoint()
        step = StepResult(key=key, name=name, expected=expected)
        self.steps.append(step)
        cursor = self.inst.mark(key)
        step.started_at = self.inst.now()
        await self.rec.action(f"{self.viewport.label}: {name}")
        try:
            await fn(step)
            if step.status == "pending":
                step.status = "passed"
        except StepFailed as exc:
            step.status = "failed"
            step.observed = step.observed or str(exc)
        except (PlaywrightError, TimeoutError) as exc:
            step.status = "error" if step.status == "pending" else step.status
            step.observed = step.observed or f"Browser error: {str(exc).splitlines()[0][:300]}"
        step.ended_at = self.inst.now()
        window = self.inst.since(cursor)
        self.step_windows[key] = window
        step.signals = {
            "requests": len(window["network"]),
            "http_errors": sum(1 for n in window["network"] if (n.get("status") or 0) >= 400),
            "failed_requests": sum(1 for n in window["network"] if n.get("failure")),
            "console_errors": sum(1 for c in window["console"] if c["type"] == "error"),
            "page_errors": len(window["page_errors"]),
        }
        if "after" not in step.evidence:
            step.evidence["after"] = await self._shot(name)
        level = {"passed": "info", "skipped": "info"}.get(step.status, "error")
        await self.rec.event(
            "assertion",
            f"{self.viewport.label} #{self.attempt} · {name}: {step.status.upper()}" + (f" — {step.observed}" if step.observed else ""),
            level=level, run_id=self.run_id, page_url=self.page.url, evidence_id=step.evidence.get("after"),
            data={"step": key, "status": step.status, "expected": expected, "viewport": self.viewport.name, "attempt": self.attempt},
        )
        if blocking and step.status in {"failed", "error"}:
            raise _Abort()
        return step

    # ------------------------------------------------------------------ steps

    async def _ensure_empty_cart(self, step: StepResult) -> None:
        if not self.plan.cart_url:
            step.status = "skipped"
            step.observed = "No cart page discovered; cart state not reset."
            return
        await self.page.goto(self.plan.cart_url, wait_until="domcontentloaded")
        await settle(self.page)
        removed = 0
        for _ in range(10):
            spec = await find_by_role(self.page, ["button"], r"^\s*remove\b")
            if spec is None:
                break
            await resolve(self.page, spec).click()
            await settle(self.page)
            removed += 1
        step.observed = f"Cart reset for consistent state ({removed} item line(s) removed from the test account's cart)."
        step.data["removed"] = removed

    async def _open_product(self, step: StepResult) -> None:
        await self.page.goto(self.plan.product_url, wait_until="domcontentloaded")
        await settle(self.page)
        spec = await find_by_role(self.page, ["button"], ADD_TO_CART)
        if spec is None:
            raise StepFailed("No visible 'Add to cart' control on the product page.")
        self.resolved["add_to_cart"] = spec.as_dict()
        self.observations["product_url"] = self.plan.product_url
        step.data["locator"] = spec.as_dict()
        step.observed = f"Found {spec.describe()}."

    async def _cart_count(self) -> int | None:
        spec = await find_by_role(self.page, ["link"], CART_LINK)
        if spec is None:
            return None
        try:
            text = await resolve(self.page, spec).inner_text(timeout=2000)
        except PlaywrightError:
            return None
        m = re.search(r"(\d+)", text)
        return int(m.group(1)) if m else None

    async def _add_to_cart(self, step: StepResult) -> None:
        before = await self._cart_count()
        spec = LocatorSpec.from_dict(self.resolved["add_to_cart"])
        await resolve(self.page, spec).click()
        deadline = time.monotonic() + 6
        while time.monotonic() < deadline:
            body = await self.page.inner_text("body")
            after = await self._cart_count()
            if ADDED_TEXT.search(body) or (before is not None and after is not None and after > before):
                step.observed = (
                    f"Cart indicator changed {before} → {after}." if after is not None and before is not None and after > before
                    else "Page confirmed the item was added."
                )
                step.data.update({"count_before": before, "count_after": after})
                return
            await asyncio.sleep(0.25)
        raise StepFailed(f"Clicked {spec.describe()} but no confirmation appeared and the cart count did not increase (was {before}).")

    async def _open_cart(self, step: StepResult) -> None:
        spec = await find_by_role(self.page, ["link"], CART_LINK)
        if spec is not None:
            self.resolved["cart_link"] = spec.as_dict()
            await resolve(self.page, spec).click()
            await settle(self.page)
        elif self.plan.cart_url:
            step.data["note"] = "Cart link not visible at this viewport; navigated to the cart URL directly."
            await self.page.goto(self.plan.cart_url, wait_until="domcontentloaded")
            await settle(self.page)
        else:
            raise StepFailed("No cart link or cart URL available.")
        body = await self.page.inner_text("body")
        if EMPTY_CART.search(body):
            raise StepFailed("Cart page reports an empty cart after adding an item.")
        entry = await find_by_role(self.page, ["link", "button"], CHECKOUT_ENTRY)
        if entry is None:
            raise StepFailed("Cart has items but no checkout control is visible.")
        self.resolved["checkout_entry"] = entry.as_dict()
        step.observed = f"Cart shows items; found {entry.describe()}."

    async def _begin_checkout(self, step: StepResult) -> None:
        entry = LocatorSpec.from_dict(self.resolved["checkout_entry"])
        await resolve(self.page, entry).click()
        await settle(self.page)
        inv = await self._inventory()
        forms = sorted(inv.get("forms", []), key=lambda f: len(f["fields"]), reverse=True)
        on_checkout = "checkout" in path_of(self.page.url).lower() or any("checkout" in h.lower() for h in inv.get("h1", []))
        if not on_checkout or not forms or len(forms[0]["fields"]) < 3:
            raise StepFailed(f"Expected a checkout form; landed on {path_of(self.page.url)} with {len(forms[0]['fields']) if forms else 0} fields.")
        self.observations["checkout_form"] = forms[0]
        self.definition["checkout_path"] = path_of(self.page.url)
        step.observed = f"Checkout form with {len(forms[0]['fields'])} fields at {path_of(self.page.url)}."

    async def _fill_checkout(self, step: StepResult) -> None:
        form = self.observations["checkout_form"]
        fields_plan: list[dict[str, Any]] = []
        filled, skipped = [], []
        for fld in form["fields"]:
            if not fld.get("visible", True):
                continue
            purpose = checkout_purpose(fld)
            label = fld.get("label") or fld.get("name") or "field"
            if purpose is None:
                skipped.append(f"{label} (unrecognized)")
                continue
            spec = await label_spec(self.page, fld.get("label", ""), fld["selector"])
            loc = resolve(self.page, spec)
            if purpose in PAYMENT_PURPOSES and not self.allow_submit:
                skipped.append(f"{label} (payment data withheld: order submission not approved)")
                continue
            if purpose == "email":
                if fld.get("hasValue"):
                    filled.append(f"{label}: kept prefilled account email")
                    fields_plan.append({"purpose": purpose, "locator": spec.as_dict(), "action": "keep"})
                    continue
                value = "webxray-checkout@example.test"
            elif purpose == "country":
                if fld.get("tag") == "select":
                    current = await loc.input_value()
                    opts = [o["value"] for o in fld.get("options") or [] if o["value"]]
                    choice = current or (opts[0] if opts else "")
                    if choice:
                        await loc.select_option(choice)
                        filled.append(f"{label}: {choice}")
                        fields_plan.append({"purpose": purpose, "locator": spec.as_dict(), "action": "select", "value": choice})
                    continue
                value = "United States"
            else:
                value = CHECKOUT_VALUES.get(purpose, "WEBXRAY")
            await loc.fill(value)
            actual = await loc.input_value()
            if actual != value:
                raise StepFailed(f"Field '{label}' did not accept input (expected value to be set, got a different value).")
            filled.append(f"{label}: {'sandbox test value' if purpose in PAYMENT_PURPOSES else 'test value'}")
            fields_plan.append({"purpose": purpose, "locator": spec.as_dict(), "action": "fill"})
        self.resolved["fields"] = fields_plan
        step.data.update({"filled": filled, "skipped": skipped})
        step.observed = f"Filled {len(filled)} field(s)" + (f"; skipped {len(skipped)}" if skipped else "") + "."

    async def _locate_submit(self, step: StepResult) -> None:
        spec = await find_by_role(self.page, ["button"], SUBMIT_ORDER)
        if spec is None:
            raise StepFailed("No order submission control (e.g. 'Place order', 'Pay') found on the checkout page.")
        loc = resolve(self.page, spec)
        if not await loc.is_enabled():
            raise StepFailed(f"{spec.describe()} is disabled after filling the form.")
        self.resolved["submit"] = spec.as_dict()
        step.observed = f"Found {spec.describe()} (visible, enabled)."

    async def _geometry_and_probe(self, loc: Any, position: str) -> dict[str, Any]:
        """Measure the control, then send a real, cancelled tap/click at its visual center.

        The probe answers the question that matters (which element does the
        browser's input pipeline deliver the user's tap to?) independent of
        coordinate-system subtleties. A capture-phase listener cancels the
        event, so the probe does not activate anything in the application.
        """
        geo = await loc.evaluate(HIT_TEST_JS)
        geo["position"] = position
        center = geo["points"][0]
        if not center["onScreen"]:
            geo["probe"] = {"installed": False, "received": False, "reason": "control center is off screen"}
            return geo
        await loc.evaluate(PROBE_INSTALL_JS)
        if self.viewport.has_touch:
            await self.page.touchscreen.tap(center["vx"], center["vy"])
        else:
            await self.page.mouse.click(center["vx"], center["vy"])
        await asyncio.sleep(0.1)
        probe = await self.page.evaluate(PROBE_READ_JS)
        probe["method"] = "tap" if self.viewport.has_touch else "click"
        probe["at"] = {"vx": center["vx"], "vy": center["vy"]}
        geo["probe"] = probe
        # Disagreement between layout-coordinate hit testing and real input delivery.
        geo["coordinate_mismatch"] = bool(probe.get("installed")) and probe.get("received") != center["hit"]
        return geo

    async def _submit_reachable(self, step: StepResult) -> None:
        spec = LocatorSpec.from_dict(self.resolved["submit"])
        loc = resolve(self.page, spec)
        attempts: list[dict[str, Any]] = []

        await loc.scroll_into_view_if_needed()
        await asyncio.sleep(0.15)
        natural = await self._geometry_and_probe(loc, "scrolled into view")
        attempts.append(natural)
        step.evidence["after"] = await self._shot(f"{spec.describe()} scrolled into view")
        c = natural["points"][0]
        pad = 24
        top = max(0, c["vy"] - natural["rect"]["height"] // 2 - pad)
        height = max(0, min(self.viewport.height - top, natural["rect"]["height"] + pad * 2 + 100))
        if height > 0:
            clip = {"x": 0, "y": top, "width": self.viewport.width, "height": height}
            step.evidence["element"] = await self._shot(f"{spec.describe()} region", clip=clip)

        reached = bool(natural["probe"].get("received"))
        if not reached:
            await self.page.evaluate(SCROLL_TO_BOTTOM_JS)
            await asyncio.sleep(0.15)
            attempts.append(await self._geometry_and_probe(loc, "page scrolled to bottom"))
            await loc.evaluate("el => el.scrollIntoView({block: 'center'})")
            await asyncio.sleep(0.15)
            attempts.append(await self._geometry_and_probe(loc, "element centered (if scroll range allows)"))
            await loc.scroll_into_view_if_needed()

        overflow = await self.page.evaluate(OVERFLOW_JS, self.viewport.width)
        if overflow["overflowPx"] > 0:
            self.observations.setdefault("overflow", {})[path_of(self.page.url)] = overflow
            step.evidence["overflow"] = await self.rec.evidence(
                "layout_overflow", overflow,
                label=f"{self.viewport.label} #{self.attempt}: horizontal overflow on {path_of(self.page.url)}",
                run_id=self.run_id, meta={"viewport": self.viewport.as_dict(), "url": self.page.url},
            )

        reachable_somewhere = any(a["probe"].get("received") for a in attempts)
        summary = {
            "locator": spec.as_dict(),
            "method": "probe tap/click at the control's visual center (event cancelled) plus elementFromPoint geometry",
            "attempts": attempts,
            "covered_at_all_positions": not reachable_somewhere,
            "layout_viewport": natural["viewport"],
            "visual_viewport": natural["visualViewport"],
            "document_width": natural["documentWidth"],
        }
        self.observations["hit_test"] = summary
        step.evidence["hit_test"] = await self.rec.evidence(
            "hit_test", summary, label=f"{self.viewport.label} #{self.attempt}: reachability probe of {spec.describe()}",
            run_id=self.run_id, meta={"viewport": self.viewport.as_dict(), "url": self.page.url},
        )
        interceptor = natural["probe"].get("interceptor") or natural.get("interceptor")
        styles = {"target": natural.get("targetStyles")}
        if interceptor:
            styles["overlay_root"] = interceptor.get("overlayStyles")
            styles["overlay_root_element"] = interceptor.get("overlayRoot")
        step.evidence["styles"] = await self.rec.evidence(
            "computed_styles", styles, label=f"{self.viewport.label} #{self.attempt}: computed styles",
            run_id=self.run_id, meta={"viewport": self.viewport.as_dict()},
        )
        if interceptor:
            step.evidence["dom"] = await self.rec.evidence(
                "dom_snapshot",
                {"target": natural.get("targetHtml"), "intercepting_overlay": interceptor.get("html")},
                label=f"{self.viewport.label} #{self.attempt}: sanitized DOM of target and overlay",
                run_id=self.run_id,
                meta={"viewport": self.viewport.as_dict(), "sanitized": "values, scripts and event handlers removed"},
            )
        step.data["hit_test_summary"] = {
            "probe_received": reached,
            "received_by": natural["probe"].get("receivedBy"),
            "element_from_point_hit": natural["centerHit"],
            "coordinate_mismatch": natural.get("coordinate_mismatch", False),
            "interceptor": (interceptor or {}).get("overlayRoot"),
            "positions_tested": len(attempts),
            "reachable_at_any_position": reachable_somewhere,
        }
        if natural["disabled"]:
            raise StepFailed(f"{spec.describe()} is disabled.")
        if not natural["visible"]:
            raise StepFailed(f"{spec.describe()} is not visible.")
        if not natural["probe"].get("installed"):
            raise StepFailed(f"The center of {spec.describe()} is off screen after scrolling it into view.")
        method = natural["probe"]["method"]
        if not reached:
            by = (interceptor or {}).get("overlayRoot") or natural["probe"].get("receivedBy") or {}
            where = (
                "at every tested scroll position" if not reachable_somewhere
                else "when scrolled into view (reachable only after extra scrolling)"
            )
            sel = f" {by.get('selector')}" if by.get("selector") else ""
            raise StepFailed(
                f"A {method} at the center of {spec.describe()} is delivered to <{by.get('tag', '?')}{sel}> "
                f"instead of the control, {where}."
            )
        step.observed = f"A {method} at the visual center of {spec.describe()} is delivered to the control."

    async def _submit_order(self, step: StepResult) -> None:
        if not self.allow_submit:
            step.status = "skipped"
            step.observed = "Order submission not approved for this environment; stopped before the consequential action."
            return
        spec = LocatorSpec.from_dict(self.resolved["submit"])
        loc = resolve(self.page, spec)
        await loc.scroll_into_view_if_needed()
        await asyncio.sleep(0.15)
        geo = await loc.evaluate(HIT_TEST_JS)
        x, y = geo["points"][0]["vx"], geo["points"][0]["vy"]  # visual-viewport coordinates
        reach = ((self.observations.get("hit_test") or {}).get("attempts") or [{}])[0].get("probe", {})
        received_by = reach.get("receivedBy") or geo["target"]
        step.evidence["before"] = await self._shot("before activating the submit control")
        before_url = self.page.url
        start_index = len(self.inst.network)
        # Activate the control the way a user would: a real tap/click at its visual center.
        if self.viewport.has_touch:
            await self.page.touchscreen.tap(x, y)
            method = "tap"
        else:
            await self.page.mouse.click(x, y)
            method = "click"
        await self.rec.event(
            "action", f"{self.viewport.label} #{self.attempt}: {method} at ({x}, {y}) on {spec.describe()}; element at that point: <{received_by.get('tag')}> {received_by.get('selector', '')}",
            run_id=self.run_id, data={"x": x, "y": y, "method": method, "received_by": received_by},
        )
        confirmed = False
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            await asyncio.sleep(0.3)
            try:
                url_ok = CONFIRM_URL.search(path_of(self.page.url)) is not None and self.page.url != before_url
                body = await self.page.inner_text("body", timeout=2000)
            except PlaywrightError:
                continue
            if url_ok or CONFIRM_TEXT.search(body):
                confirmed = True
                break
        await settle(self.page)
        after_requests = [n.as_dict() for n in self.inst.network[start_index:]]
        writes = [n for n in after_requests if n["method"] in {"POST", "PUT", "PATCH"} and n["same_origin"]]
        step.data.update({
            "activation": {"method": method, "x": x, "y": y, "received_by": received_by},
            "requests_after_activation": len(after_requests),
            "submission_requests": [{"method": n["method"], "url": n["url"], "status": n["status"]} for n in writes],
            "url_before": before_url, "url_after": self.page.url,
        })
        self.observations["submission"] = step.data
        if confirmed:
            step.observed = f"Order confirmation reached at {path_of(self.page.url)} (sandbox order)."
            self.observations["order_placed"] = True
            return
        inv = await self._inventory()
        alerts = inv.get("alerts", [])
        detail = f"No order confirmation within 10s after a {method} at the control's center. URL {'unchanged' if self.page.url == before_url else 'changed to ' + path_of(self.page.url)}"
        detail += f"; {len(writes)} submission request(s) sent"
        if alerts:
            detail += f"; page shows: {'; '.join(alerts[:2])}"
        raise StepFailed(detail + ".")

    # ------------------------------------------------------------------ run

    async def execute(self) -> RunResult:
        async with session_scope() as s:
            s.add(BrowserRun(
                id=self.run_id, org_id=self.rec.org_id, project_id=self.rec.project_id,
                investigation_id=self.rec.investigation_id, journey_id=self.journey_id,
                viewport_name=self.viewport.name, viewport=self.viewport.as_dict(), attempt=self.attempt, status="running",
            ))
        await self.rec.event(
            "action", f"Starting checkout journey on {self.viewport.label} ({self.viewport.width}×{self.viewport.height}), attempt {self.attempt}",
            run_id=self.run_id, data={"viewport": self.viewport.as_dict(), "attempt": self.attempt},
        )
        context, self.page, self.inst = await self.session.new_context(self.viewport, self.storage_state)
        try:
            try:
                await self._step("reset_cart", "Reset test account cart", "Cart starts empty for a consistent run", self._ensure_empty_cart, blocking=False)
                await self._step("open_product", "Open product page", "An 'Add to cart' control is visible", self._open_product)
                await self._step("add_to_cart", "Add product to cart", "Cart count increases or an 'added' confirmation appears", self._add_to_cart)
                await self._step("open_cart", "Open cart", "Cart lists the item and offers checkout", self._open_cart)
                await self._step("begin_checkout", "Begin checkout", "A checkout form is shown", self._begin_checkout)
                await self._step("fill_checkout", "Fill checkout form", "Each field accepts its test value", self._fill_checkout)
                await self._step("locate_submit", "Locate order submission control", "Control is visible and enabled", self._locate_submit)
                await self._step("submit_reachable", "Check submit control is reachable", "A tap/click at the control's center reaches the control", self._submit_reachable, blocking=False)
                await self._step("submit_order", "Submit order (sandbox)", "Order confirmation is shown", self._submit_order, blocking=False)
            except _Abort:
                pass
        finally:
            await context.close()

        failed = [s for s in self.steps if s.status in {"failed", "error"}]
        status = "passed" if not failed else ("error" if failed[0].status == "error" else "failed")
        failure_step = failed[0].key if failed else None
        network = [n.as_dict() for n in self.inst.network]
        console = [c.as_dict() for c in self.inst.console]
        net_eid = await self.rec.evidence(
            "network_log", {"viewport": self.viewport.name, "attempt": self.attempt, "requests": network},
            label=f"{self.viewport.label} #{self.attempt}: network log", run_id=self.run_id,
        )
        con_eid = await self.rec.evidence(
            "console_log", {"console": console, "page_errors": self.inst.page_errors, "dialogs": self.inst.dialogs},
            label=f"{self.viewport.label} #{self.attempt}: console log", run_id=self.run_id,
        )
        self.observations["network_evidence"] = str(net_eid)
        self.observations["console_evidence"] = str(con_eid)
        async with session_scope() as s:
            row = await s.get(BrowserRun, self.run_id)
            assert row is not None
            row.status = status
            row.failure_step = failure_step
            row.steps = [st.as_dict() for st in self.steps]
            row.observations = self.rec.redactor.deep({k: v for k, v in self.observations.items() if k != "checkout_form"})
            row.finished_at = datetime.now(UTC)
        await self.rec.event(
            "action",
            f"Checkout journey on {self.viewport.label} attempt {self.attempt}: {status.upper()}" + (f" at '{failure_step}'" if failure_step else ""),
            level="info" if status == "passed" else "error", run_id=self.run_id,
            data={"status": status, "failure_step": failure_step, "viewport": self.viewport.name},
        )
        return RunResult(
            run_id=self.run_id, viewport=self.viewport, attempt=self.attempt, status=status, failure_step=failure_step,
            steps=self.steps, observations=self.observations, network=network, console=console,
            page_errors=list(self.inst.page_errors), step_windows=self.step_windows,
        )


class _Abort(Exception):
    pass
