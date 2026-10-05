// Darstellung von Laborwerten: Operatoren, Referenzbereiche in Worten, Kennzeichen.
import type { components } from "../../api/schema";

export type LabResult = components["schemas"]["LabResultOut"];
export type LabReport = components["schemas"]["LabReportOut"];
export type LatestLabValue = components["schemas"]["LatestLabValueOut"];

const nf = new Intl.NumberFormat("de-DE", { minimumFractionDigits: 1, maximumFractionDigits: 3 });
const nfInt = new Intl.NumberFormat("de-DE", { minimumFractionDigits: 0, maximumFractionDigits: 3 });

/** Kleine Werte mit mindestens einer Nachkommastelle (5,0), große ohne (150). */
export function numLab(v: number): string {
  return (Math.abs(v) < 100 ? nf : nfInt).format(v);
}

/** Messwert mit Operator, z. B. `>45,4`. */
export function valueText(value: number | null, op: string | null): string {
  if (value === null) return "–";
  return `${op ?? ""}${numLab(value)}`;
}

/** Referenzbereich in Worten: `3,7–9,9`, `< 5,0`, `> 1,2`. */
export function refText(low: number | null, high: number | null, op: string | null): string {
  if (low !== null && high !== null) return `${numLab(low)}–${numLab(high)}`;
  if (high !== null) return `${op ?? "<"} ${numLab(high)}`;
  if (low !== null) return `${op ?? ">"} ${numLab(low)}`;
  return "–";
}

export const FLAG_TEXT: Record<string, string> = { L: "zu niedrig", H: "zu hoch" };

export function reportTypeText(type: string): string {
  return type === "Endbefund" || type === "Teilbefund" ? type : "Unbekannt";
}

export function reportDateIso(report: LabReport): string | null {
  return report.sample_datetime ?? report.created_at;
}

export const byAnalyte = (a: { analyte: string; unit: string }, b: { analyte: string; unit: string }): number =>
  a.analyte.localeCompare(b.analyte, "de", { sensitivity: "base" }) || a.unit.localeCompare(b.unit, "de");
