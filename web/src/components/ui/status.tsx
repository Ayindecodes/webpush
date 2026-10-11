import type { ReactNode } from "react";

import type { Classification, InvestigationStatus, Severity } from "@/lib/types";

import { Icon } from "./icons";
import { cx } from "./primitives";

const SEVERITY: Record<Severity, { label: string; icon: ReactNode; cls: string }> = {
  critical: { label: "Critical", icon: <Icon.SevCritical />, cls: "text-sev-critical" },
  high: { label: "High", icon: <Icon.SevHigh />, cls: "text-sev-high" },
  medium: { label: "Medium", icon: <Icon.SevMedium />, cls: "text-sev-medium" },
  low: { label: "Low", icon: <Icon.SevLow />, cls: "text-sev-low" },
  info: { label: "Info", icon: <Icon.SevInfo />, cls: "text-sev-info" },
};

/** Severity is always icon + label; the colour only reinforces it. */
export function SeverityLabel({ severity, compact }: { severity: Severity; compact?: boolean }) {
  const s = SEVERITY[severity] ?? SEVERITY.info;
  return (
    <span className="inline-flex items-center gap-1.5 text-label font-medium" title={`${s.label} severity`}>
      <span className={s.cls}>{s.icon}</span>
      {compact ? <span className="sr-only">{s.label}</span> : <span className="text-fg">{s.label}</span>}
    </span>
  );
}

const CLASSIFICATION: Record<Classification, { label: string; cls: string; description: string }> = {
  confirmed_defect: {
    label: "Confirmed problem",
    cls: "bg-danger-soft text-danger",
    description: "It failed every time we repeated it, and the evidence shows why",
  },
  warning: {
    label: "Possible problem",
    cls: "bg-warning-soft text-warning",
    description: "We saw it happen, but haven't proved it affects visitors",
  },
  observation: {
    label: "Note",
    cls: "bg-surface-2 text-fg-muted",
    description: "For information only",
  },
};

export function classificationLabel(value: Classification): string {
  return (CLASSIFICATION[value] ?? CLASSIFICATION.observation).label;
}

export function ClassificationBadge({ value }: { value: Classification }) {
  const c = CLASSIFICATION[value] ?? CLASSIFICATION.observation;
  return (
    <span className={cx("inline-flex h-6 items-center whitespace-nowrap rounded-full px-2.5 text-meta font-medium", c.cls)} title={c.description}>
      {c.label}
    </span>
  );
}

type Tone = "brand" | "success" | "danger" | "warning" | "neutral";
const STATUS: Record<string, { label: string; tone: Tone; glyph: "live" | "done" | "fail" | "idle" | "pause" | "hold" }> = {
  queued: { label: "Queued", tone: "neutral", glyph: "idle" },
  running: { label: "Running", tone: "brand", glyph: "live" },
  paused: { label: "Paused", tone: "warning", glyph: "pause" },
  awaiting_human: { label: "Needs you", tone: "warning", glyph: "hold" },
  completed: { label: "Finished", tone: "success", glyph: "done" },
  failed: { label: "Failed", tone: "danger", glyph: "fail" },
  stopped: { label: "Stopped", tone: "neutral", glyph: "idle" },
  blocked: { label: "Blocked", tone: "warning", glyph: "hold" },
  passed: { label: "Passed", tone: "success", glyph: "done" },
  partial: { label: "Partial", tone: "warning", glyph: "hold" },
  planned: { label: "Planned", tone: "neutral", glyph: "idle" },
  error: { label: "Error", tone: "danger", glyph: "fail" },
  skipped: { label: "Skipped", tone: "neutral", glyph: "idle" },
  pending: { label: "Pending", tone: "neutral", glyph: "idle" },
  done: { label: "Done", tone: "success", glyph: "done" },
  verified: { label: "Verified", tone: "success", glyph: "done" },
};

const TONE_CLS: Record<Tone, string> = {
  brand: "bg-brand-soft text-brand-text",
  success: "bg-success-soft text-success",
  danger: "bg-danger-soft text-danger",
  warning: "bg-warning-soft text-warning",
  neutral: "bg-surface-2 text-fg-muted",
};

function Glyph({ kind }: { kind: string }) {
  switch (kind) {
    case "live":
      return <span className="wx-live-dot inline-block size-1.5 rounded-full bg-current" />;
    case "done":
      return <Icon.Check size={12} />;
    case "fail":
      return <Icon.X size={12} />;
    case "pause":
      return <Icon.Pause size={12} />;
    case "hold":
      return <Icon.SevMedium size={12} />;
    default:
      return <span className="inline-block size-1.5 rounded-full border border-current" />;
  }
}

export function StatusPill({ status, className }: { status: InvestigationStatus | string; className?: string }) {
  const s = STATUS[status] ?? { label: status.replace(/_/g, " "), tone: "neutral" as Tone, glyph: "idle" as const };
  return (
    <span className={cx("inline-flex h-6 items-center gap-1.5 whitespace-nowrap rounded-full px-2.5 text-meta font-medium capitalize", TONE_CLS[s.tone], className)}>
      <Glyph kind={s.glyph} />
      {s.label}
    </span>
  );
}

const TEST_STATUS: Record<string, { label: string; detail: string; tone: Tone; glyph: string }> = {
  generated: { label: "Test written · not run yet", detail: "The test exists but hasn't been run", tone: "neutral", glyph: "idle" },
  reproduced: { label: "Test confirms it", detail: "We ran the test and the problem happened again", tone: "danger", glyph: "fail" },
  not_reproduced: { label: "Test passes", detail: "We ran the test and the problem no longer happens", tone: "success", glyph: "done" },
  inconclusive: { label: "Test inconclusive", detail: "The test stopped before it reached the problem", tone: "warning", glyph: "hold" },
  queued: { label: "Run queued", detail: "Waiting for a worker", tone: "neutral", glyph: "idle" },
  running: { label: "Running", detail: "Executing in the isolated runner", tone: "brand", glyph: "live" },
};

export function TestStatusBadge({ status }: { status: string | null }) {
  if (!status) return <span className="text-label text-fg-subtle">No test yet</span>;
  const s = TEST_STATUS[status] ?? { label: status, detail: status, tone: "neutral" as Tone, glyph: "idle" };
  return (
    <span className={cx("inline-flex h-6 items-center gap-1.5 whitespace-nowrap rounded-full px-2.5 text-meta font-medium", TONE_CLS[s.tone])} title={s.detail}>
      <Glyph kind={s.glyph} />
      {s.label}
    </span>
  );
}

export function StrengthLabel({ value }: { value: string }) {
  const bars = value === "strong" ? 3 : value === "moderate" ? 2 : 1;
  return (
    <span className="inline-flex items-center gap-1.5 text-label" title={`How strong the evidence is: ${value}`}>
      <span className="inline-flex items-end gap-[2px]" aria-hidden>
        {[1, 2, 3].map((i) => (
          <span key={i} className={cx("w-[3px] rounded-sm", i <= bars ? "bg-brand" : "bg-border-strong")} style={{ height: 4 + i * 3 }} />
        ))}
      </span>
      <span className="capitalize text-fg-muted">{value}</span>
    </span>
  );
}

export function HypothesisStatus({ status }: { status: string }) {
  const map: Record<string, { label: string; tone: Tone; glyph: string }> = {
    supported: { label: "Likely cause", tone: "brand", glyph: "done" },
    not_supported: { label: "Ruled out", tone: "neutral", glyph: "fail" },
    inconclusive: { label: "Inconclusive", tone: "warning", glyph: "hold" },
  };
  const s = map[status] ?? { label: status, tone: "neutral" as Tone, glyph: "idle" };
  return (
    <span className={cx("inline-flex h-6 items-center gap-1.5 rounded-full px-2.5 text-meta font-medium", TONE_CLS[s.tone])}>
      <Glyph kind={s.glyph} />
      {s.label}
    </span>
  );
}

export function ViewportIcon({ name }: { name: string | null | undefined }) {
  if (name === "mobile") return <Icon.Mobile />;
  if (name === "tablet") return <Icon.Tablet />;
  return <Icon.Desktop />;
}
