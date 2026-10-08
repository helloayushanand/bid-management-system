"""Sequential batch processing with targeted document retry support."""
from __future__ import annotations
import json
from pathlib import Path
from typing import Any, Callable
from adapters import GroqAdapter
from analysis import TenderAnalyzer
from batch.models import BatchDocument, BatchRun, BatchStage, DocumentTokenUsage
from batch.persistence import save_batch_manifest, save_document_payload
from company_context import get_synthetic_company_profile
from extraction import extract_pdf
from models import ExtractionMode

BatchProgressCallback = Callable[[BatchRun, BatchDocument, str], None]

def _notify(callback, batch, document, message):
    if callback: callback(batch, document, message)

def _save_extraction(batch, document, result):
    path = save_document_payload(batch, document.document_id, "extraction.json", result.model_dump(mode="json"))
    document.extraction_result_path = str(path.resolve())

def _save_analysis(batch, document, run):
    payload = {
        "tender_analysis": run.tender_analysis.model_dump(mode="json"),
        "tender_assessment": run.tender_assessment.model_dump(mode="json"),
        "pipeline": {
            "chunk_count": run.chunk_count,
            "input_tokens": run.input_tokens,
            "output_tokens": run.output_tokens,
            "total_tokens": run.total_tokens,
            "request_ids": run.request_ids,
            "model_names": run.model_names,
        },
    }
    path = save_document_payload(batch, document.document_id, "analysis.json", payload)
    document.analysis_result_path = str(path.resolve())
    document.assessment_result_path = str(path.resolve())

def reset_document_for_retry(document: BatchDocument) -> None:
    """Reset computed state while preserving identity and stored PDF."""
    document.stage = BatchStage.UPLOADED
    document.progress_percent = 0
    document.total_pages = 0
    document.native_pages = 0
    document.ocr_pages = 0
    document.review_pages = 0
    document.failed_pages = 0
    document.chunks_total = 0
    document.chunks_completed = 0
    document.recommendation = None
    document.token_usage = DocumentTokenUsage()
    document.errors = []
    document.extraction_result_path = None
    document.analysis_result_path = None
    document.assessment_result_path = None
    document.completed_at_utc = None
    document.metadata = {}
    document.touch()

def process_batch_document(batch: BatchRun, document: BatchDocument, *, extraction_settings: dict[str, Any], adapter: GroqAdapter, progress_callback: BatchProgressCallback | None = None) -> None:
    try:
        document.set_stage(BatchStage.INSPECTING, progress_percent=5); save_batch_manifest(batch); _notify(progress_callback,batch,document,"Extracting PDF text")
        result = extract_pdf(
            file_bytes=Path(document.stored_path).read_bytes(),
            filename=document.original_filename,
            mode=extraction_settings.get("mode", ExtractionMode.AUTOMATIC),
            minimum_native_characters=int(extraction_settings.get("minimum_native_characters",80)),
            ocr_language=str(extraction_settings.get("ocr_language","eng")),
            ocr_dpi=int(extraction_settings.get("ocr_dpi",250)),
            tessdata_path=extraction_settings.get("tessdata_path"),
        )
        document.total_pages=result.page_count; document.native_pages=result.native_page_count; document.ocr_pages=result.ocr_page_count; document.review_pages=result.review_page_count; document.failed_pages=result.failed_page_count
        _save_extraction(batch,document,result)
        if not result.successful:
            document.add_error(stage=BatchStage.INSPECTING,message=result.document_error or "PDF extraction produced no usable text.",error_type="ExtractionError")
            document.set_stage(BatchStage.FAILED,progress_percent=100); save_batch_manifest(batch); _notify(progress_callback,batch,document,"Extraction failed"); return
        document.set_stage(BatchStage.READY_FOR_ANALYSIS,progress_percent=45); save_batch_manifest(batch)
        analyzer=TenderAnalyzer(adapter); document.set_stage(BatchStage.ANALYZING,progress_percent=50)
        def progress(stage,current,total):
            if stage=="Extracting tender chunk":
                document.chunks_total=max(document.chunks_total,total); document.chunks_completed=max(document.chunks_completed,current); document.progress_percent=50+35*(current/max(total,1))
            elif stage in {"Assessing company qualification","Skipping company qualification"}: document.progress_percent=90
            elif stage=="Analysis complete": document.progress_percent=98
            document.touch(); save_batch_manifest(batch); _notify(progress_callback,batch,document,stage)
        run=analyzer.analyze(document=result,company_context=get_synthetic_company_profile(),progress_callback=progress)
        _save_analysis(batch,document,run)
        document.chunks_total=run.chunk_count; document.chunks_completed=run.chunk_count
        document.token_usage=DocumentTokenUsage(input_tokens=run.input_tokens,output_tokens=run.output_tokens,total_tokens=run.total_tokens)
        document.recommendation=run.tender_assessment.recommendation.value
        document.metadata.update({
            "document_type": run.tender_analysis.metadata.get("document_type","unknown"),
            "assessment_skipped": run.tender_assessment.metadata.get("assessment_skipped",False),
            "tender_title": run.tender_analysis.title,
            "reference_number": run.tender_analysis.reference_number,
            "issuing_authority": run.tender_analysis.issuing_authority,
            "submission_deadline": run.tender_analysis.submission_deadline,
            "model_names": run.model_names,
        })
        final=BatchStage.PARTIAL if document.review_pages or document.failed_pages else BatchStage.COMPLETED
        document.set_stage(final,progress_percent=100); save_batch_manifest(batch); _notify(progress_callback,batch,document,"Document complete")
    except Exception as exc:
        document.add_error(stage=document.stage,message=str(exc),error_type=exc.__class__.__name__,retryable=True)
        document.set_stage(BatchStage.FAILED,progress_percent=100); save_batch_manifest(batch); _notify(progress_callback,batch,document,f"Failed: {exc}")

def process_batch_sequentially(batch: BatchRun, *, extraction_settings: dict[str, Any], progress_callback: BatchProgressCallback | None = None, include_duplicates: bool = True) -> BatchRun:
    adapter=GroqAdapter()
    for document in batch.documents:
        if document.is_terminal: continue
        if document.is_duplicate and not include_duplicates:
            document.add_error(stage=BatchStage.UPLOADED,message=f"Duplicate document skipped. Original document ID: {document.duplicate_of_document_id}",error_type="DuplicateDocument",retryable=False)
            document.set_stage(BatchStage.PARTIAL,progress_percent=100); save_batch_manifest(batch); continue
        process_batch_document(batch,document,extraction_settings=extraction_settings,adapter=adapter,progress_callback=progress_callback)
    batch.refresh_status(); save_batch_manifest(batch); return batch

def retry_batch_document(batch: BatchRun, document_id: str, *, extraction_settings: dict[str, Any], progress_callback: BatchProgressCallback | None = None) -> BatchRun:
    document=batch.get_document(document_id)
    if document is None: raise KeyError(f"Unknown batch document: {document_id}")
    reset_document_for_retry(document); save_batch_manifest(batch)
    process_batch_document(batch,document,extraction_settings=extraction_settings,adapter=GroqAdapter(),progress_callback=progress_callback)
    batch.refresh_status(); save_batch_manifest(batch); return batch

def load_document_analysis(document: BatchDocument) -> dict[str, Any] | None:
    if not document.analysis_result_path: return None
    path=Path(document.analysis_result_path)
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None
