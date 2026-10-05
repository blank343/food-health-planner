# Phase 0: Ergebnisse der Spikes

Stand: 2026-10-05. Enthält **keine persönlichen Messwerte**, nur technische Ergebnisse.

| Spike | Ergebnis | Status |
|---|---|---|
| **a** Angebotsquelle für PLZ 01662 | **Marktguru ist ein No-Go**: Die AGB (Ziff. 4.e) verbieten den Einsatz von Programmen zum automatischen Auslesen von Daten, die kommerzielle Nutzung ist ebenfalls eingeschränkt. Es wurde **kein** Abruf der Marktguru-Schnittstelle durchgeführt. Händlerseiten (geprüft anhand der von dir genannten Prospekt-Links): **Lidl** zeigt Prospekte nur als eingebetteten Online-Blätterviewer ohne PDF-Download, im Footer stehen nur AGB für den Onlineshop, Datenschutz, Impressum und Widerruf, **keine Nutzungsbedingungen der Website**. **Aldi Nord**: Blätterviewer, die Seite lieferte kaum Inhalt, keine Rechtstexte lesbar. **REWE**: blockiert den automatischen Abruf (HTTP 403). Eine Erlaubnis zum automatischen Auslesen ist bei **keinem** der drei belegt. `robots.txt` von REWE erlaubt zwar Angebotsseiten, ersetzt aber keine Nutzungsbedingungen. Bestätigt mit dem Browser (2026-10-05): Auf lidl.de und aldi-nord.de gibt es im Footer bzw. auf der Startseite **keine** Nutzungsbedingungen der Website (Lidl nur Onlineshop-AGB). Fehlende Bedingungen sind aber **keine Erlaubnis**. **Automatische Alternative ohne Händlerseiten-Abruf:** Newsletter-Postfach (REWE: E-Mail und WhatsApp, ALDI Nord: E-Mail, Lidl: Newsletter), dazu eine **Preisbasis pro Zutat**. Prospekt-Upload bleibt optional. | ✅ geklärt: kein automatischer Abruf, Prospekt-Upload |
| **b** Import beider Exportformate | Beide Importer laufen auf den echten Dateien. Health-Auto-Export-ZIP: 0,5 s, ca. 25 MB RAM. Apple-Health-XML (1,3 GB): 45 s, Peak ca. 300 MB RAM (Streaming-Parser). Platzhalter-Gewichte werden erkannt und entfernt, Ausreißer gefiltert. Einheiten (kJ → kcal, Körperfett-Bruchteil → %) normalisiert. Code: `spikes/b_import/`. | ✅ |
| **c** Laborbefund-PDF-Parser | Beide Befunde (Labor Staber) werden mit `pdfplumber` gelesen: 56 bzw. 55 Analyte, Kopfdaten, L/H-Markierungen, Referenzbereiche (Bereich, `<`, `>`), Operatoren am Wert (`>45.4`) und ausstehende Werte („folgt“, 9 beim Teilbefund) korrekt erkannt. Stolperstein: `pdfplumber` klebt die Markierung teils an den Wert („H47“), wird beim Parsen getrennt. Code: `spikes/c_labpdf/`. | ✅ |
| **d** Rezeptimport | `recipe-scrapers` 15.12: **6 von 6 Rezepten** importiert. emmikochteinfach.de wird nativ unterstützt (Kalorien und Makros vollständig), einfachkochen.de über den schema.org-Fallback (Nährwerte bei 1 von 3 Rezepten leer). Salz und Ballaststoffe liefert keine Seite. Zutaten sind Freitext (z. B. „1 Einheit Suppengrün: …“) und müssen normalisiert werden. Makros kommen wie geplant aus den Zutaten. Code: `spikes/d_recipes/`. | ✅ |
| **e** Kurzbefehl → Erinnerungen | **Stufe A bestanden (2026-10-05):** Der Kurzbefehl legt Einträge aus JSON in der geteilten Liste an, sie erscheinen nach ca. 30 s auf dem zweiten iPhone, Abhaken synchronisiert. Ein zweiter Lauf erzeugt **Duplikate**, die App muss nur neue Einträge senden (Server merkt sich `exported_at`). Stolperstein: Im Titelfeld muss eine Variable stehen, kein Text, deshalb liefert der Server das fertige Feld `title`. **Stufe B bestanden (2026-10-05):** Der Kurzbefehl holt die Liste von meinem Testserver im WLAN und legt 8 Einträge an. Für den Betrieb bleibt der Abruf über die Tailscale-Adresse des Servers zu testen (nach TrueNAS-Setup). | ✅ |
| Backend-Gerüst und Compose | FastAPI-Gerüst (`backend/`) mit `/api/health` und dem Testendpunkt `/api/spike/shopping-list.json`, Alembic, Dockerfile, `deploy/docker-compose.yml` (api + Postgres 16). Gerüst von einem Subagenten (Sonnet 5.5) erstellt und vom Hauptagenten geprüft. **Docker-Test lokal bestanden (2026-10-05, Docker 29.8.1 auf WSL2):** Image baut, beide Container laufen, Postgres „healthy“, `/api/health` meldet `db: ok` (echte Verbindung), Image nutzt **Python 3.12.15** und einen **nicht-privilegierten Benutzer**, Alembic verbindet sich mit der DB. Test mit Wegwerf-Volume und Test-Passwort, danach vollständig aufgeräumt. Noch offen: Bind-Mount auf dem ZFS-Dataset (nur auf dem Server testbar). | ✅ |
| TrueNAS-Betrieb | `deploy/TRUENAS.md` liegt vor (Datasets, Custom App per YAML, `tailscale serve`, Snapshots). Unsichere Punkte sind dort als „zu prüfen“ markiert, u. a. `.env`-Ersetzung im YAML-Dialog, Rechte für die Postgres-Daten, Verhalten bei gesperrtem verschlüsselten Dataset, Registry für das api-Image. **Test auf dem Server steht aus.** | ⬜ wartet auf Test |

## Docker lokal (Windows 11 Home, AMD Ryzen 5 3600)
**Gelöst (2026-10-05):** Nach Aktivierung der Windows-Komponente „Plattform für virtuelle Computer“ und einem echten Neustart läuft Docker Desktop (29.8.1) mit WSL2. Die folgende Analyse bleibt als Hintergrund stehen.

**Befund (2026-10-05, nach `wsl --install --no-distribution`):**
- Firmware-Virtualisierung (SVM): **aktiviert**. Hypervisor: **läuft** (Windows nutzt ihn für „Virtualisierungsbasierte Sicherheit“).
- WSL 3.0.1 ist installiert, aber `wsl --status` meldet: **„WSL2 is unable to start since virtualization is not enabled … ensure the ‚Virtual Machine Platform‘ optional component is enabled“**. Die Windows-Komponente **Plattform für virtuelle Computer ist also noch nicht aktiv** (oder ein Neustart steht aus). Das Docker-Backend läuft deshalb nicht.
- Dass keine WSL-Distribution installiert ist, ist für Docker Desktop **normal** (es legt seine eigene an).

**Behebung (Administrator-PowerShell), danach echter Neustart (nicht „Herunterfahren“, wegen Schnellstart):**
```powershell
dism.exe /online /enable-feature /featurename:VirtualMachinePlatform /all /norestart
dism.exe /online /enable-feature /featurename:Microsoft-Windows-Subsystem-Linux /all /norestart
bcdedit /set hypervisorlaunchtype auto
Restart-Computer
```
Danach prüfen (normale PowerShell):
```powershell
wsl --status      # darf keine Meldung zur Virtualisierung mehr zeigen
wsl --update
```
Dann Docker Desktop neu starten. Hilft das nicht: „Windows-Features aktivieren oder deaktivieren“ öffnen und prüfen, dass **Plattform für virtuelle Computer** und **Windows-Subsystem für Linux** angehakt sind, außerdem im Docker-Desktop-Menü *Settings → General → Use the WSL 2 based engine* aktiv lassen.

- **Nicht blockierend:** Der Betrieb läuft später auf TrueNAS. Lokal reicht für die Entwicklung die Python-Umgebung (`.venv`), Docker ist nur für Build-Tests des Images nötig.
## Erkenntnisse für die Planung
- Die **Preisbasis pro Zutat** und ein **Newsletter-Postfach** (IMAP, nur lesend) ersetzen die ursprüngliche Marktguru-Annahme (Phase 5). Der Prospekt-Upload bleibt optional, damit niemand wöchentlich hochladen muss. Offen: Test mit 2 Wochen gesammelter Newsletter.
- Der **Importer für Apple-Health-XML** muss im Streaming laufen und Platzhalter/Ausreißer filtern. Beides ist im Spike nachgewiesen.
- **Nährwerte aus Rezeptseiten** sind lückenhaft: Zutaten-Normalisierung und eine Nährwertdatenbank sind Pflicht (Phase 2).
