"""Native text extraction from PDF pages."""

from __future__ import annotations

import fitz

from utils.text_utils import clean_extracted_text


def extract_native_text(
    page: fitz.Page,
    *,
    sort: bool = True,
) -> str:
    """
    Extract embedded text from a PDF page.

    This function does not perform OCR. It extracts only text already
    contained in the PDF's text layer.
    """

    if page is None:
        raise ValueError("A valid PyMuPDF page is required.")

    extracted_text = page.get_text(
        "text",
        sort=sort,
    )

    return clean_extracted_text(extracted_text)


def get_native_page_metadata(
    page: fitz.Page,
) -> dict[str, object]:
    """Return basic metadata describing a PDF page."""

    if page is None:
        raise ValueError("A valid PyMuPDF page is required.")

    page_rect = page.rect
    image_count = len(page.get_images(full=True))
    native_words = page.get_text("words")

    return {
        "width": round(float(page_rect.width), 2),
        "height": round(float(page_rect.height), 2),
        "rotation": int(page.rotation),
        "image_count": image_count,
        "native_word_count": len(native_words),
    }