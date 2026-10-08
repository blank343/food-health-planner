import { Link } from "react-router-dom";
import { numDe } from "../../components/crud";
import { num } from "../../format";
import { Badge } from "../../ui";
import { minutesText, scaleMacro, weightText } from "./format";
import { FavoriteButton, FitSummary, MacroBars, SatietyMeter, Stars } from "./parts";
import { type Macro, type RecipeCard, SLOT_NAMES, isSlot } from "./types";
import "./Recipes.css";

export const detailLink = (id: number) => ({ search: `?rezept=${id}` });

export function StatusBadge({ status }: { status: string }) {
  if (status === "needs_review") return <Badge kind="warn">Prüfen</Badge>;
  if (status === "draft") return <Badge>Entwurf</Badge>;
  return null;
}

type Props = {
  card: RecipeCard;
  /** Mahlzeit der Passung; zusammen mit `target` aus dem Tagesziel */
  fitActive: boolean;
  target: Macro | undefined;
  busy: boolean;
  onRate: (rating: number | null) => void;
  onFavorite: () => void;
};

export function RecipeCardView({ card, fitActive, target, busy, onRate, onFavorite }: Props) {
  const coveragePct = Math.round(card.coverage * 100);
  const slotNames = card.tag.slot_types.filter(isSlot).map((s) => SLOT_NAMES[s]);
  const showFit = fitActive && target !== undefined && card.fit_score !== null && card.fit_score !== undefined;
  const factor = card.fit_factor ?? 1;
  return (
    <li className="rc-card">
      <div className="rc-card-head">
        <h3>
          <Link to={detailLink(card.id)}>{card.title}</Link>
        </h3>
        <FavoriteButton favorite={card.favorite} title={card.title} onToggle={onFavorite} disabled={busy} />
      </div>

      <div className="crud-meta">
        <StatusBadge status={card.status} />
        {slotNames.map((n) => (
          <Badge key={n}>{n}</Badge>
        ))}
        {card.tag.warm && <Badge>warm</Badge>}
      </div>

      <p className="rc-facts">
        <strong>{num(card.kcal, 0, "kcal")}</strong> · <strong>{num(card.protein_g, 0, "g")}</strong> Protein{" "}
        <span className="muted">je Portion</span>
      </p>
      <p className="muted rc-sub">
        Portion {weightText(card.serving_weight_g)} · Zeit {minutesText(card.prep_min, card.cook_min)}
      </p>

      <SatietyMeter score={card.satiety_score} />
      {card.coverage < 0.995 && (
        <p className="muted rc-sub">Nährwerte unvollständig: nur {coveragePct} % der Zutaten haben Werte.</p>
      )}

      <div className="rc-rating">
        <Stars value={card.my_rating} onChange={onRate} label={`Eigene Bewertung für ${card.title}`} disabled={busy} />
        {card.avg_rating !== null && <span className="muted">Ø {numDe(card.avg_rating)}</span>}
      </div>

      {showFit && target && card.fit_score !== null && card.fit_score !== undefined && (
        <div className="rc-fit">
          <FitSummary score={card.fit_score} factor={card.fit_factor} />
          <MacroBars
            scaled={scaleMacro(
              { kcal: card.kcal, protein_g: card.protein_g, fat_g: card.fat_g, carb_g: card.carb_g },
              factor,
            )}
            target={target}
          />
        </div>
      )}
    </li>
  );
}
