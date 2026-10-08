import { Link } from "react-router-dom";
import { dateDe, num } from "../../format";
import { numDe } from "../../components/crud";
import { Alert, Badge, Card, Table } from "../../ui";
import { slotName, type MealFitOut, type MealOut } from "./types";
import "../Ingredients/Ingredients.css";

function Tile({ label, value, hint, className }: { label: string; value: string; hint?: string; className?: string }) {
  return (
    <div className={`stat card ${className ?? ""}`.trim()} style={{ marginBottom: 0 }}>
      <div className="value">{value}</div>
      <div className="label">{label}</div>
      {hint && <small>{hint}</small>}
    </div>
  );
}

const weight = (g: number) => (g >= 1000 ? num(g / 1000, 2, "kg") : num(g, 0, "g"));

/** Kompakte Leiste, die beim Scrollen oben bleibt: so sieht man beim Verschieben der Regler die Summe. */
export function SumBar({ meal, pending }: { meal: MealOut; pending: boolean }) {
  const t = meal.total;
  return (
    <div className="sum-bar" aria-hidden="true" data-pending={pending || undefined}>
      <span>{num(t.kcal, 0, "kcal")}</span>
      <span>
        <small>Protein</small> {num(t.protein_g, 0, "g")}
      </span>
      <span style={{ color: "var(--warn)" }}>
        <small>Salz</small> {num(t.salt_g, 1, "g")}
      </span>
      <span>
        <small>Gewicht</small> {weight(meal.weight_g)}
      </span>
    </div>
  );
}

function Totals({ meal }: { meal: MealOut }) {
  const t = meal.total;
  return (
    <section aria-label="Summen der Mahlzeit">
      <div className="stat-grid">
        <Tile label="Kalorien" value={num(t.kcal, 0, "kcal")} />
        <Tile label="Protein" value={num(t.protein_g, 1, "g")} />
        <Tile label="Fett" value={num(t.fat_g, 1, "g")} />
        <Tile label="Kohlenhydrate" value={num(t.carb_g, 1, "g")} />
        <Tile label="Ballaststoffe" value={num(t.fiber_g, 1, "g")} />
        <Tile label="Salz" value={num(t.salt_g, 2, "g")} className="stat-salt" hint="zählt besonders" />
        <Tile label="Gewicht der Mahlzeit" value={weight(meal.weight_g)} />
        <Tile label="Sättigung" value={`${num(meal.satiety.score, 0)} von 100`} />
        <Tile
          label="Energiedichte"
          value={meal.energy_density_kcal_per_100g === null ? "–" : num(meal.energy_density_kcal_per_100g, 0, "kcal/100 g")}
        />
      </div>
      {meal.missing.length > 0 && (
        <Alert kind="warn">
          Für diese Zutaten fehlen Nährwerte, die Summen sind dadurch zu niedrig: {meal.missing.join(", ")}.
        </Alert>
      )}
      {meal.notes.length > 0 && (
        <Alert kind="info">
          <ul style={{ margin: 0, paddingLeft: 18 }}>
            {meal.notes.map((n, i) => (
              <li key={i}>{n}</li>
            ))}
          </ul>
        </Alert>
      )}
    </section>
  );
}

function Lines({ meal }: { meal: MealOut }) {
  return (
    <Card title="Beitrag je Komponente">
      <Table>
        <thead>
          <tr>
            <th scope="col">Komponente</th>
            <th scope="col" className="num">Menge</th>
            <th scope="col" className="num">kcal</th>
            <th scope="col" className="num">Protein</th>
            <th scope="col" className="num">Fett</th>
            <th scope="col" className="num">KH</th>
            <th scope="col" className="num">Ballast.</th>
            <th scope="col" className="num">Salz</th>
          </tr>
        </thead>
        <tbody>
          {meal.lines.map((l, i) => (
            <tr key={`${l.component_id}-${l.variant_id ?? 0}-${i}`}>
              <th scope="row">
                {l.component_name}
                {l.variant_name && <small className="muted"> ({l.variant_name})</small>}
                <br />
                <small className="muted">{l.ingredient_name}</small>
              </th>
              <td className="num">
                {num(l.grams, 0, "g")}
                {l.units !== null && (
                  <>
                    <br />
                    <small className="muted">
                      {numDe(l.units)} {l.variant_name ?? "Stück"}
                    </small>
                  </>
                )}
              </td>
              <td className="num">{num(l.nutrients.kcal, 0)}</td>
              <td className="num">{num(l.nutrients.protein_g, 1)}</td>
              <td className="num">{num(l.nutrients.fat_g, 1)}</td>
              <td className="num">{num(l.nutrients.carb_g, 1)}</td>
              <td className="num">{num(l.nutrients.fiber_g, 1)}</td>
              <td className="num">{num(l.nutrients.salt_g, 2)}</td>
            </tr>
          ))}
        </tbody>
      </Table>
    </Card>
  );
}

const MACROS: { key: "kcal" | "protein_g" | "fat_g" | "carb_g"; label: string; unit: string }[] = [
  { key: "kcal", label: "Kalorien", unit: "kcal" },
  { key: "protein_g", label: "Protein", unit: "g" },
  { key: "fat_g", label: "Fett", unit: "g" },
  { key: "carb_g", label: "Kohlenhydrate", unit: "g" },
];

function FitBar({ label, unit, actual, target }: { label: string; unit: string; actual: number; target: number }) {
  const pct = target > 0 ? (actual / target) * 100 : null;
  const shown = pct === null ? null : Math.round(pct);
  const cls = pct === null ? "" : pct > 110 ? "over" : pct < 90 ? "low" : "";
  return (
    <div className="fit-row">
      <div className="fit-head">
        <span>{label}</span>
        <span>
          {num(actual, 0, unit)} von {num(target, 0, unit)}
          {shown !== null && ` (${shown} %)`}
        </span>
      </div>
      <div
        className={`fit-bar ${cls}`.trim()}
        role="progressbar"
        aria-label={`${label}: Anteil am Slot-Ziel`}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={shown === null ? 0 : Math.min(100, shown)}
        aria-valuetext={shown === null ? "kein Ziel" : `${shown} % des Ziels`}
      >
        <span style={{ width: `${pct === null ? 0 : Math.min(100, pct)}%` }} />
      </div>
    </div>
  );
}

function Fit({ meal, fit }: { meal: MealOut; fit: MealFitOut }) {
  const score = fit.fit_score;
  const kind = score >= 80 ? "ok" : score >= 60 ? "warn" : "error";
  return (
    <Card title={`Passung zum Ziel: ${slotName(fit.slot)} am ${dateDe(fit.date)}`}>
      <p>
        Passung <Badge kind={kind}>{num(score, 0)} von 100</Badge>
      </p>
      {MACROS.map((m) => (
        <FitBar key={m.key} label={m.label} unit={m.unit} actual={meal.total[m.key]} target={fit.target[m.key]} />
      ))}
      {fit.warnings.map((w, i) => (
        <Alert key={`${w.code}-${i}`} kind={w.severity === "block" ? "error" : w.severity === "warn" ? "warn" : "info"}>
          {w.message}
        </Alert>
      ))}
      {fit.notes.length > 0 && (
        <ul>
          {fit.notes.map((n, i) => (
            <li key={i}>{n}</li>
          ))}
        </ul>
      )}
      <p className="muted">
        Das ist nur eine Anzeige: Die App schlägt hier keine Mengen vor. Das macht später der Planer.
      </p>
    </Card>
  );
}

type Props = {
  meal: MealOut;
  /** Meldung, wenn die Passung nicht berechnet werden konnte. */
  fitIssue: string | null;
  slotRequested: boolean;
};

/** Summen, Posten und Passung einer berechneten Mahlzeit. */
export function MealResult({ meal, fitIssue, slotRequested }: Props) {
  return (
    <>
      <Totals meal={meal} />
      <Lines meal={meal} />
      {meal.fit && <Fit meal={meal} fit={meal.fit} />}
      {fitIssue && (
        <Alert kind="warn">
          <strong>Die Passung zum Tagesziel kann noch nicht berechnet werden.</strong>
          <br />
          {fitIssue}
          <br />
          Prüfe unter <Link to="/ziele">Tagesziel</Link>, ob ein aktuelles Gewicht und die Körpergröße vorliegen.
        </Alert>
      )}
      {!meal.fit && !fitIssue && !slotRequested && (
        <p className="muted">Wähle einen Slot, um die Passung zum Tagesziel zu sehen.</p>
      )}
    </>
  );
}
