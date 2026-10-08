"""Tests für den BLS-Importer. Nur erfundene, synthetische Dateien (keine echten BLS-Daten)."""

import zipfile
from pathlib import Path

import pytest
from openpyxl import Workbook

from app.calc.defaults import MICRO_KEYS
from app.importers import bls
from app.importers.bls import (
    bls_dish_flag,
    bls_group_name,
    bls_raw_flag,
    import_bls,
    import_bls_with_stats,
)

# (Code, Bezeichnung, Einheit) in der Reihenfolge und Schreibweise der echten Kopfzeile;
# je Nährstoff folgen "<CODE> Datenherkunft" und "<CODE> Referenz".
NUTRIENTS = [
    ("ENERCJ", "Energie (Kilojoule)", "kJ"),
    ("ENERCC", "Energie (Kilokalorien)", "kcal"),
    ("WATER", "Wasser", "g"),
    ("PROT625", "Protein (Nx6,25)", "g"),
    ("FAT", "Fett", "g"),
    ("CHO", "Kohlenhydrate, verfügbar", "g"),
    ("FIBT", "Ballaststoffe, gesamt", "g"),
    ("VITA", "Vitamin A, Retinol-Äquivalent (RE)", "µg"),
    ("VITD", "Vitamin D", "µg"),
    ("VITE", "Vitamin E (Alpha-Tocopherol)", "mg"),
    ("VITK", "Vitamin K", "µg"),
    ("VITB6", "Vitamin B6", "µg"),
    ("FOL", "Folat-Äquivalent", "µg"),
    ("VITB12", "Vitamin B12 (Cobalamine)", "µg"),
    ("VITC", "Vitamin C", "mg"),
    ("NACL", "Salz (Natriumchlorid)", "g"),
    ("NA", "Natrium", "mg"),
    ("K", "Kalium", "mg"),
    ("CA", "Calcium", "mg"),
    ("MG", "Magnesium", "mg"),
    ("P", "Phosphor", "mg"),
    ("FE", "Eisen", "mg"),
    ("ZN", "Zink", "mg"),
    ("ID", "Iodid", "µg"),
    ("SUGAR", "Zucker (Mono- und Disaccharide), gesamt", "g"),
    ("FASAT", "Fettsäuren, gesättigt, gesamt", "g"),
    ("FAPUN3", "Fettsäuren, mehrfach ungesättigt n-3 (Omega-3), gesamt", "g"),
    ("F20:5CN3", "Fettsäure C20:5 n-3 all-cis (Eicosapentaensäure)", "g"),
    ("F22:6CN3", "Fettsäure C22:6 n-3 all-cis (Docosahexaensäure)", "g"),
]


def _header(units: dict[str, str] | None = None) -> list[str]:
    head = ["BLS Code", "Lebensmittelbezeichnung", "Food name"]
    for code, label, unit in NUTRIENTS:
        head += [
            f"{code} {label} [{(units or {}).get(code, unit)}/100g]",
            f"{code} Datenherkunft",
            f"{code} Referenz",
        ]
    return head


def _row(code, name, values: dict[str, object] | None = None, english="Test food") -> list[object]:
    row: list[object] = [code, name, english]
    for nutrient, _label, _unit in NUTRIENTS:
        value = (values or {}).get(nutrient)
        row += [value, "Analyse" if value is not None else None, "-" if value is not None else None]
    return row


FOODS = [
    # normaler Eintrag mit kcal, NACL und vielen Mikros
    _row(
        "G100100", "Testzwiebel roh",
        {"ENERCJ": 142, "ENERCC": 34, "PROT625": 1.2, "FAT": 0.15, "CHO": 6.0, "FIBT": 1.4,
         "NACL": 0.022, "NA": 9, "K": 174, "CA": 31, "MG": 10, "P": 33, "FE": 0.3, "ZN": 0.21,
         "ID": 1.5, "VITA": 2, "VITD": 0, "VITE": 0.25, "VITK": 4, "VITC": 7, "VITB12": 0, "FOL": 20,
         "SUGAR": 4.2, "FASAT": 0.03, "FAPUN3": 0.01, "VITB6": 120, "WATER": 89},
    ),  # fmt: skip
    # Salz kommt aus NACL, nicht aus Natrium × 2,5
    _row(
        "E100100", "Testei roh",
        {"ENERCC": 135, "PROT625": 13.2, "FAT": 9.0, "CHO": 0.3, "FIBT": 0, "NACL": 0.385, "NA": 154,
         "ZN": 1.28},
    ),  # fmt: skip
    # Fisch: EPA + DHA werden addiert, T = Warengruppe Fisch
    _row(
        "T100100", "Testlachs roh",
        {"ENERCC": 200, "PROT625": 20, "FAT": 13, "CHO": 0, "FAPUN3": 2.5, "F20:5CN3": 0.8,
         "F22:6CN3": 1.2, "VITD": 8.7, "NA": 40},
    ),  # fmt: skip
    # nur kJ (kein kcal), kein NACL aber Natrium (2 mg → 0,005 g Salz), Warengruppe Fette/Öle
    _row("Q100000", "Testöl", {"ENERCJ": 3700, "PROT625": 0, "FAT": 99.9, "CHO": 0, "NA": 2}),
    # nicht numerische Werte: "-" und Text → None, numerischer Text mit Komma → Zahl
    _row(
        "F100100", "Testbeere roh",
        {"ENERCC": 50, "PROT625": "-", "FAT": "Spuren", "CHO": "12,5", "FIBT": "", "NA": "n.b."},
    ),  # fmt: skip
    # nur EPA (DHA fehlt): Summe = EPA
    _row("M100100", "Testfisch-Käse", {"ENERCC": 300, "PROT625": 5, "FAT": 25, "F20:5CN3": 0.1}),
    # Gericht (X): wird importiert, ist aber ein Gericht
    _row("X100143", "Testgericht gebraten", {"ENERCC": 180, "PROT625": 10, "FAT": 8, "CHO": 15}),
    # Zeilen, die übersprungen werden: keine Energie und keine Makros / kein Name / kein Code
    _row("R200000", "Testgewürz ohne Werte", {"WATER": 10, "NA": 5, "PROT625": "-", "FAT": "-"}),
    _row("G999900", "", {"ENERCC": 10, "PROT625": 1}),
    _row(None, "Eintrag ohne Code", {"ENERCC": 10, "PROT625": 1}),
    # komplett leere Zeile (Dateiende): zählt nicht
    [None] * len(_header()),
]


def _write_xlsx(path: Path, rows=None, header=None) -> Path:
    wb = Workbook()
    ws = wb.active
    ws.title = "BLS_4_0_Test"
    ws.append(header if header is not None else _header())
    for row in rows if rows is not None else FOODS:
        ws.append(row)
    wb.save(path)
    return path


def _write_zip(path: Path, xlsx: Path) -> Path:
    comp = path.parent / "components.xlsx"
    wb = Workbook()
    wb.active.append(["Index", "Nährstoffcode / Component code", "Nährstoffbezeichnung"])
    wb.active.append([1, "ENERCJ", "Energie (Kilojoule)"])
    wb.save(comp)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.write(comp, "BLS_4_0_2025_DE/BLS_4_0_Components_DE_EN.xlsx")
        zf.write(xlsx, "BLS_4_0_2025_DE/BLS_4_0_Daten_2025_DE.xlsx")
        zf.writestr("BLS_4_0_2025_DE/BLS_4_0_Dokumentation_DE.pdf", b"%PDF-1.4 dummy")
    return path


@pytest.fixture
def xlsx_path(tmp_path) -> Path:
    return _write_xlsx(tmp_path / "BLS_4_0_Daten_2025_DE.xlsx")


@pytest.fixture
def records(xlsx_path):
    return {r.source_code: r for r in import_bls(xlsx_path)}


# ---------------------------------------------------------------------------
# Mapping
# ---------------------------------------------------------------------------


def test_stats_and_skipped_rows(xlsx_path):
    recs, stats = import_bls_with_stats(xlsx_path)
    assert stats == {"rows": 10, "imported": 7, "skipped": 3}
    assert [r.source_code for r in recs] == [
        "G100100", "E100100", "T100100", "Q100000", "F100100", "M100100", "X100143",
    ]  # fmt: skip
    assert len(import_bls(xlsx_path)) == 7


def test_basic_mapping(records):
    onion = records["G100100"]
    assert onion.name == "Testzwiebel roh"
    assert onion.source == "bls"
    assert onion.category == "Gemüse"
    assert onion.kcal_100 == pytest.approx(34)  # kcal, nicht kJ (142)
    assert onion.protein_100 == pytest.approx(1.2)
    assert onion.fat_100 == pytest.approx(0.15)
    assert onion.carb_100 == pytest.approx(6.0)
    assert onion.fiber_100 == pytest.approx(1.4)
    assert onion.salt_100 == pytest.approx(0.022)
    assert onion.is_fish is False


def test_micros_mapping_and_units(records):
    micros = records["G100100"].micros
    expected = {
        "sat_fat_g": 0.03, "sugar_g": 4.2, "omega3_g": 0.01, "sodium_mg": 9, "potassium_mg": 174,
        "calcium_mg": 31, "magnesium_mg": 10, "phosphorus_mg": 33, "iron_mg": 0.3, "zinc_mg": 0.21,
        "iodine_ug": 1.5, "vit_a_ug": 2, "vit_d_ug": 0, "vit_e_mg": 0.25, "vit_k_ug": 4,
        "vit_c_mg": 7, "vit_b12_ug": 0, "folate_ug": 20,
    }  # fmt: skip
    assert micros == pytest.approx(expected)
    # nicht gesetzte Mikros (kein EPA/DHA in der Zeile) fehlen, nicht 0
    assert "epa_dha_g" not in micros
    assert "VITB6" not in micros and "vit_b6_ug" not in micros


def test_micro_keys_are_exactly_the_calc_keys(records):
    assert set(bls.MICRO_CODES) | {"epa_dha_g"} == set(MICRO_KEYS)
    for rec in records.values():
        assert set(rec.micros) <= set(MICRO_KEYS)


def test_only_set_micros_are_included(records):
    egg = records["E100100"]
    assert egg.micros == pytest.approx({"sodium_mg": 154, "zinc_mg": 1.28})


def test_salt_from_nacl_not_from_sodium(records):
    egg = records["E100100"]
    assert egg.salt_100 == pytest.approx(0.385)  # NACL gewinnt gegen 154 mg × 2,5
    assert egg.kcal_100 == pytest.approx(135)


def test_salt_from_sodium_when_nacl_missing(records):
    oil = records["Q100000"]
    assert oil.salt_100 == pytest.approx(2 * 2.5 / 1000)
    assert oil.micros["sodium_mg"] == pytest.approx(2)


def test_kcal_from_kj_fallback(records):
    assert records["Q100000"].kcal_100 == pytest.approx(3700 / 4.184)
    assert records["Q100000"].category == "Fette und Öle"


def test_epa_dha_sum_and_partial(records):
    salmon = records["T100100"]
    assert salmon.micros["epa_dha_g"] == pytest.approx(2.0)
    assert salmon.micros["omega3_g"] == pytest.approx(2.5)
    assert salmon.micros["vit_d_ug"] == pytest.approx(8.7)
    assert records["M100100"].micros["epa_dha_g"] == pytest.approx(0.1)  # DHA fehlt = 0


def test_non_numeric_values_become_none(records):
    berry = records["F100100"]
    assert berry.kcal_100 == pytest.approx(50)
    assert berry.protein_100 is None  # "-"
    assert berry.fat_100 is None  # Text
    assert berry.carb_100 == pytest.approx(12.5)  # numerischer Text mit Komma
    assert berry.fiber_100 is None  # leere Zelle
    assert berry.salt_100 is None  # "n.b." als Natrium, NACL fehlt
    assert berry.micros == {}


def test_negative_and_special_values_are_not_numbers():
    assert bls._num(-1) is None
    assert bls._num(float("nan")) is None
    assert bls._num(True) is None
    assert bls._num("1,5") == pytest.approx(1.5)
    assert bls._num(" 3 ") == pytest.approx(3.0)
    assert bls._num("<0,1") is None
    assert bls._num(0) == 0.0


def test_unit_mismatch_is_converted(tmp_path):
    # Eine Datei, in der Iod in mg und Natrium in g stehen, wird auf µg bzw. mg umgerechnet
    header = _header({"ID": "mg", "NA": "g"})
    rows = [_row("G100100", "Testzwiebel roh", {"ENERCC": 34, "ID": 0.0015, "NA": 0.009})]
    recs = import_bls(_write_xlsx(tmp_path / "u.xlsx", rows, header))
    assert recs[0].micros["iodine_ug"] == pytest.approx(1.5)
    assert recs[0].micros["sodium_mg"] == pytest.approx(9.0)
    assert recs[0].salt_100 == pytest.approx(0.0225)  # aus dem umgerechneten Natrium


def test_incompatible_unit_raises(tmp_path):
    header = _header({"ID": "kJ"})
    with pytest.raises(ValueError, match="ID"):
        import_bls(_write_xlsx(tmp_path / "u.xlsx", [_row("G100100", "x", {"ENERCC": 1})], header))


def test_columns_found_by_header_not_by_position(tmp_path):
    # Spaltenreihenfolge vertauscht (und eine unbekannte Zusatzspalte): Zuordnung bleibt richtig
    head = _header()
    rows = [_row("G100100", "Testzwiebel roh", {"ENERCC": 34, "PROT625": 1.2, "ZN": 0.21})]
    swap = [3 + 3 * 1, 3 + 3 * 3]  # ENERCC und PROT625 (Wertspalten) vertauschen
    head[swap[0]], head[swap[1]] = head[swap[1]], head[swap[0]]
    rows[0][swap[0]], rows[0][swap[1]] = rows[0][swap[1]], rows[0][swap[0]]
    rec = import_bls(_write_xlsx(tmp_path / "s.xlsx", rows, head))[0]
    assert rec.kcal_100 == pytest.approx(34)
    assert rec.protein_100 == pytest.approx(1.2)


# ---------------------------------------------------------------------------
# Warengruppen, Flags
# ---------------------------------------------------------------------------


def test_categories_and_fish(records):
    assert records["T100100"].category == "Fisch und Meeresfrüchte"
    assert records["T100100"].is_fish is True
    assert records["M100100"].category == "Milch und Milchprodukte"
    assert records["E100100"].category == "Eier und Teigwaren"
    assert records["X100143"].category.startswith("Gerichte")
    assert records["G100100"].is_fish is False and records["Q100000"].is_fish is False


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        ("B121000", "Brot und Kleingebäck"),
        ("C131000", "Getreide und Getreideprodukte"),
        ("F301100", "Obst"),
        ("P610000", "Alkoholische Getränke"),
        ("U211100", "Fleisch"),
        ("V132100", "Geflügel, Wild und Innereien"),
        ("W131000", "Wurstwaren und Fleischerzeugnisse"),
        ("K701152", "Kartoffeln, Pilze und Stärke"),
        ("g480100", "Gemüse"),  # Kleinbuchstabe
        ("Z000000", None),
        ("", None),
    ],
)
def test_group_name(code, expected):
    assert bls_group_name(code) == expected


def test_all_groups_have_names():
    assert all(name for name in bls.BLS_GROUPS.values())
    assert set(bls.BLS_GROUPS) >= set("BCDEFGHKMNPQRSTUVWXY")


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        ("X411243", True),
        ("Y720143", True),
        ("x100000", True),
        ("G480100", False),
        ("E111100", False),
        ("M713100", False),
        ("D330300", False),
        ("", False),
    ],
)
def test_dish_flag(code, expected):
    assert bls_dish_flag(code) is expected


@pytest.mark.parametrize(
    ("code", "name", "expected"),
    [
        ("G480100", "Speisezwiebel roh", True),
        ("E111100", "Hühnerei roh", True),
        ("Y720143", "Rührei gebraten", False),
        ("T422112", "Forelle/Regenbogenforellen-Filet mit Haut, roh", True),  # Code endet nicht auf 00
        ("Q120000", "Olivenöl", True),  # Grundprodukt: Code endet auf 00, keine Verarbeitung
        ("C133000", "Hafer Flocken", True),
        ("E111182", "Hühnerei gebraten ohne Fett (Pfanne)", False),
        ("F301400", "Erdbeere getrocknet", False),  # endet auf 00, aber verarbeitet
        ("G341132", "Rotkohl gekocht", False),
        ("W442000", "Schwarzwälder Schinken, Rohpökelware, geräuchert", False),  # kein Wort "roh"
        ("M114100", "Rohmilch/Vorzugsmilch, mind. 3,5 % Fett", True),  # Grundprodukt (Code ...00)
        ("X9A6030", "Hefeteig für Pizza/Pizzateig, roh", False),  # Gericht/Zubereitung
        ("B121000", "Roggenvollkornbrot", False),  # Brot ist kein Grundprodukt
        ("W112300", "Braunschweiger Mettwurst, fettreduziert", False),
        ("", "Speisezwiebel roh", False),
    ],
)
def test_raw_flag(code, name, expected):
    assert bls_raw_flag(code, name) is expected


# ---------------------------------------------------------------------------
# Eingabeformate
# ---------------------------------------------------------------------------


def test_zip_input_reads_data_file_without_extracting(tmp_path, xlsx_path):
    zip_path = _write_zip(tmp_path / "BLS_4_0_2025_DE.zip", xlsx_path)
    before = {p.name for p in tmp_path.iterdir()}
    recs, stats = import_bls_with_stats(zip_path)
    assert stats == {"rows": 10, "imported": 7, "skipped": 3}
    assert recs[0].source_code == "G100100"
    assert {p.name for p in tmp_path.iterdir()} == before  # nichts entpackt


def test_zip_and_xlsx_give_same_result(tmp_path, xlsx_path):
    zip_path = _write_zip(tmp_path / "bls.zip", xlsx_path)
    assert import_bls(zip_path) == import_bls(xlsx_path)


def test_accepts_str_path(xlsx_path):
    assert len(import_bls(str(xlsx_path))) == 7  # type: ignore[arg-type]


def test_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        import_bls(tmp_path / "gibt-es-nicht.xlsx")


def test_not_a_zip_or_xlsx(tmp_path):
    path = tmp_path / "x.csv"
    path.write_text("a,b\n1,2\n", encoding="utf-8")
    with pytest.raises(ValueError, match="weder XLSX noch ZIP"):
        import_bls(path)


def test_zip_without_xlsx(tmp_path):
    path = tmp_path / "leer.zip"
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("readme.txt", "nix")
    with pytest.raises(ValueError, match="keine XLSX"):
        import_bls(path)


def test_xlsx_with_wrong_structure(tmp_path):
    path = tmp_path / "andere.xlsx"
    wb = Workbook()
    wb.active.append(["Name", "Wert"])
    wb.active.append(["a", 1])
    wb.save(path)
    with pytest.raises(ValueError, match="BLS"):
        import_bls(path)


def test_xlsx_without_energy_columns(tmp_path):
    path = tmp_path / "ohne_energie.xlsx"
    wb = Workbook()
    wb.active.append(["BLS Code", "Lebensmittelbezeichnung", "Food name", "FAT Fett [g/100g]"])
    wb.active.append(["X1", "a", "b", 1])
    wb.save(path)
    with pytest.raises(ValueError, match="Energie"):
        import_bls(path)


# ---------------------------------------------------------------------------
# Fortschritt
# ---------------------------------------------------------------------------


def test_progress_messages(xlsx_path, monkeypatch):
    monkeypatch.setattr(bls, "PROGRESS_EVERY_ROWS", 4)
    calls: list[tuple[float, str]] = []
    import_bls(xlsx_path, lambda fraction, message: calls.append((fraction, message)))
    fractions = [c[0] for c in calls]
    assert fractions[0] == 0.0 and fractions[-1] == 1.0
    assert fractions == sorted(fractions)
    assert all(0.0 <= f <= 1.0 for f in fractions)
    assert len(calls) >= 4  # Start, zwei Zwischenmeldungen (Zeile 4 und 8), Ende
    assert all(isinstance(m, str) and m.startswith("BLS") for _, m in calls)
    assert "7 Zutaten" in calls[-1][1] and "3 Zeilen übersprungen" in calls[-1][1]


def test_progress_is_optional(xlsx_path):
    assert import_bls(xlsx_path, None)
