"use client";

import { useState } from "react";

import { EvidenceById } from "@/components/evidence/evidence";
import { Icon } from "@/components/ui/icons";
import { Button, KeyValue, cx } from "@/components/ui/primitives";
import { StatusPill, ViewportIcon } from "@/components/ui/status";
import type { BrowserRun, Journey, RunStep } from "@/lib/types";

function StepGlyph({ status }: { status: RunStep["status"] }) {
  if (status === "passed") return <Icon.Check size={13} />;
  if (status === "failed" || status === "error") return <Icon.X size={13} />;
  if (status === "skipped") return <span className="text-meta">–</span>;
  return <span className="inline-block size-1.5 rounded-full bg-current" />;
}

const STEP_CLS: Record<string, string> = {
  passed: "bg-success-soft text-success",
  failed: "bg-danger-soft text-danger ring-1 ring-inset ring-danger/50",
  error: "bg-danger-soft text-danger ring-1 ring-inset ring-danger/50",
  skipped: "bg-surface-2 text-fg-subtle",
  pending: "bg-surface-2 text-fg-subtle",
};

/** Runs × steps: every cell is a recorded step outcome; select one for details and evidence. */
export function JourneyMatrix({ journey }: { journey: Journey }) {
  const runs = journey.runs;
  const stepKeys = (journey.definition.steps as string[] | undefined) ?? runs[0]?.steps.map((s) => s.key) ?? [];
  const names: Record<string, string> = {};
  runs.forEach((r) => r.steps.forEach((s) => (names[s.key] = s.name)));
  const firstFailure = runs.find((r) => r.failure_step);
  const [selected, setSelected] = useState<{ run: BrowserRun; step: RunStep } | null>(() => {
    const step = firstFailure?.steps.find((s) => s.key === firstFailure.failure_step);
    return firstFailure && step ? { run: firstFailure, step } : null;
  });
  const [openEvidence, setOpenEvidence] = useState<string | null>(null);

  if (runs.length === 0) return <p className="text-label text-fg-subtle">No runs recorded yet.</p>;

  return (
    <div className="space-y-3">
      <div className="overflow-x-auto rounded-[var(--radius-panel)] border border-border bg-surface">
        <table className="w-full min-w-[640px] text-left text-label">
          <thead>
            <tr className="border-b border-border text-meta text-fg-subtle">
              <th className="sticky left-0 z-10 bg-surface px-4 py-2.5 font-medium">Run</th>
              {stepKeys.map((k, i) => (
                <th key={k} className="px-1 py-2.5 text-center font-medium" title={names[k] ?? k} scope="col">
                  <span className="font-mono">{i + 1}</span>
                </th>
              ))}
              <th className="px-4 py-2.5 font-medium">Result</th>
            </tr>
          </thead>
          <tbody>
            {runs.map((r) => (
              <tr key={r.id} className="border-b border-border last:border-b-0">
                <th scope="row" className="sticky left-0 z-10 bg-surface px-4 py-2 font-normal">
                  <span className="inline-flex items-center gap-1.5 whitespace-nowrap">
                    <ViewportIcon name={r.viewport_name} />
                    {r.viewport.label} <span className="text-fg-subtle">#{r.attempt}</span>
                  </span>
                </th>
                {stepKeys.map((k) => {
                  const s = r.steps.find((x) => x.key === k);
                  const isSel = selected?.run.id === r.id && selected.step.key === k;
                  return (
                    <td key={k} className="px-1 py-1.5 text-center">
                      {s ? (
                        <button
                          onClick={() => setSelected(isSel ? null : { run: r, step: s })}
                          aria-label={`${r.viewport.label} attempt ${r.attempt}, ${s.name}: ${s.status}`}
                          aria-pressed={isSel}
                          className={cx(
                            "inline-flex size-7 items-center justify-center rounded-md transition-shadow",
                            STEP_CLS[s.status] ?? STEP_CLS.pending,
                            isSel && "ring-2 ring-focus ring-offset-2 ring-offset-surface",
                          )}
                        >
                          <StepGlyph status={s.status} />
                        </button>
                      ) : (
                        <span className="text-fg-subtle">·</span>
                      )}
                    </td>
                  );
                })}
                <td className="px-4 py-2">
                  <StatusPill status={r.status} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        <div className="flex flex-wrap gap-x-4 gap-y-1 border-t border-border px-4 py-2.5 text-meta text-fg-subtle">
          {stepKeys.map((k, i) => (
            <span key={k}>
              <span className="font-mono text-fg-muted">{i + 1}</span> {names[k] ?? k}
            </span>
          ))}
        </div>
      </div>
      {selected && (
        <div className="wx-enter rounded-[var(--radius-panel)] border border-border-strong bg-surface p-4">
          <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
            <div className="text-body font-medium">
              {selected.run.viewport.label} #{selected.run.attempt} · {selected.step.name}
            </div>
            <StatusPill status={selected.step.status} />
          </div>
          <KeyValue
            items={[
              ["Expected", selected.step.expected],
              ["Observed", selected.step.observed || "—"],
              [
                "Signals",
                Object.entries(selected.step.signals)
                  .map(([k, v]) => `${k.replace(/_/g, " ")}: ${v}`)
                  .join(" · ") || "—",
              ],
            ]}
          />
          {Object.keys(selected.step.evidence).length > 0 && (
            <div className="mt-4 flex flex-wrap gap-2 border-t border-border pt-3">
              {Object.entries(selected.step.evidence).map(([role, id]) => (
                <Button key={role} size="sm" onClick={() => setOpenEvidence(id)} icon={<Icon.Layers size={13} />}>
                  {role.replace(/_/g, " ")}
                </Button>
              ))}
            </div>
          )}
        </div>
      )}
      <EvidenceById id={openEvidence} onClose={() => setOpenEvidence(null)} />
    </div>
  );
}
