"""Two-pass PDF extraction built from native inspection and selective OCR."""
from __future__ import annotations
from pathlib import Path
from models import DocumentExtractionResult, ExtractionMethod, ExtractionMode, PageExtractionResult
from extraction.inspection_models import DocumentInspectionResult, OCRDocumentResult, PageInspectionStatus
from extraction.native_extractor import inspect_pdf_path
from extraction.ocr_extractor import ocr_selected_pages

class PDFExtractionError(RuntimeError):
    """Raised when a PDF cannot be converted into an extraction result."""

def build_extraction_result(inspection: DocumentInspectionResult, ocr: OCRDocumentResult | None, *, requested_mode: ExtractionMode = ExtractionMode.AUTOMATIC) -> DocumentExtractionResult:
    ocr_by_page={page.page_number:page for page in (ocr.pages if ocr else [])}
    pages=[]
    for inspected in inspection.pages:
        ocr_page=ocr_by_page.get(inspected.page_number)
        if inspected.status==PageInspectionStatus.NATIVE_OK:
            method=ExtractionMethod.NATIVE; text=inspected.native_text; chars=inspected.native_character_count; words=inspected.native_word_count; quality=inspected.quality_score; attempted=False; review=inspected.needs_review; reasons=inspected.review_reasons; error=inspected.error
        elif inspected.status==PageInspectionStatus.OCR_REQUIRED and ocr_page and ocr_page.successful:
            method=ExtractionMethod.OCR; text=ocr_page.text; chars=ocr_page.character_count; words=ocr_page.word_count; quality=ocr_page.quality_score; attempted=True; review=ocr_page.needs_review; reasons=ocr_page.review_reasons; error=ocr_page.error
        elif inspected.status==PageInspectionStatus.FAILED:
            method=ExtractionMethod.FAILED; text=inspected.native_text; chars=inspected.native_character_count; words=inspected.native_word_count; quality=inspected.quality_score; attempted=False; review=True; reasons=inspected.review_reasons; error=inspected.error
        else:
            text=inspected.native_text; chars=len(text); words=len(text.split()); quality=inspected.quality_score; attempted=ocr_page is not None; review=True; reasons=list(inspected.review_reasons); error=inspected.error
            if ocr_page:
                reasons.extend(ocr_page.review_reasons); error=ocr_page.error or error
            method=ExtractionMethod.NATIVE if text else ExtractionMethod.EMPTY
        pages.append(PageExtractionResult(page_number=inspected.page_number,extraction_method=method,text=text,character_count=chars,word_count=words,native_character_count=inspected.native_character_count,ocr_attempted=attempted,needs_review=review,quality_score=quality,review_reasons=list(dict.fromkeys(reasons)),error=error,metadata={"inspection_status":inspected.status.value,"ocr_failed":bool(ocr_page and not ocr_page.successful)}))
    return DocumentExtractionResult(filename=inspection.filename,file_size_bytes=inspection.file_size_bytes,file_sha256=inspection.file_sha256,requested_mode=requested_mode,page_count=inspection.page_count,pages=pages,document_error=inspection.document_error,processing_seconds=(inspection.processing_seconds or 0)+(ocr.processing_seconds or 0 if ocr else 0))

def extract_pdf_path(source_path: str | Path, *, filename: str | None = None, mode: ExtractionMode = ExtractionMode.AUTOMATIC, minimum_native_characters: int = 80, ocr_language: str = "eng", ocr_dpi: int = 250, tessdata_path: str | None = None) -> DocumentExtractionResult:
    """Inspect native text, OCR selected pages, and return the shared result."""
    inspection=inspect_pdf_path(source_path,filename=filename,minimum_native_characters=minimum_native_characters)
    if inspection.document_error or not inspection.pages:
        raise PDFExtractionError(inspection.document_error or "PDF inspection produced no pages.")
    if mode==ExtractionMode.OCR_ALL:
        page_numbers=list(range(1,inspection.page_count+1))
    elif mode==ExtractionMode.NATIVE_ONLY:
        page_numbers=[]
    else:
        page_numbers=inspection.ocr_page_numbers
    ocr_result=ocr_selected_pages(source_path,page_numbers,filename=filename or Path(source_path).name,language=ocr_language,dpi=ocr_dpi,tessdata_path=tessdata_path) if page_numbers else None
    return build_extraction_result(inspection,ocr_result,requested_mode=mode)

def extract_pdf(*, file_bytes: bytes, filename: str, mode: ExtractionMode = ExtractionMode.AUTOMATIC, minimum_native_characters: int = 80, ocr_language: str = "eng", ocr_dpi: int = 250, tessdata_path: str | None = None) -> DocumentExtractionResult:
    """Compatibility wrapper for callers that provide PDF bytes."""
    from tempfile import NamedTemporaryFile
    suffix=Path(filename).suffix or ".pdf"
    with NamedTemporaryFile(suffix=suffix,delete=False) as temporary:
        temporary.write(file_bytes); path=Path(temporary.name)
    try:
        return extract_pdf_path(path,filename=filename,mode=mode,minimum_native_characters=minimum_native_characters,ocr_language=ocr_language,ocr_dpi=ocr_dpi,tessdata_path=tessdata_path)
    finally:
        path.unlink(missing_ok=True)
