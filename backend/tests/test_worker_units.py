from __future__ import annotations

import asyncio

import pytest

from webxray.security.redaction import Redactor
from webxray.security.target_policy import EgressPolicy, parse_origin
from webxray.worker.auth_flow import field_purpose
from webxray.worker.browser import VIEWPORTS, BrowserSession
from webxray.worker.crawler import classify, normalize_url
from webxray.worker.journeys.checkout import checkout_purpose
from webxray.worker.locators import LocatorSpec, to_typescript
from webxray.worker.test_runner import classify_report


@pytest.mark.parametrize(
    ("href", "base", "expected"),
    [
        ("/products?sort=price&utm_source=x#top", "http://127.0.0.1:4100/", "http://127.0.0.1:4100/products?sort=price"),
        ("HTTP://Example.com:80//a//b/", None, "http://example.com/a/b"),
        ("?b=2&a=1", "https://example.com/list", "https://example.com/list?a=1&b=2"),
        ("mailto:x@example.com", "https://example.com/", None),
        ("javascript:void(0)", "https://example.com/", None),
    ],
)
def test_normalize_url(href: str, base: str | None, expected: str | None) -> None:
    assert normalize_url(href, base) == expected


def test_classify_pages() -> None:
    assert classify("https://x.test/register", {"passwordFields": 2}) == "register"
    assert classify("https://x.test/login", {"passwordFields": 1}) == "login"
    assert classify("https://x.test/p/1", {"buttons": [{"text": "Add to cart"}]}) == "product"
    assert classify("https://x.test/cart", {}) == "cart"
    assert classify("https://x.test/checkout", {}) == "checkout"
    assert classify("https://x.test/", {}) == "home"


def test_field_purposes() -> None:
    assert field_purpose({"type": "email", "label": "Email"}, 0) == "email"
    assert field_purpose({"type": "password", "label": "Password"}, 0) == "password"
    assert field_purpose({"type": "password", "label": "Confirm password"}, 1) == "confirm_password"
    assert field_purpose({"type": "checkbox", "label": "I agree to the terms"}, 0) == "terms"
    assert checkout_purpose({"autocomplete": "cc-number"}) == "cc-number"
    assert checkout_purpose({"label": "Postal code"}) == "postal-code"
    assert checkout_purpose({"autocomplete": "shipping street-address"}) == "street-address"


def test_locator_typescript_rendering() -> None:
    assert to_typescript(LocatorSpec("role", role="button", name='Place "order"')) == (
        "page.getByRole('button', { name: \"Place \\\"order\\\"\", exact: true })"
    )
    assert to_typescript(LocatorSpec("label", label="Email")) == 'page.getByLabel("Email", { exact: true })'
    assert to_typescript(LocatorSpec("role", role="link", name_pattern="cart", nth=1)) == (
        "page.getByRole('link', { name: /cart/i }).nth(1)"
    )


def _report(status: str, message: str | None = None) -> dict:
    result = {"status": status, "errors": [{"message": message}] if message else []}
    return {"suites": [{"specs": [{"title": "t", "tests": [{"results": [result]}]}], "suites": []}]}


def test_classify_report_requires_defect_marker() -> None:
    assert classify_report(_report("passed"))[1] == "not_reproduced"
    assert classify_report(_report("failed", "Error: [WEBXRAY-DEFECT] covered"))[1] == "reproduced"
    # A failure anywhere else must NOT count as reproduction.
    assert classify_report(_report("failed", "Error: [WEBXRAY-PRECONDITION] login must succeed"))[1] == "inconclusive"
    assert classify_report(_report("failed", "TimeoutError: locator.click"))[1] == "inconclusive"
    assert classify_report(_report("skipped"))[1] == "inconclusive"
    assert classify_report({"suites": [], "errors": [{"message": "SyntaxError"}]})[1] == "inconclusive"


# ------------------------------------------------------------------ real Chromium egress enforcement


async def _serve(body: bytes) -> tuple[asyncio.base_events.Server, int]:
    async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        await reader.readuntil(b"\r\n\r\n")
        writer.write(b"HTTP/1.1 200 OK\r\nContent-Type: text/html\r\nContent-Length: %d\r\nConnection: close\r\n\r\n%s" % (len(body), body))
        await writer.drain()
        writer.close()

    server = await asyncio.start_server(handle, "127.0.0.1", 0)
    return server, server.sockets[0].getsockname()[1]


async def test_chromium_traffic_is_policy_checked_including_loopback() -> None:
    other, other_port = await _serve(b"internal service")
    page_html = f'<title>ok</title><img src="http://127.0.0.1:{other_port}/secret"><img src="http://169.254.169.254/x">'.encode()
    site, port = await _serve(page_html)
    origin = f"http://127.0.0.1:{port}"
    try:
        # Without an allowlist entry, even the target itself is unreachable.
        async with BrowserSession(EgressPolicy(), parse_origin(origin), Redactor()) as s:
            ctx, page, inst = await s.new_context(VIEWPORTS["desktop"])
            resp = await page.goto(origin)
            assert resp is not None and resp.status == 403
            await ctx.close()
        # Allowlisting the exact origin permits it — and nothing else on loopback or metadata.
        policy = EgressPolicy.from_origins([80, 443], [origin])
        async with BrowserSession(policy, parse_origin(origin), Redactor()) as s:
            ctx, page, inst = await s.new_context(VIEWPORTS["desktop"])
            resp = await page.goto(origin)
            assert resp is not None and resp.status == 200
            await page.wait_for_timeout(500)
            denied = {d.host + ":" + str(d.port) for d in s.denied}
            assert f"127.0.0.1:{other_port}" in denied
            assert "169.254.169.254:80" in denied
            assert not any(n.url.endswith("/secret") and n.status == 200 for n in inst.network)
            # Out-of-scope top-level navigation is refused by the scope guard.
            with pytest.raises(Exception):
                await page.goto("http://example.com/")
            await ctx.close()
    finally:
        other.close()
        site.close()
