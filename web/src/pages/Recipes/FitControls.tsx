import { Link } from "react-router-dom";
import { Alert, Card, SelectField, Spinner, TextField } from "../../ui";
import type { SlotChoice, SlotContext } from "./hooks";
import { SLOT_NAMES } from "./types";
import "./Recipes.css";

/** Auswahl von Datum und Mahlzeit für „Passt ins Tagesziel“, inklusive Hinweisen, wenn das Ziel fehlt. */
export function FitControls({ ctx }: { ctx: SlotContext }) {
  const options = [
    { value: "none", label: "Ohne Passung" },
    ...ctx.slots.map((s) => ({ value: s, label: SLOT_NAMES[s] })),
  ];
  return (
    <Card title="Passt ins Tagesziel">
      <div className="rc-filters">
        <TextField
          label="Datum für das Tagesziel"
          type="date"
          value={ctx.date}
          onChange={ctx.setDate}
        />
        <SelectField
          label="Mahlzeit"
          value={ctx.slot ?? "none"}
          onChange={(v) => ctx.setChoice(v as SlotChoice)}
          options={options}
          disabled={ctx.loading || ctx.slots.length === 0}
          hint={ctx.slot ? "Zeigt, wie gut ein Rezept zum Ziel dieser Mahlzeit passt." : undefined}
        />
      </div>
      {ctx.loading && <Spinner label="Berechne Tagesziel …" />}
      {!ctx.loading && !ctx.date && <Alert kind="info">Bitte ein Datum wählen, um die Passung zu sehen.</Alert>}
      {!ctx.loading && ctx.error && ctx.error.status === 422 && (
        <Alert kind="warn">
          <strong>Das Tagesziel kann noch nicht berechnet werden.</strong>
          <br />
          {ctx.error.message}
          <br />
          Ohne Tagesziel gibt es keine Passung. Tragen Sie ein Gewicht auf der Seite <Link to="/ziele">Tagesziel</Link>{" "}
          ein oder holen Sie Gesundheitsdaten über die <Link to="/importe">Importe</Link>.
        </Alert>
      )}
      {!ctx.loading && ctx.error && ctx.error.status !== 422 && <Alert kind="error">{ctx.error.message}</Alert>}
      {!ctx.loading && ctx.targets && ctx.slots.length === 0 && (
        <Alert kind="info">Für diesen Tag hat keine Mahlzeit einen Anteil am Tagesziel.</Alert>
      )}
    </Card>
  );
}
