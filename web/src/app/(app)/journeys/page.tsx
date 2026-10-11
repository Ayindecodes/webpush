"use client";

import Link from "next/link";

import { JourneyMatrix } from "@/components/journey-matrix";
import { useCrumbs, useShell } from "@/components/shell/context";
import { Icon } from "@/components/ui/icons";
import { ButtonLink, EmptyState, ErrorState, LoadingRows, PageHeader } from "@/components/ui/primitives";
import { StatusPill } from "@/components/ui/status";
import { hostOf, relativeTime } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import type { Investigation, Journey } from "@/lib/types";

export default function JourneysPage() {
  useCrumbs([{ label: "Investigations", href: "/investigations" }, { label: "Journeys tested" }]);
  const { projectId } = useShell();
  const { data, error, mutate } = useApi<Journey[]>("/api/journeys?limit=50", { refreshInterval: 10_000 });
  const invs = useApi<Investigation[]>(projectId ? `/api/investigations?limit=200&project_id=${projectId}` : null);
  const allowed = projectId ? new Set(invs.data?.map((i) => i.id)) : null;
  const items = (data ?? []).filter((j) => !allowed || allowed.has(j.investigation_id));

  return (
    <div className="space-y-10">
      <PageHeader
        title="Journeys tested"
        description="A journey is something a visitor does from start to finish — like finding a product and paying for it. Each row is one try; each square is one step. Click a square to see what happened."
      />
      <div className="flex flex-wrap items-center gap-x-5 gap-y-2 text-label text-fg-muted">
        <Legend cls="bg-success-soft text-success" icon={<Icon.Check size={12} />}>Step worked</Legend>
        <Legend cls="bg-danger-soft text-danger" icon={<Icon.X size={12} />}>Step failed</Legend>
        <Legend cls="bg-surface-2 text-fg-subtle" icon={<span className="text-[10px]">–</span>}>Skipped</Legend>
      </div>
      {error ? (
        <ErrorState error={error} retry={() => mutate()} />
      ) : !data ? (
        <LoadingRows />
      ) : items.length === 0 ? (
        <EmptyState
          icon={<Icon.Journey size={20} />}
          title="No journeys tried yet"
          description="Checkout is tried when an investigation finds a product with an “Add to cart” button."
          action={
            <ButtonLink href="/investigations/new" variant="primary">
              Check a website
            </ButtonLink>
          }
        />
      ) : (
        <div className="space-y-12">
          {items.map((j) => (
            <section key={j.id}>
              <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
                <div className="min-w-0">
                  <h2 className="flex flex-wrap items-center gap-2.5 text-[1.25rem] font-semibold tracking-[-0.02em]">
                    {j.name} <span className="font-normal text-fg-muted">on {hostOf(j.origin)}</span> <StatusPill status={j.status} />
                  </h2>
                  <p className="mt-1 text-label text-fg-subtle">
                    {j.project_name ? `${j.project_name} · ` : ""}
                    {relativeTime(j.created_at)}
                  </p>
                </div>
                <Link href={`/investigations/${j.investigation_id}`} className="inline-flex items-center gap-1 text-body font-medium text-fg-muted underline-offset-4 hover:text-fg hover:underline">
                  Open the investigation <Icon.ArrowRight size={13} />
                </Link>
              </div>
              <JourneyMatrix journey={j} />
            </section>
          ))}
        </div>
      )}
    </div>
  );
}

function Legend({ cls, icon, children }: { cls: string; icon: React.ReactNode; children: React.ReactNode }) {
  return (
    <span className="inline-flex items-center gap-2">
      <span className={`inline-flex size-6 items-center justify-center rounded-md ${cls}`}>{icon}</span>
      {children}
    </span>
  );
}
