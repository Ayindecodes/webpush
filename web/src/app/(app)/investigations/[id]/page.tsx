"use client";

import { useParams } from "next/navigation";
import { Fragment, useMemo, useState } from "react";

import { Mark } from "@/components/brand/logo";
import { EvidenceDialog, EvidenceImage } from "@/components/evidence/evidence";
import { JourneyMatrix } from "@/components/journey-matrix";
import { WorkerNotice } from "@/components/briefing";
import { FindingRows } from "@/components/lists";
import { useCrumbs } from "@/components/shell/context";
import { Timeline } from "@/components/timeline";
import { Icon } from "@/components/ui/icons";
import {
  Button,
  ButtonLink,
  ConfirmDialog,
  EmptyState,
  LoadError,
  LoadingRows,
  Mono,
  Notice,
  PageHeader,
  Section,
  Tabs,
  cx,
} from "@/components/ui/primitives";
import { StatusPill } from "@/components/ui/status";
import { api } from "@/lib/api";
import { ACTIVE_STATUSES, duration, hostOf, humanize, pathOf, relativeTime } from "@/lib/format";
import { useApi, useEventStream, useNow } from "@/lib/hooks";
import type { Evidence, Feature, Finding, Investigation, Journey, PageRecord } from "@/lib/types";

type Tab = "activity" | "pages" | "journeys" | "features" | "coverage";

/** Plain-language names for the worker's phases (keys come from worker/recorder.py). */
const PHASE_LABEL: Record<string, string> = {
  validate: "Check the website and the rules",
  discover_public: "Explore the public pages",
  authenticate: "Sign in",
  discover_authenticated: "Explore the signed-in pages",
  plan: "Decide what to test",
  execute: "Try the journeys",
  diagnose: "Work out why things failed",
  reproduce: "Write and run proof tests",
  report: "Write the report",
};

export default function InvestigationPage() {
  const { id } = useParams<{ id: string }>();
  const inv = useApi<Investigation>(`/api/investigations/${id}`, {
    refreshInterval: (d) => (d && ACTIVE_STATUSES.has(d.status) ? 1500 : 0),
  });
  const active = !!inv.data && ACTIVE_STATUSES.has(inv.data.status);
  const poll = active ? 3000 : 0;
  // One fetch on load; keeps polling only while the investigation is running.
  const { events } = useEventStream(id, active);
  const pages = useApi<PageRecord[]>(inv.data ? `/api/investigations/${id}/pages` : null, { refreshInterval: poll });
  const findings = useApi<Finding[]>(inv.data ? `/api/investigations/${id}/findings` : null, { refreshInterval: poll });
  const journeys = useApi<Journey[]>(inv.data ? `/api/investigations/${id}/journeys` : null, { refreshInterval: poll });
  const features = useApi<Feature[]>(inv.data ? `/api/investigations/${id}/features` : null, { refreshInterval: poll });
  const [tab, setTab] = useState<Tab>("activity");
  const [tabOpen, setTabOpen] = useState(false);
  const now = useNow(1000, active);
  useCrumbs([{ label: "Investigations", href: "/investigations" }, { label: inv.data ? hostOf(inv.data.origin) : "Investigation" }]);

  const observedFailures = useMemo(() => {
    // Failed checks seen during execution that diagnosis has not yet turned into findings.
    if ((findings.data?.length ?? 0) > 0) return [];
    return events.filter((e) => e.kind === "assertion" && e.level === "error");
  }, [events, findings.data]);

  if (inv.error) return <LoadError error={inv.error} retry={() => inv.mutate()} what="investigation" backHref="/investigations" backLabel="All investigations" />;
  if (!inv.data) return <LoadingRows rows={6} />;
  const i = inv.data;
  const finished = !ACTIVE_STATUSES.has(i.status);
  const confirmed = i.finding_counts.confirmed_defect ?? 0;
  const possible = i.finding_counts.warning ?? 0;

  return (
    <div className="space-y-10">
      <PageHeader
        eyebrow={`Investigation · ${i.project_name ?? "project"}`}
        title={hostOf(i.origin)}
        description={i.goal || undefined}
        meta={
          <>
            <StatusPill status={i.status} />
            <span>{i.mode === "authenticated" ? "Signed in with a test account" : "Explored as a visitor"}</span>
            <span>{i.config.viewports.map((v) => (v === "desktop" ? "computer" : v === "mobile" ? "phone" : v)).join(" & ")}</span>
            <span>Started {relativeTime(i.started_at ?? i.created_at, now)}</span>
            <span>Running time {duration(i.started_at, i.finished_at, now)}</span>
          </>
        }
        actions={<Controls inv={i} onChange={() => inv.mutate()} />}
      />

      {i.status === "awaiting_human" && (
        <Notice tone="warn" title="It needs your help" action={<ResumeButton id={i.id} onDone={() => inv.mutate()} />}>
          {i.blocked_reason} We keep the browser waiting for up to 30 minutes.
        </Notice>
      )}
      {i.status === "blocked" && (
        <Notice tone="warn" title="It couldn't continue">
          {i.blocked_reason}
        </Notice>
      )}
      {i.status === "failed" && (
        <Notice tone="danger" title="The investigation stopped with an error">
          {i.error}
        </Notice>
      )}

      {finished ? (
        <ResultSummary inv={i} confirmed={confirmed} possible={possible} pages={pages.data?.length ?? i.page_count} />
      ) : (
        <LiveView inv={i} />
      )}

      {i.status === "queued" && <WorkerNotice queuedAt={i.created_at} waiting />}

      {!finished && <Progress inv={i} />}

      {finished && (
        <Section eyebrow="Problems" title={findings.data?.length ? "What we found" : "Problems"} description={findings.data?.length ? "Click a problem to see what it means, the proof, and how to fix it." : undefined}>
          <ProblemsTab findings={findings.data} observed={observedFailures.map((e) => e.message)} finished={finished} />
        </Section>
      )}

      {journeys.data && journeys.data.length > 0 && (
        <Section eyebrow="What we tried" title="Journeys" description="A journey is something a visitor does from start to finish, like buying a product.">
          <ul className="panel divide-y divide-border overflow-hidden">
            {journeys.data.flatMap((j) => {
              const byScreen = new Map<string, { failed: number; total: number }>();
              j.runs.forEach((r) => {
                const cur = byScreen.get(r.viewport_name) ?? { failed: 0, total: 0 };
                cur.total += 1;
                if (r.status !== "passed") cur.failed += 1;
                byScreen.set(r.viewport_name, cur);
              });
              return [...byScreen.entries()].map(([screen, c]) => (
                <li key={`${j.id}-${screen}`} className="flex flex-wrap items-center gap-3 px-5 py-4 text-body">
                  <span className={cx("flex size-7 items-center justify-center rounded-full", c.failed ? "bg-danger-soft text-danger" : "bg-success-soft text-success")} aria-hidden>
                    {c.failed ? <Icon.X size={14} /> : <Icon.Check size={14} />}
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="font-semibold">{j.name}</span> on a {SCREEN_WORD[screen] ?? screen}
                  </span>
                  <span className={c.failed ? "font-medium text-danger" : "text-success"}>
                    {c.failed ? `Failed ${c.failed} of ${c.total} ${c.total === 1 ? "try" : "tries"}` : c.total > 1 ? `Worked all ${c.total} tries` : "Worked"}
                  </span>
                </li>
              ));
            })}
          </ul>
        </Section>
      )}

      {finished && i.summary?.limitations && i.summary.limitations.length > 0 && (
        <Section eyebrow="Be aware" title="What we didn't check" description="A clean result only covers what was tested.">
          <ul className="space-y-2 text-body">
            {i.summary.limitations.slice(0, 4).map((l) => (
              <li key={l} className="flex gap-2.5">
                <Icon.SevInfo className="mt-1 shrink-0 text-fg-subtle" />
                <span className="text-fg-muted">{l}</span>
              </li>
            ))}
          </ul>
        </Section>
      )}

      <details className="group panel" onToggle={(e) => setTabOpen((e.target as HTMLDetailsElement).open)}>
        <summary className="flex cursor-pointer list-none items-center justify-between gap-3 px-6 py-5 [&::-webkit-details-marker]:hidden">
          <span>
            <span className="block text-[1.0625rem] font-semibold tracking-[-0.01em]">Technical details</span>
            <span className="block text-label text-fg-muted">Every step the browser took, every page, and the raw evidence. Mostly useful for developers.</span>
          </span>
          <Icon.ChevronDown className="shrink-0 text-fg-subtle transition-transform group-open:rotate-180" />
        </summary>
        {tabOpen && (
          <div className="border-t border-border px-4 pb-6 pt-5 sm:px-6">
            <Tabs
              label="Technical details"
              value={tab}
              onChange={setTab}
              tabs={[
                { value: "activity", label: "Step-by-step log", count: events.length },
                { value: "journeys", label: "Journey steps", count: journeys.data?.reduce((a, j) => a + j.runs.length, 0) },
                { value: "pages", label: "Pages", count: pages.data?.length },
                { value: "features", label: "Features", count: features.data?.length },
                { value: "coverage", label: "Coverage" },
              ]}
            />
            <div className="pt-6">
              {tab === "activity" && <Timeline events={events} />}
              {tab === "pages" && <Pages pages={pages.data} />}
              {tab === "journeys" &&
                (!journeys.data ? (
                  <LoadingRows />
                ) : journeys.data.length === 0 ? (
                  <EmptyState compact title="No journeys yet" description="Journeys (like checkout) are planned after the site has been explored." />
                ) : (
                  <div className="space-y-10">
                    {journeys.data.map((j) => (
                      <Section key={j.id} title={j.name} description="Each square is one step of one try. Click a square to see what happened." actions={<StatusPill status={j.status} />}>
                        <JourneyMatrix journey={j} />
                      </Section>
                    ))}
                  </div>
                ))}
              {tab === "features" && <Features items={features.data} />}
              {tab === "coverage" && <Coverage inv={i} />}
            </div>
          </div>
        )}
      </details>
    </div>
  );
}

const SCREEN_WORD: Record<string, string> = { desktop: "computer", tablet: "tablet", mobile: "phone" };

function Progress({ inv }: { inv: Investigation }) {
  return (
    <Section eyebrow="Progress" title="Steps">
      <ol className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {inv.phases.length === 0 && <li className="text-body text-fg-subtle">Waiting for a free browser…</li>}
        {inv.phases.map((p, n) => (
          <li key={p.key} className={cx("panel flex gap-3 p-4 text-body", p.status === "running" && "border-[var(--wx-ink-line)]")}>
            <span
              className={cx(
                "flex size-7 shrink-0 items-center justify-center rounded-full border-[1.5px] font-mono text-[11px]",
                p.status === "done" && "border-fg bg-fg text-bg",
                p.status === "running" && "border-brand text-brand-text",
                (p.status === "failed" || p.status === "blocked") && "border-warning text-warning",
                (p.status === "pending" || p.status === "skipped") && "border-border-strong text-fg-subtle",
              )}
              aria-hidden
            >
              {p.status === "done" ? <Icon.Check size={13} /> : p.status === "running" ? <span className="wx-live-dot size-2 rounded-full bg-brand" /> : n + 1}
            </span>
            <span className="min-w-0">
              <span className={cx("block", p.status === "pending" || p.status === "skipped" ? "text-fg-subtle" : "font-medium")}>
                {PHASE_LABEL[p.key] ?? p.label}
                {p.status === "skipped" && " (not needed)"}
              </span>
              <span className="sr-only"> — {humanize(p.status)}</span>
              {p.status === "running" && <span className="mt-0.5 block text-label text-brand-text">Working on it…</span>}
            </span>
          </li>
        ))}
      </ol>
    </Section>
  );
}

function ResultSummary({ inv, confirmed, possible, pages }: { inv: Investigation; confirmed: number; possible: number; pages: number }) {
  const headline =
    inv.status !== "completed"
      ? "This investigation didn't finish."
      : confirmed > 0
        ? `We found ${confirmed} confirmed problem${confirmed > 1 ? "s" : ""}.`
        : possible > 0
          ? `No confirmed problems — ${possible} possible one${possible > 1 ? "s" : ""} to look at.`
          : "No problems found in what we checked.";
  return (
    <div className="card-ink flex flex-col gap-6 p-7 sm:p-9 lg:flex-row lg:items-center lg:justify-between">
      <div className="min-w-0">
        <p className="eyebrow">Result</p>
        <p className="mt-3 text-[1.75rem] font-semibold leading-tight tracking-[-0.03em]">{headline}</p>
        <p className="mt-2 max-w-2xl text-body text-fg-muted">
          Based on {pages} page{pages === 1 ? "" : "s"} and every journey try shown below.{" "}
          {inv.status === "completed" ? "The report explains each problem in plain words, with the evidence." : "Whatever was recorded before it stopped is still available."}
        </p>
      </div>
      <ButtonLink href={`/investigations/${inv.id}/report`} variant="primary" size="lg" icon={<Icon.ArrowRight size={15} />} trailingIcon className="shrink-0">
        Read the report
      </ButtonLink>
    </div>
  );
}

function Controls({ inv, onChange }: { inv: Investigation; onChange: () => void }) {
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [confirmStop, setConfirmStop] = useState(false);
  const act = async (action: "pause" | "resume" | "stop") => {
    setBusy(action);
    setError(null);
    try {
      await api.post(`/api/investigations/${inv.id}/${action}`);
      onChange();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(null);
      setConfirmStop(false);
    }
  };
  if (!ACTIVE_STATUSES.has(inv.status)) {
    return (
      <>
        <ButtonLink href={`/investigations/new?url=${encodeURIComponent(inv.origin ?? "")}`} variant="paper" icon={<Icon.Refresh />}>
          Run again
        </ButtonLink>
        <ButtonLink href={`/investigations/${inv.id}/report`} variant="primary" icon={<Icon.Book />}>
          Report
        </ButtonLink>
      </>
    );
  }
  const pausePending = inv.requested_control === "pause" && inv.status === "running";
  const stopPending = inv.requested_control === "stop";
  return (
    <div className="flex flex-wrap items-center gap-2">
      {error && (
        <span role="alert" className="text-label text-danger">
          {error}
        </span>
      )}
      {inv.status === "paused" ? (
        <Button variant="primary" onClick={() => act("resume")} loading={busy === "resume"} icon={<Icon.Play />}>
          Resume
        </Button>
      ) : inv.status !== "awaiting_human" ? (
        <Button onClick={() => act("pause")} loading={busy === "pause"} disabled={pausePending || stopPending || inv.status === "queued"} icon={<Icon.Pause />}>
          {pausePending ? "Pausing after this step…" : "Pause"}
        </Button>
      ) : null}
      <Button onClick={() => setConfirmStop(true)} disabled={stopPending} icon={<Icon.Stop />} variant="danger">
        {stopPending ? "Stopping…" : "Stop"}
      </Button>
      <ConfirmDialog
        open={confirmStop}
        title="Stop this investigation?"
        description="Everything recorded so far is kept, but it can't be resumed. You can always start a new one."
        confirmLabel="Stop investigation"
        busy={busy === "stop"}
        onCancel={() => setConfirmStop(false)}
        onConfirm={() => act("stop")}
      />
    </div>
  );
}

function ResumeButton({ id, onDone }: { id: string; onDone: () => void }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  return (
    <span className="flex flex-col items-end gap-1">
      <Button
        variant="primary"
        loading={busy}
        onClick={async () => {
          setBusy(true);
          setError(null);
          try {
            await api.post(`/api/investigations/${id}/resume`);
            onDone();
          } catch (e) {
            setError((e as Error).message);
          } finally {
            setBusy(false);
          }
        }}
      >
        I&apos;ve done it — continue
      </Button>
      {error && <span className="text-label text-danger">{error}</span>}
    </span>
  );
}

function LiveView({ inv }: { inv: Investigation }) {
  const [open, setOpen] = useState<Evidence | null>(null);
  return (
    <div className="grid gap-8 lg:grid-cols-[minmax(0,1.3fr)_minmax(0,1fr)]">
      <div className="card-ink overflow-hidden">
        <div className="flex items-center gap-3 border-b-[1.5px] border-[var(--wx-ink-line)] bg-surface-2 px-4 py-3">
          <span className="flex gap-1.5" aria-hidden>
            <span className="size-2.5 rounded-full bg-border-strong" />
            <span className="size-2.5 rounded-full bg-border-strong" />
            <span className="size-2.5 rounded-full bg-border-strong" />
          </span>
          <span className="flex min-w-0 flex-1 items-center gap-2 rounded-full border border-border bg-surface px-3 py-1 font-mono text-[12px] text-fg-muted" title={inv.current_url ?? ""}>
            <Icon.Lock size={12} className="shrink-0" />
            <span className="truncate">{inv.current_url ?? inv.origin}</span>
          </span>
        </div>
        <div className="relative max-h-[460px] min-h-56 overflow-hidden bg-surface">
          {inv.latest_screenshot_id ? (
            <EvidenceImage id={inv.latest_screenshot_id} alt={inv.current_title ?? "What the browser is looking at"} onOpen={setOpen} />
          ) : (
            <div className="flex h-72 flex-col items-center justify-center gap-4 text-fg-muted">
              <Mark size={56} active />
              <span className="text-body">{inv.status === "queued" ? "Waiting for a free browser…" : "Opening the website…"}</span>
            </div>
          )}
        </div>
      </div>
      <div className="min-w-0">
        <p className="eyebrow">Now</p>
        <p className="mt-3 text-[1.375rem] font-semibold leading-snug tracking-[-0.02em]" aria-live="polite">
          {inv.status === "paused" ? "Paused" : inv.status === "awaiting_human" ? "Waiting for you" : (inv.current_action ?? "Getting ready")}
        </p>
        <dl className="mt-6 space-y-4 text-body">
          <div>
            <dt className="text-label text-fg-subtle">Page</dt>
            <dd className="mt-0.5 break-words font-medium">{inv.current_title || "—"}</dd>
            <dd>
              <Mono className="break-all text-fg-subtle">{pathOf(inv.current_url)}</Mono>
            </dd>
          </div>
        </dl>
        <p className="mt-8 text-label leading-relaxed text-fg-subtle">
          The picture updates after each page and each step — it&apos;s a series of snapshots, not a video. Click it to see the full
          screenshot.
        </p>
      </div>
      <EvidenceDialog evidence={open} onClose={() => setOpen(null)} />
    </div>
  );
}

const PAGE_TYPE: Record<string, string> = {
  home: "Home",
  listing: "List of products",
  product: "Product",
  cart: "Cart",
  checkout: "Checkout",
  confirmation: "Confirmation",
  login: "Sign in",
  register: "Sign up",
  onboarding: "Setup",
  account: "Account",
  orders: "Orders",
  support: "Help",
  content: "Page",
};

function Pages({ pages }: { pages: PageRecord[] | undefined }) {
  const [open, setOpen] = useState<string | null>(null);
  if (!pages) return <LoadingRows />;
  if (pages.length === 0) return <EmptyState compact title="No pages yet" description="Pages appear here as soon as the browser opens them." />;
  const groups = [
    { auth: "public", title: "Public pages", items: pages.filter((p) => p.auth_state !== "authenticated") },
    { auth: "authenticated", title: "Signed-in pages", items: pages.filter((p) => p.auth_state === "authenticated") },
  ].filter((g) => g.items.length);
  return (
    <div className="space-y-10">
      {groups.map((g) => (
        <Section key={g.auth} title={g.title} description={`${g.items.length} page${g.items.length === 1 ? "" : "s"}. Click a row for its screenshot and details.`}>
          <div className="panel overflow-x-auto">
            <table className="w-full min-w-[640px] text-left text-body">
              <thead className="font-mono text-[11px] uppercase tracking-[0.12em] text-fg-subtle">
                <tr className="border-b border-border">
                  <th className="px-5 py-3 font-normal">Address</th>
                  <th className="px-3 py-3 font-normal">Kind of page</th>
                  <th className="px-3 py-3 font-normal">Answer</th>
                  <th className="px-3 py-3 text-right font-normal">Errors</th>
                  <th className="px-5 py-3 text-right font-normal">Load time</th>
                </tr>
              </thead>
              <tbody>
                {g.items.map((p) => {
                  const issues = p.console_error_count + p.failed_request_count;
                  return (
                    <Fragment key={p.id}>
                      <tr className="border-b border-border last:border-b-0">
                        <td className="max-w-[340px] px-5 py-0">
                          <button
                            className="flex w-full items-center gap-2 py-3 text-left font-mono text-[13px] hover:underline"
                            onClick={() => setOpen(open === p.id ? null : p.id)}
                            aria-expanded={open === p.id}
                            title={p.url}
                          >
                            <Icon.Chevron size={12} className={cx("shrink-0 text-fg-subtle transition-transform", open === p.id && "rotate-90")} />
                            <span className="truncate">{pathOf(p.url)}</span>
                          </button>
                        </td>
                        <td className="px-3 py-3 text-fg-muted">{PAGE_TYPE[p.classification] ?? humanize(p.classification)}</td>
                        <td className="px-3 py-3 tabular">
                          {p.status_code == null ? "—" : p.status_code >= 400 ? <span className="font-medium text-danger">Error {p.status_code}</span> : <span className="text-fg-muted">OK</span>}
                        </td>
                        <td className="px-3 py-3 text-right tabular">{issues > 0 ? <span className="font-semibold">{issues}</span> : <span className="text-fg-subtle">0</span>}</td>
                        <td className="px-5 py-3 text-right tabular text-fg-muted">{p.load_ms != null ? `${(p.load_ms / 1000).toFixed(1)} s` : "—"}</td>
                      </tr>
                      {open === p.id && (
                        <tr className="border-b border-border bg-surface-2/50">
                          <td colSpan={5} className="p-5">
                            <div className="grid gap-5 md:grid-cols-[300px_1fr]">
                              <div className="max-h-72 overflow-hidden rounded-xl border border-border-strong bg-surface">
                                <EvidenceImage id={p.screenshot_id} alt={`Screenshot of ${pathOf(p.url)}`} />
                              </div>
                              <div className="space-y-2 text-body">
                                <div className="font-semibold">{p.title || "Untitled page"}</div>
                                {p.inventory.h1?.length ? <div className="text-fg-muted">Main heading: “{p.inventory.h1.join(" / ")}”</div> : null}
                                <div className="text-fg-muted">
                                  {p.inventory.link_count ?? 0} links · {p.inventory.forms?.length ?? 0} forms · {p.inventory.buttons?.length ?? 0} different buttons
                                </div>
                                {p.inventory.forms?.map((f, idx) => (
                                  <div key={idx} className="rounded-xl border border-border bg-surface p-3">
                                    <div className="text-label font-medium">Form sending to {pathOf(f.action)}</div>
                                    <div className="mt-0.5 text-label text-fg-subtle">
                                      Fields: {f.fields.map((x) => `${x.label || x.type}${x.required ? " (required)" : ""}`).join(", ") || "none"}
                                    </div>
                                  </div>
                                ))}
                                {p.discovered_from && <div className="text-label text-fg-subtle">Found via a link on {pathOf(p.discovered_from)}</div>}
                              </div>
                            </div>
                          </td>
                        </tr>
                      )}
                    </Fragment>
                  );
                })}
              </tbody>
            </table>
          </div>
        </Section>
      ))}
    </div>
  );
}

function ProblemsTab({ findings, observed, finished }: { findings: Finding[] | undefined; observed: string[]; finished: boolean }) {
  if (!findings) return <LoadingRows />;
  return (
    <div className="space-y-8">
      {observed.length > 0 && (
        <Section title="Failures seen — still being checked" description="These failed while testing. They become problems only after we repeat them and look at the evidence.">
          <ul className="space-y-2 rounded-2xl border-[1.5px] border-dashed border-border-strong p-4 text-body">
            {observed.map((m, i) => (
              <li key={i} className="flex gap-2.5">
                <Icon.SevMedium className="mt-1 shrink-0 text-warning" />
                {m}
              </li>
            ))}
          </ul>
        </Section>
      )}
      {findings.length === 0 ? (
        <EmptyState
          compact
          icon={<Icon.Check size={20} />}
          title={finished ? "No problems found" : "No problems yet"}
          description={finished ? "Nothing failed in the parts we checked. See “What wasn't checked” for the limits." : "Problems appear once failures have been repeated and diagnosed."}
        />
      ) : (
        <FindingRows items={findings} showTarget={false} />
      )}
    </div>
  );
}

const FEATURE_STATUS: Record<string, string> = {
  tested: "Tested",
  untested: "Not tested",
  discovered: "Found, not tested",
  needs_permission: "Needs your permission",
  needs_human: "Needs a person",
  inaccessible: "Couldn't reach it",
};

function Features({ items }: { items: Feature[] | undefined }) {
  if (!items) return <LoadingRows />;
  if (items.length === 0) return <EmptyState compact title="No features listed yet" description="Features (sign-up, search, checkout…) are listed after the site is explored." />;
  return (
    <ul className="panel divide-y divide-border overflow-hidden">
      {items.map((f) => (
        <li key={f.id} className="grid grid-cols-[1fr_auto] gap-2 px-5 py-3.5 text-body sm:grid-cols-[240px_180px_1fr]">
          <div className="font-semibold">{f.name}</div>
          <div>
            <span className={cx("inline-flex items-center gap-1.5", f.status === "tested" ? "text-fg" : "text-fg-muted")}>
              {f.status === "tested" ? <Icon.Check size={13} /> : <span className="size-1.5 rounded-full border border-current" />}
              {FEATURE_STATUS[f.status] ?? humanize(f.status)}
            </span>
          </div>
          <div className="col-span-2 truncate text-label text-fg-subtle sm:col-span-1">
            {String(f.details.result ?? f.details.note ?? f.details.reason ?? (f.page_url ? pathOf(f.page_url) : ""))}
          </div>
        </li>
      ))}
    </ul>
  );
}

function Coverage({ inv }: { inv: Investigation }) {
  const s = inv.summary;
  if (!s || !s.limitations) return <EmptyState compact title="Available when the investigation finishes" description="We list everything we couldn't check, so a clean result is never mistaken for full coverage." />;
  return (
    <div className="space-y-10">
      <Section title="Limits of this investigation" description="Things we didn't or couldn't check. A problem could still hide here.">
        <ul className="space-y-2.5 text-body">
          {s.limitations.map((l) => (
            <li key={l} className="flex gap-2.5">
              <Icon.SevInfo className="mt-1 shrink-0 text-fg-subtle" />
              <span className="text-fg-muted">{l}</span>
            </li>
          ))}
        </ul>
      </Section>
      <Section title="Exploring the site">
        <ul className="space-y-1.5 text-body text-fg-muted">
          {(s.crawl_notes ?? []).map((n) => (
            <li key={n}>{n}</li>
          ))}
        </ul>
        {s.skipped_links && Object.keys(s.skipped_links).length > 0 && (
          <div className="mt-4 text-body">
            <div className="mb-1.5 font-semibold">Links we didn&apos;t follow</div>
            <ul className="space-y-1 text-fg-muted">
              {Object.entries(s.skipped_links).map(([reason, n]) => (
                <li key={reason}>
                  {n} × {reason}
                </li>
              ))}
            </ul>
          </div>
        )}
        {s.egress_blocked ? (
          <p className="mt-4 text-body text-fg-muted">
            {s.egress_blocked} request{s.egress_blocked === 1 ? " was" : "s were"} blocked by our safety rules (for example, to internal network addresses).
          </p>
        ) : null}
      </Section>
      {s.auth && (
        <Section title="Signing in">
          <p className="text-body text-fg-muted">
            {humanize(s.auth.status)} — {s.auth.detail}
          </p>
          {s.auth.onboarding?.steps?.length ? (
            <ul className="mt-2 space-y-1 text-label text-fg-subtle">
              {s.auth.onboarding.steps.map((x) => (
                <li key={x}>{x}</li>
              ))}
            </ul>
          ) : null}
        </Section>
      )}
    </div>
  );
}
