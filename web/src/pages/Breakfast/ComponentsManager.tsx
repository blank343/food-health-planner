import { useState } from "react";
import { api } from "../../api/client";
import {
  ConfirmDelete,
  type Editing,
  EmptyList,
  ResourceList,
  editingIdOf,
  numDe,
} from "../../components/crud";
import { num } from "../../format";
import { Badge, Button } from "../../ui";
import { saltOf } from "../Ingredients/labels";
import { ComponentForm } from "./ComponentForm";
import { VariantForm } from "./VariantForm";
import { type ComponentIn, type ComponentOut, type VariantIn, type VariantOut, kindLabel } from "./types";

type Props = {
  components: ComponentOut[];
  reload: () => void;
  onSeed: () => void;
  seeding: boolean;
  /** Steuert das Formular „Komponente anlegen“ von außen (Schaltfläche in der Seitenkopfzeile). */
  creating: boolean;
  onCreatingChange: (v: boolean) => void;
};

type VariantState = { componentId: number; variantId: number | null } | null;

function amountText(c: ComponentOut): string {
  const parts = [`${numDe(c.min_g)} bis ${numDe(c.max_g)} g`, `Schritt ${numDe(c.step_g)} g`];
  if (c.typical_g !== null) parts.push(`üblich ${numDe(c.typical_g)} g`);
  return parts.join(", ");
}

function VariantRow({ c, v, onEdit, onDelete }: { c: ComponentOut; v: VariantOut; onEdit: () => void; onDelete: () => void }) {
  return (
    <div className="variant-item">
      <span>
        <strong>{v.name}</strong>{" "}
        <small className="muted">
          {v.ingredient_id !== c.ingredient_id ? `${v.ingredient_name}, ` : ""}
          {v.grams_per_unit ? `${numDe(v.grams_per_unit)} g je Stück` : "nur in Gramm"}
        </small>
      </span>
      <span className="row">
        <Button onClick={onEdit} aria-label={`Variante ${v.name} von ${c.name} bearbeiten`}>
          Bearbeiten
        </Button>
        <Button variant="danger" onClick={onDelete} aria-label={`Variante ${v.name} von ${c.name} löschen`}>
          Löschen
        </Button>
      </span>
    </div>
  );
}

/** Komponenten und Varianten verwalten (Anlegen, Bearbeiten, Löschen). */
export function ComponentsManager({ components, reload, onSeed, seeding, creating, onCreatingChange }: Props) {
  const [editing, setEditing] = useState<Editing>(null);
  const [variantState, setVariantState] = useState<VariantState>(null);
  const [variantDelete, setVariantDelete] = useState<{ componentId: number; variantId: number } | null>(null);
  const closeEditing = () => setEditing(null);

  async function createComponent(input: ComponentIn) {
    await api("POST", "/components", input);
    reload();
    onCreatingChange(false);
  }

  async function saveVariant(c: ComponentOut, variantId: number | null, input: VariantIn) {
    if (variantId === null) await api("POST", `/components/${c.id}/variants`, input);
    else await api("PATCH", `/components/${c.id}/variants/${variantId}`, input);
    reload();
    setVariantState(null);
  }

  return (
    <>
      {creating && <ComponentForm onSave={createComponent} onCancel={() => onCreatingChange(false)} />}

      {components.length === 0 && !creating ? (
        <EmptyList actionLabel={seeding ? "Legt an …" : "Standard-Komponenten anlegen"} onAction={onSeed}>
          Noch keine Komponenten: Standard-Komponenten anlegen (Ei, Brot, Quark, Skyr, Obst und das feste
          Wochenend-Frühstück) oder eigene Komponenten hinzufügen.
        </EmptyList>
      ) : (
        <ResourceList
          items={components}
          ariaLabel="Komponenten"
          label={(c) => c.name}
          editingId={editingIdOf(editing)}
          onEdit={(c) => {
            onCreatingChange(false);
            setEditing({ mode: "edit", id: c.id });
          }}
          onRemove={async (id) => {
            await api("DELETE", `/components/${id}`);
            reload();
          }}
          renderEditor={(c) => (
            <ComponentForm
              item={c}
              onCancel={closeEditing}
              onSave={async (input) => {
                await api("PATCH", `/components/${c.id}`, input);
                reload();
                closeEditing();
              }}
            />
          )}
          renderItem={(c) => (
            <>
              <div className="crud-head">
                <h3>{c.name}</h3>
                <small>{c.ingredient_name}</small>
              </div>
              <div className="crud-meta">
                <Badge>{kindLabel(c.kind)}</Badge>
                {c.weekend_fixed && <Badge kind="warn">Wochenende fest</Badge>}
              </div>
              <div>Menge: {amountText(c)}</div>
              <small className="muted">
                Je 100 g: {num(c.per100.kcal, 0, "kcal")}, Protein {num(c.per100.protein_g, 1, "g")}, Salz{" "}
                {num(saltOf(c.per100), 2, "g")}
              </small>
            </>
          )}
          renderExtra={(c) => (
            <div>
              <h4 style={{ margin: "12px 0 0" }}>Varianten</h4>
              {c.variants.length === 0 ? (
                <p className="muted" style={{ margin: "4px 0" }}>
                  Keine Varianten. Mit einer Variante kann der Rechner in Stück rechnen (z. B. 1 Ei = 60 g).
                </p>
              ) : (
                <ul className="variant-list" aria-label={`Varianten von ${c.name}`}>
                  {c.variants.map((v) =>
                    variantState?.componentId === c.id && variantState.variantId === v.id ? (
                      <li key={v.id}>
                        <VariantForm
                          component={c}
                          item={v}
                          onCancel={() => setVariantState(null)}
                          onSave={(input) => saveVariant(c, v.id, input)}
                        />
                      </li>
                    ) : (
                      <li key={v.id}>
                        <VariantRow
                          c={c}
                          v={v}
                          onEdit={() => {
                            setVariantDelete(null);
                            setVariantState({ componentId: c.id, variantId: v.id });
                          }}
                          onDelete={() => setVariantDelete({ componentId: c.id, variantId: v.id })}
                        />
                        {variantDelete?.componentId === c.id && variantDelete.variantId === v.id && (
                          <ConfirmDelete
                            name={`${v.name} (${c.name})`}
                            onCancel={() => setVariantDelete(null)}
                            onConfirm={async () => {
                              await api("DELETE", `/components/${c.id}/variants/${v.id}`);
                              reload();
                              setVariantDelete(null);
                            }}
                          />
                        )}
                      </li>
                    ),
                  )}
                </ul>
              )}
              {variantState?.componentId === c.id && variantState.variantId === null ? (
                <VariantForm component={c} onCancel={() => setVariantState(null)} onSave={(input) => saveVariant(c, null, input)} />
              ) : (
                <Button
                  onClick={() => setVariantState({ componentId: c.id, variantId: null })}
                  aria-label={`Variante für ${c.name} hinzufügen`}
                >
                  Variante hinzufügen
                </Button>
              )}
            </div>
          )}
        />
      )}
    </>
  );
}
