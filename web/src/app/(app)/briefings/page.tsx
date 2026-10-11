"use client";

import Link from "next/link";

import { BriefingForm, BriefingRow } from "@/components/briefing";
import { useCrumbs } from "@/components/shell/context";
import { Icon } from "@/components/ui/icons";
import { EmptyState, ErrorState, LoadingRows, PageHeader, Section } from "@/components/ui/primitives";
import { useApi } from "@/lib/hooks";
import type { Briefing } from "@/lib/types";

export default function BriefingsPage() {
  useCrumbs([{ label: "Briefings" }]);
  const list = useApi<Briefing[]>("/api/briefings", {
    refreshInterval: (d) => (d?.some((b) => b.status === "queued" || b.status === "running") ? 2000 : 0),
  });
  return (
    <div className="space-y-12">
      <PageHeader
        title="Briefings"
        description="Type any website and an agent reads it for you, then explains what it is, what it's for and who runs it."
      />
      <div className="card-ink max-w-3xl p-6 sm:p-7">
        <BriefingForm compact />
        <p className="mt-3 pl-5 text-label text-fg-subtle">
          Want to ask something specific, or sign in for a more detailed briefing? Use the <Link href="/briefings/new" className="font-medium text-fg underline-offset-4 hover:underline">full form</Link>.
        </p>
      </div>
      <Section eyebrow="History" title="Your briefings">
        {list.error ? (
          <ErrorState error={list.error} retry={() => list.mutate()} />
        ) : !list.data ? (
          <LoadingRows rows={3} />
        ) : list.data.length === 0 ? (
          <EmptyState
            icon={<Icon.Compass size={20} />}
            title="No briefings yet"
            description="Try a site you're curious about — a competitor, a supplier, or a link someone sent you."
          />
        ) : (
          <div className="panel divide-y divide-border overflow-hidden">
            {list.data.map((b) => (
              <BriefingRow key={b.id} b={b} />
            ))}
          </div>
        )}
      </Section>
    </div>
  );
}
