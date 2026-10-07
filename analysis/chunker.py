"""Page-aware chunking for extracted tender documents."""

from __future__ import annotations

from dataclasses import dataclass, field

from config import AnalysisSettings
from models import DocumentExtractionResult, PageExtractionResult
from utils.text_utils import clean_extracted_text


@dataclass(frozen=True)
class TenderChunk:
    """One page-aware text chunk prepared for LLM analysis."""

    chunk_id: str
    source_filename: str
    page_start: int
    page_end: int
    page_numbers: tuple[int, ...]
    text: str
    character_count: int
    contains_review_pages: bool = False
    review_page_numbers: tuple[int, ...] = field(
        default_factory=tuple
    )

    def to_prompt_text(self) -> str:
        """Return the complete chunk text for an LLM prompt."""

        header = (
            f"[TENDER DOCUMENT: {self.source_filename}]\n"
            f"[CHUNK ID: {self.chunk_id}]\n"
            f"[PAGES: {self.page_start}-{self.page_end}]\n"
        )

        return f"{header}\n{self.text}".strip()


class TenderChunkingError(ValueError):
    """Raised when a document cannot be converted into chunks."""


def _is_usable_page(
    page: PageExtractionResult,
    *,
    minimum_page_characters: int,
) -> bool:
    """Return whether a page has enough extracted text for analysis."""

    return (
        bool(page.text.strip())
        and page.character_count >= minimum_page_characters
        and page.extraction_method not in {"empty", "failed"}
    )


def _format_page(page: PageExtractionResult) -> str:
    """Format one extracted page with an explicit page marker."""

    cleaned_text = clean_extracted_text(page.text)

    return (
        f"[PAGE {page.page_number}]\n"
        f"{cleaned_text}"
    ).strip()


def _build_chunk(
    *,
    chunk_index: int,
    source_filename: str,
    pages: list[PageExtractionResult],
) -> TenderChunk:
    """Build one immutable chunk from a list of pages."""

    if not pages:
        raise TenderChunkingError(
            "Cannot build a tender chunk without pages."
        )

    page_numbers = tuple(
        page.page_number
        for page in pages
    )

    review_page_numbers = tuple(
        page.page_number
        for page in pages
        if page.needs_review
    )

    chunk_text = "\n\n".join(
        _format_page(page)
        for page in pages
    )

    return TenderChunk(
        chunk_id=f"chunk-{chunk_index:04d}",
        source_filename=source_filename,
        page_start=min(page_numbers),
        page_end=max(page_numbers),
        page_numbers=page_numbers,
        text=chunk_text,
        character_count=len(chunk_text),
        contains_review_pages=bool(review_page_numbers),
        review_page_numbers=review_page_numbers,
    )


def _select_overlap_pages(
    pages: list[PageExtractionResult],
    *,
    overlap_pages: int,
) -> list[PageExtractionResult]:
    """Return trailing pages to repeat in the next chunk."""

    if overlap_pages <= 0:
        return []

    return pages[-overlap_pages:]


def chunk_document(
    document: DocumentExtractionResult,
    *,
    settings: AnalysisSettings | None = None,
) -> list[TenderChunk]:
    """
    Split an extracted tender into page-aware chunks.

    Pages are not split internally. When a single page exceeds the configured
    chunk size, that page is emitted as its own oversized chunk.
    """

    active_settings = settings or AnalysisSettings.from_environment()

    if document.document_error:
        raise TenderChunkingError(
            "The document contains a document-level extraction error: "
            f"{document.document_error}"
        )

    if not document.pages:
        raise TenderChunkingError(
            "The extracted document does not contain any pages."
        )

    usable_pages = [
        page
        for page in document.pages
        if _is_usable_page(
            page,
            minimum_page_characters=(
                active_settings.minimum_page_characters
            ),
        )
    ]

    if not usable_pages:
        raise TenderChunkingError(
            "The document does not contain enough usable extracted text "
            "for tender analysis."
        )

    chunks: list[TenderChunk] = []
    current_pages: list[PageExtractionResult] = []
    current_character_count = 0
    chunk_index = 1

    for page in usable_pages:
        formatted_page = _format_page(page)
        additional_characters = len(formatted_page)

        if current_pages:
            additional_characters += 2

        would_exceed_limit = (
            bool(current_pages)
            and (
                current_character_count + additional_characters
                > active_settings.maximum_chunk_characters
            )
        )

        if would_exceed_limit:
            chunks.append(
                _build_chunk(
                    chunk_index=chunk_index,
                    source_filename=document.filename,
                    pages=current_pages,
                )
            )

            chunk_index += 1

            overlap = _select_overlap_pages(
                current_pages,
                overlap_pages=active_settings.overlap_pages,
            )

            current_pages = list(overlap)

            current_character_count = sum(
                len(_format_page(overlap_page))
                for overlap_page in current_pages
            )

            if len(current_pages) > 1:
                current_character_count += (
                    2 * (len(current_pages) - 1)
                )

        current_pages.append(page)

        if current_character_count > 0:
            current_character_count += 2

        current_character_count += len(formatted_page)

    if current_pages:
        chunks.append(
            _build_chunk(
                chunk_index=chunk_index,
                source_filename=document.filename,
                pages=current_pages,
            )
        )

    return chunks


def calculate_chunk_statistics(
    chunks: list[TenderChunk],
) -> dict[str, int | float]:
    """Return basic statistics for a collection of tender chunks."""

    if not chunks:
        return {
            "chunk_count": 0,
            "total_chunk_characters": 0,
            "minimum_chunk_characters": 0,
            "maximum_chunk_characters": 0,
            "average_chunk_characters": 0.0,
            "review_chunk_count": 0,
        }

    character_counts = [
        chunk.character_count
        for chunk in chunks
    ]

    return {
        "chunk_count": len(chunks),
        "total_chunk_characters": sum(character_counts),
        "minimum_chunk_characters": min(character_counts),
        "maximum_chunk_characters": max(character_counts),
        "average_chunk_characters": round(
            sum(character_counts) / len(character_counts),
            2,
        ),
        "review_chunk_count": sum(
            chunk.contains_review_pages
            for chunk in chunks
        ),
    }