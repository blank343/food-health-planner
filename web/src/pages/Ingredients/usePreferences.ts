import { useCallback, useMemo } from "react";
import { ApiError, api } from "../../api/client";
import { useAction, useQuery } from "../../hooks/useApi";
import type { PrefLevel, PreferenceOut } from "./labels";

/** Eigene Zutaten-Vorlieben: alle Einträge als Tabelle nach Zutaten-Id, plus Setzen und Entfernen. */
export function usePreferences() {
  const list = useQuery<PreferenceOut[]>("/me/ingredient-preferences");
  const { reload } = list;

  const byId = useMemo(() => {
    const m = new Map<number, PreferenceOut>();
    for (const p of list.data ?? []) m.set(p.ingredient_id, p);
    return m;
  }, [list.data]);

  const setFn = useCallback(
    async (ingredientId: number, level: PrefLevel) => {
      await api("PUT", `/me/ingredient-preferences/${ingredientId}`, { level });
      reload();
    },
    [reload],
  );
  const clearFn = useCallback(
    async (ingredientId: number) => {
      try {
        await api("DELETE", `/me/ingredient-preferences/${ingredientId}`);
      } catch (e) {
        // Nichts zu entfernen ist kein Fehler.
        if (!(e instanceof ApiError && e.status === 404)) throw e;
      }
      reload();
    },
    [reload],
  );
  const set = useAction(setFn);
  const clear = useAction(clearFn);

  return {
    byId,
    loading: list.loading && !list.data,
    loadError: list.error,
    reload,
    set: set.run,
    clear: clear.run,
    busy: set.busy || clear.busy,
    error: set.error ?? clear.error,
    clearError: () => {
      set.clearError();
      clear.clearError();
    },
  };
}

export type Preferences = ReturnType<typeof usePreferences>;
