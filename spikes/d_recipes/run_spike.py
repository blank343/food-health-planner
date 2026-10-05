"""Spike d: Rezeptimport per URL mit recipe-scrapers (schema.org/Recipe).

Testet je 3 Rezepte von emmikochteinfach.de (nativ unterstützt) und einfachkochen.de
(Wild-Mode / schema.org-Fallback). Höflich: 2 s Pause, ehrlicher User-Agent.
"""
import json
import sys
import time
from pathlib import Path

import httpx
from recipe_scrapers import scrape_html

UA = "FoodHealthPlanner/0.1 (private home use; contact: owner)"
URLS = {
    "emmikochteinfach.de": [
        "https://emmikochteinfach.de/klassische-huehnersuppe/",
        "https://emmikochteinfach.de/asiatischer-gurkensalat/",
        "https://emmikochteinfach.de/asiatisches-lachsfilet-mit-wasabi-und-sesam/",
    ],
    "einfachkochen.de": [
        "https://www.einfachkochen.de/rezepte/butternut-kuerbissuppe-einfach-so-cremig",
        "https://www.einfachkochen.de/rezepte/haehnchen-gemuese-auflauf",
        "https://www.einfachkochen.de/rezepte/huettenkaese-omelett",
    ],
}
OUT = Path(__file__).parent / "out"
OUT.mkdir(exist_ok=True)


def safe(fn):
    try:
        return fn()
    except Exception as e:  # noqa: BLE001  (Spike: Fehlerart interessiert)
        return f"<{type(e).__name__}>"


def main() -> None:
    results = []
    with httpx.Client(headers={"User-Agent": UA}, timeout=30, follow_redirects=True) as c:
        for site, urls in URLS.items():
            for url in urls:
                r = c.get(url)
                s = scrape_html(r.text, org_url=url, supported_only=False)
                item = {
                    "site": site, "url": url, "http": r.status_code,
                    "title": safe(s.title),
                    "yields": safe(s.yields),
                    "total_time_min": safe(s.total_time),
                    "n_ingredients": len(safe(s.ingredients) or []),
                    "ingredients_sample": (safe(s.ingredients) or [])[:3],
                    "nutrients": safe(s.nutrients),
                    "n_steps": len(safe(s.instructions_list) or []),
                    "category": safe(s.category),
                    "image": bool(safe(s.image)),
                }
                results.append(item)
                print(f"\n[{site}] {item['title']}  (HTTP {item['http']})")
                print(f"  Portionen: {item['yields']} | Zeit: {item['total_time_min']} min | "
                      f"Zutaten: {item['n_ingredients']} | Schritte: {item['n_steps']} | Bild: {item['image']}")
                print(f"  Beispiel-Zutaten: {item['ingredients_sample']}")
                print(f"  Nährwerte: {item['nutrients']}")
                time.sleep(2)
    (OUT / "recipes.json").write_text(json.dumps(results, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
