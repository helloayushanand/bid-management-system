"""Split tender criteria into bounded company-assessment jobs."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Literal
from models import TenderAnalysisResult

AssessmentKind = Literal["eligibility", "scoring"]

@dataclass(frozen=True)
class AssessmentChunk:
    chunk_id: str
    kind: AssessmentKind
    criterion_ids: tuple[str, ...]
    tender_analysis: TenderAnalysisResult


def build_assessment_chunks(
    tender_analysis: TenderAnalysisResult,
    *,
    eligibility_batch_size: int = 4,
    scoring_batch_size: int = 4,
) -> list[AssessmentChunk]:
    """Create small criteria-only tender views for company assessment."""
    if eligibility_batch_size < 1 or scoring_batch_size < 1:
        raise ValueError("Assessment batch sizes must be positive.")

    chunks: list[AssessmentChunk] = []
    eligibility = list(tender_analysis.eligibility_criteria)
    scoring = list(tender_analysis.scoring_criteria)

    for offset in range(0, len(eligibility), eligibility_batch_size):
        items = eligibility[offset : offset + eligibility_batch_size]
        chunks.append(
            AssessmentChunk(
                chunk_id=f"eligibility-{offset // eligibility_batch_size + 1:04d}",
                kind="eligibility",
                criterion_ids=tuple(item.criterion_id for item in items),
                tender_analysis=tender_analysis.model_copy(
                    deep=True,
                    update={
                        "eligibility_criteria": items,
                        "scoring_criteria": [],
                    },
                ),
            )
        )

    for offset in range(0, len(scoring), scoring_batch_size):
        items = scoring[offset : offset + scoring_batch_size]
        chunks.append(
            AssessmentChunk(
                chunk_id=f"scoring-{offset // scoring_batch_size + 1:04d}",
                kind="scoring",
                criterion_ids=tuple(item.criterion_id for item in items),
                tender_analysis=tender_analysis.model_copy(
                    deep=True,
                    update={
                        "eligibility_criteria": [],
                        "scoring_criteria": items,
                    },
                ),
            )
        )

    return chunks
