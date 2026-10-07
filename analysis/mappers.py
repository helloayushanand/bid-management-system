"""Map small LLM DTOs into the rich internal application models."""

from __future__ import annotations

from models import (
    AssessmentStatus,
    CompanyEvidence,
    ConfidenceLevel,
    ContextStatus,
    CriterionType,
    EligibilityAssessment,
    EligibilityCriterion,
    RequirementCategory,
    ScoringAssessment,
    ScoringCriterion,
    TenderAssessmentResult,
    TenderChunkAnalysis,
    TenderCitation,
    TenderDeadline,
    TenderMetadataCandidate,
    TenderRisk,
)
from models.llm_dtos import SimpleChunkAnalysis, SimpleCompanyAssessment


_STATUS_MAP = {
    "pass": AssessmentStatus.PASS,
    "fail": AssessmentStatus.FAIL,
    "partial": AssessmentStatus.PARTIAL,
    "unknown": AssessmentStatus.UNKNOWN,
    "not_applicable": AssessmentStatus.NOT_APPLICABLE,
    "not applicable": AssessmentStatus.NOT_APPLICABLE,
}


def _status(value: str) -> AssessmentStatus:
    return _STATUS_MAP.get(value.strip().lower(), AssessmentStatus.UNKNOWN)


def _citation(
    *,
    filename: str,
    page: int,
    excerpt: str,
) -> TenderCitation:
    return TenderCitation(
        document_name=filename,
        page_number=page,
        excerpt=excerpt.strip() or "Citation text unavailable.",
    )


def map_simple_chunk(
    simple: SimpleChunkAnalysis,
    *,
    source_filename: str,
) -> TenderChunkAnalysis:
    """Convert one simple LLM chunk response into the internal model."""

    metadata = [
        TenderMetadataCandidate(
            field_name=item.field,
            value=item.value,
            citations=[
                _citation(
                    filename=source_filename,
                    page=item.page,
                    excerpt=f"{item.field}: {item.value}",
                )
            ],
            confidence=0.75,
        )
        for item in simple.metadata
    ]

    eligibility = []
    for index, item in enumerate(simple.eligibility, start=1):
        eligibility.append(
            EligibilityCriterion(
                criterion_id=f"{simple.chunk_id}-ELG-{index:03d}",
                title=item.title,
                criterion_type=CriterionType.OTHER,
                category=RequirementCategory.MANDATORY_ELIGIBILITY,
                mandatory=item.mandatory,
                requirement=item.requirement,
                threshold=item.threshold,
                evidence_required=item.evidence_required,
                citations=[
                    _citation(
                        filename=source_filename,
                        page=item.page,
                        excerpt=item.excerpt,
                    )
                ],
                confidence=0.75,
                confidence_level=ConfidenceLevel.MEDIUM,
                requires_human_review=False,
            )
        )

    scoring = []
    for index, item in enumerate(simple.scoring, start=1):
        scoring.append(
            ScoringCriterion(
                criterion_id=f"{simple.chunk_id}-SCR-{index:03d}",
                title=item.title,
                criterion_type=CriterionType.OTHER,
                description=item.description,
                maximum_marks=item.maximum_marks,
                scoring_method=item.scoring_method,
                evidence_required=item.evidence_required,
                citations=[
                    _citation(
                        filename=source_filename,
                        page=item.page,
                        excerpt=item.excerpt,
                    )
                ],
                confidence=0.75,
                requires_human_review=False,
            )
        )

    deadlines = [
        TenderDeadline(
            event_name=item.event,
            date_text=item.date,
            citations=[
                _citation(
                    filename=source_filename,
                    page=item.page,
                    excerpt=item.excerpt,
                )
            ],
            confidence=0.75,
        )
        for item in simple.deadlines
    ]

    risks = [
        TenderRisk(
            risk_id=f"{simple.chunk_id}-RSK-{index:03d}",
            title=item.title,
            description=item.description,
            severity=item.severity.lower(),
            citations=[
                _citation(
                    filename=source_filename,
                    page=item.page,
                    excerpt=item.excerpt,
                )
            ],
        )
        for index, item in enumerate(simple.risks, start=1)
    ]

    return TenderChunkAnalysis(
        chunk_id=simple.chunk_id,
        page_start=simple.page_start,
        page_end=simple.page_end,
        metadata_candidates=metadata,
        scope_statements=simple.scope,
        deliverables=simple.deliverables,
        eligibility_criteria=eligibility,
        scoring_criteria=scoring,
        deadlines=deadlines,
        risks=risks,
        required_documents=simple.required_documents,
        ambiguities=simple.ambiguities,
    )


def map_simple_assessment(
    simple: SimpleCompanyAssessment,
    *,
    tender_analysis,
) -> TenderAssessmentResult:
    """Convert a simple company assessment into the internal model."""

    eligibility_by_id = {
        item.criterion_id: item
        for item in tender_analysis.eligibility_criteria
    }
    scoring_by_id = {
        item.criterion_id: item
        for item in tender_analysis.scoring_criteria
    }

    eligibility_results = []
    for item in simple.eligibility:
        criterion = eligibility_by_id.get(item.criterion_id)
        if criterion is None:
            continue

        evidence = [
            CompanyEvidence(
                evidence_type="synthetic_profile_reference",
                title=reference,
                value=reference,
                source_reference=reference,
                verified=False,
            )
            for reference in item.evidence_references
        ]

        eligibility_results.append(
            EligibilityAssessment(
                criterion_id=criterion.criterion_id,
                criterion_title=criterion.title,
                mandatory=criterion.mandatory,
                status=_status(item.status),
                tender_requirement=criterion.requirement,
                company_observation=item.company_observation,
                explanation=item.explanation,
                tender_citations=criterion.citations,
                company_evidence=evidence,
                missing_evidence=item.missing_evidence,
                confidence=0.7 if evidence else 0.4,
                requires_human_review=not bool(evidence),
            )
        )

    scoring_results = []
    for item in simple.scoring:
        criterion = scoring_by_id.get(item.criterion_id)
        if criterion is None:
            continue

        estimated = item.estimated_marks
        if (
            estimated is not None
            and criterion.maximum_marks is not None
        ):
            estimated = min(estimated, criterion.maximum_marks)

        evidence = [
            CompanyEvidence(
                evidence_type="synthetic_profile_reference",
                title=reference,
                value=reference,
                source_reference=reference,
                verified=False,
            )
            for reference in item.evidence_references
        ]

        scoring_results.append(
            ScoringAssessment(
                criterion_id=criterion.criterion_id,
                criterion_title=criterion.title,
                maximum_marks=criterion.maximum_marks,
                estimated_marks=estimated,
                status=_status(item.status),
                tender_scoring_method=criterion.scoring_method,
                company_observation=item.company_observation,
                explanation=item.explanation,
                tender_citations=criterion.citations,
                company_evidence=evidence,
                missing_evidence=item.missing_evidence,
                confidence=0.7 if evidence else 0.4,
                requires_human_review=not bool(evidence),
            )
        )

    return TenderAssessmentResult(
        source_filename=tender_analysis.source_filename,
        tender_title=tender_analysis.title,
        tender_reference_number=tender_analysis.reference_number,
        company_name=simple.company_name,
        context_status=ContextStatus.SYNTHETIC_UNVERIFIED,
        production_decision_allowed=False,
        eligibility_assessments=eligibility_results,
        scoring_assessments=scoring_results,
        minimum_technical_score=tender_analysis.minimum_technical_score,
        strengths=simple.strengths,
        concerns=simple.concerns,
        missing_information=simple.missing_information,
        next_actions=simple.next_actions,
    )
