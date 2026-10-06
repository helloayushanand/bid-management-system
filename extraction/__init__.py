"""PDF extraction package for the bid management portal."""

from extraction.native_extractor import (
    extract_native_text,
    get_native_page_metadata,
)
from extraction.ocr_extractor import (
    OCRExtractionError,
    OCRResult,
    configure_tessdata,
    extract_text_with_ocr,
)
from extraction.pdf_extractor import (
    PDFExtractionError,
    extract_pdf,
)
from extraction.quality_checker import (
    TextQualityResult,
    evaluate_text_quality,
    should_run_ocr,
)

__all__ = [
    "OCRExtractionError",
    "OCRResult",
    "PDFExtractionError",
    "TextQualityResult",
    "configure_tessdata",
    "evaluate_text_quality",
    "extract_native_text",
    "extract_pdf",
    "extract_text_with_ocr",
    "get_native_page_metadata",
    "should_run_ocr",
]