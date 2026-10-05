"""Tests für den Apple-Health-XML-Importer (nur synthetische, erfundene Daten)."""

from datetime import date, datetime
from pathlib import Path

import pytest

from app.importers.apple_health import import_apple_health

Q = "HKQuantityTypeIdentifier"

HEADER = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE HealthData [
<!ELEMENT HealthData (ExportDate,Me,(Record|Correlation|Workout|ActivitySummary)*)>
<!ATTLIST HealthData locale CDATA #REQUIRED>
<!ELEMENT ExportDate EMPTY>
<!ATTLIST ExportDate value CDATA #REQUIRED>
<!ELEMENT Me EMPTY>
<!ATTLIST Me
  HKCharacteristicTypeIdentifierDateOfBirth CDATA #REQUIRED
  HKCharacteristicTypeIdentifierBiologicalSex CDATA #REQUIRED>
<!ELEMENT Record (MetadataEntry*)>
<!ATTLIST Record
  type CDATA #REQUIRED
  sourceName CDATA #REQUIRED
  unit CDATA #IMPLIED
  startDate CDATA #REQUIRED
  endDate CDATA #REQUIRED
  value CDATA #IMPLIED>
<!ELEMENT MetadataEntry EMPTY>
<!ATTLIST MetadataEntry key CDATA #REQUIRED value CDATA #REQUIRED>
<!ELEMENT Workout ANY>
<!ATTLIST Workout
  workoutActivityType CDATA #REQUIRED
  duration CDATA #IMPLIED
  durationUnit CDATA #IMPLIED
  totalDistance CDATA #IMPLIED
  totalDistanceUnit CDATA #IMPLIED
  totalEnergyBurned CDATA #IMPLIED
  totalEnergyBurnedUnit CDATA #IMPLIED
  startDate CDATA #REQUIRED
  endDate CDATA #REQUIRED>
<!ELEMENT WorkoutStatistics EMPTY>
<!ATTLIST WorkoutStatistics
  type CDATA #REQUIRED average CDATA #IMPLIED maximum CDATA #IMPLIED
  sum CDATA #IMPLIED unit CDATA #IMPLIED>
<!ELEMENT WorkoutRoute (FileReference)>
<!ELEMENT FileReference EMPTY>
<!ATTLIST FileReference path CDATA #REQUIRED>
]>
<HealthData locale="de_DE">
 <ExportDate value="2026-10-05 08:00:00 +0200"/>
"""

ME = (
    '<Me HKCharacteristicTypeIdentifierDateOfBirth="1990-04-02" '
    'HKCharacteristicTypeIdentifierBiologicalSex="HKBiologicalSexFemale"/>\n'
)


def rec(
    rtype: str,
    start: str,
    value: str,
    unit: str = "count",
    source: str = "Quelle A",
    end: str | None = None,
    extra: str = "",
) -> str:
    t = rtype if rtype.startswith("HK") else Q + rtype
    return (
        f'<Record type="{t}" sourceName="{source}" unit="{unit}" '
        f'startDate="{start} +0200" endDate="{end or start} +0200" value="{value}">{extra}</Record>\n'
    )


def write_xml(tmp_path: Path, body: str, me: str = ME) -> Path:
    p = tmp_path / "export.xml"
    p.write_text(HEADER + me + body + "</HealthData>\n", encoding="utf-8")
    return p


def by_day(result) -> dict[date, object]:
    return {r.day: r for r in result.daily}


def test_source_and_stats(tmp_path):
    p = write_xml(tmp_path, rec("StepCount", "2026-10-01 10:00:00", "100"))
    res = import_apple_health(p)
    assert res.source == "apple_health_xml"
    assert res.stats["records_seen"] == 1
    assert res.stats["records_used"] == 1
    assert res.stats["daily_rows"] == 1
    assert res.stats["workout_rows"] == 0
    assert res.stats["date_from"] == "2026-10-01"
    assert res.stats["date_to"] == "2026-10-01"
    assert res.stats["skipped_malformed"] == 0
    assert res.stats["seconds"] >= 0


def test_body_fat_fraction_to_percent_and_percent_kept(tmp_path):
    body = rec("BodyFatPercentage", "2026-10-01 07:00:00", "0.231", "%")
    body += rec("BodyFatPercentage", "2026-10-02 07:00:00", "24.5", "%")
    days = by_day(import_apple_health(write_xml(tmp_path, body)))
    assert days[date(2026, 10, 1)].body_fat_pct == pytest.approx(23.1)
    assert days[date(2026, 10, 2)].body_fat_pct == pytest.approx(24.5)


def test_steps_not_added_across_sources(tmp_path):
    """iPhone und Watch zählen dieselben Schritte: es zählt nur die größte Quellensumme."""
    body = ""
    # Quelle "Phone": 300 + 400 = 700
    body += rec("StepCount", "2026-10-01 08:00:00", "300", source="Phone")
    body += rec("StepCount", "2026-10-01 12:00:00", "400", source="Phone")
    # Quelle "Watch": 500 + 450 = 950 (größte)
    body += rec("StepCount", "2026-10-01 08:00:00", "500", source="Watch")
    body += rec("StepCount", "2026-10-01 12:00:00", "450", source="Watch")
    row = by_day(import_apple_health(write_xml(tmp_path, body)))[date(2026, 10, 1)]
    assert row.steps == pytest.approx(950)
    assert row.steps != pytest.approx(1650)


def test_energy_per_source_and_kj_to_kcal(tmp_path):
    body = rec("ActiveEnergyBurned", "2026-10-01 09:00:00", "100", "kcal", source="Phone")
    body += rec("ActiveEnergyBurned", "2026-10-01 09:00:00", "200", "kcal", source="Watch")
    body += rec("BasalEnergyBurned", "2026-10-01 00:00:00", "8368", "kJ", source="Watch")
    row = by_day(import_apple_health(write_xml(tmp_path, body)))[date(2026, 10, 1)]
    assert row.active_kcal == pytest.approx(200)
    assert row.basal_kcal == pytest.approx(2000)


def test_hrv_is_daily_mean(tmp_path):
    body = rec("HeartRateVariabilitySDNN", "2026-10-01 03:00:00", "40", "ms")
    body += rec("HeartRateVariabilitySDNN", "2026-10-01 04:00:00", "50", "ms")
    body += rec("HeartRateVariabilitySDNN", "2026-10-01 05:00:00", "60", "ms")
    row = by_day(import_apple_health(write_xml(tmp_path, body)))[date(2026, 10, 1)]
    assert row.hrv_ms == pytest.approx(50)


def test_last_value_of_day_for_resting_hr_and_lean_mass(tmp_path):
    body = rec("RestingHeartRate", "2026-10-01 12:00:00", "58", "count/min")
    body += rec("RestingHeartRate", "2026-10-01 07:00:00", "61", "count/min")
    body += rec("LeanBodyMass", "2026-10-01 07:00:00", "110", "lb")
    row = by_day(import_apple_health(write_xml(tmp_path, body)))[date(2026, 10, 1)]
    assert row.resting_hr == pytest.approx(58)  # spätester Eintrag, auch wenn er zuerst steht
    assert row.lean_mass_kg == pytest.approx(110 * 0.45359237, abs=0.01)


def test_sleep_assigned_to_end_date_and_overlaps_merged(tmp_path):
    cat = "HKCategoryTypeIdentifierSleepAnalysis"
    v = "HKCategoryValueSleepAnalysis"
    body = rec(cat, "2026-10-03 23:00:00", v + "AsleepCore", "", end="2026-10-04 02:00:00")
    body += rec(cat, "2026-10-04 02:00:00", v + "AsleepDeep", "", end="2026-10-04 03:30:00")
    # zweite Quelle überlappt (01:00-04:00 insgesamt wird mit 23:00-03:30 vereinigt)
    body += rec(cat, "2026-10-04 01:00:00", v + "AsleepREM", "", source="Quelle B", end="2026-10-04 04:00:00")
    # Wachphase und InBed zählen nicht
    body += rec(cat, "2026-10-04 04:00:00", v + "Awake", "", end="2026-10-04 05:00:00")
    body += rec(cat, "2026-10-03 22:00:00", v + "InBed", "", end="2026-10-04 06:00:00")
    days = by_day(import_apple_health(write_xml(tmp_path, body)))
    assert date(2026, 10, 3) not in days
    # Vereinigung 23:00 - 04:00 = 5 Stunden
    assert days[date(2026, 10, 4)].sleep_h == pytest.approx(5.0)


def test_placeholder_weight_removed(tmp_path):
    body = ""
    for i in range(1, 11):  # zehn Tage mit demselben Platzhalterwert
        body += rec("BodyMass", f"2026-09-{i:02d} 07:00:00", "100.00", "kg")
    for i, w in enumerate([71.2, 71.0, 70.8, 70.9, 70.7], start=11):
        body += rec("BodyMass", f"2026-09-{i:02d} 07:00:00", str(w), "kg")
    res = import_apple_health(write_xml(tmp_path, body))
    assert 100.0 in res.weight_report.placeholders
    days = by_day(res)
    assert date(2026, 9, 5) not in days
    assert days[date(2026, 9, 11)].weight_kg == pytest.approx(71.2)
    assert res.weight_report.raw == 15
    assert res.weight_report.kept == 5


def test_weight_last_value_of_day_and_lb(tmp_path):
    body = ""
    for i, w in enumerate([71.0, 71.1, 70.9, 70.8, 71.2, 70.7], start=1):
        body += rec("BodyMass", f"2026-09-{i:02d} 07:00:00", str(w), "kg")
    body += rec("BodyMass", "2026-09-06 20:00:00", "156.5", "lb")  # später am selben Tag
    days = by_day(import_apple_health(write_xml(tmp_path, body)))
    assert days[date(2026, 9, 6)].weight_kg == pytest.approx(156.5 * 0.45359237)


def test_profile_extraction_with_last_height(tmp_path):
    body = rec("Height", "2020-01-01 10:00:00", "1.60", "m")
    body += rec("Height", "2025-01-01 10:00:00", "172", "cm")
    body += rec("StepCount", "2026-10-01 10:00:00", "10")
    res = import_apple_health(write_xml(tmp_path, body))
    assert res.profile == {"birth_date": date(1990, 4, 2), "sex": "f", "height_cm": 172.0}
    # Größe erzeugt keine Tageszeile
    assert [r.day for r in res.daily] == [date(2026, 10, 1)]


def test_profile_height_in_meters_and_missing_keys(tmp_path):
    body = rec("Height", "2025-01-01 10:00:00", "1.75", "m")
    me = '<Me HKCharacteristicTypeIdentifierBiologicalSex="HKBiologicalSexMale"/>\n'
    res = import_apple_health(write_xml(tmp_path, body, me=me))
    assert res.profile == {"sex": "m", "height_cm": 175.0}


def test_implausible_height_ignored(tmp_path):
    body = rec("Height", "2025-01-01 10:00:00", "12", "cm")
    res = import_apple_health(write_xml(tmp_path, body))
    assert "height_cm" not in res.profile


def test_workout_parsing(tmp_path):
    wo = (
        '<Workout workoutActivityType="HKWorkoutActivityTypeRunning" duration="45.5" '
        'durationUnit="min" totalDistance="6.2" totalDistanceUnit="mi" '
        'totalEnergyBurned="2092" totalEnergyBurnedUnit="kJ" '
        'startDate="2026-10-02 18:30:00 +0200" endDate="2026-10-02 19:15:30 +0200">\n'
        f'  <WorkoutStatistics type="{Q}HeartRate" average="141.4" maximum="172" unit="count/min"/>\n'
        '  <WorkoutRoute><FileReference path="/workout-routes/route_unsichtbar.gpx"/></WorkoutRoute>\n'
        "</Workout>\n"
        '<Workout workoutActivityType="HKWorkoutActivityTypeYoga" duration="1800" durationUnit="sec" '
        'startDate="2026-10-03 07:00:00 +0200" endDate="2026-10-03 07:30:00 +0200"/>\n'
        '<Workout workoutActivityType="HKWorkoutActivityTypeCycling" duration="1.5" durationUnit="hr" '
        'totalEnergyBurned="300" totalEnergyBurnedUnit="kcal" '
        'startDate="2026-10-04 07:00:00 +0200" endDate="2026-10-04 08:30:00 +0200"/>\n'
    )
    res = import_apple_health(write_xml(tmp_path, wo))
    assert res.stats["workout_rows"] == 3
    run, yoga, bike = res.workouts
    assert run.type == "Running"
    assert run.start == datetime(2026, 10, 2, 18, 30)
    assert run.duration_min == pytest.approx(45.5)
    assert run.active_kcal == pytest.approx(500.0, abs=0.1)
    assert run.distance_km == pytest.approx(6.2 * 1.609344, abs=0.001)
    assert run.avg_hr == pytest.approx(141.4)
    assert run.max_hr == pytest.approx(172)
    assert yoga.type == "Yoga"
    assert yoga.duration_min == pytest.approx(30)
    assert yoga.active_kcal is None and yoga.avg_hr is None and yoga.distance_km is None
    assert bike.duration_min == pytest.approx(90)
    assert bike.active_kcal == pytest.approx(300)


def test_workout_statistics_fallback_for_energy(tmp_path):
    wo = (
        '<Workout workoutActivityType="HKWorkoutActivityTypeWalking" duration="30" durationUnit="min" '
        'startDate="2026-10-02 10:00:00 +0200" endDate="2026-10-02 10:30:00 +0200">\n'
        f'  <WorkoutStatistics type="{Q}ActiveEnergyBurned" sum="120" unit="kcal"/>\n'
        f'  <WorkoutStatistics type="{Q}DistanceWalkingRunning" sum="2400" unit="m"/>\n'
        "</Workout>\n"
    )
    (w,) = import_apple_health(write_xml(tmp_path, wo)).workouts
    assert w.active_kcal == pytest.approx(120)
    assert w.distance_km == pytest.approx(2.4)


def test_malformed_values_skipped_and_counted(tmp_path):
    body = rec("StepCount", "2026-10-01 10:00:00", "abc")
    body += rec("StepCount", "kaputt", "100")
    body += rec("StepCount", "2026-10-01 11:00:00", "250")
    body += rec("HKCategoryTypeIdentifierSleepAnalysis", "xx", "HKCategoryValueSleepAnalysisAsleepCore", "")
    body += (
        '<Workout workoutActivityType="HKWorkoutActivityTypeRunning" duration="zehn" '
        'startDate="2026-10-02 18:30:00 +0200" endDate="2026-10-02 19:00:00 +0200"/>\n'
    )
    res = import_apple_health(write_xml(tmp_path, body))
    assert res.stats["skipped_malformed"] == 4
    assert by_day(res)[date(2026, 10, 1)].steps == pytest.approx(250)
    assert res.workouts == []


def test_unknown_records_ignored_and_nested_metadata(tmp_path):
    body = rec("HeartRate", "2026-10-01 10:00:00", "70", "count/min")
    body += rec("StepCount", "2026-10-01 10:00:00", "5", extra='<MetadataEntry key="k" value="v"/>')
    res = import_apple_health(write_xml(tmp_path, body))
    assert res.stats["records_seen"] == 2
    assert res.stats["records_used"] == 1
    assert by_day(res)[date(2026, 10, 1)].steps == pytest.approx(5)


def test_progress_callback(tmp_path):
    body = "".join(rec("StepCount", f"2026-10-01 {h:02d}:00:00", "10") for h in range(24))
    calls: list[tuple[float, str]] = []
    import_apple_health(write_xml(tmp_path, body), progress=lambda f, m: calls.append((f, m)))
    assert calls[0][0] == 0.0
    assert calls[-1][0] == 1.0
    fractions = [f for f, _ in calls]
    assert fractions == sorted(fractions)
    assert all(isinstance(m, str) and m for _, m in calls)


def test_empty_export(tmp_path):
    res = import_apple_health(write_xml(tmp_path, "", me="<Me/>\n"))
    assert res.daily == []
    assert res.workouts == []
    assert res.profile == {}
    assert res.stats["daily_rows"] == 0
    assert res.stats["date_from"] is None
    assert res.stats["date_to"] is None
    assert res.weight_report.raw == 0


def test_many_records_stream_with_root_clearing(tmp_path):
    """Mehr Einträge als das Root-Clear-Intervall: Ergebnis bleibt korrekt."""
    n = 5000
    body = "".join(rec("StepCount", "2026-10-01 10:00:00", "1") for _ in range(n))
    row = by_day(import_apple_health(write_xml(tmp_path, body)))[date(2026, 10, 1)]
    assert row.steps == pytest.approx(n)
