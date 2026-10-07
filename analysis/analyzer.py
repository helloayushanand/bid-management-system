"""End-to-end tender analysis using small LLM-facing JSON models."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from adapters import BaseLLMAdapter, LLMTokenUsage
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
from models import DocumentExtractionResult, TenderAnalysisResult
from models.llm_dtos import SimpleChunkAnalysis, SimpleCompanyAssessment


ProgressCallback = Callable[[str, int, int], None]


@dataclass
class AnalysisRunResult:
    tender_analysis: TenderAnalysisResult
    tender_assessment: Any
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
    def _add_usage(totals: dict[str, int], usage: LLMTokenUsage) -> None:
        totals["input_tokens"] += usage.input_tokens
        totals["output_tokens"] += usage.output_tokens
        totals["total_tokens"] += usage.total_tokens

    @staticmethod
    def _validate_chunk(chunk: TenderChunk, result: SimpleChunkAnalysis) -> None:
        if result.chunk_id != chunk.chunk_id:
            raise ValueError(
                f"Chunk ID mismatch: {result.chunk_id} != {chunk.chunk_id}"
            )
        if result.page_start != chunk.page_start:
            raise ValueError("Returned page_start does not match the chunk.")
        if result.page_end != chunk.page_end:
            raise ValueError("Returned page_end does not match the chunk.")

    @staticmethod
    def _metadata_value(merged: dict[str, object], field_name: str) -> str | None:
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
        executive_parts = []
        title = self._metadata_value(merged, "title")
        authority = self._metadata_value(merged, "issuing_authority")
        if title:
            executive_parts.append(f"Tender: {title}.")
        if authority:
            executive_parts.append(f"Issuing authority: {authority}.")
        if scope_summary:
            executive_parts.append(scope_summary)

        return TenderAnalysisResult(
            source_filename=filename,
            title=title,
            reference_number=self._metadata_value(merged, "reference_number"),
            issuing_authority=authority,
            tender_category=self._metadata_value(merged, "tender_category"),
            location=self._metadata_value(merged, "location"),
            submission_deadline=self._metadata_value(
                merged, "submission_deadline"
            ),
            pre_bid_date=self._metadata_value(merged, "pre_bid_date"),
            tender_fee=self._metadata_value(merged, "tender_fee"),
            emd_amount=self._metadata_value(merged, "emd_amount"),
            estimated_value=self._metadata_value(merged, "estimated_value"),
            contract_duration=self._metadata_value(merged, "contract_duration"),
            executive_summary=" ".join(executive_parts),
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

    def analyze(
        self,
        *,
        document: DocumentExtractionResult,
        company_context: dict[str, Any],
        progress_callback: ProgressCallback | None = None,
    ) -> AnalysisRunResult:
        validate_synthetic_profile(company_context)
        chunks = chunk_document(document, settings=self.settings)
        totals = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
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

        self._progress(progress_callback, "Consolidating tender analysis", 1, 1)
        merged = merge_chunk_analyses(rich_chunks)
        tender_analysis = self._build_tender_analysis(
            filename=document.filename,
            merged=merged,
        )

        self._progress(progress_callback, "Assessing company qualification", 1, 1)
        assessment_response = self.adapter.generate_structured(
            system_prompt=COMPANY_ASSESSMENT_SYSTEM_PROMPT,
            user_prompt=build_company_assessment_prompt(
                tender_analysis=tender_analysis,
                company_context=company_context,
            ),
            response_model=SimpleCompanyAssessment,
            schema_name="simple_company_assessment",
        )
        assessment = map_simple_assessment(
            assessment_response.parsed,
            tender_analysis=tender_analysis,
        )
        self._add_usage(totals, assessment_response.usage)
        models.append(assessment_response.model)
        if assessment_response.request_id:
            request_ids.append(assessment_response.request_id)

        assessment.token_usage = dict(totals)
        assessment = finalize_assessment(assessment)
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
