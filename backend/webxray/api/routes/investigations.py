from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Response, status
from sqlalchemy import func, select

from webxray.api.deps import DB, CurrentPrincipal, audit, get_owned
from webxray.models import (
    Approval,
    BrowserRun,
    CredentialSecret,
    Environment,
    Event,
    Feature,
    Finding,
    Investigation,
    Journey,
    Page,
    Project,
    ReproductionTest,
)
from webxray.schemas import (
    EventOut,
    FeatureOut,
    FindingOut,
    InvestigationCreate,
    InvestigationOut,
    JourneyOut,
    PageOut,
    RunOut,
)
from webxray.services import jobs
from webxray.services.reports import build_report, report_markdown

router = APIRouter(prefix="/api", tags=["investigations"])

ACTIVE = {"queued", "running", "paused", "awaiting_human"}


async def investigation_out(db: DB, inv: Investigation) -> InvestigationOut:
    out = InvestigationOut.model_validate(inv)
    env = await db.get(Environment, inv.environment_id)
    proj = await db.get(Project, inv.project_id)
    out.origin = env.origin if env else None
    out.project_name = proj.name if proj else None
    counts = (await db.execute(
        select(Finding.classification, func.count()).where(Finding.investigation_id == inv.id).group_by(Finding.classification)
    )).all()
    out.finding_counts = {k: v for k, v in counts}
    out.page_count = await db.scalar(select(func.count()).select_from(Page).where(Page.investigation_id == inv.id)) or 0
    return out


@router.post("/projects/{project_id}/investigations", response_model=InvestigationOut, status_code=status.HTTP_201_CREATED)
async def create_investigation(project_id: uuid.UUID, body: InvestigationCreate, principal: CurrentPrincipal, db: DB) -> InvestigationOut:
    project = await get_owned(db, Project, project_id, principal, "Project")
    env = await get_owned(db, Environment, body.environment_id, principal, "Environment")
    if env.project_id != project.id:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Target belongs to a different project")
    if env.verification_status != "verified":
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT,
                            "Verify that you control this target before investigating it.")
    if body.credential_id is not None:
        cred = await get_owned(db, CredentialSecret, body.credential_id, principal, "Credential")
        if cred.environment_id != env.id:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Credential belongs to a different target")
    running = await db.scalar(select(func.count()).select_from(Investigation).where(
        Investigation.environment_id == env.id, Investigation.status.in_(ACTIVE)))
    if running:
        raise HTTPException(status.HTTP_409_CONFLICT, "An investigation is already active for this target")

    inv = Investigation(
        org_id=project.org_id, project_id=project.id, environment_id=env.id, created_by=principal.user.id,
        credential_id=body.credential_id, mode=body.mode, goal=body.goal.strip(), config=body.config.model_dump(),
        status="queued", phase="queued",
    )
    db.add(inv)
    await db.flush()
    approvals = [("scan_authorization", f"{principal.user.email} confirmed they are authorized to test {env.origin}.")]
    if body.config.allow_registration:
        approvals.append(("account_registration", f"Approved creating one designated test account on {env.origin}."))
    if body.config.allow_order_submission:
        approvals.append(("order_submission", f"Confirmed {env.origin} uses sandbox payments; approved submitting test orders."))
    for kind, statement in approvals:
        db.add(Approval(org_id=project.org_id, project_id=project.id, investigation_id=inv.id, kind=kind,
                        granted_by=principal.user.id, statement=statement))
    await jobs.enqueue(db, "investigation", inv.id, max_attempts=2)
    await audit(db, principal, "investigation.create", target_type="investigation", target_id=inv.id,
                details={"origin": env.origin, "mode": body.mode, "approvals": [k for k, _ in approvals]})
    await db.flush()
    await db.refresh(inv)
    await db.commit()
    await jobs.wake_workers()
    return await investigation_out(db, inv)


@router.get("/investigations", response_model=list[InvestigationOut])
async def list_investigations(
    principal: CurrentPrincipal, db: DB, project_id: uuid.UUID | None = None, limit: int = Query(50, ge=1, le=200)
) -> list[InvestigationOut]:
    q = select(Investigation).where(Investigation.org_id.in_(principal.org_ids))
    if project_id:
        q = q.where(Investigation.project_id == project_id)
    rows = (await db.scalars(q.order_by(Investigation.created_at.desc()).limit(limit))).all()
    return [await investigation_out(db, i) for i in rows]


@router.get("/investigations/{investigation_id}", response_model=InvestigationOut)
async def get_investigation(investigation_id: uuid.UUID, principal: CurrentPrincipal, db: DB) -> InvestigationOut:
    inv = await get_owned(db, Investigation, investigation_id, principal, "Investigation")
    return await investigation_out(db, inv)


async def _control(investigation_id: uuid.UUID, principal: CurrentPrincipal, db: DB, action: str) -> InvestigationOut:
    inv = await get_owned(db, Investigation, investigation_id, principal, "Investigation")
    if inv.status not in ACTIVE:
        raise HTTPException(status.HTTP_409_CONFLICT, f"Investigation is {inv.status}; it can no longer be {action}d")
    if action == "pause":
        if inv.status not in {"running", "queued"}:
            raise HTTPException(status.HTTP_409_CONFLICT, f"Cannot pause an investigation that is {inv.status}")
        inv.requested_control = "pause"
    elif action == "resume":
        if inv.requested_control != "pause":
            raise HTTPException(status.HTTP_409_CONFLICT, "Investigation is not paused")
        inv.requested_control = "none"
    else:
        inv.requested_control = "stop"
        if inv.status == "queued":
            # Never picked up by a worker: stop immediately.
            inv.status = "stopped"
    await audit(db, principal, f"investigation.{action}", target_type="investigation", target_id=inv.id)
    await db.flush()
    await db.refresh(inv)
    return await investigation_out(db, inv)


@router.post("/investigations/{investigation_id}/pause", response_model=InvestigationOut)
async def pause(investigation_id: uuid.UUID, principal: CurrentPrincipal, db: DB) -> InvestigationOut:
    return await _control(investigation_id, principal, db, "pause")


@router.post("/investigations/{investigation_id}/resume", response_model=InvestigationOut)
async def resume(investigation_id: uuid.UUID, principal: CurrentPrincipal, db: DB) -> InvestigationOut:
    return await _control(investigation_id, principal, db, "resume")


@router.post("/investigations/{investigation_id}/stop", response_model=InvestigationOut)
async def stop(investigation_id: uuid.UUID, principal: CurrentPrincipal, db: DB) -> InvestigationOut:
    return await _control(investigation_id, principal, db, "stop")


@router.get("/investigations/{investigation_id}/events", response_model=list[EventOut])
async def events(
    investigation_id: uuid.UUID, principal: CurrentPrincipal, db: DB,
    after: int = Query(0, ge=0), limit: int = Query(500, ge=1, le=2000),
) -> list[Event]:
    await get_owned(db, Investigation, investigation_id, principal, "Investigation")
    q = select(Event).where(Event.investigation_id == investigation_id, Event.seq > after).order_by(Event.seq).limit(limit)
    return list((await db.scalars(q)).all())


@router.get("/investigations/{investigation_id}/pages", response_model=list[PageOut])
async def pages(investigation_id: uuid.UUID, principal: CurrentPrincipal, db: DB) -> list[Page]:
    await get_owned(db, Investigation, investigation_id, principal, "Investigation")
    return list((await db.scalars(select(Page).where(Page.investigation_id == investigation_id).order_by(Page.created_at))).all())


@router.get("/investigations/{investigation_id}/features", response_model=list[FeatureOut])
async def features(investigation_id: uuid.UUID, principal: CurrentPrincipal, db: DB) -> list[Feature]:
    await get_owned(db, Investigation, investigation_id, principal, "Investigation")
    return list((await db.scalars(select(Feature).where(Feature.investigation_id == investigation_id).order_by(Feature.name))).all())


async def journey_out(db: DB, j: Journey) -> JourneyOut:
    out = JourneyOut.model_validate(j)
    runs = (await db.scalars(select(BrowserRun).where(BrowserRun.journey_id == j.id).order_by(BrowserRun.started_at))).all()
    out.runs = [RunOut.model_validate(r) for r in runs]
    inv = await db.get(Investigation, j.investigation_id)
    if inv:
        env = await db.get(Environment, inv.environment_id)
        proj = await db.get(Project, inv.project_id)
        out.origin = env.origin if env else None
        out.project_name = proj.name if proj else None
    return out


@router.get("/investigations/{investigation_id}/journeys", response_model=list[JourneyOut])
async def journeys(investigation_id: uuid.UUID, principal: CurrentPrincipal, db: DB) -> list[JourneyOut]:
    await get_owned(db, Investigation, investigation_id, principal, "Investigation")
    rows = (await db.scalars(select(Journey).where(Journey.investigation_id == investigation_id))).all()
    return [await journey_out(db, j) for j in rows]


@router.get("/journeys", response_model=list[JourneyOut])
async def all_journeys(principal: CurrentPrincipal, db: DB, limit: int = Query(50, ge=1, le=200)) -> list[JourneyOut]:
    rows = (await db.scalars(select(Journey).where(Journey.org_id.in_(principal.org_ids))
                             .order_by(Journey.created_at.desc()).limit(limit))).all()
    return [await journey_out(db, j) for j in rows]


@router.get("/investigations/{investigation_id}/findings", response_model=list[FindingOut])
async def investigation_findings(investigation_id: uuid.UUID, principal: CurrentPrincipal, db: DB) -> list[FindingOut]:
    await get_owned(db, Investigation, investigation_id, principal, "Investigation")
    from webxray.api.routes.findings import finding_out, severity_order

    rows = (await db.scalars(select(Finding).where(Finding.investigation_id == investigation_id))).all()
    return sorted([await finding_out(db, f) for f in rows], key=severity_order)


@router.get("/investigations/{investigation_id}/report")
async def report(
    investigation_id: uuid.UUID, principal: CurrentPrincipal, db: DB, format: str = Query("json", pattern="^(json|markdown)$")
) -> Any:
    inv = await get_owned(db, Investigation, investigation_id, principal, "Investigation")
    data = await build_report(db, inv)
    if format == "markdown":
        return Response(report_markdown(data), media_type="text/markdown; charset=utf-8",
                        headers={"Content-Disposition": f'attachment; filename="webxray-report-{str(inv.id)[:8]}.md"'})
    return data


@router.get("/overview")
async def overview(principal: CurrentPrincipal, db: DB) -> dict[str, Any]:
    orgs = principal.org_ids
    inv_status = dict((await db.execute(select(Investigation.status, func.count()).where(Investigation.org_id.in_(orgs))
                                        .group_by(Investigation.status))).all())
    sev = dict((await db.execute(select(Finding.severity, func.count()).where(Finding.org_id.in_(orgs))
                                 .group_by(Finding.severity))).all())
    cls = dict((await db.execute(select(Finding.classification, func.count()).where(Finding.org_id.in_(orgs))
                                 .group_by(Finding.classification))).all())
    tests = dict((await db.execute(select(ReproductionTest.verification_status, func.count())
                                   .where(ReproductionTest.org_id.in_(orgs)).group_by(ReproductionTest.verification_status))).all())
    pages = await db.scalar(select(func.count()).select_from(Page).where(Page.org_id.in_(orgs))) or 0
    feats = dict((await db.execute(select(Feature.status, func.count()).where(Feature.org_id.in_(orgs))
                                   .group_by(Feature.status))).all())
    runs = dict((await db.execute(select(BrowserRun.status, func.count()).where(BrowserRun.org_id.in_(orgs))
                                  .group_by(BrowserRun.status))).all())
    projects = await db.scalar(select(func.count()).select_from(Project).where(Project.org_id.in_(orgs))) or 0
    envs = await db.scalar(select(func.count()).select_from(Environment).where(Environment.org_id.in_(orgs))) or 0
    return {
        "projects": projects, "environments": envs,
        "investigations": {"total": sum(inv_status.values()), "by_status": inv_status},
        "findings": {"total": sum(sev.values()), "by_severity": sev, "by_classification": cls},
        "tests": {"total": sum(tests.values()), "by_status": tests},
        "pages_discovered": pages, "features": feats, "journey_runs": runs,
    }


ACTIVITY_LABELS = {
    "user.register": "created the workspace",
    "project.create": "created project",
    "environment.create": "added website",
    "environment.verify": "checked ownership of a website:",
    "environment.delete": "removed website",
    "credential.create": "saved a test account",
    "credential.delete": "deleted a test account",
    "investigation.create": "started an investigation on",
    "investigation.pause": "paused an investigation",
    "investigation.resume": "resumed an investigation",
    "investigation.stop": "stopped an investigation",
    "test.verify": "re-ran a test",
    "briefing.create": "asked for a briefing on",
    "briefing.delete": "deleted a briefing",
}
VERIFY_METHODS = {"http_file": "verification file", "dns_txt": "DNS record", "operator_allowlist": "workspace allowlist"}
HIDDEN_ACTIONS = ("user.login", "user.logout")


@router.get("/activity")
async def activity(principal: CurrentPrincipal, db: DB, limit: int = Query(15, ge=1, le=100)) -> list[dict[str, Any]]:
    """Recent audited actions in the caller's organizations (real audit records only)."""
    from webxray.models import AuditLog, User

    rows = (await db.execute(
        select(AuditLog, User.email).outerjoin(User, User.id == AuditLog.actor_user_id)
        .where(AuditLog.org_id.in_(principal.org_ids), AuditLog.action.not_in(HIDDEN_ACTIONS))
        .order_by(AuditLog.ts.desc()).limit(limit)
    )).all()
    out = []
    for log, email in rows:
        detail = log.details or {}
        subject = detail.get("origin") or detail.get("name") or detail.get("label") or ""
        if log.action == "environment.verify":
            method = VERIFY_METHODS.get(detail.get("method") or "", detail.get("method") or "")
            subject = ("confirmed" if detail.get("verified") else "not confirmed yet") + (f" (by {method})" if method else "")
        out.append({
            "id": log.id, "ts": log.ts.isoformat(), "actor": email or "system", "action": log.action,
            "label": ACTIVITY_LABELS.get(log.action, log.action.replace(".", " ").replace("_", " ")), "subject": subject,
            "target_type": log.target_type, "target_id": log.target_id,
        })
    return out
