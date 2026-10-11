"""Briefing runner: read a handful of public pages and describe the website.

Safety model (a briefing does not need a verified target, so it is narrower
than an investigation):

* Every connection goes through the per-run egress proxy: public addresses
  only, unless an operator allowlisted an origin.
* Only GET navigations to same-origin links. Nothing is clicked, typed or
  submitted; dialogs are dismissed; popups are closed.
* robots.txt is honoured for the WEB-X-RAY user agent (and ``*``) on public pages.
* Optional sign-in, only with an account the user supplied and confirmed. The
  login form is the one form a briefing ever submits. The credential is wiped
  from the database as soon as the worker has read it, is registered with the
  redactor (never stored in steps, results or logs), and password fields are
  masked in screenshots. CAPTCHA, one-time codes and MFA are reported, never
  bypassed. Signed-in pages are read on the user's behalf, so robots.txt (which
  addresses crawlers) is not applied to them; the report says so.
* Small fixed budget: a few pages, one viewport, a short time limit and a
  byte budget on the proxy.
"""

from __future__ import annotations

import contextlib
import logging
import re
import time
import uuid
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

from playwright.async_api import Error as PlaywrightError, Page
from sqlalchemy import update

from webxray.config import get_settings
from webxray.db import session_scope
from webxray.models import Briefing
from webxray.security.crypto import TestAccountSecret, decrypt_credential
from webxray.security.redaction import Redactor
from webxray.security.target_policy import TargetRejected, parse_origin, resolve_and_check
from webxray.services.briefing import ReadPage, Visit, build_briefing, pick_pages
from webxray.services.policy import egress_policy
from webxray.storage.artifacts import get_artifact_store
from webxray.worker.browser import VIEWPORTS, BrowserSession, Instrument, screenshot, settle
from webxray.worker import auth_flow
from webxray.worker.crawler import NON_HTML_EXT, SKIP_LINK, classify, normalize_url, path_of
from webxray.worker.dom import INVENTORY_JS

log = logging.getLogger(__name__)

MAX_PAGES = 8
MAX_SIGNED_IN_PAGES = 6
TIME_BUDGET_S = 120
SIGNED_IN_EXTRA_S = 90
BYTE_BUDGET = 96 * 1024 * 1024
ROBOTS_AGENT = "WEB-X-RAY"

# Read-only probe for the facts a briefing needs beyond the shared inventory.
BRIEFING_META_JS = r"""() => {
  const clip = (s, n) => (s || '').replace(/\s+/g, ' ').trim().slice(0, n);
  const meta = (sel) => clip((document.querySelector(sel) || {}).content || '', 500);
  const types = new Set(), names = [], orgNames = [];
  let address = '';
  const walk = (node, depth) => {
    if (!node || depth > 4) return;
    if (Array.isArray(node)) { node.slice(0, 30).forEach(n => walk(n, depth + 1)); return; }
    if (typeof node !== 'object') return;
    const t = node['@type'];
    (Array.isArray(t) ? t : [t]).filter(Boolean).forEach(x => types.add(String(x).slice(0, 40)));
    const isOrg = (Array.isArray(t) ? t : [t]).some(x => /Organization|Corporation|LocalBusiness|Store|Restaurant|NGO/.test(String(x)));
    if (node.name && typeof node.name === 'string') {
      if ((Array.isArray(t) ? t : [t]).includes('WebSite')) names.push(clip(node.name, 80));
      if (isOrg) orgNames.push(clip(node.name, 80));
    }
    if (node.address && !address) {
      const a = node.address;
      address = typeof a === 'string' ? clip(a, 200)
        : clip([a.streetAddress, a.addressLocality, a.addressRegion, a.postalCode, a.addressCountry && (a.addressCountry.name || a.addressCountry)].filter(Boolean).join(', '), 200);
    }
    if (node['@graph']) walk(node['@graph'], depth + 1);
    for (const k of ['publisher', 'author', 'brand', 'provider', 'mainEntity', 'itemListElement', 'offers']) if (node[k]) walk(node[k], depth + 1);
  };
  document.querySelectorAll('script[type="application/ld+json"]').forEach((s, i) => {
    if (i > 10) return;
    try { walk(JSON.parse(s.textContent || ''), 0); } catch (e) {}
  });
  const hrefs = [...document.querySelectorAll('a[href]')].slice(0, 600).map(a => a.href);
  const emails = [...new Set(hrefs.filter(h => h.startsWith('mailto:')).map(h => decodeURIComponent(h.slice(7).split('?')[0])).filter(e => /^[^@\s]+@[^@\s]+\.[a-z]{2,}$/i.test(e)))].slice(0, 5);
  const phones = [...new Set(hrefs.filter(h => h.startsWith('tel:')).map(h => decodeURIComponent(h.slice(4)).trim()))].slice(0, 5);
  const SOCIAL = /^(www\.)?(twitter|x|facebook|instagram|linkedin|youtube|github|tiktok|pinterest|threads|reddit|bsky|discord)\.(com|net|app|gg)$|^mastodon\.social$/i;
  const social = [...new Set(hrefs.filter(h => { try { return SOCIAL.test(new URL(h).hostname); } catch (e) { return false; } }))].slice(0, 12);
  const appLinks = hrefs.some(h => /apps\.apple\.com|play\.google\.com\/store/.test(h));
  const main = document.querySelector('main, [role=main], article') || document.body;
  const paragraphs = main ? [...main.querySelectorAll('p')].map(p => clip(p.innerText, 400)).filter(t => t.length > 40).slice(0, 4) : [];
  // Main content only (no header/nav/footer chrome), keeping line breaks so sentences stay separate.
  const text = main ? (main.innerText || '').replace(/[ \t\u00a0]+/g, ' ').replace(/\n\s*\n+/g, '\n').trim().slice(0, 12000) : '';
  const priceRe = /(?:[$€£¥]\s?\d[\d,]*(?:\.\d{1,2})?|\d[\d,]*(?:\.\d{1,2})?\s?(?:USD|EUR|GBP))(?:\s?(?:\/|per)\s?(?:mo|month|yr|year|user|seat))?/g;
  const prices = [...new Set((document.body ? document.body.innerText : '').match(priceRe) || [])].slice(0, 10).map(p => clip(p, 30));
  const w = window;
  const has = (sel) => !!document.querySelector(sel);
  const tech = [];
  if (w.__NEXT_DATA__ || has('script[src*="/_next/"]')) tech.push('next');
  if (w.__NUXT__ || has('script[src*="/_nuxt/"]')) tech.push('nuxt');
  if (has('#___gatsby')) tech.push('gatsby');
  if (has('link[href*="wp-content"], script[src*="wp-content"], script[src*="wp-includes"]')) tech.push('wordpress');
  if (w.Shopify || has('script[src*="cdn.shopify.com"]')) tech.push('shopify');
  if (has('meta[name="generator"][content*="Wix"]') || has('script[src*="static.parastorage.com"]')) tech.push('wix');
  if (w.Squarespace || has('script[src*="squarespace"]')) tech.push('squarespace');
  if (has('html[data-wf-site]')) tech.push('webflow');
  if (has('[ng-version]')) tech.push('angular');
  if (has('[data-v-app], [data-server-rendered]') || w.__VUE__) tech.push('vue');
  if (has('[data-reactroot]') || w.__REACT_DEVTOOLS_GLOBAL_HOOK__ && w.__REACT_DEVTOOLS_GLOBAL_HOOK__.renderers && w.__REACT_DEVTOOLS_GLOBAL_HOOK__.renderers.size) tech.push('react');
  if (has('[class*="svelte-"]')) tech.push('svelte');
  if (has('astro-island')) tech.push('astro');
  if (w.__remixContext) tech.push('remix');
  if (w.jQuery) tech.push('jquery');
  if (has('script[src*="js.hs-scripts.com"]')) tech.push('hubspot');
  if (has('script[src*="framerusercontent"]')) tech.push('framer');
  const footer = document.querySelector('footer, [role=contentinfo]');
  return {
    description: meta('meta[name="description"]'),
    og_description: meta('meta[property="og:description"]'),
    og_site_name: meta('meta[property="og:site_name"]'),
    application_name: meta('meta[name="application-name"]'),
    generator: meta('meta[name="generator"]'),
    lang: clip(document.documentElement.lang, 12),
    canonical: (document.querySelector('link[rel=canonical]') || {}).href || '',
    jsonld_types: [...types].slice(0, 20), jsonld_names: names.slice(0, 3), jsonld_org_names: orgNames.slice(0, 3),
    address, emails, phones, social, app_links: appLinks, paragraphs, prices, tech,
    has_search: has('input[type=search], form[role=search], input[name=q], input[name=query], input[name=search], input[name=s]'),
    footer: footer ? clip(footer.innerText, 1200) : '',
    text,
  };
}"""


class BriefingBlocked(Exception):
    pass


BOT_WALL = re.compile(r"(just a moment|attention required|checking your browser|verify you are human|access denied|are you a robot|ddos protection)", re.I)
LOGIN_LINK = re.compile(r"\b(log ?in|sign ?in)\b", re.I)
LOGIN_PATH = re.compile(r"/(log-?in|sign-?in|signin|account/login|users/sign_in|auth/login)(/|$)", re.I)
MEMBER_PATH = re.compile(r"\b(account|profile|dashboard|orders?|settings|billing|subscriptions?|my-|library|inbox|projects?)\b", re.I)


class _AuthRecorder:
    """The slice of worker.recorder.Recorder that auth_flow.login() uses, mapped onto a briefing.

    Events are dropped (they describe locators, not something a reader needs);
    screenshots become briefing shots so the sign-in is visible in the report.
    """

    def __init__(self, runner: BriefingRunner, page: Page) -> None:
        self.runner, self.page = runner, page

    async def action(self, message: str, **_: Any) -> None:
        await self.runner.step("Signing in with the account you provided")

    async def event(self, *_: Any, **__: Any) -> int:
        return 0

    async def update(self, **_: Any) -> None:
        return None

    async def evidence(self, kind: str, data: Any, *, label: str, **_: Any) -> int | None:
        if kind != "screenshot" or not isinstance(data, bytes):
            return None
        return self.runner._store_shot(data, self.page.url, label, signed_in=True)


class BriefingRunner:
    def __init__(self, briefing_id: uuid.UUID) -> None:
        self.briefing_id = briefing_id
        self.settings = get_settings()
        self.policy = egress_policy()
        self.redactor = Redactor()
        self.store = get_artifact_store()
        self.steps: list[dict[str, Any]] = []
        self.shots: list[dict[str, Any]] = []

    # ------------------------------------------------------------------ persistence

    async def _update(self, **values: Any) -> None:
        async with session_scope() as s:
            await s.execute(update(Briefing).where(Briefing.id == self.briefing_id).values(**values))

    async def step(self, message: str, *, url: str | None = None) -> None:
        message = self.redactor.text(message)[:300]
        self.steps.append({"ts": datetime.now(UTC).isoformat(), "message": message})
        values: dict[str, Any] = {"steps": list(self.steps[-60:]), "current_action": message}
        if url is not None:
            values["current_url"] = self.redactor.url(url)
        await self._update(**values)

    def _store_shot(self, data: bytes, url: str, title: str, *, signed_in: bool = False) -> int:
        key = f"briefings/{self.briefing_id}/{len(self.shots)}.png"
        stored = self.store.put(key, data)
        self.shots.append({"key": key, "sha256": stored.sha256, "url": self.redactor.url(url),
                           "title": self.redactor.text(title)[:200], "signed_in": signed_in})
        return len(self.shots) - 1

    async def _shot(self, page: Page, url: str, title: str, *, signed_in: bool = False) -> None:
        with contextlib.suppress(PlaywrightError):
            self._store_shot(await screenshot(page), url, title, signed_in=signed_in)
            await self._update(shots=list(self.shots))

    # ------------------------------------------------------------------ run

    async def run(self) -> None:
        async with session_scope() as s:
            b = await s.get(Briefing, self.briefing_id)
            if b is None:
                raise RuntimeError(f"briefing {self.briefing_id} not found")
            start_url, question = b.url, b.question
            b.status, b.started_at, b.error = "running", b.started_at or datetime.now(UTC), None
            b.steps, b.shots = [], []
            self.login_url, self.secret, self.credential_hint = b.login_url, None, b.credential_hint
            if b.credential_ciphertext is not None:
                self.secret = decrypt_credential(b.credential_ciphertext)
                self.redactor.add_secret(self.secret.password)
                self.redactor.add_secret(self.secret.username)
            elif b.auth_status == "pending":
                # A previous attempt was interrupted after the credential had been wiped.
                b.auth_status = "failed"
                b.auth_detail = "The sign-in details were deleted after an interrupted attempt. Ask again to sign in."
            # Wipe the stored credential now: it lives in this process's memory only.
            b.credential_ciphertext = None
        self.auth_status: str | None = None
        self.auth_detail: str | None = None

        status, error, result = "completed", None, None
        t0 = time.monotonic()
        try:
            visit = await self._visit(start_url, question)
            visit.duration_ms = int((time.monotonic() - t0) * 1000)
            if visit.origin != parse_origin(start_url).__str__():
                await self._update(origin=visit.origin)  # followed a redirect or fell back to http
            await self.step("Writing the briefing")
            result = self.redactor.deep(build_briefing(visit))
        except BriefingBlocked as exc:
            status, error = "blocked", str(exc)
        except TargetRejected as exc:
            status, error = "failed", exc.reason
        except Exception as exc:  # noqa: BLE001 — surfaced to the user, logged with stack
            log.exception("briefing %s failed", self.briefing_id)
            status, error = "failed", f"The visit failed unexpectedly ({exc.__class__.__name__})."
        self.secret = None
        values: dict[str, Any] = {}
        if self.auth_status is not None:
            values = {"auth_status": self.auth_status, "auth_detail": self.auth_detail}
        elif self.credential_hint and status != "completed":
            values = {"auth_status": "failed", "auth_detail": "The briefing stopped before it could sign in."}
        await self._update(
            status=status, error=error, result=result or {}, finished_at=datetime.now(UTC),
            current_action="Done" if status == "completed" else None, credential_ciphertext=None, **values,
        )

    async def _visit(self, start_url: str, question: str) -> Visit:
        scope = parse_origin(start_url)
        await self.step(f"Checking that {scope.host} is a public website")
        await resolve_and_check(scope.host, scope.port, self.policy)
        deadline = time.monotonic() + TIME_BUDGET_S + (SIGNED_IN_EXTRA_S if self.secret else 0)
        session = BrowserSession(self.policy, scope, self.redactor, headless=self.settings.browser_headless, byte_budget=BYTE_BUDGET)
        await session.start()
        try:
            context, page, inst = await session.new_context(VIEWPORTS["desktop"])
            try:
                return await self._read(session, page, inst, start_url, question, deadline)
            finally:
                with contextlib.suppress(Exception):
                    await context.close()
        finally:
            await session.close()

    async def _robots(self, page: Page, origin: str) -> RobotFileParser | None:
        robots = RobotFileParser()
        try:
            response = await page.goto(f"{origin}/robots.txt", wait_until="domcontentloaded")
        except PlaywrightError:
            return None
        if response is None or response.status >= 400:
            return None
        with contextlib.suppress(PlaywrightError):
            body = await response.text()
            if "html" in (response.headers.get("content-type") or "") and "user-agent" not in body.lower():
                return None
            robots.parse(body.splitlines())
            return robots
        return None

    @staticmethod
    def _allowed(robots: RobotFileParser | None, url: str) -> bool:
        return robots is None or robots.can_fetch(ROBOTS_AGENT, url)

    async def _open(self, page: Page, inst: Instrument, url: str) -> tuple[int | None, dict[str, str]] | None:
        try:
            response = await page.goto(url, wait_until="domcontentloaded")
        except PlaywrightError as exc:
            await self.step(f"Couldn't open {path_of(url)}: {str(exc).splitlines()[0][:120]}", url=url)
            return None
        await settle(page, idle_ms=2000)
        headers = {}
        if response is not None:
            headers = {k: v for k, v in response.headers.items() if k in {"server", "x-powered-by"}}
        return (response.status if response else None), headers

    async def _inspect(
        self, page: Page, url: str, status: int | None, headers: dict[str, str], *, signed_in: bool = False
    ) -> ReadPage | None:
        try:
            inv: dict[str, Any] = await page.evaluate(INVENTORY_JS)
            meta: dict[str, Any] = await page.evaluate(BRIEFING_META_JS)
        except PlaywrightError:
            return None
        meta["headers"] = headers
        text = meta.pop("text", "") or ""
        final = normalize_url(page.url) or url
        title = self.redactor.text(inv.get("title") or "")[:300]
        inv.pop("text", None)
        return ReadPage(
            url=final, path=path_of(final), status=status, title=title, kind=classify(final, inv),
            inventory=self.redactor.deep(inv), meta=self.redactor.deep(meta), text=self.redactor.text(text),
            signed_in=signed_in,
        )

    async def _read(
        self, session: BrowserSession, page: Page, inst: Instrument, start_url: str, question: str, deadline: float
    ) -> Visit:
        scope = session.scope
        visit = Visit(origin=str(scope), pages=[], question=question)
        start = normalize_url(start_url) or start_url

        await self.step("Reading robots.txt to see which pages the site lets automated visitors read")
        robots = await self._robots(page, str(scope))
        inst.blocked_navigations.clear()  # a robots.txt redirect is not the home page's
        if not self._allowed(robots, start):
            raise BriefingBlocked("This site's robots.txt asks automated visitors not to read its home page, so we didn't.")

        await self._allow_twin(session, scope)
        await self.step(f"Opening {start}", url=start)
        opened = await self._open(page, inst, start)
        # Follow one redirect to the same site's canonical origin (http→https, bare→www).
        moved = next((b["url"] for b in inst.blocked_navigations if b.get("url", "").startswith("http")), None)
        if moved:
            new_scope = parse_origin(moved)
            if new_scope.host.removeprefix("www.") != scope.host.removeprefix("www."):
                raise BriefingBlocked(
                    f"{scope.host} sends visitors to a different website ({new_scope.host}). "
                    "Start a briefing for that address instead."
                )
            await resolve_and_check(new_scope.host, new_scope.port, self.policy)
            await self.step(f"{scope.host} redirects to {new_scope}; following it")
            session.scope = inst.scope = scope = new_scope
            visit.origin = str(scope)
            inst.blocked_navigations.clear()
            start = normalize_url(moved) or moved
            robots = await self._robots(page, str(scope))
            inst.blocked_navigations.clear()
            if not self._allowed(robots, start):
                raise BriefingBlocked("This site's robots.txt asks automated visitors not to read its home page, so we didn't.")
            opened = await self._open(page, inst, start)
        if opened is None and scope.scheme == "https":
            # Like a browser: if the secure address doesn't answer, try the plain one once.
            plain_start = "http://" + start.split("://", 1)[1]
            await self.step(f"{scope.host} didn't answer over https; trying http")
            session.scope = inst.scope = scope = parse_origin(plain_start)
            visit.origin = str(scope)
            inst.blocked_navigations.clear()
            robots = await self._robots(page, str(scope))
            inst.blocked_navigations.clear()
            if not self._allowed(robots, plain_start):
                raise BriefingBlocked("This site's robots.txt asks automated visitors not to read its home page, so we didn't.")
            opened = await self._open(page, inst, plain_start)
            if opened is not None:
                start = plain_start
                visit.notes.append("The site doesn't offer a secure (https) connection, so we read it over plain http.")
        if opened is None:
            raise BriefingBlocked(f"We couldn't load {start}. The site may be down or refusing automated visitors.")

        home = await self._inspect(page, start, *opened)
        if home is None:
            raise BriefingBlocked(f"{start} loaded, but its content couldn't be read.")
        visit.pages.append(home)
        await self._shot(page, home.url, home.title)
        await self.step(f"Read the home page: “{home.title or start}”", url=home.url)
        if BOT_WALL.search(home.title or "") or ((home.status or 0) in {401, 403, 429, 503} and home.inventory.get("captcha")):
            raise BriefingBlocked(
                "This site showed a bot check (like Cloudflare's “Just a moment…” page) instead of its content. "
                "We never try to get past those, so there was nothing to read. Try again later — some sites only do this now and then."
            )

        seen: set[str] = {home.url}
        links = self._links(home, scope, seen, robots, visit)
        plan = pick_pages(links, limit=MAX_PAGES - 1, question=question)
        if plan:
            await self.step(f"Found {len(links)} links on the home page; reading {len(plan)} that explain the site best")
        await self._read_plan(page, inst, plan, visit, deadline, signed_in=False)

        if self.secret is not None:
            await self._sign_in_and_read(page, inst, scope, visit, seen, question, deadline)
        for d in session.drain_denied()[:5]:
            why = "it isn't a public internet address" if "non-public" in d.reason else "of our safety rules"
            visit.notes.append(f"The site tried to contact {d.host}; we blocked it because {why}.")
        return visit

    def _links(self, src: ReadPage, scope: Any, seen: set[str], robots: RobotFileParser | None, visit: Visit) -> list[dict[str, Any]]:
        """Same-site links on ``src`` that are safe to open (GET, no query, not state-changing)."""
        links: list[dict[str, Any]] = []
        for lk in src.inventory.get("links", []):
            n = normalize_url(lk.get("href", ""))
            if not n or n in seen:
                continue
            try:
                if not self._same_site(parse_origin(n), scope):
                    continue
            except TargetRejected:
                continue
            p = path_of(n)
            if SKIP_LINK.search(p) or NON_HTML_EXT.search(p) or urlsplit(n).query:
                continue
            seen.add(n)
            if robots is not None and not self._allowed(robots, n):
                visit.skipped.append({"url": n, "reason": "robots.txt asks automated visitors not to read it"})
                continue
            links.append({"url": n, "text": lk.get("text", ""), "in_nav": bool(lk.get("inNav"))})
        return links

    async def _read_plan(
        self, page: Page, inst: Instrument, plan: list[tuple[str, str]], visit: Visit, deadline: float, *, signed_in: bool
    ) -> None:
        for url, reason in plan:
            if time.monotonic() > deadline:
                visit.notes.append(f"Stopped after {len(visit.pages)} pages to stay within the time limit.")
                return
            await self.step(f"Opening {path_of(url)} ({reason})", url=url)
            opened = await self._open(page, inst, url)
            if inst.blocked_navigations:
                inst.blocked_navigations.clear()
                visit.skipped.append({"url": url, "reason": "redirected to another website"})
                continue
            if opened is None:
                visit.skipped.append({"url": url, "reason": "could not be loaded"})
                continue
            read = await self._inspect(page, url, *opened, signed_in=signed_in)
            if read is None or any(p.url == read.url and p.signed_in == signed_in for p in visit.pages):
                continue
            if signed_in and LOGIN_PATH.search(read.path):
                visit.notes.append(f"{path_of(url)} sent us back to the sign-in page, so the session may have ended.")
                continue
            visit.pages.append(read)
            await self._shot(page, read.url, read.title, signed_in=signed_in)
            await self.step(f"Read {read.path}{' (signed in)' if signed_in else ''}: “{read.title or read.path}”", url=read.url)

    def _find_login_url(self, visit: Visit, scope: Any) -> str | None:
        if self.login_url:
            return self.login_url
        for p in visit.pages:
            if p.kind == "login":
                return p.url
        for p in visit.pages:
            for lk in p.inventory.get("links", []):
                n = normalize_url(lk.get("href", ""))
                if not n:
                    continue
                try:
                    if not self._same_site(parse_origin(n), scope):
                        continue
                except TargetRejected:
                    continue
                if LOGIN_PATH.search(path_of(n)) or LOGIN_LINK.search(lk.get("text", "")):
                    return n
        return None

    async def _sign_in_and_read(
        self, page: Page, inst: Instrument, scope: Any, visit: Visit, seen: set[str], question: str, deadline: float
    ) -> None:
        assert self.secret is not None
        secret: TestAccountSecret = self.secret
        login_url = self._find_login_url(visit, scope)
        visit.signed_in_as = self.credential_hint
        insecure = scope.scheme != "https" or (login_url or "").startswith("http://")
        if insecure and not self.policy.is_private_allowlisted(scope.host, scope.port):
            self.auth_status = "failed"
            self.auth_detail = (
                "This site doesn't support secure (https) connections, so anyone between us and the site could read a "
                "password we send. To protect your account we didn't sign in, and described the public pages instead."
            )
            visit.auth_status, visit.auth_detail = self.auth_status, self.auth_detail
            await self.step(self.auth_detail)
            return
        if login_url is None:
            self.auth_status, self.auth_detail = "no_login_form", "We couldn't find a sign-in page. Add its address and ask again."
            visit.auth_status, visit.auth_detail = self.auth_status, self.auth_detail
            return
        await self.step(f"Opening the sign-in page {path_of(login_url)}", url=login_url)
        try:
            outcome = await auth_flow.login(page, inst, login_url, secret, _AuthRecorder(self, page))  # type: ignore[arg-type]
        except PlaywrightError as exc:
            outcome = auth_flow.AuthOutcome("failed", f"The sign-in page didn't respond as expected ({str(exc).splitlines()[0][:120]}).")
        await self._update(shots=list(self.shots))
        friendly = {
            "authenticated": "Signed in.",
            "blocked_captcha": f"{outcome.detail} So we stayed signed out and described the public pages.",
            "mfa_required": "The site asked for a one-time or two-factor code. We don't handle those, so we stayed signed out.",
            "verification_required": "The site asked to verify the account (by email or phone) before signing in.",
        }
        self.auth_status = outcome.status if outcome.status in friendly else "failed"
        generic = outcome.detail.startswith(("Login did not", "Login submit failed"))
        self.auth_detail = friendly.get(outcome.status) or (
            (
                "We filled in your details and pressed sign in, but the site stayed on its sign-in page. "
                "Check the username/ID and password are exactly what you use on the site."
                if generic else outcome.detail
            )
            + (f" The site said: “{outcome.messages[0]}”" if outcome.messages else "")
        )
        visit.auth_status, visit.auth_detail = self.auth_status, self.redactor.text(self.auth_detail)
        if outcome.status != "authenticated":
            await self.step(visit.auth_detail)
            return
        await self.step(f"Signed in as {self.credential_hint}")
        landing_url = normalize_url(page.url) or page.url
        landing = await self._inspect(page, landing_url, None, {}, signed_in=True)
        if landing is None:
            return
        public_urls = {p.url for p in visit.pages}
        if landing.url not in public_urls:
            visit.pages.append(landing)
            await self.step(f"Read {landing.path} (signed in): “{landing.title or landing.path}”", url=landing.url)
        if auth_flow.ONBOARDING_PATH.search(landing.path):
            visit.notes.append(
                "After signing in, the site asked this account to finish setting up. A briefing doesn't fill in forms, "
                "so some member pages may have redirected there."
            )
        # Member pages: links on the signed-in landing page and the home page, account areas first.
        # Spend the budget on what signing in unlocked: account-like areas, and links that
        # only appear once signed in. Public pages were already covered.
        public_links = {normalize_url(lk.get("href", "")) for p in visit.pages if not p.signed_in for lk in p.inventory.get("links", [])}
        read_before = {p.url for p in visit.pages}
        candidates: list[dict[str, Any]] = []
        for src in (landing, visit.pages[0]):
            for c in self._links(src, scope, set(read_before), None, visit):
                if c["url"] not in {x["url"] for x in candidates}:
                    candidates.append(c)
        limit = MAX_SIGNED_IN_PAGES
        member = [c for c in candidates if MEMBER_PATH.search(f"{path_of(c['url'])} {c['text']}")]
        new = [c for c in candidates if c not in member and c["url"] not in public_links]
        plan = [(c["url"], "looks like part of your account") for c in member][:limit]
        plan += pick_pages(new, limit=limit - len(plan), question=question) if len(plan) < limit else []
        plan = [(u, "only shown after signing in" if r != "looks like part of your account" else r) for u, r in plan]
        if not plan:
            visit.notes.append("Signing in didn't reveal any new pages beyond the public ones.")
        if plan:
            await self.step(f"Reading {len(plan)} pages that are only available after signing in")
        await self._read_plan(page, inst, plan, visit, deadline, signed_in=True)

    @staticmethod
    def _twin(origin: Any) -> Any:
        host = origin.host
        twin_host = host[4:] if host.startswith("www.") else f"www.{host}"
        return type(origin)(origin.scheme, twin_host, origin.port)

    def _same_site(self, origin: Any, scope: Any) -> bool:
        return origin == scope or origin == self._twin(scope)

    async def _allow_twin(self, session: BrowserSession, scope: Any) -> None:
        """Treat example.com and www.example.com as one site when the twin is reachable and allowed."""
        if scope.host.replace(".", "").isdigit() or ":" in scope.host:
            return  # IP addresses have no www twin
        twin = self._twin(scope)
        try:
            await resolve_and_check(twin.host, twin.port, self.policy)
        except TargetRejected:
            return
        session.also_allowed.add(twin)
