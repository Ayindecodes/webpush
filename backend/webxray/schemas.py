"""Pydantic models shared by the API and the worker."""

from __future__ import annotations

import re
import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

ViewportName = Literal["desktop", "tablet", "mobile"]
_PATH_PREFIX = re.compile(r"^/[A-Za-z0-9._~!$&'()*+,;=:@%/-]*$")


class InvestigationConfig(BaseModel):
    """Validated, bounded configuration persisted with each investigation."""

    model_config = ConfigDict(extra="forbid")

    viewports: list[ViewportName] = Field(default_factory=lambda: ["desktop", "mobile"], min_length=1)
    max_pages: int = Field(default=25, ge=1, le=200)
    max_depth: int = Field(default=3, ge=0, le=8)
    max_duration_s: int = Field(default=900, ge=60, le=3600)
    repeat_failed_runs: int = Field(default=1, ge=0, le=3)
    start_path: str = "/"
    include_paths: list[str] = Field(default_factory=list, max_length=20)
    exclude_paths: list[str] = Field(default_factory=list, max_length=50)
    allow_registration: bool = False
    allow_order_submission: bool = False

    @field_validator("viewports")
    @classmethod
    def _dedupe_viewports(cls, v: list[str]) -> list[str]:
        order = ["desktop", "tablet", "mobile"]
        return [x for x in order if x in set(v)]

    @field_validator("start_path")
    @classmethod
    def _start_path(cls, v: str) -> str:
        if not _PATH_PREFIX.match(v) or v.startswith("//"):
            raise ValueError("start_path must be a path beginning with '/'")
        return v

    @field_validator("include_paths", "exclude_paths")
    @classmethod
    def _paths(cls, v: list[str]) -> list[str]:
        for p in v:
            if not _PATH_PREFIX.match(p) or p.startswith("//"):
                raise ValueError(f"'{p}' is not a valid path prefix (must start with '/')")
        return v


# --------------------------------------------------------------------------- auth


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=10, max_length=256)
    display_name: str = Field(default="", max_length=120)
    organization_name: str = Field(default="", max_length=120)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=256)


class UserOut(BaseModel):
    id: uuid.UUID
    email: str
    display_name: str
    organization_id: uuid.UUID
    organization_name: str


# --------------------------------------------------------------------------- projects


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)

    @field_validator("name")
    @classmethod
    def _strip(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("name must not be blank")
        return v


class ProjectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str
    created_at: datetime
    environment_count: int = 0
    investigation_count: int = 0


class EnvironmentCreate(BaseModel):
    origin: str = Field(min_length=1, max_length=300)
    label: str = Field(default="", max_length=120)


class EnvironmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    project_id: uuid.UUID
    origin: str
    label: str
    verification_status: str
    verification_method: str | None
    verification_token: str
    verified_at: datetime | None
    created_at: datetime


class VerificationOut(BaseModel):
    verified: bool
    method: str | None
    detail: str
    environment: EnvironmentOut


class CredentialCreate(BaseModel):
    environment_id: uuid.UUID
    label: str = Field(min_length=1, max_length=120)
    username: str = Field(min_length=1, max_length=320)
    password: str = Field(min_length=1, max_length=512)


class CredentialOut(BaseModel):
    id: uuid.UUID
    environment_id: uuid.UUID
    label: str
    source: str
    username_hint: str
    lifecycle_state: str
    created_at: datetime


# --------------------------------------------------------------------------- investigations


class InvestigationCreate(BaseModel):
    environment_id: uuid.UUID
    mode: Literal["autonomous", "authenticated"]
    goal: str = Field(default="", max_length=2000)
    credential_id: uuid.UUID | None = None
    config: InvestigationConfig = Field(default_factory=InvestigationConfig)
    # Explicit approvals captured at plan review time.
    confirm_authorized: bool
    approve_registration: bool = False
    approve_order_submission: bool = False

    @model_validator(mode="after")
    def _check(self) -> InvestigationCreate:
        if not self.confirm_authorized:
            raise ValueError("You must confirm you are authorized to test this target.")
        if self.mode == "authenticated" and self.credential_id is None:
            raise ValueError("Authenticated investigations require a test-account credential.")
        if self.config.allow_registration and not self.approve_registration:
            raise ValueError("allow_registration requires approve_registration.")
        if self.config.allow_order_submission and not self.approve_order_submission:
            raise ValueError("allow_order_submission requires approve_order_submission.")
        return self


class InvestigationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    project_id: uuid.UUID
    project_name: str | None = None
    environment_id: uuid.UUID
    origin: str | None = None
    mode: str
    goal: str
    config: dict[str, Any]
    status: str
    phase: str
    phases: list[dict[str, Any]]
    requested_control: str
    blocked_reason: str | None
    error: str | None
    current_url: str | None
    current_title: str | None
    current_action: str | None
    latest_screenshot_id: uuid.UUID | None
    auth_state: str
    summary: dict[str, Any]
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    finding_counts: dict[str, int] = Field(default_factory=dict)
    page_count: int = 0


class EventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    seq: int
    ts: datetime
    kind: str
    level: str
    message: str
    data: dict[str, Any]
    browser_run_id: uuid.UUID | None
    page_url: str | None
    evidence_id: uuid.UUID | None


class PageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    url: str
    title: str
    status_code: int | None
    depth: int
    auth_state: str
    classification: str
    discovered_from: str | None
    inventory: dict[str, Any]
    screenshot_id: uuid.UUID | None
    console_error_count: int
    failed_request_count: int
    load_ms: int | None


class FeatureOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    key: str
    name: str
    status: str
    page_url: str | None
    details: dict[str, Any]


class RunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    journey_id: uuid.UUID
    viewport_name: str
    viewport: dict[str, Any]
    attempt: int
    status: str
    failure_step: str | None
    steps: list[dict[str, Any]]
    started_at: datetime
    finished_at: datetime | None


class JourneyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    investigation_id: uuid.UUID
    key: str
    name: str
    status: str
    definition: dict[str, Any]
    created_at: datetime
    runs: list[RunOut] = Field(default_factory=list)
    origin: str | None = None
    project_name: str | None = None


class EvidenceOut(BaseModel):
    id: uuid.UUID
    kind: str
    label: str
    content_type: str
    size_bytes: int
    sha256: str
    meta: dict[str, Any]
    redactions: list[str]
    event_seq: int | None
    browser_run_id: uuid.UUID | None
    created_at: datetime
    role: str | None = None
    url: str
    url_expires_at: int


class TestRunOut(BaseModel):
    __test__ = False
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    test_id: uuid.UUID
    status: str
    playwright_status: str | None
    outcome: str | None
    exit_code: int | None
    duration_ms: int | None
    error_message: str | None
    output_evidence_id: uuid.UUID | None
    source_sha256: str
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class TestOut(BaseModel):
    __test__ = False
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    finding_id: uuid.UUID
    investigation_id: uuid.UUID
    framework: str
    filename: str
    source: str
    sha256: str
    verification_status: str
    created_at: datetime
    runs: list[TestRunOut] = Field(default_factory=list)


class FindingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    investigation_id: uuid.UUID
    project_id: uuid.UUID
    kind: str
    classification: str
    severity: str
    title: str
    summary: str
    expected: str | None
    observed: str | None
    page_url: str | None
    viewport_name: str | None
    reproduction: dict[str, Any]
    hypotheses: list[dict[str, Any]]
    evidence_strength: str
    steps_to_reproduce: list[str]
    recommendation: str | None
    occurrences: int
    first_event_seq: int | None
    created_at: datetime
    origin: str | None = None
    test_status: str | None = None
    test_id: uuid.UUID | None = None


# --------------------------------------------------------------------------- briefings


class BriefingLogin(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: str = Field(min_length=1, max_length=320)
    password: str = Field(min_length=1, max_length=512)
    # Path or full URL of the sign-in page (same website). Found automatically when empty.
    login_url: str = Field(default="", max_length=2048)


class BriefingCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    url: str = Field(min_length=1, max_length=2048)
    # Optional plain-language question ("Do they ship to Canada?"). Used only to
    # pick which pages to read and which facts to surface first.
    question: str = Field(default="", max_length=300)
    login: BriefingLogin | None = None
    # Required with ``login``: the account belongs to the user (or they may use it).
    confirm_account: bool = False

    @model_validator(mode="after")
    def _confirm_login(self) -> BriefingCreate:
        if self.login is not None and not self.confirm_account:
            raise ValueError("Confirm that this is your account (or one you're allowed to use) before WEB X-RAY signs in with it.")
        return self


class BriefingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    url: str
    origin: str
    question: str
    status: str
    current_action: str | None
    current_url: str | None
    steps: list[dict[str, Any]]
    result: dict[str, Any]
    error: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    shots: list[dict[str, Any]] = Field(default_factory=list)
    # Never the credential itself: only a masked username and the sign-in outcome.
    login_url: str | None = None
    credential_hint: str | None = None
    auth_status: str = "not_requested"
    auth_detail: str | None = None
