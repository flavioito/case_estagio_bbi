from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from src.anthropic_client import AnthropicClient
from src.config import get_settings
from src.consistency_checker import check_analysis_consistency
from src.evidence_checker import validate_analysis_evidence
from src.pdf_loader import load_pdf_metadata_text, load_pdf_pages
from src.prompts import (
    SYSTEM_PROMPT,
    build_analysis_prompt,
    build_json_repair_prompt,
    build_self_critique_prompt,
)
from src.report_writer import write_executive_report
from src.schemas import EarningsCallAnalysis
from src.segmenter import build_qa_turns, segment_transcript
from src.transcript_cleaner import build_clean_text, clean_transcript_pages


@dataclass(frozen=True)
class Day1Result:
    pdf_path: Path
    output_dir: Path
    page_count: int
    segment_count: int
    clean_text_path: Path
    segments_path: Path
    qa_turns_path: Path


@dataclass(frozen=True)
class Day2Result(Day1Result):
    analysis_path: Path
    evidence_report_path: Path
    consistency_report_path: Path
    executive_report_path: Path
    run_metadata_path: Path
    prior_context_path: Path | None
    history_context_path: Path | None
    repair_attempts: int
    review_used: bool
    analysis_model: str
    review_model: str | None
    self_critique_used: bool = False
    self_critique_model: str | None = None
    self_critique_triggers: tuple[str, ...] = ()


class AnalysisValidationError(Exception):
    """Raised when Claude output cannot be validated as analysis JSON."""


def run_day1_pipeline(
    pdf_path: str | Path,
    output_dir: str | Path | None = None,
    debug: bool | None = None,
) -> Day1Result:
    settings = get_settings()
    output_path = Path(output_dir) if output_dir is not None else settings.output_dir
    output_path.mkdir(parents=True, exist_ok=True)

    should_debug = settings.debug if debug is None else debug
    resolved_pdf_path = Path(pdf_path).expanduser()

    pages = load_pdf_pages(resolved_pdf_path)
    cleaned_pages = clean_transcript_pages(pages)
    clean_text = build_clean_text(cleaned_pages)
    segments = segment_transcript(cleaned_pages)
    qa_turns = build_qa_turns(segments)

    clean_text_path = output_path / "clean_text.txt"
    segments_path = output_path / "transcript_segments.json"
    qa_turns_path = output_path / "qa_turns.json"

    clean_text_path.write_text(clean_text, encoding="utf-8")
    segments_path.write_text(
        json.dumps(segments, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    qa_turns_path.write_text(
        json.dumps(qa_turns, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    if should_debug:
        raw_pages_path = output_path / "raw_pages.json"
        clean_pages_path = output_path / "clean_pages.json"
        raw_pages_path.write_text(json.dumps(pages, ensure_ascii=False, indent=2), encoding="utf-8")
        clean_pages_path.write_text(
            json.dumps(cleaned_pages, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    return Day1Result(
        pdf_path=resolved_pdf_path,
        output_dir=output_path,
        page_count=len(pages),
        segment_count=len(segments),
        clean_text_path=clean_text_path,
        segments_path=segments_path,
        qa_turns_path=qa_turns_path,
    )


def run_day2_pipeline(
    pdf_path: str | Path,
    output_dir: str | Path | None = None,
    previous: str | Path | None = None,
    prior_context: str | Path | None = None,
    history_context: str | Path | None = None,
    language: str = "en-US",
    debug: bool | None = None,
    max_repair_attempts: int = 1,
    review_with_sonnet: bool = False,
    self_critique: bool = True,
) -> Day2Result:
    settings = get_settings()
    should_debug = settings.debug if debug is None else debug
    if review_with_sonnet:
        self_critique = True

    day1 = run_day1_pipeline(pdf_path=pdf_path, output_dir=output_dir, debug=debug)
    segments = json.loads(day1.segments_path.read_text(encoding="utf-8"))
    qa_turns = json.loads(day1.qa_turns_path.read_text(encoding="utf-8"))
    full_transcript_text = day1.clean_text_path.read_text(encoding="utf-8")
    pdf_source_metadata = _load_pdf_source_metadata(day1.pdf_path)

    previous_text = _load_optional_context(previous)
    resolved_prior_context = resolve_prior_context_path(
        explicit_path=prior_context,
        pdf_path=day1.pdf_path,
        transcript_text=full_transcript_text,
        source_text=pdf_source_metadata,
    )
    resolved_history_context = resolve_history_context_path(
        explicit_path=history_context,
        pdf_path=day1.pdf_path,
        transcript_text=full_transcript_text,
        source_text=pdf_source_metadata,
    )
    prior_context_text = _load_prior_context(resolved_prior_context)
    history_context_text = _load_history_context(resolved_history_context)

    user_prompt = build_analysis_prompt(
        transcript_segments=segments,
        qa_turns=qa_turns,
        previous_context=previous_text,
        prior_context=prior_context_text,
        history_context=history_context_text,
        language=language,
    )

    if should_debug:
        (day1.output_dir / "analysis_prompt.txt").write_text(user_prompt, encoding="utf-8")

    client = AnthropicClient(settings=settings)
    raw_response = client.send_message(
        system_prompt=SYSTEM_PROMPT,
        user_prompt=user_prompt,
        model=settings.anthropic_model,
    )
    analysis, repair_attempts, final_raw_response = _validate_or_repair_analysis(
        client=client,
        raw_response=raw_response,
        max_repair_attempts=max_repair_attempts,
        model=settings.anthropic_model,
    )

    analysis = _postprocess_analysis(
        analysis=analysis,
        full_transcript_text=full_transcript_text,
        source_text=pdf_source_metadata,
        has_previous_context=previous_text is not None,
        has_prior_context=prior_context_text is not None,
        has_history_context=history_context_text is not None,
        history_context_text=history_context_text,
    )

    analysis, evidence_report = _validate_evidence(
        analysis=analysis,
        full_transcript_text=full_transcript_text,
        transcript_segments=segments,
    )
    consistency_report = check_analysis_consistency(
        analysis.model_dump(mode="json"),
        evidence_report=evidence_report,
    )
    self_critique_used = False
    self_critique_model: str | None = None
    self_critique_triggers: list[str] = []

    if self_critique:
        pre_critique_analysis_path = day1.output_dir / "analysis_pre_self_critique.json"
        pre_critique_evidence_path = day1.output_dir / "evidence_report_pre_self_critique.json"
        pre_critique_consistency_path = day1.output_dir / "consistency_report_pre_self_critique.json"
        pre_critique_analysis_path.write_text(
            json.dumps(analysis.model_dump(mode="json"), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        pre_critique_evidence_path.write_text(
            json.dumps(evidence_report, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        pre_critique_consistency_path.write_text(
            json.dumps(consistency_report, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        self_critique_triggers = determine_self_critique_triggers(
            evidence_report=evidence_report,
            consistency_report=consistency_report,
        )
        self_critique_model = select_self_critique_model(
            settings=settings,
            evidence_report=evidence_report,
            consistency_report=consistency_report,
        )
        self_critique_prompt = build_self_critique_prompt(
            analysis_json=json.dumps(analysis.model_dump(mode="json"), ensure_ascii=False, indent=2),
            evidence_report=evidence_report,
            consistency_report=consistency_report,
            language=language,
        )
        if should_debug:
            (day1.output_dir / "self_critique_prompt.txt").write_text(
                self_critique_prompt,
                encoding="utf-8",
            )

        self_critique_raw_response = client.send_message(
            system_prompt=SYSTEM_PROMPT,
            user_prompt=self_critique_prompt,
            model=self_critique_model,
        )
        analysis, critique_repairs, self_critique_final_raw_response = _validate_or_repair_analysis(
            client=client,
            raw_response=self_critique_raw_response,
            max_repair_attempts=max_repair_attempts,
            model=self_critique_model,
        )
        repair_attempts += critique_repairs
        self_critique_used = True
        analysis = _postprocess_analysis(
            analysis=analysis,
            full_transcript_text=full_transcript_text,
            source_text=pdf_source_metadata,
            has_previous_context=previous_text is not None,
            has_prior_context=prior_context_text is not None,
            has_history_context=history_context_text is not None,
            history_context_text=history_context_text,
        )
        analysis, evidence_report = _validate_evidence(
            analysis=analysis,
            full_transcript_text=full_transcript_text,
            transcript_segments=segments,
        )
        consistency_report = check_analysis_consistency(
            analysis.model_dump(mode="json"),
            evidence_report=evidence_report,
        )
        if should_debug:
            (day1.output_dir / "self_critique_raw_response.txt").write_text(
                self_critique_final_raw_response,
                encoding="utf-8",
            )

    analysis_path = day1.output_dir / "analysis.json"
    evidence_report_path = day1.output_dir / "evidence_report.json"
    consistency_report_path = day1.output_dir / "consistency_report.json"
    executive_report_path = day1.output_dir / "executive_report.md"
    run_metadata_path = day1.output_dir / "run_metadata.json"
    evidence_report_path.write_text(
        json.dumps(evidence_report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    consistency_report_path.write_text(
        json.dumps(consistency_report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    if evidence_report["warnings"]:
        for warning in evidence_report["warnings"]:
            print(warning)
    if not consistency_report["summary"]["passed"]:
        print("Warning: consistency checker found high-severity issues. Review consistency_report.json.")

    _write_analysis_outputs(
        analysis=analysis,
        analysis_path=analysis_path,
        report_path=executive_report_path,
        evidence_report=evidence_report,
    )
    run_metadata_path.write_text(
        json.dumps(
            build_run_metadata(
                pdf_path=day1.pdf_path,
                output_dir=day1.output_dir,
                page_count=day1.page_count,
                segment_count=day1.segment_count,
                qa_turn_count=len(qa_turns),
                settings=settings,
                repair_attempts=repair_attempts,
                review_used=self_critique_used,
                review_model=self_critique_model,
                self_critique_used=self_critique_used,
                self_critique_model=self_critique_model,
                self_critique_triggers=self_critique_triggers,
                has_previous_context=previous_text is not None,
                has_prior_context=prior_context_text is not None,
                has_history_context=history_context_text is not None,
                prior_context_path=resolved_prior_context,
                history_context_path=resolved_history_context,
                evidence_report=evidence_report,
                consistency_report=consistency_report,
                analysis=analysis,
            ),
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    if should_debug:
        (day1.output_dir / "analysis_raw_response.txt").write_text(
            final_raw_response,
            encoding="utf-8",
        )

    return Day2Result(
        pdf_path=day1.pdf_path,
        output_dir=day1.output_dir,
        page_count=day1.page_count,
        segment_count=day1.segment_count,
        clean_text_path=day1.clean_text_path,
        segments_path=day1.segments_path,
        qa_turns_path=day1.qa_turns_path,
        analysis_path=analysis_path,
        evidence_report_path=evidence_report_path,
        consistency_report_path=consistency_report_path,
        executive_report_path=executive_report_path,
        run_metadata_path=run_metadata_path,
        prior_context_path=resolved_prior_context,
        history_context_path=resolved_history_context,
        repair_attempts=repair_attempts,
        review_used=self_critique_used,
        analysis_model=settings.anthropic_model,
        review_model=self_critique_model,
        self_critique_used=self_critique_used,
        self_critique_model=self_critique_model,
        self_critique_triggers=tuple(self_critique_triggers),
    )


def parse_analysis_json(raw_response: str) -> EarningsCallAnalysis:
    json_text = extract_json_object(raw_response)
    try:
        return EarningsCallAnalysis.model_validate_json(json_text)
    except ValidationError as exc:
        raise AnalysisValidationError(str(exc)) from exc


def extract_json_object(raw_response: str) -> str:
    stripped = raw_response.strip()
    if stripped.startswith("```"):
        stripped = _strip_markdown_fence(stripped)

    if stripped.startswith("{") and stripped.endswith("}"):
        return stripped

    start = stripped.find("{")
    end = stripped.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise AnalysisValidationError("A resposta do modelo nao contem um objeto JSON.")
    return stripped[start : end + 1]


def _validate_or_repair_analysis(
    *,
    client: AnthropicClient,
    raw_response: str,
    max_repair_attempts: int,
    model: str,
) -> tuple[EarningsCallAnalysis, int, str]:
    current_response = raw_response
    last_error = ""

    for attempt in range(max_repair_attempts + 1):
        try:
            return parse_analysis_json(current_response), attempt, current_response
        except AnalysisValidationError as exc:
            last_error = str(exc)
            if attempt >= max_repair_attempts:
                break
            repair_prompt = build_json_repair_prompt(
                invalid_response=current_response,
                validation_error=last_error,
            )
            current_response = client.send_message(
                system_prompt=SYSTEM_PROMPT,
                user_prompt=repair_prompt,
                model=model,
            )

    raise AnalysisValidationError(
        "Nao foi possivel validar o JSON retornado pelo Claude. "
        f"Ultimo erro: {last_error}"
    )


def enrich_analysis_metadata(
    *,
    analysis: EarningsCallAnalysis,
    full_transcript_text: str,
    source_text: str | None = None,
) -> EarningsCallAnalysis:
    """Fill objective call metadata from the transcript when Claude leaves it blank."""
    data = analysis.model_dump(mode="json")
    searchable_text = f"{source_text or ''}\n{full_transcript_text}"

    if not data.get("company_name"):
        company_name = _extract_company_name(searchable_text)
        if company_name:
            data["company_name"] = company_name

    if not data.get("ticker"):
        ticker = _extract_ticker(searchable_text)
        if ticker:
            data["ticker"] = ticker

    if not data.get("quarter"):
        quarter = _extract_quarter(searchable_text)
        if quarter:
            data["quarter"] = quarter

    if not data.get("call_date"):
        call_date = _extract_call_date(searchable_text)
        if call_date:
            data["call_date"] = call_date

    return EarningsCallAnalysis.model_validate(data)


def enrich_analysis_limitations(
    *,
    analysis: EarningsCallAnalysis,
    has_previous_context: bool,
    has_prior_context: bool,
) -> EarningsCallAnalysis:
    data = analysis.model_dump(mode="json")
    existing_limitations = list(data.get("analysis_limitations") or [])
    required_limitations: list[str] = []

    if has_prior_context:
        _append_unique_limitation(
            required_limitations,
            "External pre-call consensus was provided; surprise scores reflect comparison to documented pre-call expectations.",
        )
    else:
        _append_unique_limitation(
            required_limitations,
            "No external pre-call consensus was provided.",
        )
        _append_unique_limitation(
            required_limitations,
            "Surprise score is inferred from transcript-only signals.",
        )
    if not has_previous_context:
        _append_unique_limitation(
            required_limitations,
            "Prior-quarter transcript was not provided.",
        )

    limitations = required_limitations[:]
    for limitation in existing_limitations:
        if _limitation_category(limitation) in {
            _limitation_category(required) for required in required_limitations
        }:
            continue
        if has_prior_context and _limitation_category(limitation) == "transcript_only_surprise":
            continue
        _append_unique_limitation(limitations, limitation)

    data["analysis_limitations"] = limitations[:5]
    return EarningsCallAnalysis.model_validate(data)


def apply_surprise_score_policy(
    *,
    analysis: EarningsCallAnalysis,
    has_prior_context: bool,
    max_transcript_only_score: int = 60,
) -> EarningsCallAnalysis:
    """Avoid thesis-level surprise scores when no external expectation set was provided."""
    data = analysis.model_dump(mode="json")
    was_capped = False
    data["analysis_limitations"] = [
        limitation
        for limitation in data.get("analysis_limitations", [])
        if _limitation_category(limitation) != "surprise_score_cap"
    ]

    if has_prior_context:
        if data.get("consensus_surprise_score") is not None:
            data["overall_surprise_score"] = data["consensus_surprise_score"]
        else:
            data["overall_surprise_score"] = data.get(
                "transcript_surprise_score",
                data["overall_surprise_score"],
            )
        return EarningsCallAnalysis.model_validate(data)

    data["consensus_surprise_score"] = None
    data["consensus_surprises"] = []

    if data.get("transcript_surprise_score", data["overall_surprise_score"]) > max_transcript_only_score:
        data["transcript_surprise_score"] = max_transcript_only_score
        was_capped = True

    if data["overall_surprise_score"] > max_transcript_only_score:
        data["overall_surprise_score"] = max_transcript_only_score
        was_capped = True

    data["overall_surprise_score"] = data.get("transcript_surprise_score", data["overall_surprise_score"])

    for item in data.get("surprise_items") or []:
        if item.get("score", 0) > max_transcript_only_score:
            item["score"] = max_transcript_only_score
            was_capped = True

    components = data.get("surprise_score_components") or {}
    components["external_context_adjustment"] = 0
    data["surprise_score_components"] = components

    if data.get("surprise_score_confidence") == "high":
        data["surprise_score_confidence"] = "medium"

    if was_capped:
        limitations = list(data.get("analysis_limitations") or [])
        capped_limitation = (
            f"Surprise score was capped at {max_transcript_only_score} "
            "because no external pre-call consensus was provided."
        )
        if capped_limitation.casefold() not in {item.casefold() for item in limitations}:
            limitations.insert(min(3, len(limitations)), capped_limitation)
        data["analysis_limitations"] = limitations[:5]

    return EarningsCallAnalysis.model_validate(data)


def enrich_analysis_context(
    *,
    analysis: EarningsCallAnalysis,
    has_previous_context: bool,
    has_prior_context: bool,
    has_history_context: bool = False,
) -> EarningsCallAnalysis:
    data = analysis.model_dump(mode="json")
    data["analysis_context"] = {
        "has_prior_quarter_transcript": has_previous_context,
        "has_external_consensus": has_prior_context,
        "has_historical_context": has_history_context,
        "surprise_score_is_transcript_only": not has_prior_context,
        "surprise_score_cap_applied": any(
            _limitation_category(item) == "surprise_score_cap"
            for item in data.get("analysis_limitations", [])
        ),
    }
    return EarningsCallAnalysis.model_validate(data)


def enrich_temporal_comparison(
    *,
    analysis: EarningsCallAnalysis,
    history_context_text: str | None,
) -> EarningsCallAnalysis:
    """Fill a conservative temporal comparison when history exists and Claude omits it."""
    if not history_context_text:
        return analysis

    data = analysis.model_dump(mode="json")
    temporal = data.get("temporal_comparison") or {}
    if any(
        temporal.get(key)
        for key in [
            "tone_change",
            "recurring_topics",
            "new_or_escalating_topics",
            "analyst_pressure_change",
            "historical_context_summary",
        ]
    ):
        return analysis

    history = _parse_context_json(history_context_text)
    if not history:
        return analysis

    current_topics = _current_analysis_topics(data)
    recurring_reference = list(
        (history.get("historical_patterns") or {}).get("recurring_topics") or []
    )
    recurring_topics = [
        topic for topic in current_topics if _matches_historical_topic(topic, recurring_reference)
    ][:6]
    new_or_escalating_topics = [
        topic for topic in current_topics if topic not in recurring_topics
    ][:5]
    latest_tone = _latest_historical_tone(history)
    current_tone = str(data.get("management_tone", {}).get("classification") or "unknown").replace("_", " ")

    if latest_tone:
        tone_change = f"Current tone was {current_tone}, versus {latest_tone} in the latest historical context."
    else:
        tone_change = f"Current tone was {current_tone}; historical tone trend was available but not conclusive."

    if new_or_escalating_topics:
        pressure_change = (
            "Analyst pressure covered recurring topics and added focus on "
            f"{_join_plain(new_or_escalating_topics[:2])}."
        )
    elif recurring_topics:
        pressure_change = (
            "Analyst pressure remained concentrated on historically recurring topics: "
            f"{_join_plain(recurring_topics[:3])}."
        )
    else:
        pressure_change = "Historical Q&A patterns did not provide a strong recurring-topic match."

    if recurring_topics and new_or_escalating_topics:
        summary = (
            f"History frames {_join_plain(recurring_topics[:2])} as recurring, while "
            f"{_join_plain(new_or_escalating_topics[:2])} appears newer or more urgent in the current call."
        )
    elif recurring_topics:
        summary = f"History suggests the main current topics were largely recurring: {_join_plain(recurring_topics[:3])}."
    else:
        summary = "History did not identify a clear recurring pattern for the main current-call topics."

    data["temporal_comparison"] = {
        "tone_change": tone_change,
        "recurring_topics": recurring_topics,
        "new_or_escalating_topics": new_or_escalating_topics,
        "analyst_pressure_change": pressure_change,
        "historical_context_summary": summary,
        "confidence": "medium",
    }
    return EarningsCallAnalysis.model_validate(data)


def _postprocess_analysis(
    *,
    analysis: EarningsCallAnalysis,
    full_transcript_text: str,
    source_text: str | None,
    has_previous_context: bool,
    has_prior_context: bool,
    has_history_context: bool,
    history_context_text: str | None,
) -> EarningsCallAnalysis:
    analysis = enrich_analysis_metadata(
        analysis=analysis,
        full_transcript_text=full_transcript_text,
        source_text=source_text,
    )
    analysis = enrich_analysis_limitations(
        analysis=analysis,
        has_previous_context=has_previous_context,
        has_prior_context=has_prior_context,
    )
    analysis = apply_surprise_score_policy(
        analysis=analysis,
        has_prior_context=has_prior_context,
    )
    analysis = enrich_analysis_context(
        analysis=analysis,
        has_previous_context=has_previous_context,
        has_prior_context=has_prior_context,
        has_history_context=has_history_context,
    )
    return enrich_temporal_comparison(
        analysis=analysis,
        history_context_text=history_context_text,
    )


def determine_self_critique_triggers(
    *,
    evidence_report: dict[str, Any],
    consistency_report: dict[str, Any],
    valid_quote_rate_threshold: float = 0.90,
) -> list[str]:
    triggers: list[str] = ["routine_haiku_self_critique"]
    consistency_summary = consistency_report.get("summary") or {}
    if int(consistency_summary.get("high") or 0) > 0:
        triggers.append("consistency_high")
    if int(consistency_summary.get("medium") or 0) > 0:
        triggers.append("consistency_medium")

    evidence_summary = evidence_report.get("summary") or {}
    valid_quote_rate = evidence_summary.get("valid_quote_rate")
    try:
        if float(valid_quote_rate) < valid_quote_rate_threshold:
            triggers.append("valid_quote_rate_below_0_90")
    except (TypeError, ValueError):
        triggers.append("valid_quote_rate_unavailable")

    return triggers


def should_use_sonnet_for_self_critique(
    *,
    evidence_report: dict[str, Any],
    consistency_report: dict[str, Any],
    valid_quote_rate_threshold: float = 0.90,
) -> bool:
    triggers = determine_self_critique_triggers(
        evidence_report=evidence_report,
        consistency_report=consistency_report,
        valid_quote_rate_threshold=valid_quote_rate_threshold,
    )
    return any(
        trigger in {"consistency_high", "consistency_medium", "valid_quote_rate_below_0_90"}
        for trigger in triggers
    )


def select_self_critique_model(
    *,
    settings: Any,
    evidence_report: dict[str, Any],
    consistency_report: dict[str, Any],
) -> str:
    if should_use_sonnet_for_self_critique(
        evidence_report=evidence_report,
        consistency_report=consistency_report,
    ):
        return settings.anthropic_review_model
    return settings.anthropic_model


def build_run_metadata(
    *,
    pdf_path: Path,
    output_dir: Path,
    page_count: int,
    segment_count: int,
    qa_turn_count: int,
    settings: Any,
    repair_attempts: int,
    review_used: bool,
    review_model: str | None,
    self_critique_used: bool,
    self_critique_model: str | None,
    self_critique_triggers: list[str],
    has_previous_context: bool,
    has_prior_context: bool,
    has_history_context: bool,
    prior_context_path: Path | None,
    history_context_path: Path | None,
    evidence_report: dict[str, Any],
    consistency_report: dict[str, Any] | None = None,
    analysis: EarningsCallAnalysis,
) -> dict[str, Any]:
    return {
        "source_pdf": str(pdf_path),
        "output_dir": str(output_dir),
        "page_count": page_count,
        "segment_count": segment_count,
        "qa_turn_count": qa_turn_count,
        "analysis_model": settings.anthropic_model,
        "review_model": review_model if review_used else None,
        "review_used": review_used,
        "self_critique_used": self_critique_used,
        "self_critique_model": self_critique_model,
        "self_critique_triggers": self_critique_triggers,
        "temperature": settings.temperature,
        "max_output_tokens": settings.max_output_tokens,
        "repair_attempts": repair_attempts,
        "previous_transcript_provided": has_previous_context,
        "prior_context_provided": has_prior_context,
        "prior_context_path": str(prior_context_path) if prior_context_path else None,
        "history_context_provided": has_history_context,
        "history_context_path": str(history_context_path) if history_context_path else None,
        "surprise_score_cap_applied": analysis.analysis_context.surprise_score_cap_applied,
        "transcript_surprise_score": analysis.transcript_surprise_score,
        "consensus_surprise_score": analysis.consensus_surprise_score,
        "overall_surprise_score": analysis.overall_surprise_score,
        "schema_version": analysis.schema_version,
        "evidence_summary": evidence_report.get("summary", {}),
        "consistency_summary": (consistency_report or {}).get("summary", {}),
    }


def _append_unique_limitation(limitations: list[str], value: str) -> None:
    normalized_existing = {item.strip().casefold() for item in limitations}
    if value.strip().casefold() not in normalized_existing:
        limitations.append(value)


def _limitation_category(value: str) -> str:
    normalized = value.casefold()
    if "surprise score was capped" in normalized:
        return "surprise_score_cap"
    if "pre-call consensus" in normalized or "market consensus" in normalized:
        return "pre_call_consensus"
    if "prior-quarter" in normalized or "prior quarter" in normalized or "previous quarter" in normalized:
        return "prior_quarter"
    if "surprise score" in normalized and "transcript" in normalized:
        return "transcript_only_surprise"
    return normalized.strip()


def _extract_company_name(text: str) -> str | None:
    if re.search(r"\bBanco\s+do\s+Brasil\b", text, flags=re.IGNORECASE):
        return "Banco do Brasil"
    return None


def _extract_ticker(text: str) -> str | None:
    match = re.search(r"\(([A-Z]{4}\d{1,2})\)", text)
    if match:
        return match.group(1)

    match = re.search(r"\b([A-Z]{4}\d{1,2})\b", text)
    if match:
        return match.group(1)
    return None


def _extract_quarter(text: str) -> str | None:
    match = re.search(r"\b([1-4]Q\d{2,4})\b", text, flags=re.IGNORECASE)
    if match:
        return match.group(1).upper()

    match = re.search(r"\b(Q[1-4]\s+20\d{2})\b", text, flags=re.IGNORECASE)
    if match:
        return re.sub(r"\s+", " ", match.group(1).upper())
    return None


def _extract_call_date(text: str) -> str | None:
    months = (
        "January|February|March|April|May|June|July|August|September|"
        "October|November|December"
    )
    match = re.search(
        rf"\b({months})\s+\d{{1,2}}(?:st|nd|rd|th)?,\s+\d{{4}}\b",
        text,
        flags=re.IGNORECASE,
    )
    if match:
        return match.group(0)

    match = re.search(r"\b\d{1,2}/\d{1,2}/\d{4}\b", text)
    if match:
        return match.group(0)
    return None


def _load_pdf_source_metadata(pdf_path: Path) -> str:
    try:
        return load_pdf_metadata_text(pdf_path)
    except Exception:
        return pdf_path.name


def _load_optional_context(path: str | Path | None) -> str | None:
    if path is None:
        return None

    context_path = Path(path).expanduser()
    if not context_path.exists():
        raise OSError(f"Arquivo de contexto nao encontrado: {context_path}")
    if context_path.suffix.lower() == ".pdf":
        pages = load_pdf_pages(context_path)
        cleaned_pages = clean_transcript_pages(pages)
        return build_clean_text(cleaned_pages, include_page_markers=True)
    return context_path.read_text(encoding="utf-8")


def resolve_prior_context_path(
    *,
    explicit_path: str | Path | None,
    pdf_path: Path,
    transcript_text: str,
    source_text: str | None = None,
) -> Path | None:
    if explicit_path is not None:
        return Path(explicit_path).expanduser()

    ticker, quarter = _infer_context_identifiers(
        pdf_path=pdf_path,
        transcript_text=transcript_text,
        source_text=source_text,
    )
    if not ticker or not quarter:
        return None

    filenames = [
        f"{ticker}_{quarter}_pre_call_consensus.json",
        f"{ticker}_{quarter.lower()}_pre_call_consensus.json",
    ]
    search_dirs = _context_search_dirs(pdf_path)
    for directory in search_dirs:
        for filename in filenames:
            candidate = directory / filename
            if candidate.exists():
                return candidate
        matches = sorted(directory.glob(f"{ticker}_{quarter}*consensus*.json"))
        if matches:
            return matches[0]
    return None


def resolve_history_context_path(
    *,
    explicit_path: str | Path | None,
    pdf_path: Path,
    transcript_text: str,
    source_text: str | None = None,
) -> Path | None:
    if explicit_path is not None:
        return Path(explicit_path).expanduser()

    ticker, _quarter = _infer_context_identifiers(
        pdf_path=pdf_path,
        transcript_text=transcript_text,
        source_text=source_text,
    )
    if not ticker:
        return None

    filenames = [
        f"{ticker}_history_context.json",
        f"{ticker.lower()}_history_context.json",
    ]
    for directory in _context_search_dirs(pdf_path, include_context_dir=True):
        for filename in filenames:
            candidate = directory / filename
            if candidate.exists():
                return candidate
        matches = sorted(directory.glob(f"{ticker}*history*context*.json"))
        if matches:
            return matches[0]
    return None


def _infer_context_identifiers(
    *,
    pdf_path: Path,
    transcript_text: str,
    source_text: str | None = None,
) -> tuple[str | None, str | None]:
    searchable_text = f"{pdf_path.name}\n{source_text or ''}\n{transcript_text}"
    return _extract_ticker(searchable_text), _extract_quarter(searchable_text)


def _context_search_dirs(pdf_path: Path, *, include_context_dir: bool = False) -> list[Path]:
    cwd = Path.cwd()
    directories = [
        pdf_path.parent,
        cwd / "data",
        cwd,
    ]
    if include_context_dir:
        directories.insert(0, cwd / "context")
        directories.append(pdf_path.parent.parent / "context")

    unique_dirs: list[Path] = []
    seen: set[Path] = set()
    for directory in directories:
        resolved = directory.resolve()
        if resolved in seen or not directory.exists():
            continue
        seen.add(resolved)
        unique_dirs.append(directory)
    return unique_dirs


def _load_prior_context(path: str | Path | None) -> str | None:
    if path is None:
        return None

    context_path = Path(path).expanduser()
    if not context_path.exists():
        raise OSError(f"Arquivo de contexto nao encontrado: {context_path}")
    if context_path.suffix.lower() == ".json":
        return compact_prior_context_json(context_path.read_text(encoding="utf-8"))
    return _load_optional_context(context_path)


def _load_history_context(path: str | Path | None) -> str | None:
    if path is None:
        return None

    context_path = Path(path).expanduser()
    if not context_path.exists():
        raise OSError(f"Arquivo de contexto historico nao encontrado: {context_path}")
    if context_path.suffix.lower() == ".json":
        return compact_history_context_json(context_path.read_text(encoding="utf-8"))
    return context_path.read_text(encoding="utf-8")


def compact_history_context_json(raw_json: str) -> str:
    data = json.loads(raw_json)
    keys_to_keep = [
        "context_type",
        "ticker",
        "company",
        "period_covered",
        "source_count",
        "quarters",
        "historical_patterns",
    ]
    compacted = {key: data[key] for key in keys_to_keep if key in data}
    for quarter in compacted.get("quarters", []):
        if not isinstance(quarter, dict):
            continue
        quarter.pop("segment_count", None)
        quarter.pop("qa_turn_count", None)
        quarter["notable_management_quotes"] = quarter.get("notable_management_quotes", [])[:2]
        quarter["recurring_red_flag_language"] = quarter.get("recurring_red_flag_language", [])[:2]
    compacted["usage_rules"] = [
        "Use this only as historical context, not as current-call evidence.",
        "Use recurring topics to calibrate whether current-call issues are new, persistent, or escalating.",
        "Do not quote historical transcript excerpts as evidence for current-call claims.",
    ]
    return (
        "Compacted historical transcript context JSON:\n"
        + json.dumps(compacted, ensure_ascii=False, indent=2)
    )


def _parse_context_json(context_text: str) -> dict[str, Any] | None:
    stripped = context_text.strip()
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        parsed = json.loads(stripped[start : end + 1])
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _current_analysis_topics(data: dict[str, Any]) -> list[str]:
    topics: list[str] = []
    for item in data.get("guidance_changes") or []:
        _append_unique_topic(topics, item.get("topic"))
    for item in data.get("critical_questions") or []:
        _append_unique_topic(topics, item.get("topic"))
    for item in data.get("consensus_surprises") or []:
        _append_unique_topic(topics, item.get("topic"))
    for item in data.get("surprise_items") or []:
        _append_unique_topic(topics, item.get("item"))
    return topics


def _append_unique_topic(topics: list[str], value: Any) -> None:
    if not value:
        return
    topic = str(value).strip()
    if not topic:
        return
    normalized_existing = {_normalize_topic(existing) for existing in topics}
    if _normalize_topic(topic) not in normalized_existing:
        topics.append(topic)


def _matches_historical_topic(current_topic: str, historical_topics: list[str]) -> bool:
    normalized_current = _normalize_topic(current_topic)
    current_tokens = set(normalized_current.split())
    for historical_topic in historical_topics:
        normalized_historical = _normalize_topic(str(historical_topic).replace("_", " "))
        if normalized_historical in normalized_current or normalized_current in normalized_historical:
            return True
        if current_tokens & _historical_topic_keywords(normalized_historical):
            return True
    return False


def _historical_topic_keywords(normalized_historical_topic: str) -> set[str]:
    keyword_map = {
        "asset quality": {"asset", "quality", "npl", "delinquency", "credit"},
        "provisions cost of credit": {"provision", "provisions", "credit", "cost"},
        "agribusiness": {"agribusiness", "agro"},
        "capital": {"capital", "cet1"},
        "nii": {"nii", "selic", "interest", "margin"},
        "guidance": {"guidance", "outlook"},
        "profitability": {"roe", "profitability", "income", "earnings"},
        "tax": {"tax", "dta"},
        "portfolio mix": {"portfolio", "mix", "individuals"},
        "dividends": {"dividend", "payout"},
    }
    return keyword_map.get(normalized_historical_topic, set(normalized_historical_topic.split()))


def _normalize_topic(value: str) -> str:
    normalized = value.casefold().replace("&", " and ")
    normalized = re.sub(r"\b20\d{2}\b|\b[1-4]q\d{2}\b", " ", normalized)
    normalized = re.sub(r"[^a-z0-9]+", " ", normalized)
    return re.sub(r"\s+", " ", normalized).strip()


def _latest_historical_tone(history: dict[str, Any]) -> str | None:
    quarters = [item for item in history.get("quarters", []) if isinstance(item, dict)]
    dated = [
        item for item in quarters if item.get("quarter") and item.get("management_tone_hint")
    ]
    if not dated:
        return None
    latest = sorted(dated, key=lambda item: _quarter_sort_key_for_context(str(item["quarter"])))[-1]
    return str(latest.get("management_tone_hint"))


def _quarter_sort_key_for_context(quarter: str) -> tuple[int, int]:
    match = re.fullmatch(r"([1-4])Q(\d{2})", quarter, flags=re.IGNORECASE)
    if not match:
        return (0, 0)
    return (2000 + int(match.group(2)), int(match.group(1)))


def _join_plain(items: list[str]) -> str:
    cleaned = [item for item in items if item]
    if not cleaned:
        return ""
    if len(cleaned) == 1:
        return cleaned[0]
    return ", ".join(cleaned[:-1]) + f" and {cleaned[-1]}"


def compact_prior_context_json(raw_json: str) -> str:
    data = json.loads(raw_json)
    keys_to_keep = [
        "document_title",
        "ticker",
        "company",
        "quarter",
        "document_purpose",
        "methodology",
        "pre_call_consensus_summary",
        "known_before_call",
        "unknown_before_call",
        "potential_surprises_before_call",
        "expected_vs_surprise_framework",
        "consensus_by_topic",
        "materiality_weights",
        "prior_formal_guidance",
        "pre_call_estimates_and_actuals",
        "prompt_usage_guardrails",
        "recommended_tool_fields",
    ]
    compacted = {
        key: _remove_post_result_backtesting_references(data[key])
        for key in keys_to_keep
        if key in data
    }
    compacted["usage_rules"] = [
        "Use this as pre-call consensus/proxy context only.",
        "Do not treat post-result actuals as pre-call expectations.",
        "Use known_before_call to avoid over-scoring items already expected.",
        "Use unknown_before_call, potential_surprises_before_call, expected_vs_surprise_framework, and materiality_weights to calibrate consensus_surprises.",
        "Use prior_formal_guidance as prior guidance only when comparing to call statements.",
        "Do not copy post-result/new guidance ranges into call_statement unless they appear in literal transcript evidence.",
    ]
    return (
        "Compacted pre-call consensus context JSON:\n"
        + json.dumps(compacted, ensure_ascii=False, indent=2)
    )


def _remove_post_result_backtesting_references(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _remove_post_result_backtesting_references(child)
            for key, child in value.items()
            if key != "post_result_actuals_for_backtesting"
            and key != "actual"
            and not key.startswith("surprise_")
            and key != "within_range"
        }
    if isinstance(value, list):
        cleaned = [_remove_post_result_backtesting_references(item) for item in value]
        return [
            item
            for item in cleaned
            if not (
                isinstance(item, str)
                and "post_result_actuals_for_backtesting" in item
            )
        ]
    return value


def _strip_markdown_fence(text: str) -> str:
    lines = text.splitlines()
    if lines and lines[0].strip().startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines).strip()


def _validate_evidence(
    *,
    analysis: EarningsCallAnalysis,
    full_transcript_text: str,
    transcript_segments: list[dict[str, Any]] | None = None,
) -> tuple[EarningsCallAnalysis, dict[str, Any]]:
    analysis_dict = analysis.model_dump(mode="json")
    validated_dict, evidence_report = validate_analysis_evidence(
        analysis_dict=analysis_dict,
        full_transcript_text=full_transcript_text,
        transcript_segments=transcript_segments,
    )
    return EarningsCallAnalysis.model_validate(validated_dict), evidence_report


def _write_analysis_outputs(
    *,
    analysis: EarningsCallAnalysis,
    analysis_path: Path,
    report_path: Path,
    evidence_report: dict[str, Any] | None,
) -> None:
    analysis_path.write_text(
        json.dumps(analysis.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    write_executive_report(analysis, report_path, evidence_report=evidence_report)
