"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState, type FormEvent, type ReactNode } from "react";

import { Mark } from "@/components/brand/logo";
import { Icon } from "@/components/ui/icons";
import { Badge, Button, ButtonLink, Checkbox, Field, Input, Notice, Panel, Section, Spinner, Textarea, cx } from "@/components/ui/primitives";
import { api } from "@/lib/api";
import { formatMs, hostOf, relativeTime } from "@/lib/format";
import { useNow, useWorkers } from "@/lib/hooks";
import type { Briefing, BriefingResult } from "@/lib/types";

export const BRIEFING_PAGE_LIMIT = 8;

export const QUESTION_IDEAS = ["What do they sell?", "How much does it cost?", "How can I contact them?", "Do they have a mobile app?"];

export function isBriefingActive(b: Pick<Briefing, "status">) {
  return b.status === "queued" || b.status === "running";
}

export function hasResult(b: Briefing): b is Briefing & { result: BriefingResult } {
  return b.status === "completed" && "summary" in b.result;
}

/** Normalizes what someone typed into an http(s) URL, or explains what's wrong. */
export function parseWebsite(raw: string): { url: string } | { error: string } {
  const text = raw.trim();
  if (!text) return { error: "Type a website address, like example.com" };
  try {
    const u = new URL(text.includes("://") ? text : `https://${text}`);
    if (!["http:", "https:"].includes(u.protocol)) return { error: "Only web addresses that start with http or https work here." };
    if (!u.hostname.includes(".") && u.hostname !== "localhost") return { error: "That doesn't look like a website address. Try something like example.com" };
    return { url: u.toString() };
  } catch {
    return { error: "That doesn't look like a website address. Try something like example.com" };
  }
}

// ------------------------------------------------------------------ ask form

export function BriefingForm({ initialUrl = "", compact = false }: { initialUrl?: string; compact?: boolean }) {
  const router = useRouter();
  const [url, setUrl] = useState(initialUrl);
  const [question, setQuestion] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [useLogin, setUseLogin] = useState(false);
  const [login, setLogin] = useState({ username: "", password: "", login_url: "" });
  const [confirmed, setConfirmed] = useState(false);
  const [loginError, setLoginError] = useState<string | null>(null);

  async function submit(e: FormEvent) {
    e.preventDefault();
    const parsed = parseWebsite(url);
    if ("error" in parsed) {
      setError(parsed.error);
      return;
    }
    const withLogin = useLogin && (login.username.trim() || login.password);
    if (withLogin) {
      if (!login.username.trim() || !login.password) {
        setLoginError("Enter both the email (or username) and the password, or turn sign-in off.");
        return;
      }
      if (!confirmed) {
        setLoginError("Tick the box to confirm this is your account.");
        return;
      }
    }
    setBusy(true);
    setError(null);
    setLoginError(null);
    try {
      const b = await api.post<Briefing>("/api/briefings", {
        url: parsed.url,
        question: question.trim(),
        ...(withLogin ? { login: { ...login, username: login.username.trim(), login_url: login.login_url.trim() }, confirm_account: true } : {}),
      });
      // Don't keep the password in this (possibly preserved) form once it has been sent.
      setLogin({ username: "", password: "", login_url: "" });
      setConfirmed(false);
      setUseLogin(false);
      setUrl(initialUrl);
      setQuestion("");
      setBusy(false); // the form may be kept alive for the back button; leave it ready for the next briefing
      router.push(`/briefings/${b.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Couldn't start the briefing.");
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} noValidate className="space-y-5">
      <div>
        <label htmlFor="briefing-url" className="text-label font-semibold">
          Which website?
        </label>
        <div className="mt-2 flex items-center gap-2 rounded-full border-[1.5px] border-[var(--wx-ink-line)] bg-surface p-1.5 pl-5 transition-shadow focus-within:shadow-[0_0_0_4px_var(--wx-brand-soft)]">
          <Icon.Globe className="shrink-0 text-fg-subtle" />
          <input
            id="briefing-url"
            value={url}
            onChange={(e) => {
              setUrl(e.target.value);
              setError(null);
            }}
            placeholder="example.com"
            inputMode="url"
            autoComplete="url"
            spellCheck={false}
            autoFocus={!initialUrl}
            aria-invalid={!!error}
            aria-describedby={error ? "briefing-error" : undefined}
            className="h-11 min-w-0 flex-1 bg-transparent text-[15px] outline-none placeholder:text-fg-subtle"
          />
          <Button type="submit" variant="primary" loading={busy} icon={busy ? undefined : <Icon.ArrowRight size={14} />} trailingIcon className="h-11 px-5">
            {busy ? "Starting" : "Brief me"}
          </Button>
        </div>
        {error && (
          <p id="briefing-error" role="alert" className="mt-2 pl-5 text-label font-medium text-danger">
            {error}
          </p>
        )}
      </div>
      {!compact && (
        <div>
          <label htmlFor="briefing-question" className="text-label font-semibold">
            Anything specific you want to know? <span className="font-normal text-fg-subtle">Optional</span>
          </label>
          <Textarea
            id="briefing-question"
            className="mt-2"
            rows={2}
            maxLength={300}
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            placeholder="For example: Do they ship to Canada?"
          />
          <div className="mt-2.5 flex flex-wrap gap-2">
            {QUESTION_IDEAS.map((q) => (
              <button
                key={q}
                type="button"
                onClick={() => setQuestion(q)}
                className={cx(
                  "rounded-full border px-3 py-1 text-label transition-colors",
                  question === q ? "border-fg bg-fg text-bg" : "border-border-strong text-fg-muted hover:border-fg hover:text-fg",
                )}
              >
                {q}
              </button>
            ))}
          </div>
        </div>
      )}
      {!compact && (
        <div className={cx("rounded-2xl border transition-colors", useLogin ? "border-[var(--wx-ink-line)] bg-surface" : "border-border")}>
          <label className="flex cursor-pointer items-start gap-3 px-5 py-4">
            <input
              type="checkbox"
              checked={useLogin}
              onChange={(e) => {
                setUseLogin(e.target.checked);
                setLoginError(null);
              }}
              className="mt-1 size-[18px] shrink-0 accent-[var(--wx-fg)]"
            />
            <span>
              <span className="flex items-center gap-2 text-body font-semibold">
                <Icon.Lock size={14} /> Sign in for a more detailed briefing
              </span>
              <span className="mt-0.5 block text-label leading-relaxed text-fg-muted">
                If you have an account on this site, the agent can sign in and also describe what members see — like your
                dashboard, orders or settings.
              </span>
            </span>
          </label>
          {useLogin && (
            <div className="wx-enter space-y-4 border-t border-border px-5 pb-5 pt-4">
              <div className="grid gap-4 sm:grid-cols-2">
                <Field label="Username, email or ID" htmlFor="briefing-login-user" hint="Exactly what you type on the site's sign-in page.">
                  <Input
                    id="briefing-login-user"
                    autoComplete="off"
                    spellCheck={false}
                    value={login.username}
                    onChange={(e) => setLogin({ ...login, username: e.target.value })}
                  />
                </Field>
                <Field label="Password" htmlFor="briefing-login-pass">
                  <Input
                    id="briefing-login-pass"
                    type="password"
                    autoComplete="new-password"
                    value={login.password}
                    onChange={(e) => setLogin({ ...login, password: e.target.value })}
                  />
                </Field>
              </div>
              {/^\s*http:\/\//i.test(url) && (
                <Notice tone="warn" title="This address isn't secure (http)">
                  We only send passwords over secure (https) connections. If the site has no https version, the briefing will
                  stay signed out and describe the public pages.
                </Notice>
              )}
              <Field label="Sign-in page" htmlFor="briefing-login-url" optional hint="Leave empty and the agent will look for the sign-in link itself.">
                <Input
                  id="briefing-login-url"
                  placeholder="/login"
                  spellCheck={false}
                  className="font-mono text-[14px]"
                  value={login.login_url}
                  onChange={(e) => setLogin({ ...login, login_url: e.target.value })}
                />
              </Field>
              <Checkbox
                checked={confirmed}
                onChange={(v) => {
                  setConfirmed(v);
                  setLoginError(null);
                }}
                label="This is my account (or one I'm allowed to use)"
                description="The agent only signs in and reads pages. It won't change settings, post, buy or delete anything."
              />
              <ul className="space-y-1.5 rounded-xl bg-surface-2 px-4 py-3 text-label text-fg-muted">
                <li className="flex gap-2">
                  <Icon.Shield size={14} className="mt-0.5 shrink-0 text-brand-text" /> Your password is encrypted, used once for this briefing, then deleted.
                </li>
                <li className="flex gap-2">
                  <Icon.Shield size={14} className="mt-0.5 shrink-0 text-brand-text" /> It never appears in screenshots, steps or the report.
                </li>
                <li className="flex gap-2">
                  <Icon.Shield size={14} className="mt-0.5 shrink-0 text-brand-text" /> Bot checks and two-factor codes are never bypassed — the briefing continues signed out.
                </li>
                <li className="flex gap-2">
                  <Icon.SevInfo size={14} className="mt-0.5 shrink-0" /> Members-only pages can include your own details, and briefings are visible to your workspace.
                </li>
              </ul>
              {loginError && (
                <p role="alert" className="text-label font-medium text-danger">
                  {loginError}
                </p>
              )}
            </div>
          )}
        </div>
      )}
    </form>
  );
}

// ------------------------------------------------------------------ list item

export function BriefingRow({ b }: { b: Briefing }) {
  const name = hasResult(b) ? b.result.name : hostOf(b.origin);
  return (
    <Link href={`/briefings/${b.id}`} className="group flex items-center gap-4 px-5 py-4 transition-colors hover:bg-surface-2 sm:px-6">
      <span className="flex size-10 shrink-0 items-center justify-center rounded-xl border border-border-strong bg-surface text-fg-muted">
        {isBriefingActive(b) ? <Mark size={22} active /> : <Icon.Compass />}
      </span>
      <span className="min-w-0 flex-1">
        <span className="flex min-w-0 items-center gap-2">
          <span className="truncate text-body font-semibold">{name}</span>
          {hasResult(b) && <span className="truncate text-label text-fg-subtle max-sm:hidden">· {b.result.site_type.label}</span>}
        </span>
        <span className="mt-0.5 block truncate text-label text-fg-muted">
          {b.question ? `“${b.question}” · ` : ""}
          {hostOf(b.origin)} · {relativeTime(b.created_at)}
        </span>
      </span>
      <BriefingStatus b={b} />
      <Icon.Chevron className="shrink-0 text-fg-subtle transition-transform group-hover:translate-x-0.5" />
    </Link>
  );
}

export function BriefingStatus({ b }: { b: Briefing }) {
  if (b.status === "completed") return <Badge tone="success"><Icon.Check size={12} /> Ready</Badge>;
  if (b.status === "running") return <Badge tone="brand"><span className="wx-live-dot size-1.5 rounded-full bg-current" /> Reading</Badge>;
  if (b.status === "queued") return <Badge>Waiting to start</Badge>;
  if (b.status === "blocked") return <Badge tone="warning">Couldn&apos;t read</Badge>;
  return <Badge tone="danger">Failed</Badge>;
}

// ------------------------------------------------------------------ live view

export function WorkerNotice({ queuedAt, waiting }: { queuedAt: string; waiting: boolean }) {
  const now = useNow(1000, waiting);
  const workers = useWorkers(waiting);
  const waitedS = (now - new Date(queuedAt).getTime()) / 1000;
  if (!waiting || waitedS < 8 || !workers) return null;
  return workers.available === false ? (
    <Notice tone="warn" title="No browser is free to start this yet">
      WEB X-RAY&apos;s worker isn&apos;t running right now, so this is waiting in line. It will start by itself as soon as a
      worker is available — you don&apos;t need to do anything. (If you run WEB X-RAY yourself, start the worker process.)
    </Notice>
  ) : (
    <Notice title="Waiting in line">Another job is using the browser. This will start as soon as it&apos;s free.</Notice>
  );
}

export function BriefingLive({ b }: { b: Briefing }) {
  const pagesRead = b.shots.length;
  const latest = b.shots[b.shots.length - 1];
  const pct = Math.min(100, Math.round((pagesRead / BRIEFING_PAGE_LIMIT) * 100));
  return (
    <div className="grid gap-8 lg:grid-cols-[minmax(0,1.25fr)_minmax(0,1fr)]">
      <div className="card-ink overflow-hidden">
        <div className="flex items-center gap-3 border-b-[1.5px] border-[var(--wx-ink-line)] bg-surface-2 px-4 py-3">
          <span className="flex gap-1.5" aria-hidden>
            <span className="size-2.5 rounded-full bg-border-strong" />
            <span className="size-2.5 rounded-full bg-border-strong" />
            <span className="size-2.5 rounded-full bg-border-strong" />
          </span>
          <span className="flex min-w-0 flex-1 items-center gap-2 rounded-full border border-border bg-surface px-3 py-1 font-mono text-[12px] text-fg-muted">
            <Icon.Lock size={12} className="shrink-0" />
            <span className="truncate">{b.current_url ?? b.origin}</span>
          </span>
        </div>
        <div className="relative aspect-[16/10] bg-surface">
          {latest ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={latest.url} alt={`What the agent is looking at: ${latest.title ?? latest.page_url ?? "page"}`} className="absolute inset-0 size-full object-cover object-top" />
          ) : (
            <div className="absolute inset-0 flex flex-col items-center justify-center gap-4 text-fg-muted">
              <Mark size={56} active />
              <span className="text-body">{b.status === "queued" ? "Waiting for a free browser…" : "Opening the website…"}</span>
            </div>
          )}
          <div className="wx-scanline pointer-events-none absolute inset-x-0 h-16" aria-hidden />
        </div>
      </div>

      <div className="min-w-0">
        <p className="eyebrow">Now</p>
        <p className="mt-3 text-[1.375rem] font-semibold leading-snug tracking-[-0.02em]" aria-live="polite">
          {b.current_action ?? (b.status === "queued" ? "Waiting to start" : "Getting ready")}
        </p>
        <div className="mt-6">
          <div className="flex items-baseline justify-between text-label text-fg-muted">
            <span>Pages read</span>
            <span className="font-mono tabular">
              {pagesRead} of up to {BRIEFING_PAGE_LIMIT}
            </span>
          </div>
          <div className="mt-2 h-2 overflow-hidden rounded-full bg-surface-3" role="progressbar" aria-valuenow={pagesRead} aria-valuemin={0} aria-valuemax={BRIEFING_PAGE_LIMIT} aria-label="Pages read">
            <div className="h-full rounded-full bg-brand transition-[width] duration-500" style={{ width: `${Math.max(pct, 4)}%` }} />
          </div>
        </div>
        <ol className="mt-8 space-y-3 border-l-[1.5px] border-border pl-5">
          {b.steps.slice(-8).map((s, i, arr) => (
            <li key={`${s.ts}-${i}`} className={cx("wx-enter relative text-body", i === arr.length - 1 ? "text-fg" : "text-fg-muted")}>
              <span className={cx("absolute -left-[26px] top-1.5 size-2.5 rounded-full border-2 border-bg", i === arr.length - 1 ? "bg-brand" : "bg-border-strong")} />
              {s.message}
            </li>
          ))}
          {b.steps.length === 0 && <li className="text-body text-fg-muted">The agent will start in a moment.</li>}
        </ol>
        {b.credential_hint ? (
          <p className="mt-8 flex gap-2 text-label leading-relaxed text-fg-subtle">
            <Icon.Lock size={14} className="mt-0.5 shrink-0" />
            <span>
              After the public pages, the agent signs in as <span className="font-mono">{b.credential_hint}</span> and reads what
              members see. Signing in is the only form it submits; it never changes, buys or deletes anything.
            </span>
          </p>
        ) : (
          <p className="mt-8 text-label leading-relaxed text-fg-subtle">
            The agent only reads public pages. It doesn&apos;t fill in forms or buy anything, and it skips pages the site asks
            robots not to read.
          </p>
        )}
      </div>
    </div>
  );
}

// ------------------------------------------------------------------ report

const CONFIDENCE: Record<string, { label: string; tone: "success" | "brand" | "neutral" }> = {
  high: { label: "Clear signals", tone: "success" },
  medium: { label: "Likely", tone: "brand" },
  low: { label: "Best guess", tone: "neutral" },
};

function SiteLink({ origin, path, children }: { origin: string; path: string; children?: ReactNode }) {
  return (
    <a href={`${origin}${path}`} target="_blank" rel="noreferrer noopener" className="font-mono text-[12.5px] text-brand-text underline-offset-4 hover:underline">
      {children ?? path}
    </a>
  );
}

export function BriefingReport({ b }: { b: Briefing & { result: BriefingResult } }) {
  const r = b.result;
  const conf = CONFIDENCE[r.site_type.confidence] ?? CONFIDENCE.low;
  const org = r.organization;
  const hasContact = org.name || org.copyright || org.emails.length || org.phones.length || org.address || org.social.length;
  return (
    <div className="space-y-14">
      {/* In short */}
      <div className="card-ink grid overflow-hidden lg:grid-cols-[minmax(0,1.35fr)_minmax(0,1fr)]">
        <div className="p-7 sm:p-9">
          <p className="eyebrow">In short</p>
          <p className="mt-4 text-[1.25rem] leading-[1.55] tracking-[-0.01em] sm:text-[1.375rem]">{r.summary}</p>
          {r.headline && r.headline !== r.description && (
            <p className="mt-5 text-body text-fg-muted">
              Its home page headline: <span className="font-medium text-fg">“{r.headline}”</span>
            </p>
          )}
        </div>
        <div className="border-t-[1.5px] border-[var(--wx-ink-line)] bg-surface-2 p-7 sm:p-9 lg:border-l-[1.5px] lg:border-t-0">
          <p className="eyebrow">What kind of site</p>
          <div className="mt-4 flex flex-wrap items-center gap-3">
            <span className="text-[1.5rem] font-semibold tracking-[-0.02em]">{r.site_type.label}</span>
            <Badge tone={conf.tone}>{conf.label}</Badge>
          </div>
          <p className="mt-5 text-label font-semibold">Why we think so</p>
          <ul className="mt-2 space-y-2">
            {r.site_type.reasons.map((reason) => (
              <li key={reason} className="flex gap-2 text-body text-fg-muted">
                <Icon.Check size={15} className="mt-1 shrink-0 text-brand" /> <span>{reason.charAt(0).toUpperCase() + reason.slice(1)}</span>
              </li>
            ))}
          </ul>
          {r.other_types.length > 0 && (
            <p className="mt-5 text-label text-fg-subtle">Could also be: {r.other_types.map((t) => t.label.toLowerCase()).join(", ")}.</p>
          )}
        </div>
      </div>

      {r.sign_in && <SignInSection b={b} r={r} />}

      {/* The question */}
      {r.question && (
        <Section eyebrow="Your question" title={`“${r.question}”`}>
          {r.answer.length > 0 || (r.answer_pages?.length ?? 0) > 0 ? (
            <div className="space-y-3">
              {r.answer.map((a) => (
                <figure key={a.text} className="panel px-5 py-4">
                  <blockquote className="text-body leading-relaxed">“{a.text}”</blockquote>
                  <figcaption className="mt-2 text-label text-fg-subtle">
                    From <SiteLink origin={b.origin} path={a.page} />
                  </figcaption>
                </figure>
              ))}
              {(r.answer_pages?.length ?? 0) > 0 && (
                <p className="text-body text-fg-muted">
                  Pages that look relevant:{" "}
                  {r.answer_pages!.map((p, i) => (
                    <span key={p.page}>
                      {i > 0 && ", "}
                      <SiteLink origin={b.origin} path={p.page}>
                        {p.title || p.page}
                      </SiteLink>
                    </span>
                  ))}
                </p>
              )}
              <p className="text-label text-fg-subtle">These are quotes from the pages we read — not an interpretation. Check the source before relying on them.</p>
            </div>
          ) : (
            <Notice title="Nothing on the pages we read mentions this">
              We looked for {r.question.toLowerCase().replace(/[?.!]+$/, "")} across {r.stats.pages_read} pages and found no matching text. The answer may be
              on a page we didn&apos;t open, or behind a sign-in.
            </Notice>
          )}
        </Section>
      )}

      {/* What you can do there */}
      <Section eyebrow="What visitors can do" title="What the site lets you do" description="Each item is something we saw on the pages — click a page to check it yourself.">
        {r.capabilities.length ? (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {r.capabilities.map((c) => (
              <div key={c.key} className="panel p-5">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-[1.0625rem] font-semibold tracking-[-0.01em]">{c.label}</span>
                  {c.signed_in_only && (
                    <Badge tone="brand">
                      <Icon.Lock size={11} /> Members
                    </Badge>
                  )}
                </div>
                <div className="mt-1 text-label text-fg-muted">{c.detail}</div>
                <div className="mt-3 flex flex-wrap gap-x-3 gap-y-1">
                  {c.pages.slice(0, 3).map((p) => (
                    <SiteLink key={p} origin={b.origin} path={p} />
                  ))}
                </div>
              </div>
            ))}
          </div>
        ) : (
          <Notice>We didn&apos;t see buttons, forms or links that clearly let visitors do something (like buy, sign up or search).</Notice>
        )}
      </Section>

      <div className="grid gap-10 lg:grid-cols-2">
        {/* Sections */}
        <Section eyebrow="Main menu" title="Main sections">
          {r.sections.length ? (
            <div className="flex flex-wrap gap-2">
              {r.sections.map((s) => (
                <a
                  key={s.url}
                  href={s.url}
                  target="_blank"
                  rel="noreferrer noopener"
                  className="inline-flex items-center gap-1.5 rounded-full border border-border-strong bg-surface px-3.5 py-1.5 text-body transition-colors hover:border-fg"
                >
                  {s.label} <Icon.External size={12} className="text-fg-subtle" />
                </a>
              ))}
            </div>
          ) : (
            <p className="text-body text-fg-muted">The home page has no recognizable navigation menu.</p>
          )}
        </Section>

        {/* Who's behind it */}
        <Section eyebrow="Who's behind it" title="Owner & contact">
          {hasContact ? (
            <dl className="space-y-3 text-body">
              {(org.name || org.copyright) && <Row k="Run by">{org.name ?? org.copyright}</Row>}
              {org.emails.length > 0 && (
                <Row k="Email">
                  {org.emails.map((e) => (
                    <div key={e} className="font-mono text-[13px]">
                      {e}
                    </div>
                  ))}
                </Row>
              )}
              {org.phones.length > 0 && <Row k="Phone">{org.phones.join(", ")}</Row>}
              {org.address && <Row k="Address">{org.address}</Row>}
              {org.social.length > 0 && (
                <Row k="Social">
                  <div className="flex flex-wrap gap-x-3 gap-y-1">
                    {org.social.map((s) => (
                      <a key={s.url} href={s.url} target="_blank" rel="noreferrer noopener" className="text-brand-text underline-offset-4 hover:underline">
                        {s.network}
                      </a>
                    ))}
                  </div>
                </Row>
              )}
            </dl>
          ) : (
            <p className="text-body text-fg-muted">The pages we read don&apos;t name an owner or list contact details.</p>
          )}
        </Section>
      </div>

      {(r.prices.length > 0 || r.technology.length > 0 || r.languages.length > 0) && (
        <div className="grid gap-10 lg:grid-cols-2">
          {r.prices.length > 0 && (
            <Section eyebrow="Prices seen" title="Prices on the site" description="Exactly as written on the pages — no currency conversion.">
              <div className="flex flex-wrap gap-2">
                {r.prices.map((p) => (
                  <span key={`${p.text}-${p.page}`} className="rounded-full bg-surface-2 px-3 py-1 font-mono text-[13px]" title={`Seen on ${p.page}`}>
                    {p.text}
                  </span>
                ))}
              </div>
            </Section>
          )}
          {(r.technology.length > 0 || r.languages.length > 0) && (
            <Section eyebrow="Under the hood" title="How it's built">
              <dl className="space-y-3 text-body">
                {r.technology.map((t) => (
                  <Row key={t.name} k={t.name}>
                    <span className="text-fg-muted">{t.evidence.charAt(0).toUpperCase() + t.evidence.slice(1)}</span>
                  </Row>
                ))}
                {r.languages.length > 0 && <Row k="Language">{r.languages.map((l) => l.toUpperCase()).join(", ")}</Row>}
              </dl>
            </Section>
          )}
        </div>
      )}

      {/* Pages read */}
      <Section
        eyebrow="Evidence"
        title={r.pages.length === 1 ? "The page we read" : `The ${r.pages.length} pages we read`}
        description={
          r.sign_in?.pages.length
            ? "Screenshots taken by the agent's browser (password fields are blacked out). Pages with a lock were read while signed in."
            : "Screenshots taken by the agent's browser. Every statement above comes from these pages."
        }
      >
        <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
          {r.pages.map((p, i) => {
            const shot = b.shots.find((s) => s.page_url === p.url && s.signed_in === !!p.signed_in) ?? b.shots.find((s) => s.page_url === p.url) ?? b.shots[i];
            return (
              <a key={`${p.url}-${p.signed_in ? "in" : "out"}`} href={p.url} target="_blank" rel="noreferrer noopener" className="group block min-w-0">
                <div className="relative aspect-[16/10] overflow-hidden rounded-xl border border-border-strong bg-surface-2 transition-[border-color,box-shadow] group-hover:border-fg group-hover:shadow-[3px_3px_0_var(--wx-ink-shadow)]">
                  {shot ? (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img src={shot.url} alt={`Screenshot of ${p.path}`} loading="lazy" className="absolute inset-0 size-full object-cover object-top" />
                  ) : (
                    <span className="absolute inset-0 flex items-center justify-center text-label text-fg-subtle">No screenshot</span>
                  )}
                </div>
                <div className="mt-2.5 flex min-w-0 items-center gap-2">
                  <span className="truncate text-body font-medium">{p.title || p.path}</span>
                  {p.signed_in && <Icon.Lock size={12} className="shrink-0 text-brand-text" aria-label="Read while signed in" />}
                </div>
                <div className="truncate font-mono text-[12px] text-fg-subtle">
                  {p.path}
                  {p.status && p.status >= 400 ? ` · error ${p.status}` : ""}
                </div>
              </a>
            );
          })}
        </div>
      </Section>

      {(r.notes.length > 0 || r.skipped.length > 0) && (
        <Section eyebrow="Good to know" title="Limits of this briefing">
          <ul className="space-y-2.5">
            {r.notes.map((n) => (
              <li key={n} className="flex gap-2.5 text-body text-fg-muted">
                <Icon.SevInfo className="mt-1 shrink-0 text-fg-subtle" /> {n}
              </li>
            ))}
            {r.skipped.length > 0 && (
              <li className="flex gap-2.5 text-body text-fg-muted">
                <Icon.SevInfo className="mt-1 shrink-0 text-fg-subtle" />
                <span>
                  {r.skipped.length} link{r.skipped.length === 1 ? " was" : "s were"} not opened:{" "}
                  {r.skipped
                    .slice(0, 4)
                    .map((s) => `${new URL(s.url).pathname} (${s.reason})`)
                    .join("; ")}
                  {r.skipped.length > 4 ? "…" : "."}
                </span>
              </li>
            )}
          </ul>
        </Section>
      )}

      <details className="group panel">
        <summary className="flex cursor-pointer list-none items-center justify-between gap-3 px-5 py-4 text-body font-semibold [&::-webkit-details-marker]:hidden">
          What the agent did, step by step
          <Icon.ChevronDown className="text-fg-subtle transition-transform group-open:rotate-180" />
        </summary>
        <ol className="space-y-2 border-t border-border px-5 py-4">
          {b.steps.map((s, i) => (
            <li key={`${s.ts}-${i}`} className="grid grid-cols-[3.5rem_1fr] gap-3 text-body text-fg-muted">
              <span className="font-mono text-[12px] text-fg-subtle tabular">{new Date(s.ts).toLocaleTimeString(undefined, { minute: "2-digit", second: "2-digit" })}</span>
              {s.message}
            </li>
          ))}
        </ol>
      </details>

      <p className="font-mono text-[12px] leading-relaxed text-fg-subtle">
        {(() => {
          const member = r.pages.filter((p) => p.signed_in).length;
          const pub = r.pages.length - member;
          const plural = (n: number, w: string) => `${n} ${w}${n === 1 ? "" : "s"}`;
          return member
            ? `Written from ${plural(pub, "public page")} and ${plural(member, "members-only page")} in ${formatMs(r.stats.duration_ms)}. Apart from signing in, nothing was clicked, typed or submitted, and no outside sources were used.`
            : `Written from what we saw on ${plural(pub, "public page")} in ${formatMs(r.stats.duration_ms)}. Nothing was clicked, typed or submitted, and no outside sources were used.`;
        })()}
      </p>
    </div>
  );
}

const SIGN_IN_TITLE: Record<string, string> = {
  authenticated: "Signed in",
  failed: "Couldn't sign in",
  blocked_captcha: "Stopped at a bot check",
  mfa_required: "Two-factor code needed",
  verification_required: "Account needs verifying",
  no_login_form: "No sign-in page found",
};

function SignInSection({ b, r }: { b: Briefing; r: BriefingResult }) {
  const s = r.sign_in!;
  const ok = s.status === "authenticated";
  const memberPages = r.pages.filter((p) => p.signed_in && s.pages.includes(p.path));
  return (
    <Section eyebrow="Members area" title={ok ? `What members see${s.as ? ` (signed in as ${s.as})` : ""}` : SIGN_IN_TITLE[s.status] ?? "Sign-in"}>
      {ok ? (
        memberPages.length ? (
          <div className="grid gap-3 sm:grid-cols-2">
            {memberPages.map((p) => (
              <a key={p.path} href={p.url} target="_blank" rel="noreferrer noopener" className="panel group flex items-start gap-3 p-4 transition-colors hover:border-fg">
                <Icon.Lock size={15} className="mt-1 shrink-0 text-brand-text" />
                <span className="min-w-0">
                  <span className="block truncate text-body font-semibold">{p.title || p.path}</span>
                  <span className="block truncate font-mono text-[12px] text-fg-subtle">{p.path}</span>
                  {p.description && p.description !== r.description && <span className="mt-1 block text-label text-fg-muted">{p.description}</span>}
                </span>
              </a>
            ))}
          </div>
        ) : (
          <Notice tone="neutral">Signing in worked, but it didn&apos;t reveal any pages beyond the public ones.</Notice>
        )
      ) : (
        <Notice tone="warn" title={SIGN_IN_TITLE[s.status] ?? "Sign-in didn't work"}>
          {s.detail ?? b.auth_detail ?? "No details were recorded."} The rest of this briefing covers the public pages only.
        </Notice>
      )}
    </Section>
  );
}

function Row({ k, children }: { k: string; children: ReactNode }) {
  return (
    <div className="grid grid-cols-[6.5rem_1fr] gap-4">
      <dt className="text-label text-fg-subtle">{k}</dt>
      <dd className="min-w-0 break-words">{children}</dd>
    </div>
  );
}

export function BriefingProblem({ b }: { b: Briefing }) {
  return (
    <Panel ink className="max-w-2xl">
      <p className="eyebrow">{b.status === "blocked" ? "We stopped" : "Something went wrong"}</p>
      <h2 className="mt-3 text-[1.5rem] font-semibold tracking-[-0.02em]">
        {b.status === "blocked" ? "We couldn't read this website" : "The briefing didn't finish"}
      </h2>
      <p className="mt-3 text-body leading-relaxed text-fg-muted">{b.error ?? "No details were recorded."}</p>
      <div className="mt-6 flex flex-wrap gap-2">
        <ButtonLink href={`/briefings/new?url=${encodeURIComponent(b.origin)}`} variant="primary" icon={<Icon.Refresh />}>
          Try again
        </ButtonLink>
        <ButtonLink href="/briefings/new" variant="paper">
          Try a different site
        </ButtonLink>
      </div>
    </Panel>
  );
}

export function BriefingSpinner() {
  return (
    <span className="inline-flex items-center gap-2 text-label text-fg-muted">
      <Spinner /> Loading
    </span>
  );
}
