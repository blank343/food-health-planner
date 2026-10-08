import { num } from "../../format";
import { Alert, Badge, Button, Card, CheckField, EmptyState, Spinner, SelectField, TextField } from "../../ui";
import {
  type IngredientOut,
  type Source,
  levelLabel,
  saltOf,
  sourceLabel,
} from "./labels";
import type { Preferences } from "./usePreferences";
import { type SearchParams, useIngredientSearch } from "./useIngredientSearch";
import { useDebounced } from "./useDebounced";
import "./Ingredients.css";

const SOURCE_OPTIONS = [
  { value: "", label: "Alle Quellen" },
  { value: "bls", label: "BLS" },
  { value: "manual", label: "Manuell" },
  { value: "off", label: "Open Food Facts" },
];

const isSource = (v: string): v is Source | "" => v === "" || v === "bls" || v === "manual" || v === "off";

export type CatalogState = { text: string; source: Source | ""; includeHidden: boolean };
export const INITIAL_CATALOG: CatalogState = { text: "", source: "", includeHidden: false };

type Props = {
  state: CatalogState;
  onState: (s: CatalogState) => void;
  prefs: Preferences;
  onOpen: (id: number) => void;
  search: ReturnType<typeof useIngredientSearch>;
};

/** Sucheingaben des Katalogs (entprellt) → Suchparameter. */
export function useCatalogParams(state: CatalogState): SearchParams {
  const q = useDebounced(state.text.trim(), 300);
  return { q, source: state.source, includeHidden: state.includeHidden };
}

function Row({ item, prefLevel, onOpen }: { item: IngredientOut; prefLevel: string | null; onOpen: (id: number) => void }) {
  const n = item.nutrients;
  return (
    <li className="ing-item">
      <button type="button" className="ing-name" onClick={() => onOpen(item.id)}>
        {item.name}
      </button>
      <div className="crud-meta">
        <Badge>{sourceLabel(item.source)}</Badge>
        {item.category && <Badge>{item.category}</Badge>}
        {item.hidden && <Badge kind="warn">ausgeblendet</Badge>}
        {item.is_potassium_salt && <Badge kind="warn">Kaliumsalz</Badge>}
        {prefLevel && <Badge kind={prefLevel === "like" ? "ok" : "error"}>{levelLabel(prefLevel)}</Badge>}
      </div>
      <dl className="nutr-grid" aria-label={`Nährwerte je 100 g: ${item.name}`}>
        <div>
          <dt>kcal</dt>
          <dd>{num(n.kcal, 0)}</dd>
        </div>
        <div>
          <dt>Protein</dt>
          <dd>{num(n.protein_g, 1, "g")}</dd>
        </div>
        <div>
          <dt>Fett</dt>
          <dd>{num(n.fat_g, 1, "g")}</dd>
        </div>
        <div>
          <dt>Kohlenhydr.</dt>
          <dd>{num(n.carb_g, 1, "g")}</dd>
        </div>
        <div>
          <dt>Ballaststoffe</dt>
          <dd>{num(n.fiber_g, 1, "g")}</dd>
        </div>
        <div>
          <dt>Salz</dt>
          <dd>{num(saltOf(n), 2, "g")}</dd>
        </div>
      </dl>
    </li>
  );
}

/** Suche, Quellenfilter und Trefferliste des Zutaten-Katalogs. */
export function IngredientCatalog({ state, onState, prefs, onOpen, search }: Props) {
  const { items, total, loading, loadingMore, error, hasMore, loadMore } = search;
  return (
    <>
      <Card>
        <div className="filter-grid">
          <TextField
            label="Zutat suchen"
            type="search"
            value={state.text}
            onChange={(text) => onState({ ...state, text })}
            placeholder="z. B. Skyr oder Haferflocken"
            autoComplete="off"
          />
          <SelectField
            label="Quelle"
            value={state.source}
            onChange={(v) => onState({ ...state, source: isSource(v) ? v : "" })}
            options={SOURCE_OPTIONS}
          />
        </div>
        <CheckField
          label="Ausgeblendete Zutaten anzeigen"
          checked={state.includeHidden}
          onChange={(includeHidden) => onState({ ...state, includeHidden })}
        />
      </Card>

      {loading && <Spinner label="Suche Zutaten …" />}
      {!loading && error && <Alert kind="error">{error}</Alert>}
      {!loading && !error && items.length === 0 && (
        <EmptyState>
          <p>
            {state.text.trim() || state.source
              ? "Keine Zutat gefunden. Probiere einen anderen Suchbegriff oder lege die Zutat selbst an."
              : "Noch keine Zutaten im Katalog. Importiere die BLS-Datei (Kommandozeile) oder lege eigene Zutaten an."}
          </p>
        </EmptyState>
      )}
      {!loading && items.length > 0 && (
        <>
          <p className="muted" role="status">
            {items.length} von {total} Zutaten angezeigt.
          </p>
          <ul className="ing-list" aria-label="Zutaten">
            {items.map((i) => (
              <Row key={i.id} item={i} prefLevel={prefs.byId.get(i.id)?.level ?? null} onOpen={onOpen} />
            ))}
          </ul>
          {error && <Alert kind="error">{error}</Alert>}
          {hasMore && (
            <div className="row" style={{ justifyContent: "center", marginBottom: 16 }}>
              <Button onClick={() => void loadMore()} disabled={loadingMore} aria-busy={loadingMore}>
                {loadingMore ? "Lädt …" : "Mehr laden"}
              </Button>
            </div>
          )}
        </>
      )}
    </>
  );
}
