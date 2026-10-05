"""Importe: Datei hochladen (gestreamt), im Hintergrund verarbeiten, Status abfragen."""

import logging
import os
import tempfile
import zipfile
from collections.abc import Callable
from datetime import datetime, timedelta
from pathlib import Path, PurePosixPath
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.api.deps import CurrentPerson, Db, get_owned_or_404
from app.api.schemas import ApiModel
from app.api.uploads import CHUNK_BYTES, display_name, ensure_extension, save_upload, upload_dir
from app.db import make_session_factory
from app.models import ImportJob
from app.services.ingest import create_job, run_import_job

log = logging.getLogger(__name__)

router = APIRouter(prefix="/me/imports", tags=["Importe"])

# Ein Job, der so lange "queued"/"running" ist, gilt als hängengeblieben (z. B. Serverabsturz)
# und blockiert keinen neuen Import mehr.
STALE_JOB_AFTER = timedelta(hours=12)
MAX_XML_BYTES = 40 * 1024**3  # Obergrenze für die entpackte export.xml (Schutz vor ZIP-Bomben)
EXPORT_XML_NAME = "export.xml"


# --------------------------------------------------------------------------- Abhängigkeiten
def get_session_factory() -> sessionmaker[Session]:
    """Session-Fabrik für Hintergrund-Jobs. Tests überschreiben sie mit der Test-Engine."""
    return make_session_factory()


def get_importers() -> dict[str, Callable] | None:
    """Importer je Job-Art; `None` = echte Importer. Tests überschreiben sie mit Fälschungen."""
    return None


SessionFactory = Annotated[sessionmaker[Session], Depends(get_session_factory)]
Importers = Annotated[dict[str, Callable] | None, Depends(get_importers)]


# --------------------------------------------------------------------------- Schema
class ImportJobOut(ApiModel):
    """Stand eines Import-Jobs."""

    id: int
    kind: str
    filename: str | None
    status: str  # queued | running | done | failed
    progress: float  # 0..1
    message: str | None
    stats: dict
    error: str | None
    created_at: datetime | None
    started_at: datetime | None
    finished_at: datetime | None


# --------------------------------------------------------------------------- Apple-Health-ZIP
class _ExportError(Exception):
    """Entpacken fehlgeschlagen (deutsche Meldung für den Job)."""


def _extract_export_xml(zip_path: Path) -> Path:
    """Entpackt NUR die `export.xml` in eine eigene Temp-Datei und gibt deren Pfad zurück.

    Der Pfad des ZIP-Eintrags wird nie verwendet (nur der Basisname wird verglichen). Alle anderen
    Einträge (Routen, EKGs, Bilder) bleiben ungelesen.
    """
    try:
        with zipfile.ZipFile(zip_path) as zf:
            members = [
                i
                for i in zf.infolist()
                if not i.is_dir() and PurePosixPath(i.filename.replace("\\", "/")).name == EXPORT_XML_NAME
            ]
            if not members:
                raise _ExportError("Im ZIP wurde keine export.xml gefunden. Ist es der Apple-Health-Export?")
            members.sort(
                key=lambda i: (i.filename != f"apple_health_export/{EXPORT_XML_NAME}", len(i.filename))
            )
            fd, name = tempfile.mkstemp(prefix="apple-export-", suffix=".xml", dir=upload_dir())
            out_path = Path(name)
            try:
                copied = 0
                with os.fdopen(fd, "wb") as dst, zf.open(members[0]) as src:
                    while chunk := src.read(CHUNK_BYTES):
                        copied += len(chunk)
                        if copied > MAX_XML_BYTES:
                            raise _ExportError("Die export.xml im ZIP ist unplausibel groß.")
                        dst.write(chunk)
            except BaseException:
                out_path.unlink(missing_ok=True)
                raise
    except zipfile.BadZipFile as exc:
        raise _ExportError("Die ZIP-Datei ist beschädigt oder unvollständig.") from exc
    return out_path


def _fail_job(session_factory: sessionmaker[Session], job_id: int, error: str) -> None:
    with session_factory() as session:
        job = session.get(ImportJob, job_id)
        if job is not None:
            job.status, job.error, job.finished_at = "failed", error, datetime.now()
            session.commit()


def _run_apple_health_job(
    session_factory: sessionmaker[Session],
    job_id: int,
    path: Path,
    *,
    importers: dict[str, Callable] | None = None,
) -> None:
    """Bereitet die `export.xml` vor (aus `export.zip` oder direkt) und startet den Import.

    Löscht in jedem Fall den Upload und die entpackte XML-Datei.
    """
    xml_path: Path | None = None
    try:
        if path.suffix.lower() == ".zip":
            try:
                xml_path = _extract_export_xml(path)
            except _ExportError as exc:
                _fail_job(session_factory, job_id, str(exc))
                return
            except Exception:  # noqa: BLE001  (Hintergrund-Job: Fehler in den Job schreiben)
                log.exception("Entpacken fehlgeschlagen (Job %s)", job_id)
                _fail_job(session_factory, job_id, "Das ZIP konnte nicht entpackt werden.")
                return
            source = xml_path
        else:
            source = path
        run_import_job(session_factory, job_id, source, delete_file=True, importers=importers)
    finally:
        path.unlink(missing_ok=True)
        if xml_path is not None:
            xml_path.unlink(missing_ok=True)


# --------------------------------------------------------------------------- Hochladen
def _accept_upload(
    kind: str,
    file: UploadFile,
    allowed: tuple[str, ...],
    runner: Callable,
    *,
    person,
    db: Session,
    session_factory: sessionmaker[Session],
    importers: dict[str, Callable] | None,
    background: BackgroundTasks,
) -> ImportJob:
    suffix = ensure_extension(file, allowed)
    cutoff = datetime.now() - STALE_JOB_AFTER
    busy = db.scalar(
        select(ImportJob.id).where(
            ImportJob.person_id == person.id,
            ImportJob.kind == kind,
            ImportJob.status.in_(("queued", "running")),
            ImportJob.created_at > cutoff,
        )
    )
    if busy is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail="Für diese Importart läuft bereits ein Import. Bitte warte, bis er fertig ist.",
        )
    path = save_upload(file, suffix)
    try:
        job = create_job(db, person, kind, display_name(file))
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    background.add_task(runner, session_factory, job.id, path, importers=importers)
    return job


_FILE = File(description="Die Datei als Multipart-Feld `file`.")
_ACCEPTED = {"response_model": ImportJobOut, "status_code": status.HTTP_202_ACCEPTED}


@router.post("/hae", summary="Health-Auto-Export-Datei importieren (.zip oder .csv)", **_ACCEPTED)
def import_hae(
    file: Annotated[UploadFile, _FILE],
    background: BackgroundTasks,
    person: CurrentPerson,
    db: Db,
    session_factory: SessionFactory,
    importers: Importers,
):
    return _accept_upload(
        "hae", file, (".zip", ".csv"), run_import_job,
        person=person, db=db, session_factory=session_factory, importers=importers, background=background,
    )  # fmt: skip


@router.post(
    "/apple-health",
    summary="Apple-Health-Export importieren (export.zip oder export.xml)",
    **_ACCEPTED,
)
def import_apple_health(
    file: Annotated[UploadFile, _FILE],
    background: BackgroundTasks,
    person: CurrentPerson,
    db: Db,
    session_factory: SessionFactory,
    importers: Importers,
):
    return _accept_upload(
        "apple_health", file, (".zip", ".xml"), _run_apple_health_job,
        person=person, db=db, session_factory=session_factory, importers=importers, background=background,
    )  # fmt: skip


@router.post("/labs", summary="Laborbefund importieren (.pdf)", **_ACCEPTED)
def import_labs(
    file: Annotated[UploadFile, _FILE],
    background: BackgroundTasks,
    person: CurrentPerson,
    db: Db,
    session_factory: SessionFactory,
    importers: Importers,
):
    return _accept_upload(
        "labs", file, (".pdf",), run_import_job,
        person=person, db=db, session_factory=session_factory, importers=importers, background=background,
    )  # fmt: skip


# --------------------------------------------------------------------------- Status
@router.get("", response_model=list[ImportJobOut], summary="Letzte Importe (neueste zuerst, max. 20)")
def list_imports(person: CurrentPerson, db: Db):
    stmt = select(ImportJob).where(ImportJob.person_id == person.id).order_by(ImportJob.id.desc()).limit(20)
    return list(db.scalars(stmt))


@router.get("/{job_id}", response_model=ImportJobOut, summary="Status eines Imports")
def get_import(job_id: int, person: CurrentPerson, db: Db):
    return get_owned_or_404(db, ImportJob, job_id, person)
