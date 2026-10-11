"""Registration, login, and onboarding against the target site.

Rules enforced here:

* CAPTCHA, one-time codes, MFA and email/SMS verification are *detected and
  handed to a human*; they are never bypassed.
* A registration form is submitted at most once per investigation. If the
  outcome is unclear (timeout, unexpected page), the flow determines what
  happened by checking auth state and trying to log in — it never resubmits.
* Secret values are typed into fields but never written to events or logs.
"""

from __future__ import annotations

import re
import secrets
from dataclasses import dataclass, field
from typing import Any, Literal

from playwright.async_api import Error as PlaywrightError, Page

from webxray.security.crypto import TestAccountSecret
from webxray.worker.browser import Instrument, screenshot, settle
from webxray.worker.crawler import path_of
from webxray.worker.dom import INVENTORY_JS
from webxray.worker.locators import LocatorSpec, find_by_role, label_spec, resolve
from webxray.worker.recorder import Recorder

VERIFY_TEXT = re.compile(
    r"(verify your (email|account|phone)|confirm your email|check your (email|inbox)|"
    r"we('ve| have) sent (you )?(a|an) (email|code|link|text)|enter the (\d-digit )?code|verification code)",
    re.I,
)
MFA_TEXT = re.compile(r"(two-factor|2fa|authenticator app|one-time (pass)?code)", re.I)
ONBOARDING_PATH = re.compile(r"(onboard|welcome|setup|get-?started|getting-?started)", re.I)
LOGOUT_NAME = r"^\s*(log ?out|sign ?out|log ?off)\s*$"
CONTINUE_NAME = r"^\s*(continue|next|finish( setup)?|done|get started|complete|save( and continue)?|submit)\b"
TERMS = re.compile(r"(terms|agree|accept|privacy|conditions|policy)", re.I)
# Extra sign-in fields that are a human check (a simple CAPTCHA): "What is 3 + 4?",
# "Enter the code shown", "Security question". These are never answered automatically.
HUMAN_CHECK = re.compile(r"(captcha|\bcapt\b|security (question|code|check)|\banswer\b|are you (a )?human|verification|verify|code shown|sum of|\d\s*[+x*-]\s*\d)", re.I)
REMEMBER = re.compile(r"(remember|keep me|stay signed|trust this)", re.I)


@dataclass
class TestIdentity:
    __test__ = False
    name: str
    email: str
    password: str

    @classmethod
    def generate(cls, domain: str) -> TestIdentity:
        tag = secrets.token_hex(4)
        return cls(
            name="WEBXRAY Test User",
            email=f"webxray-{tag}@{domain}",
            password=secrets.token_urlsafe(12) + "aA1!",
        )

    def secret(self) -> TestAccountSecret:
        return TestAccountSecret(self.email, self.password)


@dataclass
class AuthArtifacts:
    """Non-secret details of the login flow, reused by generated tests."""

    login_path: str | None = None
    username_field: LocatorSpec | None = None
    password_field: LocatorSpec | None = None
    submit: LocatorSpec | None = None
    indicator: LocatorSpec | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "login_path": self.login_path,
            "username_field": self.username_field.as_dict() if self.username_field else None,
            "password_field": self.password_field.as_dict() if self.password_field else None,
            "submit": self.submit.as_dict() if self.submit else None,
            "indicator": self.indicator.as_dict() if self.indicator else None,
        }


AuthStatus = Literal[
    "registered",
    "authenticated",
    "verification_required",
    "blocked_captcha",
    "mfa_required",
    "failed",
    "outcome_unknown",
    "needs_human",
]


@dataclass
class AuthOutcome:
    status: AuthStatus
    detail: str
    messages: list[str] = field(default_factory=list)
    final_url: str | None = None
    artifacts: AuthArtifacts = field(default_factory=AuthArtifacts)
    evidence_ids: list[Any] = field(default_factory=list)


def field_purpose(f: dict[str, Any], password_index: int) -> str:
    t = (f.get("type") or "").lower()
    blob = " ".join(str(f.get(k) or "") for k in ("name", "label", "autocomplete", "placeholder", "id")).lower()
    if t == "password":
        if password_index > 0 or re.search(r"confirm|repeat|again|verify", blob):
            return "confirm_password"
        return "password"
    if t == "checkbox":
        return "terms" if TERMS.search(blob) else "checkbox"
    if t == "radio":
        return "radio"
    if f.get("tag") == "select":
        return "select"
    if t == "email" or "email" in blob or "e-mail" in blob:
        return "email"
    if re.search(r"given-name|first.?name", blob):
        return "first_name"
    if re.search(r"family-name|last.?name|surname", blob):
        return "last_name"
    if re.search(r"\bname\b|full.?name", blob):
        return "name"
    if re.search(r"user.?name|login", blob):
        return "username"
    if t == "tel" or "phone" in blob:
        return "phone"
    if t == "file":
        return "file"
    return "text"


async def _inventory(page: Page) -> dict[str, Any]:
    return await page.evaluate(INVENTORY_JS)


async def detect_auth_indicator(page: Page) -> LocatorSpec | None:
    spec = await find_by_role(page, ["link", "button", "menuitem"], LOGOUT_NAME)
    if spec is not None:
        return spec
    return await find_by_role(page, ["link", "button"], r"^\s*(my )?account\s*$|^\s*profile\s*$")


async def _submit_spec(page: Page, form: dict[str, Any]) -> LocatorSpec | None:
    for sub in form.get("submits", []):
        text = (sub.get("text") or "").strip()
        if text:
            spec = await find_by_role(page, ["button"], rf"^\s*{re.escape(text)}\s*$")
            if spec:
                return spec
        if sub.get("selector"):
            return LocatorSpec("css", css=sub["selector"])
    return None


async def _shot(page: Page, rec: Recorder, label: str) -> Any:
    try:
        data = await screenshot(page)
    except PlaywrightError:
        return None
    eid = await rec.evidence("screenshot", data, label=label, content_type="image/png", meta={"url": page.url, "masked": True})
    try:
        title = await page.title()
    except PlaywrightError:
        title = ""
    await rec.update(latest_screenshot_id=eid, current_url=page.url, current_title=title)
    return eid


async def _classify_after_submit(page: Page, inv: dict[str, Any]) -> tuple[str | None, str]:
    text = inv.get("text", "")
    if inv.get("captcha"):
        return "blocked_captcha", "A CAPTCHA challenge appeared."
    if inv.get("oneTimeCode") or MFA_TEXT.search(text):
        return "mfa_required", "The site requested a one-time or two-factor code."
    if VERIFY_TEXT.search(text):
        return "verification_required", "The site requires email/phone verification before continuing."
    return None, ""


async def register(
    page: Page, inst: Instrument, register_url: str, identity: TestIdentity, rec: Recorder, mark_consequential: Any
) -> AuthOutcome:
    await rec.action("Opening registration page")
    inst.mark("auth:register")
    await page.goto(register_url, wait_until="domcontentloaded")
    await settle(page)
    inv = await _inventory(page)
    if inv.get("captcha"):
        eid = await _shot(page, rec, "Registration page with CAPTCHA")
        return AuthOutcome("blocked_captcha", "Registration is protected by a CAPTCHA. A human must create the account.", evidence_ids=[eid])

    form = next((f for f in inv.get("forms", []) if any(x["type"] == "password" for x in f["fields"])), None)
    if form is None:
        return AuthOutcome("failed", "No registration form with a password field was found.")

    pw_index = 0
    plan: list[tuple[str, dict[str, Any]]] = []
    for fld in form["fields"]:
        if not fld.get("visible", True):
            continue
        purpose = field_purpose(fld, pw_index)
        if fld["type"] == "password":
            pw_index += 1
        plan.append((purpose, fld))

    if any(p == "file" and f.get("required") for p, f in plan):
        return AuthOutcome("needs_human", "Registration requires a file upload; human input is needed.")

    filled: list[str] = []
    for purpose, fld in plan:
        spec = await label_spec(page, fld.get("label", ""), fld["selector"])
        loc = resolve(page, spec)
        label = fld.get("label") or fld.get("name") or purpose
        try:
            if purpose == "email":
                await loc.fill(identity.email)
                filled.append(f"{label}: generated test email")
            elif purpose in {"password", "confirm_password"}:
                await loc.fill(identity.password)
                filled.append(f"{label}: generated password (secret)")
            elif purpose in {"name", "username"}:
                await loc.fill(identity.name if purpose == "name" else identity.email.split("@")[0])
                filled.append(f"{label}: test name")
            elif purpose == "first_name":
                await loc.fill("WEBXRAY")
                filled.append(f"{label}: test first name")
            elif purpose == "last_name":
                await loc.fill("Tester")
                filled.append(f"{label}: test last name")
            elif purpose == "terms" and fld.get("required"):
                await loc.check()
                filled.append(f"{label}: checked (required to register)")
            elif purpose == "select" and fld.get("required"):
                opt = next((o for o in fld.get("options") or [] if o["value"]), None)
                if opt:
                    await loc.select_option(opt["value"])
                    filled.append(f"{label}: {opt['text']}")
            elif purpose in {"text", "phone"} and fld.get("required"):
                await loc.fill("5550100" if purpose == "phone" else "WEBXRAY test")
                filled.append(f"{label}: placeholder test value")
        except PlaywrightError as exc:
            return AuthOutcome("failed", f"Could not fill registration field '{label}': {str(exc).splitlines()[0][:160]}")
    await rec.event("auth", "Filled registration form", data={"fields": filled, "email_domain": identity.email.split("@")[1]})

    submit = await _submit_spec(page, form)
    if submit is None:
        return AuthOutcome("failed", "Could not identify the registration submit button.")
    before = await _shot(page, rec, "Registration form before submit")

    # Point of no return: from here on, automatic retries must not resubmit.
    await mark_consequential()
    await rec.event("auth", f"Submitting registration form ({submit.describe()}) — single attempt")
    inst.mark("auth:register:submit")
    submit_error: str | None = None
    try:
        await resolve(page, submit).click()
    except PlaywrightError as exc:
        submit_error = str(exc).splitlines()[0][:200]
    await settle(page, idle_ms=4000)
    after = await _shot(page, rec, "Page after registration submit")

    try:
        inv2 = await _inventory(page)
    except PlaywrightError:
        inv2 = {}
    blocked, why = await _classify_after_submit(page, inv2)
    if blocked:
        return AuthOutcome(blocked, why, final_url=page.url, evidence_ids=[before, after])  # type: ignore[arg-type]
    indicator = await detect_auth_indicator(page)
    if indicator is not None:
        return AuthOutcome(
            "registered", "Registration succeeded and the session is authenticated.",
            final_url=page.url, artifacts=AuthArtifacts(indicator=indicator), evidence_ids=[before, after],
        )
    still_on_form = path_of(page.url) == path_of(register_url) and int(inv2.get("passwordFields") or 0) >= 1
    if still_on_form and inv2.get("alerts"):
        return AuthOutcome(
            "failed", "The site rejected the registration.", messages=inv2.get("alerts", []),
            final_url=page.url, evidence_ids=[before, after],
        )
    detail = "Registration outcome is unclear"
    if submit_error:
        detail += f" (submit raised: {submit_error})"
    return AuthOutcome("outcome_unknown", detail + ".", final_url=page.url, evidence_ids=[before, after])


async def login(page: Page, inst: Instrument, login_url: str, secret: TestAccountSecret, rec: Recorder) -> AuthOutcome:
    await rec.action("Logging in with the test account")
    inst.mark("auth:login")
    await page.goto(login_url, wait_until="domcontentloaded")
    await settle(page)
    inv = await _inventory(page)
    if inv.get("captcha"):
        eid = await _shot(page, rec, "Login page with CAPTCHA")
        return AuthOutcome("blocked_captcha", "Login is protected by a CAPTCHA; a human must provide a session.", evidence_ids=[eid])
    form = next((f for f in inv.get("forms", []) if sum(x["type"] == "password" for x in f["fields"]) == 1), None)
    if form is None:
        return AuthOutcome("failed", "No login form with a single password field was found.")
    # The account name field may be called username, email, ID, phone, account number…
    # Whatever it is called, it is the first visible text-like field before the password.
    pw_index = next(i for i, f in enumerate(form["fields"]) if f["type"] == "password")
    candidates = [
        f for f in form["fields"][:pw_index]
        if f["type"] in {"email", "text", "tel", "number", "search", ""} and f.get("visible", True)
    ] or [f for f in form["fields"] if f["type"] in {"email", "text", "tel", "number"} and f.get("visible", True)]
    user_fld = next((f for f in candidates if field_purpose(f, 0) in {"email", "username"}), candidates[0] if candidates else None)
    pw_fld = form["fields"][pw_index]
    if user_fld is None:
        return AuthOutcome("failed", "Login form has no username/email field.")
    others = [
        f for f in form["fields"]
        if f is not user_fld and f is not pw_fld and f.get("visible", True) and f["type"] not in {"checkbox", "radio", "hidden"}
    ]
    blob = lambda f: " ".join(str(f.get(k) or "") for k in ("name", "label", "placeholder", "id"))  # noqa: E731
    human = next((f for f in others if HUMAN_CHECK.search(blob(f))), None)
    if human is not None or inv.get("captcha"):
        eid = await _shot(page, rec, "Login page with a human check")
        return AuthOutcome(
            "blocked_captcha",
            "The sign-in form asks a security question or code to prove you're human. We never answer those automatically.",
            evidence_ids=[eid],
        )
    if any(f.get("required") for f in others):
        eid = await _shot(page, rec, "Login page with extra required fields")
        names = ", ".join((f.get("label") or f.get("name") or f["type"]) for f in others if f.get("required"))
        return AuthOutcome("failed", f"The sign-in form needs more than a username and password ({names}).", evidence_ids=[eid])
    user_spec = await label_spec(page, user_fld.get("label", ""), user_fld["selector"])
    pw_spec = await label_spec(page, pw_fld.get("label", ""), pw_fld["selector"])
    submit = await _submit_spec(page, form)
    if submit is None:
        return AuthOutcome("failed", "Could not identify the login submit button.")
    await resolve(page, user_spec).fill(secret.username)
    await resolve(page, pw_spec).fill(secret.password)
    await rec.event("auth", f"Submitting login form ({submit.describe()}); credentials supplied from the secret store")
    try:
        await resolve(page, submit).click()
    except PlaywrightError as exc:
        return AuthOutcome("failed", f"Login submit failed: {str(exc).splitlines()[0][:160]}")
    await settle(page, idle_ms=4000)
    eid = await _shot(page, rec, "Page after login")
    inv2 = await _inventory(page)
    blocked, why = await _classify_after_submit(page, inv2)
    artifacts = AuthArtifacts(login_path=path_of(login_url), username_field=user_spec, password_field=pw_spec, submit=submit)
    if blocked:
        return AuthOutcome(blocked, why, final_url=page.url, artifacts=artifacts, evidence_ids=[eid])  # type: ignore[arg-type]
    indicator = await detect_auth_indicator(page)
    if indicator is None:
        # No "log out"/"account" control — sites word these differently. A login that
        # leaves the sign-in form behind (no password field, no error shown) succeeded.
        left_form = int(inv2.get("passwordFields") or 0) == 0 and not inv2.get("alerts")
        if left_form:
            return AuthOutcome("authenticated", "Logged in (the sign-in form went away).", final_url=page.url, artifacts=artifacts, evidence_ids=[eid])
        return AuthOutcome(
            "failed", "Login did not produce an authenticated session.", messages=inv2.get("alerts", []),
            final_url=page.url, artifacts=artifacts, evidence_ids=[eid],
        )
    artifacts.indicator = indicator
    return AuthOutcome("authenticated", "Logged in.", final_url=page.url, artifacts=artifacts, evidence_ids=[eid])


@dataclass
class OnboardingOutcome:
    status: Literal["not_needed", "completed", "stuck", "blocked"]
    steps: list[str]
    detail: str = ""


async def complete_onboarding(page: Page, inst: Instrument, rec: Recorder, max_steps: int = 6) -> OnboardingOutcome:
    steps: list[str] = []
    for i in range(max_steps):
        await rec.checkpoint()
        if not ONBOARDING_PATH.search(path_of(page.url)):
            return OnboardingOutcome("completed" if i else "not_needed", steps)
        inst.mark(f"auth:onboarding:{i + 1}")
        inv = await _inventory(page)
        if inv.get("captcha"):
            return OnboardingOutcome("blocked", steps, "Onboarding presented a CAPTCHA.")
        blocked, why = await _classify_after_submit(page, inv)
        if blocked:
            return OnboardingOutcome("blocked", steps, why)
        form = next((f for f in inv.get("forms", []) if f.get("submits")), None)
        if form is None:
            return OnboardingOutcome("stuck", steps, "Onboarding page has no form to continue.")
        actions: list[str] = []
        checkboxes = [f for f in form["fields"] if f["type"] == "checkbox" and f.get("visible", True)]
        if checkboxes and not any(f.get("hasValue") for f in checkboxes):
            first = checkboxes[0]
            await resolve(page, await label_spec(page, first.get("label", ""), first["selector"])).check()
            actions.append(f"checked '{first.get('label')}'")
        radios = [f for f in form["fields"] if f["type"] == "radio" and f.get("visible", True)]
        if radios and not any(f.get("hasValue") for f in radios):
            await resolve(page, await label_spec(page, radios[0].get("label", ""), radios[0]["selector"])).check()
            actions.append(f"selected '{radios[0].get('label')}'")
        for fld in form["fields"]:
            if fld.get("tag") == "select" and not fld.get("hasValue"):
                opt = next((o for o in fld.get("options") or [] if o["value"]), None)
                if opt:
                    await resolve(page, await label_spec(page, fld.get("label", ""), fld["selector"])).select_option(opt["value"])
                    actions.append(f"chose '{opt['text']}' for '{fld.get('label')}'")
            elif fld["type"] in {"text", "textarea"} and fld.get("required") and not fld.get("hasValue"):
                await resolve(page, await label_spec(page, fld.get("label", ""), fld["selector"])).fill("WEBXRAY test")
                actions.append(f"filled '{fld.get('label')}'")
        button = await find_by_role(page, ["button"], CONTINUE_NAME) or await _submit_spec(page, form)
        if button is None:
            return OnboardingOutcome("stuck", steps, "No continue button found.")
        before_url = page.url
        await resolve(page, button).click()
        await settle(page)
        step_desc = f"Step {i + 1}: " + (", ".join(actions) if actions else "no input needed") + f"; clicked {button.describe()}"
        steps.append(step_desc)
        await rec.event("auth", f"Onboarding {step_desc}", page_url=before_url)
        if page.url == before_url:
            inv_after = await _inventory(page)
            if inv_after.get("alerts"):
                return OnboardingOutcome("stuck", steps, "Onboarding rejected input: " + "; ".join(inv_after["alerts"][:2]))
    return OnboardingOutcome("stuck", steps, f"Onboarding did not finish within {max_steps} steps.")
