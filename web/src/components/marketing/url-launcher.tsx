"use client";

import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";

import { Icon } from "@/components/ui/icons";
import { cx } from "@/components/ui/primitives";
import { useSession } from "@/lib/hooks";
import { registerHref } from "@/lib/routes";

type Mode = "brief" | "check";

const MODES: { value: Mode; label: string; button: string; placeholder: string; hint: string }[] = [
  { value: "brief", label: "Explain a website", button: "Brief me", placeholder: "any-website.com", hint: "Works on any public website." },
  { value: "check", label: "Find what's broken", button: "Investigate", placeholder: "your-site.com", hint: "For sites you own — you'll prove it first." },
];

/**
 * "Paste a URL" entry point with two jobs: a briefing (any site) or an
 * investigation (your site). Signed-in users go straight to the pre-filled
 * form; everyone else creates an account first and lands there after.
 * Nothing runs until they confirm on that form.
 */
export function UrlLauncher({ dark = false, className = "", initialMode = "brief" }: { dark?: boolean; className?: string; initialMode?: Mode }) {
  const router = useRouter();
  const user = useSession();
  const [mode, setMode] = useState<Mode>(initialMode);
  const [url, setUrl] = useState("");
  const [error, setError] = useState<string | null>(null);
  const m = MODES.find((x) => x.value === mode)!;
  const id = dark ? "launch-url-footer" : "launch-url";

  function submit(e: FormEvent) {
    e.preventDefault();
    let origin: string;
    try {
      const raw = url.trim();
      const u = new URL(raw.includes("://") ? raw : `https://${raw}`);
      if (!["http:", "https:"].includes(u.protocol) || (!u.hostname.includes(".") && u.hostname !== "localhost")) throw new Error();
      origin = u.origin;
    } catch {
      setError("Type a website address, like example.com");
      return;
    }
    const target = mode === "brief" ? `/briefings/new?url=${encodeURIComponent(origin)}` : `/investigations/new?url=${encodeURIComponent(origin)}`;
    router.push(user ? target : registerHref(target));
  }

  return (
    <form onSubmit={submit} className={className} noValidate>
      <div role="radiogroup" aria-label="What do you want to do?" className={cx("mb-3 inline-flex gap-1 rounded-full p-1", dark ? "bg-white/8" : "border border-border bg-surface")}>
        {MODES.map((x) => (
          <button
            key={x.value}
            type="button"
            role="radio"
            aria-checked={mode === x.value}
            onClick={() => {
              setMode(x.value);
              setError(null);
            }}
            className={cx(
              "h-8 rounded-full px-3.5 text-label font-medium transition-colors",
              mode === x.value ? (dark ? "bg-white text-[oklch(0.17_0.008_275)]" : "bg-fg text-bg") : dark ? "text-white/70 hover:text-white" : "text-fg-muted hover:text-fg",
            )}
          >
            {x.label}
          </button>
        ))}
      </div>
      <div
        className={cx(
          "flex items-center gap-2 rounded-full border p-1.5 pl-5 transition-shadow focus-within:shadow-[0_0_0_4px_var(--wx-brand-soft)]",
          dark ? "border-white/15 bg-white/5" : "border-border-strong bg-surface shadow-[0_10px_30px_-18px_oklch(0.3_0.02_85/0.5)]",
        )}
      >
        <Icon.Globe className={dark ? "shrink-0 text-white/50" : "shrink-0 text-fg-subtle"} />
        <label htmlFor={id} className="sr-only">
          Website address
        </label>
        <input
          id={id}
          value={url}
          onChange={(e) => {
            setUrl(e.target.value);
            setError(null);
          }}
          placeholder={m.placeholder}
          inputMode="url"
          autoComplete="url"
          spellCheck={false}
          aria-invalid={!!error}
          aria-describedby={`${id}-hint`}
          className={cx("h-10 min-w-0 flex-1 bg-transparent text-[15px] outline-none", dark ? "text-white placeholder:text-white/40" : "text-fg placeholder:text-fg-subtle")}
        />
        <button
          type="submit"
          className={cx(
            "inline-flex h-10 shrink-0 items-center gap-1.5 rounded-full px-4 text-body font-medium transition-colors",
            dark ? "bg-brand text-brand-fg hover:bg-brand-hover" : "bg-fg text-bg hover:bg-fg/88",
          )}
        >
          {m.button} <Icon.ArrowRight size={14} />
        </button>
      </div>
      <p
        id={`${id}-hint`}
        role={error ? "alert" : undefined}
        className={cx("mt-2 pl-5 text-label", error ? (dark ? "text-[oklch(0.8_0.12_30)]" : "text-danger") : dark ? "text-white/45" : "text-fg-subtle")}
      >
        {error ?? m.hint}
      </p>
    </form>
  );
}
