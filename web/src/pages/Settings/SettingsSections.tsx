// Abschnitte, die in /me/settings gespeichert werden: Grenzen, Energiebedarf, Mahlzeiten, Datenquellen.
import { type FormEvent, useState } from "react";
import { num } from "../../format";
import { Alert, Button, Card, CheckField } from "../../ui";
import {
  DecimalField,
  type NumSpec,
  SectionFooter,
  type SettingsOut,
  type Stored,
  parseDecimal,
  toField,
  useNumericForm,
  useSettingsSave,
  validateNumber,
} from "./helpers";

type SectionProps = { settings: SettingsOut; onSaved: (s: SettingsOut) => void };

/** Standardwert als Platzhalter, falls der wirksame Wert gesetzt ist. */
function defaultHint(effective: Stored, key: string, digits = 1): string | undefined {
  const v = effective[key];
  return typeof v === "number" ? `Standard: ${num(v, digits)}` : undefined;
}

// ---------------------------------------------------------------- Sicherheitsgrenzen

const SAFETY_SPECS: NumSpec[] = [
  {
    key: "kcal_floor",
    label: "Untergrenze Energie pro Tag",
    unit: "kcal",
    min: 0,
    placeholder: "Standard: max. 1500/1200 kcal oder Grundumsatz",
  },
  { key: "protein_floor_g_per_kg", label: "Untergrenze Protein", unit: "g/kg Körpergewicht", min: 0 },
  {
    key: "max_rate_kg_per_week",
    label: "Maximales Tempo",
    unit: "kg/Woche",
    min: 0,
    placeholder: "Standard: höchstens 1 kg bzw. 1 % des Körpergewichts",
  },
  {
    key: "weight_floor_kg",
    label: "Gewichtsgrenze",
    unit: "kg",
    gt: 0,
    placeholder: "Standard: keine feste Grenze",
    hint: "Die App warnt nur (ohne zu blockieren), wenn eine Grenze unplausibel niedrig wirkt, zum Beispiel unter der Magermasse. Nähert sich das Gewicht der Grenze, wird das Tempo automatisch langsamer.",
  },
  {
    key: "bf_floor_pct",
    label: "Körperfett-Grenze",
    unit: "%",
    min: 0,
    max: 60,
    placeholder: "Standard: keine feste Grenze",
    hint: "Auch hier gilt: Die App warnt nur bei unplausibel niedrigen Werten und bremst das Tempo, wenn die Grenze näher rückt.",
  },
  { key: "taper_weight_kg", label: "Tempo-Auslauf vor der Gewichtsgrenze", unit: "kg", min: 0 },
  { key: "taper_bf_pct_points", label: "Tempo-Auslauf vor der Körperfett-Grenze", unit: "Prozentpunkte", min: 0 },
  {
    key: "single_meal_max_kcal",
    label: "Obergrenze Energie pro Mahlzeit",
    unit: "kcal",
    gt: 0,
    placeholder: "Standard: keine Obergrenze",
    hint: "Optional: Eine einzelne Mahlzeit soll diesen Wert nicht überschreiten.",
  },
];
const SAFETY_KEYS = SAFETY_SPECS.map((s) => s.key);

export function SafetySection({ settings, onSaved }: SectionProps) {
  const form = useNumericForm(SAFETY_SPECS, settings.stored);
  const sv = useSettingsSave(settings, onSaved, SAFETY_KEYS);
  const eff = settings.effective as Stored;

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!form.validate()) return;
    await sv.save(form.payload());
  };
  const reset = async () => {
    form.clear();
    await sv.save({});
  };

  return (
    <Card title="Sicherheitsgrenzen">
      <p className="muted">
        Leere Felder verwenden den sicheren Standardwert. Nur ausgefüllte Felder werden als eigene Einstellung
        gespeichert.
      </p>
      <form aria-label="Sicherheitsgrenzen" onSubmit={submit} noValidate>
        {SAFETY_SPECS.map((s) => (
          <DecimalField
            key={s.key}
            label={s.label}
            unit={s.unit}
            value={form.values[s.key] ?? ""}
            onChange={(v) => {
              form.set(s.key, v);
              sv.hideSaved();
            }}
            error={form.errors[s.key]}
            hint={s.hint}
            placeholder={s.placeholder ?? defaultHint(eff, s.key)}
          />
        ))}
        <SectionFooter busy={sv.busy} saved={sv.saved} error={sv.error} onReset={reset} />
      </form>
    </Card>
  );
}

// ---------------------------------------------------------------- Energiebedarf

const INTAKE_SPEC: NumSpec = {
    key: "reported_intake_kcal",
    label: "Aktuelle Aufnahme (kcal pro Tag, grob)",
    gt: 0,
    hint: "Grobe Schätzung deiner derzeitigen Aufnahme. Daraus und aus dem Gewichtstrend wird der Energiebedarf kalibriert.",
};
const PER_KG_SPEC: NumSpec = {
    key: "kcal_per_kg",
    label: "Energie pro kg Körpermasse",
    unit: "kcal",
    gt: 0,
    hint: "Nur für Fortgeschrittene. Orientierungswert, der Gewichtsänderung in Energie umrechnet.",
};
const ENERGY_SPECS: NumSpec[] = [INTAKE_SPEC, PER_KG_SPEC];
const ENERGY_KEYS = ["tdee_calibration", "use_katch_mcardle", ...ENERGY_SPECS.map((s) => s.key)];
const BOOL_DEFAULTS = { tdee_calibration: true, use_katch_mcardle: false } as const;

export function EnergySection({ settings, onSaved }: SectionProps) {
  const form = useNumericForm(ENERGY_SPECS, settings.stored);
  const sv = useSettingsSave(settings, onSaved, ENERGY_KEYS);
  const eff = settings.effective as Stored;
  const [calibration, setCalibration] = useState<boolean>(settings.effective.tdee_calibration);
  const [katch, setKatch] = useState<boolean>(settings.effective.use_katch_mcardle);
  const [advancedOpen, setAdvancedOpen] = useState(false);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!form.validate()) {
      if (validateNumber(form.values.kcal_per_kg ?? "", PER_KG_SPEC)) setAdvancedOpen(true);
      return;
    }
    const values = form.payload();
    const stored = settings.stored;
    if ("tdee_calibration" in stored || calibration !== BOOL_DEFAULTS.tdee_calibration) {
      values.tdee_calibration = calibration;
    }
    if ("use_katch_mcardle" in stored || katch !== BOOL_DEFAULTS.use_katch_mcardle) {
      values.use_katch_mcardle = katch;
    }
    await sv.save(values);
  };
  const reset = async () => {
    form.clear();
    setCalibration(BOOL_DEFAULTS.tdee_calibration);
    setKatch(BOOL_DEFAULTS.use_katch_mcardle);
    await sv.save({});
  };

  return (
    <Card title="Energiebedarf">
      <form aria-label="Energiebedarf" onSubmit={submit} noValidate>
        <CheckField
          label="Kalibrierung am Gewichtstrend"
          checked={calibration}
          onChange={(v) => {
            setCalibration(v);
            sv.hideSaved();
          }}
          hint="Der Energiebedarf aus den Gerätedaten wird mit deinem tatsächlichen Gewichtsverlauf abgeglichen."
        />
        <DecimalField
          label={INTAKE_SPEC.label}
          value={form.values.reported_intake_kcal ?? ""}
          onChange={(v) => {
            form.set("reported_intake_kcal", v);
            sv.hideSaved();
          }}
          error={form.errors.reported_intake_kcal}
          hint={INTAKE_SPEC.hint}
          placeholder="Standard: nicht angegeben"
        />
        <CheckField
          label="Grundumsatz nach Katch-McArdle"
          checked={katch}
          onChange={(v) => {
            setKatch(v);
            sv.hideSaved();
          }}
          hint="Nutzt die fettfreie Masse statt der Standardformel. Braucht einen Körperfettwert."
        />
        <details open={advancedOpen} onToggle={(e) => setAdvancedOpen(e.currentTarget.open)}>
          <summary className="settings-summary">Erweitert</summary>
          <DecimalField
            label={PER_KG_SPEC.label}
            unit={PER_KG_SPEC.unit}
            value={form.values.kcal_per_kg ?? ""}
            onChange={(v) => {
              form.set("kcal_per_kg", v);
              sv.hideSaved();
            }}
            error={form.errors.kcal_per_kg}
            hint={PER_KG_SPEC.hint}
            placeholder={defaultHint(eff, "kcal_per_kg", 0)}
          />
        </details>
        <SectionFooter busy={sv.busy} saved={sv.saved} error={sv.error} onReset={reset} />
      </form>
    </Card>
  );
}

// ---------------------------------------------------------------- Mahlzeiten-Verteilung

const SLOTS: [string, string][] = [
  ["breakfast", "Frühstück"],
  ["lunch", "Mittagessen"],
  ["dinner", "Abendessen"],
  ["snack", "Snack"],
];
const SLOT_KEYS = ["slot_shares", "slot_shares_weekend"] as const;

function asNumberMap(v: unknown): Record<string, number> | null {
  if (!v || typeof v !== "object" || Array.isArray(v)) return null;
  const out: Record<string, number> = {};
  for (const [k, n] of Object.entries(v as Record<string, unknown>)) if (typeof n === "number") out[k] = n;
  return out;
}

function toTexts(map: Record<string, number> | null): Record<string, string> {
  return Object.fromEntries(Object.entries(map ?? {}).map(([k, v]) => [k, toField(v)]));
}

type SlotCheck = { rows: Record<string, string | null>; sum: string | null };

function slotKeysOf(...maps: (Record<string, unknown> | null)[]): [string, string][] {
  const known = new Set(SLOTS.map(([k]) => k));
  const extra = new Set<string>();
  for (const m of maps) for (const k of Object.keys(m ?? {})) if (!known.has(k)) extra.add(k);
  return [...SLOTS, ...[...extra].map((k): [string, string] => [k, k])];
}

function checkSlots(values: Record<string, string>, keys: [string, string][]): SlotCheck {
  const rows: Record<string, string | null> = {};
  let total = 0;
  let any = false;
  let bad = false;
  for (const [k] of keys) {
    const raw = values[k] ?? "";
    const { value, invalid } = parseDecimal(raw);
    if (invalid) rows[k] = "Bitte eine Zahl eingeben.";
    else if (value !== null && value < 0) rows[k] = "Darf nicht negativ sein.";
    else rows[k] = null;
    if (rows[k]) bad = true;
    if (value !== null) {
      any = true;
      if (value > 0) total += value;
    }
  }
  const sum = !bad && any && total <= 0 ? "Mindestens ein Anteil muss größer als 0 sein." : null;
  return { rows, sum };
}

function slotPayload(values: Record<string, string>, keys: [string, string][]): Record<string, number> | null {
  const out: Record<string, number> = {};
  for (const [k] of keys) {
    const { value } = parseDecimal(values[k] ?? "");
    if (value !== null && value > 0) out[k] = value;
  }
  return Object.keys(out).length > 0 ? out : null;
}

function percent(p: number): string {
  const r = Math.round(p * 10) / 10;
  return `${num(r, Number.isInteger(r) ? 0 : 1)} %`;
}

function SlotEditor(props: {
  legend: string;
  keys: [string, string][];
  values: Record<string, string>;
  onChange: (next: Record<string, string>) => void;
  fallback: Record<string, number>;
  check: SlotCheck | null;
}) {
  const { keys, values, fallback, check } = props;
  const parsed = keys.map(([k]) => parseDecimal(values[k] ?? ""));
  const anyEntered = parsed.some((p) => p.value !== null);
  const usable = parsed.every((p) => !p.invalid && (p.value ?? 0) >= 0);
  const shares: Record<string, number> = {};
  keys.forEach(([k], i) => {
    shares[k] = anyEntered ? (parsed[i]?.value ?? 0) : (fallback[k] ?? 0);
  });
  const total = Object.values(shares).reduce((a, b) => a + b, 0);
  const showPreview = usable && total > 0;

  return (
    <fieldset className="settings-fieldset">
      <legend>{props.legend}</legend>
      {!anyEntered && <p className="muted">Keine eigene Verteilung: Der Standard wird verwendet.</p>}
      {keys.map(([k, label]) => (
        <DecimalField
          key={k}
          label={label}
          value={values[k] ?? ""}
          onChange={(v) => props.onChange({ ...values, [k]: v })}
          error={check?.rows[k]}
          placeholder={fallback[k] !== undefined ? `Standard: ${toField(fallback[k])}` : "0"}
          hint={showPreview ? `Anteil: ${percent(((shares[k] ?? 0) / total) * 100)}` : undefined}
        />
      ))}
      {check?.sum && <Alert kind="error">{check.sum}</Alert>}
      <Button onClick={() => props.onChange({ breakfast: "1" })}>Nur Frühstück (100 %)</Button>
    </fieldset>
  );
}

export function SlotsSection({ settings, onSaved }: SectionProps) {
  const storedWeek = asNumberMap(settings.stored.slot_shares);
  const storedWeekend = asNumberMap(settings.stored.slot_shares_weekend);
  const effWeek = asNumberMap(settings.effective.slot_shares) ?? {};
  const effWeekend = asNumberMap(settings.effective.slot_shares_weekend);
  const keys = slotKeysOf(storedWeek, storedWeekend, effWeek, effWeekend);

  const [week, setWeek] = useState(() => toTexts(storedWeek));
  const [weekend, setWeekend] = useState(() => toTexts(storedWeekend));
  const [same, setSame] = useState(storedWeekend === null);
  const [checks, setChecks] = useState<{ week: SlotCheck; weekend: SlotCheck | null } | null>(null);
  const sv = useSettingsSave(settings, onSaved, SLOT_KEYS);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    const cw = checkSlots(week, keys);
    const ce = same ? null : checkSlots(weekend, keys);
    setChecks({ week: cw, weekend: ce });
    const bad = (c: SlotCheck | null) => !!c && (!!c.sum || Object.values(c.rows).some(Boolean));
    if (bad(cw) || bad(ce)) return;
    const values: Stored = {};
    const w = slotPayload(week, keys);
    if (w) values.slot_shares = w;
    if (!same) {
      const we = slotPayload(weekend, keys);
      if (we) values.slot_shares_weekend = we;
    }
    await sv.save(values);
  };
  const reset = async () => {
    setWeek({});
    setWeekend({});
    setSame(true);
    setChecks(null);
    await sv.save({});
  };

  return (
    <Card title="Mahlzeiten-Verteilung">
      <p className="muted">
        Wie das Tagesziel auf die Mahlzeiten verteilt wird. Du kannst beliebige Zahlen eingeben: Sie werden
        automatisch auf 100 % umgerechnet, die Vorschau zeigt das Ergebnis.
      </p>
      <form aria-label="Mahlzeiten-Verteilung" onSubmit={submit} noValidate>
        <SlotEditor
          legend="Montag bis Freitag"
          keys={keys}
          values={week}
          onChange={(v) => {
            setWeek(v);
            sv.hideSaved();
          }}
          fallback={effWeek}
          check={checks?.week ?? null}
        />
        <CheckField
          label="Samstag und Sonntag wie unter der Woche"
          checked={same}
          onChange={(v) => {
            setSame(v);
            sv.hideSaved();
          }}
        />
        {!same && (
          <SlotEditor
            legend="Samstag und Sonntag"
            keys={keys}
            values={weekend}
            onChange={(v) => {
              setWeekend(v);
              sv.hideSaved();
            }}
            fallback={effWeekend ?? effWeek}
            check={checks?.weekend ?? null}
          />
        )}
        <SectionFooter busy={sv.busy} saved={sv.saved} error={sv.error} onReset={reset} />
      </form>
    </Card>
  );
}

// ---------------------------------------------------------------- Datenquellen

const SOURCE_LABEL: Record<string, string> = {
  manual: "Manuell",
  apple_health_xml: "Apple Health",
  hae_zip: "Health Auto Export",
};

export function SourcesSection({ settings, onSaved }: SectionProps) {
  const initial = Array.isArray(settings.stored.source_priority)
    ? (settings.stored.source_priority as unknown[]).filter((x): x is string => typeof x === "string")
    : (settings.effective.source_priority ?? []);
  const [order, setOrder] = useState<string[]>(initial);
  const [dirty, setDirty] = useState(false);
  const sv = useSettingsSave(settings, onSaved, ["source_priority"]);

  const move = (index: number, delta: -1 | 1) => {
    const target = index + delta;
    if (target < 0 || target >= order.length) return;
    const a = order[index];
    const b = order[target];
    if (a === undefined || b === undefined) return;
    const next = [...order];
    next[index] = b;
    next[target] = a;
    setOrder(next);
    setDirty(true);
    sv.hideSaved();
  };

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    const values: Stored = {};
    if (dirty || "source_priority" in settings.stored) values.source_priority = order;
    await sv.save(values);
  };
  const reset = async () => {
    const res = await sv.save({});
    if (!res) return;
    setOrder(res.effective.source_priority ?? []);
    setDirty(false);
  };

  return (
    <Card title="Datenquellen">
      <p className="muted">
        Liefern mehrere Quellen Werte für denselben Tag, gewinnt die Quelle weiter oben in der Liste.
      </p>
      <form aria-label="Datenquellen" onSubmit={submit} noValidate>
        <ol className="settings-sources" aria-label="Reihenfolge der Datenquellen">
          {order.map((src, i) => {
            const name = SOURCE_LABEL[src] ?? src;
            return (
              <li key={src} className="row">
                <span className="settings-source-name">
                  {i + 1}. {name}
                </span>
                <Button aria-label={`${name} nach oben`} disabled={i === 0} onClick={() => move(i, -1)}>
                  Nach oben
                </Button>
                <Button
                  aria-label={`${name} nach unten`}
                  disabled={i === order.length - 1}
                  onClick={() => move(i, 1)}
                >
                  Nach unten
                </Button>
              </li>
            );
          })}
        </ol>
        <SectionFooter busy={sv.busy} saved={sv.saved} error={sv.error} onReset={reset} />
      </form>
    </Card>
  );
}
