"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState, type FormEvent, type ReactNode } from "react";

import { BriefingForm, BriefingRow, parseWebsite } from "@/components/briefing";
import { FindingRows, InvestigationTable } from "@/components/lists";
import { useCrumbs, useShell } from "@/components/shell/context";
import { Icon } from "@/components/ui/icons";
import { Button, EmptyState, ErrorState, LoadingRows, Metric, MetricStrip, Section, Skeleton, StepTile } from "@/components/ui/primitives";
import { relativeTime } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import type { Briefing, Finding, Investigation, Overview } from "@/lib/types";

interface Activity {
  id: number;
  ts: string;
  actor: string;
  label: string;
  subject: string;
}

function greeting(): string {
  const h = new Date().getHours();
  return h < 12 ? "Good morning" : h < 18 ? "Good afternoon" : "Good evening";
}

export default function HomePage() {
  useCrumbs([{ label: "Home" }]);
  const { user } = useShell();
  const overview = useApi<Overview>("/api/overview", { refreshInterval: 10_000 });
  const investigations = useApi<Investigation[]>("/api/investigations?limit=5", { refreshInterval: 5_000 });
  const briefings = useApi<Briefing[]>("/api/briefings?limit=4", { refreshInterval: 5_000 });
  const findings = useApi<Finding[]>("/api/findings?classification=confirmed_defect&classification=warning&limit=5", { refreshInterval: 10_000 });
  const activity = useApi<Activity[]>("/api/activity?limit=8", { refreshInterval: 15_000 });

  const o = overview.data;
  const firstName = (user.display_name || "").split(/\s+/)[0];
  const hasInvestigations = (o?.investigations.total ?? 0) > 0;

  return (
    <div className="space-y-14">
      <header>
        <h1 className="display">
          {greeting()}
          {firstName ? `, ${firstName}` : ""}.
        </h1>
        <p className="mt-2.5 text-body text-fg-muted">What would you like to find out today?</p>
      </header>

      <div className="grid gap-8 lg:grid-cols-2">
        <ActionCard
          eyebrow="Any website"
          title="Learn what a website is for"
          body="An agent reads the site and explains it in plain words — what it does, who it's for and who runs it."
          icon={<Icon.Compass size={20} />}
        >
          <BriefingForm compact />
        </ActionCard>
        <ActionCard
          eyebrow="Your website"
          title="Check your site for problems"
          body="Tests sign-up, checkout and more on desktop and phone, and proves every problem it finds."
          icon={<Icon.Search size={20} />}
        >
          <CheckSiteForm />
        </ActionCard>
      </div>

      {overview.error ? (
        <ErrorState error={overview.error} retry={() => overview.mutate()} />
      ) : !o ? (
        <Skeleton className="h-32 w-full" />
      ) : !hasInvestigations && o.projects === 0 ? (
        <GettingStarted />
      ) : (
        <Section eyebrow="At a glance" title="Your numbers" description="Counted from what our browsers actually did — nothing estimated.">
          <MetricStrip>
            <Metric
              label="Investigations"
              value={o.investigations.total}
              hint={activeHint(o)}
              href="/investigations"
            />
            <Metric
              label="Confirmed problems"
              value={o.findings.by_classification.confirmed_defect ?? 0}
              tone={(o.findings.by_classification.confirmed_defect ?? 0) > 0 ? "danger" : undefined}
              hint={`${o.findings.by_classification.warning ?? 0} possible · ${plural(o.findings.by_classification.observation ?? 0, "note")}`}
              href="/findings?classification=confirmed_defect"
            />
            <Metric
              label="Proved by a test"
              value={o.tests.by_status.reproduced ?? 0}
              hint={`${o.tests.by_status.not_reproduced ?? 0} fixed and now passing`}
              href="/findings"
            />
            <Metric label="Pages checked" value={o.pages_discovered} hint={`${o.features.tested ?? 0} features tested`} />
          </MetricStrip>
        </Section>
      )}

      <div className="grid gap-12 xl:grid-cols-[minmax(0,1fr)_320px]">
        <div className="min-w-0 space-y-12">
          <Section
            eyebrow="Needs attention"
            title="Problems to look at"
            description="Confirmed and possible problems, newest first."
            actions={<SeeAll href="/findings">All problems</SeeAll>}
          >
            {findings.error ? (
              <ErrorState error={findings.error} retry={() => findings.mutate()} />
            ) : !findings.data ? (
              <LoadingRows rows={3} />
            ) : findings.data.length === 0 ? (
              <EmptyState
                compact
                icon={<Icon.Check size={20} />}
                title="Nothing to fix"
                description={hasInvestigations ? "Your investigations haven't found any problems." : "Problems show up here after you check a site."}
              />
            ) : (
              <FindingRows items={findings.data} />
            )}
          </Section>

          <Section eyebrow="Recent" title="Investigations" actions={<SeeAll href="/investigations">All investigations</SeeAll>}>
            {investigations.error ? (
              <ErrorState error={investigations.error} retry={() => investigations.mutate()} />
            ) : !investigations.data ? (
              <LoadingRows />
            ) : investigations.data.length === 0 ? (
              <EmptyState compact title="No investigations yet" description="Check one of your sites to see results here." />
            ) : (
              <InvestigationTable items={investigations.data} />
            )}
          </Section>

          <Section eyebrow="Recent" title="Briefings" actions={<SeeAll href="/briefings">All briefings</SeeAll>}>
            {briefings.error ? (
              <ErrorState error={briefings.error} retry={() => briefings.mutate()} />
            ) : !briefings.data ? (
              <LoadingRows rows={2} />
            ) : briefings.data.length === 0 ? (
              <EmptyState compact title="No briefings yet" description="Ask about any website using the box above." />
            ) : (
              <div className="panel divide-y divide-border overflow-hidden">
                {briefings.data.map((b) => (
                  <BriefingRow key={b.id} b={b} />
                ))}
              </div>
            )}
          </Section>
        </div>

        <Section eyebrow="Activity" title="What happened" description="Recorded actions in your workspace.">
          {activity.error ? (
            <ErrorState error={activity.error} retry={() => activity.mutate()} />
          ) : !activity.data ? (
            <LoadingRows rows={5} />
          ) : activity.data.length === 0 ? (
            <p className="text-body text-fg-subtle">Nothing yet.</p>
          ) : (
            <ol className="space-y-4 border-l-[1.5px] border-border pl-5">
              {activity.data.map((a) => (
                <li key={a.id} className="relative text-body">
                  <span className="absolute -left-[26px] top-2 size-2.5 rounded-full border-2 border-bg bg-border-strong" aria-hidden />
                  <div className="leading-snug">
                    <span className="font-medium">{a.actor}</span> <span className="text-fg-muted">{a.label}</span>
                    {a.subject && <span className="break-words text-fg"> {a.subject}</span>}
                  </div>
                  <div className="mt-0.5 text-label text-fg-subtle">{relativeTime(a.ts)}</div>
                </li>
              ))}
            </ol>
          )}
        </Section>
      </div>
    </div>
  );
}

function plural(n: number, word: string): string {
  return `${n} ${word}${n === 1 ? "" : "s"}`;
}

function activeHint(o: Overview): string {
  const by = o.investigations.by_status;
  const active = (by.running ?? 0) + (by.queued ?? 0) + (by.paused ?? 0) + (by.awaiting_human ?? 0);
  return active ? `${active} running now` : `${by.completed ?? 0} finished`;
}

function SeeAll({ href, children }: { href: string; children: ReactNode }) {
  return (
    <Link href={href} className="inline-flex items-center gap-1 text-body font-medium text-fg-muted underline-offset-4 hover:text-fg hover:underline">
      {children} <Icon.ArrowRight size={13} />
    </Link>
  );
}

function ActionCard({ eyebrow, title, body, icon, children }: { eyebrow: string; title: string; body: string; icon: ReactNode; children: ReactNode }) {
  return (
    <section className="card-ink flex min-w-0 flex-col p-6 sm:p-8">
      <div className="flex items-start gap-4">
        <span className="flex size-11 shrink-0 items-center justify-center rounded-xl border-[1.5px] border-[var(--wx-ink-line)] bg-surface-2">{icon}</span>
        <div className="min-w-0">
          <p className="eyebrow">{eyebrow}</p>
          <h2 className="mt-1.5 text-[1.375rem] font-semibold leading-tight tracking-[-0.02em]">{title}</h2>
        </div>
      </div>
      <p className="mt-4 text-body leading-relaxed text-fg-muted">{body}</p>
      <div className="mt-6">{children}</div>
    </section>
  );
}

function CheckSiteForm() {
  const router = useRouter();
  const [url, setUrl] = useState("");
  const [error, setError] = useState<string | null>(null);
  const submit = (e: FormEvent) => {
    e.preventDefault();
    const parsed = parseWebsite(url);
    if ("error" in parsed) {
      setError(parsed.error);
      return;
    }
    router.push(`/investigations/new?url=${encodeURIComponent(new URL(parsed.url).origin)}`);
  };
  return (
    <form onSubmit={submit} noValidate>
      <label htmlFor="check-url" className="text-label font-semibold">
        Your website
      </label>
      <div className="mt-2 flex items-center gap-2 rounded-full border-[1.5px] border-border-strong bg-surface p-1.5 pl-5 transition-shadow focus-within:border-[var(--wx-ink-line)] focus-within:shadow-[0_0_0_4px_var(--wx-brand-soft)]">
        <Icon.Globe className="shrink-0 text-fg-subtle" />
        <input
          id="check-url"
          value={url}
          onChange={(e) => {
            setUrl(e.target.value);
            setError(null);
          }}
          placeholder="staging.your-app.com"
          inputMode="url"
          autoComplete="url"
          spellCheck={false}
          aria-invalid={!!error}
          aria-describedby="check-url-help"
          className="h-11 min-w-0 flex-1 bg-transparent text-[15px] outline-none placeholder:text-fg-subtle"
        />
        <Button type="submit" variant="paper" icon={<Icon.ArrowRight size={14} />} trailingIcon className="h-11 px-5">
          Continue
        </Button>
      </div>
      <p id="check-url-help" role={error ? "alert" : undefined} className={error ? "mt-2 pl-5 text-label font-medium text-danger" : "mt-2 pl-5 text-label text-fg-subtle"}>
        {error ?? "Only sites you own or may test. You'll prove that before anything runs."}
      </p>
    </form>
  );
}

function GettingStarted() {
  const steps = [
    { title: "Add your website", body: "Create a project and add the address you want to check.", href: "/projects" },
    { title: "Prove it's yours", body: "Add a small file or DNS record. We never test sites you don't control.", href: "/projects" },
    { title: "Start an investigation", body: "Pick phone and desktop, approve what it may do, and press start.", href: "/investigations/new" },
  ];
  return (
    <Section eyebrow="Getting started" title="Check your own site in three steps">
      <ol className="grid gap-6 md:grid-cols-3">
        {steps.map((s, i) => (
          <li key={s.title} className="panel flex gap-4 p-5">
            <StepTile>{String(i + 1).padStart(2, "0")}</StepTile>
            <div className="min-w-0">
              <Link href={s.href} className="text-[1.0625rem] font-semibold tracking-[-0.01em] underline-offset-4 hover:underline">
                {s.title}
              </Link>
              <p className="mt-1 text-body text-fg-muted">{s.body}</p>
            </div>
          </li>
        ))}
      </ol>
    </Section>
  );
}
