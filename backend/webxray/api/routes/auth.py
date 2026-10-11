from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

import redis.asyncio as aioredis
from fastapi import APIRouter, HTTPException, Request, Response, status
from sqlalchemy import select

from webxray.api.deps import DB, SESSION_COOKIE, CurrentPrincipal, audit
from webxray.config import get_settings
from webxray.models import AuthSession, Membership, Organization, User
from webxray.schemas import LoginRequest, RegisterRequest, UserOut
from webxray.security.crypto import DUMMY_PASSWORD_HASH, hash_password, hash_token, new_session_token, verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])
log = logging.getLogger(__name__)

LOGIN_LIMIT = 10  # attempts per window per (ip, email)
LOGIN_WINDOW_S = 300


async def _rate_limited(key: str) -> bool:
    try:
        client = aioredis.from_url(get_settings().redis_url)
        async with client:
            n = await client.incr(key)
            if n == 1:
                await client.expire(key, LOGIN_WINDOW_S)
            return n > LOGIN_LIMIT
    except Exception as exc:  # fail open on Redis outage, but log it
        log.warning("rate limiter unavailable: %s", exc)
        return False


async def _issue_session(db: DB, response: Response, user: User) -> None:
    settings = get_settings()
    token = new_session_token()
    db.add(AuthSession(user_id=user.id, token_hash=hash_token(token),
                       expires_at=datetime.now(UTC) + timedelta(hours=settings.session_ttl_hours)))
    response.set_cookie(
        SESSION_COOKIE, token, httponly=True, secure=settings.cookie_secure, samesite="lax",
        max_age=settings.session_ttl_hours * 3600, path="/",
    )


def _user_out(user: User, org: Organization) -> UserOut:
    return UserOut(id=user.id, email=user.email, display_name=user.display_name,
                   organization_id=org.id, organization_name=org.name)


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def register(body: RegisterRequest, response: Response, db: DB) -> UserOut:
    email = body.email.lower()
    if await db.scalar(select(User.id).where(User.email == email)):
        raise HTTPException(status.HTTP_409_CONFLICT, "An account with this email already exists")
    user = User(email=email, display_name=body.display_name.strip() or email.split("@")[0],
                password_hash=hash_password(body.password))
    org = Organization(name=body.organization_name.strip() or f"{user.display_name}'s workspace")
    db.add_all([user, org])
    await db.flush()
    db.add(Membership(org_id=org.id, user_id=user.id, role="owner"))
    await _issue_session(db, response, user)
    await audit(db, None, "user.register", target_type="user", target_id=user.id, org_id=org.id, actor_user_id=user.id)
    return _user_out(user, org)


@router.post("/login", response_model=UserOut)
async def login(body: LoginRequest, request: Request, response: Response, db: DB) -> UserOut:
    email = body.email.lower()
    ip = request.client.host if request.client else "unknown"
    if await _rate_limited(f"webxray:login:{ip}:{email}"):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many sign-in attempts. Try again in a few minutes.")
    user = await db.scalar(select(User).where(User.email == email))
    ok = verify_password(user.password_hash if user else DUMMY_PASSWORD_HASH, body.password)
    if user is None or not ok:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Email or password is incorrect")
    membership = await db.scalar(select(Membership).where(Membership.user_id == user.id))
    assert membership is not None
    org = await db.get(Organization, membership.org_id)
    assert org is not None
    await _issue_session(db, response, user)
    await audit(db, None, "user.login", target_type="user", target_id=user.id, org_id=org.id, actor_user_id=user.id)
    return _user_out(user, org)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(principal: CurrentPrincipal, response: Response, db: DB) -> Response:
    sess = await db.get(AuthSession, principal.session_id)
    if sess is not None:
        sess.revoked_at = datetime.now(UTC)
    await audit(db, principal, "user.logout", target_type="user", target_id=principal.user.id)
    response.delete_cookie(SESSION_COOKIE, path="/")
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.get("/me", response_model=UserOut)
async def me(principal: CurrentPrincipal) -> UserOut:
    return _user_out(principal.user, principal.org)


@router.get("/session")
async def session(request: Request, db: DB) -> dict[str, object]:
    """Non-failing session probe for public pages: 200 whether or not the visitor is signed in."""
    from webxray.api.deps import current_principal

    try:
        principal = await current_principal(request, db)
    except HTTPException:
        return {"authenticated": False, "user": None}
    return {"authenticated": True, "user": _user_out(principal.user, principal.org).model_dump(mode="json")}
