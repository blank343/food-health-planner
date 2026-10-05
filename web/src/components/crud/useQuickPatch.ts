import { useCallback } from "react";
import { api } from "../../api/client";
import { useAction } from "../../hooks/useApi";

/** Schnelle Teiländerung (PATCH) eines Eintrags, danach wird die Liste neu geladen. */
export function useQuickPatch(resource: string, reload: () => void) {
  const fn = useCallback(
    async (id: number, partial: Record<string, unknown>) => {
      await api("PATCH", `/me/${resource}/${id}`, partial);
      reload();
    },
    [resource, reload],
  );
  const { run, busy, error, clearError } = useAction(fn);
  return { patch: run, busy, error, clearError };
}
