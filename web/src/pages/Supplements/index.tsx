import { useState } from "react";
import type { components } from "../../api/schema";
import {
  type Editing,
  EmptyList,
  FormShell,
  NUTRIENT_LABELS,
  ResourceList,
  SUPPLEMENT_NUTRIENT_KEYS,
  SuggestField,
  TextAreaField,
  editingIdOf,
  numDe,
  nutrientLabel,
  optText,
  suggestionOptions,
} from "../../components/crud";
import { useCrud } from "../../hooks/useCrud";
import { Alert, Async, Badge, Button, CheckField, NumberField, PageHeader, SelectField, TextField } from "../../ui";

type Supplement = components["schemas"]["SupplementOut"];
type SupplementIn = components["schemas"]["SupplementIn"];

export const TIMES_OF_DAY = ["morgens", "mittags", "abends", "zu den Mahlzeiten", "frei"];
const DOSE_UNITS = ["mg", "g", "µg", "IE", "ml", "Kapseln", "Tabletten"];

type Row = { rid: number; key: string; value: number | null };
let nextRow = 1;
const newRow = (key = "", value: number | null = null): Row => ({ rid: nextRow++, key, value });

/** Baut den Beitrag pro Tag aus den Zeilen oder liefert eine deutsche Fehlermeldung. */
function buildNutrients(rows: Row[]): { ok: Record<string, number> } | { error: string } {
  const out: Record<string, number> = {};
  for (const r of rows) {
    const key = r.key.trim();
    if (key === "" && r.value === null) continue;
    if (key === "") return { error: "Bitte für jeden Mengenwert einen Nährstoff angeben." };
    if (r.value === null) return { error: `Bitte eine Menge für „${key}“ angeben.` };
    if (r.value < 0) return { error: "Nährstoffmengen dürfen nicht negativ sein." };
    if (key in out) return { error: `„${key}“ ist doppelt eingetragen.` };
    out[key] = r.value;
  }
  return { ok: out };
}

function SupplementForm({
  item,
  onSave,
  onCancel,
}: {
  item?: Supplement;
  onSave: (input: SupplementIn) => Promise<unknown>;
  onCancel: () => void;
}) {
  const [name, setName] = useState(item?.name ?? "");
  const [amount, setAmount] = useState<number | null>(item?.dose_amount ?? null);
  const [unit, setUnit] = useState(item?.dose_unit ?? "");
  const [rows, setRows] = useState<Row[]>(() =>
    Object.entries(item?.nutrients_per_day ?? {}).map(([k, v]) => newRow(k, v)),
  );
  const [taking, setTaking] = useState(item?.taking ?? true);
  const [time, setTime] = useState(item?.time_of_day ?? "");
  const [note, setNote] = useState(item?.note ?? "");

  const timeOptions = [
    { value: "", label: "Nicht festgelegt" },
    ...TIMES_OF_DAY.map((t) => ({ value: t, label: t })),
    ...(time && !TIMES_OF_DAY.includes(time) ? [{ value: time, label: time }] : []),
  ];

  const setRow = (rid: number, patch: Partial<Row>) =>
    setRows((rs) => rs.map((r) => (r.rid === rid ? { ...r, ...patch } : r)));

  function validate(): string | null {
    if (name.trim() === "") return "Bitte einen Namen angeben.";
    if (amount !== null && amount < 0) return "Die Dosis darf nicht negativ sein.";
    const n = buildNutrients(rows);
    return "error" in n ? n.error : null;
  }

  async function submit() {
    const n = buildNutrients(rows);
    if ("error" in n) throw new Error(n.error);
    await onSave({
      name: name.trim(),
      dose_amount: amount,
      dose_unit: optText(unit),
      nutrients_per_day: n.ok,
      taking,
      time_of_day: optText(time),
      note: optText(note),
    });
  }

  return (
    <FormShell
      title={item ? "Supplement bearbeiten" : "Supplement hinzufügen"}
      onSubmit={submit}
      onCancel={onCancel}
      validate={validate}
    >
      <TextField label="Name" value={name} onChange={setName} maxLength={120} required autoComplete="off" />
      <div className="crud-form-grid">
        <NumberField label="Dosis (Menge)" value={amount} onChange={setAmount} min={0} step="any" />
        <SuggestField
          label="Dosis (Einheit)"
          value={unit}
          onChange={setUnit}
          options={DOSE_UNITS.map((u) => ({ value: u }))}
          maxLength={20}
        />
      </div>

      <fieldset style={{ border: 0, padding: 0, margin: "0 0 12px" }}>
        <legend className="label" style={{ fontWeight: 600, padding: 0, marginBottom: 4 }}>
          Nährstoffbeitrag pro Tag
        </legend>
        <p className="muted" style={{ fontSize: ".85rem", margin: "0 0 8px" }}>
          Pro Zeile ein Nährstoff mit der Menge, die das Supplement am Tag liefert. Diese Beiträge werden bei
          Obergrenzen (z. B. Zink) zusammen mit dem Essen gezählt.
        </p>
        <datalist id="supplement-nutrient-keys">
          {suggestionOptions(SUPPLEMENT_NUTRIENT_KEYS, NUTRIENT_LABELS).map((o) => (
            <option key={o.value} value={o.value} label={o.label} />
          ))}
        </datalist>
        {rows.map((r, i) => (
          <div className="kv-row" key={r.rid}>
            <TextField
              label={`Nährstoff ${i + 1}`}
              value={r.key}
              onChange={(v) => setRow(r.rid, { key: v })}
              list="supplement-nutrient-keys"
              maxLength={60}
              autoComplete="off"
            />
            <NumberField
              label={`Menge pro Tag ${i + 1}`}
              value={r.value}
              onChange={(v) => setRow(r.rid, { value: v })}
              min={0}
              step="any"
            />
            <Button
              onClick={() => setRows((rs) => rs.filter((x) => x.rid !== r.rid))}
              aria-label={`Nährstoff ${i + 1} entfernen`}
            >
              Entfernen
            </Button>
          </div>
        ))}
        <Button onClick={() => setRows((rs) => [...rs, newRow()])}>Nährstoff hinzufügen</Button>
      </fieldset>

      <CheckField label="Nimmt aktuell" checked={taking} onChange={setTaking} />
      <SelectField label="Tageszeit" value={time} onChange={setTime} options={timeOptions} />
      <TextAreaField label="Notiz" value={note} onChange={setNote} maxLength={2000} />
    </FormShell>
  );
}

function contributions(s: Supplement): string {
  return Object.entries(s.nutrients_per_day ?? {})
    .map(([k, v]) => `${nutrientLabel(k)}: ${numDe(v)}`)
    .join(" · ");
}

export default function SupplementsPage() {
  const { items, data, loading, error, create, update, remove } = useCrud<Supplement, SupplementIn>("supplements");
  const [editing, setEditing] = useState<Editing>(null);
  const close = () => setEditing(null);

  return (
    <>
      <PageHeader
        title="Supplemente"
        actions={
          <Button variant="primary" onClick={() => setEditing({ mode: "new" })} disabled={editing?.mode === "new"}>
            Supplement hinzufügen
          </Button>
        }
      >
        Was du zusätzlich zum Essen einnimmst.
      </PageHeader>
      <Alert kind="info">
        Beiträge von Supplementen werden zusammen mit dem Essen auf Obergrenzen angerechnet (z. B. Zink). Trage
        deshalb pro Tag ein, wie viel jedes Supplement von einem Nährstoff liefert. Die Angaben stammen von dir; die
        App gibt keine Dosierungsempfehlungen.
      </Alert>

      {editing?.mode === "new" && (
        <SupplementForm
          onCancel={close}
          onSave={async (input) => {
            await create(input);
            close();
          }}
        />
      )}

      <Async loading={loading && !data} error={error}>
        {items.length === 0 && editing?.mode !== "new" ? (
          <EmptyList actionLabel="Erstes Supplement hinzufügen" onAction={() => setEditing({ mode: "new" })}>
            Noch keine Supplemente eingetragen. Füge hinzu, was du regelmäßig einnimmst, damit es bei den Grenzwerten
            mitgezählt wird.
          </EmptyList>
        ) : (
          <ResourceList
            items={items}
            ariaLabel="Supplemente"
            label={(s) => s.name}
            editingId={editingIdOf(editing)}
            onEdit={(s) => setEditing({ mode: "edit", id: s.id })}
            onRemove={remove}
            renderEditor={(s) => (
              <SupplementForm
                item={s}
                onCancel={close}
                onSave={async (input) => {
                  await update(s.id, input);
                  close();
                }}
              />
            )}
            renderItem={(s) => {
              const contrib = contributions(s);
              return (
                <>
                  <div className="crud-head">
                    <h3>{s.name}</h3>
                    {s.taking ? <Badge kind="ok">nimmt aktuell</Badge> : <Badge>nimmt aktuell nicht</Badge>}
                  </div>
                  <div className="crud-meta">
                    {s.dose_amount != null && (
                      <span>
                        Dosis: {numDe(s.dose_amount)}
                        {s.dose_unit ? ` ${s.dose_unit}` : ""}
                      </span>
                    )}
                    {s.time_of_day && <Badge>{s.time_of_day}</Badge>}
                  </div>
                  <div>
                    {contrib ? (
                      <span>Beitrag pro Tag: {contrib}</span>
                    ) : (
                      <span className="muted">Kein Nährstoffbeitrag eingetragen.</span>
                    )}
                  </div>
                  {s.note && <p className="crud-note">{s.note}</p>}
                </>
              );
            }}
          />
        )}
      </Async>
    </>
  );
}
