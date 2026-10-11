import type { Metadata } from "next";
import Image from "next/image";
import Link from "next/link";
import type { ReactNode } from "react";

import { HeroGlobe } from "@/components/marketing/hero-globe";
import { UrlLauncher } from "@/components/marketing/url-launcher";
import { Icon } from "@/components/ui/icons";
import { ButtonLink } from "@/components/ui/primitives";

export const metadata: Metadata = {
  title: { absolute: "WEB X-RAY — Send an agent to any website" },
};

const STEPS: { n: string; tag: string; title: string; body: string; icon: ReactNode }[] = [
  {
    n: "01",
    tag: "Verify",
    title: "Prove the site is yours",
    body: "Add your origin and publish a token as a DNS TXT record or a well-known file. Nothing is scanned before that.",
    icon: <Icon.Shield size={22} />,
  },
  {
    n: "02",
    tag: "Scope",
    title: "Say what's allowed",
    body: "Choose viewports, page budgets and paths to skip. Creating a test account or placing sandbox orders needs your explicit yes.",
    icon: <Icon.Target size={22} />,
  },
  {
    n: "03",
    tag: "Investigate",
    title: "It browses like a user",
    body: "An isolated Chromium explores your pages, signs up, and runs checkout on desktop and mobile — repeating anything that fails.",
    icon: <Icon.Globe size={22} />,
  },
  {
    n: "04",
    tag: "Prove",
    title: "You get evidence and a test",
    body: "Each defect arrives with screenshots, geometry, logs, ranked causes and a Playwright test that WEB X-RAY has already run.",
    icon: <Icon.Flask size={22} />,
  },
];

const BOX: [string, string][] = [
  ["Exploration", "Crawls pages, forms and controls inside your origin. Never follows logout or delete-style links."],
  ["Journeys", "Sign-up, login, onboarding and checkout today — verified by the state that follows, not by the click."],
  ["Responsive runs", "Desktop 1440, tablet 768 and mobile 390, compared step by step."],
  ["Evidence", "Masked screenshots, hit tests, computed styles, sanitized DOM, network and console logs — each hashed."],
  ["Root causes", "Overlays, disabled controls, JS errors and failed requests — supported or ruled out by evidence."],
  ["Playwright tests", "Generated from the exact locators used, executed for you, and yours to keep."],
];

const PLANS = [
  {
    name: "Free",
    price: "$0",
    cadence: "forever",
    blurb: "Try it on one site and see what it finds.",
    cta: { label: "Start free", href: "/register" },
    features: ["1 project · 1 verified site", "3 investigations a month", "Desktop & mobile runs", "Findings with full evidence", "Generated Playwright tests"],
  },
  {
    name: "Scout",
    price: "$3",
    cadence: "per month",
    blurb: "For a developer keeping an eye on a few sites.",
    cta: { label: "Choose Scout", href: "/register?plan=scout" },
    features: ["5 projects · 5 verified sites", "30 investigations a month", "Desktop, tablet & mobile", "Re-run tests on demand", "Markdown report export"],
    featured: true,
  },
  {
    name: "Investigator",
    price: "$5",
    cadence: "per month",
    blurb: "For teams testing behind the login.",
    cta: { label: "Choose Investigator", href: "/register?plan=investigator" },
    features: ["Unlimited projects", "100 investigations a month", "Stored test accounts (encrypted)", "Sandbox checkout journeys", "Everything in Scout"],
  },
];

export default function LandingPage() {
  return (
    <>
      {/* ------------------------------------------------------------ hero */}
      <section className="relative overflow-hidden">
        <div className="halftone halftone-hero" aria-hidden />
        <div className="relative mx-auto grid max-w-[1180px] items-center gap-12 px-5 pb-20 pt-14 sm:px-8 lg:grid-cols-[1.25fr_0.9fr] lg:pb-28 lg:pt-20">
          <div>
            <p className="eyebrow">An agent for any website · Start free</p>
            <h1 className="mt-6 text-[clamp(2.6rem,5.2vw,4.1rem)] font-semibold leading-[1] tracking-[-0.045em]">
              Give it a URL.
              <br />
              It does the looking.
            </h1>
            <p className="mt-7 max-w-[34rem] text-[1.0625rem] leading-relaxed text-fg-muted">
              Ask about any website and an agent reads it for you, then explains what it is and what it&apos;s for. Point it at your
              own site and it signs up, checks out and tries everything on a computer and a phone — then shows you what&apos;s broken,
              with proof.
            </p>
            <UrlLauncher className="mt-9 max-w-[33rem]" />
            <div className="mt-5 flex flex-wrap items-center gap-x-5 gap-y-3">
              <ButtonLink href="/register" variant="ink" icon={<Icon.ArrowRight size={14} />} className="h-10 flex-row-reverse px-5">
                Start free
              </ButtonLink>
              <Link href="#how-it-works" className="text-body font-medium text-fg-muted underline-offset-4 hover:text-fg hover:underline">
                How it works
              </Link>
            </div>
            <p className="mt-6 font-mono text-[12px] leading-relaxed text-fg-subtle">
              Real browser · plain-language answers · proof for every problem
            </p>
          </div>
          <div className="relative mx-auto w-full max-w-[330px] sm:max-w-[420px] lg:mr-0 lg:max-w-[450px]">
            <HeroGlobe />
          </div>
        </div>
      </section>

      {/* ------------------------------------------------------------ evidence ribbon */}
      <section className="border-y border-border bg-surface">
        <div className="mx-auto flex max-w-[1180px] flex-wrap items-center justify-between gap-x-8 gap-y-3 px-5 py-6 sm:px-8">
          <span className="eyebrow">Recorded for every finding</span>
          <ul className="flex flex-wrap gap-x-7 gap-y-2 text-body text-fg-muted">
            {["Screenshots", "Hit tests", "Computed styles", "Network & console", "Playwright test"].map((t) => (
              <li key={t} className="inline-flex items-center gap-2">
                <span className="size-1.5 rounded-full bg-brand" /> {t}
              </li>
            ))}
          </ul>
        </div>
      </section>


      {/* ------------------------------------------------------------ two jobs */}
      <section id="what-it-does" className="scroll-mt-20 border-b border-border">
        <div className="mx-auto max-w-[1180px] px-5 py-24 sm:px-8">
          <p className="eyebrow">Two things it does</p>
          <h2 className="mt-5 max-w-3xl text-[clamp(2.25rem,4.4vw,3.5rem)] font-semibold leading-[1.02] tracking-[-0.04em]">
            Understand any site.
            <br />
            Fix your own.
          </h2>
          <div className="mt-12 grid gap-8 lg:grid-cols-2">
            <article className="card-ink flex min-w-0 flex-col p-7 sm:p-9">
              <p className="eyebrow text-brand-text">Briefing · any website · about a minute</p>
              <h3 className="mt-3 text-[1.75rem] font-semibold leading-tight tracking-[-0.025em]">&ldquo;What is this website, and what&apos;s it for?&rdquo;</h3>
              <p className="mt-3 text-[1rem] leading-relaxed text-fg-muted">
                The agent opens the site, reads the pages that explain it best — and, if you give it your login, what members see too.
                You get a plain-language briefing with a link to every source. It never buys, posts or changes anything.
              </p>
              <figure className="mt-6 rounded-xl border border-border bg-surface-2 p-5">
                <figcaption className="font-mono text-[11px] uppercase tracking-[0.14em] text-fg-subtle">Real briefing · Northwind Supply (our demo store)</figcaption>
                <blockquote className="mt-3 text-body leading-relaxed">
                  &ldquo;Northwind Supply is an online store. It describes itself as: &lsquo;Small-batch stationery and desk goods.&rsquo; On the 8 public pages we
                  read, visitors can browse products, buy things online, create an account, sign in and get help. After signing in, we also read 2
                  members-only pages: Profile and Orders.&rdquo;
                </blockquote>
              </figure>
              <ButtonLink href="/register?next=%2Fbriefings%2Fnew" variant="ink" icon={<Icon.ArrowRight size={14} />} className="mt-7 h-11 flex-row-reverse self-start px-5">
                Ask about a website
              </ButtonLink>
            </article>
            <article className="card-ink flex min-w-0 flex-col p-7 sm:p-9">
              <p className="eyebrow text-danger">Investigation · your website</p>
              <h3 className="mt-3 text-[1.75rem] font-semibold leading-tight tracking-[-0.025em]">&ldquo;What&apos;s broken on my site — and can you prove it?&rdquo;</h3>
              <p className="mt-3 text-[1rem] leading-relaxed text-fg-muted">
                After you prove the site is yours, it explores it, signs up, goes through checkout on a computer and a phone, and repeats
                anything that fails. Each problem comes with screenshots, the cause, a suggested fix and an automatic test.
              </p>
              <ul className="mt-6 space-y-2.5 text-body">
                {["Finds problems real visitors hit", "Explains each one in plain words", "Proves the fix with a test it runs for you"].map((t) => (
                  <li key={t} className="flex gap-2.5">
                    <Icon.Check size={15} className="mt-1 shrink-0 text-brand" /> {t}
                  </li>
                ))}
              </ul>
              <ButtonLink href="/register?next=%2Finvestigations%2Fnew" variant="paper" icon={<Icon.ArrowRight size={14} />} className="mt-auto h-11 flex-row-reverse self-start px-5 max-lg:mt-7">
                Check my site
              </ButtonLink>
            </article>
          </div>
        </div>
      </section>

      {/* ------------------------------------------------------------ how it works */}
      <section id="how-it-works" className="relative scroll-mt-20 overflow-hidden border-b border-border">
        <div className="halftone halftone-corner" aria-hidden />
        <div className="relative mx-auto grid max-w-[1180px] gap-14 px-5 py-24 sm:px-8 lg:grid-cols-[0.95fr_1.05fr]">
          <div className="lg:sticky lg:top-28 lg:self-start">
            <p className="eyebrow">How an investigation works</p>
            <h2 className="mt-5 text-[clamp(2.25rem,4.4vw,3.5rem)] font-semibold leading-[1.02] tracking-[-0.04em]">
              One URL in.
              <br />
              Evidence out.
            </h2>
            <p className="mt-6 max-w-md text-[1.0625rem] leading-relaxed text-fg-muted">
              No test suite to write first. You decide what it may do; it does the clicking, checking and re-checking, and shows
              its work.
            </p>
            <div className="mt-8 flex flex-wrap items-center gap-3">
              <ButtonLink href="/register" variant="ink" icon={<Icon.ArrowRight size={14} />} className="h-10 flex-row-reverse px-5">
                Start free
              </ButtonLink>
              <ButtonLink href="/docs#getting-started" variant="paper" className="h-10 px-5">
                Read the guide
              </ButtonLink>
            </div>
          </div>
          <ol className="divide-y divide-border">
            {STEPS.map((s) => (
              <li key={s.n} className="grid grid-cols-[56px_1fr] gap-5 py-8 first:pt-0 last:pb-0">
                <div className="flex size-14 items-center justify-center rounded-2xl border-[1.5px] border-fg bg-surface text-fg shadow-[3px_3px_0_var(--wx-fg)]">
                  {s.icon}
                </div>
                <div>
                  <p className="eyebrow !tracking-[0.18em]">
                    {s.n} · {s.tag}
                  </p>
                  <h3 className="mt-2 text-[1.5rem] font-semibold tracking-[-0.02em]">{s.title}</h3>
                  <p className="mt-2 text-[1rem] leading-relaxed text-fg-muted">{s.body}</p>
                </div>
              </li>
            ))}
          </ol>
        </div>
      </section>

      {/* ------------------------------------------------------------ findings from a real run */}
      <section id="findings" className="scroll-mt-20 border-b border-border">
        <div className="mx-auto max-w-[1180px] px-5 py-24 sm:px-8">
          <p className="eyebrow">From a real run</p>
          <h2 className="mt-5 max-w-3xl text-[clamp(2.25rem,4.4vw,3.5rem)] font-semibold leading-[1.02] tracking-[-0.04em]">
            Three findings. Not mockups.
          </h2>
          <p className="mt-6 max-w-2xl text-[1.0625rem] leading-relaxed text-fg-muted">
            We pointed WEB X-RAY at its benchmark store, Northwind Supply. Below is what it recorded — the screenshot is the
            evidence it captured on a 390&nbsp;px phone.
          </p>

          {/* 01 — confirmed defect */}
          <article className="card-ink mt-12 grid min-w-0 overflow-hidden lg:grid-cols-[minmax(0,1fr)_minmax(0,1.05fr)]">
            <div className="flex flex-col p-7 sm:p-9">
              <p className="eyebrow text-danger">01 · Confirmed defect · Critical</p>
              <h3 className="mt-3 text-[1.75rem] font-semibold leading-tight tracking-[-0.025em]">Checkout can&apos;t be completed on a phone.</h3>
              <p className="mt-3 text-[1rem] leading-relaxed text-fg-muted">
                A fixed &ldquo;Questions about your order?&rdquo; bar covers the Place order button at every scroll position. A real
                tap at the button&apos;s centre lands on the bar, and no order request is ever sent. On desktop the same journey
                completes.
              </p>
              <dl className="mt-auto grid grid-cols-3 gap-4 border-t border-border pt-6 max-lg:mt-8">
                {[
                  ["Mobile runs", "2 of 2 failed"],
                  ["Desktop", "passed"],
                  ["Playwright", "reproduced"],
                ].map(([k, v]) => (
                  <div key={k}>
                    <dt className="font-mono text-[11px] uppercase tracking-[0.14em] text-fg-subtle">{k}</dt>
                    <dd className="mt-1 text-[1.0625rem] font-medium">{v}</dd>
                  </div>
                ))}
              </dl>
            </div>
            <div className="relative border-t-[1.5px] border-fg bg-surface-2 p-6 sm:p-8 lg:border-l-[1.5px] lg:border-t-0">
              <div className="mb-3 flex items-center justify-between font-mono text-[11px] text-fg-subtle">
                <span>evidence · mobile #1 · checkout</span>
                <span>390 × 844</span>
              </div>
              <div className="relative overflow-hidden rounded-xl border border-border-strong bg-white">
                <Image
                  src="/landing/evidence-mobile-region.png"
                  alt="Captured screenshot: the help bar fills the bottom of the checkout page where the Place order button should be"
                  width={1170}
                  height={336}
                  className="block h-auto w-full"
                />
                <div className="absolute inset-x-[4%] bottom-[14%] top-[34%] rounded-lg border-2 border-dashed border-brand" />
                <span className="absolute right-[5%] top-[6%] rounded-full bg-fg px-2.5 py-1 font-mono text-[11px] text-bg">Place order is under here</span>
              </div>
              <div className="mt-4 rounded-xl border border-border bg-surface p-4 font-mono text-[12px] leading-relaxed">
                <div className="text-fg-subtle"># probe tap at the button&apos;s visual centre</div>
                <div>
                  delivered to <span className="text-danger">&lt;aside.help-bar&gt;</span> · position: fixed · z-index: 40
                </div>
                <div className="text-fg-subtle">ruled out: JS errors · failed requests · disabled state</div>
              </div>
            </div>
          </article>

          <div className="mt-8 grid gap-8 lg:grid-cols-2">
            {/* 02 — warning */}
            <article className="card-ink flex min-w-0 flex-col p-7 sm:p-9">
              <p className="eyebrow text-warning">02 · Warning · Medium</p>
              <h3 className="mt-3 text-[1.5rem] font-semibold leading-tight tracking-[-0.02em]">An API fails on every page load.</h3>
              <p className="mt-3 text-[1rem] leading-relaxed text-fg-muted">
                Observed directly, not guessed — but its user impact wasn&apos;t verified, so it&apos;s a warning, not a defect.
              </p>
              <div className="mt-6 overflow-x-auto rounded-xl border border-border bg-surface-2 p-4 font-mono text-[12px] leading-relaxed">
                <div>
                  GET /api/recommendations <span className="text-danger">→ 503</span>
                </div>
                <div className="text-fg-subtle">10 of 10 page loads · /, /products/*</div>
                <div className="mt-2 border-t border-border pt-2 text-fg-muted">console: [recommendations] request failed with HTTP 503</div>
              </div>
            </article>

            {/* 03 — the test */}
            <article className="card-ink flex min-w-0 flex-col p-7 sm:p-9">
              <p className="eyebrow text-brand-text">03 · Reproduction test</p>
              <h3 className="mt-3 text-[1.5rem] font-semibold leading-tight tracking-[-0.02em]">A test that proves it — and proves the fix.</h3>
              <p className="mt-3 text-[1rem] leading-relaxed text-fg-muted">
                Generated from the exact locators the investigation used, then run. After the fix, the same test passed.
              </p>
              <pre className="mt-6 overflow-x-auto rounded-xl border border-border bg-[oklch(0.19_0.01_275)] p-4 font-mono text-[11.5px] leading-relaxed text-[oklch(0.9_0.01_85)]">
                <code>
                  <span className="text-[oklch(0.65_0.02_85)]">{"// mobile 390×844 · tap at the control's centre\n"}</span>
                  {"const probe = await probeCenter(page, placeOrder);\n"}
                  {"expect(probe.received, "}
                  <span className="text-[oklch(0.8_0.12_190)]">{"'[WEBXRAY-DEFECT] …'"}</span>
                  {").toBe(true);"}
                </code>
              </pre>
              <div className="mt-4 flex flex-wrap gap-2 font-mono text-[11.5px]">
                <span className="rounded-full bg-danger-soft px-2.5 py-1 text-danger">before fix · reproduced</span>
                <span className="rounded-full bg-success-soft px-2.5 py-1 text-success">after fix · passing</span>
              </div>
            </article>
          </div>
          <p className="mt-8 font-mono text-[12px] text-fg-subtle">
            Northwind Supply is WEB X-RAY&apos;s own benchmark store with known defects. Your findings come from your site.
          </p>
        </div>
      </section>

      {/* ------------------------------------------------------------ what's in the box */}
      <section className="border-b border-border bg-surface">
        <div className="mx-auto grid max-w-[1180px] gap-12 px-5 py-24 sm:px-8 lg:grid-cols-[0.8fr_1.2fr]">
          <div>
            <p className="eyebrow">What&apos;s in an investigation</p>
            <h2 className="mt-5 text-[clamp(2rem,3.6vw,2.75rem)] font-semibold leading-[1.05] tracking-[-0.035em]">Everything it takes to trust a bug report.</h2>
          </div>
          <dl className="grid gap-x-10 sm:grid-cols-2">
            {BOX.map(([t, d], i) => (
              <div key={t} className="border-t border-border py-6">
                <dt className="flex items-baseline gap-3">
                  <span className="font-mono text-[11px] text-fg-subtle">{String(i + 1).padStart(2, "0")}</span>
                  <span className="text-[1.125rem] font-semibold tracking-[-0.01em]">{t}</span>
                </dt>
                <dd className="mt-2 pl-8 text-body leading-relaxed text-fg-muted">{d}</dd>
              </div>
            ))}
          </dl>
        </div>
      </section>

      {/* ------------------------------------------------------------ safety */}
      <section id="safety" className="scroll-mt-20 border-b border-border">
        <div className="mx-auto max-w-[1180px] px-5 py-24 sm:px-8">
          <div className="card-ink grid overflow-hidden lg:grid-cols-[0.9fr_1.1fr]">
            <div className="p-8 sm:p-10">
              <p className="eyebrow">Safety</p>
              <h2 className="mt-5 text-[clamp(2rem,3.6vw,2.75rem)] font-semibold leading-[1.05] tracking-[-0.035em]">
                Safe to point at real systems.
              </h2>
              <p className="mt-5 max-w-md text-[1rem] leading-relaxed text-fg-muted">
                The guardrails are enforced by the platform itself, independent of any automation — so a page can&apos;t talk its
                way past them.
              </p>
              <Link href="/docs#security" className="mt-6 inline-flex items-center gap-1.5 text-body font-medium underline-offset-4 hover:underline">
                Read the security model <Icon.ArrowRight size={14} />
              </Link>
            </div>
            <dl className="grid border-t-[1.5px] border-fg bg-surface-2 sm:grid-cols-2 lg:border-l-[1.5px] lg:border-t-0">
              {[
                ["Verified sites only", "No investigation starts until you prove you control the origin."],
                ["No internal access", "Loopback, private and cloud-metadata addresses are blocked, and DNS answers are pinned."],
                ["Consent for consequences", "Test accounts and sandbox orders happen only with your recorded approval."],
                ["Humans for human checks", "CAPTCHA, MFA and email verification pause for you — they are never bypassed."],
              ].map(([t, d], i) => (
                <div key={t} className={`p-7 ${i % 2 === 0 ? "sm:border-r" : ""} ${i < 2 ? "border-b" : ""} border-border`}>
                  <dt className="flex items-center gap-2 text-[1.0625rem] font-semibold">
                    <Icon.Check size={15} className="text-brand" /> {t}
                  </dt>
                  <dd className="mt-2 text-body leading-relaxed text-fg-muted">{d}</dd>
                </div>
              ))}
            </dl>
          </div>
        </div>
      </section>

      {/* ------------------------------------------------------------ pricing */}
      <section id="pricing" className="relative scroll-mt-20 overflow-hidden border-b border-border">
        <div className="halftone halftone-corner" aria-hidden />
        <div className="relative mx-auto max-w-[1180px] px-5 py-24 sm:px-8">
          <div className="max-w-2xl">
            <p className="eyebrow">Pricing · Early access</p>
            <h2 className="mt-5 text-[clamp(2.25rem,4.4vw,3.5rem)] font-semibold leading-[1.02] tracking-[-0.04em]">
              Start free.
              <br />
              Upgrade for a few dollars.
            </h2>
          </div>
          <div className="mt-12 grid items-stretch gap-6 md:grid-cols-3">
            {PLANS.map((p) => (
              <div
                key={p.name}
                className={
                  p.featured
                    ? "card-ink relative flex flex-col p-7"
                    : "relative flex flex-col rounded-2xl border-[1.5px] border-border-strong bg-surface p-7"
                }
              >
                {p.featured && (
                  <span className="absolute -top-3 left-7 rounded-full bg-brand px-2.5 py-0.5 font-mono text-[11px] text-brand-fg">Best value</span>
                )}
                <h3 className="text-[1.25rem] font-semibold">{p.name}</h3>
                <p className="mt-1.5 text-body text-fg-muted">{p.blurb}</p>
                <p className="mt-6 flex items-baseline gap-2">
                  <span className="text-[3rem] font-semibold leading-none tracking-[-0.04em]">{p.price}</span>
                  <span className="text-body text-fg-subtle">{p.cadence}</span>
                </p>
                <ul className="mt-6 space-y-3 border-t border-border pt-6">
                  {p.features.map((f) => (
                    <li key={f} className="flex items-start gap-2.5 text-body">
                      <Icon.Check size={15} className="mt-0.5 shrink-0 text-brand" /> {f}
                    </li>
                  ))}
                </ul>
                <ButtonLink
                  href={p.cta.href}
                  variant={p.featured ? "ink" : "paper"}
                  className="mt-8 h-11 w-full"
                >
                  {p.cta.label}
                </ButtonLink>
              </div>
            ))}
          </div>
          <p className="mt-8 max-w-3xl font-mono text-[12px] leading-relaxed text-fg-subtle">
            Early access: billing isn&apos;t switched on yet, so every workspace currently has every feature at no cost. Plan
            limits take effect when billing launches — we&apos;ll tell you before anything is charged.
          </p>
        </div>
      </section>

      {/* ------------------------------------------------------------ final call */}
      <section>
        <div className="mx-auto max-w-[1180px] px-5 py-24 text-center sm:px-8">
          <p className="eyebrow">Your turn</p>
          <h2 className="mx-auto mt-5 max-w-3xl text-[clamp(2.25rem,4.4vw,3.5rem)] font-semibold leading-[1.02] tracking-[-0.04em]">
            Point it at your staging site.
          </h2>
          <p className="mx-auto mt-5 max-w-xl text-[1.0625rem] leading-relaxed text-fg-muted">
            Verify the site, approve the scope, and get findings you can reproduce — with the evidence to prove each one.
          </p>
          <UrlLauncher className="mx-auto mt-9 max-w-[33rem] text-left" />
        </div>
      </section>
    </>
  );
}
