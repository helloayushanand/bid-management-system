"""Process-safe native PDF inspection worker."""
from __future__ import annotations
from typing import Any
from extraction.native_extractor import inspect_pdf_path


def run_native_inspection_job(job: dict[str, Any]) -> dict[str, Any]:
    """Inspect one PDF in a child process and return serializable data."""
    document_id = str(job["document_id"])
    try:
        result = inspect_pdf_path(
            job["source_path"],
            filename=job["filename"],
            minimum_native_characters=int(
                job.get("minimum_native_characters", 80)
            ),
        )
        return {
            "document_id": document_id,
            "inspection": result.model_dump(mode="json"),
            "error": None,
        }
    except Exception as exc:
        return {
            "document_id": document_id,
            "inspection": None,
            "error": f"{exc.__class__.__name__}: {exc}",
        }
