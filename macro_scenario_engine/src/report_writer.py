from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

from src.schemas import (
    AnalystQuestion,
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
    lines: list[str] = ["# Executive Earnings Call Brief", ""]

    bottom_line = _bottom_line(analysis, evidence_report)
    lines.extend(["## Bottom line", bottom_line, ""])

    lines.extend(
        [
            "## Management tone",
            _with_evidence_note(
                _shorten(analysis.management_tone.summary, 32),
                analysis.management_tone.evidence,
            ),
            "",
        ]
    )

    guidance = _valid_guidance_changes(analysis.guidance_changes)
    if guidance:
        lines.extend(["## Main guidance/theme changes"])
        for item in guidance[:2]:
            confidence_note = (
                f" Confidence: {item.confidence}."
                if item.confidence != "high"
                else ""
            )
            basis_note = (
                f" Basis: {item.statement_basis}."
                if item.statement_basis != "explicit"
                else ""
            )
            lines.append(
                f"- {_shorten(item.topic, 8)}: {_shorten(item.current_statement, 26)} "
                f"Implication: {item.investment_implication}.{confidence_note}{basis_note}"
            )
        lines.append("")

    questions = _valid_questions(analysis.critical_questions)
    if questions:
        lines.extend(["## Critical Q&A"])
        for item in questions[:2]:
            institution = f", {item.institution}" if item.institution else ""
            lines.append(
                f"- {item.analyst}{institution}: {item.topic}. "
                f"Response quality: {item.answer_quality}. "
                f"{_shorten(item.management_response_summary, 24)}"
            )
        lines.append("")

    red_flags = _valid_red_flags(analysis.red_flags)
    if red_flags:
        lines.extend(["## Red flags"])
        for item in red_flags[:2]:
            lines.append(
                f"- {item.type} ({item.severity}): "
                f"{_shorten(item.explanation, 18)}"
            )
        lines.append("")

    surprise = _valid_surprise_items(analysis.surprise_items)
    lines.extend(["## Surprise score"])
    score_label = (
        "consensus surprise score"
        if analysis.consensus_surprise_score is not None
        else "transcript surprise score"
    )
    if surprise:
        top = surprise[0]
        lines.append(
            f"{analysis.overall_surprise_score}/100 {score_label} "
            f"(confidence: {analysis.surprise_score_confidence}). "
            f"{_shorten(top.item, 8)}: {_shorten(top.why_surprising, 24)}"
        )
    else:
        lines.append(
            f"{analysis.overall_surprise_score}/100 {score_label} "
            f"(confidence: {analysis.surprise_score_confidence}). "
            "Score should be read with the stated limitations."
        )
    lines.append("")

    limitations = _limit_items(analysis.analysis_limitations, 1)
    if limitations:
        lines.extend(["## Limitations"])
        for item in limitations:
            lines.append(f"- {_shorten(item, 24)}")
        lines.append("")

    report = "\n".join(lines).strip() + "\n"
    return _enforce_word_limit(report)


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


def _bottom_line(
    analysis: EarningsCallAnalysis,
    evidence_report: dict[str, Any] | None,
) -> str:
    score = analysis.overall_surprise_score
    tone = analysis.management_tone.classification.replace("_", " ")
    score_label = "consensus" if analysis.consensus_surprise_score is not None else "transcript-only"
    base = f"Management tone was {tone}, with a {score_label} surprise score of {score}/100."
    summary = _evidence_summary_sentence(evidence_report)
    if summary:
        return f"{base} {summary}"
    return base


def _evidence_summary_sentence(evidence_report: dict[str, Any] | None) -> str | None:
    if not evidence_report:
        return None
    summary = evidence_report.get("summary", {})
    total = summary.get("total_quotes")
    if not total:
        return None
    valid_rate = summary.get("valid_quote_rate")
    invalid = summary.get("invalid_quotes")
    return f"Evidence validation: {valid_rate:.0%} valid quotes, {invalid} invalid."


def _with_evidence_note(summary: str, evidence: Iterable[Evidence]) -> str:
    valid = _valid_evidence(list(evidence))
    if valid:
        first = valid[0]
        page = f", p. {first.page}" if first.page else ""
        return f"{summary} Key evidence: \"{_shorten(first.quote, 18)}\" ({first.speaker}{page})."
    return f"{summary} Evidence should be reviewed because no validated quote was available for this section."


def _valid_guidance_changes(items: list[GuidanceChange]) -> list[GuidanceChange]:
    return [item for item in items if _has_valid_evidence(item.evidence)]


def _valid_questions(items: list[AnalystQuestion]) -> list[AnalystQuestion]:
    return [item for item in items if _has_valid_evidence(item.evidence)]


def _valid_red_flags(items: list[RedFlag]) -> list[RedFlag]:
    return [item for item in items if item.evidence_validated is not False]


def _valid_surprise_items(items: list[SurpriseItem]) -> list[SurpriseItem]:
    return [item for item in items if _has_valid_evidence(item.evidence)]


def _has_valid_evidence(evidence: Iterable[Evidence]) -> bool:
    evidence_list = list(evidence)
    if not evidence_list:
        return False
    return any(item.evidence_validated is not False for item in evidence_list)


def _valid_evidence(evidence: list[Evidence]) -> list[Evidence]:
    return [item for item in evidence if item.evidence_validated is not False]


def _limit_items(items: list[str], limit: int) -> list[str]:
    return [item for item in items if item][:limit]


def _shorten(text: str, max_words: int) -> str:
    words = str(text).split()
    if len(words) <= max_words:
        return str(text)
    return " ".join(words[:max_words]).rstrip(" ,;:") + "..."


def _enforce_word_limit(report: str) -> str:
    word_count = count_words(report)
    if word_count <= MAX_REPORT_WORDS:
        return report

    compact_lines = []
    for line in report.splitlines():
        if line.startswith("## Limitations"):
            break
        compact_lines.append(line)
    compact = "\n".join(compact_lines).strip() + "\n"
    if count_words(compact) <= MAX_REPORT_WORDS:
        return compact

    words = compact.split()
    truncated = " ".join(words[: MAX_REPORT_WORDS - 5]).rstrip(" ,;:") + "...\n"
    if count_words(truncated) <= MAX_REPORT_WORDS:
        return truncated
    raise ReportWriterError(f"Relatorio executivo excede {MAX_REPORT_WORDS} palavras: {word_count}.")
