"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useMemo, useState, type ReactNode } from "react";

import { EvidenceBody, EvidenceDialog, EvidenceImage, EvidenceMeta } from "@/components/evidence/evidence";
import { useCrumbs } from "@/components/shell/context";
import { Timeline } from "@/components/timeline";
import { Icon } from "@/components/ui/icons";
import { Button, ButtonLink, CodeBlock, LoadError, LoadingRows, Mono, Notice, PageHeader, Section, Tabs, cx } from "@/components/ui/primitives";
import { ClassificationBadge, HypothesisStatus, SeverityLabel, StatusPill, TestStatusBadge, ViewportIcon } from "@/components/ui/status";
import { api } from "@/lib/api";
import { formatMs, hostOf, humanize, relativeTime } from "@/lib/format";
import { useApi, useEventStream } from "@/lib/hooks";
import type { Evidence, Finding, ReproTest, TestRun } from "@/lib/types";

const KIND_TABS: { kind: string; label: string }[] = [
  { kind: "hit_test", label: "Tap test" },
  { kind: "computed_styles", label: "Styles" },
  { kind: "dom_snapshot", label: "Page structure" },
  { kind: "network_log", label: "Network" },
  { kind: "console_log", label: "Console" },
  { kind: "layout_overflow", label: "Layout" },
  { kind: "test_output", label: "Test output" },
];
const SCREEN: Record<string, string> = { desktop: "computer", tablet: "tablet", mobile: "phone" };

const SEVERITY_MEANING: Record<string, string> = {
  critical: "Critical — it stops visitors from doing something important, like paying.",
  high: "High — it seriously gets in visitors' way.",
  medium: "Medium — something is broken, but most visitors can still get things done.",
  low: "Low — a small annoyance.",
  info: "Info — worth knowing, not necessarily a problem.",
};

export default function FindingPage() {
  const { id } = useParams<{ id: string }>();
  const finding = useApi<Finding>(`/api/findings/${id}`);
  const evidence = useApi<Evidence[]>(finding.data ? `/api/findings/${id}/evidence` : null, { refreshInterval: 5 * 60_000 });
  const f = finding.data;
  useCrumbs([{ label: "Problems found", href: "/findings" }, { label: f ? f.title : "Problem" }]);

  if (finding.error) return <LoadError error={finding.error} retry={() => finding.mutate()} what="problem" backHref="/findings" backLabel="All problems" />;
  if (!f) return <LoadingRows rows={6} />;
  const r = f.reproduction;
  const screen = f.viewport_name ? (SCREEN[f.viewport_name] ?? f.viewport_name) : null;

  return (
    <div className="space-y-14">
      <PageHeader
        eyebrow={`Problem · ${hostOf(f.origin)}`}
        title={f.title}
        meta={
          <>
            <SeverityLabel severity={f.severity} />
            <ClassificationBadge value={f.classification} />
            {f.test_status && <TestStatusBadge status={f.test_status} />}
            <span>Found {relativeTime(f.created_at)}</span>
          </>
        }
        actions={
          <ButtonLink href={`/investigations/${f.investigation_id}`} variant="paper" icon={<Icon.ArrowLeft size={14} />}>
            Back to the investigation
          </ButtonLink>
        }
      />

      {r.status === "fixed" && (
        <Notice tone="success" title="Fixed">
          The automatic test passed{r.fixed_at ? ` on ${new Date(r.fixed_at).toLocaleString()}` : ""} after failing before, so this problem no
          longer happens. Run it again any time to make sure it stays fixed.
        </Notice>
      )}

      {/* In plain words */}
      <div className="card-ink overflow-hidden">
        <div className="p-7 sm:p-9">
          <p className="eyebrow">In plain words</p>
          <p className="mt-4 max-w-3xl text-[1.125rem] leading-relaxed">{f.summary}</p>
        </div>
        {(f.expected || f.observed) && (
          <div className="grid border-t-[1.5px] border-[var(--wx-ink-line)] md:grid-cols-2">
            <div className="p-6 sm:p-7">
              <div className="text-label font-semibold text-fg-subtle">What should happen</div>
              <p className="mt-1.5 text-body">{f.expected ?? "—"}</p>
            </div>
            <div className="bg-danger-soft p-6 sm:p-7 md:border-l-[1.5px] md:border-[var(--wx-ink-line)]">
              <div className="text-label font-semibold text-danger">What actually happens</div>
              <p className="mt-1.5 text-body">{f.observed ?? "—"}</p>
            </div>
          </div>
        )}
      </div>

      <div className="grid gap-4 sm:grid-cols-3">
        <Fact label="How serious">{SEVERITY_MEANING[f.severity] ?? humanize(f.severity)}</Fact>
        <Fact label="Who it affects">
          {screen ? `Visitors on a ${screen}` : "All visitors"}
          {r.passing_viewports?.length ? ` — it works on ${r.passing_viewports.map((v) => `a ${SCREEN[v] ?? v}`).join(" and ")}` : ""}.
        </Fact>
        <Fact label="How sure we are">
          {r.total_runs != null
            ? f.kind === "journey_failure"
              ? `It failed ${r.failed_runs} out of ${r.total_runs} times we tried.`
              : `Seen on ${r.failed_runs} of ${r.total_runs} page loads.`
            : humanize(r.status)}
          {r.status === "fixed" ? " It has since been fixed." : f.classification === "confirmed_defect" ? " Confirmed." : f.classification === "warning" ? " Not yet proven to affect visitors." : ""}
        </Fact>
      </div>

      <Section id="evidence" eyebrow="The proof" title="What our browser saw" description="Screenshots from the real test. Password fields are blacked out.">
        {evidence.error ? (
          <Notice tone="danger">{evidence.error.message}</Notice>
        ) : !evidence.data ? (
          <LoadingRows rows={2} />
        ) : (
          <Screenshots items={evidence.data} finding={f} />
        )}
      </Section>

      <Section id="causes" eyebrow="Why" title="Why it happens" description="Possible causes we checked. Each is backed — or ruled out — by evidence.">
        <Hypotheses finding={f} evidence={evidence.data ?? []} />
      </Section>

      {f.recommendation && (
        <Section id="fix" eyebrow="Fix" title="How to fix it">
          <div className="rounded-2xl border border-brand-line bg-brand-soft p-6 text-body leading-relaxed">{f.recommendation}</div>
        </Section>
      )}

      {f.steps_to_reproduce.length > 0 && (
        <Section id="reproduce" eyebrow="Check it yourself" title="See it with your own eyes">
          <ol className="space-y-3 text-body">
            {f.steps_to_reproduce.map((s, i) => (
              <li key={i} className="flex gap-3">
                <span className="flex size-6 shrink-0 items-center justify-center rounded-full border-[1.5px] border-[var(--wx-ink-line)] font-mono text-[11px]">{i + 1}</span>
                <span className="pt-0.5">{s}</span>
              </li>
            ))}
          </ol>
        </Section>
      )}

      <Section id="test" eyebrow="Prove the fix" title="Automatic test">
        <TestPanel finding={f} />
      </Section>

      <details className="group panel">
        <summary className="flex cursor-pointer list-none items-center justify-between gap-3 px-6 py-5 [&::-webkit-details-marker]:hidden">
          <span>
            <span className="block text-[1.0625rem] font-semibold tracking-[-0.01em]">Technical evidence</span>
            <span className="block text-label text-fg-muted">Tap tests, styles, page structure, network and console logs, and the step-by-step log — for developers.</span>
          </span>
          <Icon.ChevronDown className="shrink-0 text-fg-subtle transition-transform group-open:rotate-180" />
        </summary>
        <div className="space-y-10 border-t border-border px-4 pb-6 pt-6 sm:px-6">
          {evidence.data && <TechnicalEvidence items={evidence.data} />}
          <Section title="Step-by-step log" description="Events from the tries behind this problem.">
            <FindingTimeline finding={f} />
          </Section>
        </div>
      </details>
    </div>
  );
}

function Fact({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="panel p-5">
      <div className="text-label font-semibold text-fg-subtle">{label}</div>
      <p className="mt-1.5 text-body leading-relaxed">{children}</p>
    </div>
  );
}

function roleViewport(role: string | null) {
  return role?.split(/[#:]/)[0] ?? "";
}

function Screenshots({ items, finding }: { items: Evidence[]; finding: Finding }) {
  const [open, setOpen] = useState<Evidence | null>(null);
  const shots = items.filter((e) => e.kind === "screenshot");
  const failing = shots.find((e) => e.role?.includes(":submit_reachable:after")) ?? shots.find((e) => !e.role?.startsWith("contrast")) ?? null;
  const region = shots.find((e) => e.role?.endsWith(":element"));
  const contrast = shots.find((e) => e.role?.startsWith("contrast"));
  if (!failing && !contrast) return <p className="text-body text-fg-muted">There are no screenshots for this problem — see the technical evidence below.</p>;
  return (
    <div className="space-y-5">
      <div className={cx("grid gap-5", contrast && failing ? "md:grid-cols-2" : "")}>
        {failing && (
          <Shot
            tone="danger"
            title={`Broken${roleViewport(failing.role) || finding.viewport_name ? ` — on a ${SCREEN[roleViewport(failing.role) || finding.viewport_name || ""] ?? "screen"}` : ""}`}
            caption={failing.label.split(": ").slice(1).join(": ")}
            viewport={roleViewport(failing.role) || finding.viewport_name}
          >
            <EvidenceImage id={failing.id} alt={failing.label} onOpen={setOpen} fit />
          </Shot>
        )}
        {contrast && (
          <Shot tone="success" title={`Working — on a ${SCREEN[contrast.role?.split(":")[1] ?? ""] ?? "screen"}`} caption="the same step, for comparison" viewport={contrast.role?.split(":")[1]}>
            <EvidenceImage id={contrast.id} alt={contrast.label} onOpen={setOpen} fit />
          </Shot>
        )}
      </div>
      {region && (
        <figure className="panel overflow-hidden">
          <figcaption className="border-b border-border px-4 py-2.5 text-label font-semibold">Close-up of the button</figcaption>
          <div className="bg-surface-2/50">
            <EvidenceImage id={region.id} alt={region.label} onOpen={setOpen} className="mx-auto max-w-md" />
          </div>
        </figure>
      )}
      <p className="text-label text-fg-subtle">Click a screenshot to see it full size.</p>
      <EvidenceDialog evidence={open} onClose={() => setOpen(null)} />
    </div>
  );
}

function Shot({ tone, title, caption, viewport, children }: { tone: "danger" | "success"; title: string; caption: string; viewport?: string | null; children: ReactNode }) {
  return (
    <figure className={cx("overflow-hidden rounded-2xl border-[1.5px] bg-surface", tone === "danger" ? "border-danger/60" : "border-success/50")}>
      <figcaption className="flex items-center justify-between gap-2 border-b border-border px-4 py-2.5 text-label">
        <span className={cx("inline-flex items-center gap-1.5 font-semibold", tone === "danger" ? "text-danger" : "text-success")}>
          <ViewportIcon name={viewport} /> {title}
        </span>
        <span className="truncate text-meta text-fg-subtle">{caption}</span>
      </figcaption>
      <div className="h-[440px] bg-surface-2/40 p-2">{children}</div>
    </figure>
  );
}

function TechnicalEvidence({ items }: { items: Evidence[] }) {
  const [open, setOpen] = useState<Evidence | null>(null);
  const available = KIND_TABS.filter((t) => items.some((e) => e.kind === t.kind));
  const [tab, setTab] = useState(available[0]?.kind ?? "");
  const tabItems = items.filter((e) => e.kind === tab);
  const [selected, setSelected] = useState<string | null>(null);
  const current = tabItems.find((e) => e.id === selected) ?? tabItems.find((e) => !e.role?.startsWith("contrast")) ?? tabItems[0];
  if (items.length === 0) return <p className="text-body text-fg-subtle">No evidence is linked to this problem.</p>;
  return (
    <div className="space-y-6">
      {available.length > 0 && (
        <div>
          <Tabs
            label="Technical evidence"
            value={tab}
            onChange={(v) => {
              setTab(v);
              setSelected(null);
            }}
            tabs={available.map((t) => ({ value: t.kind, label: t.label, count: items.filter((e) => e.kind === t.kind).length }))}
          />
          {current && (
            <div className="space-y-3 pt-4">
              {tabItems.length > 1 && (
                <div className="flex flex-wrap gap-1.5">
                  {tabItems.map((e) => (
                    <button
                      key={e.id}
                      onClick={() => setSelected(e.id)}
                      aria-pressed={current.id === e.id}
                      className={cx(
                        "h-7 rounded-full border px-3 text-meta",
                        current.id === e.id ? "border-fg bg-fg text-bg" : "border-border text-fg-muted hover:text-fg",
                      )}
                    >
                      {e.role?.replace(/:/g, " · ") ?? e.label}
                    </button>
                  ))}
                </div>
              )}
              <div className="text-body font-semibold">{current.label}</div>
              <EvidenceMeta e={current} />
              <EvidenceBody evidence={current} />
            </div>
          )}
        </div>
      )}
      <div>
        <div className="mb-2 text-body font-semibold">All {items.length} evidence items</div>
        <ul className="panel divide-y divide-border overflow-hidden">
          {items.map((e) => (
            <li key={e.id} className="flex items-center gap-3 px-4 py-2 text-label">
              <span className="w-28 shrink-0 text-fg-subtle">{humanize(e.kind)}</span>
              <span className="min-w-0 flex-1 truncate">{e.label}</span>
              <Mono className="hidden text-fg-subtle sm:inline" >{e.sha256.slice(0, 10)}</Mono>
              <Button size="sm" variant="ghost" onClick={() => setOpen(e)}>
                Open
              </Button>
            </li>
          ))}
        </ul>
      </div>
      <EvidenceDialog evidence={open} onClose={() => setOpen(null)} />
    </div>
  );
}

function Hypotheses({ finding, evidence }: { finding: Finding; evidence: Evidence[] }) {
  const [open, setOpen] = useState<Evidence | null>(null);
  if (finding.hypotheses.length === 0) {
    return <p className="text-body text-fg-muted">This is something we observed directly, so there&apos;s no cause to work out. The proof above shows it.</p>;
  }
  const ordered = [...finding.hypotheses].sort((a, b) => (a.status === "supported" ? -1 : 0) - (b.status === "supported" ? -1 : 0));
  return (
    <ol className="space-y-3">
      {ordered.map((h) => (
        <li key={h.key} className={cx("rounded-2xl border-[1.5px] bg-surface p-5", h.status === "supported" ? "border-[var(--wx-ink-line)] shadow-[3px_3px_0_var(--wx-ink-shadow)]" : "border-border")}>
          <HypothesisStatus status={h.status} />
          <div className={cx("mt-2.5 text-[1.0625rem] font-semibold tracking-[-0.01em]", h.status === "not_supported" && "text-fg-muted")}>{h.title}</div>
          <p className="mt-1 text-body leading-relaxed text-fg-muted">{h.rationale}</p>
          {h.evidence.length > 0 && (
            <div className="mt-3 flex flex-wrap gap-1.5">
              {h.evidence.map((ref) => {
                const ev = evidence.find((e) => e.id === ref.evidence_id);
                return (
                  <Button key={ref.evidence_id + ref.role} size="sm" variant="paper" disabled={!ev} onClick={() => ev && setOpen(ev)} icon={<Icon.Layers size={13} />}>
                    {ref.role.replace(/:/g, " · ")}
                  </Button>
                );
              })}
            </div>
          )}
        </li>
      ))}
      <EvidenceDialog evidence={open} onClose={() => setOpen(null)} />
    </ol>
  );
}

const TEST_WORDS: Record<string, string> = {
  generated: "The test is written but hasn't been run yet.",
  reproduced: "The last time we ran it, the problem happened again — it isn't fixed yet.",
  not_reproduced: "The last time we ran it, everything worked — the problem looks fixed.",
  inconclusive: "The last run stopped before it reached the problem, so it didn't prove anything either way.",
};

function TestPanel({ finding }: { finding: Finding }) {
  const hasTest = !!finding.test_id;
  const { data: test, error, mutate } = useApi<ReproTest>(hasTest ? `/api/tests/${finding.test_id}` : null, {
    refreshInterval: (d) => (d?.runs.some((r) => r.status === "queued" || r.status === "running") ? 2000 : 0),
  });
  const [busy, setBusy] = useState(false);
  const [runError, setRunError] = useState<string | null>(null);

  if (!hasTest) {
    return (
      <Notice>
        There&apos;s no automatic test for this one. Tests are written for journeys that break (like checkout); for this kind of
        problem, use the steps above to check it.
      </Notice>
    );
  }
  if (error) return <Notice tone="danger">{error.message}</Notice>;
  if (!test) return <LoadingRows rows={3} />;
  const pending = test.runs.some((r) => r.status === "queued" || r.status === "running");

  async function run() {
    setBusy(true);
    setRunError(null);
    try {
      await api.post(`/api/tests/${test!.id}/verify`);
      await mutate();
    } catch (e) {
      setRunError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-5">
      <div className="card-ink-sm flex flex-col gap-4 p-5 sm:flex-row sm:items-center">
        <div className="min-w-0 flex-1">
          <TestStatusBadge status={pending ? "running" : test.verification_status} />
          <p className="mt-2 text-body">{pending ? "Running the test in a fresh browser…" : TEST_WORDS[test.verification_status] ?? ""}</p>
          <p className="mt-1 text-label text-fg-subtle">Fixed it? Run the test again — when it passes, you have proof the fix works.</p>
        </div>
        <Button variant="primary" onClick={run} loading={busy} disabled={pending} icon={<Icon.Play />}>
          {pending ? "Running…" : "Run the test again"}
        </Button>
      </div>
      {runError && <Notice tone="warn">{runError}</Notice>}
      <RunHistory runs={test.runs} />
      <details className="group">
        <summary className="inline-flex cursor-pointer list-none items-center gap-1.5 text-body font-medium underline-offset-4 hover:underline [&::-webkit-details-marker]:hidden">
          <Icon.Code size={15} /> Show the test code (for developers)
          <Icon.ChevronDown size={14} className="transition-transform group-open:rotate-180" />
        </summary>
        <div className="mt-4 space-y-3">
          <CodeBlock code={test.source} title={test.filename} maxHeight="32rem" actions={
            <ButtonLink href={`/api/tests/${test.id}/download`} size="sm" variant="ghost" icon={<Icon.Download />} download>
              Download
            </ButtonLink>
          } />
          <p className="text-label text-fg-subtle">A Playwright test you can run in your own pipeline. It fails while the problem exists and passes once it&apos;s fixed.</p>
        </div>
      </details>
    </div>
  );
}

function RunHistory({ runs }: { runs: TestRun[] }) {
  if (runs.length === 0) return null;
  return (
    <div>
      <div className="mb-2 text-body font-semibold">Test history</div>
      <ul className="panel divide-y divide-border overflow-hidden">
        {runs.map((r) => (
          <li key={r.id} className="flex flex-wrap items-center gap-3 px-5 py-3 text-body">
            <span className="w-28 text-fg-muted">{relativeTime(r.finished_at ?? r.created_at)}</span>
            {r.status === "finished" || r.status === "error" ? <TestStatusBadge status={r.outcome ?? "inconclusive"} /> : <StatusPill status={r.status} />}
            <span className="text-label text-fg-subtle">{r.duration_ms != null ? `took ${formatMs(r.duration_ms)}` : ""}</span>
            {r.error_message && <span className="min-w-0 flex-1 truncate font-mono text-[11.5px] text-fg-subtle" title={r.error_message}>{r.error_message.split("\n")[0]}</span>}
          </li>
        ))}
      </ul>
    </div>
  );
}

function FindingTimeline({ finding }: { finding: Finding }) {
  const { events } = useEventStream(finding.investigation_id, false);
  const runIds = finding.reproduction.run_ids;
  const relevant = useMemo(
    () =>
      events.filter(
        (e) =>
          (runIds && e.browser_run_id && runIds.includes(e.browser_run_id)) ||
          (e.kind === "finding" && e.data.finding_id === finding.id) ||
          (e.kind === "system" && typeof e.message === "string" && e.message.includes("eproduction test")),
      ),
    [events, runIds, finding.id],
  );
  if (events.length === 0) return <LoadingRows rows={3} />;
  if (relevant.length === 0)
    return (
      <p className="text-body text-fg-muted">
        This was found while exploring pages, not during a journey. See the{" "}
        <Link href={`/investigations/${finding.investigation_id}`} className="underline">
          investigation
        </Link>{" "}
        for the full log.
      </p>
    );
  return <Timeline events={relevant} newestFirst={false} highlightSeq={finding.first_event_seq} maxHeight="28rem" />;
}
