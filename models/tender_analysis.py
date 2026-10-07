"""Structured models for extracting requirements from tender documents."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class CriterionType(str, Enum):
    """Types of requirements commonly found in tender documents."""

    LEGAL = "legal"
    FINANCIAL = "financial"
    TECHNICAL = "technical"
    EXPERIENCE = "experience"
    CERTIFICATION = "certification"
    PERSONNEL = "personnel"
    INFRASTRUCTURE = "infrastructure"
    COMMERCIAL = "commercial"
    DOCUMENTARY = "documentary"
    OTHER = "other"


class RequirementCategory(str, Enum):
    """High-level classification of a tender requirement."""

    MANDATORY_ELIGIBILITY = "mandatory_eligibility"
    TECHNICAL_SCORING = "technical_scoring"
    COMMERCIAL = "commercial"
    CONTRACTUAL = "contractual"
    INFORMATIONAL = "informational"
    OTHER = "other"


class ConfidenceLevel(str, Enum):
    """Human-readable interpretation of extraction confidence."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class TenderCitation(BaseModel):
    """Evidence from the tender supporting an extracted statement."""

    model_config = ConfigDict(extra="forbid")

    document_name: str = Field(
        ...,
        min_length=1,
        description="Name of the tender document containing the evidence.",
    )
    page_number: int = Field(
        ...,
        ge=1,
        description="One-based page number containing the evidence.",
    )
    excerpt: str = Field(
        ...,
        min_length=1,
        description="Short evidence excerpt from the cited page.",
    )


class TenderMetadataCandidate(BaseModel):
    """One metadata value found in a tender chunk."""

    model_config = ConfigDict(extra="forbid")

    field_name: str = Field(
        ...,
        min_length=1,
        description="Normalized metadata field name.",
    )
    value: str = Field(
        ...,
        min_length=1,
        description="Value exactly as extracted or normalized.",
    )
    citations: list[TenderCitation] = Field(
        default_factory=list,
        description="Tender evidence supporting the metadata value.",
    )
    confidence: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
    )


class EligibilityCriterion(BaseModel):
    """One mandatory or non-mandatory tender eligibility requirement."""

    model_config = ConfigDict(extra="forbid")

    criterion_id: str = Field(
        ...,
        min_length=1,
        description="Stable identifier assigned by the analysis pipeline.",
    )
    title: str = Field(
        ...,
        min_length=1,
        description="Short title for the criterion.",
    )
    criterion_type: CriterionType = Field(
        default=CriterionType.OTHER,
    )
    category: RequirementCategory = Field(
        default=RequirementCategory.MANDATORY_ELIGIBILITY,
    )
    mandatory: bool = Field(
        ...,
        description="Whether failure can make the bidder ineligible.",
    )
    requirement: str = Field(
        ...,
        min_length=1,
        description="Complete requirement stated in the tender.",
    )
    threshold: str | None = Field(
        default=None,
        description="Numeric or qualitative threshold, when stated.",
    )
    lookback_period: str | None = Field(
        default=None,
        description="Applicable financial-year or experience period.",
    )
    evidence_required: list[str] = Field(
        default_factory=list,
        description="Documents required to prove compliance.",
    )
    citations: list[TenderCitation] = Field(
        default_factory=list,
        description="Tender passages supporting the criterion.",
    )
    confidence: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
    )
    confidence_level: ConfidenceLevel = Field(
        default=ConfidenceLevel.LOW,
    )
    requires_human_review: bool = Field(
        default=False,
    )
    review_reason: str | None = Field(
        default=None,
    )

    @model_validator(mode="after")
    def validate_citations(self) -> EligibilityCriterion:
        """Flag criteria without citations for manual review."""

        if not self.citations:
            self.requires_human_review = True

            if not self.review_reason:
                self.review_reason = (
                    "No supporting tender citation was extracted."
                )

        return self


class ScoringBand(BaseModel):
    """One score band within a technical evaluation criterion."""

    model_config = ConfigDict(extra="forbid")

    condition: str = Field(
        ...,
        min_length=1,
        description="Condition required to receive the associated marks.",
    )
    marks: float | None = Field(
        default=None,
        ge=0.0,
        description="Marks awarded when the condition is met.",
    )


class ScoringCriterion(BaseModel):
    """One criterion from the tender's technical marking system."""

    model_config = ConfigDict(extra="forbid")

    criterion_id: str = Field(
        ...,
        min_length=1,
    )
    title: str = Field(
        ...,
        min_length=1,
    )
    criterion_type: CriterionType = Field(
        default=CriterionType.OTHER,
    )
    description: str = Field(
        ...,
        min_length=1,
    )
    maximum_marks: float | None = Field(
        default=None,
        ge=0.0,
    )
    scoring_method: str = Field(
        ...,
        min_length=1,
        description="Tender scoring logic stated in readable form.",
    )
    scoring_bands: list[ScoringBand] = Field(
        default_factory=list,
    )
    evidence_required: list[str] = Field(
        default_factory=list,
    )
    citations: list[TenderCitation] = Field(
        default_factory=list,
    )
    confidence: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
    )
    requires_human_review: bool = Field(
        default=False,
    )
    review_reason: str | None = Field(
        default=None,
    )

    @model_validator(mode="after")
    def validate_citations(self) -> ScoringCriterion:
        """Flag scoring criteria without citations."""

        if not self.citations:
            self.requires_human_review = True

            if not self.review_reason:
                self.review_reason = (
                    "No supporting tender citation was extracted."
                )

        return self


class TenderDeadline(BaseModel):
    """One important date or deadline from the tender."""

    model_config = ConfigDict(extra="forbid")

    event_name: str = Field(
        ...,
        min_length=1,
    )
    date_text: str = Field(
        ...,
        min_length=1,
        description="Date exactly as stated in the tender.",
    )
    normalized_date: str | None = Field(
        default=None,
        description="ISO-formatted date when confidently available.",
    )
    citations: list[TenderCitation] = Field(
        default_factory=list,
    )
    confidence: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
    )


class TenderRisk(BaseModel):
    """One contractual, commercial, delivery, or compliance risk."""

    model_config = ConfigDict(extra="forbid")

    risk_id: str = Field(
        ...,
        min_length=1,
    )
    title: str = Field(
        ...,
        min_length=1,
    )
    description: str = Field(
        ...,
        min_length=1,
    )
    severity: str = Field(
        default="medium",
        description="Expected values: low, medium, high, or critical.",
    )
    citations: list[TenderCitation] = Field(
        default_factory=list,
    )
    requires_human_review: bool = Field(
        default=False,
    )


class TenderChunkAnalysis(BaseModel):
    """Structured extraction result returned for one tender chunk."""

    model_config = ConfigDict(extra="forbid")

    chunk_id: str = Field(
        ...,
        min_length=1,
    )
    page_start: int = Field(
        ...,
        ge=1,
    )
    page_end: int = Field(
        ...,
        ge=1,
    )
    metadata_candidates: list[TenderMetadataCandidate] = Field(
        default_factory=list,
    )
    scope_statements: list[str] = Field(
        default_factory=list,
    )
    deliverables: list[str] = Field(
        default_factory=list,
    )
    eligibility_criteria: list[EligibilityCriterion] = Field(
        default_factory=list,
    )
    scoring_criteria: list[ScoringCriterion] = Field(
        default_factory=list,
    )
    deadlines: list[TenderDeadline] = Field(
        default_factory=list,
    )
    risks: list[TenderRisk] = Field(
        default_factory=list,
    )
    required_documents: list[str] = Field(
        default_factory=list,
    )
    ambiguities: list[str] = Field(
        default_factory=list,
    )
    notes: list[str] = Field(
        default_factory=list,
    )


class TenderAnalysisResult(BaseModel):
    """Consolidated structured analysis of a complete tender package."""

    model_config = ConfigDict(extra="forbid")

    source_filename: str = Field(
        ...,
        min_length=1,
    )
    title: str | None = None
    reference_number: str | None = None
    issuing_authority: str | None = None
    tender_category: str | None = None
    location: str | None = None
    submission_deadline: str | None = None
    pre_bid_date: str | None = None
    tender_fee: str | None = None
    emd_amount: str | None = None
    estimated_value: str | None = None
    contract_duration: str | None = None
    minimum_technical_score: float | None = Field(
        default=None,
        ge=0.0,
    )

    executive_summary: str = Field(
        default="",
    )
    scope_summary: str = Field(
        default="",
    )
    deliverables: list[str] = Field(
        default_factory=list,
    )
    eligibility_criteria: list[EligibilityCriterion] = Field(
        default_factory=list,
    )
    scoring_criteria: list[ScoringCriterion] = Field(
        default_factory=list,
    )
    deadlines: list[TenderDeadline] = Field(
        default_factory=list,
    )
    risks: list[TenderRisk] = Field(
        default_factory=list,
    )
    required_documents: list[str] = Field(
        default_factory=list,
    )
    ambiguities: list[str] = Field(
        default_factory=list,
    )
    source_chunk_ids: list[str] = Field(
        default_factory=list,
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
    )

    @property
    def maximum_available_marks(self) -> float:
        """Return the sum of stated maximum marks."""

        return sum(
            criterion.maximum_marks or 0.0
            for criterion in self.scoring_criteria
        )

    @property
    def mandatory_criteria_count(self) -> int:
        """Return the number of mandatory eligibility criteria."""

        return sum(
            criterion.mandatory
            for criterion in self.eligibility_criteria
        )

    @property
    def criteria_requiring_review_count(self) -> int:
        """Return the number of criteria marked for human review."""

        eligibility_count = sum(
            criterion.requires_human_review
            for criterion in self.eligibility_criteria
        )

        scoring_count = sum(
            criterion.requires_human_review
            for criterion in self.scoring_criteria
        )

        return eligibility_count + scoring_count