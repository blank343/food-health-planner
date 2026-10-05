import { useCallback } from "react";
import { api } from "../api/client";
import { useQuery } from "./useApi";

/**
 * Liste und Änderungen für eine Ressource unter `/me/<resource>`
 * (Supplemente, Ernährungsregeln, Trainingsplan, Laborregeln).
 * Die Funktionen werfen `ApiError` mit deutscher Meldung; sie laden die Liste danach neu.
 */
export function useCrud<T extends { id: number }, In = Omit<T, "id">>(resource: string) {
  const list = useQuery<T[]>(`/me/${resource}`);
  const { reload } = list;

  const create = useCallback(
    async (input: In) => {
      const created = await api<T>("POST", `/me/${resource}`, input);
      reload();
      return created;
    },
    [resource, reload],
  );
  const update = useCallback(
    async (id: number, input: In) => {
      const updated = await api<T>("PUT", `/me/${resource}/${id}`, input);
      reload();
      return updated;
    },
    [resource, reload],
  );
  const remove = useCallback(
    async (id: number) => {
      await api<void>("DELETE", `/me/${resource}/${id}`);
      reload();
    },
    [resource, reload],
  );

  return { ...list, items: list.data ?? [], create, update, remove };
}
