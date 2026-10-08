import { useEffect, useRef, useState } from "react";
import { ApiError, api } from "../../api/client";
import { SLOT_ORDER, type SlotName, type TargetsOut } from "./types";

export type SlotTargets = {
  status: "loading" | "ok" | "unavailable" | "error";
  /** Slots mit Ziel (kcal > 0) in fester Reihenfolge; ohne Zieldaten alle vier. */
  slots: SlotName[];
  /** Meldung des Dienstes bei `unavailable` (422) oder `error`. */
  message: string | null;
};

/** Verfügbare Slots für ein Datum aus `GET /me/targets?date=`. 422 heißt: Ziel noch nicht berechenbar. */
export function useSlotTargets(date: string): SlotTargets {
  const [state, setState] = useState<SlotTargets>({ status: "loading", slots: SLOT_ORDER, message: null });
  const seq = useRef(0);

  useEffect(() => {
    const mine = ++seq.current;
    setState((s) => ({ ...s, status: "loading" }));
    api<TargetsOut>("GET", `/me/targets?date=${encodeURIComponent(date)}`)
      .then((t) => {
        if (mine !== seq.current) return;
        const slots = SLOT_ORDER.filter((s) => (t.slots[s]?.kcal ?? 0) > 0);
        setState({ status: "ok", slots, message: null });
      })
      .catch((e: unknown) => {
        if (mine !== seq.current) return;
        const message = e instanceof ApiError ? e.message : "Unbekannter Fehler.";
        const status = e instanceof ApiError && e.status === 422 ? "unavailable" : "error";
        setState({ status, slots: SLOT_ORDER, message });
      });
  }, [date]);

  return state;
}
