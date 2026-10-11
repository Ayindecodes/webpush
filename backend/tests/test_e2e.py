"""End-to-end acceptance test for the first vertical slice.

Requires the benchmark shop:  DEMO_ALLOW_RESET=1 uvicorn app:app --app-dir demo-shop --port 4100
Runs real Chromium through the real API, queue, worker, and Node test runner.
"""

from __future__ import annotations

import json
import uuid

import httpx
import pytest
from sqlalchemy import select

from tests.conftest import register
from webxray.db import session_scope
from webxray.models import CredentialSecret, Event, Evidence, Finding, Investigation, Page, TestRun
from webxray.security.crypto import decrypt_credential
from webxray.storage.artifacts import get_artifact_store
from webxray.worker.main import run_worker

DEMO = "http://127.0.0.1:4100"
pytestmark = pytest.mark.e2e


def _demo_available() -> bool:
    try:
        return httpx.get(f"{DEMO}/__demo/health", timeout=2).status_code == 200
    except httpx.HTTPError:
        return False


@pytest.fixture
def demo() -> None:
    if not _demo_available():
        pytest.skip("benchmark shop is not running on 127.0.0.1:4100")
    r = httpx.post(f"{DEMO}/__demo/reset", timeout=5)
    if r.status_code != 200:
        pytest.skip("benchmark shop must run with DEMO_ALLOW_RESET=1")


async def test_vertical_slice_detects_reproduces_and_verifies_fix(client: httpx.AsyncClient, demo: None) -> None:
    await register(client)
    pid = (await client.post("/api/projects", json={"name": "Northwind"})).json()["id"]
    env = (await client.post(f"/api/projects/{pid}/environments", json={"origin": DEMO})).json()
    assert (await client.post(f"/api/environments/{env['id']}/verify")).json()["verified"]
    r = await client.post(f"/api/projects/{pid}/investigations", json={
        "environment_id": env["id"], "mode": "autonomous", "goal": "Check checkout on desktop and mobile",
        "confirm_authorized": True, "approve_registration": True, "approve_order_submission": True,
        "config": {"viewports": ["desktop", "mobile"], "allow_registration": True, "allow_order_submission": True,
                   "max_pages": 20, "repeat_failed_runs": 1},
    })
    assert r.status_code == 201, r.text
    inv_id = r.json()["id"]

    await run_worker(once=True)

    inv = (await client.get(f"/api/investigations/{inv_id}")).json()
    assert inv["status"] == "completed", inv["error"]
    assert inv["auth_state"] == "authenticated"
    assert {p["key"]: p["status"] for p in inv["phases"]}["execute"] == "done"

    # --- discovery: dedupe, limits, scope, and destructive-link avoidance
    pages = (await client.get(f"/api/investigations/{inv_id}/pages")).json()
    urls = {(p["url"], p["auth_state"]) for p in pages}
    assert (f"{DEMO}/register", "public") in urls and (f"{DEMO}/account/profile", "authenticated") in urls
    assert not any("/logout" in u for u, _ in urls), "logout link must never be followed"
    assert not any("example.org" in u for u, _ in urls), "off-site links must not be crawled"
    journal = [u for u, a in urls if "/journal" in u and a == "public"]
    assert len(journal) <= 3, "query-variant limit must stop the pagination trap"
    assert not any("utm_source" in u for u, _ in urls), "tracking parameters are normalized away"

    # --- journeys: desktop passes, mobile fails reproducibly at the reachability check
    journeys = (await client.get(f"/api/investigations/{inv_id}/journeys")).json()
    runs = journeys[0]["runs"]
    desktop = [x for x in runs if x["viewport_name"] == "desktop"]
    mobile = [x for x in runs if x["viewport_name"] == "mobile"]
    assert [x["status"] for x in desktop] == ["passed"]
    assert [x["status"] for x in mobile] == ["failed", "failed"]
    assert all(x["failure_step"] == "submit_reachable" for x in mobile)
    for run in runs:  # every step has a recorded outcome
        assert all(s["status"] in {"passed", "failed", "skipped", "error"} for s in run["steps"])

    # --- findings
    findings = (await client.get(f"/api/investigations/{inv_id}/findings")).json()
    journey = next(f for f in findings if f["kind"] == "journey_failure")
    assert journey["classification"] == "confirmed_defect" and journey["severity"] == "critical"
    assert journey["viewport_name"] == "mobile"
    assert journey["reproduction"]["status"] == "reproducible"
    assert journey["reproduction"]["passing_viewports"] == ["desktop"]
    top = journey["hypotheses"][0]
    assert top["key"] == "overlay_interception" and top["status"] == "supported" and top["strength"] == "strong"
    assert "help-bar" in top["rationale"]
    ruled_out = {h["key"] for h in journey["hypotheses"] if h["status"] == "not_supported"}
    assert {"failed_request", "javascript_exception", "disabled_control"} <= ruled_out
    assert journey["test_status"] == "reproduced"

    http = next(f for f in findings if f["kind"] == "http_error")
    assert "/api/recommendations" in http["title"] and "503" in http["title"] and http["classification"] == "warning"
    blocked = next(f for f in findings if f["kind"] == "blocked_request")
    assert "169.254.169.254" in blocked["title"]

    # --- evidence is real, linked, and fetched via short-lived signed links
    evidence = (await client.get(f"/api/findings/{journey['id']}/evidence")).json()
    kinds = {e["kind"] for e in evidence}
    assert {"hit_test", "screenshot", "computed_styles", "dom_snapshot", "network_log", "console_log", "test_output"} <= kinds
    shot = next(e for e in evidence if e["kind"] == "screenshot")
    img = await client.get(shot["url"])
    assert img.status_code == 200 and img.content[:8] == b"\x89PNG\r\n\x1a\n"
    hit = next(e for e in evidence if e["kind"] == "hit_test" and e["role"].startswith("mobile"))
    hit_data = (await client.get(hit["url"])).json()
    assert hit_data["covered_at_all_positions"] is True
    assert hit_data["attempts"][0]["probe"]["received"] is False
    contrast = next(e for e in evidence if e["kind"] == "hit_test" and e["role"].startswith("contrast:desktop"))
    assert (await client.get(contrast["url"])).json()["attempts"][0]["probe"]["received"] is True

    # --- generated test is real TypeScript and its execution is recorded
    test = (await client.post(f"/api/findings/{journey['id']}/reproduce")).json()
    assert "[WEBXRAY-DEFECT]" in test["source"] and "process.env.WEBXRAY_TEST_PASSWORD" in test["source"]
    assert test["runs"][0]["outcome"] == "reproduced" and test["runs"][0]["playwright_status"] == "failed"

    # --- credentials never leak into events, findings, evidence, or the report
    async with session_scope() as s:
        cred = (await s.scalars(select(CredentialSecret).where(CredentialSecret.created_by_investigation_id == uuid.UUID(inv_id)))).one()
        secret = decrypt_credential(cred.ciphertext)
        assert cred.lifecycle_state == "registered"
        assert secret.password not in test["source"]
        haystacks = [e.message + json.dumps(e.data) for e in (await s.scalars(select(Event).where(Event.investigation_id == uuid.UUID(inv_id)))).all()]
        haystacks += [f.summary + (f.observed or "") + json.dumps(f.hypotheses) for f in (await s.scalars(select(Finding))).all()]
        haystacks += [json.dumps((await s.get(Investigation, uuid.UUID(inv_id))).summary)]
        store = get_artifact_store()
        for ev in (await s.scalars(select(Evidence).where(Evidence.investigation_id == uuid.UUID(inv_id)))).all():
            if not ev.content_type.startswith("image/"):
                haystacks.append(store.get(ev.storage_key).decode("utf-8", "replace"))
    report_md = (await client.get(f"/api/investigations/{inv_id}/report?format=markdown")).text
    haystacks.append(report_md)
    assert all(secret.password not in h for h in haystacks)
    assert "Coverage and limitations" in report_md and "reproduced" in report_md

    # --- fix verification: switch the defect off and re-run the generated test
    httpx.post(f"{DEMO}/__demo/flags", json={"DEMO_FIX_CHECKOUT_OVERLAY": True}, timeout=5)
    try:
        r = await client.post(f"/api/tests/{test['id']}/verify")
        assert r.status_code == 202
        await run_worker(once=True)
    finally:
        httpx.post(f"{DEMO}/__demo/flags", json={"DEMO_FIX_CHECKOUT_OVERLAY": False}, timeout=5)
    async with session_scope() as s:
        run = await s.get(TestRun, uuid.UUID(r.json()["id"]))
    assert run.status == "finished" and run.outcome == "not_reproduced" and run.playwright_status == "passed"
    after = (await client.get(f"/api/tests/{test['id']}")).json()
    assert after["verification_status"] == "not_reproduced"
    # A pass after a reproduction means "fixed" — not "the test contradicts the finding".
    fixed = (await client.get(f"/api/findings/{journey['id']}")).json()
    assert fixed["classification"] == "confirmed_defect" and fixed["reproduction"]["status"] == "fixed"
    assert "contradicting" not in fixed["summary"]


async def test_public_only_investigation_without_approvals(client: httpx.AsyncClient, demo: None) -> None:
    """Without approval to register, WEB X-RAY stays in public areas and says so."""
    await register(client)
    pid = (await client.post("/api/projects", json={"name": "Northwind"})).json()["id"]
    env = (await client.post(f"/api/projects/{pid}/environments", json={"origin": DEMO})).json()
    await client.post(f"/api/environments/{env['id']}/verify")
    r = await client.post(f"/api/projects/{pid}/investigations", json={
        "environment_id": env["id"], "mode": "autonomous", "confirm_authorized": True,
        "config": {"viewports": ["desktop"], "max_pages": 6}})
    inv_id = r.json()["id"]
    await run_worker(once=True)
    inv = (await client.get(f"/api/investigations/{inv_id}")).json()
    assert inv["status"] == "completed"
    assert inv["page_count"] <= 6
    assert any("didn't allow creating a test account" in x for x in inv["summary"]["limitations"])
    async with session_scope() as s:
        assert (await s.scalars(select(CredentialSecret))).all() == []
        assert all(p.auth_state == "public" for p in (await s.scalars(select(Page))).all())
