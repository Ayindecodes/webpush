"use client";

import { useCrumbs } from "@/components/shell/context";
import { Icon } from "@/components/ui/icons";
import { Notice, PageHeader } from "@/components/ui/primitives";

const PLANNED = [
  {
    name: "GitHub",
    body: "Link problems to the code that causes them, suggest a fix in a separate branch, and prove it with the automatic test before you merge.",
    icon: <Icon.Code size={18} />,
  },
  { name: "Pull-request checks", body: "Run the automatic tests on every preview of a change, before it goes live.", icon: <Icon.Flask size={18} /> },
  { name: "Scheduled checks", body: "Check your site again on a schedule, or after every release, to catch new problems early.", icon: <Icon.Refresh size={18} /> },
];

export default function IntegrationsPage() {
  useCrumbs([{ label: "Settings", href: "/settings" }, { label: "Integrations" }]);
  return (
    <div className="space-y-10">
      <PageHeader
        title="Integrations"
        description="Connect WEB X-RAY to the tools your team already uses. Everything else in WEB X-RAY works without them."
      />
      <Notice title="Not available yet">
        None of these connections exist yet — they&apos;re listed so you know what&apos;s coming. We won&apos;t show a connect button until it really works.
      </Notice>
      <ul className="grid gap-5 md:grid-cols-3">
        {PLANNED.map((p) => (
          <li key={p.name} className="panel flex flex-col p-6">
            <span className="flex size-11 items-center justify-center rounded-xl border-[1.5px] border-border-strong bg-surface-2 text-fg-muted">{p.icon}</span>
            <div className="mt-4 text-[1.125rem] font-semibold tracking-[-0.01em]">{p.name}</div>
            <p className="mt-1.5 flex-1 text-body leading-relaxed text-fg-muted">{p.body}</p>
            <span className="mt-5 self-start rounded-full border border-dashed border-border-strong px-3 py-1 text-meta text-fg-subtle">Coming later</span>
          </li>
        ))}
      </ul>
      <p className="max-w-2xl text-body leading-relaxed text-fg-muted">
        Today you can already download any automatic test from a problem&apos;s page and add it to your own test suite. It reads the website address
        and test-account details from environment variables, so no secrets are written into the file.
      </p>
    </div>
  );
}
