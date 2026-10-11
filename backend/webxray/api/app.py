"""FastAPI application (control plane).

Run:  uvicorn webxray.api.app:app --port 8000
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy import text

from webxray.api.routes import auth, briefings, findings, investigations, projects
from webxray.config import get_settings
from webxray.db import dispose_engine, sessionmaker
from webxray.logging_setup import configure_logging

log = logging.getLogger("webxray.api")
UNSAFE = {"POST", "PUT", "PATCH", "DELETE"}


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    configure_logging(get_settings().log_level)
    yield
    await dispose_engine()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="WEB X-RAY API", version="0.1.0", lifespan=lifespan,
        docs_url="/api/docs" if settings.environment != "production" else None, openapi_url="/api/openapi.json",
    )

    @app.middleware("http")
    async def security_middleware(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        request_id = request.headers.get("x-request-id") or uuid.uuid4().hex[:16]
        # CSRF defence in depth (cookies are also SameSite=Lax): state-changing requests
        # must come from an allowed web origin when the browser declares one.
        if request.method in UNSAFE:
            origin = request.headers.get("origin")
            if origin is not None and origin not in settings.allowed_web_origins:
                return JSONResponse({"detail": "Cross-origin request rejected"}, status_code=403)
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault("X-Frame-Options", "DENY")
        if request.url.path.startswith("/api/") and "Cache-Control" not in response.headers:
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.exception_handler(RequestValidationError)
    async def validation_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        errors = [
            {"loc": [str(x) for x in e.get("loc", [])], "msg": str(e.get("msg", "")).removeprefix("Value error, ")}
            for e in exc.errors()
        ]
        return JSONResponse({"detail": errors}, status_code=422)

    @app.get("/api/health")
    async def health() -> dict[str, object]:
        db_ok = True
        try:
            async with sessionmaker()() as s:
                await s.execute(text("select 1"))
        except Exception:
            db_ok = False
        return {"ok": db_ok, "database": db_ok}

    @app.get("/api/system/workers")
    async def workers(request: Request) -> dict[str, object]:
        """How many job workers are alive (signed-in users only; no worker details are exposed)."""
        from webxray.api.deps import current_principal
        from webxray.db import sessionmaker as _sm

        async with _sm()() as db:
            await current_principal(request, db)
        import redis.asyncio as aioredis

        try:
            client = aioredis.from_url(settings.redis_url)
            async with client:
                count = 0
                async for _ in client.scan_iter(match="webxray:worker:*", count=100):
                    count += 1
            return {"available": count > 0, "count": count, "known": True}
        except Exception:
            return {"available": None, "count": None, "known": False}

    for r in (auth.router, projects.router, investigations.router, findings.router, briefings.router):
        app.include_router(r)
    return app


app = create_app()
