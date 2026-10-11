from __future__ import annotations

import httpx
import pytest
from sqlalchemy import select

from tests.conftest import register
from webxray.db import session_scope
from webxray.models import Approval, AuditLog, CredentialSecret, Evidence, Investigation, Job

DEMO = "http://127.0.0.1:4100"


async def _project(client: httpx.AsyncClient, name: str = "Shop") -> str:
    r = await client.post("/api/projects", json={"name": name})
    assert r.status_code == 201, r.text
    return r.json()["id"]


async def _verified_env(client: httpx.AsyncClient, project_id: str) -> dict:
    r = await client.post(f"/api/projects/{project_id}/environments", json={"origin": DEMO + "/some/path"})
    assert r.status_code == 201, r.text
    env = r.json()
    assert env["origin"] == DEMO and env["verification_status"] == "pending"
    r = await client.post(f"/api/environments/{env['id']}/verify")
    assert r.status_code == 200 and r.json()["verified"] and r.json()["method"] == "operator_allowlist"
    return r.json()["environment"]


async def test_auth_lifecycle(client: httpx.AsyncClient) -> None:
    assert (await client.get("/api/auth/me")).status_code == 401
    user = await register(client)
    assert user["email"] == "dev@example.com"
    assert (await client.get("/api/auth/me")).status_code == 200
    r = await client.post("/api/auth/register", json={"email": "dev@example.com", "password": "another-long-pass"})
    assert r.status_code == 409
    assert (await client.post("/api/auth/logout")).status_code == 204
    assert (await client.get("/api/auth/me")).status_code == 401
    r = await client.post("/api/auth/login", json={"email": "dev@example.com", "password": "wrong-password"})
    assert r.status_code == 401
    r = await client.post("/api/auth/login", json={"email": "DEV@example.com", "password": "correct-horse-battery"})
    assert r.status_code == 200
    assert (await client.get("/api/auth/me")).status_code == 200


async def test_short_password_rejected(client: httpx.AsyncClient) -> None:
    r = await client.post("/api/auth/register", json={"email": "a@example.com", "password": "short"})
    assert r.status_code == 422


@pytest.mark.parametrize(
    ("origin", "code"),
    [
        ("http://10.0.0.5", "private_address"),
        ("http://169.254.169.254", "private_address"),
        ("http://localhost:4100", "private_address"),  # not the exact allowlisted host
        ("http://127.0.0.1:5432", "private_address"),
        ("ftp://example.com", "invalid_scheme"),
        ("https://user:pw@example.com", "invalid_url"),
    ],
)
async def test_prohibited_targets_rejected(client: httpx.AsyncClient, origin: str, code: str) -> None:
    await register(client)
    pid = await _project(client)
    r = await client.post(f"/api/projects/{pid}/environments", json={"origin": origin})
    assert r.status_code == 422, r.text
    assert r.json()["detail"]["code"] in {code, "port_blocked"}


async def test_unverified_target_cannot_be_investigated(client: httpx.AsyncClient) -> None:
    await register(client)
    pid = await _project(client)
    env = (await client.post(f"/api/projects/{pid}/environments", json={"origin": DEMO})).json()
    r = await client.post(f"/api/projects/{pid}/investigations", json={
        "environment_id": env["id"], "mode": "autonomous", "confirm_authorized": True})
    assert r.status_code == 422
    assert "Verify" in r.json()["detail"]


async def test_investigation_requires_authorization_and_records_approvals(client: httpx.AsyncClient) -> None:
    await register(client)
    pid = await _project(client)
    env = await _verified_env(client, pid)
    base = {"environment_id": env["id"], "mode": "autonomous"}
    r = await client.post(f"/api/projects/{pid}/investigations", json={**base, "confirm_authorized": False})
    assert r.status_code == 422
    r = await client.post(f"/api/projects/{pid}/investigations", json={
        **base, "confirm_authorized": True, "config": {"allow_order_submission": True}})
    assert r.status_code == 422  # consequential action without explicit approval
    r = await client.post(f"/api/projects/{pid}/investigations", json={
        **base, "confirm_authorized": True, "approve_registration": True, "approve_order_submission": True,
        "config": {"allow_registration": True, "allow_order_submission": True, "viewports": ["mobile", "desktop", "mobile"]}})
    assert r.status_code == 201, r.text
    inv = r.json()
    assert inv["status"] == "queued" and inv["config"]["viewports"] == ["desktop", "mobile"]
    async with session_scope() as s:
        kinds = {a.kind for a in (await s.scalars(select(Approval).where(Approval.investigation_id == inv["id"]))).all()}
        jobs = (await s.scalars(select(Job).where(Job.ref_id == inv["id"]))).all()
    assert kinds == {"scan_authorization", "account_registration", "order_submission"}
    assert len(jobs) == 1 and jobs[0].status == "queued"
    # Only one active investigation per target.
    r = await client.post(f"/api/projects/{pid}/investigations", json={**base, "confirm_authorized": True})
    assert r.status_code == 409
    # Stopping a queued investigation takes effect immediately.
    r = await client.post(f"/api/investigations/{inv['id']}/stop")
    assert r.status_code == 200 and r.json()["status"] == "stopped"
    assert (await client.post(f"/api/investigations/{inv['id']}/resume")).status_code == 409


async def test_credentials_are_encrypted_and_never_returned(client: httpx.AsyncClient) -> None:
    await register(client)
    pid = await _project(client)
    env = await _verified_env(client, pid)
    r = await client.post(f"/api/projects/{pid}/credentials", json={
        "environment_id": env["id"], "label": "QA account", "username": "qa-person@example.com", "password": "Sup3r-Secret-PW!"})
    assert r.status_code == 201
    body = r.text
    assert "Sup3r-Secret-PW!" not in body and "qa-person@example.com" not in body
    listing = (await client.get(f"/api/projects/{pid}/credentials")).text
    assert "Sup3r-Secret-PW!" not in listing and "qa-person" not in listing
    async with session_scope() as s:
        cred = (await s.scalars(select(CredentialSecret))).one()
        audits = (await s.scalars(select(AuditLog))).all()
    assert b"Sup3r-Secret-PW!" not in bytes(cred.ciphertext)
    assert all("Sup3r-Secret-PW!" not in str(a.details) and "qa-person" not in str(a.details) for a in audits)


async def test_tenant_isolation(client: httpx.AsyncClient) -> None:
    await register(client, "alice@example.com")
    pid = await _project(client, "Alice project")
    env = await _verified_env(client, pid)
    r = await client.post(f"/api/projects/{pid}/investigations", json={
        "environment_id": env["id"], "mode": "autonomous", "confirm_authorized": True})
    inv_id = r.json()["id"]
    async with session_scope() as s:
        inv = await s.get(Investigation, inv_id)
        ev = Evidence(org_id=inv.org_id, project_id=inv.project_id, investigation_id=inv.id, kind="screenshot",
                      label="x", storage_key="none.png", content_type="image/png", size_bytes=0, sha256="0" * 64)
        s.add(ev)
        await s.flush()
        ev_id = str(ev.id)
    await client.post("/api/auth/logout")

    await register(client, "mallory@example.com")
    assert (await client.get(f"/api/projects/{pid}")).status_code == 404
    assert (await client.get(f"/api/projects/{pid}/environments")).status_code == 404
    assert (await client.get(f"/api/investigations/{inv_id}")).status_code == 404
    assert (await client.get(f"/api/investigations/{inv_id}/events")).status_code == 404
    assert (await client.get(f"/api/evidence/{ev_id}")).status_code == 404
    assert (await client.post(f"/api/investigations/{inv_id}/stop")).status_code == 404
    assert (await client.get("/api/investigations")).json() == []
    assert (await client.get("/api/findings")).json() == []
    r = await client.post(f"/api/projects/{pid}/investigations", json={
        "environment_id": env["id"], "mode": "autonomous", "confirm_authorized": True})
    assert r.status_code == 404
    # Evidence content requires a valid signature, regardless of session.
    assert (await client.get(f"/api/evidence/{ev_id}/content?exp=9999999999&sig=forged")).status_code == 403


async def test_cross_origin_state_change_rejected(client: httpx.AsyncClient) -> None:
    await register(client)
    r = await client.post("/api/projects", json={"name": "x"}, headers={"Origin": "https://evil.example"})
    assert r.status_code == 403
    r = await client.post("/api/projects", json={"name": "x"}, headers={"Origin": "http://localhost:3000"})
    assert r.status_code == 201


async def test_overview_counts_are_real(client: httpx.AsyncClient) -> None:
    await register(client)
    data = (await client.get("/api/overview")).json()
    assert data["investigations"]["total"] == 0 and data["findings"]["total"] == 0 and data["projects"] == 0
    await _project(client)
    assert (await client.get("/api/overview")).json()["projects"] == 1


async def test_session_probe_never_fails(client: httpx.AsyncClient) -> None:
    r = await client.get("/api/auth/session")
    assert r.status_code == 200 and r.json() == {"authenticated": False, "user": None}
    await register(client, "probe@example.com")
    r = await client.get("/api/auth/session")
    assert r.status_code == 200 and r.json()["authenticated"] is True
    assert r.json()["user"]["email"] == "probe@example.com"


async def test_get_single_environment_is_tenant_scoped(client: httpx.AsyncClient) -> None:
    await register(client)
    pid = await _project(client)
    env = await _verified_env(client, pid)
    r = await client.get(f"/api/environments/{env['id']}")
    assert r.status_code == 200 and r.json()["origin"] == DEMO and r.json()["verification_status"] == "verified"
    await client.post("/api/auth/logout")
    await register(client, "intruder@example.com")
    assert (await client.get(f"/api/environments/{env['id']}")).status_code == 404


async def test_remove_website_only_without_investigations(client: httpx.AsyncClient) -> None:
    await register(client)
    pid = await _project(client)
    env = await _verified_env(client, pid)
    spare = (await client.post(f"/api/projects/{pid}/environments", json={"origin": "https://example.com"}))
    if spare.status_code == 201:  # requires DNS; skip that half offline
        assert (await client.delete(f"/api/environments/{spare.json()['id']}")).status_code == 204
        assert (await client.get(f"/api/environments/{spare.json()['id']}")).status_code == 404
    r = await client.post(f"/api/projects/{pid}/investigations", json={
        "environment_id": env["id"], "mode": "autonomous", "confirm_authorized": True, "config": {"viewports": ["desktop"]}})
    assert r.status_code == 201, r.text
    r = await client.delete(f"/api/environments/{env['id']}")
    assert r.status_code == 409 and "1 investigation" in r.text
    await client.post("/api/auth/logout")
    await register(client, "stranger@example.com")
    assert (await client.delete(f"/api/environments/{env['id']}")).status_code == 404
