import { useState } from "react";
import { FormShell } from "../../components/crud";
import { NumberField, TextField } from "../../ui";
import { IngredientPicker, type IngredientRef } from "../Ingredients/IngredientPicker";
import type { ComponentOut, VariantIn, VariantOut } from "./types";

type Props = {
  component: ComponentOut;
  item?: VariantOut;
  onSave: (input: VariantIn) => Promise<unknown>;
  onCancel: () => void;
};

/** Variante einer Komponente: Name, optional andere Zutat, Gramm je Einheit (z. B. 1 Ei = 60 g). */
export function VariantForm({ component, item, onSave, onCancel }: Props) {
  const [name, setName] = useState(item?.name ?? "");
  const [ingredient, setIngredient] = useState<IngredientRef | null>(
    item ? { id: item.ingredient_id, name: item.ingredient_name } : null,
  );
  const [gpu, setGpu] = useState<number | null>(item?.grams_per_unit ?? null);

  function validate(): string | null {
    if (name.trim() === "") return "Bitte einen Namen angeben.";
    if (gpu !== null && (gpu <= 0 || gpu > 10000)) return "Gramm je Einheit müssen zwischen 0 und 10.000 liegen.";
    return null;
  }

  return (
    <FormShell
      title={item ? `Variante bearbeiten: ${item.name}` : `Variante für ${component.name} anlegen`}
      submitLabel={item ? "Speichern" : "Anlegen"}
      onSubmit={() =>
        onSave({
          name: name.trim(),
          ...(ingredient ? { ingredient_id: ingredient.id } : {}),
          grams_per_unit: gpu,
        })
      }
      onCancel={onCancel}
      validate={validate}
    >
      <TextField label="Name der Variante" value={name} onChange={setName} maxLength={120} required hint="z. B. Stück, Scheibe, Rührei." />
      <IngredientPicker
        label="Zutat der Variante"
        value={ingredient}
        onChange={setIngredient}
        emptyText={`Wie die Komponente (${component.ingredient_name})`}
        clearable={!item}
        startOpen={false}
      />
      <NumberField
        label="Gramm je Einheit"
        unit="g"
        value={gpu}
        onChange={setGpu}
        min={0}
        step="any"
        hint="z. B. 1 Ei = 60 g. Damit rechnet der Rechner in Stück. Leer = nur in Gramm."
      />
    </FormShell>
  );
}
