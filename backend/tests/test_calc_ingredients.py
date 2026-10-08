"""Tests für calc/ingredients.py und calc/synonym_seed.py (nur synthetische Daten, keine BLS-Datei)."""

import pytest

from app.calc import defaults
from app.calc.ingredients import (
    CatalogEntry,
    match_ingredient,
    mean_quantity,
    normalize_name,
    parse_ingredient_line,
    to_grams,
)
from app.calc.synonym_seed import _RAW_SEED, SYNONYM_SEED, _build_seed
from app.calc.types import ParsedIngredient

# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

# (Zeile, Name, Menge, Menge max, Einheit, Zusatz, optional)
PARSE_CASES = [
    ("200 g Mehl", "Mehl", 200, None, "g", None, False),
    ("1 Zwiebel", "Zwiebel", 1, None, None, None, False),
    ("½ Bund Petersilie", "Petersilie", 0.5, None, "Bund", None, False),
    ("2 EL Olivenöl", "Olivenöl", 2, None, "EL", None, False),
    ("500 ml Milch", "Milch", 500, None, "ml", None, False),
    ("1 Prise Salz", "Salz", 1, None, "Prise", None, False),
    ("Salz und Pfeffer", "Salz und Pfeffer", None, None, None, None, False),
    ("3-4 Karotten", "Karotten", 3, 4, None, None, False),
    ("3 bis 4 Zwiebeln", "Zwiebeln", 3, 4, None, None, False),
    ("2-3 EL Zitronensaft", "Zitronensaft", 2, 3, "EL", None, False),
    ("1,5 kg Kartoffeln", "Kartoffeln", 1.5, None, "kg", None, False),
    ("1,5 l Wasser", "Wasser", 1.5, None, "l", None, False),
    ("1/2 TL Zimt", "Zimt", 0.5, None, "TL", None, False),
    ("1 1/2 EL Senf", "Senf", 1.5, None, "EL", None, False),
    ("1½ Tassen Reis", "Reis", 1.5, None, "Tasse", None, False),
    ("¼ l Milch", "Milch", 0.25, None, "l", None, False),
    ("⅓ Tasse Milch", "Milch", 1 / 3, None, "Tasse", None, False),
    ("¾ l Wasser", "Wasser", 0.75, None, "l", None, False),
    ("2 Knoblauchzehen", "Knoblauch", 2, None, "Zehe", None, False),
    ("2 Zehen Knoblauch", "Knoblauch", 2, None, "Zehe", None, False),
    ("6 Toastscheiben", "Toast", 6, None, "Scheibe", None, False),
    ("4 Scheiben Toast", "Toast", 4, None, "Scheibe", None, False),
    ("1 Dose Tomaten (400 g)", "Tomaten", 400, None, "g", "1 Dose", False),
    ("2 Dosen Tomaten (je 400 g)", "Tomaten", 800, None, "g", "2 Dosen", False),
    ("1 Bund Suppengrün (ca. 300 g)", "Suppengrün", 300, None, "g", "1 Bund", False),
    ("1 Dose Linsen (Abtropfgewicht 240 g)", "Linsen", 240, None, "g", "1 Dose; Abtropfgewicht 240 g", False),
    ("ca. 200 g Skyr", "Skyr", 200, None, "g", None, False),
    ("etwa 3 EL Öl", "Öl", 3, None, "EL", None, False),
    ("1 Einheit Suppengrün: Karotte, Sellerie", "Suppengrün", 1, None, "Stück", "Karotte, Sellerie", False),
    ("2 Stk. Eier", "Eier", 2, None, "Stück", None, False),
    ("Petersilie, nach Belieben", "Petersilie", None, None, None, None, True),
    ("evtl. 1 TL Honig", "Honig", 1, None, "TL", None, True),
    ("1 Zitrone (optional)", "Zitrone", 1, None, None, None, True),
    ("Salz nach Geschmack", "Salz", None, None, None, "nach Geschmack", False),
    ("200g Hafer", "Hafer", 200, None, "g", None, False),
    ("2EL Öl", "Öl", 2, None, "EL", None, False),
    ("1 Zwiebel, fein gehackt", "Zwiebel", 1, None, None, "fein gehackt", False),
    ("400 g Hähnchenbrust, in Streifen", "Hähnchenbrust", 400, None, "g", "in Streifen", False),
    ("2 Eier (Größe M)", "Eier", 2, None, None, "Größe M", False),
    ("200 g Mehl (Type 405)", "Mehl", 200, None, "g", "Type 405", False),
    ("100 g Skyr (oder Quark)", "Skyr", 100, None, "g", "oder Quark", False),
    ("eine Prise Zucker", "Zucker", 1, None, "Prise", None, False),
    ("Prise Salz", "Salz", 1, None, "Prise", None, False),
    ("eine halbe Zitrone", "Zitrone", 0.5, None, None, None, False),
    ("etwas Salz", "Salz", None, None, None, None, False),
    ("1 Pck. Vanillezucker", "Vanillezucker", 1, None, "Packung", None, False),
    ("2 Zweige Rosmarin", "Rosmarin", 2, None, "Zweig", None, False),
    ("1 Handvoll Rucola", "Rucola", 1, None, "Handvoll", None, False),
    ("Mehl zum Bestäuben", "Mehl", None, None, None, "zum Bestäuben", False),
    ("1 EL Olivenöl zum Braten", "Olivenöl", 1, None, "EL", "zum Braten", False),
    ("1 kleine Zwiebel", "kleine Zwiebel", 1, None, None, None, False),
    ("7-Korn-Brot", "7-Korn-Brot", None, None, None, None, False),
    ("Zwiebel", "Zwiebel", None, None, None, None, False),
    ("250 g Magerquark", "Magerquark", 250, None, "g", None, False),
    # Zeilen aus echten Rezepten (ähnlich nachgebaut)
    ("5 Stängel Petersilie, glatt oder kraus", "Petersilie", 5, None, "Zweig", "glatt oder kraus", False),
    ("3 Stiele Thymian", "Thymian", 3, None, "Zweig", None, False),
    ("2 Stiele Staudensellerie", "Staudensellerie", 2, None, "Stange", None, False),
    ("2 Möhre (je ca. 150 g)", "Möhre", 300, None, "g", None, False),
    ("3 Zwiebeln (à 80 g), gewürfelt", "Zwiebeln", 240, None, "g", "gewürfelt", False),
    ("3-4 Möhren (je 100 g)", "Möhren", 300, 400, "g", None, False),
    (
        "4 Lachsfilets mit Haut à ca. 150-200g (Gerne mit Skin)",
        "Lachsfilets",
        700,
        None,
        "g",
        "Gerne mit Skin; à ca. 150-200g; mit Haut",
        False,
    ),
    ("2 Lachsfilets à 150 g", "Lachsfilets", 300, None, "g", "à 150 g", False),
    ("1 Stück Ingwer (ca. daumengroß)", "Ingwer", 1, None, "Stück", "ca. daumengroß", False),
    (
        "1,5 EL Reisessig oder anderen milden Essig",
        "Reisessig",
        1.5,
        None,
        "EL",
        "oder anderen milden Essig",
        False,
    ),
    (
        "Petersilie oder Schnittlauch, frisch (fein gehackt)",
        "Petersilie",
        None,
        None,
        None,
        "fein gehackt; frisch; oder Schnittlauch",
        False,
    ),
    ("glatte oder krause Petersilie", "Petersilie", None, None, None, "glatte oder krause", False),
    ("1 EL gehackte Kräuter (frisch oder TK)", "gehackte Kräuter", 1, None, "EL", "frisch oder TK", False),
    (
        "Gemüse nach Wahl, z. B. Möhre, Blumenkohl",
        "Gemüse",
        None,
        None,
        None,
        "nach Wahl, z. B. Möhre, Blumenkohl",
        True,
    ),
    (
        "150 g Kräuterfrischkäse (max. 12 % Fett absolut)",
        "Kräuterfrischkäse",
        150,
        None,
        "g",
        "max. 12 % Fett absolut",
        False,
    ),
    ("0.5 Petersilie", "Petersilie", 0.5, None, None, None, False),
    ("3 Ei (Größe M)", "Ei", 3, None, None, "Größe M", False),
    ("1 Suppenhuhn, ca. 2,2 kg (gerne Bio)", "Suppenhuhn", 2200, None, "g", "gerne Bio; ca. 2,2 kg", False),
    ("1 Suppenhuhn, ca. 2,2 kg", "Suppenhuhn", 2200, None, "g", "ca. 2,2 kg", False),
    ("250 ml Milch 1,5 %", "Milch 1,5 %", 250, None, "ml", None, False),
    ("200 g Hähnchenbrust in Streifen", "Hähnchenbrust", 200, None, "g", "in Streifen", False),
    ("Pfeffer aus der Mühle", "Pfeffer", None, None, None, "aus der Mühle", False),
    ("2 TL Paprikapulver, edelsüß", "Paprikapulver", 2, None, "TL", "edelsüß", False),
    ("1 Pk. Hefe", "Hefe", 1, None, "Packung", None, False),
    ("1 Zwiebel (unvollständige Klammer", "Zwiebel", 1, None, None, "unvollständige Klammer", False),
]


@pytest.mark.parametrize("text, name, qty, qty_max, unit, note, optional", PARSE_CASES)
def test_parse_ingredient_line(text, name, qty, qty_max, unit, note, optional):
    p = parse_ingredient_line(text)
    assert p.raw == text
    assert p.name == name
    assert p.quantity == pytest.approx(qty) if qty is not None else p.quantity is None
    assert p.quantity_max == pytest.approx(qty_max) if qty_max is not None else p.quantity_max is None
    assert p.unit == unit
    assert p.note == note
    assert p.optional is optional


def test_parse_has_enough_cases():
    assert len(PARSE_CASES) >= 65


def test_parse_empty_line():
    p = parse_ingredient_line("   ")
    assert p.name == ""
    assert p.quantity is None and p.unit is None and not p.optional


def test_parse_unit_aliases_normalized():
    assert parse_ingredient_line("2 Esslöffel Öl").unit == "EL"
    assert parse_ingredient_line("3 Teelöffel Zucker").unit == "TL"
    assert parse_ingredient_line("100 Gramm Reis").unit == "g"
    assert parse_ingredient_line("1 Liter Brühe").unit == "l"
    assert parse_ingredient_line("1 Msp. Zimt").unit == "Prise"


def test_parse_unicode_whitespace_and_bullet():
    p = parse_ingredient_line("• 2 EL  Honig")
    assert (p.quantity, p.unit, p.name) == (2.0, "EL", "Honig")


# ---------------------------------------------------------------------------
# Mengen und Einheiten
# ---------------------------------------------------------------------------


def test_mean_quantity():
    assert mean_quantity(parse_ingredient_line("3-4 Karotten")) == pytest.approx(3.5)
    assert mean_quantity(parse_ingredient_line("200 g Mehl")) == 200
    assert mean_quantity(parse_ingredient_line("Salz")) is None
    assert mean_quantity(ParsedIngredient(raw="x", name="x", quantity=2.0, quantity_max=3.0)) == 2.5


def test_to_grams_weight_and_volume():
    assert to_grams(200, "g") == 200
    assert to_grams(1.5, "kg") == 1500
    assert to_grams(500, "ml") == 500  # Dichte-Standard 1,0
    assert to_grams(1, "l") == 1000
    assert to_grams(250, "ml", density_g_per_ml=1.03) == pytest.approx(257.5)
    assert to_grams(0.5, "l", density_g_per_ml=0.92) == pytest.approx(460)


def test_to_grams_spoons_and_cups_use_density():
    assert to_grams(2, "EL") == pytest.approx(30)
    assert to_grams(1, "TL") == pytest.approx(5)
    assert to_grams(2, "EL", density_g_per_ml=0.92) == pytest.approx(27.6)
    assert to_grams(1, "Tasse") == pytest.approx(defaults.ML_PER_UNIT["Tasse"])
    assert to_grams(1, "Becher", density_g_per_ml=1.05) == pytest.approx(150 * 1.05)
    assert to_grams(1, "Glas") == pytest.approx(200)


def test_to_grams_pieces():
    assert to_grams(2, None, piece_g=60) == 120
    assert to_grams(3, "Stück", piece_g=55) == 165
    assert to_grams(0.5, None, piece_g=40) == pytest.approx(20)


def test_to_grams_pieces_without_weight_stay_open():
    # kein stillschweigender Standardwert von 100 g mehr: 3 Frühlingszwiebeln != 300 g
    assert to_grams(2, None) is None
    assert to_grams(1, "Stück") is None
    assert to_grams(3, None, piece_g=0) is None
    assert to_grams(3, None, piece_g=None) is None


def test_to_grams_default_piece_keeps_old_behaviour():
    assert to_grams(2, None, default_piece=True) == 2 * defaults.DEFAULT_PIECE_G
    assert to_grams(1, "Stück", default_piece=True) == defaults.DEFAULT_PIECE_G
    assert to_grams(2, None, piece_g=60, default_piece=True) == 120  # Stückgewicht der Zutat gewinnt
    assert to_grams(None, None, default_piece=True) is None
    assert to_grams(2, "Schuss", default_piece=True) is None  # unbekannte Einheit bleibt offen


def test_to_grams_unit_g_overrides_table_units_only():
    assert to_grams(1, "Packung", unit_g=15) == 15  # Päckchen Backpulver
    assert to_grams(2, "Dose", unit_g=240) == 480  # Abtropfgewicht
    assert to_grams(4, "Scheibe", unit_g=45) == 180
    assert to_grams(1, "Packung") == defaults.GRAMS_PER_UNIT["Packung"]
    assert to_grams(1, "Packung", unit_g=0) == defaults.GRAMS_PER_UNIT["Packung"]
    assert to_grams(2, "g", unit_g=15) == 2  # g/ml/EL und Stück kennen kein unit_g
    assert to_grams(2, "EL", unit_g=15) == pytest.approx(30)
    assert to_grams(2, "Stück", piece_g=50, unit_g=15) == 100


def test_to_grams_stalks_count_like_sprigs():
    assert to_grams(5, "Zweig") == pytest.approx(5 * defaults.GRAMS_PER_UNIT["Zweig"])
    assert to_grams(2, "Stange") == pytest.approx(2 * defaults.GRAMS_PER_UNIT["Stange"])


def test_to_grams_table_units():
    assert to_grams(1, "Prise") == pytest.approx(0.4)
    assert to_grams(2, "Zehe") == pytest.approx(2 * defaults.GRAMS_PER_UNIT["Zehe"])
    assert to_grams(0.5, "Bund") == pytest.approx(0.5 * defaults.GRAMS_PER_UNIT["Bund"])
    assert to_grams(1, "Dose") == pytest.approx(defaults.GRAMS_PER_UNIT["Dose"])
    assert to_grams(4, "Scheibe") == pytest.approx(4 * defaults.GRAMS_PER_UNIT["Scheibe"])
    # Stückgewicht der Zutat gilt nicht für Dose/Packung usw.
    assert to_grams(1, "Dose", piece_g=60) == pytest.approx(defaults.GRAMS_PER_UNIT["Dose"])


def test_to_grams_unknown_or_missing():
    assert to_grams(None, "g") is None
    assert to_grams(None, None) is None
    assert to_grams(2, "Schuss") is None
    assert to_grams(2, "Fuder") is None


def test_to_grams_accepts_alias_spelling():
    assert to_grams(2, "Esslöffel") == pytest.approx(30)
    assert to_grams(1, "kilo") == 1000


def test_parse_then_grams_roundtrip():
    p = parse_ingredient_line("3-4 Karotten")
    assert to_grams(mean_quantity(p), p.unit, piece_g=80) == pytest.approx(280)
    p = parse_ingredient_line("1 Dose Tomaten (400 g)")
    assert to_grams(mean_quantity(p), p.unit) == 400


def test_parse_then_grams_real_recipe_lines():
    p = parse_ingredient_line("2 Möhre (je ca. 150 g)")
    assert to_grams(mean_quantity(p), p.unit) == pytest.approx(300)
    p = parse_ingredient_line("4 Lachsfilets mit Haut à ca. 150-200g")
    assert to_grams(mean_quantity(p), p.unit) == pytest.approx(700)  # 4 × Mittelwert 175 g
    p = parse_ingredient_line("1 Suppenhuhn, ca. 2,2 kg")
    assert to_grams(mean_quantity(p), p.unit) == pytest.approx(2200)
    p = parse_ingredient_line("5 Stängel Petersilie")
    assert to_grams(mean_quantity(p), p.unit) == pytest.approx(10)
    # Menge ohne Einheit bei Kräutern: nur mit Stückgewicht (Bund), sonst offen
    p = parse_ingredient_line("0.5 Petersilie")
    assert to_grams(mean_quantity(p), p.unit, piece_g=40) == pytest.approx(20)
    assert to_grams(mean_quantity(p), p.unit) is None
    p = parse_ingredient_line("3 Frühlingszwiebeln")
    assert to_grams(mean_quantity(p), p.unit) is None
    assert to_grams(mean_quantity(p), p.unit, piece_g=20) == pytest.approx(60)
    p = parse_ingredient_line("1 Dose Kichererbsen (Abtropfgewicht 240 g)")
    assert to_grams(mean_quantity(p), p.unit) == pytest.approx(240)


# ---------------------------------------------------------------------------
# Normalisierung
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text, expected",
    [
        ("Karotten", "karotte"),
        ("Eier", "ei"),
        ("Tomaten", "tomate"),
        ("Zwiebeln", "zwiebel"),
        ("Kartoffeln", "kartoffel"),
        ("Mandeln", "mandel"),
        ("Walnüsse", "walnuss"),
        ("Äpfel", "apfel"),
        ("Frische Petersilie, gehackt", "petersilie"),
        ("große Zwiebeln", "zwiebel"),
        ("2 mittelgroße Zwiebeln", "2 zwiebel"),
        ("Bio-Zitronen", "zitrone"),
        ("Salz nach Geschmack", "salz"),
        ("Zwiebel (rot)", "zwiebel"),
        ("Mehl für die Arbeitsfläche", "mehl"),
        ("Schinken", "schinken"),
        ("Brötchen", "brötchen"),
        ("Haferflocken", "haferflocke"),
        ("rote Paprika", "rot paprika"),
        ("Milch 3,5 % Fett", "milch 35pct"),
        ("Milch 1,5 %", "milch 15pct"),
        ("  Olivenöl  ", "olivenöl"),
        ("Hähnchenbrustfilet", "hähnchenbrustfilet"),
        ("Kräuter", "kräuter"),
        ("gehackte Kräuter", "kräuter"),
        ("Lachsfilets", "lachsfilet"),
        ("Weizenmehl", "weizenmehl"),
        ("Spinat TK", "spinat"),
        ("glatte Petersilie", "petersilie"),
        ("Joghurt 3,5 %", "joghurt 35pct"),
    ],
)
def test_normalize_name(text, expected):
    assert normalize_name(text) == expected


def test_normalize_name_only_fillers_keeps_something():
    assert normalize_name("frische") != ""


def test_normalize_name_is_idempotent_for_simple_names():
    for name in ["Karotten", "Eier", "Zwiebeln", "Haferflocken", "frische Tomaten"]:
        once = normalize_name(name)
        assert normalize_name(once) == once


# ---------------------------------------------------------------------------
# Zuordnung zum Katalog (künstlicher Katalog im BLS-Namensstil)
# ---------------------------------------------------------------------------

CATALOG = [
    CatalogEntry(1, "Speisezwiebel roh", 10.0),
    CatalogEntry(2, "Streichmettwurst mit Zwiebeln"),
    CatalogEntry(3, "Zwiebelsuppe Instantpulver", -20.0),
    CatalogEntry(4, "Hühnerei roh", 10.0),
    CatalogEntry(5, "Speisequark Magerstufe, Magerquark < 10 % Fett i. Tr."),
    CatalogEntry(6, "Olivenöl"),
    CatalogEntry(7, "Kartoffel geschält, roh", 10.0),
    CatalogEntry(8, "Kartoffelsalat mit Mayonnaise", -20.0),
    CatalogEntry(9, "Skyr, Frischkäse < 10 % Fett i. Tr."),
    CatalogEntry(10, "Hafer Flocken"),
    CatalogEntry(11, "Haferflocken-Nussplätzchen", -20.0),
    CatalogEntry(12, "Karotte/Möhre, roh", 10.0),
    CatalogEntry(13, "Gemüsepaprika rot, roh", 10.0),
    CatalogEntry(14, "Rote Rübe/Rote Bete, roh", 10.0),
    CatalogEntry(15, "Milch fettarm, frisch, 1,5 % Fett, pasteurisiert"),
    CatalogEntry(16, "Vollmilch frisch, 3,5 % Fett, pasteurisiert"),
    CatalogEntry(17, "Tomate roh", 10.0),
    CatalogEntry(18, "Tomatenketchup"),
    CatalogEntry(19, "Weizen Mehl, Type 405"),
    CatalogEntry(20, "Weizen Mehl, Type 550"),
]


def ids(matches):
    return [m.ingredient_id for m in matches]


def test_match_prefers_zutat_over_beiwerk():
    result = match_ingredient("Zwiebel", CATALOG)
    assert result[0].ingredient_id == 1
    assert result[0].via == "fuzzy"
    assert 2 not in ids(result)  # "Streichmettwurst mit Zwiebeln": Zwiebel nur Beiwerk
    assert 3 not in ids(result)  # Instantpulver wird nicht vorgeschlagen


def test_match_plural_and_fillers():
    assert match_ingredient("große Zwiebeln, gehackt", CATALOG)[0].ingredient_id == 1
    assert match_ingredient("Kartoffeln", CATALOG)[0].ingredient_id == 7


def test_match_without_rank_hint_still_prefers_word_start_and_end():
    plain = [CatalogEntry(1, "Speisezwiebel roh"), CatalogEntry(2, "Streichmettwurst mit Zwiebeln")]
    assert match_ingredient("Zwiebel", plain)[0].ingredient_id == 1
    # Wortanfang schlägt Vorkommen als Beiwerk
    plain = [CatalogEntry(1, "Kartoffelsalat mit Mayonnaise"), CatalogEntry(2, "Kartoffel geschält, roh")]
    assert match_ingredient("Kartoffel", plain)[0].ingredient_id == 2


def test_match_exact():
    result = match_ingredient("Olivenöl", CATALOG)
    assert result[0].ingredient_id == 6
    assert result[0].via == "exact"
    assert result[0].score == 100


def test_match_exact_on_head_before_comma():
    result = match_ingredient("Skyr", CATALOG)
    assert result[0].ingredient_id == 9 and result[0].via == "exact"


def test_match_compound_written_apart():
    result = match_ingredient("Haferflocken", CATALOG)
    assert result[0].ingredient_id == 10
    assert result[0].via == "exact"


def test_match_synonym_first_with_score_100():
    synonyms = {"ei": 4}
    result = match_ingredient("Eier", CATALOG, synonyms)
    assert result[0] == match_ingredient("Eier", CATALOG, synonyms)[0]
    assert result[0].ingredient_id == 4
    assert result[0].via == "synonym"
    assert result[0].score == 100
    assert result[0].name == "Hühnerei roh"


def test_match_synonym_wins_over_better_fuzzy():
    synonyms = {"zwiebel": 3}
    result = match_ingredient("Zwiebel", CATALOG, synonyms)
    assert result[0].ingredient_id == 3 and result[0].via == "synonym"
    assert ids(result).count(3) == 1  # keine Dublette durch Fuzzy


def test_match_synonym_with_id_missing_in_catalog():
    result = match_ingredient("Ei", CATALOG[:3], {"ei": 99})
    assert result[0].ingredient_id == 99 and result[0].via == "synonym"


def test_match_fuzzy_magerquark():
    result = match_ingredient("Magerquark", CATALOG)
    assert result and result[0].ingredient_id == 5
    assert result[0].via == "fuzzy"
    assert 60 <= result[0].score <= 100


def test_match_typo_is_found():
    result = match_ingredient("Olivenoel", CATALOG)
    assert result and result[0].ingredient_id == 6


def test_match_multiword_and_color():
    result = match_ingredient("rote Paprika", CATALOG)
    assert result[0].ingredient_id == 13
    assert result[0].ingredient_id != 14


def test_match_percentages_distinguish_milk():
    assert match_ingredient("Milch 3,5 %", CATALOG)[0].ingredient_id == 16
    assert match_ingredient("Milch 1,5 % Fett", CATALOG)[0].ingredient_id == 15


def test_match_flour_type():
    assert match_ingredient("Weizenmehl Type 405", CATALOG)[0].ingredient_id == 19
    assert match_ingredient("Weizenmehl Type 550", CATALOG)[0].ingredient_id == 20
    assert match_ingredient("Weizenmehl Typ 405", CATALOG)[0].ingredient_id == 19  # "Typ" statt "Type"
    assert match_ingredient("Mehl Typ 550", CATALOG)[0].ingredient_id == 20


def test_match_rank_hint_breaks_ties():
    cat = [CatalogEntry(1, "Tomate gekocht", 15.0), CatalogEntry(2, "Tomate roh", 0.0)]
    assert match_ingredient("Tomate", cat)[0].ingredient_id == 1
    cat = [CatalogEntry(1, "Tomate gekocht", -30.0), CatalogEntry(2, "Tomate roh", 0.0)]
    assert match_ingredient("Tomate", cat)[0].ingredient_id == 2


def test_match_shorter_name_is_tiebreaker():
    cat = [CatalogEntry(1, "Reis poliert, roh, extra lang"), CatalogEntry(2, "Reis poliert")]
    assert match_ingredient("Reis", cat)[0].ingredient_id == 2


def test_match_below_threshold_is_dropped():
    assert match_ingredient("Xylophon", CATALOG) == []
    assert match_ingredient("", CATALOG) == []
    assert match_ingredient("Zwiebel", []) == []


def test_match_short_query_needs_word_relation():
    cat = [CatalogEntry(1, "Reis poliert, roh"), CatalogEntry(2, "Hühnerei roh")]
    assert ids(match_ingredient("ei", cat)) == [2]


def test_match_limit_sorted_and_bounded():
    result = match_ingredient("Zwiebel", CATALOG, limit=2)
    assert len(result) <= 2
    full = match_ingredient("Tomate", CATALOG, limit=10)
    scores = [m.score for m in full]
    assert scores == sorted(scores, reverse=True)
    assert all(0 <= s <= 100 for s in scores)
    assert match_ingredient("Tomate", CATALOG, limit=0) == []


def test_match_does_not_mutate_catalog():
    before = list(CATALOG)
    match_ingredient("Zwiebel", CATALOG)
    assert CATALOG == before


# Katalog mit typischen Stolperfallen (BLS-Stil): Beiwerk, Getränke, Kuchen, ähnliche Wörter
CATALOG2 = [
    CatalogEntry(1, "Lachs roh", 10.0),
    CatalogEntry(2, "Lachs geräuchert (Räucherlachs)"),
    CatalogEntry(3, "Kaffee (Getränk) mit Zucker"),
    CatalogEntry(4, "Apfelkraut"),
    CatalogEntry(5, "Brotaufstrich Ei-Kräuter"),
    CatalogEntry(6, "Gemüsepaprika rot, roh", 10.0),
    CatalogEntry(7, "Gemüsemischung Kaisergemüse, roh", 10.0),
    CatalogEntry(8, "Tomate roh", 10.0),
    CatalogEntry(9, "Kirschtorte"),
    CatalogEntry(10, "Suppenhuhn Fleisch, mit Haut, roh", 10.0),
    CatalogEntry(11, "Eierteigwaren roh", 10.0),
    CatalogEntry(12, "Hühnerei roh", 10.0),
    CatalogEntry(13, "Quark-Plunder"),
    CatalogEntry(14, "Speisequark Magerstufe, Magerquark < 10 % Fett i. Tr."),
    CatalogEntry(15, "Schwein Filet/Lende, roh", 10.0),
    CatalogEntry(16, "Hähnchen Brustfilet, roh", 10.0),
    CatalogEntry(17, "Nori-Blatt geröstet"),
    CatalogEntry(18, "Eier-Frischteigwaren roh", 10.0),
    CatalogEntry(19, "Zucker weiß"),
    CatalogEntry(20, "Apfelkuchen mit Zimt"),
    CatalogEntry(21, "Apfel roh", 10.0),
]


def test_match_beiwerk_in_query_is_ignored():
    # "mit Haut" ist Beiwerk des Rezepts, kein Suchwort ("Kaffee (Getränk) mit Zucker", Score 89)
    result = match_ingredient("Lachsfilets mit Haut", CATALOG2)
    assert result and result[0].ingredient_id == 1
    assert 3 not in ids(result)


def test_match_compound_query_finds_head_word():
    result = match_ingredient("Kirschtomate", CATALOG2)
    assert result[0].ingredient_id == 8
    assert 9 not in ids(result)  # "Kirschtorte": nur klangähnlich
    assert result[0].score < 99  # Abzug gegenüber dem direkten Treffer
    assert match_ingredient("Lachsfilet", CATALOG2)[0].ingredient_id == 1


def test_match_generic_suffix_does_not_link_cuts():
    # "putenbrustfilet" endet auf "filet", aber das ist kein Grund für "Schwein Filet/Lende"
    assert 15 not in ids(match_ingredient("Putenbrustfilet", CATALOG2))
    assert 17 not in ids(match_ingredient("Lorbeerblatt", CATALOG2))  # "Nori-Blatt"


def test_match_vague_query_gives_no_suggestion():
    assert match_ingredient("gehackte Kräuter", CATALOG2) == []  # "Apfelkraut", "Ei-Kräuter"
    assert match_ingredient("Gemüse", CATALOG2) == []  # "Gemüsepaprika", "Kaisergemüse"
    assert match_ingredient("Gemüse nach Wahl", CATALOG2) == []


def test_match_similar_sounding_word_is_not_a_hit():
    assert 10 not in ids(match_ingredient("Suppennudeln", CATALOG2))  # nicht "Suppenhuhn"
    assert 9 not in ids(match_ingredient("Kirschtomate", CATALOG2))
    assert match_ingredient("Olivenoel", [CatalogEntry(1, "Olivenöl")])[0].ingredient_id == 1  # Tippfehler
    assert match_ingredient("Olivenöll", [CatalogEntry(1, "Olivenöl")]) != []  # ein Buchstabe daneben
    assert match_ingredient("Olivenaal", [CatalogEntry(1, "Olivenöl")]) == []  # zwei Buchstaben: kein Treffer


def test_match_hyphen_prefix_is_modifier():
    assert ids(match_ingredient("Quark", CATALOG2)) == [14]  # "Quark-Plunder" weder Quark noch erwünscht
    assert match_ingredient("Ei", CATALOG2)[0].ingredient_id == 12  # vor "Eier-Frischteigwaren"


def test_match_drinks_and_sweets_are_demoted():
    result = match_ingredient("Apfel", CATALOG2)
    assert result[0].ingredient_id == 21
    assert 20 not in ids(result)  # "Apfelkuchen mit Zimt"
    cake = match_ingredient("Apfelkuchen", CATALOG2)
    assert cake and cake[0].ingredient_id == 20  # wer Kuchen sucht, bekommt Kuchen
    assert 3 not in ids(match_ingredient("Zucker", CATALOG2))  # "Kaffee (Getränk) mit Zucker"
    assert match_ingredient("Zucker", CATALOG2)[0].ingredient_id == 19


def test_match_synonym_is_found_for_core_without_beiwerk():
    result = match_ingredient("Lachsfilets mit Haut", CATALOG2, {"lachsfilet": 2})
    assert result[0].ingredient_id == 2 and result[0].via == "synonym"


def test_match_score_is_high_only_for_good_hits():
    good = match_ingredient("Zwiebel", CATALOG)[0]
    weak = match_ingredient("Kirschtomate", CATALOG2)[0]
    assert good.score >= 88  # reicht für die automatische Zuordnung
    assert weak.score < good.score


# ---------------------------------------------------------------------------
# Synonym-Seed
# ---------------------------------------------------------------------------


def test_seed_size_and_types():
    assert len(SYNONYM_SEED) >= 700
    assert all(isinstance(k, str) and isinstance(v, str) for k, v in SYNONYM_SEED.items())


def test_seed_keys_are_normalized_lowercase():
    for key in SYNONYM_SEED:
        assert key == key.lower()
        assert key == key.strip()
        assert key == normalize_name(key), key


def test_seed_values_not_empty():
    for key, value in SYNONYM_SEED.items():
        assert value.strip(), key
        assert value == value.strip(), key


def test_seed_has_no_duplicates():
    normalized = [normalize_name(k) for k in _RAW_SEED]
    assert len(normalized) == len(set(normalized))
    assert len(SYNONYM_SEED) == len(_RAW_SEED)


def test_seed_contains_core_ingredients():
    for alias in ["ei", "zwiebel", "knoblauch", "kartoffel", "karotte", "mehl", "zucker", "butter"]:
        assert alias in SYNONYM_SEED, alias
    assert SYNONYM_SEED["ei"] == "Hühnerei roh"
    assert SYNONYM_SEED[normalize_name("Magerquark")].startswith("Speisequark Magerstufe")


def test_seed_aliases_resolve_user_input():
    assert normalize_name("Eier") in SYNONYM_SEED
    assert normalize_name("Haferflocken") in SYNONYM_SEED
    assert normalize_name("frische Zwiebeln") in SYNONYM_SEED
    assert normalize_name("Milch 3,5 % Fett") in SYNONYM_SEED
    assert SYNONYM_SEED[normalize_name("Milch 1,5 %")] != SYNONYM_SEED[normalize_name("Milch 3,5 %")]


def test_seed_build_detects_conflicts_and_empty_aliases():
    with pytest.raises(ValueError):
        _build_seed({"Ei": "Hühnerei roh", "Eier": "Wachtelei roh"})  # gleiche Normalform, anderes Ziel
    with pytest.raises(ValueError):
        _build_seed({"frisch": "x", "   ": "y"})
    assert _build_seed({"Ei": "Hühnerei roh", "Eier": "Hühnerei roh"}) == {"ei": "Hühnerei roh"}


def test_seed_broths_are_ready_to_drink():
    for alias in [
        "Gemüsebrühe",
        "Brühe",
        "Hühnerbrühe",
        "Fleischbrühe",
        "Rinderbrühe",
        "Gemüsefond",
        "Fischfond",
    ]:
        target = SYNONYM_SEED[normalize_name(alias)]
        assert not any(w in target for w in ("Pulver", "Brühwürfel", "Bouillon")), (alias, target)
    # die Pulver-Einträge nur über eindeutige Aliase
    for alias in ["Brühwürfel", "Gemüsebrühepulver", "Instantbrühe", "Hühnerbrühwürfel"]:
        assert "Pulver" in SYNONYM_SEED[normalize_name(alias)], alias


def test_seed_fresh_foods_avoid_concentrates():
    bad = ("Pulver", "Instant", "Konzentrat", "getrocknet", "Mus", "Püree", "Trocken")
    for alias in [
        "Milch",
        "Tomate",
        "Kirschtomate",
        "Kartoffel",
        "Zwiebel",
        "Knoblauch",
        "Ei",
        "Apfel",
        "Karotte",
        "Spinat",
        "Petersilie",
        "Basilikum",
        "Paprika",
        "Zitrone",
        "Sahne",
        "Joghurt",
        "Banane",
    ]:
        target = SYNONYM_SEED[normalize_name(alias)]
        assert not any(w in target for w in bad), (alias, target)


def test_seed_powder_targets_only_for_powder_aliases():
    hints = ("pulver", "würfel", "instant", "kakao", "bouillon", "xylit", "birkenzucker", "sahnesteif")
    for alias, target in SYNONYM_SEED.items():
        if any(w in target for w in ("Pulver", "Instant", "Brühwürfel", "Konzentrat")):
            assert any(h in alias for h in hints), (alias, target)


def test_seed_covers_gaps_from_real_recipes():
    for text in [
        "Kirschtomaten",
        "Cherrytomaten",
        "Snackgurke",
        "Salatgurke",
        "Paprikaschote",
        "Spitzpaprika",
        "Sesamkörner",
        "Sesamsamen",
        "Suppenhuhn",
        "Petersilienwurzel",
        "Kräuterfrischkäse",
        "Suppennudeln",
        "Reisessig",
        "Lachsfilets",
        "Lachsfilet",
        "Griechischer Joghurt",
        "Hüttenkäse",
        "Parmesan",
        "Mozzarella",
        "Feta",
        "Tofu",
        "Kidneybohnen",
        "Linsen",
        "Haferflocken",
        "Tomatenmark",
        "passierte Tomaten",
        "stückige Tomaten",
        "Senf",
        "Ketchup",
        "Mayonnaise",
        "Sojasauce",
        "Honig",
        "Ahornsirup",
        "Chiasamen",
        "Leinsamen",
        "Sonnenblumenkerne",
        "Kürbiskerne",
        "Backpulver",
        "Hefe",
        "Speisestärke",
        "Vanillezucker",
        "Hafermilch",
        "Sojadrink",
    ]:
        assert normalize_name(text) in SYNONYM_SEED, text


def test_seed_pepper_colors_are_respected():
    for text, color in [
        ("rote Paprika", "rot"),
        ("gelbe Paprikaschote", "gelb"),
        ("grüne Spitzpaprika", "grün"),
        ("rote Spitzpaprika", "rot"),
        ("orange Paprika", "gelb"),
    ]:
        assert color in SYNONYM_SEED[normalize_name(text)], text


def test_seed_maps_spices_missing_in_bls_to_dried_herb_approximation():
    # die BLS enthält diese Gewürze nicht: Näherung über "Basilikum getrocknet" (kleine Mengen)
    for text in [
        "Zimt",
        "Muskat",
        "Paprikapulver",
        "Kurkuma",
        "Currypulver",
        "Kümmel",
        "Piment",
        "Lorbeerblatt",
    ]:
        assert SYNONYM_SEED[normalize_name(text)] == "Basilikum getrocknet", text
