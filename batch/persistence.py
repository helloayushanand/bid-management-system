"""JSON persistence helpers for batch manifests and stage outputs."""

from __future__ import annotations

import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

from batch.models import BatchRun


MANIFEST_FILENAME = "batch-manifest.json"


def save_json_atomic(path: str | Path, payload: Any) -> Path:
    """Write JSON atomically by replacing the target after a full write."""

    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)

    with NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=target.parent,
        prefix=f".{target.stem}-",
        suffix=".tmp",
        delete=False,
    ) as temporary:
        json.dump(payload, temporary, ensure_ascii=False, indent=2)
        temporary.flush()
        os.fsync(temporary.fileno())
        temporary_path = Path(temporary.name)

    temporary_path.replace(target)
    return target


def save_batch_manifest(batch: BatchRun) -> Path:
    """Persist one complete batch manifest."""

    batch.refresh_status()
    path = Path(batch.batch_directory) / MANIFEST_FILENAME
    return save_json_atomic(
        path,
        batch.model_dump(mode="json"),
    )


def load_batch_manifest(path: str | Path) -> BatchRun:
    """Load and validate a saved batch manifest."""

    manifest_path = Path(path)
    if manifest_path.is_dir():
        manifest_path = manifest_path / MANIFEST_FILENAME

    with manifest_path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)

    return BatchRun.model_validate(payload)


def save_document_payload(
    batch: BatchRun,
    document_id: str,
    filename: str,
    payload: Any,
) -> Path:
    """Save one document stage result inside its batch directory."""

    document = batch.get_document(document_id)
    if document is None:
        raise KeyError(f"Unknown batch document: {document_id}")

    output_dir = (
        Path(batch.batch_directory)
        / "results"
        / document_id
    )
    return save_json_atomic(output_dir / filename, payload)
