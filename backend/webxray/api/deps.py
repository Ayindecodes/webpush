from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from webxray.db import sessionmaker
from webxray.models import AuditLog, AuthSession, Membership, Organization, User
from webxray.security.crypto import hash_token

SESSION_COOKIE = "wx_session"


async def get_db() -> AsyncIterator[AsyncSession]:
    async with sessionmaker()() as session:
        try:
            yield session
            await session.commit()
        except BaseException:
            await session.rollback()
            raise


DB = Annotated[AsyncSession, Depends(get_db)]


@dataclass
class Principal:
    user: User
    org: Organization
    org_ids: set[uuid.UUID]
    session_id: uuid.UUID


async def current_principal(request: Request, db: DB) -> Principal:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not signed in")
    sess = await db.scalar(select(AuthSession).where(AuthSession.token_hash == hash_token(token)))
    if sess is None or sess.revoked_at is not None or sess.expires_at < datetime.now(UTC):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session expired")
    user = await db.get(User, sess.user_id)
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session expired")
    memberships = (await db.scalars(select(Membership).where(Membership.user_id == user.id))).all()
    if not memberships:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "No organization membership")
    org = await db.get(Organization, memberships[0].org_id)
    assert org is not None
    return Principal(user=user, org=org, org_ids={m.org_id for m in memberships}, session_id=sess.id)


CurrentPrincipal = Annotated[Principal, Depends(current_principal)]


def not_found(what: str = "Resource") -> HTTPException:
    # 404 (not 403) for other tenants' resources so existence is not disclosed.
    return HTTPException(status.HTTP_404_NOT_FOUND, f"{what} not found")


async def get_owned(db: AsyncSession, model: Any, obj_id: uuid.UUID, principal: Principal, what: str) -> Any:
    obj = await db.get(model, obj_id)
    if obj is None or getattr(obj, "org_id", None) not in principal.org_ids:
        raise not_found(what)
    return obj


async def audit(
    db: AsyncSession,
    principal: Principal | None,
    action: str,
    *,
    target_type: str | None = None,
    target_id: Any = None,
    details: dict[str, Any] | None = None,
    org_id: uuid.UUID | None = None,
    actor_user_id: uuid.UUID | None = None,
) -> None:
    db.add(
        AuditLog(
            org_id=org_id or (principal.org.id if principal else None),
            actor_user_id=principal.user.id if principal else actor_user_id,
            action=action,
            target_type=target_type,
            target_id=str(target_id) if target_id is not None else None,
            details=details or {},
        )
    )
