"""Tests für parse_lab.parse_line (synthetische Zeilen, keine echten Daten nötig)."""
from parse_lab import parse_line


def test_normal_range():
    r = parse_line("Leukozyten 4.8 G/l 3.7-9.9 DFZ E")
    assert (r["analyte"], r["value"], r["unit"], r["flag"]) == ("Leukozyten", 4.8, "G/l", None)
    assert (r["ref_low"], r["ref_high"]) == (3.7, 9.9)


def test_low_flag_with_space():
    r = parse_line("MCV L 79 fl 80-96 DFZ E")
    assert r["analyte"] == "MCV" and r["flag"] == "L" and r["value"] == 79.0


def test_flag_glued_to_value():
    r = parse_line("Lymphozyten H47 % 13-45 DFZ E")
    assert r["flag"] == "H" and r["value"] == 47.0 and r["unit"] == "%"


def test_value_operator_and_flag():
    r = parse_line("Folsäure H>45.4 nmol/l 9.5-44.9 ECLIA S")
    assert r["flag"] == "H" and r["value"] == 45.4 and r["value_op"] == ">"


def test_upper_bound_only_reference():
    r = parse_line("Triglyceride 0.38 mmol/l < 1.70 PHOT S")
    assert r["ref_high"] == 1.7 and r["ref_op"] == "<" and "ref_low" not in r


def test_lower_bound_only_reference_with_flag():
    r = parse_line("HDL-Cholesterin L 1.2 mmol/l > 1.2 PHOT S")
    assert r["flag"] == "L" and r["ref_low"] == 1.2 and r["ref_op"] == ">"


def test_pending_value():
    r = parse_line("Testosteron folgt nmol/l 0.3-1.7 ECLIA S")
    assert r["pending"] is True and r["value"] is None and r["ref_high"] == 1.7


def test_no_reference():
    r = parse_line("Apolipoprotein B 57 mg/dl TURB S")
    assert r["value"] == 57.0 and "ref_low" not in r and "ref_high" not in r


def test_analyte_with_digits_and_parentheses():
    r = parse_line("HbA1c (immunologisch) 5.0 % 4.5-5.6 TURB E")
    assert r["analyte"] == "HbA1c (immunologisch)" and r["value"] == 5.0


def test_non_result_lines_ignored():
    assert parse_line("Differentialblutbild autom.abs. E") is None
    assert parse_line("Hinweise zu den Untersuchungsstandorten einzelner Parameter") is None
    assert parse_line("Zielwert < 3.0 mmol/l bei niedrigem Risiko") is None
