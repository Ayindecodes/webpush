"""Worker process: claims jobs from the durable queue and executes them.

Run:  python -m webxray.worker.main
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import socket
import uuid
from datetime import UTC, datetime

import redis.asyncio as aioredis

from webxray.config import get_settings
from webxray.db import dispose_engine, session_scope
from webxray.logging_setup import configure_logging
from webxray.models import Briefing, Investigation, Job, TestRun
from webxray.services import jobs
from webxray.worker.briefing import BriefingRunner
from webxray.worker.pipeline import InvestigationRunner, run_test

log = logging.getLogger("webxray.worker")


async def _heartbeat_loop(job_id: uuid.UUID, worker_id: str, stop: asyncio.Event) -> None:
    interval = max(5, get_settings().worker_lease_seconds // 3)
    while not stop.is_set():
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(stop.wait(), interval)
        if not stop.is_set():
            await jobs.heartbeat(job_id, worker_id)


async def handle(job: Job, worker_id: str) -> None:
    stop = asyncio.Event()
    hb = asyncio.create_task(_heartbeat_loop(job.id, worker_id, stop))
    error: str | None = None
    try:
        if job.kind == "investigation":
            await InvestigationRunner(job.ref_id).run()
        elif job.kind == "test_run":
            await run_test(job.ref_id)
        elif job.kind == "briefing":
            await BriefingRunner(job.ref_id).run()
        else:
            error = f"unknown job kind {job.kind}"
    except Exception as exc:  # noqa: BLE001
        log.exception("job %s failed", job.id)
        error = f"{exc.__class__.__name__}: {exc}"[:2000]
        await _mark_ref_failed(job, error)
    finally:
        stop.set()
        await hb
        await jobs.complete(job.id, error=error)


async def _mark_ref_failed(job: Job, error: str) -> None:
    async with session_scope() as s:
        if job.kind == "investigation":
            inv = await s.get(Investigation, job.ref_id)
            if inv is not None and inv.status not in {"completed", "stopped", "blocked", "failed"}:
                inv.status, inv.error, inv.finished_at = "failed", error, datetime.now(UTC)
        elif job.kind == "test_run":
            run = await s.get(TestRun, job.ref_id)
            if run is not None and run.status in {"queued", "running"}:
                run.status, run.outcome, run.error_message = "error", "inconclusive", error
        elif job.kind == "briefing":
            b = await s.get(Briefing, job.ref_id)
            if b is not None and b.status in {"queued", "running"}:
                b.status, b.error, b.finished_at = "failed", "The visit failed unexpectedly.", datetime.now(UTC)
            if b is not None:
                b.credential_ciphertext = None  # never keep a sign-in past its run


PRESENCE_PREFIX = "webxray:worker:"
PRESENCE_TTL = 30


async def _presence_loop(client: aioredis.Redis, worker_id: str) -> None:
    """Advertise that this worker is alive (the dashboard tells users when none are)."""
    while True:
        with contextlib.suppress(Exception):
            await client.set(f"{PRESENCE_PREFIX}{worker_id}", "1", ex=PRESENCE_TTL)
        await asyncio.sleep(PRESENCE_TTL / 3)


async def run_worker(*, once: bool = False) -> None:
    settings = get_settings()
    worker_id = f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:6]}"
    log.info("worker %s starting", worker_id)
    client = aioredis.from_url(settings.redis_url)
    last_recovery = 0.0
    loop = asyncio.get_running_loop()
    presence = asyncio.create_task(_presence_loop(client, worker_id))
    try:
        while True:
            if loop.time() - last_recovery > 15:
                with contextlib.suppress(Exception):
                    await jobs.recover_expired()
                last_recovery = loop.time()
            job = await jobs.claim(worker_id)
            if job is not None:
                log.info("claimed job %s kind=%s ref=%s attempt=%s", job.id, job.kind, job.ref_id, job.attempts)
                await handle(job, worker_id)
                if once:
                    return
                continue
            if once:
                return
            try:
                await client.blpop([jobs.WAKE_KEY], timeout=settings.worker_poll_seconds)
            except Exception:  # Redis unavailable: fall back to polling.
                await asyncio.sleep(settings.worker_poll_seconds)
    finally:
        presence.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await presence
        with contextlib.suppress(Exception):
            await client.delete(f"{PRESENCE_PREFIX}{worker_id}")
        await client.aclose()
        await dispose_engine()


def main() -> None:
    configure_logging(get_settings().log_level)
    asyncio.run(run_worker())


if __name__ == "__main__":
    main()
