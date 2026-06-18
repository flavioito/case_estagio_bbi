from __future__ import annotations

import json
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


WORD_RE = re.compile(r"\b[\w'-]+\b", re.UNICODE)

ToneClassification = Literal[
    "positive",
    "cautiously_positive",
    "neutral",
    "cautious",
    "negative",
    "mixed",
]
Confidence = Literal["low", "medium", "high"]
AnswerQuality = Literal["strong", "adequate", "weak", "evasive", "unclear"]
RedFlagType = Literal[
    "hesitation",
    "evasion",
    "topic_shift",
    "uncertainty",
    "softening_language",
    "promotional_language",
    "other",
]
Severity = Literal["low", "medium", "high"]
MetricDirection = Literal[
    "increased",
    "decreased",
    "raised",
    "lowered",
    "reaffirmed",
    "unchanged",
    "introduced",
    "withdrawn",
    "mixed",
    "unknown",
]
InvestmentImplication = Literal["positive", "negative", "neutral", "mixed", "unclear"]
SurpriseDirection = Literal["positive", "negative", "neutral", "mixed", "unclear"]
SurpriseMagnitude = Literal["low", "medium", "high"]
StatementBasis = Literal["explicit", "inferred", "external_context"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Evidence(StrictModel):
    quote: str = Field(..., min_length=1)
    speaker: str = Field(..., min_length=1)
    page: int | None = Field(default=None, ge=1)
    rationale: str = Field(..., min_length=1)
    evidence_validated: bool | None = Field(
        default=None,
        description="Mechanical quote check against the transcript; not an analytical confidence score.",
    )
    speaker_validated: bool | None = Field(
        default=None,
        description="Mechanical check that the quote was found in a transcript segment attributed to the stated speaker.",
    )
    source_block_ids: list[str] = Field(
        default_factory=list,
        description="Transcript segment block IDs where the quote was mechanically found.",
    )
    match_type: Literal["exact", "normalized_exact", "approximate", "not_found"] | None = None
    matched_text: str | None = None
    match_score: float | None = Field(default=None, ge=0, le=1)

    @field_validator("quote")
    @classmethod
    def quote_must_be_literal(cls, value: str) -> str:
        if len(value.split()) < 2:
            raise ValueError("Evidence quote must contain a literal transcript excerpt.")
        return value


class ManagementTone(StrictModel):
    classification: ToneClassification
    summary: str = Field(..., min_length=1)
    evidence: list[Evidence] = Field(..., min_length=1, max_length=3)
    confidence: Confidence = Field(
        ...,
        description="Analytical confidence based on evidence strength and ambiguity.",
    )


class GuidanceChange(StrictModel):
    topic: str = Field(..., min_length=1)
    metric_direction: MetricDirection
    investment_implication: InvestmentImplication
    statement_basis: StatementBasis = Field(
        ...,
        description="Whether the statement is explicitly stated in the transcript, inferred from the call, or derived from external context.",
    )
    current_statement: str = Field(..., min_length=1)
    previous_reference: str | None = None
    evidence: list[Evidence] = Field(..., min_length=1, max_length=2)
    confidence: Confidence = Field(
        ...,
        description="Analytical confidence that this is a material guidance/theme change.",
    )


class AnalystQuestion(StrictModel):
    analyst: str = Field(..., min_length=1)
    institution: str | None = None
    topic: str = Field(..., min_length=1)
    why_critical: str = Field(..., min_length=1)
    question_summary: str = Field(..., min_length=1)
    management_response_summary: str = Field(..., min_length=1)
    answer_quality: AnswerQuality
    evidence: list[Evidence] = Field(..., min_length=1, max_length=2)
    confidence: Confidence = Field(
        ...,
        description="Analytical confidence in the criticality and response-quality assessment.",
    )


class RedFlag(StrictModel):
    type: RedFlagType
    quote: str = Field(..., min_length=1)
    speaker: str = Field(..., min_length=1)
    page: int | None = Field(default=None, ge=1)
    explanation: str = Field(..., min_length=1)
    severity: Severity
    confidence: Confidence = Field(
        ...,
        description="Analytical confidence that the quote is a meaningful linguistic red flag.",
    )
    evidence_validated: bool | None = Field(
        default=None,
        description="Mechanical quote check against the transcript; not an analytical confidence score.",
    )
    speaker_validated: bool | None = Field(
        default=None,
        description="Mechanical check that the quote was found in a transcript segment attributed to the stated speaker.",
    )
    source_block_ids: list[str] = Field(
        default_factory=list,
        description="Transcript segment block IDs where the quote was mechanically found.",
    )
    match_type: Literal["exact", "normalized_exact", "approximate", "not_found"] | None = None
    matched_text: str | None = None
    match_score: float | None = Field(default=None, ge=0, le=1)


class SurpriseItem(StrictModel):
    item: str = Field(..., min_length=1)
    score: int = Field(..., ge=0, le=100)
    why_surprising: str = Field(..., min_length=1)
    evidence: list[Evidence] = Field(..., min_length=1, max_length=2)
    confidence: Confidence = Field(
        ...,
        description="Analytical confidence that this item is surprising based on available context.",
    )
    limitation: str = Field(..., min_length=1)


class ConsensusSurprise(StrictModel):
    topic: str = Field(..., min_length=1)
    pre_call_expectation: str = Field(..., min_length=1)
    statement_basis: StatementBasis = Field(
        ...,
        description="Whether the call statement is explicitly stated in the transcript, inferred from the call, or derived from external context.",
    )
    call_statement: str = Field(..., min_length=1)
    surprise_direction: SurpriseDirection
    surprise_magnitude: SurpriseMagnitude
    already_in_consensus: bool
    confidence: Confidence = Field(
        ...,
        description="Analytical confidence in the gap between pre-call expectation and call statement.",
    )
    evidence: list[Evidence] = Field(..., min_length=1, max_length=2)


class SurpriseScoreComponents(StrictModel):
    guidance_revision: int = Field(..., ge=0, le=100)
    analyst_pressure: int = Field(..., ge=0, le=100)
    tone_shift: int = Field(..., ge=0, le=100)
    new_material_numbers: int = Field(..., ge=0, le=100)
    external_context_adjustment: int = Field(..., ge=0, le=100)


class AnalysisContext(StrictModel):
    has_prior_quarter_transcript: bool = False
    has_external_consensus: bool = False
    has_historical_context: bool = False
    surprise_score_is_transcript_only: bool = True
    surprise_score_cap_applied: bool = False


class TemporalComparison(StrictModel):
    tone_change: str | None = Field(
        default=None,
        description="How management tone changed versus historical transcript context, if provided.",
    )
    recurring_topics: list[str] = Field(default_factory=list, max_length=6)
    new_or_escalating_topics: list[str] = Field(default_factory=list, max_length=5)
    analyst_pressure_change: str | None = Field(
        default=None,
        description="How analyst pressure changed versus historical Q&A patterns, if provided.",
    )
    historical_context_summary: str | None = Field(
        default=None,
        description="Concise summary of what history adds to the current-call interpretation.",
    )
    confidence: Confidence | None = Field(
        default=None,
        description="Analytical confidence in the temporal comparison.",
    )


class EarningsCallAnalysis(StrictModel):
    schema_version: str = "1.2"
    company_name: str | None = None
    ticker: str | None = None
    quarter: str | None = None
    call_date: str | None = None
    management_tone: ManagementTone
    guidance_changes: list[GuidanceChange] = Field(default_factory=list, max_length=4)
    critical_questions: list[AnalystQuestion] = Field(default_factory=list, max_length=3)
    red_flags: list[RedFlag] = Field(default_factory=list, max_length=5)
    surprise_items: list[SurpriseItem] = Field(default_factory=list, max_length=3)
    consensus_surprises: list[ConsensusSurprise] = Field(default_factory=list, max_length=3)
    surprise_score_components: SurpriseScoreComponents
    transcript_surprise_score: int = Field(..., ge=0, le=100)
    consensus_surprise_score: int | None = Field(default=None, ge=0, le=100)
    overall_surprise_score: int = Field(..., ge=0, le=100)
    surprise_score_confidence: Confidence = Field(
        ...,
        description="Analytical confidence in the overall surprise score.",
    )
    temporal_comparison: TemporalComparison = Field(default_factory=TemporalComparison)
    analysis_context: AnalysisContext = Field(default_factory=AnalysisContext)
    analysis_limitations: list[str] = Field(..., min_length=1, max_length=5)


def analysis_schema_json() -> str:
    return json.dumps(EarningsCallAnalysis.model_json_schema(), ensure_ascii=False, indent=2)


def count_report_words(markdown: str) -> int:
    return len(WORD_RE.findall(markdown))
