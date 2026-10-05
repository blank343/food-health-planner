// Gemeinsame Hilfen der Einstellungsseite: Zahlen-Eingabe als Text (Dezimalkomma), Prüfung, Speichern.
import { useState } from "react";
import type { components } from "../../api/schema";
import { api } from "../../api/client";
import { useAction } from "../../hooks/useApi";
import { Alert, Button, TextField } from "../../ui";

export type SettingsOut = components["schemas"]["SettingsOut"];
export type Stored = Record<string, unknown>;

export type Parsed = { value: number | null; invalid: boolean };

/** Text → Zahl. Leer = `null`; Komma und Punkt sind erlaubt. */
export function parseDecimal(raw: string): Parsed {
  const t = raw.trim().replace(",", ".");
  if (t === "") return { value: null, invalid: false };
  if (!/^-?\d+(\.\d+)?$/.test(t)) return { value: null, invalid: true };
  return { value: Number(t), invalid: false };
}

/** Gespeicherter Wert → Eingabetext (leer, wenn nicht gesetzt). */
export function toField(v: unknown): string {
  return typeof v === "number" && Number.isFinite(v) ? String(v).replace(".", ",") : "";
}

export function omitKeys(obj: Stored, keys: readonly string[]): Stored {
  const out: Stored = {};
  for (const [k, v] of Object.entries(obj)) if (!keys.includes(k)) out[k] = v;
  return out;
}

export type NumSpec = {
  key: string;
  label: string;
  unit?: string;
  min?: number;
  max?: number;
  /** Streng größer als. */
  gt?: number;
  hint?: string;
  placeholder?: string;
};

const de = (n: number) => String(n).replace(".", ",");

export function validateNumber(raw: string, spec: Pick<NumSpec, "min" | "max" | "gt">): string | null {
  const { value, invalid } = parseDecimal(raw);
  if (invalid) return "Bitte eine Zahl eingeben (zum Beispiel 0,5).";
  if (value === null) return null;
  if (spec.gt !== undefined && value <= spec.gt) return `Der Wert muss größer als ${de(spec.gt)} sein.`;
  if (spec.min !== undefined && value < spec.min) return `Der Wert darf nicht kleiner als ${de(spec.min)} sein.`;
  if (spec.max !== undefined && value > spec.max) return `Der Wert darf nicht größer als ${de(spec.max)} sein.`;
  return null;
}

/** Zahlenfeld als Textfeld: Dezimalkomma funktioniert auch auf Handys zuverlässig. */
export function DecimalField(props: {
  label: string;
  unit?: string;
  value: string;
  onChange: (v: string) => void;
  hint?: string;
  error?: string | null;
  placeholder?: string;
}) {
  const { unit, label, ...rest } = props;
  return <TextField {...rest} label={unit ? `${label} (${unit})` : label} inputMode="decimal" autoComplete="off" />;
}

/** Eingabewerte mehrerer Zahlenfelder samt Prüfung und Umwandlung in die Server-Nutzlast. */
export function useNumericForm(specs: readonly NumSpec[], stored: Stored) {
  const [values, setValues] = useState<Record<string, string>>(() =>
    Object.fromEntries(specs.map((s) => [s.key, toField(stored[s.key])])),
  );
  const [errors, setErrors] = useState<Record<string, string | null>>({});

  const set = (key: string, v: string) => {
    setValues((prev) => ({ ...prev, [key]: v }));
    setErrors((prev) => ({ ...prev, [key]: null }));
  };
  const validate = (): boolean => {
    const next: Record<string, string | null> = {};
    let ok = true;
    for (const s of specs) {
      const e = validateNumber(values[s.key] ?? "", s);
      next[s.key] = e;
      if (e) ok = false;
    }
    setErrors(next);
    return ok;
  };
  const payload = (): Stored => {
    const out: Stored = {};
    for (const s of specs) {
      const { value } = parseDecimal(values[s.key] ?? "");
      if (value !== null) out[s.key] = value;
    }
    return out;
  };
  const clear = () => {
    setValues(Object.fromEntries(specs.map((s) => [s.key, ""])));
    setErrors({});
  };
  return { values, errors, set, validate, payload, clear };
}

/**
 * Speichert einen Abschnitt der Einstellungen. Der Server ersetzt alles, deshalb werden die
 * übrigen gespeicherten Felder unverändert mitgesendet; Felder dieses Abschnitts nur, wenn gesetzt.
 */
export function useSettingsSave(
  settings: SettingsOut,
  onSaved: (s: SettingsOut) => void,
  keys: readonly string[],
) {
  const [saved, setSaved] = useState(false);
  const action = useAction(async (values: Stored) => {
    const body = { ...omitKeys(settings.stored, keys), ...values };
    const res = await api<SettingsOut>("PUT", "/me/settings", body);
    onSaved(res);
    return res;
  });
  return {
    busy: action.busy,
    error: action.error,
    saved,
    hideSaved: () => setSaved(false),
    /** Liefert die Antwort des Servers (wirksame und gespeicherte Werte) oder `undefined` bei Fehler. */
    async save(values: Stored): Promise<SettingsOut | undefined> {
      setSaved(false);
      const res = await action.run(values);
      if (res) setSaved(true);
      return res;
    },
  };
}

export function SectionFooter(props: {
  busy: boolean;
  saved: boolean;
  error: string | null;
  onReset?: () => void;
  resetLabel?: string;
}) {
  return (
    <>
      {props.error && <Alert kind="error">{props.error}</Alert>}
      {props.saved && <Alert kind="ok">Gespeichert.</Alert>}
      <div className="row">
        <Button type="submit" variant="primary" disabled={props.busy}>
          {props.busy ? "Speichert …" : "Speichern"}
        </Button>
        {props.onReset && (
          <Button variant="ghost" disabled={props.busy} onClick={props.onReset}>
            {props.resetLabel ?? "Auf Standard zurücksetzen"}
          </Button>
        )}
      </div>
    </>
  );
}
