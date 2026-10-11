"""Persistent data model.

Every tenant-owned row carries ``org_id`` (and ``project_id`` where relevant) so
authorization checks never depend on walking relationships. Credentials live in
their own table and are only ever stored encrypted.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from webxray.db import Base


def _uuid() -> uuid.UUID:
    return uuid.uuid4()


def _pk() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)


def _created() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


def _fk(target: str, *, nullable: bool = False, ondelete: str = "CASCADE") -> Mapped[Any]:
    return mapped_column(
        UUID(as_uuid=True), ForeignKey(target, ondelete=ondelete), nullable=nullable, index=True
    )


# --------------------------------------------------------------------------- identity


class User(Base):
    __tablename__ = "users"
    id: Mapped[uuid.UUID] = _pk()
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = _created()


class Organization(Base):
    __tablename__ = "organizations"
    id: Mapped[uuid.UUID] = _pk()
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    created_at: Mapped[datetime] = _created()


class Membership(Base):
    __tablename__ = "memberships"
    __table_args__ = (UniqueConstraint("org_id", "user_id"),)
    id: Mapped[uuid.UUID] = _pk()
    org_id: Mapped[uuid.UUID] = _fk("organizations.id")
    user_id: Mapped[uuid.UUID] = _fk("users.id")
    role: Mapped[str] = mapped_column(String(32), nullable=False, default="owner")
    created_at: Mapped[datetime] = _created()


class AuthSession(Base):
    __tablename__ = "auth_sessions"
    id: Mapped[uuid.UUID] = _pk()
    user_id: Mapped[uuid.UUID] = _fk("users.id")
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    created_at: Mapped[datetime] = _created()
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


# --------------------------------------------------------------------------- projects


class Project(Base):
    __tablename__ = "projects"
    id: Mapped[uuid.UUID] = _pk()
    org_id: Mapped[uuid.UUID] = _fk("organizations.id")
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    created_at: Mapped[datetime] = _created()


class Environment(Base):
    """A scan target: one origin within a project, with proof of authorization."""

    __tablename__ = "environments"
    __table_args__ = (UniqueConstraint("project_id", "origin"),)
    id: Mapped[uuid.UUID] = _pk()
    org_id: Mapped[uuid.UUID] = _fk("organizations.id")
    project_id: Mapped[uuid.UUID] = _fk("projects.id")
    origin: Mapped[str] = mapped_column(String(300), nullable=False)
    label: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    # pending | verified
    verification_status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    # http_file | dns_txt | operator_allowlist
    verification_method: Mapped[str | None] = mapped_column(String(32))
    verification_token: Mapped[str] = mapped_column(String(64), nullable=False)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = _created()


class CredentialSecret(Base):
    """Encrypted test-account credentials. Never serialized to API responses in plaintext."""

    __tablename__ = "credential_secrets"
    id: Mapped[uuid.UUID] = _pk()
    org_id: Mapped[uuid.UUID] = _fk("organizations.id")
    project_id: Mapped[uuid.UUID] = _fk("projects.id")
    environment_id: Mapped[uuid.UUID] = _fk("environments.id")
    label: Mapped[str] = mapped_column(String(120), nullable=False)
    # user_supplied | generated
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    username_hint: Mapped[str] = mapped_column(String(120), nullable=False)
    ciphertext: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    # For generated accounts: registration_pending | registered | verification_required |
    # registration_failed | outcome_unknown. For supplied accounts: active.
    lifecycle_state: Mapped[str] = mapped_column(String(40), nullable=False)
    created_by_investigation_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    created_at: Mapped[datetime] = _created()
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


# --------------------------------------------------------------------------- investigations


class Investigation(Base):
    __tablename__ = "investigations"
    id: Mapped[uuid.UUID] = _pk()
    org_id: Mapped[uuid.UUID] = _fk("organizations.id")
    project_id: Mapped[uuid.UUID] = _fk("projects.id")
    environment_id: Mapped[uuid.UUID] = _fk("environments.id")
    created_by: Mapped[uuid.UUID | None] = _fk("users.id", nullable=True, ondelete="SET NULL")
    credential_id: Mapped[uuid.UUID | None] = _fk(
        "credential_secrets.id", nullable=True, ondelete="SET NULL"
    )
    # autonomous | authenticated
    mode: Mapped[str] = mapped_column(String(32), nullable=False)
    goal: Mapped[str] = mapped_column(Text, nullable=False, default="")
    config: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    # queued | running | paused | completed | failed | stopped | blocked
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="queued", index=True)
    phase: Mapped[str] = mapped_column(String(48), nullable=False, default="queued")
    phases: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    # none | pause | stop — set by the API, honoured by the worker at checkpoints.
    requested_control: Mapped[str] = mapped_column(String(16), nullable=False, default="none")
    blocked_reason: Mapped[str | None] = mapped_column(Text)
    error: Mapped[str | None] = mapped_column(Text)
    current_url: Mapped[str | None] = mapped_column(Text)
    current_title: Mapped[str | None] = mapped_column(Text)
    current_action: Mapped[str | None] = mapped_column(Text)
    latest_screenshot_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    # True once the worker has done something that must not be blindly repeated
    # (e.g. submitted a registration form). Governs automatic retry on worker loss.
    consequential_started: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    auth_state: Mapped[str] = mapped_column(String(40), nullable=False, default="anonymous")
    budget: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    summary: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = _created()
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Page(Base):
    __tablename__ = "pages"
    __table_args__ = (UniqueConstraint("investigation_id", "url", "auth_state"),)
    id: Mapped[uuid.UUID] = _pk()
    org_id: Mapped[uuid.UUID] = _fk("organizations.id")
    project_id: Mapped[uuid.UUID] = _fk("projects.id")
    investigation_id: Mapped[uuid.UUID] = _fk("investigations.id")
    url: Mapped[str] = mapped_column(Text, nullable=False)
    final_url: Mapped[str | None] = mapped_column(Text)
    title: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status_code: Mapped[int | None] = mapped_column(Integer)
    depth: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    auth_state: Mapped[str] = mapped_column(String(32), nullable=False)
    classification: Mapped[str] = mapped_column(String(32), nullable=False, default="content")
    discovered_from: Mapped[str | None] = mapped_column(Text)
    inventory: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    screenshot_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    console_error_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed_request_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    load_ms: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = _created()


class Feature(Base):
    __tablename__ = "features"
    __table_args__ = (UniqueConstraint("investigation_id", "key"),)
    id: Mapped[uuid.UUID] = _pk()
    org_id: Mapped[uuid.UUID] = _fk("organizations.id")
    project_id: Mapped[uuid.UUID] = _fk("projects.id")
    investigation_id: Mapped[uuid.UUID] = _fk("investigations.id")
    key: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    # discovered | tested | untested | needs_permission | needs_human | inaccessible
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="discovered")
    page_url: Mapped[str | None] = mapped_column(Text)
    details: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = _created()


class Journey(Base):
    __tablename__ = "journeys"
    id: Mapped[uuid.UUID] = _pk()
    org_id: Mapped[uuid.UUID] = _fk("organizations.id")
    project_id: Mapped[uuid.UUID] = _fk("projects.id")
    investigation_id: Mapped[uuid.UUID] = _fk("investigations.id")
    key: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    definition: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    # planned | passed | failed | partial | skipped
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="planned")
    created_at: Mapped[datetime] = _created()


class BrowserRun(Base):
    __tablename__ = "browser_runs"
    id: Mapped[uuid.UUID] = _pk()
    org_id: Mapped[uuid.UUID] = _fk("organizations.id")
    project_id: Mapped[uuid.UUID] = _fk("projects.id")
    investigation_id: Mapped[uuid.UUID] = _fk("investigations.id")
    journey_id: Mapped[uuid.UUID] = _fk("journeys.id")
    viewport_name: Mapped[str] = mapped_column(String(32), nullable=False)
    viewport: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    # running | passed | failed | error | blocked
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="running")
    failure_step: Mapped[str | None] = mapped_column(String(64))
    steps: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    observations: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    started_at: Mapped[datetime] = _created()
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Event(Base):
    __tablename__ = "events"
    __table_args__ = (
        UniqueConstraint("investigation_id", "seq"),
        Index("ix_events_inv_seq", "investigation_id", "seq"),
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    org_id: Mapped[uuid.UUID] = _fk("organizations.id")
    investigation_id: Mapped[uuid.UUID] = _fk("investigations.id")
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    # phase | navigation | action | assertion | console | network | finding | policy | auth | system
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    level: Mapped[str] = mapped_column(String(16), nullable=False, default="info")
    message: Mapped[str] = mapped_column(Text, nullable=False)
    data: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    browser_run_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), index=True)
    page_url: Mapped[str | None] = mapped_column(Text)
    evidence_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))


class Finding(Base):
    __tablename__ = "findings"
    __table_args__ = (UniqueConstraint("investigation_id", "dedupe_key"),)
    id: Mapped[uuid.UUID] = _pk()
    org_id: Mapped[uuid.UUID] = _fk("organizations.id")
    project_id: Mapped[uuid.UUID] = _fk("projects.id")
    investigation_id: Mapped[uuid.UUID] = _fk("investigations.id")
    journey_id: Mapped[uuid.UUID | None] = _fk("journeys.id", nullable=True, ondelete="SET NULL")
    dedupe_key: Mapped[str] = mapped_column(String(200), nullable=False)
    # journey_failure | http_error | page_error | console_error | request_failure | blocked_request
    kind: Mapped[str] = mapped_column(String(40), nullable=False)
    # confirmed_defect | warning | observation
    classification: Mapped[str] = mapped_column(String(32), nullable=False)
    # critical | high | medium | low | info
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    expected: Mapped[str | None] = mapped_column(Text)
    observed: Mapped[str | None] = mapped_column(Text)
    page_url: Mapped[str | None] = mapped_column(Text)
    viewport_name: Mapped[str | None] = mapped_column(String(32))
    reproduction: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    hypotheses: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    # strong | moderate | limited
    evidence_strength: Mapped[str] = mapped_column(String(16), nullable=False, default="limited")
    steps_to_reproduce: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    recommendation: Mapped[str | None] = mapped_column(Text)
    occurrences: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    first_event_seq: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = _created()


class Evidence(Base):
    __tablename__ = "evidence"
    id: Mapped[uuid.UUID] = _pk()
    org_id: Mapped[uuid.UUID] = _fk("organizations.id")
    project_id: Mapped[uuid.UUID] = _fk("projects.id")
    investigation_id: Mapped[uuid.UUID] = _fk("investigations.id")
    browser_run_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), index=True)
    # screenshot | dom_snapshot | hit_test | computed_styles | network_log | console_log |
    # test_source | test_output
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    label: Mapped[str] = mapped_column(Text, nullable=False, default="")
    storage_key: Mapped[str] = mapped_column(Text, nullable=False)
    content_type: Mapped[str] = mapped_column(String(100), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    meta: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    redactions: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    event_seq: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = _created()


class FindingEvidence(Base):
    __tablename__ = "finding_evidence"
    __table_args__ = (UniqueConstraint("finding_id", "evidence_id"),)
    id: Mapped[uuid.UUID] = _pk()
    finding_id: Mapped[uuid.UUID] = _fk("findings.id")
    evidence_id: Mapped[uuid.UUID] = _fk("evidence.id")
    role: Mapped[str] = mapped_column(String(48), nullable=False, default="supporting")


class ReproductionTest(Base):
    __tablename__ = "reproduction_tests"
    id: Mapped[uuid.UUID] = _pk()
    org_id: Mapped[uuid.UUID] = _fk("organizations.id")
    project_id: Mapped[uuid.UUID] = _fk("projects.id")
    investigation_id: Mapped[uuid.UUID] = _fk("investigations.id")
    finding_id: Mapped[uuid.UUID] = _fk("findings.id")
    framework: Mapped[str] = mapped_column(String(32), nullable=False, default="playwright-ts")
    filename: Mapped[str] = mapped_column(String(200), nullable=False)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    # generated | reproduced | not_reproduced | inconclusive — only changed by real test runs.
    verification_status: Mapped[str] = mapped_column(String(32), nullable=False, default="generated")
    last_run_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    created_at: Mapped[datetime] = _created()


class TestRun(Base):
    __tablename__ = "test_runs"
    __test__ = False  # keep pytest from collecting this class
    id: Mapped[uuid.UUID] = _pk()
    org_id: Mapped[uuid.UUID] = _fk("organizations.id")
    project_id: Mapped[uuid.UUID] = _fk("projects.id")
    test_id: Mapped[uuid.UUID] = _fk("reproduction_tests.id")
    requested_by: Mapped[uuid.UUID | None] = _fk("users.id", nullable=True, ondelete="SET NULL")
    # queued | running | finished | error
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="queued")
    # passed | failed | skipped | timed_out | interrupted (Playwright's own result)
    playwright_status: Mapped[str | None] = mapped_column(String(32))
    # reproduced | not_reproduced | inconclusive
    outcome: Mapped[str | None] = mapped_column(String(32))
    exit_code: Mapped[int | None] = mapped_column(Integer)
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    error_message: Mapped[str | None] = mapped_column(Text)
    output_evidence_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    source_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = _created()
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Approval(Base):
    __tablename__ = "approvals"
    id: Mapped[uuid.UUID] = _pk()
    org_id: Mapped[uuid.UUID] = _fk("organizations.id")
    project_id: Mapped[uuid.UUID] = _fk("projects.id")
    investigation_id: Mapped[uuid.UUID | None] = _fk("investigations.id", nullable=True)
    # scan_authorization | account_registration | order_submission
    kind: Mapped[str] = mapped_column(String(48), nullable=False)
    granted_by: Mapped[uuid.UUID | None] = _fk("users.id", nullable=True, ondelete="SET NULL")
    statement: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = _created()


class AuditLog(Base):
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    org_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), index=True)
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    actor: Mapped[str] = mapped_column(String(32), nullable=False, default="user")
    action: Mapped[str] = mapped_column(String(80), nullable=False)
    target_type: Mapped[str | None] = mapped_column(String(48))
    target_id: Mapped[str | None] = mapped_column(String(64))
    details: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class Job(Base):
    """Durable work queue. Postgres is the source of truth; Redis only wakes workers."""

    __tablename__ = "jobs"
    __table_args__ = (Index("ix_jobs_claim", "status", "run_after"),)
    id: Mapped[uuid.UUID] = _pk()
    # investigation | test_run | briefing
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    ref_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    # queued | running | succeeded | failed
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="queued")
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=2)
    run_after: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    locked_by: Mapped[str | None] = mapped_column(String(120))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = _created()
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


# --------------------------------------------------------------------------- briefings


class Briefing(Base):
    """A read-only "what is this website?" visit.

    Unlike an investigation it never submits forms, signs in, or clicks
    anything but links, so it does not need a verified target. It still goes
    through the egress proxy (public addresses only) and honours robots.txt.
    """

    __tablename__ = "briefings"
    id: Mapped[uuid.UUID] = _pk()
    org_id: Mapped[uuid.UUID] = _fk("organizations.id")
    created_by: Mapped[uuid.UUID | None] = _fk("users.id", nullable=True, ondelete="SET NULL")
    url: Mapped[str] = mapped_column(Text, nullable=False)
    origin: Mapped[str] = mapped_column(String(300), nullable=False)
    question: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # queued | running | completed | failed | blocked
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="queued", index=True)
    current_action: Mapped[str | None] = mapped_column(Text)
    current_url: Mapped[str | None] = mapped_column(Text)
    # [{ts, message}] — what the agent did, in order.
    steps: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    # [{key, sha256, url, title}] — screenshots in the artifact store.
    shots: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    result: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    error: Mapped[str | None] = mapped_column(Text)
    # Optional sign-in. The ciphertext exists only while the briefing is queued or
    # running; the worker wipes it when the run ends, whatever the outcome.
    login_url: Mapped[str | None] = mapped_column(Text)
    credential_ciphertext: Mapped[bytes | None] = mapped_column(LargeBinary)
    credential_hint: Mapped[str | None] = mapped_column(String(160))
    # not_requested | pending | authenticated | failed | blocked_captcha | mfa_required |
    # verification_required | no_login_form
    auth_status: Mapped[str] = mapped_column(String(32), nullable=False, default="not_requested")
    auth_detail: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = _created()
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
