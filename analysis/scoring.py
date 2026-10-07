"""Deterministic scoring and recommendation logic."""

from __future__ import annotations

from models import (
    AssessmentStatus,
    RecommendationLabel,
    TenderAssessmentResult,
)


def calculate_score_totals(
    assessment: TenderAssessmentResult,
) -> tuple[float | None, float | None, float | None]:
    """Calculate expected marks, maximum marks, and percentage."""

    scored_items = [
        item
        for item in assessment.scoring_assessments
        if item.maximum_marks is not None
    ]

    if not scored_items:
        return None, None, None

    maximum_marks = sum(
        item.maximum_marks or 0.0
        for item in scored_items
    )

    known_estimates = [
        item
        for item in scored_items
        if item.estimated_marks is not None
    ]

    if not known_estimates:
        return None, maximum_marks, None

    expected_marks = sum(
        item.estimated_marks or 0.0
        for item in known_estimates
    )

    percentage = (
        round((expected_marks / maximum_marks) * 100.0, 2)
        if maximum_marks > 0
        else None
    )

    return expected_marks, maximum_marks, percentage


def determine_recommendation(
    assessment: TenderAssessmentResult,
) -> tuple[RecommendationLabel, str]:
    """Calculate the overall colour label from criterion outcomes."""

    mandatory_failures = [
        item
        for item in assessment.eligibility_assessments
        if item.mandatory and item.status == AssessmentStatus.FAIL
    ]

    if mandatory_failures:
        titles = ", ".join(
            item.criterion_title
            for item in mandatory_failures[:3]
        )
        return (
            RecommendationLabel.RED,
            "One or more mandatory eligibility criteria have confirmed "
            f"failures: {titles}.",
        )

    unresolved_mandatory = [
        item
        for item in assessment.eligibility_assessments
        if item.mandatory
        and item.status in {
            AssessmentStatus.PARTIAL,
            AssessmentStatus.UNKNOWN,
        }
    ]

    if unresolved_mandatory:
        return (
            RecommendationLabel.ORANGE,
            "No mandatory failure is confirmed, but one or more mandatory "
            "criteria remain partial or unknown.",
        )

    if assessment.minimum_technical_score is not None:
        if assessment.expected_score_percentage is None:
            return (
                RecommendationLabel.ORANGE,
                "The tender specifies a minimum technical score, but the "
                "expected score could not be calculated reliably.",
            )

        if (
            assessment.expected_score_percentage
            < assessment.minimum_technical_score
        ):
            return (
                RecommendationLabel.RED,
                "The estimated technical score is below the tender's "
                "stated minimum technical score.",
            )

    review_items = [
        item
        for item in assessment.eligibility_assessments
        if item.requires_human_review
    ] + [
        item
        for item in assessment.scoring_assessments
        if item.requires_human_review
    ]

    if review_items or assessment.missing_information:
        return (
            RecommendationLabel.ORANGE,
            "No confirmed disqualification was found, but evidence gaps or "
            "human-review items remain.",
        )

    if not assessment.eligibility_assessments:
        return (
            RecommendationLabel.ORANGE,
            "No eligibility criteria were available for a reliable decision.",
        )

    return (
        RecommendationLabel.GREEN,
        "All extracted mandatory criteria are assessed as satisfied and no "
        "critical unresolved assessment items remain.",
    )


def finalize_assessment(
    assessment: TenderAssessmentResult,
) -> TenderAssessmentResult:
    """Apply deterministic totals, safety flags, and recommendation."""

    expected, maximum, percentage = calculate_score_totals(assessment)
    assessment.expected_marks = expected
    assessment.maximum_marks = maximum
    assessment.expected_score_percentage = percentage

    label, reason = determine_recommendation(assessment)
    assessment.recommendation = label
    assessment.recommendation_reason = reason

    if assessment.context_status.value == "synthetic_unverified":
        assessment.production_decision_allowed = False

    return assessment
