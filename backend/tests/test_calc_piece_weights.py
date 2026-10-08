"""Tests für calc/piece_weights.py (nur synthetische Daten, keine BLS-Datei)."""

import pytest

from app.calc.ingredients import normalize_name, to_grams
from app.calc.piece_weights import (
    CAN_WEIGHT_SEED,
    PACK_WEIGHT_SEED,
    PIECE_WEIGHT_ALIAS_SEED,
    PIECE_WEIGHT_SEED,
    SLICE_WEIGHT_SEED,
    piece_weight_for_alias,
    piece_weight_for_name,
    slice_weight_for_name,
    unit_weight_for_name,
)
from app.calc.synonym_seed import SYNONYM_SEED

TABLES = {
    "piece": PIECE_WEIGHT_SEED,
    "slice": SLICE_WEIGHT_SEED,
    "pack": PACK_WEIGHT_SEED,
    "can": CAN_WEIGHT_SEED,
}


def test_piece_weight_seed_is_large_enough():
    assert len(PIECE_WEIGHT_SEED) >= 100


@pytest.mark.parametrize("table", list(TABLES))
def test_weights_are_plausible(table):
    for name, grams in TABLES[table].items():
        assert isinstance(name, str) and isinstance(grams, float), name
        assert 0 < grams < 5000, (name, grams)


@pytest.mark.parametrize("table", list(TABLES))
def test_keys_are_clean_and_unique(table):
    names = list(TABLES[table])
    assert all(name == name.strip() and name for name in names)
    folded = [name.casefold() for name in names]
    assert len(folded) == len(set(folded))  # keine Dubletten, auch nicht durch Groß-/Kleinschreibung


def test_keys_are_full_bls_names_not_aliases():
    # Schlüssel sind Ingredient.name, also nicht die kurze Schreibweise aus Rezepten
    for short in ["Zwiebel", "Möhre", "Tomate", "Ei", "Zitrone", "Apfel", "Petersilie", "Lachs"]:
        assert short not in PIECE_WEIGHT_SEED
        assert normalize_name(short) not in PIECE_WEIGHT_SEED
    for name in PIECE_WEIGHT_SEED:
        assert name[0].isupper(), name


def test_piece_weight_for_name_is_exact_lookup():
    assert piece_weight_for_name("Speisezwiebel roh") == 80
    assert piece_weight_for_name("Hühnerei roh") == 60
    assert piece_weight_for_name("Karotte/Möhre, roh") == 100
    assert piece_weight_for_name("Zucchini roh") == 250
    assert piece_weight_for_name("speisezwiebel roh") is None  # kein Fuzzy, keine Kleinschreibung
    assert piece_weight_for_name("Zwiebel") is None
    assert piece_weight_for_name("") is None


def test_typical_values_follow_the_spec():
    expected = {
        "Speisezwiebel roh": 80,
        "Karotte/Möhre, roh": 100,
        "Zucchini roh": 250,
        "Gemüsepaprika rot, roh": 160,
        "Kartoffel geschält, roh": 90,
        "Tomate roh": 100,
        "Gurke roh": 350,
        "Aubergine roh": 300,
        "Zitrone roh": 100,
        "Orange roh": 180,
        "Apfel roh": 180,
        "Birne roh": 170,
        "Banane roh": 120,
        "Kiwi roh": 75,
        "Avocado roh": 150,
        "Hühnerei roh": 60,
        "Knoblauch roh": 4,
        "Ingwer/Ingwerwurzel, roh": 20,
        "Hähnchen Brustfilet, roh": 150,
        "Lachs roh": 150,
        "Mozzarella mind. 45 % Fett i. Tr.": 125,
        "Feta mind. 45 % Fett i. Tr.": 200,
        "Broccoli roh": 500,
        "Blumenkohl roh": 600,
        "Kohlrabi roh": 250,
        "Gemüsefenchel roh": 250,
        "Porree/Lauch, roh": 200,
        "Bleichsellerie roh": 60,
        "Weizenbrötchen": 55,
    }
    for name, grams in expected.items():
        assert piece_weight_for_name(name) == grams, name
    assert 30 <= PIECE_WEIGHT_SEED["Petersilienblatt roh"] <= 40  # ein Bund
    assert PIECE_WEIGHT_SEED["Frühlingszwiebel/Lauchzwiebel, roh"] < PIECE_WEIGHT_SEED["Speisezwiebel roh"]


def test_not_sold_by_piece_stay_out():
    # Hack, Quark, Mehl, Champignons u. Ä. werden nach Gewicht gekauft: ohne Stückgewicht bleibt es offen
    blocked = ("Hackfleisch", "Quark", "Mehl", "Champignon", "Frischkäse", "Butter", "Milch", "Reis poliert")
    for name in PIECE_WEIGHT_SEED:
        assert not any(word in name for word in blocked), name


def test_core_aliases_of_the_synonym_seed_have_a_piece_weight():
    # Zusammenspiel: Das Ziel des Aliases steht auch in der Stückgewichts-Tabelle
    for alias in [
        "Zwiebel",
        "Möhre",
        "Kartoffel",
        "Tomate",
        "Zitrone",
        "Apfel",
        "Banane",
        "Ei",
        "Zucchini",
        "Gurke",
        "Avocado",
        "Knoblauch",
        "Ingwer",
        "Petersilie",
        "Frühlingszwiebel",
        "Hähnchenbrust",
        "Lachs",
        "Brötchen",
        "Mozzarella",
        "Feta",
        "Brokkoli",
        "Blumenkohl",
        "Paprika",
        "Aubergine",
        "Kohlrabi",
        "Fenchel",
        "Lauch",
        "Staudensellerie",
        "Orange",
        "Birne",
        "Kiwi",
        "Schalotte",
    ]:
        target = SYNONYM_SEED[normalize_name(alias)]
        assert piece_weight_for_name(target) is not None, (alias, target)


def test_herb_approximations_share_the_parsley_bund():
    for alias in ["Dill", "Koriander", "Minze"]:
        target = SYNONYM_SEED[normalize_name(alias)]
        assert piece_weight_for_name(target) == piece_weight_for_name("Petersilienblatt roh")


def test_slice_pack_and_can_weights():
    assert slice_weight_for_name("Roggenmischbrot") == 45
    assert slice_weight_for_name("Hühnerei roh") is None
    assert unit_weight_for_name("Roggenmischbrot", "Scheibe") == 45
    assert unit_weight_for_name("Backpulver", "Packung") == 15
    assert unit_weight_for_name("Vanillezucker", "Packung") == 8
    assert unit_weight_for_name("Kichererbse reif, Konserve, abgetropft", "Dose") == 240
    # nur die passende Einheit zählt
    assert unit_weight_for_name("Backpulver", "Dose") is None
    assert unit_weight_for_name("Backpulver", "Stück") is None
    assert unit_weight_for_name("Backpulver", None) is None
    assert unit_weight_for_name("Unbekannt", "Packung") is None


def test_alias_weights_for_varieties():
    assert piece_weight_for_alias("Kirschtomaten") == 15
    assert piece_weight_for_alias("Cherrytomate") == 15
    assert piece_weight_for_alias("Snackgurke") == 100
    assert piece_weight_for_alias("Gemüsezwiebel") == 200
    assert piece_weight_for_alias("Tomaten") is None  # Normalform: Wert der Zutat gilt
    assert piece_weight_for_alias("") is None
    assert all(key == normalize_name(key) for key in PIECE_WEIGHT_ALIAS_SEED)
    assert all(0 < grams < 5000 for grams in PIECE_WEIGHT_ALIAS_SEED.values())
    # Sorten wiegen anders als die Normalform ("Tomate roh" 100 g), sonst wäre der Alias überflüssig
    assert piece_weight_for_alias("Kirschtomate") != PIECE_WEIGHT_SEED["Tomate roh"]


def test_alias_weights_point_to_seeded_ingredients():
    for alias in PIECE_WEIGHT_ALIAS_SEED:
        if alias in SYNONYM_SEED:
            assert piece_weight_for_name(SYNONYM_SEED[alias]) is not None, alias


def test_weights_work_with_to_grams():
    onion = piece_weight_for_name("Frühlingszwiebel/Lauchzwiebel, roh")
    assert to_grams(3, None, piece_g=onion) == pytest.approx(60)  # nicht mehr 300 g
    parsley = piece_weight_for_name("Petersilienblatt roh")
    assert to_grams(0.5, None, piece_g=parsley) == pytest.approx(0.5 * parsley)
    pack = unit_weight_for_name("Backpulver", "Packung")
    assert to_grams(1, "Packung", unit_g=pack) == 15
    assert (
        to_grams(1, "Dose", unit_g=unit_weight_for_name("Kidneybohne reif, Konserve, abgetropft", "Dose"))
        == 250
    )
    # ohne Eintrag bleibt die Zeile offen
    assert to_grams(2, None, piece_g=piece_weight_for_name("Rind Hackfleisch, roh")) is None
