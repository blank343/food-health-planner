import { type ReactNode, useEffect, useId, useRef } from "react";
import { Button } from "../../ui";
import "./Recipes.css";

const FOCUSABLE =
  'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

/**
 * Dialog über der Seite (role=dialog, aria-modal): Fokus wandert hinein und bleibt darin (Tab),
 * Escape schließt, danach kehrt der Fokus zum auslösenden Element zurück.
 */
export function Modal({ title, onClose, children }: { title: string; onClose: () => void; children: ReactNode }) {
  const titleId = useId();
  const boxRef = useRef<HTMLDivElement>(null);
  const closeRef = useRef(onClose);
  closeRef.current = onClose;

  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    const box = boxRef.current;
    const focusables = () => (box ? [...box.querySelectorAll<HTMLElement>(FOCUSABLE)] : []);
    // erstes Eingabefeld bevorzugen, sonst das erste bedienbare Element
    (box?.querySelector<HTMLElement>("input, textarea, select") ?? focusables()[0])?.focus();

    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") {
        e.stopPropagation();
        closeRef.current();
        return;
      }
      if (e.key !== "Tab") return;
      const items = focusables();
      if (items.length === 0) return;
      const first = items[0]!;
      const last = items[items.length - 1]!;
      const active = document.activeElement;
      if (e.shiftKey && (active === first || !box?.contains(active))) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && (active === last || !box?.contains(active))) {
        e.preventDefault();
        first.focus();
      }
    }
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("keydown", onKey);
      previous?.focus?.();
    };
  }, []);

  return (
    <div className="rc-modal-backdrop">
      <div className="rc-modal" role="dialog" aria-modal="true" aria-labelledby={titleId} ref={boxRef}>
        <div className="topbar">
          <h2 id={titleId}>{title}</h2>
          <Button variant="ghost" onClick={onClose} aria-label={`${title} schließen`}>
            Schließen
          </Button>
        </div>
        {children}
      </div>
    </div>
  );
}
