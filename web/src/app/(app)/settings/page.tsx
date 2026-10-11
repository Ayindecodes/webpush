"use client";

import Link from "next/link";
import { useState } from "react";

import { useCrumbs, useShell } from "@/components/shell/context";
import { useTheme } from "@/components/theme";
import { Icon } from "@/components/ui/icons";
import { Button, KeyValue, PageHeader, Section, cx } from "@/components/ui/primitives";
import { api } from "@/lib/api";

const SAFETY = [
  ["We only test sites you've proved are yours", "Before an investigation, you add a small file or DNS record to show you own the site."],
  ["Nothing internal is ever reached", "Our browser can't connect to private networks, your computer, or cloud servers' internal addresses."],
  ["Passwords stay locked away", "They're encrypted, only typed into our isolated browser, and hidden from logs, screenshots and reports."],
  ["Nothing important happens without your yes", "Creating accounts and placing test orders need your explicit permission, which we record."],
  ["Human checks are left to humans", "CAPTCHAs, two-factor codes and email confirmations are never bypassed."],
];

export default function SettingsPage() {
  useCrumbs([{ label: "Settings" }]);
  const { user } = useShell();
  const [theme, setTheme] = useTheme();
  const [busy, setBusy] = useState(false);

  return (
    <div className="space-y-14">
      <PageHeader title="Settings" />

      <Section eyebrow="You" title="Your account">
        <div className="panel max-w-2xl p-6">
          <KeyValue
            items={[
              ["Name", user.display_name || "—"],
              ["Email", user.email],
              ["Workspace", user.organization_name],
            ]}
          />
          <div className="mt-6 border-t border-border pt-5">
            <Button
              variant="paper"
              loading={busy}
              icon={<Icon.Logout />}
              onClick={async () => {
                setBusy(true);
                try {
                  await api.post("/api/auth/logout");
                } finally {
                  // Full reload so nothing from this session stays cached in the page.
                  // eslint-disable-next-line @next/next/no-location-assign-relative-destination
                  window.location.assign("/login");
                }
              }}
            >
              Sign out
            </Button>
          </div>
        </div>
      </Section>

      <Section eyebrow="Look" title="Appearance" description="Paper is light and easy to read in daylight; Ink is dark and easier on the eyes at night.">
        <div className="grid max-w-xl gap-4 sm:grid-cols-2" role="radiogroup" aria-label="Theme">
          {([
            ["light", "Paper", "Light"],
            ["dark", "Ink", "Dark"],
          ] as const).map(([value, name, sub]) => (
            <button
              key={value}
              role="radio"
              aria-checked={theme === value}
              onClick={() => setTheme(value)}
              className={cx(
                "flex items-center gap-4 rounded-2xl border-[1.5px] p-4 text-left transition-colors",
                theme === value ? "border-[var(--wx-ink-line)] bg-surface shadow-[3px_3px_0_var(--wx-ink-shadow)]" : "border-border hover:border-border-strong",
              )}
            >
              <span
                className={cx(
                  "flex size-12 shrink-0 items-center justify-center rounded-xl border",
                  value === "light" ? "border-[oklch(0.8_0.018_85)] bg-[oklch(0.968_0.008_85)] text-[oklch(0.2_0.012_275)]" : "border-[oklch(0.4_0.012_275)] bg-[oklch(0.165_0.008_275)] text-[oklch(0.95_0.008_85)]",
                )}
                aria-hidden
              >
                {value === "light" ? <Icon.Sun /> : <Icon.Moon />}
              </span>
              <span className="flex-1">
                <span className="block text-body font-semibold">{name}</span>
                <span className="block text-label text-fg-muted">{sub}</span>
              </span>
              <span className={cx("size-4 rounded-full border", theme === value ? "border-[5px] border-fg" : "border-border-strong")} />
            </button>
          ))}
        </div>
      </Section>

      <Section eyebrow="Connections" title="Integrations" description="Connect WEB X-RAY to tools like GitHub. Nothing is available yet — see what's planned.">
        <Link href="/integrations" className="inline-flex items-center gap-1.5 text-body font-medium underline-offset-4 hover:underline">
          See planned integrations <Icon.ArrowRight size={13} />
        </Link>
      </Section>

      <Section eyebrow="Safety" title="How we keep things safe" description="These rules are built into WEB X-RAY itself — they can't be switched off by a website.">
        <ul className="grid gap-4 md:grid-cols-2">
          {SAFETY.map(([t, d]) => (
            <li key={t} className="panel flex gap-3 p-5">
              <Icon.Shield size={18} className="mt-0.5 shrink-0 text-brand-text" />
              <div>
                <div className="text-body font-semibold">{t}</div>
                <p className="mt-1 text-label leading-relaxed text-fg-muted">{d}</p>
              </div>
            </li>
          ))}
        </ul>
      </Section>
    </div>
  );
}
