// Kleine Darstellungsbausteine der Rezeptseiten: Sterne, Favorit, Balken, Fit-Anzeige, Sättigung.
import { num } from "../../format";
import { Badge } from "../../ui";
import { deviationText, factorText, fitLevel, macroShares, satietyLevel } from "./format";
import type { Macro } from "./types";
import "./Recipes.css";

/**
 * Bewertung 1–5. Ein Klick auf den aktuellen Stern nimmt die Bewertung zurück (`onChange(null)`).
 * Jeder Stern ist eine Schaltfläche mit Textalternative („3 von 5 Sternen“).
 */
export function Stars({
  value,
  onChange,
  label,
  disabled,
}: {
  value: number | null;
  onChange: (rating: number | null) => void;
  label: string;
  disabled?: boolean;
}) {
  return (
    <div className="rc-stars" role="group" aria-label={label}>
      {[1, 2, 3, 4, 5].map((i) => (
        <button
          key={i}
          type="button"
          className={`rc-star${value !== null && i <= value ? " on" : ""}`}
          aria-label={`${i} von 5 Sternen`}
          aria-pressed={value === i}
          disabled={disabled}
          onClick={() => onChange(value === i ? null : i)}
        >
          <span aria-hidden="true">{value !== null && i <= value ? "★" : "☆"}</span>
        </button>
      ))}
    </div>
  );
}

export function FavoriteButton({
  favorite,
  title,
  onToggle,
  disabled,
}: {
  favorite: boolean;
  title: string;
  onToggle: () => void;
  disabled?: boolean;
}) {
  return (
    <button
      type="button"
      className={`rc-fav${favorite ? " on" : ""}`}
      aria-pressed={favorite}
      aria-label={favorite ? `Favorit entfernen: ${title}` : `Als Favorit markieren: ${title}`}
      disabled={disabled}
      onClick={onToggle}
    >
      <span aria-hidden="true">{favorite ? "★" : "☆"}</span>
      <span className="rc-fav-text" aria-hidden="true">
        Favorit
      </span>
    </button>
  );
}

const BAR_MAX = 150; // Skala der Balken: 0–150 % des Ziels, Markierung bei 100 %

/** Balken je Makro: Anteil der (skalierten) Portion am Slot-Ziel, mit Abweichung als Text. */
export function MacroBars({ scaled, target }: { scaled: Macro; target: Macro }) {
  const rows = macroShares(scaled, target);
  return (
    <ul className="rc-macros" aria-label="Anteil am Ziel der Mahlzeit">
      {rows.map((r) => {
        const pct = r.pct === null ? 0 : Math.round(r.pct);
        const state = r.deviation === null ? "" : r.deviation > 10 ? " over" : r.deviation < -10 ? " under" : "";
        const text = deviationText(r.deviation);
        return (
          <li key={r.key}>
            <div className="rc-macro-head">
              <span>{r.label}</span>
              <span>
                {num(r.value)} von {num(r.target, 0, r.unit)} · {text}
              </span>
            </div>
            <div
              className={`rc-bar${state}`}
              role="meter"
              aria-label={`${r.label}: ${pct} % des Ziels`}
              aria-valuemin={0}
              aria-valuemax={BAR_MAX}
              aria-valuenow={Math.min(pct, BAR_MAX)}
              aria-valuetext={`${pct} % des Ziels, ${text}`}
            >
              <span style={{ width: `${Math.min(pct, BAR_MAX) / (BAR_MAX / 100)}%` }} />
            </div>
          </li>
        );
      })}
    </ul>
  );
}

/** Fit-Score als Zahl mit Einstufung (Text), dazu der Portionsfaktor. */
export function FitSummary({ score, factor }: { score: number; factor: number | null | undefined }) {
  const level = fitLevel(score);
  return (
    <div className="rc-fit-summary">
      <Badge kind={level.kind}>
        Passung {num(score)} von 100: {level.label}
      </Badge>
      {factor !== null && factor !== undefined && <span className="muted">{factorText(factor)}</span>}
    </div>
  );
}

/** Sättigung als kleiner Balken mit Zahl und Einstufung als Text. */
export function SatietyMeter({ score }: { score: number }) {
  const pct = Math.round(Math.max(0, Math.min(100, score)));
  return (
    <div className="rc-satiety">
      <span>
        Sättigung {pct} von 100 ({satietyLevel(score)})
      </span>
      <div
        className="rc-bar"
        role="meter"
        aria-label={`Sättigung: ${pct} von 100`}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={pct}
        aria-valuetext={`${pct} von 100, ${satietyLevel(score)}`}
      >
        <span style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}
