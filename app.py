"""Streamlit UI for bounded parallel tender processing."""
from __future__ import annotations
import json
import os
from pathlib import Path
import streamlit as st
from batch import BatchRun, BatchSettings, BatchValidationError, batch_summary_rows, cleanup_batch_directory, create_batch, save_batch_manifest
from batch.parallel_runner import load_document_analysis, process_batch_parallel, retry_batch_document
from models import ExtractionMode

st.set_page_config(page_title="Batch Tender Processing",page_icon="📚",layout="wide")
MODES={"Automatic":ExtractionMode.AUTOMATIC,"Native text only":ExtractionMode.NATIVE_ONLY,"OCR all pages":ExtractionMode.OCR_ALL}

def initialize():
    if "batch_run" not in st.session_state: st.session_state.batch_run=None

def clear(): st.session_state.batch_run=None

def render_metrics(batch):
    cols=st.columns(8)
    values=[("Documents",batch.document_count),("Inspected",sum(bool(d.metadata.get("inspection_result_path")) for d in batch.documents)),("Need OCR",sum(bool(d.metadata.get("ocr_page_numbers")) for d in batch.documents)),("Ready",sum(d.stage.value=="ready_for_analysis" for d in batch.documents)),("Completed",batch.completed_count),("Partial",batch.partial_count),("Failed",batch.failed_count),("Tokens",f"{batch.total_tokens:,}")]
    for col,(label,value) in zip(cols,values): col.metric(label,value)

def render_results(batch):
    st.subheader("Document results and errors")
    for doc in batch.documents:
        dtype=doc.metadata.get("document_type","unknown")
        with st.expander(f"{doc.original_filename} | {doc.stage.value} | {dtype}"):
            cols=st.columns(5)
            cols[0].metric("Stage",doc.stage.value); cols[1].metric("Type",dtype); cols[2].metric("OCR required",doc.metadata.get("ocr_required_pages",0)); cols[3].metric("OCR complete",doc.ocr_pages); cols[4].metric("Tokens",f"{doc.token_usage.total_tokens:,}")
            st.write(f"**Pages:** {doc.total_pages} total, {doc.native_pages} native, {doc.ocr_pages} OCR, {doc.review_pages} review, {doc.failed_pages} failed")
            if doc.metadata.get("assessment_skipped"): st.info("Company assessment was skipped because no tender eligibility or scoring criteria were found.")
            for error in doc.errors: st.error(f"{error.error_type or 'Error'} at {error.stage.value}: {error.message} | Retryable: {error.retryable}")
            payload=load_document_analysis(doc)
            if payload:
                st.download_button("Download analysis JSON",data=json.dumps(payload,ensure_ascii=False,indent=2).encode(),file_name=Path(doc.original_filename).stem+"_analysis.json",mime="application/json",key=f"download-{doc.document_id}")

def main():
    initialize(); settings=BatchSettings.from_environment()
    st.title("Batch Tender Processing")
    st.write("Native inspection uses bounded parallel processes, selective OCR uses its own bounded process pool, and LLM analysis remains sequential.")
    st.sidebar.header("Pipeline")
    st.sidebar.write(f"Native workers: {settings.native_workers}")
    st.sidebar.write(f"OCR workers: {settings.ocr_workers}")
    st.sidebar.write(f"Multiprocessing: {'enabled' if settings.multiprocessing_enabled else 'disabled'}")
    mode_label=st.sidebar.selectbox("Extraction mode",list(MODES),index=0)
    min_chars=st.sidebar.number_input("Minimum native characters per page",0,5000,80,10)
    ocr_language=st.sidebar.text_input("OCR language","eng")
    ocr_dpi=st.sidebar.slider("OCR resolution",150,400,250,25)
    tessdata=st.sidebar.text_input("Tesseract data folder",value=os.getenv("TESSDATA_PREFIX",r"C:\Program Files\Tesseract-OCR\tessdata"))
    tesseract_cmd=st.sidebar.text_input("Tesseract executable",value=os.getenv("TESSERACT_CMD",r"C:\Program Files\Tesseract-OCR\tesseract.exe"))
    include_duplicates=st.sidebar.checkbox("Process duplicate files independently",True)
    uploads=st.file_uploader("Select tender PDFs",type=["pdf"],accept_multiple_files=True,on_change=clear)
    if uploads:
        st.caption(f"Selected {len(uploads)} file(s), {sum(f.size for f in uploads)/(1024*1024):.2f} MB total.")
        if len(uploads)>settings.maximum_documents: st.error(f"Select no more than {settings.maximum_documents} PDFs.")
    if st.button("Create batch manifest",type="primary",use_container_width=True,disabled=not uploads or len(uploads)>settings.maximum_documents):
        try: st.session_state.batch_run=create_batch(uploads,settings=settings,batch_metadata={"workflow":"bounded_parallel_phase_4"}); st.success("Batch manifest created.")
        except BatchValidationError as exc: st.error(str(exc))
        except Exception as exc: st.exception(exc)
    batch=st.session_state.batch_run
    if batch is None: return
    extraction_settings={"mode":MODES[mode_label],"minimum_native_characters":int(min_chars),"ocr_language":ocr_language.strip() or "eng","ocr_dpi":int(ocr_dpi),"tessdata_path":tessdata.strip() or None,"tesseract_command":tesseract_cmd.strip() or None}
    st.divider(); st.write(f"**Batch ID:** `{batch.batch_id}` | **Status:** {batch.status.value}"); render_metrics(batch); st.dataframe(batch_summary_rows(batch),use_container_width=True,hide_index=True)
    process_col,retry_col,cleanup_col=st.columns(3)
    process=process_col.button("Process Batch",type="primary",use_container_width=True,disabled=batch.terminal_count==batch.document_count)
    retryable=[d for d in batch.documents if d.stage.value in {"failed","partial"}]
    selected=retry_col.selectbox("Retry document",retryable,format_func=lambda d:d.original_filename,index=None,placeholder="Select failed/partial PDF") if retryable else None
    retry=retry_col.button("Retry selected document",use_container_width=True,disabled=selected is None)
    cleanup=cleanup_col.button("Delete batch working files",use_container_width=True)
    if process or retry:
        bar=st.progress(0.0); status=st.empty(); live=st.empty()
        def callback(current_batch,current_doc,message):
            base=current_batch.terminal_count/max(current_batch.document_count,1); active=(current_doc.progress_percent/100)/max(current_batch.document_count,1); bar.progress(min(base+active,1.0)); status.write(f"{current_doc.original_filename}: {message}"); live.dataframe(batch_summary_rows(current_batch),use_container_width=True,hide_index=True)
        with st.spinner("Running bounded batch pipeline..."):
            if retry: st.session_state.batch_run=retry_batch_document(batch,selected.document_id,extraction_settings=extraction_settings,callback=callback)
            else: st.session_state.batch_run=process_batch_parallel(batch,extraction_settings=extraction_settings,callback=callback,include_duplicates=include_duplicates)
        bar.progress(1.0); status.success("Batch processing finished."); save_batch_manifest(st.session_state.batch_run); st.rerun()
    if cleanup:
        cleanup_batch_directory(batch); clear(); st.rerun()
    render_results(batch)

if __name__ == "__main__":
    main()
