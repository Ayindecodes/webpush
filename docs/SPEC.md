# WEB X-RAY — Product Specification (condensed, authoritative)

> Condensed from the product brief supplied on 2026-10-09. Where this file and
> the code disagree, this file describes the intended product; `docs/STATUS.md`
> describes what is actually implemented.

## Promise
Give WEB X-RAY a website. It investigates how the website actually behaves,
identifies what is broken, explains what the evidence suggests, and helps
developers verify the solution. It is not a crawler, Lighthouse clone, or
chatbot: it interacts with a real site, observes, reproduces failures, and
hands developers evidence they can independently verify.

## Operating modes
- **A — Autonomous discovery.** Validate scope → isolated browser → discover
  public routes → find register/login → create a test account *when permitted*
  → onboarding → authenticated discovery → feature inventory → journeys →
  findings + report. Email/SMS verification, CAPTCHA, SSO approval ⇒ pause and
  ask for authorized human help. Never bypass auth or anti-abuse controls.
- **B — Authenticated investigation.** User supplies a designated test account
  via a secure credential interface (or an approved session) and an optional
  narrower scope. Credentials never go to an AI model as prompt text.
- **C — Repository-assisted (future).** Optional GitHub correlation; core
  product must work without it.

## Capabilities
- **Discovery:** public/auth routes, nav, links, forms, controls, modals, SPA
  support, URL normalization, loop avoidance, query-variant control, dedupe,
  page/resource limits. Discovered ≠ verified.
- **Account creation:** locate form, inspect requirements, approved test
  identity, submit, inspect validation, detect verification requirements,
  confirm success, onboarding, record account lifecycle. A timeout after submit
  must NOT trigger a second registration — determine outcome first.
- **Authenticated exploration:** inventory of discovered / tested / untested /
  needs-permission / needs-human / inaccessible features. Never claim full
  coverage when only a subset was inspected.
- **Agent:** orchestrator over controlled tools (inspect, navigate approved
  URLs, click permitted elements, fill approved fields, submit approved forms,
  computed styles, screenshots/traces, sanitized network metadata, verify,
  record findings, generate tests, request approval). Loop: Observe →
  Understand → Plan → Execute → Verify → Record → Continue/Stop. Every tool call
  validates inputs, permissions, scope, budgets. Persistent investigation state
  (route graph, features, action history, journey results, auth status,
  findings, evidence refs, remaining budget) — not just chat history.
- **Journeys:** registration, login/logout, password reset, onboarding, search,
  forms, profile edit, cart, checkout, subscriptions, navigation, responsive
  menus, settings. Each has preconditions, actions, expected outcomes, cleanup.
  Verify state transitions (clickable Save ≠ profile edit works). Never make real
  purchases, delete real data, change billing, or send external communications
  just to explore. Consequential actions need authorization.
- **Responsive:** Desktop 1440×900, Tablet 768×1024, Mobile 390×844. Compare
  success, geometry, clickability/overlap, visibility/clipping, horizontal
  overflow, nav, form usability, runtime/network errors.
- **Instrumentation:** DOM/accessibility info, bounding boxes, visibility &
  enabled state, computed CSS, `elementFromPoint` hit tests, console + page
  errors, request failures, HTTP errors, timing, navigation, interactions,
  screenshot checkpoints, Playwright traces, viewport config, expected vs
  observed. Correlate events with the journey step. A failed request ≠ failed
  workflow; a successful click ≠ successful workflow.
- **Evidence:** per-finding bundle (before/after/full/element screenshots,
  traces, DOM snapshots, geometry, styles, network/console, navigation history,
  repro steps, test source + results). Project-scoped access, retention,
  integrity metadata. Redact credentials, cookies, tokens, PII. Evidence is only
  ever captured from real execution — the AI never invents it.
- **Diagnosis:** observed failure vs likely cause vs supporting evidence vs
  alternative hypotheses vs evidence strength vs next action vs verification
  status. Rank explanations from evidence; no "it's the footer because mobile".
  Without source access report a *likely* cause. Confidence grounded in
  reproducibility and evidence quality — never arbitrary LLM percentages.
- **Repro tests:** Playwright tests with setup/cleanup, auth via approved flow,
  explicit viewport, stable accessible locators, actions, assertions of
  expected behavior, safe fixtures, good error messages. Execute when
  verification is requested; record actual results. Generated ≠ verified.
- **Fix verification (optional, later):** locate files, propose patch, apply in
  isolated branch, run repro + regression, compare, request approval before
  merge/deploy. Never silently deploy.

## Flagship demo
Controlled e-commerce app with: registration/login, onboarding, product
listing, cart, checkout, profile settings, simulated payment provider, and
deliberate defects — **mobile-only checkout defect**, **form-validation
defect**, **simulated API failure**. Demo flow: discover → register test
account → onboard → find checkout → run desktop + mobile → desktop passes,
mobile fails → repeat mobile → capture evidence → identify overlay/responsive
CSS evidence → generate Playwright test → run it → show in dashboard.

## UI (see docs/DESIGN.md for the full design brief)
Nav: Overview, Investigations, Findings, Journeys, Projects, Integrations,
Settings. Screens: investigation creation (URL, mode, goal, viewports, secure
test-account entry, permitted routes, excluded actions, depth/budgets, plan
approval), live investigation (latest viewport, URL/title, progress, current
action, routes/features, timeline, findings, pause/resume/stop — real job state
only), overview, finding detail (evidence, timeline, DOM/style inspector,
network/console, hypotheses, repro, generated test + verification status),
final report (13 sections; every claim links to evidence).

## Architecture
Modular-monolith control plane + separately isolated browser workers.
Next.js/TS/Tailwind · FastAPI/Pydantic · Playwright Chromium · Redis + task
queue with persistent job states/retries · PostgreSQL · S3-compatible
artifacts · AI layer separate from deterministic execution/verification.

Entities: Organization, Project, Environment, Credential reference,
Investigation, Page, Feature, Journey, Browser run, Event, Finding, Evidence,
Reproduction test, Fix attempt, Approval record — all org/project owned;
credentials stored separately; evidence via protected refs + short-lived links.

Proposed routes: `POST /api/projects`, `POST /api/projects/:id/investigations`,
`GET /api/investigations/:id`, `POST …/pause|resume|stop`,
`GET …/events|pages|findings`, `GET /api/findings/:id`, `…/evidence`,
`POST /api/findings/:id/reproduce`, `GET /api/tests/:id`,
`POST /api/tests/:id/verify`, `POST /api/integrations/github/connect`.

## Security (non-negotiable)
Authorization to scan; scope restriction; block loopback/private/link-local/
metadata; validate destination IP at connect time and on redirects; mitigate
SSRF + DNS rebinding; isolate workers from each other and the control plane;
no access to worker secrets/local files; encrypted secrets, short-lived creds;
redact logs/screenshots/traces/reports; limit time/bandwidth/pages/concurrency;
approval for consequential actions; never bypass auth/anti-abuse; never
silently destroy or purchase; page content is untrusted and cannot override
policy; audit auth/approvals/consequential actions. Enforcement must not depend
on the AI model.

## Roadmap & acceptance criteria
- **P0 Foundation:** register project; scan authorized target; screenshot;
  retrieve result + evidence; reject invalid/prohibited target.
- **P1 Discovery:** discover demo public pages; dedupe; stop at limits; persist
  routes + evidence.
- **P2 Auth/registration:** create test account when supported; use existing
  account; no credentials in AI prompts/logs; human verification ⇒ safe pause;
  continue exploring authorized authenticated pages.
- **P3 Journeys:** state machine; discover + execute checkout; every action has
  a recorded outcome; click ≠ success; budgets and approvals enforced.
- **P4 Instrumentation/diagnosis:** detect the mobile checkout failure;
  separate observed failure from inferred cause; findings link to real
  evidence; repeated runs separate reproducible from flaky.
- **P5 Dashboard/test-gen:** inspect a finding; evidence synced with timeline;
  generated test reproduces known defect; verification status reflects real
  results; reports include coverage + limitations.
- **P6 Reliability/beta:** no cross-project evidence access; no credential
  leakage; prohibited destinations blocked; recoverable worker failures;
  false-positive + reproduction metrics measured.
- **P7 Expansion:** GitHub, source-aware diagnosis, PR checks, CD scanning,
  patch proposals, visual regression, schedules, cross-browser, teams,
  enterprise. Not before the first end-to-end investigation works.

## Metrics
Route/feature discovery coverage, journey success, defect precision,
reproduction rate, root-cause accuracy, generated-test validity, fix
verification rate, time to first actionable finding, cost/time, repeat use.
Measured against a benchmark app with labeled defects. Hundreds of false
positives = failure.
