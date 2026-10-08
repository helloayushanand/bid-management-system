"""Cleanup helpers for temporary batch data."""

from __future__ import annotations

import shutil
from pathlib import Path

from batch.models import BatchRun


def cleanup_batch_directory(batch: BatchRun) -> bool:
    """Delete the complete working directory for one batch."""

    path = Path(batch.batch_directory)
    if not path.exists():
        return False

    shutil.rmtree(path)
    return True


def cleanup_document_file(batch: BatchRun, document_id: str) -> bool:
    """Delete only the stored uploaded PDF for one batch document."""

    document = batch.get_document(document_id)
    if document is None:
        raise KeyError(f"Unknown batch document: {document_id}")

    path = Path(document.stored_path)
    if not path.exists():
        return False

    path.unlink()
    document.touch()
    return True
