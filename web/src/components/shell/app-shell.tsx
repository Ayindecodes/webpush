"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useRef, useState, type ReactNode } from "react";

import { Mark, Wordmark } from "@/components/brand/logo";
import { ThemeToggle } from "@/components/theme";
import { Icon } from "@/components/ui/icons";
import { Button, Spinner, cx } from "@/components/ui/primitives";
import { api, ApiError } from "@/lib/api";
import { useApi, useLocalStorage } from "@/lib/hooks";
import { loginHref } from "@/lib/routes";
import type { Briefing, Overview, Project, User } from "@/lib/types";

import { ShellProvider, useShell } from "./context";

type Badge = "investigations" | "briefings";

const NAV: { href: string; label: string; icon: (p: { className?: string }) => ReactNode; badge?: Badge }[] = [
  { href: "/overview", label: "Home", icon: Icon.Home },
  { href: "/briefings", label: "Briefings", icon: Icon.Compass, badge: "briefings" },
  { href: "/investigations", label: "Investigations", icon: Icon.Investigation, badge: "investigations" },
  { href: "/findings", label: "Problems found", icon: Icon.Finding },
  { href: "/projects", label: "Websites", icon: Icon.Globe },
  { href: "/settings", label: "Settings", icon: Icon.Settings },
];

const NEW_ACTIONS = [
  { href: "/briefings/new", label: "Ask about a website", body: "Any site — get a plain-English explanation.", icon: Icon.Compass },
  { href: "/investigations/new", label: "Check my site for problems", body: "Your own site — find what's broken, with proof.", icon: Icon.Search },
];

/** One "New" button that asks what you want to do (replaces two look-alike buttons). */
function NewMenu({ collapsed }: { collapsed: boolean }) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent | KeyboardEvent) => {
      if (e instanceof KeyboardEvent ? e.key === "Escape" : !ref.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", close);
    return () => {
      document.removeEventListener("mousedown", close);
      document.removeEventListener("keydown", close);
    };
  }, [open]);
  return (
    <div className="relative" ref={ref}>
      <button
        type="button"
        onClick={() => setOpen(!open)}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label={collapsed ? "New" : undefined}
        title={collapsed ? "New" : undefined}
        className={cx(
          "flex items-center justify-center gap-2 rounded-full bg-fg font-medium text-bg transition-colors hover:bg-fg/85",
          collapsed ? "mx-auto size-10" : "h-10 w-full",
        )}
      >
        <Icon.Plus />
        {!collapsed && <span>New</span>}
      </button>
      {open && (
        <div role="menu" className={cx("card-ink-sm wx-enter absolute z-50 mt-2 w-72 p-1.5", collapsed ? "left-0" : "left-0 right-0 w-auto")}>
          {NEW_ACTIONS.map(({ href, label, body, icon: I }) => (
            <Link key={href} role="menuitem" href={href} className="flex gap-3 rounded-xl px-3 py-2.5 hover:bg-surface-2" onClick={() => setOpen(false)}>
              <I className="mt-0.5 shrink-0 text-fg-muted" />
              <span>
                <span className="block text-body font-semibold">{label}</span>
                <span className="block text-label text-fg-muted">{body}</span>
              </span>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}

function isActive(pathname: string, href: string) {
  return pathname === href || pathname.startsWith(href + "/");
}

export function AppShell({ children }: { children: ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const { data: user, error, isLoading, mutate } = useApi<User>("/api/auth/me");

  useEffect(() => {
    // Session expired or revoked while the cookie is still present.
    if (error instanceof ApiError && error.status === 401) {
      router.replace(loginHref(pathname + window.location.search));
    }
  }, [error, router, pathname]);

  if (isLoading || (error instanceof ApiError && error.status === 401)) {
    return (
      <div className="flex min-h-screen flex-col items-center justify-center gap-4 text-fg-muted">
        <Mark size={40} active />
        <Spinner />
      </div>
    );
  }
  if (error || !user) {
    return (
      <div className="flex min-h-screen items-center justify-center p-6">
        <div className="card-ink max-w-md p-8 text-center">
          <Mark size={40} className="mx-auto mb-5" />
          <div className="text-title font-semibold">We can&apos;t reach WEB X-RAY right now</div>
          <p className="mt-2 text-body text-fg-muted">{error instanceof Error ? error.message : "Unknown error"}</p>
          <p className="mt-2 text-label text-fg-subtle">If you run WEB X-RAY yourself, check that the API server is running.</p>
          <Button className="mt-6" variant="primary" onClick={() => mutate()} icon={<Icon.Refresh />}>
            Try again
          </Button>
        </div>
      </div>
    );
  }
  return (
    <ShellProvider user={user}>
      <Frame>{children}</Frame>
    </ShellProvider>
  );
}

function useCounts() {
  const { data: overview } = useApi<Overview>("/api/overview", { refreshInterval: 5000 });
  const { data: briefings } = useApi<Briefing[]>("/api/briefings?limit=20", { refreshInterval: 5000 });
  const byStatus = overview?.investigations.by_status ?? {};
  const running = byStatus.running ?? 0;
  const briefingsActive = (briefings ?? []).filter((b) => b.status === "queued" || b.status === "running").length;
  return {
    running: running + briefingsActive,
    investigations: running + (byStatus.queued ?? 0) + (byStatus.paused ?? 0) + (byStatus.awaiting_human ?? 0),
    briefings: briefingsActive,
    needsYou: byStatus.awaiting_human ?? 0,
  };
}
type Counts = ReturnType<typeof useCounts>;

function Frame({ children }: { children: ReactNode }) {
  const [collapsed, setCollapsed] = useLocalStorage("wx.sidebar.collapsed", false);
  const pathname = usePathname();
  // The drawer is open for the path it was opened on; navigating closes it.
  const [openedAt, setOpenedAt] = useState<string | null>(null);
  const mobileOpen = openedAt === pathname;
  const counts = useCounts();

  return (
    <div className="flex min-h-screen">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:fixed focus:left-3 focus:top-3 focus:z-50 focus:rounded-full focus:bg-fg focus:px-4 focus:py-2 focus:text-bg"
      >
        Skip to content
      </a>
      <aside
        className={cx(
          "sticky top-0 hidden h-screen shrink-0 flex-col border-r border-border bg-surface/70 transition-[width] duration-200 md:flex",
          collapsed ? "w-[72px]" : "w-[256px]",
        )}
        aria-label="Sidebar"
      >
        <SidebarContent collapsed={collapsed} onToggle={() => setCollapsed(!collapsed)} counts={counts} />
      </aside>
      {mobileOpen && (
        <div className="fixed inset-0 z-40 md:hidden">
          <div className="absolute inset-0 bg-overlay" onClick={() => setOpenedAt(null)} />
          <aside className="wx-enter absolute inset-y-0 left-0 flex w-[280px] flex-col border-r-[1.5px] border-[var(--wx-ink-line)] bg-bg">
            <SidebarContent collapsed={false} onToggle={() => setOpenedAt(null)} counts={counts} mobile />
          </aside>
        </div>
      )}
      <div className="flex min-w-0 flex-1 flex-col">
        <Topbar onMenu={() => setOpenedAt(pathname)} />
        <main id="main" className="mx-auto w-full max-w-[1200px] flex-1 px-4 pb-20 pt-6 sm:px-6 lg:px-10 lg:pt-8">
          {children}
        </main>
      </div>
    </div>
  );
}

function SidebarContent({ collapsed, onToggle, counts, mobile }: { collapsed: boolean; onToggle: () => void; counts: Counts; mobile?: boolean }) {
  const pathname = usePathname();
  return (
    <>
      <div className={cx("flex h-16 items-center", collapsed ? "justify-center" : "justify-between pl-5 pr-3")}>
        <Link
          href="/overview"
          className="flex items-center gap-2.5 rounded-md"
          aria-label={counts.running ? `WEB X-RAY — ${counts.running} running` : "WEB X-RAY — home"}
          title={counts.running ? "Working…" : undefined}
        >
          <Mark size={26} active={counts.running > 0} tone="duo" />
          {!collapsed && <Wordmark height={12} className="text-fg" />}
        </Link>
        {!collapsed && (
          <Button
            variant="ghost"
            size="sm"
            onClick={onToggle}
            aria-label={mobile ? "Close navigation" : "Collapse sidebar"}
            icon={mobile ? <Icon.X /> : <Icon.Sidebar />}
            className="size-8 px-0"
          />
        )}
      </div>

      <div className={cx("pb-3", collapsed ? "px-0" : "px-4")}>
        <NewMenu collapsed={collapsed} />
      </div>

      <nav aria-label="Main" className="flex-1 overflow-y-auto px-3 py-2">
        <ul className="space-y-1">
          {NAV.map(({ href, label, icon: I, badge }) => {
            const active = isActive(pathname, href);
            const n = badge ? counts[badge] : 0;
            return (
              <li key={href}>
                <Link
                  href={href}
                  aria-current={active ? "page" : undefined}
                  title={collapsed ? label : undefined}
                  className={cx(
                    "relative flex h-10 items-center gap-3 rounded-full text-body transition-colors",
                    collapsed ? "mx-auto w-10 justify-center" : "px-3.5",
                    active ? "bg-surface font-semibold text-fg shadow-[inset_0_0_0_1.5px_var(--wx-ink-line)]" : "text-fg-muted hover:bg-surface-2 hover:text-fg",
                  )}
                >
                  <I className="shrink-0" />
                  {!collapsed && <span className="flex-1 truncate">{label}</span>}
                  {!collapsed && badge === "investigations" && counts.needsYou > 0 && (
                    <span className="rounded-full bg-warning-soft px-2 text-meta font-medium text-warning" title="Waiting for you">
                      {counts.needsYou}
                    </span>
                  )}
                  {!collapsed && n > 0 && (
                    <span className="flex items-center gap-1 rounded-full bg-brand-soft px-2 text-meta font-medium text-brand-text" title="Running now">
                      <span className="wx-live-dot size-1.5 rounded-full bg-current" />
                      {n}
                    </span>
                  )}
                  {collapsed && n > 0 && <span className="absolute right-1 top-1 size-2 rounded-full bg-brand" aria-label={`${n} running`} />}
                </Link>
              </li>
            );
          })}
        </ul>
      </nav>

      <div className={cx("flex items-center border-t border-border p-3", collapsed ? "flex-col gap-1" : "gap-1")}>
        <Link
          href="/docs"
          className={cx(
            "flex h-9 items-center gap-2 rounded-full px-3 text-label text-fg-muted transition-colors hover:bg-surface-2 hover:text-fg",
            !collapsed && "flex-1",
          )}
          title="Help & guides"
        >
          <Icon.Book />
          {!collapsed && "Help & guides"}
        </Link>
        <ThemeToggle />
        {collapsed && !mobile && <Button variant="ghost" size="sm" onClick={onToggle} aria-label="Expand sidebar" icon={<Icon.Sidebar />} className="size-9 px-0" />}
      </div>
    </>
  );
}

export function ProjectSwitcher() {
  const { projectId, setProjectId } = useShell();
  const { data: projects } = useApi<Project[]>("/api/projects");
  const current = projects?.find((p) => p.id === projectId);
  if (!projects || projects.length === 0) return null;
  return (
    <label className="relative flex h-9 items-center rounded-full border border-border bg-surface transition-colors hover:border-border-strong focus-within:border-fg">
      <span className="sr-only">Show work from</span>
      <Icon.Project className="pointer-events-none absolute left-3 text-fg-subtle" />
      <select
        value={projectId ?? ""}
        onChange={(e) => setProjectId(e.target.value || null)}
        className="h-full w-full max-w-[200px] cursor-pointer appearance-none truncate bg-transparent pl-9 pr-8 text-label font-medium text-fg outline-none"
        title={current ? `Showing ${current.name}` : "Showing all projects"}
      >
        <option value="">All projects</option>
        {projects.map((p) => (
          <option key={p.id} value={p.id}>
            {p.name}
          </option>
        ))}
      </select>
      <Icon.ChevronDown className="pointer-events-none absolute right-3 text-fg-subtle" size={14} />
    </label>
  );
}

function Topbar({ onMenu }: { onMenu: () => void }) {
  const { crumbs } = useShell();
  const pathname = usePathname();
  const showProject = /^\/(investigations|findings|journeys)(\/|$)/.test(pathname) && !pathname.endsWith("/new");
  return (
    <header className="sticky top-0 z-30 flex h-16 items-center gap-3 border-b border-border bg-bg/85 px-4 backdrop-blur-md sm:px-6 lg:px-10">
      <button
        type="button"
        className="-ml-2 flex size-10 items-center justify-center rounded-full text-fg hover:bg-surface-2 md:hidden"
        onClick={onMenu}
        aria-label="Open menu"
      >
        <Icon.Menu size={22} />
      </button>
      <Link href="/overview" className="md:hidden" aria-label="WEB X-RAY home">
        <Mark size={24} />
      </Link>
      <nav aria-label="Breadcrumb" className="min-w-0 flex-1">
        <ol className="flex items-center gap-2 text-body">
          {crumbs.map((c, i) => (
            <li key={i} className={cx("flex min-w-0 items-center gap-2", i < crumbs.length - 1 && "max-sm:hidden")}>
              {i > 0 && <span className="text-fg-subtle">/</span>}
              {c.href && i < crumbs.length - 1 ? (
                <Link href={c.href} className="truncate text-fg-muted transition-colors hover:text-fg">
                  {c.label}
                </Link>
              ) : (
                <span className="truncate font-medium" aria-current="page">
                  {c.label}
                </span>
              )}
            </li>
          ))}
        </ol>
      </nav>
      {showProject && (
        <div className="max-lg:hidden">
          <ProjectSwitcher />
        </div>
      )}
      <AccountMenu />
    </header>
  );
}

function AccountMenu() {
  const { user } = useShell();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent | KeyboardEvent) => {
      if (e instanceof KeyboardEvent ? e.key === "Escape" : !ref.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", close);
    return () => {
      document.removeEventListener("mousedown", close);
      document.removeEventListener("keydown", close);
    };
  }, [open]);
  const initials = (user.display_name || user.email)
    .split(/\s+/)
    .map((w) => w[0])
    .join("")
    .slice(0, 2)
    .toUpperCase();
  return (
    <div className="relative" ref={ref}>
      <button
        onClick={() => setOpen(!open)}
        aria-haspopup="menu"
        aria-expanded={open}
        className="flex size-9 items-center justify-center rounded-full border-[1.5px] border-[var(--wx-ink-line)] bg-surface text-[11px] font-semibold text-fg transition-colors hover:bg-surface-2"
        aria-label="Account menu"
      >
        {initials}
      </button>
      {open && (
        <div role="menu" className="card-ink-sm wx-enter absolute right-0 top-11 z-50 w-72 p-1.5">
          <div className="px-3 py-3">
            <div className="truncate text-body font-semibold">{user.display_name || "Your account"}</div>
            <div className="truncate text-label text-fg-subtle">{user.email}</div>
            <div className="mt-2 inline-flex rounded-full bg-surface-2 px-2.5 py-0.5 text-meta text-fg-muted">{user.organization_name}</div>
          </div>
          <div className="my-1 border-t border-border" />
          <MenuLink href="/settings" icon={<Icon.Settings />} onClick={() => setOpen(false)}>
            Settings
          </MenuLink>
          <MenuLink href="/docs" icon={<Icon.Book />} onClick={() => setOpen(false)}>
            Help &amp; guides
          </MenuLink>
          <MenuLink href="/" icon={<Icon.Globe />} onClick={() => setOpen(false)}>
            WEB X-RAY website
          </MenuLink>
          <button
            role="menuitem"
            className="flex w-full items-center gap-2.5 rounded-xl px-3 py-2.5 text-left text-body hover:bg-surface-2"
            onClick={async () => {
              try {
                await api.post("/api/auth/logout");
              } finally {
                // Deliberately a full reload: it drops every cached API response from this session.
                // eslint-disable-next-line @next/next/no-location-assign-relative-destination
                window.location.assign("/login");
              }
            }}
          >
            <Icon.Logout className="text-fg-subtle" /> Sign out
          </button>
        </div>
      )}
    </div>
  );
}

function MenuLink({ href, icon, children, onClick }: { href: string; icon: ReactNode; children: ReactNode; onClick: () => void }) {
  return (
    <Link role="menuitem" href={href} className="flex items-center gap-2.5 rounded-xl px-3 py-2.5 text-body hover:bg-surface-2 [&>svg]:text-fg-subtle" onClick={onClick}>
      {icon} {children}
    </Link>
  );
}
