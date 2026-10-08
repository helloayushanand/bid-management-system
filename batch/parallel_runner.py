"""Bounded parallel extraction with sequential shared LLM analysis."""
from __future__ import annotations
import json
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Callable, Iterable
from adapters import GroqAdapter
from analysis import TenderAnalyzer
from batch.models import BatchDocument, BatchRun, BatchStage, DocumentTokenUsage
from batch.persistence import save_batch_manifest, save_document_payload
from batch.settings import BatchSettings
from company_context import get_synthetic_company_profile
from extraction import DocumentInspectionResult, OCRDocumentResult, build_extraction_result
from models import DocumentExtractionResult, ExtractionMode
from workers import run_native_inspection_job, run_ocr_job

EXTRACTION_COMPUTED_FIELDS = {
    "total_characters",
    "total_words",
    "native_page_count",
    "ocr_page_count",
    "empty_page_count",
    "failed_page_count",
    "review_page_count",
    "successful",
}

ProgressCallback=Callable[[BatchRun,BatchDocument,str],None]

def _notify(cb,batch,doc,msg):
    if cb: cb(batch,doc,msg)

def _save(batch,doc,name,payload):
    return save_document_payload(batch,doc.document_id,name,payload)

def _dump_extraction_result(extraction: DocumentExtractionResult) -> dict[str, Any]:
    """Serialize only declared model fields, excluding computed values."""
    return extraction.model_dump(
        mode="json",
        exclude=EXTRACTION_COMPUTED_FIELDS,
    )

def _load_extraction_result(path: str | Path) -> DocumentExtractionResult:
    """Load extraction JSON while tolerating older computed fields."""
    payload=json.loads(Path(path).read_text(encoding="utf-8"))
    for field_name in EXTRACTION_COMPUTED_FIELDS:
        payload.pop(field_name,None)
    return DocumentExtractionResult.model_validate(payload)

def _selected(batch: BatchRun, document_ids: set[str] | None) -> list[BatchDocument]:
    return [d for d in batch.documents if (document_ids is None or d.document_id in document_ids) and not d.is_terminal]

def reset_document(doc: BatchDocument):
    doc.stage=BatchStage.UPLOADED; doc.progress_percent=0; doc.total_pages=0; doc.native_pages=0; doc.ocr_pages=0; doc.review_pages=0; doc.failed_pages=0; doc.chunks_total=0; doc.chunks_completed=0; doc.recommendation=None; doc.token_usage=DocumentTokenUsage(); doc.errors=[]; doc.extraction_result_path=None; doc.analysis_result_path=None; doc.assessment_result_path=None; doc.completed_at_utc=None; doc.metadata={}; doc.touch()

def _native_job(doc, extraction_settings):
    return {"document_id":doc.document_id,"source_path":doc.stored_path,"filename":doc.original_filename,"minimum_native_characters":int(extraction_settings.get("minimum_native_characters",80))}

def _apply_inspection(batch,doc,payload,error,mode):
    if error or payload is None:
        doc.add_error(stage=BatchStage.INSPECTING,message=error or "Native worker returned no result.",error_type="NativeInspectionError"); doc.set_stage(BatchStage.FAILED,progress_percent=100); return
    inspection=DocumentInspectionResult.model_validate(payload)
    p=_save(batch,doc,"inspection.json",inspection.model_dump(mode="json")); doc.metadata["inspection_result_path"]=str(p.resolve()); doc.total_pages=inspection.page_count; doc.native_pages=inspection.native_page_count; doc.failed_pages=inspection.failed_page_count; doc.metadata["ocr_required_pages"]=inspection.ocr_required_page_count; doc.metadata["empty_pages"]=inspection.empty_page_count
    if inspection.document_error or not inspection.pages:
        doc.add_error(stage=BatchStage.INSPECTING,message=inspection.document_error or "Inspection produced no pages.",error_type="NativeInspectionError"); doc.set_stage(BatchStage.FAILED,progress_percent=100); return
    if mode==ExtractionMode.OCR_ALL: ocr_numbers=list(range(1,inspection.page_count+1))
    elif mode==ExtractionMode.NATIVE_ONLY: ocr_numbers=[]
    else: ocr_numbers=inspection.ocr_page_numbers
    doc.metadata["ocr_page_numbers"]=ocr_numbers
    if ocr_numbers:
        doc.set_stage(BatchStage.OCR_PENDING,progress_percent=25)
    else:
        extraction=build_extraction_result(inspection,None,requested_mode=mode)
        p=_save(batch,doc,"extraction.json",_dump_extraction_result(extraction)); doc.extraction_result_path=str(p.resolve()); doc.review_pages=extraction.review_page_count; doc.failed_pages=extraction.failed_page_count
        doc.set_stage(BatchStage.READY_FOR_ANALYSIS,progress_percent=45)

def run_native_stage(batch, *, extraction_settings, settings, callback=None, document_ids=None):
    docs=_selected(batch,document_ids)
    for doc in docs: doc.set_stage(BatchStage.INSPECTING,progress_percent=5)
    save_batch_manifest(batch)
    jobs=[_native_job(doc,extraction_settings) for doc in docs]
    if settings.multiprocessing_enabled and jobs:
        with ProcessPoolExecutor(max_workers=settings.native_workers) as pool:
            futures={pool.submit(run_native_inspection_job,job):job["document_id"] for job in jobs}
            for future in as_completed(futures):
                doc=batch.get_document(futures[future])
                try: result=future.result()
                except Exception as exc: result={"inspection":None,"error":f"Process worker failed: {exc}"}
                _apply_inspection(batch,doc,result.get("inspection"),result.get("error"),extraction_settings.get("mode",ExtractionMode.AUTOMATIC)); save_batch_manifest(batch); _notify(callback,batch,doc,"Native inspection complete")
    else:
        for job in jobs:
            result=run_native_inspection_job(job); doc=batch.get_document(job["document_id"]); _apply_inspection(batch,doc,result.get("inspection"),result.get("error"),extraction_settings.get("mode",ExtractionMode.AUTOMATIC)); save_batch_manifest(batch); _notify(callback,batch,doc,"Native inspection complete")

def _load_inspection(doc):
    return DocumentInspectionResult.model_validate_json(Path(doc.metadata["inspection_result_path"]).read_text(encoding="utf-8"))

def _ocr_job(doc, extraction_settings):
    return {"document_id":doc.document_id,"source_path":doc.stored_path,"filename":doc.original_filename,"page_numbers":doc.metadata.get("ocr_page_numbers",[]),"language":extraction_settings.get("ocr_language","eng"),"dpi":int(extraction_settings.get("ocr_dpi",250)),"tessdata_path":extraction_settings.get("tessdata_path"),"tesseract_command":extraction_settings.get("tesseract_command")}

def _apply_ocr(batch,doc,payload,error,mode):
    inspection=_load_inspection(doc)
    if error or payload is None:
        doc.add_error(stage=BatchStage.OCR_RUNNING,message=error or "OCR worker returned no result.",error_type="OCRError"); doc.set_stage(BatchStage.FAILED,progress_percent=100); return
    ocr=OCRDocumentResult.model_validate(payload); p=_save(batch,doc,"ocr.json",ocr.model_dump(mode="json")); doc.metadata["ocr_result_path"]=str(p.resolve()); doc.ocr_pages=ocr.successful_page_count; doc.metadata["ocr_failed_pages"]=ocr.failed_page_count
    extraction=build_extraction_result(inspection,ocr,requested_mode=mode); p=_save(batch,doc,"extraction.json",_dump_extraction_result(extraction)); doc.extraction_result_path=str(p.resolve()); doc.review_pages=extraction.review_page_count; doc.failed_pages=extraction.failed_page_count
    if extraction.successful: doc.set_stage(BatchStage.READY_FOR_ANALYSIS,progress_percent=45)
    else: doc.add_error(stage=BatchStage.OCR_RUNNING,message="OCR completed but extraction produced no usable text. Check ocr.json.",error_type="OCRError"); doc.set_stage(BatchStage.FAILED,progress_percent=100)

def run_ocr_stage(batch, *, extraction_settings, settings, callback=None, document_ids=None):
    docs=[d for d in batch.documents if d.stage==BatchStage.OCR_PENDING and (document_ids is None or d.document_id in document_ids)]
    for doc in docs: doc.set_stage(BatchStage.OCR_RUNNING,progress_percent=25)
    save_batch_manifest(batch); jobs=[_ocr_job(d,extraction_settings) for d in docs]
    if settings.multiprocessing_enabled and jobs:
        with ProcessPoolExecutor(max_workers=settings.ocr_workers) as pool:
            futures={pool.submit(run_ocr_job,j):j["document_id"] for j in jobs}
            for future in as_completed(futures):
                doc=batch.get_document(futures[future])
                try: result=future.result()
                except Exception as exc: result={"ocr":None,"error":f"OCR process failed: {exc}"}
                _apply_ocr(batch,doc,result.get("ocr"),result.get("error"),extraction_settings.get("mode",ExtractionMode.AUTOMATIC)); save_batch_manifest(batch); _notify(callback,batch,doc,"OCR stage complete")
    else:
        for job in jobs:
            result=run_ocr_job(job); doc=batch.get_document(job["document_id"]); _apply_ocr(batch,doc,result.get("ocr"),result.get("error"),extraction_settings.get("mode",ExtractionMode.AUTOMATIC)); save_batch_manifest(batch); _notify(callback,batch,doc,"OCR stage complete")

def run_analysis_stage(batch, *, callback=None, document_ids=None):
    adapter=GroqAdapter(); docs=[d for d in batch.documents if d.stage==BatchStage.READY_FOR_ANALYSIS and (document_ids is None or d.document_id in document_ids)]
    for doc in docs:
        try:
            extraction=_load_extraction_result(doc.extraction_result_path); doc.set_stage(BatchStage.ANALYZING,progress_percent=50)
            def progress(stage,current,total):
                if stage=="Extracting tender chunk": doc.chunks_total=max(doc.chunks_total,total); doc.chunks_completed=max(doc.chunks_completed,current); doc.progress_percent=50+35*(current/max(total,1))
                elif stage in {"Assessing company qualification","Skipping company qualification"}: doc.progress_percent=90
                elif stage=="Analysis complete": doc.progress_percent=98
                save_batch_manifest(batch); _notify(callback,batch,doc,stage)
            run=TenderAnalyzer(adapter).analyze(document=extraction,company_context=get_synthetic_company_profile(),progress_callback=progress)
            payload={"tender_analysis":run.tender_analysis.model_dump(mode="json"),"tender_assessment":run.tender_assessment.model_dump(mode="json"),"pipeline":{"chunk_count":run.chunk_count,"input_tokens":run.input_tokens,"output_tokens":run.output_tokens,"total_tokens":run.total_tokens,"request_ids":run.request_ids,"model_names":run.model_names}}
            p=_save(batch,doc,"analysis.json",payload); doc.analysis_result_path=str(p.resolve()); doc.assessment_result_path=str(p.resolve()); doc.chunks_total=run.chunk_count; doc.chunks_completed=run.chunk_count; doc.token_usage=DocumentTokenUsage(input_tokens=run.input_tokens,output_tokens=run.output_tokens,total_tokens=run.total_tokens); doc.recommendation=run.tender_assessment.recommendation.value; doc.metadata.update({"document_type":run.tender_analysis.metadata.get("document_type","unknown"),"assessment_skipped":run.tender_assessment.metadata.get("assessment_skipped",False),"tender_title":run.tender_analysis.title,"reference_number":run.tender_analysis.reference_number,"issuing_authority":run.tender_analysis.issuing_authority,"submission_deadline":run.tender_analysis.submission_deadline,"model_names":run.model_names}); doc.set_stage(BatchStage.PARTIAL if doc.review_pages or doc.failed_pages else BatchStage.COMPLETED,progress_percent=100)
        except Exception as exc:
            doc.add_error(stage=doc.stage,message=str(exc),error_type=exc.__class__.__name__); doc.set_stage(BatchStage.FAILED,progress_percent=100)
        save_batch_manifest(batch); _notify(callback,batch,doc,"Analysis stage complete")

def process_batch_parallel(batch: BatchRun, *, extraction_settings: dict[str,Any], callback: ProgressCallback|None=None, document_ids: set[str]|None=None, include_duplicates: bool=True) -> BatchRun:
    settings=BatchSettings.from_environment()
    for doc in _selected(batch,document_ids):
        if doc.is_duplicate and not include_duplicates:
            doc.add_error(stage=BatchStage.UPLOADED,message=f"Duplicate skipped. Original: {doc.duplicate_of_document_id}",error_type="DuplicateDocument",retryable=False); doc.set_stage(BatchStage.PARTIAL,progress_percent=100)
    run_native_stage(batch,extraction_settings=extraction_settings,settings=settings,callback=callback,document_ids=document_ids)
    run_ocr_stage(batch,extraction_settings=extraction_settings,settings=settings,callback=callback,document_ids=document_ids)
    run_analysis_stage(batch,callback=callback,document_ids=document_ids)
    batch.refresh_status(); save_batch_manifest(batch); return batch

def retry_batch_document(batch: BatchRun, document_id: str, *, extraction_settings: dict[str,Any], callback: ProgressCallback|None=None) -> BatchRun:
    doc=batch.get_document(document_id)
    if doc is None: raise KeyError(f"Unknown document: {document_id}")
    reset_document(doc); save_batch_manifest(batch)
    return process_batch_parallel(batch,extraction_settings=extraction_settings,callback=callback,document_ids={document_id})

def load_document_analysis(doc: BatchDocument) -> dict[str,Any]|None:
    if not doc.analysis_result_path: return None
    path=Path(doc.analysis_result_path); return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None
