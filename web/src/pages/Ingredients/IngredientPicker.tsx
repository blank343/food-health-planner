import { useState } from "react";
import type { components } from "../../api/schema";
import { Button, Spinner, TextField } from "../../ui";
import { useQuery } from "../../hooks/useApi";
import { useDebounced } from "./useDebounced";
import { sourceLabel } from "./labels";
import "./Ingredients.css";

type IngredientList = components["schemas"]["IngredientListOut"];

export type IngredientRef = { id: number; name: string };

type Props = {
  label: string;
  value: IngredientRef | null;
  onChange: (value: IngredientRef | null) => void;
  /** Text, wenn nichts gewählt ist (z. B. „Zutat der Komponente“). */
  emptyText?: string;
  /** Erlaubt es, die Auswahl wieder zu entfernen. */
  clearable?: boolean;
  error?: string | null;
  /** Suchfeld sofort zeigen (Standard: nur ohne Auswahl). */
  startOpen?: boolean;
};

/** Zutatenauswahl über die Suche (`GET /ingredients?q=`). Ohne Auswahl erscheint das Suchfeld. */
export function IngredientPicker({ label, value, onChange, emptyText = "Keine Zutat gewählt", clearable = false, error, startOpen }: Props) {
  const [searching, setSearching] = useState(startOpen ?? value === null);
  const [text, setText] = useState("");
  const q = useDebounced(text.trim(), 250);
  const path = searching && q.length >= 2 ? `/ingredients?q=${encodeURIComponent(q)}&limit=10` : null;
  const res = useQuery<IngredientList>(path);

  if (!searching) {
    return (
      <div className="field">
        <span className="label" style={{ display: "block", fontWeight: 600, marginBottom: 4 }}>
          {label}
        </span>
        <div className="picker-selected">
          <strong>{value ? value.name : emptyText}</strong>
          <span className="row">
            <Button onClick={() => setSearching(true)} aria-label={`${label} ändern`}>
              Ändern
            </Button>
            {clearable && value && (
              <Button variant="ghost" onClick={() => onChange(null)} aria-label={`${label} entfernen`}>
                Entfernen
              </Button>
            )}
          </span>
        </div>
        {error && (
          <span className="err" role="alert" style={{ color: "var(--danger)", fontSize: ".85rem" }}>
            {error}
          </span>
        )}
      </div>
    );
  }

  const items = path ? (res.data?.items ?? []) : [];
  return (
    <div>
      <TextField
        label={label}
        value={text}
        onChange={setText}
        placeholder="Zutat suchen (mindestens 2 Buchstaben)"
        autoComplete="off"
        hint={value ? `Aktuell: ${value.name}` : undefined}
        error={error}
      />
      {path && res.loading && <Spinner label="Suche …" />}
      {path && res.error && <p className="err" role="alert" style={{ color: "var(--danger)" }}>{res.error}</p>}
      {!res.loading && path && !res.error && items.length === 0 && <p className="muted">Keine Zutat gefunden.</p>}
      {items.length > 0 && (
        <ul className="picker-results" aria-label={`Treffer für ${label}`}>
          {items.map((i) => (
            <li key={i.id}>
              <button
                type="button"
                onClick={() => {
                  onChange({ id: i.id, name: i.name });
                  setSearching(false);
                  setText("");
                }}
              >
                <span>{i.name}</span>
                <small>{sourceLabel(i.source)}</small>
              </button>
            </li>
          ))}
        </ul>
      )}
      {(value || startOpen === false) && (
        <Button variant="ghost" onClick={() => setSearching(false)}>
          {value ? "Auswahl behalten" : "Abbrechen"}
        </Button>
      )}
    </div>
  );
}
