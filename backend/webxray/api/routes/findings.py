from __future__ import annotations

import hashlib
import uuid
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Response, status
from sqlalchemy import or_, select

from webxray.api.deps import DB, CurrentPrincipal, audit, get_owned
from webxray.models import Environment, Evidence, Finding, FindingEvidence, Investigation, ReproductionTest, TestRun
from webxray.schemas import EvidenceOut, FindingOut, TestOut, TestRunOut
from webxray.security.crypto import sign_evidence_link, verify_evidence_link
from webxray.services import jobs
from webxray.storage.artifacts import get_artifact_store

router = APIRouter(prefix="/api", tags=["findings"])

SEVERITY_RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}
CLASS_RANK = {"confirmed_defect": 0, "warning": 1, "observation": 2}


def severity_order(f: FindingOut) -> tuple[int, int, str]:
    return (CLASS_RANK.get(f.classification, 9), SEVERITY_RANK.get(f.severity, 9), f.title)


async def finding_out(db: DB, f: Finding) -> FindingOut:
    out = FindingOut.model_validate(f)
    inv = await db.get(Investigation, f.investigation_id)
    if inv:
        env = await db.get(Environment, inv.environment_id)
        out.origin = env.origin if env else None
    test = await db.scalar(select(ReproductionTest).where(ReproductionTest.finding_id == f.id)
                           .order_by(ReproductionTest.created_at.desc()).limit(1))
    if test:
        out.test_status, out.test_id = test.verification_status, test.id
    return out


def evidence_out(e: Evidence, role: str | None = None) -> EvidenceOut:
    exp, sig = sign_evidence_link(str(e.id))
    return EvidenceOut(
        id=e.id, kind=e.kind, label=e.label, content_type=e.content_type, size_bytes=e.size_bytes, sha256=e.sha256,
        meta=e.meta, redactions=e.redactions, event_seq=e.event_seq, browser_run_id=e.browser_run_id,
        created_at=e.created_at, role=role, url=f"/api/evidence/{e.id}/content?exp={exp}&sig={sig}", url_expires_at=exp,
    )


@router.get("/findings", response_model=list[FindingOut])
async def list_findings(
    principal: CurrentPrincipal, db: DB,
    q: str | None = Query(None, max_length=200),
    severity: list[str] = Query(default_factory=list),
    classification: list[str] = Query(default_factory=list),
    project_id: uuid.UUID | None = None,
    investigation_id: uuid.UUID | None = None,
    limit: int = Query(200, ge=1, le=500),
) -> list[FindingOut]:
    stmt = select(Finding).where(Finding.org_id.in_(principal.org_ids))
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(Finding.title.ilike(like), Finding.summary.ilike(like)))
    if severity:
        stmt = stmt.where(Finding.severity.in_(severity))
    if classification:
        stmt = stmt.where(Finding.classification.in_(classification))
    if project_id:
        stmt = stmt.where(Finding.project_id == project_id)
    if investigation_id:
        stmt = stmt.where(Finding.investigation_id == investigation_id)
    rows = (await db.scalars(stmt.order_by(Finding.created_at.desc()).limit(limit))).all()
    return [await finding_out(db, f) for f in rows]


@router.get("/findings/{finding_id}", response_model=FindingOut)
async def get_finding(finding_id: uuid.UUID, principal: CurrentPrincipal, db: DB) -> FindingOut:
    f = await get_owned(db, Finding, finding_id, principal, "Finding")
    return await finding_out(db, f)


@router.get("/findings/{finding_id}/evidence", response_model=list[EvidenceOut])
async def finding_evidence(finding_id: uuid.UUID, principal: CurrentPrincipal, db: DB) -> list[EvidenceOut]:
    f = await get_owned(db, Finding, finding_id, principal, "Finding")
    rows = (await db.execute(
        select(Evidence, FindingEvidence.role).join(FindingEvidence, FindingEvidence.evidence_id == Evidence.id)
        .where(FindingEvidence.finding_id == f.id, Evidence.org_id.in_(principal.org_ids)).order_by(Evidence.created_at)
    )).all()
    return [evidence_out(e, role) for e, role in rows]


@router.get("/investigations/{investigation_id}/evidence", response_model=list[EvidenceOut])
async def investigation_evidence(
    investigation_id: uuid.UUID, principal: CurrentPrincipal, db: DB, kind: str | None = None,
    ids: list[uuid.UUID] = Query(default_factory=list),
) -> list[EvidenceOut]:
    await get_owned(db, Investigation, investigation_id, principal, "Investigation")
    stmt = select(Evidence).where(Evidence.investigation_id == investigation_id)
    if kind:
        stmt = stmt.where(Evidence.kind == kind)
    if ids:
        stmt = stmt.where(Evidence.id.in_(ids))
    rows = (await db.scalars(stmt.order_by(Evidence.created_at).limit(1000))).all()
    return [evidence_out(e) for e in rows]


@router.get("/evidence/{evidence_id}", response_model=EvidenceOut)
async def get_evidence(evidence_id: uuid.UUID, principal: CurrentPrincipal, db: DB) -> EvidenceOut:
    e = await get_owned(db, Evidence, evidence_id, principal, "Evidence")
    return evidence_out(e)


@router.get("/evidence/{evidence_id}/content")
async def evidence_content(evidence_id: uuid.UUID, db: DB, exp: int, sig: str) -> Response:
    """Serve an artifact through a short-lived signed link (issued only to authorized users)."""
    if not verify_evidence_link(str(evidence_id), exp, sig):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Evidence link is invalid or has expired")
    e = await db.get(Evidence, evidence_id)
    if e is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Evidence not found")
    data = get_artifact_store().get(e.storage_key)
    ctype = e.content_type
    # Captured page content is untrusted: never let the browser render it as HTML here.
    if not (ctype.startswith("image/") or ctype.startswith("application/json")):
        ctype = "text/plain; charset=utf-8"
    return Response(data, media_type=ctype, headers={
        "Cache-Control": "private, max-age=300",
        "X-Content-Type-Options": "nosniff",
        "Content-Security-Policy": "default-src 'none'; sandbox",
        "X-WebXray-SHA256": e.sha256,
    })


# --------------------------------------------------------------------------- tests


async def test_out(db: DB, t: ReproductionTest) -> TestOut:
    out = TestOut.model_validate(t)
    runs = (await db.scalars(select(TestRun).where(TestRun.test_id == t.id).order_by(TestRun.created_at.desc()))).all()
    out.runs = [TestRunOut.model_validate(r) for r in runs]
    return out


@router.post("/findings/{finding_id}/reproduce", response_model=TestOut)
async def reproduce(finding_id: uuid.UUID, principal: CurrentPrincipal, db: DB) -> TestOut:
    """Return the finding's reproduction test. Tests are generated by the worker from
    recorded journey evidence; findings without a recorded journey cannot have one."""
    f = await get_owned(db, Finding, finding_id, principal, "Finding")
    t = await db.scalar(select(ReproductionTest).where(ReproductionTest.finding_id == f.id)
                        .order_by(ReproductionTest.created_at.desc()).limit(1))
    if t is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT,
                            "No reproduction test exists for this finding. Tests are generated for journey failures "
                            "with a recorded login flow; page-level observations do not have one.")
    return await test_out(db, t)


@router.get("/tests/{test_id}", response_model=TestOut)
async def get_test(test_id: uuid.UUID, principal: CurrentPrincipal, db: DB) -> TestOut:
    t = await get_owned(db, ReproductionTest, test_id, principal, "Test")
    return await test_out(db, t)


@router.get("/tests/{test_id}/download")
async def download_test(test_id: uuid.UUID, principal: CurrentPrincipal, db: DB) -> Response:
    t = await get_owned(db, ReproductionTest, test_id, principal, "Test")
    return Response(t.source, media_type="text/plain; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{t.filename}"'})


@router.post("/tests/{test_id}/verify", response_model=TestRunOut, status_code=status.HTTP_202_ACCEPTED)
async def verify_test(test_id: uuid.UUID, principal: CurrentPrincipal, db: DB) -> Any:
    t = await get_owned(db, ReproductionTest, test_id, principal, "Test")
    pending = await db.scalar(select(TestRun.id).where(TestRun.test_id == t.id, TestRun.status.in_(["queued", "running"])))
    if pending:
        raise HTTPException(status.HTTP_409_CONFLICT, "A run of this test is already queued or running")
    run = TestRun(org_id=t.org_id, project_id=t.project_id, test_id=t.id, requested_by=principal.user.id,
                  status="queued", source_sha256=hashlib.sha256(t.source.encode()).hexdigest())
    db.add(run)
    await db.flush()
    await jobs.enqueue(db, "test_run", run.id, max_attempts=2)
    await audit(db, principal, "test.verify", target_type="test", target_id=t.id, details={"run_id": str(run.id)})
    await db.flush()
    await db.refresh(run)
    out = TestRunOut.model_validate(run)
    await db.commit()
    await jobs.wake_workers()
    return out
