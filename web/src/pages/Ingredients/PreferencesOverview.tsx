import { useState } from "react";
import { useQuery } from "../../hooks/useApi";
import { Alert, Async, Badge, Button, Card, EmptyState, SelectField } from "../../ui";
import { PreferenceControl } from "./PreferenceControl";
import { LEVELS, LEVEL_LABELS, type PrefLevel, type PreferenceOut, isLevel, levelLabel } from "./labels";
import type { Preferences } from "./usePreferences";
import "./Ingredients.css";

type Props = {
  prefs: Preferences;
  onOpen: (id: number) => void;
};

const FILTER_OPTIONS = [{ value: "", label: "Alle Stufen" }, ...LEVELS.map((l) => ({ value: l, label: LEVEL_LABELS[l] }))];

/** „Meine Vorlieben“: alle eigenen Einstellungen, filterbar nach Stufe, mit direkter Änderung. */
export function PreferencesOverview({ prefs, onOpen }: Props) {
  const [level, setLevel] = useState<PrefLevel | "">("");
  const q = useQuery<PreferenceOut[]>(level ? `/me/ingredient-preferences?level=${level}` : "/me/ingredient-preferences");
  const items = q.data ?? [];

  async function change(id: number, l: PrefLevel | null) {
    if (l) await prefs.set(id, l);
    else await prefs.clear(id);
    q.reload();
  }

  return (
    <>
      <Alert kind="info">
        „Nie“ ist eine harte Grenze: Der spätere Planer schlägt Rezepte mit dieser Zutat gar nicht erst vor. „Mag ich nicht“
        wird nach Möglichkeit vermieden, „Mag ich“ bevorzugt. Die Vorlieben gelten nur für dich.
      </Alert>
      <Card>
        <SelectField
          label="Nach Stufe filtern"
          value={level}
          onChange={(v) => setLevel(isLevel(v) ? v : "")}
          options={FILTER_OPTIONS}
        />
      </Card>
      {prefs.error && <Alert kind="error">{prefs.error}</Alert>}
      <Async loading={q.loading && !q.data} error={q.error}>
        {items.length === 0 ? (
          <EmptyState>
            <p>
              {level
                ? `Keine Zutaten mit der Stufe „${levelLabel(level)}“.`
                : "Noch keine Vorlieben. Öffne eine Zutat im Katalog und lege fest, ob du sie magst."}
            </p>
          </EmptyState>
        ) : (
          <ul className="ing-list" aria-label="Meine Vorlieben">
            {items.map((p) => (
              <li key={p.ingredient_id} className="ing-item">
                <div className="crud-head">
                  <button type="button" className="ing-name" onClick={() => onOpen(p.ingredient_id)} style={{ width: "auto" }}>
                    {p.ingredient_name}
                  </button>
                  <Badge kind={p.level === "like" ? "ok" : "error"}>{levelLabel(p.level)}</Badge>
                </div>
                <PreferenceControl
                  name={p.ingredient_name}
                  level={isLevel(p.level) ? p.level : null}
                  onChange={(l) => void change(p.ingredient_id, l)}
                  showHelp={false}
                />
                <Button variant="ghost" onClick={() => void change(p.ingredient_id, null)} aria-label={`Vorliebe für ${p.ingredient_name} entfernen`}>
                  Vorliebe entfernen
                </Button>
              </li>
            ))}
          </ul>
        )}
      </Async>
    </>
  );
}
