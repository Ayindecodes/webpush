import Link from "next/link";

import { Mark } from "@/components/brand/logo";

export default function NotFound() {
  return (
    <div data-surface="paper" className="flex min-h-screen flex-col items-center justify-center px-6 text-center">
      <Mark size={48} />
      <p className="eyebrow mt-8">Error 404</p>
      <h1 className="display mt-3">Nothing to see here.</h1>
      <p className="mt-4 max-w-sm text-[1.0625rem] leading-relaxed text-fg-muted">This page doesn&apos;t exist, or it has moved.</p>
      <div className="mt-8 flex flex-wrap justify-center gap-3">
        <Link href="/overview" className="inline-flex h-11 items-center rounded-full bg-fg px-5 text-body font-medium text-bg hover:bg-fg/85">
          Go to your dashboard
        </Link>
        <Link href="/" className="inline-flex h-11 items-center rounded-full border border-border-strong bg-surface px-5 text-body font-medium hover:border-fg">
          WEB X-RAY home
        </Link>
      </div>
    </div>
  );
}
