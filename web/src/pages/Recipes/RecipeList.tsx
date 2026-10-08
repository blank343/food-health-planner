import { useEffect, useState } from "react";
import { api } from "../../api/client";
import { EmptyList } from "../../components/crud";
import { useQuery } from "../../hooks/useApi";
import { Alert, Card, CheckField, SelectField, Spinner, TextField } from "../../ui";
import { FitControls } from "./FitControls";
import { errorInfo } from "./format";
import { type SlotContext, useDebounced } from "./hooks";
import { RecipeCardView } from "./RecipeCardView";
import {
  DEFAULT_FILTERS,
  type ListFilters,
  type RecipeCard,
  type RecipeListData,
  SLOT_NAMES,
  SLOTS,
  SORT_LABELS,
  type SortKey,
  STATUS_OPTIONS,
  type StatusFilter,
  isSlot,
} from "./types";
import "./Recipes.css";

const PAGE_SIZE = 100;

export function buildListPath(
  f: ListFilters,
  q: string,
  fit: { slot: string; date: string } | null,
  sort: SortKey,
): string {
  const p = new URLSearchParams();
  if (q) p.set("q", q);
  if (f.slot) {
    p.set("slot", f.slot);
    if (f.untagged) p.set("include_untagged", "true");
  }
  if (f.favorite) p.set("favorite", "true");
  if (f.status) p.set("status", f.status);
  if (fit) {
    p.set("fit_slot", fit.slot);
    if (fit.date) p.set("fit_date", fit.date);
  }
  p.set("sort", sort);
  p.set("limit", String(PAGE_SIZE));
  return `/recipes?${p.toString()}`;
}

type Props = {
  ctx: SlotContext;
  filters: ListFilters;
  setFilters: (f: ListFilters) => void;
  onImport: () => void;
};

export function RecipeList({ ctx, filters, setFilters, onImport }: Props) {
  const debouncedQ = useDebounced(filters.q.trim(), 300);
  const fitActive = ctx.slot !== null;
  const sort: SortKey = filters.sort === "fit" && !fitActive ? "title" : filters.sort;
  const path = ctx.loading
    ? null
    : buildListPath(filters, debouncedQ, ctx.slot ? { slot: ctx.slot, date: ctx.date } : null, sort);
  const list = useQuery<RecipeListData>(path);

  // Änderungen (Bewertung, Favorit) zeigen wir sofort an, ohne die Reihenfolge der Liste zu ändern.
  const [patches, setPatches] = useState<Record<number, Partial<RecipeCard>>>({});
  const [busyId, setBusyId] = useState<number | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  useEffect(() => setPatches({}), [list.data]);

  const set = (patch: Partial<ListFilters>) => setFilters({ ...filters, ...patch });
  const hasFilters = filters.q.trim() !== "" || filters.slot !== "" || filters.favorite || filters.status !== "";

  async function run(id: number, action: () => Promise<Partial<RecipeCard>>) {
    setBusyId(id);
    setActionError(null);
    try {
      const patch = await action();
      setPatches((p) => ({ ...p, [id]: { ...p[id], ...patch } }));
    } catch (e) {
      setActionError(errorInfo(e).message);
    } finally {
      setBusyId(null);
    }
  }

  const rate = (card: RecipeCard, rating: number | null) =>
    run(card.id, async () => {
      if (rating === null) await api("DELETE", `/recipes/${card.id}/rating`);
      else await api("PUT", `/recipes/${card.id}/rating`, { rating });
      return { my_rating: rating };
    });
  const toggleFavorite = (card: RecipeCard) =>
    run(card.id, async () => {
      await api("PATCH", `/recipes/${card.id}`, { favorite: !card.favorite });
      return { favorite: !card.favorite };
    });

  const sortOptions = (Object.keys(SORT_LABELS) as SortKey[])
    .filter((k) => k !== "fit" || fitActive)
    .map((k) => ({ value: k, label: SORT_LABELS[k] }));

  const target = ctx.slot && ctx.targets ? ctx.targets.slots[ctx.slot] : undefined;
  const items = (list.data?.items ?? []).map((c) => ({ ...c, ...patches[c.id] }));

  return (
    <>
      <FitControls ctx={ctx} />

      <Card title="Suchen und filtern">
        <div className="rc-filters">
          <TextField
            label="Rezepte suchen"
            type="search"
            value={filters.q}
            onChange={(q) => set({ q })}
            autoComplete="off"
          />
          <SelectField
            label="Sortierung"
            value={sort}
            onChange={(v) => set({ sort: v as SortKey })}
            options={sortOptions}
          />
          <SelectField
            label="Mahlzeit des Rezepts"
            value={filters.slot}
            onChange={(v) => set({ slot: isSlot(v) ? v : "", untagged: isSlot(v) ? filters.untagged : false })}
            options={[{ value: "", label: "Alle Mahlzeiten" }, ...SLOTS.map((s) => ({ value: s, label: SLOT_NAMES[s] }))]}
          />
          <SelectField
            label="Status"
            value={filters.status}
            onChange={(v) => set({ status: v as StatusFilter })}
            options={STATUS_OPTIONS.map((o) => ({ value: o.value, label: o.label }))}
          />
        </div>
        {filters.slot !== "" && (
          <CheckField
            label="Auch Rezepte ohne Slot-Tag"
            checked={filters.untagged}
            onChange={(untagged) => set({ untagged })}
            hint="Rezepte, bei denen noch keine Mahlzeit eingetragen ist, bleiben sichtbar."
          />
        )}
        <CheckField label="Nur Favoriten" checked={filters.favorite} onChange={(favorite) => set({ favorite })} />
      </Card>

      <h2 className="rc-sr">Rezepte</h2>
      {actionError && <Alert kind="error">{actionError}</Alert>}

      {!list.data && list.error && <Alert kind="error">{list.error}</Alert>}
      {!list.data && !list.error && <Spinner label="Lade Rezepte …" />}
      {list.data && (
        <>
          {list.error && <Alert kind="error">{list.error}</Alert>}
          <p className="muted" aria-live="polite">
            {list.data.total === 1 ? "1 Rezept" : `${list.data.total} Rezepte`}
            {list.data.total > items.length && ` (die ersten ${items.length} werden angezeigt, bitte Suche oder Filter nutzen)`}
          </p>
          {items.length === 0 ? (
            hasFilters ? (
              <EmptyList
                actionLabel="Filter zurücksetzen"
                onAction={() => setFilters({ ...DEFAULT_FILTERS, sort: filters.sort })}
              >
                Keine Rezepte gefunden. Passen Sie Suche und Filter an.
              </EmptyList>
            ) : (
              <EmptyList actionLabel="Rezept importieren" onAction={onImport}>
                Noch keine Rezepte: Importiere ein Rezept per URL.
              </EmptyList>
            )
          ) : (
            <ul className="rc-grid" aria-label="Rezepte">
              {items.map((card) => (
                <RecipeCardView
                  key={card.id}
                  card={card}
                  fitActive={fitActive}
                  target={target}
                  busy={busyId === card.id}
                  onRate={(r) => rate(card, r)}
                  onFavorite={() => toggleFavorite(card)}
                />
              ))}
            </ul>
          )}
        </>
      )}
      {list.loading && list.data && (
        <p className="muted" role="status">
          Aktualisiere …
        </p>
      )}
    </>
  );
}
