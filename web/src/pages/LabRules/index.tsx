import { useMemo, useState } from "react";
import type { components } from "../../api/schema";
import {
  EFFECT_KEYS,
  EFFECT_LABELS,
  type Editing,
  EmptyList,
  FormShell,
  QuickToggle,
  ResourceList,
  SuggestField,
  TextAreaField,
  editingIdOf,
  effectLabel,
  numDe,
  optText,
  suggestionOptions,
  useQuickPatch,
  withPlaceholder,
} from "../../components/crud";
import { useCrud } from "../../hooks/useCrud";
import { useQuery } from "../../hooks/useApi";
import { Alert, Async, Badge, Button, CheckField, NumberField, PageHeader, SelectField, TextField } from "../../ui";

type Rule = components["schemas"]["LabRuleOut"];
type RuleIn = components["schemas"]["LabRuleIn"];
type LatestValue = components["schemas"]["LatestLabValueOut"];
type Comparator = RuleIn["comparator"];

export const COMPARATOR_LABELS: Record<Comparator, string> = {
  lt: "kleiner als",
  gt: "größer als",
  between: "zwischen",
  outside_ref: "außerhalb des Referenzbereichs",
};
const COMPARATORS: Comparator[] = ["lt", "gt", "between", "outside_ref"];
const isComparator = (v: string): v is Comparator => (COMPARATORS as string[]).includes(v);

/**
 * Schwellenwert-Konvention (wie in den Servertests): „lt“ nutzt `threshold_high`, „gt“ nutzt `threshold_low`,
 * „between“ beide. Beim Lesen wird der jeweils andere Wert als Rückfall akzeptiert.
 */
function singleThreshold(r: Pick<Rule, "comparator" | "threshold_low" | "threshold_high">): number | null {
  if (r.comparator === "lt") return r.threshold_high ?? r.threshold_low ?? null;
  return r.threshold_low ?? r.threshold_high ?? null;
}

/** Bedingung in Worten, z. B. „Wert unter 1,2“. */
export function conditionText(r: Pick<Rule, "comparator" | "threshold_low" | "threshold_high">): string {
  const t = singleThreshold(r);
  switch (r.comparator) {
    case "lt":
      return t === null ? "Wert unter Schwelle" : `Wert unter ${numDe(t)}`;
    case "gt":
      return t === null ? "Wert über Schwelle" : `Wert über ${numDe(t)}`;
    case "between":
      return r.threshold_low != null && r.threshold_high != null
        ? `Wert zwischen ${numDe(r.threshold_low)} und ${numDe(r.threshold_high)}`
        : "Wert zwischen zwei Grenzen";
    case "outside_ref":
      return "Wert außerhalb des Referenzbereichs";
  }
}

function RuleForm({
  item,
  analytes,
  onSave,
  onCancel,
}: {
  item?: Rule;
  analytes: string[];
  onSave: (input: RuleIn) => Promise<unknown>;
  onCancel: () => void;
}) {
  const [name, setName] = useState(item?.name ?? "");
  const [analyte, setAnalyte] = useState(item?.analyte ?? "");
  const [comparator, setComparator] = useState<string>(item?.comparator ?? "");
  const [single, setSingle] = useState<number | null>(item ? singleThreshold(item) : null);
  const [low, setLow] = useState<number | null>(item?.threshold_low ?? null);
  const [high, setHigh] = useState<number | null>(item?.threshold_high ?? null);
  const [effect, setEffect] = useState(item?.effect_key ?? "");
  const [weight, setWeight] = useState<number | null>(item?.effect_weight ?? 0.5);
  const [enabled, setEnabled] = useState(item?.enabled ?? true);
  const [confirmed, setConfirmed] = useState(item?.doctor_confirmed ?? false);
  const [source, setSource] = useState(item?.source ?? "");
  const [note, setNote] = useState(item?.note ?? "");

  function validate(): string | null {
    if (name.trim() === "") return "Bitte einen Namen angeben.";
    if (analyte.trim() === "") return "Bitte den Analyten (Laborwert) angeben.";
    if (!isComparator(comparator)) return "Bitte die Bedingung wählen.";
    if ((comparator === "lt" || comparator === "gt") && single === null) return "Bitte einen Schwellenwert angeben.";
    if (comparator === "between") {
      if (low === null || high === null) return "Für „zwischen“ sind untere und obere Grenze erforderlich.";
      if (low > high) return "Die untere Grenze darf nicht größer als die obere sein.";
    }
    if (effect.trim() === "") return "Bitte die Wirkung angeben.";
    if (weight === null || weight < 0 || weight > 1) return "Das Gewicht muss zwischen 0 und 1 liegen.";
    return null;
  }

  async function submit() {
    if (!isComparator(comparator) || weight === null) return;
    await onSave({
      name: name.trim(),
      analyte: analyte.trim(),
      comparator,
      threshold_low: comparator === "gt" ? single : comparator === "between" ? low : null,
      threshold_high: comparator === "lt" ? single : comparator === "between" ? high : null,
      effect_key: effect.trim(),
      effect_weight: weight,
      enabled,
      doctor_confirmed: confirmed,
      suggested_by_app: item?.suggested_by_app ?? false,
      source: optText(source),
      note: optText(note),
    });
  }

  return (
    <FormShell
      title={item ? "Laborregel bearbeiten" : "Laborregel hinzufügen"}
      onSubmit={submit}
      onCancel={onCancel}
      validate={validate}
    >
      <TextField label="Name" value={name} onChange={setName} maxLength={120} required autoComplete="off" />
      <SuggestField
        label="Analyt (Laborwert)"
        hint="Die Vorschläge stammen aus deinen importierten Laborberichten."
        value={analyte}
        onChange={setAnalyte}
        options={analytes.map((a) => ({ value: a }))}
        maxLength={120}
      />
      <SelectField
        label="Bedingung"
        value={comparator}
        onChange={setComparator}
        options={withPlaceholder(COMPARATORS.map((c) => ({ value: c, label: COMPARATOR_LABELS[c] })))}
      />
      {(comparator === "lt" || comparator === "gt") && (
        <NumberField
          label="Schwellenwert"
          value={single}
          onChange={setSingle}
          step="any"
          hint={comparator === "lt" ? "Die Regel greift bei Werten darunter." : "Die Regel greift bei Werten darüber."}
        />
      )}
      {comparator === "between" && (
        <div className="crud-form-grid">
          <NumberField label="Untere Grenze" value={low} onChange={setLow} step="any" />
          <NumberField label="Obere Grenze" value={high} onChange={setHigh} step="any" />
        </div>
      )}
      {comparator === "outside_ref" && (
        <p className="muted">Die Regel greift, wenn der Wert außerhalb des Referenzbereichs aus dem Laborbericht liegt.</p>
      )}
      <SuggestField
        label="Wirkung"
        hint="Welches sanfte Planziel die Regel auslöst. Eigene Schlüssel sind möglich."
        value={effect}
        onChange={setEffect}
        options={suggestionOptions(EFFECT_KEYS, EFFECT_LABELS)}
        maxLength={60}
      />
      <NumberField
        label="Gewicht (0 bis 1)"
        value={weight}
        onChange={setWeight}
        min={0}
        max={1}
        step={0.1}
        hint="0 = kaum Einfluss auf den Plan, 1 = starker Einfluss."
      />
      <CheckField label="Aktiv" checked={enabled} onChange={setEnabled} />
      <CheckField label="Vom Arzt bestätigt" checked={confirmed} onChange={setConfirmed} />
      <TextField label="Quelle" value={source} onChange={setSource} maxLength={200} />
      <TextAreaField label="Notiz" value={note} onChange={setNote} maxLength={2000} />
    </FormShell>
  );
}

export default function LabRulesPage() {
  const { items, data, loading, error, reload, create, update, remove } = useCrud<Rule, RuleIn>("lab-rules");
  const quick = useQuickPatch("lab-rules", reload);
  const latest = useQuery<LatestValue[]>("/me/labs/latest"); // Fehler werden bewusst ignoriert
  const analytes = useMemo(
    () => [...new Set((latest.data ?? []).map((v) => v.analyte))].sort((a, b) => a.localeCompare(b, "de")),
    [latest.data],
  );
  const [editing, setEditing] = useState<Editing>(null);
  const close = () => setEditing(null);

  return (
    <>
      <PageHeader
        title="Laborregeln"
        actions={
          <Button variant="primary" onClick={() => setEditing({ mode: "new" })} disabled={editing?.mode === "new"}>
            Laborregel hinzufügen
          </Button>
        }
      >
        Wenn ein Laborwert in einem Bereich liegt, setzt der Planer ein sanftes Ziel.
      </PageHeader>
      <Alert kind="info">
        Laborregeln erzeugen nur sanfte Planungsziele und stellen niemals eine Diagnose. Die App gibt keine
        medizinischen Ratschläge; besprich Regeln mit deiner Ärztin oder deinem Arzt.
      </Alert>
      {quick.error && <Alert kind="error">{quick.error}</Alert>}

      {editing?.mode === "new" && (
        <RuleForm
          analytes={analytes}
          onCancel={close}
          onSave={async (input) => {
            await create(input);
            close();
          }}
        />
      )}

      <Async loading={loading && !data} error={error}>
        {items.length === 0 && editing?.mode !== "new" ? (
          <EmptyList actionLabel="Erste Laborregel hinzufügen" onAction={() => setEditing({ mode: "new" })}>
            Noch keine Laborregeln. Lege fest, welches sanfte Planziel bei einem bestimmten Laborwert gelten soll.
          </EmptyList>
        ) : (
          <ResourceList
            items={items}
            ariaLabel="Laborregeln"
            label={(r) => r.name}
            editingId={editingIdOf(editing)}
            onEdit={(r) => setEditing({ mode: "edit", id: r.id })}
            onRemove={remove}
            renderEditor={(r) => (
              <RuleForm
                item={r}
                analytes={analytes}
                onCancel={close}
                onSave={async (input) => {
                  await update(r.id, input);
                  close();
                }}
              />
            )}
            renderItem={(r) => (
              <>
                <div className="crud-head">
                  <h3>{r.name}</h3>
                  <small>{r.analyte}</small>
                </div>
                <div>{conditionText(r)}</div>
                <div>
                  Wirkung: {effectLabel(r.effect_key)}
                  {EFFECT_LABELS[r.effect_key] && <small className="muted"> ({r.effect_key})</small>}
                </div>
                <div className="crud-meta">
                  <Badge>Gewicht {numDe(r.effect_weight)}</Badge>
                  {!r.enabled && <Badge>pausiert</Badge>}
                  {r.doctor_confirmed && <Badge kind="ok">Vom Arzt bestätigt</Badge>}
                  {r.suggested_by_app && !r.doctor_confirmed && (
                    <Badge kind="warn">Vorschlag der App – bitte ärztlich bestätigen</Badge>
                  )}
                </div>
                {r.source && <small className="muted">Quelle: {r.source}</small>}
                {r.note && <p className="crud-note">{r.note}</p>}
              </>
            )}
            renderExtra={(r) => (
              <div className="crud-toggles">
                <QuickToggle
                  label="aktiv"
                  name={r.name}
                  checked={r.enabled}
                  disabled={quick.busy}
                  onChange={(v) => void quick.patch(r.id, { enabled: v })}
                />
                <QuickToggle
                  label="Arzt bestätigt"
                  name={r.name}
                  checked={r.doctor_confirmed}
                  disabled={quick.busy}
                  onChange={(v) => void quick.patch(r.id, { doctor_confirmed: v })}
                />
              </div>
            )}
          />
        )}
      </Async>
    </>
  );
}
