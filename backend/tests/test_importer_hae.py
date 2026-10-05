"""Tests für den HAE-Importer. Nur erfundene, synthetische Daten."""

import zipfile
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest

from app.importers.hae import KJ_PER_KCAL, import_hae

DAILY_HEADER = (
    "Date/Time,Active Energy (kJ),Resting Energy (kJ),Weight (kg),Body Fat Percentage (%),"
    "Lean Body Mass (kg),Step Count (count),Resting Heart Rate (count/min),"
    "Heart Rate Variability (ms),Sleep Analysis [Asleep] (hr),Sleep Analysis [Total] (hr)"
)
WORKOUT_HEADER = (
    "Workout Type,Start,End,Duration,Active Energy (kJ),Max. Heart Rate (count/min),"
    "Avg. Heart Rate (count/min),Distance (km)"
)


def _write(path: Path, text: str, encoding: str = "utf-8") -> Path:
    path.write_bytes(text.encode(encoding))
    return path


def _zip(path: Path, members: dict[str, str]) -> Path:
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, content in members.items():
            zf.writestr(name, content.encode("utf-8"))
    return path


def test_daily_conversion_and_fields(tmp_path):
    text = (
        f"{DAILY_HEADER}\n"
        "2030-01-02 00:00:00,418.4,836.8,70.5,22.5,54.6,1234,55,48.5,7.25,7.9\n"
    )
    result = import_hae(_write(tmp_path / "HealthAutoExport-x.csv", text))
    assert result.source == "hae_zip"
    (row,) = result.daily
    assert row.day == date(2030, 1, 2)
    assert row.active_kcal == pytest.approx(418.4 / KJ_PER_KCAL, abs=0.05)
    assert row.active_kcal == 100.0
    assert row.basal_kcal == 200.0
    assert row.body_fat_pct == 22.5  # bleibt Prozent, keine Umrechnung
    assert row.lean_mass_kg == 54.6
    assert row.steps == 1234
    assert row.resting_hr == 55
    assert row.hrv_ms == 48.5
    assert row.sleep_h == 7.25  # Asleep hat Vorrang vor Total
    assert row.weight_kg == 70.5


def test_sleep_falls_back_to_total(tmp_path):
    text = f"{DAILY_HEADER}\n2030-01-02 00:00:00,,,,,,,,,,6.5\n"
    result = import_hae(_write(tmp_path / "HealthAutoExport-x.csv", text))
    assert result.daily[0].sleep_h == 6.5


def test_bom_missing_columns_and_empty_cells(tmp_path):
    text = (
        "Date/Time,Weight (kg),Step Count (count)\n"
        "2030-01-02 00:00:00,,500\n"
        "2030-01-03 00:00:00,70.0,\n"
    )
    path = _write(tmp_path / "HealthAutoExport-x.csv", text, encoding="utf-8-sig")
    result = import_hae(path)
    first, second = result.daily
    assert first.weight_kg is None and first.steps == 500
    assert second.weight_kg == 70.0 and second.steps is None
    assert first.active_kcal is None and first.sleep_h is None and first.body_fat_pct is None


def test_unparsable_numbers_and_missing_dates_are_skipped(tmp_path):
    text = (
        "Date/Time,Weight (kg),Step Count (count)\n"
        "2030-01-02 00:00:00,abc,100\n"
        ",70.0,200\n"
        "kaputt,70.0,300\n"
        "2030-01-03 00:00:00,nan,400\n"
    )
    result = import_hae(_write(tmp_path / "HealthAutoExport-x.csv", text))
    assert [r.day for r in result.daily] == [date(2030, 1, 2), date(2030, 1, 3)]
    assert [r.weight_kg for r in result.daily] == [None, None]
    assert [r.steps for r in result.daily] == [100, 400]
    assert result.stats["skipped_rows"] == 2
    assert result.stats["daily_rows"] == 2


def test_weight_placeholder_is_removed(tmp_path):
    start = date(2030, 1, 1)
    real = [70.0, 69.8, 69.9, 69.6, 69.5, 69.7, 69.4, 69.3, 69.2, 69.1]
    lines = [DAILY_HEADER.split(",")[0] + ",Weight (kg)"]
    expected_none = 0
    for i in range(20):
        weight = 81.0 if i % 2 == 0 else real[i // 2]
        expected_none += weight == 81.0
        lines.append(f"{start + timedelta(days=i)} 00:00:00,{weight}")
    result = import_hae(_write(tmp_path / "HealthAutoExport-x.csv", "\n".join(lines) + "\n"))
    assert 81.0 in result.weight_report.placeholders
    assert result.weight_report.raw == 20
    assert result.weight_report.kept == 10
    assert sum(r.weight_kg is None for r in result.daily) == expected_none
    assert all(r.weight_kg != 81.0 for r in result.daily)
    assert len(result.daily) == 20  # Tage bleiben erhalten, nur das Gewicht entfällt


def test_workouts_parsing(tmp_path):
    text = (
        f"{WORKOUT_HEADER}\n"
        "Laufen,2030-02-03 09:17,2030-02-03 09:53,00:36:10,2092,170,150,5.2\n"
        "Krafttraining,2030-02-01 18:00,2030-02-01 19:00,01:00:00,,,,\n"
        "Kaputt,nicht-datum,x,00:10:00,100,,,\n"
        "Yoga,2030-02-04 07:00,2030-02-04 07:20,xx,,,,\n"
    )
    result = import_hae(_write(tmp_path / "Workouts-x.csv", text))
    assert result.daily == []
    assert result.stats["skipped_rows"] == 1
    strength, run, yoga = result.workouts  # nach Start sortiert
    assert run.type == "Laufen"
    assert run.start == datetime(2030, 2, 3, 9, 17)
    assert run.duration_min == 36.2  # 36 min 10 s
    assert run.active_kcal == pytest.approx(2092 / KJ_PER_KCAL, abs=0.05)
    assert (run.avg_hr, run.max_hr, run.distance_km) == (150, 170, 5.2)
    assert strength.duration_min == 60.0
    assert strength.active_kcal is None and strength.avg_hr is None and strength.distance_km is None
    assert yoga.duration_min == 0.0


def test_zip_reads_only_needed_members(tmp_path, monkeypatch):
    daily = f"{DAILY_HEADER}\n2030-03-01 00:00:00,418.4,,70.0,,,1000,,,,\n"
    workouts = f"{WORKOUT_HEADER}\nRadfahren,2030-03-01 10:00,2030-03-01 11:00,01:00:00,836.8,,,20\n"
    path = _zip(
        tmp_path / "export.zip",
        {
            "HealthAutoExport-2030.csv": daily,
            "Workouts-2030.csv": workouts,
            "Workout-Dateien/Radfahren-2030-03-01.csv": "Date/Time,Weight (kg)\n2030-03-01 00:00:00,99\n",
            "Workout-Dateien/Radfahren-2030-03-01.gpx": "<gpx>nicht öffnen</gpx>",
            "readme.txt": "unwichtig",
        },
    )
    opened: list[str] = []
    original_open = zipfile.ZipFile.open

    def spy(self, name, *args, **kwargs):
        opened.append(name.filename if hasattr(name, "filename") else name)
        return original_open(self, name, *args, **kwargs)

    monkeypatch.setattr(zipfile.ZipFile, "open", spy)
    result = import_hae(path)

    assert sorted(opened) == ["HealthAutoExport-2030.csv", "Workouts-2030.csv"]
    assert result.stats["files_read"] == 2
    assert len(result.daily) == 1 and result.daily[0].weight_kg == 70.0
    assert len(result.workouts) == 1 and result.workouts[0].distance_km == 20


def test_single_csv_detected_by_header(tmp_path):
    daily = _write(tmp_path / "export.csv", f"{DAILY_HEADER}\n2030-04-01 00:00:00,,,,,,10,,,,\n")
    assert import_hae(daily).daily[0].steps == 10
    workouts = _write(tmp_path / "andere.csv", f"{WORKOUT_HEADER}\nGehen,2030-04-01 10:00,x,00:30:00,,,,\n")
    result = import_hae(workouts)
    assert len(result.workouts) == 1 and result.daily == []


def test_duplicate_days_are_merged_and_sorted(tmp_path):
    path = _zip(
        tmp_path / "e.zip",
        {
            "HealthAutoExport-b.csv": "Date/Time,Step Count (count)\n2030-05-02 00:00:00,20\n",
            "HealthAutoExport-a.csv": (
                "Date/Time,Step Count (count),Weight (kg)\n"
                "2030-05-03 00:00:00,30,\n2030-05-02 00:00:00,,70.0\n"
            ),
        },
    )
    result = import_hae(path)
    assert [r.day for r in result.daily] == [date(2030, 5, 2), date(2030, 5, 3)]
    assert result.daily[0].steps == 20 and result.daily[0].weight_kg == 70.0
    assert result.stats["date_from"] == date(2030, 5, 2)
    assert result.stats["date_to"] == date(2030, 5, 3)


def test_progress_callback(tmp_path):
    path = _zip(
        tmp_path / "e.zip",
        {
            "HealthAutoExport-a.csv": f"{DAILY_HEADER}\n2030-06-01 00:00:00,,,,,,5,,,,\n",
            "Workouts-a.csv": f"{WORKOUT_HEADER}\n",
        },
    )
    calls: list[tuple[float, str]] = []
    import_hae(path, lambda fraction, message: calls.append((fraction, message)))
    assert len(calls) >= 3
    fractions = [f for f, _ in calls]
    assert fractions == sorted(fractions)
    assert all(0.0 <= f <= 1.0 for f in fractions)
    assert fractions[-1] == 1.0
    assert all(isinstance(m, str) and m for _, m in calls)


def test_empty_file_and_empty_zip(tmp_path):
    result = import_hae(_write(tmp_path / "leer.csv", ""))
    assert result.daily == [] and result.workouts == []
    assert result.stats["daily_rows"] == 0
    assert result.stats["date_from"] is None and result.stats["date_to"] is None
    assert result.weight_report.raw == 0

    empty_zip = _zip(tmp_path / "leer.zip", {"unrelated.txt": "x"})
    result = import_hae(empty_zip)
    assert result.stats["files_read"] == 0 and result.daily == []


def test_stats_keys(tmp_path):
    result = import_hae(_write(tmp_path / "HealthAutoExport-x.csv", f"{DAILY_HEADER}\n"))
    assert {
        "files_read",
        "daily_rows",
        "workout_rows",
        "skipped_rows",
        "date_from",
        "date_to",
        "seconds",
    } <= set(result.stats)


def test_height_goes_into_profile(tmp_path):
    csv_text = (
        "Date/Time,Height (m),Weight (kg)\n"
        "2026-01-01 00:00:00,1.80,80\n"
        "2026-01-02 00:00:00,,80\n"
        "2026-01-03 00:00:00,1.82,80\n"
        "2026-01-04 00:00:00,9.0,80\n"  # unplausibel
    )
    f = tmp_path / "HealthAutoExport-2026.csv"
    f.write_text(csv_text, encoding="utf-8")
    assert import_hae(f).profile == {"height_cm": 182.0}


def test_no_height_gives_empty_profile(tmp_path):
    f = tmp_path / "HealthAutoExport-2026.csv"
    f.write_text("Date/Time,Weight (kg)\n2026-01-01 00:00:00,80\n", encoding="utf-8")
    assert import_hae(f).profile == {}
