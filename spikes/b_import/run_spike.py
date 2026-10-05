"""Führt beide Importer gegen die echten Dateien aus und druckt eine Kurzbilanz.

Ausgabe (JSON) landet in spikes/b_import/out/ (gitignored, enthält echte Daten).
Aufruf:  .venv/Scripts/python spikes/b_import/run_spike.py
"""
import json
import statistics
import sys
import time
from pathlib import Path

import psutil

sys.path.insert(0, str(Path(__file__).parent))
from importers import import_apple_health_xml, import_hae_zip  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "Health Daten"
OUT = Path(__file__).parent / "out"
OUT.mkdir(exist_ok=True)


def summarize(name: str, res: dict, secs: float, peak_mb: float) -> None:
    daily = res["daily"]
    print(f"\n=== {name}  ({secs:.1f} s, Peak-RAM ≈ {peak_mb:.0f} MB)")
    print(f"Tage: {len(daily)}  {daily[0]['date']} .. {daily[-1]['date']}   Workouts: {len(res['workouts'])}")
    wr = res["weight_report"]
    print(f"Gewicht: roh {wr['raw']} → bereinigt {wr['kept']}; Platzhalter {wr['placeholders']}; "
          f"Ausreißer {len(wr['outliers'])} {wr['outliers'][:4]}")
    w = [(r["date"], r["weight_kg"]) for r in daily if r.get("weight_kg")]
    if w:
        print(f"  letztes Gewicht: {w[-1][0]} {w[-1][1]:.1f} kg; Min {min(x for _, x in w):.1f}, Max {max(x for _, x in w):.1f}")
    cut = sorted(r["date"] for r in daily)[-90:][0]
    recent = [r for r in daily if r["date"] >= cut]
    for key in ("active_kcal", "basal_kcal", "steps", "resting_hr", "hrv_ms", "sleep_h", "body_fat_pct"):
        v = [r[key] for r in recent if r.get(key) is not None]
        if v:
            print(f"  {key:<13} Ø letzte 90 Tage: {statistics.mean(v):8.1f}  (n={len(v)})")
    act = [r["active_kcal"] for r in recent if r.get("active_kcal")]
    bas = [r["basal_kcal"] for r in recent if r.get("basal_kcal")]
    if act and bas:
        print(f"  Gerätebedarf (Aktiv + Ruhe): ≈ {statistics.mean(act) + statistics.mean(bas):.0f} kcal/Tag")


def run(name: str, fn, path: Path) -> dict:
    proc = psutil.Process()
    t0 = time.time()
    peak = 0.0
    # einfacher Peak-Sampler: vor/nach reicht für den Streaming-Nachweis nur grob,
    # deshalb zusätzlich ein Thread, der alle 0,5 s misst
    import threading
    stop = threading.Event()

    def sample():
        nonlocal peak
        while not stop.is_set():
            peak = max(peak, proc.memory_info().rss / 1e6)
            time.sleep(0.5)

    th = threading.Thread(target=sample, daemon=True)
    th.start()
    res = fn(path)
    stop.set()
    th.join()
    peak = max(peak, proc.memory_info().rss / 1e6)
    summarize(name, res, time.time() - t0, peak)
    (OUT / f"{name}.json").write_text(json.dumps(res, ensure_ascii=False))
    return res


if __name__ == "__main__":
    run("christian_hae", import_hae_zip, DATA / "Christian" / "HealthAutoExport_20261002211844.zip")
    run("liesa_apple_xml", import_apple_health_xml,
        DATA / "Liesa" / "export" / "apple_health_export" / "export.xml")
