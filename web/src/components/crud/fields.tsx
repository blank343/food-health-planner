import { useId } from "react";
import { Field, TextField } from "../../ui";
import "./crud.css";

type Common = { label: string; hint?: string; error?: string | null };

export function TextAreaField({
  label,
  hint,
  error,
  value,
  onChange,
  rows = 3,
  maxLength,
}: Common & { value: string; onChange: (v: string) => void; rows?: number; maxLength?: number }) {
  return (
    <Field label={label} hint={hint} error={error}>
      {(id, d) => (
        <textarea
          id={id}
          className="textarea"
          rows={rows}
          maxLength={maxLength}
          aria-describedby={d}
          aria-invalid={error ? true : undefined}
          value={value}
          onChange={(e) => onChange(e.target.value)}
        />
      )}
    </Field>
  );
}

/** Textfeld mit Vorschlagsliste (`<datalist>`). Vorschläge werden nie automatisch übernommen; freie Eingabe bleibt möglich. */
export function SuggestField({
  label,
  hint,
  error,
  value,
  onChange,
  options,
  maxLength,
  placeholder,
}: Common & {
  value: string;
  onChange: (v: string) => void;
  options: { value: string; label?: string }[];
  maxLength?: number;
  placeholder?: string;
}) {
  const listId = useId();
  return (
    <>
      <TextField
        label={label}
        hint={hint}
        error={error}
        value={value}
        onChange={onChange}
        list={listId}
        maxLength={maxLength}
        placeholder={placeholder}
        autoComplete="off"
      />
      <datalist id={listId}>
        {options.map((o) => (
          <option key={o.value} value={o.value} label={o.label} />
        ))}
      </datalist>
    </>
  );
}

/** Schalter direkt in der Liste. Der zugängliche Name enthält den Eintrag („Aktiv: Salz“). */
export function QuickToggle({
  label,
  name,
  checked,
  onChange,
  disabled,
}: {
  label: string;
  name: string;
  checked: boolean;
  onChange: (v: boolean) => void;
  disabled?: boolean;
}) {
  return (
    <label className="crud-toggle">
      <input
        type="checkbox"
        aria-label={`${label}: ${name}`}
        checked={checked}
        disabled={disabled}
        onChange={(e) => onChange(e.target.checked)}
      />
      <span aria-hidden="true">{label}</span>
    </label>
  );
}

/** Auswahlliste mit Platzhalter („Bitte wählen“), damit nichts stillschweigend vorbelegt wird. */
export function withPlaceholder(options: { value: string; label: string }[], text = "Bitte wählen") {
  return [{ value: "", label: text }, ...options];
}
