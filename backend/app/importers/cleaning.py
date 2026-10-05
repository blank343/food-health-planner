"""Bereinigung von Messreihen (aus dem Spike b übernommen und getestet)."""

import statistics
from collections import Counter
from datetime import date

from app.importers.types import WeightCleanReport


def clean_weights(
    series: list[tuple[date, float]],
    lo: float = 35.0,
    hi: float = 250.0,
) -> tuple[list[tuple[date, float]], WeightCleanReport]:
    """Entfernt unplausible Werte, wiederholte Platzhalter und Ausreißer.

    - Unplausibel: außerhalb [lo, hi].
    - Platzhalter: derselbe auf 2 Nachkommastellen gerundete Wert, der in der Reihe
      auffällig oft vorkommt (>= 5 % der plausiblen Messungen und >= 4 Mal).
    - Ausreißer: Abweichung > 6 MAD vom gleitenden Median (Fenster 15) und > 3 kg.
    """
    report = WeightCleanReport(raw=len(series))
    in_range = [(d, w) for d, w in series if lo <= w <= hi]
    report.out_of_range = len(series) - len(in_range)

    counts = Counter(round(w, 2) for _, w in in_range)
    threshold = max(4, int(0.05 * len(in_range)))
    placeholders = {v for v, c in counts.items() if c >= threshold}
    report.placeholders = sorted(placeholders)
    after = [(d, w) for d, w in in_range if round(w, 2) not in placeholders]

    kept: list[tuple[date, float]] = []
    for i, (d, w) in enumerate(after):
        window = [x for _, x in after[max(0, i - 7) : i + 8]]
        med = statistics.median(window)
        mad = statistics.median([abs(x - med) for x in window]) or 0.5
        if abs(w - med) > 6 * 1.4826 * mad and abs(w - med) > 3.0:
            report.outliers.append((d, w))
        else:
            kept.append((d, w))
    report.kept = len(kept)
    return kept, report
