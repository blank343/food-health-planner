import { useEffect, useState } from "react";

/** Gibt `value` erst nach `delayMs` Ruhe weiter (für Suchfelder und Live-Berechnungen). */
export function useDebounced<T>(value: T, delayMs = 300): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setDebounced(value), delayMs);
    return () => clearTimeout(t);
  }, [value, delayMs]);
  return debounced;
}
