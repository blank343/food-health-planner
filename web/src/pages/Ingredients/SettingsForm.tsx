import { useState } from "react";
import { FormShell } from "../../components/crud";
import { CheckField, NumberField } from "../../ui";
import type { IngredientDetail, IngredientPatch } from "./labels";

type Props = {
  item: IngredientDetail;
  onSave: (patch: IngredientPatch) => Promise<unknown>;
  onCancel: () => void;
};

/** Einstellungen importierter Zutaten (BLS, Open Food Facts): Name und Nährwerte bleiben unverändert. */
export function SettingsForm({ item, onSave, onCancel }: Props) {
  const [hidden, setHidden] = useState(item.hidden);
  const [potassiumSalt, setPotassiumSalt] = useState(item.is_potassium_salt);
  const [density, setDensity] = useState<number | null>(item.density_g_per_ml);
  const [pieceG, setPieceG] = useState<number | null>(item.piece_g);
  const [shelf, setShelf] = useState<number | null>(item.shelf_days);

  function validate(): string | null {
    if (density !== null && density <= 0) return "Die Dichte muss größer als 0 sein.";
    if (pieceG !== null && pieceG <= 0) return "Das Stückgewicht muss größer als 0 sein.";
    if (shelf !== null && (shelf < 0 || !Number.isInteger(shelf))) return "Die Haltbarkeit muss eine ganze Zahl von Tagen sein.";
    return null;
  }

  return (
    <FormShell
      title="Einstellungen"
      onSubmit={() =>
        onSave({
          hidden,
          is_potassium_salt: potassiumSalt,
          density_g_per_ml: density,
          piece_g: pieceG,
          shelf_days: shelf,
        })
      }
      onCancel={onCancel}
      validate={validate}
    >
      <p className="muted">Name und Nährwerte importierter Zutaten lassen sich nicht ändern.</p>
      <CheckField label="Ausgeblendet" checked={hidden} onChange={setHidden} hint="Erscheint nicht in der Standardsuche." />
      <CheckField
        label="Kaliumsalz (Salzersatz)"
        checked={potassiumSalt}
        onChange={setPotassiumSalt}
        hint="Markiert die Zutat für Ernährungsregeln zu Kaliumsalz."
      />
      <div className="crud-form-grid">
        <NumberField label="Dichte" unit="g/ml" value={density} onChange={setDensity} min={0} step="any" />
        <NumberField label="Stückgewicht" unit="g" value={pieceG} onChange={setPieceG} min={0} step="any" />
        <NumberField label="Haltbarkeit" unit="Tage" value={shelf} onChange={setShelf} min={0} step={1} />
      </div>
    </FormShell>
  );
}
