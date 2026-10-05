"""Gestreamter Datei-Upload auf die Platte (Chunks, Größenlimit, Endungs- und Kopfprüfung).

Große Dateien (Apple-Exporte über 1 GB) werden nie komplett in den Speicher gelesen. Der Dateiname des
Clients wird nie für einen Pfad verwendet, nur als Anzeigename für den Job.
"""

import os
import tempfile
from pathlib import Path

from fastapi import HTTPException, UploadFile, status

from app.config import get_settings

CHUNK_BYTES = 1024 * 1024
MAX_NAME_LEN = 255

# Erste Bytes je Endung (Plausibilitätsprüfung, kein Virenscan)
_MAGIC = {".zip": b"PK", ".pdf": b"%PDF", ".xml": b"<"}
_LEAD = b"\xef\xbb\xbf \t\r\n"  # UTF-8-BOM und Leerraum vor dem Dateikopf


def upload_dir() -> Path:
    """Zwischenablage für Uploads (wird bei Bedarf angelegt)."""
    configured = get_settings().upload_dir
    path = Path(configured) if configured else Path(tempfile.gettempdir()) / "fhp-uploads"
    path.mkdir(parents=True, exist_ok=True)
    return path


def display_name(file: UploadFile) -> str:
    """Dateiname ohne Verzeichnisanteil, gekürzt (nur zur Anzeige)."""
    name = os.path.basename((file.filename or "").replace("\\", "/")).strip()
    return name[:MAX_NAME_LEN] or "unbenannt"


def ensure_extension(file: UploadFile, allowed: tuple[str, ...]) -> str:
    """Kleingeschriebene Endung der Datei, sonst 415."""
    suffix = Path(display_name(file)).suffix.lower()
    if suffix not in allowed:
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Dateityp nicht unterstützt. Erlaubt: {', '.join(allowed)}.",
        )
    return suffix


def save_upload(file: UploadFile, suffix: str) -> Path:
    """Schreibt den Upload in Chunks in eine neue Datei im Upload-Ordner und liefert deren Pfad.

    Überschreitet die Datei `max_upload_mb`, wird 413 gemeldet und die Teildatei gelöscht.
    Leere Dateien und falsche Dateikopfzeilen (z. B. keine ZIP-Datei) ergeben 422.
    """
    limit = get_settings().max_upload_mb * 1024 * 1024
    fd, name = tempfile.mkstemp(prefix="upload-", suffix=suffix, dir=upload_dir())
    path = Path(name)
    total = 0
    try:
        with os.fdopen(fd, "wb") as out:
            while chunk := file.file.read(CHUNK_BYTES):
                if total == 0 and (magic := _MAGIC.get(suffix)) and not chunk.lstrip(_LEAD).startswith(magic):
                    raise HTTPException(
                        status.HTTP_422_UNPROCESSABLE_CONTENT,
                        detail=f"Die Datei ist keine gültige {suffix[1:].upper()}-Datei.",
                    )
                total += len(chunk)
                if total > limit:
                    raise HTTPException(
                        status.HTTP_413_CONTENT_TOO_LARGE,
                        detail=f"Die Datei ist zu groß (Limit {get_settings().max_upload_mb} MB).",
                    )
                out.write(chunk)
        if total == 0:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Die Datei ist leer.")
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    return path
