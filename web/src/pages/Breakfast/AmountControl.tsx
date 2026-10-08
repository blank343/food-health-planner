import { useEffect, useState } from "react";
import { numDe } from "../../components/crud";
import { clamp, resolve, type Entry, withVariant } from "./amounts";
import type { ComponentOut } from "./types";
import "../Ingredients/Ingredients.css";

type Props = {
  component: ComponentOut;
  entry: Entry;
  onChange: (e: Entry) => void;
};

/** Zahlenfeld mit eigenem Text: Zwischenstände beim Tippen bleiben erhalten, beim Verlassen wird auf die Spanne begrenzt. */
function AmountNumber({
  label,
  value,
  min,
  max,
  step,
  onChange,
}: {
  label: string;
  value: number;
  min: number;
  max: number;
  step: number;
  onChange: (n: number) => void;
}) {
  const [text, setText] = useState(String(value));
  useEffect(() => {
    setText((t) => (Number(t.replace(",", ".")) === value ? t : String(value)));
  }, [value]);
  return (
    <input
      type="number"
      className="input"
      inputMode="decimal"
      aria-label={label}
      min={min}
      max={max}
      step={step}
      value={text}
      onChange={(e) => {
        const raw = e.target.value;
        setText(raw);
        const n = Number(raw.replace(",", ".").trim());
        if (raw.trim() !== "" && Number.isFinite(n) && n >= 0) onChange(n);
      }}
      onBlur={() => {
        const n = Number(text.replace(",", ".").trim());
        const next = text.trim() === "" || !Number.isFinite(n) ? min : clamp(n, min, max);
        setText(String(next));
        if (next !== value) onChange(next);
      }}
    />
  );
}

/** Menge einer Komponente: Regler und Zahlenfeld (Gramm im Schritt der Komponente, bei Varianten mit Stückgewicht Stückzahl). */
export function AmountControl({ component: c, entry, onChange }: Props) {
  const r = resolve(c, entry);
  const unit = r.gpu && r.variant ? r.variant.name : "g";
  const outside = entry.amount < r.min - 1e-9 || entry.amount > r.max + 1e-9;
  const valueText = r.gpu ? `${numDe(entry.amount)} ${unit} = ${numDe(r.grams)} g` : `${numDe(entry.amount)} g`;
  return (
    <div>
      {c.variants.length > 0 && (
        <div className="field">
          <label className="label" htmlFor={`variant-${c.id}`}>
            Variante für {c.name}
          </label>
          <select
            id={`variant-${c.id}`}
            className="select"
            value={entry.variantId === null ? "" : String(entry.variantId)}
            onChange={(e) => onChange(withVariant(c, entry, e.target.value === "" ? null : Number(e.target.value)))}
          >
            <option value="">Gramm</option>
            {c.variants.map((v) => (
              <option key={v.id} value={v.id}>
                {v.grams_per_unit ? `${v.name} (${numDe(v.grams_per_unit)} g je Stück)` : `${v.name} (in Gramm)`}
              </option>
            ))}
          </select>
        </div>
      )}
      <div className="amount">
        <input
          type="range"
          className="range"
          aria-label={`Menge ${c.name} (Regler)`}
          aria-valuetext={valueText}
          min={r.min}
          max={r.max}
          step={r.step}
          value={clamp(entry.amount, r.min, r.max)}
          onChange={(e) => onChange({ ...entry, amount: Number(e.target.value) })}
        />
        <AmountNumber
          label={r.gpu ? `Anzahl ${unit} ${c.name}` : `Menge ${c.name} in Gramm`}
          value={entry.amount}
          min={r.min}
          max={r.max}
          step={r.step}
          onChange={(amount) => onChange({ ...entry, amount })}
        />
      </div>
      <small className="muted">
        {r.gpu ? `${valueText}. ` : ""}
        Spanne {numDe(r.min)} bis {numDe(r.max)} {unit}, Schritt {numDe(r.step)} {unit}.
      </small>
      {outside && (
        <div className="err" role="alert" style={{ color: "var(--warn)", fontSize: ".85rem" }}>
          Die Menge liegt außerhalb der Spanne dieser Komponente.
        </div>
      )}
    </div>
  );
}
