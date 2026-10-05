# Phase 1: Gesundheitsdaten, Profile, Ziele (Spezifikation)

Gilt für `backend/`. Sprache der Oberfläche und Meldungen: Deutsch. Code und Bezeichner: Englisch.
Leitprinzip (PLAN.md, Abschnitt 1): **Nichts Persönliches im Code.** Grenzwerte, Regeln, Ziele, Supplemente, Trainingsplan sind Daten in der Datenbank, pro Person pflegbar. Der Code enthält nur Rechenlogik und **sichere Standardwerte** (`app/calc/defaults.py`).

## 1. Verzeichnislayout

```
backend/app/
  config.py            (vorhanden)
  db.py                Engine, Session, get_session (Fundament, fertig)
  models.py            alle Tabellen (Fundament, fertig)
  main.py              App, Router einbinden
  auth.py              Bearer-Token je Person
  cli.py               Verwaltung (create-person, rotate-token)
  importers/
    types.py           gemeinsame Datentypen (Fundament, fertig)
    cleaning.py        Platzhalter/Ausreißer filtern (Fundament, fertig)
    hae.py             Health Auto Export (ZIP/CSV)
    apple_health.py    Apple-Health-export.xml (Streaming)
    lab_pdf.py         Laborbefund-PDF (Labor Staber)
  calc/
    defaults.py        sichere Standardwerte
    types.py           Eingabe-/Ausgabetypen der Rechner
    energy.py          BMR, TDEE aus Gerätedaten, adaptive Kalibrierung
    macros.py          Ziele pro Tag und Woche, Makros
    safety.py          Sicherheitsgrenzen und Warnungen
    slots.py           Verteilung auf Mahlzeiten-Slots
  services/
    ingest.py          schreibt Importergebnisse in die DB (Upsert, Dedupe)
    targets.py         verbindet DB-Daten mit calc/ zu Tageszielen
  api/
    deps.py, schemas.py, routers (me, settings, goals, supplements, rules, training,
    imports, health, labs, targets, dashboard)
backend/tests/         pytest, SQLite in-memory, **nur synthetische Daten**
```

## 2. Harte Regeln für alle Beteiligten

1. **Keine echten Gesundheitsdaten im Repo.** Tests nutzen ausschließlich selbst erzeugte, erfundene Daten. Der Ordner `Health Daten/` darf **nie** committet, kopiert oder in Testdateien verwendet werden. Für eine lokale Plausibilitätsprüfung darf ein Importer einmal gegen die echten Dateien laufen (Pfade siehe `docs/SPIKES.md`). Berichtet werden dabei **nur Aggregate** (Anzahl Zeilen, Zeitraum, Laufzeit, Speicher), keine Einzelwerte.
2. **Keine Zugangsdaten** in Code, Tests oder Doku. Tokens nur als Hash (SHA-256) speichern.
3. Tests laufen ohne Docker und ohne Postgres (SQLite in-memory). Migrationen werden gegen Postgres geprüft (macht der Hauptagent).
4. Jede Datei hat Tests. `pytest backend -q` und `ruff check backend` müssen grün sein.
5. Nur die dir zugewiesenen Dateien ändern. Gemeinsame Dateien (`models.py`, `importers/types.py`, `importers/cleaning.py`, `pyproject.toml`, `main.py` außer E) gehören dem Hauptagenten. Brauchst du eine Änderung dort, beschreibe sie im Abschlussbericht.
6. Kein `git add`/`commit`. Der Hauptagent committet.
7. Typen: Python 3.12, `from __future__ import annotations` nicht nötig, moderne Union-Syntax (`X | None`).
8. Zahlen und Einheiten: kcal (nicht kJ), kg, cm, Prozent als 0–100, Datum als `date`, Zeitpunkte als naive Ortszeit `datetime` (Europe/Berlin).

## 3. Importer-Vertrag (`importers/types.py`)

Importer sind **reine Funktionen ohne Datenbank**: Pfad rein, Datenklassen raus. Fortschritt optional über `progress(fraction: float, message: str)`.

- `hae.import_hae(path: Path, progress=None) -> HealthImport` (ZIP oder einzelne CSV; Tages-CSV `HealthAutoExport-*.csv`, Workout-CSV `Workouts-*.csv`, kJ → kcal)
- `apple_health.import_apple_health(path: Path, progress=None) -> HealthImport` (Streaming, konstanter Speicher, Ziel: < 400 MB bei 1,3 GB XML)
- `lab_pdf.import_lab_pdf(path: Path) -> LabReport`, außerdem `lab_pdf.parse_lab_text(text: str) -> LabReport` (testbar ohne PDF)

Beide Health-Importer bereinigen Gewichte mit `cleaning.clean_weights` und liefern den Bericht in `HealthImport.weight_report` mit.

## 4. Datenbank (`models.py`)

Tabellen: `person`, `person_settings` (JSON, validiert durch `PersonSettings` aus `calc/types.py`), `goal_profile` (versioniert), `health_daily`, `workout`, `lab_report`, `lab_result`, `lab_rule`, `supplement`, `nutrient_rule`, `training_plan_item`, `import_job`. Details im Code. Eindeutigkeiten: `health_daily (person_id, date, source)`, `workout (person_id, start, type, source)`, `lab_report (person_id, order_no)`, `lab_result (report_id, analyte, unit)`.

**Quellenpriorität pro Tag:** Gibt es mehrere Quellen für denselben Tag, gewinnt je Feld die Quelle mit der höchsten Priorität (`person_settings.source_priority`, Default `["apple_health_xml", "hae_zip"]`), fehlende Felder werden aus der anderen Quelle ergänzt. Das macht `services/targets.py`/Abfragen beim Lesen, nicht beim Schreiben.

## 5. Rechner (`calc/`, reine Funktionen, keine DB)

Alle Funktionen bekommen ihre Parameter als Argument. Standardwerte kommen aus `defaults.py` und werden von den Personeneinstellungen überschrieben.

### 5.1 `energy.py`
- `bmr_mifflin(weight_kg, height_cm, age_years, sex) -> float` (`sex`: `"m"`/`"f"`)
- `bmr_katch_mcardle(lean_mass_kg) -> float`
- `device_tdee(daily: list[DayEnergy], window_days=28) -> DeviceTdee` (Ø `basal_kcal + active_kcal` über die letzten Tage mit Daten; `n_days`, `coverage`)
- `weight_trend(points: list[tuple[date, float]], window_days=28) -> WeightTrend` (geglättet; Steigung kg/Tag per robuster Regression, `n_points`, `last_smoothed_kg`)
- `calibrate_tdee(device: DeviceTdee, trend: WeightTrend, reported_intake_kcal: float | None, *, kcal_per_kg=7700, min_points=6, clamp=(0.75, 1.15), max_blend=0.7) -> TdeeEstimate`
  - Energiebilanz: `implied_tdee = intake − slope_kg_per_day × kcal_per_kg`
  - `confidence` aus Anzahl Messpunkte, Spanne und Streuung (0–1). `blended = w·implied + (1−w)·device`, `w = min(max_blend, confidence)`. Ergebnis auf `device × clamp` begrenzen.
  - Ohne `reported_intake_kcal` oder zu wenige Punkte: `blended = device`, `method = "device"`.
  - Zurück: `TdeeEstimate(tdee_kcal, device_kcal, implied_kcal|None, confidence, method, notes: list[str])`

### 5.2 `macros.py`
- `daily_target(profile, goal, tdee_kcal, settings, day_type="easy") -> DayTarget` mit kcal, protein_g, fat_g, carb_g
- `weekly_targets(profile, goal, tdee_kcal, settings, week_day_types: dict[int, str]) -> list[DayTarget]`: verteilt die **Wochenenergie** über Tage nach `settings.day_type_weights` (Default rest 0.95, easy 1.0, moderate 1.03, hard 1.08, auf Mittel 1 normalisiert). Die Wochensumme bleibt gleich.
- Defizit: `rate_kg_per_week × kcal_per_kg / 7` (oder `kcal_modifier_pct`), nie über die Sicherheitsgrenze hinaus.
- Protein in g/kg Körpergewicht (Default im Defizit 2.0, sonst 1.6), Fett als Anteil der Kalorien (Default 30 %), Rest Kohlenhydrate.

### 5.3 `safety.py`
- `apply_safety_limits(target, profile, limits, current) -> SafetyResult(target, warnings, hard_blocks)`
- Grenzen aus `PersonSettings`/Defaults: kcal-Untergrenze (Default `max(1500 m / 1200 f, 1.0 × BMR)`), Protein-Untergrenze (Default 1.2 g/kg), maximales Tempo (Default `min(1.0 kg, 1.0 % KG)` pro Woche), `weight_floor_kg` und `bf_floor_pct` (beide Default `None`, für Männer/Frauen sind Empfehlungen 10 % / 18 % als **Hinweis**, nicht als Zwang).
- **Tempo-Auslauf:** Nähert sich Gewicht oder Körperfett der Grenze (Gewicht innerhalb 3 kg, Körperfett innerhalb 2 Prozentpunkte), sinkt das Tempo linear auf 0.
- **Plausibilitätshinweis:** Liegt `weight_floor_kg` unter `lean_mass_kg × 1.05` (oder ergibt sich daraus ein Körperfett unter 5 %), wird eine **nicht blockierende** Warnung erzeugt. Die Grenze wird trotzdem angewendet.
- Warnungen sind deutsche, verständliche Sätze mit Code (`code: str`, `severity: info|warn|block`).

### 5.4 `slots.py`
- `distribute_to_slots(target, shares: dict[str, float]) -> dict[str, SlotTarget]` (Anteile werden normalisiert, Summe bleibt exakt gleich dem Tagesziel; Rundung auf 1 kcal/0,1 g mit Restausgleich im größten Slot).
- Check für Einzelmahlzeiten: `single_meal_check(slot_target, limits) -> list[Warning]` (kcal und Volumen über Obergrenze, Protein-Mindestmenge).

## 6. API (`api/`)

Alle Endpunkte unter `/api`, Authentifizierung per `Authorization: Bearer <token>`. Jede Person sieht und ändert **nur ihre eigenen** Daten (`/api/me/...`). Fehlermeldungen auf Deutsch. OpenAPI wird automatisch erzeugt (`/docs`).

| Bereich | Endpunkte |
|---|---|
| Profil | `GET/PATCH /me` |
| Einstellungen | `GET/PUT /me/settings` (validiert gegen `PersonSettings`, fehlende Felder = Defaults) |
| Ziele | `GET /me/goals`, `POST /me/goals` (neue Version), `GET /me/goals/active?on=` |
| Supplemente | CRUD `/me/supplements` |
| Ernährungsregeln | CRUD `/me/nutrient-rules` (inkl. `doctor_confirmed`, `suggested_by_app`) |
| Trainingsplan | CRUD `/me/training-plan` |
| Laborregeln | CRUD `/me/lab-rules` |
| Importe | `POST /me/imports/hae`, `POST /me/imports/apple-health`, `POST /me/imports/labs` (Upload gestreamt auf Platte, Verarbeitung im Hintergrund), `GET /me/imports`, `GET /me/imports/{id}` |
| Daten | `GET /me/health/daily?from&to`, `GET /me/workouts?from&to`, `GET /me/labs` (Berichte mit Ergebnissen) |
| Ziele berechnen | `GET /me/targets?date=&shares=` → Tagesziel, Slot-Ziele, TDEE-Details (`device`, `implied`, `confidence`), Warnungen |
| Übersicht | `GET /me/dashboard` (Gewichtstrend, Ø Energie, Workouts pro Woche, letzte Importe, offene Warnungen) |

## 7. Authentifizierung und CLI

- Token: `secrets.token_urlsafe(32)`, gespeichert wird nur `sha256(token)`. Anzeige **einmalig** bei der Erstellung.
- `python -m app.cli create-person --name … --sex m|f --birth YYYY-MM-DD [--height-cm N]` und `python -m app.cli rotate-token --name …`. Namen sind eindeutig.
- Vergleich der Hashes mit `secrets.compare_digest`. Kein Logging von Tokens.

## 8. Importe in die Datenbank (`services/ingest.py`)

- Upsert nach den Eindeutigkeiten aus Abschnitt 4, **idempotent** (zweimal importieren ändert nichts).
- `import_job` mit Status `queued|running|done|failed`, `stats` (Zeilen neu/aktualisiert/übersprungen, Zeitraum, Gewicht: Platzhalter/Ausreißer), Fehlermeldung.
- Beim Gesundheitsimport werden fehlende Profilfelder ergänzt (Größe aus Apple Health), vorhandene nie überschrieben.
- Beim Laborimport wird das **Geburtsdatum** des Berichts mit `person.birth_date` verglichen. Weicht es ab, wird der Import mit klarer Meldung abgelehnt. **Der Patientenname wird nicht gespeichert.**
- Teilbefunde: Ergebnisse mit `pending=True`. Ein späterer Bericht mit derselben `order_no` aktualisiert vorhandene Ergebnisse, ersetzt `pending` durch Werte und ändert `report_type`.

## 9. Abnahme Phase 1 (Backend)

- Alle Tests grün, `ruff` sauber.
- Beide echten Exporte und beide Laborbefunde lassen sich lokal importieren (nur Aggregate berichten).
- `GET /me/targets` liefert für beide Personen plausible Werte, Warnungen erscheinen bei unplausiblen Grenzen.
- Konfiguration (Einstellungen, Ziele, Supplemente, Regeln, Trainingsplan) ist komplett per API änderbar.
- Docker-Image baut, Migration läuft gegen Postgres.

## 10. Ergebnis Phase 1a (Backend) – Stand 2026-10-05

**Abgenommen.** 330 Tests grün, `ruff` sauber. Ende-zu-Ende mit den echten Dateien über die HTTP-Schnittstelle, sowohl gegen SQLite als auch gegen Postgres 16 im Docker-Container (Datenbank danach vollständig entfernt):

| Prüfung | Ergebnis |
|---|---|
| HAE-ZIP (Christian) importieren | 0,2 s, 367 Tage, 586 Workouts, Körpergröße übernommen |
| Apple-Health-XML (1,3 GB, Liesa) importieren | ca. 28 s, 809 Tage, 2.177 Workouts, Größe übernommen, Streaming mit ca. 30 MB Speicher |
| Laborbefunde beider Personen | 56 und 55 Werte, 9 ausstehend beim Teilbefund |
| Befund mit falschem Geburtsdatum | abgelehnt, deutsche Meldung, nichts gespeichert |
| Zielwerte `/me/targets` | beide Personen plausibel, Warnungen wie erwartet (veraltetes Gewicht, unplausible Gewichtsgrenze) |
| Zugriff ohne Token / auf fremde Daten | 401 bzw. 404 |
| Migration `0001` auf Postgres | hoch, runter, hoch, `alembic check` ohne Abweichung |

**Abweichungen von der ursprünglichen Spezifikation**
- `PersonSettings.slot_shares_weekend` (neu): Slot-Anteile für Samstag/Sonntag, falls sie von Montag bis Freitag abweichen.
- `PersonSettings.source_priority` Standard jetzt `["manual", "apple_health_xml", "hae_zip"]`; neuer Endpunkt `POST /api/me/health/manual` für Gewicht/Körperfett von Hand (Quelle `manual`, hat Vorrang). Grund: Bei Christian liefert die Waage kaum echte Gewichte.
- `GET /me/dashboard` enthält keine Warnungen; sie kommen aus `/me/targets`.
- `GET /me/labs/latest` gruppiert nach **Analyt und Einheit** (HbA1c in % und mmol/mol bleiben getrennt).
- HAE-Importer übernimmt `Height (m)` ins Profil.
- Apple-Health-Importer verhindert **Doppelzählung über mehrere Quellen** (iPhone und Watch): je Tag und Typ zählt die Quelle mit der größten Summe. Das senkte die Schrittzahl in einem Test von ca. 19.800 auf ca. 12.900 pro Tag (ca. 35 % weniger). Energiewerte änderten sich kaum.
- Ingest kürzt Texte auf die Spaltenlänge (Postgres lehnt zu lange Werte ab, SQLite nicht; gefunden durch den Postgres-Test).
- Importstatistiken werden JSON-tauglich gemacht (Datum → ISO-Text).

**Bekannte Einschränkungen**
- Ein Upload über 1 GB wird von Starlette zuerst in eine eigene Temp-Datei geschrieben und dann kopiert (doppelt auf der Platte). Ein früher Abbruch bei zu großen Dateien bräuchte eine Prüfung von `Content-Length` vor dem Parsen.
- `single_meal_check` prüft Energie und Protein, aber kein Volumen (dafür fehlen Daten bis zur Rezeptbibliothek).
- Zielwerte nutzen die Trainingsplan-Belastung nur, wenn ein Trainingsplan gepflegt ist (sonst gilt „easy“ bzw. „rest“).
- Es gibt noch keine Web-Oberfläche. Bis Phase 1b dient `/docs` (OpenAPI) als Konfigurationsoberfläche, Anmeldung mit dem Token aus `python -m app.cli`.

