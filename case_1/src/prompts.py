from __future__ import annotations

import json
from typing import Any

from src.schemas import analysis_schema_json


SYSTEM_PROMPT = """You are an expert equity research analyst specializing in earnings call analysis.

Analyze only the provided transcript segments and optional prior context.
Do not use outside knowledge.
Every analytical claim must be grounded in literal transcript evidence.
If evidence is insufficient, say so in the limitations rather than inventing.
Do not invent guidance, consensus expectations, analyst names, financial figures, or management roles.
Distinguish management claims, analyst concerns, and your own interpretation.
Red flags are linguistic indicators, not proof of misconduct.
Return valid JSON only."""

METADATA_PROMPT = """Metadata task:
- Identify company_name, ticker, quarter, and call_date only if stated in the transcript.
- Use null when a field is not supported by the transcript."""

TONE_PROMPT = """Management tone task:
- Focus on management speakers only.
- Classify the overall tone as one of the schema categories.
- Consider confidence, caution, defensiveness, transparency, uncertainty, recognition of problems, and repeated language.
- Set confidence based on how direct and repeated the tone evidence is.
- Include 2 to 3 literal evidence excerpts."""

GUIDANCE_PROMPT = """Guidance and theme changes task:
- Identify explicit guidance revisions, reaffirmations, withdrawals, and material theme changes.
- Return at most 4 items. Prefer the most material ones.
- Do not invent a previous quarter or market consensus.
- If no previous transcript or prior context is provided, set previous_reference to null unless the current call explicitly states the comparison.
- If a new numeric guidance range is not literally stated in the transcript, do not present it as a formal call statement. Say that management indicated an upward/downward revision and keep the unstated range out of current_statement.
- Numeric ranges from prior_context may be used in previous_reference or pre_call_expectation, but not as call evidence unless the transcript itself states them.
- Set statement_basis for each guidance item:
  explicit = the transcript directly states the change or number;
  inferred = the change is inferred from multiple transcript statements;
  external_context = the statement mainly comes from prior_context rather than the call and should usually be avoided for current_statement.
- Use metric_direction for the numerical or stated direction, and investment_implication for the likely investment implication.
- Include confidence for every guidance item:
  high confidence = explicit quantified guidance or directly stated revision;
  medium confidence = explicit theme change with partial quantification;
  low confidence = inferred theme change or weakly supported materiality.
- Include 1 to 2 evidence excerpts for every item."""

CRITICAL_QUESTIONS_PROMPT = """Critical Q&A task:
- Select up to the top 3 analyst questions by materiality.
- Prefer questions about guidance credibility, asset quality, capital, dividends, sustainable growth, quantified risk, or inconsistencies.
- For each question, summarize the question, summarize management's response, explain why it was critical, and assess answer_quality.
- Set confidence based on the specificity of the question, the completeness of the answer, and the evidence quality.
- Include 1 to 2 literal evidence excerpts from the question and/or answer."""

RED_FLAGS_PROMPT = """Linguistic red flags task:
- Return only 3 to 5 relevant signals, or fewer if the transcript does not support more.
- Do not treat all caution as a red flag.
- Use red flags as linguistic indicators only.
- Include quote, speaker, page, explanation, severity, and confidence.
- Use lower confidence for ambiguous caution, routine legalistic language, or weak linguistic signals."""

SURPRISE_PROMPT = """Surprise task:
- Estimate surprise using transcript evidence and, when provided, pre-call consensus or prior analyst context.
- If pre-call context is provided, compare what management said in the call against the pre-call expectations, narrative consensus, estimates, and interpretation rules in that context.
- If pre-call context is provided, give higher surprise weight only to items that differ from or sharpen the prior expectation.
- If pre-call context is not provided, estimate transcript-only surprise using signals such as management saying guidance changed, analysts repeatedly pressing one issue, new material numbers, defensive tone, or explicit changes in scenario.
- Do not treat post-result actuals as pre-call expectations unless the context explicitly labels them as reported pre-result consensus or backtesting data.
- In consensus_surprises, call_statement must be supported by literal transcript evidence. Do not include a numeric range in call_statement unless the transcript evidence itself contains that range.
- Numeric ranges or expectations from prior_context belong in pre_call_expectation, not in call_statement, unless also stated in the call transcript.
- Set statement_basis for each consensus surprise call_statement using the same explicit/inferred/external_context definitions.
- Always fill transcript_surprise_score using only transcript-internal signals.
- Fill consensus_surprise_score only when pre-call context is provided; otherwise use null.
- Fill consensus_surprises only when pre-call context is provided. Each item must compare pre_call_expectation vs call_statement.
- Set overall_surprise_score equal to consensus_surprise_score when available; otherwise set it equal to transcript_surprise_score after the transcript-only cap.
- Fill surprise_score_components with 0-100 contribution scores for guidance_revision, analyst_pressure, tone_shift, new_material_numbers, and external_context_adjustment.
- With no external context, external_context_adjustment must be 0.
- With external context, external_context_adjustment should reflect how strongly the call diverges from documented pre-call consensus.
- Set confidence for each surprise item and surprise_score_confidence for the overall score.
- surprise_score_confidence should usually be low or medium when no external pre-call consensus is provided.
- Without external pre-call consensus or prior analyst context, do not assign an overall surprise score above 60.
- If no external pre-call consensus file was provided, include this limitation exactly:
  "No external pre-call consensus file was provided; score is inferred from transcript evidence and should not be interpreted as a verified market consensus gap."
- Use 0-20 for little surprise, 21-40 for mild surprise, 41-60 for moderate surprise, 61-80 for relevant surprise, and 81-100 for potentially thesis-material surprise."""

JSON_RULES = """JSON output rules:
- Return only one JSON object. Do not wrap it in Markdown.
- Follow the JSON schema exactly. Do not add fields.
- Use null for unknown optional values.
- Keep evidence quotes literal and short, ideally under 25 words.
- Leave source_block_ids empty if unknown; the pipeline will fill them mechanically after quote validation.
- Do not set evidence_validated or speaker_validated yourself; the pipeline will fill them mechanically.
- Keep confidence and evidence_validated conceptually separate:
  confidence is analytical certainty; evidence_validated is a later mechanical quote check.
- Keep summaries concise: one or two sentences per field.
- Page should be the approximate transcript page where the quote appears.
- critical_questions must contain no more than 3 items.
- guidance_changes must contain no more than 4 items.
- red_flags must contain no more than 5 items.
- surprise_items must contain no more than 3 items.
- consensus_surprises must contain no more than 3 items.
- every evidence list must contain no more than 2 items, except management_tone which may contain up to 3.
- analysis_limitations must explicitly state key data limitations.
- If previous transcript/context is not provided, include: "Prior-quarter transcript was not provided."
- If pre-call consensus/prior analyst context is not provided, include: "No external pre-call consensus was provided."
- If the surprise score uses only transcript evidence, include: "Surprise score is inferred from transcript-only signals."
- Do not include an executive report field. The final Markdown report will be rendered by code from the validated JSON."""


def build_analysis_prompt(
    *,
    transcript_segments: list[dict[str, Any]],
    qa_turns: list[dict[str, Any]] | None = None,
    previous_context: str | None = None,
    prior_context: str | None = None,
    language: str = "en-US",
) -> str:
    transcript_json = json.dumps(
        compact_transcript_segments_for_prompt(transcript_segments),
        ensure_ascii=False,
        indent=2,
    )
    qa_turns_json = json.dumps(
        compact_qa_turns_for_prompt(qa_turns or []),
        ensure_ascii=False,
        indent=2,
    )
    schema = analysis_schema_json()

    previous_block = _context_block(
        title="Previous transcript or previous-quarter context",
        value=previous_context,
    )
    prior_block = _context_block(
        title="Pre-call consensus or prior analyst context",
        value=prior_context,
    )

    return f"""Single-call analysis task:
Use one integrated pass to analyze the full transcript and return the complete JSON.
Do not ask for follow-up calls. Do not split the task into separate model calls.
Do not generate Markdown in the JSON. The final report will be rendered by code from structured fields.
Prefer a compact but complete JSON. It is more important to close valid JSON than to include every possible observation.

{METADATA_PROMPT}

{TONE_PROMPT}

{GUIDANCE_PROMPT}

{CRITICAL_QUESTIONS_PROMPT}

{RED_FLAGS_PROMPT}

{SURPRISE_PROMPT}

{JSON_RULES}

Report language preference for summaries inside JSON: {language}

JSON schema:
{schema}

{previous_block}

{prior_block}

Grouped Q&A turns:
Use this grouped structure first for critical question ranking and response-quality assessment.
Ignore blocks with block_type = "acknowledgement" when ranking critical questions.
{qa_turns_json}

Transcript segments:
Use the full segment list for prepared remarks, tone, guidance, red flags, and evidence page references.
{transcript_json}
"""


def build_review_prompt(
    *,
    analysis_json: str,
    transcript_segments: list[dict[str, Any]],
    language: str = "en-US",
) -> str:
    transcript_json = json.dumps(transcript_segments, ensure_ascii=False, indent=2)
    schema = analysis_schema_json()
    return f"""Revise this JSON generated from the transcript.

Check whether there are:
- analytical conclusions without evidence;
- weak or non-literal quotes;
- exaggerated red flags;
- speculative surprise score;
- internal inconsistencies across JSON fields.

Do not redo the full analysis.
Only correct problems that are clearly supported by the transcript.
Preserve the existing structure and return one complete valid JSON object.
Do not add outside knowledge.
If no correction is needed, return the same JSON.
Summary language preference inside JSON fields is: {language}

JSON schema:
{schema}

Transcript segments:
{transcript_json}

JSON to review:
{analysis_json}
"""


def build_json_repair_prompt(*, invalid_response: str, validation_error: str) -> str:
    schema = analysis_schema_json()
    return f"""The previous response was not valid JSON according to the schema.

Fix only the JSON structure and schema compliance.
Do not add new analysis.
Do not use outside knowledge.
Return only valid JSON.
If the previous response was truncated, remove lower-priority tail items and return a compact complete JSON.
Keep at most 3 tone evidence items, 4 guidance items, 3 critical questions, 5 red flags, 3 surprise items, and 3 consensus surprise items.

Validation error:
{validation_error}

JSON schema:
{schema}

Previous response:
{invalid_response}
"""


def _context_block(title: str, value: str | None) -> str:
    if value and value.strip():
        return f"{title}:\n{value.strip()}"
    return f"{title}: not provided."


def compact_transcript_segments_for_prompt(
    transcript_segments: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    keys = [
        "block_id",
        "speaker",
        "speaker_type",
        "role_title",
        "institution",
        "section",
        "block_type",
        "qa_turn_id",
        "page_start",
        "page_end",
        "word_count",
        "has_question",
        "text",
    ]
    return [_select_keys(segment, keys) for segment in transcript_segments]


def compact_qa_turns_for_prompt(qa_turns: list[dict[str, Any]]) -> list[dict[str, Any]]:
    turn_keys = ["qa_turn_id", "analyst", "institution"]
    block_keys = [
        "block_id",
        "speaker",
        "speaker_type",
        "role_title",
        "institution",
        "block_type",
        "page_start",
        "page_end",
        "word_count",
        "has_question",
        "text",
    ]

    compacted: list[dict[str, Any]] = []
    for turn in qa_turns:
        compact_turn = _select_keys(turn, turn_keys)
        for collection in ["questions", "answers", "ir_clarifications", "other_blocks"]:
            compact_turn[collection] = [
                _select_keys(block, block_keys)
                for block in turn.get(collection, [])
                if isinstance(block, dict)
            ]
        compacted.append(compact_turn)
    return compacted


def _select_keys(value: dict[str, Any], keys: list[str]) -> dict[str, Any]:
    return {key: value.get(key) for key in keys if key in value and value.get(key) is not None}
