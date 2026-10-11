from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from collections.abc import AsyncIterator
from pathlib import Path

import pytest

# Configure before any webxray module reads settings.
_TMP = Path(tempfile.mkdtemp(prefix="webxray-test-"))
os.environ.update({
    "WEBXRAY_ENVIRONMENT": "test",
    "WEBXRAY_DATABASE_URL": os.environ.get(
        "WEBXRAY_TEST_DATABASE_URL", "postgresql+asyncpg://webxray:webxray_dev_password@127.0.0.1:55432/webxray_test"
    ),
    "WEBXRAY_ARTIFACT_DIR": str(_TMP / "artifacts"),
    "WEBXRAY_ALLOWED_PRIVATE_ORIGINS": os.environ.get("WEBXRAY_TEST_DEMO_ORIGIN", "http://127.0.0.1:4100"),
    "WEBXRAY_LOG_LEVEL": "WARNING",
})

import httpx  # noqa: E402
from sqlalchemy import text  # noqa: E402

from webxray.db import Base, dispose_engine, session_scope  # noqa: E402

BACKEND = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session", autouse=True)
def migrated_database() -> None:
    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=BACKEND, check=True, env=os.environ.copy(),
                   capture_output=True)


@pytest.fixture(autouse=True)
async def clean_tables() -> AsyncIterator[None]:
    from webxray import models  # noqa: F401

    names = ", ".join(t.name for t in reversed(Base.metadata.sorted_tables))
    async with session_scope() as s:
        await s.execute(text(f"TRUNCATE {names} RESTART IDENTITY CASCADE"))
    yield


@pytest.fixture(scope="session", autouse=True)
async def _dispose() -> AsyncIterator[None]:
    yield
    await dispose_engine()


@pytest.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    from webxray.api.app import app

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as c:
        yield c


async def register(client: httpx.AsyncClient, email: str = "dev@example.com", password: str = "correct-horse-battery") -> dict:
    r = await client.post("/api/auth/register", json={"email": email, "password": password, "organization_name": email})
    assert r.status_code == 201, r.text
    return r.json()
