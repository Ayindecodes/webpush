"use client";

import { useSearchParams } from "next/navigation";
import { Suspense } from "react";

import { BriefingForm } from "@/components/briefing";
import { useCrumbs } from "@/components/shell/context";
import { Icon } from "@/components/ui/icons";
import { PageHeader } from "@/components/ui/primitives";

const STEPS = [
  { title: "It opens the site", body: "A fresh, isolated browser visits the home page — just like you would." },
  { title: "It reads the important pages", body: "About, pricing, products, help, contact… up to 8 public pages — plus up to 6 members-only pages if you let it sign in." },
  { title: "It writes you a briefing", body: "What the site is, what you can do there, who runs it — with links to every source." },
];

function NewBriefing() {
  const params = useSearchParams();
  useCrumbs([{ label: "Briefings", href: "/briefings" }, { label: "Ask about a website" }]);
  return (
    <div className="grid gap-12 lg:grid-cols-[minmax(0,1.2fr)_minmax(0,0.8fr)]">
      <div className="min-w-0">
        <PageHeader
          eyebrow="Briefing · about a minute"
          title="Ask about any website."
          description="Send an agent to read a website and tell you, in plain words, what it is and what it's for. It works on any public site — it doesn't need to be yours."
        />
        <div className="card-ink p-6 sm:p-8">
          <BriefingForm initialUrl={params.get("url") ?? ""} />
        </div>
      </div>
      <aside className="min-w-0 lg:pt-28">
        <p className="eyebrow">What happens</p>
        <ol className="mt-5 space-y-6">
          {STEPS.map((s, i) => (
            <li key={s.title} className="grid grid-cols-[2.5rem_1fr] gap-4">
              <span className="flex size-10 items-center justify-center rounded-xl border-[1.5px] border-[var(--wx-ink-line)] bg-surface font-mono text-[12px]">
                {String(i + 1).padStart(2, "0")}
              </span>
              <div>
                <div className="text-[1.0625rem] font-semibold tracking-[-0.01em]">{s.title}</div>
                <p className="mt-1 text-body text-fg-muted">{s.body}</p>
              </div>
            </li>
          ))}
        </ol>
        <div className="mt-8 rounded-2xl border border-border bg-surface-2/70 p-5">
          <div className="flex items-center gap-2 text-body font-semibold">
            <Icon.Shield size={16} className="text-brand-text" /> Look, don&apos;t touch
          </div>
          <p className="mt-2 text-label leading-relaxed text-fg-muted">
            A briefing never fills in forms, clicks buttons or buys anything. It follows the site&apos;s robots.txt and only
            visits public internet addresses. If you add an account, signing in is the one form it submits — and your password
            is deleted when the briefing ends.
          </p>
        </div>
      </aside>
    </div>
  );
}

export default function NewBriefingPage() {
  return (
    <Suspense>
      <NewBriefing />
    </Suspense>
  );
}
