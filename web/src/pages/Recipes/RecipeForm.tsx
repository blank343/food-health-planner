import { useState } from "react";
import { api } from "../../api/client";
import { FormShell, TextAreaField, optText } from "../../components/crud";
import { CheckField, NumberField, TextField } from "../../ui";
import { splitLines } from "./format";
import {
  type Line,
  type LineIn,
  type RecipeCreate,
  type RecipeDetail,
  type RecipePatch,
  SLOT_NAMES,
  SLOTS,
  type SlotName,
} from "./types";
import "./Recipes.css";

const MAX_LINE = 400;
const MAX_LINES = 100;

/**
 * Wandelt den Zutatentext in Zeilen für die API. Unveränderte Zeilen behalten ihre `id` (und damit
 * ihre Zuordnung), neue oder geänderte Zeilen werden als Freitext gesendet.
 */
export function buildLines(text: string, original: Line[] = []): LineIn[] {
  const pool = new Map<string, Line[]>();
  for (const l of original) pool.set(l.raw_text, [...(pool.get(l.raw_text) ?? []), l]);
  return splitLines(text).map((t) => {
    const hit = pool.get(t)?.shift();
    return hit ? { id: hit.id, raw_text: t } : { raw_text: t };
  });
}

type Props = {
  mode: "new" | "edit";
  recipe?: RecipeDetail;
  onSaved: (recipe: RecipeDetail) => void;
  onCancel: () => void;
};

function isMinutes(v: number | null): boolean {
  return v === null || (Number.isInteger(v) && v >= 0 && v <= 10_000);
}

/** Formular zum Anlegen (Titel, Portionen, Zutaten, Anleitung) und zum vollständigen Bearbeiten eines Rezepts. */
export function RecipeForm({ mode, recipe, onSaved, onCancel }: Props) {
  const edit = mode === "edit" && recipe !== undefined;
  const [title, setTitle] = useState(recipe?.title ?? "");
  const [servings, setServings] = useState<number | null>(recipe?.servings ?? 2);
  const [prep, setPrep] = useState<number | null>(recipe?.prep_min ?? null);
  const [cook, setCook] = useState<number | null>(recipe?.cook_min ?? null);
  const [slots, setSlots] = useState<SlotName[]>(() => (recipe?.tag.slot_types ?? []).filter((s): s is SlotName => (SLOTS as readonly string[]).includes(s)));
  const [warm, setWarm] = useState(recipe?.tag.warm ?? false);
  const [transportable, setTransportable] = useState(recipe?.tag.transportable ?? false);
  const [batch, setBatch] = useState(recipe?.tag.batch_cookable ?? false);
  const [cuisine, setCuisine] = useState(recipe?.tag.cuisine ?? "");
  const [main, setMain] = useState(recipe?.tag.main_ingredient ?? "");
  const [lines, setLines] = useState((recipe?.lines ?? []).map((l) => l.raw_text).join("\n"));
  const [instructions, setInstructions] = useState(recipe?.instructions ?? "");
  const [notes, setNotes] = useState(recipe?.notes ?? "");
  const [favorite, setFavorite] = useState(recipe?.favorite ?? false);

  function validate(): string | null {
    if (title.trim() === "") return "Bitte einen Titel angeben.";
    if (servings === null || servings <= 0 || servings > 100) return "Die Portionszahl muss zwischen 0 und 100 liegen.";
    if (!isMinutes(prep) || !isMinutes(cook)) return "Zeiten sind ganze Minuten (0 oder mehr).";
    const parsed = splitLines(lines);
    if (parsed.length > MAX_LINES) return `Höchstens ${MAX_LINES} Zutatenzeilen sind erlaubt.`;
    const tooLong = parsed.find((l) => l.length > MAX_LINE);
    if (tooLong) return `Eine Zutatenzeile ist zu lang (höchstens ${MAX_LINE} Zeichen): „${tooLong.slice(0, 40)} …“`;
    return null;
  }

  async function submit() {
    if (servings === null) return;
    if (edit && recipe) {
      const patch: RecipePatch = {
        title: title.trim(),
        servings,
        prep_min: prep,
        cook_min: cook,
        instructions: optText(instructions),
        notes: optText(notes),
        favorite,
        tag: {
          slot_types: slots,
          warm,
          transportable,
          batch_cookable: batch,
          cuisine: optText(cuisine),
          main_ingredient: optText(main),
        },
        lines: buildLines(lines, recipe.lines),
      };
      onSaved(await api<RecipeDetail>("PATCH", `/recipes/${recipe.id}`, patch));
      return;
    }
    const create: RecipeCreate = {
      title: title.trim(),
      servings,
      instructions: optText(instructions),
      favorite: false,
      lines: buildLines(lines),
    };
    onSaved(await api<RecipeDetail>("POST", "/recipes", create));
  }

  const toggleSlot = (s: SlotName, on: boolean) =>
    setSlots((cur) => (on ? SLOTS.filter((x) => x === s || cur.includes(x)) : cur.filter((x) => x !== s)));

  return (
    <FormShell
      title={edit ? "Rezept bearbeiten" : "Neues Rezept"}
      submitLabel={edit ? "Speichern" : "Rezept anlegen"}
      onSubmit={submit}
      onCancel={onCancel}
      validate={validate}
    >
      <TextField label="Titel" value={title} onChange={setTitle} maxLength={300} required autoComplete="off" />
      <div className="crud-form-grid">
        <NumberField label="Portionen" value={servings} onChange={setServings} min={0.5} max={100} step="any" required />
        {edit && (
          <>
            <NumberField label="Vorbereitung" unit="Min." value={prep} onChange={setPrep} min={0} step={1} />
            <NumberField label="Kochzeit" unit="Min." value={cook} onChange={setCook} min={0} step={1} />
          </>
        )}
      </div>

      {edit && (
        <>
          <fieldset className="rc-fieldset">
            <legend className="label">Passt zu (Slot-Eignung)</legend>
            <div className="crud-toggles">
              {SLOTS.map((s) => (
                <CheckField key={s} label={SLOT_NAMES[s]} checked={slots.includes(s)} onChange={(on) => toggleSlot(s, on)} />
              ))}
            </div>
          </fieldset>
          <fieldset className="rc-fieldset">
            <legend className="label">Eigenschaften</legend>
            <div className="crud-toggles">
              <CheckField label="Warm" checked={warm} onChange={setWarm} />
              <CheckField label="Transportierbar" checked={transportable} onChange={setTransportable} />
              <CheckField label="Vorkochbar" checked={batch} onChange={setBatch} />
            </div>
          </fieldset>
          <div className="crud-form-grid">
            <TextField label="Küche" value={cuisine} onChange={setCuisine} maxLength={60} autoComplete="off" />
            <TextField label="Hauptzutat" value={main} onChange={setMain} maxLength={80} autoComplete="off" />
          </div>
        </>
      )}

      <TextAreaField
        label="Zutaten (eine pro Zeile)"
        hint={
          edit
            ? "Unveränderte Zeilen behalten ihre Zuordnung. Geänderte oder neue Zeilen werden neu erkannt."
            : "Zum Beispiel „200 g Haferflocken“ oder „2 EL Olivenöl“. Die Zuordnung zu Zutaten geschieht danach."
        }
        value={lines}
        onChange={setLines}
        rows={8}
      />
      <TextAreaField label="Anleitung" value={instructions} onChange={setInstructions} rows={6} maxLength={20000} />
      {edit && (
        <>
          <TextAreaField label="Notizen" value={notes} onChange={setNotes} rows={3} maxLength={5000} />
          <CheckField label="Favorit" checked={favorite} onChange={setFavorite} />
        </>
      )}
    </FormShell>
  );
}
