// Hilfen für Achsen: „runde“ Schrittweiten und Ticks.

export function niceStep(rough: number): number {
  if (!(rough > 0)) return 1;
  const pow = 10 ** Math.floor(Math.log10(rough));
  const f = rough / pow;
  const nice = f <= 1 ? 1 : f <= 2 ? 2 : f <= 5 ? 5 : 10;
  return nice * pow;
}

/** Runde Werte innerhalb [lo, hi], etwa `count` Stück. */
export function niceTicks(lo: number, hi: number, count = 4): number[] {
  const step = niceStep((hi - lo) / Math.max(1, count - 1));
  const ticks: number[] = [];
  for (let v = Math.ceil(lo / step) * step; v <= hi + step * 1e-9; v += step) {
    ticks.push(Math.round(v / step) * step);
  }
  return ticks;
}

/** Wertebereich mit Rand oben und unten; bei gleichen Werten ein sichtbarer Bereich. */
export function paddedRange(min: number, max: number, pad = 0.12): [number, number] {
  if (max - min < 1e-9) {
    const d = Math.max(1, Math.abs(min) * 0.02);
    return [min - d, max + d];
  }
  const d = (max - min) * pad;
  return [min - d, max + d];
}

/** ISO-Datum → Tageszahl (UTC), für lineare Zeitachsen. */
export function dayNumber(iso: string): number {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso);
  if (!m) return Number.NaN;
  return Date.UTC(Number(m[1]), Number(m[2]) - 1, Number(m[3])) / 86_400_000;
}

/** `2026-10-05` → `05.10.` */
export function shortDate(iso: string): string {
  const m = /^\d{4}-(\d{2})-(\d{2})/.exec(iso);
  return m ? `${m[2]}.${m[1]}.` : iso;
}
