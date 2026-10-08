"""Streamlit batch tender-processing interface."""
from __future__ import annotations
import json
import os
from pathlib import Path
import streamlit as st
from batch import BatchRun, BatchSettings, BatchValidationError, batch_summary_rows, cleanup_batch_directory, create_batch, save_batch_manifest
from batch.sequential_runner import load_document_analysis, process_batch_sequentially, retry_batch_document
from models import ExtractionMode

st.set_page_config(page_title="Batch Tender Processing",page_icon="📚",layout="wide")
MODE_LABELS={"Automatic":ExtractionMode.AUTOMATIC,"Native text only":ExtractionMode.NATIVE_ONLY,"OCR all pages":ExtractionMode.OCR_ALL}

def init():
    if "batch_run" not in st.session_state: st.session_state.batch_run=None

def clear(): st.session_state.batch_run=None

def metrics(batch: BatchRun):
    cols=st.columns(6); cols[0].metric("Documents",batch.document_count); cols[1].metric("Completed",batch.completed_count); cols[2].metric("Partial",batch.partial_count); cols[3].metric("Failed",batch.failed_count); cols[4].metric("Duplicates",batch.duplicate_count); cols[5].metric("Tokens",f"{batch.total_tokens:,}")

def manifest(batch): st.dataframe(batch_summary_rows(batch),use_container_width=True,hide_index=True)

def progress_callback_factory(batch, progress_bar, status, table):
    def update(current_batch,current_document,message):
        base=current_batch.terminal_count/max(current_batch.document_count,1)
        active=(current_document.progress_percent/100)/max(current_batch.document_count,1)
        progress_bar.progress(min(base+active,1.0)); status.write(f"{current_document.original_filename}: {message}"); table.dataframe(batch_summary_rows(current_batch),use_container_width=True,hide_index=True)
    return update

def render_documents(batch: BatchRun):
    st.subheader("Document results and errors")
    for document in batch.documents:
        dtype=document.metadata.get("document_type","unknown")
        label=f"{document.original_filename} | {document.stage.value} | {dtype}"
        with st.expander(label):
            c1,c2,c3,c4=st.columns(4)
            c1.metric("Stage",document.stage.value); c2.metric("Document type",dtype); c3.metric("Recommendation",document.recommendation or "Unavailable"); c4.metric("Tokens",f"{document.token_usage.total_tokens:,}")
            st.write(f"**Pages:** {document.total_pages} total, {document.native_pages} native, {document.ocr_pages} OCR, {document.review_pages} review, {document.failed_pages} failed")
            if document.metadata.get("assessment_skipped"):
                st.info("Company assessment was skipped because no tender eligibility or scoring criteria were found.")
            if document.errors:
                st.error("This document has processing errors.")
                for error in document.errors:
                    st.write(f"- **{error.error_type or 'Error'}** at `{error.stage.value}`: {error.message} | Retryable: {error.retryable}")
            payload=load_document_analysis(document)
            if payload is not None:
                st.download_button("Download analysis JSON",data=json.dumps(payload,ensure_ascii=False,indent=2).encode("utf-8"),file_name=Path(document.original_filename).stem+"_analysis.json",mime="application/json",key=f"download-{document.document_id}")

def main():
    init(); st.title("Batch Tender Processing"); st.write("Upload and process 1 to 10 PDF documents. Documents are currently processed one by one; failed documents can be retried individually.")
    settings=BatchSettings.from_environment(); st.sidebar.header("Batch settings"); st.sidebar.write(f"Maximum documents: {settings.maximum_documents}")
    selected_mode=st.sidebar.selectbox("Extraction mode",list(MODE_LABELS),index=0)
    min_chars=st.sidebar.number_input("Minimum native characters per page",0,5000,80,10)
    ocr_lang=st.sidebar.text_input("OCR language","eng"); ocr_dpi=st.sidebar.slider("OCR resolution",150,400,250,25)
    tessdata=st.sidebar.text_input("Tesseract data folder",value=os.environ.get("TESSDATA_PREFIX",""),placeholder=r"C:\Program Files\Tesseract-OCR\tessdata")
    include_duplicates=st.sidebar.checkbox("Process duplicate files independently",True)
    files=st.file_uploader("Select tender PDFs",type=["pdf"],accept_multiple_files=True,on_change=clear)
    if files:
        st.caption(f"Selected {len(files)} file(s), {sum(f.size for f in files)/(1024*1024):.2f} MB total.")
        if len(files)>settings.maximum_documents: st.error(f"Select no more than {settings.maximum_documents} PDFs.")
    if st.button("Create batch manifest",type="primary",use_container_width=True,disabled=not files or len(files)>settings.maximum_documents):
        try: st.session_state.batch_run=create_batch(files,settings=settings,batch_metadata={"workflow":"sequential_phase_2"}); st.success("Batch manifest created.")
        except BatchValidationError as exc: st.error(str(exc))
        except Exception as exc: st.exception(exc)
    batch=st.session_state.batch_run
    if batch is None: return
    settings_dict={"mode":MODE_LABELS[selected_mode],"minimum_native_characters":int(min_chars),"ocr_language":ocr_lang.strip() or "eng","ocr_dpi":int(ocr_dpi),"tessdata_path":tessdata.strip() or None}
    st.divider(); st.write(f"**Batch ID:** `{batch.batch_id}`"); st.write(f"**Batch status:** {batch.status.value}"); metrics(batch); manifest(batch)
    pcol,rcol,ccol=st.columns(3)
    process=pcol.button("Process remaining documents",type="primary",use_container_width=True,disabled=batch.terminal_count==batch.document_count)
    retryable=[d for d in batch.documents if d.stage.value in {"failed","partial"}]
    selected_retry=rcol.selectbox("Retry document",options=retryable,format_func=lambda d:d.original_filename,index=None,placeholder="Select failed/partial PDF") if retryable else None
    retry=rcol.button("Retry selected document",use_container_width=True,disabled=selected_retry is None)
    cleanup=ccol.button("Delete batch working files",use_container_width=True)
    if process or retry:
        bar=st.progress(0.0); status=st.empty(); table=st.empty(); callback=progress_callback_factory(batch,bar,status,table)
        with st.spinner("Processing..."):
            if retry: st.session_state.batch_run=retry_batch_document(batch,selected_retry.document_id,extraction_settings=settings_dict,progress_callback=callback)
            else: st.session_state.batch_run=process_batch_sequentially(batch,extraction_settings=settings_dict,progress_callback=callback,include_duplicates=include_duplicates)
        bar.progress(1.0); status.success("Processing finished."); save_batch_manifest(st.session_state.batch_run); st.rerun()
    if cleanup:
        cleanup_batch_directory(batch); clear(); st.success("Batch working files deleted."); st.rerun()
    render_documents(batch)

main()
