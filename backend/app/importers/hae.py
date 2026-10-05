"""Importer für Health Auto Export (HAE): ZIP oder einzelne CSV.

Aus dem ZIP werden nur die benötigten Mitglieder gelesen: die Tages-CSV
(`HealthAutoExport-*.csv`) und `Workouts-*.csv`. Die tausenden Einzel-Workout-
Dateien (CSV/GPX) werden weder entpackt noch geöffnet. Energie kommt in kJ und
wird in kcal umgerechnet. Das Gewicht wird mit `cleaning.clean_weights` bereinigt.
"""

import csv
import io
import math
import time
import zipfile
from datetime import date, datetime
from pathlib import Path
from typing import IO

from app.importers.cleaning import clean_weights
from app.importers.types import DailyRow, HealthImport, Progress, WeightCleanReport, WorkoutRow

KJ_PER_KCAL = 4.184

_DAILY = "daily"
_WORKOUTS = "workouts"


def _kind_from_name(name: str) -> str | None:
    """Art der Datei anhand des Dateinamens (ohne Ordner), sonst None."""
    base = Path(name).name
    if not base.lower().endswith(".csv"):
        return None
    if base.startswith("HealthAutoExport-"):
        return _DAILY
    if base.startswith("Workouts-"):
        return _WORKOUTS
    return None


def _num(value: str | None) -> float | None:
    """Zahl aus einer CSV-Zelle; leer oder unlesbar ergibt None."""
    if value is None:
        return None
    value = value.strip()
    if not value:
        return None
    try:
        number = float(value)
    except ValueError:
        return None
    return number if math.isfinite(number) else None


def _kcal(kj: float | None) -> float | None:
    return None if kj is None else round(kj / KJ_PER_KCAL, 1)


def _parse_day(value: str | None) -> date | None:
    """Datum aus `Date/Time` (z. B. `2025-09-30 00:00:00`)."""
    try:
        return date.fromisoformat((value or "").strip()[:10])
    except ValueError:
        return None


def _parse_start(value: str | None) -> datetime | None:
    """Startzeit eines Workouts (z. B. `2026-10-04 09:17`), naive Ortszeit."""
    try:
        return datetime.fromisoformat((value or "").strip())
    except ValueError:
        return None


def _parse_duration_min(value: str | None) -> float:
    """Dauer `HH:MM:SS` (oder `MM:SS`) in Minuten; unlesbar ergibt 0."""
    try:
        parts = [int(p) for p in (value or "").strip().split(":")]
    except ValueError:
        return 0.0
    if len(parts) == 2:
        parts = [0, *parts]
    if len(parts) != 3:
        return 0.0
    h, m, s = parts
    return round(h * 60 + m + s / 60, 1)


def _daily_row(record: dict[str, str]) -> DailyRow | None:
    day = _parse_day(record.get("Date/Time"))
    if day is None:
        return None
    asleep = _num(record.get("Sleep Analysis [Asleep] (hr)"))
    total = _num(record.get("Sleep Analysis [Total] (hr)"))
    return DailyRow(
        day=day,
        weight_kg=_num(record.get("Weight (kg)")),
        body_fat_pct=_num(record.get("Body Fat Percentage (%)")),
        lean_mass_kg=_num(record.get("Lean Body Mass (kg)")),
        active_kcal=_kcal(_num(record.get("Active Energy (kJ)"))),
        basal_kcal=_kcal(_num(record.get("Resting Energy (kJ)"))),
        steps=_num(record.get("Step Count (count)")),
        resting_hr=_num(record.get("Resting Heart Rate (count/min)")),
        hrv_ms=_num(record.get("Heart Rate Variability (ms)")),
        # 0 h Schlaf gilt als „nicht erfasst“ und fällt auf die Gesamtzeit zurück
        sleep_h=asleep if asleep else total,
    )


def _workout_row(record: dict[str, str]) -> WorkoutRow | None:
    start = _parse_start(record.get("Start"))
    if start is None:
        return None
    return WorkoutRow(
        type=(record.get("Workout Type") or "").strip(),
        start=start,
        duration_min=_parse_duration_min(record.get("Duration")),
        active_kcal=_kcal(_num(record.get("Active Energy (kJ)"))),
        avg_hr=_num(record.get("Avg. Heart Rate (count/min)")),
        max_hr=_num(record.get("Max. Heart Rate (count/min)")),
        distance_km=_num(record.get("Distance (km)")),
    )


def _height_cm(record: dict[str, str]) -> float | None:
    """Körpergröße aus `Height (m)` (Meter) in cm; unplausible Werte werden ignoriert."""
    value = _num(record.get("Height (m)"))
    if value is None:
        return None
    cm = value * 100 if value < 3 else value
    return cm if 100 <= cm <= 250 else None


def _read_csv(
    raw: IO[bytes], kind: str | None, heights: list[float] | None = None
) -> tuple[str | None, list[DailyRow], list[WorkoutRow], int]:
    """Liest eine CSV im Streaming. Ohne `kind` wird er aus der Kopfzeile erkannt.

    Rückgabe: (Art, Tageszeilen, Workouts, übersprungene Zeilen). Gefundene Körpergrößen (cm)
    werden an `heights` angehängt, falls angegeben.
    """
    text = io.TextIOWrapper(raw, encoding="utf-8-sig", errors="replace", newline="")
    reader = csv.DictReader(text)
    fields = reader.fieldnames or []
    if kind is None:
        if "Date/Time" in fields:
            kind = _DAILY
        elif "Workout Type" in fields and "Start" in fields:
            kind = _WORKOUTS
    daily: list[DailyRow] = []
    workouts: list[WorkoutRow] = []
    skipped = 0
    if kind is None:
        return None, daily, workouts, skipped
    for record in reader:
        if kind == _DAILY:
            row = _daily_row(record)
            if row is None:
                skipped += 1
            else:
                daily.append(row)
                if heights is not None and (h := _height_cm(record)) is not None:
                    heights.append(h)
        else:
            wrow = _workout_row(record)
            if wrow is None:
                skipped += 1
            else:
                workouts.append(wrow)
    return kind, daily, workouts, skipped


def _merge_days(rows: list[DailyRow]) -> list[DailyRow]:
    """Fasst mehrere Zeilen desselben Tages zusammen (später gelesene Werte gewinnen)."""
    merged: dict[date, DailyRow] = {}
    for row in rows:
        current = merged.get(row.day)
        if current is None:
            merged[row.day] = row
            continue
        for name in vars(row):
            value = getattr(row, name)
            if name != "day" and value is not None:
                setattr(current, name, value)
    return [merged[d] for d in sorted(merged)]


def _clean_weight_column(daily: list[DailyRow]) -> WeightCleanReport:
    """Bereinigt die Gewichtsreihe; entfernte Werte werden in den Zeilen auf None gesetzt."""
    series = [(r.day, r.weight_kg) for r in daily if r.weight_kg is not None]
    kept, report = clean_weights(series)
    keep_days = {d for d, _ in kept}
    for row in daily:
        if row.weight_kg is not None and row.day not in keep_days:
            row.weight_kg = None
    return report


def import_hae(path: Path, progress: Progress | None = None) -> HealthImport:
    """Importiert einen Health-Auto-Export-ZIP oder eine einzelne CSV-Datei."""
    started = time.monotonic()
    path = Path(path)
    daily: list[DailyRow] = []
    workouts: list[WorkoutRow] = []
    skipped = 0
    files_read = 0
    heights: list[float] = []

    def report(fraction: float, message: str) -> None:
        if progress is not None:
            progress(fraction, message)

    report(0.0, "Import wird gestartet")
    if zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as zf:
            members = [(i.filename, k) for i in zf.infolist() if (k := _kind_from_name(i.filename))]
            for n, (name, kind) in enumerate(members, start=1):
                with zf.open(name) as raw:
                    _, d, w, s = _read_csv(raw, kind, heights)
                daily += d
                workouts += w
                skipped += s
                files_read += 1
                report(0.9 * n / len(members), f"{Path(name).name} gelesen")
    else:
        with path.open("rb") as raw:
            kind, daily, workouts, skipped = _read_csv(raw, _kind_from_name(path.name), heights)
        files_read = 1 if kind else 0
        report(0.9, "Datei gelesen")

    daily = _merge_days(daily)
    weight_report = _clean_weight_column(daily)
    workouts.sort(key=lambda w: w.start)
    report(1.0, "Import abgeschlossen")

    days = [r.day for r in daily]
    return HealthImport(
        source="hae_zip",
        daily=daily,
        workouts=workouts,
        profile={"height_cm": round(heights[-1], 1)} if heights else {},
        weight_report=weight_report,
        stats={
            "files_read": files_read,
            "daily_rows": len(daily),
            "workout_rows": len(workouts),
            "skipped_rows": skipped,
            "date_from": min(days) if days else None,
            "date_to": max(days) if days else None,
            "seconds": round(time.monotonic() - started, 2),
        },
    )
