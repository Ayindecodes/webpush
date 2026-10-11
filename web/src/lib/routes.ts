/**
 * Route map and redirect safety. Shared by the proxy (server) and the client.
 * Keep this module free of browser/server-only APIs.
 */

/** Signed-in areas. The proxy sends visitors without a session cookie to /login. */
export const APP_PREFIXES = [
  "/overview",
  "/briefings",
  "/investigations",
  "/findings",
  "/journeys",
  "/projects",
  "/integrations",
  "/settings",
] as const;

export const AUTH_PAGES = ["/login", "/register"] as const;

export const SESSION_COOKIE = "wx_session";
export const DEFAULT_AFTER_LOGIN = "/overview";

export function isAppPath(pathname: string): boolean {
  return APP_PREFIXES.some((p) => pathname === p || pathname.startsWith(`${p}/`));
}

/**
 * Returns `next` only if it is a same-site, in-app path; otherwise the default.
 *
 * Rejects absolute and protocol-relative URLs ("//evil", "/\\evil" — browsers
 * treat a backslash like a slash), control characters, and anything outside
 * the signed-in app (including /api).
 */
export function safeNext(next: string | null | undefined, fallback: string = DEFAULT_AFTER_LOGIN): string {
  if (!next || next.length > 2048) return fallback;
  if (!next.startsWith("/") || next.startsWith("//") || next.includes("\\")) return fallback;
  if (/[\u0000-\u001f\u007f]/.test(next)) return fallback;
  let url: URL;
  try {
    url = new URL(next, "http://wx.invalid");
  } catch {
    return fallback;
  }
  if (url.origin !== "http://wx.invalid" || !isAppPath(url.pathname)) return fallback;
  return url.pathname + url.search + url.hash;
}

export function loginHref(next?: string | null): string {
  const target = next ? safeNext(next, "") : "";
  return target ? `/login?next=${encodeURIComponent(target)}` : "/login";
}

export function registerHref(next?: string | null, plan?: string | null): string {
  const params = new URLSearchParams();
  const target = next ? safeNext(next, "") : "";
  if (target) params.set("next", target);
  if (plan) params.set("plan", plan);
  const qs = params.toString();
  return qs ? `/register?${qs}` : "/register";
}
