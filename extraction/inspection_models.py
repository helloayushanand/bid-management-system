"""Models for two-pass PDF inspection and selective OCR."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class PageInspectionStatus(str, Enum):
    NATIVE_OK = "native_ok"
    OCR_REQUIRED = "ocr_required"
    EMPTY = "empty"
    FAILED = "failed"


class PageInspectionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    page_number: int = Field(ge=1)
    status: PageInspectionStatus
    native_text: str = ""
    native_character_count: int = Field(default=0, ge=0)
    native_word_count: int = Field(default=0, ge=0)
    quality_score: float = Field(default=0.0, ge=0.0, le=1.0)
    needs_review: bool = False
    review_reasons: list[str] = Field(default_factory=list)
    error: str | None = None


class DocumentInspectionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    filename: str
    source_path: str
    file_size_bytes: int = Field(ge=0)
    file_sha256: str
    page_count: int = Field(ge=0)
    pages: list[PageInspectionResult] = Field(default_factory=list)
    document_error: str | None = None
    processing_seconds: float | None = Field(default=None, ge=0.0)

    @property
    def native_page_count(self) -> int:
        return sum(page.status == PageInspectionStatus.NATIVE_OK for page in self.pages)

    @property
    def ocr_required_page_count(self) -> int:
        return sum(page.status == PageInspectionStatus.OCR_REQUIRED for page in self.pages)

    @property
    def empty_page_count(self) -> int:
        return sum(page.status == PageInspectionStatus.EMPTY for page in self.pages)

    @property
    def failed_page_count(self) -> int:
        return sum(page.status == PageInspectionStatus.FAILED for page in self.pages)

    @property
    def ocr_page_numbers(self) -> list[int]:
        return [
            page.page_number
            for page in self.pages
            if page.status == PageInspectionStatus.OCR_REQUIRED
        ]


class OCRPageResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    page_number: int = Field(ge=1)
    text: str = ""
    character_count: int = Field(default=0, ge=0)
    word_count: int = Field(default=0, ge=0)
    quality_score: float = Field(default=0.0, ge=0.0, le=1.0)
    successful: bool = False
    needs_review: bool = False
    review_reasons: list[str] = Field(default_factory=list)
    error: str | None = None


class OCRDocumentResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    filename: str
    source_path: str
    requested_page_numbers: list[int] = Field(default_factory=list)
    pages: list[OCRPageResult] = Field(default_factory=list)
    processing_seconds: float | None = Field(default=None, ge=0.0)

    @property
    def successful_page_count(self) -> int:
        return sum(page.successful for page in self.pages)

    @property
    def failed_page_count(self) -> int:
        return sum(not page.successful for page in self.pages)
