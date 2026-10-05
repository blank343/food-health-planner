"""Spike c: Laborbefund-PDF (Labor Staber) -> strukturierte Ergebnisse.

Zeilenformat im PDF-Text:
  <Analyt> [L|H] <Wert|folgt> <Einheit> [<Referenz>] <Methode> <Material>
Beispiele:
  MCV L 79 fl 80-96 DFZ E
  Folsäure H >45.4 nmol/l 9.5-44.9 ECLIA S
  Testosteron folgt nmol/l 0.3-1.7 ECLIA S
  Triglyceride 0.38 mmol/l < 1.70 PHOT S
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pdfplumber

MATERIALS = {"E", "S", "NAF", "P", "U", "B"}
VALUE_RE = re.compile(r"^[<>]?\d+(?:[.,]\d+)?$")
RANGE_RE = re.compile(r"^(\d+(?:[.,]\d+)?)-(\d+(?:[.,]\d+)?)$")


def _num(s: str) -> float:
    return float(s.replace(",", "."))


def parse_ref(tokens: list[str]) -> dict:
    text = "".join(tokens).replace(" ", "")
    if not text:
        return {}
    m = RANGE_RE.match(text)
    if m:
        return {"ref_low": _num(m.group(1)), "ref_high": _num(m.group(2))}
    if text.startswith("<") and VALUE_RE.match(text[1:]):
        return {"ref_high": _num(text[1:]), "ref_op": "<"}
    if text.startswith(">") and VALUE_RE.match(text[1:]):
        return {"ref_low": _num(text[1:]), "ref_op": ">"}
    return {"ref_raw": text}


FLAG_GLUED_RE = re.compile(r"(?<=\s)([LH])(?=[<>]?\d)")
HEADER_RE = re.compile(
    r"^(?P<patient>.+?), (?P<sex>[MFWD]) (?P<birth>\d{2}\.\d{2}\.\d{4}) "
    r"(?P<received>\d{2}\.\d{2}\.\d{4} - \d{2}:\d{2}) (?P<order>\d+) "
    r"(?P<sampled>\d{2}\.\d{2}\.\d{4} - \d{2}:\d{2})$"
)


def parse_line(line: str) -> dict | None:
    # pdfplumber klebt die Markierung teils an den Wert ("H47", "H>45.4"), wieder trennen
    line = FLAG_GLUED_RE.sub(r"\1 ", " " + line).strip()
    tok = line.split()
    if len(tok) < 5 or tok[-1] not in MATERIALS:
        return None
    method = tok[-2]
    if not method.isupper() or not method.isalpha():
        return None
    mid = tok[:-2]
    # erstes Wert-Token (Zahl oder 'folgt'), dahinter muss eine Einheit stehen
    for i in range(1, len(mid) - 1):
        t = mid[i]
        if VALUE_RE.match(t) or t == "folgt":
            name_tokens = mid[:i]
            flag = None
            if name_tokens and name_tokens[-1] in ("L", "H") and len(name_tokens) > 1:
                flag = name_tokens[-1]
                name_tokens = name_tokens[:-1]
            unit = mid[i + 1]
            ref = parse_ref(mid[i + 2:])
            row = {
                "analyte": " ".join(name_tokens),
                "unit": unit,
                "flag": flag,
                "method": method,
                "material": tok[-1],
                **ref,
            }
            if t == "folgt":
                row.update({"pending": True, "value": None})
            else:
                op = t[0] if t[0] in "<>" else None
                row.update({"pending": False, "value": _num(t.lstrip("<>")), **({"value_op": op} if op else {})})
            return row
    return None


def parse_pdf(path: Path) -> dict:
    results, header = [], {}
    with pdfplumber.open(path) as pdf:
        text = "\n".join((p.extract_text() or "") for p in pdf.pages)
    for line in text.splitlines():
        m = HEADER_RE.match(line.strip())
        if m:
            header = m.groupdict()
            break
    header["report_type"] = "Teilbefund" if "Teilbefund" in text else ("Endbefund" if "Endbefund" in text else "?")
    for line in text.splitlines():
        row = parse_line(line.strip())
        if row:
            results.append(row)
    return {"header": header, "results": results}


def main() -> None:
    root = Path(__file__).resolve().parents[2] / "Health Daten"
    out = Path(__file__).parent / "out"
    out.mkdir(exist_ok=True)
    for who, pdf in (("christian", next((root / "Christian").glob("Befund_*.pdf"))),
                     ("liesa", next((root / "Liesa").glob("Befund_*.pdf")))):
        res = parse_pdf(pdf)
        (out / f"{who}_lab.json").write_text(json.dumps(res, ensure_ascii=False, indent=1))
        r = res["results"]
        flagged = [(x["analyte"], x["value"], x["unit"], x["flag"]) for x in r if x["flag"]]
        pending = [x["analyte"] for x in r if x["pending"]]
        print(f"\n=== {who}: {res['header']}")
        print(f"Analyte erkannt: {len(r)}, markiert: {flagged}")
        print(f"Ausstehend ('folgt'): {pending}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
