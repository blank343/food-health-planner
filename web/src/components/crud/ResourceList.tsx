import { type ReactNode, useState } from "react";
import { Button, EmptyState } from "../../ui";
import { ConfirmDelete } from "./ConfirmDelete";
import "./crud.css";

type Props<T extends { id: number }> = {
  items: T[];
  ariaLabel: string;
  /** Name für Schaltflächen und die Löschfrage. */
  label: (item: T) => string;
  renderItem: (item: T) => ReactNode;
  /** Zusatzbedienelemente unter dem Eintrag (z. B. Schalter). */
  renderExtra?: (item: T) => ReactNode;
  /** Id des Eintrags, der gerade bearbeitet wird: statt der Ansicht erscheint `renderEditor`. */
  editingId: number | null;
  onEdit: (item: T) => void;
  renderEditor: (item: T) => ReactNode;
  onRemove: (id: number) => Promise<unknown>;
};

/** Liste mit „Bearbeiten“ und „Löschen“ (mit Rückfrage) je Eintrag. */
export function ResourceList<T extends { id: number }>({
  items,
  ariaLabel,
  label,
  renderItem,
  renderExtra,
  editingId,
  onEdit,
  renderEditor,
  onRemove,
}: Props<T>) {
  const [confirmId, setConfirmId] = useState<number | null>(null);
  return (
    <ul className="crud-list" aria-label={ariaLabel}>
      {items.map((item) => {
        if (item.id === editingId) {
          return <li key={item.id}>{renderEditor(item)}</li>;
        }
        const name = label(item);
        return (
          <li key={item.id} className="crud-item">
            {renderItem(item)}
            {renderExtra?.(item)}
            {confirmId === item.id ? (
              <ConfirmDelete
                name={name}
                onCancel={() => setConfirmId(null)}
                onConfirm={async () => {
                  await onRemove(item.id);
                  setConfirmId(null);
                }}
              />
            ) : (
              <div className="crud-actions">
                <Button onClick={() => onEdit(item)} aria-label={`${name} bearbeiten`}>
                  Bearbeiten
                </Button>
                <Button variant="danger" onClick={() => setConfirmId(item.id)} aria-label={`${name} löschen`}>
                  Löschen
                </Button>
              </div>
            )}
          </li>
        );
      })}
    </ul>
  );
}

/** Leerer Zustand mit freundlicher Aufforderung und Schaltfläche. */
export function EmptyList({
  children,
  actionLabel,
  onAction,
}: {
  children: ReactNode;
  actionLabel: string;
  onAction: () => void;
}) {
  return (
    <EmptyState>
      <p>{children}</p>
      <Button variant="primary" onClick={onAction}>
        {actionLabel}
      </Button>
    </EmptyState>
  );
}

export type Editing<P = undefined> = { mode: "new"; preset?: P } | { mode: "edit"; id: number } | null;

/** Id des bearbeiteten Eintrags oder `null`. */
export const editingIdOf = <P,>(e: Editing<P>): number | null => (e?.mode === "edit" ? e.id : null);
