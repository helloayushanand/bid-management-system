"""File conversion, download naming, and hashing utilities."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import BinaryIO

from models import DocumentExtractionResult


_INVALID_FILENAME_CHARACTERS = re.compile(r'[<>:"/\\|?*\x00-\x1F]')


def calculate_sha256(file_bytes: bytes) -> str:
    """Return the SHA-256 hash of a byte sequence."""

    return hashlib.sha256(file_bytes).hexdigest()


def read_binary_file(file_object: BinaryIO) -> bytes:
    """
    Read an uploaded or local binary file from its beginning.

    The original file position is restored when the object supports seek.
    """

    original_position: int | None = None

    try:
        if hasattr(file_object, "tell"):
            original_position = file_object.tell()

        if hasattr(file_object, "seek"):
            file_object.seek(0)

        content = file_object.read()

        if not isinstance(content, bytes):
            raise TypeError(
                "The uploaded file did not return binary content."
            )

        return content

    finally:
        if (
            original_position is not None
            and hasattr(file_object, "seek")
        ):
            file_object.seek(original_position)


def sanitize_filename(filename: str) -> str:
    """Return a filename safe for local output and downloads."""

    filename = Path(filename).name.strip()
    filename = _INVALID_FILENAME_CHARACTERS.sub("_", filename)
    filename = filename.rstrip(". ")

    return filename or "document.pdf"


def output_stem(filename: str) -> str:
    """Return the sanitized filename without its final extension."""

    safe_filename = sanitize_filename(filename)
    stem = Path(safe_filename).stem.strip()

    return stem or "document"


def result_to_json_bytes(
    result: DocumentExtractionResult,
    indent: int = 2,
) -> bytes:
    """Serialize an extraction result as UTF-8 JSON bytes."""

    data = result.model_dump(mode="json")

    json_text = json.dumps(
        data,
        ensure_ascii=False,
        indent=indent,
    )

    return json_text.encode("utf-8")


def result_to_text(
    result: DocumentExtractionResult,
) -> str:
    """Convert an extraction result into a readable text document."""

    separator = "=" * 80

    sections: list[str] = [
        separator,
        "PDF EXTRACTION REPORT",
        separator,
        f"Filename: {result.filename}",
        f"File size: {result.file_size_bytes} bytes",
        f"SHA-256: {result.file_sha256}",
        f"Requested mode: {result.requested_mode}",
        f"Total pages: {result.page_count}",
        f"Native pages: {result.native_page_count}",
        f"OCR pages: {result.ocr_page_count}",
        f"Empty pages: {result.empty_page_count}",
        f"Failed pages: {result.failed_page_count}",
        f"Pages requiring review: {result.review_page_count}",
        f"Total characters: {result.total_characters}",
        f"Total words: {result.total_words}",
    ]

    if result.processing_seconds is not None:
        sections.append(
            f"Processing time: {result.processing_seconds:.2f} seconds"
        )

    if result.document_error:
        sections.extend(
            [
                "",
                f"Document error: {result.document_error}",
            ]
        )

    for page in result.pages:
        sections.extend(
            [
                "",
                separator,
                f"PAGE {page.page_number}",
                separator,
                f"Extraction method: {page.extraction_method}",
                f"Character count: {page.character_count}",
                f"Word count: {page.word_count}",
                f"Quality score: {page.quality_score:.2f}",
                (
                    "OCR attempted: "
                    f"{'Yes' if page.ocr_attempted else 'No'}"
                ),
                (
                    "Needs review: "
                    f"{'Yes' if page.needs_review else 'No'}"
                ),
            ]
        )

        if page.review_reasons:
            sections.append(
                "Review reasons: "
                + "; ".join(page.review_reasons)
            )

        if page.error:
            sections.append(f"Error: {page.error}")

        sections.extend(
            [
                "",
                page.text or "[No text extracted]",
            ]
        )

    return "\n".join(sections).strip() + "\n"


def result_to_text_bytes(
    result: DocumentExtractionResult,
) -> bytes:
    """Convert an extraction result into UTF-8 text bytes."""

    return result_to_text(result).encode("utf-8")


def build_download_filename(
    original_filename: str,
    extension: str,
) -> str:
    """Build a download filename using the original PDF name."""

    normalized_extension = extension.lower().lstrip(".")

    if not normalized_extension:
        raise ValueError("A download extension is required.")

    return (
        f"{output_stem(original_filename)}"
        f"_extracted.{normalized_extension}"
    )
