"""Selective, memory-bounded OCR using the local Tesseract engine."""

from __future__ import annotations

import os
from pathlib import Path
from time import perf_counter

from PIL import Image
import pytesseract
from pytesseract import TesseractNotFoundError

try:
    import pymupdf
except ImportError:
    import fitz as pymupdf

from extraction.inspection_models import OCRDocumentResult, OCRPageResult


def configure_tesseract(
    *,
    tesseract_command: str | None = None,
    tessdata_path: str | None = None,
) -> str:
    """Configure and verify the local Tesseract executable."""

    configured_command = (
        tesseract_command
        or os.environ.get("TESSERACT_CMD")
        or r"C:\Program Files\Tesseract-OCR\tesseract.exe"
    )

    command_path = Path(configured_command)
    if not command_path.is_file():
        raise TesseractNotFoundError(
            "Tesseract executable was not found. Set TESSERACT_CMD in .env "
            "to the full path of tesseract.exe. Current value: "
            f"{configured_command}"
        )

    pytesseract.pytesseract.tesseract_cmd = str(command_path)

    configured_tessdata = (
        tessdata_path
        or os.environ.get("TESSDATA_PREFIX")
        or str(command_path.parent / "tessdata")
    )
    tessdata_directory = Path(configured_tessdata)
    if tessdata_directory.is_dir():
        os.environ["TESSDATA_PREFIX"] = str(tessdata_directory)

    try:
        version = pytesseract.get_tesseract_version()
    except Exception as exc:
        raise RuntimeError(
            "Tesseract was found but could not be started: "
            f"{exc}"
        ) from exc

    return str(version)


def _quality(text: str) -> float:
    if not text:
        return 0.0
    printable = sum(character.isprintable() for character in text) / len(text)
    useful = sum(character.isalnum() for character in text) / len(text)
    return round(min(1.0, (printable * 0.55) + (useful * 0.45)), 3)


def ocr_selected_pages(
    source_path: str | Path,
    page_numbers: list[int],
    *,
    filename: str | None = None,
    language: str = "eng",
    dpi: int = 250,
    tessdata_path: str | None = None,
    tesseract_command: str | None = None,
    minimum_ocr_characters: int = 20,
    page_timeout_seconds: int = 120,
) -> OCRDocumentResult:
    """OCR only requested pages, releasing each rendered image immediately."""

    started = perf_counter()
    path = Path(source_path)
    requested_pages = sorted(set(page_numbers))
    page_results: list[OCRPageResult] = []

    try:
        tesseract_version = configure_tesseract(
            tesseract_command=tesseract_command,
            tessdata_path=tessdata_path,
        )
    except Exception as exc:
        error_message = f"OCR engine configuration failed: {exc}"
        return OCRDocumentResult(
            filename=filename or path.name,
            source_path=str(path.resolve()),
            requested_page_numbers=requested_pages,
            pages=[
                OCRPageResult(
                    page_number=page_number,
                    successful=False,
                    needs_review=True,
                    review_reasons=[error_message],
                    error=error_message,
                )
                for page_number in requested_pages
            ],
            processing_seconds=round(perf_counter() - started, 3),
        )

    with pymupdf.open(str(path)) as document:
        for page_number in requested_pages:
            pixmap = None
            image = None
            try:
                if page_number < 1 or page_number > document.page_count:
                    raise ValueError(
                        f"Page {page_number} is outside the PDF page range."
                    )

                page = document.load_page(page_number - 1)
                scale = dpi / 72.0
                pixmap = page.get_pixmap(
                    matrix=pymupdf.Matrix(scale, scale),
                    alpha=False,
                    colorspace=pymupdf.csRGB,
                )
                image = Image.frombytes(
                    "RGB",
                    (pixmap.width, pixmap.height),
                    pixmap.samples,
                )

                text = pytesseract.image_to_string(
                    image,
                    lang=language,
                    config="--oem 3 --psm 6",
                    timeout=page_timeout_seconds,
                ).strip()

                character_count = len(text)
                successful = character_count >= minimum_ocr_characters
                review_reasons = []
                if not successful:
                    review_reasons.append(
                        "Tesseract ran successfully but produced only "
                        f"{character_count} characters."
                    )

                page_results.append(
                    OCRPageResult(
                        page_number=page_number,
                        text=text,
                        character_count=character_count,
                        word_count=len(text.split()),
                        quality_score=_quality(text),
                        successful=successful,
                        needs_review=not successful,
                        review_reasons=review_reasons,
                        error=None,
                    )
                )

            except RuntimeError as exc:
                message = (
                    f"OCR timed out or Tesseract failed on page {page_number}: "
                    f"{exc}"
                )
                page_results.append(
                    OCRPageResult(
                        page_number=page_number,
                        successful=False,
                        needs_review=True,
                        review_reasons=[message],
                        error=message,
                    )
                )
            except Exception as exc:
                message = f"OCR failed on page {page_number}: {exc}"
                page_results.append(
                    OCRPageResult(
                        page_number=page_number,
                        successful=False,
                        needs_review=True,
                        review_reasons=[message],
                        error=message,
                    )
                )
            finally:
                if image is not None:
                    image.close()
                del image
                del pixmap

    return OCRDocumentResult(
        filename=filename or path.name,
        source_path=str(path.resolve()),
        requested_page_numbers=requested_pages,
        pages=page_results,
        processing_seconds=round(perf_counter() - started, 3),
    )
