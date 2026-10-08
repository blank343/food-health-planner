import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../../api/client";
import { ConfirmDelete, errorText, numDe } from "../../components/crud";
import { dateDe, num } from "../../format";
import { useQuery } from "../../hooks/useApi";
import { Alert, Badge, Button, Card, Spinner } from "../../ui";
import { FitControls } from "./FitControls";
import { LinesCard } from "./LinesCard";
import { NutritionCard, SatietyCard } from "./NutritionCard";
import { factorText, minutesDetail, minutesText } from "./format";
import type { SlotContext } from "./hooks";
import { FavoriteButton, FitSummary, MacroBars, Stars } from "./parts";
import { StatusBadge } from "./RecipeCardView";
import { RecipeForm } from "./RecipeForm";
import { type RecipeDetail, SLOT_NAMES, isSlot } from "./types";
import "./Recipes.css";

type Props = {
  id: number;
  ctx: SlotContext;
  onDeleted: () => void;
};

export function RecipeDetailView({ id, ctx, onDeleted }: Props) {
  const path = ctx.loading
    ? null
    : `/recipes/${id}${ctx.slot ? `?fit_slot=${ctx.slot}&fit_date=${encodeURIComponent(ctx.date)}` : ""}`;
  const q = useQuery<RecipeDetail>(path);
  const recipe = q.data;

  const [chosenFactor, setChosenFactor] = useState<number | null>(null);
  const [editing, setEditing] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const headingRef = useRef<HTMLHeadingElement>(null);

  useEffect(() => {
    if (recipe) headingRef.current?.focus();
  }, [recipe?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  async function act(fn: () => Promise<unknown>) {
    setBusy(true);
    setActionError(null);
    try {
      await fn();
      q.reload();
    } catch (e) {
      setActionError(errorText(e));
    } finally {
      setBusy(false);
    }
  }

  const back = (
    <p>
      <Link to={{ search: "" }}>← Alle Rezepte</Link>
    </p>
  );

  if (!recipe) {
    return (
      <>
        {back}
        {q.error ? <Alert kind="error">{q.error}</Alert> : <Spinner label="Lade Rezept …" />}
      </>
    );
  }

  const fit = ctx.slot && recipe.fit ? recipe.fit : null;
  const factor = chosenFactor ?? fit?.factor ?? 1;
  const unassigned = recipe.lines.filter((l) => l.ingredient === null && !l.optional).length;
  const slotNames = recipe.tag.slot_types.filter(isSlot).map((s) => SLOT_NAMES[s]);
  const time = minutesDetail(recipe.prep_min, recipe.cook_min);

  if (editing) {
    return (
      <>
        {back}
        <RecipeForm
          mode="edit"
          recipe={recipe}
          onCancel={() => setEditing(false)}
          onSaved={() => {
            setEditing(false);
            q.reload();
          }}
        />
      </>
    );
  }

  return (
    <>
      {back}
      <header>
        <div className="topbar">
          <h1 ref={headingRef} tabIndex={-1}>
            {recipe.title}
          </h1>
        </div>
        <div className="crud-meta">
          <StatusBadge status={recipe.status} />
          {slotNames.map((n) => (
            <Badge key={n}>{n}</Badge>
          ))}
          {recipe.tag.warm && <Badge>warm</Badge>}
          {recipe.tag.transportable && <Badge>transportierbar</Badge>}
          {recipe.tag.batch_cookable && <Badge>vorkochbar</Badge>}
          {recipe.tag.cuisine && <Badge>{recipe.tag.cuisine}</Badge>}
          {recipe.tag.main_ingredient && <Badge>{recipe.tag.main_ingredient}</Badge>}
        </div>
        <p className="muted rc-sub">
          {numDe(recipe.servings)} {recipe.servings === 1 ? "Portion" : "Portionen"} · Zeit{" "}
          {minutesText(recipe.prep_min, recipe.cook_min)}
          {time && ` (${time})`}
          {recipe.source_url && (
            <>
              {" · Quelle: "}
              <a href={recipe.source_url} target="_blank" rel="noopener noreferrer">
                {recipe.source_site ?? recipe.source_url}
              </a>
            </>
          )}
        </p>
        <div className="row rc-actions">
          <FavoriteButton
            favorite={recipe.favorite}
            title={recipe.title}
            disabled={busy}
            onToggle={() => act(() => api("PATCH", `/recipes/${recipe.id}`, { favorite: !recipe.favorite }))}
          />
          <Button onClick={() => setEditing(true)}>Bearbeiten</Button>
          <Button variant="danger" onClick={() => setConfirming(true)} disabled={confirming}>
            Löschen
          </Button>
        </div>
        {confirming && (
          <ConfirmDelete
            name={recipe.title}
            onCancel={() => setConfirming(false)}
            onConfirm={async () => {
              await api("DELETE", `/recipes/${recipe.id}`);
              onDeleted();
            }}
          />
        )}
      </header>

      {actionError && <Alert kind="error">{actionError}</Alert>}
      {q.error && <Alert kind="error">{q.error}</Alert>}
      {recipe.warnings?.map((w, i) => (
        <Alert key={i} kind="warn">
          {w}
        </Alert>
      ))}
      {unassigned > 0 && (
        <Alert kind="warn">
          <strong>Prüfen:</strong> {unassigned} {unassigned === 1 ? "Zutat ist" : "Zutaten sind"} noch keiner Zutat aus
          dem Katalog zugeordnet. Die Nährwerte sind deshalb unvollständig. Unten lässt sich das direkt zuordnen.
        </Alert>
      )}
      {recipe.notes && (
        <Alert kind="info">
          <span className="rc-pre">{recipe.notes}</span>
        </Alert>
      )}

      <Card title="Bewertung">
        <div className="rc-rating">
          <Stars
            value={recipe.my_rating}
            label="Eigene Bewertung"
            disabled={busy}
            onChange={(rating) =>
              act(() =>
                rating === null
                  ? api("DELETE", `/recipes/${recipe.id}/rating`)
                  : api("PUT", `/recipes/${recipe.id}/rating`, { rating }),
              )
            }
          />
          <span className="muted">Ein Klick auf den gewählten Stern nimmt die Bewertung zurück.</span>
        </div>
        {recipe.ratings.length === 0 ? (
          <p className="muted">Noch keine Bewertungen.</p>
        ) : (
          <ul className="rc-ratings" aria-label="Bewertungen">
            {recipe.ratings.map((r) => (
              <li key={r.person_id}>
                {r.person_name}: {r.rating} von 5 Sternen
              </li>
            ))}
          </ul>
        )}
      </Card>

      <FitControls ctx={ctx} />
      {fit && ctx.slot && (
        <Card title={`Passt ins Tagesziel: ${SLOT_NAMES[ctx.slot]}`}>
          <FitSummary score={fit.fit_score} factor={fit.factor} />
          <p className="muted rc-sub">
            Ziel der Mahlzeit am {dateDe(fit.date)}: {num(fit.slot_target.kcal, 0, "kcal")}, {num(fit.slot_target.protein_g, 0, "g")}{" "}
            Protein. Die Balken zeigen die gewählte Portion ({factorText(factor)}).
          </p>
          <MacroBars
            scaled={{
              kcal: recipe.per_serving.kcal * factor,
              protein_g: recipe.per_serving.protein_g * factor,
              fat_g: recipe.per_serving.fat_g * factor,
              carb_g: recipe.per_serving.carb_g * factor,
            }}
            target={fit.slot_target}
          />
          {Math.abs(factor - fit.factor) > 0.001 && (
            <p className="muted rc-sub">
              Passung und Hinweise des Dienstes gelten für die {factorText(fit.factor)}.
            </p>
          )}
          {fit.notes.length > 0 && (
            <ul aria-label="Hinweise zur Passung">
              {fit.notes.map((n, i) => (
                <li key={i}>{n}</li>
              ))}
            </ul>
          )}
        </Card>
      )}

      <NutritionCard
        recipe={recipe}
        factor={factor}
        onFactor={setChosenFactor}
        fitFactor={fit ? fit.factor : null}
        onUseFit={() => setChosenFactor(null)}
      />
      <SatietyCard recipe={recipe} />
      <LinesCard lines={recipe.lines} onAssigned={() => q.reload()} />

      {recipe.instructions && (
        <Card title="Anleitung">
          <p className="rc-pre">{recipe.instructions}</p>
        </Card>
      )}
    </>
  );
}
