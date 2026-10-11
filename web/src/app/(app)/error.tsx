"use client";

import { Icon } from "@/components/ui/icons";
import { Button, ButtonLink } from "@/components/ui/primitives";

export default function AppError({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return (
    <div className="mx-auto max-w-lg py-16">
      <div className="card-ink p-8 text-center">
        <div className="mx-auto flex size-12 items-center justify-center rounded-xl border-[1.5px] border-danger/50 bg-danger-soft text-danger">
          <Icon.SevHigh size={20} />
        </div>
        <h1 className="mt-5 text-[1.5rem] font-semibold tracking-[-0.02em]">Something went wrong on this page</h1>
        <p className="mt-2 text-body text-fg-muted">It&apos;s not you. Try again, and if it keeps happening, go back home.</p>
        {error.digest && <p className="mt-3 font-mono text-meta text-fg-subtle">Reference: {error.digest}</p>}
        <div className="mt-6 flex flex-wrap justify-center gap-3">
          <Button variant="primary" onClick={reset} icon={<Icon.Refresh />}>
            Try again
          </Button>
          <ButtonLink href="/overview" variant="paper">
            Go home
          </ButtonLink>
        </div>
      </div>
    </div>
  );
}
