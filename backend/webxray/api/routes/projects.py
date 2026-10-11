from __future__ import annotations

import secrets
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import delete, func, select

from webxray.api.deps import DB, CurrentPrincipal, audit, get_owned
from webxray.models import CredentialSecret, Environment, Investigation, Project
from webxray.schemas import (
    CredentialCreate,
    CredentialOut,
    EnvironmentCreate,
    EnvironmentOut,
    ProjectCreate,
    ProjectOut,
    VerificationOut,
)
from webxray.security.crypto import TestAccountSecret, encrypt_credential, mask_username
from webxray.security.target_policy import TargetRejected, parse_origin, validate_target_origin
from webxray.services.verification import DNS_LABEL, WELL_KNOWN_PATH, verify_environment
from webxray.services.policy import egress_policy

router = APIRouter(prefix="/api", tags=["projects"])


async def _project_out(db: DB, p: Project) -> ProjectOut:
    envs = await db.scalar(select(func.count()).select_from(Environment).where(Environment.project_id == p.id))
    invs = await db.scalar(select(func.count()).select_from(Investigation).where(Investigation.project_id == p.id))
    return ProjectOut(id=p.id, name=p.name, created_at=p.created_at, environment_count=envs or 0, investigation_count=invs or 0)


@router.get("/projects", response_model=list[ProjectOut])
async def list_projects(principal: CurrentPrincipal, db: DB) -> list[ProjectOut]:
    rows = (await db.scalars(select(Project).where(Project.org_id.in_(principal.org_ids)).order_by(Project.created_at.desc()))).all()
    return [await _project_out(db, p) for p in rows]


@router.post("/projects", response_model=ProjectOut, status_code=status.HTTP_201_CREATED)
async def create_project(body: ProjectCreate, principal: CurrentPrincipal, db: DB) -> ProjectOut:
    p = Project(org_id=principal.org.id, name=body.name)
    db.add(p)
    await db.flush()
    await db.refresh(p)
    await audit(db, principal, "project.create", target_type="project", target_id=p.id, details={"name": p.name})
    return await _project_out(db, p)


@router.get("/projects/{project_id}", response_model=ProjectOut)
async def get_project(project_id: uuid.UUID, principal: CurrentPrincipal, db: DB) -> ProjectOut:
    p = await get_owned(db, Project, project_id, principal, "Project")
    return await _project_out(db, p)


# --------------------------------------------------------------------------- environments


@router.get("/projects/{project_id}/environments", response_model=list[EnvironmentOut])
async def list_environments(project_id: uuid.UUID, principal: CurrentPrincipal, db: DB) -> list[Environment]:
    await get_owned(db, Project, project_id, principal, "Project")
    return list((await db.scalars(select(Environment).where(Environment.project_id == project_id).order_by(Environment.created_at))).all())


@router.post("/projects/{project_id}/environments", response_model=EnvironmentOut, status_code=status.HTTP_201_CREATED)
async def create_environment(project_id: uuid.UUID, body: EnvironmentCreate, principal: CurrentPrincipal, db: DB) -> Environment:
    p = await get_owned(db, Project, project_id, principal, "Project")
    try:
        origin, _ = await validate_target_origin(body.origin, egress_policy())
    except TargetRejected as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, {"code": exc.code, "message": exc.reason}) from exc
    if await db.scalar(select(Environment.id).where(Environment.project_id == p.id, Environment.origin == str(origin))):
        raise HTTPException(status.HTTP_409_CONFLICT, "This target already exists in the project")
    env = Environment(org_id=p.org_id, project_id=p.id, origin=str(origin), label=body.label.strip(),
                      verification_token=secrets.token_hex(16))
    db.add(env)
    await db.flush()
    await db.refresh(env)
    await audit(db, principal, "environment.create", target_type="environment", target_id=env.id, details={"origin": env.origin})
    return env


@router.get("/environments/{environment_id}", response_model=EnvironmentOut)
async def get_environment(environment_id: uuid.UUID, principal: CurrentPrincipal, db: DB) -> Environment:
    return await get_owned(db, Environment, environment_id, principal, "Website")


@router.delete("/environments/{environment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_environment(environment_id: uuid.UUID, principal: CurrentPrincipal, db: DB) -> None:
    """Remove a website. Refused once it has investigations, so their history can't vanish by accident."""
    env = await get_owned(db, Environment, environment_id, principal, "Website")
    used = await db.scalar(select(func.count()).select_from(Investigation).where(Investigation.environment_id == env.id))
    if used:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            f"This website has {used} investigation{'s' if used != 1 else ''}, so it can't be removed.")
    await db.execute(delete(CredentialSecret).where(CredentialSecret.environment_id == env.id))
    await db.delete(env)
    await audit(db, principal, "environment.delete", target_type="environment", target_id=environment_id,
                details={"origin": env.origin})


@router.get("/environments/{environment_id}/verification-instructions")
async def verification_instructions(environment_id: uuid.UUID, principal: CurrentPrincipal, db: DB) -> dict[str, str]:
    env = await get_owned(db, Environment, environment_id, principal, "Environment")
    host = env.origin.split("://", 1)[1].split(":")[0]
    return {
        "http_file_url": f"{env.origin}{WELL_KNOWN_PATH}",
        "http_file_content": env.verification_token,
        "dns_txt_name": f"{DNS_LABEL}.{host}",
        "dns_txt_value": f"webxray-verification={env.verification_token}",
    }


@router.post("/environments/{environment_id}/verify", response_model=VerificationOut)
async def verify(environment_id: uuid.UUID, principal: CurrentPrincipal, db: DB) -> VerificationOut:
    env = await get_owned(db, Environment, environment_id, principal, "Environment")
    result = await verify_environment(parse_origin(env.origin), env.verification_token, egress_policy())
    if result.verified:
        env.verification_status = "verified"
        env.verification_method = result.method
        env.verified_at = datetime.now(UTC)
    await audit(db, principal, "environment.verify", target_type="environment", target_id=env.id,
                details={"verified": result.verified, "method": result.method, "detail": result.detail})
    await db.flush()
    await db.refresh(env)
    return VerificationOut(verified=result.verified, method=result.method, detail=result.detail,
                           environment=EnvironmentOut.model_validate(env))


# --------------------------------------------------------------------------- credentials


def _cred_out(c: CredentialSecret) -> CredentialOut:
    return CredentialOut(id=c.id, environment_id=c.environment_id, label=c.label, source=c.source,
                         username_hint=c.username_hint, lifecycle_state=c.lifecycle_state, created_at=c.created_at)


@router.get("/projects/{project_id}/credentials", response_model=list[CredentialOut])
async def list_credentials(project_id: uuid.UUID, principal: CurrentPrincipal, db: DB) -> list[CredentialOut]:
    await get_owned(db, Project, project_id, principal, "Project")
    rows = (await db.scalars(select(CredentialSecret).where(CredentialSecret.project_id == project_id)
                             .order_by(CredentialSecret.created_at.desc()))).all()
    return [_cred_out(c) for c in rows]


@router.post("/projects/{project_id}/credentials", response_model=CredentialOut, status_code=status.HTTP_201_CREATED)
async def create_credential(project_id: uuid.UUID, body: CredentialCreate, principal: CurrentPrincipal, db: DB) -> CredentialOut:
    p = await get_owned(db, Project, project_id, principal, "Project")
    env = await get_owned(db, Environment, body.environment_id, principal, "Environment")
    if env.project_id != p.id:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Environment belongs to a different project")
    cred = CredentialSecret(
        org_id=p.org_id, project_id=p.id, environment_id=env.id, label=body.label.strip(), source="user_supplied",
        username_hint=mask_username(body.username), lifecycle_state="active",
        ciphertext=encrypt_credential(TestAccountSecret(body.username, body.password)),
    )
    db.add(cred)
    await db.flush()
    await db.refresh(cred)
    # Never include the username or password in audit details.
    await audit(db, principal, "credential.create", target_type="credential", target_id=cred.id, details={"label": cred.label})
    return _cred_out(cred)


@router.delete("/credentials/{credential_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_credential(credential_id: uuid.UUID, principal: CurrentPrincipal, db: DB) -> None:
    cred = await get_owned(db, CredentialSecret, credential_id, principal, "Credential")
    await db.delete(cred)
    await audit(db, principal, "credential.delete", target_type="credential", target_id=credential_id)
