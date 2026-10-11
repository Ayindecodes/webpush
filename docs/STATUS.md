# Status

## Second slice — briefings, plain-language redesign, web security (2026-10-10)

**Briefings** ("tell me what this website is"): `POST /api/briefings`, `worker/briefing.py`,
`services/briefing.py`, migrations 0002–0003, UI under `/briefings`.

* Reads up to 8 public pages of **any** public site (no ownership proof needed because it is
  read-only): GET navigations only, robots.txt honoured, egress proxy (public addresses only),
  www/bare-domain treated as one site, https→http fallback like a browser, bot walls
  (e.g. Cloudflare "Just a moment…") reported instead of bypassed. Limits: 2 running and
  40 per day per workspace.
* Optional sign-in with the user's own account (explicit confirmation required). The
  credential is Fernet-encrypted, wiped from the database as soon as the worker reads it,
  registered with the redactor, never sent over plain http (except operator-allowlisted dev
  origins), and CAPTCHA / security-question / MFA forms are reported, never answered.
  Signed-in pages are read on the user's behalf, so robots.txt is not applied to them; the
  report says so.
* Output is deterministic and evidence-bound: site type with reasons, capabilities with the
  pages they were seen on, sections, owner/contact, prices, technology, quoted answers to an
  optional question, screenshots (signed 10-minute links), and limitations.

**Sign-in fixes found on real sites:** inputs without a `type` attribute are now treated as
text (they were never recognised as username fields); the account field is the first
text-like field before the password, whatever it is called (username, email, ID, phone);
a login that makes the sign-in form disappear counts as success even without a "Log out"
link; extra required fields and arithmetic "human checks" stop the sign-in with a clear reason.

**Fix verification:** a proof test that passes *after* it previously reproduced the problem
now marks the finding **fixed** (it stays a confirmed defect); previously it was wrongly
downgraded as "contradicting" the investigation.

**Web app:** paper/ink design everywhere (light default, dark "Ink" theme), plain-language
copy, 3-step "check my site" flow, story-first investigation and problem pages with
technical detail collapsed, Problems/Journeys/Sites/Settings/Integrations redesigned,
remove-website and delete-test-account actions with confirmations, "no worker available"
notice backed by a worker heartbeat (`GET /api/system/workers`).

**Routing and security:** `src/proxy.ts` sends signed-out visitors to `/login?next=…` before
any app page renders (the API remains the authorization boundary); one `safeNext()` check for
every post-login redirect (rejects absolute, protocol-relative, backslash and non-app targets);
signed-in users skip the auth pages; sign-out does a full reload so no cached data survives;
security headers on every response (CSP, frame-ancestors none, COOP/CORP, Permissions-Policy,
nosniff, no-referrer, HSTS in production, no `X-Powered-By`). CSP allows inline scripts because
nonce-based CSP is incompatible with Cache Components (documented in `next.config.ts`).

**Verified:** 95 backend tests pass (incl. real-Chromium briefings with and without sign-in,
login-form edge cases, fix verification, tenancy of every new endpoint); web typecheck, lint and
production build pass; every app and public page renders at 1440 and 390 px with no console
errors, failed API calls or horizontal overflow. Findings recorded before this change keep their
old technical wording; new investigations use the plain-language wording.

## First vertical slice (2026-10-09)

## Verified end to end

Against the Northwind benchmark (`demo-shop/`), through the real API, queue, worker,
Chromium and Node test runner (`backend/tests/test_e2e.py`, and manually through the
dashboard):

| Spec §12 step | Result |
|---|---|
| Authorized URL entered and validated | Target verified; prohibited targets (private, loopback, metadata, bad schemes, embedded credentials) rejected |
| Public routes discovered | 15 public pages; tracking params normalized; pagination trap capped at 3 variants; logout and off-site links not followed |
| Designated test account created | Registered once, onboarding completed (2 steps), login re-verified in a fresh context |
| Authenticated exploration | 15 authenticated pages |
| Checkout journey discovered | Product → cart → checkout planned from discovered pages |
| Desktop + mobile execution | Desktop passed and placed a sandbox order; mobile failed 2/2 |
| Mobile defect detected | Probe taps delivered to `aside.help-bar` at every scroll position; no submission request sent |
| Evidence captured | Screenshots (masked), probe/hit-test geometry, computed styles, sanitized DOM, network and console logs |
| Playwright test generated and executed | Failed on `[WEBXRAY-DEFECT]` → **reproduced** |
| Fix verification | With `DEMO_FIX_CHECKOUT_OVERLAY` on, the same test passed → **not reproduced** |
| Dashboard | All screens render at 1440 and 390 px without console errors, failed API calls, or overflow (`scripts/ui_smoke.py`) |

Also detected: D3 (`GET /api/recommendations` → 503 on 10/10 loads, warning) and the S1
security probe (169.254.169.254 beacon blocked, observation).

Test suites: **72 backend tests pass** (security, API/tenancy, worker units, real-Chromium
egress, e2e); web typecheck, lint, and production build pass.

### Honest record of problems found while building

* The first mobile result was a **false positive** produced by WEB X-RAY: it tapped
  layout-viewport coordinates as screen coordinates. The generated test passed and
  contradicted it. Fixed by probe taps in visual-viewport coordinates, and findings are now
  automatically downgraded when their test contradicts them.
* The benchmark itself had an unintended horizontal overflow and a footer that made D1
  unreachable as documented; both were found by WEB X-RAY and are logged in
  `demo-shop/defects.json` → `changelog`.

## Benchmark coverage (labelled defects)

| Defect | Detected? |
|---|---|
| D1 Mobile checkout overlay | Yes — confirmed, reproduced by test, fix verified |
| D2 Profile phone validation | **No** — no profile-edit journey yet |
| D3 Recommendations API 503 | Yes — warning with correlated console error |

## Not implemented yet (by design of this slice)

* **AI layer.** No model is used for planning, interpretation or test generation; all
  logic is deterministic. The investigation "goal" is recorded but does not change the plan.
* **Journeys other than checkout** (profile edit, search, password reset, …). Other features
  are inventoried and marked *untested*.
* **SPA route discovery** beyond `<a href>` links.
* **Playwright traces** — not recorded until a trace redaction pass exists.
* **Tablet** viewport is selectable but was not part of the verified benchmark run.
* **Resume after human verification** is implemented as a held pause + login retry, but is
  only exercised by unit-level paths; no benchmark page requires email verification yet.
* **Production isolation** — workers run on the host in development. Containerized workers
  (browser with no reachable DB credentials), S3 artifact storage, retention policies, and
  per-tenant concurrency limits are Phase 6 work.
* GitHub / source-aware diagnosis / patch proposals (Integrations page says so; no fake controls).

## Suggested next steps

1. Profile-edit journey with persistence check → should detect D2 (form-validation).
2. Containerized worker image + network policy; S3 artifact store; retention job.
3. Trace capture with header/cookie/fill-value scrubbing.
4. AI planner behind the existing tool boundary (navigate/click/fill/verify with policy checks),
   starting with journey planning for unknown sites; keep diagnosis evidence-bound.
5. Benchmark harness that scores findings against `defects.json` (precision/recall per run).
