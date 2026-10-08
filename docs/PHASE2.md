# Phase 2: Rezeptbibliothek, Nährwerte, Komponenten (Spezifikation)

Gilt für `backend/` und `web/`. Sprache der Oberfläche und Meldungen: Deutsch. Code und Bezeichner: Englisch.
Es gelten die harten Regeln aus `docs/PHASE1.md` (Abschnitt 2) unverändert: keine echten Gesundheitsdaten im Repo, keine Zugangsdaten, Tests ohne Docker (SQLite in-memory), nur zugewiesene Dateien ändern, kein Commit durch Subagenten.

## 1. Ziel und Abnahme

Rezepte (eigene Favoriten und Import per URL) bekommen **berechnete Nährwerte aus normalisierten Zutaten**. Pro Rezept und Person sieht man, **wie gut eine Portion ins Tagesziel passt**. Christians Frühstück wird als **Komponenten-Baukasten** abgebildet.

Abnahme (PLAN.md): 30–50 Rezepte und der Frühstücks-Baukasten mit gültigen Nährwerten. Zusätzlich: Ansicht „Passt ins Tagesziel“ (Abschnitt 6).

## 2. Entscheidungen

| Thema | Entscheidung | Begründung |
|---|---|---|
| Nährwertdatenbank | **BLS 4.0** (Bundeslebensmittelschlüssel, Max Rubner-Institut) als Hauptquelle | Seit 16.12.2025 kostenlos, ca. 7.140 Lebensmittel, 138 Nährstoffe, deutsche Bezeichnungen, deckt Küchenzutaten ab. Datei wird **nicht ins Repo** eingecheckt, sondern lokal importiert (Pfad per CLI). |
| Ergänzung | Einträge für Markenprodukte (z. B. Lidl-Eigenmarken, Skyr) **manuell oder per Open Food Facts** anlegen (`source = "manual"`/`"off"`) | BLS kennt keine Marken. Open Food Facts nur auf Abruf im Editor, kein Massen-Crawl. |
| USDA | **nicht verwendet** | Englisch, amerikanische Lebensmittel, bringt gegenüber BLS keinen Vorteil. |
| Zutaten-Normalisierung | **Regeln und Synonymtabelle** (kein LLM nötig). Nicht erkannte Zutaten landen in einer Prüfliste und werden einmal von Hand zugeordnet, die Zuordnung wird als Synonym gespeichert. | Keine API-Schlüssel nötig, Ergebnis nachvollziehbar, Qualität wächst mit der Nutzung. Claude-Unterstützung bleibt eine spätere Option. |
| Nährwerte der Rezeptseiten | werden **ignoriert**, außer als Plausibilitätsvergleich (Abweichung > 25 % → Hinweis) | lückenhaft (Spike d). |

## 3. Datenbank (Ergänzung zu `models.py`, Hauptagent)

- `ingredient`: `id`, `name` (normalisiert), `category`, `source` (`bls`|`off`|`manual`), `source_code`, `kcal_100`, `protein_100`, `fat_100`, `carb_100`, `fiber_100`, `salt_100` (g), `micros` (JSON: Schlüssel → Menge je 100 g, u. a. `zinc_mg`, `iron_mg`, `potassium_mg`, `magnesium_mg`, `vit_c_mg`, `omega3_g`), `density_g_per_ml` (optional), `piece_g` (optional, Gewicht eines Stücks), `is_fish`, `is_potassium_salt` (Schalter für Ernährungsregeln), `shelf_days` (optional).
- `ingredient_synonym`: `alias` (eindeutig, klein geschrieben), `ingredient_id`.
- `recipe`: `id`, `title`, `source_url`, `source_site`, `servings`, `prep_min`, `cook_min`, `instructions` (Text), `image_url` (optional, nur Link), `favorite`, `notes`, `status` (`draft`|`ready`|`needs_review`), `created_at`.
- `recipe_ingredient`: `recipe_id`, `position`, `raw_text`, `quantity`, `unit`, `grams` (berechnet), `ingredient_id` (nullable bis zugeordnet), `optional` (bool).
- `recipe_tag`: `recipe_id`, `slot_types` (JSON-Liste: breakfast, lunch, dinner, snack), `cuisine`, `main_ingredient`, `batch_cookable`, `transportable`, `warm`, `shelf_days`, `season`.
- `recipe_rating`: `recipe_id`, `person_id`, `rating` (1–5), `updated_at`.
- `ingredient_preference`: `person_id`, `ingredient_id`, `level` (`like`|`dislike`|`never`).
- `component`: `id`, `name`, `kind` (z. B. `protein`, `carb`, `dairy`, `fruit`, `veg`), `ingredient_id`, `min_g`, `max_g`, `step_g`, `typical_g`, `weekend_fixed` (bool).
- `component_variant`: `component_id`, `name`, `ingredient_id`, `grams_per_unit` (z. B. 1 Ei = 60 g).

Nährwerte pro Rezept werden **nicht gespeichert**, sondern bei Bedarf berechnet (billig, immer aktuell).

## 4. Reine Rechenlogik (`calc/`, keine DB)

### 4.1 `calc/ingredients.py`
- `parse_ingredient_line(text: str) -> ParsedIngredient` (Menge, Einheit, Name, Zusatz, optional). Muss können: `200 g Mehl`, `1 Zwiebel`, `½ Bund Petersilie`, `2 EL Olivenöl`, `500 ml Milch`, `1 Prise Salz`, `Salz und Pfeffer`, `3-4 Karotten` (Mittelwert), Brüche und Dezimalkomma, `1 Einheit Suppengrün: Karotte, Sellerie` (Zusatz nach Doppelpunkt ignorieren), `ca.`/`etwa`.
- `to_grams(quantity, unit, ingredient) -> float | None`: g, kg, ml, l (mit `density_g_per_ml`, sonst 1,0), EL (15 ml), TL (5 ml), Prise (0,4 g), Stück/Zehe/Bund/Dose/Packung über `piece_g` oder eine Tabelle typischer Gewichte in `defaults`. Unbekannt → `None` (Rezept bekommt Status `needs_review`).
- `normalize_name(text) -> str` (Kleinschreibung, Zusätze wie „frisch“, „gehackt“, „große“ entfernen, Plural vereinfachen) und `match_ingredient(name, catalog) -> list[Match]` (Synonym zuerst, dann Fuzzy-Treffer mit Score, `rapidfuzz`).

### 4.2 `calc/nutrition.py`
- `recipe_nutrition(lines: list[LineNutrition], servings: float) -> RecipeNutrition`: Summe und pro Portion für kcal, Protein, Fett, Kohlenhydrate, Ballaststoffe, Salz, Mikros. Dazu `total_weight_g`, `energy_density_kcal_per_100g` und `coverage` (Anteil der Zutaten mit gültigen Werten, 0–1).
- `satiety_score(nutrition, *, warm: bool, weights) -> SatietyScore`: 0–100 aus niedriger Energiedichte, hohem Gewicht/Volumen der Portion, Protein je 100 kcal, Ballaststoffe je 100 kcal und warm/Suppe als Bonus. Gewichte und Schwellen stehen in `defaults` (einstellbar).
- `fit_to_target(nutrition_per_serving, target: SlotTarget, *, min_factor=0.5, max_factor=2.0) -> SlotFit`: siehe Abschnitt 6.
- `component_meal(components: list[ComponentChoice]) -> RecipeNutrition`: Frühstück aus Komponenten und Mengen, gleiche Ausgabe wie ein Rezept (inkl. Salz).

## 5. Importer und Services

- `importers/recipe_web.py`: `import_recipe_url(url) -> ImportedRecipe` mit `recipe-scrapers` (höflich, eigener User-Agent, `robots.txt` beachten, Timeout). Rein ohne DB, Test mit gespeicherten HTML-Beispielen (selbst geschrieben, kein Kopieren fremder Seiten ins Repo).
- `importers/bls.py`: liest die lokal heruntergeladene BLS-Datei (Format wird festgelegt, sobald die Datei vorliegt) und liefert `list[IngredientRecord]` mit Mapping der BLS-Schlüssel auf unsere Felder (Energie in kcal, nicht kJ).
- `services/recipes.py`: Import in die DB, Zutatenzeilen parsen und zuordnen, Status setzen, Nährwerte berechnen.
- `services/catalog.py`: Zutaten suchen, Synonyme pflegen, BLS-Import (idempotent per `source_code`).
- CLI: `python -m app.cli import-bls <Pfad>`, `python -m app.cli import-recipe <URL>`.

## 6. „Passt ins Tagesziel“ (Kernfunktion der Rezeptansicht)

Für ein Rezept, eine Person, einen Wochentag und einen Slot (Frühstück/Mittag/Abendessen/Snack):
1. Slot-Ziel aus dem vorhandenen Rechner (`services/targets.py`, `calc/slots.py`), also kcal, Protein, Fett, Kohlenhydrate.
2. **Portionsfaktor** = Ziel-kcal / kcal je Portion, begrenzt auf `[min_factor, max_factor]` (einstellbar).
3. Ergebnis `SlotFit`: Faktor, resultierende Menge in g, kcal und Makros der skalierten Portion, **Abweichung je Makro in % vom Slot-Ziel**, `fit_score` (0–100, gewichtet, Protein stärker als Fett/Kohlenhydrate), Hinweise (z. B. „Portion wäre 1,8-fach: sehr groß“, „Protein 22 g unter Ziel“).
4. Bei Christians Frühstück zusätzlich: Gewicht und Volumen der Portion gegen `single_meal_max_kcal` und realistische Mengen.
5. API: `GET /api/recipes/{id}/fit?person_id=&date=&slot=` und `GET /api/recipes?fit_for=<person>&date=&slot=` (Liste mit Fit-Score, sortierbar).

Das ist **keine Planung**, nur Anzeige und Bewertung. Der Planer (Phase 3) nutzt dieselbe Funktion.

## 7. API (`api/`)

Rezepte: Liste mit Filtern (Slot, Tag, Favorit, Status, Suche, Fit), Detail (mit Nährwerten, Zutaten, Fit), Anlegen/Bearbeiten (manuell), Import per URL (Vorschau vor dem Speichern), Löschen, Bewertung pro Person. Zutaten: Suche, Detail, Anlegen/Bearbeiten, Synonyme, Prüfliste nicht zugeordneter Zeilen. Vorlieben pro Person. Komponenten und Varianten (CRUD) plus Berechnung `POST /api/components/meal` (Mengen → Nährwerte und Fit).

## 8. Oberfläche (`web/`)

Rezeptliste (Suche, Filter, Karten mit kcal/Protein je Portion, Sättigung, Fit-Anzeige für gewählte Person/Tag/Slot), Rezeptdetail (Zutaten mit Zuordnung, Nährwerte, Portionsregler, Balken „Anteil am Slot-Ziel“), Import-Dialog (URL → Vorschau → Zutaten zuordnen → speichern), Prüfliste für unzugeordnete Zutaten, Zutaten-Katalog mit Vorlieben, Frühstücks-Baukasten mit Live-Summe (kcal, Protein, Salz) und Fit.

## 9. Aufteilung für Subagenten (Sonnet 5.5, keine gemeinsamen Dateien)

| Auftrag | Dateien | Voraussetzung |
|---|---|---|
| **A** Zutaten-Parser und Einheiten | `calc/ingredients.py`, `tests/test_calc_ingredients.py` | keine |
| **B** Nährwertrechner, Sättigung, Fit | `calc/nutrition.py`, `tests/test_calc_nutrition.py` | Typen aus `calc/types.py` (Hauptagent ergänzt) |
| **C** Web-Rezeptimport | `importers/recipe_web.py`, Tests | keine |
| **D** BLS-Importer | `importers/bls.py`, Tests | **BLS-Datei liegt lokal vor** |
| **E** Services und API | `services/recipes.py`, `services/catalog.py`, `api/recipes.py`, `api/ingredients.py`, `api/components.py`, Tests | Modelle, A, B |
| **F** Oberfläche | `web/src/...` | OpenAPI aus E |

Hauptagent: Modelle und Migration, Typen, Defaults, CLI, Zusammenführung, Tests auf Postgres, Docker-Prüfung.

## 10. Verifikation

- Unit-Tests für Parser (mindestens 40 Beispielzeilen), Einheiten, Nährwertsummen (von Hand nachgerechnet), Sättigungsscore (Suppe schlägt Pizza), Fit (Faktor, Klammerung, Abweichungen).
- Importer gegen 6 reale Rezept-URLs (3 + 3, nur lokal, Aggregate im Bericht).
- 30–50 Rezepte importiert, **Anteil Zeilen mit Zuordnung ≥ 90 %** nach einer Prüfrunde, `coverage ≥ 0,9` bei „ready“.
- Stichprobe: 5 Rezepte von Hand nachgerechnet, Abweichung der kcal ≤ 10 % gegenüber Rechner.
- Frühstücks-Baukasten: Standardfrühstück liefert plausible Summen inkl. Salz.

## 11. Ergebnis (Stand 2026-10-06)

**Gebaut:** Datenmodell und Migration `0002`, Zutaten-Parser und Einheiten (`calc/ingredients.py`), Stückgewichte (`calc/piece_weights.py`), Start-Synonyme (903 Aliase auf BLS-Namen, `calc/synonym_seed.py`), Nährwertrechner, Sättigung und Passung (`calc/nutrition.py`), BLS-Importer, Web-Rezeptimport, Services und API für Zutaten, Rezepte, Komponenten und Vorlieben, CLI (`import-bls`, `import-recipe`, `seed-synonyms`), Web-Seiten „Rezepte“, „Frühstück“, „Zutaten“.

**Abweichungen von der Spezifikation:**
- Die Passung (`/fit`, `fit_slot`) gilt immer für die **angemeldete Person**, es gibt keinen `person_id`-Parameter (jede Person sieht nur ihre eigenen Gesundheitsdaten).
- Stückangaben ohne bekanntes Stückgewicht (z. B. „3 Dinkelflocken“) bleiben **offen** (Status „Prüfen“), statt mit 100 g zu rechnen. Das Stückgewicht lässt sich je Zutat auf der Seite „Zutaten“ eintragen.
- Zeilen **ohne Mengenangabe** mit zugeordneter Zutat („Salz“, „Pfeffer“) gelten als „nach Geschmack“: Sie zählen nicht in die Nährwerte und halten den Status nicht auf.
- Gewürze, die die BLS nicht enthält (Paprikapulver, Zimt, Curry, Lorbeer …), sind als **Näherung auf „Basilikum getrocknet“** hinterlegt (kleine Mengen, grobes Profil). Das ist im Synonym-Seed dokumentiert.
- Die Automatik ordnet nur **sichere Treffer** zu (Synonym, exakt, oder Fuzzy mit ganzem Wort und Abstand zum Zweitbesten). Alles andere erscheint als Vorschlag in der Prüfliste („Apfel“ wird nie automatisch „Apfelmus“).

**Echtdaten-Test (lokal, Wegwerf-Postgres):** BLS 4.0 vollständig importiert (7.140 Zutaten, ca. 15 s), 5 Rezepte von emmikochteinfach.de und einfachkochen.de importiert: 50 von 52 Zutatenzeilen automatisch zugeordnet. Berechnete kcal je Portion gegenüber der Seitenangabe: Lachs 486 zu 474, Hühnersuppe 362 zu 370, Hüttenkäse-Omelett 523 zu 494. Der Gurkensalat weicht um 43 % ab (eine Zutat offen), die App weist darauf hin.

**Bekannte Grenzen:**
- Fleisch und Geflügel „ganz“ (z. B. Suppenhuhn) zählen mit Knochen, ohne Ausbeutefaktor sind die Nährwerte etwas zu hoch.
- Der URL-Import ruft beliebige http(s)-Adressen ab (kein Schutz gegen interne Adressen). Für den privaten Betrieb mit zwei angemeldeten Personen akzeptiert, im Auge behalten.
- Liste der Rezepte lädt höchstens 100 Einträge, keine Seitenweise-Anzeige.
- Rezept-Slots (Frühstück/Mittag/Abend) sind nach dem Import meist leer und werden von Hand getaggt (Filter „auch ohne Slot-Tag“).
- Zutaten, die die BLS nicht kennt (Chiliflocken, Fisch- und Worcestersauce, Currypaste …), legst du als manuelle Zutat an.

**Abnahme noch offen:** BLS auf TrueNAS einspielen, 30–50 Rezepte importieren, Zutaten prüfen, Frühstücks-Baukasten anlegen (Standard-Komponenten per Knopf, dann Mengen und fehlende Zutaten ergänzen).

