import type { NextConfig } from "next";

// The dashboard talks to the FastAPI control plane through a same-origin rewrite,
// so the session cookie stays first-party and no CORS surface is opened.
const API_URL = process.env.WEBXRAY_API_URL ?? "http://127.0.0.1:8000";
const isDev = process.env.NODE_ENV === "development";

/*
 * Content Security Policy. Nonce-based script CSP is incompatible with Cache
 * Components (the static shell can't carry a per-request nonce), so inline
 * scripts are allowed; everything else is locked to this origin. Untrusted
 * text captured from investigated sites is only ever rendered through React
 * (escaped) and evidence is served by the API with its own sandbox CSP.
 */
const CSP = [
  "default-src 'self'",
  `script-src 'self' 'unsafe-inline'${isDev ? " 'unsafe-eval'" : ""}`,
  "style-src 'self' 'unsafe-inline'",
  "img-src 'self' data: blob:",
  "font-src 'self' data:",
  `connect-src 'self'${isDev ? " ws: wss:" : ""}`,
  "worker-src 'self' blob:",
  "manifest-src 'self'",
  "media-src 'none'",
  "object-src 'none'",
  "frame-src 'none'",
  "frame-ancestors 'none'",
  "base-uri 'self'",
  "form-action 'self'",
  ...(isDev ? [] : ["upgrade-insecure-requests"]),
].join("; ");

const SECURITY_HEADERS = [
  { key: "Content-Security-Policy", value: CSP },
  { key: "X-Frame-Options", value: "DENY" },
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "Referrer-Policy", value: "no-referrer" },
  { key: "Cross-Origin-Opener-Policy", value: "same-origin" },
  { key: "Cross-Origin-Resource-Policy", value: "same-origin" },
  {
    key: "Permissions-Policy",
    value: "camera=(), microphone=(), geolocation=(), payment=(), usb=(), serial=(), bluetooth=(), browsing-topics=()",
  },
  // Only meaningful over HTTPS; production must be served over TLS.
  ...(isDev ? [] : [{ key: "Strict-Transport-Security", value: "max-age=63072000; includeSubDomains" }]),
];

const nextConfig: NextConfig = {
  poweredByHeader: false,
  cacheComponents: true,
  partialPrefetching: true,
  // Keep the dev-only indicator clear of the sidebar's primary action.
  devIndicators: { position: "bottom-right" },
  experimental: {
    // Dashboard views are client-rendered from live API state; validate instant
    // navigation only for segments that explicitly opt in with `instant`.
    instantInsights: { validationLevel: "manual-warning" },
  },
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${API_URL}/api/:path*` }];
  },
  async headers() {
    return [{ source: "/:path*", headers: SECURITY_HEADERS }];
  },
};

export default nextConfig;
