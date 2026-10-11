"""Sign-in against small local pages that mimic real-world login forms."""

from __future__ import annotations

import asyncio
import contextlib
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import pytest
from playwright.async_api import async_playwright

from webxray.security.crypto import TestAccountSecret
from webxray.worker import auth_flow

PAGES = {
    # An "ID" field with no label (like an SMS portal) and no logout link afterwards.
    "/id-login": """<form method=post action=/id-login><input type=text name=user>
        <input type=password name=password><input type=submit value=login></form>""",
    # A login form with an arithmetic human check.
    "/math-login": """<form method=post action=/math-login><label>Username <input name=username></label>
        <label>Password <input type=password name=password></label>
        <label>What is 3 + 4? Answer <input type=number name=capt required></label><button>LOGIN</button></form>""",
}
DASHBOARD = "<h1>Welcome back</h1><p>Credits: 120</p><a href=/reports>Reports</a>"


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a: Any) -> None:  # silence
        pass

    def _send(self, body: str, code: int = 200) -> None:
        data = f"<!doctype html><title>Portal</title>{body}".encode()
        self.send_response(code)
        self.send_header("content-type", "text/html")
        self.send_header("content-length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:
        self._send(PAGES.get(self.path, "not found"), 200 if self.path in PAGES else 404)

    def do_POST(self) -> None:
        length = int(self.headers.get("content-length", 0))
        form = dict(x.split("=", 1) for x in self.rfile.read(length).decode().split("&") if "=" in x)
        if self.path == "/id-login" and form.get("user") == "4471" and form.get("password") == "pw-ok":
            self._send(DASHBOARD)
        else:
            self._send(PAGES.get(self.path, "") + "<div role=alert>Invalid ID or password</div>", 401)


class FakeRec:
    async def action(self, *a: Any, **k: Any) -> None: ...
    async def event(self, *a: Any, **k: Any) -> int:
        return 0
    async def update(self, **k: Any) -> None: ...
    async def evidence(self, *a: Any, **k: Any) -> None:
        return None


@pytest.fixture(scope="module")
def site() -> Any:
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()


async def _login(url: str, user: str, pw: str) -> auth_flow.AuthOutcome:
    from webxray.worker.browser import Instrument
    from webxray.security.redaction import Redactor
    from webxray.security.target_policy import parse_origin

    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        inst = Instrument(scope=parse_origin(url), redactor=Redactor())
        try:
            return await auth_flow.login(page, inst, url, TestAccountSecret(user, pw), FakeRec())  # type: ignore[arg-type]
        finally:
            with contextlib.suppress(Exception):
                await browser.close()


async def test_id_field_without_label_and_no_logout_link(site: str) -> None:
    ok = await _login(f"{site}/id-login", "4471", "pw-ok")
    assert ok.status == "authenticated", ok.detail
    bad = await _login(f"{site}/id-login", "4471", "wrong")
    assert bad.status == "failed" and bad.messages and "Invalid ID or password" in bad.messages[0]


async def test_human_check_question_is_never_answered(site: str) -> None:
    out = await _login(f"{site}/math-login", "someone", "pw")
    assert out.status == "blocked_captcha"
    assert "security question" in out.detail
