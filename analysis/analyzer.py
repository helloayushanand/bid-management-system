"""Tender analysis with bounded, complete company-assessment batches."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Callable

from adapters import BaseLLMAdapter, LLMTokenUsage
from analysis.assessment_chunker import build_assessment_chunks
from analysis.assessment_merger import merge_assessment_results
from analysis.chunker import TenderChunk, chunk_document
from analysis.mappers import map_simple_assessment, map_simple_chunk
from analysis.prompts import (
    COMPANY_ASSESSMENT_SYSTEM_PROMPT,
    TENDER_EXTRACTION_SYSTEM_PROMPT,
    build_company_assessment_prompt,
    build_tender_chunk_prompt,
)
from analysis.result_merger import merge_chunk_analyses
from analysis.scoring import finalize_assessment
from company_context import validate_synthetic_profile
from config import AnalysisSettings
from models import (
    ContextStatus,
    DocumentExtractionResult,
    RecommendationLabel,
    TenderAnalysisResult,
    TenderAssessmentResult,
)
from models.llm_dtos import SimpleChunkAnalysis, SimpleCompanyAssessment

ProgressCallback = Callable[[str, int, int], None]


def classify_document(tender_analysis: TenderAnalysisResult) -> str:
    if tender_analysis.eligibility_criteria or tender_analysis.scoring_criteria:
        return "tender"

    indicators = [
        tender_analysis.reference_number,
        tender_analysis.submission_deadline,
        tender_analysis.tender_fee,
        tender_analysis.emd_amount,
        tender_analysis.estimated_value,
        tender_analysis.minimum_technical_score,
    ]
    if any(value not in {None, ""} for value in indicators):
        return "tender_like"
    if tender_analysis.risks or tender_analysis.scope_summary:
        return "non_tender"
    return "unknown"


def build_not_applicable_assessment(
    *,
    tender_analysis: TenderAnalysisResult,
    company_context: dict[str, Any],
    document_type: str,
    token_usage: dict[str, int],
) -> TenderAssessmentResult:
    company_name = company_context.get("company", {}).get(
        "legal_name",
        "Synthetic company profile",
    )
    return TenderAssessmentResult(
        source_filename=tender_analysis.source_filename,
        tender_title=tender_analysis.title,
        tender_reference_number=tender_analysis.reference_number,
        company_name=company_name,
        context_status=ContextStatus.SYNTHETIC_UNVERIFIED,
        production_decision_allowed=False,
        recommendation=RecommendationLabel.NOT_APPLICABLE,
        recommendation_reason=(
            "Company qualification was skipped because no tender eligibility "
            "or technical scoring criteria were extracted."
        ),
        concerns=[
            "No tender eligibility or scoring criteria were available for assessment."
        ],
        missing_information=[
            "Tender eligibility criteria",
            "Tender technical scoring criteria",
        ],
        next_actions=[
            "Confirm that the uploaded document is a tender or RFP before assessment."
        ],
        token_usage=dict(token_usage),
        metadata={
            "document_type": document_type,
            "assessment_skipped": True,
            "assessment_coverage_percentage": 100.0,
            "assessment_complete": True,
        },
    )


@dataclass
class AnalysisRunResult:
    tender_analysis: TenderAnalysisResult
    tender_assessment: TenderAssessmentResult
    chunk_count: int
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    request_ids: list[str] = field(default_factory=list)
    model_names: list[str] = field(default_factory=list)

    def token_usage(self) -> dict[str, int]:
        return {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
        }


class TenderAnalyzer:
    def __init__(
        self,
        adapter: BaseLLMAdapter,
        *,
        settings: AnalysisSettings | None = None,
    ) -> None:
        self.adapter = adapter
        self.settings = settings or AnalysisSettings.from_environment()

    @staticmethod
    def _progress(
        callback: ProgressCallback | None,
        stage: str,
        current: int,
        total: int,
    ) -> None:
        if callback:
            callback(stage, current, total)

    @staticmethod
    def _add_usage(
        totals: dict[str, int],
        usage: LLMTokenUsage,
    ) -> None:
        totals["input_tokens"] += usage.input_tokens
        totals["output_tokens"] += usage.output_tokens
        totals["total_tokens"] += usage.total_tokens

    @staticmethod
    def _validate_chunk(
        chunk: TenderChunk,
        result: SimpleChunkAnalysis,
    ) -> None:
        if result.chunk_id != chunk.chunk_id:
            raise ValueError(
                f"Chunk ID mismatch: {result.chunk_id} != {chunk.chunk_id}"
            )
        if result.page_start != chunk.page_start:
            raise ValueError("Returned page_start does not match the chunk.")
        if result.page_end != chunk.page_end:
            raise ValueError("Returned page_end does not match the chunk.")

    @staticmethod
    def _metadata_value(
        merged: dict[str, object],
        field_name: str,
    ) -> str | None:
        normalized = field_name.lower().replace(" ", "_")
        for item in merged.get("metadata_candidates", []):
            name = str(item.get("field_name", "")).lower().replace(" ", "_")
            if name == normalized:
                return str(item.get("value") or "") or None
        return None

    def _build_tender_analysis(
        self,
        *,
        filename: str,
        merged: dict[str, object],
    ) -> TenderAnalysisResult:
        scope_items = list(merged.get("scope_statements", []))
        scope_summary = " ".join(scope_items[:6])
        title = self._metadata_value(merged, "title")
        authority = self._metadata_value(merged, "issuing_authority")
        executive = []
        if title:
            executive.append(f"Tender: {title}.")
        if authority:
            executive.append(f"Issuing authority: {authority}.")
        if scope_summary:
            executive.append(scope_summary)

        return TenderAnalysisResult(
            source_filename=filename,
            title=title,
            reference_number=self._metadata_value(merged, "reference_number"),
            issuing_authority=authority,
            tender_category=self._metadata_value(merged, "tender_category"),
            location=self._metadata_value(merged, "location"),
            submission_deadline=self._metadata_value(
                merged,
                "submission_deadline",
            ),
            pre_bid_date=self._metadata_value(merged, "pre_bid_date"),
            tender_fee=self._metadata_value(merged, "tender_fee"),
            emd_amount=self._metadata_value(merged, "emd_amount"),
            estimated_value=self._metadata_value(merged, "estimated_value"),
            contract_duration=self._metadata_value(merged, "contract_duration"),
            executive_summary=" ".join(executive),
            scope_summary=scope_summary,
            deliverables=list(merged.get("deliverables", [])),
            eligibility_criteria=merged.get("eligibility_criteria", []),
            scoring_criteria=merged.get("scoring_criteria", []),
            deadlines=merged.get("deadlines", []),
            risks=merged.get("risks", []),
            required_documents=list(merged.get("required_documents", [])),
            ambiguities=list(merged.get("ambiguities", [])),
            source_chunk_ids=list(merged.get("source_chunk_ids", [])),
        )

    def _assess_in_batches(
        self,
        *,
        tender_analysis: TenderAnalysisResult,
        company_context: dict[str, Any],
        totals: dict[str, int],
        models: list[str],
        request_ids: list[str],
        progress_callback: ProgressCallback | None,
    ) -> TenderAssessmentResult:
        eligibility_batch_size = int(
            os.getenv("ASSESSMENT_ELIGIBILITY_BATCH_SIZE", "4")
        )
        scoring_batch_size = int(
            os.getenv("ASSESSMENT_SCORING_BATCH_SIZE", "4")
        )
        assessment_chunks = build_assessment_chunks(
            tender_analysis,
            eligibility_batch_size=eligibility_batch_size,
            scoring_batch_size=scoring_batch_size,
        )
        partial_assessments: list[TenderAssessmentResult] = []

        for index, assessment_chunk in enumerate(assessment_chunks, start=1):
            self._progress(
                progress_callback,
                f"Assessing company qualification {index}/{len(assessment_chunks)}",
                index,
                len(assessment_chunks),
            )
            response = self.adapter.generate_structured(
                system_prompt=COMPANY_ASSESSMENT_SYSTEM_PROMPT,
                user_prompt=build_company_assessment_prompt(
                    tender_analysis=assessment_chunk.tender_analysis,
                    company_context=company_context,
                ),
                response_model=SimpleCompanyAssessment,
                schema_name=(
                    "simple_company_assessment_"
                    f"{assessment_chunk.chunk_id}"
                ),
            )
            partial = map_simple_assessment(
                response.parsed,
                tender_analysis=assessment_chunk.tender_analysis,
            )
            partial.metadata.update(
                {
                    "assessment_chunk_id": assessment_chunk.chunk_id,
                    "assessment_kind": assessment_chunk.kind,
                    "criterion_ids": list(assessment_chunk.criterion_ids),
                }
            )
            partial_assessments.append(partial)
            self._add_usage(totals, response.usage)
            models.append(response.model)
            if response.request_id:
                request_ids.append(response.request_id)

        assessment = merge_assessment_results(
            tender_analysis=tender_analysis,
            partial_results=partial_assessments,
        )
        assessment.token_usage = dict(totals)
        return finalize_assessment(assessment)

    def analyze(
        self,
        *,
        document: DocumentExtractionResult,
        company_context: dict[str, Any],
        progress_callback: ProgressCallback | None = None,
    ) -> AnalysisRunResult:
        validate_synthetic_profile(company_context)
        chunks = chunk_document(document, settings=self.settings)
        totals = {
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
        }
        request_ids: list[str] = []
        models: list[str] = []
        rich_chunks = []

        for index, chunk in enumerate(chunks, start=1):
            self._progress(
                progress_callback,
                "Extracting tender chunk",
                index,
                len(chunks),
            )
            response = self.adapter.generate_structured(
                system_prompt=TENDER_EXTRACTION_SYSTEM_PROMPT,
                user_prompt=build_tender_chunk_prompt(chunk),
                response_model=SimpleChunkAnalysis,
                schema_name="simple_chunk_analysis",
            )
            self._validate_chunk(chunk, response.parsed)
            rich_chunks.append(
                map_simple_chunk(
                    response.parsed,
                    source_filename=document.filename,
                )
            )
            self._add_usage(totals, response.usage)
            models.append(response.model)
            if response.request_id:
                request_ids.append(response.request_id)

        self._progress(
            progress_callback,
            "Consolidating tender analysis",
            1,
            1,
        )
        tender_analysis = self._build_tender_analysis(
            filename=document.filename,
            merged=merge_chunk_analyses(rich_chunks),
        )
        document_type = classify_document(tender_analysis)
        tender_analysis.metadata["document_type"] = document_type

        has_tender_criteria = bool(
            tender_analysis.eligibility_criteria
            or tender_analysis.scoring_criteria
        )
        if has_tender_criteria:
            assessment = self._assess_in_batches(
                tender_analysis=tender_analysis,
                company_context=company_context,
                totals=totals,
                models=models,
                request_ids=request_ids,
                progress_callback=progress_callback,
            )
        else:
            self._progress(
                progress_callback,
                "Skipping company qualification",
                1,
                1,
            )
            assessment = build_not_applicable_assessment(
                tender_analysis=tender_analysis,
                company_context=company_context,
                document_type=document_type,
                token_usage=totals,
            )

        self._progress(progress_callback, "Analysis complete", 1, 1)
        return AnalysisRunResult(
            tender_analysis=tender_analysis,
            tender_assessment=assessment,
            chunk_count=len(chunks),
            input_tokens=totals["input_tokens"],
            output_tokens=totals["output_tokens"],
            total_tokens=totals["total_tokens"],
            request_ids=request_ids,
            model_names=list(dict.fromkeys(models)),
        )
