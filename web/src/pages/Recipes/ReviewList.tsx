import { useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../../api/client";
import { useQuery } from "../../hooks/useApi";
import { Alert, Async, EmptyState } from "../../ui";
import { AssignPanel } from "./AssignPanel";
import { quantityText } from "./format";
import { detailLink } from "./RecipeCardView";
import type { AssignOut, UnassignedListData } from "./types";
import "./Recipes.css";

const LIMIT = 50;

/** Prüfliste: Zutatenzeilen ohne Zuordnung. Nach einer Zuordnung verschwinden gleichlautende Zeilen. */
export function ReviewList() {
  const list = useQuery<UnassignedListData>(`/recipe-lines/unassigned?limit=${LIMIT}`);
  const [notice, setNotice] = useState<string | null>(null);
  const items = list.data?.items ?? [];

  async function assign(lineId: number, raw: string, ingredientId: number, remember: boolean) {
    const out = await api<AssignOut>("POST", `/recipe-lines/${lineId}/assign`, {
      ingredient_id: ingredientId,
      save_synonym: remember,
    });
    const n = out.assigned_line_ids.length;
    const recipes = out.recipe_ids.length;
    setNotice(
      n > 1
        ? `„${raw}“ zugeordnet: ${n} Zeilen in ${recipes === 1 ? "einem Rezept" : `${recipes} Rezepten`} wurden aktualisiert.`
        : `„${raw}“ zugeordnet.`,
    );
    list.reload();
  }

  return (
    <>
      <p className="muted">
        Diese Zutatenzeilen konnten keiner Zutat aus dem Katalog zugeordnet werden. Solange das fehlt, sind die
        Nährwerte der Rezepte unvollständig.
      </p>
      {notice && <Alert kind="ok">{notice}</Alert>}
      <Async loading={list.loading && !list.data} error={list.error}>
        {list.data && items.length === 0 ? (
          <EmptyState>
            <p>Alle Zutaten sind zugeordnet. Hier gibt es nichts zu prüfen.</p>
          </EmptyState>
        ) : (
          <>
            <p className="muted" aria-live="polite">
              {list.data?.total === 1 ? "1 Zeile offen" : `${list.data?.total ?? 0} Zeilen offen`}
              {list.data && list.data.total > items.length && `, die ersten ${items.length} werden angezeigt`}
            </p>
            <ul className="crud-list" aria-label="Zutaten prüfen">
              {items.map((item) => (
                <li key={item.line_id} className="crud-item">
                  <h3>{item.raw_text}</h3>
                  <p className="muted rc-sub">
                    In <Link to={detailLink(item.recipe_id)}>{item.recipe_title}</Link>
                    {item.quantity !== null && ` · Menge ${quantityText(item.quantity, item.unit)}`}
                    {item.similar_count > 1 &&
                      ` · ${item.similar_count - 1} gleichlautende ${item.similar_count - 1 === 1 ? "Zeile" : "Zeilen"} werden bei „Zuordnung merken“ mit zugeordnet`}
                  </p>
                  <AssignPanel
                    label={item.raw_text}
                    initialQuery=""
                    suggestions={item.suggestions}
                    onAssign={(id, remember) => assign(item.line_id, item.raw_text, id, remember)}
                  />
                </li>
              ))}
            </ul>
          </>
        )}
      </Async>
    </>
  );
}
