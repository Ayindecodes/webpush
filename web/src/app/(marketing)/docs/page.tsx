import type { Metadata } from "next";
import Link from "next/link";
import type { ReactNode } from "react";

export const metadata: Metadata = { title: "Documentation" };

const TOC = [
  ["getting-started", "Getting started"],
  ["verification", "Verifying a target"],
  ["investigations", "Running an investigation"],
  ["approvals", "Approvals & human checks"],
  ["findings", "Reading findings"],
  ["tests", "Reproduction tests"],
  ["security", "Security model"],
  ["limitations", "Current limitations"],
] as const;

export default function DocsPage() {
  return (
    <div className="mx-auto grid max-w-[1200px] gap-10 px-5 py-12 sm:px-8 lg:grid-cols-[220px_minmax(0,1fr)] lg:py-16">
      <nav aria-label="Documentation" className="lg:sticky lg:top-24 lg:self-start">
        <div className="mb-3 text-label font-medium text-brand-text">Documentation</div>
        <ol className="space-y-0.5 border-l border-border">
          {TOC.map(([id, label]) => (
            <li key={id}>
              <a href={`#${id}`} className="-ml-px block border-l border-transparent py-1.5 pl-4 text-label text-fg-muted transition-colors hover:border-fg-subtle hover:text-fg">
                {label}
              </a>
            </li>
          ))}
        </ol>
      </nav>

      <article className="max-w-[720px] space-y-14">
        <header>
          <h1 className="text-headline font-semibold">WEB X-RAY documentation</h1>
          <p className="mt-3 text-[1.0625rem] leading-relaxed text-fg-muted">
            Everything you need to run your first investigation and to read what it finds. WEB X-RAY drives a real Chromium browser
            against a website you are authorized to test, records evidence of what happened, and generates Playwright tests for the
            defects it confirms.
          </p>
        </header>

        <Doc id="getting-started" title="Getting started">
          <Steps
            items={[
              <>
                <Link href="/register">Create an account</Link>. You get a private workspace; projects, targets and evidence are visible only
                to its members.
              </>,
              <>Create a <strong>project</strong> for the application you want to test.</>,
              <>Add a <strong>target</strong> — the origin, such as <code>https://staging.example.com</code> — and verify it (below).</>,
              <>Start an <strong>investigation</strong>, review the plan, confirm you are authorized, and follow it live.</>,
            ]}
          />
        </Doc>

        <Doc id="verification" title="Verifying a target">
          <P>
            WEB X-RAY only investigates origins you prove you control. Each target gets a unique token; publish it using either method
            and press <em>Run verification check</em>:
          </P>
          <ul className="list-disc space-y-1.5 pl-5 text-body text-fg-muted">
            <li>
              <strong className="text-fg">Well-known file</strong> — serve the token as plain text at <code>/.well-known/webxray-verification.txt</code>.
            </li>
            <li>
              <strong className="text-fg">DNS TXT record</strong> — add <code>_webxray-verification.&lt;host&gt;</code> with value{" "}
              <code>webxray-verification=&lt;token&gt;</code>.
            </li>
          </ul>
          <P>The check fetches through the same SSRF-safe path used for scanning and never follows redirects.</P>
        </Doc>

        <Doc id="investigations" title="Running an investigation">
          <P>An investigation moves through recorded phases; the workspace shows exactly the phase the worker reports:</P>
          <Definition
            items={[
              ["Validate", "Re-checks authorization and the destination address."],
              ["Discover", "Crawls public pages (and authenticated pages, if a session exists) within your page and depth budget."],
              ["Authenticate", "Logs in with a stored test account, or creates one if you approved it."],
              ["Execute", "Runs the checkout journey at each viewport you selected; failed runs are repeated."],
              ["Diagnose", "Turns failed checks into findings and ranks likely causes from the evidence."],
              ["Reproduce", "Generates a Playwright test for each journey failure and executes it."],
            ]}
          />
          <P>
            Modes: <strong>Autonomous discovery</strong> explores and may create a test account; <strong>Authenticated investigation</strong> logs in
            with a test account you provide. You can pause (at the next safe checkpoint) or stop at any time.
          </P>
        </Doc>

        <Doc id="approvals" title="Approvals & human checks">
          <P>Consequential actions only happen with an explicit approval that is recorded with your name and the time:</P>
          <ul className="list-disc space-y-1.5 pl-5 text-body text-fg-muted">
            <li>
              <strong className="text-fg">Creating a test account</strong> — submitted once; if the outcome is unclear WEB X-RAY checks by logging in
              rather than registering again.
            </li>
            <li>
              <strong className="text-fg">Submitting orders</strong> — only for environments you confirm use sandbox payments. Without it, card data is
              never typed and the order is not placed.
            </li>
          </ul>
          <P>
            If a site asks for email or phone verification, a one-time code, or a CAPTCHA, the investigation pauses with status{" "}
            <em>Needs you</em>. Complete the step yourself, then resume. These checks are never bypassed.
          </P>
        </Doc>

        <Doc id="findings" title="Reading findings">
          <Definition
            items={[
              ["Confirmed defect", "Failed in every repeated run at that viewport, with supporting evidence."],
              ["Warning", "Directly observed (for example an HTTP 503), but user impact or reproducibility was not established."],
              ["Observation", "Context worth knowing, such as a page requesting a blocked internal address."],
            ]}
          />
          <P>
            <strong>Evidence strength</strong> (strong, moderate, limited) reflects how many runs agree and how direct the evidence is — it is never
            a model-generated percentage. <strong>Likely causes</strong> are marked supported, ruled out, or inconclusive, and each links to the
            evidence behind it.
          </P>
        </Doc>

        <Doc id="tests" title="Reproduction tests">
          <P>
            Each journey failure gets a TypeScript Playwright test generated from the locators the investigation used. WEB X-RAY runs it in an
            isolated runner and records the real result:
          </P>
          <Definition
            items={[
              ["Reproduced", "The test failed on its [WEBXRAY-DEFECT] assertion — the defect is real and reproducible."],
              ["Passing", "The expected behaviour works. After a fix, this is how you confirm it."],
              ["Inconclusive", "The test failed before reaching the defect check (for example, login failed)."],
            ]}
          />
          <P>
            Download a test from its finding and run it in your own suite: it reads <code>WEBXRAY_BASE_URL</code>, <code>WEBXRAY_TEST_EMAIL</code> and{" "}
            <code>WEBXRAY_TEST_PASSWORD</code> from the environment — credentials are never embedded in the file.
          </P>
        </Doc>

        <Doc id="security" title="Security model">
          <ul className="list-disc space-y-1.5 pl-5 text-body text-fg-muted">
            <li>Every browser connection passes through an egress proxy that blocks loopback, private, link-local, CGNAT and cloud-metadata addresses, validates every DNS answer, and pins the connection to the validated address.</li>
            <li>Navigation stays inside the target origin; popups, downloads and service workers are disabled.</li>
            <li>Test-account credentials are encrypted at rest, injected only into the isolated browser or test process, and redacted from logs, evidence, reports and test output.</li>
            <li>Screenshots mask password, card and one-time-code fields. Evidence is served through signed links that expire after ten minutes.</li>
            <li>Approvals, credential changes and investigation controls are written to an audit log.</li>
          </ul>
        </Doc>

        <Doc id="limitations" title="Current limitations">
          <ul className="list-disc space-y-1.5 pl-5 text-body text-fg-muted">
            <li>Automated journeys today: sign-up, login, onboarding and checkout. Other features are inventoried and shown as not tested.</li>
            <li>Discovery follows links; routes reachable only through scripts or buttons are not discovered yet.</li>
            <li>Chromium only. Playwright traces are not recorded yet.</li>
            <li>Diagnosis is deterministic and evidence-based; no AI model is used in investigations yet.</li>
            <li>Source-control integrations (such as GitHub) are not available yet.</li>
          </ul>
        </Doc>
      </article>
    </div>
  );
}

function Doc({ id, title, children }: { id: string; title: string; children: ReactNode }) {
  return (
    <section id={id} className="scroll-mt-24 space-y-4 [&_a]:font-medium [&_a]:text-brand-text [&_a:hover]:underline [&_code]:rounded [&_code]:bg-surface-2 [&_code]:px-1 [&_code]:py-0.5">
      <h2 className="text-title font-semibold">{title}</h2>
      {children}
    </section>
  );
}

function P({ children }: { children: ReactNode }) {
  return <p className="text-body leading-relaxed text-fg-muted">{children}</p>;
}

function Steps({ items }: { items: ReactNode[] }) {
  return (
    <ol className="space-y-3">
      {items.map((item, i) => (
        <li key={i} className="flex gap-3 text-body text-fg-muted">
          <span className="flex size-6 shrink-0 items-center justify-center rounded-full bg-brand-soft font-mono text-meta font-semibold text-brand-text">{i + 1}</span>
          <span className="pt-0.5">{item}</span>
        </li>
      ))}
    </ol>
  );
}

function Definition({ items }: { items: [string, string][] }) {
  return (
    <dl className="divide-y divide-border rounded-[var(--radius-panel)] border border-border">
      {items.map(([term, def]) => (
        <div key={term} className="grid gap-1 px-4 py-3 sm:grid-cols-[150px_1fr] sm:gap-4">
          <dt className="text-body font-medium">{term}</dt>
          <dd className="text-body text-fg-muted">{def}</dd>
        </div>
      ))}
    </dl>
  );
}
