"""Streamlit interface for tender PDF text extraction."""

from __future__ import annotations

import os
from typing import Any

import streamlit as st

from extraction import PDFExtractionError, extract_pdf
from models import DocumentExtractionResult, ExtractionMode
from utils.file_utils import (
    build_download_filename,
    result_to_json_bytes,
    result_to_text_bytes,
)


APP_TITLE = "Tender PDF Text Extractor"

MODE_LABELS = {
    "Automatic": ExtractionMode.AUTOMATIC,
    "Native text only": ExtractionMode.NATIVE_ONLY,
    "OCR all pages": ExtractionMode.OCR_ALL,
}


def initialize_session_state() -> None:
    """Initialize values retained across Streamlit reruns."""

    defaults: dict[str, Any] = {
        "extraction_result": None,
        "processed_file_hash": None,
    }

    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def reset_result() -> None:
    """Clear the currently displayed extraction result."""

    st.session_state.extraction_result = None
    st.session_state.processed_file_hash = None


def render_sidebar() -> dict[str, Any]:
    """Render extraction settings and return selected values."""

    st.sidebar.header("Extraction settings")

    selected_mode_label = st.sidebar.selectbox(
        "Extraction mode",
        options=list(MODE_LABELS.keys()),
        index=0,
        help=(
            "Automatic uses embedded PDF text first and runs OCR only "
            "when the native text appears inadequate."
        ),
    )

    minimum_characters = st.sidebar.number_input(
        "Minimum native characters per page",
        min_value=0,
        max_value=5000,
        value=80,
        step=10,
        help=(
            "In Automatic mode, pages below this threshold may be sent "
            "to OCR after the remaining quality checks are applied."
        ),
    )

    ocr_language = st.sidebar.text_input(
        "OCR language",
        value="eng",
        help=(
            "Tesseract language code. The corresponding trained-data "
            "file must be installed."
        ),
    )

    ocr_dpi = st.sidebar.slider(
        "OCR resolution",
        min_value=150,
        max_value=400,
        value=300,
        step=25,
        help=(
            "Higher values may improve OCR on difficult scans but use "
            "more CPU and memory."
        ),
    )

    default_tessdata_path = os.environ.get("TESSDATA_PREFIX", "")

    tessdata_path = st.sidebar.text_input(
        "Tesseract data folder",
        value=default_tessdata_path,
        placeholder=r"C:\Program Files\Tesseract-OCR\tessdata",
        help=(
            "Optional folder containing files such as eng.traineddata. "
            "Leave empty if TESSDATA_PREFIX is already configured."
        ),
    )

    st.sidebar.divider()

    st.sidebar.caption(
        "Automatic mode is recommended. It avoids OCR for pages that "
        "already contain usable embedded text."
    )

    return {
        "mode": MODE_LABELS[selected_mode_label],
        "minimum_native_characters": int(minimum_characters),
        "ocr_language": ocr_language.strip() or "eng",
        "ocr_dpi": int(ocr_dpi),
        "tessdata_path": tessdata_path.strip() or None,
    }


def render_document_summary(
    result: DocumentExtractionResult,
) -> None:
    """Display top-level extraction statistics."""

    st.subheader("Extraction summary")

    first_row = st.columns(4)

    first_row[0].metric(
        "Total pages",
        result.page_count,
    )
    first_row[1].metric(
        "Native pages",
        result.native_page_count,
    )
    first_row[2].metric(
        "OCR pages",
        result.ocr_page_count,
    )
    first_row[3].metric(
        "Review pages",
        result.review_page_count,
    )

    second_row = st.columns(4)

    second_row[0].metric(
        "Empty pages",
        result.empty_page_count,
    )
    second_row[1].metric(
        "Failed pages",
        result.failed_page_count,
    )
    second_row[2].metric(
        "Characters",
        f"{result.total_characters:,}",
    )
    second_row[3].metric(
        "Words",
        f"{result.total_words:,}",
    )

    if result.processing_seconds is not None:
        st.caption(
            f"Processing completed in "
            f"{result.processing_seconds:.2f} seconds."
        )

    if result.successful:
        st.success("PDF extraction completed successfully.")
    else:
        st.warning(
            "Processing completed, but the document did not produce "
            "usable text on all required pages."
        )

    if result.document_error:
        st.error(result.document_error)


def render_document_information(
    result: DocumentExtractionResult,
) -> None:
    """Display uploaded document metadata."""

    with st.expander("Document information"):
        st.write(f"**Filename:** {result.filename}")
        st.write(
            f"**File size:** {result.file_size_bytes:,} bytes"
        )
        st.write(
            f"**Requested mode:** {result.requested_mode}"
        )
        st.write(f"**SHA-256:** `{result.file_sha256}`")

        if result.started_at_utc:
            st.write(
                "**Started at:** "
                f"{result.started_at_utc.isoformat()}"
            )

        if result.completed_at_utc:
            st.write(
                "**Completed at:** "
                f"{result.completed_at_utc.isoformat()}"
            )


def build_page_table(
    result: DocumentExtractionResult,
) -> list[dict[str, Any]]:
    """Build table rows for page-level extraction status."""

    rows: list[dict[str, Any]] = []

    for page in result.pages:
        rows.append(
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
        )

    return rows


def render_page_status(
    result: DocumentExtractionResult,
) -> None:
    """Display extraction status for every page."""

    st.subheader("Page-level status")

    page_table = build_page_table(result)

    st.dataframe(
        page_table,
        use_container_width=True,
        hide_index=True,
    )


def render_page_preview(
    result: DocumentExtractionResult,
) -> None:
    """Display extracted text for a selected page."""

    st.subheader("Extracted text preview")

    if not result.pages:
        st.info("No pages are available for preview.")
        return

    page_numbers = [
        page.page_number
        for page in result.pages
    ]

    selected_page_number = st.selectbox(
        "Select a page",
        options=page_numbers,
        format_func=lambda value: f"Page {value}",
    )

    selected_page = result.page_by_number(
        selected_page_number
    )

    if selected_page is None:
        st.error("The selected page could not be found.")
        return

    status_columns = st.columns(4)

    status_columns[0].metric(
        "Method",
        selected_page.extraction_method,
    )
    status_columns[1].metric(
        "Characters",
        selected_page.character_count,
    )
    status_columns[2].metric(
        "Words",
        selected_page.word_count,
    )
    status_columns[3].metric(
        "Quality",
        f"{selected_page.quality_score:.2f}",
    )

    if selected_page.needs_review:
        st.warning(
            "This page has been marked for manual review."
        )

    if selected_page.review_reasons:
        with st.expander("Review reasons", expanded=True):
            for reason in selected_page.review_reasons:
                st.write(f"- {reason}")

    if selected_page.error:
        st.error(selected_page.error)

    st.text_area(
        "Page text",
        value=selected_page.text or "[No text extracted]",
        height=500,
        disabled=True,
        key=f"page_text_{selected_page.page_number}",
    )

    if selected_page.metadata:
      with st.expander("Page metadata"):
            st.json(selected_page.metadata)


def render_complete_text(
    result: DocumentExtractionResult,
) -> None:
    """Display the full human-readable extracted document."""

    with st.expander("Preview complete extracted document"):
        complete_text = result_to_text_bytes(
            result
        ).decode("utf-8")

        st.text_area(
            "Complete extraction",
            value=complete_text,
            height=600,
            disabled=True,
        )


def render_download_buttons(
    result: DocumentExtractionResult,
) -> None:
    """Display TXT and JSON download controls."""

    st.subheader("Download results")

    text_filename = build_download_filename(
        result.filename,
        "txt",
    )
    json_filename = build_download_filename(
        result.filename,
        "json",
    )

    text_bytes = result_to_text_bytes(result)
    json_bytes = result_to_json_bytes(result)

    first_column, second_column = st.columns(2)

    first_column.download_button(
        label="Download extracted TXT",
        data=text_bytes,
        file_name=text_filename,
        mime="text/plain",
        use_container_width=True,
    )

    second_column.download_button(
        label="Download structured JSON",
        data=json_bytes,
        file_name=json_filename,
        mime="application/json",
        use_container_width=True,
    )


def process_uploaded_pdf(
    uploaded_file: Any,
    settings: dict[str, Any],
) -> DocumentExtractionResult:
    """Read and process the uploaded Streamlit PDF."""

    file_bytes = uploaded_file.getvalue()

    if not file_bytes:
        raise ValueError("The uploaded PDF is empty.")

    return extract_pdf(
        file_bytes=file_bytes,
        filename=uploaded_file.name,
        mode=settings["mode"],
        minimum_native_characters=(
            settings["minimum_native_characters"]
        ),
        ocr_language=settings["ocr_language"],
        ocr_dpi=settings["ocr_dpi"],
        tessdata_path=settings["tessdata_path"],
    )


def main() -> None:
    """Run the Streamlit application."""

    st.set_page_config(
        page_title=APP_TITLE,
        page_icon="📄",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    initialize_session_state()

    st.title(APP_TITLE)

    st.write(
        "Upload a tender PDF to extract page-referenced text. "
        "The application uses embedded PDF text first and can apply "
        "local OCR when required."
    )

    settings = render_sidebar()

    uploaded_file = st.file_uploader(
        "Upload a tender PDF",
        type=["pdf"],
        accept_multiple_files=False,
        help="Only one PDF is processed at a time in Phase 1.",
        on_change=reset_result,
    )

    if uploaded_file is None:
        st.info(
            "Upload a PDF document to begin extraction."
        )
        return

    file_size = uploaded_file.size

    file_columns = st.columns(2)

    file_columns[0].write(
        f"**Selected file:** {uploaded_file.name}"
    )
    file_columns[1].write(
        f"**File size:** {file_size:,} bytes"
    )

    extract_clicked = st.button(
        "Extract PDF text",
        type="primary",
        use_container_width=True,
    )

    if extract_clicked:
        try:
            with st.spinner(
                "Extracting text from the PDF..."
            ):
                result = process_uploaded_pdf(
                    uploaded_file,
                    settings,
                )

            st.session_state.extraction_result = result
            st.session_state.processed_file_hash = (
                result.file_sha256
            )

        except PDFExtractionError as exc:
            reset_result()
            st.error(str(exc))

        except FileNotFoundError as exc:
            reset_result()
            st.error(str(exc))

        except Exception as exc:
            reset_result()
            st.exception(exc)

    result = st.session_state.extraction_result

    if result is None:
        return

    st.divider()

    render_document_summary(result)
    render_document_information(result)
    render_page_status(result)
    render_page_preview(result)
    render_complete_text(result)
    render_download_buttons(result)


if __name__ == "__main__":
    main()