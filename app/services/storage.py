from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import BinaryIO

from app.config import get_settings
from app.services.text import slug

settings = get_settings()

_CHUNK_SIZE = 1024 * 1024


def safe_filename(filename: str) -> str:
    path = Path(filename)
    suffix = path.suffix.lower()
    stem = slug(path.stem)[:120]
    return f"{stem}{suffix}"


def save_upload(fileobj: BinaryIO, document_id: str, filename: str) -> tuple[Path, str, int]:
    directory = settings.uploads_dir / document_id
    directory.mkdir(parents=True, exist_ok=True)
    destination = directory / safe_filename(filename)
    digest = hashlib.sha256()
    size = 0
    with destination.open("wb") as output:
        while True:
            chunk = fileobj.read(_CHUNK_SIZE)
            if not chunk:
                break
            size += len(chunk)
            if size > settings.max_upload_mb * 1024 * 1024:
                output.close()
                destination.unlink(missing_ok=True)
                raise ValueError(f"File exceeds {settings.max_upload_mb} MB")
            digest.update(chunk)
            output.write(chunk)
    return destination, digest.hexdigest(), size


def delete_document_files(document_id: str) -> None:
    directory = settings.uploads_dir / document_id
    if directory.exists():
        for child in sorted(directory.rglob("*"), reverse=True):
            if child.is_file():
                child.unlink(missing_ok=True)
            elif child.is_dir():
                child.rmdir()
        directory.rmdir()


def guess_mime_type(filename: str) -> str:
    suffix = Path(filename).suffix.lower()
    if suffix == ".pdf":
        return "application/pdf"
    if suffix == ".docx":
        return "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    return "application/octet-stream"


def sanitize_for_header(value: str) -> str:
    return re.sub(r"[\r\n]", "", value)
