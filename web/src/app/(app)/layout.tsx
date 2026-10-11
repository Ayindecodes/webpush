import { Suspense } from "react";

import { AppShell } from "@/components/shell/app-shell";

// The dashboard is session-gated and every view reads live investigation state
// client-side (with its own loading skeletons), so there is no meaningful static
// shell to validate for instant navigation.
export const instant = false;

export default function AppLayout({ children }: { children: React.ReactNode }) {
  return (
    <Suspense>
      <AppShell>{children}</AppShell>
    </Suspense>
  );
}
