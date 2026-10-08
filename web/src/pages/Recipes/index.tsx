// Rezeptseiten: Liste mit „Passt ins Tagesziel“, Detail, Import, manuelles Anlegen und Prüfliste.
// Alles läuft unter einer Route (`/rezepte`); Detail und Prüfliste werden über die Adresse gewählt:
//   /rezepte                Liste
//   /rezepte?rezept=12      Detail des Rezepts 12
//   /rezepte?tab=pruefen    Prüfliste „Zutaten prüfen“
import { useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { Button, PageHeader } from "../../ui";
import { ImportDialog } from "./ImportDialog";
import { Modal } from "./Modal";
import { RecipeDetailView } from "./RecipeDetailView";
import { RecipeForm } from "./RecipeForm";
import { RecipeList } from "./RecipeList";
import { ReviewList } from "./ReviewList";
import { useSlotContext } from "./hooks";
import { DEFAULT_FILTERS, type ListFilters } from "./types";
import "./Recipes.css";

type Dialog = "import" | "new" | null;

/** Positive ganze Zahl aus dem Adressparameter oder `null`. */
export function parseId(raw: string | null): number | null {
  if (raw === null || !/^\d+$/.test(raw)) return null;
  const n = Number(raw);
  return n > 0 ? n : null;
}

export default function RecipesPage() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const ctx = useSlotContext();
  const [filters, setFilters] = useState<ListFilters>(DEFAULT_FILTERS);
  const [dialog, setDialog] = useState<Dialog>(null);

  const recipeId = parseId(params.get("rezept"));
  const tab = params.get("tab") === "pruefen" ? "pruefen" : "rezepte";
  const open = (id: number) => navigate({ search: `?rezept=${id}` });
  const closeDialog = () => setDialog(null);

  return (
    <>
      {recipeId === null && (
        <PageHeader
          title="Rezepte"
          actions={
            <>
              <Button variant="primary" onClick={() => setDialog("import")}>
                Rezept importieren
              </Button>
              <Button onClick={() => setDialog("new")}>Neues Rezept</Button>
            </>
          }
        >
          Gespeicherte Rezepte mit Nährwerten und der Passung zum Tagesziel.
        </PageHeader>
      )}

      {recipeId === null && (
        <nav className="rc-tabs" aria-label="Bereiche der Rezeptseite">
          <Link to={{ search: "" }} aria-current={tab === "rezepte" ? "page" : undefined}>
            Rezepte
          </Link>
          <Link to={{ search: "?tab=pruefen" }} aria-current={tab === "pruefen" ? "page" : undefined}>
            Zutaten prüfen
          </Link>
        </nav>
      )}

      {recipeId !== null ? (
        <RecipeDetailView key={recipeId} id={recipeId} ctx={ctx} onDeleted={() => navigate({ search: "" })} />
      ) : tab === "pruefen" ? (
        <ReviewList />
      ) : (
        <RecipeList ctx={ctx} filters={filters} setFilters={setFilters} onImport={() => setDialog("import")} />
      )}

      {dialog === "import" && (
        <ImportDialog
          onClose={closeDialog}
          onImported={(id) => {
            closeDialog();
            open(id);
          }}
        />
      )}
      {dialog === "new" && (
        <Modal title="Rezept von Hand anlegen" onClose={closeDialog}>
          <RecipeForm
            mode="new"
            onCancel={closeDialog}
            onSaved={(recipe) => {
              closeDialog();
              open(recipe.id);
            }}
          />
        </Modal>
      )}
    </>
  );
}
