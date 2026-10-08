// Eigene Hooks der Rezeptseiten: verzögerte Eingabe und gemeinsamer Kontext „Passt ins Tagesziel“.
import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../../api/client";
import { todayIso } from "../../format";
import { type ErrorInfo, defaultSlotForHour, errorInfo } from "./format";
import { SLOTS, type SlotName, type Targets, isSlot } from "./types";

/** Gibt den Wert erst nach `delay` ms Ruhe weiter (z. B. für die Suche beim Tippen). */
export function useDebounced<T>(value: T, delay = 300): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const id = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(id);
  }, [value, delay]);
  return debounced;
}

export type SlotChoice = "auto" | "none" | SlotName;

export type SlotContext = {
  date: string;
  setDate: (d: string) => void;
  /** Wirksame Mahlzeit für die Passung oder `null` (keine Passung) */
  slot: SlotName | null;
  choice: SlotChoice;
  setChoice: (c: SlotChoice) => void;
  /** Mahlzeiten mit Anteil > 0 am gewählten Tag */
  slots: SlotName[];
  targets: Targets | undefined;
  loading: boolean;
  error: ErrorInfo | null;
};

/**
 * Lädt das Tagesziel für das Datum und leitet daraus die wählbaren Mahlzeiten ab.
 * Ohne Auswahl gilt die Mahlzeit nach Tageszeit (falls verfügbar, sonst die erste verfügbare).
 */
export function useSlotContext(): SlotContext {
  const [date, setDate] = useState(todayIso());
  const [choice, setChoice] = useState<SlotChoice>("auto");
  const [state, setState] = useState<{ targets: Targets | undefined; loading: boolean; error: ErrorInfo | null }>({
    targets: undefined,
    loading: true,
    error: null,
  });
  const seq = useRef(0);

  useEffect(() => {
    if (!date) {
      setState({ targets: undefined, loading: false, error: null });
      return;
    }
    const mine = ++seq.current;
    setState((s) => ({ ...s, loading: true }));
    api<Targets>("GET", `/me/targets?date=${encodeURIComponent(date)}`)
      .then((targets) => {
        if (mine === seq.current) setState({ targets, loading: false, error: null });
      })
      .catch((e: unknown) => {
        if (mine === seq.current) setState({ targets: undefined, loading: false, error: errorInfo(e) });
      });
  }, [date]);

  const { targets } = state;
  const slots = targets ? SLOTS.filter((s) => (targets.slots[s]?.kcal ?? 0) > 0) : [];
  let slot: SlotName | null = null;
  if (targets && choice !== "none") {
    if (isSlot(choice) && slots.includes(choice)) slot = choice;
    else {
      const byTime = defaultSlotForHour(new Date().getHours());
      slot = slots.includes(byTime) ? byTime : (slots[0] ?? null);
    }
  }

  const setDateStable = useCallback((d: string) => setDate(d), []);
  return { date, setDate: setDateStable, slot, choice, setChoice, slots, ...state };
}
