"""OCR extraction from PDF pages using PyMuPDF and Tesseract."""

from __future__ import annotations

import os
from dataclasses import dataclass

import fitz

from utils.text_utils import clean_extracted_text


class OCRExtractionError(RuntimeError):
    """Raised when OCR cannot process a PDF page."""


@dataclass(frozen=True)
class OCRResult:
    """Text and metadata returned by a page-level OCR operation."""

    text: str
    language: str
    dpi: int
    full_page: bool


def configure_tessdata(tessdata_path: str | None = None) -> str | None:
    """
    Configure the Tesseract language-data directory.

    The supplied directory should contain files such as eng.traineddata.
    """

    if not tessdata_path:
        return os.environ.get("TESSDATA_PREFIX")

    normalized_path = os.path.abspath(
        os.path.expanduser(tessdata_path)
    )

    if not os.path.isdir(normalized_path):
        raise FileNotFoundError(
            f"Tesseract data directory was not found: {normalized_path}"
        )

    os.environ["TESSDATA_PREFIX"] = normalized_path

    return normalized_path


def extract_text_with_ocr(
    page: fitz.Page,
    *,
    language: str = "eng",
    dpi: int = 300,
    full_page: bool = True,
    tessdata_path: str | None = None,
) -> OCRResult:
    """
    Run Tesseract OCR on one PDF page through PyMuPDF.

    The returned text is cleaned but page coordinates are not currently
    included in the application result.
    """

    if page is None:
        raise ValueError("A valid PyMuPDF page is required.")

    if dpi < 72:
        raise ValueError("OCR DPI must be at least 72.")

    configure_tessdata(tessdata_path)

    try:
        text_page = page.get_textpage_ocr(
            language=language,
            dpi=dpi,
            full=full_page,
        )

        extracted_text = page.get_text(
            "text",
            textpage=text_page,
            sort=True,
        )

    except Exception as exc:
        message = str(exc).strip() or exc.__class__.__name__

        raise OCRExtractionError(
            "OCR failed. Confirm that Tesseract OCR is installed and "
            "that TESSDATA_PREFIX points to the folder containing "
            f"the requested language data. Original error: {message}"
        ) from exc

    return OCRResult(
        text=clean_extracted_text(extracted_text),
        language=language,
        dpi=dpi,
        full_page=full_page,
    )