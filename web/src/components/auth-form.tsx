"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState, type FormEvent } from "react";

import { Logo } from "@/components/brand/logo";
import { HeroGlobe } from "@/components/marketing/hero-globe";
import { Icon } from "@/components/ui/icons";
import { Button, Field, Input, Notice } from "@/components/ui/primitives";
import { api } from "@/lib/api";
import { useSession } from "@/lib/hooks";
import { loginHref, registerHref, safeNext as toSafeNext } from "@/lib/routes";

const PLAN_NAMES: Record<string, string> = { scout: "Scout", investigator: "Investigator" };

const POINTS = [
  "Real Chromium sessions against targets you verify",
  "Evidence for every finding: screenshots, geometry, logs",
  "Playwright tests that WEB X-RAY actually runs",
];

export function AuthForm({ mode }: { mode: "login" | "register" }) {
  const router = useRouter();
  const params = useSearchParams();
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const next = params.get("next");
  const safeNext = toSafeNext(next);
  const plan = PLAN_NAMES[params.get("plan") ?? ""];
  const signedIn = useSession();

  // Already signed in (valid session): skip the form and go where they were headed.
  useEffect(() => {
    if (signedIn) router.replace(safeNext);
  }, [signedIn, router, safeNext]);

  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = new FormData(e.currentTarget);
    setBusy(true);
    setError(null);
    try {
      if (mode === "login") {
        await api.post("/api/auth/login", { email: form.get("email"), password: form.get("password") });
      } else {
        await api.post("/api/auth/register", {
          email: form.get("email"),
          password: form.get("password"),
          display_name: form.get("name"),
          organization_name: form.get("organization"),
        });
      }
      router.replace(safeNext);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Request failed");
      setBusy(false);
    }
  }

  return (
    <div data-surface="paper" className="grid min-h-screen lg:grid-cols-[1fr_minmax(0,560px)]">
      <aside className="relative hidden overflow-hidden border-r border-border bg-surface lg:flex lg:flex-col lg:justify-between lg:p-12">
        <div className="halftone halftone-hero" aria-hidden />
        <Link href="/" className="relative" aria-label="WEB X-RAY home">
          <Logo height={14} />
        </Link>
        <div className="relative grid grid-cols-[1fr_0.9fr] items-center gap-8">
          <div>
            <h2 className="text-[2.25rem] font-semibold leading-[1.05] tracking-[-0.035em]">
              Give it a URL.
              <br />
              It finds what&apos;s broken.
            </h2>
            <ul className="mt-6 space-y-3">
              {POINTS.map((p) => (
                <li key={p} className="flex items-start gap-2.5 text-body text-fg-muted">
                  <Icon.Check className="mt-0.5 shrink-0 text-brand" /> {p}
                </li>
              ))}
            </ul>
          </div>
          <HeroGlobe idPrefix="auth-globe" />
        </div>
        <p className="relative text-meta text-fg-subtle">Only investigate websites you are authorized to test.</p>
      </aside>

      <div className="flex items-center justify-center px-5 py-12 sm:px-10">
        <div className="w-full max-w-[380px]">
          <Link href="/" className="mb-10 inline-flex lg:hidden" aria-label="WEB X-RAY home">
            <Logo height={13} />
          </Link>
          <h1 className="text-title font-semibold">{mode === "login" ? "Sign in to WEB X-RAY" : "Create your workspace"}</h1>
          <p className="mt-1.5 text-body text-fg-muted">
            {mode === "login"
              ? "Welcome back. Pick up where your investigations left off."
              : "Your account gets a private organization. Projects, targets and evidence are visible only to its members."}
          </p>
          {mode === "register" && plan && (
            <div className="mt-5">
              <Notice tone="brand" title={`You picked ${plan}`}>
                Billing isn&apos;t switched on yet, so you&apos;ll start with every feature at no cost. We&apos;ll ask before anything is charged.
              </Notice>
            </div>
          )}
          <form onSubmit={submit} className="mt-8 flex flex-col gap-4">
            {mode === "register" && (
              <div className="grid gap-4 sm:grid-cols-2">
                <Field label="Your name" htmlFor="name">
                  <Input id="name" name="name" autoComplete="name" required maxLength={120} />
                </Field>
                <Field label="Organization" htmlFor="organization" optional>
                  <Input id="organization" name="organization" autoComplete="organization" maxLength={120} />
                </Field>
              </div>
            )}
            <Field label="Work email" htmlFor="email">
              <Input id="email" name="email" type="email" autoComplete="email" required placeholder="you@company.com" />
            </Field>
            <Field label="Password" htmlFor="password" hint={mode === "register" ? "At least 10 characters." : undefined}>
              <Input
                id="password"
                name="password"
                type="password"
                autoComplete={mode === "login" ? "current-password" : "new-password"}
                minLength={mode === "register" ? 10 : undefined}
                required
              />
            </Field>
            {error && <Notice tone="danger">{error}</Notice>}
            <Button type="submit" variant="ink" size="lg" loading={busy} className="mt-1 h-11 w-full">
              {mode === "login" ? "Sign in" : "Create account"}
            </Button>
          </form>
          <p className="mt-6 text-label text-fg-subtle">
            {mode === "login" ? (
              <>
                New to WEB X-RAY?{" "}
                <Link className="font-medium text-brand-text hover:underline" href={registerHref(next, params.get("plan"))}>
                  Create an account
                </Link>
              </>
            ) : (
              <>
                Already have an account?{" "}
                <Link className="font-medium text-brand-text hover:underline" href={loginHref(next)}>
                  Sign in
                </Link>
              </>
            )}
          </p>
        </div>
      </div>
    </div>
  );
}
