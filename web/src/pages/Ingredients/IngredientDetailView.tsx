import { useCallback, useState } from "react";
import { api } from "../../api/client";
import { ConfirmDelete } from "../../components/crud";
import { useAction, useQuery } from "../../hooks/useApi";
import { num } from "../../format";
import { Alert, Async, Badge, Button, Card, Table, TextField } from "../../ui";
import { IngredientForm } from "./IngredientForm";
import { PreferenceControl } from "./PreferenceControl";
import { SettingsForm } from "./SettingsForm";
import {
  type IngredientDetail,
  type IngredientIn,
  type IngredientPatch,
  type PrefLevel,
  fmt,
  microEntries,
  saltOf,
  sourceLabel,
} from "./labels";
import type { Preferences } from "./usePreferences";
import "./Ingredients.css";

type Props = {
  id: number;
  prefs: Preferences;
  onBack: () => void;
  /** Nach Änderungen: die Trefferliste neu laden. */
  onChanged: () => void;
  onDeleted: () => void;
};

type Mode = "view" | "edit" | "confirm-delete";

function Synonyms({ item, onChanged }: { item: IngredientDetail; onChanged: () => void }) {
  const [alias, setAlias] = useState("");
  const add = useAction(
    useCallback(
      async (text: string) => {
        await api("POST", `/ingredients/${item.id}/synonyms`, { alias: text });
        onChanged();
        return true;
      },
      [item.id, onChanged],
    ),
  );
  const remove = useAction(
    useCallback(
      async (text: string) => {
        await api("DELETE", `/ingredients/${item.id}/synonyms/${encodeURIComponent(text)}`);
        onChanged();
      },
      [item.id, onChanged],
    ),
  );

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    const text = alias.trim();
    if (!text) return;
    const ok = await add.run(text);
    if (ok) setAlias((cur) => (cur.trim() === text ? "" : cur));
  }

  return (
    <Card title="Synonyme">
      <p className="muted">
        Andere Namen, unter denen die Zutat in Rezepten vorkommt (z. B. „Magerquark“ für „Quark, mager“). Sie helfen bei
        der automatischen Zuordnung.
      </p>
      {item.synonyms.length === 0 ? (
        <p className="muted">Noch keine Synonyme.</p>
      ) : (
        <ul className="chips" aria-label="Synonyme">
          {item.synonyms.map((s) => (
            <li key={s} className="chip">
              <span>{s}</span>
              <Button
                aria-label={`Synonym „${s}“ entfernen`}
                onClick={() => void remove.run(s)}
                disabled={remove.busy}
              >
                ×
              </Button>
            </li>
          ))}
        </ul>
      )}
      {remove.error && <Alert kind="error">{remove.error}</Alert>}
      <form className="inline-form" onSubmit={submit} noValidate>
        <TextField label="Neues Synonym" value={alias} onChange={setAlias} maxLength={200} autoComplete="off" />
        <Button type="submit" disabled={add.busy || alias.trim() === ""}>
          Hinzufügen
        </Button>
      </form>
      {add.error && <Alert kind="error">{add.error}</Alert>}
    </Card>
  );
}

function NutrientTable({ item }: { item: IngredientDetail }) {
  const n = item.nutrients;
  const salt = saltOf(n);
  const micros = microEntries(n.micros ?? {});
  return (
    <Card title="Nährwerte je 100 g">
      <Table>
        <tbody>
          <tr>
            <th scope="row">Kalorien</th>
            <td className="num">{num(n.kcal, 0, "kcal")}</td>
          </tr>
          <tr>
            <th scope="row">Protein</th>
            <td className="num">{num(n.protein_g, 1, "g")}</td>
          </tr>
          <tr>
            <th scope="row">Fett</th>
            <td className="num">{num(n.fat_g, 1, "g")}</td>
          </tr>
          <tr>
            <th scope="row">Kohlenhydrate</th>
            <td className="num">{num(n.carb_g, 1, "g")}</td>
          </tr>
          <tr>
            <th scope="row">Ballaststoffe</th>
            <td className="num">{num(n.fiber_g, 1, "g")}</td>
          </tr>
          <tr>
            <th scope="row">Salz{n.salt_g === null && salt !== null ? " (aus Natrium)" : ""}</th>
            <td className="num">{num(salt, 2, "g")}</td>
          </tr>
        </tbody>
      </Table>
      <h3>Mikronährstoffe</h3>
      {micros.length === 0 ? (
        <p className="muted">Keine Mikronährstoffe hinterlegt.</p>
      ) : (
        <Table>
          <tbody>
            {micros.map(([key, label, value]) => (
              <tr key={key}>
                <th scope="row">{label}</th>
                <td className="num">{fmt(value)}</td>
              </tr>
            ))}
          </tbody>
        </Table>
      )}
      <h3>Umrechnung und Haltbarkeit</h3>
      <Table>
        <tbody>
          <tr>
            <th scope="row">Dichte</th>
            <td className="num">{item.density_g_per_ml === null ? "–" : num(item.density_g_per_ml, 2, "g/ml")}</td>
          </tr>
          <tr>
            <th scope="row">Stückgewicht</th>
            <td className="num">{item.piece_g === null ? "–" : num(item.piece_g, 0, "g")}</td>
          </tr>
          <tr>
            <th scope="row">Haltbarkeit</th>
            <td className="num">{item.shelf_days === null ? "–" : `${item.shelf_days} Tage`}</td>
          </tr>
        </tbody>
      </Table>
    </Card>
  );
}

/** Detailansicht einer Zutat: Nährwerte, Vorliebe, Synonyme, Einstellungen bzw. Bearbeiten und Löschen. */
export function IngredientDetailView({ id, prefs, onBack, onChanged, onDeleted }: Props) {
  const q = useQuery<IngredientDetail>(`/ingredients/${id}`);
  const [mode, setMode] = useState<Mode>("view");
  const item = q.data;
  const manual = item?.source === "manual";
  const reload = q.reload;
  const changed = useCallback(() => {
    reload();
    onChanged();
  }, [reload, onChanged]);

  const patch = async (p: IngredientPatch | IngredientIn) => {
    await api<IngredientDetail>("PATCH", `/ingredients/${id}`, p);
    setMode("view");
    changed();
  };

  const level = (item && (prefs.byId.get(item.id)?.level as PrefLevel | undefined)) ?? null;

  return (
    <>
      <div className="row" style={{ marginBottom: 12 }}>
        <Button onClick={onBack}>← Zurück zur Liste</Button>
      </div>
      <Async loading={q.loading && !item} error={q.error}>
        {item && (
          <>
            <header>
              <h2 style={{ fontSize: "1.3rem" }}>{item.name}</h2>
              <div className="crud-meta">
                <Badge>{sourceLabel(item.source)}</Badge>
                {item.category && <Badge>{item.category}</Badge>}
                {item.hidden && <Badge kind="warn">ausgeblendet</Badge>}
                {item.is_potassium_salt && <Badge kind="warn">Kaliumsalz</Badge>}
                {item.is_fish && <Badge>Fisch</Badge>}
                {item.source_code && <small className="muted">Code {item.source_code}</small>}
              </div>
            </header>

            <Card title="Meine Vorliebe">
              <PreferenceControl
                name={item.name}
                level={level}
                onChange={(l) => void (l ? prefs.set(item.id, l) : prefs.clear(item.id))}
              />
              {prefs.error && <Alert kind="error">{prefs.error}</Alert>}
            </Card>

            <NutrientTable item={item} />
            <Synonyms item={item} onChanged={changed} />

            {mode === "edit" &&
              (manual ? (
                <IngredientForm item={item} onSave={patch} onCancel={() => setMode("view")} />
              ) : (
                <SettingsForm item={item} onSave={patch} onCancel={() => setMode("view")} />
              ))}

            {mode !== "edit" && (
              <Card title={manual ? "Zutat verwalten" : "Einstellungen"}>
                {!manual && (
                  <p className="muted">
                    Diese Zutat stammt aus {sourceLabel(item.source)}. Name und Nährwerte bleiben unverändert; du kannst
                    sie ausblenden und Dichte, Stückgewicht, Haltbarkeit und die Kaliumsalz-Markierung ergänzen.
                  </p>
                )}
                <div className="row">
                  <Button variant="primary" onClick={() => setMode("edit")}>
                    {manual ? "Bearbeiten" : "Einstellungen ändern"}
                  </Button>
                  {manual && mode === "view" && (
                    <Button variant="danger" onClick={() => setMode("confirm-delete")}>
                      Löschen
                    </Button>
                  )}
                </div>
                {mode === "confirm-delete" && (
                  <ConfirmDelete
                    name={item.name}
                    onCancel={() => setMode("view")}
                    onConfirm={async () => {
                      await api("DELETE", `/ingredients/${item.id}`);
                      onChanged();
                      onDeleted();
                    }}
                  />
                )}
              </Card>
            )}
          </>
        )}
      </Async>
      {q.error && item && <Alert kind="error">{q.error}</Alert>}
    </>
  );
}
