# Web-Oberfläche (PWA)

React 19, TypeScript, Vite. Deutsche Oberfläche, mobil zuerst, hell/dunkel.

## Entwickeln
```bash
cd web
npm install
npm run dev        # http://localhost:5173, leitet /api an das Backend auf Port 8000 weiter
npm run typecheck
npm test
npm run build      # erzeugt web/dist, das das Backend ausliefert (FHP_WEB_DIR bzw. ../web/dist)
```
Hinweis Windows: Die npm-Skripte rufen die Werkzeuge direkt über `node` auf. Das war nötig, solange der
Projektordner ein `&` im Namen hatte (das zerstört die `.bin`-Verknüpfungen von npm). Der Ordner heißt inzwischen
„Food Health Planner“; die Skripte bleiben bewusst so, sie funktionieren überall.

## API-Typen
`src/api/schema.d.ts` wird aus der OpenAPI-Beschreibung des Backends erzeugt:
```bash
.venv/Scripts/python backend/scripts/export_openapi.py   # schreibt web/openapi.json
cd web && npm run gen:api
```
Nach jeder API-Änderung beides ausführen und die Dateien mit committen.

## Aufbau
- `src/api/` Client (Token, deutsche Fehlermeldungen, Upload mit Fortschritt) und erzeugte Typen
- `src/auth/` Anmeldung per Zugangstoken (liegt nur im Browser-Speicher des Geräts)
- `src/ui/` gemeinsame Bausteine und Gestaltung (`ui.css`)
- `src/components/crud/` wiederverwendbare Listen und Formulare
- `src/charts/` kleine SVG-Diagramme mit Textalternative
- `src/pages/` eine Seite je Ordner, Routen in `src/routes.tsx`
- `src/test/` Testhilfen (`mockServer`, `renderPage`)

## Produktion
Das Docker-Image (`backend/Dockerfile`, Build-Kontext ist die Projektwurzel) baut die Oberfläche in einer
eigenen Stufe und liefert sie über das Backend aus. Es braucht keinen weiteren Webserver.
