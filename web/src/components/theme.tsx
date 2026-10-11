"use client";

import { useEffect } from "react";

import { Icon } from "@/components/ui/icons";
import { cx } from "@/components/ui/primitives";
import { useLocalStorage } from "@/lib/hooks";

export type Theme = "dark" | "light";
const KEY = "wx.theme";

export function useTheme(): [Theme, (t: Theme) => void] {
  return useLocalStorage<Theme>(KEY, "light");
}

/** Keeps <html data-theme> in sync with the saved preference after hydration and on change. */
export function ThemeSync() {
  const [theme] = useTheme();
  useEffect(() => {
    document.documentElement.dataset.theme = theme;
  }, [theme]);
  return null;
}

export function ThemeToggle({ className }: { className?: string }) {
  const [theme, setTheme] = useTheme();
  const next = theme === "dark" ? "light" : "dark";
  return (
    <button
      type="button"
      onClick={() => setTheme(next)}
      aria-label={next === "dark" ? "Switch to ink (dark) theme" : "Switch to paper (light) theme"}
      title={next === "dark" ? "Ink theme" : "Paper theme"}
      className={cx(
        "flex size-9 items-center justify-center rounded-full text-fg-muted transition-colors hover:bg-surface-2 hover:text-fg",
        className,
      )}
    >
      {theme === "dark" ? <Icon.Sun /> : <Icon.Moon />}
    </button>
  );
}
