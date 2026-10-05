# Food Health Planner auf TrueNAS SCALE 24.10 (ElectricEel 24.10.2.4)

Betrieb als **Custom App** per „Install via YAML“ (zwei Container: API mit Oberfläche und PostgreSQL).
Das Image kommt aus der **GitHub Container Registry (ghcr.io)**, gebaut von GitHub Actions aus dem privaten Repo.
Stellen, die noch nicht gegen eine echte 24.10.2.4-Installation geprüft wurden, sind mit **zu prüfen** markiert.

**Bereits getestet (lokal):** Das Image baut, die Datenbank-Migration läuft beim Start automatisch, die CLI im Container
funktioniert, ein Neustart ist idempotent. **Noch nie gelaufen:** der GitHub-Workflow und alles auf TrueNAS.

## 1. Überblick

```
GitHub (privates Repo) --Actions--> ghcr.io/<owner>/food-health-planner:<version>   (privates Image)
                                              |
TrueNAS: Custom App "food-health-planner" ----+   Container api (Port 9180 -> 8000) + db (Postgres 16)
Daten:   /mnt/vm-storage/apps/food-health-planner/postgres   (dein Dataset)
Zugriff: nur über Tailscale vom iPhone/Laptop
```

Das Image enthält nur Code und die gebaute Oberfläche, **keine Gesundheitsdaten** (`.dockerignore` schließt sie aus).

## 2. Einmalige Vorbereitung auf TrueNAS

Angelegt sind: `vm-storage/apps/food-health-planner` und darunter `postgres`.

1. **Besitzer für PostgreSQL setzen.** Das Image `postgres:16-alpine` läuft als Benutzer mit **uid/gid 70**.
   In der TrueNAS-Shell (System > Shell oder SSH):
   ```bash
   sudo chown -R 70:70 /mnt/vm-storage/apps/food-health-planner/postgres
   sudo chmod 700 /mnt/vm-storage/apps/food-health-planner/postgres
   ```
   Bei einem Dataset mit NFSv4-ACL kann das `chown` allein nicht reichen (**zu prüfen**). Erscheint im Log des
   `db`-Containers „Permission denied“ oder „could not change permissions“, dann in der UI unter
   Datasets > `postgres` > Permissions den ACL-Typ auf **POSIX** stellen und den Besitzer 70 setzen.
2. **Verschlüsselung:** Die Datenbank enthält Gesundheitsdaten. Prüfe unter Datasets, ob
   `vm-storage/apps/food-health-planner` verschlüsselt ist (Schloss-Symbol). Falls nicht: ein verschlüsseltes
   Dataset lässt sich nicht nachträglich für ein bestehendes einschalten, du müsstest ein neues anlegen und umziehen.
   Bedenke, dass ein verschlüsseltes Dataset nach jedem Neustart entsperrt werden muss, sonst startet die App nicht
   (**zu prüfen:** Verhalten der Apps beim Boot).
3. **Zugangsdaten für das private Image** (siehe Abschnitt 3, letzter Schritt).

## 3. GitHub: Repo, Image, Zugang

1. **Privates Repo** auf GitHub anlegen und den Code pushen (`Health Daten/` ist per `.gitignore` ausgeschlossen).
2. **Image bauen lassen:** Der Workflow `.github/workflows/build.yml` testet bei jedem Push und baut das Image bei einem
   Versions-Tag:
   ```bash
   git tag v0.1.0
   git push origin v0.1.0
   ```
   Danach liegt das Image unter `ghcr.io/<github-name>/food-health-planner:0.1.0` (GitHub > Repo > Packages).
   Es ist **privat** und mit dem Repo verknüpft.
3. **Lesezugriff für TrueNAS:** GitHub > Settings > Developer settings > Personal access tokens > *Tokens (classic)* >
   Berechtigung nur **`read:packages`**, möglichst kurze Laufzeit. Dann in der TrueNAS-Shell:
   ```bash
   sudo docker login ghcr.io -u <github-name>
   # Passwort: das Token einfügen (wird nicht angezeigt)
   ```
   Der Login steht danach in `/root/.docker/config.json`. Ob er Neustarts und TrueNAS-Updates übersteht, ist **zu prüfen**.
   **Ausweg ohne Login:** Das Paket unter GitHub > Packages > Package settings auf **Public** stellen. Es enthält nur
   Code, keine Gesundheitsdaten und keine Zugangsdaten.

## 4. App installieren

1. TrueNAS > Apps > Discover Apps > **Custom App** > *Install via YAML*, Name `food-health-planner`.
2. Inhalt von `deploy/truenas-app.yaml` einfügen und anpassen:
   - **Passwort** an **beiden** Stellen (`POSTGRES_PASSWORD` und in `FHP_DATABASE_URL`) durch dasselbe,
     selbst erzeugte Passwort aus Buchstaben und Ziffern ersetzen (`openssl rand -hex 16`).
   - **Image-Tag** auf die veröffentlichte Version setzen.
   - Port `9180` ist ein Vorschlag (TrueNAS belegt Ports unter 9000 häufig selbst). Bei Konflikt anderen wählen.
3. Speichern. Status unter Apps > Installed, Logs über das Log-Symbol (beide Container prüfen).
   Beim ersten Start legt die API die Tabellen selbst an (Migration), das dauert einige Sekunden.
4. Das YAML enthält das Passwort im Klartext: nicht in Git, nicht in Chats.

## 5. Erster Start: Personen anlegen

Containernamen herausfinden und die Verwaltungs-CLI im API-Container ausführen (TrueNAS-Shell):

```bash
sudo docker ps --format '{{.Names}}'          # z. B. ix-food-health-planner-api-1 (zu prüfen)
sudo docker exec -it <api-container> python -m app.cli create-person --name <Name> --sex m --birth 1990-01-01
sudo docker exec -it <api-container> python -m app.cli create-person --name <Name2> --sex f --birth 1992-02-02
```

Jede Person bekommt **einmalig** ein Zugangstoken angezeigt. Sicher aufbewahren (z. B. Passwortmanager), nicht in
Chats weitergeben. Mit `rotate-token --name <Name>` lässt sich ein neues erzeugen. Das Token gibst du auf dem
Anmeldebildschirm der App ein.

Danach in der App: Importe (Health Auto Export, Apple Health, Laborbefund), unter „Tagesziel“ das aktuelle Gewicht
eintragen, unter „Einstellungen“ Ziele und Grenzen pflegen.

## 6. Zugriff über Tailscale

Die App sollte **nicht** ins Internet oder ins normale LAN veröffentlicht werden.

- **Schnelltest:** `http://<tailscale-name-des-NAS>:9180` vom Handy (Tailscale an). Funktioniert ohne HTTPS.
- **Mit HTTPS (empfohlen für die App auf dem Homescreen):** Tailscale-HTTPS-Zertifikate und MagicDNS müssen im
  Tailnet aktiviert sein (Admin-Konsole > DNS). Dann auf dem Host:
  ```bash
  sudo tailscale serve --bg --https=443 http://127.0.0.1:9180
  sudo tailscale serve status
  ```
  Erreichbar unter `https://<nas-name>.<tailnet>.ts.net/`. Das gilt, wenn Tailscale **direkt auf dem TrueNAS-Host**
  läuft. Läuft es als **Katalog-App** in einem Container, zeigt `127.0.0.1` auf diesen Container, dann als Ziel die
  LAN-IP des NAS nehmen (`http://<nas-lan-ip>:9180`); ob `serve` dort konfigurierbar ist, ist **zu prüfen**.
- Soll der Port im LAN nicht direkt offen sein, in der YAML `"127.0.0.1:9180:8000"` statt `"9180:8000"` verwenden
  (passt zu Tailscale auf dem Host, nicht zur Katalog-App).

## 7. Prüfen

```bash
curl http://<nas>:9180/api/health
# erwartet: {"status":"ok","env":"prod","db":"ok"}
```

- `"db":"unavailable"`: DB-Container läuft nicht, falsches Passwort in `FHP_DATABASE_URL`, oder Rechte auf dem
  Dataset (Abschnitt 2). Log des `db`-Containers prüfen.
- Container `api` startet immer wieder neu und das Log zeigt „Datenbank-Migration nach 30 Versuchen fehlgeschlagen“:
  gleiche Ursachen wie oben.
- Interaktive API-Dokumentation: `/docs`.
- Beispiel-Liste für den Kurzbefehl-Test: `/api/spike/shopping-list.json` (Spike-Daten, wird in Phase 4 ersetzt).

## 8. Snapshots und Backup

Ein ZFS-Snapshot eines laufenden Postgres-Datasets ist *crash-konsistent*, normalerweise per WAL-Recovery
wiederherstellbar, aber kein garantiert sauberes Backup. Zusätzlich regelmäßig einen logischen Dump ziehen:

```bash
sudo docker exec <db-container> pg_dump -U fhp -d fhp -Fc > /mnt/vm-storage/apps/food-health-planner/backup/fhp-$(date +%F).dump
```

(Ordner `backup` vorher anlegen, am besten in einem ebenfalls verschlüsselten Dataset; Docker-CLI-Zugriff auf dem Host
ist **zu prüfen**.) Snapshots: Data Protection > Periodic Snapshot Tasks > Dataset
`vm-storage/apps/food-health-planner` (rekursiv), z. B. täglich, 14 bis 30 Tage Aufbewahrung. Vor jedem Update zusätzlich
einen manuellen Snapshot. Gesundheitsdaten nie unverschlüsselt in fremde Clouds legen.

Wiederherstellen: App stoppen, Snapshot zurückrollen (oder Dump mit `pg_restore` einspielen), App starten.

## 9. Updates

1. Code ändern, Tests laufen lassen, committen, neuen Tag pushen (`git tag v0.1.1 && git push origin v0.1.1`).
2. Warten, bis der Workflow grün ist und das Image unter Packages erscheint.
3. Snapshot des Datasets anlegen.
4. In TrueNAS die App bearbeiten, den Image-Tag in der YAML ändern, speichern. Die API startet neu und führt
   neue Datenbank-Migrationen selbst aus.
5. `/api/health` prüfen. Bei Problemen alten Tag eintragen (bei Migrationen ggf. Snapshot zurückrollen).

## Offene Punkte (zu prüfen)

- GitHub-Workflow: bisher nie gelaufen.
- Besitzerrechte für uid 70 auf dem Dataset (ACL-Typ) und Verschlüsselungsstatus des Datasets.
- Bleibt der `docker login` für ghcr.io nach Neustart und TrueNAS-Update erhalten?
- Containername der API (`docker ps`) und Docker-CLI-Zugriff auf dem Host in 24.10.2.4.
- Tailscale: direkt auf dem Host oder als Katalog-App (bestimmt, worauf `serve` zeigt).
- Verhalten der Apps beim Boot mit gesperrtem verschlüsseltem Dataset.
