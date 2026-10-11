"use client";

import { useParams, useRouter } from "next/navigation";
import { useState } from "react";

import { BriefingLive, BriefingProblem, BriefingReport, BriefingStatus, WorkerNotice, hasResult, isBriefingActive } from "@/components/briefing";
import { useCrumbs } from "@/components/shell/context";
import { Icon } from "@/components/ui/icons";
import { Button, ButtonLink, ConfirmDialog, LoadError, LoadingRows, PageHeader, useToast } from "@/components/ui/primitives";
import { api } from "@/lib/api";
import { duration, hostOf, relativeTime } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import type { Briefing } from "@/lib/types";

export default function BriefingPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const toast = useToast();
  const [confirm, setConfirm] = useState(false);
  const [deleting, setDeleting] = useState(false);
  // Screenshot links are signed for 10 minutes; refresh finished briefings well inside that.
  const q = useApi<Briefing>(`/api/briefings/${id}`, {
    refreshInterval: (d) => (d && isBriefingActive(d) ? 1200 : 5 * 60 * 1000),
  });
  const b = q.data;
  useCrumbs([{ label: "Briefings", href: "/briefings" }, { label: b ? (hasResult(b) ? b.result.name : hostOf(b.origin)) : "Briefing" }]);

  if (q.error) return <LoadError error={q.error} retry={() => q.mutate()} what="briefing" backHref="/briefings" backLabel="All briefings" />;
  if (!b) return <LoadingRows rows={6} />;

  const done = hasResult(b);
  return (
    <div>
      <PageHeader
        eyebrow={
          <span className="inline-flex flex-wrap items-center gap-2">
            Briefing · {hostOf(b.origin)}
          </span>
        }
        title={done ? b.result.name : isBriefingActive(b) ? `Reading ${hostOf(b.origin)}…` : hostOf(b.origin)}
        description={done ? (b.result.description ? `“${b.result.description}”` : undefined) : undefined}
        meta={
          <>
            <BriefingStatus b={b} />
            <span>Asked {relativeTime(b.created_at)}</span>
            {b.started_at && <span>Took {duration(b.started_at, b.finished_at)}</span>}
            <a href={b.origin} target="_blank" rel="noreferrer noopener" className="inline-flex items-center gap-1 hover:text-fg">
              Visit site <Icon.External size={12} />
            </a>
          </>
        }
        actions={
          !isBriefingActive(b) && (
            <>
              <ButtonLink href={`/briefings/new?url=${encodeURIComponent(b.origin)}`} variant="paper" icon={<Icon.Refresh />}>
                Ask again
              </ButtonLink>
              <Button variant="ghost" icon={<Icon.Trash />} onClick={() => setConfirm(true)}>
                Delete
              </Button>
            </>
          )
        }
      />

      {b.status === "queued" && (
        <div className="mb-8">
          <WorkerNotice queuedAt={b.created_at} waiting />
        </div>
      )}
      {isBriefingActive(b) ? <BriefingLive b={b} /> : done ? <BriefingReport b={b} /> : <BriefingProblem b={b} />}

      {done && (
        <div className="card-ink mt-14 flex flex-col gap-5 p-7 sm:flex-row sm:items-center sm:justify-between sm:p-8">
          <div>
            <p className="eyebrow">Is this your website?</p>
            <p className="mt-2 text-[1.25rem] font-semibold tracking-[-0.02em]">Check it for problems next.</p>
            <p className="mt-1 max-w-xl text-body text-fg-muted">
              An investigation goes further: it tests sign-up and checkout on desktop and phone, and proves every problem it finds.
            </p>
          </div>
          <ButtonLink href={`/investigations/new?url=${encodeURIComponent(b.origin)}`} variant="primary" size="lg" icon={<Icon.ArrowRight size={15} />} trailingIcon>
            Start an investigation
          </ButtonLink>
        </div>
      )}

      <ConfirmDialog
        open={confirm}
        title="Delete this briefing?"
        description="The briefing and its screenshots will be removed for everyone in your workspace."
        confirmLabel="Delete briefing"
        busy={deleting}
        onCancel={() => setConfirm(false)}
        onConfirm={async () => {
          setDeleting(true);
          try {
            await api.del(`/api/briefings/${b.id}`);
            toast("Briefing deleted");
            router.replace("/briefings");
          } catch (e) {
            toast(e instanceof Error ? e.message : "Couldn't delete", "danger");
            setDeleting(false);
            setConfirm(false);
          }
        }}
      />
    </div>
  );
}
