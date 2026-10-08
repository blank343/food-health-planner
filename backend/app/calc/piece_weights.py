"""Stückgewichte typischer Zutaten (Gramm je Stück) für Zeilen wie "3 Möhren" oder "0,5 Petersilie".

Die Schlüssel sind **vollständige BLS-Namen** (Spalte "Bezeichnung" der BLS 4.0), also genau
`Ingredient.name` der importierten Zutat. Beim BLS-Import setzt der Katalog daraus `piece_g`,
wenn die Zutat noch keines hat. Die Werte sind grobe Küchenwerte für den **essbaren Anteil**
(Avocado ohne Kern und Schale, Banane ohne Schale, Hühnerei Größe M ohne Schale); sie sind nur
Startwerte und lassen sich je Zutat überschreiben.

Nicht stückweise gekaufte Zutaten (Hackfleisch, Quark, Mehl, Champignons nach Gewicht usw.)
fehlen bewusst: Ohne Stückgewicht bleibt eine Zeile "2 Hackfleisch" offen zur Prüfung, statt
mit einem erfundenen Wert zu rechnen.

Zusätzlich (für `to_grams(..., unit_g=unit_weight_for_name(name, unit))`):
- `SLICE_WEIGHT_SEED`: Gewicht einer **Scheibe** (Brot, Käse, Schinken).
- `PACK_WEIGHT_SEED`: Gewicht einer **Packung/eines Päckchens** (Backpulver 15 g, Vanillezucker 8 g).
- `CAN_WEIGHT_SEED`: **Abtropfgewicht einer Dose** (Kichererbsen 240 g, Thunfisch 140 g).
  Die Standardtabelle (`defaults.GRAMS_PER_UNIT`) kennt nur eine Zahl je Einheit.
- `PIECE_WEIGHT_ALIAS_SEED`: Stückgewicht für Sorten, die dieselbe BLS-Zutat wie die Normalform
  haben, aber deutlich anders wiegen (Kirschtomate und Tomate sind beide "Tomate roh").
"""

from app.calc.ingredients import normalize_name

__all__ = [
    "CAN_WEIGHT_SEED",
    "PACK_WEIGHT_SEED",
    "PIECE_WEIGHT_ALIAS_SEED",
    "PIECE_WEIGHT_SEED",
    "SLICE_WEIGHT_SEED",
    "piece_weight_for_alias",
    "piece_weight_for_name",
    "slice_weight_for_name",
    "unit_weight_for_name",
]

# BLS-Name -> Gramm je Stück
PIECE_WEIGHT_SEED: dict[str, float] = {
    # Gemüse
    "Speisezwiebel roh": 80.0,
    "Frühlingszwiebel/Lauchzwiebel, roh": 20.0,
    "Schalotte roh": 25.0,
    "Knoblauch roh": 4.0,  # eine Zehe
    "Ingwer/Ingwerwurzel, roh": 20.0,  # ein daumengroßes Stück
    "Karotte/Möhre, roh": 100.0,
    "Zucchini roh": 250.0,
    "Gemüsepaprika rot, roh": 160.0,
    "Gemüsepaprika gelb, roh": 160.0,
    "Gemüsepaprika grün, roh": 150.0,
    "Pfefferschote rot, roh": 15.0,
    "Pfefferschote grün, roh": 15.0,
    "Kartoffel geschält, roh": 90.0,
    "Kartoffel ungeschält, roh": 100.0,
    "Batate/Süßkartoffel, roh": 250.0,
    "Tomate roh": 100.0,
    "Gurke roh": 350.0,
    "Aubergine roh": 300.0,
    "Broccoli roh": 500.0,  # ganzer Kopf
    "Blumenkohl roh": 600.0,  # ganzer Kopf
    "Romanesco roh": 500.0,
    "Kohlrabi roh": 250.0,
    "Gemüsefenchel roh": 250.0,
    "Porree/Lauch, roh": 200.0,
    "Bleichsellerie roh": 60.0,  # eine Stange
    "Knollensellerie roh": 600.0,
    "Rote Rübe/Rote Bete, roh": 100.0,
    "Radieschen roh": 15.0,
    "Rettich roh": 300.0,
    "Pastinake roh": 150.0,
    "Wurzelpetersilie roh": 80.0,
    "Kürbis Hokkaido (C. maxima) roh": 1000.0,
    "Kürbis Pumpkin (C. pepo) roh": 1000.0,
    "Weißkohl roh": 1200.0,
    "Rotkohl roh": 1200.0,
    "Wirsing roh": 1000.0,
    "Spitzkohl roh": 800.0,
    "Chinakohl roh": 800.0,
    "Pak Choi roh": 150.0,
    "Eisbergsalat roh": 500.0,
    "Kopfsalat roh": 300.0,
    "Römischer Salat/Romanasalat, roh": 200.0,
    "Endivie/Escariol, roh": 300.0,
    "Radicchio roh": 200.0,
    "Chicoree roh": 100.0,
    "Artischocke roh": 200.0,
    "Spargel roh": 25.0,  # eine Stange
    "Zuckermais roh": 250.0,  # ein Kolben
    "Kohlrübe/Steckrübe, roh": 800.0,
    "Topinambur/Erdartischocke, roh": 50.0,
    # Frische Kräuter: ein Bund bzw. Töpfchen
    "Petersilienblatt roh": 40.0,
    "Basilikum roh": 30.0,
    "Schnittlauch roh": 30.0,
    # Obst
    "Zitrone roh": 100.0,
    "Limette roh": 60.0,
    "Orange roh": 180.0,
    "Mandarine roh": 70.0,
    "Clementine roh": 65.0,
    "Grapefruit roh": 300.0,
    "Apfel roh": 180.0,
    "Birne roh": 170.0,
    "Banane roh": 120.0,
    "Kiwi roh": 75.0,
    "Avocado roh": 150.0,
    "Mango roh": 350.0,
    "Pfirsich roh": 150.0,
    "Nektarine roh": 140.0,
    "Aprikose roh": 45.0,
    "Pflaume roh": 40.0,
    "Zwetschge roh": 30.0,
    "Feige roh": 50.0,
    "Kaki roh": 150.0,
    "Granatapfel roh": 300.0,
    "Ananas roh": 900.0,
    "Honigmelone roh": 800.0,
    "Quitte roh": 250.0,
    "Dattel getrocknet": 12.0,
    "Pflaume getrocknet": 8.0,
    "Aprikose getrocknet": 8.0,
    "Feige getrocknet": 20.0,
    # Eier
    "Hühnerei roh": 60.0,  # Größe M
    "Hühnerei Eigelb, roh": 18.0,
    "Hühnerei Eiklar, roh": 35.0,
    "Wachtelei roh": 10.0,
    # Fleisch, Fisch, Wurst
    "Hähnchen Brustfilet, roh": 150.0,
    "Hähnchen Brust, ohne Haut, roh": 150.0,
    "Hähnchen Oberschenkel, mit Haut, roh": 130.0,
    "Hähnchen Unterschenkel, mit Haut, roh": 90.0,
    "Hähnchen Flügel, mit Haut, roh": 80.0,
    "Hähnchen ganz, entbeint, mit Haut, roh": 1200.0,
    "Suppenhuhn Fleisch, mit Haut, roh": 1200.0,
    "Pute Brust, ohne Haut, roh": 150.0,
    "Schwein Schnitzel (Oberschale) roh": 150.0,
    "Schwein Kotelett (Rücken/cranial) roh": 180.0,
    "Schwein Filet/Lende, roh": 400.0,
    "Rind Steak (Rücken) roh": 200.0,
    "Rind Filetsteak roh": 150.0,
    "Kalb Schnitzel (Keule) roh": 150.0,
    "Lamm Kotelett, roh": 80.0,
    "Lachs roh": 150.0,
    "Forelle roh": 250.0,
    "Dorsch/Kabeljau, roh": 150.0,
    "Köhler/Seelachs, roh": 150.0,
    "Thunfisch roh": 150.0,
    "Sardine roh": 50.0,
    "Makrele roh": 250.0,
    "Heilbutt/Weißer Heilbutt, roh": 150.0,
    "Rostbratwurst": 120.0,
    "Wiener Würstchen": 50.0,
    "Bockwurst": 100.0,
    "Fleischwurst": 200.0,
    # Milchprodukte
    "Mozzarella mind. 45 % Fett i. Tr.": 125.0,
    "Mozzarella mind. 20 % Fett i. Tr.": 125.0,
    "Feta mind. 45 % Fett i. Tr.": 200.0,
    "Camembert mind. 45 % Fett i. Tr.": 125.0,
    "Halloumi Grillkäse": 225.0,
    "Salzlakenkäse aus Kuhmilch, Hirtenkäse, mind. 45 % Fett i. Tr.": 200.0,
    # Brot und Backwaren
    "Weizenbrötchen": 55.0,
    "Roggenbrötchen": 55.0,
    "Weizenvollkornbrötchen": 60.0,
    "Mehrkornbrötchen": 60.0,
    "Dinkelbrötchen": 60.0,
    "Weizentortilla": 60.0,
    "Weizenfladenbrot": 80.0,
    "Weizenmischtoastbrot": 25.0,  # eine Toastscheibe
    "Roggenmischbrot": 40.0,
    "Vollkornbrot": 40.0,
    "Weizenbrot/Weißbrot": 35.0,
    "Zwieback eifrei": 8.0,
    "Roggenknäckebrot": 10.0,
    "Reiswaffeln ungesalzen": 8.0,
    "Cracker": 4.0,
}

# BLS-Name -> Gramm je Scheibe (Brot, Aufschnitt, Käse)
SLICE_WEIGHT_SEED: dict[str, float] = {
    "Roggenmischbrot": 45.0,
    "Weizenmischbrot": 45.0,
    "Vollkornbrot": 45.0,
    "Roggenbrot": 45.0,
    "Weizenbrot/Weißbrot": 35.0,
    "Weizenmischtoastbrot": 25.0,
    "Roggenknäckebrot": 10.0,
    "Gouda mind. 40 % Fett i. Tr.": 25.0,
    "Gouda 48 % Fett i. Tr.": 25.0,
    "Emmentaler mind. 45 % Fett i. Tr.": 25.0,
    "Edamer mind. 40 % Fett i. Tr.": 25.0,
    "Schnittkäse mind. 45 % Fett i. Tr.": 25.0,
    "Mozzarella mind. 45 % Fett i. Tr.": 30.0,
    "Schwein Kochschinken, Kochpökelware": 20.0,
    "Schwein Bauchspeck, Rohpökelware, geräuchert": 15.0,
    "Schwein Frühstücksspeck, Rohpökelware, geräuchert": 12.0,
    "Parmaschinken": 12.0,
    "Salami": 5.0,
    "Leberkäse": 60.0,
    "Putenbrust, Kochpökelware, geräuchert": 15.0,
    "Lachs geräuchert (Räucherlachs)": 25.0,
    "Zitrone roh": 8.0,
    "Gurke roh": 5.0,
    "Tomate roh": 15.0,
    "Speisezwiebel roh": 5.0,
    "Ananas roh": 80.0,
}

# BLS-Name -> Gramm je Packung/Päckchen (Standard wäre 250 g)
PACK_WEIGHT_SEED: dict[str, float] = {
    "Backpulver": 15.0,
    "Vanillezucker": 8.0,
    "Vanillinzucker": 8.0,
    "Backhefe getrocknet (Trockenbackhefe)": 7.0,
    "Backhefe frisch (Frischbackhefe)": 42.0,
    "Puddingpulver Vanille, ungezuckert": 37.0,
    "Gelatine/Speisegelatine": 10.0,
    "Sahnestandmittel": 8.0,
    "Mozzarella mind. 45 % Fett i. Tr.": 125.0,
    "Mozzarella mind. 20 % Fett i. Tr.": 125.0,
    "Feta mind. 45 % Fett i. Tr.": 200.0,
    "Halloumi Grillkäse": 225.0,
    "Tofu": 200.0,
}

# BLS-Name -> Abtropfgewicht je Dose in g (Standard wäre 400 g)
CAN_WEIGHT_SEED: dict[str, float] = {
    "Thunfisch roh": 140.0,  # "1 Dose Thunfisch" meint Konserve
    "Thunfisch in Öl, Konserve, abgetropft": 140.0,
    "Thunfisch im eigenen Saft, Konserve, abgetropft": 140.0,
    "Sardelle in Öl, Konserve, abgetropft": 50.0,
    "Kichererbse reif, Konserve, abgetropft": 240.0,
    "Kidneybohne reif, Konserve, abgetropft": 250.0,
    "Linse reif, Konserve, abgetropft": 250.0,
    "Zuckermais Konserve, abgetropft": 285.0,
}

# normalisierter Alias -> Gramm je Stück (weicht vom Stückgewicht der Zutat ab)
_RAW_ALIAS_WEIGHTS: dict[str, float] = {
    "Kirschtomate": 15.0,
    "Cherrytomate": 15.0,
    "Snacktomate": 15.0,
    "Datteltomate": 12.0,
    "Cocktailtomate": 30.0,
    "Eiertomate": 70.0,
    "Fleischtomate": 200.0,
    "Snackgurke": 100.0,
    "Minigurke": 100.0,
    "Spitzpaprika": 100.0,
    "Snackpaprika": 30.0,
    "Minipaprika": 30.0,
    "Gemüsezwiebel": 200.0,
    "Knoblauchknolle": 40.0,
    "Babybanane": 80.0,
}
PIECE_WEIGHT_ALIAS_SEED: dict[str, float] = {normalize_name(k): v for k, v in _RAW_ALIAS_WEIGHTS.items()}


def piece_weight_for_name(name: str) -> float | None:
    """Stückgewicht in g für den vollständigen Zutatennamen (exakter Lookup), sonst None."""
    return PIECE_WEIGHT_SEED.get(name)


def slice_weight_for_name(name: str) -> float | None:
    """Gewicht einer Scheibe in g für den vollständigen Zutatennamen (exakter Lookup), sonst None."""
    return SLICE_WEIGHT_SEED.get(name)


def unit_weight_for_name(name: str, unit: str | None) -> float | None:
    """Gewicht der Einheit (Scheibe, Packung, Dose) für diese Zutat in g, sonst None.

    `unit` ist die normalisierte Einheit des Parsers ("Scheibe", "Packung", "Dose"); für andere
    Einheiten gibt es nie einen Wert. Das Ergebnis geht als `unit_g` an `to_grams`.
    """
    tables = {"Scheibe": SLICE_WEIGHT_SEED, "Packung": PACK_WEIGHT_SEED, "Dose": CAN_WEIGHT_SEED}
    table = tables.get(unit or "")
    return None if table is None else table.get(name)


def piece_weight_for_alias(text: str) -> float | None:
    """Stückgewicht für eine Sorte im Rezepttext ("Kirschtomaten" → 15 g), sonst None.

    Gilt nur für Sorten, deren BLS-Zutat ein anderes Stückgewicht hat (`PIECE_WEIGHT_SEED`);
    der Aufrufer nimmt diesen Wert vor dem der Zutat.
    """
    return PIECE_WEIGHT_ALIAS_SEED.get(normalize_name(text))
