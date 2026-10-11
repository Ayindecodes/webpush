# Architecture

## Components

| Component | Tech | Responsibility |
|---|---|---|
| Control plane (`backend/webxray/api`) | FastAPI, Pydantic, SQLAlchemy 2 (async), Alembic | Auth, projects, targets + verification, credentials, investigations, findings, evidence links, reports, audit log |
| Job queue (`services/jobs.py`) | PostgreSQL + Redis | Durable jobs in Postgres (`FOR UPDATE SKIP LOCKED`, leases, heartbeats); Redis only wakes idle workers |
| Worker (`worker/`) | Playwright (Python) / Chromium | Runs the investigation state machine and test executions |
| Egress proxy (`worker/egress_proxy.py`) | asyncio | The browser's only network route; enforces destination policy |
| Test runner (`runner/`, `worker/test_runner.py`) | @playwright/test 1.63 (Node) | Executes generated tests in a subprocess with a minimal environment |
| Artifact store (`storage/artifacts.py`) | Local filesystem (S3-shaped interface) | Evidence blobs with SHA-256 integrity metadata |
| Dashboard (`web/`) | Next.js 16, TypeScript, Tailwind v4, SWR | Client-rendered views over the API via a same-origin rewrite |

The AI layer named in the spec is **not present yet**; every decision in this version is
deterministic (see `STATUS.md`). It is designed to sit *beside* the execution engine as a
planner/explainer, never as the component that enforces scope, policy, or verification.

## Investigation state machine (`worker/pipeline.py`)

```
queued → running: validate → discover_public → authenticate → discover_authenticated
                  → plan → execute → diagnose → reproduce → report → completed
         paused / awaiting_human (held at checkpoints) · stopped · blocked · failed
```

Each phase records status + detail in `investigations.phases`. The worker honours
pause/stop at **checkpoints** between units of browser work; the UI only reflects these
recorded states (no client-side progress estimation).

## Data model (`backend/webxray/models.py`)

Organization · Membership · User · AuthSession · Project · Environment (target + proof of
authorization) · CredentialSecret (encrypted, separate table) · Investigation · Page ·
Feature · Journey · BrowserRun · Event (ordered by `seq`) · Finding · Evidence ·
FindingEvidence · ReproductionTest · TestRun · Approval · AuditLog · Job.

Every tenant row carries `org_id` (and `project_id`); API access checks use it directly and
return 404 for other tenants' objects.

## Security boundaries

1. **Authorization to scan.** A target must be verified by a well-known file or DNS TXT
   record before an investigation can be created (`services/verification.py`). The
   verification fetch uses the same pinned-address path as the browser. Operator-allowlisted
   origins (local benchmark only) are the sole exception and are configured per deployment.
2. **Egress policy (SSRF / DNS rebinding).** Chromium is launched with the per-investigation
   proxy (random credential, loopback included via `<-loopback>`). For every connection the
   proxy resolves the host, rejects the request if *any* answer is loopback, private,
   link-local, CGNAT, NAT64/6to4-embedded, metadata, multicast or reserved, then connects to
   the validated IP itself. Ports are restricted. A per-investigation byte budget is enforced.
   This runs independently of crawler, journey or any future AI logic.
3. **Scope.** Top-level navigations outside the target origin are aborted by a route guard;
   popups are closed; downloads and service workers are disabled. Links that look
   state-destroying (logout, delete, unsubscribe, …) are never followed.
4. **Consequential actions.** Registration and order submission require explicit approvals
   stored in `approvals` + `audit_log`. Registration is submitted once; after a submit the
   investigation is marked `consequential_started`, so a lost worker never re-runs it
   automatically. Without order approval, card fields are never typed and the order is not
   placed (reachability of the submit control is still tested non-destructively).
5. **Human gates.** CAPTCHA, MFA/one-time codes and email/phone verification are detected and
   handed to a person (`awaiting_human`), never bypassed.
6. **Secrets.** Test credentials are Fernet-encrypted at rest, decrypted only inside the
   worker, injected into the browser or the test subprocess environment, and added to the
   investigation's `Redactor`, which scrubs every event, evidence file, finding, report and
   test output. Screenshots mask password, card and OTP inputs. Logs are JSON with a
   redaction pass. Credentials are never returned by the API.
7. **Evidence access.** Artifacts are served only through HMAC-signed links that expire after
   10 minutes, issued to members of the owning organization; captured page content is never
   rendered as HTML (`text/plain`, `CSP: sandbox`, `nosniff`).
8. **Web app.** Session cookie is HttpOnly + SameSite=Lax (+Secure in production); state-changing
   requests from foreign Origins are rejected; login is rate-limited via Redis; passwords use
   Argon2id.
9. **Test execution isolation.** Generated tests run in a subprocess whose environment
   contains no database URL or platform secrets, through a fresh egress proxy.

**Known gap:** browser workers are separate processes and Chromium is sandboxed, but this
development setup runs the worker on the host. Production must run workers in containers
without database credentials reachable from the browser process (see `STATUS.md`).

## Evidence-grounded diagnosis (`worker/diagnosis.py`)

* **Observed failure** = the first failing step and its recorded `observed` text.
* **Hypotheses** (overlay interception, disabled control, invisible control, JS exception,
  failed request, horizontal overflow) are each marked *supported / ruled out /
  inconclusive* from recorded evidence, and link to it.
* **Reachability** is decided by a *probe tap*: a real tap/click at the control's
  visual-viewport centre, captured and cancelled by a capture-phase listener, so the result
  reflects the browser's input pipeline rather than layout-coordinate arithmetic.
  `elementFromPoint` is kept as corroborating geometry.
* **Classification**: `confirmed_defect` only when the failure repeats in every run of that
  viewport (≥2 runs); otherwise `warning`. Page-level HTTP errors are `warning` (observed,
  user impact unverified); context items are `observation`.
* **Verification**: a generated test is "reproduced" only if Playwright fails on the
  `[WEBXRAY-DEFECT]` assertion. If the test passes, a confirmed finding is downgraded and
  marked `contradicted_by_test`.

## Frontend design system

Color lives only in `web/src/styles/theme.css` as semantic tokens (surface, fg, border,
status-*). **No brand palette has been chosen**: the default themes are achromatic
placeholders, and severity/status always carry an icon and a label so meaning never depends
on color. Typography scale (title/section/body/label/meta) and radii are tokens in
`globals.css`.
