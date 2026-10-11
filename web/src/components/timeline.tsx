"use client";

import { useMemo, useState } from "react";

import { EvidenceById } from "@/components/evidence/evidence";
import { Icon } from "@/components/ui/icons";
import { Button, Segmented, cx } from "@/components/ui/primitives";
import { clockTime } from "@/lib/format";
import type { InvestigationEvent } from "@/lib/types";

const KIND_LABEL: Record<string, string> = {
  phase: "Step",
  navigation: "Page",
  action: "Action",
  assertion: "Check",
  finding: "Problem",
  auth: "Sign-in",
  policy: "Safety",
  system: "Note",
  console: "Console",
  network: "Network",
};

type Filter = "all" | "important" | "assertion" | "navigation" | "finding";

export function Timeline({
  events,
  maxHeight = "34rem",
  highlightSeq,
  filterRunIds,
  newestFirst = true,
  showFilters = true,
}: {
  events: InvestigationEvent[];
  maxHeight?: string;
  highlightSeq?: number | null;
  filterRunIds?: string[];
  newestFirst?: boolean;
  showFilters?: boolean;
}) {
  const [filter, setFilter] = useState<Filter>("all");
  const [openEvidence, setOpenEvidence] = useState<string | null>(null);

  const scoped = useMemo(
    () => (filterRunIds?.length ? events.filter((e) => !e.browser_run_id || filterRunIds.includes(e.browser_run_id)) : events),
    [events, filterRunIds],
  );
  const issues = scoped.filter((e) => e.level !== "info" || e.kind === "finding").length;
  const rows = useMemo(() => {
    let list = scoped;
    if (filter === "important") list = list.filter((e) => e.level !== "info" || e.kind === "finding");
    else if (filter !== "all") list = list.filter((e) => e.kind === filter);
    return newestFirst ? [...list].reverse() : list;
  }, [scoped, filter, newestFirst]);

  return (
    <div className="flex min-h-0 flex-col gap-3">
      {showFilters && (
        <Segmented
          label="Filter events"
          value={filter}
          onChange={setFilter}
          options={[
            { value: "all", label: "All", count: scoped.length },
            { value: "important", label: "Only issues", count: issues },
            { value: "assertion", label: "Checks" },
            { value: "navigation", label: "Pages" },
            { value: "finding", label: "Problems" },
          ]}
        />
      )}
      <ol className="panel overflow-y-auto" style={{ maxHeight }} aria-live="polite" aria-label="What happened, newest first">
        {rows.length === 0 && <li className="px-4 py-8 text-center text-label text-fg-subtle">No events to show.</li>}
        {rows.map((e) => (
          <li
            key={e.seq}
            id={`event-${e.seq}`}
            className={cx(
              "wx-enter grid grid-cols-[4.25rem_1fr_auto] items-start gap-3 border-b border-border px-5 py-2.5 text-label last:border-b-0",
              highlightSeq === e.seq && "bg-brand-soft",
            )}
          >
            <span className="pt-px font-mono text-[11px] tabular text-fg-subtle" title={new Date(e.ts).toISOString()}>
              {clockTime(e.ts)}
            </span>
            <span className="min-w-0">
              <span
                className={cx(
                  "mr-2 inline-flex items-center gap-1 rounded-full px-2 align-[1px] text-[11px] font-medium",
                  e.level === "error" ? "bg-danger-soft text-danger" : e.level === "warn" ? "bg-warning-soft text-warning" : e.kind === "finding" ? "bg-brand-soft text-brand-text" : "bg-surface-2 text-fg-subtle",
                )}
              >
                {e.level === "error" ? <Icon.X size={10} /> : e.level === "warn" ? <Icon.SevMedium size={10} /> : null}
                {KIND_LABEL[e.kind] ?? e.kind}
              </span>
              <span className={cx("break-words", e.level === "error" ? "text-fg" : "text-fg-muted")}>{e.message}</span>
            </span>
            {e.evidence_id ? (
              <Button size="sm" variant="ghost" className="h-6 px-1.5 text-meta" onClick={() => setOpenEvidence(e.evidence_id)} aria-label="Open evidence">
                <Icon.Layers size={13} /> Evidence
              </Button>
            ) : (
              <span />
            )}
          </li>
        ))}
      </ol>
      <EvidenceById id={openEvidence} onClose={() => setOpenEvidence(null)} />
    </div>
  );
}
