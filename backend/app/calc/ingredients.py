"""Zutatenzeilen: Parser, Einheiten-Umrechnung, Namens-Normalisierung und Katalog-Zuordnung.

Reine Funktionen ohne Datenbank (siehe docs/PHASE2.md, Abschnitt 4.1).
"""

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from functools import lru_cache

from rapidfuzz.distance import Levenshtein

from app.calc import defaults
from app.calc.types import IngredientMatch, ParsedIngredient

__all__ = [
    "CatalogEntry",
    "match_ingredient",
    "mean_quantity",
    "normalize_name",
    "parse_ingredient_line",
    "to_grams",
]

# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

_FRACTIONS = {
    "½": "1/2", "¼": "1/4", "¾": "3/4", "⅓": "1/3", "⅔": "2/3", "⅕": "1/5", "⅖": "2/5",
    "⅗": "3/5", "⅘": "4/5", "⅙": "1/6", "⅚": "5/6", "⅛": "1/8", "⅜": "3/8", "⅝": "5/8", "⅞": "7/8",
}  # fmt: skip

_NUM = r"(?:\d+\s+\d+/\d+|\d+\s*/\s*\d+|\d+(?:[.,]\d+)?)"
_QTY_RE = re.compile(
    rf"^(?:(?:ca\.?|circa|etwa|ungefähr|ungef\.|~)\s*)?(?P<q1>{_NUM})"
    rf"(?:\s*(?:-|–|—|bis)\s*(?P<q2>{_NUM}))?",
    re.IGNORECASE,
)
_NUM_RE = re.compile(_NUM)
_MIXED_RE = re.compile(r"^(\d+)\s+(\d+)/(\d+)$")
_FRAC_RE = re.compile(r"^(\d+)\s*/\s*(\d+)$")
_HALF_RE = re.compile(r"^(?:(?:ein|eine|einen|einem|einer)\s+)?halb(?:e|er|es|en|em)\s+", re.IGNORECASE)
_ONE_RE = re.compile(r"^(?:ein|eine|einen|einem|einer)\s+", re.IGNORECASE)
_UNIT_WORD_RE = re.compile(r"^([A-Za-zÄÖÜäöüß]+\.?)(?=[\s,;]|$)")
_OPT_PREFIX_RE = re.compile(r"^(?:evtl\.?|eventuell|ggf\.?|gegebenenfalls|optional:?)\s+", re.IGNORECASE)
_OPT_SUFFIX_RE = re.compile(
    r"(?:[,;]\s*|\s+)(?P<word>nach\s+belieben|optional|evtl\.?|eventuell|ggf\.?|gegebenenfalls)\s*$",
    re.IGNORECASE,
)
_TASTE_SUFFIX_RE = re.compile(r"(?:[,;]\s*|\s+)(?P<word>nach\s+(?:geschmack|bedarf))\s*$", re.IGNORECASE)
_LEAD_FILLER_RE = re.compile(r"^(?:etwas|ein\s+wenig|einige|ein\s+paar|wenig)\s+", re.IGNORECASE)
_PURPOSE_RE = re.compile(
    r"\s+(?P<note>(?:(?:zum|zur|für|zu)\s+|aus\s+(?:der|dem)\s+Mühle"
    r"|in\s+(?:Streifen|Scheiben|Würfeln?|Stücken|Ringen|Spalten|Stiften|Hälften|Vierteln|Achteln)\b).*)$",
    re.IGNORECASE,
)
_PAREN_RE = re.compile(r"\(([^)]*)\)")
_APPROX = r"(?:(?:ca\.?|circa|etwa|ungefähr|ungef\.|~)\s*)?"
_RANGE = rf"(?:\s*(?:-|–|—|bis)\s*(?P<q2>{_NUM}))?"
# Gewichtsangabe in Klammern oder nach einem Komma: "(je ca. 150 g)", "(400 g)", "ca. 2,2 kg"
_PAREN_WEIGHT_RE = re.compile(
    rf"^(?P<desc>(?:Abtropfgewicht|abgetropft(?:es Gewicht)?|Abtropfgew\.|Einwaage|Füllmenge)\s*:?\s*)?"
    rf"{_APPROX}(?P<each>(?:je|à|a|pro)\s*)?{_APPROX}(?P<q>{_NUM}){_RANGE}\s*(?P<u>[A-Za-zäöüß]+)\.?\s*(?P<rest>.*)$",
    re.IGNORECASE,
)
# Gewicht je Stück ohne Klammer am Zeilenende: "à ca. 150-200g", "je 80 g"
_EACH_TAIL_RE = re.compile(
    rf"\s+(?P<each>(?:je|à|pro)\s*){_APPROX}(?P<q>{_NUM}){_RANGE}\s*(?P<u>[A-Za-zäöüß]+)\.?(?P<rest>(?:\s.*)?)$",
    re.IGNORECASE,
)
_COMMA_RE = re.compile(r",(?!\d)")
_CHOICE_RE = re.compile(r"\s+nach\s+wahl\b.*$", re.IGNORECASE)
_OR_RE = re.compile(r"\s+oder\s+", re.IGNORECASE)
_WITH_RE = re.compile(r"\s+(?:mit|ohne)\s+", re.IGNORECASE)
_OPT_WORDS = {"optional", "evtl.", "evtl", "eventuell", "ggf.", "ggf", "nach belieben"}
_WEIGHT_UNITS = {"g", "kg", "ml", "l"}
# Adjektive, die vor "oder" stehen können ("glatte oder krause Petersilie")
_ADJECTIVES = {
    "glatt", "kraus", "mild", "scharf", "süß", "sauer", "reif", "fest", "mehlig", "frisch", "gefroren",
    "tiefgekühlt", "getrocknet", "rot", "gelb", "grün", "weiß", "schwarz", "braun", "orange", "dunkel",
    "hell", "fein", "grob", "klein", "groß", "tk",
}  # fmt: skip
_ADJ_ENDINGS = ("", "e", "er", "es", "en", "em")
# Weitere Einheiten, die `defaults.UNIT_ALIASES` nicht kennt (Stängel/Stiele zählen wie Zweige)
_LOCAL_UNIT_ALIASES = {
    "stängel": "Zweig", "stengel": "Zweig", "stiel": "Zweig", "stiele": "Zweig", "bündel": "Bund",
    "pk": "Packung", "pkt": "Packung",
}  # fmt: skip
# Zusammengesetzte Formen: "Knoblauchzehen" = Zehe Knoblauch (Endung -> Einheit)
_COMPOUND_UNITS = {
    "zehen": "Zehe", "zehe": "Zehe", "scheiben": "Scheibe", "scheibe": "Scheibe",
    "stangen": "Stange", "stange": "Stange", "zweige": "Zweig", "zweig": "Zweig",
    "blätter": "Blatt", "bund": "Bund",
}  # fmt: skip
_COMPOUND_RE = re.compile(
    r"^(?P<stem>[A-Za-zÄÖÜäöüß]{3,}?)(?P<end>" + "|".join(_COMPOUND_UNITS) + r")$", re.IGNORECASE
)
# Standalone-Einheiten ohne Zahl ("Prise Salz")
_BARE_UNITS = {"Prise", "Handvoll", "Bund"}


def _clean(text: str) -> str:
    s = text.replace(" ", " ").replace(" ", " ").replace(" ", " ")
    s = s.strip().lstrip("•*·-– ").strip()
    for ch, frac in _FRACTIONS.items():
        s = re.sub(rf"(\d)\s*{ch}", rf"\1 {frac}", s)
        s = s.replace(ch, frac)
    return re.sub(r"\s+", " ", s)


def _parse_number(text: str) -> float:
    t = text.strip()
    m = _MIXED_RE.match(t)
    if m:
        return int(m.group(1)) + int(m.group(2)) / int(m.group(3))
    m = _FRAC_RE.match(t)
    if m:
        return int(m.group(1)) / int(m.group(2))
    return float(t.replace(",", "."))


def _lookup_unit(token: str) -> str | None:
    key = token.lower()
    for candidate in (key, key.rstrip(".")):
        if candidate in defaults.UNIT_ALIASES:
            return defaults.UNIT_ALIASES[candidate]
        if candidate in _LOCAL_UNIT_ALIASES:
            return _LOCAL_UNIT_ALIASES[candidate]
    return None


def _split_unit(rest: str) -> tuple[str | None, str, str]:
    """Trennt eine führende Einheit ab. Gibt (Einheit, Rest, Originaltext der Einheit) zurück."""
    m = _UNIT_WORD_RE.match(rest)
    if not m:
        return None, rest, ""
    unit = _lookup_unit(m.group(1))
    if unit is None:
        return None, rest, ""
    remainder = rest[m.end() :].strip()
    if remainder.lower().startswith("von "):
        remainder = remainder[4:].strip()
    if not remainder:  # nur die Einheit, kein Name: lieber als Name behandeln
        return None, rest, ""
    return unit, remainder, m.group(1)


def _add_note(notes: list[str], text: str | None) -> None:
    if text and text.strip() and text.strip() not in notes:
        notes.append(text.strip())


@dataclass
class _ParenWeight:
    quantity: float  # Mittelwert bei Bereichen ("150-200" → 175)
    unit: str  # g, kg, ml oder l
    each: bool  # "je"/"à": Gewicht pro Stück
    text: str  # Originaltext für den Zusatz
    quantity_max: float | None = None
    descriptive: bool = False  # mit Beschreibung ("Abtropfgewicht 240 g"): Text bleibt im Zusatz


def _weight_from_match(wm: re.Match[str], text: str) -> _ParenWeight | None:
    """Baut ein Gewicht aus einem Treffer von `_PAREN_WEIGHT_RE`/`_EACH_TAIL_RE` (nur g/kg/ml/l)."""
    unit = _lookup_unit(wm.group("u"))
    if unit not in _WEIGHT_UNITS:
        return None
    low = _parse_number(wm.group("q"))
    high = _parse_number(wm.group("q2")) if wm.group("q2") else None
    mean = low if high is None or high == low else (low + high) / 2
    descriptive = "desc" in wm.groupdict() and bool(wm.group("desc"))
    return _ParenWeight(mean, unit, bool(wm.group("each")), text.strip(), descriptive=descriptive)


def _read_parens(s: str, notes: list[str]) -> tuple[str, bool, _ParenWeight | None]:
    """Entfernt Klammern aus `s`; liefert (Rest, optional, Klammer-Gewicht)."""
    optional = False
    weight: _ParenWeight | None = None
    for m in _PAREN_RE.finditer(s):
        content = m.group(1).strip()
        if not content:
            continue
        if content.lower() in _OPT_WORDS:
            optional = True
            continue
        wm = _PAREN_WEIGHT_RE.match(content)
        found = _weight_from_match(wm, content) if wm else None
        if wm and found is not None and weight is None:
            weight = found
            _add_note(notes, wm.group("rest"))
            continue
        _add_note(notes, content)
    s = _PAREN_RE.sub(" ", s)
    if "(" in s:  # nicht geschlossene Klammer: Rest ist ein Zusatz
        s, _, tail = s.partition("(")
        _add_note(notes, tail.strip(" )"))
    return re.sub(r"\s+", " ", s).strip(), optional, weight


def _is_adjective(token: str) -> bool:
    low = token.lower()
    return any(low.startswith(stem) and low[len(stem) :] in _ADJ_ENDINGS for stem in _ADJECTIVES)


def parse_ingredient_line(text: str) -> ParsedIngredient:
    """Zerlegt eine deutsche Rezept-Zutatenzeile in Menge, Einheit, Name und Zusatz.

    Beispiele: `200 g Mehl`, `½ Bund Petersilie`, `3-4 Karotten`, `1 Dose Tomaten (400 g)`.
    Eine Gewichtsangabe in g/ml (in Klammern, nach einem Komma oder als "à 150 g") hat Vorrang
    vor Dose/Packung/Stück: bei "je"/"à" gilt sie pro Stück ("2 Möhren (je 150 g)" → 300 g, ein
    Bereich zählt als Mittelwert); die ursprüngliche Angabe landet im Zusatz. Zusätze nach Komma
    oder Doppelpunkt, "mit …"-Beiwerk und "oder"-Alternativen stehen in `note` (bei Alternativen
    gilt der erste Name); "nach Wahl" macht die Zeile optional.
    """
    raw = text
    s = _clean(text)
    if not s:
        return ParsedIngredient(raw=raw, name="")
    notes: list[str] = []
    optional = False

    m = _OPT_PREFIX_RE.match(s)
    if m:
        optional = True
        s = s[m.end() :]

    if ":" in s:
        head, tail = s.split(":", 1)
        if head.strip():
            s = head.strip()
            _add_note(notes, tail)
        else:
            s = tail.strip()

    s, paren_optional, paren_weight = _read_parens(s, notes)
    optional = optional or paren_optional

    m = _CHOICE_RE.search(s)  # "Gemüse nach Wahl, z. B. Möhre" → optional, Rest als Zusatz
    if m:
        optional = True
        _add_note(notes, s[m.start() :].strip())
        s = s[: m.start()].strip()
    while True:
        m = _OPT_SUFFIX_RE.search(s)
        if not m:
            break
        optional = True
        s = s[: m.start()].strip()
    m = _TASTE_SUFFIX_RE.search(s)
    if m:
        _add_note(notes, m.group("word"))
        s = s[: m.start()].strip()
    each_match = _EACH_TAIL_RE.search(s)
    if each_match:
        rest_text = each_match.group("rest")
        matched = each_match.group(0)
        found = _weight_from_match(each_match, matched[: len(matched) - len(rest_text)])
        if found is not None:
            if paren_weight is None:
                paren_weight = found
                _add_note(notes, found.text)
            else:
                _add_note(notes, found.text)
            _add_note(notes, rest_text)
            s = s[: each_match.start()].strip()
    s = _LEAD_FILLER_RE.sub("", s)

    quantity: float | None = None
    quantity_max: float | None = None
    unit: str | None = None
    qty_text = ""
    rest = s
    unit_text = ""

    m = _QTY_RE.match(s)
    if m and s[m.end() :].startswith("-") and s[m.end() : m.end() + 2][1:].isalpha():
        m = None  # z. B. "7-Korn-Brot": keine Menge
    if m:
        quantity = _parse_number(m.group("q1"))
        if m.group("q2"):
            quantity_max = _parse_number(m.group("q2"))
            if quantity_max == quantity:
                quantity_max = None
        rest = s[m.end() :].strip()
        qty_text = s[: m.end()].strip()
        unit, rest, unit_text = _split_unit(rest)
    else:
        hm = _HALF_RE.match(s)
        om = _ONE_RE.match(s)
        if hm:
            quantity = 0.5
            rest = s[hm.end() :]
        elif om:
            candidate_unit, _, _ = _split_unit(s[om.end() :])
            if candidate_unit is not None:
                quantity = 1.0
                rest = s[om.end() :]
        if quantity is not None:
            unit, rest, unit_text = _split_unit(rest)
            qty_text = "½" if quantity == 0.5 else "1"
        else:
            bare_unit, bare_rest, bare_text = _split_unit(s)
            if bare_unit in _BARE_UNITS:
                quantity, unit, rest, unit_text = 1.0, bare_unit, bare_rest, bare_text

    name, name_notes, tail_weight = _clean_name_part(rest)
    for n in name_notes:
        _add_note(notes, n)
    if paren_weight is None and tail_weight is not None:
        paren_weight = tail_weight
        _add_note(notes, tail_weight.text)

    if (
        unit == "Zweig"
        and unit_text.lower().startswith("stiel")
        and re.search(r"sellerie|rhabarber|mangold", name, re.IGNORECASE)
    ):
        unit = "Stange"  # Stiele von Gemüse sind keine Kräuterzweige

    if unit is None and quantity is not None:
        cm = _COMPOUND_RE.match(name)
        if cm:
            unit = _COMPOUND_UNITS[cm.group("end").lower()]
            name = cm.group("stem")
            unit_text = cm.group("end")

    if paren_weight is not None and unit not in _WEIGHT_UNITS:
        factor = 1.0
        if paren_weight.each and quantity is not None:
            factor = quantity
        if quantity is not None and unit_text:  # "2 Dosen" bleibt als Zusatz erhalten
            _add_note(notes, f"{qty_text} {unit_text}".strip())
        if paren_weight.descriptive:
            _add_note(notes, paren_weight.text)
        if quantity_max is not None and paren_weight.each and quantity is not None:
            quantity_max = paren_weight.quantity * quantity_max
        else:
            quantity_max = None
        quantity = paren_weight.quantity * factor
        unit = paren_weight.unit
        if unit == "kg":  # Gesamtgewicht immer in g bzw. ml
            quantity, unit = quantity * 1000.0, "g"
            quantity_max = None if quantity_max is None else quantity_max * 1000.0
        elif unit == "l":
            quantity, unit = quantity * 1000.0, "ml"
            quantity_max = None if quantity_max is None else quantity_max * 1000.0
    elif paren_weight is not None:
        _add_note(notes, paren_weight.text)

    if not name:
        name = s if quantity is None else rest.strip()
    return ParsedIngredient(
        raw=raw,
        name=name,
        quantity=quantity,
        quantity_max=quantity_max,
        unit=unit,
        note="; ".join(notes) if notes else None,
        optional=optional,
    )


def _clean_name_part(rest: str) -> tuple[str, list[str], _ParenWeight | None]:
    """Trennt Zusätze (Komma, "oder", "mit …", "zum Braten") vom Namen ab.

    Liefert (Name, Zusätze, Gewicht nach dem Komma wie bei "Suppenhuhn, ca. 2,2 kg").
    """
    notes: list[str] = []
    weight: _ParenWeight | None = None
    name = rest.strip()
    if name.lower().startswith("von "):
        name = name[4:].strip()
    am = re.match(r"^(\S+)\s+oder\s+(\S+)\s+(.+)$", name, re.IGNORECASE)
    if am and _is_adjective(am.group(1)) and _is_adjective(am.group(2)):
        _add_note(notes, f"{am.group(1)} oder {am.group(2)}")  # "glatte oder krause Petersilie"
        name = am.group(3)
    parts = _COMMA_RE.split(name, maxsplit=1)  # ohne Dezimalkomma ("Milch 1,5 %")
    if len(parts) == 2:
        name, tail = parts[0], parts[1].strip(" ,;")
        wm = _PAREN_WEIGHT_RE.match(tail)
        found = _weight_from_match(wm, tail[: len(tail) - len(wm.group("rest"))]) if wm else None
        if wm and found is not None:
            weight = found
            _add_note(notes, wm.group("rest").strip(" ,;"))
        else:
            _add_note(notes, tail)
    om = _OR_RE.search(name)
    if om and name[: om.start()].strip():
        _add_note(notes, name[om.start() :].strip())  # "Reisessig oder anderen Essig" → Reisessig
        name = name[: om.start()]
    wm2 = _WITH_RE.search(name)
    if wm2 and name[: wm2.start()].strip():
        _add_note(notes, name[wm2.start() :].strip())  # "Lachsfilets mit Haut" → Lachsfilets
        name = name[: wm2.start()]
    m = _PURPOSE_RE.search(name)
    if m:
        _add_note(notes, m.group("note"))
        name = name[: m.start()]
    return name.strip(" ,;.*"), notes, weight


def mean_quantity(parsed: ParsedIngredient) -> float | None:
    """Mittelwert bei Bereichen ("3-4" → 3,5), sonst die Menge; None ohne Menge."""
    if parsed.quantity is None:
        return None
    if parsed.quantity_max is not None:
        return (parsed.quantity + parsed.quantity_max) / 2
    return parsed.quantity


# ---------------------------------------------------------------------------
# Einheiten
# ---------------------------------------------------------------------------

_CANONICAL_UNITS = set(defaults.UNIT_ALIASES.values()) | set(_LOCAL_UNIT_ALIASES.values())


def _canonical_unit(unit: str | None) -> str | None:
    if unit is None:
        return None
    if unit in _CANONICAL_UNITS:
        return unit
    return _lookup_unit(unit.strip())


def to_grams(
    quantity: float | None,
    unit: str | None,
    *,
    density_g_per_ml: float | None = None,
    piece_g: float | None = None,
    default_piece: bool = False,
    unit_g: float | None = None,
) -> float | None:
    """Rechnet Menge und Einheit in Gramm um. Unbekannte Einheit oder fehlende Menge → None.

    - g/kg direkt; ml/l über die Dichte (Standard 1,0 g/ml).
    - EL/TL/Tasse/Becher/Glas über `defaults.ML_PER_UNIT` und die Dichte.
    - Stück bzw. keine Einheit: nur mit `piece_g` (Stückgewicht der Zutat). Fehlt es, ist das
      Ergebnis None und das Rezept bleibt zur Prüfung offen; nur mit `default_piece=True`
      gilt ersatzweise `defaults.DEFAULT_PIECE_G` (früheres Verhalten).
    - Prise, Zehe, Bund, Zweig, Dose, Packung, Scheibe usw.: `defaults.GRAMS_PER_UNIT`, es sei denn
      `unit_g` nennt das Gewicht dieser Einheit für die Zutat (z. B. 1 Päckchen Backpulver = 15 g).
    """
    if quantity is None:
        return None
    density = density_g_per_ml if density_g_per_ml and density_g_per_ml > 0 else 1.0
    canonical = None if unit is None else _canonical_unit(unit)
    if unit is None or canonical == "Stück":
        if piece_g and piece_g > 0:
            return quantity * piece_g
        return quantity * defaults.DEFAULT_PIECE_G if default_piece else None
    if canonical is None:
        return None
    if canonical == "g":
        return quantity
    if canonical == "kg":
        return quantity * 1000.0
    if canonical == "ml":
        return quantity * density
    if canonical == "l":
        return quantity * 1000.0 * density
    if canonical in defaults.ML_PER_UNIT:
        return quantity * defaults.ML_PER_UNIT[canonical] * density
    if canonical in defaults.GRAMS_PER_UNIT:
        per_unit = unit_g if unit_g and unit_g > 0 else defaults.GRAMS_PER_UNIT[canonical]
        return quantity * per_unit
    return None


# ---------------------------------------------------------------------------
# Namens-Normalisierung
# ---------------------------------------------------------------------------

# Füllwörter (Grundform; erlaubte Endungen siehe _FILLER_ENDINGS)
_FILLER_STEMS = {
    "frisch", "gehackt", "gewürfelt", "geschnitten", "geschält", "geraspelt", "gerieben", "groß",
    "gross", "klein", "mittelgroß", "mittelgross", "bio", "reif", "weich", "kalt", "tiefgekühlt",
    "gemahlen", "feingehackt", "gewaschen", "entkernt", "halbiert", "zimmerwarm", "ganz", "fein",
    "grob", "gestrichen", "gehäuft", "dünn", "dick", "tk", "etwas", "ca", "circa", "etwa",
    "optional", "evtl", "ggf", "festkochend", "mehligkochend", "vorwiegend", "glatt", "kraus",
}  # fmt: skip
_FILLER_ENDINGS = ("", "e", "er", "es", "en", "em")
_CUT_RE = re.compile(r"\b(?:nach|zum|zur|für|zu)\b.*$")
_PERCENT_RE = re.compile(r"[<>]?\s*(\d+)(?:[.,](\d+))?\s*%")  # "3,5 %" -> "35pct" (Milch 3,5 vs. 1,5)
_IN_DM_RE = re.compile(r"\bi\.\s*tr\.|\bfett\b")
_PUNCT_RE = re.compile(r"[^\w\säöüß]")

# Singular-Ausnahmen auf -en (Schinken, Samen, ...); Plural wäre sonst "schinke"
_KEEP_EN = {
    "schinken", "samen", "boden", "magen", "wagen", "kuchen", "lachen", "garten", "hafer", "weizen",
    "roggen",
}  # fmt: skip


def _is_filler(token: str) -> bool:
    for stem in _FILLER_STEMS:
        if token.startswith(stem) and token[len(stem) :] in _FILLER_ENDINGS:
            return True
    return False


_COLORS = ("rot", "gelb", "grün", "weiß", "schwarz", "braun")
_COLOR_FORMS = {c + e: c for c in _COLORS for e in ("e", "er", "es", "en", "em")}


def _singular(token: str) -> str:
    """Konservative Pluralvereinfachung (Karotten → karotte, Eier → ei, Mandeln → mandel)."""
    if token in _COLOR_FORMS:
        return _COLOR_FORMS[token]
    if len(token) < 4 or token in _KEEP_EN:
        return token
    if token.endswith("nüsse"):
        return token[:-5] + "nuss"
    if token.endswith("äpfel"):
        return token[:-5] + "apfel"
    if token.endswith("eier"):
        return token[:-2]
    if token.endswith(("filets", "steaks")):
        return token[:-1]
    if token.endswith("eln"):
        return token[:-1]
    if token.endswith("en") and not token.endswith(("chen", "uchen", "samen", "schinken")):
        return token[:-1]
    if token.endswith("ons"):
        return token[:-1]
    return token


def _percent(text: str) -> str:
    return _PERCENT_RE.sub(lambda m: f" {m.group(1)}{m.group(2) or ''}pct ", text)


def _basic_clean(text: str) -> str:
    s = _percent(text.lower())
    s = _IN_DM_RE.sub(" ", s)
    s = s.replace("-", " ")
    return re.sub(r"\s+", " ", _PUNCT_RE.sub(" ", s)).strip()


def normalize_name(text: str) -> str:
    """Normalisiert einen Zutatennamen für Synonyme und Suche.

    Kleinschreibung, Klammern und Zusätze nach Komma/Doppelpunkt entfallen, ebenso Füllwörter
    (frisch, gehackt, große, bio, nach Geschmack ...); Plural wird vereinfacht.
    """
    s = _percent(text.lower())  # vor dem Komma-Schnitt ("3,5 % Fett")
    s = _PAREN_RE.sub(" ", s)
    s = s.split(":")[0].split(",")[0]
    s = _basic_clean(s)
    s = _CUT_RE.sub("", s).strip()
    tokens = [t for t in s.split() if not _is_filler(t)]
    if not tokens:
        tokens = s.split()
    return " ".join(_singular(t) for t in tokens)


# ---------------------------------------------------------------------------
# Zuordnung zum Katalog
# ---------------------------------------------------------------------------
#
# Die Bewertung ist wortbasiert: Ein Treffer braucht einen Wortbezug zum Katalognamen (ganzes
# Wort, Wortende einer Zusammensetzung, Kopfwort des Suchbegriffs ...). Reine Zeichenähnlichkeit
# zählt nur als Tippfehler (höchstens ein Buchstabe Unterschied). Nur der Kopf des Katalognamens
# (bis zum ersten Komma und bis "mit"/"und"/...) zählt als Hauptteil.


@dataclass(frozen=True)
class CatalogEntry:
    id: int
    name: str
    rank_hint: float = 0.0  # vom Aufrufer: z. B. +10 für Rohware, −20 für Fertiggerichte


@dataclass(frozen=True)
class _Prepared:
    full: str  # normalisierter ganzer Katalogname
    head: str  # normalisierter Teil vor dem ersten Komma
    primary: tuple[str, ...]  # Wörter des Kopfs bis zu "mit", "und", ...
    secondary: tuple[str, ...]  # Wörter nach "mit", "und", ... (Beiwerk)
    tail: tuple[str, ...]  # Wörter nach dem ersten Komma ("roh", "type", "405", "35pct")
    joins: frozenset[str]  # zusammengeschriebene Nachbarwörter: "hafer flocke" → "haferflocke"
    modifiers: frozenset[str]  # Vorderglieder von Bindestrich-Wörtern ("Quark-Plunder" → quark)
    sweet: bool  # Getränk, Kuchen, Torte, Süßware

    @property
    def words(self) -> frozenset[str]:
        return frozenset(self.primary + self.secondary + self.tail)

    @property
    def full_joined(self) -> str:
        return self.full.replace(" ", "")

    @property
    def head_joined(self) -> str:
        return self.head.replace(" ", "")


_CONNECTORS = {"mit", "und", "in", "auf", "ohne", "von", "aus", "im", "an"}
_QUERY_CUTS = {"mit", "ohne", "und", "oder"}  # ab hier beginnt im Suchbegriff Beiwerk
_MIN_SCORE = 60.0
_SWORD_RE = re.compile(r"[\wäöüß]+")
_SWEET_WORDS = {
    "getränk", "kuchen", "torte", "gebäck", "plätzchen", "keks", "kekse", "praline", "pralinen",
    "likör", "speiseeis", "eis", "bonbon", "konfekt", "riegel", "pudding", "flammeri", "limonade",
    "plunder", "teilchen", "muffin", "waffel",
}  # fmt: skip
_SWEET_ENDINGS = ("kuchen", "torte", "gebäck", "plätzchen", "likör", "praline", "pralinen", "plunder")
# Zu allgemeine Suchwörter: ohne Synonym/exakten Namen gibt es keinen sinnvollen Vorschlag
_VAGUE_QUERIES = {
    "gemüse", "obst", "fleisch", "fisch", "wurst", "kräuter", "gewürz", "früchte", "frucht", "beilage",
    "topping", "einlage", "fett", "zutat", "garnitur",
}  # fmt: skip
# Zu allgemeine Endwörter: "hähnchenbrustfilet" soll nicht über "filet" zu "Schwein Filet" führen
_GENERIC_TAILS = {
    "filet", "steak", "fleisch", "salat", "suppe", "brust", "keule", "schnitzel", "kotelett", "wurst",
    "saft", "sauce", "soße", "creme", "pulver", "würfel", "scheibe", "stück", "stange", "kern", "brot",
    "käse", "mehl", "zucker", "salz", "wasser", "sirup", "paste", "püree", "flocke", "kuchen", "torte",
    "blatt", "blätter", "kraut", "korn", "samen", "wurzel", "frucht", "bohne", "schote", "nuss",
}  # fmt: skip
# "Lachsfilet" meint Lachs: Zusätze, die das Grundprodukt nur zerteilen
_NEUTRAL_TAILS = ("filet", "steak", "stück", "scheibe", "würfel", "streifen", "schnitzel", "medaillon")


def _is_sweet_word(word: str) -> bool:
    return word in _SWEET_WORDS or word.endswith(_SWEET_ENDINGS)


@lru_cache(maxsize=50000)
def _prepare(name: str) -> _Prepared:
    lowered = name.lower()
    sweet = any(_is_sweet_word(w) for w in _SWORD_RE.findall(lowered))
    raw = _percent(_PAREN_RE.sub(" ", lowered))
    head_raw = raw.split(",")[0]
    full_tokens = [_singular(t) for t in _basic_clean(raw).split()]
    head_tokens = [_singular(t) for t in _basic_clean(head_raw).split()]
    primary: list[str] = []
    secondary: list[str] = []
    in_secondary = False
    for tok in head_tokens:
        if tok in _CONNECTORS:
            in_secondary = True
        (secondary if in_secondary else primary).append(tok)
    joins = {"".join(primary[i : i + n]) for n in (2, 3) for i in range(len(primary) - n + 1)}
    modifiers: set[str] = set()
    for word in re.split(r"[\s/]+", head_raw):
        if "-" in word:
            for part in word.split("-")[:-1]:
                cleaned = _basic_clean(part)
                if cleaned and " " not in cleaned:
                    modifiers.add(_singular(cleaned))
    return _Prepared(
        " ".join(full_tokens),
        " ".join(head_tokens),
        tuple(primary),
        tuple(secondary),
        _tail_words(full_tokens[len(head_tokens) :]),
        frozenset(joins),
        frozenset(modifiers),
        sweet,
    )


def _tail_words(tokens: Sequence[str]) -> tuple[str, ...]:
    """Angaben nach dem ersten Komma, aber ohne Beiwerk ab "mit"/"in"/... ("mit Zitronensaft")."""
    for i, tok in enumerate(tokens):
        if tok in _CONNECTORS:
            return tuple(tokens[:i])
    return tuple(tokens)


def _umlaut_variants(token: str) -> set[str]:
    """Schreibweise ohne Umlaute ("olivenoel") auch als Umlaut-Variante prüfen."""
    return {token, token.replace("oe", "ö").replace("ae", "ä").replace("ue", "ü").replace("ss", "ß")}


def _token_relation(tok: str, prep: _Prepared) -> float | None:
    """Wie gut passt ein Suchwort zum Katalognamen? None = kein Wortbezug.

    Ganzes Wort im Kopf 88–92; Wort in den Angaben nach dem Komma 84; Endwort einer Zusammensetzung
    ("zwiebel" in "speisezwiebel") 86; Kopfwort des Suchbegriffs ("kirschtomate" → "tomate") 78–80;
    Wortanfang ("zwiebel" in "zwiebelsuppe") höchstens 66 und weniger bei langem Rest; Tippfehler 74.
    """
    primary = prep.primary
    if any(ch.isdigit() for ch in tok):  # Zahlen (Fettstufe, Type) müssen exakt stimmen
        return 90.0 if tok in prep.words else None
    if tok in primary:
        if tok in prep.modifiers:  # "Quark-Plunder" ist kein Quark
            return 64.0
        return 92.0 if tok == primary[0] else 88.0
    if tok in prep.joins:
        return 90.0
    if tok in prep.tail:
        return 84.0
    n = len(tok)
    best: float | None = None
    for word in primary:
        score: float | None = None
        if n >= 2 and len(word) > n and word.endswith(tok):
            score = 86.0 if n >= 4 else 78.0
        elif n >= 8 and len(word) >= 5 and word not in _GENERIC_TAILS and tok.endswith(word):
            score = 78.0 if n - len(word) >= 3 else None
        elif n >= 8 and len(word) >= 4 and tok.startswith(word) and tok[len(word) :] in _NEUTRAL_TAILS:
            score = 80.0
        elif n >= 4 and len(word) > n and word.startswith(tok):
            score = 66.0 - (len(word) - n)
        elif n >= 5 and len(word) >= 5 and abs(len(word) - n) <= 1:
            if any(Levenshtein.distance(v, word, score_cutoff=1) <= 1 for v in _umlaut_variants(tok)):
                score = 74.0
        if score is not None and (best is None or score > best):
            best = score
    return best


def _query_score(tokens: Sequence[str], prep: _Prepared) -> float | None:
    """Wortbezug des (mehrteiligen) Suchbegriffs zum Katalognamen; None = unbrauchbar."""
    if len(tokens) == 1:
        return _token_relation(tokens[0], prep)
    joined = "".join(tokens)
    joined_primary = "".join(prep.primary)
    if joined == joined_primary or joined in prep.joins:
        return 92.0
    if joined_primary.startswith(joined):
        return 80.0
    words = [t for t in tokens if t != "type" and not any(ch.isdigit() for ch in t)]
    head_token = words[-1] if words else None
    scores: list[float] = []
    penalty = 0.0
    for tok in tokens:
        rel = _token_relation(tok, prep)
        if rel is None:
            if tok == head_token or any(ch.isdigit() for ch in tok) or tok in _COLORS:
                return None  # Kopfwort, Zahl und Farbe müssen stimmen ("rot" ≠ "gelb", 3,5 % ≠ 1,5 %)
            penalty += 14.0
            continue
        scores.append(rel)
    return min(scores) - penalty if scores else None


def _core_tokens(query: str) -> list[str]:
    """Suchwörter ohne Beiwerk ("lachsfilet mit haut" → lachsfilet) und ohne führende Mengen."""
    tokens = query.split()
    for i, tok in enumerate(tokens):
        if tok in _QUERY_CUTS and i > 0:
            tokens = tokens[:i]
            break
    while len(tokens) > 1 and tokens[0].isdigit():
        tokens = tokens[1:]
    return ["type" if tok == "typ" else tok for tok in tokens]  # "Typ 405" = "Type 405"


def match_ingredient(
    name: str,
    catalog: Sequence[CatalogEntry],
    synonyms: Mapping[str, int] | None = None,
    *,
    limit: int = 5,
) -> list[IngredientMatch]:
    """Findet passende Katalogeinträge: Synonym (Score 100), exakt, dann Wortbezug (≥ 60).

    `synonyms` bildet normalisierte Aliase auf Katalog-IDs ab. Beim Wortbezug zählen ganze Wörter
    im Kopf des Katalognamens, Wortende ("zwiebel" in "speisezwiebel") und das Kopfwort einer
    Zusammensetzung im Suchbegriff ("kirschtomate" → "tomate"; mit Abzug), dazu `rank_hint`
    und die Kürze des Katalognamens (Tiebreaker). Beiwerk ("mit Haut"), Getränke und Süßwaren
    sowie reine Klangähnlichkeit ergeben keinen Treffer. Das Ergebnis ist nach Score absteigend.
    """
    query = normalize_name(name)
    if not query or limit <= 0:
        return []
    tokens = _core_tokens(query)
    vague = len(tokens) == 1 and tokens[0] in _VAGUE_QUERIES
    core = " ".join(tokens)
    queries = {query, core}
    joined_queries = {q.replace(" ", "") for q in queries}
    query_sweet = any(_is_sweet_word(t) for t in query.split())
    by_id = {e.id: e for e in catalog}
    ranked: list[tuple[float, float, IngredientMatch]] = []  # (Rang, Namenslänge, Treffer)
    seen: set[int] = set()

    if synonyms:
        sid = None
        for key in (query, name.strip().lower(), core):
            sid = synonyms.get(key)
            if sid is not None:
                break
        if sid is not None:
            entry = by_id.get(sid)
            label = entry.name if entry else query
            ranked.append((10_000.0, 0.0, IngredientMatch(sid, label, 100.0, "synonym")))
            seen.add(sid)

    fuzzy: list[tuple[float, float, IngredientMatch]] = []
    for entry in catalog:
        if entry.id in seen:
            continue
        prep = _prepare(entry.name)
        if queries & {prep.full, prep.head} or joined_queries & {prep.full_joined, prep.head_joined}:
            rank = 1000.0 + entry.rank_hint - 0.05 * len(entry.name)
            score = max(0.0, min(100.0, 100.0 + min(entry.rank_hint, 0.0)))
            ranked.append((rank, len(entry.name), IngredientMatch(entry.id, entry.name, score, "exact")))
            seen.add(entry.id)
            continue
        relation = None if vague else _query_score(tokens, prep)
        if relation is None:
            continue
        raw_score = relation + entry.rank_hint - 0.05 * len(entry.name)
        if prep.sweet and not query_sweet:
            raw_score -= 25.0
        score = max(0.0, min(99.0, raw_score))  # 100 bleibt Synonym/exakt vorbehalten
        if score < _MIN_SCORE:
            continue
        hit = IngredientMatch(entry.id, entry.name, round(score, 1), "fuzzy")
        fuzzy.append((raw_score, len(entry.name), hit))
    ranked.extend(fuzzy)
    ranked.sort(key=lambda r: (-r[0], r[1], r[2].ingredient_id))
    return [r[2] for r in ranked[:limit]]
