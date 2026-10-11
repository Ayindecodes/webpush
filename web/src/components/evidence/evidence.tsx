"use client";

import { useState, type ReactNode } from "react";

import { Icon } from "@/components/ui/icons";
import { Button, CodeBlock, Dialog, ErrorState, LoadingRows, Mono, Skeleton, cx } from "@/components/ui/primitives";
import { bytes, humanize, pathOf } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import type { Evidence } from "@/lib/types";

/** Resolve an evidence id to metadata + a fresh short-lived signed URL. */
export function useEvidence(id: string | null | undefined) {
  return useApi<Evidence>(id ? `/api/evidence/${id}` : null, { refreshInterval: 5 * 60_000 });
}

export function EvidenceImage({
  id,
  alt,
  className,
  onOpen,
  fit = false,
}: {
  id: string | null | undefined;
  alt: string;
  className?: string;
  onOpen?: (e: Evidence) => void;
  /** Scale the whole image into its container instead of filling the width. */
  fit?: boolean;
}) {
  const { data, error } = useEvidence(id);
  if (!id) return <div className={cx("flex items-center justify-center bg-surface-2 text-label text-fg-subtle", className)}>No screenshot</div>;
  if (error) return <div className={cx("flex items-center justify-center bg-surface-2 text-label text-fg-subtle", className)}>Unavailable</div>;
  if (!data) return <Skeleton className={className} />;
  const img = (
    // eslint-disable-next-line @next/next/no-img-element -- signed, short-lived evidence URLs
    <img
      src={data.url}
      alt={alt}
      className={cx("block bg-surface-2 object-contain", fit ? "h-full w-full" : "h-auto w-full object-top", className)}
      loading="lazy"
    />
  );
  return onOpen ? (
    <button type="button" onClick={() => onOpen(data)} className={cx("block w-full cursor-zoom-in text-left", fit && "h-full")} aria-label={`Open ${alt}`}>
      {img}
    </button>
  ) : (
    img
  );
}

function useJson<T>(evidence: Evidence | null | undefined) {
  return useApi<T>(evidence ? evidence.url : null, { revalidateOnFocus: false });
}

export function EvidenceMeta({ e }: { e: Evidence }) {
  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-meta text-fg-subtle">
      <span>{humanize(e.kind)}</span>
      <span>{bytes(e.size_bytes)}</span>
      <span title={e.sha256}>
        sha256 <Mono>{e.sha256.slice(0, 12)}…</Mono>
      </span>
      {e.event_seq != null && <span>event #{e.event_seq}</span>}
      {e.redactions.length > 0 && <span title={e.redactions.join(", ")}>redacted: {e.redactions.join(", ")}</span>}
      {e.meta?.masked ? <span>sensitive inputs masked</span> : null}
    </div>
  );
}

// ------------------------------------------------------------------ structured viewers

interface HitAttempt {
  position: string;
  rect: { x: number; y: number; width: number; height: number };
  viewport: { width: number; height: number };
  visualViewport?: { width: number; height: number; offsetTop: number; offsetLeft: number; scale: number };
  documentWidth?: number;
  centerHit: boolean;
  coordinate_mismatch?: boolean;
  points: { fx: number; fy: number; x: number; y: number; vx: number; vy: number; hit: boolean; onScreen: boolean; top: Described | null }[];
  probe?: {
    installed: boolean;
    received: boolean;
    method?: string;
    at?: { vx: number; vy: number };
    receivedBy?: Described | null;
    interceptor?: { overlayRoot?: Described; overlayStyles?: Record<string, string> } | null;
    reason?: string;
  };
  targetStyles?: Record<string, string>;
}
interface Described {
  tag: string;
  id: string | null;
  classes: string[];
  name: string;
  selector: string;
  rect: { x: number; y: number; width: number; height: number };
}
interface HitTestData {
  locator: Record<string, unknown>;
  method: string;
  attempts: HitAttempt[];
  covered_at_all_positions: boolean;
  layout_viewport?: { width: number; height: number };
  visual_viewport?: { width: number; height: number };
  document_width?: number;
}

function describeEl(d: Described | null | undefined) {
  if (!d) return "—";
  return `<${d.tag}${d.id ? "#" + d.id : ""}${d.classes.length ? "." + d.classes.join(".") : ""}>`;
}

export function HitTestView({ evidence }: { evidence: Evidence }) {
  const { data, error } = useJson<HitTestData>(evidence);
  if (error) return <ErrorState error={error} />;
  if (!data) return <LoadingRows rows={3} />;
  return (
    <div className="space-y-4">
      <p className="text-label text-fg-muted">
        Method: {data.method}. Layout viewport {data.layout_viewport?.width}×{data.layout_viewport?.height}, visual viewport{" "}
        {data.visual_viewport?.width}×{data.visual_viewport?.height}, document width {data.document_width}px.
      </p>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[640px] text-left text-label">
          <thead className="text-meta uppercase tracking-wider text-fg-subtle">
            <tr className="border-b border-border">
              <th className="py-2 pr-3 font-medium">Scroll position</th>
              <th className="py-2 pr-3 font-medium">Probe {data.attempts[0]?.probe?.method ?? ""}</th>
              <th className="py-2 pr-3 font-medium">Delivered to</th>
              <th className="py-2 pr-3 font-medium">elementFromPoint</th>
              <th className="py-2 font-medium">Control rect</th>
            </tr>
          </thead>
          <tbody>
            {data.attempts.map((a, i) => (
              <tr key={i} className="border-b border-border align-top">
                <td className="py-2 pr-3">{a.position}</td>
                <td className="py-2 pr-3">
                  {a.probe?.installed ? (
                    <span className="inline-flex items-center gap-1 font-medium">
                      {a.probe.received ? <Icon.Check size={13} /> : <Icon.X size={13} />}
                      {a.probe.received ? "reached control" : "intercepted"}
                    </span>
                  ) : (
                    <span className="text-fg-subtle">{a.probe?.reason ?? "not run"}</span>
                  )}
                  {a.probe?.at && <div className="text-meta text-fg-subtle">at ({a.probe.at.vx}, {a.probe.at.vy})</div>}
                </td>
                <td className="py-2 pr-3">
                  <Mono>{a.probe?.received ? "the control" : describeEl(a.probe?.interceptor?.overlayRoot ?? a.probe?.receivedBy)}</Mono>
                </td>
                <td className="py-2 pr-3">
                  {a.centerHit ? "control" : <Mono>{describeEl(a.points[0]?.top)}</Mono>}
                  {a.coordinate_mismatch && <div className="text-meta text-fg-subtle">disagrees with probe</div>}
                </td>
                <td className="py-2">
                  <Mono className="text-fg-muted">
                    {a.rect.x},{a.rect.y} {a.rect.width}×{a.rect.height}
                  </Mono>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {data.attempts[0]?.probe?.interceptor?.overlayStyles && (
        <StyleTable title="Intercepting element — computed styles" styles={data.attempts[0].probe.interceptor.overlayStyles} />
      )}
    </div>
  );
}

function StyleTable({ title, styles }: { title: string; styles: Record<string, string> }) {
  return (
    <div>
      <div className="mb-1.5 text-label font-medium">{title}</div>
      <div className="grid grid-cols-[repeat(auto-fill,minmax(180px,1fr))] gap-x-4 gap-y-1 rounded-xl border border-border bg-surface-2/50 p-4">
        {Object.entries(styles).map(([k, v]) => (
          <div key={k} className="flex justify-between gap-2 font-mono text-[12px]">
            <span className="text-fg-subtle">{k}</span>
            <span className="truncate">{v}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

export function StylesView({ evidence }: { evidence: Evidence }) {
  const { data, error } = useJson<Record<string, Record<string, string> | Described | undefined>>(evidence);
  if (error) return <ErrorState error={error} />;
  if (!data) return <LoadingRows rows={3} />;
  return (
    <div className="space-y-4">
      {data.target && <StyleTable title="Target control" styles={data.target as Record<string, string>} />}
      {data.overlay_root && (
        <StyleTable
          title={`Overlay ${describeEl(data.overlay_root_element as Described | undefined)}`}
          styles={data.overlay_root as Record<string, string>}
        />
      )}
    </div>
  );
}

interface NetEntry {
  id: number;
  ts: number;
  method: string;
  url: string;
  resource_type: string;
  status: number | null;
  failure: string | null;
  duration_ms: number | null;
  step: string | null;
  same_origin: boolean;
  blocked_by_policy: boolean;
}

export function NetworkView({ evidence }: { evidence: Evidence }) {
  const { data, error } = useJson<{ requests: NetEntry[] }>(evidence);
  const [onlyProblems, setOnlyProblems] = useState(true);
  if (error) return <ErrorState error={error} />;
  if (!data) return <LoadingRows rows={4} />;
  const problem = (r: NetEntry) => (r.status ?? 0) >= 400 || !!r.failure || r.blocked_by_policy;
  const rows = onlyProblems ? data.requests.filter(problem) : data.requests;
  return (
    <div>
      <div className="mb-2 flex items-center justify-between gap-2">
        <span className="text-label text-fg-muted">
          {data.requests.length} requests · {data.requests.filter(problem).length} with problems
        </span>
        <Button size="sm" variant="ghost" onClick={() => setOnlyProblems(!onlyProblems)}>
          {onlyProblems ? "Show all" : "Only problems"}
        </Button>
      </div>
      <div className="max-h-96 overflow-auto rounded-xl border border-border">
        <table className="w-full min-w-[720px] text-left font-mono text-[12px]">
          <thead className="sticky top-0 bg-surface text-meta uppercase tracking-wider text-fg-subtle">
            <tr>
              <th className="px-2 py-1.5 font-medium">t (s)</th>
              <th className="px-2 py-1.5 font-medium">Method</th>
              <th className="px-2 py-1.5 font-medium">URL</th>
              <th className="px-2 py-1.5 font-medium">Type</th>
              <th className="px-2 py-1.5 font-medium">Result</th>
              <th className="px-2 py-1.5 font-medium">Step</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.id} className={cx("border-t border-border", problem(r) && "font-semibold")}>
                <td className="px-2 py-1 tabular text-fg-subtle">{r.ts.toFixed(2)}</td>
                <td className="px-2 py-1">{r.method}</td>
                <td className="max-w-[360px] truncate px-2 py-1" title={r.url}>
                  {r.same_origin ? pathOf(r.url) : r.url}
                </td>
                <td className="px-2 py-1 text-fg-muted">{r.resource_type}</td>
                <td className="px-2 py-1">{r.blocked_by_policy ? "blocked (policy)" : r.failure ?? r.status ?? "—"}</td>
                <td className="px-2 py-1 text-fg-muted">{r.step ?? "—"}</td>
              </tr>
            ))}
            {rows.length === 0 && (
              <tr>
                <td colSpan={6} className="px-2 py-4 text-center font-sans text-fg-subtle">
                  No requests to show.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export function ConsoleView({ evidence }: { evidence: Evidence }) {
  const { data, error } = useJson<{
    console: { ts: number; type: string; text: string; location: string | null; step: string | null }[];
    page_errors: { ts: number; message: string; stack: string; step: string | null }[];
    dialogs?: { type: string; message: string }[];
  }>(evidence);
  if (error) return <ErrorState error={error} />;
  if (!data) return <LoadingRows rows={3} />;
  const lines = [
    ...data.console.map((c) => ({ ts: c.ts, kind: c.type, text: c.text, where: c.location, step: c.step })),
    ...data.page_errors.map((p) => ({ ts: p.ts, kind: "exception", text: p.message, where: null, step: p.step })),
  ].sort((a, b) => a.ts - b.ts);
  if (lines.length === 0) return <p className="text-label text-fg-subtle">No console output was recorded.</p>;
  return (
    <div className="max-h-96 overflow-auto rounded-xl border border-border bg-surface-2/50 font-mono text-[12px]">
      {lines.map((l, i) => (
        <div key={i} className={cx("flex gap-3 border-b border-border px-2.5 py-1.5", (l.kind === "error" || l.kind === "exception") && "font-semibold")}>
          <span className="w-12 shrink-0 tabular text-fg-subtle">{l.ts.toFixed(2)}</span>
          <span className="w-16 shrink-0 text-fg-muted">{l.kind}</span>
          <span className="min-w-0 flex-1 break-words">
            {l.text}
            {l.where && <span className="block text-fg-subtle">{l.where}</span>}
          </span>
        </div>
      ))}
    </div>
  );
}

function TextView({ evidence }: { evidence: Evidence }) {
  const { data, error } = useApi<unknown>(evidence.url, { revalidateOnFocus: false });
  if (error) return <ErrorState error={error} />;
  if (data === undefined) return <LoadingRows rows={3} />;
  const text = typeof data === "string" ? data : JSON.stringify(data, null, 2);
  return <CodeBlock code={text} title={evidence.label} />;
}

function OverflowView({ evidence }: { evidence: Evidence }) {
  const { data, error } = useJson<{ overflowPx: number; documentWidth: number; culprits: { element: Described; right: number }[] }>(evidence);
  if (error) return <ErrorState error={error} />;
  if (!data) return <LoadingRows rows={2} />;
  return (
    <div className="space-y-2 text-label">
      <p>
        Document is <strong>{data.documentWidth}px</strong> wide ({data.overflowPx}px wider than the viewport).
      </p>
      <ul className="space-y-1">
        {data.culprits.map((c, i) => (
          <li key={i}>
            <Mono>{describeEl(c.element)}</Mono> <span className="text-fg-subtle">extends to {c.right}px</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

export function EvidenceBody({ evidence }: { evidence: Evidence }) {
  switch (evidence.kind) {
    case "screenshot":
      return (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={evidence.url} alt={evidence.label} className="mx-auto block h-auto max-w-full border border-border" />
      );
    case "hit_test":
      return <HitTestView evidence={evidence} />;
    case "computed_styles":
      return <StylesView evidence={evidence} />;
    case "network_log":
      return <NetworkView evidence={evidence} />;
    case "console_log":
      return <ConsoleView evidence={evidence} />;
    case "layout_overflow":
      return <OverflowView evidence={evidence} />;
    default:
      return <TextView evidence={evidence} />;
  }
}

export function EvidenceDialog({ evidence, onClose }: { evidence: Evidence | null; onClose: () => void }) {
  return (
    <Dialog open={!!evidence} onClose={onClose} title={evidence?.label ?? "Evidence"} wide>
      {evidence && (
        <div className="space-y-3">
          <EvidenceMeta e={evidence} />
          <EvidenceBody evidence={evidence} />
        </div>
      )}
    </Dialog>
  );
}

/** Open any evidence by id (used by timeline rows). */
export function EvidenceById({ id, onClose }: { id: string | null; onClose: () => void }) {
  const { data } = useEvidence(id);
  return <EvidenceDialog evidence={id ? (data ?? null) : null} onClose={onClose} />;
}

export function EvidenceKindIcon({ kind }: { kind: string }): ReactNode {
  return <span className="font-mono text-[10px] uppercase text-fg-subtle">{kind.replace(/_.*/, "").slice(0, 4)}</span>;
}
