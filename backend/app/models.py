"""Datenbankmodell Phase 1 (siehe docs/PHASE1.md, Abschnitt 4).

Persönliche Werte (Grenzen, Regeln, Ziele, Supplemente, Trainingsplan) sind Daten, nicht Code.
"""

from datetime import date, datetime, time

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    Time,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

JsonType = JSON().with_variant(JSONB(), "postgresql")


class Person(Base):
    __tablename__ = "person"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(80), unique=True)
    sex: Mapped[str] = mapped_column(String(1))  # "m" | "f"
    birth_date: Mapped[date] = mapped_column(Date)
    height_cm: Mapped[float | None] = mapped_column(Float, nullable=True)
    token_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    settings: Mapped["PersonSettingsRow | None"] = relationship(
        back_populates="person", uselist=False, cascade="all, delete-orphan"
    )


class PersonSettingsRow(Base):
    """Einstellungen als JSON, validiert durch `calc.types.PersonSettings`."""

    __tablename__ = "person_settings"

    person_id: Mapped[int] = mapped_column(ForeignKey("person.id", ondelete="CASCADE"), primary_key=True)
    data: Mapped[dict] = mapped_column(JsonType, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    person: Mapped[Person] = relationship(back_populates="settings")


class GoalProfile(Base):
    """Zielprofil, versioniert: aktiv ist die jüngste Version mit valid_from <= Datum."""

    __tablename__ = "goal_profile"
    __table_args__ = (Index("ix_goal_profile_person_valid", "person_id", "valid_from"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    person_id: Mapped[int] = mapped_column(ForeignKey("person.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(10))  # lose | maintain | gain
    rate_kg_per_week: Mapped[float | None] = mapped_column(Float, nullable=True)
    kcal_modifier_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    protein_g_per_kg: Mapped[float | None] = mapped_column(Float, nullable=True)
    fat_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    valid_from: Mapped[date] = mapped_column(Date)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class HealthDaily(Base):
    __tablename__ = "health_daily"
    __table_args__ = (
        UniqueConstraint("person_id", "day", "source", name="uq_health_daily_person_day_source"),
        Index("ix_health_daily_person_day", "person_id", "day"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    person_id: Mapped[int] = mapped_column(ForeignKey("person.id", ondelete="CASCADE"))
    day: Mapped[date] = mapped_column(Date)
    source: Mapped[str] = mapped_column(String(30))
    weight_kg: Mapped[float | None] = mapped_column(Float, nullable=True)
    body_fat_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    lean_mass_kg: Mapped[float | None] = mapped_column(Float, nullable=True)
    active_kcal: Mapped[float | None] = mapped_column(Float, nullable=True)
    basal_kcal: Mapped[float | None] = mapped_column(Float, nullable=True)
    steps: Mapped[float | None] = mapped_column(Float, nullable=True)
    resting_hr: Mapped[float | None] = mapped_column(Float, nullable=True)
    hrv_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    sleep_h: Mapped[float | None] = mapped_column(Float, nullable=True)


class Workout(Base):
    __tablename__ = "workout"
    __table_args__ = (
        UniqueConstraint("person_id", "start", "type", "source", name="uq_workout_person_start_type_source"),
        Index("ix_workout_person_start", "person_id", "start"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    person_id: Mapped[int] = mapped_column(ForeignKey("person.id", ondelete="CASCADE"))
    type: Mapped[str] = mapped_column(String(60))
    start: Mapped[datetime] = mapped_column(DateTime)
    duration_min: Mapped[float] = mapped_column(Float)
    active_kcal: Mapped[float | None] = mapped_column(Float, nullable=True)
    avg_hr: Mapped[float | None] = mapped_column(Float, nullable=True)
    max_hr: Mapped[float | None] = mapped_column(Float, nullable=True)
    distance_km: Mapped[float | None] = mapped_column(Float, nullable=True)
    source: Mapped[str] = mapped_column(String(30))


class LabReport(Base):
    __tablename__ = "lab_report"
    __table_args__ = (UniqueConstraint("person_id", "order_no", name="uq_lab_report_person_order"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    person_id: Mapped[int] = mapped_column(ForeignKey("person.id", ondelete="CASCADE"))
    lab_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    order_no: Mapped[str | None] = mapped_column(String(40), nullable=True)
    report_type: Mapped[str] = mapped_column(String(20))  # Endbefund | Teilbefund | ?
    sample_datetime: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    source_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    results: Mapped[list["LabResult"]] = relationship(
        back_populates="report", cascade="all, delete-orphan", order_by="LabResult.id"
    )


class LabResult(Base):
    __tablename__ = "lab_result"
    __table_args__ = (
        UniqueConstraint("report_id", "analyte", "unit", name="uq_lab_result_report_analyte_unit"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    report_id: Mapped[int] = mapped_column(ForeignKey("lab_report.id", ondelete="CASCADE"))
    analyte: Mapped[str] = mapped_column(String(120))
    unit: Mapped[str] = mapped_column(String(30))
    value: Mapped[float | None] = mapped_column(Float, nullable=True)
    value_op: Mapped[str | None] = mapped_column(String(2), nullable=True)
    flag: Mapped[str | None] = mapped_column(String(1), nullable=True)
    ref_low: Mapped[float | None] = mapped_column(Float, nullable=True)
    ref_high: Mapped[float | None] = mapped_column(Float, nullable=True)
    ref_op: Mapped[str | None] = mapped_column(String(2), nullable=True)
    pending: Mapped[bool] = mapped_column(Boolean, default=False)
    method: Mapped[str | None] = mapped_column(String(20), nullable=True)
    material: Mapped[str | None] = mapped_column(String(10), nullable=True)

    report: Mapped[LabReport] = relationship(back_populates="results")


class LabRule(Base):
    """Regel „Laborwert/Bereich → sanftes Planziel“. Einsehbar und abschaltbar."""

    __tablename__ = "lab_rule"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    person_id: Mapped[int] = mapped_column(ForeignKey("person.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    analyte: Mapped[str] = mapped_column(String(120))
    comparator: Mapped[str] = mapped_column(String(10))  # lt | gt | between | outside_ref
    threshold_low: Mapped[float | None] = mapped_column(Float, nullable=True)
    threshold_high: Mapped[float | None] = mapped_column(Float, nullable=True)
    effect_key: Mapped[str] = mapped_column(String(60))  # z. B. "boost_iron_vitc"
    effect_weight: Mapped[float] = mapped_column(Float, default=0.5)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    doctor_confirmed: Mapped[bool] = mapped_column(Boolean, default=False)
    suggested_by_app: Mapped[bool] = mapped_column(Boolean, default=False)
    source: Mapped[str | None] = mapped_column(String(200), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)


class Supplement(Base):
    __tablename__ = "supplement"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    person_id: Mapped[int] = mapped_column(ForeignKey("person.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    dose_amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    dose_unit: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # Beitrag pro Tag, z. B. {"zinc_mg": 15, "epa_dha_mg": 600}
    nutrients_per_day: Mapped[dict] = mapped_column(JsonType, default=dict)
    taking: Mapped[bool] = mapped_column(Boolean, default=True)
    time_of_day: Mapped[str | None] = mapped_column(String(30), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)


class NutrientRule(Base):
    """Ernährungsregel, z. B. Salz max 5 g/Tag, Kaliumsalz meiden, Fisch 1–2×/Woche."""

    __tablename__ = "nutrient_rule"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    person_id: Mapped[int] = mapped_column(ForeignKey("person.id", ondelete="CASCADE"), index=True)
    subject: Mapped[str] = mapped_column(String(80))  # Nährstoff- oder Lebensmittelgruppen-Schlüssel
    kind: Mapped[str] = mapped_column(String(10))  # max | min | avoid | target
    value: Mapped[float | None] = mapped_column(Float, nullable=True)
    unit: Mapped[str | None] = mapped_column(String(20), nullable=True)
    per: Mapped[str] = mapped_column(String(10), default="day")  # day | week
    hard: Mapped[bool] = mapped_column(Boolean, default=True)  # hart (Grenze) oder sanftes Ziel
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    doctor_confirmed: Mapped[bool] = mapped_column(Boolean, default=False)
    suggested_by_app: Mapped[bool] = mapped_column(Boolean, default=False)
    source: Mapped[str | None] = mapped_column(String(200), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)


class TrainingPlanItem(Base):
    __tablename__ = "training_plan_item"
    __table_args__ = (Index("ix_training_plan_person_weekday", "person_id", "weekday"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    person_id: Mapped[int] = mapped_column(ForeignKey("person.id", ondelete="CASCADE"))
    weekday: Mapped[int] = mapped_column(Integer)  # 0 = Montag … 6 = Sonntag
    session_type: Mapped[str] = mapped_column(String(60))
    intensity: Mapped[str] = mapped_column(String(10))  # easy | moderate | hard
    start_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    duration_min: Mapped[float | None] = mapped_column(Float, nullable=True)
    expected_kcal: Mapped[float | None] = mapped_column(Float, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)


class ImportJob(Base):
    __tablename__ = "import_job"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    person_id: Mapped[int] = mapped_column(ForeignKey("person.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(20))  # hae | apple_health | labs
    filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(10), default="queued")  # queued|running|done|failed
    progress: Mapped[float] = mapped_column(Float, default=0.0)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    stats: Mapped[dict] = mapped_column(JsonType, default=dict)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
