"use client";

import Link from "next/link";

import { Icon } from "@/components/ui/icons";
import { ClassificationBadge, SeverityLabel, StatusPill, TestStatusBadge, ViewportIcon } from "@/components/ui/status";
import { ACTIVE_STATUSES, duration, hostOf, relativeTime } from "@/lib/format";
import { useNow } from "@/lib/hooks";
import type { Finding, Investigation } from "@/lib/types";

const COLS = "lg:grid-cols-[minmax(0,2.2fr)_120px_80px_minmax(0,1.3fr)_80px_90px]";

/** Investigations as a responsive list: a table on wide screens, stacked rows on small ones. */
export function InvestigationTable({ items, showProject = true }: { items: Investigation[]; showProject?: boolean }) {
  const anyActive = items.some((i) => ACTIVE_STATUSES.has(i.status));
  const now = useNow(1000, anyActive);
  return (
    <div className="panel overflow-hidden">
      <div className={`hidden gap-4 border-b border-border px-5 py-3 font-mono text-[11px] uppercase tracking-[0.12em] text-fg-subtle lg:grid ${COLS}`}>
        <span>Website</span>
        <span>Status</span>
        <span className="text-right">Pages</span>
        <span>Problems found</span>
        <span className="text-right">Took</span>
        <span className="text-right">Started</span>
      </div>
      <ul className="divide-y divide-border">
        {items.map((i) => {
          const confirmed = i.finding_counts.confirmed_defect ?? 0;
          const warnings = i.finding_counts.warning ?? 0;
          const total = Object.values(i.finding_counts).reduce((a, b) => a + (b ?? 0), 0);
          return (
            <li key={i.id}>
              <Link
                href={`/investigations/${i.id}`}
                className={`grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-4 gap-y-2 px-5 py-4 transition-colors hover:bg-surface-2 ${COLS}`}
              >
                <div className="min-w-0">
                  <div className="truncate text-body font-semibold">{hostOf(i.origin)}</div>
                  <div className="truncate text-label text-fg-subtle">
                    {showProject && i.project_name ? `${i.project_name} · ` : ""}
                    {i.goal || `${i.mode === "authenticated" ? "Signed-in check" : "Full check"} on ${i.config.viewports.join(" & ")}`}
                  </div>
                </div>
                <div className="justify-self-end lg:justify-self-start">
                  <StatusPill status={i.status} />
                </div>
                <span className="text-right text-body tabular text-fg-muted max-lg:hidden">{i.page_count}</span>
                <span className="flex flex-wrap items-center gap-1.5 text-label max-lg:col-span-2">
                  {total === 0 ? (
                    <span className="text-fg-subtle">{ACTIVE_STATUSES.has(i.status) ? "Still looking…" : "None found"}</span>
                  ) : (
                    <>
                      {confirmed > 0 && (
                        <span className="rounded-full bg-danger-soft px-2.5 py-0.5 text-meta font-medium text-danger">
                          {confirmed} confirmed
                        </span>
                      )}
                      {warnings > 0 && (
                        <span className="rounded-full bg-warning-soft px-2.5 py-0.5 text-meta font-medium text-warning">
                          {warnings} possible
                        </span>
                      )}
                      {total - confirmed - warnings > 0 && (
                        <span className="text-meta text-fg-subtle">
                          +{total - confirmed - warnings} note{total - confirmed - warnings > 1 ? "s" : ""}
                        </span>
                      )}
                    </>
                  )}
                  <span className="text-meta text-fg-subtle lg:hidden">· {relativeTime(i.created_at, now)}</span>
                </span>
                <span className="text-right text-label tabular text-fg-muted max-lg:hidden">{duration(i.started_at, i.finished_at, now)}</span>
                <span className="text-right text-label text-fg-subtle max-lg:hidden">{relativeTime(i.created_at, now)}</span>
              </Link>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

export function FindingRows({ items, showTarget = true }: { items: Finding[]; showTarget?: boolean }) {
  return (
    <ul className="panel divide-y divide-border overflow-hidden">
      {items.map((f) => (
        <li key={f.id}>
          <Link href={`/findings/${f.id}`} className="group flex items-start gap-4 px-5 py-4 transition-colors hover:bg-surface-2">
            <div className="w-[92px] shrink-0 pt-0.5">
              <SeverityLabel severity={f.severity} />
            </div>
            <div className="min-w-0 flex-1">
              <div className="text-body font-semibold leading-snug">{f.title}</div>
              <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1.5 text-label text-fg-subtle">
                <ClassificationBadge value={f.classification} />
                {f.reproduction?.status === "fixed" && (
                  <span className="inline-flex h-6 items-center gap-1 rounded-full bg-success-soft px-2.5 text-meta font-medium text-success">
                    <Icon.Check size={12} /> Fixed
                  </span>
                )}
                {f.viewport_name && (
                  <span className="inline-flex items-center gap-1 capitalize">
                    <ViewportIcon name={f.viewport_name} /> {f.viewport_name}
                  </span>
                )}
                {f.reproduction?.total_runs ? (
                  <span>
                    {f.kind === "journey_failure"
                      ? `failed ${f.reproduction.failed_runs} of ${f.reproduction.total_runs} tries`
                      : `${f.reproduction.failed_runs} of ${f.reproduction.total_runs} page loads`}
                  </span>
                ) : null}
                {showTarget && <span>{hostOf(f.origin)}</span>}
                {f.test_status && <TestStatusBadge status={f.test_status} />}
              </div>
            </div>
            <Icon.Chevron className="mt-1 shrink-0 text-fg-subtle transition-transform group-hover:translate-x-0.5" />
          </Link>
        </li>
      ))}
    </ul>
  );
}
