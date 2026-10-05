import { type FormEvent, type ReactNode, useEffect, useId, useRef, useState } from "react";
import { Alert, Button, Card } from "../../ui";
import "./crud.css";
import { errorText } from "./format";

type Props = {
  title: string;
  submitLabel?: string;
  /** Speichert. Wirft die Funktion, erscheint die (deutsche) Meldung neben dem Formular. */
  onSubmit: () => Promise<unknown>;
  onCancel: () => void;
  /** Prüfung vor dem Senden: liefert eine Meldung oder `null`. */
  validate?: () => string | null;
  children: ReactNode;
};

/** Formular mit Titel, Fehlermeldung (role=alert), „Speichern“/„Abbrechen“ und Sperre während des Speicherns. */
export function FormShell({ title, submitLabel = "Speichern", onSubmit, onCancel, validate, children }: Props) {
  const headingId = useId();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const alive = useRef(true);
  useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
    };
  }, []);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (busy) return;
    const problem = validate?.() ?? null;
    if (problem) {
      setError(problem);
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await onSubmit();
    } catch (err) {
      if (alive.current) setError(errorText(err));
    } finally {
      if (alive.current) setBusy(false);
    }
  }

  return (
    <div className="crud-form">
      <Card>
        <form noValidate aria-labelledby={headingId} onSubmit={handleSubmit}>
          <h2 id={headingId}>{title}</h2>
          {children}
          {error && <Alert kind="error">{error}</Alert>}
          <div className="crud-form-actions">
            <Button onClick={onCancel} disabled={busy}>
              Abbrechen
            </Button>
            <Button type="submit" variant="primary" disabled={busy} aria-busy={busy}>
              {busy ? "Speichert …" : submitLabel}
            </Button>
          </div>
        </form>
      </Card>
    </div>
  );
}
