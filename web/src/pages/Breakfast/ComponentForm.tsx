import { useState } from "react";
import { FormShell, withPlaceholder } from "../../components/crud";
import { CheckField, NumberField, SelectField, TextField } from "../../ui";
import { IngredientPicker, type IngredientRef } from "../Ingredients/IngredientPicker";
import { type ComponentIn, type ComponentOut, KIND_LABELS, KIND_ORDER, isKind } from "./types";

type Props = {
  item?: ComponentOut;
  onSave: (input: ComponentIn) => Promise<unknown>;
  onCancel: () => void;
};

/** Komponente anlegen oder bearbeiten: Name, Art, Zutat (per Suche), Mengenspanne, übliche Menge. */
export function ComponentForm({ item, onSave, onCancel }: Props) {
  const [name, setName] = useState(item?.name ?? "");
  const [kind, setKind] = useState<string>(item?.kind ?? "");
  const [ingredient, setIngredient] = useState<IngredientRef | null>(
    item ? { id: item.ingredient_id, name: item.ingredient_name } : null,
  );
  const [min, setMin] = useState<number | null>(item?.min_g ?? 0);
  const [max, setMax] = useState<number | null>(item?.max_g ?? 300);
  const [step, setStep] = useState<number | null>(item?.step_g ?? 10);
  const [typical, setTypical] = useState<number | null>(item?.typical_g ?? null);
  const [weekend, setWeekend] = useState(item?.weekend_fixed ?? false);
  const [ingredientError, setIngredientError] = useState<string | null>(null);

  function validate(): string | null {
    setIngredientError(null);
    if (name.trim() === "") return "Bitte einen Namen angeben.";
    if (!isKind(kind)) return "Bitte die Art der Komponente wählen.";
    if (!ingredient) {
      setIngredientError("Bitte eine Zutat wählen.");
      return "Bitte eine Zutat wählen.";
    }
    if (min === null || max === null || step === null) return "Mindest-, Höchst- und Schrittmenge sind erforderlich.";
    if (min < 0) return "Die Mindestmenge darf nicht negativ sein.";
    if (max <= 0 || max > 10000) return "Die Höchstmenge muss zwischen 0 und 10.000 g liegen.";
    if (min > max) return "Die Mindestmenge darf nicht größer als die Höchstmenge sein.";
    if (step <= 0) return "Die Schrittweite muss größer als 0 sein.";
    if (typical !== null && (typical < min || typical > max)) {
      return "Die übliche Menge muss zwischen Mindest- und Höchstmenge liegen.";
    }
    return null;
  }

  async function submit() {
    if (!isKind(kind) || !ingredient || min === null || max === null || step === null) return;
    await onSave({
      name: name.trim(),
      kind,
      ingredient_id: ingredient.id,
      min_g: min,
      max_g: max,
      step_g: step,
      typical_g: typical,
      weekend_fixed: weekend,
    });
  }

  return (
    <FormShell
      title={item ? "Komponente bearbeiten" : "Komponente anlegen"}
      submitLabel={item ? "Speichern" : "Anlegen"}
      onSubmit={submit}
      onCancel={onCancel}
      validate={validate}
    >
      <TextField label="Name" value={name} onChange={setName} maxLength={120} required />
      <SelectField
        label="Art"
        value={kind}
        onChange={setKind}
        options={withPlaceholder(KIND_ORDER.map((k) => ({ value: k, label: KIND_LABELS[k] ?? k })))}
      />
      <IngredientPicker label="Zutat" value={ingredient} onChange={setIngredient} error={ingredientError} />
      <div className="crud-form-grid">
        <NumberField label="Mindestmenge" unit="g" value={min} onChange={setMin} min={0} step="any" />
        <NumberField label="Höchstmenge" unit="g" value={max} onChange={setMax} min={0} step="any" />
        <NumberField label="Schritt" unit="g" value={step} onChange={setStep} min={0} step="any" hint="Schrittweite des Reglers." />
        <NumberField label="Übliche Menge" unit="g" value={typical} onChange={setTypical} min={0} step="any" hint="Startwert im Rechner. Leer = keine." />
      </div>
      <CheckField
        label="Wochenende fest"
        checked={weekend}
        onChange={setWeekend}
        hint="Gehört zum festen Wochenend-Frühstück und wird nicht geplant."
      />
    </FormShell>
  );
}
