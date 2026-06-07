import os
import zipfile
import codecs
from dataclasses import dataclass
from typing import BinaryIO

from fastapi import HTTPException, UploadFile, status

from app.config import settings


@dataclass(frozen=True)
class UploadPolicy:
    max_files: int
    max_file_bytes: int
    max_total_bytes: int


POLICY = UploadPolicy(
    max_files=settings.UPLOAD_MAX_FILES,
    max_file_bytes=settings.UPLOAD_MAX_FILE_MB * 1024 * 1024,
    max_total_bytes=settings.UPLOAD_MAX_TOTAL_MB * 1024 * 1024,
)

_ALLOWED_MIME_TYPES = {
    ".pdf": {"application/pdf", "application/octet-stream"},
    ".docx": {
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/zip",
        "application/octet-stream",
    },
    ".txt": {"text/plain", "application/octet-stream"},
}


def validate_upload_metadata(file: UploadFile) -> tuple[str, str]:
    safe_filename = os.path.basename(file.filename or "")
    if not safe_filename:
        raise HTTPException(status_code=400, detail="Invalid filename")

    extension = os.path.splitext(safe_filename)[1].lower()
    if extension not in _ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported file type: {safe_filename}",
        )

    content_type = (file.content_type or "application/octet-stream").lower()
    if content_type not in _ALLOWED_MIME_TYPES[extension]:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Invalid content type for {safe_filename}",
        )
    return safe_filename, extension


def stream_upload(file: UploadFile, destination: BinaryIO, total_so_far: int) -> tuple[int, bytes]:
    file_bytes = 0
    first_bytes = b""

    while True:
        chunk = file.file.read(settings.UPLOAD_CHUNK_SIZE_BYTES)
        if not chunk:
            break
        if not first_bytes:
            first_bytes = chunk[:16]

        file_bytes += len(chunk)
        if file_bytes > POLICY.max_file_bytes:
            raise HTTPException(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                detail=f"File exceeds {settings.UPLOAD_MAX_FILE_MB} MB",
            )
        if total_so_far + file_bytes > POLICY.max_total_bytes:
            raise HTTPException(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                detail=f"Upload exceeds {settings.UPLOAD_MAX_TOTAL_MB} MB total",
            )
        destination.write(chunk)

    return file_bytes, first_bytes


def validate_file_signature(path: str, extension: str, first_bytes: bytes) -> None:
    if extension == ".pdf" and not first_bytes.startswith(b"%PDF-"):
        raise HTTPException(status_code=415, detail="Invalid PDF signature")

    if extension == ".docx":
        if not first_bytes.startswith(b"PK"):
            raise HTTPException(status_code=415, detail="Invalid DOCX signature")
        try:
            with zipfile.ZipFile(path) as archive:
                names = set(archive.namelist())
                if "[Content_Types].xml" not in names or "word/document.xml" not in names:
                    raise HTTPException(status_code=415, detail="Invalid DOCX structure")
        except zipfile.BadZipFile as exc:
            raise HTTPException(status_code=415, detail="Invalid DOCX archive") from exc

    if extension == ".txt":
        try:
            decoder = codecs.getincrementaldecoder("utf-8")()
            with open(path, "rb") as source:
                while True:
                    chunk = source.read(settings.UPLOAD_CHUNK_SIZE_BYTES)
                    if not chunk:
                        break
                    if b"\x00" in chunk:
                        raise HTTPException(status_code=415, detail="Invalid text file")
                    decoder.decode(chunk)
                decoder.decode(b"", final=True)
        except UnicodeDecodeError as exc:
            raise HTTPException(status_code=415, detail="Text files must be UTF-8") from exc


def publish_staged_files(
    staging_dir: str,
    filenames: list[str],
    target_dir: str,
) -> None:
    """Move staged files idempotently so an interrupted publish can be retried."""
    for filename in filenames:
        source_path = os.path.join(staging_dir, filename)
        target_path = os.path.join(target_dir, filename)
        if os.path.exists(source_path):
            os.replace(source_path, target_path)
        elif not os.path.exists(target_path):
            raise FileNotFoundError(f"Missing staged document: {filename}")
