"""Merge bounded company-assessment responses and calculate coverage."""
from __future__ import annotations
from models import AssessmentStatus, TenderAnalysisResult, TenderAssessmentResult


def _unique_by_id(items, attribute: str):
    output = []
    seen = set()
    for item in items:
        identifier = getattr(item, attribute)
        if identifier in seen:
            continue
        seen.add(identifier)
        output.append(item)
    return output


def merge_assessment_results(
    *,
    tender_analysis: TenderAnalysisResult,
    partial_results: list[TenderAssessmentResult],
) -> TenderAssessmentResult:
    """Merge partial results and add deterministic assessment coverage metadata."""
    if not partial_results:
        raise ValueError("At least one partial assessment result is required.")

    base = partial_results[0].model_copy(deep=True)
    eligibility = _unique_by_id(
        [item for result in partial_results for item in result.eligibility_assessments],
        "criterion_id",
    )
    scoring = _unique_by_id(
        [item for result in partial_results for item in result.scoring_assessments],
        "criterion_id",
    )

    expected_eligibility = {
        item.criterion_id for item in tender_analysis.eligibility_criteria
    }
    expected_scoring = {
        item.criterion_id for item in tender_analysis.scoring_criteria
    }
    assessed_eligibility = {item.criterion_id for item in eligibility}
    assessed_scoring = {item.criterion_id for item in scoring}
    missing_eligibility = sorted(expected_eligibility - assessed_eligibility)
    missing_scoring = sorted(expected_scoring - assessed_scoring)

    total_expected = len(expected_eligibility) + len(expected_scoring)
    total_assessed = len(assessed_eligibility) + len(assessed_scoring)
    coverage = round((total_assessed / total_expected) * 100, 2) if total_expected else 100.0

    base.eligibility_assessments = eligibility
    base.scoring_assessments = scoring
    base.strengths = list(dict.fromkeys(item for result in partial_results for item in result.strengths))
    base.concerns = list(dict.fromkeys(item for result in partial_results for item in result.concerns))
    base.missing_information = list(dict.fromkeys(item for result in partial_results for item in result.missing_information))
    base.next_actions = list(dict.fromkeys(item for result in partial_results for item in result.next_actions))

    if missing_eligibility:
        base.missing_information.append(
            "Unassessed eligibility criteria: " + ", ".join(missing_eligibility)
        )
    if missing_scoring:
        base.missing_information.append(
            "Unassessed scoring criteria: " + ", ".join(missing_scoring)
        )

    base.metadata.update(
        {
            "eligibility_criteria_count": len(expected_eligibility),
            "eligibility_assessed_count": len(assessed_eligibility),
            "scoring_criteria_count": len(expected_scoring),
            "scoring_assessed_count": len(assessed_scoring),
            "assessment_coverage_percentage": coverage,
            "missing_eligibility_criterion_ids": missing_eligibility,
            "missing_scoring_criterion_ids": missing_scoring,
            "assessment_complete": not missing_eligibility and not missing_scoring,
        }
    )
    return base
