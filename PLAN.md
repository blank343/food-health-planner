# Food & Health Planner – Projektplan

> Lebendes Dokument. Aktueller Stand und Änderungslog stehen ganz unten ([Fortschritt](#fortschritt)).
> **Status: Planungsphase, es wurde noch kein Code geschrieben.**
> Zuletzt aktualisiert: 2026-10-04
> Persönliche Messwerte und Laborergebnisse stehen **nicht** in diesem Dokument, sondern in `Health Daten/Auswertung.md` (vertraulich, nicht für Git).

## 1. Ziel

Eine App für Christian und Liesa, die aus Gesundheits- und Trainingsdaten, Laborwerten, Vorlieben und aktuellen Supermarkt-Angeboten einen **Wochen-Mealplan** und eine **Einkaufsliste** erzeugt.

- Mischung aus bekannten Lieblingsgerichten und neuen Gerichten (Anteil einstellbar).
- Der Plan ist auf die Gesundheitsgeschichte, Laborwerte und den Trainingsumfang jeder Person abgestimmt.
- Angebote aus den Supermärkten der Umgebung (PLZ 01662) senken die Kosten.
- Die Einkaufsliste ist auf beiden iPhones jederzeit verfügbar (bisher: geteilte Erinnerungsliste).
- Das Backend läuft auf dem Homeserver in Docker.

### Leitprinzip: Konfiguration statt Code
**Nichts Persönliches wird im Code festgelegt.** Grenzwerte (Gewicht, Körperfett, kcal, Protein, Salz, Zink …), Ernährungsregeln, Supplemente, Ziele, Tempo, Slot-Anteile, Vorlieben und Abneigungen, Regelwerke aus Laborwerten und der Trainingsplan sind **Daten in der App**, pro Person pflegbar, versioniert und mit Quelle versehen. Der Code enthält nur die Rechenlogik und **sichere Standardwerte**, die beim Start gelten, bis jemand sie anpasst. Das gilt auch für die Daten beider Personen: Eine Änderung braucht kein Deployment.

## 2. Festgelegte Rahmenbedingungen

| Thema | Festlegung |
|---|---|
| Region / Läden | PLZ **01662 (Meißen)**. **Christian kauft Mo–Fr täglich bei Lidl ein**, samstags **Aldi Nord und REWE**. |
| Einkaufsliste | Eigene **PWA** (Homescreen, offline, Live-Sync, Abhaken) mit Tagesansicht „Heute bei Lidl“. Optionaler Export per Apple-Kurzbefehl in die geteilte Erinnerungsliste. Apple bietet keine stabile API für geteilte Erinnerungslisten. |
| Server | **Intel N100, 16 GB DDR5, TrueNAS SCALE ElectricEel 24.10.2.4** (Docker-basierte Apps, Custom App per Compose-YAML). **Tailscale läuft bereits** auf Server und beiden iPhones. |
| Datenquellen | **Alle Dateien im Projektordner sind freigegeben**, auch die Laborbefunde. Start mit manuellem Import: Christian per Health Auto Export (CSV/ZIP), Liesa per nativem Apple-Health-Export (`export.xml`), beide per Laborbefund-PDF. Live-Push per Health Auto Export folgt später. Gesundheitsgeschichte, Medikation und Supplemente von Christian liegen als Chat-Export vor (`Health Daten/Christian/`), **Liesas Historie reicht sie nach**. |
| Rezepte | Eigene Favoriten plus Rezeptseiten, v. a. **emmikochteinfach.de** und **einfachkochen.de** (weitere Quellen definierst du später). |
| Ziele | **Beide: Abnehmen.** Das operative Ziel kann sich ändern und muss in der App pro Person umstellbar sein. Die App berechnet pro Person die Makroverteilung und berücksichtigt sie im Plan. **Christian:** isst aktuell ca. 2.000 kcal/Tag, Tempo **0,5 kg/Woche**, mit harter Untergrenze (siehe Abschnitt 4, Sicherheitsgrenzen). **Liesa:** isst aktuell grob 2.500 kcal/Tag. |
| Allergien | Keine. |
| Vorlieben | Ungeliebte Zutaten sind **nicht hartcodiert**, sondern in der App pflegbar (Mag ich / mag ich nicht / nie). |
| Sprache | Deutsch (App und Rezepte). |

### Slot-Modell

| | Mo–Fr | Sa/So |
|---|---|---|
| **Christian** (OMAD, eine Mahlzeit am Tag) | **nur Frühstück**, das ist seine einzige Mahlzeit und trägt das gesamte Tagesziel | festes Frühstück + gemeinsames Abendessen, teilweise kleine Snacks |
| **Liesa** | Frühstück + Mittag (beides fürs Mitnehmen in die Schule) + Abendessen (warm, schnell, ≈ ≤ 30 min), optional Snack | festes Frühstück + gemeinsames Abendessen, teilweise kleine Snacks |
| **Gemeinsam** | – | Abendessen: aufwendig, gemeinsam gekocht |

**Christians Frühstück ist ein Baukasten, kein Rezept.**
- Unter der Woche: Rührei, Brot oder Brötchen mit Kräuterquark, Skyr, Apfel, Banane, saure Gurken, Tomate.
- Am Wochenende (fest): Brot, Hummus, Kräuterquark, Croissant, Marmelade, Rührei, Kiwi.
- Der Planer behandelt diesen Slot als **Komponenten-Slot**: Er optimiert Mengen der Komponenten (Eier, Brot, Quark, Skyr, Obst, Gemüse) auf das Tagesziel und wechselt Varianten durch. Er wählt hier keine fertigen Rezepte.

**Liesas Slots bevorzugen sättigende, kalorienarme Gerichte.** Im Defizit hat sie oft Hunger. Der Planer bekommt dafür ein **Sättigungs-Scoring** (niedrige Energiedichte, hohes Volumen, viel Protein und Ballaststoffe, warm, Suppen/Eintöpfe/Ofengemüse).

Weitere Folgerungen:
- Slots haben Attribute: wer isst mit, max. Kochzeit, vorkochbar, transportierbar, fix oder variabel, Slot-Typ (Rezept, Baukasten oder Snack).
- **Fixe Slots** (Wochenend-Frühstück) werden nicht geplant, aber in Einkauf und Makros berücksichtigt.
- **Snacks** sind ein eigener, optionaler Slot pro Person mit kleinem Kalorienbudget (Wochenende gelegentlich, bei Liesa auch Mo–Fr als Hungerpuffer).
- **Vorbereitung für den Folgetag:** Liesa bereitet Frühstück und Mittag am Vorabend vor. Die App zeigt abends eine Aufgabenliste „Heute für morgen vorbereiten“ mit einem **Zeitbudget von ca. 30 Minuten** für Frühstück und Mittag zusammen. **Vorkochen im Voraus ist denkbar, aber kein fester Sonntagstermin.** Die App behandelt Vorkochen deshalb als optionalen Modus (Batch-Gerichte mit 3–4 Tagen Haltbarkeit).
- Für Christian gibt es unter der Woche **kein „extern/ungeplant“-Budget** (Default 0, einstellbar).

### Einkaufsrhythmus
- **Mo–Fr:** täglicher Einkauf bei Lidl. Die Liste wird pro Tag erzeugt: „Heute bei Lidl“ enthält, was für heute Abend und für die Vorbereitung für morgen gebraucht wird. Frisches lässt sich tagesfrisch kaufen, Kühlschranklagerung spielt weniger Rolle.
- **Samstag:** großer Einkauf bei **Aldi Nord und REWE** für das Wochenende und haltbare Vorräte.
- Der Planer teilt jede Zutat dem günstigsten und passenden Einkaufstermin zu, abhängig von Angeboten und Haltbarkeit.
- **Planungshorizont:** Die App **kann die ganze Woche im Voraus planen, muss aber nicht**. Der Plan lässt sich pro Tag bestätigen oder verwerfen, die Tagesliste ist immer verfügbar. Bis ein Tag bestätigt ist, darf der Planer ihn bei neuen Angeboten anpassen.

## 3. Folgerungen aus den Daten (ohne persönliche Werte)

Details: `Health Daten/Auswertung.md`.

- **Aktivität:** Beide trainieren viel, häufig früh morgens. Die Geräteschätzung des Energieverbrauchs (Apple Watch) ist unsicher. Die App schätzt den Energiebedarf deshalb **adaptiv aus dem Gewichtstrend** (ab Phase 1, einfache Version), statt nur der Gerätezahl zu folgen.
- **Ernährungsdaten:** In Apple Health sind kaum Ernährungsdaten geloggt. Die Aufnahme kommt aus dem Plan, nicht aus Apple Health.
- **Importformate:** Zwei unterschiedliche Quellen (HAE-CSV/-ZIP, Apple-Health-XML mit 1,3 GB, Streaming-Parser nötig), außerdem Laborbefund-PDFs. Daten enthalten Ausreißer (z. B. falsche Gewichte), die gefiltert werden müssen.
- **Labor als Planungsinput:** Beide Befunde (Labor Staber) sind maschinenlesbar. Aus Befunden werden **sanfte, nachvollziehbare Ziele** abgeleitet (z. B. Eisenquellen plus Vitamin C bei niedrig-normalem Ferritin, ungesättigte Fette bei grenzwertigem HDL). Die App **diagnostiziert nicht** und verweist bei Auffälligkeiten auf die Ärztin/den Arzt. Regeln sind für euch einsehbar und abschaltbar.
- **Ernährungsregeln aus ärztlicher Beratung (Christian, Details in `Health Daten/Auswertung.md`):** Salz-Obergrenze pro Tag, kein Kaliumsalz und keine Kalium-Supplemente ohne Rücksprache (kaliumreiche Lebensmittel sind erwünscht), Omega-3-Obergrenze bzw. Fisch 1–2× pro Woche, Zink-Obergrenze **inklusive Supplement**. Der Planer behandelt diese Regeln als **harte Grenzen**. Sie müssen in der App sichtbar, pflegbar und mit Quelle versehen sein. Für Liesa kommen Regeln nach, sobald ihre Historie vorliegt.
- **Supplemente zählen mit:** Nährstoff-Summen gelten für **Essen plus Supplement** (z. B. Zink, Magnesium, Vitamin D, Omega-3). Dafür braucht die App Dosierungen pro Supplement. Liesa nimmt ähnliche Supplemente, zusätzlich Folsäure für die Haare, deshalb kein Folsäure-Fokus im Plan.
- **Salz im Frühstücks-Baukasten:** Christians typische Komponenten (Brot/Brötchen, Kräuterquark, saure Gurken, Käse) sind salzreich. Die Salzbilanz wird für diesen Slot ausdrücklich gerechnet und kann die Auswahl begrenzen.
- **Trainingsplan als Input:** Christian hat einen festen Wochenplan (Kraft morgens Mo–Fr, Laufband Mo und Do, langer lockerer Lauf am Sonntag, Intervalle am Wochenende). Der Planer nutzt diese **Wochenstruktur für Kohlenhydrat- und Energieverteilung** (z. B. mehr Kohlenhydrate vor/nach Intervall- und Langlauftagen, Beintag) und gleicht sie mit den echten Workouts ab.
- **Kreatin beeinflusst das Gewicht** (Wasserspeicherung). Gewichtstrends werden geglättet, damit die adaptive Energieschätzung nicht verrutscht.
- **Platzhalter in den Daten:** Gewicht „81,00 kg“ (oft wiederholt) und Sechs-Minuten-Gehtest „500 m“ sind vermutlich keine echten Messwerte. Importer filtern wiederholte Platzhalter.
- **Liesas Befund ist ein Teilbefund** (einige Werte „folgt“). Das Datenmodell muss Nachlieferungen aufnehmen.
- **Rezeptquellen:** emmikochteinfach.de und einfachkochen.de liefern schema.org-Recipe-JSON-LD (Zutaten, Portionen, Zeit). `robots.txt` von emmikochteinfach.de erlaubt das Auslesen. Nährwerte der Seiten sind oft unvollständig (häufig nur Kalorien), deshalb werden **Makros aus den Zutaten berechnet**. Quelle und Link bleiben am Rezept, alles nur für den privaten Gebrauch.

## 4. Systemarchitektur

```
 iPhone Christian / Liesa                    TrueNAS SCALE 24.10 (N100, 16 GB), Docker-Apps
 ┌───────────────┐  HTTPS via Tailscale   ┌────────────────────────────────────────┐
 │ PWA (Plan,    │◄──────────────────────►│ Tailscale Serve (TLS) / Reverse Proxy  │
 │ Liste, Rating)│                        │   ├─ /      → web  (statische PWA)     │
 ├───────────────┤                        │   └─ /api   → api  (FastAPI)           │
 │ Health Auto   │  später: POST JSON     │ worker (Angebote, Planung, Import, LLM)│
 │ Export (REST) │───────────────────────►│ postgres  (ZFS-Dataset, Snapshots)     │
 ├───────────────┤                        │ optional: redis                        │
 │ Kurzbefehl    │  GET /api/list.json    └────────────┬───────────────────────────┘
 │ → Erinnerungen│◄────────────────────────────────────┘
 └───────────────┘     ausgehend: Angebote (manueller Import, ggf. Händlerseiten), Rezeptseiten,
                                   Claude API (nur Rezepte/Zutaten), Nährwert-DB (BLS / Open Food Facts / USDA)
 Manueller Import (Start): HAE-ZIP/CSV, Apple-Health-export.xml, Labor-PDF → Upload in der PWA oder CLI
```

### Komponenten
- **Backend:** Python 3.12, **FastAPI**. Passende Bibliotheken: `recipe-scrapers` (Rezeptseiten), OR-Tools (Planer), `lxml.iterparse` (Streaming-Import des Apple-Health-XML), `pdfplumber` (Laborbefunde).
- **DB:** PostgreSQL (Alembic-Migrationen). Redis nur, falls der Worker mehr als APScheduler braucht. Auf der N100-Hardware reicht das locker, ein lokales ML-Modell ist nicht nötig.
- **Worker:** eigener Container (gleiches Image) für Cron-Jobs: Angebots-Refresh, Planerzeugung, Rezeptimport, LLM-Calls.
- **Frontend:** **PWA** (Svelte oder React mit Vite). Offline-Cache der Liste, Live-Sync über SSE oder WebSocket. HTTPS ist Pflicht für Installation und Service Worker.
- **Zugriff:** **Tailscale** (läuft bereits). HTTPS über `tailscale serve` und MagicDNS. Keine offenen Ports.
- **TrueNAS SCALE 24.10:** Betrieb als Custom App per Docker-Compose-YAML. Daten auf eigenen **ZFS-Datasets** (Gesundheitsdaten auf einem **verschlüsselten Dataset**), Backup per **ZFS-Snapshots und Replikation** zusätzlich zu `pg_dump`.
- **Auth:** zwei Nutzer, einfache Session oder Passkey. Für den späteren HAE-Push gibt es pro Person einen langen API-Token. Jede Person sieht standardmäßig nur ihre eigenen Gesundheitsdaten, der gemeinsame Plan ist sichtbar.
- **LLM:** Claude API, nur für **Rezept- und Zutatentexte** (Zutaten-Normalisierung, Angebots-Matching bei Unklarheit, Neu-Rezept-Vorschläge). **Gesundheits- und Laborwerte gehen nie an die API.** Die Gesundheitslogik läuft lokal als deterministisches Regelwerk, Begründungstexte entstehen aus Vorlagen.

### Datenmodell (Kern)
- `person` (Größe, Geburtsjahr, Geschlecht, Ziel, Diäten, Untergrenzen für kcal/Protein/Körperfett)
- `health_daily` und `workout` (aus zwei Importern mit gemeinsamem Zielschema und `source`-Feld)
- `lab_result` (Person, Datum, Analyt, Wert, Einheit, Referenz, Flag, Teilbefund/ausstehend) und `lab_rule` (Regel „Wert/Bereich → sanftes Planziel“, einsehbar und abschaltbar)
- `health_context` (Vorerkrankungen, Medikamente, vom Nutzer gepflegt)
- `supplement` (Person, Name, Dosierung, Nährstoffbeitrag, Einnahmezeit). Wird in die Nährstoff-Summen eingerechnet.
- `nutrient_rule` (Person, Nährstoff oder Lebensmittelgruppe, Typ: Obergrenze/Untergrenze/meiden/Ziel, Wert, Quelle, „vom Arzt bestätigt“-Flag). Beispiele: Salz-Obergrenze, Zink-Obergrenze inkl. Supplement, Kaliumsalz meiden.
- `training_plan` (Person, Wochentag, Einheit, Intensität, Uhrzeit, Dauer, erwartete Energie). Basis für die Planwoche, abgeglichen mit `workout`.
- `goal_profile` (Zielart, kcal-Modifikator, Protein g/kg, Fett %, gültig ab). **Versioniert, damit das Ziel jederzeit wechselbar ist.**
- `target_day` (berechnetes kcal/Makro-Ziel pro Person und Tag, mit Trainingstag-Faktor)
- `recipe`, `recipe_ingredient`, `ingredient` (normalisiert, Einheiten, Nährwerte inkl. Mikros, Energiedichte), `recipe_tag` (Slot-Eignung, Kochzeit, vorkochbar, transportierbar, Küche, Saison, **Sättigungsscore**)
- `component` und `component_variant` (Baukasten-Bestandteile für Christians Frühstück, mit Mengenspannen)
- `preference` (pro Person: Rezept-Rating, Zutat mag/mag nicht/nie, **in der App pflegbar**)
- `store`, `shopping_trip` (Lidl Mo–Fr täglich, Aldi Nord + REWE Sa), `offer` (Händler, Produkt, Preis, Grundpreis, gültig von/bis, Kategorie), `offer_match` (Zutat ↔ Angebot, Konfidenz)
- `plan` / `plan_slot` (Woche, Tag, Slot, Rezept oder Komponenten, **Portionen pro Person**, Status: Vorschlag/fix/gegessen)
- `shopping_list` / `shopping_item` (Menge, Einheit, Händler und Einkaufstag, Angebotsersparnis, abgehakt von/um)
- `pantry` (optional, Phase 7)

### Zielwert-Berechnung (Gesundheitsdaten → Makros)
1. **Grundumsatz:** Mifflin-St-Jeor aus Gewicht, Größe, Alter, Geschlecht. Alternativ Katch-McArdle bei verlässlichem Körperfett.
2. **Aktivität:** aus echten Daten (Ø Active Energy der letzten 7–28 Tage plus erwartete Workouts der Planwoche), **kalibriert am Gewichtstrend** (adaptiver Faktor), weil Geräteschätzungen abweichen.
3. **Ziel-Modifikator** aus dem aktiven `goal_profile` (Abnehmen: Defizit in % oder kg/Woche, einstellbar pro Person).
4. **Makros:** Protein in g/kg (im Defizit hoch), Fett in % der kcal, Rest Kohlenhydrate. An Trainingstagen etwas mehr Kohlenhydrate (Schalter).
5. **Verteilung auf Slots:** Ziel pro Slot = Tagesziel × Anteil je Person und Wochentag. Bei Christian Mo–Fr **100 % im Frühstück** (OMAD). Bei Liesa frei einstellbar, Default mit Snack-Puffer.
6. **Sicherheitsgrenzen (hart):** Untergrenze für kcal und Protein pro Person, **Tempo-Obergrenze** (Christian 0,5 kg/Woche, Tempo sinkt automatisch, je näher er der Untergrenze kommt), einstellbare **Untergrenze für Gewicht und Körperfett**, ab der kein weiteres Defizit vorgeschlagen wird. **Es gilt, was zuerst erreicht wird.** Die Grenzen sind **Einstellungen pro Person** (Leitprinzip). Eine Gewichtsgrenze, die rechnerisch ein sehr niedriges Körperfett bedeutet (z. B. 70 kg bei ca. 70 kg Magermasse), löst einen **nicht blockierenden Hinweis** aus, zusätzlich lässt sich eine Körperfett- oder höhere Gewichtsgrenze setzen. Warnung bei großem Defizit plus hohem Trainingsumfang (Ruhepuls/HRV/Gewicht als Frühwarnung).
7. **OMAD-Plausibilitätschecks (Christian):** Die App prüft, ob das Frühstück in einer realistischen Portion (kcal, **Gewicht und Volumen**) das Tagesziel erreicht, sowie Ballaststoffe, Protein-Mindestmenge und Schlüssel-Mikronährstoffe.
8. **Labor-Regeln:** Aus `lab_result` abgeleitete **sanfte Planziele** (Gewichtung statt harte Verbote), z. B. mehr Eisenquellen plus Vitamin C bei niedrig-normalem Ferritin. Fehlt ein Wert (Teilbefund), wird kein Ziel abgeleitet.
8a. **Ernährungsregeln (`nutrient_rule`) als harte Grenzen:** Salz pro Tag, Zink (Essen plus Supplement), Omega-3/Fisch-Häufigkeit, Kaliumsalz und Kalium-Supplemente nie vorschlagen. Kaliumreiche Lebensmittel als sanftes Ziel. Zusätzlich vorgeschlagene Vorsichtsregeln (z. B. Lakritz meiden, Grapefruit meiden) sind **als „vom Arzt zu bestätigen“ markiert**, bis ihr sie abhakt.
9. **Hinweis in der App:** Orientierungswerte, keine medizinische Beratung.

### Planungs-Algorithmus (Wochenplan)
- **Harte Constraints:** Allergien/Diäten, „nie“-Zutaten, Slot-Eignung, max. Kochzeit, Transportierbarkeit/Haltbarkeit, keine Wiederholung innerhalb von N Tagen, Sicherheitsgrenzen, **Ernährungsregeln** (Salz, Zink inkl. Supplement, Omega-3/Fisch pro Woche, kein Kaliumsalz).
- **Zielfunktion (gewichtet, einstellbar):**
  - Makro-Treffer pro Person und Tag. Portionen werden **pro Person skaliert**. Für Christians Baukasten-Frühstück zusätzlich: realistische Menge und Volumen.
  - **Sättigung für Liesa:** niedrige Energiedichte, hohes Volumen, hohes Protein, viele Ballaststoffe, warme Gerichte.
  - **Sanfte Labor-Ziele** (siehe oben) und **kaliumreiche Lebensmittel**.
  - **Trainingsperiodisierung:** Kohlenhydrate und Energie nach Wochenplan (Beintag, Intervalle, langer Lauf).
  - Beliebtheit (Ratings) gegen **Neuheit** (Ziel z. B. 70 % bekannt / 30 % neu).
  - **Angebotsersparnis** für die benötigten Mengen.
  - Zutaten-Überschneidung (angebrochene Packungen nicht verderben lassen) und Abwechslung bei Küche, Hauptzutat, Zubereitung.
  - **Einkaufslogik:** Haltbares und Angebote auf Samstag (Aldi Nord/REWE), Frisches auf den jeweiligen Lidl-Tag.
- **Umsetzung:** OR-Tools CP-SAT, zunächst Heuristik plus lokale Suche. **Tauschen-Button** pro Slot. Gesperrte Slots (Wochenend-Frühstück, auswärts essen) bleiben unverändert.
- **Neue Rezepte:** Rezepte von den Quellen werden per URL oder über die Sitemap (höflich, mit Pausen, `robots.txt` beachten) in einen Kandidatenpool importiert. Der Solver wählt aus Favoriten plus Kandidaten, Claude schlägt nur ergänzend vor.

### Angebote
- **Ergebnis Spike a (2026-10-04): Marktguru ist ein No-Go.** Die AGB von marktguru verbieten ausdrücklich den Einsatz von Programmen zum automatischen Auslesen von Daten (Ziff. 4.e) und die kommerzielle Datennutzung. Die inoffizielle Schnittstelle (Key aus der Startseite) wird daher **nicht** verwendet. Gleiches gilt vorsorglich für kaufDA/MeinProspekt, solange deren AGB nicht geprüft sind.
- **Quellen (nach Priorität), jeweils hinter dem `OfferProvider`-Adapter:**
  1. **Preisbasis pro Zutat (immer aktiv, kein wöchentlicher Aufwand):** Die App führt pro Zutat und Händler einen Referenzpreis (Lidl, Aldi Nord, REWE). Er wird gelegentlich angepasst (manuell oder aus einem Kassenbon-Foto). Der Planer spart damit **über die Zutatenwahl** (günstige Basics, Eigenmarken, passende Händler), auch ohne tagesaktuelle Angebote.
  2. **Newsletter-Postfach (Ziel: automatisch):** REWE (E-Mail und WhatsApp), ALDI Nord (E-Mail) und Lidl bieten Newsletter mit Wochenangeboten an. Ihr legt ein **eigenes Postfach** an, abonniert die Newsletter, und der Server liest dieses Postfach per IMAP **nur lesend**. Eine Extraktion (Claude, nur Angebotstexte und -bilder, keine Gesundheitsdaten) erzeugt daraus die Angebote. Das sind Informationen, die die Händler **ausdrücklich an euch senden**, nichts wird von Händlerseiten abgerufen. Einschränkung: Newsletter zeigen meist nur **Highlights**, nicht das ganze Prospekt. Ob die Abdeckung für Lebensmittel reicht, zeigt ein Test in Phase 0 mit 2 Wochen gesammelter Newsletter.
  3. **Prospekt-Upload (optional, gelegentlich):** PDF, Foto/Screenshot oder Text des Prospekts mit Extraktion und Prüfansicht, wenn ihr eine Woche besonders gut abdecken wollt. Kein Pflichttermin.
  4. **Manuelle Eingabe** einzelner Angebote als Fallback.
  5. **Händlerseiten direkt:** zurückgestellt (siehe oben). Marktguru und kaufDA kommen nicht infrage.
- **Risiko:** Die Angebotsquelle bleibt der unsicherste Teil. Der Plan funktioniert ohne tagesaktuelle Angebote (Preisbasis), Angebote sind ein Zusatz und keine Voraussetzung.
- **Matching:** Angebot → normalisierte Zutat über Kategorien, Synonyme, Embeddings. Unklare Fälle an Claude (Haiku). Kein Match heißt: kein Preiseinfluss.
- **Zeitfenster:** Gültigkeit der Angebote an Einkaufstag und Kochtage koppeln. Lidl-Angebote gelten oft ab Montag oder Donnerstag, passend zum täglichen Einkauf.

### Einkaufsliste (iPhone)
- Aggregation aller Zutaten, Einheiten umrechnen, Packungsgrößen runden, optional Vorrat abziehen.
- **Pro Einkaufstag eine Liste** (Mo–Fr „Lidl“, Sa „Aldi Nord / REWE“), plus Wochenüberblick. Angebote hervorgehoben („−1,20 € bei Lidl bis Sa“).
- Beide iPhones sehen dieselbe Liste live, Abhaken wird synchronisiert, offline nutzbar.
- **Kurzbefehl-Export:** Ein Apple-Kurzbefehl holt `GET /api/list.json` (Tagesliste) und legt die Einträge in eure bestehende Erinnerungsliste. Die PWA bleibt die Quelle der Wahrheit.

### Datenschutz und Repo-Hygiene
- Gesundheitsdaten, Befunde und Exporte enthalten Namen und medizinische Informationen. Das Projekt ist noch kein Git-Repo. **Beim Anlegen des Repos wird `Health Daten/` sofort in `.gitignore` aufgenommen**, damit nichts davon versehentlich committet wird. Dieses Dokument enthält deshalb keine persönlichen Messwerte.
- Importe werden aus dem Ordner gelesen und liegen später nur auf dem Homeserver (verschlüsseltes Dataset).
- Gesundheitsdaten verlassen den Server nicht (keine LLM-Aufrufe damit).

## 4a. Arbeitsweise bei der Umsetzung

- **Parallelisieren mit Subagenten:** Wenn sich Arbeit parallel erledigen lässt, werden **Subagenten auf Sonnet 5.5** (`model: sonnet`) gestartet, um schneller voranzukommen. Typische Aufteilung: Backend-Endpunkte, Importer, Frontend-Ansichten, Tests und Dokumentation laufen als getrennte Aufgaben mit klar abgegrenzten Dateien und Schnittstellen.
- **Regeln dafür:**
  - Jede Aufgabe bekommt einen eigenen, selbsterklärenden Auftrag (Ziel, betroffene Dateien, Schnittstelle, Abnahmekriterium), weil Subagenten keinen Gesprächskontext haben.
  - Nur parallelisieren, wenn die Aufgaben **keine gemeinsamen Dateien** bearbeiten. Abhängige Schritte laufen nacheinander.
  - Aufgaben mit viel Kontext oder Architekturentscheidungen bleiben beim Hauptagenten. Subagenten bekommen abgegrenzte Teilaufgaben.
  - Die Ergebnisse werden vom Hauptagenten geprüft und zusammengeführt (Tests laufen lassen, Diff lesen), bevor etwas als erledigt gilt.
  - **Persönliche Gesundheitsdaten** (`Health Daten/`) dürfen Subagenten nur lesen, wenn die Aufgabe es zwingend braucht (z. B. Importer-Tests). Sie dürfen sie nie in Dateien außerhalb von `Health Daten/` oder `out/` kopieren und nie committen.
  - Commits macht der Hauptagent, und nur auf deine Anweisung.
- **Beispiele, wo es sich lohnt:** Phase 1 (HAE-Importer, Apple-Health-Importer und Labor-Parser parallel), Phase 2 (Rezeptimport, Nährwertberechnung, Komponenten-Katalog parallel), Phase 4 (PWA-Frontend, Listen-API, Kurzbefehl-Export parallel).

## 5. Projektplan (Phasen)

Aufwand bei Hobby-Tempo (ca. 5–8 h/Woche). **MVP = Phasen 0–4.** Gesamt grob 14–18 Wochen, MVP nach ca. 8–10 Wochen.

| Phase | Inhalt | Abnahme | Dauer |
|---|---|---|---|
| **0 – Fundament & Spikes** | Repo (mit `.gitignore` für `Health Daten/`), Docker Compose lokal und Test als TrueNAS-Custom-App (24.10.2.4), Tailscale-HTTPS. **Spikes:** (a) Angebotsquelle für PLZ 01662 klären (Ergebnis: Marktguru No-Go, Import per Prospekt-Upload als Standard), (b) Streaming-Import von Liesas `export.xml` und Christians HAE-ZIP, (c) Laborbefund-PDF-Parser auf beiden Befunden, (d) `recipe-scrapers` auf je 3 Rezepten beider Seiten, (e) Kurzbefehl legt Test-Items in der geteilten Erinnerungsliste an. Optional: Mealie/Tandoor einen Tag ausprobieren (Build vs. Buy). | Alle Risiken sind „geht“ oder „Plan B“ | 1–1,5 Wo. |
| **1 – Gesundheitsdaten & Profile** | Importer (HAE-CSV/ZIP, Apple-Health-XML, Labor-PDF), Upload in der App, Profile, Zielprofile (wechselbar), TDEE/Makro-Rechner mit **Kalibrierung am Gewichtstrend**, Sicherheitsgrenzen, Labor-Ansicht mit Regelwerk, **Pflege von Supplementen, Ernährungsregeln und Trainingsplan**, Dashboard (Gewichtstrend, Training, Tagesziel) | Tagesziele beider Personen nachvollziehbar und plausibel, Laborwerte korrekt importiert | 2–2,5 Wo. |
| **2 – Rezeptbibliothek & Komponenten** | Favoriten anlegen, Import per URL (JSON-LD), Zutaten-Normalisierung, Nährwerte (BLS/OFF/USDA, inkl. Mikros und Energiedichte), Sättigungsscore, Tags, Rating, **pflegbare Zutaten-Vorlieben**, **Komponenten-Katalog** für Christians Frühstück | 30–50 Rezepte und der Frühstücks-Baukasten mit gültigen Nährwerten | 2 Wo. |
| **3 – Planer v1** | Slot-Vorlagen (Wochentag/Wochenende, Person, Rezept-, Baukasten- und Snack-Slot), Solver, Portionsskalierung, Fix-/Sperr-Slots, Vorbereitung für den Folgetag, optionaler Vorkoch-Modus, OMAD-Checks, Sättigungs- und Labor-Ziele, Tauschen | Wochenplan per Klick, Makros pro Person und Tag im Zielkorridor | 2–3 Wo. |
| **4 – Einkaufsliste & PWA** | Aggregation, Tageslisten (Lidl Mo–Fr) und Samstagsliste (Aldi Nord/REWE), Live-Sync, Offline, Kurzbefehl-Export, Installation auf beiden iPhones | Ihr kauft eine Woche damit ein | 1,5–2 Wo. |
| **5 – Angebote** | `OfferProvider`-Adapter, **Preisbasis pro Zutat und Händler**, **Newsletter-Postfach (IMAP, nur lesend) mit Extraktion**, optionaler Prospekt-Upload mit Prüfansicht, Matching, Preisziel im Solver, Zuordnung zu Einkaufstagen, manuelle Eingabe | Plan nutzt Angebote, Ersparnis pro Woche sichtbar | 2–3 Wo. |
| **6 – Neue Rezepte & Lernen** | Crawl über Sitemap (höflich), Kandidatenpool, Neuheitsquote, Claude für Vorschläge, Präferenzmodell aus Ratings | ca. 30 % neue Gerichte pro Woche, die zum Geschmack passen | 2 Wo. |
| **7 – Politur & Betrieb** | Push-Erinnerungen, Vorrat, Live-Push per Health Auto Export, Folgebefunde nachtragen, Zyklus-Modul (nur mit Opt-in), Backups testen, Monitoring, Export/Import, Doku | Läuft stabil ohne Eingreifen | 1–2 Wo. |

**Kritischer Pfad:** 0 → 1 und 2 (parallel möglich) → 3 → 4 → 5 → 6. Die größte Unsicherheit liegt bei den Angeboten (5), der Nährwertqualität (2) und der Machbarkeit von Christians Tagesziel in einem Frühstück (3).

### Risiken

| Risiko | Gegenmaßnahme |
|---|---|
| Angebotsdaten: Marktguru-AGB verbieten automatisches Auslesen, Händler-AGB ungeprüft | Kein automatischer Abruf. Prospekt-Upload (nutzerinitiiert) als Standard, Adapter für spätere erlaubte Quellen, Plan funktioniert auch ohne Angebote |
| Nährwerte pro Rezept ungenau (Zutaten-Mapping) | Datenbank (BLS/OFF), Review-Ansicht, Werte bleiben Schätzwerte |
| **OMAD mit großem Tagesziel** (Volumen ≈ ein sehr großes Frühstück) | Planer zeigt Gewicht und Volumen, schlägt energiedichte Komponenten vor, Defizit und Verteilung sind einstellbar |
| **Großes Defizit plus hoher Trainingsumfang** bei beiden | Harte Untergrenzen, Wochenlimit fürs Defizit, Körperfett-/Gewichtsuntergrenze, Frühwarnung aus Ruhepuls/HRV/Gewicht |
| **Geräte-Energieschätzung ungenau** | Kalibrierung am Gewichtstrend, Zielwerte nur als Orientierung |
| **Gewichtsuntergrenze zu niedrig eingestellt** (z. B. 70 kg bei ca. 70 kg Magermasse) | Grenzen sind Einstellungen, nicht blockierender Hinweis bei unplausibel niedrigem Körperfett, zusätzliche Körperfett-/Gewichtsgrenze möglich, Tempo sinkt gegen Ende |
| **Wechselwirkung Ernährung und Medikation** (Salz, Kalium, Lakritz, Grapefruit) | Regeln als `nutrient_rule` mit Quelle, Hinweis „mit Arzt abstimmen“, keine Eigenempfehlungen ohne Markierung |
| **Laborwerte falsch gedeutet** | Nur sanfte Planziele, einsehbare und abschaltbare Regeln, keine Diagnosen, Hinweis auf Arzt, Teilbefunde markieren |
| 1,3-GB-XML (Liesa) sprengt den Speicher | Streaming-Parser, nur ausgewählte Record-Typen, GPX-Routen ignorieren |
| iOS-PWA-Einschränkungen (Push, Hintergrund) | Push optional, Kern funktioniert ohne |
| Gesundheitsdaten sind sensibel | Nur lokal, Tailscale, verschlüsseltes Dataset, `.gitignore`, kein Gesundheits-Input an LLM, personenbezogene Sicht |
| Scope Creep (Rezeptmanager nachbauen) | MVP strikt Phasen 0–4, Build-vs-Buy-Spike zu Mealie/Tandoor |
| TrueNAS-App-Modell (Custom App/Compose) | Compose-Datei bleibt portabel, Test in Phase 0 |

## 6. Konfiguration statt offener Fragen

**Entscheidung (2026-10-04):** Persönliche Werte, Grenzen und Regeln sind **kein Planungs-Blocker**. Sie werden **nicht im Code festgelegt**, sondern in der App gepflegt (siehe Leitprinzip in Abschnitt 4). Die Umsetzung kann starten, ohne dass diese Werte vorab geklärt sind.

| Thema | Wo gepflegt | Startwert / Verhalten ohne Eingabe |
|---|---|---|
| Ziele, Tempo (kg/Woche), Zielgewicht oder -körperfett | `goal_profile` pro Person, versioniert | Tempo-Default konservativ, kein Zielgewicht, bis es gesetzt wird |
| Untergrenzen für Gewicht, Körperfett, kcal, Protein | `person` / Einstellungen pro Person | Standard-Sicherheitswerte der App. Wer eine Gewichtsgrenze setzt, bekommt einen **nicht blockierenden Hinweis**, wenn sie rechnerisch ein sehr niedriges Körperfett bedeutet. |
| Ernährungsregeln (Salz, Zink, Omega-3, Kalium, Meiden-Listen wie Lakritz/Grapefruit) | `nutrient_rule` mit Quelle und „vom Arzt bestätigt“-Flag | Ohne Regel keine Einschränkung. Vorschläge der App sind als „zu bestätigen“ markiert. |
| Supplemente und Dosierungen | `supplement` pro Person | Ohne Dosis werden Supplemente nicht in Obergrenzen eingerechnet und die App weist darauf hin |
| Vorerkrankungen, Medikamente | `health_context` pro Person (Liesa reicht nach) | Leer = keine Zusatzregeln |
| Laborwerte | `lab_result` per PDF-Import (Liesa reicht Rest nach) | Fehlende Werte erzeugen keine Planziele |
| Trainingsplan | `training_plan` pro Person | Ohne Plan: Ableitung aus den echten Workouts |
| Zyklus | Opt-in-Schalter pro Person (Daten lokal) | Aus, bis aktiviert |
| Slot-Anteile, Snack-Budget, Vorbereitungszeit (≈ 30 Min.), Kochzeit-Limits | Slot-Vorlagen und Einstellungen | Defaults aus diesem Plan |
| Einkaufszeiten, Händlerpräferenz, Budget/Sparziel | Einstellungen und `store` | Preisvergleich entscheidet, kein Budgetlimit |
| Küche (Geräte), Neuheitsquote (z. B. 70/30), Rezeptquellen | Einstellungen | 70 % bekannt / 30 % neu, emmikochteinfach.de und einfachkochen.de |
| Nährwertdatenbank | Einstellung, austauschbar | Wird in Phase 2 per Vergleich entschieden (BLS / Open Food Facts / USDA) |

**Technische Restpunkte (in Phase 0 zu klären, keine Nutzerentscheidung):** TrueNAS-Betrieb (Tailscale als App oder auf dem Host, verschlüsseltes Dataset), Newsletter-Test: Ihr abonniert REWE-, ALDI-Nord- und Lidl-Newsletter in einem eigenen Postfach, nach 2 Wochen prüfen wir, wie gut sich daraus Lebensmittel-Angebote extrahieren lassen.

## 7. Ideen und Verbesserungsvorschläge
- **Build vs. Buy:** Mealie oder Tandoor decken Rezeptimport und Liste ab, kennen aber weder Makroziele pro Person, Laborwerte, Sättigung noch Angebote. Empfehlung: eigener schlanker Kern, Rezeptimport über `recipe-scrapers`. Phase 0 enthält einen kurzen Vergleich.
- **Ein Gericht, zwei Portionen:** Die App skaliert pro Person statt zwei Gerichte zu planen (Liesa mehr Gemüse und Volumen, Christian mehr Energie).
- **Hunger-Management:** Liesa kann in der App „heute viel Hunger“ markieren. Der Planer erhöht dann Volumen und Protein für die nächsten Tage und schlägt einen Snack vor.
- **Trainingstags-Logik:** Mehr Kohlenhydrate und Protein an Trainingstagen, aus den echten Workouts abgeleitet.
- **Reste und Vorrat:** Angebrochene Packungen und Reste in die Folgewoche übernehmen.
- **Rückblick:** Wöchentlich „geplant vs. gegessen vs. gekauft“, Gewichtstrend, Ersparnis und Makro-Treffer als Zahlen.
- **Laborverlauf:** Befunde über die Zeit vergleichen, sobald es Folgebefunde gibt.
- **Kassenbon-Scan** (spätere Option): echte Preise, präzisere Ersparnis.
- **Backup und Export:** Alle Daten als JSON exportierbar.
- **Haftung:** Die App gibt Orientierungswerte und keine medizinische oder ernährungstherapeutische Beratung. Mit hohem Trainingsumfang und Defizit ist es sinnvoll, Ziele und Fortschritt mit einer Ärztin/einem Arzt oder einer Ernährungsberatung abzustimmen.

## 8. Verifikation (für die spätere Umsetzung)
- **Phase 0:** Spike-Skripte laufen (Angebote für 01662, Import beider Exportformate, Laborbefund-PDF-Parser, Rezeptimport von 3+3 Seiten, Kurzbefehl legt Test-Items an, Compose-App läuft auf TrueNAS).
- **Phase 1:** Import beider Datensätze erzeugt dieselben Summen wie die Quelldateien (Stichprobe pro Messgröße), alle Laborwerte beider Befunde stimmen mit dem PDF überein, berechneter Energiebedarf passt zum Gewichtsverlauf.
- **Phase 2–3:** Unit-Tests für Zutaten-Normalisierung, Skalierung und Solver (Wochenplan hält Constraints, liegt im Makro-Korridor ±5–10 %, OMAD-Check und Sicherheitsgrenzen schlagen korrekt an, Sättigungsscore bevorzugt volumenreiche Gerichte).
- **Phase 4:** Zwei echte iPhones, Abhaken erscheint auf dem anderen Gerät in unter 2 s, Offline im Supermarkt, Tagesliste „Heute bei Lidl“ stimmt mit dem Plan überein.
- **Phase 5:** Ausgewiesene Ersparnis wird mit einem echten Kassenbon verglichen.
- **Ende-zu-Ende:** Eine Woche nach Plan einkaufen und kochen, Feedback zurück in die Präferenzen.

---

## Fortschritt

**Legende:** ✅ erledigt · 🔄 in Arbeit · ⬜ offen

### Planung
| Status | Aufgabe |
|---|---|
| ✅ | Anforderungen aufgenommen, Scope-Fragen gestellt und beantwortet (Runde 1 und 2) |
| ✅ | Architektur- und Phasenplan erstellt und freigegeben |
| ✅ | OMAD-Korrektur eingearbeitet (Slot-Modell) |
| ✅ | Antworten Runde 1 eingearbeitet (Läden, Server, Rezeptquellen, Frühstücks-Baukasten) |
| ✅ | Antworten Runde 2 eingearbeitet (Ziele, Labor freigegeben, Snacks, täglicher Lidl-Einkauf, TrueNAS 24.10.2.4) |
| ✅ | Christians Gesundheitsdaten und Befund ausgewertet |
| ✅ | Liesas Apple-Health-Export und (Teil-)Befund ausgewertet |
| ✅ | Rezeptquellen geprüft (JSON-LD vorhanden bei beiden Seiten) |
| ✅ | Persönliche Auswertung in `Health Daten/Auswertung.md` ausgelagert |
| ✅ | Antworten Runde 3 eingearbeitet (Historie/Supplemente per Chat-Export, Tempo, Aufnahme, Zyklus, Vorbereitungszeit, Planungshorizont) |
| ✅ | Chat-Export von Christian ausgewertet (Ernährungsregeln, Medikation, Trainingsplan) |
| ✅ | Offene Fragen Runde 4: Entscheidung, dass persönliche Werte und Regeln **in der App konfigurierbar** sind und nicht vorab geklärt werden müssen (Abschnitt 6) |
| ✅ | Plan final freigegeben, Phase 0 gestartet |

### Umsetzung
| Status | Phase |
|---|---|
| 🔄 | Phase 0 – Fundament & Spikes (Details: `docs/SPIKES.md`) |
| 🔄 | Phase 1 – Gesundheitsdaten & Profile (Spezifikation und Ergebnis: `docs/PHASE1.md`). **1a Backend ✅ abgenommen** (Datenmodell, Importer, Rechner, API, 330 Tests, Ende-zu-Ende mit echten Daten auf SQLite und Postgres). **1b Web-Oberfläche ⬜** (Einstellungen, Ziele, Supplemente, Regeln, Trainingsplan, Uploads, Dashboard) |
| ⬜ | Phase 2 – Rezeptbibliothek & Komponenten |
| ⬜ | Phase 3 – Planer v1 |
| ⬜ | Phase 4 – Einkaufsliste & PWA *(MVP)* |
| ⬜ | Phase 5 – Angebote |
| ⬜ | Phase 6 – Neue Rezepte & Lernen |
| ⬜ | Phase 7 – Politur & Betrieb |

### Änderungslog
| Datum | Änderung |
|---|---|
| 2026-10-04 | Erstfassung des Plans (Architektur, Phasen, Risiken, offene Fragen). |
| 2026-10-04 | Korrektur: Christian isst unter der Woche nur Frühstück (OMAD). Slot-Modell und Planer-Checks angepasst. |
| 2026-10-04 | Antworten Runde 1 eingearbeitet: PLZ 01662, Lidl/Aldi Nord/REWE, manueller Datenimport zuerst, pflegbare Vorlieben, Wochenend-Slots bestätigt, Frühstücks-Baukasten, Server (N100, TrueNAS SCALE, Tailscale), Rezeptquellen. |
| 2026-10-04 | Datenfunde ergänzt, persönliche Werte in `Health Daten/Auswertung.md` ausgelagert (nicht für Git). |
| 2026-10-05 | **Phase 1a (Backend) abgeschlossen.** 330 Tests grün. Ende-zu-Ende mit den echten Dateien über die HTTP-Schnittstelle gegen SQLite und Postgres 16: Importe (HAE 0,2 s, Apple-XML 1,3 GB in ca. 28 s), Laborbefunde, Zielwerte, Zugriffsschutz, Ablehnung eines Befunds mit falschem Geburtsdatum. Gefundene und behobene Fehler: Doppelzählung von Schritten über mehrere Quellen (Schritte ca. 35 % niedriger), Laborwerte mit zwei Einheiten, zu lange Texte in Postgres, Datum in JSON-Statistik. Neu: manuelle Gewichtseingabe (Vorrang), Wochenend-Slot-Anteile, Körpergröße aus HAE. Parallele Subagenten (Sonnet 5.5) für 6 der 8 Teile, alle vom Hauptagenten nachgeprüft. |
| 2026-10-05 | **Phase 1 gestartet.** Spezifikation `docs/PHASE1.md`. Fundament vom Hauptagenten: Datenmodell (12 Tabellen, Alembic-Migration gegen Postgres geprüft), gemeinsame Typen und Standardwerte, Bereinigung, Ingest-Service mit Import-Jobs (12 Tests). Fünf Sonnet-5.5-Agenten arbeiten parallel an HAE-Importer, Apple-Health-Importer (inkl. Behebung der Doppelzählung von Schritten über mehrere Quellen), Labor-Parser, Rechnern (Energie, Makros, Sicherheitsgrenzen, Slots) und Auth/CLI/CRUD-API. |
| 2026-10-05 | **Spike e, Stufe B bestanden:** Der Kurzbefehl holt die Liste vom Server und legt 8 Einträge an. Spike e ist damit abgeschlossen (Betrieb über Tailscale nach dem TrueNAS-Setup zu testen). |
| 2026-10-05 | **Spike e, Stufe A bestanden:** Der Kurzbefehl legt Einträge in der geteilten Erinnerungsliste an, Sync auf das zweite iPhone nach ca. 30 s, Abhaken synchronisiert. Zweiter Lauf erzeugt Duplikate: Phase 4 sendet nur neue Einträge (`exported_at` am Server). Testendpunkt liefert das fertige Feld `title`. Stufe B offen. |
| 2026-10-05 | Docker läuft lokal (WSL2). **Docker-Test bestanden:** Image baut, Compose-Stack startet, Postgres gesund, `/api/health` meldet `db: ok`, Python 3.12.15, nicht-privilegierter Benutzer, Alembic verbindet. Händlerseiten per Browser geprüft: keine Website-Nutzungsbedingungen bei Lidl/Aldi Nord gefunden (keine Erlaubnis), REWE blockiert. **Angebotsquellen neu geordnet:** Preisbasis pro Zutat (immer), Newsletter-Postfach per IMAP (automatisch), Prospekt-Upload nur optional. Erster lokaler Commit. |
| 2026-10-04 | **Phase 0 gestartet.** Git-Repo mit strenger `.gitignore` (`Health Daten/` ausgeschlossen), venv, Spikes b (Importer), c (Labor-PDF-Parser, 10 Tests grün), d (Rezeptimport 6/6) erfolgreich. **Spike a: Marktguru ist ein No-Go** (AGB verbieten automatisches Auslesen), Angebote kommen per Prospekt-Upload, Händler-AGB noch zu prüfen. Neuer Abschnitt 4a: Subagenten (Sonnet 5.5) für parallele Umsetzung. Docker lokal: WSL fehlt (siehe `docs/SPIKES.md`). Backend-Gerüst und Compose-Datei per Subagent erstellt und geprüft (Tests grün, Docker-Build ungetestet). Offen: Spike e (Kurzbefehl, Test auf iPhone), TrueNAS-Test, Docker-Build-Test. |
| 2026-10-04 | **Leitprinzip „Konfiguration statt Code“** ergänzt. Abschnitt 6 (offene Fragen) in eine Konfigurationstabelle mit Startwerten umgebaut, damit nichts Persönliches vorab geklärt oder hartcodiert werden muss. Planung gilt damit als abgeschlossen, wartet auf Freigabe für Phase 0. |
| 2026-10-04 | Antworten Runde 3 und Chat-Export eingearbeitet: harte Ernährungsregeln (Salz, Zink inkl. Supplement, Omega-3/Fisch, kein Kaliumsalz), Supplement-Tabelle, `nutrient_rule`, `training_plan` und Trainingsperiodisierung, Salzbilanz im Frühstücks-Baukasten, Kreatin-Gewichtsglättung, Platzhalter-Filter, Planungshorizont „ganze Woche optional“, Vorbereitung ≈ 30 Min. **Neu: Hinweis, dass 70 kg als alleinige Untergrenze für Christian nicht schützt** (Körperfett-Grenze vorgeschlagen). |
| 2026-10-04 | Antworten Runde 2 eingearbeitet: beide wollen abnehmen, Labordaten freigegeben (Befunde ausgewertet), Liesa braucht sättigende kalorienarme Gerichte (Sättigungsscore), Snack-Slot, täglicher Lidl-Einkauf (Tageslisten), Vorbereitung am Vorabend, Vorkochen optional, TrueNAS ElectricEel 24.10.2.4. Neu: Labor-Modul mit sanften Planzielen, adaptive Energiekalibrierung am Gewichtstrend, Sicherheitsgrenzen, Zyklus-Modul als Opt-in. |
