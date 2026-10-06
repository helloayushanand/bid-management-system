"""Data models for PDF extraction results."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, computed_field


class ExtractionMethod(str, Enum):
    """Supported page extraction methods."""

    NATIVE = "native"
    OCR = "ocr"
    EMPTY = "empty"
    FAILED = "failed"


class ExtractionMode(str, Enum):
    """Extraction modes exposed by the application."""

    AUTOMATIC = "automatic"
    NATIVE_ONLY = "native_only"
    OCR_ALL = "ocr_all"


class PageExtractionResult(BaseModel):
    """Extraction result for one PDF page."""

    model_config = ConfigDict(
        extra="forbid",
        use_enum_values=True,
    )

    page_number: int = Field(
        ...,
        ge=1,
        description="Human-readable one-based PDF page number.",
    )
    extraction_method: ExtractionMethod = Field(
        ...,
        description="Method used to obtain the final page text.",
    )
    text: str = Field(
        default="",
        description="Text extracted from the page.",
    )
    character_count: int = Field(
        default=0,
        ge=0,
        description="Number of characters in the cleaned page text.",
    )
    word_count: int = Field(
        default=0,
        ge=0,
        description="Number of whitespace-separated words in the page text.",
    )
    native_character_count: int = Field(
        default=0,
        ge=0,
        description="Character count obtained through native PDF extraction.",
    )
    ocr_attempted: bool = Field(
        default=False,
        description="Whether OCR was attempted for this page.",
    )
    needs_review: bool = Field(
        default=False,
        description="Whether the page should be checked manually.",
    )
    quality_score: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Heuristic extraction-quality score from zero to one.",
    )
    review_reasons: list[str] = Field(
        default_factory=list,
        description="Reasons why the page may require manual review.",
    )
    error: str | None = Field(
        default=None,
        description="Page-level processing error, if one occurred.",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional page-level extraction metadata.",
    )


class DocumentExtractionResult(BaseModel):
    """Complete extraction result for one uploaded PDF."""

    model_config = ConfigDict(
        extra="forbid",
        use_enum_values=True,
    )

    filename: str = Field(
        ...,
        min_length=1,
        description="Original uploaded PDF filename.",
    )
    file_size_bytes: int = Field(
        ...,
        ge=0,
        description="Size of the uploaded PDF in bytes.",
    )
    file_sha256: str = Field(
        ...,
        min_length=64,
        max_length=64,
        description="SHA-256 hash of the uploaded PDF.",
    )
    requested_mode: ExtractionMode = Field(
        default=ExtractionMode.AUTOMATIC,
        description="Extraction mode requested by the user.",
    )
    page_count: int = Field(
        ...,
        ge=0,
        description="Total number of pages in the PDF.",
    )
    pages: list[PageExtractionResult] = Field(
        default_factory=list,
        description="Ordered page-level extraction results.",
    )
    started_at_utc: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC timestamp when document processing started.",
    )
    completed_at_utc: datetime | None = Field(
        default=None,
        description="UTC timestamp when document processing completed.",
    )
    processing_seconds: float | None = Field(
        default=None,
        ge=0.0,
        description="Total processing duration in seconds.",
    )
    document_error: str | None = Field(
        default=None,
        description="Document-level error, if the PDF could not be processed.",
    )

    @computed_field
    @property
    def total_characters(self) -> int:
        """Return the total extracted character count."""

        return sum(page.character_count for page in self.pages)

    @computed_field
    @property
    def total_words(self) -> int:
        """Return the total extracted word count."""

        return sum(page.word_count for page in self.pages)

    @computed_field
    @property
    def native_page_count(self) -> int:
        """Return the number of pages extracted natively."""

        return sum(
            page.extraction_method == ExtractionMethod.NATIVE.value
            for page in self.pages
        )

    @computed_field
    @property
    def ocr_page_count(self) -> int:
        """Return the number of pages whose final output came from OCR."""

        return sum(
            page.extraction_method == ExtractionMethod.OCR.value
            for page in self.pages
        )

    @computed_field
    @property
    def empty_page_count(self) -> int:
        """Return the number of pages with no usable extracted text."""

        return sum(
            page.extraction_method == ExtractionMethod.EMPTY.value
            for page in self.pages
        )

    @computed_field
    @property
    def failed_page_count(self) -> int:
        """Return the number of pages that failed during extraction."""

        return sum(
            page.extraction_method == ExtractionMethod.FAILED.value
            for page in self.pages
        )

    @computed_field
    @property
    def review_page_count(self) -> int:
        """Return the number of pages marked for manual review."""

        return sum(page.needs_review for page in self.pages)

    @computed_field
    @property
    def successful(self) -> bool:
        """Return whether document processing produced usable output."""

        return (
            self.document_error is None
            and self.page_count > 0
            and self.total_characters > 0
        )

    def page_by_number(self, page_number: int) -> PageExtractionResult | None:
        """Return one page result using a one-based page number."""

        return next(
            (
                page
                for page in self.pages
                if page.page_number == page_number
            ),
            None,
        )
