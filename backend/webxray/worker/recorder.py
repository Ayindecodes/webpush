"""Persistence of investigation state, events and evidence from inside the worker.

Every write is a short transaction so the dashboard sees progress as it
happens. All text passes through the investigation's :class:`Redactor` before
it is stored.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select, update

from webxray.db import session_scope
from webxray.models import Event, Evidence, Investigation
from webxray.security.redaction import Redactor
from webxray.storage.artifacts import ArtifactStore

log = logging.getLogger(__name__)

PHASES: list[tuple[str, str]] = [
    ("validate", "Validate target and scope"),
    ("discover_public", "Discover public pages"),
    ("authenticate", "Authenticate"),
    ("discover_authenticated", "Discover authenticated pages"),
    ("plan", "Plan journeys"),
    ("execute", "Execute journeys"),
    ("diagnose", "Diagnose failures"),
    ("reproduce", "Generate and run reproduction tests"),
    ("report", "Compile report"),
]


class ControlRequested(Exception):
    """Raised at a checkpoint when the user asked to stop."""


class Recorder:
    def __init__(
        self,
        investigation_id: uuid.UUID,
        org_id: uuid.UUID,
        project_id: uuid.UUID,
        store: ArtifactStore,
        redactor: Redactor,
    ) -> None:
        self.investigation_id = investigation_id
        self.org_id = org_id
        self.project_id = project_id
        self.store = store
        self.redactor = redactor
        self._seq = 0
        self._phases: list[dict[str, Any]] = [
            {"key": k, "label": label, "status": "pending", "detail": None} for k, label in PHASES
        ]

    async def init(self) -> None:
        async with session_scope() as s:
            max_seq = await s.scalar(
                select(func.max(Event.seq)).where(Event.investigation_id == self.investigation_id)
            )
            inv = await s.get(Investigation, self.investigation_id)
            if inv is not None and inv.phases:
                self._phases = inv.phases
        self._seq = max_seq or 0

    @property
    def seq(self) -> int:
        return self._seq

    # ------------------------------------------------------------------ events

    async def event(
        self,
        kind: str,
        message: str,
        *,
        level: str = "info",
        data: dict[str, Any] | None = None,
        run_id: uuid.UUID | None = None,
        page_url: str | None = None,
        evidence_id: uuid.UUID | None = None,
    ) -> int:
        self._seq += 1
        seq = self._seq
        async with session_scope() as s:
            s.add(
                Event(
                    org_id=self.org_id,
                    investigation_id=self.investigation_id,
                    seq=seq,
                    kind=kind,
                    level=level,
                    message=self.redactor.text(message)[:4000],
                    data=self.redactor.deep(data or {}),
                    browser_run_id=run_id,
                    page_url=self.redactor.url(page_url) if page_url else None,
                    evidence_id=evidence_id,
                )
            )
        return seq

    # ------------------------------------------------------------------ evidence

    async def evidence(
        self,
        kind: str,
        data: bytes | str | dict[str, Any] | list[Any],
        *,
        label: str,
        content_type: str | None = None,
        run_id: uuid.UUID | None = None,
        meta: dict[str, Any] | None = None,
        redactions: list[str] | None = None,
    ) -> uuid.UUID:
        applied = list(redactions or [])
        if isinstance(data, dict | list):
            payload = json.dumps(self.redactor.deep(data), indent=2, default=str).encode()
            content_type = content_type or "application/json"
            applied.append("structured_redaction")
        elif isinstance(data, str):
            text, rules = self.redactor.text_with_rules(data)
            payload = text.encode()
            content_type = content_type or "text/plain; charset=utf-8"
            applied.extend(rules)
        else:
            payload = data
            content_type = content_type or "application/octet-stream"
        evidence_id = uuid.uuid4()
        ext = {"image/png": "png", "image/jpeg": "jpg", "application/json": "json"}.get(
            content_type.split(";")[0], "txt"
        )
        key = f"org/{self.org_id}/project/{self.project_id}/inv/{self.investigation_id}/{evidence_id}.{ext}"
        stored = self.store.put(key, payload)
        async with session_scope() as s:
            s.add(
                Evidence(
                    id=evidence_id,
                    org_id=self.org_id,
                    project_id=self.project_id,
                    investigation_id=self.investigation_id,
                    browser_run_id=run_id,
                    kind=kind,
                    label=self.redactor.text(label)[:500],
                    storage_key=stored.key,
                    content_type=content_type,
                    size_bytes=stored.size,
                    sha256=stored.sha256,
                    meta=self.redactor.deep(meta or {}),
                    redactions=sorted(set(applied)),
                    event_seq=self._seq or None,
                )
            )
        return evidence_id

    # ------------------------------------------------------------------ state

    async def update(self, **fields: Any) -> None:
        for key in ("current_url",):
            if fields.get(key):
                fields[key] = self.redactor.url(fields[key])
        for key in ("current_title", "current_action", "blocked_reason", "error"):
            if fields.get(key):
                fields[key] = self.redactor.text(fields[key])
        async with session_scope() as s:
            await s.execute(
                update(Investigation).where(Investigation.id == self.investigation_id).values(**fields)
            )

    async def action(self, text: str, **extra: Any) -> None:
        await self.update(current_action=text, **extra)

    async def phase(self, key: str, status: str = "running", detail: str | None = None) -> None:
        for p in self._phases:
            if p["key"] == key:
                p["status"] = status
                p["detail"] = self.redactor.text(detail) if detail else p.get("detail")
                if status == "running":
                    p["started_at"] = datetime.now(UTC).isoformat()
                elif status in {"done", "skipped", "failed", "blocked"}:
                    p["finished_at"] = datetime.now(UTC).isoformat()
        fields: dict[str, Any] = {"phases": [dict(p) for p in self._phases]}
        if status == "running":
            fields["phase"] = key
        await self.update(**fields)
        label = next(lbl for k, lbl in PHASES if k == key)
        verb = {"running": "Started", "done": "Completed", "skipped": "Skipped", "failed": "Failed", "blocked": "Blocked"}
        msg = f"{verb.get(status, status)}: {label}" + (f" — {detail}" if detail else "")
        await self.event("phase", msg, level="warn" if status in {"failed", "blocked"} else "info", data={"phase": key, "status": status})

    # ------------------------------------------------------------------ control

    async def wait_for_human(self, reason: str, *, timeout_s: float = 30 * 60) -> bool:
        """Pause safely until a person resumes the investigation.

        Returns True when resumed, False on timeout. Raises ControlRequested on stop.
        """
        import asyncio

        await self.update(status="awaiting_human", blocked_reason=reason, requested_control="pause")
        await self.event("auth", f"Waiting for human assistance: {reason}", level="warn")
        waited = 0.0
        while waited < timeout_s:
            async with session_scope() as s:
                control = await s.scalar(
                    select(Investigation.requested_control).where(Investigation.id == self.investigation_id)
                )
            if control == "stop":
                raise ControlRequested("stop")
            if control != "pause":
                await self.update(status="running", blocked_reason=None)
                await self.event("auth", "Human assistance confirmed; continuing")
                return True
            await asyncio.sleep(1.0)
            waited += 1.0
        await self.update(status="running", requested_control="none")
        await self.event("auth", "No human response within the time limit; continuing without it", level="warn")
        return False

    async def checkpoint(self) -> None:
        """Honour pause/stop requests. Called between every unit of browser work."""
        import asyncio

        paused_announced = False
        waited = 0.0
        while True:
            async with session_scope() as s:
                control = await s.scalar(
                    select(Investigation.requested_control).where(Investigation.id == self.investigation_id)
                )
            if control == "stop":
                raise ControlRequested("stop")
            if control != "pause":
                if paused_announced:
                    await self.update(status="running")
                    await self.event("system", "Investigation resumed")
                return
            if not paused_announced:
                await self.update(status="paused")
                await self.event("system", "Investigation paused by user; browser state is held")
                paused_announced = True
            await asyncio.sleep(1.0)
            waited += 1.0
            if waited > 30 * 60:
                await self.event("system", "Paused for more than 30 minutes; stopping", level="warn")
                raise ControlRequested("stop")
