"""Deterministic utilities for merging tender chunk analyses."""

from __future__ import annotations

from collections.abc import Iterable
from copy import deepcopy
from typing import TypeVar

from models import (
    EligibilityCriterion,
    ScoringCriterion,
    TenderChunkAnalysis,
    TenderCitation,
    TenderDeadline,
    TenderMetadataCandidate,
    TenderRisk,
)


T = TypeVar("T")


class ResultMergeError(ValueError):
    """Raised when chunk-analysis results cannot be merged."""


def _normalize_text(value: str | None) -> str:
    """Normalize text for deterministic comparison."""

    if not value:
        return ""

    return " ".join(value.lower().split())


def _unique_strings(values: Iterable[str]) -> list[str]:
    """Return non-empty strings while preserving first-seen order."""

    output: list[str] = []
    seen: set[str] = set()

    for value in values:
        cleaned = " ".join(value.split()).strip()
        key = _normalize_text(cleaned)

        if cleaned and key not in seen:
            seen.add(key)
            output.append(cleaned)

    return output


def _citation_key(citation: TenderCitation) -> tuple[str, int, str]:
    """Return a stable deduplication key for one citation."""

    return (
        _normalize_text(citation.document_name),
        citation.page_number,
        _normalize_text(citation.excerpt),
    )


def merge_citations(
    *citation_groups: Iterable[TenderCitation],
) -> list[TenderCitation]:
    """Merge citations while preserving first-seen order."""

    merged: list[TenderCitation] = []
    seen: set[tuple[str, int, str]] = set()

    for group in citation_groups:
        for citation in group:
            key = _citation_key(citation)

            if key not in seen:
                seen.add(key)
                merged.append(deepcopy(citation))

    return merged


def _eligibility_key(
    criterion: EligibilityCriterion,
) -> tuple[str, str, str, str, bool]:
    """Return a deterministic key for eligibility deduplication."""

    return (
        _normalize_text(criterion.title),
        _normalize_text(criterion.requirement),
        _normalize_text(criterion.threshold),
        _normalize_text(criterion.lookback_period),
        criterion.mandatory,
    )


def _scoring_key(
    criterion: ScoringCriterion,
) -> tuple[str, str, str, float | None]:
    """Return a deterministic key for scoring deduplication."""

    return (
        _normalize_text(criterion.title),
        _normalize_text(criterion.description),
        _normalize_text(criterion.scoring_method),
        criterion.maximum_marks,
    )


def _deadline_key(
    deadline: TenderDeadline,
) -> tuple[str, str, str]:
    """Return a deterministic key for deadline deduplication."""

    return (
        _normalize_text(deadline.event_name),
        _normalize_text(deadline.date_text),
        _normalize_text(deadline.normalized_date),
    )


def _risk_key(risk: TenderRisk) -> tuple[str, str]:
    """Return a deterministic key for risk deduplication."""

    return (
        _normalize_text(risk.title),
        _normalize_text(risk.description),
    )


def _metadata_key(
    candidate: TenderMetadataCandidate,
) -> tuple[str, str]:
    """Return a deterministic key for metadata deduplication."""

    return (
        _normalize_text(candidate.field_name),
        _normalize_text(candidate.value),
    )


def merge_eligibility_criteria(
    criteria: Iterable[EligibilityCriterion],
) -> list[EligibilityCriterion]:
    """Merge exactly matching eligibility criteria and their evidence."""

    merged: dict[
        tuple[str, str, str, str, bool],
        EligibilityCriterion,
    ] = {}

    for criterion in criteria:
        key = _eligibility_key(criterion)

        if key not in merged:
            merged[key] = deepcopy(criterion)
            continue

        existing = merged[key]
        existing.citations = merge_citations(
            existing.citations,
            criterion.citations,
        )
        existing.evidence_required = _unique_strings(
            [
                *existing.evidence_required,
                *criterion.evidence_required,
            ]
        )
        existing.confidence = max(
            existing.confidence,
            criterion.confidence,
        )
        existing.requires_human_review = (
            existing.requires_human_review
            or criterion.requires_human_review
        )

        review_reasons = _unique_strings(
            [
                existing.review_reason or "",
                criterion.review_reason or "",
            ]
        )
        existing.review_reason = (
            "; ".join(review_reasons)
            if review_reasons
            else None
        )

    output = list(merged.values())

    for index, criterion in enumerate(output, start=1):
        criterion.criterion_id = f"ELG-{index:03d}"

    return output


def merge_scoring_criteria(
    criteria: Iterable[ScoringCriterion],
) -> list[ScoringCriterion]:
    """Merge matching scoring criteria and their evidence."""

    merged: dict[
        tuple[str, str, str, float | None],
        ScoringCriterion,
    ] = {}

    for criterion in criteria:
        key = _scoring_key(criterion)

        if key not in merged:
            merged[key] = deepcopy(criterion)
            continue

        existing = merged[key]
        existing.citations = merge_citations(
            existing.citations,
            criterion.citations,
        )
        existing.evidence_required = _unique_strings(
            [
                *existing.evidence_required,
                *criterion.evidence_required,
            ]
        )

        existing_bands = {
            (
                _normalize_text(band.condition),
                band.marks,
            )
            for band in existing.scoring_bands
        }

        for band in criterion.scoring_bands:
            band_key = (
                _normalize_text(band.condition),
                band.marks,
            )

            if band_key not in existing_bands:
                existing.scoring_bands.append(deepcopy(band))
                existing_bands.add(band_key)

        existing.confidence = max(
            existing.confidence,
            criterion.confidence,
        )
        existing.requires_human_review = (
            existing.requires_human_review
            or criterion.requires_human_review
        )

        review_reasons = _unique_strings(
            [
                existing.review_reason or "",
                criterion.review_reason or "",
            ]
        )
        existing.review_reason = (
            "; ".join(review_reasons)
            if review_reasons
            else None
        )

    output = list(merged.values())

    for index, criterion in enumerate(output, start=1):
        criterion.criterion_id = f"SCR-{index:03d}"

    return output


def merge_deadlines(
    deadlines: Iterable[TenderDeadline],
) -> list[TenderDeadline]:
    """Merge matching tender deadlines."""

    merged: dict[tuple[str, str, str], TenderDeadline] = {}

    for deadline in deadlines:
        key = _deadline_key(deadline)

        if key not in merged:
            merged[key] = deepcopy(deadline)
            continue

        existing = merged[key]
        existing.citations = merge_citations(
            existing.citations,
            deadline.citations,
        )
        existing.confidence = max(
            existing.confidence,
            deadline.confidence,
        )

    return list(merged.values())


def merge_risks(risks: Iterable[TenderRisk]) -> list[TenderRisk]:
    """Merge matching tender risks."""

    merged: dict[tuple[str, str], TenderRisk] = {}

    for risk in risks:
        key = _risk_key(risk)

        if key not in merged:
            merged[key] = deepcopy(risk)
            continue

        existing = merged[key]
        existing.citations = merge_citations(
            existing.citations,
            risk.citations,
        )
        existing.requires_human_review = (
            existing.requires_human_review
            or risk.requires_human_review
        )

    output = list(merged.values())

    for index, risk in enumerate(output, start=1):
        risk.risk_id = f"RSK-{index:03d}"

    return output


def merge_metadata_candidates(
    candidates: Iterable[TenderMetadataCandidate],
) -> list[TenderMetadataCandidate]:
    """Merge matching metadata values while preserving alternatives."""

    merged: dict[
        tuple[str, str],
        TenderMetadataCandidate,
    ] = {}

    for candidate in candidates:
        key = _metadata_key(candidate)

        if key not in merged:
            merged[key] = deepcopy(candidate)
            continue

        existing = merged[key]
        existing.citations = merge_citations(
            existing.citations,
            candidate.citations,
        )
        existing.confidence = max(
            existing.confidence,
            candidate.confidence,
        )

    return list(merged.values())


def merge_chunk_analyses(
    analyses: list[TenderChunkAnalysis],
) -> dict[str, object]:
    """
    Merge chunk-level results into a consolidation-ready dictionary.

    This does not create the final TenderAnalysisResult. It performs safe,
    deterministic deduplication before the final consolidation LLM call.
    """

    if not analyses:
        raise ResultMergeError(
            "At least one tender chunk analysis is required."
        )

    chunk_ids = [analysis.chunk_id for analysis in analyses]

    if len(chunk_ids) != len(set(chunk_ids)):
        raise ResultMergeError(
            "Duplicate chunk IDs were found in chunk analyses."
        )

    metadata_candidates = merge_metadata_candidates(
        candidate
        for analysis in analyses
        for candidate in analysis.metadata_candidates
    )
    eligibility_criteria = merge_eligibility_criteria(
        criterion
        for analysis in analyses
        for criterion in analysis.eligibility_criteria
    )
    scoring_criteria = merge_scoring_criteria(
        criterion
        for analysis in analyses
        for criterion in analysis.scoring_criteria
    )
    deadlines = merge_deadlines(
        deadline
        for analysis in analyses
        for deadline in analysis.deadlines
    )
    risks = merge_risks(
        risk
        for analysis in analyses
        for risk in analysis.risks
    )

    return {
        "source_chunk_ids": chunk_ids,
        "page_start": min(analysis.page_start for analysis in analyses),
        "page_end": max(analysis.page_end for analysis in analyses),
        "metadata_candidates": [
            item.model_dump(mode="json")
            for item in metadata_candidates
        ],
        "scope_statements": _unique_strings(
            statement
            for analysis in analyses
            for statement in analysis.scope_statements
        ),
        "deliverables": _unique_strings(
            item
            for analysis in analyses
            for item in analysis.deliverables
        ),
        "eligibility_criteria": [
            item.model_dump(mode="json")
            for item in eligibility_criteria
        ],
        "scoring_criteria": [
            item.model_dump(mode="json")
            for item in scoring_criteria
        ],
        "deadlines": [
            item.model_dump(mode="json")
            for item in deadlines
        ],
        "risks": [
            item.model_dump(mode="json")
            for item in risks
        ],
        "required_documents": _unique_strings(
            item
            for analysis in analyses
            for item in analysis.required_documents
        ),
        "ambiguities": _unique_strings(
            item
            for analysis in analyses
            for item in analysis.ambiguities
        ),
        "notes": _unique_strings(
            item
            for analysis in analyses
            for item in analysis.notes
        ),
    }
