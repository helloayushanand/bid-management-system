"""Streamlit interface for tender PDF extraction and analysis."""

from __future__ import annotations

import json
import os
from typing import Any

import streamlit as st

from adapters import GroqAdapter
from analysis import AnalysisRunResult, TenderAnalyzer
from company_context import (
    get_synthetic_company_profile,
    get_synthetic_context_warning,
)
from extraction import PDFExtractionError, extract_pdf
from models import DocumentExtractionResult, ExtractionMode
from utils.file_utils import (
    build_download_filename,
    result_to_json_bytes,
    result_to_text_bytes,
)


APP_TITLE = "Tender PDF Analyzer"

MODE_LABELS = {
    "Automatic": ExtractionMode.AUTOMATIC,
    "Native text only": ExtractionMode.NATIVE_ONLY,
    "OCR all pages": ExtractionMode.OCR_ALL,
}


def initialize_session_state() -> None:
    """Initialize values retained across Streamlit reruns."""

    defaults: dict[str, Any] = {
        "extraction_result": None,
        "analysis_run": None,
        "processed_filename": None,
    }

    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def reset_results() -> None:
    """Clear extraction and analysis results after a file change."""

    st.session_state.extraction_result = None
    st.session_state.analysis_run = None
    st.session_state.processed_filename = None


def render_sidebar() -> dict[str, Any]:
    """Render PDF extraction settings."""

    st.sidebar.header("PDF extraction")

    selected_mode_label = st.sidebar.selectbox(
        "Extraction mode",
        options=list(MODE_LABELS.keys()),
        index=0,
    )

    minimum_characters = st.sidebar.number_input(
        "Minimum native characters per page",
        min_value=0,
        max_value=5000,
        value=80,
        step=10,
    )

    ocr_language = st.sidebar.text_input(
        "OCR language",
        value="eng",
    )

    ocr_dpi = st.sidebar.slider(
        "OCR resolution",
        min_value=150,
        max_value=400,
        value=300,
        step=25,
    )

    tessdata_path = st.sidebar.text_input(
        "Tesseract data folder",
        value=os.environ.get("TESSDATA_PREFIX", ""),
        placeholder=r"C:\Program Files\Tesseract-OCR\tessdata",
    )

    st.sidebar.divider()
    st.sidebar.header("LLM analysis")
    st.sidebar.caption(
        "Groq configuration is loaded from the local .env file. "
        "The company profile is synthetic and unverified."
    )

    return {
        "mode": MODE_LABELS[selected_mode_label],
        "minimum_native_characters": int(minimum_characters),
        "ocr_language": ocr_language.strip() or "eng",
        "ocr_dpi": int(ocr_dpi),
        "tessdata_path": tessdata_path.strip() or None,
    }


def process_uploaded_pdf(
    uploaded_file: Any,
    settings: dict[str, Any],
) -> DocumentExtractionResult:
    """Extract text from one uploaded PDF."""

    file_bytes = uploaded_file.getvalue()

    if not file_bytes:
        raise ValueError("The uploaded PDF is empty.")

    return extract_pdf(
        file_bytes=file_bytes,
        filename=uploaded_file.name,
        mode=settings["mode"],
        minimum_native_characters=settings["minimum_native_characters"],
        ocr_language=settings["ocr_language"],
        ocr_dpi=settings["ocr_dpi"],
        tessdata_path=settings["tessdata_path"],
    )


def render_extraction_summary(result: DocumentExtractionResult) -> None:
    """Display extraction statistics."""

    row = st.columns(5)
    row[0].metric("Pages", result.page_count)
    row[1].metric("Native", result.native_page_count)
    row[2].metric("OCR", result.ocr_page_count)
    row[3].metric("Review", result.review_page_count)
    row[4].metric("Words", f"{result.total_words:,}")

    if result.successful:
        st.success("PDF extraction completed.")
    else:
        st.warning("Extraction completed with unresolved pages or no usable text.")

    if result.processing_seconds is not None:
        st.caption(
            f"Processing time: {result.processing_seconds:.2f} seconds"
        )


def render_page_table(result: DocumentExtractionResult) -> None:
    """Display page-level extraction status."""

    rows = [
        {
            "Page": page.page_number,
            "Method": page.extraction_method,
            "Characters": page.character_count,
            "Words": page.word_count,
            "Quality": round(page.quality_score, 3),
            "OCR attempted": page.ocr_attempted,
            "Needs review": page.needs_review,
            "Error": page.error or "",
        }
        for page in result.pages
    ]

    st.dataframe(rows, use_container_width=True, hide_index=True)


def render_page_preview(result: DocumentExtractionResult) -> None:
    """Display extracted text for a selected page."""

    if not result.pages:
        return

    page_number = st.selectbox(
        "Select page",
        options=[page.page_number for page in result.pages],
        format_func=lambda value: f"Page {value}",
    )
    page = result.page_by_number(page_number)

    if page is None:
        return

    if page.needs_review:
        st.warning("This page requires manual review.")

    if page.review_reasons:
        st.write("**Review reasons:**")
        for reason in page.review_reasons:
            st.write(f"- {reason}")

    st.text_area(
        "Extracted page text",
        value=page.text or "[No text extracted]",
        height=450,
        disabled=True,
        key=f"preview_{page.page_number}",
    )


def render_extraction_downloads(result: DocumentExtractionResult) -> None:
    """Display TXT and JSON extraction downloads."""

    first, second = st.columns(2)

    first.download_button(
        "Download extracted TXT",
        data=result_to_text_bytes(result),
        file_name=build_download_filename(result.filename, "txt"),
        mime="text/plain",
        use_container_width=True,
    )

    second.download_button(
        "Download extraction JSON",
        data=result_to_json_bytes(result),
        file_name=build_download_filename(result.filename, "json"),
        mime="application/json",
        use_container_width=True,
    )


def run_tender_analysis(
    extraction_result: DocumentExtractionResult,
) -> AnalysisRunResult:
    """Run Groq analysis using the synthetic company profile."""

    adapter = GroqAdapter()
    analyzer = TenderAnalyzer(adapter)
    progress_bar = st.progress(0.0)
    status = st.empty()

    stage_weights = {
        "Extracting tender chunk": 0.70,
        "Consolidating tender analysis": 0.82,
        "Assessing company qualification": 0.94,
        "Analysis complete": 1.0,
    }

    def update_progress(stage: str, current: int, total: int) -> None:
        status.write(f"{stage}: {current}/{total}")

        if stage == "Extracting tender chunk":
            progress = 0.70 * (current / max(total, 1))
        else:
            progress = stage_weights.get(stage, 0.0)

        progress_bar.progress(min(progress, 1.0))

    try:
        return analyzer.analyze(
            document=extraction_result,
            company_context=get_synthetic_company_profile(),
            progress_callback=update_progress,
        )
    finally:
        progress_bar.empty()
        status.empty()


def render_metadata(analysis: Any) -> None:
    """Display extracted tender metadata."""

    fields = [
        ("Title", analysis.title),
        ("Reference", analysis.reference_number),
        ("Authority", analysis.issuing_authority),
        ("Submission deadline", analysis.submission_deadline),
        ("Pre-bid date", analysis.pre_bid_date),
        ("Tender fee", analysis.tender_fee),
        ("EMD", analysis.emd_amount),
        ("Estimated value", analysis.estimated_value),
        ("Contract duration", analysis.contract_duration),
    ]

    for label, value in fields:
        st.write(f"**{label}:** {value or 'Not found'}")


def render_eligibility(analysis_run: AnalysisRunResult) -> None:
    """Display eligibility extraction and assessment."""

    analysis = analysis_run.tender_analysis
    assessment_by_id = {
        item.criterion_id: item
        for item in analysis_run.tender_assessment.eligibility_assessments
    }

    if not analysis.eligibility_criteria:
        st.info("No eligibility criteria were extracted.")
        return

    rows = []
    for criterion in analysis.eligibility_criteria:
        assessment = assessment_by_id.get(criterion.criterion_id)
        rows.append(
            {
                "ID": criterion.criterion_id,
                "Criterion": criterion.title,
                "Mandatory": criterion.mandatory,
                "Requirement": criterion.requirement,
                "Threshold": criterion.threshold or "",
                "Assessment": (
                    assessment.status.value if assessment else "not assessed"
                ),
                "Confidence": (
                    round(assessment.confidence, 2) if assessment else ""
                ),
                "Review": (
                    assessment.requires_human_review if assessment else True
                ),
            }
        )

    st.dataframe(rows, use_container_width=True, hide_index=True)

    for criterion in analysis.eligibility_criteria:
        assessment = assessment_by_id.get(criterion.criterion_id)
        with st.expander(
            f"{criterion.criterion_id}: {criterion.title}"
        ):
            st.write(f"**Requirement:** {criterion.requirement}")
            if criterion.evidence_required:
                st.write("**Required evidence:**")
                for item in criterion.evidence_required:
                    st.write(f"- {item}")

            if assessment:
                st.write(f"**Status:** {assessment.status.value.upper()}")
                st.write(f"**Company observation:** {assessment.company_observation}")
                st.write(f"**Explanation:** {assessment.explanation}")
                if assessment.missing_evidence:
                    st.write("**Missing evidence:**")
                    for item in assessment.missing_evidence:
                        st.write(f"- {item}")

            if criterion.citations:
                st.write("**Tender citations:**")
                for citation in criterion.citations:
                    st.write(
                        f"- Page {citation.page_number}: {citation.excerpt}"
                    )


def render_scoring(analysis_run: AnalysisRunResult) -> None:
    """Display scoring criteria and estimated marks."""

    analysis = analysis_run.tender_analysis
    assessment_by_id = {
        item.criterion_id: item
        for item in analysis_run.tender_assessment.scoring_assessments
    }

    if not analysis.scoring_criteria:
        st.info("No technical scoring criteria were extracted.")
        return

    rows = []
    for criterion in analysis.scoring_criteria:
        assessment = assessment_by_id.get(criterion.criterion_id)
        rows.append(
            {
                "ID": criterion.criterion_id,
                "Criterion": criterion.title,
                "Maximum marks": criterion.maximum_marks,
                "Estimated marks": (
                    assessment.estimated_marks if assessment else None
                ),
                "Status": (
                    assessment.status.value if assessment else "not assessed"
                ),
                "Review": (
                    assessment.requires_human_review if assessment else True
                ),
            }
        )

    st.dataframe(rows, use_container_width=True, hide_index=True)


def render_analysis_summary(analysis_run: AnalysisRunResult) -> None:
    """Display the overall analysis and recommendation."""

    analysis = analysis_run.tender_analysis
    assessment = analysis_run.tender_assessment

    st.error(get_synthetic_context_warning())

    label = assessment.recommendation.value.upper()
    if label == "GREEN":
        st.success(f"Demonstration recommendation: {label}")
    elif label == "RED":
        st.error(f"Demonstration recommendation: {label}")
    else:
        st.warning(f"Demonstration recommendation: {label}")

    st.write(assessment.recommendation_reason)

    metrics = st.columns(4)
    metrics[0].metric("Chunks", analysis_run.chunk_count)
    metrics[1].metric("Input tokens", f"{analysis_run.input_tokens:,}")
    metrics[2].metric("Output tokens", f"{analysis_run.output_tokens:,}")
    metrics[3].metric("Total tokens", f"{analysis_run.total_tokens:,}")

    score_columns = st.columns(3)
    score_columns[0].metric(
        "Expected marks",
        assessment.expected_marks if assessment.expected_marks is not None else "N/A",
    )
    score_columns[1].metric(
        "Maximum marks",
        assessment.maximum_marks if assessment.maximum_marks is not None else "N/A",
    )
    score_columns[2].metric(
        "Expected score",
        (
            f"{assessment.expected_score_percentage:.2f}%"
            if assessment.expected_score_percentage is not None
            else "N/A"
        ),
    )

    st.subheader("Executive summary")
    st.write(analysis.executive_summary or "No executive summary generated.")

    st.subheader("Scope summary")
    st.write(analysis.scope_summary or "No scope summary generated.")

    with st.expander("Tender metadata"):
        render_metadata(analysis)

    if assessment.strengths:
        st.subheader("Strengths")
        for item in assessment.strengths:
            st.write(f"- {item}")

    if assessment.concerns:
        st.subheader("Concerns")
        for item in assessment.concerns:
            st.write(f"- {item}")

    if assessment.next_actions:
        st.subheader("Next actions")
        for item in assessment.next_actions:
            st.write(f"- {item}")


def render_analysis_downloads(analysis_run: AnalysisRunResult) -> None:
    """Display structured analysis downloads."""

    payload = {
        "tender_analysis": analysis_run.tender_analysis.model_dump(mode="json"),
        "tender_assessment": analysis_run.tender_assessment.model_dump(mode="json"),
        "pipeline": {
            "chunk_count": analysis_run.chunk_count,
            "token_usage": analysis_run.token_usage(),
            "models": analysis_run.model_names,
            "request_ids": analysis_run.request_ids,
        },
    }

    filename = (
        PathSafeStem(analysis_run.tender_analysis.source_filename)
        + "_analysis.json"
    )

    st.download_button(
        "Download tender analysis JSON",
        data=json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8"),
        file_name=filename,
        mime="application/json",
        use_container_width=True,
    )


def PathSafeStem(filename: str) -> str:
    """Return a simple safe file stem for analysis downloads."""

    stem = os.path.splitext(os.path.basename(filename))[0].strip()
    safe = "".join(
        character if character.isalnum() or character in "-_" else "_"
        for character in stem
    )
    return safe or "tender"


def main() -> None:
    """Run the Streamlit application."""

    st.set_page_config(
        page_title=APP_TITLE,
        page_icon="📄",
        layout="wide",
    )
    initialize_session_state()

    st.title(APP_TITLE)
    st.write(
        "Extract text from digital or scanned tender PDFs, then run a "
        "structured Groq analysis using synthetic company context."
    )

    settings = render_sidebar()
    uploaded_file = st.file_uploader(
        "Upload a tender PDF",
        type=["pdf"],
        accept_multiple_files=False,
        on_change=reset_results,
    )

    if uploaded_file is None:
        st.info("Upload a PDF to begin.")
        return

    st.write(f"**Selected:** {uploaded_file.name}")

    if st.button(
        "Extract PDF text",
        type="primary",
        use_container_width=True,
    ):
        try:
            with st.spinner("Extracting PDF text..."):
                result = process_uploaded_pdf(uploaded_file, settings)
            st.session_state.extraction_result = result
            st.session_state.analysis_run = None
            st.session_state.processed_filename = uploaded_file.name
        except PDFExtractionError as exc:
            st.error(str(exc))
        except Exception as exc:
            st.exception(exc)

    extraction_result = st.session_state.extraction_result

    if extraction_result is None:
        return

    extraction_tab, analysis_tab = st.tabs(
        ["PDF extraction", "Tender analysis"]
    )

    with extraction_tab:
        render_extraction_summary(extraction_result)
        st.subheader("Page-level status")
        render_page_table(extraction_result)
        st.subheader("Page preview")
        render_page_preview(extraction_result)
        st.subheader("Downloads")
        render_extraction_downloads(extraction_result)

    with analysis_tab:
        st.error(get_synthetic_context_warning())
        st.caption(
            "Analysis sends extracted tender text to the configured Groq model. "
            "Run it only after checking extraction quality."
        )

        if extraction_result.review_page_count:
            st.warning(
                f"{extraction_result.review_page_count} extracted page(s) are "
                "flagged for review. LLM output may inherit OCR errors."
            )

        if st.button(
            "Analyze tender with Groq",
            type="primary",
            use_container_width=True,
        ):
            try:
                with st.spinner("Running structured tender analysis..."):
                    st.session_state.analysis_run = run_tender_analysis(
                        extraction_result
                    )
            except Exception as exc:
                st.exception(exc)

        analysis_run = st.session_state.analysis_run

        if analysis_run is not None:
            render_analysis_summary(analysis_run)
            st.subheader("Eligibility assessment")
            render_eligibility(analysis_run)
            st.subheader("Technical scoring")
            render_scoring(analysis_run)

            if analysis_run.tender_analysis.risks:
                st.subheader("Tender risks")
                for risk in analysis_run.tender_analysis.risks:
                    st.write(
                        f"- **{risk.severity.upper()} | {risk.title}:** "
                        f"{risk.description}"
                    )

            st.subheader("Analysis download")
            render_analysis_downloads(analysis_run)


if __name__ == "__main__":
    main()
