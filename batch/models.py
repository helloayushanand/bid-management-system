"""Data models for bounded multi-document batch processing."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, computed_field


class BatchStage(str, Enum):
    CREATED = "created"
    UPLOADED = "uploaded"
    INSPECTING = "inspecting"
    OCR_PENDING = "ocr_pending"
    OCR_RUNNING = "ocr_running"
    READY_FOR_ANALYSIS = "ready_for_analysis"
    ANALYZING = "analyzing"
    COMPLETED = "completed"
    PARTIAL = "partial"
    FAILED = "failed"
    CANCELLED = "cancelled"


class BatchStatus(str, Enum):
    CREATED = "created"
    READY = "ready"
    RUNNING = "running"
    COMPLETED = "completed"
    PARTIAL = "partial"
    FAILED = "failed"
    CANCELLED = "cancelled"


class BatchError(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stage: BatchStage
    message: str = Field(min_length=1)
    error_type: str | None = None
    retryable: bool = True
    occurred_at_utc: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


class DocumentTokenUsage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    total_tokens: int = Field(default=0, ge=0)


class BatchDocument(BaseModel):
    """Serializable state for one PDF in a batch."""

    model_config = ConfigDict(extra="forbid")

    document_id: str = Field(min_length=1)
    batch_id: str = Field(min_length=1)
    original_filename: str = Field(min_length=1)
    stored_filename: str = Field(min_length=1)
    stored_path: str = Field(min_length=1)
    file_size_bytes: int = Field(ge=0)
    file_sha256: str = Field(min_length=64, max_length=64)
    mime_type: str = "application/pdf"

    stage: BatchStage = BatchStage.UPLOADED
    progress_percent: float = Field(default=0.0, ge=0.0, le=100.0)
    duplicate_of_document_id: str | None = None

    total_pages: int = Field(default=0, ge=0)
    native_pages: int = Field(default=0, ge=0)
    ocr_pages: int = Field(default=0, ge=0)
    review_pages: int = Field(default=0, ge=0)
    failed_pages: int = Field(default=0, ge=0)
    chunks_total: int = Field(default=0, ge=0)
    chunks_completed: int = Field(default=0, ge=0)

    recommendation: str | None = None
    token_usage: DocumentTokenUsage = Field(
        default_factory=DocumentTokenUsage
    )
    errors: list[BatchError] = Field(default_factory=list)

    extraction_result_path: str | None = None
    analysis_result_path: str | None = None
    assessment_result_path: str | None = None

    created_at_utc: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    updated_at_utc: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    completed_at_utc: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @computed_field
    @property
    def has_errors(self) -> bool:
        return bool(self.errors)

    @computed_field
    @property
    def is_duplicate(self) -> bool:
        return self.duplicate_of_document_id is not None

    @computed_field
    @property
    def is_terminal(self) -> bool:
        return self.stage in {
            BatchStage.COMPLETED,
            BatchStage.PARTIAL,
            BatchStage.FAILED,
            BatchStage.CANCELLED,
        }

    @computed_field
    @property
    def file_exists(self) -> bool:
        return Path(self.stored_path).is_file()

    def touch(self) -> None:
        self.updated_at_utc = datetime.now(timezone.utc)

    def set_stage(
        self,
        stage: BatchStage,
        *,
        progress_percent: float | None = None,
    ) -> None:
        self.stage = stage
        if progress_percent is not None:
            self.progress_percent = max(
                0.0, min(100.0, progress_percent)
            )
        if self.is_terminal:
            self.completed_at_utc = datetime.now(timezone.utc)
        self.touch()

    def add_error(
        self,
        *,
        stage: BatchStage,
        message: str,
        error_type: str | None = None,
        retryable: bool = True,
    ) -> None:
        self.errors.append(
            BatchError(
                stage=stage,
                message=message,
                error_type=error_type,
                retryable=retryable,
            )
        )
        self.touch()


class BatchRun(BaseModel):
    """Serializable manifest for one batch of PDF documents."""

    model_config = ConfigDict(extra="forbid")

    batch_id: str = Field(min_length=1)
    batch_directory: str = Field(min_length=1)
    status: BatchStatus = BatchStatus.CREATED
    maximum_documents: int = Field(default=10, ge=1, le=100)
    documents: list[BatchDocument] = Field(default_factory=list)
    created_at_utc: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    updated_at_utc: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    completed_at_utc: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @computed_field
    @property
    def document_count(self) -> int:
        return len(self.documents)

    @computed_field
    @property
    def completed_count(self) -> int:
        return sum(
            document.stage == BatchStage.COMPLETED
            for document in self.documents
        )

    @computed_field
    @property
    def partial_count(self) -> int:
        return sum(
            document.stage == BatchStage.PARTIAL
            for document in self.documents
        )

    @computed_field
    @property
    def failed_count(self) -> int:
        return sum(
            document.stage == BatchStage.FAILED
            for document in self.documents
        )

    @computed_field
    @property
    def duplicate_count(self) -> int:
        return sum(document.is_duplicate for document in self.documents)

    @computed_field
    @property
    def terminal_count(self) -> int:
        return sum(document.is_terminal for document in self.documents)

    @computed_field
    @property
    def total_input_tokens(self) -> int:
        return sum(
            document.token_usage.input_tokens
            for document in self.documents
        )

    @computed_field
    @property
    def total_output_tokens(self) -> int:
        return sum(
            document.token_usage.output_tokens
            for document in self.documents
        )

    @computed_field
    @property
    def total_tokens(self) -> int:
        return sum(
            document.token_usage.total_tokens
            for document in self.documents
        )

    def touch(self) -> None:
        self.updated_at_utc = datetime.now(timezone.utc)

    def get_document(self, document_id: str) -> BatchDocument | None:
        return next(
            (
                document
                for document in self.documents
                if document.document_id == document_id
            ),
            None,
        )

    def refresh_status(self) -> BatchStatus:
        if not self.documents:
            self.status = BatchStatus.CREATED
        elif self.terminal_count == self.document_count:
            if self.failed_count == self.document_count:
                self.status = BatchStatus.FAILED
            elif self.failed_count or self.partial_count:
                self.status = BatchStatus.PARTIAL
            else:
                self.status = BatchStatus.COMPLETED
            self.completed_at_utc = datetime.now(timezone.utc)
        elif any(
            document.stage not in {
                BatchStage.UPLOADED,
                BatchStage.CREATED,
            }
            for document in self.documents
        ):
            self.status = BatchStatus.RUNNING
        else:
            self.status = BatchStatus.READY
        self.touch()
        return self.status
