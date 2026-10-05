"""Import-API: Upload (gestreamt), Hintergrund-Job, Status. Nur erfundene Daten, Importer sind Fälschungen."""

import io
import zipfile
from datetime import date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.api import uploads
from app.api.imports import get_importers, get_session_factory
from app.auth import generate_token, hash_token
from app.config import get_settings
from app.db import get_session
from app.importers.types import DailyRow, HealthImport, LabReport, LabResultRow, WorkoutRow
from app.main import app
from app.models import ImportJob, Person

BIRTH = date(1990, 5, 1)
XML = b'<?xml version="1.0" encoding="UTF-8"?><HealthData locale="de_DE"></HealthData>'
PDF = b"%PDF-1.4 erfundener Inhalt"
ZIP_MAGIC = b"PK\x03\x04 erfunden"


@pytest.fixture
def factory(engine):
    return sessionmaker(bind=engine, expire_on_commit=False)


@pytest.fixture
def up(tmp_path, monkeypatch):
    """Eigener Upload-Ordner je Test."""
    path = tmp_path / "uploads"
    monkeypatch.setenv("FHP_UPLOAD_DIR", str(path))
    get_settings.cache_clear()
    yield path
    get_settings.cache_clear()


def files_in(path) -> list[str]:
    return sorted(p.name for p in path.iterdir()) if path.exists() else []


@pytest.fixture
def seen():
    """Was die gefälschten Importer gesehen haben."""
    return []


@pytest.fixture
def importers(seen, up):
    def hae(path, progress=None):
        seen.append(("hae", path.name, path.read_bytes(), files_in(up)))
        progress(0.5, "halb") if progress else None
        return HealthImport(
            source="hae_zip",
            daily=[DailyRow(day=date(2025, 1, 1), weight_kg=70.0, active_kcal=400.0, basal_kcal=1500.0)],
            workouts=[WorkoutRow(type="Laufen", start=datetime(2025, 1, 1, 7, 0), duration_min=30.0)],
        )

    def apple(path, progress=None):
        seen.append(("apple_health", path.name, path.read_bytes(), files_in(up)))
        return HealthImport(source="apple_health_xml", daily=[DailyRow(day=date(2025, 1, 2), weight_kg=71.0)])

    def labs(path, progress=None):
        seen.append(("labs", path.name, path.read_bytes(), files_in(up)))
        return LabReport(
            report_type="Endbefund", order_no="T-1", birth_date=BIRTH, patient_name="Erfunden, Erika",
            sample_datetime=datetime(2025, 1, 3, 8, 0),
            results=[LabResultRow(analyte="Testwert", unit="mg/dl", value=1.5)],
        )  # fmt: skip

    return {"hae": hae, "apple_health": apple, "labs": labs}


@pytest.fixture
def client(factory, importers):
    def _session():
        with factory() as s:
            yield s

    app.dependency_overrides[get_session] = _session
    app.dependency_overrides[get_session_factory] = lambda: factory
    app.dependency_overrides[get_importers] = lambda: importers
    try:
        yield TestClient(app)
    finally:
        for dep in (get_session, get_session_factory, get_importers):
            app.dependency_overrides.pop(dep, None)


def _make(session, name, birth=BIRTH) -> dict[str, str]:
    token = generate_token()
    session.add(Person(name=name, sex="f", birth_date=birth, token_hash=hash_token(token)))
    session.commit()
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def a(client, session):
    return _make(session, "Person A")


@pytest.fixture
def b(client, session):
    return _make(session, "Person B")


def make_zip(members: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, data in members.items():
            zf.writestr(name, data)
    return buf.getvalue()


def upload(client, headers, kind, name, content, ctype="application/octet-stream"):
    return client.post(f"/api/me/imports/{kind}", files={"file": (name, content, ctype)}, headers=headers)


# --------------------------------------------------------------------------- Happy Path


def test_requires_auth(client):
    assert client.post("/api/me/imports/hae", files={"file": ("x.csv", b"a")}).status_code == 401
    assert client.get("/api/me/imports").status_code == 401


def test_hae_zip_upload_runs_job(client, a, up, seen):
    resp = upload(client, a, "hae", "export.ZIP", ZIP_MAGIC)
    assert resp.status_code == 202
    body = resp.json()
    assert body["kind"] == "hae"
    assert body["filename"] == "export.ZIP"
    assert body["status"] == "queued"

    job = client.get(f"/api/me/imports/{body['id']}", headers=a).json()
    assert job["status"] == "done"
    assert job["progress"] == 1.0
    assert job["error"] is None
    assert job["stats"]["daily_new"] == 1
    assert job["stats"]["workout_new"] == 1
    assert job["finished_at"] is not None
    assert seen[0][2] == ZIP_MAGIC  # Importer bekam den Inhalt unverändert
    assert files_in(up) == []  # Temp-Datei wurde gelöscht

    daily = client.get("/api/me/health/daily", headers=a).json()
    assert [d["day"] for d in daily] == ["2025-01-01"]


def test_hae_csv_upload(client, a, up):
    resp = upload(client, a, "hae", "HealthAutoExport-2025.csv", b"Date,Weight\n2025-01-01,70\n", "text/csv")
    assert resp.status_code == 202
    assert client.get(f"/api/me/imports/{resp.json()['id']}", headers=a).json()["status"] == "done"
    assert files_in(up) == []


def test_labs_upload(client, a, up):
    resp = upload(client, a, "labs", "befund.pdf", PDF, "application/pdf")
    assert resp.status_code == 202
    job = client.get(f"/api/me/imports/{resp.json()['id']}", headers=a).json()
    assert job["status"] == "done"
    assert job["stats"]["results_new"] == 1
    assert files_in(up) == []
    labs = client.get("/api/me/labs", headers=a).json()
    assert len(labs) == 1
    assert "patient_name" not in labs[0]
    assert "Erfunden" not in str(labs)


def test_labs_birth_date_mismatch_fails_job(client, session, up):
    other = _make(session, "Person C", birth=date(1985, 1, 1))
    resp = upload(client, other, "labs", "befund.pdf", PDF)
    assert resp.status_code == 202
    job = client.get(f"/api/me/imports/{resp.json()['id']}", headers=other).json()
    assert job["status"] == "failed"
    assert "Geburtsdatum" in job["error"]
    assert files_in(up) == []
    assert client.get("/api/me/labs", headers=other).json() == []


def test_importer_crash_fails_job_with_german_message(client, a, up, importers):
    def boom(path, progress=None):
        raise RuntimeError("interner Fehler mit Details")

    importers["hae"] = boom
    resp = upload(client, a, "hae", "x.csv", b"a,b\n1,2\n")
    assert resp.status_code == 202
    job = client.get(f"/api/me/imports/{resp.json()['id']}", headers=a).json()
    assert job["status"] == "failed"
    assert "fehlgeschlagen" in job["error"]
    assert "Details" not in job["error"]
    assert files_in(up) == []


def test_upload_is_streamed_in_chunks(client, a, up, seen, monkeypatch):
    monkeypatch.setattr(uploads, "CHUNK_BYTES", 7)
    content = b"%PDF-" + bytes(range(65, 91)) * 5
    resp = upload(client, a, "labs", "befund.pdf", content)
    assert resp.status_code == 202
    assert seen[0][2] == content


def test_filename_is_reduced_to_basename(client, a):
    resp = upload(client, a, "hae", "..\\..\\evil/pfad\\daten.csv", b"a\n")
    assert resp.status_code == 202
    assert resp.json()["filename"] == "daten.csv"


# --------------------------------------------------------------------------- Apple Health


def test_apple_health_bare_xml(client, a, up, seen):
    resp = upload(client, a, "apple-health", "export.xml", XML, "text/xml")
    assert resp.status_code == 202
    job = client.get(f"/api/me/imports/{resp.json()['id']}", headers=a).json()
    assert job["status"] == "done"
    assert job["kind"] == "apple_health"
    assert seen[0][2] == XML
    assert files_in(up) == []


def test_apple_health_zip_extracts_only_export_xml(client, a, up, seen):
    payload = make_zip(
        {
            "apple_health_export/export.xml": XML,
            "apple_health_export/export_cda.xml": b"<ClinicalDocument>nicht entpacken</ClinicalDocument>",
            "apple_health_export/workout-routes/route_1.gpx": b"<gpx>nicht entpacken</gpx>",
            "../../escape.txt": b"nicht entpacken",
        }
    )
    resp = upload(client, a, "apple-health", "export.zip", payload, "application/zip")
    assert resp.status_code == 202
    job = client.get(f"/api/me/imports/{resp.json()['id']}", headers=a).json()
    assert job["status"] == "done", job
    kind, name, content, during = seen[0]
    assert kind == "apple_health"
    assert name.startswith("apple-export-") and name.endswith(".xml")  # eigene Temp-Datei, kein ZIP-Pfad
    assert content == XML
    # Während des Imports lagen nur das ZIP und die eine entpackte XML im Ordner
    assert len(during) == 2
    assert sum(n.endswith(".xml") for n in during) == 1
    assert files_in(up) == []  # danach ist alles weg
    assert not (up.parent / "escape.txt").exists()
    assert not (up.parent.parent / "escape.txt").exists()


def test_apple_health_zip_finds_xml_by_basename(client, a, up, seen):
    payload = make_zip({"irgendein_ordner/export.xml": XML, "andere.xml": b"<x/>"})
    resp = upload(client, a, "apple-health", "export.zip", payload)
    job = client.get(f"/api/me/imports/{resp.json()['id']}", headers=a).json()
    assert job["status"] == "done"
    assert seen[0][2] == XML


def test_apple_health_zip_without_export_xml_fails(client, a, up, seen):
    payload = make_zip({"apple_health_export/export_cda.xml": b"<x/>"})
    resp = upload(client, a, "apple-health", "export.zip", payload)
    assert resp.status_code == 202
    job = client.get(f"/api/me/imports/{resp.json()['id']}", headers=a).json()
    assert job["status"] == "failed"
    assert "export.xml" in job["error"]
    assert seen == []
    assert files_in(up) == []


def test_apple_health_corrupt_zip_fails(client, a, up, seen):
    resp = upload(client, a, "apple-health", "export.zip", ZIP_MAGIC)
    job = client.get(f"/api/me/imports/{resp.json()['id']}", headers=a).json()
    assert job["status"] == "failed"
    assert "ZIP" in job["error"]
    assert files_in(up) == []


def test_apple_health_importer_failure_cleans_both_files(client, a, up, importers):
    def boom(path, progress=None):
        raise RuntimeError("kaputt")

    importers["apple_health"] = boom
    resp = upload(client, a, "apple-health", "export.zip", make_zip({"apple_health_export/export.xml": XML}))
    job = client.get(f"/api/me/imports/{resp.json()['id']}", headers=a).json()
    assert job["status"] == "failed"
    assert files_in(up) == []


# --------------------------------------------------------------------------- Ablehnung


@pytest.mark.parametrize(
    ("kind", "name"),
    [
        ("hae", "daten.txt"),
        ("hae", "daten"),
        ("hae", "daten.xml"),
        ("apple-health", "daten.csv"),
        ("labs", "befund.zip"),
        ("labs", "befund.PDF.exe"),
    ],
)
def test_wrong_extension_rejected(client, a, up, kind, name):
    resp = upload(client, a, kind, name, PDF)
    assert resp.status_code == 415
    assert "nicht unterstützt" in resp.json()["detail"]
    assert client.get("/api/me/imports", headers=a).json() == []
    assert files_in(up) == []


def test_wrong_content_rejected(client, a, up):
    resp = upload(client, a, "labs", "befund.pdf", b"das ist gar kein pdf")
    assert resp.status_code == 422
    assert "PDF" in resp.json()["detail"]
    resp = upload(client, a, "hae", "export.zip", b"kein zip")
    assert resp.status_code == 422
    assert client.get("/api/me/imports", headers=a).json() == []
    assert files_in(up) == []


def test_empty_file_rejected(client, a, up):
    resp = upload(client, a, "hae", "leer.csv", b"")
    assert resp.status_code == 422
    assert "leer" in resp.json()["detail"]
    assert files_in(up) == []


def test_size_limit(client, a, up, monkeypatch):
    monkeypatch.setenv("FHP_MAX_UPLOAD_MB", "1")
    get_settings.cache_clear()
    limit = 1024 * 1024
    ok = upload(client, a, "hae", "gross.csv", b"x" * limit)
    assert ok.status_code == 202

    too_big = upload(client, a, "hae", "zu_gross.csv", b"x" * (limit + 1))
    assert too_big.status_code == 413
    assert "zu groß" in too_big.json()["detail"]
    assert "1 MB" in too_big.json()["detail"]
    assert files_in(up) == []  # Teildatei gelöscht
    assert len(client.get("/api/me/imports", headers=a).json()) == 1  # kein Job für die große Datei


# --------------------------------------------------------------------------- Parallele Jobs


def _add_job(session, person_name, kind="hae", status="running", age=timedelta(0)):
    person = session.scalar(select(Person).where(Person.name == person_name))
    job = ImportJob(person_id=person.id, kind=kind, status=status, filename="alt.zip")
    session.add(job)
    session.commit()
    if age:
        job.created_at = datetime.now() - age
        session.commit()
    return job


@pytest.mark.parametrize("status", ["queued", "running"])
def test_second_job_of_same_kind_is_409(client, a, session, up, status):
    _add_job(session, "Person A", "hae", status)
    resp = upload(client, a, "hae", "neu.csv", b"a\n")
    assert resp.status_code == 409
    assert "läuft bereits" in resp.json()["detail"]
    assert files_in(up) == []


def test_other_kind_and_other_person_not_blocked(client, a, b, session):
    _add_job(session, "Person A", "hae", "running")
    assert upload(client, a, "labs", "befund.pdf", PDF).status_code == 202
    assert upload(client, b, "hae", "neu.csv", b"a\n").status_code == 202


def test_finished_or_stale_job_does_not_block(client, a, session):
    _add_job(session, "Person A", "hae", "done")
    _add_job(session, "Person A", "hae", "failed")
    _add_job(session, "Person A", "hae", "running", age=timedelta(days=2))  # hängengeblieben
    assert upload(client, a, "hae", "neu.csv", b"a\n").status_code == 202


# --------------------------------------------------------------------------- Status und Isolation


def test_list_newest_first_and_limited(client, a, session):
    for _ in range(22):
        _add_job(session, "Person A", "labs", "done")
    jobs = client.get("/api/me/imports", headers=a).json()
    assert len(jobs) == 20
    ids = [j["id"] for j in jobs]
    assert ids == sorted(ids, reverse=True)


def test_job_fields(client, a, session):
    job = _add_job(session, "Person A", "hae", "running")
    body = client.get(f"/api/me/imports/{job.id}", headers=a).json()
    assert set(body) == {
        "id", "kind", "filename", "status", "progress", "message", "stats", "error",
        "created_at", "started_at", "finished_at",
    }  # fmt: skip
    assert body["status"] == "running"
    assert 0.0 <= body["progress"] <= 1.0


def test_foreign_and_unknown_job_is_404(client, a, b, session):
    job = _add_job(session, "Person B", "hae", "done")
    assert client.get(f"/api/me/imports/{job.id}", headers=a).status_code == 404
    assert client.get("/api/me/imports/999999", headers=a).status_code == 404
    assert client.get(f"/api/me/imports/{job.id}", headers=b).status_code == 200
    assert client.get("/api/me/imports", headers=a).json() == []
    assert [j["id"] for j in client.get("/api/me/imports", headers=b).json()] == [job.id]
