// Import-Jobs: Typen, deutsche Bezeichnungen und die Zusammenfassung aus `stats`.
import type { components } from "../../api/schema";
import { dateDe, num } from "../../format";

export type ImportJob = components["schemas"]["ImportJobOut"];

const KIND_LABEL: Record<string, string> = {
  hae: "Health Auto Export",
  apple_health: "Apple Health",
  labs: "Laborbefund",
};
export const kindLabel = (kind: string): string => KIND_LABEL[kind] ?? kind;

export const isActive = (job: ImportJob): boolean => job.status === "queued" || job.status === "running";

/** Der Server räumt hängengebliebene Jobs nach 12 Stunden ab (sie blockieren dann nichts mehr). */
const STALE_MS = 12 * 60 * 60 * 1000;
export function isStale(job: ImportJob, now = Date.now()): boolean {
  if (!job.created_at) return false;
  const t = Date.parse(job.created_at);
  return Number.isFinite(t) && now - t > STALE_MS;
}

export const STATUS_LABEL: Record<string, string> = {
  queued: "wartet",
  running: "läuft",
  done: "fertig",
  failed: "fehlgeschlagen",
};

function count(stats: ImportJob["stats"], key: string): number {
  const v = stats[key];
  return typeof v === "number" && Number.isFinite(v) ? v : 0;
}

function text(stats: ImportJob["stats"], key: string): string | null {
  const v = stats[key];
  return typeof v === "string" && v ? v : null;
}

const plural = (n: number, one: string, many: string) => `${num(n)} ${n === 1 ? one : many}`;

/** Freundliche Zusammenfassung eines fertigen Imports. */
export function summarize(job: ImportJob): string {
  const s = job.stats ?? {};
  if (job.kind === "labs") {
    let out = plural(count(s, "results_new"), "Laborwert", "Laborwerte");
    const updated = count(s, "results_updated");
    if (updated > 0) out += `, ${num(updated)} aktualisiert`;
    const pending = count(s, "pending");
    if (pending > 0) out += `, ${pending === 1 ? "1 steht" : `${num(pending)} stehen`} noch aus`;
    return out;
  }
  let out = `${plural(count(s, "daily_new"), "neuer Tag", "neue Tage")}, ${plural(count(s, "workout_new"), "Workout", "Workouts")} importiert`;
  const du = count(s, "daily_updated");
  const wu = count(s, "workout_updated");
  if (du + wu > 0) out += ` (außerdem aktualisiert: ${plural(du, "Tag", "Tage")}, ${plural(wu, "Workout", "Workouts")})`;
  const from = text(s, "date_from");
  const to = text(s, "date_to");
  if (from && to) out += `, Zeitraum ${dateDe(from)} bis ${dateDe(to)}`;
  const extras: string[] = [];
  const placeholders = count(s, "weight_placeholders_removed");
  if (placeholders > 0) extras.push(`${plural(placeholders, "Platzhalter-Gewicht", "Platzhalter-Gewichte")} entfernt`);
  const outliers = count(s, "weight_outliers_removed");
  if (outliers > 0) extras.push(`${plural(outliers, "unplausibler Gewichtswert", "unplausible Gewichtswerte")} entfernt`);
  return extras.length > 0 ? `${out}; ${extras.join("; ")}` : out;
}

/** `2026-10-05T14:30:00` wird zu `05.10.2026 14:30`. */
export function timeDe(iso: string | null | undefined): string {
  if (!iso) return "–";
  const hm = /T(\d{2}:\d{2})/.exec(iso);
  return hm ? `${dateDe(iso)} ${hm[1]}` : dateDe(iso);
}
