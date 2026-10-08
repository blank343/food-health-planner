import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { todayIso } from "../../format";
import { Alert, Badge, Button, Card, CheckField, EmptyState, SelectField, Spinner, TextField } from "../../ui";
import { AmountControl } from "./AmountControl";
import { MealResult, SumBar } from "./MealResult";
import { type Entry, initialEntry, presetSelection, toMealItem } from "./amounts";
import { type ComponentOut, type SlotName, isSlot, kindLabel, slotName } from "./types";
import { useMeal } from "./useMeal";
import { useSlotTargets } from "./useSlotTargets";
import "../Ingredients/Ingredients.css";

type Props = {
  components: ComponentOut[];
  onSeed: () => void;
  seeding: boolean;
};

/** Frühstück zusammenstellen: Komponenten wählen, Mengen einstellen, Live-Summe und Passung zum Slot-Ziel. */
export function Composer({ components, onSeed, seeding }: Props) {
  const [selected, setSelected] = useState<Record<number, Entry>>({});
  const [date, setDate] = useState(todayIso());
  const [slot, setSlot] = useState<SlotName | "">("breakfast");
  const targets = useSlotTargets(date || todayIso());

  // Komponenten oder Varianten können sich in der Verwaltung ändern: Auswahl bereinigen.
  useEffect(() => {
    setSelected((prev) => {
      let changed = false;
      const next: Record<number, Entry> = {};
      for (const [key, entry] of Object.entries(prev)) {
        const c = components.find((x) => x.id === Number(key));
        if (!c) {
          changed = true;
          continue;
        }
        if (entry.variantId !== null && !c.variants.some((v) => v.id === entry.variantId)) {
          changed = true;
          next[c.id] = initialEntry(c);
        } else next[c.id] = entry;
      }
      return changed ? next : prev;
    });
  }, [components]);

  // Slot, den es an diesem Tag nicht gibt (z. B. Mittag bei OMAD), wird ersetzt.
  useEffect(() => {
    if (targets.status === "ok" && slot !== "" && !targets.slots.includes(slot)) {
      setSlot(targets.slots[0] ?? "");
    }
  }, [targets.status, targets.slots, slot]);

  const items = useMemo(
    () =>
      components.flatMap((c) => {
        const e = selected[c.id];
        const item = e ? toMealItem(c, e) : null;
        return item ? [item] : [];
      }),
    [components, selected],
  );

  const fitSlot: SlotName | "" = targets.status === "unavailable" ? "" : slot;
  const meal = useMeal(items, date, fitSlot);
  const selectedCount = components.filter((c) => selected[c.id]).length;

  if (components.length === 0) {
    return (
      <EmptyState>
        <p>Noch keine Komponenten: Standard-Komponenten anlegen und das Frühstück daraus zusammenstellen.</p>
        <Button variant="primary" onClick={onSeed} disabled={seeding} aria-busy={seeding}>
          {seeding ? "Legt an …" : "Standard-Komponenten anlegen"}
        </Button>
      </EmptyState>
    );
  }

  const slotOptions = [
    { value: "", label: "Kein Slot (nur Summe)" },
    ...targets.slots.map((s) => ({ value: s, label: slotName(s) })),
  ];

  return (
    <>
      <Card title="Start und Ziel">
        <p className="muted">Eine Voreinstellung wählen und dann die Mengen anpassen.</p>
        <div className="preset-row" style={{ marginBottom: 12 }}>
          <Button onClick={() => setSelected(presetSelection(components, "weekday"))}>Werktag</Button>
          <Button onClick={() => setSelected(presetSelection(components, "weekend"))}>Wochenende</Button>
          <Button variant="ghost" onClick={() => setSelected({})} disabled={selectedCount === 0}>
            Alles abwählen
          </Button>
        </div>
        <div className="filter-grid">
          <TextField label="Datum" type="date" value={date} onChange={setDate} hint="Für das Ziel dieses Tages." />
          <SelectField
            label="Slot"
            value={slot}
            onChange={(v) => setSlot(isSlot(v) ? v : "")}
            options={slotOptions}
          />
        </div>
        {targets.status === "unavailable" && (
          <Alert kind="warn">
            <strong>Das Tagesziel kann noch nicht berechnet werden.</strong>
            <br />
            {targets.message}
            <br />
            Die Summen siehst du trotzdem. Für die Passung braucht es ein aktuelles Gewicht und die Körpergröße (
            <Link to="/ziele">Tagesziel</Link>, <Link to="/einstellungen">Einstellungen</Link>).
          </Alert>
        )}
        {targets.status === "error" && <Alert kind="warn">Die Slots konnten nicht geladen werden: {targets.message}</Alert>}
      </Card>

      {meal.data && <SumBar meal={meal.data} pending={meal.pending} />}

      <Card title="Komponenten">
        <ul className="crud-list" aria-label="Komponenten wählen">
          {components.map((c) => {
            const entry = selected[c.id];
            return (
              <li key={c.id} className={`comp-card ${entry ? "on" : ""}`.trim()}>
                <CheckField
                  label={c.name}
                  checked={!!entry}
                  onChange={(on) =>
                    setSelected((prev) => {
                      const next = { ...prev };
                      if (on) next[c.id] = initialEntry(c);
                      else delete next[c.id];
                      return next;
                    })
                  }
                />
                <div className="crud-meta">
                  <Badge>{kindLabel(c.kind)}</Badge>
                  {c.weekend_fixed && <Badge kind="warn">Wochenende fest</Badge>}
                  <small className="muted">{c.ingredient_name}</small>
                </div>
                {entry && (
                  <AmountControl
                    component={c}
                    entry={entry}
                    onChange={(e) => setSelected((prev) => ({ ...prev, [c.id]: e }))}
                  />
                )}
              </li>
            );
          })}
        </ul>
      </Card>

      <div aria-busy={meal.pending}>
        {items.length === 0 && (
          <Alert kind="info">Wähle mindestens eine Komponente mit einer Menge über 0, um Summen und Passung zu sehen.</Alert>
        )}
        {meal.error && <Alert kind="error">{meal.error}</Alert>}
        {meal.pending && !meal.data && selectedCount > 0 && !meal.error && <Spinner label="Berechne Mahlzeit …" />}
        {meal.data && <MealResult meal={meal.data} fitIssue={meal.fitIssue} slotRequested={fitSlot !== ""} />}
      </div>
    </>
  );
}
