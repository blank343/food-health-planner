# Spike f: Newsletter-Postfach als Angebotsquelle

**Frage:** Reichen die Newsletter von REWE, ALDI Nord und Lidl, um daraus automatisch Lebensmittel-Angebote zu gewinnen?

## Ablauf (ca. 2 Wochen sammeln)
1. Eigenes Gmail-Postfach nur für Newsletter (nicht das private Hauptpostfach).
2. REWE (Markt Meißen), ALDI Nord und Lidl abonnieren. **Bestätigungsmails** (Double-Opt-in) per Link bestätigen.
3. Nach 1–2 Wochen pro Händler **2–3 Newsletter** als `.eml` exportieren (siehe unten) und in `spikes/f_newsletters/samples/` ablegen. Der Ordner ist per `.gitignore` ausgeschlossen.
4. Claude wertet die Mails lokal aus: Was steht drin (Text, Bilder, Preise, Gültigkeit)? Wie viel davon sind Lebensmittel?

## `.eml` exportieren (Gmail im Browser)
Mail öffnen → drei Punkte oben rechts (⋮) → **Nachricht herunterladen**. Die Datei endet auf `.eml`.

## Bewertung
| Kriterium | Ergebnis |
|---|---|
| Preise und Produkte als Text lesbar (nicht nur als Bild)? | ⬜ |
| Angabe der Gültigkeit (von/bis)? | ⬜ |
| Anteil Lebensmittel an den Angeboten? | ⬜ |
| Erscheint der Newsletter mindestens wöchentlich? | ⬜ |
| Bezug zum Markt (REWE Meißen) erkennbar? | ⬜ |

## Betrieb später (nicht jetzt)
Der Server liest das Postfach per IMAP nur lesend. Das Passwort (Gmail-App-Passwort) steht ausschließlich in der `.env` auf dem Server und wird **nie** in einem Chat oder im Repo abgelegt.
