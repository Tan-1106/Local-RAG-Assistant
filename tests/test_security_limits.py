import io
import os
import sys
import zipfile

import pytest
from fastapi import HTTPException, UploadFile

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend")))

from app.services import upload_validation
from app.services.rate_limit import RateLimit, RateLimiter
from app.services.upload_validation import (
    UploadPolicy,
    publish_staged_files,
    stream_upload,
    validate_file_signature,
    validate_upload_metadata,
)


class FakeRateRedis:
    def __init__(self, result):
        self.result = result

    def eval(self, *_args):
        return self.result


def test_rate_limiter_returns_429_with_retry_after():
    limiter = RateLimiter(FakeRateRedis([6, 42]))

    with pytest.raises(HTTPException) as exc:
        limiter.enforce("login:ip", "127.0.0.1", RateLimit(5, 60))

    assert exc.value.status_code == 429
    assert exc.value.headers["Retry-After"] == "42"


def test_upload_rejects_unsupported_extension():
    upload = UploadFile(filename="payload.exe", file=io.BytesIO(b"MZ"))

    with pytest.raises(HTTPException) as exc:
        validate_upload_metadata(upload)

    assert exc.value.status_code == 415


def test_upload_stream_stops_when_file_limit_is_exceeded(monkeypatch):
    monkeypatch.setattr(
        upload_validation,
        "POLICY",
        UploadPolicy(max_files=1, max_file_bytes=4, max_total_bytes=8),
    )
    upload = UploadFile(filename="large.txt", file=io.BytesIO(b"12345"))

    with pytest.raises(HTTPException) as exc:
        stream_upload(upload, io.BytesIO(), total_so_far=0)

    assert exc.value.status_code == 413


def test_docx_structure_validation(tmp_path):
    docx_path = tmp_path / "valid.docx"
    with zipfile.ZipFile(docx_path, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types />")
        archive.writestr("word/document.xml", "<document />")

    validate_file_signature(
        str(docx_path),
        ".docx",
        docx_path.read_bytes()[:16],
    )


def test_staged_file_publish_is_idempotent_after_partial_move(tmp_path):
    staging = tmp_path / "staging"
    target = tmp_path / "target"
    staging.mkdir()
    target.mkdir()
    (target / "already.txt").write_text("published", encoding="utf-8")
    (staging / "pending.txt").write_text("pending", encoding="utf-8")

    publish_staged_files(
        str(staging),
        ["already.txt", "pending.txt"],
        str(target),
    )

    assert (target / "already.txt").read_text(encoding="utf-8") == "published"
    assert (target / "pending.txt").read_text(encoding="utf-8") == "pending"
