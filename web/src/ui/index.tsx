// Gemeinsame Bausteine. Klassen siehe ui.css. Alle Texte sind deutsch, alle Felder haben Beschriftungen.
import {
  type ButtonHTMLAttributes,
  type InputHTMLAttributes,
  type ReactNode,
  type SelectHTMLAttributes,
  useId,
} from "react";
import "./ui.css";

export function PageHeader({ title, actions, children }: { title: string; actions?: ReactNode; children?: ReactNode }) {
  return (
    <header>
      <div className="topbar">
        <h1>{title}</h1>
        {actions && <div className="row">{actions}</div>}
      </div>
      {children && <p className="muted">{children}</p>}
    </header>
  );
}

export function Card({ title, children, actions }: { title?: string; children: ReactNode; actions?: ReactNode }) {
  return (
    <section className="card">
      {(title || actions) && (
        <div className="topbar">
          {title && <h2>{title}</h2>}
          {actions && <div className="row">{actions}</div>}
        </div>
      )}
      {children}
    </section>
  );
}

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "primary" | "danger" | "ghost" };
export function Button({ variant, className, type = "button", ...rest }: ButtonProps) {
  return <button type={type} className={`btn ${variant ?? ""} ${className ?? ""}`.trim()} {...rest} />;
}

type FieldProps = {
  label: string;
  hint?: string;
  error?: string | null;
  children: (id: string, describedBy: string | undefined) => ReactNode;
};
/** Beschriftung, Hinweis und Fehler um ein Eingabefeld (id und aria werden durchgereicht). */
export function Field({ label, hint, error, children }: FieldProps) {
  const id = useId();
  const hintId = hint ? `${id}-hint` : undefined;
  const errId = error ? `${id}-err` : undefined;
  const describedBy = [hintId, errId].filter(Boolean).join(" ") || undefined;
  return (
    <div className="field">
      <label className="label" htmlFor={id}>
        {label}
      </label>
      {children(id, describedBy)}
      {hint && (
        <span className="hint" id={hintId}>
          {hint}
        </span>
      )}
      {error && (
        <span className="err" id={errId} role="alert">
          {error}
        </span>
      )}
    </div>
  );
}

type TextFieldProps = Omit<InputHTMLAttributes<HTMLInputElement>, "onChange" | "value"> & {
  label: string;
  value: string;
  onChange: (v: string) => void;
  hint?: string;
  error?: string | null;
};
export function TextField({ label, hint, error, onChange, value, ...rest }: TextFieldProps) {
  return (
    <Field label={label} hint={hint} error={error}>
      {(id, d) => (
        <input
          id={id}
          className="input"
          aria-describedby={d}
          aria-invalid={error ? true : undefined}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          {...rest}
        />
      )}
    </Field>
  );
}

type NumberFieldProps = {
  label: string;
  value: number | null;
  onChange: (v: number | null) => void;
  hint?: string;
  error?: string | null;
  min?: number;
  max?: number;
  step?: number | "any";
  unit?: string;
  required?: boolean;
};
/** Zahlenfeld, das leer = `null` liefert. Dezimalkomma und -punkt werden akzeptiert. */
export function NumberField({ label, value, onChange, hint, error, unit, ...rest }: NumberFieldProps) {
  return (
    <Field label={unit ? `${label} (${unit})` : label} hint={hint} error={error}>
      {(id, d) => (
        <input
          id={id}
          className="input"
          type="number"
          inputMode="decimal"
          aria-describedby={d}
          aria-invalid={error ? true : undefined}
          value={value ?? ""}
          onChange={(e) => {
            const raw = e.target.value.replace(",", ".").trim();
            if (raw === "") return onChange(null);
            const n = Number(raw);
            onChange(Number.isFinite(n) ? n : null);
          }}
          {...rest}
        />
      )}
    </Field>
  );
}

type SelectFieldProps = Omit<SelectHTMLAttributes<HTMLSelectElement>, "onChange" | "value"> & {
  label: string;
  value: string;
  onChange: (v: string) => void;
  options: { value: string; label: string }[];
  hint?: string;
  error?: string | null;
};
export function SelectField({ label, hint, error, options, onChange, value, ...rest }: SelectFieldProps) {
  return (
    <Field label={label} hint={hint} error={error}>
      {(id, d) => (
        <select
          id={id}
          className="select"
          aria-describedby={d}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          {...rest}
        >
          {options.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
      )}
    </Field>
  );
}

export function CheckField({
  label,
  checked,
  onChange,
  hint,
}: {
  label: string;
  checked: boolean;
  onChange: (v: boolean) => void;
  hint?: string;
}) {
  const id = useId();
  return (
    <div className="field">
      <label className="check" htmlFor={id}>
        <input id={id} type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)} />
        <span>{label}</span>
      </label>
      {hint && <span className="hint">{hint}</span>}
    </div>
  );
}

export function Alert({ kind = "info", children }: { kind?: "error" | "warn" | "info" | "ok"; children: ReactNode }) {
  return (
    <div className={`alert ${kind}`} role={kind === "error" ? "alert" : "status"}>
      {children}
    </div>
  );
}

export function Badge({ kind, children }: { kind?: "ok" | "warn" | "error"; children: ReactNode }) {
  return <span className={`badge ${kind ?? ""}`.trim()}>{children}</span>;
}

export function Spinner({ label = "Lädt …" }: { label?: string }) {
  return (
    <span role="status" aria-live="polite" className="row">
      <span className="spinner" aria-hidden="true" />
      <span className="muted">{label}</span>
    </span>
  );
}

export function EmptyState({ children }: { children: ReactNode }) {
  return <div className="empty">{children}</div>;
}

export function Stat({ label, value, hint }: { label: string; value: ReactNode; hint?: string }) {
  return (
    <div className="stat card" style={{ marginBottom: 0 }}>
      <div className="value">{value}</div>
      <div className="label">{label}</div>
      {hint && <small>{hint}</small>}
    </div>
  );
}

export function Progress({ fraction, label }: { fraction: number; label: string }) {
  const pct = Math.round(Math.max(0, Math.min(1, fraction)) * 100);
  return (
    <div role="progressbar" aria-label={label} aria-valuemin={0} aria-valuemax={100} aria-valuenow={pct} className="progress">
      <span style={{ width: `${pct}%` }} />
    </div>
  );
}

export function Table({ children }: { children: ReactNode }) {
  return (
    <div className="table-wrap">
      <table className="table">{children}</table>
    </div>
  );
}

/** Zeigt Ladezustand, Fehler oder den Inhalt. */
export function Async({
  loading,
  error,
  children,
}: {
  loading: boolean;
  error: string | null;
  children: ReactNode;
}) {
  if (loading) return <Spinner />;
  if (error) return <Alert kind="error">{error}</Alert>;
  return <>{children}</>;
}
