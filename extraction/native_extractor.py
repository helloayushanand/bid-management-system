"""Native extraction and first-pass PDF inspection. This module never invokes OCR."""
from __future__ import annotations
import hashlib
import re
from pathlib import Path
from time import perf_counter
try:
    import pymupdf
except ImportError:
    import fitz as pymupdf
from extraction.inspection_models import DocumentInspectionResult, PageInspectionResult, PageInspectionStatus

_PRINTABLE_RE = re.compile(r"[A-Za-z0-9]")

def _clean(text: str) -> str:
    return "\n".join(line.rstrip() for line in text.replace("\x00", "").splitlines()).strip()

def _quality(text: str) -> float:
    if not text: return 0.0
    printable=sum(ch.isprintable() for ch in text)/len(text)
    useful=sum(ch.isalnum() for ch in text)/len(text)
    return round(min(1.0,(printable*0.55)+(useful*0.45)),3)

def inspect_pdf_path(source_path: str | Path, *, filename: str | None = None, minimum_native_characters: int = 80) -> DocumentInspectionResult:
    start=perf_counter(); path=Path(source_path); content=path.read_bytes(); digest=hashlib.sha256(content).hexdigest(); pages=[]
    try:
        with pymupdf.open(str(path)) as document:
            page_count=document.page_count
            for index in range(page_count):
                page_number=index+1
                try:
                    page=document.load_page(index); text=_clean(page.get_text("text") or ""); chars=len(text); words=len(text.split()); score=_quality(text)
                    if chars >= minimum_native_characters and _PRINTABLE_RE.search(text):
                        status=PageInspectionStatus.NATIVE_OK; review=False; reasons=[]
                    elif chars == 0:
                        status=PageInspectionStatus.OCR_REQUIRED; review=True; reasons=["No native text was extracted; OCR is required."]
                    else:
                        status=PageInspectionStatus.OCR_REQUIRED; review=True; reasons=[f"Native text contains only {chars} characters; OCR threshold is {minimum_native_characters}."]
                    pages.append(PageInspectionResult(page_number=page_number,status=status,native_text=text,native_character_count=chars,native_word_count=words,quality_score=score,needs_review=review,review_reasons=reasons))
                except Exception as exc:
                    pages.append(PageInspectionResult(page_number=page_number,status=PageInspectionStatus.FAILED,needs_review=True,review_reasons=["Native page inspection failed."],error=str(exc)))
            return DocumentInspectionResult(filename=filename or path.name,source_path=str(path.resolve()),file_size_bytes=len(content),file_sha256=digest,page_count=page_count,pages=pages,processing_seconds=round(perf_counter()-start,3))
    except Exception as exc:
        return DocumentInspectionResult(filename=filename or path.name,source_path=str(path.resolve()),file_size_bytes=len(content),file_sha256=digest,page_count=0,pages=[],document_error=str(exc),processing_seconds=round(perf_counter()-start,3))
