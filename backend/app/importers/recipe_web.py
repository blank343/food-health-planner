"""Web-Import von Rezepten (schema.org/Recipe über `recipe-scrapers`).

Zwei getrennte Schritte:

* `fetch_html`: höflicher Abruf (eigener User-Agent, robots.txt, Pause je Host, Größenlimit).
* `parse_recipe_html`: reine Funktion ohne Netzwerk, liefert einen `ImportedRecipe`.

`import_recipe_url` verbindet beide. Die Zutaten werden hier nur als Textzeilen übernommen;
Normalisierung und Zuordnung passieren später in `calc/ingredients.py` und im Service.
"""

from __future__ import annotations

import re
import threading
import time
import urllib.robotparser
from urllib.parse import urlparse

import httpx
from recipe_scrapers import scrape_html

from app.importers.types import ImportedRecipe

USER_AGENT = "FoodHealthPlanner/0.1 (privater Hausgebrauch)"
MAX_REDIRECTS = 5
MAX_BYTES = 5 * 1024 * 1024
DEFAULT_MIN_INTERVAL = 1.0


class RecipeImportError(Exception):
    """Rezept konnte nicht abgerufen oder gelesen werden (Meldung ist für Anwender gedacht)."""


# ---------------------------------------------------------------------------
# Parser für Zahlen, Zeiten und Portionen
# ---------------------------------------------------------------------------

_NUMBER_RE = re.compile(r"\d+(?:[.,]\d+)*")
_ISO_DURATION_RE = re.compile(
    r"^P(?:(?P<d>\d+)D)?(?:T(?:(?P<h>\d+)H)?(?:(?P<m>\d+)M)?(?:\d+S)?)?$", re.IGNORECASE
)
_HOURS_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*(?:std|stunde|stunden|h)\b", re.IGNORECASE)
_MINUTES_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*(?:min|minute|minuten|m)\b", re.IGNORECASE)


def _to_float(token: str) -> float | None:
    """Wandelt ein Zahl-Token in float; versteht Dezimalkomma und Tausenderpunkte."""
    if "," in token and "." in token:
        # "1.234,5" (deutsch) oder "1,234.5" (englisch): das letzte Zeichen ist das Dezimaltrennzeichen
        if token.rfind(",") > token.rfind("."):
            token = token.replace(".", "").replace(",", ".")
        else:
            token = token.replace(",", "")
    elif "," in token:
        token = token.replace(",", ".")
    elif token.count(".") > 1:
        # "1.234.567" -> Tausenderpunkte
        token = token.replace(".", "")
    try:
        return float(token)
    except ValueError:
        return None


def parse_number(value: object) -> float | None:
    """Erste Zahl aus Text wie "320 kcal", "12,5 g" oder "17.00"; None, wenn keine vorhanden."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    match = _NUMBER_RE.search(str(value))
    if not match:
        return None
    return _to_float(match.group(0))


def parse_servings(value: object) -> float | None:
    """Portionen aus "4 Portionen", "für 2 Personen" oder "4 servings" (bei "4-6" die untere Zahl)."""
    number = parse_number(value)
    if number is None or number <= 0:
        return None
    return number


def parse_minutes(value: object) -> int | None:
    """Minuten aus Zahl, "45 Min.", "1 Std. 30 Min." oder ISO-8601 ("PT1H30M"); 0/leer -> None."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        minutes = round(float(value))
        return minutes if minutes > 0 else None
    text = str(value).strip()
    if not text:
        return None
    iso = _ISO_DURATION_RE.match(text)
    if iso and any(iso.group(k) for k in ("d", "h", "m")):
        total = (
            int(iso.group("d") or 0) * 24 * 60
            + int(iso.group("h") or 0) * 60
            + int(iso.group("m") or 0)
        )
        return total if total > 0 else None
    hours = _HOURS_RE.search(text)
    minutes = _MINUTES_RE.search(text)
    if hours or minutes:
        total_f = 0.0
        if hours:
            total_f += (_to_float(hours.group(1)) or 0.0) * 60
        if minutes:
            total_f += _to_float(minutes.group(1)) or 0.0
        total = round(total_f)
        return total if total > 0 else None
    number = parse_number(text)  # nackte Zahl ("45") gilt als Minuten
    if number is None:
        return None
    total = round(number)
    return total if total > 0 else None


_NUTRIENT_KEYS = {
    "calories": "kcal",
    "proteinContent": "protein_g",
    "fatContent": "fat_g",
    "carbohydrateContent": "carb_g",
}
_KJ_PER_KCAL = 4.184


def _parse_nutrients(raw: object) -> tuple[dict[str, float], list[str]]:
    """Nährwerte je Portion aus dem schema.org-`nutrition`-Dict; zweiter Wert: Hinweise."""
    result: dict[str, float] = {}
    notes: list[str] = []
    if not isinstance(raw, dict):
        return result, notes
    for source_key, target_key in _NUTRIENT_KEYS.items():
        text = raw.get(source_key)
        number = parse_number(text)
        if number is None or number < 0:
            continue
        if target_key == "kcal" and re.search(r"kj", str(text), re.IGNORECASE) and not re.search(
            r"kcal", str(text), re.IGNORECASE
        ):
            number = number / _KJ_PER_KCAL
        result[target_key] = round(number, 2)
    serving = str(raw.get("servingSize") or "")
    if result and re.search(r"\d\s*(?:g|ml|kg|l)\b", serving, re.IGNORECASE):
        notes.append(f"Nährwerte beziehen sich evtl. nicht auf eine Portion (Angabe: {serving.strip()})")
    return result, notes


# ---------------------------------------------------------------------------
# Rezept aus HTML lesen
# ---------------------------------------------------------------------------


def _clean(text: object) -> str:
    return " ".join(str(text).split()) if text is not None else ""


def _safe(call):
    """Ruft einen Scraper-Getter auf; fehlende Felder (Exception) ergeben None."""
    try:
        return call()
    except Exception:  # noqa: BLE001 - recipe-scrapers wirft je nach Seite verschiedene Fehler
        return None


def _site_of(url: str) -> str | None:
    host = (urlparse(url).hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    return host or None


def parse_recipe_html(html: str, url: str) -> ImportedRecipe:
    """Liest ein Rezept aus HTML (ohne Netzwerk). Fehlende Felder bleiben leer, es gibt Warnungen."""
    try:
        scraper = scrape_html(html, org_url=url, supported_only=False)
    except Exception as exc:  # noqa: BLE001
        raise RecipeImportError("Auf der Seite wurde kein Rezept (schema.org/Recipe) gefunden") from exc

    warnings: list[str] = []
    site = _site_of(url)

    title = _clean(_safe(scraper.title))
    lines = [_clean(line) for line in (_safe(scraper.ingredients) or [])]
    lines = [line for line in lines if line]

    if not title and not lines:
        raise RecipeImportError("Auf der Seite wurde kein Rezept (Titel und Zutaten fehlen) gefunden")
    if not title:
        title = f"Rezept von {site}" if site else "Rezept ohne Titel"
        warnings.append("Kein Titel gefunden")
    if not lines:
        warnings.append("Keine Zutaten gefunden")

    servings = parse_servings(_safe(scraper.yields))
    if servings is None:
        warnings.append("Keine Portionsangabe gefunden")

    prep_min = parse_minutes(_safe(scraper.prep_time))
    cook_min = parse_minutes(_safe(scraper.cook_time))
    if prep_min is None and cook_min is None:
        total_min = parse_minutes(_safe(scraper.total_time))
        if total_min is not None:
            prep_min = total_min
            warnings.append("Nur Gesamtzeit vorhanden, als Vorbereitungszeit übernommen")
        else:
            warnings.append("Keine Zeitangabe gefunden")

    instructions = _safe(scraper.instructions_list)
    if instructions:
        steps = [_clean(step) for step in instructions]
        text = "\n".join(step for step in steps if step)
    else:
        text = "\n".join(
            _clean(part) for part in str(_safe(scraper.instructions) or "").splitlines() if _clean(part)
        )
    if not text:
        warnings.append("Keine Anleitung gefunden")

    image = _clean(_safe(scraper.image)) or None

    nutrients, notes = _parse_nutrients(_safe(scraper.nutrients))
    if not nutrients:
        warnings.append("Keine Nährwerte auf der Seite")
    warnings.extend(notes)

    return ImportedRecipe(
        title=title,
        source_url=url,
        source_site=site,
        servings=servings,
        prep_min=prep_min,
        cook_min=cook_min,
        instructions=text or None,
        image_url=image,
        ingredient_lines=lines,
        site_nutrients=nutrients,
        warnings=warnings,
    )


# ---------------------------------------------------------------------------
# Höflicher Abruf
# ---------------------------------------------------------------------------

_lock = threading.Lock()
_last_fetch: dict[str, float] = {}
_robots_cache: dict[str, urllib.robotparser.RobotFileParser | None] = {}


def _reset_state() -> None:
    """Leert Pausen-Zeitstempel und robots-Cache (für Tests)."""
    with _lock:
        _last_fetch.clear()
        _robots_cache.clear()


def _throttle(host: str, min_interval: float) -> None:
    """Wartet, bis seit dem letzten Abruf desselben Hosts `min_interval` Sekunden vergangen sind."""
    with _lock:
        last = _last_fetch.get(host)
        wait = 0.0
        if last is not None and min_interval > 0:
            wait = max(0.0, last + min_interval - time.monotonic())
        # Zeitstempel für den Abruf setzen, der gleich folgt (auch bei parallelen Aufrufen)
        _last_fetch[host] = time.monotonic() + wait
    if wait > 0:
        time.sleep(wait)


def _validate_url(url: str) -> tuple[str, str, str]:
    parsed = urlparse(url.strip())
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise RecipeImportError("Nur http- und https-Adressen werden unterstützt")
    return parsed.scheme, parsed.netloc.lower(), parsed.hostname.lower()


def _robots_allows(
    client: httpx.Client, scheme: str, netloc: str, host: str, url: str, min_interval: float
) -> bool:
    key = f"{scheme}://{netloc}"
    with _lock:
        cached = key in _robots_cache
        parser = _robots_cache.get(key)
    if not cached:
        parser = None
        _throttle(host, min_interval)
        try:
            response = client.get(f"{key}/robots.txt")
            if response.status_code == 200:
                parser = urllib.robotparser.RobotFileParser()
                parser.parse(response.text.splitlines())
        except httpx.HTTPError:
            parser = None  # nicht erreichbar: erlaubt
        with _lock:
            _robots_cache[key] = parser
    if parser is None:
        return True
    return parser.can_fetch(USER_AGENT, url)


def _status_message(status: int) -> str:
    if status == 404:
        return "Seite nicht gefunden (HTTP 404)"
    if status in (401, 403):
        return f"Zugriff auf die Seite verweigert (HTTP {status})"
    if status == 429:
        return "Die Seite lehnt weitere Abrufe vorübergehend ab (HTTP 429)"
    if status >= 500:
        return f"Die Seite meldet einen Serverfehler (HTTP {status})"
    return f"Abruf fehlgeschlagen (HTTP {status})"


def fetch_html(
    url: str,
    *,
    timeout: float = 15.0,
    min_interval: float = DEFAULT_MIN_INTERVAL,
    client: httpx.Client | None = None,
) -> str:
    """Ruft eine Rezeptseite höflich ab (robots.txt, Pause je Host, max. 5 MB, max. 5 Weiterleitungen).

    `client` ist für Tests gedacht (z. B. mit `httpx.MockTransport`).
    """
    scheme, netloc, host = _validate_url(url)
    own_client = client is None
    if client is None:
        client = httpx.Client(
            headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"},
            timeout=timeout,
            follow_redirects=True,
            max_redirects=MAX_REDIRECTS,
        )
    try:
        if not _robots_allows(client, scheme, netloc, host, url, min_interval):
            raise RecipeImportError("robots.txt verbietet den Abruf")
        _throttle(host, min_interval)
        try:
            with client.stream("GET", url) as response:
                if response.status_code >= 400:
                    raise RecipeImportError(_status_message(response.status_code))
                ctype = response.headers.get("content-type", "").lower()
                if ctype and not any(t in ctype for t in ("html", "xml", "text")):
                    raise RecipeImportError("Die Adresse liefert keine Webseite")
                declared = response.headers.get("content-length", "")
                if declared.isdigit() and int(declared) > MAX_BYTES:
                    raise RecipeImportError("Die Seite ist zu groß (mehr als 5 MB)")
                chunks: list[bytes] = []
                size = 0
                for chunk in response.iter_bytes():
                    size += len(chunk)
                    if size > MAX_BYTES:
                        raise RecipeImportError("Die Seite ist zu groß (mehr als 5 MB)")
                    chunks.append(chunk)
                encoding = response.charset_encoding or "utf-8"
        except httpx.TimeoutException as exc:
            raise RecipeImportError("Zeitüberschreitung beim Abruf der Seite") from exc
        except httpx.TooManyRedirects as exc:
            raise RecipeImportError("Zu viele Weiterleitungen") from exc
        except httpx.HTTPError as exc:
            raise RecipeImportError(f"Seite konnte nicht abgerufen werden ({type(exc).__name__})") from exc
        body = b"".join(chunks)
        try:
            return body.decode(encoding, errors="replace")
        except LookupError:
            return body.decode("utf-8", errors="replace")
    finally:
        if own_client:
            client.close()


def import_recipe_url(url: str) -> ImportedRecipe:
    """Ruft die Seite ab und liest das Rezept."""
    return parse_recipe_html(fetch_html(url), url)
