"""Sequential two-pass batch runner: inspect, selective OCR, analyze."""
from __future__ import annotations
import json
from pathlib import Path
from typing import Any, Callable
from adapters import GroqAdapter
from analysis import TenderAnalyzer
from batch.models import BatchDocument, BatchRun, BatchStage, DocumentTokenUsage
from batch.persistence import save_batch_manifest, save_document_payload
from company_context import get_synthetic_company_profile
from extraction import build_extraction_result, inspect_pdf_path, ocr_selected_pages
from models import ExtractionMode
BatchProgressCallback=Callable[[BatchRun,BatchDocument,str],None]

def _notify(cb,batch,doc,msg):
    if cb: cb(batch,doc,msg)

def _save(batch,doc,name,payload):
    return save_document_payload(batch,doc.document_id,name,payload)

def reset_document_for_retry(doc: BatchDocument):
    doc.stage=BatchStage.UPLOADED; doc.progress_percent=0; doc.total_pages=0; doc.native_pages=0; doc.ocr_pages=0; doc.review_pages=0; doc.failed_pages=0; doc.chunks_total=0; doc.chunks_completed=0; doc.recommendation=None; doc.token_usage=DocumentTokenUsage(); doc.errors=[]; doc.extraction_result_path=None; doc.analysis_result_path=None; doc.assessment_result_path=None; doc.completed_at_utc=None; doc.metadata={}; doc.touch()

def process_batch_document(batch: BatchRun, doc: BatchDocument, *, extraction_settings: dict[str,Any], adapter: GroqAdapter, progress_callback: BatchProgressCallback|None=None):
    try:
        doc.set_stage(BatchStage.INSPECTING,progress_percent=5); save_batch_manifest(batch); _notify(progress_callback,batch,doc,"Inspecting native PDF text")
        inspection=inspect_pdf_path(doc.stored_path,filename=doc.original_filename,minimum_native_characters=int(extraction_settings.get("minimum_native_characters",80)))
        p=_save(batch,doc,"inspection.json",inspection.model_dump(mode="json")); doc.metadata["inspection_result_path"]=str(p.resolve()); doc.total_pages=inspection.page_count; doc.native_pages=inspection.native_page_count; doc.failed_pages=inspection.failed_page_count; doc.metadata["ocr_required_pages"]=inspection.ocr_required_page_count; doc.metadata["empty_pages"]=inspection.empty_page_count
        if inspection.document_error or not inspection.pages: raise RuntimeError(inspection.document_error or "Native inspection produced no pages.")
        mode=extraction_settings.get("mode",ExtractionMode.AUTOMATIC)
        if mode==ExtractionMode.OCR_ALL: ocr_numbers=list(range(1,inspection.page_count+1))
        elif mode==ExtractionMode.NATIVE_ONLY: ocr_numbers=[]
        else: ocr_numbers=inspection.ocr_page_numbers
        ocr_result=None
        if ocr_numbers:
            doc.set_stage(BatchStage.OCR_PENDING,progress_percent=20); save_batch_manifest(batch); _notify(progress_callback,batch,doc,f"OCR required for {len(ocr_numbers)} page(s)")
            doc.set_stage(BatchStage.OCR_RUNNING,progress_percent=25); save_batch_manifest(batch)
            ocr_result=ocr_selected_pages(doc.stored_path,ocr_numbers,filename=doc.original_filename,language=str(extraction_settings.get("ocr_language","eng")),dpi=int(extraction_settings.get("ocr_dpi",250)),tessdata_path=extraction_settings.get("tessdata_path"))
            p=_save(batch,doc,"ocr.json",ocr_result.model_dump(mode="json")); doc.metadata["ocr_result_path"]=str(p.resolve()); doc.ocr_pages=ocr_result.successful_page_count; doc.metadata["ocr_failed_pages"]=ocr_result.failed_page_count
        extraction=build_extraction_result(inspection,ocr_result,requested_mode=mode)
        p=_save(batch,doc,"extraction.json",extraction.model_dump(mode="json")); doc.extraction_result_path=str(p.resolve()); doc.review_pages=extraction.review_page_count; doc.failed_pages=extraction.failed_page_count
        if not extraction.successful: raise RuntimeError(extraction.document_error or "Extraction produced no usable text.")
        doc.set_stage(BatchStage.READY_FOR_ANALYSIS,progress_percent=45); save_batch_manifest(batch); _notify(progress_callback,batch,doc,"Extraction complete")
        analyzer=TenderAnalyzer(adapter); doc.set_stage(BatchStage.ANALYZING,progress_percent=50)
        def analysis_progress(stage,current,total):
            if stage=="Extracting tender chunk": doc.chunks_total=max(doc.chunks_total,total); doc.chunks_completed=max(doc.chunks_completed,current); doc.progress_percent=50+35*(current/max(total,1))
            elif stage in {"Assessing company qualification","Skipping company qualification"}: doc.progress_percent=90
            elif stage=="Analysis complete": doc.progress_percent=98
            doc.touch(); save_batch_manifest(batch); _notify(progress_callback,batch,doc,stage)
        run=analyzer.analyze(document=extraction,company_context=get_synthetic_company_profile(),progress_callback=analysis_progress)
        payload={"tender_analysis":run.tender_analysis.model_dump(mode="json"),"tender_assessment":run.tender_assessment.model_dump(mode="json"),"pipeline":{"chunk_count":run.chunk_count,"input_tokens":run.input_tokens,"output_tokens":run.output_tokens,"total_tokens":run.total_tokens,"request_ids":run.request_ids,"model_names":run.model_names}}
        p=_save(batch,doc,"analysis.json",payload); doc.analysis_result_path=str(p.resolve()); doc.assessment_result_path=str(p.resolve()); doc.chunks_total=run.chunk_count; doc.chunks_completed=run.chunk_count; doc.token_usage=DocumentTokenUsage(input_tokens=run.input_tokens,output_tokens=run.output_tokens,total_tokens=run.total_tokens); doc.recommendation=run.tender_assessment.recommendation.value
        doc.metadata.update({"document_type":run.tender_analysis.metadata.get("document_type","unknown"),"assessment_skipped":run.tender_assessment.metadata.get("assessment_skipped",False),"tender_title":run.tender_analysis.title,"reference_number":run.tender_analysis.reference_number,"issuing_authority":run.tender_analysis.issuing_authority,"submission_deadline":run.tender_analysis.submission_deadline,"model_names":run.model_names})
        doc.set_stage(BatchStage.PARTIAL if doc.review_pages or doc.failed_pages else BatchStage.COMPLETED,progress_percent=100); save_batch_manifest(batch); _notify(progress_callback,batch,doc,"Document complete")
    except Exception as exc:
        doc.add_error(stage=doc.stage,message=str(exc),error_type=exc.__class__.__name__,retryable=True); doc.set_stage(BatchStage.FAILED,progress_percent=100); save_batch_manifest(batch); _notify(progress_callback,batch,doc,f"Failed: {exc}")

def process_batch_sequentially(batch: BatchRun, *, extraction_settings: dict[str,Any], progress_callback: BatchProgressCallback|None=None, include_duplicates: bool=True) -> BatchRun:
    adapter=GroqAdapter()
    for doc in batch.documents:
        if doc.is_terminal: continue
        if doc.is_duplicate and not include_duplicates:
            doc.add_error(stage=BatchStage.UPLOADED,message=f"Duplicate skipped. Original: {doc.duplicate_of_document_id}",error_type="DuplicateDocument",retryable=False); doc.set_stage(BatchStage.PARTIAL,progress_percent=100); save_batch_manifest(batch); continue
        process_batch_document(batch,doc,extraction_settings=extraction_settings,adapter=adapter,progress_callback=progress_callback)
    batch.refresh_status(); save_batch_manifest(batch); return batch

def retry_batch_document(batch: BatchRun, document_id: str, *, extraction_settings: dict[str,Any], progress_callback: BatchProgressCallback|None=None) -> BatchRun:
    doc=batch.get_document(document_id)
    if doc is None: raise KeyError(f"Unknown document: {document_id}")
    reset_document_for_retry(doc); process_batch_document(batch,doc,extraction_settings=extraction_settings,adapter=GroqAdapter(),progress_callback=progress_callback); batch.refresh_status(); save_batch_manifest(batch); return batch

def load_document_analysis(doc: BatchDocument) -> dict[str,Any]|None:
    if not doc.analysis_result_path: return None
    path=Path(doc.analysis_result_path); return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None
