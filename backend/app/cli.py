"""Verwaltung per Kommandozeile: `python -m app.cli <befehl>`.

Die Funktionen nehmen eine Session entgegen und sind damit ohne echte Datenbank testbar.
Ein Token wird nur direkt nach `create-person` bzw. `rotate-token` einmalig angezeigt.
"""

import argparse
import sys
from collections.abc import Callable, Sequence
from datetime import date

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.auth import generate_token, hash_token
from app.db import make_session_factory
from app.models import Person


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
    return parser


def run(args: argparse.Namespace, session: Session, out: Callable[[str], None] = print) -> None:
    if args.command == "create-person":
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
