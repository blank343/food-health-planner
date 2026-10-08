import { useState } from "react";
import { FormShell, optText } from "../../components/crud";
import { CheckField, NumberField, TextField } from "../../ui";
import { type IngredientDetail, type IngredientIn, MICRO_KEYS, MICRO_LABELS } from "./labels";
import "./Ingredients.css";

type Props = {
  /** Vorhandene manuelle Zutat zum Bearbeiten; ohne Angabe wird eine neue angelegt. */
  item?: IngredientDetail;
  onSave: (input: IngredientIn) => Promise<unknown>;
  onCancel: () => void;
};

type Num = number | null;

/** Formular für manuelle Zutaten: Name, Kategorie, Nährwerte je 100 g, Mikronährstoffe, Dichte, Stückgewicht. */
export function IngredientForm({ item, onSave, onCancel }: Props) {
  const n = item?.nutrients;
  const [name, setName] = useState(item?.name ?? "");
  const [category, setCategory] = useState(item?.category ?? "");
  const [kcal, setKcal] = useState<Num>(n?.kcal ?? null);
  const [protein, setProtein] = useState<Num>(n?.protein_g ?? null);
  const [fat, setFat] = useState<Num>(n?.fat_g ?? null);
  const [carb, setCarb] = useState<Num>(n?.carb_g ?? null);
  const [fiber, setFiber] = useState<Num>(n?.fiber_g ?? null);
  const [salt, setSalt] = useState<Num>(n?.salt_g ?? null);
  const [micros, setMicros] = useState<Record<string, Num>>(() =>
    Object.fromEntries(MICRO_KEYS.map((k) => [k, n?.micros?.[k] ?? null])),
  );
  const [density, setDensity] = useState<Num>(item?.density_g_per_ml ?? null);
  const [pieceG, setPieceG] = useState<Num>(item?.piece_g ?? null);
  const [shelf, setShelf] = useState<Num>(item?.shelf_days ?? null);
  const [isFish, setIsFish] = useState(item?.is_fish ?? false);
  const [potassiumSalt, setPotassiumSalt] = useState(item?.is_potassium_salt ?? false);
  const [hidden, setHidden] = useState(item?.hidden ?? false);

  function validate(): string | null {
    if (name.trim() === "") return "Bitte einen Namen angeben.";
    const nums: [string, Num, number][] = [
      ["Kalorien", kcal, 900],
      ["Protein", protein, 100],
      ["Fett", fat, 100],
      ["Kohlenhydrate", carb, 100],
      ["Ballaststoffe", fiber, 100],
      ["Salz", salt, 100],
    ];
    for (const [label, v, max] of nums) {
      if (v !== null && (v < 0 || v > max)) return `${label}: Bitte einen Wert zwischen 0 und ${max} angeben.`;
    }
    if ((protein ?? 0) + (fat ?? 0) + (carb ?? 0) > 100.5) {
      return "Protein, Fett und Kohlenhydrate zusammen dürfen 100 g je 100 g nicht übersteigen.";
    }
    for (const k of MICRO_KEYS) {
      const v = micros[k] ?? null;
      if (v !== null && v < 0) return `${MICRO_LABELS[k] ?? k}: Der Wert darf nicht negativ sein.`;
    }
    if (density !== null && density <= 0) return "Die Dichte muss größer als 0 sein.";
    if (pieceG !== null && pieceG <= 0) return "Das Stückgewicht muss größer als 0 sein.";
    if (shelf !== null && (shelf < 0 || !Number.isInteger(shelf))) return "Die Haltbarkeit muss eine ganze Zahl von Tagen sein.";
    return null;
  }

  async function submit() {
    // Unbekannte Schlüssel der bestehenden Zutat bleiben erhalten.
    const kept = Object.fromEntries(Object.entries(n?.micros ?? {}).filter(([k]) => !MICRO_KEYS.includes(k)));
    const known = Object.fromEntries(MICRO_KEYS.flatMap((k) => (micros[k] === null || micros[k] === undefined ? [] : [[k, micros[k] as number]])));
    await onSave({
      name: name.trim(),
      category: optText(category),
      kcal_100: kcal,
      protein_100: protein,
      fat_100: fat,
      carb_100: carb,
      fiber_100: fiber,
      salt_100: salt,
      micros: { ...kept, ...known },
      density_g_per_ml: density,
      piece_g: pieceG,
      is_fish: isFish,
      is_potassium_salt: potassiumSalt,
      shelf_days: shelf,
      hidden,
    });
  }

  return (
    <FormShell
      title={item ? "Zutat bearbeiten" : "Zutat anlegen"}
      submitLabel={item ? "Speichern" : "Anlegen"}
      onSubmit={submit}
      onCancel={onCancel}
      validate={validate}
    >
      <TextField label="Name" value={name} onChange={setName} maxLength={200} required />
      <TextField label="Kategorie" value={category} onChange={setCategory} maxLength={60} hint="Optional, z. B. Milchprodukte." />
      <h3>Nährwerte je 100 g</h3>
      <div className="crud-form-grid">
        <NumberField label="Kalorien" unit="kcal" value={kcal} onChange={setKcal} min={0} step="any" />
        <NumberField label="Protein" unit="g" value={protein} onChange={setProtein} min={0} step="any" />
        <NumberField label="Fett" unit="g" value={fat} onChange={setFat} min={0} step="any" />
        <NumberField label="Kohlenhydrate" unit="g" value={carb} onChange={setCarb} min={0} step="any" />
        <NumberField label="Ballaststoffe" unit="g" value={fiber} onChange={setFiber} min={0} step="any" />
        <NumberField label="Salz" unit="g" value={salt} onChange={setSalt} min={0} step="any" hint="Salz, nicht Natrium." />
      </div>
      <details className="micros">
        <summary>Mikronährstoffe je 100 g (optional)</summary>
        <div className="crud-form-grid">
          {MICRO_KEYS.map((k) => (
            <NumberField
              key={k}
              label={MICRO_LABELS[k] ?? k}
              value={micros[k] ?? null}
              onChange={(v) => setMicros((m) => ({ ...m, [k]: v }))}
              min={0}
              step="any"
            />
          ))}
        </div>
      </details>
      <h3>Umrechnung</h3>
      <div className="crud-form-grid">
        <NumberField label="Dichte" unit="g/ml" value={density} onChange={setDensity} min={0} step="any" hint="Für Angaben in ml, EL, TL." />
        <NumberField label="Stückgewicht" unit="g" value={pieceG} onChange={setPieceG} min={0} step="any" hint="Gewicht eines Stücks." />
        <NumberField label="Haltbarkeit" unit="Tage" value={shelf} onChange={setShelf} min={0} step={1} />
      </div>
      <CheckField label="Fisch" checked={isFish} onChange={setIsFish} hint="Zählt für die Regel zu fettem Fisch." />
      <CheckField
        label="Kaliumsalz (Salzersatz)"
        checked={potassiumSalt}
        onChange={setPotassiumSalt}
        hint="Markiert die Zutat für Ernährungsregeln zu Kaliumsalz."
      />
      <CheckField label="Ausgeblendet" checked={hidden} onChange={setHidden} hint="Erscheint nicht in der Standardsuche." />
    </FormShell>
  );
}
