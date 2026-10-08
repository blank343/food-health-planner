"""Gemeinsame Typen der Rechner (Vertrag zwischen calc/, services/ und api/).

Reine Datenklassen ohne Datenbankbezug. Änderungen an diesen Typen nur durch den Hauptagenten.
"""

from dataclasses import dataclass, field
from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.calc import defaults

Sex = Literal["m", "f"]
DayType = Literal["rest", "easy", "moderate", "hard"]
GoalKind = Literal["lose", "maintain", "gain"]
Severity = Literal["info", "warn", "block"]


class PersonSettings(BaseModel):
    """Alle einstellbaren Werte einer Person. Fehlende Felder = sichere Standardwerte."""

    # Sicherheitsgrenzen (None = Standardwert aus defaults.py verwenden)
    kcal_floor: float | None = Field(default=None, ge=0)
    protein_floor_g_per_kg: float = Field(default=defaults.PROTEIN_FLOOR_G_PER_KG, ge=0)
    max_rate_kg_per_week: float | None = Field(default=None, ge=0)
    weight_floor_kg: float | None = Field(default=None, gt=0)
    bf_floor_pct: float | None = Field(default=None, ge=0, le=60)
    taper_weight_kg: float = Field(default=defaults.TAPER_WEIGHT_KG, ge=0)
    taper_bf_pct_points: float = Field(default=defaults.TAPER_BF_PCT_POINTS, ge=0)

    # Energie
    kcal_per_kg: float = Field(default=defaults.KCAL_PER_KG_BODY_MASS, gt=0)
    use_katch_mcardle: bool = False
    tdee_calibration: bool = True
    reported_intake_kcal: float | None = Field(default=None, gt=0)

    # Verteilung
    day_type_weights: dict[str, float] = Field(default_factory=lambda: dict(defaults.DAY_TYPE_WEIGHTS))
    slot_shares: dict[str, float] = Field(default_factory=lambda: dict(defaults.DEFAULT_SLOT_SHARES))
    # Samstag/Sonntag, falls abweichend (None = wie unter der Woche)
    slot_shares_weekend: dict[str, float] | None = None
    single_meal_max_kcal: float | None = Field(default=None, gt=0)

    # Datenquellen
    source_priority: list[str] = Field(default_factory=lambda: list(defaults.SOURCE_PRIORITY))

    @field_validator("slot_shares", "slot_shares_weekend", "day_type_weights")
    @classmethod
    def _positive(cls, v: dict[str, float] | None) -> dict[str, float] | None:
        if v is None:
            return v
        if any(x < 0 for x in v.values()):
            raise ValueError("Werte dürfen nicht negativ sein")
        if not v or sum(v.values()) <= 0:
            raise ValueError("Mindestens ein Wert muss größer als 0 sein")
        return v


@dataclass(frozen=True)
class PersonProfile:
    """Körperdaten zum Berechnungszeitpunkt."""

    sex: Sex
    age_years: float
    height_cm: float
    weight_kg: float
    body_fat_pct: float | None = None
    lean_mass_kg: float | None = None


@dataclass(frozen=True)
class GoalSpec:
    kind: GoalKind
    rate_kg_per_week: float | None = None  # bei "lose": gewünschter Verlust pro Woche (positiv)
    kcal_modifier_pct: float | None = None  # alternativ: -10 = 10 % Defizit
    protein_g_per_kg: float | None = None
    fat_pct: float | None = None


@dataclass(frozen=True)
class DayEnergy:
    day: date
    basal_kcal: float | None
    active_kcal: float | None


@dataclass(frozen=True)
class DeviceTdee:
    kcal: float | None
    n_days: int
    coverage: float  # Anteil der Tage im Fenster mit Daten (0–1)


@dataclass(frozen=True)
class WeightTrend:
    slope_kg_per_day: float | None
    last_smoothed_kg: float | None
    n_points: int
    span_days: int


@dataclass(frozen=True)
class TdeeEstimate:
    tdee_kcal: float
    device_kcal: float | None
    implied_kcal: float | None
    confidence: float  # 0–1
    method: Literal["device", "calibrated", "formula"]
    notes: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class DayTarget:
    kcal: float
    protein_g: float
    fat_g: float
    carb_g: float
    day_type: DayType = "easy"


@dataclass(frozen=True)
class SlotTarget:
    kcal: float
    protein_g: float
    fat_g: float
    carb_g: float


@dataclass(frozen=True)
class Warning:
    code: str
    severity: Severity
    message: str  # deutsch, verständlich


@dataclass(frozen=True)
class SafetyResult:
    target: DayTarget
    warnings: list[Warning]
    applied_rate_kg_per_week: float | None = None


# ---------------------------------------------------------------------------
# Phase 2: Zutaten und Nährwerte (siehe docs/PHASE2.md, Abschnitte 4 und 6)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ParsedIngredient:
    """Ergebnis von `calc.ingredients.parse_ingredient_line`."""

    raw: str
    name: str  # Rohname ohne Menge, Einheit und Zusatz, z. B. "Zwiebel"
    quantity: float | None = None  # None bei "Salz und Pfeffer", "nach Geschmack"
    quantity_max: float | None = None  # bei Bereichen "3-4": quantity=3, quantity_max=4
    unit: str | None = None  # normalisiert (siehe defaults.UNIT_ALIASES); None = Stückzahl
    note: str | None = None  # z. B. "fein gehackt", Text nach Doppelpunkt
    optional: bool = False  # "optional", "nach Belieben", "evtl."


@dataclass(frozen=True)
class IngredientMatch:
    ingredient_id: int
    name: str
    score: float  # 0–100
    via: Literal["synonym", "exact", "fuzzy"]


@dataclass(frozen=True)
class Nutrients:
    """Absolute Nährwerte (z. B. einer Zeile, einer Portion oder eines Rezepts)."""

    kcal: float = 0.0
    protein_g: float = 0.0
    fat_g: float = 0.0
    carb_g: float = 0.0
    fiber_g: float = 0.0
    salt_g: float = 0.0
    micros: dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class NutrientsPer100:
    """Nährwerte je 100 g einer Zutat. None = unbekannt (zählt nicht als 0)."""

    kcal: float | None = None
    protein_g: float | None = None
    fat_g: float | None = None
    carb_g: float | None = None
    fiber_g: float | None = None
    salt_g: float | None = None
    micros: dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class LineNutrition:
    """Eine Zutatenzeile für den Rechner: Menge in g und die zugeordnete Zutat."""

    label: str
    grams: float | None  # None = Menge unbekannt (Zeile zählt als "fehlend")
    per100: NutrientsPer100 | None  # None = keine Zutat zugeordnet
    optional: bool = False  # optionale Zeilen zählen nicht in die Summe und nicht als fehlend


@dataclass(frozen=True)
class RecipeNutrition:
    total: Nutrients
    per_serving: Nutrients
    servings: float
    total_weight_g: float
    serving_weight_g: float
    energy_density_kcal_per_100g: float | None
    coverage: float  # Anteil der (nicht optionalen) Zeilen mit Menge und Werten, 0–1
    missing: list[str] = field(default_factory=list)  # Labels der Zeilen ohne Werte


@dataclass(frozen=True)
class SatietyScore:
    score: float  # 0–100, höher = sättigender
    # Teilwerte 0–1: density, volume, protein, fiber, warm
    parts: dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class SlotFit:
    """Wie gut passt eine Portion in das Ziel einer Mahlzeit (siehe PHASE2.md, Abschnitt 6)."""

    factor: float  # Portionsfaktor (nach Begrenzung)
    unclamped_factor: float
    grams: float  # Menge der skalierten Portion
    scaled: Nutrients  # Nährwerte der skalierten Portion
    deviation_pct: dict[str, float]  # kcal, protein, fat, carb: (Ist − Ziel) / Ziel × 100
    fit_score: float  # 0–100
    notes: list[str] = field(default_factory=list)  # deutsche Hinweise


@dataclass(frozen=True)
class ComponentChoice:
    """Eine Baukasten-Komponente mit gewählter Menge."""

    label: str
    grams: float
    per100: NutrientsPer100
