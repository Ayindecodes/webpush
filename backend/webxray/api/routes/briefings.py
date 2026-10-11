"""Briefings: "send an agent to tell me what this website is".

A briefing only reads public pages (see webxray.worker.briefing for the safety
model), so it does not require a verified target. It is still limited per
organization so it cannot be used to hammer third-party sites.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, HTTPException, Query, Response, status
from sqlalchemy import delete, func, select

from webxray.api.deps import DB, CurrentPrincipal, audit, get_owned
from webxray.models import Briefing, Job
from webxray.schemas import BriefingCreate, BriefingOut
from webxray.security.crypto import TestAccountSecret, encrypt_credential, mask_username, sign_evidence_link, verify_evidence_link
from webxray.security.target_policy import TargetRejected, parse_origin, validate_target_origin
from webxray.services import jobs
from webxray.services.policy import egress_policy
from webxray.storage.artifacts import get_artifact_store

router = APIRouter(prefix="/api", tags=["briefings"])

ACTIVE = {"queued", "running"}
MAX_ACTIVE_PER_ORG = 2
MAX_PER_DAY_PER_ORG = 40


def _shot_token(briefing_id: uuid.UUID, index: int) -> str:
    return f"briefing-{briefing_id}-{index}"


def briefing_out(b: Briefing) -> BriefingOut:
    out = BriefingOut.model_validate(b)
    shots = []
    for i, shot in enumerate(b.shots or []):
        exp, sig = sign_evidence_link(_shot_token(b.id, i))
        shots.append({
            "url": f"/api/briefings/{b.id}/shots/{i}?exp={exp}&sig={sig}",
            "page_url": shot.get("url"), "title": shot.get("title"), "sha256": shot.get("sha256"),
            "signed_in": bool(shot.get("signed_in")),
        })
    out.shots = shots
    return out


@router.post("/briefings", response_model=BriefingOut, status_code=status.HTTP_201_CREATED)
async def create_briefing(body: BriefingCreate, principal: CurrentPrincipal, db: DB) -> BriefingOut:
    raw = body.url.strip()
    url = raw if "://" in raw else f"https://{raw}"
    try:
        origin, _ = await validate_target_origin(url, egress_policy())
    except TargetRejected as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, {"code": exc.code, "message": exc.reason}) from exc
    org_id = principal.org.id
    active = await db.scalar(
        select(func.count()).select_from(Briefing).where(Briefing.org_id == org_id, Briefing.status.in_(ACTIVE))
    )
    if (active or 0) >= MAX_ACTIVE_PER_ORG:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS,
                            f"{MAX_ACTIVE_PER_ORG} briefings are already running. Wait for one to finish.")
    since = datetime.now(UTC) - timedelta(days=1)
    recent = await db.scalar(
        select(func.count()).select_from(Briefing).where(Briefing.org_id == org_id, Briefing.created_at >= since)
    )
    if (recent or 0) >= MAX_PER_DAY_PER_ORG:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS,
                            f"Your workspace has used its {MAX_PER_DAY_PER_ORG} briefings for the last 24 hours.")
    b = Briefing(org_id=org_id, created_by=principal.user.id, url=url[:2048], origin=str(origin),
                 question=body.question.strip(), status="queued", steps=[], shots=[], result={})
    if body.login is not None:
        login_url = body.login.login_url.strip()
        if login_url:
            login_url = login_url if "://" in login_url else f"{origin}/{login_url.lstrip('/')}"
            try:
                same_site = parse_origin(login_url) == origin
            except TargetRejected:
                same_site = False
            if not same_site:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT,
                                    {"code": "login_url_off_site", "message": "The sign-in page must be on the same website."})
        username = body.login.username.strip()
        b.credential_ciphertext = encrypt_credential(TestAccountSecret(username, body.login.password))
        b.credential_hint = mask_username(username)
        b.login_url = login_url or None
        b.auth_status = "pending"
    db.add(b)
    await db.flush()
    await jobs.enqueue(db, "briefing", b.id)
    await audit(db, principal, "briefing.create", target_type="briefing", target_id=b.id,
                details={"origin": str(origin), "sign_in": body.login is not None})
    await db.commit()
    await db.refresh(b)
    await jobs.wake_workers()
    return briefing_out(b)


@router.get("/briefings", response_model=list[BriefingOut])
async def list_briefings(principal: CurrentPrincipal, db: DB, limit: int = Query(50, ge=1, le=200)) -> list[BriefingOut]:
    rows = (await db.scalars(
        select(Briefing).where(Briefing.org_id.in_(principal.org_ids)).order_by(Briefing.created_at.desc()).limit(limit)
    )).all()
    return [briefing_out(b) for b in rows]


@router.get("/briefings/{briefing_id}", response_model=BriefingOut)
async def get_briefing(briefing_id: uuid.UUID, principal: CurrentPrincipal, db: DB) -> BriefingOut:
    return briefing_out(await get_owned(db, Briefing, briefing_id, principal, "Briefing"))


@router.delete("/briefings/{briefing_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_briefing(briefing_id: uuid.UUID, principal: CurrentPrincipal, db: DB) -> Response:
    b = await get_owned(db, Briefing, briefing_id, principal, "Briefing")
    if b.status in ACTIVE:
        raise HTTPException(status.HTTP_409_CONFLICT, "This briefing is still running.")
    store = get_artifact_store()
    for shot in b.shots or []:
        store.delete(shot["key"])
    await db.execute(delete(Job).where(Job.ref_id == b.id, Job.kind == "briefing"))
    await db.delete(b)
    await audit(db, principal, "briefing.delete", target_type="briefing", target_id=briefing_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/briefings/{briefing_id}/shots/{index}")
async def briefing_shot(briefing_id: uuid.UUID, index: int, db: DB, exp: int, sig: str) -> Response:
    """Serve a screenshot through a short-lived signed link (issued only to members)."""
    if not verify_evidence_link(_shot_token(briefing_id, index), exp, sig):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Link is invalid or has expired")
    b = await db.get(Briefing, briefing_id)
    if b is None or not 0 <= index < len(b.shots or []):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Screenshot not found")
    data = get_artifact_store().get(b.shots[index]["key"])
    return Response(data, media_type="image/png", headers={
        "Cache-Control": "private, max-age=300", "X-Content-Type-Options": "nosniff",
        "Content-Security-Policy": "default-src 'none'; sandbox",
    })
