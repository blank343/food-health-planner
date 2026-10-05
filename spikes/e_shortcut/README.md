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

### Kurzbefehl anlegen
1. **Kurzbefehle**-App → oben rechts **+** → oben auf den Namen tippen → **Umbenennen** → `Einkauf Test A`.
2. **Aktion hinzufügen** → suchen: **Text** → in das Textfeld diesen JSON-Text einfügen (Text kopieren, in das Feld einfügen):
   ```
   {"items":[{"name":"Skyr","quantity":"500 g","note":""},{"name":"Haferflocken","quantity":"1 Packung","note":"kernig"},{"name":"Eier","quantity":"10 Stück","note":"Freiland"}]}
   ```
3. **Aktion hinzufügen** → **Wörterbuch abrufen aus Eingabe** (englisch: *Get Dictionary from Input*). Eingabe: das Ergebnis des Textes (wird automatisch verbunden).
4. **Aktion hinzufügen** → **Wert für Schlüssel in Wörterbuch abrufen**. Schlüssel: `items`. Eingabe: **Wörterbuch** aus Schritt 3 (blaues Feld antippen, Variable wählen).
5. **Aktion hinzufügen** → **Für jedes Element wiederholen**. Eingabe: **Wörterbuchwert** aus Schritt 4.
6. **Innerhalb** der Wiederholung (zwischen „Für jedes“ und „Ende der Wiederholung“):
   - **Wert für Schlüssel in Wörterbuch abrufen**, Schlüssel `name`, Eingabe **Wiederholungselement**.
   - **Wert für Schlüssel in Wörterbuch abrufen**, Schlüssel `quantity`, Eingabe **Wiederholungselement**.
   - **Neue Erinnerung hinzufügen**: im Feld **Erinnerung** erst die Variable *Wörterbuchwert* (name), dann ein Leerzeichen, dann die Variable *Wörterbuchwert 2* (quantity) eintragen. Beim Feld **Liste** `ZZ Test-Einkauf` wählen. Über **Mehr anzeigen** (Pfeil an der Aktion) siehst du weitere Felder (Notiz, Datum).
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
| Stufe A: 3 Einträge erscheinen in `ZZ Test-Einkauf` | ⬜ |
| Stufe A: Einträge erscheinen auf Liesas iPhone (nach wie vielen Sekunden?) | ⬜ |
| Stufe A: Abhaken auf Liesas Gerät erscheint bei dir | ⬜ |
| Stufe A: zweiter Lauf erzeugt Duplikate (erwartet) | ⬜ |
| Stufe B: Safari zeigt das JSON im WLAN | ⬜ |
| Stufe B: 8 Einträge werden angelegt | ⬜ |
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
