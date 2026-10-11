"use client";

import { createContext, useContext, useEffect, useState, type ReactNode } from "react";

import { useLocalStorage } from "@/lib/hooks";
import type { User } from "@/lib/types";

export interface Crumb {
  label: string;
  href?: string;
}

interface ShellState {
  user: User;
  crumbs: Crumb[];
  setCrumbs: (c: Crumb[]) => void;
  projectId: string | null;
  setProjectId: (id: string | null) => void;
}

const ShellContext = createContext<ShellState | null>(null);

export function ShellProvider({ user, children }: { user: User; children: ReactNode }) {
  const [crumbs, setCrumbs] = useState<Crumb[]>([]);
  const [projectId, setProjectId] = useLocalStorage<string | null>("wx.project", null);
  return (
    <ShellContext.Provider value={{ user, crumbs, setCrumbs, projectId, setProjectId }}>{children}</ShellContext.Provider>
  );
}

export function useShell(): ShellState {
  const ctx = useContext(ShellContext);
  if (!ctx) throw new Error("useShell must be used inside the app shell");
  return ctx;
}

/** Declare the breadcrumb trail for the current page. */
export function useCrumbs(crumbs: Crumb[]) {
  const { setCrumbs } = useShell();
  const key = JSON.stringify(crumbs);
  useEffect(() => {
    setCrumbs(JSON.parse(key));
  }, [key, setCrumbs]);
}
