"""Tests für den Web-Rezeptimport (ohne Netzwerk; HTML-Beispiele sind selbst erfunden)."""

import json

import httpx
import pytest

from app.importers import recipe_web
from app.importers.recipe_web import (
    RecipeImportError,
    fetch_html,
    import_recipe_url,
    parse_minutes,
    parse_number,
    parse_recipe_html,
    parse_servings,
)


def _page(recipe: dict | None, title: str = "Testseite") -> str:
    data = ""
    if recipe is not None:
        payload = {"@context": "https://schema.org", "@type": "Recipe", **recipe}
        data = f'<script type="application/ld+json">{json.dumps(payload, ensure_ascii=False)}</script>'
    return f"<html><head><title>{title}</title>{data}</head><body><h1>{title}</h1></body></html>"


FULL = _page(
    {
        "name": "  Linsen-Eintopf  ",
        "recipeYield": "4 Portionen",
        "prepTime": "PT15M",
        "cookTime": "PT30M",
        "image": "https://beispiel.test/bilder/eintopf.jpg",
        "recipeIngredient": ["200 g rote Linsen", " 1 Zwiebel ", "", "2 EL Olivenöl", "Salz und Pfeffer"],
        "recipeInstructions": [
            {"@type": "HowToStep", "text": "Zwiebel würfeln."},
            {"@type": "HowToStep", "text": "Linsen mit Wasser kochen."},
        ],
        "nutrition": {
            "@type": "NutritionInformation",
            "calories": "320 kcal",
            "proteinContent": "12,5 g",
            "fatContent": "9 g",
            "carbohydrateContent": "41.0 g",
            "servingSize": "1 Portion",
        },
    }
)

NO_NUTRITION = _page(
    {
        "name": "Gurkensalat",
        "prepTime": "PT10M",
        "recipeIngredient": ["1 Gurke", "2 EL Essig"],
        "recipeInstructions": "Gurke hobeln.\nMit Essig mischen.",
    }
)

TOTAL_ONLY = _page(
    {
        "name": "Ofengemüse",
        "recipeYield": "für 2 Personen",
        "totalTime": "PT1H20M",
        "recipeIngredient": ["500 g Kürbis"],
        "recipeInstructions": ["Alles in den Ofen."],
    }
)

NO_RECIPE = _page(None, title="Impressum")


# --- Parser für Zahlen, Zeiten, Portionen ---------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("320 kcal", 320.0),
        ("12,5 g", 12.5),
        ("17.00", 17.0),
        ("1.234,5 kJ", 1234.5),
        ("1,234.5", 1234.5),
        ("ca. 3 g", 3.0),
        (7, 7.0),
        (2.5, 2.5),
        ("keine", None),
        ("", None),
        (None, None),
    ],
)
def test_parse_number(text, expected):
    assert parse_number(text) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("4 Portionen", 4.0),
        ("für 2 Personen", 2.0),
        ("4 servings", 4.0),
        ("1,5 Portionen", 1.5),
        ("4-6 Portionen", 4.0),
        ("0 Portionen", None),
        ("Portionen", None),
        (None, None),
    ],
)
def test_parse_servings(text, expected):
    assert parse_servings(text) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (45, 45),
        (30.0, 30),
        ("PT1H30M", 90),
        ("PT45M", 45),
        ("P1DT2H", 26 * 60),
        ("45 Min.", 45),
        ("1 Std. 30 Min.", 90),
        ("2 Stunden", 120),
        ("45", 45),
        (0, None),
        ("PT0M", None),
        ("", None),
        (None, None),
        ("unbekannt", None),
    ],
)
def test_parse_minutes(value, expected):
    assert parse_minutes(value) == expected


# --- parse_recipe_html -----------------------------------------------------------------------


def test_parse_full_page():
    recipe = parse_recipe_html(FULL, "https://www.beispiel.test/rezepte/linsen-eintopf")
    assert recipe.title == "Linsen-Eintopf"
    assert recipe.source_site == "beispiel.test"
    assert recipe.source_url == "https://www.beispiel.test/rezepte/linsen-eintopf"
    assert recipe.servings == 4.0
    assert recipe.prep_min == 15
    assert recipe.cook_min == 30
    assert recipe.ingredient_lines == [
        "200 g rote Linsen",
        "1 Zwiebel",
        "2 EL Olivenöl",
        "Salz und Pfeffer",
    ]
    assert recipe.instructions == "Zwiebel würfeln.\nLinsen mit Wasser kochen."
    assert recipe.image_url == "https://beispiel.test/bilder/eintopf.jpg"
    assert recipe.site_nutrients == {"kcal": 320.0, "protein_g": 12.5, "fat_g": 9.0, "carb_g": 41.0}
    assert recipe.warnings == []


def test_parse_without_nutrition_and_servings():
    recipe = parse_recipe_html(NO_NUTRITION, "https://beispiel.test/gurkensalat")
    assert recipe.title == "Gurkensalat"
    assert recipe.servings is None
    assert recipe.site_nutrients == {}
    assert recipe.prep_min == 10
    assert recipe.cook_min is None
    assert recipe.instructions == "Gurke hobeln.\nMit Essig mischen."
    assert "Keine Portionsangabe gefunden" in recipe.warnings
    assert "Keine Nährwerte auf der Seite" in recipe.warnings
    assert recipe.image_url is None


def test_parse_total_time_only_goes_to_prep():
    recipe = parse_recipe_html(TOTAL_ONLY, "https://beispiel.test/ofengemuese")
    assert recipe.servings == 2.0
    assert recipe.prep_min == 80
    assert recipe.cook_min is None
    assert any("Gesamtzeit" in w for w in recipe.warnings)


def test_parse_no_recipe_raises():
    with pytest.raises(RecipeImportError):
        parse_recipe_html(NO_RECIPE, "https://beispiel.test/impressum")


def test_parse_empty_recipe_raises():
    html = _page({"name": "", "recipeIngredient": []})
    with pytest.raises(RecipeImportError):
        parse_recipe_html(html, "https://beispiel.test/leer")


def test_parse_missing_ingredients_warns():
    html = _page({"name": "Nur Titel", "recipeYield": "2"})
    recipe = parse_recipe_html(html, "https://beispiel.test/titel")
    assert recipe.ingredient_lines == []
    assert "Keine Zutaten gefunden" in recipe.warnings


def test_parse_missing_title_uses_fallback():
    html = _page({"recipeIngredient": ["1 Ei"]})
    recipe = parse_recipe_html(html, "https://www.beispiel.test/x")
    assert recipe.title == "Rezept von beispiel.test"
    assert "Kein Titel gefunden" in recipe.warnings


def test_parse_kj_and_non_portion_serving_size():
    html = _page(
        {
            "name": "Brei",
            "recipeIngredient": ["50 g Haferflocken"],
            "nutrition": {"calories": "836 kJ", "proteinContent": "5 g", "servingSize": "100 g"},
        }
    )
    recipe = parse_recipe_html(html, "https://beispiel.test/brei")
    assert recipe.site_nutrients["kcal"] == pytest.approx(199.81, abs=0.01)
    assert any("nicht auf eine Portion" in w for w in recipe.warnings)


# --- fetch_html ------------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clean_state():
    recipe_web._reset_state()
    yield
    recipe_web._reset_state()


def _client(handler) -> httpx.Client:
    return httpx.Client(
        transport=httpx.MockTransport(handler),
        headers={"User-Agent": recipe_web.USER_AGENT},
        follow_redirects=True,
        max_redirects=recipe_web.MAX_REDIRECTS,
    )


def _robots_handler(robots: str | int, page: httpx.Response | None = None, calls: list | None = None):
    def handler(request: httpx.Request) -> httpx.Response:
        if calls is not None:
            calls.append(str(request.url))
        if request.url.path == "/robots.txt":
            if isinstance(robots, int):
                return httpx.Response(robots)
            return httpx.Response(200, text=robots)
        return page or httpx.Response(200, text="<html>ok</html>", headers={"content-type": "text/html"})

    return handler


def test_fetch_ok_sends_user_agent():
    seen = []

    def handler(request):
        seen.append(request.headers["user-agent"])
        return httpx.Response(200, text="<html>Hallo</html>", headers={"content-type": "text/html"})

    html = fetch_html("https://beispiel.test/r", min_interval=0, client=_client(handler))
    assert html == "<html>Hallo</html>"
    assert seen and all(ua == "FoodHealthPlanner/0.1 (privater Hausgebrauch)" for ua in seen)


def test_fetch_robots_disallow():
    robots = "User-agent: *\nDisallow: /privat/\n"
    client = _client(_robots_handler(robots))
    with pytest.raises(RecipeImportError, match="robots.txt verbietet den Abruf"):
        fetch_html("https://beispiel.test/privat/rezept", min_interval=0, client=client)
    # anderer Pfad desselben Hosts bleibt erlaubt
    assert fetch_html("https://beispiel.test/rezepte/a", min_interval=0, client=client)


def test_fetch_robots_disallow_for_our_agent_only():
    robots = "User-agent: FoodHealthPlanner\nDisallow: /\n"
    client = _client(_robots_handler(robots))
    with pytest.raises(RecipeImportError, match="robots.txt"):
        fetch_html("https://beispiel.test/rezepte/a", min_interval=0, client=client)


@pytest.mark.parametrize("status", [404, 500])
def test_fetch_robots_unavailable_allows(status):
    client = _client(_robots_handler(status))
    assert fetch_html("https://beispiel.test/r", min_interval=0, client=client)


def test_fetch_robots_network_error_allows():
    def handler(request):
        if request.url.path == "/robots.txt":
            raise httpx.ConnectError("kaputt", request=request)
        return httpx.Response(200, text="<html>ok</html>", headers={"content-type": "text/html"})

    assert fetch_html("https://beispiel.test/r", min_interval=0, client=_client(handler))


def test_fetch_robots_cached_per_host():
    calls: list[str] = []
    client = _client(_robots_handler("User-agent: *\nDisallow:\n", calls=calls))
    fetch_html("https://beispiel.test/a", min_interval=0, client=client)
    fetch_html("https://beispiel.test/b", min_interval=0, client=client)
    assert sum(c.endswith("/robots.txt") for c in calls) == 1
    fetch_html("https://anders.test/a", min_interval=0, client=client)
    assert sum(c.endswith("/robots.txt") for c in calls) == 2


def test_fetch_rejects_other_schemes():
    for url in ("ftp://beispiel.test/r", "file:///etc/passwd", "javascript:alert(1)", "beispiel.test/r"):
        with pytest.raises(RecipeImportError, match="http"):
            fetch_html(url, min_interval=0)


def test_fetch_status_errors_in_german():
    page = httpx.Response(404, text="weg")
    with pytest.raises(RecipeImportError, match="404"):
        fetch_html("https://beispiel.test/r", min_interval=0, client=_client(_robots_handler(404, page)))
    recipe_web._reset_state()
    page = httpx.Response(503, text="down")
    with pytest.raises(RecipeImportError, match="Serverfehler"):
        fetch_html("https://beispiel.test/r", min_interval=0, client=_client(_robots_handler(404, page)))


def test_fetch_size_limit_stream():
    big = b"a" * (recipe_web.MAX_BYTES + 1)
    page = httpx.Response(200, content=big, headers={"content-type": "text/html"})
    with pytest.raises(RecipeImportError, match="zu groß"):
        fetch_html("https://beispiel.test/r", min_interval=0, client=_client(_robots_handler(404, page)))


def test_fetch_size_limit_content_length():
    page = httpx.Response(
        200,
        content=b"x",
        headers={"content-type": "text/html", "content-length": str(recipe_web.MAX_BYTES + 1)},
    )

    def handler(request):
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        return page

    with pytest.raises(RecipeImportError, match="zu groß"):
        fetch_html("https://beispiel.test/r", min_interval=0, client=_client(handler))


def test_fetch_exactly_at_limit_is_ok():
    body = b"a" * recipe_web.MAX_BYTES
    page = httpx.Response(200, content=body, headers={"content-type": "text/html"})
    html = fetch_html("https://beispiel.test/r", min_interval=0, client=_client(_robots_handler(404, page)))
    assert len(html) == recipe_web.MAX_BYTES


def test_fetch_non_html_rejected():
    page = httpx.Response(200, content=b"%PDF", headers={"content-type": "application/pdf"})
    with pytest.raises(RecipeImportError, match="keine Webseite"):
        fetch_html("https://beispiel.test/r", min_interval=0, client=_client(_robots_handler(404, page)))


def test_fetch_follows_redirects_up_to_limit():
    def handler(request):
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        n = int(request.url.path.strip("/") or 0)
        if n < 3:
            return httpx.Response(302, headers={"location": f"/{n + 1}"})
        return httpx.Response(200, text="<html>Ziel</html>", headers={"content-type": "text/html"})

    assert fetch_html("https://beispiel.test/0", min_interval=0, client=_client(handler)) == (
        "<html>Ziel</html>"
    )


def test_fetch_too_many_redirects():
    def handler(request):
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        n = int(request.url.path.strip("/") or 0)
        return httpx.Response(302, headers={"location": f"/{n + 1}"})

    with pytest.raises(RecipeImportError, match="Weiterleitungen"):
        fetch_html("https://beispiel.test/0", min_interval=0, client=_client(handler))


def test_fetch_timeout_message():
    def handler(request):
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        raise httpx.ReadTimeout("zu langsam", request=request)

    with pytest.raises(RecipeImportError, match="Zeitüberschreitung"):
        fetch_html("https://beispiel.test/r", min_interval=0, client=_client(handler))


def test_fetch_decodes_declared_charset():
    page = httpx.Response(
        200,
        content="<html>Käse</html>".encode("latin-1"),
        headers={"content-type": "text/html; charset=iso-8859-1"},
    )
    html = fetch_html("https://beispiel.test/r", min_interval=0, client=_client(_robots_handler(404, page)))
    assert "Käse" in html


# --- Pause zwischen Abrufen -----------------------------------------------------------------


def test_throttle_sleeps_between_requests_of_same_host(monkeypatch):
    sleeps: list[float] = []
    monkeypatch.setattr(recipe_web.time, "sleep", sleeps.append)
    recipe_web._throttle("beispiel.test", 1.0)
    assert sleeps == []  # erster Abruf: keine Pause
    recipe_web._throttle("beispiel.test", 1.0)
    assert len(sleeps) == 1
    assert 0 < sleeps[0] <= 1.0
    recipe_web._throttle("anders.test", 1.0)  # anderer Host: keine Pause
    assert len(sleeps) == 1


def test_throttle_disabled_with_zero_interval(monkeypatch):
    sleeps: list[float] = []
    monkeypatch.setattr(recipe_web.time, "sleep", sleeps.append)
    for _ in range(3):
        recipe_web._throttle("beispiel.test", 0)
    assert sleeps == []


def test_fetch_uses_pause_between_calls(monkeypatch):
    sleeps: list[float] = []
    monkeypatch.setattr(recipe_web.time, "sleep", sleeps.append)
    client = _client(_robots_handler(404))
    fetch_html("https://beispiel.test/a", min_interval=1.0, client=client)
    n_first = len(sleeps)
    fetch_html("https://beispiel.test/b", min_interval=1.0, client=client)
    assert len(sleeps) > n_first


# --- import_recipe_url -----------------------------------------------------------------------


def test_import_recipe_url_combines_fetch_and_parse(monkeypatch):
    monkeypatch.setattr(recipe_web, "fetch_html", lambda url: FULL)
    recipe = import_recipe_url("https://www.beispiel.test/rezepte/x")
    assert recipe.title == "Linsen-Eintopf"
    assert recipe.source_site == "beispiel.test"
