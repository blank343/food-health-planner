"""Tests für den Laborbefund-Importer. Ausschließlich synthetische Daten (erfundene Person/Werte)."""

from datetime import date, datetime

import pytest

from app.importers.lab_pdf import (
    import_lab_pdf,
    parse_lab_text,
    parse_lab_text_with_stats,
    parse_result_line,
)

# --- Zeilenparser (portiert aus dem Spike) ---------------------------------------------------------


def test_normal_range():
    r = parse_result_line("Leukozyten 4.8 G/l 3.7-9.9 DFZ E")
    assert (r.analyte, r.value, r.unit, r.flag) == ("Leukozyten", 4.8, "G/l", None)
    assert (r.ref_low, r.ref_high, r.ref_op) == (3.7, 9.9, None)
    assert (r.method, r.material, r.pending, r.value_op) == ("DFZ", "E", False, None)


def test_low_flag_with_space():
    r = parse_result_line("MCV L 79 fl 80-96 DFZ E")
    assert r.analyte == "MCV" and r.flag == "L" and r.value == 79.0


def test_flag_glued_to_value():
    r = parse_result_line("Lymphozyten H47 % 13-45 DFZ E")
    assert r.analyte == "Lymphozyten" and r.flag == "H" and r.value == 47.0 and r.unit == "%"


def test_value_operator_and_flag():
    r = parse_result_line("Folsäure H>45.4 nmol/l 9.5-44.9 ECLIA S")
    assert r.flag == "H" and r.value == 45.4 and r.value_op == ">"


def test_value_operator_without_flag():
    r = parse_result_line("CRP <0.6 mg/l < 5.0 TURB S")
    assert r.flag is None and r.value == 0.6 and r.value_op == "<"
    assert r.ref_high == 5.0 and r.ref_op == "<"


def test_upper_bound_only_reference():
    r = parse_result_line("Triglyceride 0.38 mmol/l < 1.70 PHOT S")
    assert r.ref_high == 1.7 and r.ref_op == "<" and r.ref_low is None


def test_lower_bound_only_reference_with_flag():
    r = parse_result_line("HDL-Cholesterin L 1.2 mmol/l > 1.2 PHOT S")
    assert r.flag == "L" and r.ref_low == 1.2 and r.ref_op == ">" and r.ref_high is None


def test_pending_value():
    r = parse_result_line("Testosteron folgt nmol/l 0.3-1.7 ECLIA S")
    assert r.pending is True and r.value is None and r.ref_high == 1.7 and r.unit == "nmol/l"


def test_no_reference():
    r = parse_result_line("Apolipoprotein B 57 mg/dl TURB S")
    assert r.value == 57.0 and r.ref_low is None and r.ref_high is None and r.ref_op is None


def test_analyte_with_digits_and_parentheses():
    r = parse_result_line("HbA1c (immunologisch) 5.0 % 4.5-5.6 TURB E")
    assert r.analyte == "HbA1c (immunologisch)" and r.value == 5.0


def test_decimal_commas():
    r = parse_result_line("Ferritin 41,5 µg/l 30,0-400,0 ECLIA S")
    assert r.value == 41.5 and (r.ref_low, r.ref_high) == (30.0, 400.0)
    r = parse_result_line("Kreatinin <0,3 mg/dl < 1,2 PHOT S")
    assert r.value == 0.3 and r.value_op == "<" and r.ref_high == 1.2


def test_analyte_starting_with_flag_letter_is_not_a_flag():
    r = parse_result_line("LDL-Cholesterin 2.9 mmol/l < 3.0 PHOT S")
    assert r.analyte == "LDL-Cholesterin" and r.flag is None


def test_non_result_lines_ignored():
    assert parse_result_line("Differentialblutbild autom.abs. E") is None
    assert parse_result_line("Hinweise zu den Untersuchungsstandorten einzelner Parameter") is None
    assert parse_result_line("Zielwert < 3.0 mmol/l bei niedrigem Risiko") is None
    assert parse_result_line("Sekundäre Zielwerte: LDL < 2.6 mmol/l bei hohem Risiko PHOT S") is None
    assert parse_result_line("") is None


@pytest.mark.parametrize(
    "line",
    [
        "x",
        "Wert 12 mg/dl",  # kein Material
        "Wert 12 mg/dl 1-2 abc E",  # Methode nicht in Großbuchstaben
        "Wert 1-2-3 mg/dl PHOT S",  # kein parsbarer Wert
        "12 34 56 78 PHOT S",  # nur Zahlen
        "Muster Max, M 01.01.1990 02.01.2026 - 08:00 1234567890 01.01.2026 - 07:00",
    ],
)
def test_odd_lines_never_raise(line):
    assert parse_result_line(line) is None


def test_unparseable_reference_is_ignored_but_row_kept():
    r = parse_result_line("Wert 5 mg/dl negativ PHOT S")
    assert r is not None and r.ref_low is None and r.ref_high is None


# --- Gesamter Text ---------------------------------------------------------------------------------

HEADER = "Muster Max, M 01.01.1990 03.02.2026 - 08:15 1234567890 02.02.2026 - 07:45"

PAGE1 = f"""Mein Direktlabor Beispielstadt
Labor Beispiel GmbH
Teilbefund
{HEADER}
Untersuchung Ergebnis Einheit Referenz Methode Material
Differentialblutbild autom.abs. E
Leukozyten 4.8 G/l 3.7-9.9 DFZ E
MCV L 79 fl 80-96 DFZ E
Lymphozyten 1.9 G/l 1.1-3.5 DFZ E
Lymphozyten H47 % 13-45 DFZ E
HbA1c (immunologisch) 5.0 % 4.5-5.6 TURB E
HbA1c (immunologisch) 31 mmol/mol 26-38 TURB E
Folsäure H>45.4 nmol/l 9.5-44.9 ECLIA S
Testosteron folgt nmol/l 0.3-1.7 ECLIA S
Vitamin B12 folgt pmol/l 140-700 ECLIA S
"""

PAGE2 = f"""{HEADER}
Untersuchung Ergebnis Einheit Referenz Methode Material
MCV L 79 fl 80-96 DFZ E
Triglyceride 0.38 mmol/l < 1.70 PHOT S
HDL-Cholesterin L 1.2 mmol/l > 1.2 PHOT S
Zielwert < 3.0 mmol/l bei niedrigem Risiko
Sekundäre Zielwerte siehe Leitlinie
CRP <0.6 mg/l < 5.0 TURB S
Apolipoprotein B 57 mg/dl TURB S
Ferritin 41,5 µg/l 30,0-400,0 ECLIA S
Hinweise zu den Untersuchungsstandorten einzelner Parameter
Seite 2 von 2
"""

TEXT = PAGE1 + PAGE2


def test_parse_lab_text_header_fields():
    rep = parse_lab_text(TEXT)
    assert rep.report_type == "Teilbefund"
    assert rep.lab_name == "Mein Direktlabor Beispielstadt"
    assert rep.order_no == "1234567890"
    assert rep.sample_datetime == datetime(2026, 2, 2, 7, 45)
    assert rep.patient_name == "Muster Max"
    assert rep.birth_date == date(1990, 1, 1)


def test_parse_lab_text_results():
    rep, stats = parse_lab_text_with_stats(TEXT)
    by_key = {(r.analyte, r.unit): r for r in rep.results}
    # doppelte Kopfblöcke/Wiederholungen werden nicht mehrfach gezählt; 14 verschiedene Ergebnisse
    assert len(rep.results) == len(by_key) == 14
    assert stats["parsed"] == 14 and stats["duplicates"] == 1
    assert stats["header_found"] is True
    assert stats["suspicious_skipped"] == 0

    assert by_key[("MCV", "fl")].flag == "L"
    assert by_key[("Lymphozyten", "%")].flag == "H" and by_key[("Lymphozyten", "%")].value == 47.0
    assert by_key[("Folsäure", "nmol/l")].value_op == ">"
    assert by_key[("CRP", "mg/l")].value_op == "<" and by_key[("CRP", "mg/l")].value == 0.6
    assert by_key[("Triglyceride", "mmol/l")].ref_op == "<"
    assert by_key[("Ferritin", "µg/l")].value == 41.5


def test_pending_rows_in_teilbefund():
    rep = parse_lab_text(TEXT)
    pending = [r for r in rep.results if r.pending]
    assert {r.analyte for r in pending} == {"Testosteron", "Vitamin B12"}
    assert all(r.value is None and r.flag is None for r in pending)
    assert sum(1 for r in rep.results if r.flag) == 4  # MCV, Lymphozyten %, Folsäure, HDL


def test_same_analyte_with_two_units_is_kept():
    rep = parse_lab_text(TEXT)
    hba1c = [r for r in rep.results if r.analyte == "HbA1c (immunologisch)"]
    assert {(r.unit, r.value) for r in hba1c} == {("%", 5.0), ("mmol/mol", 31.0)}
    lympho = [r for r in rep.results if r.analyte == "Lymphozyten"]
    assert {r.unit for r in lympho} == {"G/l", "%"}


def test_duplicate_key_keeps_first_occurrence():
    text = f"""Endbefund
{HEADER}
Natrium 140 mmol/l 135-145 ISE S
{HEADER}
Natrium 99 mmol/l 135-145 ISE S
"""
    rep, stats = parse_lab_text_with_stats(text)
    assert [r.value for r in rep.results] == [140.0]
    assert stats["duplicates"] == 1


def test_endbefund_type_and_unknown_type():
    assert parse_lab_text(f"Endbefund\n{HEADER}\nNatrium 140 mmol/l 135-145 ISE S").report_type == "Endbefund"
    assert parse_lab_text("nichts Brauchbares").report_type == "?"


def test_garbage_text_does_not_raise():
    rep, stats = parse_lab_text_with_stats("\x00\n  \n§$%&/()\nFoo 1 2 3 4 5 6 7\n")
    assert rep.results == [] and rep.order_no is None and rep.birth_date is None
    assert rep.sample_datetime is None and rep.lab_name is None
    assert stats["header_found"] is False


def test_suspicious_lines_are_counted():
    # sieht nach Ergebnis aus (endet auf Material), Wert fehlt aber
    text = "Foo bar 5x baz PHOT S\nHinweis zu 5 etwas DFZ E\nDifferentialblutbild autom.abs. E"
    _, stats = parse_lab_text_with_stats(text)
    assert stats["suspicious_skipped"] == 1


def test_import_lab_pdf_uses_pdfplumber(tmp_path, monkeypatch):
    pdfplumber = pytest.importorskip("pdfplumber")

    class FakePage:
        def __init__(self, text):
            self._text = text

        def extract_text(self):
            return self._text

    class FakePdf:
        pages = [FakePage(PAGE1), FakePage(None), FakePage(PAGE2)]

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr(pdfplumber, "open", lambda path: FakePdf())
    rep = import_lab_pdf(tmp_path / "x.pdf")
    assert rep.order_no == "1234567890" and len(rep.results) == 14
