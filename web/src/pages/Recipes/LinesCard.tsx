import { Fragment, useState } from "react";
import { api } from "../../api/client";
import { num } from "../../format";
import { Alert, Badge, Button, Card, Table } from "../../ui";
import { AssignPanel } from "./AssignPanel";
import { guessName, quantityText } from "./format";
import type { AssignOut, Line } from "./types";
import "./Recipes.css";

type Props = {
  lines: Line[];
  /** Wird nach einer Zuordnung aufgerufen (z. B. zum Neuladen des Rezepts) */
  onAssigned: (out: AssignOut) => void;
};

/** Zutatenliste mit Menge, Gramm und Zuordnung. Nicht zugeordnete Zeilen sind markiert und direkt zuordenbar. */
export function LinesCard({ lines, onAssigned }: Props) {
  const [openId, setOpenId] = useState<number | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  async function assign(line: Line, ingredientId: number, remember: boolean) {
    const out = await api<AssignOut>("POST", `/recipe-lines/${line.id}/assign`, {
      ingredient_id: ingredientId,
      save_synonym: remember,
    });
    setOpenId(null);
    const more = out.assigned_line_ids.length - 1;
    setNotice(
      more > 0
        ? `Zugeordnet. ${more} gleichlautende ${more === 1 ? "Zeile wurde" : "Zeilen wurden"} ebenfalls zugeordnet.`
        : "Zeile zugeordnet.",
    );
    onAssigned(out);
  }

  return (
    <Card title="Zutaten">
      {notice && <Alert kind="ok">{notice}</Alert>}
      {lines.length === 0 ? (
        <p className="muted">Dieses Rezept hat noch keine Zutaten. Über „Bearbeiten“ lassen sie sich eintragen.</p>
      ) : (
        <Table>
          <thead>
            <tr>
              <th scope="col">Zutat laut Rezept</th>
              <th scope="col">Menge</th>
              <th scope="col">Gramm</th>
              <th scope="col">Zugeordnete Zutat</th>
            </tr>
          </thead>
          <tbody>
            {lines.map((line) => {
              const unassigned = line.ingredient === null;
              const open = openId === line.id;
              return (
                <Fragment key={line.id}>
                  <tr className={unassigned && !line.optional ? "rc-unassigned" : undefined}>
                    <th scope="row">
                      {line.raw_text}
                      {line.optional && (
                        <>
                          {" "}
                          <Badge>optional</Badge>
                        </>
                      )}
                    </th>
                    <td>{quantityText(line.quantity, line.unit)}</td>
                    <td>
                      {line.grams !== null ? (
                        num(line.grams, 0, "g")
                      ) : (
                        <span className="muted">unbekannt</span>
                      )}
                    </td>
                    <td>
                      {line.ingredient ? (
                        <>
                          {line.ingredient.name}
                          <br />
                          <Button
                            variant="ghost"
                            onClick={() => setOpenId(open ? null : line.id)}
                            aria-expanded={open}
                            aria-label={`Zuordnung ändern: ${line.raw_text}`}
                          >
                            Ändern
                          </Button>
                        </>
                      ) : (
                        <>
                          <Badge kind={line.optional ? undefined : "warn"}>Nicht zugeordnet</Badge>
                          <br />
                          <Button
                            onClick={() => setOpenId(open ? null : line.id)}
                            aria-expanded={open}
                            aria-label={`Zutat zuordnen: ${line.raw_text}`}
                          >
                            Zuordnen
                          </Button>
                        </>
                      )}
                    </td>
                  </tr>
                  {open && (
                    <tr>
                      <td colSpan={4}>
                        <AssignPanel
                          label={line.raw_text}
                          initialQuery={guessName(line.raw_text)}
                          onAssign={(id, remember) => assign(line, id, remember)}
                          onCancel={() => setOpenId(null)}
                        />
                      </td>
                    </tr>
                  )}
                </Fragment>
              );
            })}
          </tbody>
        </Table>
      )}
    </Card>
  );
}
