import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, api } from "../api/client";

export type Query<T> = {
  data: T | undefined;
  error: string | null;
  loading: boolean;
  reload: () => void;
};

/** Lädt per GET. `path = null` pausiert die Abfrage. Aktualisiert bei Pfadänderung. */
export function useQuery<T>(path: string | null): Query<T> {
  const [data, setData] = useState<T | undefined>(undefined);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState<boolean>(path !== null);
  const [tick, setTick] = useState(0);
  const seq = useRef(0);

  useEffect(() => {
    if (path === null) {
      setLoading(false);
      return;
    }
    const mine = ++seq.current;
    setLoading(true);
    api<T>("GET", path)
      .then((d) => {
        if (mine !== seq.current) return;
        setData(d);
        setError(null);
      })
      .catch((e: unknown) => {
        if (mine !== seq.current) return;
        setError(e instanceof ApiError ? e.message : "Unbekannter Fehler.");
      })
      .finally(() => {
        if (mine === seq.current) setLoading(false);
      });
  }, [path, tick]);

  const reload = useCallback(() => setTick((t) => t + 1), []);
  return { data, error, loading, reload };
}

export type Action<A extends unknown[], R> = {
  run: (...args: A) => Promise<R | undefined>;
  busy: boolean;
  error: string | null;
  clearError: () => void;
};

/** Führt eine Aktion (POST/PUT/…) aus und merkt sich Laufzustand und Fehlermeldung. */
export function useAction<A extends unknown[], R>(fn: (...args: A) => Promise<R>): Action<A, R> {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const run = useCallback(
    async (...args: A) => {
      setBusy(true);
      setError(null);
      try {
        return await fn(...args);
      } catch (e) {
        setError(e instanceof ApiError ? e.message : "Unbekannter Fehler.");
        return undefined;
      } finally {
        setBusy(false);
      }
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [fn],
  );
  return { run, busy, error, clearError: () => setError(null) };
}
