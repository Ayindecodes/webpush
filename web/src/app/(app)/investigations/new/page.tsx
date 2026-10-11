"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useMemo, useState, type FormEvent, type ReactNode } from "react";

import { parseWebsite } from "@/components/briefing";
import { useCrumbs } from "@/components/shell/context";
import { CredentialForm, TargetRow } from "@/components/targets";
import { Icon } from "@/components/ui/icons";
import { Button, Checkbox, Field, Input, LoadingRows, Notice, PageHeader, Select, StepTile, Textarea, cx } from "@/components/ui/primitives";
import { api } from "@/lib/api";
import { hostOf } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import type { Credential, Environment, Investigation, Project, ViewportName } from "@/lib/types";

const SCREENS: { name: ViewportName; label: string; icon: ReactNode }[] = [
  { name: "desktop", label: "Computer", icon: <Icon.Desktop size={18} /> },
  { name: "tablet", label: "Tablet", icon: <Icon.Tablet size={18} /> },
  { name: "mobile", label: "Phone", icon: <Icon.Mobile size={18} /> },
];
const DEFAULT_PROJECT = "My websites";

function splitPaths(s: string): string[] {
  return s
    .split(/[\n,]/)
    .map((x) => x.trim())
    .filter(Boolean);
}

function clamp(n: number, lo: number, hi: number): number {
  return Number.isFinite(n) ? Math.min(hi, Math.max(lo, Math.round(n))) : lo;
}

export default function NewInvestigationPage() {
  return (
    <Suspense fallback={<LoadingRows />}>
      <NewInvestigation />
    </Suspense>
  );
}

/**
 * Finds the website (environment) the user means, in any project, or adds it to a default project.
 * When they didn't type http:// or https://, any scheme and the www/bare-domain twin count as a match
 * (preferring one that's already confirmed), so "shop.com" finds an existing "https://www.shop.com".
 */
async function findOrAddWebsite(origin: string, typedScheme: boolean): Promise<Environment> {
  const want = new URL(origin);
  const bare = (h: string) => h.replace(/^www\./, "");
  const projects = await api.get<Project[]>("/api/projects");
  const loose: Environment[] = [];
  for (const p of projects) {
    const envs = await api.get<Environment[]>(`/api/projects/${p.id}/environments`);
    const exact = envs.find((e) => e.origin === origin);
    if (exact) return exact;
    if (!typedScheme) {
      loose.push(...envs.filter((e) => {
        const u = new URL(e.origin);
        return bare(u.hostname) === bare(want.hostname) && (u.port || "") === (want.port || "");
      }));
    }
  }
  const best = loose.find((e) => e.verification_status === "verified") ?? loose[0];
  if (best) return best;
  const project = projects.find((p) => p.name === DEFAULT_PROJECT) ?? projects[0] ?? (await api.post<Project>("/api/projects", { name: DEFAULT_PROJECT }));
  return api.post<Environment>(`/api/projects/${project.id}/environments`, { origin, label: "" });
}

function NewInvestigation() {
  useCrumbs([{ label: "Investigations", href: "/investigations" }, { label: "New investigation" }]);
  const params = useSearchParams();
  const [envId, setEnvId] = useState<string | null>(params.get("environment"));
  const urlParam = params.get("url") ?? "";

  const env = useApi<Environment>(envId ? `/api/environments/${envId}` : null);
  const site = env.data;
  const verified = site?.verification_status === "verified";
  const step = !site ? 1 : !verified ? 2 : 3;

  return (
    <div className="mx-auto max-w-3xl">
      <PageHeader
        eyebrow="New investigation"
        title="Check your website for problems."
        description="Three quick steps. We'll try your site like a real visitor would — on a computer and a phone — and show you anything that's broken, with proof."
      />
      <ol className="mb-8 flex flex-wrap items-center gap-x-3 gap-y-2 text-body" aria-label="Steps">
        {["Your website", "Prove it's yours", "Start"].map((label, i) => (
          <li key={label} className="flex items-center gap-3">
            {i > 0 && <span className="h-px w-6 bg-border-strong" aria-hidden />}
            <StepTile active={step === i + 1} done={step > i + 1}>
              {String(i + 1).padStart(2, "0")}
            </StepTile>
            <span className={cx(step === i + 1 ? "font-semibold" : "text-fg-muted")} aria-current={step === i + 1 ? "step" : undefined}>
              {label}
            </span>
          </li>
        ))}
      </ol>

      {envId && env.error ? (
        <Notice tone="danger" title="We couldn't load that website" action={<Button onClick={() => setEnvId(null)}>Start over</Button>}>
          {env.error.message}
        </Notice>
      ) : envId && !site ? (
        <LoadingRows rows={2} />
      ) : step === 1 ? (
        <WebsiteStep initial={urlParam} onReady={(e) => setEnvId(e.id)} />
      ) : step === 2 && site ? (
        <section className="card-ink p-6 sm:p-8">
          <h2 className="text-[1.375rem] font-semibold tracking-[-0.02em]">Prove that {hostOf(site.origin)} is yours</h2>
          <p className="mt-2 text-body leading-relaxed text-fg-muted">
            We only test websites their owners have approved. You do this once per website.
          </p>
          <ul className="panel mt-6 overflow-hidden">
            <TargetRow env={site} onChange={() => env.mutate()} />
          </ul>
          <button type="button" className="mt-5 text-label text-fg-muted underline-offset-4 hover:text-fg hover:underline" onClick={() => setEnvId(null)}>
            Use a different website
          </button>
        </section>
      ) : site ? (
        <StartStep env={site} onChangeSite={() => setEnvId(null)} />
      ) : null}
    </div>
  );
}

function WebsiteStep({ initial, onReady }: { initial: string; onReady: (e: Environment) => void }) {
  const [url, setUrl] = useState(initial);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  async function submit(e: FormEvent) {
    e.preventDefault();
    const parsed = parseWebsite(url);
    if ("error" in parsed) {
      setError(parsed.error);
      return;
    }
    setBusy(true);
    setError(null);
    try {
      onReady(await findOrAddWebsite(new URL(parsed.url).origin, url.includes("://")));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Couldn't add that website.");
      setBusy(false);
    }
  }
  return (
    <section className="card-ink p-6 sm:p-8">
      <h2 className="text-[1.375rem] font-semibold tracking-[-0.02em]">What&apos;s the address of your website?</h2>
      <p className="mt-2 text-body leading-relaxed text-fg-muted">A test or staging copy is best, but your live site works too.</p>
      <form onSubmit={submit} noValidate className="mt-6">
        <label htmlFor="site-url" className="sr-only">
          Website address
        </label>
        <div className="flex items-center gap-2 rounded-full border-[1.5px] border-[var(--wx-ink-line)] bg-surface p-1.5 pl-5 focus-within:shadow-[0_0_0_4px_var(--wx-brand-soft)]">
          <Icon.Globe className="shrink-0 text-fg-subtle" />
          <input
            id="site-url"
            value={url}
            onChange={(e) => {
              setUrl(e.target.value);
              setError(null);
            }}
            placeholder="www.your-site.com"
            inputMode="url"
            autoComplete="url"
            spellCheck={false}
            autoFocus
            aria-invalid={!!error}
            aria-describedby={error ? "site-url-error" : undefined}
            className="h-11 min-w-0 flex-1 bg-transparent text-[15px] outline-none placeholder:text-fg-subtle"
          />
          <Button type="submit" variant="primary" loading={busy} icon={busy ? undefined : <Icon.ArrowRight size={14} />} trailingIcon className="h-11 px-5">
            Continue
          </Button>
        </div>
        {error && (
          <p id="site-url-error" role="alert" className="mt-2 pl-5 text-label font-medium text-danger">
            {error}
          </p>
        )}
      </form>
    </section>
  );
}

function StartStep({ env, onChangeSite }: { env: Environment; onChangeSite: () => void }) {
  const router = useRouter();
  const creds = useApi<Credential[]>(`/api/projects/${env.project_id}/credentials`);
  const [showOptions, setShowOptions] = useState(false);
  const [signIn, setSignIn] = useState(false);
  const usable = useMemo(
    () => (creds.data ?? []).filter((c) => c.environment_id === env.id && c.lifecycle_state !== "registration_failed"),
    [creds.data, env.id],
  );
  const [credentialId, setCredentialId] = useState("");
  const chosenCredential = usable.some((c) => c.id === credentialId) ? credentialId : (usable[0]?.id ?? "");
  const [screens, setScreens] = useState<ViewportName[]>(["desktop", "mobile"]);
  const [allowRegistration, setAllowRegistration] = useState(false);
  const [allowOrders, setAllowOrders] = useState(false);
  const [startPath, setStartPath] = useState("/");
  const [exclude, setExclude] = useState("");
  const [maxPages, setMaxPages] = useState(25);
  const [maxMinutes, setMaxMinutes] = useState(15);
  const [goal, setGoal] = useState("");
  const [authorized, setAuthorized] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const site = hostOf(env.origin);
  const screenWords = screens.map((s) => SCREENS.find((x) => x.name === s)!.label.toLowerCase()).join(" and ");
  const blockers: string[] = [];
  if (signIn && !chosenCredential) blockers.push("Add the test account it should sign in with.");
  if (screens.length === 0) blockers.push("Pick at least one screen.");
  if (!startPath.startsWith("/")) blockers.push("The starting page must begin with “/”.");
  if (!authorized) blockers.push("Tick the box to confirm you're allowed to test this website.");

  async function start() {
    if (blockers.length) return;
    setBusy(true);
    setError(null);
    try {
      const inv = await api.post<Investigation>(`/api/projects/${env.project_id}/investigations`, {
        environment_id: env.id,
        mode: signIn ? "authenticated" : "autonomous",
        goal,
        credential_id: signIn ? chosenCredential : null,
        confirm_authorized: authorized,
        approve_registration: !signIn && allowRegistration,
        approve_order_submission: allowOrders,
        config: {
          viewports: screens,
          max_pages: clamp(maxPages, 1, 200),
          max_depth: 3,
          max_duration_s: clamp(maxMinutes, 1, 60) * 60,
          repeat_failed_runs: 1,
          start_path: startPath || "/",
          include_paths: [],
          exclude_paths: splitPaths(exclude),
          allow_registration: !signIn && allowRegistration,
          allow_order_submission: allowOrders,
        },
      });
      router.push(`/investigations/${inv.id}`);
    } catch (err) {
      setError((err as Error).message);
      setBusy(false);
    }
  }

  return (
    <section className="card-ink p-6 sm:p-8">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="flex items-center gap-2 text-body text-success">
            <Icon.Check size={15} /> {site} is confirmed as yours
          </p>
          <h2 className="mt-2 text-[1.375rem] font-semibold tracking-[-0.02em]">Ready when you are</h2>
        </div>
        <button type="button" className="text-label text-fg-muted underline-offset-4 hover:text-fg hover:underline" onClick={onChangeSite}>
          Different website
        </button>
      </div>

      <div className="mt-6 rounded-2xl bg-surface-2 p-5">
        <p className="text-label font-semibold text-fg-subtle">What it will do</p>
        <ul className="mt-3 space-y-2.5 text-body">
          <Plan>
            Visit {site} on a {screenWords || "—"} and look around up to {maxPages} pages{startPath !== "/" ? `, starting at ${startPath}` : ""}.
          </Plan>
          <Plan>
            {signIn ? "Sign in with your test account and look at the members' pages." : allowRegistration ? "Create one test account if there's a sign-up form." : "Browse as a visitor — it won't sign up or sign in."}
          </Plan>
          <Plan>Try buying something, but {allowOrders ? "place a test order (test payments only)" : "stop before the order is placed"}.</Plan>
          <Plan>Repeat anything that fails, find out why, and prove it with an automated test.</Plan>
        </ul>
        <p className="mt-4 text-label text-fg-subtle">
          It never clicks “log out”, “delete” or similar, never types card details, and stops to ask you about CAPTCHAs or email codes.
        </p>
      </div>

      <button
        type="button"
        onClick={() => setShowOptions(!showOptions)}
        aria-expanded={showOptions}
        className="mt-5 inline-flex items-center gap-1.5 text-body font-medium underline-offset-4 hover:underline"
      >
        <Icon.Settings size={15} /> {showOptions ? "Hide options" : "Change options"}
        <Icon.ChevronDown size={14} className={cx("transition-transform", showOptions && "rotate-180")} />
      </button>

      {showOptions && (
        <div className="wx-enter mt-5 space-y-8 border-t border-border pt-6">
          <Option title="Screens">
            <div className="grid gap-3 sm:grid-cols-3">
              {SCREENS.map((v) => {
                const on = screens.includes(v.name);
                return (
                  <button
                    key={v.name}
                    type="button"
                    aria-pressed={on}
                    onClick={() => setScreens(on ? screens.filter((x) => x !== v.name) : [...screens, v.name])}
                    className={cx(
                      "flex items-center gap-3 rounded-2xl border-[1.5px] px-4 py-3 text-left transition-colors",
                      on ? "border-[var(--wx-ink-line)] bg-surface" : "border-border hover:border-border-strong",
                    )}
                  >
                    {v.icon}
                    <span className="flex-1 text-body font-medium">{v.label}</span>
                    <span className={cx("flex size-5 items-center justify-center rounded-full border", on ? "border-fg bg-fg text-bg" : "border-border-strong")}>
                      {on && <Icon.Check size={12} />}
                    </span>
                  </button>
                );
              })}
            </div>
          </Option>

          <Option title="Signing in">
            <div className="space-y-4">
              <Checkbox
                checked={signIn}
                onChange={setSignIn}
                label="Sign in with a test account"
                description="Use this to check pages only members can see."
              />
              {signIn && (
                <div className="space-y-4 pl-7">
                  {usable.length > 0 && (
                    <Field label="Which account" htmlFor="cred">
                      <Select id="cred" value={chosenCredential} onChange={(e) => setCredentialId(e.target.value)}>
                        {usable.map((c) => (
                          <option key={c.id} value={c.id}>
                            {c.label} — {c.username_hint}
                          </option>
                        ))}
                      </Select>
                    </Field>
                  )}
                  <details className="group panel" open={usable.length === 0}>
                    <summary className="flex cursor-pointer list-none items-center justify-between px-5 py-3.5 text-body font-semibold [&::-webkit-details-marker]:hidden">
                      Add a test account
                      <Icon.ChevronDown className="text-fg-subtle transition-transform group-open:rotate-180" />
                    </summary>
                    <div className="border-t border-border px-5 py-5">
                      <CredentialForm
                        projectId={env.project_id}
                        environments={[env]}
                        onCreated={async (c) => {
                          await creds.mutate();
                          setCredentialId(c.id);
                        }}
                      />
                    </div>
                  </details>
                </div>
              )}
              <Checkbox
                checked={!signIn && allowRegistration}
                disabled={signIn}
                onChange={setAllowRegistration}
                label="Let it create one test account"
                description="It signs up once. If the site asks for an email code or a CAPTCHA, it pauses and asks you."
              />
            </div>
          </Option>

          <Option title="Orders">
            <Checkbox
              checked={allowOrders}
              onChange={setAllowOrders}
              label="Place test orders — this site uses test payments"
              description="Leave this off for real shops. It will still check that the order button works."
            />
          </Option>

          <Option title="Limits">
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Start on page" htmlFor="start">
                <Input id="start" value={startPath} onChange={(e) => setStartPath(e.target.value)} className="font-mono text-[14px]" spellCheck={false} />
              </Field>
              <Field label="Never visit" htmlFor="exc" optional hint="One per line, like /admin">
                <Textarea id="exc" rows={1} value={exclude} onChange={(e) => setExclude(e.target.value)} className="min-h-11 font-mono text-[13px]" />
              </Field>
              <Field label="Most pages to look at" htmlFor="mp">
                <Input id="mp" type="number" min={1} max={200} value={maxPages} onChange={(e) => setMaxPages(Number(e.target.value))} />
              </Field>
              <Field label="Time limit (minutes)" htmlFor="mm">
                <Input id="mm" type="number" min={1} max={60} value={maxMinutes} onChange={(e) => setMaxMinutes(Number(e.target.value))} />
              </Field>
              <div className="sm:col-span-2">
                <Field label="Note for the report" htmlFor="goal" optional>
                  <Input id="goal" value={goal} onChange={(e) => setGoal(e.target.value)} maxLength={2000} placeholder="e.g. Before the summer sale" />
                </Field>
              </div>
            </div>
          </Option>
        </div>
      )}

      <div className="mt-8 border-t border-border pt-6">
        <Checkbox
          checked={authorized}
          onChange={setAuthorized}
          label={`I own ${site}, or I'm allowed to test it`}
          description="We save this with your name and the time."
        />
        {blockers.length > 0 && (authorized || blockers.length > 1) && (
          <ul className="mt-4 space-y-1 text-label text-fg-muted" aria-live="polite">
            {blockers.map((b) => (
              <li key={b}>· {b}</li>
            ))}
          </ul>
        )}
        {error && (
          <div className="mt-4">
            <Notice tone="danger">{error}</Notice>
          </div>
        )}
        <Button variant="primary" size="lg" className="mt-6 w-full sm:w-auto" disabled={blockers.length > 0} loading={busy} onClick={start} icon={<Icon.Play />}>
          Start the investigation
        </Button>
      </div>
    </section>
  );
}

function Plan({ children }: { children: ReactNode }) {
  return (
    <li className="flex gap-2.5">
      <Icon.Check size={15} className="mt-1 shrink-0 text-brand-text" />
      <span>{children}</span>
    </li>
  );
}

function Option({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div>
      <h3 className="mb-3 text-label font-semibold uppercase tracking-[0.12em] text-fg-subtle">{title}</h3>
      {children}
    </div>
  );
}
