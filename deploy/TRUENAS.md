# Food Health Planner auf TrueNAS SCALE 24.10 (ElectricEel 24.10.2.4)

Betrieb als **Custom App** per „Install via YAML“ (zwei Container: API mit Oberfläche und PostgreSQL).
Das Image kommt aus der **GitHub Container Registry (ghcr.io)**, gebaut von GitHub Actions aus dem privaten Repo.
Stellen, die noch nicht gegen eine echte 24.10.2.4-Installation geprüft wurden, sind mit **zu prüfen** markiert.

**Bereits getestet:** Das Image baut lokal und auf GitHub (Version `0.1.0` ist unter `ghcr.io/blank343/food-health-planner`
veröffentlicht), die Datenbank-Migration läuft beim Start automatisch, die CLI im Container funktioniert, ein Neustart ist
idempotent, die Tests laufen grün in GitHub Actions. **Noch nie gelaufen:** alles auf TrueNAS selbst.

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
2. **Verschlüsselung:** Das Dataset ist bewusst **nicht verschlüsselt** (privater Homeserver ohne Zugriff von außen).
   Das hat einen praktischen Vorteil: Die App startet nach einem Neustart ohne Entsperren. Der Preis: Die Datenbank
   mit den Gesundheitsdaten liegt im Klartext auf der Platte, und auch Snapshots und Backups sind dann unverschlüsselt.
   Deshalb Backups nie unverschlüsselt in fremde Clouds legen (Abschnitt 8) und das Dataset nicht per SMB/NFS teilen.
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

## 6. Zugriff über Tailscale (Katalog-App)

Die App sollte **nicht** ins Internet oder ins normale LAN veröffentlicht werden.

- **Erster Test:** Vom iPhone (Tailscale an) `http://<tailscale-name-oder-ip-des-NAS>:9180` öffnen. Das klappt, wenn du die
  anderen Dienste auf dem NAS genauso erreichst (Port 9180 ist auf dem Host veröffentlicht). Funktioniert ohne HTTPS.
- **Mit HTTPS (empfohlen für die App auf dem Homescreen, später für Offline-Betrieb nötig):** Im Tailnet müssen
  **MagicDNS** und **HTTPS-Zertifikate** aktiviert sein (Admin-Konsole > DNS). Da Tailscale als Katalog-App in einem
  eigenen Container läuft, zeigt `127.0.0.1` dort auf diesen Container. Als Ziel für `serve` deshalb die LAN-IP des NAS
  verwenden (TrueNAS-Shell):
  ```bash
  sudo docker ps --format '{{.Names}}' | grep -i tailscale          # Name des Tailscale-Containers
  sudo docker exec <tailscale-container> tailscale serve --bg --https=443 http://<nas-lan-ip>:9180
  sudo docker exec <tailscale-container> tailscale serve status
  ```
  Erreichbar dann unter `https://<nas-name>.<tailnet>.ts.net/`. Ob `serve` in der Katalog-App dauerhaft bleibt
  (nach Neustart oder App-Update) und ob der Container den NAS-Host unter der LAN-IP erreicht, ist **zu prüfen**.
  Wenn `serve` Port 443 schon für einen anderen Dienst nutzt, einen anderen HTTPS-Port wählen (`--https=8443`).
- In der YAML bleibt `"9180:8000"`, weil der Tailscale-Container den Port über die LAN-IP des NAS erreichen muss.
  Ein direkter Zugriff aus dem LAN ist damit ebenfalls möglich; falls das nicht gewollt ist, am Router/Firewall sperren.

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

- Besitzerrechte für uid 70 auf dem Dataset (ACL-Typ). Das `chown` ist ausgeführt, ob es reicht, zeigt der erste Start.
- Bleibt der `docker login` für ghcr.io nach Neustart und TrueNAS-Update erhalten?
- Containername der API (`docker ps`) und Docker-CLI-Zugriff auf dem Host in 24.10.2.4.
- Tailscale-Katalog-App: Container-Name, ob `serve` dauerhaft bleibt, ob der Container die NAS-LAN-IP erreicht.
