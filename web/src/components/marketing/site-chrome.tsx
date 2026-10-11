"use client";

import Link from "next/link";
import { useState } from "react";

import { Mark, Wordmark } from "@/components/brand/logo";
import { HeroGlobe } from "@/components/marketing/hero-globe";
import { UrlLauncher } from "@/components/marketing/url-launcher";
import { Icon } from "@/components/ui/icons";
import { ButtonLink } from "@/components/ui/primitives";
import { useSession } from "@/lib/hooks";

const LINKS = [
  { href: "/#what-it-does", label: "What it does" },
  { href: "/#how-it-works", label: "How it works" },
  { href: "/#findings", label: "What it finds" },
  { href: "/#pricing", label: "Pricing" },
  { href: "/docs", label: "Docs" },
];

function BrandLink({ inverse = false }: { inverse?: boolean }) {
  const [hover, setHover] = useState(false);
  return (
    <Link
      href="/"
      aria-label="WEB X-RAY home"
      className="flex shrink-0 items-center gap-2.5"
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      onFocus={() => setHover(true)}
      onBlur={() => setHover(false)}
    >
      <Mark size={26} active={hover} tone={inverse ? "current" : "duo"} className={inverse ? "text-white" : ""} />
      <Wordmark height={13} className={inverse ? "text-white" : "text-fg"} />
    </Link>
  );
}

export function SiteHeader() {
  const user = useSession();
  const [open, setOpen] = useState(false);
  return (
    <header className="sticky top-0 z-40 border-b border-border/60 bg-bg/85 backdrop-blur-md">
      <div className="mx-auto grid h-[72px] max-w-[1180px] grid-cols-[auto_1fr_auto] items-center gap-6 px-5 sm:px-8">
        <BrandLink />
        <nav aria-label="Main" className="hidden justify-center gap-1 md:flex">
          {LINKS.map((l) => (
            <Link key={l.href} href={l.href} className="rounded-full px-3.5 py-2 text-body text-fg-muted transition-colors hover:text-fg">
              {l.label}
            </Link>
          ))}
        </nav>
        <div className="col-start-3 flex items-center gap-2">
          {user ? (
            <ButtonLink href="/overview" variant="ink" icon={<Icon.ArrowRight size={14} />} className="h-9 flex-row-reverse px-4">
              Open dashboard
            </ButtonLink>
          ) : (
            <>
              <ButtonLink href="/login" variant="paper" className="h-9 px-4 max-sm:hidden">
                Sign in
              </ButtonLink>
              <ButtonLink href="/register" variant="ink" icon={<Icon.ArrowRight size={14} />} className="h-9 flex-row-reverse px-4">
                Start free
              </ButtonLink>
            </>
          )}
          <button
            className="flex size-9 items-center justify-center rounded-full text-fg-muted hover:bg-surface-2 md:hidden"
            onClick={() => setOpen(!open)}
            aria-expanded={open}
            aria-label="Menu"
          >
            {open ? <Icon.X /> : <Icon.Menu />}
          </button>
        </div>
      </div>
      {open && (
        <nav aria-label="Main mobile" className="wx-enter border-t border-border px-5 pb-4 pt-2 md:hidden">
          {LINKS.map((l) => (
            <Link key={l.href} href={l.href} onClick={() => setOpen(false)} className="block border-b border-border py-3 text-body text-fg">
              {l.label}
            </Link>
          ))}
          {!user && (
            <Link href="/login" className="block py-3 text-body text-fg">
              Sign in
            </Link>
          )}
        </nav>
      )}
    </header>
  );
}

export function SiteFooter() {
  return (
    <footer className="relative overflow-hidden bg-[oklch(0.17_0.008_275)] text-white">
      <div
        className="pointer-events-none absolute inset-0 opacity-60 [background-image:url(/landing/halftone-dark.png)] [background-position:right_bottom] [background-repeat:no-repeat] [background-size:cover]"
        aria-hidden
      />
      <div className="relative mx-auto max-w-[1180px] px-5 pb-10 pt-16 sm:px-8">
        <div className="grid gap-12 md:grid-cols-[1.3fr_1fr]">
          <div className="max-w-md">
            <BrandLink inverse />
            <p className="mt-5 text-body leading-relaxed text-white/65">
              An agent for any website. It explains what a site is for — and on your own site, finds what&apos;s broken and proves it.
            </p>
            <UrlLauncher dark className="mt-6" />
          </div>
          <div className="grid grid-cols-3 gap-6">
            <FooterCol title="Product" links={[["What it does", "/#what-it-does"], ["How it works", "/#how-it-works"], ["What it finds", "/#findings"], ["Pricing", "/#pricing"], ["Safety", "/#safety"]]} />
            <FooterCol title="Learn" links={[["Getting started", "/docs#getting-started"], ["Reading findings", "/docs#findings"], ["Reproduction tests", "/docs#tests"], ["Security model", "/docs#security"]]} />
            <FooterCol title="Account" links={[["Sign in", "/login"], ["Create account", "/register"], ["Dashboard", "/overview"]]} />
          </div>
        </div>
        <div className="mt-16 flex flex-wrap items-center justify-between gap-3 border-t border-white/10 pt-6 font-mono text-[12px] text-white/45 xl:pr-[230px]">
          <span>WEB X-RAY · Only investigate websites you are authorized to test.</span>
          <span>Every finding links to its evidence.</span>
        </div>
      </div>
      <div
        className="pointer-events-none absolute -bottom-[170px] -right-[90px] hidden w-[330px] xl:block"
        style={{ ["--wx-surface" as string]: "oklch(0.23 0.01 275)", ["--wx-fg" as string]: "oklch(0.93 0.01 85)" }}
      >
        <HeroGlobe showFinding={false} idPrefix="footer-globe" />
      </div>
    </footer>
  );
}

function FooterCol({ title, links }: { title: string; links: [string, string][] }) {
  return (
    <div>
      <div className="mb-4 font-mono text-[11px] uppercase tracking-[0.16em] text-white/45">{title}</div>
      <ul className="space-y-3">
        {links.map(([label, href]) => (
          <li key={href}>
            <Link href={href} className="text-body text-white/80 transition-colors hover:text-white">
              {label}
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}
