import { useId } from "react";
import { LEVELS, LEVEL_HELP, LEVEL_LABELS, type PrefLevel } from "./labels";
import "./Ingredients.css";

type Props = {
  /** Name der Zutat (für den zugänglichen Namen der Gruppe). */
  name: string;
  level: PrefLevel | null;
  onChange: (level: PrefLevel | null) => void;
  showHelp?: boolean;
};

/**
 * Eigene Vorliebe für eine Zutat. Native Radioknöpfe: Pfeiltasten wechseln die Stufe,
 * „Keine Angabe“ entfernt die Vorliebe.
 */
export function PreferenceControl({ name, level, onChange, showHelp = true }: Props) {
  const group = useId();
  const options: { value: PrefLevel | "none"; label: string }[] = [
    { value: "none", label: "Keine Angabe" },
    ...LEVELS.map((l) => ({ value: l, label: LEVEL_LABELS[l] })),
  ];
  const current = level ?? "none";
  return (
    <>
      <fieldset className="seg">
        <legend className="vh">Vorliebe für {name}</legend>
        {options.map((o) => (
          <label key={o.value} className="seg-opt">
            <input
              type="radio"
              name={group}
              value={o.value}
              className={o.value === "never" ? "never" : undefined}
              checked={current === o.value}
              onChange={() => onChange(o.value === "none" ? null : o.value)}
            />
            <span>{o.label}</span>
          </label>
        ))}
      </fieldset>
      {showHelp && (
        <p className="muted" style={{ fontSize: ".9rem" }}>
          {level ? LEVEL_HELP[level] : "Ohne Angabe behandelt der Planer die Zutat neutral."}{" "}
          {level !== "never" && <>„Nie“ ist eine harte Grenze: Der Planer verwendet die Zutat dann nie.</>}
        </p>
      )}
    </>
  );
}
