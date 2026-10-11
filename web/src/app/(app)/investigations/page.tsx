"use client";

import { useState } from "react";

import { InvestigationTable } from "@/components/lists";
import { useCrumbs, useShell } from "@/components/shell/context";
import { Icon } from "@/components/ui/icons";
import { ButtonLink, EmptyState, ErrorState, LoadingRows, PageHeader, Segmented } from "@/components/ui/primitives";
import { ACTIVE_STATUSES } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import type { Investigation } from "@/lib/types";

type Filter = "all" | "active" | "completed" | "problem";

const MATCH: Record<Filter, (i: Investigation) => boolean> = {
  all: () => true,
  active: (i) => ACTIVE_STATUSES.has(i.status),
  completed: (i) => i.status === "completed",
  problem: (i) => ["failed", "blocked", "stopped"].includes(i.status),
};

export default function InvestigationsPage() {
  useCrumbs([{ label: "Investigations" }]);
  const { projectId } = useShell();
  const { data, error, mutate } = useApi<Investigation[]>(`/api/investigations?limit=200${projectId ? `&project_id=${projectId}` : ""}`, {
    refreshInterval: (d) => (d?.some((i) => ACTIVE_STATUSES.has(i.status)) ? 3000 : 15000),
  });
  const [filter, setFilter] = useState<Filter>("all");
  const items = (data ?? []).filter(MATCH[filter]);
  const count = (f: Filter) => (data ?? []).filter(MATCH[f]).length;

  return (
    <div className="space-y-8">
      <PageHeader
        title="Investigations"
        description="Each investigation opens your website in a fresh, isolated browser, tries the important journeys on desktop and phone, and reports what's broken — with proof."
        actions={
          <>
            <ButtonLink href="/journeys" variant="paper" icon={<Icon.Journey />}>
              Journeys tried
            </ButtonLink>
            <ButtonLink href="/investigations/new" variant="primary" icon={<Icon.Plus />}>
              New investigation
            </ButtonLink>
          </>
        }
      />
      <Segmented
        label="Show investigations"
        value={filter}
        onChange={setFilter}
        options={[
          { value: "all", label: "All", count: count("all") },
          { value: "active", label: "Running", count: count("active") },
          { value: "completed", label: "Finished", count: count("completed") },
          { value: "problem", label: "Stopped or failed", count: count("problem") },
        ]}
      />
      {error ? (
        <ErrorState error={error} retry={() => mutate()} />
      ) : !data ? (
        <LoadingRows />
      ) : items.length === 0 ? (
        <EmptyState
          icon={<Icon.Investigation size={20} />}
          title={data.length === 0 ? "No investigations yet" : "Nothing here"}
          description={data.length === 0 ? "Add one of your websites, prove it's yours, and start your first check." : "No investigations match this filter."}
          action={
            data.length === 0 ? (
              <ButtonLink href="/investigations/new" variant="primary">
                Start an investigation
              </ButtonLink>
            ) : undefined
          }
        />
      ) : (
        <InvestigationTable items={items} />
      )}
    </div>
  );
}
