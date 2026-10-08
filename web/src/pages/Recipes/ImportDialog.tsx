import { type FormEvent, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../../api/client";
import { numDe } from "../../components/crud";
import { num } from "../../format";
import { Alert, Button, CheckField, SelectField, Spinner, TextField } from "../../ui";
import { type ErrorInfo, errorInfo, existingRecipeId, minutesDetail, quantityText } from "./format";
import { Modal } from "./Modal";
import { detailLink } from "./RecipeCardView";
import type { Preview, PreviewLine, RecipeDetail } from "./types";
import "./Recipes.css";

type Props = {
  onClose: () => void;
  /** Rezept wurde gespeichert: Seite zeigt das Detail */
  onImported: (id: number) => void;
};

const LEAD: Record<number, string> = {
  409: "Dieses Rezept gibt es schon.",
  422: "Diese Adresse lässt sich nicht als Rezept lesen.",
  502: "Die Seite hat nicht richtig geantwortet.",
  0: "Keine Verbindung.",
};

/** Verständliche Darstellung eines Importfehlers; bei 409 mit Link zum vorhandenen Rezept. */
export function ImportError({ error, onOpen }: { error: ErrorInfo; onOpen: () => void }) {
  const existing = error.status === 409 ? existingRecipeId(error.message) : null;
  return (
    <Alert kind="error">
      <strong>{LEAD[error.status] ?? "Der Import ist fehlgeschlagen."}</strong> {error.message}
      {existing !== null && (
        <>
          {" "}
          <Link to={detailLink(existing)} onClick={onOpen}>
            Vorhandenes Rezept öffnen
          </Link>
        </>
      )}
      {error.status === 502 && <> Bitte später erneut versuchen oder das Rezept von Hand anlegen.</>}
    </Alert>
  );
}

/** Gespeicherte Zeilen den Vorschauzeilen zuordnen (gleiche Reihenfolge, Text als Absicherung). */
function matchSavedLines(saved: RecipeDetail["lines"], preview: PreviewLine[]): (number | null)[] {
  const ordered = [...saved].sort((a, b) => a.position - b.position);
  const used = new Set<number>();
  return preview.map((p, index) => {
    const text = p.raw_text.trim().slice(0, 400);
    const byIndex = ordered[index];
    const hit =
      byIndex && byIndex.raw_text === text && !used.has(byIndex.id)
        ? byIndex
        : ordered.find((l) => l.raw_text === text && !used.has(l.id));
    if (!hit) return null;
    used.add(hit.id);
    return hit.id;
  });
}

function lineDetail(line: PreviewLine): string {
  const parts: string[] = [];
  if (line.quantity !== null || line.unit) parts.push(quantityText(line.quantity, line.unit));
  if (line.grams !== null) parts.push(`≈ ${num(line.grams, 0, "g")}`);
  if (line.optional) parts.push("optional");
  if (line.note) parts.push(line.note);
  return parts.join(" · ");
}

export function ImportDialog({ onClose, onImported }: Props) {
  const [url, setUrl] = useState("");
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<ErrorInfo | null>(null);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [choices, setChoices] = useState<Record<number, string>>({});
  const [remember, setRemember] = useState(true);
  const [partial, setPartial] = useState<{ id: number; failed: number } | null>(null);

  async function loadPreview(e: FormEvent) {
    e.preventDefault();
    const address = url.trim();
    if (!/^https?:\/\//i.test(address)) {
      setError({ status: 0, message: "Bitte eine Adresse mit http:// oder https:// eingeben." });
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const p = await api<Preview>("POST", "/recipes/import-preview", { url: address });
      setPreview(p);
      setChoices(Object.fromEntries(p.lines.map((l, i) => [i, l.ingredient_id === null ? "" : String(l.ingredient_id)])));
    } catch (err) {
      setPreview(null);
      setError(errorInfo(err));
    } finally {
      setLoading(false);
    }
  }

  async function save() {
    if (!preview) return;
    setSaving(true);
    setError(null);
    let recipe: RecipeDetail;
    try {
      recipe = await api<RecipeDetail>("POST", "/recipes/import", { url: url.trim() });
    } catch (err) {
      setError(errorInfo(err));
      setSaving(false);
      return;
    }
    // Geänderte oder neu gewählte Zuordnungen übernehmen (der Import selbst ordnet nur sichere Treffer zu)
    const savedIds = matchSavedLines(recipe.lines, preview.lines);
    let failed = 0;
    for (let i = 0; i < preview.lines.length; i++) {
      const chosen = choices[i] ?? "";
      const original = preview.lines[i]!.ingredient_id;
      if (chosen === "" || chosen === (original === null ? "" : String(original))) continue;
      const lineId = savedIds[i];
      if (lineId === null || lineId === undefined) {
        failed++;
        continue;
      }
      try {
        await api("POST", `/recipe-lines/${lineId}/assign`, { ingredient_id: Number(chosen), save_synonym: remember });
      } catch {
        failed++;
      }
    }
    setSaving(false);
    if (failed > 0) setPartial({ id: recipe.id, failed });
    else onImported(recipe.id);
  }

  const busy = loading || saving;

  return (
    <Modal title="Rezept importieren" onClose={onClose}>
      {partial ? (
        <>
          <Alert kind="warn">
            Das Rezept ist gespeichert. {partial.failed === 1 ? "Eine Zuordnung" : `${partial.failed} Zuordnungen`} konnte
            nicht übernommen werden. Bitte im Rezept oder in der Liste „Zutaten prüfen“ nachholen.
          </Alert>
          <div className="row end">
            <Button variant="primary" onClick={() => onImported(partial.id)}>
              Rezept öffnen
            </Button>
          </div>
        </>
      ) : (
        <>
          <form onSubmit={loadPreview} noValidate>
            <TextField
              label="Adresse des Rezepts (URL)"
              type="url"
              inputMode="url"
              placeholder="https://…"
              value={url}
              onChange={(v) => {
                setUrl(v);
                if (preview) setPreview(null);
              }}
              autoComplete="off"
              hint="Es wird nichts gespeichert, bevor Sie die Vorschau bestätigt haben."
            />
            <div className="row end">
              <Button type="submit" variant={preview ? undefined : "primary"} disabled={busy || url.trim() === ""}>
                {loading ? "Lädt …" : "Vorschau laden"}
              </Button>
            </div>
          </form>

          {loading && <Spinner label="Rezept wird gelesen …" />}
          {error && <ImportError error={error} onOpen={onClose} />}

          {preview && (
            <div className="rc-preview">
              <h3>{preview.title}</h3>
              <p className="muted rc-sub">
                {preview.source_site ?? preview.source_url}
                {preview.servings !== null && ` · ${numDe(preview.servings)} Portionen`}
                {minutesDetail(preview.prep_min, preview.cook_min) && ` · ${minutesDetail(preview.prep_min, preview.cook_min)}`}
              </p>
              {preview.warnings.map((w, i) => (
                <Alert key={i} kind="warn">
                  {w}
                </Alert>
              ))}
              {preview.servings === null && (
                <Alert kind="warn">Die Seite nennt keine Portionszahl. Es wird mit 1 Portion gerechnet.</Alert>
              )}

              <h4>Erkannte Zutaten ({preview.lines.length})</h4>
              {preview.lines.length === 0 ? (
                <Alert kind="warn">Es wurden keine Zutaten erkannt. Das Rezept lässt sich trotzdem speichern.</Alert>
              ) : (
                <ul className="rc-preview-lines" aria-label="Erkannte Zutaten">
                  {preview.lines.map((line, i) => {
                    const matches = [...line.matches];
                    if (line.ingredient_id !== null && !matches.some((m) => m.ingredient_id === line.ingredient_id)) {
                      matches.unshift({
                        ingredient_id: line.ingredient_id,
                        name: line.ingredient_name ?? `Zutat ${line.ingredient_id}`,
                        score: 100,
                        via: "auto",
                      });
                    }
                    const options = [
                      ...(line.ingredient_id === null ? [{ value: "", label: "Später zuordnen" }] : []),
                      ...matches.map((m) => ({ value: String(m.ingredient_id), label: `${m.name} (${Math.round(m.score)} %)` })),
                    ];
                    return (
                      <li key={i}>
                        <strong>{line.raw_text}</strong>
                        {lineDetail(line) && <small className="muted"> {lineDetail(line)}</small>}
                        <SelectField
                          label="Zutat"
                          aria-label={`Zutat für ${line.raw_text}`}
                          value={choices[i] ?? ""}
                          onChange={(v) => setChoices((c) => ({ ...c, [i]: v }))}
                          options={options}
                          hint={
                            line.ingredient_id === null && matches.length === 0
                              ? "Kein Treffer. Die Zeile kann später in „Zutaten prüfen“ zugeordnet werden."
                              : undefined
                          }
                        />
                      </li>
                    );
                  })}
                </ul>
              )}
              <CheckField
                label="Neue Zuordnungen merken"
                checked={remember}
                onChange={setRemember}
                hint="Gewählte Zutaten werden als Synonym gespeichert und künftig automatisch erkannt."
              />
              <div className="row end">
                <Button onClick={onClose} disabled={saving}>
                  Abbrechen
                </Button>
                <Button variant="primary" onClick={save} disabled={saving} aria-busy={saving}>
                  {saving ? "Speichert …" : "Speichern"}
                </Button>
              </div>
            </div>
          )}
        </>
      )}
    </Modal>
  );
}
