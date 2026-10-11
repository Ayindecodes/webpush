"use client";

import { useCallback, useEffect, useMemo, useRef, useState, useSyncExternalStore } from "react";
import useSWR, { type SWRConfiguration } from "swr";

import { api, ApiError, fetcher } from "./api";
import type { InvestigationEvent } from "./types";

export function useApi<T>(path: string | null, config?: SWRConfiguration<T>) {
  return useSWR<T>(path, fetcher, { revalidateOnFocus: true, shouldRetryOnError: false, ...config });
}

/** Incrementally polls the event stream (seq-based), accumulating events in order. */
export function useEventStream(investigationId: string, active: boolean) {
  const [store, setStore] = useState<{ id: string; events: InvestigationEvent[] }>({ id: investigationId, events: [] });
  const [error, setError] = useState<Error | null>(null);
  const lastSeq = useRef(0);
  const events = store.id === investigationId ? store.events : [];

  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    if (store.id !== investigationId) lastSeq.current = 0;
    const tick = async () => {
      try {
        const batch = await api.get<InvestigationEvent[]>(
          `/api/investigations/${investigationId}/events?after=${lastSeq.current}&limit=1000`,
        );
        if (cancelled) return;
        if (batch.length) {
          lastSeq.current = batch[batch.length - 1].seq;
          setStore((prev) =>
            prev.id === investigationId ? { id: prev.id, events: [...prev.events, ...batch] } : { id: investigationId, events: batch },
          );
        }
        setError(null);
        // Drain backlog immediately; otherwise poll at a steady cadence while active.
        if (batch.length >= 1000) timer = setTimeout(tick, 0);
        else if (active) timer = setTimeout(tick, 1500);
      } catch (e) {
        if (!cancelled) {
          setError(e as Error);
          // Retry network/server errors; a 4xx (gone, forbidden, signed out) won't fix itself.
          const status = e instanceof ApiError ? e.status : 0;
          if (status < 400 || status >= 500) timer = setTimeout(tick, 4000);
        }
      }
    };
    tick();
    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
    // store.id is read only to detect an investigation switch.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [investigationId, active]);

  return { events, error };
}

export function useNow(intervalMs = 1000, enabled = true): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!enabled) return;
    const id = setInterval(() => setNow(Date.now()), intervalMs);
    return () => clearInterval(id);
  }, [intervalMs, enabled]);
  return now;
}

const LOCAL_EVENT = "wx:local-storage";

function subscribeLocal(callback: () => void) {
  window.addEventListener("storage", callback);
  window.addEventListener(LOCAL_EVENT, callback);
  return () => {
    window.removeEventListener("storage", callback);
    window.removeEventListener(LOCAL_EVENT, callback);
  };
}

/** A JSON value persisted in localStorage, shared by every component that reads the same key. */
export function useLocalStorage<T>(key: string, initial: T): [T, (v: T) => void] {
  const raw = useSyncExternalStore(
    subscribeLocal,
    () => window.localStorage.getItem(key),
    () => null,
  );
  const value = useMemo(() => {
    if (raw === null) return initial;
    try {
      return JSON.parse(raw) as T;
    } catch {
      return initial;
    }
    // initial is a default for a missing key; it should not invalidate a stored value.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [raw]);
  const set = useCallback(
    (v: T) => {
      try {
        window.localStorage.setItem(key, JSON.stringify(v));
      } catch {
        /* storage unavailable */
      }
      window.dispatchEvent(new Event(LOCAL_EVENT));
    },
    [key],
  );
  return [value, set];
}

/** Public-page session probe: never errors for anonymous visitors. */
export function useSession() {
  const { data } = useApi<{ authenticated: boolean; user: import("./types").User | null }>("/api/auth/session", {
    revalidateOnFocus: false,
  });
  return data?.user ?? null;
}

/** Whether any job worker is alive. `available` is null when it can't be determined. */
export function useWorkers(enabled: boolean) {
  const { data } = useApi<{ available: boolean | null; count: number | null }>(enabled ? "/api/system/workers" : null, {
    refreshInterval: enabled ? 5000 : 0,
  });
  return data;
}
