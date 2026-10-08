"""Process-safe selective OCR worker."""
from __future__ import annotations
from typing import Any
from extraction.ocr_extractor import ocr_selected_pages


def run_ocr_job(job: dict[str, Any]) -> dict[str, Any]:
    """OCR selected pages of one PDF in a child process."""
    document_id = str(job["document_id"])
    try:
        result = ocr_selected_pages(
            job["source_path"],
            list(job["page_numbers"]),
            filename=job["filename"],
            language=str(job.get("language", "eng")),
            dpi=int(job.get("dpi", 250)),
            tessdata_path=job.get("tessdata_path"),
            tesseract_command=job.get("tesseract_command"),
            minimum_ocr_characters=int(
                job.get("minimum_ocr_characters", 20)
            ),
            page_timeout_seconds=int(
                job.get("page_timeout_seconds", 120)
            ),
        )
        return {
            "document_id": document_id,
            "ocr": result.model_dump(mode="json"),
            "error": None,
        }
    except Exception as exc:
        return {
            "document_id": document_id,
            "ocr": None,
            "error": f"{exc.__class__.__name__}: {exc}",
        }
