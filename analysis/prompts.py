"""Compact prompt builders for simplified LLM JSON responses."""

from __future__ import annotations

import json
from typing import Any

from analysis.chunker import TenderChunk
from models import TenderAnalysisResult


TENDER_EXTRACTION_SYSTEM_PROMPT = """
Extract tender information from the supplied pages.
Use only the supplied text. Do not guess.
Return one JSON object only, with these top-level fields:
chunk_id, page_start, page_end, metadata, eligibility, scoring, scope,
deliverables, deadlines, risks, required_documents, ambiguities.
Use empty arrays when nothing is found.
Every eligibility, scoring, deadline, and risk item must use a page number
visible in the supplied page markers.
""".strip()


COMPANY_ASSESSMENT_SYSTEM_PROMPT = """
Compare tender criteria with the supplied synthetic company profile.
Return one JSON object only with these top-level fields:
company_name, eligibility, scoring, strengths, concerns,
missing_information, next_actions.
Allowed status values are pass, fail, partial, unknown, not_applicable.
Use only supplied company facts. Do not invent evidence.
Evidence references must be profile paths such as synthetic.projects.syn_proj_001.
""".strip()


def build_tender_chunk_prompt(chunk: TenderChunk) -> str:
    return (
        "Analyze this tender chunk. Preserve the exact chunk ID and page range.\n\n"
        f"{chunk.to_prompt_text()}"
    )


def build_company_assessment_prompt(
    *,
    tender_analysis: TenderAnalysisResult,
    company_context: dict[str, Any],
) -> str:
    compact_tender = {
        "source_filename": tender_analysis.source_filename,
        "title": tender_analysis.title,
        "reference_number": tender_analysis.reference_number,
        "minimum_technical_score": tender_analysis.minimum_technical_score,
        "eligibility": [
            {
                "criterion_id": item.criterion_id,
                "title": item.title,
                "mandatory": item.mandatory,
                "requirement": item.requirement,
                "threshold": item.threshold,
            }
            for item in tender_analysis.eligibility_criteria
        ],
        "scoring": [
            {
                "criterion_id": item.criterion_id,
                "title": item.title,
                "maximum_marks": item.maximum_marks,
                "scoring_method": item.scoring_method,
            }
            for item in tender_analysis.scoring_criteria
        ],
    }

    payload = {
        "tender": compact_tender,
        "company_context": company_context,
    }
    return (
        "Assess the tender criteria using only the supplied synthetic context.\n"
        "Return assessments using the exact criterion IDs.\n\n"
        f"INPUT JSON:\n{json.dumps(payload, ensure_ascii=False)}"
    )
