import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, api } from "../../api/client";
import type { components } from "../../api/schema";
import type { IngredientOut, Source } from "./labels";

type IngredientList = components["schemas"]["IngredientListOut"];

export const PAGE_SIZE = 25;

export type SearchParams = { q: string; source: Source | ""; includeHidden: boolean };

function pathFor(p: SearchParams, offset: number): string {
  const qs = new URLSearchParams();
  if (p.q) qs.set("q", p.q);
  if (p.source) qs.set("source", p.source);
  if (p.includeHidden) qs.set("include_hidden", "true");
  qs.set("limit", String(PAGE_SIZE));
  qs.set("offset", String(offset));
  return `/ingredients?${qs.toString()}`;
}

/** Zutatensuche mit seitenweisem Nachladen („Mehr laden“ hängt die nächste Seite an). */
export function useIngredientSearch(params: SearchParams) {
  const { q, source, includeHidden } = params;
  const [items, setItems] = useState<IngredientOut[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [tick, setTick] = useState(0);
  const seq = useRef(0);
  const itemsRef = useRef<IngredientOut[]>([]);
  itemsRef.current = items;

  useEffect(() => {
    const mine = ++seq.current;
    setLoading(true);
    setLoadingMore(false);
    setError(null);
    api<IngredientList>("GET", pathFor({ q, source, includeHidden }, 0))
      .then((res) => {
        if (mine !== seq.current) return;
        setItems(res.items);
        setTotal(res.total);
      })
      .catch((e: unknown) => {
        if (mine !== seq.current) return;
        setItems([]);
        setTotal(0);
        setError(e instanceof ApiError ? e.message : "Unbekannter Fehler.");
      })
      .finally(() => {
        if (mine === seq.current) setLoading(false);
      });
  }, [q, source, includeHidden, tick]);

  const loadMore = useCallback(async () => {
    const mine = seq.current;
    setLoadingMore(true);
    setError(null);
    try {
      const res = await api<IngredientList>("GET", pathFor({ q, source, includeHidden }, itemsRef.current.length));
      if (mine !== seq.current) return;
      setItems((prev) => {
        const known = new Set(prev.map((i) => i.id));
        return [...prev, ...res.items.filter((i) => !known.has(i.id))];
      });
      setTotal(res.total);
    } catch (e) {
      if (mine === seq.current) setError(e instanceof ApiError ? e.message : "Unbekannter Fehler.");
    } finally {
      if (mine === seq.current) setLoadingMore(false);
    }
  }, [q, source, includeHidden]);

  const reload = useCallback(() => setTick((t) => t + 1), []);
  return { items, total, loading, loadingMore, error, loadMore, reload, hasMore: items.length < total };
}
