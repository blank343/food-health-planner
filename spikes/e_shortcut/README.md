# Spike e: Apple-Kurzbefehl legt Einkaufsliste in „Erinnerungen“ an

**Frage, die der Test beantwortet:** Kann ein Kurzbefehl Einträge aus einer JSON-Liste in eine **geteilte Erinnerungsliste** schreiben, sodass sie auf **beiden iPhones** erscheinen? Das geht nur auf einem iPhone, deshalb ist dies ein **manueller Test von dir**.

Der Test hat zwei Stufen. **Stufe A braucht keinen Server** und prüft den riskanten Teil (Erinnerungen und Teilen). **Stufe B** prüft zusätzlich den Abruf vom Server.

Dauer: Stufe A ca. 15 Minuten, Stufe B ca. 10 Minuten.

---

## Vorbereitung: eigene Testliste (damit eure echte Liste sauber bleibt)

1. **Erinnerungen**-App → unten rechts **Liste hinzufügen** → Name `ZZ Test-Einkauf` → **Fertig**.
2. Liste öffnen → oben rechts **…** (drei Punkte) → **Liste teilen** → Liesa hinzufügen (Nachrichten oder Link) → sie nimmt die Einladung auf ihrem iPhone an.
3. Prüfen: In Liesas Erinnerungen-App erscheint die Liste `ZZ Test-Einkauf`.

---

## Stufe A: Kurzbefehl mit eingebauten Testdaten (ohne Server)

> **Wichtig (gelernt im Test):** Im Titelfeld von *Add New Reminder* muss eine **Variable** stehen, erkennbar am kleinen orangen Symbol vor dem Namen. Normaler Text im Feld wird wörtlich als Titel angelegt. Variable einsetzen: Feld **leeren**, dann in der Leiste über der Tastatur **Dictionary Value** wählen.

> **Englische Oberfläche?** Die Aktionsnamen heißen dann: *Text* (Text), *Get Dictionary from Input* (Wörterbuch abrufen aus Eingabe), *Get Dictionary Value* (Wert für Schlüssel in Wörterbuch abrufen), *Repeat with Each* (Für jedes Element wiederholen), *Add New Reminder* (Neue Erinnerung hinzufügen), *Get Contents of URL* (Inhalt von URL abrufen). Zwischenprüfung: Nach der Aktion *Get Dictionary Value* mit Schlüssel `items` zeigt ▶ eine Vorschau mit 3 Einträgen.
### Kurzbefehl anlegen
1. **Kurzbefehle**-App → oben rechts **+** → oben auf den Namen tippen → **Umbenennen** → `Einkauf Test A`.
2. **Aktion hinzufügen** → suchen: **Text** → in das Textfeld diesen JSON-Text einfügen (Text kopieren, in das Feld einfügen):
   ```
   {"items":[{"title":"Skyr 500 g","note":""},{"title":"Haferflocken 1 Packung","note":"kernig"},{"title":"Eier 10 Stück","note":"Freiland"}]}
   ```
3. **Aktion hinzufügen** → **Wörterbuch abrufen aus Eingabe** (englisch: *Get Dictionary from Input*). Eingabe: das Ergebnis des Textes (wird automatisch verbunden).
4. **Aktion hinzufügen** → **Wert für Schlüssel in Wörterbuch abrufen**. Schlüssel: `items`. Eingabe: **Wörterbuch** aus Schritt 3 (blaues Feld antippen, Variable wählen).
5. **Aktion hinzufügen** → **Für jedes Element wiederholen**. Eingabe: **Wörterbuchwert** aus Schritt 4.
6. **Innerhalb** der Wiederholung (zwischen „Für jedes“ und „Ende der Wiederholung“), **zwei** Aktionen:
   - **Wert für Schlüssel in Wörterbuch abrufen** (*Get Dictionary Value*), Schlüssel `title`, Eingabe **Wiederholungselement** (*Repeat Item*).
   - **Neue Erinnerung hinzufügen** (*Add New Reminder*): Das Titelfeld ist ein Variablenfeld. Tippe darauf und wähle **Wörterbuchwert** (*Dictionary Value*) aus der Liste. Beim Feld **Liste** `ZZ Test-Einkauf` wählen.
   - Hinweis: Der Titel kommt bewusst **fertig** aus dem JSON (`title`, z. B. „Skyr 500 g“), weil sich im Titelfeld keine mehreren Variablen mischen lassen.
7. **Fertig** antippen.

### Ausführen und prüfen
1. Kurzbefehl `Einkauf Test A` antippen (▶). Beim ersten Mal **Erlauben** für den Zugriff auf Erinnerungen.
2. Erinnerungen-App → Liste `ZZ Test-Einkauf` → es müssen **3 Einträge** stehen (Skyr 500 g, Haferflocken 1 Packung, Eier 10 Stück).
3. Auf **Liesas iPhone** nachsehen: Erscheinen die 3 Einträge dort? Wie lange dauert es (Sekunden)?
4. **Abhaken** auf Liesas Gerät: Wird es auf deinem sichtbar?
5. Kurzbefehl ein **zweites Mal** ausführen: Es entstehen vermutlich **doppelte Einträge** (das ist erwartet, die App muss später nur neue Einträge senden).

---

## Stufe B: Liste vom Server holen

Der Server liefert bereits einen Testendpunkt: `GET /api/spike/shopping-list.json` (8 Beispieleinträge im selben Format).

### Server starten (auf deinem PC)
In einem Terminal im Projektordner:
```powershell
.venv\Scripts\python -m uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port 8765
```
Windows fragt nach Firewall-Freigabe: **Private Netzwerke zulassen** (nicht öffentliche).

### Adresse herausfinden
1. Terminal: `ipconfig` → bei deinem WLAN-/LAN-Adapter die **IPv4-Adresse** (z. B. `192.168.x.y`).
2. Das iPhone muss **im selben WLAN** sein (Tailscale ist für diese Variante nicht nötig).
3. Test im iPhone-Safari: `http://192.168.x.y:8765/api/spike/shopping-list.json` öffnen → es erscheint JSON.
   - Erscheint nichts: PC-Firewall prüfen, oder WLAN mit „Client-Isolation“ (Gästenetz) ausschließen.

### Kurzbefehl B anlegen
1. Kurzbefehl `Einkauf Test A` **duplizieren** (lange drücken → Duplizieren) → umbenennen in `Einkauf Test B`.
2. Die ersten beiden Aktionen (**Text** und **Wörterbuch abrufen aus Eingabe**) **löschen** und ersetzen durch **Inhalt von URL abrufen**:
   - URL: `http://192.168.x.y:8765/api/spike/shopping-list.json`
   - Methode: GET.
3. Die Aktion **Wert für Schlüssel items** bekommt als Eingabe jetzt **Inhalt von URL**.
4. Ausführen und wie in Stufe A prüfen (hier 8 Einträge).

### Später (Betrieb auf dem Server)
- Statt der lokalen IP verwendest du die **Tailscale-Adresse des Servers** (z. B. `https://<servername>.<tailnet>.ts.net/api/…`). Tailscale muss dann auf dem iPhone **verbunden** sein. Der Kurzbefehl funktioniert dadurch auch unterwegs.
- Zeigt iOS einen Fehler bei `http://`, nimm für den Test `https` über Tailscale (`tailscale serve`).

---

## Automation testen (optional)
**Kurzbefehle** → Reiter **Automation** → **+** → **Tageszeit** → z. B. 16:00, **Wochentage** Mo–Fr → **Weiter** → Aktion **Kurzbefehl ausführen** → `Einkauf Test B` → **Weiter** → **Sofort ausführen** aktivieren → **Fertig**. Am nächsten Tag prüfen, ob die Einträge zur Uhrzeit erscheinen. Danach die Automation wieder **löschen**.

---

## Ergebnisse eintragen
| Prüfpunkt | Ergebnis |
|---|---|
| Stufe A: 3 Einträge erscheinen in der Testliste | ✅ (2026-10-05) |
| Stufe A: Einträge erscheinen auf Liesas iPhone | ✅ nach ca. 30 Sekunden (iCloud-Sync, nicht beeinflussbar) |
| Stufe A: Abhaken auf Liesas Gerät erscheint bei dir | ✅ |
| Stufe A: zweiter Lauf erzeugt Duplikate (erwartet) | ✅ bestätigt: Einträge werden dupliziert |
| Stufe B: Server vom iPhone im WLAN erreichbar | ✅ |
| Stufe B: 8 Einträge werden angelegt | ✅ (2026-10-05) |
| Dauer bei ca. 30 Einträgen (optional: Testdaten verlängern) | ⬜ |
| Automation läuft ohne Rückfrage zur Uhrzeit (optional) | ⬜ |

**Danach aufräumen:** Liste `ZZ Test-Einkauf` löschen, Automation löschen, den PC-Server mit `Strg+C` beenden.

## Wenn etwas nicht klappt
- **Keine Einträge entstehen:** Kurzbefehl einzeln durchgehen (Schritt für Schritt antippen), die Ergebnisvorschau jeder Aktion zeigt, wo es hakt (meist ist die Variable in einem Feld falsch gewählt).
- **„Zugriff auf Erinnerungen“ fehlt:** iOS **Einstellungen → Kurzbefehle → Erinnerungen** erlauben.
- **Schlüssel nicht gefunden:** Schlüsselnamen exakt klein schreiben (`items`, `name`, `quantity`).

## Was wir daraus ableiten
- Die PWA bleibt die **Quelle der Wahrheit**, die Erinnerungen sind nur eine Kopie. Der Kurzbefehl sollte später nur **neue** Einträge anlegen (Phase 4: `?since=` oder „nur offene Artikel“).
- Erinnerungen lassen sich per Kurzbefehl **hinzufügen**, aber nicht zuverlässig als „erledigt“ zurückspielen. Abgehakt wird in der PWA.
- Fällt Stufe A durch (kein Teilen/Sync wie erwartet), bleibt die eigene PWA-Liste die einzige Liste, und der Export entfällt.

## Ergebnis Stufe A (2026-10-05): bestanden
- Der Kurzbefehl legt Einträge aus JSON in einer geteilten Liste an. Sie erscheinen nach ca. 30 Sekunden auf dem zweiten iPhone, Abhaken wird synchronisiert.
- **Ein zweiter Lauf erzeugt Duplikate.** Das muss die App lösen (Entscheidung für Phase 4):
  - **Server merkt sich den Export:** Jeder Eintrag bekommt `exported_at`. Der Endpunkt liefert nur Einträge **ohne** `exported_at` und setzt es beim Abruf (ein Abruf pro Einkaufstermin genügt, beide iPhones teilen sich ja die Liste).
  - **Kurzbefehl prüft selbst:** *Find Reminders* in der Liste nach dem Titel, nur anlegen, wenn nichts gefunden wird. Das ist robuster, wenn Einträge von Hand gelöscht werden, braucht aber mehr Aktionen.
  - Empfehlung: erst die Server-Variante, bei Bedarf plus die Prüfung im Kurzbefehl.
- Der Export ist eine **Einbahnstraße** (App → Erinnerungen). Das Abhaken in den Erinnerungen kommt nicht zurück in die App, abgehakt wird in der PWA.

## Ergebnis Stufe B (2026-10-05): bestanden
- Der Kurzbefehl holt die Liste per `Get Contents of URL` (HTTP, lokales Netz) von `GET /api/spike/shopping-list.json` und legt alle 8 Einträge in der geteilten Liste an.
- Stolperstein: Nach dem Austausch der ersten Aktionen zeigte die Variable in *Get Dictionary Value* rot auf die gelöschte Aktion. Die Eingabe muss auf **Contents of URL** umgestellt werden.
- **Offen für den Betrieb:** Auf dem Server läuft der Abruf über die Tailscale-Adresse (HTTPS, `tailscale serve`). Tailscale muss dann auf dem iPhone verbunden sein. Das ist mit TrueNAS zu testen.
