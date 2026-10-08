import { Link } from "react-router-dom";
import { Alert, Button } from "../../ui";
import type { SeedOut } from "./types";

/** Ergebnis von „Standard-Komponenten anlegen“: angelegt, übersprungen und was im Zutaten-Katalog fehlt. */
export function SeedResult({ result, onDismiss }: { result: SeedOut; onDismiss: () => void }) {
  const created = result.created.length;
  const matched = Object.entries(result.matched);
  return (
    <section aria-label="Ergebnis: Standard-Komponenten">
      <Alert kind={created > 0 ? "ok" : "info"}>
        <strong>
          {created > 0
            ? `${created} ${created === 1 ? "Komponente" : "Komponenten"} angelegt${
                result.variants_created > 0 ? `, ${result.variants_created} Varianten` : ""
              }.`
            : "Es wurde nichts Neues angelegt."}
        </strong>
        {created > 0 && <div>{result.created.join(", ")}</div>}
        {result.skipped.length > 0 && (
          <div>
            Übersprungen, weil sie schon vorhanden sind ({result.skipped.length}): {result.skipped.join(", ")}.
          </div>
        )}
      </Alert>
      {(result.missing.length > 0 || result.missing_variants.length > 0) && (
        <Alert kind="warn">
          <strong>Im Zutaten-Katalog fehlt noch etwas.</strong>
          {result.missing.length > 0 && <div>Nicht gefundene Zutaten: {result.missing.join(", ")}.</div>}
          {result.missing_variants.length > 0 && (
            <div>Varianten ohne passende Zutat: {result.missing_variants.join(", ")}.</div>
          )}
          <div>
            Lege die fehlenden Zutaten auf der Seite <Link to="/zutaten">Zutaten</Link> an (oder importiere die
            BLS-Datei) und klicke danach erneut auf „Standard-Komponenten anlegen“. Vorhandenes bleibt unverändert.
          </div>
        </Alert>
      )}
      {matched.length > 0 && (
        <details style={{ marginBottom: 12 }}>
          <summary>Zugeordnete Zutaten ({matched.length})</summary>
          <ul>
            {matched.map(([component, ingredient]) => (
              <li key={component}>
                {component}: {ingredient}
              </li>
            ))}
          </ul>
        </details>
      )}
      <div className="row end" style={{ marginBottom: 12 }}>
        <Button variant="ghost" onClick={onDismiss}>
          Meldung schließen
        </Button>
      </div>
    </section>
  );
}
