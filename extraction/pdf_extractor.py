"""Document-level PDF text extraction orchestration."""

from __future__ import annotations

from datetime import datetime, timezone
from time import perf_counter

import fitz

from extraction.native_extractor import (
    extract_native_text,
    get_native_page_metadata,
)
from extraction.ocr_extractor import (
    OCRExtractionError,
    extract_text_with_ocr,
)
from extraction.quality_checker import evaluate_text_quality
from models import (
    DocumentExtractionResult,
    ExtractionMethod,
    ExtractionMode,
    PageExtractionResult,
)
from utils.file_utils import calculate_sha256
from utils.text_utils import clean_extracted_text, count_words


class PDFExtractionError(RuntimeError):
    """Raised when a PDF cannot be opened or processed."""


def _normalize_mode(
    mode: ExtractionMode | str,
) -> ExtractionMode:
    """Convert a string or enum into an ExtractionMode value."""

    if isinstance(mode, ExtractionMode):
        return mode

    try:
        return ExtractionMode(mode)

    except ValueError as exc:
        valid_modes = ", ".join(
            item.value for item in ExtractionMode
        )

        raise ValueError(
            f"Invalid extraction mode '{mode}'. "
            f"Valid modes are: {valid_modes}."
        ) from exc


def _build_page_result(
    *,
    page_number: int,
    extraction_method: ExtractionMethod,
    text: str,
    native_character_count: int,
    ocr_attempted: bool,
    quality_score: float,
    needs_review: bool,
    review_reasons: list[str],
    error: str | None,
    metadata: dict[str, object],
) -> PageExtractionResult:
    """Build a validated page extraction result."""

    cleaned_text = clean_extracted_text(text)

    return PageExtractionResult(
        page_number=page_number,
        extraction_method=extraction_method,
        text=cleaned_text,
        character_count=len(cleaned_text),
        word_count=count_words(cleaned_text),
        native_character_count=native_character_count,
        ocr_attempted=ocr_attempted,
        quality_score=quality_score,
        needs_review=needs_review,
        review_reasons=review_reasons,
        error=error,
        metadata=metadata,
    )


def _extract_page(
    page: fitz.Page,
    *,
    page_number: int,
    mode: ExtractionMode,
    minimum_native_characters: int,
    ocr_language: str,
    ocr_dpi: int,
    tessdata_path: str | None,
) -> PageExtractionResult:
    """Extract one page using native extraction and optional OCR."""

    metadata = get_native_page_metadata(page)

    native_text = extract_native_text(page)
    native_character_count = len(native_text)

    native_quality = evaluate_text_quality(
        native_text,
        minimum_characters=minimum_native_characters,
    )

    if mode == ExtractionMode.NATIVE_ONLY:
        if native_text:
            extraction_method = ExtractionMethod.NATIVE
        else:
            extraction_method = ExtractionMethod.EMPTY

        return _build_page_result(
            page_number=page_number,
            extraction_method=extraction_method,
            text=native_text,
            native_character_count=native_character_count,
            ocr_attempted=False,
            quality_score=native_quality.score,
            needs_review=not native_quality.is_usable,
            review_reasons=native_quality.reasons,
            error=None,
            metadata=metadata,
        )

    should_attempt_ocr = (
        mode == ExtractionMode.OCR_ALL
        or native_quality.requires_ocr
    )

    if not should_attempt_ocr:
        return _build_page_result(
            page_number=page_number,
            extraction_method=ExtractionMethod.NATIVE,
            text=native_text,
            native_character_count=native_character_count,
            ocr_attempted=False,
            quality_score=native_quality.score,
            needs_review=native_quality.needs_review,
            review_reasons=native_quality.reasons,
            error=None,
            metadata=metadata,
        )

    try:
        ocr_result = extract_text_with_ocr(
            page,
            language=ocr_language,
            dpi=ocr_dpi,
            full_page=True,
            tessdata_path=tessdata_path,
        )

        ocr_quality = evaluate_text_quality(
            ocr_result.text,
            minimum_characters=minimum_native_characters,
        )

        metadata.update(
            {
                "ocr_language": ocr_result.language,
                "ocr_dpi": ocr_result.dpi,
                "ocr_full_page": ocr_result.full_page,
            }
        )

        if ocr_result.text:
            extraction_method = ExtractionMethod.OCR
            final_text = ocr_result.text
        elif native_text:
            extraction_method = ExtractionMethod.NATIVE
            final_text = native_text
        else:
            extraction_method = ExtractionMethod.EMPTY
            final_text = ""

        if extraction_method == ExtractionMethod.NATIVE:
            final_quality = native_quality
            review_reasons = list(native_quality.reasons)
            review_reasons.append(
                "OCR returned no usable text; native text was retained."
            )
        else:
            final_quality = ocr_quality
            review_reasons = list(ocr_quality.reasons)

        return _build_page_result(
            page_number=page_number,
            extraction_method=extraction_method,
            text=final_text,
            native_character_count=native_character_count,
            ocr_attempted=True,
            quality_score=final_quality.score,
            needs_review=not final_quality.is_usable,
            review_reasons=review_reasons,
            error=None,
            metadata=metadata,
        )

    except OCRExtractionError as exc:
        review_reasons = list(native_quality.reasons)
        review_reasons.append("OCR failed for this page.")

        if native_text:
            extraction_method = ExtractionMethod.NATIVE
            final_text = native_text
        else:
            extraction_method = ExtractionMethod.FAILED
            final_text = ""

        return _build_page_result(
            page_number=page_number,
            extraction_method=extraction_method,
            text=final_text,
            native_character_count=native_character_count,
            ocr_attempted=True,
            quality_score=native_quality.score,
            needs_review=True,
            review_reasons=review_reasons,
            error=str(exc),
            metadata=metadata,
        )


def extract_pdf(
    file_bytes: bytes,
    filename: str,
    *,
    mode: ExtractionMode | str = ExtractionMode.AUTOMATIC,
    minimum_native_characters: int = 80,
    ocr_language: str = "eng",
    ocr_dpi: int = 300,
    tessdata_path: str | None = None,
) -> DocumentExtractionResult:
    """
    Extract text and page metadata from a PDF byte sequence.

    One page failing does not stop processing of the remaining pages.
    """

    if not isinstance(file_bytes, bytes):
        raise TypeError("file_bytes must be a bytes object.")

    if not file_bytes:
        raise ValueError("The uploaded PDF is empty.")

    if not filename or not filename.strip():
        raise ValueError("A PDF filename is required.")

    normalized_mode = _normalize_mode(mode)
    started_at = datetime.now(timezone.utc)
    started_counter = perf_counter()

    try:
        document = fitz.open(
            stream=file_bytes,
            filetype="pdf",
        )

    except Exception as exc:
        raise PDFExtractionError(
            f"The uploaded file could not be opened as a PDF: {exc}"
        ) from exc

    try:
        if document.needs_pass:
            raise PDFExtractionError(
                "The uploaded PDF is password protected."
            )

        if document.page_count == 0:
            raise PDFExtractionError(
                "The uploaded PDF does not contain any pages."
            )

        page_results: list[PageExtractionResult] = []

        for page_index in range(document.page_count):
            page_number = page_index + 1

            try:
                page = document.load_page(page_index)

                page_result = _extract_page(
                    page,
                    page_number=page_number,
                    mode=normalized_mode,
                    minimum_native_characters=minimum_native_characters,
                    ocr_language=ocr_language,
                    ocr_dpi=ocr_dpi,
                    tessdata_path=tessdata_path,
                )

            except Exception as exc:
                page_result = PageExtractionResult(
                    page_number=page_number,
                    extraction_method=ExtractionMethod.FAILED,
                    text="",
                    character_count=0,
                    word_count=0,
                    native_character_count=0,
                    ocr_attempted=False,
                    quality_score=0.0,
                    needs_review=True,
                    review_reasons=[
                        "An unexpected page-processing error occurred."
                    ],
                    error=str(exc),
                    metadata={},
                )

            page_results.append(page_result)

        completed_at = datetime.now(timezone.utc)
        processing_seconds = perf_counter() - started_counter

        return DocumentExtractionResult(
            filename=filename.strip(),
            file_size_bytes=len(file_bytes),
            file_sha256=calculate_sha256(file_bytes),
            requested_mode=normalized_mode,
            page_count=document.page_count,
            pages=page_results,
            started_at_utc=started_at,
            completed_at_utc=completed_at,
            processing_seconds=round(processing_seconds, 4),
            document_error=None,
        )

    finally:
        document.close()