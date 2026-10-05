import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { ApiError, api } from "../../api/client";
import type { components } from "../../api/schema";
import { dateDe, grams, kcal, kg, num, todayIso } from "../../format";
import { Alert, Badge, Card, PageHeader, Spinner, Stat, Table, TextField } from "../../ui";
import ManualForm from "./ManualForm";

type TargetsData = components["schemas"]["TargetsOut"];
type Macro = components["schemas"]["MacroOut"];
type Warning = components["schemas"]["WarningOut"];

type TargetsState = {
  data: TargetsData | undefined;
  loading: boolean;
  error: { message: string; status: number } | null;
};

/** Lädt die Zielwerte; merkt sich den Statuscode, damit 422 (Daten fehlen) anders erklärt werden kann. */
function useTargets(date: string): TargetsState & { reload: () => void } {
  const [state, setState] = useState<TargetsState>({ data: undefined, loading: date !== "", error: null });
  const [tick, setTick] = useState(0);
  const seq = useRef(0);

  useEffect(() => {
    if (!date) {
      setState({ data: undefined, loading: false, error: null });
      return;
    }
    const mine = ++seq.current;
    setState((s) => ({ ...s, loading: true }));
    api<TargetsData>("GET", `/me/targets?date=${encodeURIComponent(date)}`)
      .then((data) => {
        if (mine === seq.current) setState({ data, loading: false, error: null });
      })
      .catch((e: unknown) => {
        if (mine !== seq.current) return;
        const error =
          e instanceof ApiError ? { message: e.message, status: e.status } : { message: "Unbekannter Fehler.", status: 0 };
        setState({ data: undefined, loading: false, error });
      });
  }, [date, tick]);

  const reload = useCallback(() => setTick((t) => t + 1), []);
  return { ...state, reload };
}

const SLOT_ORDER = ["breakfast", "lunch", "dinner", "snack"];
const SLOT_NAMES: Record<string, string> = {
  breakfast: "Frühstück",
  lunch: "Mittagessen",
  dinner: "Abendessen",
  snack: "Snack",
};

const DAY_TYPES: Record<string, string> = {
  rest: "Ruhetag",
  easy: "Leichter Trainingstag",
  moderate: "Mittlerer Trainingstag",
  hard: "Harter Trainingstag",
};

const METHODS: Record<string, { label: string; kind: "ok" | "warn" | undefined }> = {
  device: { label: "Gerät", kind: "ok" },
  calibrated: { label: "Kalibriert am Gewichtstrend", kind: "ok" },
  formula: { label: "Formel", kind: "warn" },
};

const GOAL_KINDS: Record<string, string> = { lose: "Abnehmen", maintain: "Halten", gain: "Zunehmen" };

function orderedSlots(slots: Record<string, Macro>): [string, Macro][] {
  const names = Object.keys(slots);
  const sorted = [
    ...SLOT_ORDER.filter((n) => names.includes(n)),
    ...names.filter((n) => !SLOT_ORDER.includes(n)).sort(),
  ];
  return sorted.map((n) => [n, slots[n]!] as [string, Macro]).filter(([, m]) => m.kcal > 0);
}

function WarningAlert({ w }: { w: Warning }) {
  const kind = w.severity === "block" ? "error" : w.severity === "warn" ? "warn" : "info";
  return <Alert kind={kind}>{w.message}</Alert>;
}

function rate(v: number | null | undefined): string {
  return v === null || v === undefined ? "nicht festgelegt" : `${v > 0 ? "+" : ""}${num(v, 2, "kg/Woche")}`;
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <tr>
      <th scope="row">{label}</th>
      <td>{value}</td>
    </tr>
  );
}

function TargetsView({ t }: { t: TargetsData }) {
  const slots = orderedSlots(t.slots);
  const method = METHODS[t.tdee.method] ?? { label: t.tdee.method, kind: undefined };
  const g = t.goal;
  const b = t.body;
  return (
    <>
      {t.warnings.map((w, i) => (
        <WarningAlert key={`${w.code}-${i}`} w={w} />
      ))}

      <div className="grid" style={{ marginBottom: 16 }}>
        <Stat label="Kalorien" value={kcal(t.target.kcal)} hint={DAY_TYPES[t.day_type] ?? t.day_type} />
        <Stat label="Protein" value={grams(t.target.protein_g)} />
        <Stat label="Fett" value={grams(t.target.fat_g)} />
        <Stat label="Kohlenhydrate" value={grams(t.target.carb_g)} />
      </div>

      <Card title="Verteilung auf Mahlzeiten">
        {slots.length === 0 ? (
          <p className="muted">Keine Mahlzeiten mit Zielwerten.</p>
        ) : (
          <Table>
            <thead>
              <tr>
                <th scope="col">Mahlzeit</th>
                <th scope="col">kcal</th>
                <th scope="col">Protein (g)</th>
                <th scope="col">Fett (g)</th>
                <th scope="col">Kohlenhydrate (g)</th>
              </tr>
            </thead>
            <tbody>
              {slots.map(([name, m]) => (
                <tr key={name}>
                  <th scope="row">{SLOT_NAMES[name] ?? name}</th>
                  <td>{num(m.kcal)}</td>
                  <td>{num(m.protein_g)}</td>
                  <td>{num(m.fat_g)}</td>
                  <td>{num(m.carb_g)}</td>
                </tr>
              ))}
            </tbody>
          </Table>
        )}
      </Card>

      <Card title="Energiebedarf">
        <p>
          <strong>{kcal(t.tdee.tdee_kcal)}</strong> pro Tag <Badge kind={method.kind}>{method.label}</Badge>
        </p>
        <Table>
          <tbody>
            <Row label="Laut Gerät (Uhr)" value={kcal(t.tdee.device_kcal)} />
            <Row label="Aus dem Gewichtstrend abgeleitet" value={kcal(t.tdee.implied_kcal)} />
            <Row label="Vertrauen" value={num(t.tdee.confidence * 100, 0, "%")} />
          </tbody>
        </Table>
        {t.tdee.notes.length > 0 && (
          <ul>
            {t.tdee.notes.map((n, i) => (
              <li key={i}>{n}</li>
            ))}
          </ul>
        )}
      </Card>

      <Card title="Verwendete Körperdaten">
        <Table>
          <tbody>
            <Row label="Gewicht" value={`${kg(b.weight_kg)} (vom ${dateDe(b.weight_date)})`} />
            <Row label="Körperfett" value={b.body_fat_pct === null ? "–" : num(b.body_fat_pct, 1, "%")} />
            <Row label="Magermasse" value={kg(b.lean_mass_kg)} />
            <Row label="Größe" value={num(b.height_cm, 0, "cm")} />
            <Row label="Alter" value={num(b.age_years, 1, "Jahre")} />
          </tbody>
        </Table>
      </Card>

      <Card title="Ziel">
        <Table>
          <tbody>
            <Row label="Art" value={GOAL_KINDS[g.kind] ?? g.kind} />
            <Row label="Gewünschtes Tempo" value={rate(g.rate_kg_per_week)} />
            <Row label="Angewendetes Tempo" value={rate(g.applied_rate_kg_per_week)} />
            {g.valid_from && <Row label="Gültig ab" value={dateDe(g.valid_from)} />}
          </tbody>
        </Table>
        {g.applied_rate_kg_per_week !== g.rate_kg_per_week && (
          <p className="muted">
            Das angewendete Tempo weicht vom gewünschten ab, weil Sicherheitsgrenzen eingehalten werden müssen.
          </p>
        )}
      </Card>
    </>
  );
}

export default function TargetsPage() {
  const [date, setDate] = useState(todayIso());
  const q = useTargets(date);

  return (
    <>
      <PageHeader title="Tagesziel">Kalorien und Nährstoffe für den gewählten Tag, verteilt auf die Mahlzeiten.</PageHeader>

      <Card>
        <TextField label="Datum für das Tagesziel" type="date" value={date} onChange={setDate} />
      </Card>

      {q.loading && <Spinner label="Berechne Tagesziel …" />}

      {!q.loading && q.error && q.error.status === 422 && (
        <Alert kind="warn">
          <strong>Das Tagesziel kann noch nicht berechnet werden.</strong>
          <br />
          {q.error.message}
          <br />
          Tragen Sie unten ein aktuelles Gewicht ein. Fehlt die Körpergröße, ergänzen Sie sie unter{" "}
          <Link to="/einstellungen">Einstellungen</Link>.
        </Alert>
      )}
      {!q.loading && q.error && q.error.status !== 422 && <Alert kind="error">{q.error.message}</Alert>}
      {!q.loading && !date && <Alert kind="info">Bitte ein Datum wählen.</Alert>}
      {!q.loading && q.data && <TargetsView t={q.data} />}

      <ManualForm onSaved={q.reload} />
    </>
  );
}
