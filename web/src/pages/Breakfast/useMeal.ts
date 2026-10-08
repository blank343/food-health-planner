import { useEffect, useRef, useState } from "react";
import { ApiError, api } from "../../api/client";
import { useDebounced } from "../Ingredients/useDebounced";
import type { MealIn, MealItemIn, MealOut, SlotName } from "./types";

type State = {
  data: MealOut | undefined;
  error: string | null;
  /** Meldung, wenn die Passung zum Tagesziel nicht berechnet werden konnte (HTTP 422). */
  fitIssue: string | null;
  busy: boolean;
};

export const MEAL_DEBOUNCE_MS = 300;

/**
 * Live-Berechnung der Baukasten-Mahlzeit (`POST /components/meal`), entprellt.
 * Kann der Dienst die Passung nicht berechnen (422, z. B. fehlendes Gewicht), wird ohne Slot neu gerechnet
 * und die Meldung in `fitIssue` bereitgestellt: die Summen bleiben sichtbar.
 */
export function useMeal(items: MealItemIn[], date: string, slot: SlotName | "") {
  const key = JSON.stringify({ items, date, slot });
  const debounced = useDebounced(key, MEAL_DEBOUNCE_MS);
  const [state, setState] = useState<State>({ data: undefined, error: null, fitIssue: null, busy: false });
  const seq = useRef(0);

  useEffect(() => {
    const req = JSON.parse(debounced) as { items: MealItemIn[]; date: string; slot: SlotName | "" };
    const mine = ++seq.current;
    if (req.items.length === 0) {
      setState({ data: undefined, error: null, fitIssue: null, busy: false });
      return;
    }
    setState((s) => ({ ...s, busy: true }));
    const fresh = () => mine === seq.current;
    const body: MealIn = { items: req.items };
    if (req.slot) {
      body.slot = req.slot;
      if (req.date) body.date = req.date;
    }
    api<MealOut>("POST", "/components/meal", body)
      .then((data) => {
        if (fresh()) setState({ data, error: null, fitIssue: null, busy: false });
      })
      .catch(async (e: unknown) => {
        if (!fresh()) return;
        if (e instanceof ApiError && e.status === 422 && req.slot) {
          try {
            const data = await api<MealOut>("POST", "/components/meal", { items: req.items });
            if (fresh()) setState({ data, error: null, fitIssue: e.message, busy: false });
          } catch (e2) {
            if (fresh()) setState({ data: undefined, error: e2 instanceof ApiError ? e2.message : "Unbekannter Fehler.", fitIssue: null, busy: false });
          }
          return;
        }
        setState((s) => ({ ...s, data: undefined, error: e instanceof ApiError ? e.message : "Unbekannter Fehler.", fitIssue: null, busy: false }));
      });
  }, [debounced]);

  const empty = items.length === 0;
  return {
    data: empty ? undefined : state.data,
    error: empty ? null : state.error,
    fitIssue: empty ? null : state.fitIssue,
    pending: !empty && (state.busy || key !== debounced),
  };
}
