"""Durable job queue.

Postgres holds job state (so a crashed worker or Redis restart never loses
work); Redis is only a wake-up signal so idle workers react immediately.
Claiming uses ``FOR UPDATE SKIP LOCKED`` and a lease that the worker renews.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta

import redis.asyncio as aioredis
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from webxray.config import get_settings
from webxray.db import session_scope
from webxray.models import Briefing, Investigation, Job

log = logging.getLogger(__name__)

WAKE_KEY = "webxray:jobs:wake"


def _now() -> datetime:
    return datetime.now(UTC)


async def enqueue(s: AsyncSession, kind: str, ref_id: uuid.UUID, *, max_attempts: int = 2) -> Job:
    job = Job(kind=kind, ref_id=ref_id, status="queued", max_attempts=max_attempts)
    s.add(job)
    await s.flush()
    return job


async def wake_workers() -> None:
    try:
        client = aioredis.from_url(get_settings().redis_url)
        async with client:
            await client.lpush(WAKE_KEY, "1")
            await client.ltrim(WAKE_KEY, 0, 100)
    except Exception as exc:  # Redis is an optimization; workers also poll.
        log.warning("could not signal workers via Redis: %s", exc)


async def claim(worker_id: str) -> Job | None:
    lease = get_settings().worker_lease_seconds
    async with session_scope() as s:
        job = await s.scalar(
            select(Job)
            .where(Job.status == "queued", Job.run_after <= _now())
            .order_by(Job.created_at)
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        if job is None:
            return None
        job.status = "running"
        job.attempts += 1
        job.locked_by = worker_id
        job.lease_expires_at = _now() + timedelta(seconds=lease)
        return job


async def heartbeat(job_id: uuid.UUID, worker_id: str) -> bool:
    lease = get_settings().worker_lease_seconds
    async with session_scope() as s:
        result = await s.execute(
            update(Job)
            .where(Job.id == job_id, Job.locked_by == worker_id, Job.status == "running")
            .values(lease_expires_at=_now() + timedelta(seconds=lease))
        )
        return bool(result.rowcount)  # type: ignore[attr-defined]


async def complete(job_id: uuid.UUID, *, error: str | None = None) -> None:
    async with session_scope() as s:
        await s.execute(
            update(Job)
            .where(Job.id == job_id)
            .values(status="failed" if error else "succeeded", last_error=error, lease_expires_at=None)
        )


async def recover_expired() -> int:
    """Requeue or fail jobs whose worker stopped renewing its lease.

    An investigation that already performed a consequential action (e.g.
    submitted a registration form) is *not* retried automatically — repeating
    it could create duplicate accounts. It is marked failed with an explanation.
    """
    recovered = 0
    async with session_scope() as s:
        jobs = (
            await s.scalars(
                select(Job).where(Job.status == "running", Job.lease_expires_at < _now()).with_for_update(skip_locked=True)
            )
        ).all()
        for job in jobs:
            recovered += 1
            retry = job.attempts < job.max_attempts
            if job.kind == "investigation":
                inv = await s.get(Investigation, job.ref_id)
                if inv is not None and inv.consequential_started:
                    retry = False
                if inv is not None:
                    if retry:
                        inv.status = "queued"
                        inv.phase = "queued"
                    else:
                        inv.status = "failed"
                        inv.finished_at = _now()
                        inv.error = (
                            "The worker running this investigation stopped responding. It was not retried "
                            "automatically because it had already performed a consequential action "
                            "(such as submitting a registration form)."
                            if inv.consequential_started
                            else "The worker running this investigation stopped responding and the retry limit was reached."
                        )
            if job.kind == "briefing":
                # Briefings are read-only, so retrying is always safe.
                b = await s.get(Briefing, job.ref_id)
                if b is not None:
                    if retry:
                        b.status = "queued"
                    else:
                        b.status, b.finished_at = "failed", _now()
                        b.error = "The worker reading this website stopped responding."
                        b.credential_ciphertext = None
            job.status = "queued" if retry else "failed"
            job.locked_by = None
            job.lease_expires_at = None
            job.last_error = "lease expired (worker lost)"
            log.warning("recovered job %s (%s) retry=%s", job.id, job.kind, retry)
    return recovered
