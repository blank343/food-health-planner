import { type FormEvent, useState } from "react";
import { api } from "../../api/client";
import type { components } from "../../api/schema";
import { dateDe, kg, num, todayIso } from "../../format";
import { useAction } from "../../hooks/useApi";
import { Alert, Button, Card, NumberField, TextField } from "../../ui";

type ManualIn = components["schemas"]["ManualMeasurementIn"];
type ManualOut = components["schemas"]["ManualMeasurementOut"];

type Errors = { day?: string; weight?: string; fat?: string; lean?: string; form?: string };

/** Prüft die Eingaben mit den gleichen Grenzen wie der Server und liefert deutsche Meldungen. */
export function validateManual(v: {
  day: string;
  weight: number | null;
  fat: number | null;
  lean: number | null;
  today: string;
}): Errors {
  const e: Errors = {};
  if (!v.day) e.day = "Bitte ein Datum wählen.";
  else if (v.day > v.today) e.day = "Das Datum liegt in der Zukunft.";
  if (v.weight !== null && (v.weight < 30 || v.weight > 300)) e.weight = "Das Gewicht muss zwischen 30 und 300 kg liegen.";
  if (v.fat !== null && (v.fat < 2 || v.fat > 60)) e.fat = "Der Körperfettanteil muss zwischen 2 und 60 % liegen.";
  if (v.lean !== null && (v.lean < 20 || v.lean > 200)) e.lean = "Die Magermasse muss zwischen 20 und 200 kg liegen.";
  if (v.weight === null && v.fat === null && v.lean === null) e.form = "Bitte mindestens einen Wert angeben.";
  return e;
}

function summary(r: ManualOut): string {
  const parts = [
    r.weight_kg !== null && `Gewicht ${kg(r.weight_kg)}`,
    r.body_fat_pct !== null && `Körperfett ${num(r.body_fat_pct, 1, "%")}`,
    r.lean_mass_kg !== null && `Magermasse ${kg(r.lean_mass_kg)}`,
  ].filter(Boolean);
  return `Gespeichert für den ${dateDe(r.day)}: ${parts.join(", ")}.`;
}

export default function ManualForm({ onSaved }: { onSaved: () => void }) {
  const [day, setDay] = useState(todayIso());
  const [weight, setWeight] = useState<number | null>(null);
  const [fat, setFat] = useState<number | null>(null);
  const [lean, setLean] = useState<number | null>(null);
  const [errors, setErrors] = useState<Errors>({});
  const [saved, setSaved] = useState<string | null>(null);
  const save = useAction((body: ManualIn) => api<ManualOut>("POST", "/me/health/manual", body));

  async function submit(ev: FormEvent) {
    ev.preventDefault();
    setSaved(null);
    save.clearError();
    const found = validateManual({ day, weight, fat, lean, today: todayIso() });
    setErrors(found);
    if (Object.keys(found).length > 0) return;
    const body: ManualIn = { day };
    if (weight !== null) body.weight_kg = weight;
    if (fat !== null) body.body_fat_pct = fat;
    if (lean !== null) body.lean_mass_kg = lean;
    const res = await save.run(body);
    if (!res) return;
    setSaved(summary(res));
    setWeight(null);
    setFat(null);
    setLean(null);
    onSaved();
  }

  return (
    <Card title="Messwerte von Hand eintragen">
      <p className="muted">
        Ohne Import oder bei ungenauen Waagenwerten: Gewicht und Körperzusammensetzung hier eintragen. Mindestens ein
        Wert ist nötig. Manuelle Werte haben Vorrang vor Importen.
      </p>
      <form onSubmit={(e) => void submit(e)} noValidate>
        {errors.form && <Alert kind="error">{errors.form}</Alert>}
        {save.error && <Alert kind="error">{save.error}</Alert>}
        {saved && <Alert kind="ok">{saved}</Alert>}
        <div className="grid">
          <TextField label="Datum der Messung" type="date" value={day} onChange={setDay} max={todayIso()} error={errors.day} />
          <NumberField label="Gewicht" unit="kg" value={weight} onChange={setWeight} min={30} max={300} step="any" error={errors.weight} />
          <NumberField label="Körperfett" unit="%" value={fat} onChange={setFat} min={2} max={60} step="any" error={errors.fat} hint="optional" />
          <NumberField label="Magermasse" unit="kg" value={lean} onChange={setLean} min={20} max={200} step="any" error={errors.lean} hint="optional" />
        </div>
        <Button type="submit" variant="primary" disabled={save.busy}>
          {save.busy ? "Speichert …" : "Speichern"}
        </Button>
      </form>
    </Card>
  );
}
