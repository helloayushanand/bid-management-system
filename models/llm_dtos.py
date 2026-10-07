"""Small LLM-facing data transfer objects.

These models intentionally avoid the deeply nested internal application schema.
Python mapping code enriches these objects after the LLM response is validated.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class SimpleMetadataItem(BaseModel):
    field: str
    value: str
    page: int = Field(ge=1)


class SimpleRequirementItem(BaseModel):
    title: str
    requirement: str
    mandatory: bool = True
    threshold: str | None = None
    evidence_required: list[str] = Field(default_factory=list)
    page: int = Field(ge=1)
    excerpt: str


class SimpleScoringItem(BaseModel):
    title: str
    description: str
    maximum_marks: float | None = Field(default=None, ge=0)
    scoring_method: str
    evidence_required: list[str] = Field(default_factory=list)
    page: int = Field(ge=1)
    excerpt: str


class SimpleDeadlineItem(BaseModel):
    event: str
    date: str
    page: int = Field(ge=1)
    excerpt: str


class SimpleRiskItem(BaseModel):
    title: str
    description: str
    severity: str = "medium"
    page: int = Field(ge=1)
    excerpt: str


class SimpleChunkAnalysis(BaseModel):
    chunk_id: str
    page_start: int = Field(ge=1)
    page_end: int = Field(ge=1)
    metadata: list[SimpleMetadataItem] = Field(default_factory=list)
    eligibility: list[SimpleRequirementItem] = Field(default_factory=list)
    scoring: list[SimpleScoringItem] = Field(default_factory=list)
    scope: list[str] = Field(default_factory=list)
    deliverables: list[str] = Field(default_factory=list)
    deadlines: list[SimpleDeadlineItem] = Field(default_factory=list)
    risks: list[SimpleRiskItem] = Field(default_factory=list)
    required_documents: list[str] = Field(default_factory=list)
    ambiguities: list[str] = Field(default_factory=list)


class SimpleEligibilityAssessment(BaseModel):
    criterion_id: str
    status: str
    company_observation: str
    explanation: str
    evidence_references: list[str] = Field(default_factory=list)
    missing_evidence: list[str] = Field(default_factory=list)


class SimpleScoringAssessment(BaseModel):
    criterion_id: str
    status: str
    estimated_marks: float | None = Field(default=None, ge=0)
    company_observation: str
    explanation: str
    evidence_references: list[str] = Field(default_factory=list)
    missing_evidence: list[str] = Field(default_factory=list)


class SimpleCompanyAssessment(BaseModel):
    company_name: str
    eligibility: list[SimpleEligibilityAssessment] = Field(default_factory=list)
    scoring: list[SimpleScoringAssessment] = Field(default_factory=list)
    strengths: list[str] = Field(default_factory=list)
    concerns: list[str] = Field(default_factory=list)
    missing_information: list[str] = Field(default_factory=list)
    next_actions: list[str] = Field(default_factory=list)
