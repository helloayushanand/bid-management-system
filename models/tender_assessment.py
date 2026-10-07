"""Models for assessing tender requirements against company context."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from models.tender_analysis import TenderCitation


class AssessmentStatus(str, Enum):
    """Possible assessment outcomes for a tender criterion."""

    PASS = "pass"
    FAIL = "fail"
    PARTIAL = "partial"
    UNKNOWN = "unknown"
    NOT_APPLICABLE = "not_applicable"


class RecommendationLabel(str, Enum):
    """Overall recommendation labels displayed in the application."""

    GREEN = "green"
    ORANGE = "orange"
    RED = "red"


class ContextStatus(str, Enum):
    """Verification status of company context used for assessment."""

    SYNTHETIC_UNVERIFIED = "synthetic_unverified"
    VERIFIED = "verified"


class CompanyEvidence(BaseModel):
    """Company information used to assess one tender criterion."""

    model_config = ConfigDict(extra="forbid")

    evidence_type: str = Field(
        ...,
        min_length=1,
        description="Type of company record or synthetic fact.",
    )
    title: str = Field(
        ...,
        min_length=1,
    )
    value: str = Field(
        ...,
        min_length=1,
    )
    source_reference: str | None = Field(
        default=None,
        description="Source document or synthetic profile path.",
    )
    verified: bool = Field(
        default=False,
    )


class EligibilityAssessment(BaseModel):
    """Assessment of one tender eligibility criterion."""

    model_config = ConfigDict(extra="forbid")

    criterion_id: str = Field(
        ...,
        min_length=1,
    )
    criterion_title: str = Field(
        ...,
        min_length=1,
    )
    mandatory: bool
    status: AssessmentStatus
    tender_requirement: str = Field(
        ...,
        min_length=1,
    )
    company_observation: str = Field(
        ...,
        min_length=1,
    )
    explanation: str = Field(
        ...,
        min_length=1,
    )
    tender_citations: list[TenderCitation] = Field(
        default_factory=list,
    )
    company_evidence: list[CompanyEvidence] = Field(
        default_factory=list,
    )
    missing_evidence: list[str] = Field(
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
    review_reason: str | None = None

    @model_validator(mode="after")
    def validate_assessment(self) -> EligibilityAssessment:
        """Apply transparency requirements to uncertain assessments."""

        if self.status in {
            AssessmentStatus.PARTIAL,
            AssessmentStatus.UNKNOWN,
        }:
            self.requires_human_review = True

            if not self.review_reason:
                self.review_reason = (
                    "The available context does not establish a "
                    "definitive compliance result."
                )

        if not self.company_evidence:
            self.requires_human_review = True

            if not self.review_reason:
                self.review_reason = (
                    "No company evidence supports this assessment."
                )

        return self


class ScoringAssessment(BaseModel):
    """Expected score for one technical evaluation criterion."""

    model_config = ConfigDict(extra="forbid")

    criterion_id: str = Field(
        ...,
        min_length=1,
    )
    criterion_title: str = Field(
        ...,
        min_length=1,
    )
    maximum_marks: float | None = Field(
        default=None,
        ge=0.0,
    )
    estimated_marks: float | None = Field(
        default=None,
        ge=0.0,
    )
    status: AssessmentStatus
    tender_scoring_method: str = Field(
        ...,
        min_length=1,
    )
    company_observation: str = Field(
        ...,
        min_length=1,
    )
    explanation: str = Field(
        ...,
        min_length=1,
    )
    tender_citations: list[TenderCitation] = Field(
        default_factory=list,
    )
    company_evidence: list[CompanyEvidence] = Field(
        default_factory=list,
    )
    missing_evidence: list[str] = Field(
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

    @model_validator(mode="after")
    def validate_estimated_marks(self) -> ScoringAssessment:
        """Ensure estimated marks do not exceed stated maximum marks."""

        if (
            self.maximum_marks is not None
            and self.estimated_marks is not None
            and self.estimated_marks > self.maximum_marks
        ):
            raise ValueError(
                "Estimated marks cannot exceed maximum marks."
            )

        if self.status in {
            AssessmentStatus.PARTIAL,
            AssessmentStatus.UNKNOWN,
        }:
            self.requires_human_review = True

        return self


class TenderAssessmentResult(BaseModel):
    """Complete company assessment for one analyzed tender."""

    model_config = ConfigDict(extra="forbid")

    source_filename: str = Field(
        ...,
        min_length=1,
    )
    tender_title: str | None = None
    tender_reference_number: str | None = None

    company_name: str = Field(
        ...,
        min_length=1,
    )
    context_status: ContextStatus = Field(
        default=ContextStatus.SYNTHETIC_UNVERIFIED,
    )
    production_decision_allowed: bool = Field(
        default=False,
    )
    context_warning: str = Field(
        default=(
            "Testing data only. Company information has not been "
            "verified and must not be used for a real bid decision."
        ),
    )

    eligibility_assessments: list[EligibilityAssessment] = Field(
        default_factory=list,
    )
    scoring_assessments: list[ScoringAssessment] = Field(
        default_factory=list,
    )

    expected_marks: float | None = Field(
        default=None,
        ge=0.0,
    )
    maximum_marks: float | None = Field(
        default=None,
        ge=0.0,
    )
    expected_score_percentage: float | None = Field(
        default=None,
        ge=0.0,
        le=100.0,
    )
    minimum_technical_score: float | None = Field(
        default=None,
        ge=0.0,
    )

    recommendation: RecommendationLabel = Field(
        default=RecommendationLabel.ORANGE,
    )
    recommendation_reason: str = Field(
        default="Assessment requires review.",
    )
    strengths: list[str] = Field(
        default_factory=list,
    )
    concerns: list[str] = Field(
        default_factory=list,
    )
    missing_information: list[str] = Field(
        default_factory=list,
    )
    next_actions: list[str] = Field(
        default_factory=list,
    )

    token_usage: dict[str, int] = Field(
        default_factory=dict,
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
    )

    @model_validator(mode="after")
    def enforce_context_safety(self) -> TenderAssessmentResult:
        """Prevent synthetic company context from appearing production-ready."""

        if self.context_status == ContextStatus.SYNTHETIC_UNVERIFIED:
            self.production_decision_allowed = False

        return self

    @property
    def mandatory_failure_count(self) -> int:
        """Return confirmed failures among mandatory criteria."""

        return sum(
            assessment.mandatory
            and assessment.status == AssessmentStatus.FAIL
            for assessment in self.eligibility_assessments
        )

    @property
    def unresolved_mandatory_count(self) -> int:
        """Return partial or unknown mandatory assessments."""

        unresolved_statuses = {
            AssessmentStatus.PARTIAL,
            AssessmentStatus.UNKNOWN,
        }

        return sum(
            assessment.mandatory
            and assessment.status in unresolved_statuses
            for assessment in self.eligibility_assessments
        )

    @property
    def review_item_count(self) -> int:
        """Return the number of assessments requiring manual review."""

        eligibility_count = sum(
            assessment.requires_human_review
            for assessment in self.eligibility_assessments
        )

        scoring_count = sum(
            assessment.requires_human_review
            for assessment in self.scoring_assessments
        )

        return eligibility_count + scoring_count