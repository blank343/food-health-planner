"""Verwaltung per Kommandozeile: `python -m app.cli <befehl>`.

Die Funktionen nehmen eine Session entgegen und sind damit ohne echte Datenbank testbar.
Ein Token wird nur direkt nach `create-person` bzw. `rotate-token` einmalig angezeigt.
"""

import argparse
import sys
from collections.abc import Callable, Sequence
from datetime import date
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.auth import generate_token, hash_token
from app.db import make_session_factory
from app.models import Person
from app.services import catalog
from app.services import recipes as recipe_service


class CliError(Exception):
    """Fehler mit deutscher Meldung für die Anzeige."""


def create_person(
    session: Session, *, name: str, sex: str, birth_date: date, height_cm: float | None = None
) -> tuple[Person, str]:
    name = name.strip()
    if not name:
        raise CliError("Der Name darf nicht leer sein.")
    if sex not in ("m", "f"):
        raise CliError("Geschlecht muss 'm' oder 'f' sein.")
    if birth_date >= date.today():
        raise CliError("Das Geburtsdatum muss in der Vergangenheit liegen.")
    if height_cm is not None and not 50 <= height_cm <= 260:
        raise CliError("Die Körpergröße muss zwischen 50 und 260 cm liegen.")
    if session.scalar(select(Person.id).where(Person.name == name)) is not None:
        raise CliError(f"Eine Person mit dem Namen '{name}' existiert bereits.")
    token = generate_token()
    person = Person(
        name=name, sex=sex, birth_date=birth_date, height_cm=height_cm,
        token_hash=hash_token(token), is_active=True,
    )  # fmt: skip
    session.add(person)
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise CliError(f"Eine Person mit dem Namen '{name}' existiert bereits.") from exc
    return person, token


def rotate_token(session: Session, *, name: str) -> tuple[Person, str]:
    person = session.scalar(select(Person).where(Person.name == name.strip()))
    if person is None:
        raise CliError(f"Keine Person mit dem Namen '{name}' gefunden.")
    token = generate_token()
    person.token_hash = hash_token(token)
    session.commit()
    return person, token


def list_persons(session: Session) -> list[Person]:
    return list(session.scalars(select(Person).order_by(Person.id)))


def _iso_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise argparse.ArgumentTypeError("Datum bitte als JJJJ-MM-TT angeben.") from None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m app.cli", description="Food & Health Planner Verwaltung")
    sub = parser.add_subparsers(dest="command", required=True)

    create = sub.add_parser("create-person", help="Person anlegen und Zugangstoken ausgeben")
    create.add_argument("--name", required=True)
    create.add_argument("--sex", required=True, choices=["m", "f"])
    create.add_argument("--birth", required=True, type=_iso_date, help="Geburtsdatum, JJJJ-MM-TT")
    create.add_argument("--height-cm", type=float, default=None)

    rotate = sub.add_parser("rotate-token", help="Neues Zugangstoken erzeugen (altes wird ungültig)")
    rotate.add_argument("--name", required=True)

    sub.add_parser("list-persons", help="Personen auflisten (ohne Tokens)")

    bls = sub.add_parser("import-bls", help="BLS-Nährwertdatei (XLSX oder ZIP) in den Katalog importieren")
    bls.add_argument("path", type=Path, help="Pfad zur BLS-Datei (liegt nie im Repo)")

    recipe = sub.add_parser("import-recipe", help="Rezept von einer URL importieren")
    recipe.add_argument("url")

    sub.add_parser("seed-synonyms", help="Start-Synonyme für Zutaten anlegen (idempotent)")
    return parser


MAX_MISSING_SHOWN = 15


def import_bls(session: Session, path: Path, out: Callable[[str], None] = print) -> dict[str, int]:
    """BLS-Datei importieren, danach die Start-Synonyme anlegen. Gibt Fortschritt und Zusammenfassung aus."""
    last_step = -1

    def progress(fraction: float, message: str) -> None:
        nonlocal last_step
        step = int(fraction * 10)  # höchstens eine Zeile je 10 %
        if step != last_step or fraction >= 1.0:
            last_step = step
            out(f"[{fraction * 100:3.0f} %] {message}")

    try:
        stats = catalog.import_bls_file(session, path, progress)
    except FileNotFoundError as exc:
        raise CliError(str(exc)) from exc
    except (ValueError, OSError) as exc:
        raise CliError(f"BLS-Datei konnte nicht gelesen werden: {exc}") from exc
    out(
        f"Zutaten: {stats['created']} neu, {stats['updated']} aktualisiert, "
        f"{stats['unchanged']} unverändert, {stats['skipped']} übersprungen."
    )
    seed_synonyms(session, out)
    return stats


def seed_synonyms(session: Session, out: Callable[[str], None] = print) -> dict[str, object]:
    result = catalog.ensure_seed_synonyms(session)
    out(
        f"Synonyme: {result['created']} angelegt, {result['skipped']} schon vorhanden, "
        f"{result['not_found']} ohne Treffer im Katalog."
    )
    missing: list[str] = list(result["missing"])  # type: ignore[call-overload]
    if missing:
        out("Nicht gefundene Zielnamen (BLS-Datei passt evtl. nicht zur Version der Liste):")
        for name in missing[:MAX_MISSING_SHOWN]:
            out(f"  - {name}")
        if len(missing) > MAX_MISSING_SHOWN:
            out(f"  … und {len(missing) - MAX_MISSING_SHOWN} weitere")
    return result


def import_recipe(
    session: Session, url: str, out: Callable[[str], None] = print
) -> recipe_service.ImportResult:
    """Rezept von einer URL importieren und speichern; gibt Titel, Zeilen, Zuordnung und Status aus."""
    from app.importers import recipe_web  # erst bei Bedarf (lädt recipe-scrapers)

    url = url.strip()
    existing = recipe_service.find_by_url(session, url)
    if existing is not None:
        raise CliError(f"Dieses Rezept ist schon vorhanden (ID {existing.id}: {existing.title}).")
    try:
        imported = recipe_web.import_recipe_url(url)
    except recipe_web.RecipeImportError as exc:
        raise CliError(str(exc)) from exc
    result = recipe_service.build_recipe_from_import(session, imported)
    recipe = result.recipe
    out(f"Rezept '{recipe.title}' gespeichert (ID {recipe.id}).")
    out(
        f"Zutatenzeilen: {result.line_count}, davon zugeordnet: {result.assigned_count}. "
        f"Status: {recipe.status}."
    )
    for warning in result.warnings:
        out(f"Hinweis: {warning}")
    if recipe.status != "ready":
        out("Offene Zeilen lassen sich in der Prüfliste (Oberfläche) zuordnen.")
    return result


def run(args: argparse.Namespace, session: Session, out: Callable[[str], None] = print) -> None:
    if args.command in ("import-bls", "import-recipe", "seed-synonyms"):
        _run_catalog(args, session, out)
    elif args.command == "create-person":
        person, token = create_person(
            session, name=args.name, sex=args.sex, birth_date=args.birth, height_cm=args.height_cm
        )
        out(f"Person '{person.name}' angelegt (ID {person.id}).")
        out("Zugangstoken (wird nur jetzt angezeigt, bitte sicher aufbewahren):")
        out(token)
    elif args.command == "rotate-token":
        person, token = rotate_token(session, name=args.name)
        out(f"Neues Zugangstoken für '{person.name}' (das alte ist ungültig, wird nur jetzt angezeigt):")
        out(token)
    elif args.command == "list-persons":
        persons = list_persons(session)
        if not persons:
            out("Keine Personen vorhanden.")
        for p in persons:
            height = f"{p.height_cm:g} cm" if p.height_cm is not None else "Größe unbekannt"
            out(
                f"{p.id}\t{p.name}\t{p.sex}\t{p.birth_date.isoformat()}\t{height}\t"
                f"{'aktiv' if p.is_active else 'inaktiv'}\t"
                f"Token: {'gesetzt' if p.token_hash else 'keins'}"
            )


def _run_catalog(args: argparse.Namespace, session: Session, out: Callable[[str], None]) -> bool:
    if args.command == "import-bls":
        import_bls(session, args.path, out)
    elif args.command == "import-recipe":
        import_recipe(session, args.url, out)
    elif args.command == "seed-synonyms":
        seed_synonyms(session, out)
    else:
        return False
    return True


def main(argv: Sequence[str] | None = None, session_factory: sessionmaker[Session] | None = None) -> int:
    args = build_parser().parse_args(argv)
    factory = session_factory or make_session_factory()
    with factory() as session:
        try:
            run(args, session)
        except CliError as exc:
            print(f"Fehler: {exc}", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
