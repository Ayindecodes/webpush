"""Investigation state machine.

validate → discover_public → authenticate → discover_authenticated → plan →
execute → diagnose → reproduce → report

Every phase records its outcome; failures in one phase degrade the
investigation (and are reported as limitations) rather than being hidden.
"""

from __future__ import annotations

import logging
import time
import traceback
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit

from sqlalchemy import func, select

from webxray.config import get_settings
from webxray.db import session_scope
from webxray.models import (
    CredentialSecret,
    Environment,
    Evidence,
    Feature,
    Finding,
    FindingEvidence,
    Investigation,
    Journey,
    ReproductionTest,
    TestRun,
)
from webxray.schemas import InvestigationConfig
from webxray.security.crypto import TestAccountSecret, decrypt_credential, encrypt_credential, mask_username
from webxray.security.redaction import Redactor
from webxray.security.target_policy import TargetRejected, parse_origin, resolve_and_check
from webxray.services.policy import egress_policy
from webxray.storage.artifacts import get_artifact_store
from webxray.worker import auth_flow
from webxray.worker.browser import VIEWPORTS, BrowserSession
from webxray.worker.crawler import CrawledPage, Crawler, CrawlLimits, path_of
from webxray.worker.diagnosis import DiagnosedFinding, diagnose_checkout, diagnose_layout, diagnose_pages
from webxray.worker.journeys.checkout import CheckoutRun, RunResult, plan_checkout
from webxray.worker.recorder import ControlRequested, Recorder
from webxray.worker.test_runner import execute_test
from webxray.worker.testgen import generate_checkout_test, source_sha256

log = logging.getLogger(__name__)


class Blocked(Exception):
    pass




@dataclass
class State:
    public_pages: list[CrawledPage] = field(default_factory=list)
    auth_pages: list[CrawledPage] = field(default_factory=list)
    skipped: list[dict[str, str]] = field(default_factory=list)
    crawl_notes: list[str] = field(default_factory=list)
    redirects: dict[str, str] = field(default_factory=dict)
    auth_status: str = "not_attempted"
    auth_detail: str = ""
    auth_artifacts: dict[str, Any] = field(default_factory=dict)
    storage_state: dict[str, Any] | None = None
    secret: TestAccountSecret | None = None
    credential_id: uuid.UUID | None = None
    onboarding: dict[str, Any] = field(default_factory=dict)
    runs: list[RunResult] = field(default_factory=list)
    journey_id: uuid.UUID | None = None
    journey_definition: dict[str, Any] = field(default_factory=dict)
    finding_ids: list[uuid.UUID] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)
    tests: list[dict[str, Any]] = field(default_factory=list)

    @property
    def all_pages(self) -> list[CrawledPage]:
        return self.public_pages + self.auth_pages


class InvestigationRunner:
    def __init__(self, investigation_id: uuid.UUID) -> None:
        self.investigation_id = investigation_id
        self.settings = get_settings()
        self.policy = egress_policy()
        self.redactor = Redactor()
        self.state = State()

    async def run(self) -> None:
        async with session_scope() as s:
            inv = await s.get(Investigation, self.investigation_id)
            if inv is None:
                raise RuntimeError(f"investigation {self.investigation_id} not found")
            env = await s.get(Environment, inv.environment_id)
            assert env is not None
            cred = await s.get(CredentialSecret, inv.credential_id) if inv.credential_id else None
            self.inv_mode = inv.mode
            self.org_id, self.project_id = inv.org_id, inv.project_id
            self.env_id, self.origin = env.id, env.origin
            self.env_verified = env.verification_status == "verified"
            self.cfg = InvestigationConfig.model_validate(inv.config)
            if cred is not None:
                self.state.secret = decrypt_credential(cred.ciphertext)
                self.state.credential_id = cred.id
                self.redactor.add_secret(self.state.secret.password)
                self.redactor.add_secret(self.state.secret.username)
            inv.status = "running"
            inv.started_at = inv.started_at or datetime.now(UTC)
            inv.error = None
        self.scope = parse_origin(self.origin)
        self.rec = Recorder(self.investigation_id, self.org_id, self.project_id, get_artifact_store(), self.redactor)
        await self.rec.init()
        self.deadline = time.monotonic() + self.cfg.max_duration_s
        await self.rec.event("system", f"Investigation started against {self.origin} ({self.inv_mode} mode)", data={"config": self.cfg.model_dump()})

        final_status, error, blocked_reason = "completed", None, None
        try:
            await self._validate()
            session = BrowserSession(self.policy, self.scope, self.redactor, headless=self.settings.browser_headless)
            await session.start()
            try:
                await self._discover_public(session)
                await self._authenticate(session)
                await self._discover_authenticated(session)
                await self._build_features()
                plan = await self._plan()
                if plan is not None:
                    await self._execute(session, plan)
            finally:
                await session.close()
            await self._diagnose()
            await self._reproduce()
        except ControlRequested:
            final_status = "stopped"
            await self.rec.event("system", "Investigation stopped by user", level="warn")
        except Blocked as exc:
            final_status, blocked_reason = "blocked", str(exc)
            await self.rec.event("system", f"Investigation blocked: {exc}", level="warn")
        except Exception as exc:  # noqa: BLE001 - must record any failure
            final_status = "failed"
            error = self.redactor.text(f"{exc.__class__.__name__}: {exc}")[:2000]
            log.error("investigation %s failed:\n%s", self.investigation_id, self.redactor.text(traceback.format_exc()))
            await self.rec.event("system", f"Investigation failed: {error}", level="error")
        try:
            await self._report(final_status)
        except Exception:  # pragma: no cover
            log.exception("report compilation failed")
        await self.rec.update(
            status=final_status, error=error, blocked_reason=blocked_reason, finished_at=datetime.now(UTC),
            current_action=None, requested_control="none",
        )
        await self.rec.event("system", f"Investigation {final_status}")

    # ------------------------------------------------------------------ phases

    async def _validate(self) -> None:
        await self.rec.phase("validate")
        if not self.env_verified:
            await self.rec.phase("validate", "blocked", "target authorization is not verified")
            raise Blocked("The target environment has not been verified as authorized.")
        try:
            dest = await resolve_and_check(self.scope.host, self.scope.port, self.policy)
        except TargetRejected as exc:
            await self.rec.phase("validate", "blocked", exc.reason)
            raise Blocked(exc.reason) from exc
        detail = f"{self.scope} → {', '.join(dest.addresses)}" + (" (operator allowlist)" if dest.allowlisted_private else "")
        await self.rec.phase("validate", "done", detail)

    def _limits(self) -> CrawlLimits:
        return CrawlLimits(
            max_pages=self.cfg.max_pages, max_depth=self.cfg.max_depth, include_paths=self.cfg.include_paths,
            exclude_paths=self.cfg.exclude_paths, deadline=self.deadline,
        )

    async def _discover_public(self, session: BrowserSession) -> None:
        await self.rec.phase("discover_public")
        context, page, inst = await session.new_context(VIEWPORTS["desktop"])
        try:
            crawler = Crawler(session, self.rec, self.scope, self._limits())
            report = await crawler.crawl(page, inst, [str(self.scope) + self.cfg.start_path], "public")
        finally:
            await context.close()
        self.state.public_pages = report.pages
        self.state.skipped += report.skipped
        self.state.redirects.update(report.redirects)
        self.state.crawl_notes.append(f"Public discovery: {len(report.pages)} page(s); stopped because {report.stopped_reason}.")
        await self.rec.phase("discover_public", "done", f"{len(report.pages)} page(s) — {report.stopped_reason}")

    def _find_page(self, classification: str) -> CrawledPage | None:
        return next((p for p in self.state.public_pages if p.classification == classification), None)

    async def _store_generated_credential(self, identity: auth_flow.TestIdentity) -> uuid.UUID:
        async with session_scope() as s:
            cred = CredentialSecret(
                org_id=self.org_id, project_id=self.project_id, environment_id=self.env_id,
                label=f"Generated by investigation {str(self.investigation_id)[:8]}", source="generated",
                username_hint=mask_username(identity.email), ciphertext=encrypt_credential(identity.secret()),
                lifecycle_state="registration_pending", created_by_investigation_id=self.investigation_id,
            )
            s.add(cred)
            await s.flush()
            inv = await s.get(Investigation, self.investigation_id)
            assert inv is not None
            inv.credential_id = cred.id
            return cred.id

    async def _set_lifecycle(self, state: str) -> None:
        if self.state.credential_id is None:
            return
        async with session_scope() as s:
            cred = await s.get(CredentialSecret, self.state.credential_id)
            if cred is not None and cred.source == "generated":
                cred.lifecycle_state = state

    async def _mark_consequential(self) -> None:
        await self.rec.update(consequential_started=True)

    async def _login_fresh(self, session: BrowserSession) -> auth_flow.AuthOutcome | None:
        login_page = self._find_page("login")
        if login_page is None or self.state.secret is None:
            return None
        context, page, inst = await session.new_context(VIEWPORTS["desktop"])
        try:
            outcome = await auth_flow.login(page, inst, login_page.final_url, self.state.secret, self.rec)
            if outcome.status == "authenticated":
                onboarding = await auth_flow.complete_onboarding(page, inst, self.rec)
                if onboarding.status != "not_needed":
                    self.state.onboarding = {"status": onboarding.status, "steps": onboarding.steps, "detail": onboarding.detail}
                self.state.storage_state = await context.storage_state()
            return outcome
        finally:
            await context.close()

    async def _authenticate(self, session: BrowserSession) -> None:
        await self.rec.phase("authenticate")
        st = self.state
        if self.inv_mode == "authenticated":
            outcome = await self._login_fresh(session)
            if outcome is None:
                st.auth_status, st.auth_detail = "failed", "No login page was discovered."
            else:
                st.auth_status, st.auth_detail = outcome.status, outcome.detail
                st.auth_artifacts = outcome.artifacts.as_dict()
                if outcome.status in {"blocked_captcha", "mfa_required"}:
                    if await self.rec.wait_for_human(f"{outcome.detail} Complete the step in your own browser, then resume."):
                        retry = await self._login_fresh(session)
                        if retry is not None:
                            st.auth_status, st.auth_detail = retry.status, retry.detail
                            st.auth_artifacts = retry.artifacts.as_dict()
            await self._finish_auth_phase()
            return

        if not self.cfg.allow_registration:
            st.auth_status, st.auth_detail = "not_attempted", "Account creation was not approved; investigating public areas only."
            st.limitations.append("Pages for signed-in members weren't explored, because you didn't allow creating a test account.")
            await self.rec.phase("authenticate", "skipped", st.auth_detail)
            return
        register_page = self._find_page("register")
        if register_page is None:
            st.auth_status, st.auth_detail = "not_attempted", "No registration page was discovered."
            st.limitations.append("We didn't find a sign-up page, so pages for signed-in members weren't explored.")
            await self.rec.phase("authenticate", "skipped", st.auth_detail)
            return

        identity = auth_flow.TestIdentity.generate(self.settings.test_identity_email_domain)
        self.redactor.add_secret(identity.password)
        st.secret = identity.secret()
        st.credential_id = await self._store_generated_credential(identity)
        await self.rec.event("auth", f"Created designated test identity ({mask_username(identity.email)}); credentials stored encrypted")

        context, page, inst = await session.new_context(VIEWPORTS["desktop"])
        try:
            outcome = await auth_flow.register(page, inst, register_page.final_url, identity, self.rec, self._mark_consequential)
            await self.rec.event(
                "auth", f"Registration result: {outcome.status} — {outcome.detail}",
                level="info" if outcome.status == "registered" else "warn",
                data={"messages": outcome.messages, "final_url": outcome.final_url},
            )
            if outcome.status == "registered":
                await self._set_lifecycle("registered")
                onboarding = await auth_flow.complete_onboarding(page, inst, self.rec)
                st.onboarding = {"status": onboarding.status, "steps": onboarding.steps, "detail": onboarding.detail}
                await self.rec.event("auth", f"Onboarding: {onboarding.status}" + (f" — {onboarding.detail}" if onboarding.detail else ""))
                st.storage_state = await context.storage_state()
        finally:
            await context.close()

        if outcome.status == "verification_required":
            await self._set_lifecycle("verification_required")
            resumed = await self.rec.wait_for_human(
                "The site requires email/phone verification for the new test account. Complete verification, then resume."
            )
            if resumed:
                outcome = await self._login_fresh(session) or outcome
        elif outcome.status in {"blocked_captcha", "mfa_required", "needs_human"}:
            # Not something a resume can fix inside this run: a person must create the
            # account and start an authenticated investigation with it.
            st.limitations.append(f"Registration needs a human: {outcome.detail}")
            await self.rec.event(
                "auth", f"Human assistance required: {outcome.detail} Create a test account manually, add it as a "
                "credential, and start an authenticated investigation.", level="warn",
            )
        elif outcome.status == "outcome_unknown":
            # Never resubmit registration: determine what happened by logging in.
            await self.rec.event("auth", "Registration outcome unclear; checking by logging in instead of resubmitting")
            check = await self._login_fresh(session)
            if check is not None and check.status == "authenticated":
                outcome = auth_flow.AuthOutcome("registered", "Registration had succeeded (confirmed by logging in).", artifacts=check.artifacts)
                await self._set_lifecycle("registered")
            else:
                await self._set_lifecycle("outcome_unknown")
        elif outcome.status == "failed":
            await self._set_lifecycle("registration_failed")

        st.auth_status, st.auth_detail = outcome.status, outcome.detail
        if outcome.status in {"registered", "authenticated"}:
            # Verify the login flow with the new credentials in a clean context. This also
            # records the login locators reused by generated tests.
            login = await self._login_fresh(session)
            if login is not None and login.status == "authenticated":
                st.auth_artifacts = login.artifacts.as_dict()
                await self.rec.event("auth", "Verified login with the new test account in a fresh browser context")
            else:
                st.limitations.append("Logging back in with the new test account did not succeed; generated tests cannot log in.")
        await self._finish_auth_phase()

    async def _finish_auth_phase(self) -> None:
        st = self.state
        ok = st.storage_state is not None and st.auth_status in {"registered", "authenticated"}
        await self.rec.update(auth_state="authenticated" if ok else st.auth_status)
        if ok:
            await self.rec.phase("authenticate", "done", st.auth_detail)
        else:
            if st.auth_status not in {"not_attempted"}:
                st.limitations.append(f"Authentication did not complete ({st.auth_status}): {st.auth_detail}")
            await self.rec.phase("authenticate", "failed" if st.auth_status == "failed" else "blocked", st.auth_detail)

    async def _discover_authenticated(self, session: BrowserSession) -> None:
        if self.state.storage_state is None:
            await self.rec.phase("discover_authenticated", "skipped", "no authenticated session")
            return
        await self.rec.phase("discover_authenticated")
        seeds = [str(self.scope) + self.cfg.start_path]
        # Pages that redirected to login while anonymous are prime authenticated targets.
        seeds += [src for src, dst in self.state.redirects.items() if "login" in path_of(dst) or "signin" in path_of(dst)]
        context, page, inst = await session.new_context(VIEWPORTS["desktop"], self.state.storage_state)
        try:
            crawler = Crawler(session, self.rec, self.scope, self._limits())
            report = await crawler.crawl(page, inst, seeds, "authenticated")
            still_authed = await auth_flow.detect_auth_indicator(page) is not None
        finally:
            await context.close()
        self.state.auth_pages = report.pages
        self.state.skipped += report.skipped
        self.state.crawl_notes.append(f"Authenticated discovery: {len(report.pages)} page(s); stopped because {report.stopped_reason}.")
        if not still_authed:
            self.state.limitations.append("The session appeared logged out by the end of authenticated discovery.")
        await self.rec.phase("discover_authenticated", "done", f"{len(report.pages)} page(s) — {report.stopped_reason}")

    async def _build_features(self) -> None:
        st = self.state
        features: dict[str, dict[str, Any]] = {}

        def add(key: str, name: str, status: str, page: CrawledPage | None = None, **details: Any) -> None:
            if key in features and features[key]["status"] == "tested":
                return
            features[key] = {"name": name, "status": status, "page_url": page.final_url if page else None, "details": details}

        cls_map = {
            "listing": ("catalog", "Product catalog"), "product": ("product_detail", "Product detail"),
            "cart": ("cart", "Shopping cart"), "checkout": ("checkout", "Checkout"),
            "account": ("account", "Account / profile settings"), "orders": ("orders", "Order history"),
            "support": ("support", "Help & support"), "home": ("home", "Home page"),
            "onboarding": ("onboarding", "Onboarding"),
        }
        for p in st.all_pages:
            if p.classification in cls_map:
                key, name = cls_map[p.classification]
                add(key, name, "discovered", p, auth_state=p.auth_state)
            for f in p.inventory.get("forms", []):
                if any(fld.get("type") == "search" or "search" in (fld.get("name") or "") for fld in f["fields"]):
                    add("search", "Search", "discovered", p)
        reg = self._find_page("register")
        if reg:
            tested = st.auth_status in {"registered", "verification_required", "failed", "outcome_unknown"} and self.inv_mode == "autonomous" and self.cfg.allow_registration
            add("registration", "Registration", "tested" if tested else "untested", reg, result=st.auth_status if tested else None)
        login = self._find_page("login")
        if login:
            add("login", "Login", "tested" if st.auth_artifacts.get("indicator") else "untested", login,
                result="passed" if st.auth_artifacts.get("indicator") else None)
        if st.onboarding:
            add("onboarding", "Onboarding", "tested", None, result=st.onboarding.get("status"), steps=st.onboarding.get("steps"))
        if st.storage_state is None:
            for src, dst in st.redirects.items():
                if "login" in path_of(dst):
                    name = f"Protected area {path_of(src)}"
                    features[f"protected:{path_of(src)}"] = {
                        "name": name, "status": "needs_permission", "page_url": src,
                        "details": {"reason": "Redirected to login while unauthenticated"},
                    }
        if st.auth_status in {"verification_required", "blocked_captcha", "mfa_required", "needs_human"}:
            features["authenticated_area"] = {"name": "Authenticated area", "status": "needs_human", "page_url": None,
                                              "details": {"reason": st.auth_detail}}
        for key in list(features):
            if features[key]["status"] == "discovered" and key in {"account", "orders", "search", "catalog", "product_detail", "support", "home"}:
                features[key]["status"] = "untested"
                features[key]["details"]["note"] = "Inventoried; no automated journey for this feature in this version."
        async with session_scope() as s:
            for key, f in features.items():
                s.add(Feature(org_id=self.org_id, project_id=self.project_id, investigation_id=self.investigation_id,
                              key=key[:64], name=f["name"], status=f["status"], page_url=f["page_url"],
                              details=self.redactor.deep(f["details"])))
        self._features = features

    async def _set_feature(self, key: str, status: str, **details: Any) -> None:
        async with session_scope() as s:
            row = await s.scalar(select(Feature).where(Feature.investigation_id == self.investigation_id, Feature.key == key))
            if row is None:
                return
            row.status = status
            row.details = {**row.details, **self.redactor.deep(details)}

    async def _plan(self) -> Any:
        await self.rec.phase("plan")
        plan = plan_checkout(self.state.all_pages)
        if plan is None:
            self.state.limitations.append("We didn't find a product with an 'Add to cart' button, so checkout wasn't tried.")
            await self.rec.phase("plan", "done", "no checkout journey could be planned")
            await self.rec.phase("execute", "skipped", "no journeys planned")
            return None
        if self.state.storage_state is None:
            self.state.limitations.append("Checkout on this site needs a signed-in account, which we didn't have, so it wasn't tried.")
            await self.rec.phase("plan", "done", "checkout discovered but requires authentication")
            await self.rec.phase("execute", "skipped", "no authenticated session")
            return None
        definition = {
            "kind": "checkout",
            "product_path": path_of(plan.product_url),
            "product_title": plan.product_title,
            "cart_path": path_of(plan.cart_url) if plan.cart_url else None,
            "viewports": self.cfg.viewports,
            "allow_order_submission": self.cfg.allow_order_submission,
            "steps": ["reset_cart", "open_product", "add_to_cart", "open_cart", "begin_checkout", "fill_checkout",
                      "locate_submit", "submit_reachable", "submit_order"],
        }
        async with session_scope() as s:
            j = Journey(org_id=self.org_id, project_id=self.project_id, investigation_id=self.investigation_id,
                        key="checkout", name="Checkout", definition=definition, status="planned")
            s.add(j)
            await s.flush()
            self.state.journey_id = j.id
        self.state.journey_definition = definition
        await self.rec.phase("plan", "done", f"checkout via {path_of(plan.product_url)} on {', '.join(self.cfg.viewports)}")
        return plan

    async def _execute(self, session: BrowserSession, plan: Any) -> None:
        await self.rec.phase("execute")
        assert self.state.journey_id is not None
        for vname in self.cfg.viewports:
            vp = VIEWPORTS[vname]
            attempts = 1 + self.cfg.repeat_failed_runs
            for attempt in range(1, attempts + 1):
                if time.monotonic() > self.deadline:
                    self.state.limitations.append(f"Time budget exhausted before finishing {vp.label} runs.")
                    break
                run = CheckoutRun(
                    session, self.rec, plan, self.state.journey_definition, viewport=vp, attempt=attempt,
                    journey_id=self.state.journey_id, storage_state=self.state.storage_state,
                    allow_submit=self.cfg.allow_order_submission,
                )
                result = await run.execute()
                self.state.runs.append(result)
                if result.status == "passed":
                    break
                if attempt < attempts:
                    await self.rec.event("action", f"{vp.label} run failed; repeating to check reproducibility ({attempt + 1}/{attempts})")
        statuses = {r.status for r in self.state.runs}
        jstatus = "passed" if statuses == {"passed"} else ("failed" if "passed" not in statuses else "partial")
        async with session_scope() as s:
            j = await s.get(Journey, self.state.journey_id)
            assert j is not None
            j.status = jstatus
            j.definition = self.redactor.deep(self.state.journey_definition)
        by_vp = {}
        for r in self.state.runs:
            by_vp.setdefault(r.viewport.label, []).append(r.status)
        summary = "; ".join(f"{k}: {', '.join(v)}" for k, v in by_vp.items())
        await self._set_feature("checkout", "tested", result=jstatus, runs=summary)
        await self._set_feature("cart", "tested", result="exercised by checkout journey")
        await self._set_feature("product_detail", "tested", result="exercised by checkout journey")
        await self.rec.phase("execute", "done", summary)

    async def _diagnose(self) -> None:
        await self.rec.phase("diagnose")
        diagnosed: list[DiagnosedFinding] = []
        if self.state.runs:
            diagnosed += diagnose_checkout(self.state.runs)
            diagnosed += diagnose_layout(self.state.runs)
        diagnosed += diagnose_pages(self.state.all_pages)
        for d in diagnosed:
            fid = await self._persist_finding(d)
            self.state.finding_ids.append(fid)
        await self.rec.phase("diagnose", "done", f"{len(diagnosed)} finding(s)")

    async def _persist_finding(self, d: DiagnosedFinding) -> uuid.UUID:
        async with session_scope() as s:
            f = Finding(
                org_id=self.org_id, project_id=self.project_id, investigation_id=self.investigation_id,
                journey_id=self.state.journey_id if d.kind == "journey_failure" else None,
                dedupe_key=d.dedupe_key[:200], kind=d.kind, classification=d.classification, severity=d.severity,
                title=self.redactor.text(d.title), summary=self.redactor.text(d.summary),
                expected=self.redactor.text(d.expected) if d.expected else None,
                observed=self.redactor.text(d.observed) if d.observed else None,
                page_url=self.redactor.url(d.page_url) if d.page_url else None, viewport_name=d.viewport_name,
                reproduction=self.redactor.deep({**d.reproduction, **({"journey": d.journey_failure} if d.journey_failure else {})}),
                hypotheses=self.redactor.deep([h.as_dict() for h in d.hypotheses]),
                evidence_strength=d.evidence_strength, steps_to_reproduce=[self.redactor.text(x) for x in d.steps_to_reproduce],
                recommendation=self.redactor.text(d.recommendation) if d.recommendation else None, occurrences=d.occurrences,
            )
            s.add(f)
            await s.flush()
            ids = {uuid.UUID(str(e.evidence_id)) for e in d.evidence}
            valid = set((await s.scalars(select(Evidence.id).where(Evidence.id.in_(ids), Evidence.investigation_id == self.investigation_id))).all()) if ids else set()
            for e in d.evidence:
                eid = uuid.UUID(str(e.evidence_id))
                if eid in valid:
                    s.add(FindingEvidence(finding_id=f.id, evidence_id=eid, role=e.role[:48]))
                    valid.discard(eid)
            first_seq = await s.scalar(select(func.min(Evidence.event_seq)).where(Evidence.id.in_(ids))) if ids else None
            f.first_event_seq = first_seq
            fid = f.id
        await self.rec.event(
            "finding", f"{'Confirmed defect' if d.classification == 'confirmed_defect' else d.classification.capitalize()} · {d.severity}: {d.title}",
            level="error" if d.classification == "confirmed_defect" else ("warn" if d.classification == "warning" else "info"),
            data={"finding_id": str(fid), "severity": d.severity, "classification": d.classification, "kind": d.kind},
        )
        return fid

    async def _reproduce(self) -> None:
        await self.rec.phase("reproduce")
        async with session_scope() as s:
            findings = (await s.scalars(select(Finding).where(
                Finding.investigation_id == self.investigation_id, Finding.kind == "journey_failure"))).all()
        if not findings:
            await self.rec.phase("reproduce", "skipped", "no journey failures to reproduce")
            return
        auth = self.state.auth_artifacts
        done = 0
        for f in findings:
            await self.rec.checkpoint()
            vp_name = f.viewport_name or "desktop"
            vp = VIEWPORTS[vp_name]
            try:
                filename, source = generate_checkout_test(
                    finding_title=f.title, investigation_id=str(self.investigation_id), origin=str(self.scope),
                    viewport=vp.as_dict(), user_agent=vp.user_agent, definition=self.state.journey_definition, auth=auth,
                )
            except (ValueError, KeyError) as exc:
                await self.rec.event("system", f"Could not generate a reproduction test for '{f.title}': {exc}", level="warn")
                self.state.limitations.append(f"No reproduction test for '{f.title}': {exc}")
                continue
            test_id = await create_test(f.id, filename, source)
            await self.rec.event("system", f"Generated Playwright test {filename} (status: generated, not yet verified)",
                                 data={"test_id": str(test_id), "finding_id": str(f.id)})
            run_id = await create_test_run(self.org_id, self.project_id, test_id, source, requested_by=None)
            outcome = await run_test(run_id, recorder=self.rec)
            self.state.tests.append({"finding_id": str(f.id), "test_id": str(test_id), "outcome": outcome})
            done += 1
        await self.rec.phase("reproduce", "done", f"{done} test(s) generated and executed")

    async def _report(self, final_status: str) -> None:
        await self.rec.phase("report")
        st = self.state
        async with session_scope() as s:
            counts = dict((await s.execute(
                select(Finding.severity, func.count()).where(Finding.investigation_id == self.investigation_id).group_by(Finding.severity)
            )).all())
            classes = dict((await s.execute(
                select(Finding.classification, func.count()).where(Finding.investigation_id == self.investigation_id).group_by(Finding.classification)
            )).all())
            feats = dict((await s.execute(
                select(Feature.status, func.count()).where(Feature.investigation_id == self.investigation_id).group_by(Feature.status)
            )).all())
        skipped_reasons: dict[str, int] = {}
        for sk in st.skipped:
            skipped_reasons[sk["reason"]] = skipped_reasons.get(sk["reason"], 0) + 1
        limitations = list(dict.fromkeys(st.limitations + [
            "We find pages by following ordinary links. Pages you can only reach by pressing buttons, or that scripts create, weren't explored.",
            "Only checkout was tried from start to finish. Other features we found are listed, but weren't tested.",
            "There's no video replay of the browser. The evidence is screenshots, tap tests, page structure and the browser's logs.",
            "Problems were worked out from the evidence using fixed rules — no AI guesswork was involved.",
        ]))
        summary = {
            "final_status": final_status,
            "origin": str(self.scope),
            "pages": {"public": len(st.public_pages), "authenticated": len(st.auth_pages)},
            "crawl_notes": st.crawl_notes,
            "skipped_links": skipped_reasons,
            "auth": {"status": st.auth_status, "detail": st.auth_detail, "onboarding": st.onboarding,
                     "login_verified": bool(st.auth_artifacts.get("indicator"))},
            "features": feats,
            "journeys": {
                "checkout": {
                    "runs": [{"viewport": r.viewport.name, "attempt": r.attempt, "status": r.status, "failure_step": r.failure_step,
                              "run_id": str(r.run_id)} for r in st.runs]
                }
            } if st.runs else {},
            "findings": {"by_severity": counts, "by_classification": classes, "total": sum(counts.values())},
            "tests": st.tests,
            "viewports": self.cfg.viewports,
            "limitations": limitations,
            "egress_blocked": sum(len(p.signals.blocked_requests) for p in st.all_pages),
        }
        await self.rec.update(summary=self.redactor.deep(summary))
        await self.rec.phase("report", "done")


# --------------------------------------------------------------------------- tests


async def create_test(finding_id: uuid.UUID, filename: str, source: str) -> uuid.UUID:
    async with session_scope() as s:
        f = await s.get(Finding, finding_id)
        assert f is not None
        t = ReproductionTest(org_id=f.org_id, project_id=f.project_id, investigation_id=f.investigation_id, finding_id=f.id,
                             filename=filename, source=source, sha256=source_sha256(source), verification_status="generated")
        s.add(t)
        await s.flush()
        return t.id


async def create_test_run(org_id: uuid.UUID, project_id: uuid.UUID, test_id: uuid.UUID, source: str,
                          requested_by: uuid.UUID | None) -> uuid.UUID:
    async with session_scope() as s:
        r = TestRun(org_id=org_id, project_id=project_id, test_id=test_id, requested_by=requested_by,
                    status="queued", source_sha256=source_sha256(source))
        s.add(r)
        await s.flush()
        return r.id


async def run_test(run_id: uuid.UUID, recorder: Recorder | None = None) -> str:
    """Execute a queued TestRun and record the real outcome. Returns the outcome."""
    async with session_scope() as s:
        run = await s.get(TestRun, run_id)
        assert run is not None
        test = await s.get(ReproductionTest, run.test_id)
        assert test is not None
        inv = await s.get(Investigation, test.investigation_id)
        assert inv is not None
        env = await s.get(Environment, inv.environment_id)
        assert env is not None
        cred = await s.get(CredentialSecret, inv.credential_id) if inv.credential_id else None
        cfg = InvestigationConfig.model_validate(inv.config)
        run.status = "running"
        run.started_at = datetime.now(UTC)
        filename, source, finding_id, org_id, project_id, inv_id = test.filename, test.source, test.finding_id, test.org_id, test.project_id, inv.id
        origin = env.origin
        secret = decrypt_credential(cred.ciphertext) if cred else None
    redactor = Redactor([secret.password, secret.username] if secret else [])
    rec = recorder or Recorder(inv_id, org_id, project_id, get_artifact_store(), redactor)
    if recorder is None:
        await rec.init()
    if recorder is not None and secret:
        rec.redactor.add_secret(secret.password)
    await rec.action(f"Running reproduction test {filename}")
    await rec.event("system", f"Executing reproduction test {filename} in an isolated Node.js Playwright runner")
    try:
        result = await execute_test(
            filename=filename, source=source, origin=origin, secret=secret,
            allow_order_submission=cfg.allow_order_submission, policy=egress_policy(),
        )
    except Exception as exc:  # noqa: BLE001
        async with session_scope() as s:
            run = await s.get(TestRun, run_id)
            assert run is not None
            run.status, run.outcome = "error", "inconclusive"
            run.error_message = redactor.text(str(exc))[:2000]
            run.finished_at = datetime.now(UTC)
            test = await s.get(ReproductionTest, run.test_id)
            assert test is not None
            test.last_run_id = run.id
            test.verification_status = "inconclusive"
        await rec.event("system", f"Reproduction test could not run: {exc}", level="error")
        return "inconclusive"

    out_eid = await rec.evidence(
        "test_output", result.output or "(no output)", label=f"Playwright output for {filename}",
        meta={"test_run_id": str(run_id), "playwright_status": result.playwright_status, "outcome": result.outcome},
    )
    async with session_scope() as s:
        run = await s.get(TestRun, run_id)
        assert run is not None
        run.status = "finished"
        run.playwright_status = result.playwright_status
        run.outcome = result.outcome
        run.exit_code = result.exit_code
        run.duration_ms = result.duration_ms
        run.error_message = result.error_message[:4000] if result.error_message else None
        run.output_evidence_id = out_eid
        run.finished_at = datetime.now(UTC)
        test = await s.get(ReproductionTest, run.test_id)
        assert test is not None
        previous = test.verification_status
        test.last_run_id = run.id
        test.verification_status = result.outcome
        f = await s.get(Finding, finding_id)
        if f is not None:
            repro = {**f.reproduction, "test": {"test_id": str(test.id), "run_id": str(run.id), "outcome": result.outcome,
                                                "playwright_status": result.playwright_status}}
            if result.outcome == "not_reproduced" and previous in {"reproduced", "not_reproduced"} and repro.get("status") != "contradicted_by_test":
                # The test reproduced the defect before and passes now: the defect was fixed.
                # It stays a confirmed defect (it really happened); its status records the fix.
                repro["status"] = "fixed"
                repro["fixed_at"] = datetime.now(UTC).isoformat()
            elif result.outcome == "reproduced" and repro.get("status") == "fixed":
                repro["status"] = "reproducible"  # regressed after a fix
                repro.pop("fixed_at", None)
            elif result.outcome == "not_reproduced" and f.classification == "confirmed_defect":
                # The independent reproduction contradicts the investigation: never keep
                # presenting it as confirmed.
                f.classification = "warning"
                f.evidence_strength = "limited"
                repro["status"] = "contradicted_by_test"
                f.summary = (f.summary + " The generated reproduction test PASSED, contradicting the browser runs; "
                             "this finding is downgraded until the discrepancy is explained.")
            elif result.outcome == "reproduced" and repro.get("status") == "contradicted_by_test":
                repro["status"] = "reproducible"
            f.reproduction = repro
            s.add(FindingEvidence(finding_id=f.id, evidence_id=out_eid, role=f"test_output:{result.outcome}"))
    label = {"reproduced": "REPRODUCED the defect", "not_reproduced": "PASSED (defect not reproduced)", "inconclusive": "was INCONCLUSIVE"}[result.outcome]
    await rec.event(
        "system", f"Reproduction test {filename} {label} — Playwright status: {result.playwright_status}, {result.duration_ms} ms",
        level="error" if result.outcome == "reproduced" else ("info" if result.outcome == "not_reproduced" else "warn"),
        evidence_id=out_eid, data={"test_run_id": str(run_id), "outcome": result.outcome,
                                   "error": (result.error_message or "")[:500], "egress_denied": result.egress_denied},
    )
    return result.outcome


def origin_host(origin: str) -> str:
    return urlsplit(origin).hostname or origin
