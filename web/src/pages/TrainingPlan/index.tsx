import { useState } from "react";
import type { components } from "../../api/schema";
import {
  type Editing,
  EmptyList,
  FormShell,
  ResourceList,
  SuggestField,
  TextAreaField,
  editingIdOf,
  hhmm,
  numDe,
  optText,
  withPlaceholder,
} from "../../components/crud";
import { WEEKDAYS } from "../../format";
import { useCrud } from "../../hooks/useCrud";
import { Alert, Async, Badge, Button, CheckField, NumberField, PageHeader, SelectField, Stat, TextField } from "../../ui";

type Item = components["schemas"]["TrainingItemOut"];
type ItemIn = components["schemas"]["TrainingItemIn"];
type Intensity = ItemIn["intensity"];

export const INTENSITY_LABELS: Record<Intensity, string> = { easy: "leicht", moderate: "mittel", hard: "hart" };
const INTENSITIES: Intensity[] = ["easy", "moderate", "hard"];
const SESSION_SUGGESTIONS = ["Krafttraining", "Laufen", "Radfahren", "Schwimmen", "Spazieren", "Yoga", "Mobility"];

const isIntensity = (v: string): v is Intensity => (INTENSITIES as string[]).includes(v);

type Preset = { weekday: number };

function SessionForm({
  item,
  preset,
  onSave,
  onCancel,
}: {
  item?: Item;
  preset?: Preset;
  onSave: (input: ItemIn) => Promise<unknown>;
  onCancel: () => void;
}) {
  const [weekday, setWeekday] = useState(String(item?.weekday ?? preset?.weekday ?? 0));
  const [type, setType] = useState(item?.session_type ?? "");
  const [intensity, setIntensity] = useState<string>(item?.intensity ?? "");
  const [start, setStart] = useState(hhmm(item?.start_time));
  const [duration, setDuration] = useState<number | null>(item?.duration_min ?? null);
  const [kcal, setKcal] = useState<number | null>(item?.expected_kcal ?? null);
  const [enabled, setEnabled] = useState(item?.enabled ?? true);
  const [note, setNote] = useState(item?.note ?? "");

  function validate(): string | null {
    if (type.trim() === "") return "Bitte die Art der Einheit angeben (z. B. Laufen).";
    if (!isIntensity(intensity)) return "Bitte die Intensität wählen.";
    if (duration !== null && (duration <= 0 || duration > 1440)) return "Die Dauer muss zwischen 1 und 1440 Minuten liegen.";
    if (kcal !== null && (kcal < 0 || kcal > 10000)) return "Die erwarteten kcal müssen zwischen 0 und 10.000 liegen.";
    return null;
  }

  async function submit() {
    if (!isIntensity(intensity)) return;
    await onSave({
      weekday: Number(weekday),
      session_type: type.trim(),
      intensity,
      start_time: start === "" ? null : start,
      duration_min: duration,
      expected_kcal: kcal,
      enabled,
      note: optText(note),
    });
  }

  return (
    <FormShell
      title={item ? "Einheit bearbeiten" : "Einheit hinzufügen"}
      onSubmit={submit}
      onCancel={onCancel}
      validate={validate}
    >
      <SelectField
        label="Wochentag"
        value={weekday}
        onChange={setWeekday}
        options={WEEKDAYS.map((d, i) => ({ value: String(i), label: d }))}
      />
      <SuggestField
        label="Art der Einheit"
        value={type}
        onChange={setType}
        options={SESSION_SUGGESTIONS.map((s) => ({ value: s }))}
        maxLength={60}
      />
      <SelectField
        label="Intensität"
        value={intensity}
        onChange={setIntensity}
        options={withPlaceholder(INTENSITIES.map((i) => ({ value: i, label: INTENSITY_LABELS[i] })))}
      />
      <div className="crud-form-grid">
        <TextField label="Uhrzeit (optional)" type="time" value={start} onChange={setStart} />
        <NumberField label="Dauer" unit="min" value={duration} onChange={setDuration} min={1} max={1440} step="any" />
      </div>
      <NumberField label="Erwartete Kalorien" unit="kcal" value={kcal} onChange={setKcal} min={0} max={10000} step="any" />
      <CheckField label="Aktiv" checked={enabled} onChange={setEnabled} />
      <TextAreaField label="Notiz" value={note} onChange={setNote} maxLength={2000} />
    </FormShell>
  );
}

export default function TrainingPlanPage() {
  const { items, data, loading, error, create, update, remove } = useCrud<Item, ItemIn>("training-plan");
  const [editing, setEditing] = useState<Editing<Preset>>(null);
  const close = () => setEditing(null);

  const active = items.filter((i) => i.enabled);
  const byIntensity = (k: Intensity) => active.filter((i) => i.intensity === k).length;
  const trainingDays = new Set(active.map((i) => i.weekday)).size;

  return (
    <>
      <PageHeader title="Training">Dein Wochenplan: Was machst du an welchem Tag?</PageHeader>
      <Alert kind="info">
        Der Planer nutzt pro Tag die härteste aktive Einheit, um die Energie zu verteilen. Tage ohne Einheit gelten als
        Ruhetage.
      </Alert>

      <Async loading={loading && !data} error={error}>
        {items.length === 0 && editing === null && (
          <EmptyList actionLabel="Erste Einheit hinzufügen" onAction={() => setEditing({ mode: "new", preset: { weekday: 0 } })}>
            Noch keine Trainingseinheiten. Lege fest, was du in der Woche machst. Ohne Einheiten gilt jeder Tag als
            Ruhetag.
          </EmptyList>
        )}

        <section aria-label="Zusammenfassung" className="card">
          <h2>Zusammenfassung</h2>
          <div className="grid">
            <Stat label="Einheiten pro Woche" value={active.length} hint="nur aktive" />
            <Stat label="Trainingstage" value={trainingDays} hint={`${7 - trainingDays} Ruhetage`} />
            {INTENSITIES.map((k) => (
              <Stat key={k} label={`Intensität ${INTENSITY_LABELS[k]}`} value={byIntensity(k)} />
            ))}
          </div>
        </section>

        <div className="week-grid">
          {WEEKDAYS.map((day, weekday) => {
            const dayItems = items.filter((i) => i.weekday === weekday);
            const adding = editing?.mode === "new" && editing.preset?.weekday === weekday;
            return (
              <section key={day} className="week-day" aria-label={day}>
                <h2>{day}</h2>
                {dayItems.length === 0 && !adding && <p className="week-rest">Ruhetag (keine Einheit)</p>}
                {dayItems.length > 0 && (
                  <ResourceList
                    items={dayItems}
                    ariaLabel={`Einheiten am ${day}`}
                    label={(i) => `${i.session_type} am ${day}`}
                    editingId={editingIdOf(editing)}
                    onEdit={(i) => setEditing({ mode: "edit", id: i.id })}
                    onRemove={remove}
                    renderEditor={(i) => (
                      <SessionForm
                        item={i}
                        onCancel={close}
                        onSave={async (input) => {
                          await update(i.id, input);
                          close();
                        }}
                      />
                    )}
                    renderItem={(i) => (
                      <>
                        <div className="crud-head">
                          <h3>{i.session_type}</h3>
                          <Badge kind={i.intensity === "hard" ? "warn" : undefined}>{INTENSITY_LABELS[i.intensity]}</Badge>
                        </div>
                        <div className="crud-meta">
                          {i.start_time && <span>{hhmm(i.start_time)} Uhr</span>}
                          {i.duration_min != null && <span>{numDe(i.duration_min)} min</span>}
                          {i.expected_kcal != null && <span>{numDe(i.expected_kcal)} kcal</span>}
                          {!i.enabled && <Badge>pausiert</Badge>}
                        </div>
                        {i.note && <p className="crud-note">{i.note}</p>}
                      </>
                    )}
                  />
                )}
                {adding && (
                  <SessionForm
                    preset={editing.preset}
                    onCancel={close}
                    onSave={async (input) => {
                      await create(input);
                      close();
                    }}
                  />
                )}
                {!adding && (
                  <Button
                    onClick={() => setEditing({ mode: "new", preset: { weekday } })}
                    aria-label={`Einheit hinzufügen: ${day}`}
                  >
                    Einheit hinzufügen
                  </Button>
                )}
              </section>
            );
          })}
        </div>
      </Async>
    </>
  );
}
