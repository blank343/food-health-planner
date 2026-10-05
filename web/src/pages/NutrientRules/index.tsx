import { useState } from "react";
import type { components } from "../../api/schema";
import {
  type Editing,
  EmptyList,
  FormShell,
  NUTRIENT_LABELS,
  QuickToggle,
  RULE_SUBJECT_KEYS,
  ResourceList,
  SuggestField,
  TextAreaField,
  editingIdOf,
  nutrientLabel,
  numDe,
  optText,
  suggestionOptions,
  useQuickPatch,
  withPlaceholder,
} from "../../components/crud";
import { useCrud } from "../../hooks/useCrud";
import { Alert, Async, Badge, Button, CheckField, NumberField, PageHeader, SelectField, TextField } from "../../ui";

type Rule = components["schemas"]["NutrientRuleOut"];
type RuleIn = components["schemas"]["NutrientRuleIn"];
type Kind = RuleIn["kind"];

export const KIND_LABELS: Record<Kind, string> = {
  max: "Obergrenze",
  min: "Untergrenze",
  avoid: "Meiden",
  target: "Ziel",
};
const KIND_ORDER: Kind[] = ["max", "min", "avoid", "target"];
const UNIT_SUGGESTIONS = ["g", "mg", "µg", "kcal", "Portionen"];

const isKind = (v: string): v is Kind => (KIND_ORDER as string[]).includes(v);
const needsValue = (kind: string) => kind === "max" || kind === "min" || kind === "target";

function RuleForm({
  item,
  onSave,
  onCancel,
}: {
  item?: Rule;
  onSave: (input: RuleIn) => Promise<unknown>;
  onCancel: () => void;
}) {
  const [subject, setSubject] = useState(item?.subject ?? "");
  const [kind, setKind] = useState<string>(item?.kind ?? "");
  const [value, setValue] = useState<number | null>(item?.value ?? null);
  const [unit, setUnit] = useState(item?.unit ?? "");
  const [per, setPer] = useState<string>(item?.per ?? "day");
  const [hard, setHard] = useState(item?.hard ?? true);
  const [enabled, setEnabled] = useState(item?.enabled ?? true);
  const [confirmed, setConfirmed] = useState(item?.doctor_confirmed ?? false);
  const [source, setSource] = useState(item?.source ?? "");
  const [note, setNote] = useState(item?.note ?? "");

  function validate(): string | null {
    if (subject.trim() === "") return "Bitte einen Gegenstand angeben (z. B. salt_g).";
    if (!isKind(kind)) return "Bitte die Art der Regel wählen.";
    if (needsValue(kind) && value === null) return "Für diese Regelart ist ein Wert erforderlich.";
    if (value !== null && value < 0) return "Der Wert darf nicht negativ sein.";
    return null;
  }

  async function submit() {
    if (!isKind(kind)) return;
    const avoid = kind === "avoid";
    await onSave({
      subject: subject.trim(),
      kind,
      value: avoid ? null : value,
      unit: avoid ? null : optText(unit),
      per: per === "week" ? "week" : "day",
      hard,
      enabled,
      doctor_confirmed: confirmed,
      suggested_by_app: item?.suggested_by_app ?? false,
      source: optText(source),
      note: optText(note),
    });
  }

  return (
    <FormShell
      title={item ? "Regel bearbeiten" : "Regel hinzufügen"}
      onSubmit={submit}
      onCancel={onCancel}
      validate={validate}
    >
      <SuggestField
        label="Gegenstand"
        hint="Nährstoff- oder Lebensmittelschlüssel, z. B. salt_g. Die Liste enthält nur Vorschläge."
        value={subject}
        onChange={setSubject}
        options={suggestionOptions(RULE_SUBJECT_KEYS, NUTRIENT_LABELS)}
        maxLength={80}
      />
      <SelectField
        label="Art der Regel"
        value={kind}
        onChange={setKind}
        options={withPlaceholder(KIND_ORDER.map((k) => ({ value: k, label: KIND_LABELS[k] })))}
      />
      {needsValue(kind) && (
        <div className="crud-form-grid">
          <NumberField label="Wert" value={value} onChange={setValue} min={0} step="any" />
          <SuggestField
            label="Einheit"
            value={unit}
            onChange={setUnit}
            options={UNIT_SUGGESTIONS.map((u) => ({ value: u }))}
            maxLength={20}
          />
        </div>
      )}
      <SelectField
        label="Gilt pro"
        value={per}
        onChange={setPer}
        options={[
          { value: "day", label: "Tag" },
          { value: "week", label: "Woche" },
        ]}
      />
      <CheckField
        label="Harte Regel"
        checked={hard}
        onChange={setHard}
        hint="Hart = feste Grenze. Ohne Haken ist die Regel ein sanftes Ziel."
      />
      <CheckField label="Aktiv" checked={enabled} onChange={setEnabled} />
      <CheckField label="Vom Arzt bestätigt" checked={confirmed} onChange={setConfirmed} />
      <TextField label="Quelle" value={source} onChange={setSource} maxLength={200} hint="z. B. Datum der Beratung." />
      <TextAreaField label="Notiz" value={note} onChange={setNote} maxLength={2000} />
    </FormShell>
  );
}

function ruleText(r: Rule): string {
  if (r.kind === "avoid") return "Meiden";
  const amount = r.value != null ? `${numDe(r.value)}${r.unit ? ` ${r.unit}` : ""}` : "ohne Wert";
  return `${KIND_LABELS[r.kind]}: ${amount} pro ${r.per === "week" ? "Woche" : "Tag"}`;
}

type SortKey = "subject" | "kind";

function sortRules(rules: Rule[], by: SortKey): Rule[] {
  const bySubject = (a: Rule, b: Rule) => nutrientLabel(a.subject).localeCompare(nutrientLabel(b.subject), "de");
  return [...rules].sort((a, b) =>
    by === "kind" ? KIND_ORDER.indexOf(a.kind) - KIND_ORDER.indexOf(b.kind) || bySubject(a, b) : bySubject(a, b),
  );
}

export default function NutrientRulesPage() {
  const { items, data, loading, error, reload, create, update, remove } = useCrud<Rule, RuleIn>("nutrient-rules");
  const quick = useQuickPatch("nutrient-rules", reload);
  const [editing, setEditing] = useState<Editing>(null);
  const [sort, setSort] = useState<SortKey>("subject");
  const close = () => setEditing(null);

  return (
    <>
      <PageHeader
        title="Ernährungsregeln"
        actions={
          <Button variant="primary" onClick={() => setEditing({ mode: "new" })} disabled={editing?.mode === "new"}>
            Regel hinzufügen
          </Button>
        }
      >
        Grenzen, Untergrenzen und Dinge, die du meiden willst.
      </PageHeader>
      <Alert kind="warn">
        Die App gibt keine medizinischen Ratschläge. Diese Regeln stammen aus deiner eigenen ärztlichen Beratung. Was
        die App selbst vorschlägt, ist nur ein Hinweis und sollte ärztlich bestätigt werden.
      </Alert>
      {quick.error && <Alert kind="error">{quick.error}</Alert>}

      {editing?.mode === "new" && (
        <RuleForm
          onCancel={close}
          onSave={async (input) => {
            await create(input);
            close();
          }}
        />
      )}

      <Async loading={loading && !data} error={error}>
        {items.length === 0 && editing?.mode !== "new" ? (
          <EmptyList actionLabel="Erste Regel hinzufügen" onAction={() => setEditing({ mode: "new" })}>
            Noch keine Ernährungsregeln. Trage ein, was dir deine Ärztin oder dein Arzt empfohlen hat, z. B. eine
            Obergrenze für Salz.
          </EmptyList>
        ) : (
          <>
            {items.length > 1 && (
              <SelectField
                label="Sortieren nach"
                value={sort}
                onChange={(v) => setSort(v === "kind" ? "kind" : "subject")}
                options={[
                  { value: "subject", label: "Gegenstand" },
                  { value: "kind", label: "Art der Regel" },
                ]}
              />
            )}
            <ResourceList
              items={sortRules(items, sort)}
              ariaLabel="Ernährungsregeln"
              label={(r) => nutrientLabel(r.subject)}
              editingId={editingIdOf(editing)}
              onEdit={(r) => setEditing({ mode: "edit", id: r.id })}
              onRemove={remove}
              renderEditor={(r) => (
                <RuleForm
                  item={r}
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
                    <h3>{nutrientLabel(r.subject)}</h3>
                    {NUTRIENT_LABELS[r.subject] && <small>{r.subject}</small>}
                  </div>
                  <div>{ruleText(r)}</div>
                  <div className="crud-meta">
                    <Badge>{KIND_LABELS[r.kind]}</Badge>
                    <Badge>{r.hard ? "hart" : "sanft"}</Badge>
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
                    name={nutrientLabel(r.subject)}
                    checked={r.enabled}
                    disabled={quick.busy}
                    onChange={(v) => void quick.patch(r.id, { enabled: v })}
                  />
                  <QuickToggle
                    label="Arzt bestätigt"
                    name={nutrientLabel(r.subject)}
                    checked={r.doctor_confirmed}
                    disabled={quick.busy}
                    onChange={(v) => void quick.patch(r.id, { doctor_confirmed: v })}
                  />
                </div>
              )}
            />
          </>
        )}
      </Async>
    </>
  );
}
