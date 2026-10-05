"""Gemeinsame Datentypen der Importer (Vertrag zwischen importers/ und services/).

Reine Datenklassen ohne Datenbankbezug. Änderungen nur durch den Hauptagenten.
Einheiten: kcal, kg, cm, Prozent 0–100, Zeitpunkte als naive Ortszeit.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime

# progress(fraction 0..1, message)
Progress = Callable[[float, str], None]


@dataclass
class DailyRow:
    day: date
    weight_kg: float | None = None
    body_fat_pct: float | None = None
    lean_mass_kg: float | None = None
    active_kcal: float | None = None
    basal_kcal: float | None = None
    steps: float | None = None
    resting_hr: float | None = None
    hrv_ms: float | None = None
    sleep_h: float | None = None


@dataclass
class WorkoutRow:
    type: str
    start: datetime
    duration_min: float
    active_kcal: float | None = None
    avg_hr: float | None = None
    max_hr: float | None = None
    distance_km: float | None = None


@dataclass
class WeightCleanReport:
    raw: int = 0
    kept: int = 0
    out_of_range: int = 0
    placeholders: list[float] = field(default_factory=list)
    outliers: list[tuple[date, float]] = field(default_factory=list)


@dataclass
class HealthImport:
    source: str  # "hae_zip" | "apple_health_xml"
    daily: list[DailyRow] = field(default_factory=list)
    workouts: list[WorkoutRow] = field(default_factory=list)
    profile: dict[str, object] = field(default_factory=dict)  # z. B. height_cm, birth_date, sex
    weight_report: WeightCleanReport = field(default_factory=WeightCleanReport)
    stats: dict[str, object] = field(default_factory=dict)  # Laufzeit, Dateien, übersprungene Zeilen


@dataclass
class LabResultRow:
    analyte: str
    unit: str
    value: float | None
    value_op: str | None = None  # "<" oder ">" am Messwert
    flag: str | None = None  # "L" | "H"
    ref_low: float | None = None
    ref_high: float | None = None
    ref_op: str | None = None  # "<" oder ">" bei einseitigen Referenzen
    pending: bool = False  # "folgt"
    method: str | None = None
    material: str | None = None


@dataclass
class LabReport:
    report_type: str  # "Endbefund" | "Teilbefund" | "?"
    lab_name: str | None = None
    order_no: str | None = None
    sample_datetime: datetime | None = None
    # Nur zur Zuordnung/Prüfung, werden NICHT gespeichert:
    patient_name: str | None = None
    birth_date: date | None = None
    results: list[LabResultRow] = field(default_factory=list)
