import { type FormEvent, useCallback, useEffect, useState } from "react";
import type { components } from "../../api/schema";
import { ApiError, api } from "../../api/client";
import { useAction, useQuery } from "../../hooks/useApi";
import { dateDe, num, todayIso } from "../../format";
import { Alert, Async, Button, Card, EmptyState, SelectField, Spinner, Table, TextField } from "../../ui";
import { DecimalField, type NumSpec, parseDecimal, validateNumber } from "./helpers";

type Goal = components["schemas"]["app__api__schemas__GoalOut"];
type GoalIn = components["schemas"]["GoalIn"];
type Kind = Goal["kind"];

const KIND_LABEL: Record<Kind, string> = { lose: "Abnehmen", maintain: "Gewicht halten", gain: "Zunehmen" };

const RATE: NumSpec = { key: "rate", label: "Gewünschtes Tempo", unit: "kg/Woche", min: 0, max: 2 };
const PCT: NumSpec = { key: "pct", label: "Energieanpassung", unit: "%", min: -60, max: 60 };
const PROTEIN: NumSpec = { key: "protein", label: "Protein", unit: "g/kg Körpergewicht", gt: 0, max: 5 };
const FAT: NumSpec = { key: "fat", label: "Fett", unit: "% der Kalorien", min: 0, max: 60 };

function pace(g: Goal): string {
  if (g.rate_kg_per_week !== null) return `${num(g.rate_kg_per_week, 2)} kg/Woche`;
  if (g.kcal_modifier_pct !== null) return `${num(g.kcal_modifier_pct, 1)} % Energie`;
  return "–";
}

type Active =
  | { state: "loading" }
  | { state: "none" }
  | { state: "ok"; goal: Goal }
  | { state: "error"; message: string };

function useActiveGoal() {
  const [active, setActive] = useState<Active>({ state: "loading" });
  const [tick, setTick] = useState(0);
  useEffect(() => {
    let cancelled = false;
    setActive({ state: "loading" });
    api<Goal>("GET", "/me/goals/active")
      .then((goal) => {
        if (!cancelled) setActive({ state: "ok", goal });
      })
      .catch((e: unknown) => {
        if (cancelled) return;
        if (e instanceof ApiError && e.status === 404) setActive({ state: "none" });
        else setActive({ state: "error", message: e instanceof ApiError ? e.message : "Unbekannter Fehler." });
      });
    return () => {
      cancelled = true;
    };
  }, [tick]);
  return { active, reload: useCallback(() => setTick((t) => t + 1), []) };
}

export function GoalSection() {
  const { active, reload: reloadActive } = useActiveGoal();
  const list = useQuery<Goal[]>("/me/goals");

  const [kind, setKind] = useState<Kind>("lose");
  const [rate, setRate] = useState("");
  const [pct, setPct] = useState("");
  const [protein, setProtein] = useState("");
  const [fat, setFat] = useState("");
  const [validFrom, setValidFrom] = useState(todayIso());
  const [note, setNote] = useState("");
  const [errors, setErrors] = useState<Record<string, string | null>>({});
  const [saved, setSaved] = useState(false);

  const create = useAction(async (body: GoalIn) => {
    await api("POST", "/me/goals", body);
    return true;
  });

  const clearError = (key: string) => setErrors((p) => ({ ...p, [key]: null }));
  const usesRate = kind !== "maintain";

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setSaved(false);
    const next: Record<string, string | null> = {
      rate: usesRate ? validateNumber(rate, RATE) : null,
      pct: validateNumber(pct, PCT),
      protein: validateNumber(protein, PROTEIN),
      fat: validateNumber(fat, FAT),
    };
    const r = usesRate ? parseDecimal(rate).value : null;
    const p = parseDecimal(pct).value;
    if (!next.pct && r !== null && p !== null) {
      next.pct = "Bitte entweder das Tempo oder die Energieanpassung angeben, nicht beides.";
    }
    setErrors(next);
    if (Object.values(next).some(Boolean)) return;

    const body: GoalIn = { kind };
    if (r !== null) body.rate_kg_per_week = r;
    if (p !== null) body.kcal_modifier_pct = p;
    const pr = parseDecimal(protein).value;
    if (pr !== null) body.protein_g_per_kg = pr;
    const f = parseDecimal(fat).value;
    if (f !== null) body.fat_pct = f;
    if (validFrom) body.valid_from = validFrom;
    if (note.trim()) body.note = note.trim();

    if (await create.run(body)) {
      setSaved(true);
      setRate("");
      setPct("");
      setProtein("");
      setFat("");
      setNote("");
      setErrors({});
      reloadActive();
      list.reload();
    }
  };

  return (
    <Card title="Ziel">
      <p className="muted">
        Ziele sind versioniert: Ein neues Ziel gilt ab dem gewählten Datum, ältere bleiben unverändert in der Historie.
      </p>

      <h3>Aktuell gültig</h3>
      {active.state === "loading" && <Spinner />}
      {active.state === "error" && <Alert kind="error">{active.message}</Alert>}
      {active.state === "none" && <EmptyState>Noch kein Ziel hinterlegt</EmptyState>}
      {active.state === "ok" && (
        <p>
          <strong>{KIND_LABEL[active.goal.kind]}</strong> seit {dateDe(active.goal.valid_from)}
          {` · Tempo: ${pace(active.goal)}`}
          {active.goal.protein_g_per_kg !== null && ` · Protein: ${num(active.goal.protein_g_per_kg, 1)} g/kg`}
          {active.goal.fat_pct !== null && ` · Fett: ${num(active.goal.fat_pct, 0)} % der Kalorien`}
          {active.goal.note ? ` · ${active.goal.note}` : ""}
        </p>
      )}

      <h3>Historie</h3>
      <Async loading={list.loading} error={list.error}>
        {list.data && list.data.length > 0 ? (
          <Table>
            <thead>
              <tr>
                <th scope="col">Gültig ab</th>
                <th scope="col">Art</th>
                <th scope="col">Tempo</th>
                <th scope="col">Notiz</th>
              </tr>
            </thead>
            <tbody>
              {list.data.map((g) => (
                <tr key={g.id}>
                  <td>{dateDe(g.valid_from)}</td>
                  <td>{KIND_LABEL[g.kind]}</td>
                  <td>{pace(g)}</td>
                  <td>{g.note ?? "–"}</td>
                </tr>
              ))}
            </tbody>
          </Table>
        ) : (
          <EmptyState>Noch keine Ziele gespeichert.</EmptyState>
        )}
      </Async>

      <h3>Neue Zielversion anlegen</h3>
      <form aria-label="Neue Zielversion" onSubmit={submit} noValidate>
        <SelectField
          label="Art"
          value={kind}
          onChange={(v) => {
            const k = v as Kind;
            setKind(k);
            if (k === "maintain") setRate("");
          }}
          options={(Object.keys(KIND_LABEL) as Kind[]).map((k) => ({ value: k, label: KIND_LABEL[k] }))}
        />
        {usesRate && (
          <DecimalField
            label={RATE.label}
            unit={RATE.unit}
            value={rate}
            onChange={(v) => {
              setRate(v);
              clearError("rate");
            }}
            error={errors.rate}
            hint="Zum Beispiel 0,5"
          />
        )}
        <DecimalField
          label={PCT.label}
          unit={PCT.unit}
          value={pct}
          onChange={(v) => {
            setPct(v);
            clearError("pct");
          }}
          error={errors.pct}
          hint="Alternative zum Tempo: negativ = Defizit (zum Beispiel -10), positiv = Überschuss. Entweder Tempo oder Prozent angeben."
        />
        <DecimalField
          label={PROTEIN.label}
          unit={PROTEIN.unit}
          value={protein}
          onChange={(v) => {
            setProtein(v);
            clearError("protein");
          }}
          error={errors.protein}
          placeholder="Standard: 2,0 / 1,6 / 1,8"
          hint="Optional. Standard je nach Art: Abnehmen 2,0, Halten 1,6, Zunehmen 1,8 g pro kg."
        />
        <DecimalField
          label={FAT.label}
          unit={FAT.unit}
          value={fat}
          onChange={(v) => {
            setFat(v);
            clearError("fat");
          }}
          error={errors.fat}
          placeholder="Standard: 30"
          hint="Optional. Leer lassen, dann gilt der Standardwert."
        />
        <TextField label="Gültig ab" type="date" value={validFrom} onChange={setValidFrom} />
        <TextField label="Notiz" value={note} onChange={setNote} maxLength={500} />
        {create.error && <Alert kind="error">{create.error}</Alert>}
        {saved && <Alert kind="ok">Neue Zielversion gespeichert.</Alert>}
        <Button type="submit" variant="primary" disabled={create.busy}>
          {create.busy ? "Speichert …" : "Speichern"}
        </Button>
      </form>
    </Card>
  );
}
