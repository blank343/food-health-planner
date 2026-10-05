"""Admin-CLI: create-person, rotate-token, list-persons."""

from datetime import date

import pytest
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app import cli
from app.auth import authenticate, hash_token
from app.models import Person


@pytest.fixture
def factory(engine):
    return sessionmaker(bind=engine, expire_on_commit=False)


def run_cli(factory, *argv):
    return cli.main(list(argv), session_factory=factory)


def last_line(text: str) -> str:
    return text.strip().splitlines()[-1]


def test_create_person_prints_token_once(factory, session, capsys):
    code = run_cli(
        factory,
        "create-person",
        "--name", "Erika Muster",
        "--sex", "f",
        "--birth", "1988-03-02",
        "--height-cm", "168.5",
    )  # fmt: skip
    assert code == 0
    out = capsys.readouterr().out
    person = session.scalar(select(Person).where(Person.name == "Erika Muster"))
    assert person.sex == "f" and person.birth_date == date(1988, 3, 2) and person.height_cm == 168.5
    token = last_line(out)
    assert authenticate(session, token).id == person.id
    assert person.token_hash == hash_token(token)
    assert person.token_hash not in out  # der Hash wird nie ausgegeben


def test_create_person_without_height(factory, session):
    assert run_cli(factory, "create-person", "--name", "Max", "--sex", "m", "--birth", "1990-01-01") == 0
    assert session.scalar(select(Person.height_cm).where(Person.name == "Max")) is None


def test_duplicate_name_is_error(factory, session, capsys):
    args = ("create-person", "--name", "Max", "--sex", "m", "--birth", "1990-01-01")
    assert run_cli(factory, *args) == 0
    capsys.readouterr()
    assert run_cli(factory, *args) == 1
    captured = capsys.readouterr()
    assert "existiert bereits" in captured.err
    assert captured.out == ""
    assert len(session.scalars(select(Person)).all()) == 1


def test_invalid_birth_date_rejected_by_parser(factory, capsys):
    with pytest.raises(SystemExit) as exc:
        run_cli(factory, "create-person", "--name", "X", "--sex", "m", "--birth", "01.02.1990")
    assert exc.value.code == 2
    assert "JJJJ-MM-TT" in capsys.readouterr().err


def test_invalid_sex_rejected_by_parser(factory):
    with pytest.raises(SystemExit):
        run_cli(factory, "create-person", "--name", "X", "--sex", "x", "--birth", "1990-01-01")


def test_future_birth_date_is_error(factory, capsys):
    assert run_cli(factory, "create-person", "--name", "X", "--sex", "m", "--birth", "2999-01-01") == 1
    assert "Vergangenheit" in capsys.readouterr().err


def test_rotate_token(factory, session, capsys):
    run_cli(factory, "create-person", "--name", "Max", "--sex", "m", "--birth", "1990-01-01")
    old = last_line(capsys.readouterr().out)
    assert run_cli(factory, "rotate-token", "--name", "Max") == 0
    new = last_line(capsys.readouterr().out)
    assert new != old
    assert authenticate(session, new) is not None
    assert authenticate(session, old) is None


def test_rotate_unknown_person(factory, capsys):
    assert run_cli(factory, "rotate-token", "--name", "Niemand") == 1
    assert "Keine Person" in capsys.readouterr().err


def test_list_persons_never_shows_tokens(factory, session, capsys):
    run_cli(factory, "create-person", "--name", "Erika", "--sex", "f", "--birth", "1988-03-02")
    token = last_line(capsys.readouterr().out)
    run_cli(factory, "create-person", "--name", "Max", "--sex", "m", "--birth", "1990-01-01")
    capsys.readouterr()
    assert run_cli(factory, "list-persons") == 0
    out = capsys.readouterr().out
    assert "Erika" in out and "Max" in out and "aktiv" in out
    assert token not in out
    assert all(p.token_hash not in out for p in session.scalars(select(Person)))


def test_list_persons_empty(factory, capsys):
    assert run_cli(factory, "list-persons") == 0
    assert "Keine Personen" in capsys.readouterr().out
