import { numDe } from "../../components/crud";
import { num } from "../../format";
import { Alert, Button, Card, Field, Progress, Table } from "../../ui";
import { MICRO_ROWS, SATIETY_PART_LABELS, factorText, scaleNutrients } from "./format";
import { SatietyMeter } from "./parts";
import type { RecipeDetail } from "./types";
import "./Recipes.css";

export const MIN_FACTOR = 0.5;
export const MAX_FACTOR = 2;

type RowDef = { label: string; unit: string; digits: number; get: (n: RecipeDetail["total"]) => number | undefined };

function rowsFor(recipe: RecipeDetail): RowDef[] {
  const micros = new Set([...Object.keys(recipe.per_serving.micros), ...Object.keys(recipe.total.micros)]);
  return [
    { label: "Kalorien", unit: "kcal", digits: 0, get: (n) => n.kcal },
    { label: "Protein", unit: "g", digits: 1, get: (n) => n.protein_g },
    { label: "Fett", unit: "g", digits: 1, get: (n) => n.fat_g },
    { label: "Kohlenhydrate", unit: "g", digits: 1, get: (n) => n.carb_g },
    { label: "Ballaststoffe", unit: "g", digits: 1, get: (n) => n.fiber_g },
    { label: "Salz", unit: "g", digits: 2, get: (n) => n.salt_g },
    ...MICRO_ROWS.filter((m) => micros.has(m.key)).map((m) => ({
      label: m.label,
      unit: m.unit,
      digits: 1,
      get: (n: RecipeDetail["total"]) => n.micros[m.key],
    })),
  ];
}

type Props = {
  recipe: RecipeDetail;
  factor: number;
  onFactor: (f: number) => void;
  /** Faktor der Passung, falls vorhanden: Schaltfläche „Auf Mahlzeit abstimmen“ */
  fitFactor: number | null;
  onUseFit: () => void;
};

/** Nährwerte je Portion (mit Portionsregler) und gesamt, dazu Datenabdeckung. */
export function NutritionCard({ recipe, factor, onFactor, fitFactor, onUseFit }: Props) {
  const per = scaleNutrients(recipe.per_serving, factor);
  const rows = rowsFor(recipe);
  const coveragePct = Math.round(recipe.coverage * 100);
  const incomplete = recipe.coverage < 0.995;
  const scaled = Math.abs(factor - 1) > 0.001;
  return (
    <Card title="Nährwerte">
      <Field
        label="Portionsfaktor"
        hint={`Rechnet die Werte je Portion um (${num(MIN_FACTOR, 1)} bis ${num(MAX_FACTOR, 1)}).`}
      >
        {(id, d) => (
          <input
            id={id}
            className="rc-range"
            type="range"
            min={MIN_FACTOR}
            max={MAX_FACTOR}
            step={0.05}
            value={factor}
            aria-describedby={d}
            aria-valuetext={factorText(factor)}
            onChange={(e) => onFactor(Math.round(Number(e.target.value) * 100) / 100)}
          />
        )}
      </Field>
      <div className="row rc-factor">
        <output aria-live="polite">
          {factorText(factor)} · {num(recipe.serving_weight_g * factor, 0, "g")}
        </output>
        <Button onClick={() => onFactor(1)} disabled={!scaled}>
          Eine Portion
        </Button>
        {fitFactor !== null && (
          <Button onClick={onUseFit} disabled={Math.abs(factor - fitFactor) < 0.001}>
            Auf Mahlzeit abstimmen
          </Button>
        )}
      </div>

      {incomplete ? (
        <Alert kind="warn">
          <strong>Datenabdeckung {coveragePct} %:</strong> Für einen Teil der Zutaten fehlen Nährwerte oder Gewichte,
          die Summen sind deshalb zu niedrig.
          {recipe.missing.length > 0 && <> Es fehlen: {recipe.missing.join(", ")}.</>}
        </Alert>
      ) : (
        <p className="muted">Datenabdeckung {coveragePct} %: Alle Zutaten haben Werte.</p>
      )}

      <Table>
        <thead>
          <tr>
            <th scope="col">Nährwert</th>
            <th scope="col">Je Portion{scaled ? ` (${factorText(factor)})` : ""}</th>
            <th scope="col">Gesamtes Rezept</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.label}>
              <th scope="row">{r.label}</th>
              <td>{num(r.get(per), r.digits, r.unit)}</td>
              <td>{num(r.get(recipe.total), r.digits, r.unit)}</td>
            </tr>
          ))}
        </tbody>
      </Table>
      <p className="muted">
        {numDe(recipe.servings)} {recipe.servings === 1 ? "Portion" : "Portionen"} · Gesamtgewicht {num(recipe.total_weight_g, 0, "g")}
        {recipe.energy_density_kcal_per_100g !== null &&
          ` · ${num(recipe.energy_density_kcal_per_100g, 0, "kcal")} je 100 g`}
      </p>
    </Card>
  );
}

/** Sättigung mit den Teilwerten (0–100 %). */
export function SatietyCard({ recipe }: { recipe: RecipeDetail }) {
  const parts = Object.entries(recipe.satiety.parts);
  return (
    <Card title="Sättigung">
      <SatietyMeter score={recipe.satiety.score} />
      {parts.length > 0 && (
        <ul className="rc-parts" aria-label="Teilwerte der Sättigung">
          {parts.map(([key, value]) => (
            <li key={key}>
              <span>{SATIETY_PART_LABELS[key] ?? key}</span>
              <span className="muted">{Math.round(value * 100)} %</span>
              <Progress fraction={value} label={SATIETY_PART_LABELS[key] ?? key} />
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
