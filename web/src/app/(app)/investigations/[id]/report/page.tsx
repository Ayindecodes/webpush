"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useState, type ReactNode } from "react";

import { EvidenceById } from "@/components/evidence/evidence";
import { useCrumbs } from "@/components/shell/context";
import { Icon } from "@/components/ui/icons";
import { Button, ButtonLink, KeyValue, LoadError, LoadingRows, Mono, PageHeader } from "@/components/ui/primitives";
import { ClassificationBadge, HypothesisStatus, SeverityLabel, StatusPill, TestStatusBadge } from "@/components/ui/status";
import { formatMs, hostOf, humanize, pathOf } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import type { Classification, Hypothesis, Severity } from "@/lib/types";

interface Report {
  investigation: { id: string; status: string; mode: string; goal: string; created_at: string; started_at: string | null; finished_at: string | null; error: string | null; blocked_reason: string | null };
  executive_summary: string;
  target: { project: string; origin: string; verification: string; viewports: string[]; browser: string };
  access: { auth_state: string; status?: string; detail?: string; approvals: { kind: string; statement: string; at: string }[]; onboarding?: { status?: string; steps?: string[] } };
  discovery: { pages: { url: string; title: string; status: number | null; classification: string; auth_state: string }[]; crawl_notes: string[]; skipped_links: Record<string, number> };
  features: { key: string; name: string; status: string }[];
  journeys: { name: string; status: string; runs: { id: string; viewport: string; attempt: number; status: string; failure_step: string | null }[] }[];
  coverage: { limitations: string[]; egress_blocked_requests: number };
  findings: {
    id: string; title: string; severity: Severity; classification: Classification; kind: string; summary: string; expected: string | null; observed: string | null;
    viewport: string | null; reproduction: { status?: string; failed_runs?: number; total_runs?: number }; evidence_strength: string; hypotheses: Hypothesis[];
    steps_to_reproduce: string[]; recommendation: string | null;
    evidence: { id: string; kind: string; label: string; sha256: string; role: string }[];
    test: { id: string; filename: string; verification_status: string; last_run: { outcome: string; playwright_status: string; duration_ms: number } | null } | null;
  }[];
}

const SECTIONS = [
  ["summary", "In short"],
  ["problems", "Problems found"],
  ["journeys", "Journeys we tried"],
  ["pages", "Pages and features"],
  ["access", "Signing in and permissions"],
  ["setup", "The website and our setup"],
  ["limits", "What wasn't checked"],
  ["next", "What to do next"],
] as const;

const SCREEN: Record<string, string> = { desktop: "Computer", tablet: "Tablet", mobile: "Phone" };
const APPROVAL: Record<string, string> = {
  scan_authorization: "Allowed to test this website",
  account_registration: "Allowed to create a test account",
  order_submission: "Allowed to place test orders",
};
const EVIDENCE_KIND: Record<string, string> = {
  screenshot: "Screenshot",
  dom_snapshot: "Page structure",
  hit_test: "Tap test",
  computed_styles: "Styles",
  network_log: "Network log",
  console_log: "Console log",
  test_source: "Test code",
  test_output: "Test output",
};

export default function ReportPage() {
  const { id } = useParams<{ id: string }>();
  const { data: r, error, mutate } = useApi<Report>(`/api/investigations/${id}/report`);
  const [openEvidence, setOpenEvidence] = useState<string | null>(null);
  useCrumbs([
    { label: "Investigations", href: "/investigations" },
    { label: r ? hostOf(r.target.origin) : "Investigation", href: `/investigations/${id}` },
    { label: "Report" },
  ]);
  if (error) return <LoadError error={error} retry={() => mutate()} what="report" backHref="/investigations" backLabel="All investigations" />;
  if (!r) return <LoadingRows rows={8} />;

  const confirmed = r.findings.filter((f) => f.classification === "confirmed_defect");
  return (
    <div>
      <PageHeader
        eyebrow={`Investigation report · ${r.target.project ?? "project"}`}
        title={hostOf(r.target.origin)}
        meta={
          <>
            <StatusPill status={r.investigation.status} />
            <span>{r.investigation.finished_at ? `Finished ${new Date(r.investigation.finished_at).toLocaleString()}` : "Still running"}</span>
            <span className="font-mono text-[12px]">ID {r.investigation.id.slice(0, 8)}</span>
          </>
        }
        actions={
          <div className="no-print flex flex-wrap gap-2">
            <Button variant="paper" onClick={() => window.print()} icon={<Icon.Download />}>
              Print or save as PDF
            </Button>
            <ButtonLink href={`/api/investigations/${id}/report?format=markdown`} variant="primary" icon={<Icon.Download />} download>
              Download (Markdown)
            </ButtonLink>
          </div>
        }
      />
      <div className="grid gap-12 lg:grid-cols-[210px_minmax(0,1fr)]">
        <nav aria-label="Report sections" className="no-print hidden lg:block">
          <ol className="sticky top-24 space-y-0.5 border-l-[1.5px] border-border">
            {SECTIONS.map(([k, label], i) => (
              <li key={k}>
                <a href={`#${k}`} className="-ml-[1.5px] flex gap-2.5 border-l-[1.5px] border-transparent py-1.5 pl-4 text-body text-fg-muted transition-colors hover:border-fg hover:text-fg">
                  <span className="font-mono text-[11px] leading-6 text-fg-subtle">{String(i + 1).padStart(2, "0")}</span>
                  {label}
                </a>
              </li>
            ))}
          </ol>
        </nav>

        <article className="min-w-0 max-w-4xl space-y-16">
          <ReportSection id="summary" n={1} title="In short">
            <div className="card-ink p-6 sm:p-8">
              <p className="text-[1.125rem] leading-relaxed">{r.executive_summary}</p>
              {r.investigation.goal && <p className="mt-3 text-body text-fg-muted">Your note: {r.investigation.goal}</p>}
            </div>
            <SeverityTable findings={r.findings} />
            <p className="mt-3 text-label text-fg-subtle">
              Severity is how badly a problem affects visitors: <strong className="font-medium text-fg-muted">critical</strong> blocks something important
              (like paying), <strong className="font-medium text-fg-muted">info</strong> is for your information only.
            </p>
          </ReportSection>

          <ReportSection id="problems" n={2} title={`Problems found (${r.findings.length})`}>
            {r.findings.length === 0 ? (
              <p className="text-body text-fg-muted">No problems were recorded in the parts of the site we checked.</p>
            ) : (
              <div className="space-y-6">
                {r.findings.map((f, i) => (
                  <div key={f.id} className="panel break-inside-avoid p-6">
                    <div className="flex flex-wrap items-center gap-2.5">
                      <span className="font-mono text-[12px] text-fg-subtle">2.{i + 1}</span>
                      <SeverityLabel severity={f.severity} />
                      <ClassificationBadge value={f.classification} />
                      {f.test && <TestStatusBadge status={f.test.verification_status} />}
                    </div>
                    <Link href={`/findings/${f.id}`} className="mt-3 block text-[1.25rem] font-semibold leading-snug tracking-[-0.015em] hover:underline">
                      {f.title}
                    </Link>
                    <p className="mt-2 text-body leading-relaxed text-fg-muted">{f.summary}</p>
                    <div className="mt-4 grid gap-3 sm:grid-cols-2">
                      <div className="rounded-xl bg-surface-2 p-4 text-body">
                        <div className="text-label font-semibold text-fg-subtle">What should happen</div>
                        <div className="mt-1">{f.expected ?? "—"}</div>
                      </div>
                      <div className="rounded-xl bg-danger-soft p-4 text-body">
                        <div className="text-label font-semibold text-danger">What actually happened</div>
                        <div className="mt-1">{f.observed ?? "—"}</div>
                      </div>
                    </div>
                    {f.steps_to_reproduce.length > 0 && (
                      <div className="mt-4">
                        <div className="text-label font-semibold">How to see it yourself</div>
                        <ol className="mt-1.5 list-decimal space-y-1 pl-5 text-body text-fg-muted">
                          {f.steps_to_reproduce.map((s, k) => (
                            <li key={k}>{s}</li>
                          ))}
                        </ol>
                      </div>
                    )}
                    {f.hypotheses.length > 0 && (
                      <div className="mt-4 space-y-2">
                        <div className="text-label font-semibold">Why it happens</div>
                        {f.hypotheses.map((h) => (
                          <div key={h.key} className="flex flex-wrap items-start gap-2.5 text-body">
                            <HypothesisStatus status={h.status} />
                            <span className={h.status === "not_supported" ? "text-fg-subtle line-through decoration-fg-subtle/40" : ""}>{h.title}</span>
                          </div>
                        ))}
                      </div>
                    )}
                    {f.recommendation && (
                      <div className="mt-4 rounded-xl border border-brand-line bg-brand-soft p-4 text-body">
                        <div className="text-label font-semibold text-brand-text">Suggested fix</div>
                        <div className="mt-1">{f.recommendation}</div>
                      </div>
                    )}
                    {f.test && (
                      <p className="mt-4 text-label text-fg-muted">
                        Proof test <Mono>{f.test.filename}</Mono>:{" "}
                        {f.test.last_run
                          ? `${f.test.last_run.outcome === "reproduced" ? "the problem happened again" : f.test.last_run.outcome === "not_reproduced" ? "the problem no longer happens" : humanize(f.test.last_run.outcome)} (ran in ${formatMs(f.test.last_run.duration_ms)})`
                          : "written, not run yet"}
                      </p>
                    )}
                    {f.evidence.length > 0 && (
                      <div className="no-print mt-4 flex flex-wrap gap-2 border-t border-border pt-4">
                        <span className="mr-1 self-center text-label text-fg-subtle">Evidence:</span>
                        {f.evidence.map((e) => (
                          <Button key={e.id} size="sm" variant="paper" onClick={() => setOpenEvidence(e.id)} title={`SHA-256 ${e.sha256}`}>
                            {EVIDENCE_KIND[e.kind] ?? humanize(e.kind)}
                          </Button>
                        ))}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}
          </ReportSection>

          <ReportSection id="journeys" n={3} title="Journeys we tried">
            {r.journeys.length === 0 ? (
              <p className="text-body text-fg-muted">No journeys were tried.</p>
            ) : (
              <div className="space-y-6">
                {r.journeys.map((j) => (
                  <div key={j.name}>
                    <div className="flex flex-wrap items-center gap-2.5 text-[1.0625rem] font-semibold">
                      {j.name} <StatusPill status={j.status} />
                    </div>
                    <ul className="panel mt-3 divide-y divide-border overflow-hidden">
                      {j.runs.map((run) => (
                        <li key={run.id} className="flex flex-wrap items-center gap-3 px-5 py-3 text-body">
                          <span className="w-32">
                            {SCREEN[run.viewport] ?? run.viewport} · try {run.attempt}
                          </span>
                          <StatusPill status={run.status} />
                          {run.failure_step && <span className="text-fg-muted">stopped at “{humanize(run.failure_step)}”</span>}
                        </li>
                      ))}
                    </ul>
                  </div>
                ))}
              </div>
            )}
          </ReportSection>

          <ReportSection id="pages" n={4} title="Pages and features">
            {r.discovery.crawl_notes.length > 0 && (
              <ul className="mb-4 space-y-1 text-body text-fg-muted">
                {r.discovery.crawl_notes.map((n) => (
                  <li key={n}>{n}</li>
                ))}
              </ul>
            )}
            <div className="panel overflow-x-auto">
              <table className="w-full min-w-[560px] text-left text-body">
                <thead className="font-mono text-[11px] uppercase tracking-[0.12em] text-fg-subtle">
                  <tr className="border-b border-border">
                    <th className="px-5 py-3 font-normal">Address</th>
                    <th className="px-3 py-3 font-normal">Kind</th>
                    <th className="px-3 py-3 font-normal">Answer</th>
                    <th className="px-5 py-3 font-normal">Seen as</th>
                  </tr>
                </thead>
                <tbody>
                  {r.discovery.pages.map((p) => (
                    <tr key={p.url + p.auth_state} className="border-b border-border last:border-b-0">
                      <td className="px-5 py-2 font-mono text-[12.5px]">{pathOf(p.url)}</td>
                      <td className="px-3 py-2 text-fg-muted">{humanize(p.classification)}</td>
                      <td className="px-3 py-2 tabular">{p.status == null ? "—" : p.status >= 400 ? <span className="text-danger">Error {p.status}</span> : "OK"}</td>
                      <td className="px-5 py-2 text-fg-muted">{p.auth_state === "authenticated" ? "Signed in" : "Visitor"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {r.features.length > 0 && (
              <>
                <h3 className="mb-2 mt-6 text-body font-semibold">Features we found</h3>
                <ul className="grid gap-x-8 sm:grid-cols-2">
                  {r.features.map((f) => (
                    <li key={f.key} className="flex justify-between gap-3 border-b border-border py-2 text-body">
                      <span>{f.name}</span>
                      <span className="text-fg-muted">{f.status === "tested" ? "Tested" : f.status === "untested" ? "Not tested" : humanize(f.status)}</span>
                    </li>
                  ))}
                </ul>
              </>
            )}
          </ReportSection>

          <ReportSection id="access" n={5} title="Signing in and permissions">
            <KeyValue
              items={[
                ["Browsed as", r.access.auth_state === "authenticated" ? "A signed-in test account" : "A visitor (not signed in)"],
                ["Sign-in result", r.access.status ? `${humanize(r.access.status)}${r.access.detail ? ` — ${r.access.detail}` : ""}` : "Not attempted"],
                ...(r.access.onboarding?.steps?.length ? ([["Account setup", r.access.onboarding.steps.join("; ")]] as [ReactNode, ReactNode][]) : []),
              ]}
            />
            <h3 className="mb-2 mt-6 text-body font-semibold">Permissions you gave</h3>
            <ul className="space-y-2 text-body">
              {r.access.approvals.map((a) => (
                <li key={a.kind} className="flex gap-2.5">
                  <Icon.Check size={15} className="mt-1 shrink-0 text-success" />
                  <span>
                    <span className="font-medium">{APPROVAL[a.kind] ?? humanize(a.kind)}</span>{" "}
                    <span className="text-fg-subtle">· {new Date(a.at).toLocaleString()}</span>
                  </span>
                </li>
              ))}
            </ul>
          </ReportSection>

          <ReportSection id="setup" n={6} title="The website and our setup">
            <KeyValue
              items={[
                ["Project", r.target.project],
                ["Website", <Mono key="o">{r.target.origin}</Mono>],
                ["Proof of ownership", r.target.verification === "operator_allowlist" ? "Workspace allowlist" : r.target.verification === "dns_txt" ? "DNS record" : r.target.verification === "http_file" ? "Verification file" : humanize(r.target.verification)],
                ["Screens", r.target.viewports.map((v) => SCREEN[v] ?? v).join(", ")],
                ["Browser", r.target.browser],
              ]}
            />
          </ReportSection>

          <ReportSection id="limits" n={7} title="What wasn't checked">
            <ul className="space-y-2.5 text-body">
              {r.coverage.limitations.map((l) => (
                <li key={l} className="flex gap-2.5">
                  <Icon.SevInfo className="mt-1 shrink-0 text-fg-subtle" />
                  <span className="text-fg-muted">{l}</span>
                </li>
              ))}
            </ul>
            {r.coverage.egress_blocked_requests > 0 && (
              <p className="mt-4 text-body text-fg-muted">
                For safety, {r.coverage.egress_blocked_requests} request{r.coverage.egress_blocked_requests === 1 ? " was" : "s were"} blocked (for example, to internal network addresses).
              </p>
            )}
          </ReportSection>

          <ReportSection id="next" n={8} title="What to do next">
            <ol className="space-y-3 text-body">
              {[
                confirmed.length
                  ? `Fix the ${confirmed.length} confirmed problem${confirmed.length > 1 ? "s" : ""} first. Then open ${confirmed.length > 1 ? "each one" : "it"} and press “Run the test again” to prove the fix.`
                  : "There are no confirmed problems to fix.",
                "Look at the possible problems. We saw them happen, but couldn't prove they affect visitors.",
                "Check “What wasn't checked” above, and run a new investigation for those areas if they matter.",
              ].map((t, i) => (
                <li key={t} className="flex gap-3">
                  <span className="flex size-6 shrink-0 items-center justify-center rounded-full border-[1.5px] border-[var(--wx-ink-line)] font-mono text-[11px]">{i + 1}</span>
                  <span className="text-fg-muted">{t}</span>
                </li>
              ))}
            </ol>
          </ReportSection>
        </article>
      </div>
      <EvidenceById id={openEvidence} onClose={() => setOpenEvidence(null)} />
    </div>
  );
}

function ReportSection({ id, n, title, children }: { id: string; n: number; title: string; children: ReactNode }) {
  return (
    <section id={id} className="scroll-mt-24">
      <p className="eyebrow">{String(n).padStart(2, "0")}</p>
      <h2 className="mb-5 mt-2 text-[1.625rem] font-semibold tracking-[-0.025em]">{title}</h2>
      {children}
    </section>
  );
}

function SeverityTable({ findings }: { findings: Report["findings"] }) {
  const sev: Severity[] = ["critical", "high", "medium", "low", "info"];
  return (
    <div className="mt-6 grid grid-cols-2 overflow-hidden rounded-2xl border border-border bg-surface sm:grid-cols-5 [&>*]:border-border max-sm:[&>*:nth-child(even)]:border-l max-sm:[&>*:nth-child(n+3)]:border-t sm:[&>*:not(:first-child)]:border-l">
      {sev.map((s) => (
        <div key={s} className="px-4 py-3">
          <SeverityLabel severity={s} />
          <div className="mt-1 text-[1.5rem] font-semibold tabular">{findings.filter((f) => f.severity === s).length}</div>
        </div>
      ))}
    </div>
  );
}
