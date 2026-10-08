"""Create a bounded batch manifest from uploaded PDF files."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any, Protocol, Sequence
from uuid import uuid4

from batch.models import (
    BatchDocument,
    BatchRun,
    BatchStage,
    BatchStatus,
)
from batch.persistence import save_batch_manifest
from batch.settings import BatchSettings


class UploadedFileLike(Protocol):
    name: str
    type: str
    size: int

    def getvalue(self) -> bytes:
        ...


class BatchValidationError(ValueError):
    """Raised when uploaded files cannot form a valid batch."""


_INVALID_FILENAME = re.compile(r'[^A-Za-z0-9._-]+')


def _safe_filename(filename: str) -> str:
    name = Path(filename).name.strip()
    safe = _INVALID_FILENAME.sub("_", name).strip("._")
    if not safe:
        safe = "document.pdf"
    if not safe.lower().endswith(".pdf"):
        safe = f"{safe}.pdf"
    return safe


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _file_bytes(uploaded_file: UploadedFileLike) -> bytes:
    content = uploaded_file.getvalue()
    if not isinstance(content, bytes):
        raise BatchValidationError(
            f"File '{uploaded_file.name}' did not return binary content."
        )
    return content


def create_batch(
    uploaded_files: Sequence[UploadedFileLike],
    *,
    settings: BatchSettings | None = None,
    batch_metadata: dict[str, Any] | None = None,
) -> BatchRun:
    """Validate uploads, save PDFs, mark duplicates, and persist a manifest."""

    active = settings or BatchSettings.from_environment()

    if not uploaded_files:
        raise BatchValidationError("Select at least one PDF.")
    if len(uploaded_files) > active.maximum_documents:
        raise BatchValidationError(
            f"A batch can contain at most {active.maximum_documents} PDFs."
        )

    batch_id = f"batch-{uuid4().hex[:12]}"
    batch_directory = active.working_root / batch_id
    uploads_directory = batch_directory / "uploads"
    uploads_directory.mkdir(parents=True, exist_ok=False)

    batch = BatchRun(
        batch_id=batch_id,
        batch_directory=str(batch_directory.resolve()),
        status=BatchStatus.CREATED,
        maximum_documents=active.maximum_documents,
        metadata=batch_metadata or {},
    )

    seen_hashes: dict[str, str] = {}
    maximum_bytes = active.maximum_file_size_mb * 1024 * 1024

    try:
        for uploaded_file in uploaded_files:
            original_name = Path(uploaded_file.name).name
            if not original_name.lower().endswith(".pdf"):
                raise BatchValidationError(
                    f"Only PDF files are accepted: {original_name}"
                )

            content = _file_bytes(uploaded_file)
            if not content:
                raise BatchValidationError(
                    f"Uploaded PDF is empty: {original_name}"
                )
            if len(content) > maximum_bytes:
                raise BatchValidationError(
                    f"'{original_name}' exceeds the "
                    f"{active.maximum_file_size_mb} MB limit."
                )
            if not content.startswith(b"%PDF"):
                raise BatchValidationError(
                    f"'{original_name}' does not have a valid PDF signature."
                )

            document_id = f"doc-{uuid4().hex[:10]}"
            digest = _sha256(content)
            safe_name = _safe_filename(original_name)
            stored_filename = f"{document_id}-{safe_name}"
            stored_path = uploads_directory / stored_filename
            stored_path.write_bytes(content)

            duplicate_of = seen_hashes.get(digest)
            if duplicate_of is None:
                seen_hashes[digest] = document_id

            document = BatchDocument(
                document_id=document_id,
                batch_id=batch_id,
                original_filename=original_name,
                stored_filename=stored_filename,
                stored_path=str(stored_path.resolve()),
                file_size_bytes=len(content),
                file_sha256=digest,
                mime_type=getattr(
                    uploaded_file,
                    "type",
                    "application/pdf",
                ) or "application/pdf",
                stage=BatchStage.UPLOADED,
                duplicate_of_document_id=duplicate_of,
                progress_percent=0.0,
            )
            batch.documents.append(document)

        batch.status = BatchStatus.READY
        batch.touch()
        save_batch_manifest(batch)
        return batch

    except Exception:
        if batch_directory.exists():
            import shutil
            shutil.rmtree(batch_directory, ignore_errors=True)
        raise


def batch_summary_rows(batch: BatchRun) -> list[dict[str, Any]]:
    """Return table-ready rows for the batch dashboard."""

    return [
        {
            "Document ID": document.document_id,
            "File Name": document.original_filename,
            "Size (MB)": round(
                document.file_size_bytes / (1024 * 1024), 2
            ),
            "Stage": document.stage.value,
            "Progress": document.progress_percent,
            "Duplicate": document.is_duplicate,
            "Duplicate Of": document.duplicate_of_document_id or "",
            "Pages": document.total_pages,
            "Native Pages": document.native_pages,
            "OCR Pages": document.ocr_pages,
            "Review Pages": document.review_pages,
            "Recommendation": document.recommendation or "",
            "Errors": len(document.errors),
        }
        for document in batch.documents
    ]
