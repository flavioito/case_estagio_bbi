from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from src.anthropic_client import AnthropicClient
from src.config import get_settings
from src.evidence_checker import validate_analysis_evidence
from src.pdf_loader import load_pdf_metadata_text, load_pdf_pages
from src.prompts import (
    SYSTEM_PROMPT,
    build_analysis_prompt,
    build_json_repair_prompt,
    build_review_prompt,
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
    executive_report_path: Path
    run_metadata_path: Path
    repair_attempts: int
    review_used: bool
    analysis_model: str
    review_model: str | None


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
    language: str = "en-US",
    debug: bool | None = None,
    max_repair_attempts: int = 1,
    review_with_sonnet: bool = False,
) -> Day2Result:
    settings = get_settings()
    should_debug = settings.debug if debug is None else debug

    day1 = run_day1_pipeline(pdf_path=pdf_path, output_dir=output_dir, debug=debug)
    segments = json.loads(day1.segments_path.read_text(encoding="utf-8"))
    qa_turns = json.loads(day1.qa_turns_path.read_text(encoding="utf-8"))

    previous_text = _load_optional_context(previous)
    prior_context_text = _load_prior_context(prior_context)

    user_prompt = build_analysis_prompt(
        transcript_segments=segments,
        qa_turns=qa_turns,
        previous_context=previous_text,
        prior_context=prior_context_text,
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

    if review_with_sonnet:
        haiku_analysis_path = day1.output_dir / "analysis_haiku.json"
        haiku_report_path = day1.output_dir / "executive_report_haiku.md"
        _write_analysis_outputs(
            analysis=analysis,
            analysis_path=haiku_analysis_path,
            report_path=haiku_report_path,
            evidence_report=None,
        )

        review_prompt = build_review_prompt(
            analysis_json=json.dumps(analysis.model_dump(mode="json"), ensure_ascii=False, indent=2),
            transcript_segments=segments,
            language=language,
        )
        if should_debug:
            (day1.output_dir / "review_prompt.txt").write_text(review_prompt, encoding="utf-8")

        review_raw_response = client.send_message(
            system_prompt=SYSTEM_PROMPT,
            user_prompt=review_prompt,
            model=settings.anthropic_review_model,
        )
        analysis, review_repairs, review_final_raw_response = _validate_or_repair_analysis(
            client=client,
            raw_response=review_raw_response,
            max_repair_attempts=max_repair_attempts,
            model=settings.anthropic_review_model,
        )
        repair_attempts += review_repairs
        if should_debug:
            (day1.output_dir / "review_raw_response.txt").write_text(
                review_final_raw_response,
                encoding="utf-8",
            )

    full_transcript_text = day1.clean_text_path.read_text(encoding="utf-8")
    analysis = enrich_analysis_metadata(
        analysis=analysis,
        full_transcript_text=full_transcript_text,
        source_text=_load_pdf_source_metadata(day1.pdf_path),
    )
    analysis = enrich_analysis_limitations(
        analysis=analysis,
        has_previous_context=previous_text is not None,
        has_prior_context=prior_context_text is not None,
    )
    analysis = apply_surprise_score_policy(
        analysis=analysis,
        has_prior_context=prior_context_text is not None,
    )
    analysis = enrich_analysis_context(
        analysis=analysis,
        has_previous_context=previous_text is not None,
        has_prior_context=prior_context_text is not None,
    )

    analysis, evidence_report = _validate_evidence(
        analysis=analysis,
        full_transcript_text=full_transcript_text,
        transcript_segments=segments,
    )

    analysis_path = day1.output_dir / "analysis.json"
    evidence_report_path = day1.output_dir / "evidence_report.json"
    executive_report_path = day1.output_dir / "executive_report.md"
    run_metadata_path = day1.output_dir / "run_metadata.json"
    evidence_report_path.write_text(
        json.dumps(evidence_report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    if evidence_report["warnings"]:
        for warning in evidence_report["warnings"]:
            print(warning)

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
                review_used=review_with_sonnet,
                has_previous_context=previous_text is not None,
                has_prior_context=prior_context_text is not None,
                evidence_report=evidence_report,
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
        executive_report_path=executive_report_path,
        run_metadata_path=run_metadata_path,
        repair_attempts=repair_attempts,
        review_used=review_with_sonnet,
        analysis_model=settings.anthropic_model,
        review_model=settings.anthropic_review_model if review_with_sonnet else None,
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
) -> EarningsCallAnalysis:
    data = analysis.model_dump(mode="json")
    data["analysis_context"] = {
        "has_prior_quarter_transcript": has_previous_context,
        "has_external_consensus": has_prior_context,
        "surprise_score_is_transcript_only": not has_prior_context,
        "surprise_score_cap_applied": any(
            _limitation_category(item) == "surprise_score_cap"
            for item in data.get("analysis_limitations", [])
        ),
    }
    return EarningsCallAnalysis.model_validate(data)


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
    has_previous_context: bool,
    has_prior_context: bool,
    evidence_report: dict[str, Any],
    analysis: EarningsCallAnalysis,
) -> dict[str, Any]:
    return {
        "source_pdf": str(pdf_path),
        "output_dir": str(output_dir),
        "page_count": page_count,
        "segment_count": segment_count,
        "qa_turn_count": qa_turn_count,
        "analysis_model": settings.anthropic_model,
        "review_model": settings.anthropic_review_model if review_used else None,
        "review_used": review_used,
        "temperature": settings.temperature,
        "max_output_tokens": settings.max_output_tokens,
        "repair_attempts": repair_attempts,
        "previous_transcript_provided": has_previous_context,
        "prior_context_provided": has_prior_context,
        "surprise_score_cap_applied": analysis.analysis_context.surprise_score_cap_applied,
        "transcript_surprise_score": analysis.transcript_surprise_score,
        "consensus_surprise_score": analysis.consensus_surprise_score,
        "overall_surprise_score": analysis.overall_surprise_score,
        "schema_version": analysis.schema_version,
        "evidence_summary": evidence_report.get("summary", {}),
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


def _load_prior_context(path: str | Path | None) -> str | None:
    if path is None:
        return None

    context_path = Path(path).expanduser()
    if not context_path.exists():
        raise OSError(f"Arquivo de contexto nao encontrado: {context_path}")
    if context_path.suffix.lower() == ".json":
        return compact_prior_context_json(context_path.read_text(encoding="utf-8"))
    return _load_optional_context(context_path)


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
