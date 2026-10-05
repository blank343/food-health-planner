"""Importer für Laborbefund-PDFs (Labor Staber, "Mein Direktlabor").

Reine Funktionen ohne Datenbank. Der PDF-Text (pdfplumber) hat pro Ergebniszeile das Format

    <Analyt> [L|H] <Wert|folgt> <Einheit> [<Referenz>] <Methode> <Material>

z. B. ``MCV L 79 fl 80-96 DFZ E`` oder ``Folsäure H>45.4 nmol/l 9.5-44.9 ECLIA S``.
Die Kopfzeile (Patient, Geburtsdatum, Eingang, Auftragsnummer, Abnahme) wiederholt sich auf jeder Seite.
Unbekannte oder defekte Zeilen werden übersprungen, der Parser wirft nie wegen einer einzelnen Zeile.
"""

import re
from datetime import date, datetime
from pathlib import Path

from app.importers.types import LabReport, LabResultRow

MATERIALS = {"E", "S", "NAF", "P", "U", "B"}

_NUM = r"\d+(?:[.,]\d+)?"
VALUE_RE = re.compile(rf"^[<>]?{_NUM}$")
RANGE_RE = re.compile(rf"^({_NUM})-({_NUM})$")
METHOD_RE = re.compile(r"^[A-ZÄÖÜ][A-ZÄÖÜ0-9/\-]+$")
GLUED_FLAG_RE = re.compile(rf"^([LH])([<>]?{_NUM})$")

HEADER_RE = re.compile(
    r"^(?P<patient>.+?),\s+(?P<sex>[MFWD])\s+(?P<birth>\d{2}\.\d{2}\.\d{4})\s+"
    r"(?P<received>\d{2}\.\d{2}\.\d{4}\s+-\s+\d{2}:\d{2})\s+(?P<order>\d+)\s+"
    r"(?P<sampled>\d{2}\.\d{2}\.\d{4}\s+-\s+\d{2}:\d{2})$"
)

# Erklärende Zeilen, die nie Ergebnisse sind (Kleinschreibung, Präfix-Vergleich)
_EXPLANATORY_PREFIXES = (
    "zielwert",
    "zielwerte",
    "sekundäre zielwert",
    "hinweis",
    "anmerkung",
    "bewertung",
    "kommentar",
    "beurteilung",
    "siehe ",
)


def _num(text: str) -> float:
    return float(text.replace(",", "."))


def _parse_dt(text: str) -> datetime | None:
    try:
        return datetime.strptime(re.sub(r"\s+", " ", text), "%d.%m.%Y - %H:%M")
    except ValueError:
        return None


def _parse_date(text: str) -> date | None:
    try:
        return datetime.strptime(text, "%d.%m.%Y").date()
    except ValueError:
        return None


def _parse_ref(tokens: list[str]) -> tuple[float | None, float | None, str | None]:
    """Referenzbereich -> (ref_low, ref_high, ref_op). Unbekanntes Format: alles None."""
    text = "".join(tokens).replace(" ", "")
    if not text:
        return None, None, None
    m = RANGE_RE.match(text)
    if m:
        return _num(m.group(1)), _num(m.group(2)), None
    if text[0] in "<>" and re.fullmatch(_NUM, text[1:]):
        value = _num(text[1:])
        return (None, value, "<") if text[0] == "<" else (value, None, ">")
    return None, None, None


def _is_explanatory(line: str) -> bool:
    return line.lower().startswith(_EXPLANATORY_PREFIXES)


def parse_result_line(line: str) -> LabResultRow | None:
    """Parst eine einzelne Ergebniszeile. ``None``, wenn die Zeile kein Ergebnis ist. Wirft nie."""
    try:
        return _parse_result_line(line)
    except (ValueError, IndexError):
        return None


def _parse_result_line(line: str) -> LabResultRow | None:
    line = line.strip()
    if not line or _is_explanatory(line):
        return None
    tok = line.split()
    # Flag klebt teils am Wert ("H47", "H>45.4"): wieder trennen (nie am ersten Token = Analytname)
    split: list[str] = []
    for i, t in enumerate(tok):
        m = GLUED_FLAG_RE.match(t) if i > 0 else None
        if m:
            split.extend([m.group(1), m.group(2)])
        else:
            split.append(t)
    tok = split
    if len(tok) < 5 or tok[-1] not in MATERIALS:
        return None
    method = tok[-2]
    if not METHOD_RE.match(method):
        return None
    mid = tok[:-2]
    # erstes Wert-Token (Zahl oder "folgt"), dahinter muss eine Einheit stehen
    for i in range(1, len(mid) - 1):
        t = mid[i]
        if not (VALUE_RE.match(t) or t == "folgt"):
            continue
        unit = mid[i + 1]
        if VALUE_RE.match(unit) or unit == "folgt":
            continue
        name_tokens = mid[:i]
        flag = None
        if len(name_tokens) > 1 and name_tokens[-1] in ("L", "H"):
            flag = name_tokens[-1]
            name_tokens = name_tokens[:-1]
        ref_low, ref_high, ref_op = _parse_ref(mid[i + 2 :])
        row = LabResultRow(
            analyte=" ".join(name_tokens),
            unit=unit,
            value=None,
            flag=flag,
            ref_low=ref_low,
            ref_high=ref_high,
            ref_op=ref_op,
            method=method,
            material=tok[-1],
        )
        if t == "folgt":
            row.pending = True
        else:
            if t[0] in "<>":
                row.value_op = t[0]
            row.value = _num(t.lstrip("<>"))
        return row
    return None


def parse_lab_text_with_stats(text: str) -> tuple[LabReport, dict[str, int | bool]]:
    """Wie ``parse_lab_text``, liefert zusätzlich Zähler zur Plausibilisierung."""
    lines = [ln.strip() for ln in text.splitlines()]
    lines = [ln for ln in lines if ln]

    report_type = "Teilbefund" if "Teilbefund" in text else ("Endbefund" if "Endbefund" in text else "?")
    report = LabReport(report_type=report_type)

    for ln in lines:
        if "Direktlabor" in ln or "Labor" in ln:
            report.lab_name = ln[:200]
            break

    stats: dict[str, int | bool] = {
        "lines": len(lines),
        "header_found": False,
        "parsed": 0,
        "duplicates": 0,
        "skipped": 0,
        "suspicious_skipped": 0,
    }
    seen: set[tuple[str, str]] = set()
    for ln in lines:
        m = HEADER_RE.match(ln)
        if m:
            if not stats["header_found"]:
                stats["header_found"] = True
                report.patient_name = m.group("patient")
                report.birth_date = _parse_date(m.group("birth"))
                report.order_no = m.group("order")
                report.sample_datetime = _parse_dt(m.group("sampled"))
            continue
        row = parse_result_line(ln)
        if row is None:
            stats["skipped"] += 1
            parts = ln.split()
            looks_like_result = len(parts) >= 4 and parts[-1] in MATERIALS and any(c.isdigit() for c in ln)
            if looks_like_result and not _is_explanatory(ln):
                stats["suspicious_skipped"] += 1  # sieht nach Ergebnis aus, ließ sich aber nicht parsen
            continue
        key = (row.analyte, row.unit)
        if key in seen:
            stats["duplicates"] += 1
            continue
        seen.add(key)
        report.results.append(row)
        stats["parsed"] += 1
    return report, stats


def parse_lab_text(text: str) -> LabReport:
    """Parst den extrahierten PDF-Text eines Laborbefunds."""
    return parse_lab_text_with_stats(text)[0]


def import_lab_pdf(path: Path) -> LabReport:
    """Liest ein Laborbefund-PDF (Text per pdfplumber) und parst es."""
    import pdfplumber  # lazy: nur für den PDF-Weg nötig

    with pdfplumber.open(path) as pdf:
        text = "\n".join((page.extract_text() or "") for page in pdf.pages)
    return parse_lab_text(text)
