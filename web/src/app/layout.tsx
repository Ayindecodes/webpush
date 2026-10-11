import type { Metadata, Viewport } from "next";
import { Geist, Geist_Mono } from "next/font/google";

import { ThemeSync } from "@/components/theme";
import { ToastProvider } from "@/components/ui/primitives";

import "./globals.css";

const geistSans = Geist({ variable: "--font-geist-sans", subsets: ["latin"] });
const geistMono = Geist_Mono({ variable: "--font-geist-mono", subsets: ["latin"] });

export const metadata: Metadata = {
  title: { default: "WEB X-RAY — See what's really broken on your website", template: "%s · WEB X-RAY" },
  description:
    "WEB X-RAY explores your website in an isolated browser, runs real user journeys on desktop and mobile, and hands you evidence and a Playwright test for every defect it confirms.",
};

export const viewport: Viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: dark)", color: "#16161c" },
    { media: "(prefers-color-scheme: light)", color: "#f6f3ee" },
  ],
};

// Applies the saved theme before first paint (see Next.js "Preventing flash before hydration").
const THEME_SCRIPT = `(function(){try{var t=localStorage.getItem("wx.theme");if(t){t=JSON.parse(t);if(t==="light"||t==="dark")document.documentElement.setAttribute("data-theme",t)}}catch(e){}})()`;

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="en"
      data-theme="light"
      suppressHydrationWarning
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_SCRIPT }} />
      </head>
      <body className="min-h-full">
        <ToastProvider>
          <ThemeSync />
          {children}
        </ToastProvider>
      </body>
    </html>
  );
}
