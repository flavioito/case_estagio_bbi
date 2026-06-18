from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Iterable

from src.schemas import (
    AnalystQuestion,
    ConsensusSurprise,
    EarningsCallAnalysis,
    Evidence,
    GuidanceChange,
    RedFlag,
    SurpriseItem,
    count_report_words,
)


MAX_REPORT_WORDS = 400


class ReportWriterError(Exception):
    """Raised when the executive report cannot be rendered or written."""


def render_executive_report(
    analysis: EarningsCallAnalysis,
    evidence_report: dict[str, Any] | None = None,
) -> str:
    """Render a deterministic Markdown report from validated analysis fields."""
    for config in _report_configs():
        report = _build_report(analysis, evidence_report, config)
        if count_words(report) <= MAX_REPORT_WORDS:
            return report

    raise ReportWriterError(
        f"Relatorio executivo excede {MAX_REPORT_WORDS} palavras mesmo na versao compacta."
    )


def _build_report(
    analysis: EarningsCallAnalysis,
    evidence_report: dict[str, Any] | None,
    config: dict[str, int],
) -> str:
    lines: list[str] = [f"# {_report_title(analysis)}", ""]

    guidance = _valid_guidance_changes(analysis.guidance_changes)
    questions = _valid_questions(analysis.critical_questions)
    red_flags = _valid_red_flags(analysis.red_flags)
    surprise = _valid_surprise_items(analysis.surprise_items)
    consensus = _valid_consensus_surprises(analysis.consensus_surprises)
    temporal_context = _temporal_comparison_line(
        analysis.temporal_comparison,
        max_words=config["temporal_words"],
        topic_limit=config["temporal_topic_count"],
    )

    lines.extend(
        [
            _executive_summary(
                analysis=analysis,
                guidance=guidance,
                questions=questions,
                max_words=config["summary_words"],
            ),
            "",
        ]
    )

    if guidance:
        lines.extend(["## Key Financial and Guidance Highlights"])
        for item in guidance[: config["guidance_count"]]:
            lines.append(_guidance_line(item, config["detail_words"]))
        lines.append("")

    if temporal_context:
        lines.extend(["## Temporal Context", temporal_context, ""])

    if questions:
        lines.extend(["## Key Themes From Analyst Q&A"])
        for item in questions[: config["question_count"]]:
            lines.append(_question_line(item, config["detail_words"]))
        lines.append("")

    if red_flags:
        lines.extend(["## Linguistic Red Flags"])
        for item in red_flags[: config["red_flag_count"]]:
            lines.append(_red_flag_line(item, config["quote_words"]))
        lines.append("")

    lines.extend(["## Surprise Context"])
    lines.append(_surprise_context_sentence(analysis))
    if consensus:
        for item in consensus[: config["surprise_count"]]:
            lines.append(_consensus_surprise_line(item, config["detail_words"]))
    elif surprise:
        for item in surprise[: config["surprise_count"]]:
            lines.append(_surprise_line(item, config["detail_words"]))
    else:
        lines.append("- Read the score with the stated limitations.")
    lines.append("")

    return "\n".join(lines).strip() + "\n"


def write_executive_report(
    analysis: EarningsCallAnalysis,
    output_path: str | Path,
    evidence_report: dict[str, Any] | None = None,
) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_executive_report(analysis, evidence_report), encoding="utf-8")
    return path


def count_words(markdown: str) -> int:
    return count_report_words(markdown)


def _executive_summary(
    *,
    analysis: EarningsCallAnalysis,
    guidance: list[GuidanceChange],
    questions: list[AnalystQuestion],
    max_words: int,
) -> str:
    main_themes = _join_phrases([item.topic for item in guidance[:2]])
    q_themes = _join_phrases([item.topic for item in questions[:2]])

    first_sentence = _fit_sentence(analysis.management_tone.summary, max_words // 2)
    summary = first_sentence
    if main_themes:
        summary += f" Key changes centered on {main_themes}"
    if q_themes:
        summary += f". Analyst focus centered on {q_themes}."
    else:
        summary += "."
    return _fit_sentence(summary, max_words)


def _valid_guidance_changes(items: list[GuidanceChange]) -> list[GuidanceChange]:
    return [item for item in items if _has_valid_evidence(item.evidence)]


def _valid_questions(items: list[AnalystQuestion]) -> list[AnalystQuestion]:
    return [item for item in items if _has_valid_evidence(item.evidence)]


def _valid_red_flags(items: list[RedFlag]) -> list[RedFlag]:
    return [item for item in items if item.evidence_validated is not False]


def _valid_surprise_items(items: list[SurpriseItem]) -> list[SurpriseItem]:
    return [item for item in items if _has_valid_evidence(item.evidence)]


def _valid_consensus_surprises(items: list[ConsensusSurprise]) -> list[ConsensusSurprise]:
    return [item for item in items if _has_valid_evidence(item.evidence)]


def _has_valid_evidence(evidence: Iterable[Evidence]) -> bool:
    evidence_list = list(evidence)
    if not evidence_list:
        return False
    return any(item.evidence_validated is not False for item in evidence_list)


def _report_title(analysis: EarningsCallAnalysis) -> str:
    parts = [part for part in [analysis.ticker, analysis.quarter] if part]
    if parts:
        return f"{' '.join(parts)} Summary"
    if analysis.company_name:
        return f"{analysis.company_name} Summary"
    return "Earnings Call Summary"


def _surprise_context_sentence(analysis: EarningsCallAnalysis) -> str:
    if analysis.consensus_surprise_score is not None:
        return "The call showed notable divergence from pre-call expectations."
    return "Surprise assessment is based only on transcript-internal signals."


def _join_phrases(items: list[str]) -> str:
    cleaned = [item.strip() for item in items if item and item.strip()]
    if not cleaned:
        return ""
    if len(cleaned) == 1:
        return cleaned[0]
    return ", ".join(cleaned[:-1]) + f" and {cleaned[-1]}"


def _temporal_comparison_line(
    temporal_comparison: Any,
    *,
    max_words: int,
    topic_limit: int,
) -> str:
    summary = getattr(temporal_comparison, "historical_context_summary", None)
    recurring = list(getattr(temporal_comparison, "recurring_topics", []) or [])[:topic_limit]
    escalating = list(getattr(temporal_comparison, "new_or_escalating_topics", []) or [])[:topic_limit]

    if recurring or escalating:
        parts: list[str] = []
        if recurring:
            parts.append(f"Recurring historical themes: {_join_phrases(recurring)}.")
        if escalating:
            parts.append(f"New or escalating themes: {_join_phrases(escalating)}.")
        line = " ".join(parts)
        if len(_words(line)) <= max_words:
            return line
        if recurring and escalating:
            return (
                f"Recurring historical theme: {recurring[0]}. "
                f"New or escalating theme: {escalating[0]}."
            )

    if summary:
        return _fit_sentence(summary, max_words)
    return ""


def _guidance_line(item: GuidanceChange, max_words: int) -> str:
    statement = _fit_sentence(item.current_statement, max_words)
    return (
        f"- {item.topic}: {item.metric_direction}; investment read-through {item.investment_implication}. "
        f"{statement}"
    )


def _question_line(item: AnalystQuestion, max_words: int) -> str:
    institution = f" ({item.institution})" if item.institution else ""
    response = _fit_sentence(item.management_response_summary, max_words)
    return (
        f"- {item.analyst}{institution}: {item.topic}; "
        f"quality {item.answer_quality}. Response: {response}"
    )


def _red_flag_line(item: RedFlag, quote_words: int) -> str:
    quote = _fit_quote(item.quote, quote_words)
    return f"- {item.speaker}: {quote}"


def _surprise_line(item: SurpriseItem, max_words: int) -> str:
    reason = _fit_sentence(item.why_surprising, max_words)
    return f"- {item.item}: {item.score}/100. {reason}"


def _consensus_surprise_line(item: ConsensusSurprise, max_words: int) -> str:
    statement = _fit_sentence(item.call_statement, max_words)
    return f"- {item.topic}: {statement}"


def _fit_quote(text: str, max_words: int) -> str:
    words = _words(text)
    if len(words) <= max_words:
        return _strip_terminal(_trim_bad_terminal_words(str(text)))
    first_sentence = _first_sentence(str(text))
    if first_sentence and len(_words(first_sentence)) <= max_words:
        return _strip_terminal(first_sentence)
    return _strip_terminal(_trim_bad_terminal_words(" ".join(words[:max_words])))


def _fit_sentence(text: str, max_words: int) -> str:
    cleaned = " ".join(str(text).split())
    if not cleaned:
        return ""

    words = _words(cleaned)
    if len(words) <= max_words:
        return _ensure_sentence(_trim_bad_terminal_words(cleaned))

    first_sentence = _first_sentence(cleaned)
    if first_sentence and len(_words(first_sentence)) <= max_words:
        return _ensure_sentence(first_sentence)

    clause = _best_clause(cleaned, max_words)
    if clause:
        return _ensure_sentence(clause)

    clipped = words[:max_words]
    while len(clipped) > 6 and clipped[-1].casefold().strip("().,;:") in _bad_terminal_words():
        clipped.pop()
    return _ensure_sentence(" ".join(clipped).rstrip(" ,;:"))


def _first_sentence(text: str) -> str | None:
    match = re.search(r"[.!?]\s+(?=[A-Z])", text)
    if match:
        return text[: match.start() + 1]
    return None


def _best_clause(text: str, max_words: int) -> str | None:
    for separator in ["; ", ", "]:
        if separator not in text:
            continue
        candidate = text.split(separator, 1)[0]
        word_count = len(_words(candidate))
        if 5 <= word_count <= max_words:
            return candidate
    return None


def _ensure_sentence(text: str) -> str:
    cleaned = _strip_terminal(text)
    if not cleaned:
        return ""
    return cleaned + "."


def _strip_terminal(text: str) -> str:
    return str(text).strip().rstrip(" .,;:")


def _words(text: str) -> list[str]:
    return str(text).split()


def _trim_bad_terminal_words(text: str) -> str:
    words = _words(text)
    while len(words) > 6 and words[-1].casefold().strip("().,;:") in _bad_terminal_words():
        words.pop()
    return " ".join(words)


def _bad_terminal_words() -> set[str]:
    return {
        "a",
        "an",
        "and",
        "as",
        "at",
        "be",
        "but",
        "by",
        "from",
        "for",
        "in",
        "is",
        "of",
        "or",
        "per",
        "that",
        "the",
        "to",
        "was",
        "were",
        "with",
        "would",
        "versus",
        "vs",
    }


def _report_configs() -> list[dict[str, int]]:
    return [
        {
            "summary_words": 58,
            "guidance_count": 4,
            "question_count": 3,
            "red_flag_count": 3,
            "surprise_count": 3,
            "temporal_topic_count": 2,
            "limitation_count": 2,
            "detail_words": 20,
            "quote_words": 12,
            "temporal_words": 34,
            "limitation_words": 16,
        },
        {
            "summary_words": 44,
            "guidance_count": 4,
            "question_count": 3,
            "red_flag_count": 3,
            "surprise_count": 2,
            "temporal_topic_count": 2,
            "limitation_count": 2,
            "detail_words": 16,
            "quote_words": 10,
            "temporal_words": 26,
            "limitation_words": 12,
        },
        {
            "summary_words": 34,
            "guidance_count": 3,
            "question_count": 3,
            "red_flag_count": 2,
            "surprise_count": 1,
            "temporal_topic_count": 1,
            "limitation_count": 1,
            "detail_words": 10,
            "quote_words": 8,
            "temporal_words": 18,
            "limitation_words": 12,
        },
    ]
