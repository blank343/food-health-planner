"""Pydantic-Schemas der CRUD-Endpunkte (Ein- und Ausgabe). Datumsangaben als ISO 8601."""

from datetime import date, datetime, time
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator, model_validator

from app.calc.types import GoalKind, PersonSettings, Sex

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
ShortText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=60)]
OptText = Annotated[str, StringConstraints(strip_whitespace=True, max_length=2000)]


class ApiModel(BaseModel):
    """Basis: unbekannte Felder werden abgelehnt (422), Ausgabe aus ORM-Objekten erlaubt."""

    model_config = ConfigDict(from_attributes=True, extra="forbid")


# --------------------------------------------------------------------------- Profil


class PersonOut(ApiModel):
    id: int
    name: str
    sex: Sex
    birth_date: date
    height_cm: float | None


class PersonPatch(ApiModel):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)] | None = None
    sex: Sex | None = None
    birth_date: date | None = None
    height_cm: float | None = Field(default=None, ge=50, le=260)

    @field_validator("birth_date")
    @classmethod
    def _past(cls, v: date | None) -> date | None:
        if v is not None and v >= date.today():
            raise ValueError("Das Geburtsdatum muss in der Vergangenheit liegen.")
        return v

    @model_validator(mode="after")
    def _no_null_required(self) -> Self:
        for field in ("name", "sex", "birth_date"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"'{field}' darf nicht leer sein.")
        return self


# --------------------------------------------------------------------------- Einstellungen


class SettingsIn(PersonSettings):
    """Wie `PersonSettings`, aber unbekannte Felder führen zu 422."""

    model_config = ConfigDict(extra="forbid")


class SettingsOut(ApiModel):
    effective: PersonSettings  # gespeicherte Werte, ergänzt um Standardwerte
    stored: dict  # genau das, was gespeichert ist


# --------------------------------------------------------------------------- Ziele


class GoalIn(ApiModel):
    kind: GoalKind
    rate_kg_per_week: float | None = Field(default=None, ge=0, le=2)
    kcal_modifier_pct: float | None = Field(default=None, ge=-60, le=60)
    protein_g_per_kg: float | None = Field(default=None, gt=0, le=5)
    fat_pct: float | None = Field(default=None, ge=0, le=60)
    valid_from: date | None = None  # None = heute
    note: OptText | None = None


class GoalOut(ApiModel):
    id: int
    kind: GoalKind
    rate_kg_per_week: float | None
    kcal_modifier_pct: float | None
    protein_g_per_kg: float | None
    fat_pct: float | None
    valid_from: date
    note: str | None
    created_at: datetime


# --------------------------------------------------------------------------- Supplemente


class SupplementIn(ApiModel):
    name: Name
    dose_amount: float | None = Field(default=None, ge=0)
    dose_unit: Annotated[str, StringConstraints(strip_whitespace=True, max_length=20)] | None = None
    nutrients_per_day: dict[Annotated[str, StringConstraints(min_length=1, max_length=60)], float] = Field(
        default_factory=dict, description='Beitrag pro Tag, z. B. {"zinc_mg": 15}'
    )
    taking: bool = True
    time_of_day: Annotated[str, StringConstraints(strip_whitespace=True, max_length=30)] | None = None
    note: OptText | None = None

    @field_validator("nutrients_per_day")
    @classmethod
    def _non_negative(cls, v: dict[str, float]) -> dict[str, float]:
        if any(x < 0 for x in v.values()):
            raise ValueError("Nährstoffmengen dürfen nicht negativ sein.")
        return v


class SupplementOut(SupplementIn):
    id: int


# --------------------------------------------------------------------------- Ernährungsregeln


class NutrientRuleIn(ApiModel):
    subject: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]
    kind: Literal["max", "min", "avoid", "target"]
    value: float | None = Field(default=None, ge=0)
    unit: Annotated[str, StringConstraints(strip_whitespace=True, max_length=20)] | None = None
    per: Literal["day", "week"] = "day"
    hard: bool = True
    enabled: bool = True
    doctor_confirmed: bool = False
    suggested_by_app: bool = False
    source: Annotated[str, StringConstraints(strip_whitespace=True, max_length=200)] | None = None
    note: OptText | None = None

    @model_validator(mode="after")
    def _value_required(self) -> Self:
        if self.kind in ("max", "min", "target") and self.value is None:
            raise ValueError("Für diese Regelart ist ein Wert erforderlich.")
        return self


class NutrientRuleOut(NutrientRuleIn):
    id: int


# --------------------------------------------------------------------------- Trainingsplan


class TrainingItemIn(ApiModel):
    weekday: int = Field(ge=0, le=6, description="0 = Montag … 6 = Sonntag")
    session_type: ShortText
    intensity: Literal["easy", "moderate", "hard"]
    start_time: time | None = None
    duration_min: float | None = Field(default=None, gt=0, le=1440)
    expected_kcal: float | None = Field(default=None, ge=0, le=10000)
    enabled: bool = True
    note: OptText | None = None


class TrainingItemOut(TrainingItemIn):
    id: int


# --------------------------------------------------------------------------- Laborregeln


class LabRuleIn(ApiModel):
    name: Name
    analyte: Name
    comparator: Literal["lt", "gt", "between", "outside_ref"]
    threshold_low: float | None = None
    threshold_high: float | None = None
    effect_key: ShortText
    effect_weight: float = Field(default=0.5, ge=0, le=1)
    enabled: bool = True
    doctor_confirmed: bool = False
    suggested_by_app: bool = False
    source: Annotated[str, StringConstraints(strip_whitespace=True, max_length=200)] | None = None
    note: OptText | None = None

    @model_validator(mode="after")
    def _thresholds(self) -> Self:
        low, high = self.threshold_low, self.threshold_high
        if self.comparator == "between":
            if low is None or high is None:
                raise ValueError("Für 'between' sind threshold_low und threshold_high erforderlich.")
            if low > high:
                raise ValueError("threshold_low darf nicht größer als threshold_high sein.")
        elif self.comparator in ("lt", "gt") and low is None and high is None:
            raise ValueError("Für 'lt'/'gt' ist ein Schwellenwert erforderlich.")
        return self


class LabRuleOut(LabRuleIn):
    id: int
