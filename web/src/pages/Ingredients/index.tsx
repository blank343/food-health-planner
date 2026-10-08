import { useCallback, useState } from "react";
import { api } from "../../api/client";
import { Alert, Button, PageHeader } from "../../ui";
import { IngredientCatalog, INITIAL_CATALOG, useCatalogParams, type CatalogState } from "./IngredientCatalog";
import { IngredientDetailView } from "./IngredientDetailView";
import { IngredientForm } from "./IngredientForm";
import { PreferencesOverview } from "./PreferencesOverview";
import type { IngredientDetail, IngredientIn } from "./labels";
import { useIngredientSearch } from "./useIngredientSearch";
import { usePreferences } from "./usePreferences";
import "./Ingredients.css";

type Tab = "catalog" | "prefs";

export default function IngredientsPage() {
  const [tab, setTab] = useState<Tab>("catalog");
  const [catalog, setCatalog] = useState<CatalogState>(INITIAL_CATALOG);
  const [selected, setSelected] = useState<number | null>(null);
  const [creating, setCreating] = useState(false);
  const prefs = usePreferences();
  const search = useIngredientSearch(useCatalogParams(catalog));
  const { reload } = search;

  const open = useCallback((id: number) => {
    setTab("catalog");
    setCreating(false);
    setSelected(id);
  }, []);

  async function create(input: IngredientIn) {
    const created = await api<IngredientDetail>("POST", "/ingredients", input);
    reload();
    setCreating(false);
    setSelected(created.id);
  }

  const inDetail = tab === "catalog" && selected !== null;

  return (
    <>
      <PageHeader
        title="Zutaten"
        actions={
          !creating && !inDetail ? (
            <Button
              variant="primary"
              onClick={() => {
                setTab("catalog");
                setCreating(true);
              }}
            >
              Zutat anlegen
            </Button>
          ) : undefined
        }
      >
        Der Zutaten-Katalog mit Nährwerten je 100 g und deine persönlichen Vorlieben.
      </PageHeader>

      {prefs.loadError && <Alert kind="warn">Deine Vorlieben konnten nicht geladen werden: {prefs.loadError}</Alert>}

      {!inDetail && !creating && (
        <div className="tabs" role="tablist" aria-label="Bereiche">
          <button
            type="button"
            role="tab"
            id="tab-catalog"
            className="tab"
            aria-selected={tab === "catalog"}
            aria-controls="panel-catalog"
            onClick={() => setTab("catalog")}
          >
            Katalog
          </button>
          <button
            type="button"
            role="tab"
            id="tab-prefs"
            className="tab"
            aria-selected={tab === "prefs"}
            aria-controls="panel-prefs"
            onClick={() => setTab("prefs")}
          >
            Meine Vorlieben
          </button>
        </div>
      )}

      {creating ? (
        <IngredientForm onSave={create} onCancel={() => setCreating(false)} />
      ) : inDetail ? (
        <IngredientDetailView
          id={selected}
          prefs={prefs}
          onBack={() => setSelected(null)}
          onChanged={reload}
          onDeleted={() => setSelected(null)}
        />
      ) : tab === "catalog" ? (
        <div role="tabpanel" id="panel-catalog" aria-labelledby="tab-catalog">
          <IngredientCatalog state={catalog} onState={setCatalog} prefs={prefs} onOpen={open} search={search} />
        </div>
      ) : (
        <div role="tabpanel" id="panel-prefs" aria-labelledby="tab-prefs">
          <PreferencesOverview prefs={prefs} onOpen={open} />
        </div>
      )}
    </>
  );
}
