from __future__ import annotations

from pathlib import Path

from src.report_writer import count_words, render_executive_report, write_executive_report
from src.schemas import EarningsCallAnalysis


def _analysis() -> EarningsCallAnalysis:
    evidence = {
        "quote": "the current context demands prudence",
        "speaker": "Geovanne Tobias",
        "page": 2,
        "rationale": "The quote supports a cautious tone assessment.",
        "evidence_validated": True,
        "match_type": "exact",
        "matched_text": "the current context demands prudence",
        "match_score": 1.0,
    }
    invalid_evidence = {
        "quote": "we are very concerned about credit quality",
        "speaker": "Felipe Prince",
        "page": 4,
        "rationale": "This is not literal.",
        "evidence_validated": False,
        "match_type": "not_found",
        "matched_text": None,
        "match_score": 0.0,
    }
    return EarningsCallAnalysis.model_validate(
        {
            "schema_version": "1.2",
            "company_name": "Banco do Brasil",
            "ticker": "BBAS3",
            "quarter": "1Q26",
            "call_date": "May 14th, 2026",
            "management_tone": {
                "classification": "cautious",
                "summary": "Management emphasized prudence.",
                "evidence": [evidence],
                "confidence": "high",
            },
            "guidance_changes": [
                {
                    "topic": "Cost of credit",
                    "metric_direction": "increased",
                    "investment_implication": "negative",
                    "statement_basis": "explicit",
                    "current_statement": "Management revised credit-cost expectations.",
                    "previous_reference": None,
                    "evidence": [evidence],
                    "confidence": "high",
                }
            ],
            "critical_questions": [
                {
                    "analyst": "Antônio Ruette",
                    "institution": "Bank of America",
                    "topic": "Provision guidance",
                    "why_critical": "It tested guidance credibility.",
                    "question_summary": "The analyst asked why provisions should stabilize.",
                    "management_response_summary": "Management said expected-loss models anticipated risk.",
                    "answer_quality": "adequate",
                    "evidence": [evidence],
                    "confidence": "high",
                }
            ],
            "red_flags": [
                {
                    "type": "uncertainty",
                    "quote": "many more uncertainties and challenges",
                    "speaker": "Geovanne Tobias",
                    "page": 2,
                    "explanation": "Signals uncertainty.",
                    "severity": "medium",
                    "confidence": "medium",
                    "evidence_validated": True,
                    "match_type": "exact",
                    "matched_text": "many more uncertainties and challenges",
                    "match_score": 1.0,
                },
                {
                    "type": "evasion",
                    "quote": "not a real quote",
                    "speaker": "Felipe Prince",
                    "page": 4,
                    "explanation": "Should be filtered.",
                    "severity": "high",
                    "confidence": "low",
                    "evidence_validated": False,
                    "match_type": "not_found",
                    "matched_text": None,
                    "match_score": 0.0,
                },
            ],
            "surprise_items": [
                {
                    "item": "Guidance revision",
                    "score": 70,
                    "why_surprising": "The call states that guidance ranges were revised.",
                    "evidence": [invalid_evidence],
                    "confidence": "low",
                    "limitation": "Transcript-only score.",
                }
            ],
            "consensus_surprises": [],
            "surprise_score_components": {
                "guidance_revision": 25,
                "analyst_pressure": 20,
                "tone_shift": 10,
                "new_material_numbers": 10,
                "external_context_adjustment": 0,
            },
            "transcript_surprise_score": 70,
            "consensus_surprise_score": None,
            "overall_surprise_score": 70,
            "surprise_score_confidence": "low",
            "analysis_context": {
                "has_prior_quarter_transcript": False,
                "has_external_consensus": False,
                "surprise_score_is_transcript_only": True,
                "surprise_score_cap_applied": False,
            },
            "analysis_limitations": ["Transcript-only surprise score."],
        }
    )


def test_render_executive_report_uses_structured_json() -> None:
    report = render_executive_report(_analysis())

    assert "# BBAS3 1Q26 Summary" in report
    assert not report.splitlines()[2].startswith("Banco do Brasil")
    assert "## Executive Summary" not in report
    assert "## Bottom line" not in report
    assert "## Management tone" not in report
    assert "## Limitations" not in report
    assert "Cost of credit" in report
    assert "Antônio Ruette (Bank of America)" in report


def test_render_executive_report_filters_invalid_evidence_items() -> None:
    report = render_executive_report(_analysis())

    assert "Should be filtered" not in report
    assert "Guidance revision" not in report
    assert "Geovanne Tobias: many more uncertainties and challenges" in report


def test_render_executive_report_keeps_evidence_summary_out_of_markdown() -> None:
    report = render_executive_report(
        _analysis(),
        evidence_report={
            "summary": {
                "total_quotes": 10,
                "valid_quote_rate": 0.8,
                "invalid_quotes": 2,
            }
        },
    )

    assert "80% valid quotes" not in report
    assert "Evidence validation" not in report


def test_render_executive_report_omits_schema_jargon_from_final_markdown() -> None:
    report = render_executive_report(_analysis())

    assert "confidence" not in report.casefold()
    assert "Basis:" not in report
    assert "uncertainty/" not in report
    assert "evasion/" not in report
    assert "70/100" not in report


def test_render_executive_report_keeps_guidance_without_statement_basis_label() -> None:
    analysis = _analysis()
    analysis.guidance_changes[0].statement_basis = "inferred"

    report = render_executive_report(analysis)

    assert "Management revised credit-cost expectations." in report
    assert "Basis:" not in report
    assert "inferred" not in report


def test_write_executive_report_creates_markdown_file(tmp_path: Path) -> None:
    report_path = tmp_path / "nested" / "executive_report.md"

    written_path = write_executive_report(_analysis(), report_path)

    assert written_path == report_path
    assert "# BBAS3 1Q26 Summary" in report_path.read_text(encoding="utf-8")


def test_count_words_ignores_markdown_symbols() -> None:
    assert count_words("# Title\n\nTone: cautiously-positive.") == 3


def test_render_executive_report_never_exceeds_400_words() -> None:
    analysis = _analysis()

    report = render_executive_report(analysis)

    assert count_words(report) <= 400


def test_render_executive_report_does_not_emit_trailing_ellipses() -> None:
    analysis = _analysis()
    analysis.management_tone.summary = " ".join(["Management discussed credit quality"] * 20)

    report = render_executive_report(analysis)

    assert "..." not in report
    assert count_words(report) <= 400


def test_render_executive_report_includes_top_three_questions() -> None:
    analysis = _analysis()
    base_question = analysis.critical_questions[0]
    analysis.critical_questions = [
        base_question.model_copy(update={"analyst": "Analyst One", "topic": "Provision guidance"}),
        base_question.model_copy(update={"analyst": "Analyst Two", "topic": "Capital adequacy"}),
        base_question.model_copy(update={"analyst": "Analyst Three", "topic": "Tax credits"}),
    ]

    report = render_executive_report(analysis)

    assert "Analyst One" in report
    assert "Analyst Two" in report
    assert "Analyst Three" in report
    assert count_words(report) <= 400


def test_render_executive_report_includes_temporal_context_when_available() -> None:
    analysis = _analysis()
    analysis.temporal_comparison.historical_context_summary = (
        "History frames cost of credit as recurring while capital pressure intensified in the current call."
    )
    analysis.temporal_comparison.recurring_topics = ["cost of credit"]
    analysis.temporal_comparison.new_or_escalating_topics = ["capital pressure"]

    report = render_executive_report(analysis)

    assert "## Temporal Context" in report
    assert "Recurring historical themes: cost of credit" in report
    assert count_words(report) <= 400
