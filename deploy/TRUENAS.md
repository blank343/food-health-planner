# Food & Health Planner auf TrueNAS SCALE 24.10 (ElectricEel 24.10.2.4)

Anleitung, um das Backend (API + PostgreSQL) als **Custom App** per "Install via YAML" zu betreiben.
Alles, was nicht gegen eine echte 24.10.2.4-Installation geprüft wurde, ist mit **zu prüfen** markiert.
Der Compose-Stack und das Dockerfile sind bisher **nicht** mit Docker getestet.

## 0. Voraussetzungen

- TrueNAS SCALE 24.10.2.4 mit eingerichtetem Apps-Pool (Apps > Settings > Choose Pool).
- Ein Pool, hier `tank` genannt (an den eigenen Poolnamen anpassen).
- Ein Container-Image der API in einer Registry (siehe Abschnitt 2), weil der YAML-Dialog nicht bauen kann.
- Tailscale auf dem NAS oder als App, falls der Zugriff übers Tailnet laufen soll (Abschnitt 5).

## 1. Datasets anlegen

Datasets > Add Dataset:

1. Übergeordnet: `tank/apps` (existiert evtl. schon), darunter `tank/apps/foodhealth`.
2. Darunter `tank/apps/foodhealth/postgres` für die Datenbankdateien.

**Verschlüsselung:** Die Datenbank wird Gesundheitsdaten enthalten. Daher `tank/apps/foodhealth`
mit **Verschlüsselung** anlegen (Encryption aktivieren, Passphrase oder Key), sodass `postgres`
als Kind-Dataset erbt. Beachten: Ein verschlüsseltes Dataset muss nach jedem Neustart
entsperrt werden, sonst startet die App nicht (zu prüfen: Verhalten der Apps beim Boot mit
gesperrtem Dataset). Verschlüsselung lässt sich nachträglich nicht einfach für ein
bestehendes Dataset einschalten, deshalb gleich beim Anlegen entscheiden.

Dataset-Optionen für `postgres`: Compression lz4 (Standard). Record Size 8K bis 16K
passt zur PostgreSQL-Seitengröße von 8K (der beste Wert ist zu prüfen; der Standard von 128K funktioniert ebenfalls).

## 2. API-Image bereitstellen

Der Custom-App-YAML-Dialog unterstützt kein `build:`. Das Image muss daher auf einem
anderen Rechner gebaut werden (dort mit Docker):

```bash
cd backend
docker build -t ghcr.io/<dein-user>/foodhealth-api:0.1.0 .
docker push ghcr.io/<dein-user>/foodhealth-api:0.1.0
```

Hinweise:

- Das Image enthält keine Gesundheitsdaten (nur Code). Das Repository trotzdem **privat** halten.
- Bei privater Registry braucht TrueNAS Zugangsdaten (Registry-Login in den Apps-Einstellungen; genaue Stelle zu prüfen).
- Architektur: Das NAS ist vermutlich amd64. Auf ARM-Rechnern mit `--platform linux/amd64` bauen (zu prüfen).
- Das Dockerfile ist ungetestet; der erste Build kann Korrekturen erfordern.

## 3. Berechtigungen für PostgreSQL

Das Image `postgres:16-alpine` läuft mit dem Benutzer `postgres` mit **uid/gid 70**
(Debian-basierte Images nutzen 999, daher bewusst alpine).

**Variante A (empfohlen):** Datasets > `tank/apps/foodhealth/postgres` > Permissions > Edit:

- User und Group `70` (numerische ID; ob die UI eine nicht existierende ID direkt akzeptiert, ist zu prüfen).
- Mode `0700`. "Apply permissions recursively" nur nutzen, solange das Dataset leer ist.
- Falls das Dataset den ACL-Typ NFSv4 hat und die UI einen ACL-Editor zeigt: ACL-Typ **POSIX** wählen
  bzw. einen Eintrag für uid 70 mit Full Control setzen (zu prüfen, welcher Weg in 24.10 sauberer ist).

**Variante B:** Der offizielle Postgres-Entrypoint startet als root und setzt den Besitzer des
Datenverzeichnisses auf `postgres`, bevor er Rechte abgibt. Bei einem leeren Dataset kann es daher auch ohne
manuelle Rechte klappen. Bei ACL-Datasets kann das `chown` scheitern (zu prüfen). Bei Fehlern wie
`could not change permissions of directory` oder `Permission denied` im Log zurück zu Variante A.

## 4. Custom App per YAML installieren

1. Apps > Discover Apps > **Custom App** bzw. *Install via YAML*.
2. Name: `foodhealth`.
3. Inhalt von `deploy/docker-compose.yml` einfügen und anpassen:
   - Im Service `api`: Zeile `build: ../backend` **löschen**, die Zeile `image: ghcr.io/<dein-user>/foodhealth-api:0.1.0` aktivieren und anpassen.
   - `${FHP_DB_PATH:-./data/postgres}` ersetzen durch den absoluten Pfad `/mnt/tank/apps/foodhealth/postgres`.
   - `${FHP_DB_PASSWORD...}` ersetzen durch ein selbst erzeugtes alphanumerisches Passwort
     (z. B. `openssl rand -hex 24`). Dasselbe Passwort in `POSTGRES_PASSWORD` **und** in `FHP_DATABASE_URL`.
   - Ob der Dialog `${VAR}`-Ersetzung aus einer `.env`-Datei kennt, ist **zu prüfen**. Sicherer ist, alle `${...}`-Platzhalter durch feste Werte zu ersetzen.
   - Ob `depends_on` mit `condition: service_healthy` und `healthcheck` im Dialog akzeptiert werden, ist **zu prüfen** (es ist Standard-Compose, sollte also gehen).
4. Das YAML enthält danach das DB-Passwort im Klartext. Nicht in Git oder Chats weitergeben.
5. Port: Standard `8000`. Die TrueNAS-UI kennt für eigene Apps Port-Empfehlungen/-Reservierungen (häufig ab 9000);
   ob 8000 in 24.10 frei ist, ist **zu prüfen**. Bei Konflikt z. B. `9080:8000` verwenden und unten alle `8000` durch `9080` ersetzen.
6. Save / Deploy. Status in Apps > Installed beobachten; Logs über das Log-Symbol der App (beide Container prüfen).

Datenbank-Migrationen: Aktuell gibt es noch keine Modelle und keine Revisionen. Sobald es welche gibt
(Phase 1+), im api-Container `alembic upgrade head` ausführen (Shell der App); eine Automatisierung beim Start ist später zu entscheiden.

## 5. Zugriff übers Tailnet

Die API sollte **nicht** ins Internet oder ins normale LAN veröffentlicht werden. Zugriff per Tailscale:

**Variante A: Tailscale direkt auf dem TrueNAS-Host** (falls dort installiert/aktiviert):

```bash
tailscale serve --bg --https=443 http://127.0.0.1:8000
tailscale serve status
```

Voraussetzungen im Tailnet: MagicDNS und HTTPS-Zertifikate aktiviert (Admin-Konsole > DNS).
Die App ist dann unter `https://<nas-name>.<tailnet-name>.ts.net/` erreichbar.
Der Port wird auf allen Interfaces des Hosts veröffentlicht, `127.0.0.1:8000` sollte also vom Host aus erreichbar sein (zu prüfen).

**Variante B: Tailscale-App aus dem TrueNAS-Katalog:** Die App läuft in einem eigenen Container;
`127.0.0.1` zeigt dann auf diesen Container, **nicht** auf den Host. Als Ziel für `serve` dann
die LAN-IP des NAS und den veröffentlichten Port verwenden, z. B. `http://<nas-lan-ip>:8000` (zu prüfen).
Ob `serve` in der Katalog-App konfigurierbar ist, ist ebenfalls zu prüfen.

Wer nur über Tailscale zugreifen will, kann in der Compose-Datei `"127.0.0.1:8000:8000"` statt `"8000:8000"`
veröffentlichen, dann ist die API im LAN nicht direkt erreichbar. Das passt zu Variante A, nicht zu Variante B.

## 6. Prüfen

Vom Handy/Laptop im Tailnet (oder im LAN, falls offen):

```bash
curl https://<nas-name>.<tailnet-name>.ts.net/api/health
# oder direkt: curl http://<nas-lan-ip>:8000/api/health
```

Erwartet:

```json
{"status":"ok","env":"prod","db":"ok"}
```

- `"db":"unavailable"`: DB-Container läuft nicht oder noch nicht, falsches Passwort in `FHP_DATABASE_URL`, oder Rechte auf dem Dataset (siehe Abschnitt 3). Logs des `db`-Containers prüfen.
- Beispiel-Liste für den Apple-Shortcut-Test: `/api/spike/shopping-list.json` (Spike-Daten, werden in Phase 4 ersetzt).
- Interaktive API-Doku: `/docs`.

## 7. Snapshots und Backup

**Wichtig:** Ein ZFS-Snapshot eines laufenden Postgres-Datasets ist *crash-konsistent*. Postgres kann so
einen Snapshot normalerweise per WAL-Recovery wiederherstellen, aber es ist kein garantiert sauberes Backup.
Zusätzlich regelmäßig einen logischen Dump ziehen:

```bash
docker exec <db-container> pg_dump -U fhp -d fhp -Fc > /mnt/tank/apps/foodhealth/backup/fhp-$(date +%F).dump
```

(Containername mit `docker ps` herausfinden; Ziel am besten ein eigenes, ebenfalls verschlüsseltes Dataset
`tank/apps/foodhealth/backup`; Docker-CLI-Zugriff auf dem Host in 24.10 ist zu prüfen. Alternativ in der Shell des db-Containers
dumpen und die Datei über ein zusätzliches Volume ablegen.)

Snapshots einrichten: Data Protection > Periodic Snapshot Tasks > Add:

- Dataset `tank/apps/foodhealth` (rekursiv), z. B. täglich, Aufbewahrung 14 bis 30 Tage.
- Manueller Snapshot vor Updates: Datasets > Dataset wählen > Snapshots > Add.

Wiederherstellen: App stoppen, Snapshot zurückrollen (Rollback) oder auf einen Klon zeigen, App starten.
Gegen Hardware-Ausfall zusätzlich Replikation auf ein zweites System oder ein Cloud-Sync mit
Verschlüsselung; Gesundheitsdaten nie unverschlüsselt in fremde Clouds legen.

## 8. Updates

1. Neues Image bauen und mit neuem Tag pushen (z. B. `0.1.1`).
2. Vor dem Update einen Snapshot anlegen.
3. In der App den Image-Tag im YAML ändern und speichern; die App wird neu erstellt.
4. `/api/health` prüfen.

## Offene Punkte (zusammengefasst)

- Funktioniert `${VAR}`/`.env` im YAML-Dialog von 24.10.2.4?
- Ist Port 8000 für Custom Apps frei oder muss ein anderer Port gewählt werden?
- Dataset-ACL-Typ und Besitzerrechte für uid 70 (Weg über die UI).
- Verhalten der Apps nach Neustart bei gesperrtem verschlüsseltem Dataset.
- Registry-Login für ein privates Image in 24.10.
- Wie genau Tailscale (Host vs. Katalog-App) `serve` auf den veröffentlichten Port zeigt.
- Dockerfile und Compose-Datei insgesamt: bisher nie mit Docker gebaut oder gestartet.
