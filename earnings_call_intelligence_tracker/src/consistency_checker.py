from __future__ import annotations

import re
from collections import Counter
from typing import Any


ConsistencyIssue = dict[str, Any]

NUMBER_RE = re.compile(
    r"(?<![A-Za-z0-9])"
    r"(?:R\$\s*)?\d+(?:[.,]\d+)?"
    r"(?:\s*(?:-|–|to)\s*(?:R\$\s*)?\d+(?:[.,]\d+)?)?"
    r"\s*(?:bn|billion|bps|bp|pp|p\.p\.|%)?"
    r"(?![A-Za-z0-9])",
    flags=re.IGNORECASE,
)


def check_analysis_consistency(
    analysis_dict: dict[str, Any],
    evidence_report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run deterministic consistency checks over validated analysis JSON.

    This module does not judge the investment thesis. It checks whether the
    final JSON is internally coherent after schema validation, surprise-score
    policy, and mechanical evidence validation.
    """
    issues: list[ConsistencyIssue] = []
    _check_evidence_report(evidence_report or {}, issues)
    _check_surprise_context(analysis_dict, issues)
    _check_score_components(analysis_dict, issues)
    _check_statement_basis(analysis_dict, issues)

    counts = Counter(issue["severity"] for issue in issues)
    high_count = counts.get("high", 0)
    return {
        "summary": {
            "passed": high_count == 0,
            "issues_count": len(issues),
            "high": high_count,
            "medium": counts.get("medium", 0),
            "low": counts.get("low", 0),
        },
        "issues": issues,
    }


def _check_evidence_report(evidence_report: dict[str, Any], issues: list[ConsistencyIssue]) -> None:
    summary = evidence_report.get("summary") or {}
    total_quotes = int(summary.get("total_quotes") or 0)
    if total_quotes == 0:
        _add_issue(
            issues,
            path="evidence_report.summary.total_quotes",
            severity="medium",
            issue_type="missing_evidence_checks",
            message="No evidence quotes were checked.",
            suggestion="Review evidence_checker.py output and ensure the analysis contains literal quotes.",
        )
        return

    invalid_quotes = int(summary.get("invalid_quotes") or 0)
    if invalid_quotes:
        _add_issue(
            issues,
            path="evidence_report.summary.invalid_quotes",
            severity="high",
            issue_type="invalid_evidence",
            message=f"{invalid_quotes} quote(s) were not found in the transcript.",
            suggestion="Review invalid_quotes before relying on the analysis or executive report.",
        )

    invalid_speakers = int(summary.get("speaker_invalid_quotes") or 0)
    if invalid_speakers:
        _add_issue(
            issues,
            path="evidence_report.summary.speaker_invalid_quotes",
            severity="medium",
            issue_type="speaker_mismatch",
            message=f"{invalid_speakers} quote(s) were found but not attributed to the expected speaker.",
            suggestion="Check speaker attribution in transcript_segments.json and analysis.json.",
        )


def _check_surprise_context(analysis: dict[str, Any], issues: list[ConsistencyIssue]) -> None:
    context = analysis.get("analysis_context") or {}
    limitations = " ".join(analysis.get("analysis_limitations") or []).casefold()
    has_external_consensus = bool(context.get("has_external_consensus"))
    transcript_only = bool(context.get("surprise_score_is_transcript_only"))
    consensus_score = analysis.get("consensus_surprise_score")
    transcript_score = analysis.get("transcript_surprise_score")
    overall_score = analysis.get("overall_surprise_score")
    consensus_surprises = analysis.get("consensus_surprises") or []

    if has_external_consensus:
        if transcript_only:
            _add_issue(
                issues,
                path="analysis_context.surprise_score_is_transcript_only",
                severity="high",
                issue_type="surprise_context_conflict",
                message="External consensus is present, but the score is still marked as transcript-only.",
                suggestion="Set surprise_score_is_transcript_only=false when --prior-context is provided.",
            )
        if consensus_score is None:
            _add_issue(
                issues,
                path="consensus_surprise_score",
                severity="high",
                issue_type="missing_consensus_score",
                message="External consensus is present, but consensus_surprise_score is null.",
                suggestion="Populate consensus_surprise_score or remove the external-consensus context flag.",
            )
        elif overall_score != consensus_score:
            _add_issue(
                issues,
                path="overall_surprise_score",
                severity="medium",
                issue_type="score_mismatch",
                message="overall_surprise_score does not match consensus_surprise_score.",
                suggestion="When consensus is available, overall_surprise_score should use the consensus-based score.",
            )
        if not consensus_surprises:
            _add_issue(
                issues,
                path="consensus_surprises",
                severity="medium",
                issue_type="missing_consensus_surprises",
                message="External consensus is present, but no consensus surprise items were produced.",
                suggestion="Generate consensus_surprises from the prior-context comparison or lower score confidence.",
            )
        if "transcript-only" in limitations or "transcript only" in limitations:
            _add_issue(
                issues,
                path="analysis_limitations",
                severity="low",
                issue_type="stale_limitation",
                message="Limitations still mention transcript-only surprise scoring despite external consensus.",
                suggestion="Remove stale transcript-only limitation when --prior-context is provided.",
            )
    else:
        if not transcript_only:
            _add_issue(
                issues,
                path="analysis_context.surprise_score_is_transcript_only",
                severity="high",
                issue_type="surprise_context_conflict",
                message="No external consensus is present, but the score is not marked as transcript-only.",
                suggestion="Set surprise_score_is_transcript_only=true without --prior-context.",
            )
        if consensus_score is not None:
            _add_issue(
                issues,
                path="consensus_surprise_score",
                severity="high",
                issue_type="unexpected_consensus_score",
                message="consensus_surprise_score is populated without external consensus.",
                suggestion="Set consensus_surprise_score=null unless --prior-context is provided.",
            )
        if consensus_surprises:
            _add_issue(
                issues,
                path="consensus_surprises",
                severity="high",
                issue_type="unexpected_consensus_surprises",
                message="consensus_surprises are populated without external consensus.",
                suggestion="Clear consensus_surprises unless --prior-context is provided.",
            )
        if overall_score != transcript_score:
            _add_issue(
                issues,
                path="overall_surprise_score",
                severity="medium",
                issue_type="score_mismatch",
                message="overall_surprise_score does not match transcript_surprise_score without consensus.",
                suggestion="Without prior context, overall_surprise_score should equal transcript_surprise_score.",
            )
        if isinstance(overall_score, int) and overall_score > 60:
            _add_issue(
                issues,
                path="overall_surprise_score",
                severity="medium",
                issue_type="transcript_only_score_uncapped",
                message="Transcript-only surprise score is above the configured cap of 60.",
                suggestion="Apply the transcript-only cap or provide --prior-context.",
            )


def _check_score_components(analysis: dict[str, Any], issues: list[ConsistencyIssue]) -> None:
    context = analysis.get("analysis_context") or {}
    components = analysis.get("surprise_score_components") or {}
    if not context.get("has_external_consensus") and components.get("external_context_adjustment", 0) != 0:
        _add_issue(
            issues,
            path="surprise_score_components.external_context_adjustment",
            severity="medium",
            issue_type="unexpected_external_adjustment",
            message="external_context_adjustment is non-zero without external consensus.",
            suggestion="Use 0 for external_context_adjustment unless --prior-context is provided.",
        )


def _check_statement_basis(analysis: dict[str, Any], issues: list[ConsistencyIssue]) -> None:
    for index, item in enumerate(analysis.get("guidance_changes") or []):
        _check_numeric_support(
            item=item,
            statement_key="current_statement",
            evidence_key="evidence",
            path=f"guidance_changes[{index}]",
            issues=issues,
        )

    for index, item in enumerate(analysis.get("consensus_surprises") or []):
        _check_numeric_support(
            item=item,
            statement_key="call_statement",
            evidence_key="evidence",
            path=f"consensus_surprises[{index}]",
            issues=issues,
        )


def _check_numeric_support(
    *,
    item: dict[str, Any],
    statement_key: str,
    evidence_key: str,
    path: str,
    issues: list[ConsistencyIssue],
) -> None:
    statement_basis = item.get("statement_basis")
    statement = str(item.get(statement_key) or "")
    statement_numbers = _numeric_tokens(statement)
    if not statement_numbers:
        return

    evidence_text = " ".join(
        str(evidence.get("quote") or "")
        for evidence in item.get(evidence_key) or []
        if isinstance(evidence, dict)
    )
    evidence_numbers = _numeric_tokens(evidence_text)
    missing_numbers = sorted(statement_numbers - evidence_numbers)
    if not missing_numbers:
        return

    if statement_basis == "explicit":
        severity = "medium"
        issue_type = "unsupported_explicit_numeric_claim"
        message = (
            f"{statement_key} contains numeric token(s) not present in its evidence quotes: "
            f"{', '.join(missing_numbers)}."
        )
        suggestion = "Either add transcript evidence containing these numbers or mark the statement as inferred/external_context."
    elif statement_basis == "inferred":
        severity = "low"
        issue_type = "unsupported_inferred_numeric_claim"
        message = (
            f"{statement_key} contains inferred numeric token(s) not present in its evidence quotes: "
            f"{', '.join(missing_numbers)}."
        )
        suggestion = "Keep numeric inferences conservative and explain them in limitations when material."
    else:
        severity = "low"
        issue_type = "external_context_numeric_claim"
        message = (
            f"{statement_key} contains numeric token(s) supported by context rather than transcript evidence: "
            f"{', '.join(missing_numbers)}."
        )
        suggestion = "Avoid using external-context numbers as transcript call statements."

    _add_issue(
        issues,
        path=f"{path}.{statement_key}",
        severity=severity,
        issue_type=issue_type,
        message=message,
        suggestion=suggestion,
    )


def _numeric_tokens(text: str) -> set[str]:
    tokens: set[str] = set()
    for match in NUMBER_RE.finditer(text):
        token = _normalize_numeric_token(match.group(0))
        if not token or _is_year_token(token):
            continue
        tokens.add(token)
    return tokens


def _normalize_numeric_token(value: str) -> str:
    normalized = value.casefold()
    normalized = normalized.replace("r$", "")
    normalized = normalized.replace("–", "-")
    normalized = re.sub(r"\s+to\s+", "-", normalized)
    normalized = re.sub(r"\s+", "", normalized)
    normalized = normalized.replace(",", ".")
    normalized = normalized.replace("p.p.", "pp")
    normalized = normalized.strip(".")
    return normalized


def _is_year_token(token: str) -> bool:
    return bool(re.fullmatch(r"20\d{2}", token))


def _add_issue(
    issues: list[ConsistencyIssue],
    *,
    path: str,
    severity: str,
    issue_type: str,
    message: str,
    suggestion: str,
) -> None:
    issues.append(
        {
            "path": path,
            "severity": severity,
            "issue_type": issue_type,
            "message": message,
            "suggestion": suggestion,
        }
    )
