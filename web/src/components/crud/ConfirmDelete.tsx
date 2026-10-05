import { useEffect, useId, useRef, useState } from "react";
import { Alert, Button } from "../../ui";
import "./crud.css";
import { errorText } from "./format";

type Props = {
  name: string;
  onConfirm: () => Promise<unknown>;
  onCancel: () => void;
};

/** Eingebettete Löschbestätigung (kein `window.confirm`). Der Fokus liegt zuerst auf „Abbrechen“. */
export function ConfirmDelete({ name, onConfirm, onCancel }: Props) {
  const titleId = useId();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const boxRef = useRef<HTMLDivElement>(null);
  const alive = useRef(true);
  useEffect(() => {
    alive.current = true;
    boxRef.current?.querySelector("button")?.focus();
    return () => {
      alive.current = false;
    };
  }, []);

  async function confirm() {
    setBusy(true);
    setError(null);
    try {
      await onConfirm();
    } catch (e) {
      if (alive.current) setError(errorText(e));
    } finally {
      if (alive.current) setBusy(false);
    }
  }

  return (
    <div className="confirm" role="alertdialog" aria-labelledby={titleId} ref={boxRef}>
      <p id={titleId}>
        <strong>„{name}“ wirklich löschen?</strong> Das lässt sich nicht rückgängig machen.
      </p>
      {error && <Alert kind="error">{error}</Alert>}
      <div className="row">
        <Button onClick={onCancel} disabled={busy}>
          Abbrechen
        </Button>
        <Button variant="danger" onClick={confirm} disabled={busy} aria-busy={busy}>
          {busy ? "Löscht …" : "Ja, löschen"}
        </Button>
      </div>
    </div>
  );
}
