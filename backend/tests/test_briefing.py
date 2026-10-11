from __future__ import annotations

import uuid

import httpx
import pytest
from sqlalchemy import select

from tests.conftest import register
from webxray.db import session_scope
from webxray.models import AuditLog, Briefing, Job
from webxray.services.briefing import ReadPage, Visit, build_briefing, pick_pages, question_terms

DEMO = "http://127.0.0.1:4100"


def _page(path: str, *, title: str = "", kind: str = "content", buttons=(), links=(), meta=None, h1=(), text="", forms=()):
    return ReadPage(
        url=f"https://shop.example{path}", path=path, status=200, title=title, kind=kind,
        inventory={"h1": list(h1), "buttons": [{"text": b} for b in buttons],
                   "links": [{"href": f"https://shop.example{h}", "text": t, "inNav": nav} for h, t, nav in links],
                   "forms": list(forms)},
        meta=meta or {}, text=text,
    )


# --------------------------------------------------------------------------- analysis units


def test_pick_pages_prefers_explanatory_pages_and_question() -> None:
    links = [
        {"url": "https://a.example/blog/post-1", "text": "Post one", "in_nav": False},
        {"url": "https://a.example/pricing", "text": "Pricing", "in_nav": True},
        {"url": "https://a.example/about", "text": "About us", "in_nav": True},
        {"url": "https://a.example/shipping", "text": "Shipping & returns", "in_nav": False},
        {"url": "https://a.example/terms", "text": "Terms", "in_nav": False},
    ]
    plan = pick_pages(links, limit=3, question="Do you ship to Canada?")
    urls = [u for u, _ in plan]
    assert urls[0] == "https://a.example/shipping"  # matches "ship"
    assert "https://a.example/about" in urls and "https://a.example/pricing" in urls
    assert len(plan) == 3
    assert question_terms("What do they sell?") == ["sell"]


def test_store_briefing_is_built_from_observed_signals() -> None:
    home = _page(
        "/", title="Home · Northwind Supply", kind="home", h1=["Tools for considered work"],
        links=[("/products", "Shop", True), ("/help", "Help", True), ("/login", "Log in", True), ("/register", "Create account", True)],
        meta={"description": "Small-batch stationery and desk goods.", "prices": ["$24.00", "$12.00"], "lang": "en",
              "footer": "© 2026 Northwind Supply Co. All rights reserved.", "emails": ["Hello@northwind.example"]},
    )
    product = _page("/products/notebook", title="Notebook · Northwind Supply", kind="product", buttons=["Add to cart"],
                    meta={"prices": ["$24.00"], "jsonld_types": ["Product", "Offer"]})
    cart = _page("/cart", title="Cart · Northwind Supply", kind="cart")
    b = build_briefing(Visit(origin="https://shop.example", pages=[home, product, cart]))

    assert b["name"] == "Northwind Supply" and b["name_source"] == "the page titles"
    assert b["site_type"]["key"] == "online_store" and b["site_type"]["confidence"] == "high"
    assert any("Add to cart" in r for r in b["site_type"]["reasons"])
    caps = {c["key"]: c for c in b["capabilities"]}
    assert {"buy", "browse_products", "sign_up", "log_in", "contact"} <= caps.keys()
    assert caps["buy"]["pages"] == ["/products/notebook", "/cart"]
    assert b["description"] == "Small-batch stationery and desk goods."
    assert b["summary"].startswith("Northwind Supply is an online store.")
    assert "“Small-batch stationery and desk goods.”" in b["summary"]
    assert [s["label"] for s in b["sections"]] == ["Shop", "Help"]  # sign-in links are capabilities, not sections
    assert b["organization"]["copyright"] == "Northwind Supply Co"
    assert b["organization"]["emails"] == ["hello@northwind.example"]
    assert b["languages"] == ["en"]


def test_weak_signals_are_hedged_not_overstated() -> None:
    b = build_briefing(Visit(origin="https://quiet.example", pages=[_page("/", title="Welcome", kind="home")]))
    assert b["site_type"]["confidence"] == "low"
    assert b["summary"].startswith("quiet.example appears to be")  # "Welcome" is a page word, not a name
    assert b["capabilities"] == [] and b["description"] is None


def test_subscription_prices_point_to_software() -> None:
    home = _page("/", title="Acme", kind="home", buttons=["Start free trial"], links=[("/pricing", "Pricing", True)],
                 meta={"prices": ["$12/month"]})
    pricing = _page("/pricing", title="Pricing — Acme", meta={"prices": ["$12/month", "$29/month"]})
    b = build_briefing(Visit(origin="https://acme.example", pages=[home, pricing]))
    assert b["site_type"]["key"] == "software"
    assert "view_pricing" in {c["key"] for c in b["capabilities"]}


def test_question_answers_quote_the_pages() -> None:
    home = _page("/", title="Shop", kind="home",
                 text="We ship worldwide. Orders to Canada usually arrive in 5 days. Our team is small.")
    b = build_briefing(Visit(origin="https://s.example", pages=[home], question="Do you ship to Canada?"))
    assert b["answer"][0] == {"text": "Orders to Canada usually arrive in 5 days.", "page": "/"}
    assert all("team" not in a["text"] for a in b["answer"])


# --------------------------------------------------------------------------- API


@pytest.mark.parametrize("url", ["http://10.0.0.5", "http://169.254.169.254/latest", "http://localhost:4100", "ftp://example.com"])
async def test_briefing_rejects_non_public_targets(client: httpx.AsyncClient, url: str) -> None:
    await register(client)
    r = await client.post("/api/briefings", json={"url": url})
    assert r.status_code == 422, r.text
    async with session_scope() as s:
        assert (await s.scalars(select(Briefing))).all() == []


async def test_briefing_create_queue_limits_and_isolation(client: httpx.AsyncClient) -> None:
    await register(client)
    r = await client.post("/api/briefings", json={"url": DEMO, "question": "What do they sell?"})
    assert r.status_code == 201, r.text
    first = r.json()
    assert first["status"] == "queued" and first["origin"] == DEMO and first["question"] == "What do they sell?"
    assert (await client.post("/api/briefings", json={"url": DEMO})).status_code == 201
    third = await client.post("/api/briefings", json={"url": DEMO})
    assert third.status_code == 429  # two already active
    async with session_scope() as s:
        jobs = (await s.scalars(select(Job).where(Job.kind == "briefing"))).all()
        assert len(jobs) == 2
        assert (await s.scalar(select(AuditLog).where(AuditLog.action == "briefing.create"))) is not None
    # Still running: cannot be deleted.
    assert (await client.delete(f"/api/briefings/{first['id']}")).status_code == 409

    await client.post("/api/auth/logout")
    await register(client, "other@example.com")
    assert (await client.get(f"/api/briefings/{first['id']}")).status_code == 404
    assert (await client.get("/api/briefings")).json() == []


async def test_briefing_screenshot_links_are_signed(client: httpx.AsyncClient) -> None:
    await register(client)
    bid = (await client.post("/api/briefings", json={"url": DEMO})).json()["id"]
    r = await client.get(f"/api/briefings/{bid}/shots/0?exp=9999999999&sig=forged")
    assert r.status_code == 403
    r = await client.get(f"/api/briefings/{uuid.uuid4()}/shots/0?exp=1&sig=x")
    assert r.status_code == 403


# --------------------------------------------------------------------------- end to end


@pytest.mark.e2e
async def test_briefing_reads_demo_shop_without_changing_anything(client: httpx.AsyncClient) -> None:
    from webxray.worker.main import run_worker

    async with httpx.AsyncClient(base_url=DEMO) as demo:
        try:
            await demo.get("/__demo/health")
        except httpx.HTTPError:
            pytest.skip("demo shop is not running on :4100")
        await demo.post("/__demo/reset")

    await register(client)
    bid = (await client.post("/api/briefings", json={"url": DEMO, "question": "Is there a help page?"})).json()["id"]
    await run_worker(once=True)

    b = (await client.get(f"/api/briefings/{bid}")).json()
    assert b["status"] == "completed", b["error"]
    res = b["result"]
    assert res["name"] == "Northwind Supply"
    assert res["site_type"]["key"] == "online_store"
    assert res["description"] == "Small-batch stationery and desk goods from Northwind Supply."
    caps = {c["key"] for c in res["capabilities"]}
    assert {"browse_products", "buy", "sign_up", "log_in", "help"} <= caps
    paths = [p["path"] for p in res["pages"]]
    assert paths[0] == "/" and "/about" in paths and "/help" in paths
    assert len(paths) <= 8
    # Never follows state-changing links, never reads robots-disallowed pages.
    assert not any(p.startswith(("/logout", "/orders", "/account", "/__")) for p in paths)
    assert any(s["url"].endswith("/orders") or "/account" in s["url"] for s in res["skipped"]) or "/orders" not in str(res)
    assert any(a["page"] == "/help" for a in res["answer_pages"])
    assert all("Log in" not in a["text"] for a in res["answer"])  # main content only, not nav chrome
    # Screenshots are stored and served through signed links.
    assert len(b["shots"]) == len(paths)
    shot = await client.get(b["shots"][0]["url"])
    assert shot.status_code == 200 and shot.content[:8] == b"\x89PNG\r\n\x1a\n"
    assert b["steps"] and any("robots.txt" in s["message"] for s in b["steps"])

    # Deleting removes the row and the stored screenshots.
    from webxray.storage.artifacts import get_artifact_store
    async with session_scope() as s:
        keys = [shot["key"] for shot in (await s.get(Briefing, uuid.UUID(bid))).shots]
    assert (await client.delete(f"/api/briefings/{bid}")).status_code == 204
    assert (await client.get(f"/api/briefings/{bid}")).status_code == 404
    for key in keys:
        with pytest.raises(FileNotFoundError):
            get_artifact_store().get(key)

    # The demo shop saw only reads: no accounts, carts or orders.
    async with httpx.AsyncClient(base_url=DEMO) as demo:
        health = (await demo.get("/__demo/health")).json()
    assert health.get("users", 0) == 0 and health.get("orders", 0) == 0


# --------------------------------------------------------------------------- sign-in


def test_member_pages_are_reported_separately() -> None:
    home = _page("/", title="Home · Shop", kind="home", links=[("/login", "Log in", True)])
    login = _page("/login", title="Log in · Shop", kind="login")
    landing = _page("/products", title="Shop · Shop", kind="listing")
    landing.signed_in = True
    orders = _page("/orders", title="Your orders · Shop", kind="orders", buttons=["Track parcel"])
    orders.signed_in = True
    visit = Visit(origin="https://s.example", pages=[home, login, landing, orders],
                  auth_status="authenticated", auth_detail="Signed in.", signed_in_as="jo•••@s.example")
    b = build_briefing(visit)
    assert b["sign_in"] == {"status": "authenticated", "detail": "Signed in.", "as": "jo•••@s.example", "pages": ["/products", "/orders"]}
    assert "After signing in as jo•••@s.example, we also read 2 members-only pages: Shop and Your orders." in b["summary"]
    assert "On the 2 public pages we read" in b["summary"]
    assert [p["signed_in"] for p in b["pages"]] == [False, False, True, True]
    assert not any("Add an account" in n for n in b["notes"])
    assert any("robots.txt" in n for n in b["notes"])


async def test_sign_in_requires_confirmation_and_same_site_login_page(client: httpx.AsyncClient) -> None:
    await register(client)
    login = {"username": "me@example.com", "password": "hunter2-secret"}
    r = await client.post("/api/briefings", json={"url": DEMO, "login": login})
    assert r.status_code == 422 and "Confirm" in r.text
    r = await client.post("/api/briefings", json={"url": DEMO, "confirm_account": True,
                                                  "login": {**login, "login_url": "https://evil.example/login"}})
    assert r.status_code == 422 and "same website" in r.text
    r = await client.post("/api/briefings", json={"url": DEMO, "confirm_account": True, "login": {**login, "login_url": "/login"}})
    assert r.status_code == 201, r.text
    out = r.json()
    assert out["auth_status"] == "pending" and out["login_url"] == f"{DEMO}/login"
    assert out["credential_hint"] == "me•@example.com"
    assert "hunter2-secret" not in r.text and "credential_ciphertext" not in out
    async with session_scope() as s:
        row = await s.get(Briefing, uuid.UUID(out["id"]))
        assert row.credential_ciphertext and b"hunter2-secret" not in row.credential_ciphertext
        audit_row = await s.scalar(select(AuditLog).where(AuditLog.action == "briefing.create"))
        assert audit_row.details == {"origin": DEMO, "sign_in": True}


async def _demo_account(email: str, password: str) -> None:
    async with httpx.AsyncClient(base_url=DEMO, follow_redirects=True) as demo:
        await demo.get("/")  # the demo only binds a sign-up to an existing session
        r = await demo.post("/register", data={"name": "Briefing Tester", "email": email, "password": password,
                                                "confirm": password, "terms": "yes"})
        assert r.status_code == 200
        await demo.post("/onboarding", data={"interests": "paper"})
        r = await demo.post("/onboarding", data={"country": "US"})
        assert r.url.path == "/products"  # onboarding finished


@pytest.mark.e2e
async def test_briefing_signs_in_and_reads_member_pages(client: httpx.AsyncClient) -> None:
    from webxray.worker.main import run_worker

    async with httpx.AsyncClient(base_url=DEMO) as demo:
        try:
            await demo.get("/__demo/health")
        except httpx.HTTPError:
            pytest.skip("demo shop is not running on :4100")
        await demo.post("/__demo/reset")
    password = "member-pass-9137"
    await _demo_account("member@shop.test", password)

    await register(client)
    r = await client.post("/api/briefings", json={
        "url": DEMO, "question": "Where can I see my orders?", "confirm_account": True,
        "login": {"username": "member@shop.test", "password": password}})
    bid = r.json()["id"]
    await run_worker(once=True)

    b = (await client.get(f"/api/briefings/{bid}")).json()
    assert b["status"] == "completed", b["error"]
    assert b["auth_status"] == "authenticated", b["auth_detail"]
    res = b["result"]
    assert res["sign_in"]["status"] == "authenticated"
    member = res["sign_in"]["pages"]
    assert "/orders" in member and "/account/profile" in member  # robots-disallowed publicly, readable as the member
    assert not any(p.startswith("/products") for p in member)  # public pages aren't re-read as "member" pages
    assert all(p["signed_in"] for p in res["pages"] if p["path"] in member[1:])
    assert not any(p["path"].startswith("/logout") for p in res["pages"])
    assert "After signing in as me" in res["summary"]
    assert any(s["signed_in"] for s in b["shots"]) and not b["shots"][0]["signed_in"]
    # The secret never appears anywhere we store or return, and the ciphertext is gone.
    blob = r.text + str(b)
    assert password not in blob and "member@shop.test" not in blob
    async with session_scope() as s:
        row = await s.get(Briefing, uuid.UUID(bid))
        assert row.credential_ciphertext is None
        assert password not in str(row.steps) + str(row.result)
    # Read-only: still exactly one account (ours) and no orders.
    async with httpx.AsyncClient(base_url=DEMO) as demo:
        health = (await demo.get("/__demo/health")).json()
    assert health["users"] == 1 and health["orders"] == 0


@pytest.mark.e2e
async def test_briefing_reports_failed_sign_in_and_still_briefs(client: httpx.AsyncClient) -> None:
    from webxray.worker.main import run_worker

    async with httpx.AsyncClient(base_url=DEMO) as demo:
        try:
            await demo.post("/__demo/reset")
        except httpx.HTTPError:
            pytest.skip("demo shop is not running on :4100")
    await register(client)
    bid = (await client.post("/api/briefings", json={
        "url": DEMO, "confirm_account": True, "login": {"username": "nobody@shop.test", "password": "wrong-password"}})).json()["id"]
    await run_worker(once=True)
    b = (await client.get(f"/api/briefings/{bid}")).json()
    assert b["status"] == "completed"
    assert b["auth_status"] == "failed" and "stayed on its sign-in page" in b["auth_detail"]
    assert "Email or password is incorrect" in b["auth_detail"]  # the site's own message is passed on
    assert b["result"]["sign_in"]["pages"] == []
    assert b["result"]["name"] == "Northwind Supply"


@pytest.mark.e2e
async def test_briefing_falls_back_to_http_like_a_browser(client: httpx.AsyncClient) -> None:
    from webxray.worker.main import run_worker

    async with httpx.AsyncClient(base_url=DEMO) as demo:
        try:
            await demo.post("/__demo/reset")
        except httpx.HTTPError:
            pytest.skip("demo shop is not running on :4100")
    await register(client)
    # What the dashboard sends when someone types "127.0.0.1:4100" without a scheme.
    bid = (await client.post("/api/briefings", json={"url": "127.0.0.1:4100"})).json()["id"]
    await run_worker(once=True)
    b = (await client.get(f"/api/briefings/{bid}")).json()
    assert b["status"] == "completed", b["error"]
    assert b["origin"] == DEMO
    assert any("plain http" in n for n in b["result"]["notes"])
    assert b["result"]["pages"][0]["url"].startswith("http://")


def test_site_name_skips_page_words_and_login_home_is_members_only() -> None:
    home = _page("/", title="Choice SMS | Login", kind="login")
    b = build_briefing(Visit(origin="http://choicesms.example", pages=[home]))
    assert b["name"] == "Choice SMS"
    assert b["site_type"]["key"] == "members_only"
    assert any("home page is a sign-in page" in n for n in b["notes"])
