import { NextResponse, type NextRequest } from "next/server";

import { SESSION_COOKIE, isAppPath, safeNext } from "@/lib/routes";

/**
 * Optimistic route protection: signed-in areas need a session cookie, otherwise
 * the visitor goes to /login and comes back afterwards. This is a UX gate only —
 * every API call is authorized by the backend, which is the security boundary.
 */
export function proxy(request: NextRequest) {
  const { pathname, search } = request.nextUrl;
  if (isAppPath(pathname) && !request.cookies.get(SESSION_COOKIE)?.value) {
    const url = request.nextUrl.clone();
    url.pathname = "/login";
    url.search = "";
    const next = safeNext(pathname + search, "");
    if (next) url.searchParams.set("next", next);
    return NextResponse.redirect(url);
  }
  return NextResponse.next();
}

export const config = {
  matcher: [
    {
      source: "/((?!api|_next/static|_next/image|landing|icon.svg|apple-icon.png|favicon.ico).*)",
      missing: [
        { type: "header", key: "next-router-prefetch" },
        { type: "header", key: "purpose", value: "prefetch" },
      ],
    },
  ],
};
