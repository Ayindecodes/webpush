"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useMemo, useState, type ReactNode } from "react";

import { FindingRows } from "@/components/lists";
import { useCrumbs, useShell } from "@/components/shell/context";
import { Icon } from "@/components/ui/icons";
import { ButtonLink, EmptyState, ErrorState, LoadingRows, PageHeader, Select, cx } from "@/components/ui/primitives";
import { useApi } from "@/lib/hooks";
import type { Classification, Finding, Severity } from "@/lib/types";

const SEVERITIES: Severity[] = ["critical", "high", "medium", "low", "info"];
const CLASSES: { value: Classification; label: string; hint: string }[] = [
  { value: "confirmed_defect", label: "Confirmed", hint: "Failed every time, with proof" },
  { value: "warning", label: "Possible", hint: "Seen, but not proven to affect visitors" },
  { value: "observation", label: "Notes", hint: "For information" },
];
const SEV_RANK = Object.fromEntries(SEVERITIES.map((s, i) => [s, i]));
const CLS_RANK: Record<string, number> = { confirmed_defect: 0, warning: 1, observation: 2 };
const KIND_LABEL: Record<string, string> = {
  journey_failure: "A journey breaks",
  http_error: "Something doesn't load",
  page_error: "A script crashes",
  console_error: "The page reports an error",
  request_failure: "A request fails",
  blocked_request: "Blocked for safety",
  layout_overflow: "Layout too wide",
};

export default function FindingsPage() {
  return (
    <Suspense fallback={<LoadingRows />}>
      <Findings />
    </Suspense>
  );
}

function Findings() {
  useCrumbs([{ label: "Problems found" }]);
  const { projectId } = useShell();
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const [q, setQ] = useState(params.get("q") ?? "");
  const severity = params.getAll("severity");
  const classification = params.getAll("classification");
  const sort = params.get("sort") ?? "severity";
  const kind = params.get("kind") ?? "";

  // Debounced search → URL (so filters survive reloads and can be shared).
  useEffect(() => {
    const t = setTimeout(() => update({ q: q.trim() || null }), 250);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [q]);

  function update(changes: Record<string, string | string[] | null>) {
    const next = new URLSearchParams(params.toString());
    for (const [k, v] of Object.entries(changes)) {
      next.delete(k);
      if (Array.isArray(v)) v.forEach((x) => next.append(k, x));
      else if (v) next.set(k, v);
    }
    const qs = next.toString();
    if (qs !== params.toString()) router.replace(`${pathname}${qs ? `?${qs}` : ""}`, { scroll: false });
  }
  const toggle = (key: string, list: string[], v: string) => update({ [key]: list.includes(v) ? list.filter((x) => x !== v) : [...list, v] });

  const query = new URLSearchParams();
  if (params.get("q")) query.set("q", params.get("q")!.slice(0, 200));
  severity.filter((s) => SEVERITIES.includes(s as Severity)).forEach((s) => query.append("severity", s));
  classification.filter((c) => c in CLS_RANK).forEach((c) => query.append("classification", c));
  if (projectId) query.set("project_id", projectId);
  query.set("limit", "500");
  const { data, error, mutate } = useApi<Finding[]>(`/api/findings?${query.toString()}`, { refreshInterval: 15_000 });

  const kinds = useMemo(() => Array.from(new Set((data ?? []).map((f) => f.kind))).sort(), [data]);
  const items = useMemo(() => {
    const list = (data ?? []).filter((f) => !kind || f.kind === kind);
    return [...list].sort((a, b) =>
      sort === "newest"
        ? b.created_at.localeCompare(a.created_at)
        : (CLS_RANK[a.classification] ?? 9) - (CLS_RANK[b.classification] ?? 9) || SEV_RANK[a.severity] - SEV_RANK[b.severity],
    );
  }, [data, kind, sort]);
  const filtered = !!(params.get("q") || severity.length || classification.length || kind);

  return (
    <div className="space-y-8">
      <PageHeader
        title="Problems found"
        description="Everything our investigations found, worst first. “Confirmed” means it failed every time we tried and we have proof."
      />
      <div className="panel space-y-4 p-5">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-center">
          <label className="relative flex-1">
            <span className="sr-only">Search problems</span>
            <Icon.Search className="pointer-events-none absolute left-4 top-1/2 -translate-y-1/2 text-fg-subtle" />
            <input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Search problems"
              maxLength={200}
              className="h-11 w-full rounded-full border border-border-strong bg-surface pl-11 pr-4 text-body outline-none focus:border-fg focus:shadow-[0_0_0_4px_var(--wx-brand-soft)]"
            />
          </label>
          <div className="flex gap-2">
            <Select value={kind} onChange={(e) => update({ kind: e.target.value || null })} aria-label="Kind of problem" className="w-52 rounded-full">
              <option value="">All kinds</option>
              {kinds.map((k) => (
                <option key={k} value={k}>
                  {KIND_LABEL[k] ?? k.replace(/_/g, " ")}
                </option>
              ))}
            </Select>
            <Select value={sort} onChange={(e) => update({ sort: e.target.value === "severity" ? null : e.target.value })} aria-label="Sort" className="w-40 rounded-full">
              <option value="severity">Worst first</option>
              <option value="newest">Newest first</option>
            </Select>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-x-6 gap-y-3">
          <ChipGroup label="Certainty">
            {CLASSES.map((c) => (
              <Chip key={c.value} on={classification.includes(c.value)} onClick={() => toggle("classification", classification, c.value)} title={c.hint}>
                {c.label}
              </Chip>
            ))}
          </ChipGroup>
          <ChipGroup label="How serious">
            {SEVERITIES.map((s) => (
              <Chip key={s} on={severity.includes(s)} onClick={() => toggle("severity", severity, s)}>
                <span className="capitalize">{s}</span>
              </Chip>
            ))}
          </ChipGroup>
          {filtered && (
            <button
              type="button"
              onClick={() => {
                setQ("");
                router.replace(pathname, { scroll: false });
              }}
              className="text-label text-fg-muted underline-offset-4 hover:text-fg hover:underline"
            >
              Clear filters
            </button>
          )}
        </div>
      </div>
      {error ? (
        <ErrorState error={error} retry={() => mutate()} />
      ) : !data ? (
        <LoadingRows rows={6} />
      ) : items.length === 0 ? (
        <EmptyState
          icon={<Icon.Check size={20} />}
          title={!filtered ? "No problems found yet" : "Nothing matches these filters"}
          description={!filtered ? "When an investigation finds something broken, it shows up here." : "Try removing a filter."}
          action={
            !filtered ? (
              <ButtonLink href="/investigations/new" variant="primary">
                Check a website
              </ButtonLink>
            ) : undefined
          }
        />
      ) : (
        <>
          <div className="text-label text-fg-subtle" aria-live="polite">
            {items.length} problem{items.length === 1 ? "" : "s"}
          </div>
          <FindingRows items={items} />
        </>
      )}
    </div>
  );
}

function ChipGroup({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex flex-wrap items-center gap-1.5" role="group" aria-label={label}>
      <span className="mr-1 text-label text-fg-subtle">{label}:</span>
      {children}
    </div>
  );
}

function Chip({ on, onClick, children, title }: { on: boolean; onClick: () => void; children: ReactNode; title?: string }) {
  return (
    <button
      onClick={onClick}
      aria-pressed={on}
      title={title}
      className={cx(
        "h-8 rounded-full border px-3.5 text-label transition-colors",
        on ? "border-fg bg-fg font-medium text-bg" : "border-border-strong text-fg-muted hover:border-fg hover:text-fg",
      )}
    >
      {children}
    </button>
  );
}
