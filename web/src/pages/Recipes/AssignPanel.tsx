import { useState } from "react";
import { useQuery } from "../../hooks/useApi";
import { Alert, Button, CheckField, Spinner, TextField } from "../../ui";
import { errorInfo } from "./format";
import { useDebounced } from "./hooks";
import type { IngredientList, Match } from "./types";
import "./Recipes.css";

type Props = {
  /** Name der Zeile, für die Beschriftung der Gruppe */
  label: string;
  /** Startwert der Zutatensuche; leer = erst nach Eingabe suchen */
  initialQuery?: string;
  /** Vorschläge des Dienstes (Schaltflächen) */
  suggestions?: Match[];
  /** Ordnet zu. Wirft bei Fehlern (die Meldung erscheint im Panel). */
  onAssign: (ingredientId: number, remember: boolean) => Promise<unknown>;
  onCancel?: () => void;
};

/** Zuordnung einer Zutatenzeile: Vorschläge und Zutatensuche, wahlweise mit „Zuordnung merken“. */
export function AssignPanel({ label, initialQuery = "", suggestions = [], onAssign, onCancel }: Props) {
  const [query, setQuery] = useState(initialQuery);
  const [remember, setRemember] = useState(true);
  const [busyId, setBusyId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const debounced = useDebounced(query.trim(), 300);
  const search = useQuery<IngredientList>(
    debounced.length >= 2 ? `/ingredients?q=${encodeURIComponent(debounced)}&limit=8` : null,
  );

  async function assign(id: number) {
    setBusyId(id);
    setError(null);
    try {
      await onAssign(id, remember);
    } catch (e) {
      setError(errorInfo(e).message);
    } finally {
      setBusyId(null);
    }
  }

  const busy = busyId !== null;
  const results = debounced.length >= 2 ? (search.data?.items ?? []) : [];

  return (
    <div className="rc-assign" role="group" aria-label={`Zuordnung für ${label}`}>
      <CheckField
        label="Zuordnung merken"
        checked={remember}
        onChange={setRemember}
        hint="Gleichlautende Zeilen werden künftig automatisch zugeordnet."
      />
      {error && <Alert kind="error">{error}</Alert>}
      {suggestions.length > 0 && (
        <div>
          <p className="label-sm">Vorschläge</p>
          <div className="row">
            {suggestions.map((s) => (
              <Button
                key={s.ingredient_id}
                onClick={() => assign(s.ingredient_id)}
                disabled={busy}
                aria-label={`Vorschlag ${s.name} zuordnen`}
              >
                {s.name}
              </Button>
            ))}
          </div>
        </div>
      )}
      <TextField label="Andere Zutat suchen" type="search" value={query} onChange={setQuery} autoComplete="off" />
      {debounced.length >= 2 && search.loading && !search.data && <Spinner label="Suche …" />}
      {debounced.length >= 2 && search.error && <Alert kind="error">{search.error}</Alert>}
      {debounced.length >= 2 && !search.loading && !search.error && search.data && results.length === 0 && (
        <p className="muted">Keine Zutat gefunden. Zutaten legen Sie im Katalog an.</p>
      )}
      {results.length > 0 && (
        <ul className="rc-results" aria-label="Suchergebnisse">
          {results.map((i) => (
            <li key={i.id}>
              <Button onClick={() => assign(i.id)} disabled={busy} aria-label={`${i.name} zuordnen`}>
                <span>{i.name}</span>
                {i.category && <small className="muted">{i.category}</small>}
              </Button>
            </li>
          ))}
        </ul>
      )}
      {onCancel && (
        <div className="row end">
          <Button onClick={onCancel} disabled={busy}>
            Abbrechen
          </Button>
        </div>
      )}
    </div>
  );
}
