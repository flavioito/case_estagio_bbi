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

    assert "# Executive Earnings Call Brief" in report
    assert "Management emphasized prudence." in report
    assert "Cost of credit" in report
    assert "Antônio Ruette" in report


def test_render_executive_report_filters_invalid_evidence_items() -> None:
    report = render_executive_report(_analysis())

    assert "Should be filtered" not in report
    assert "Guidance revision" not in report
    assert "uncertainty" in report


def test_render_executive_report_uses_evidence_report_summary() -> None:
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

    assert "80% valid quotes" in report


def test_render_executive_report_limits_confidence_display_noise() -> None:
    report = render_executive_report(_analysis())

    assert "Response quality: adequate. Confidence:" not in report
    assert "uncertainty (medium, confidence:" not in report
    assert "(confidence: low)" in report


def test_render_executive_report_shows_inferred_guidance_basis_only_when_needed() -> None:
    analysis = _analysis()
    analysis.guidance_changes[0].statement_basis = "inferred"

    report = render_executive_report(analysis)

    assert "Basis: inferred." in report


def test_write_executive_report_creates_markdown_file(tmp_path: Path) -> None:
    report_path = tmp_path / "nested" / "executive_report.md"

    written_path = write_executive_report(_analysis(), report_path)

    assert written_path == report_path
    assert "# Executive Earnings Call Brief" in report_path.read_text(encoding="utf-8")


def test_count_words_ignores_markdown_symbols() -> None:
    assert count_words("# Title\n\nTone: cautiously-positive.") == 3


def test_render_executive_report_never_exceeds_400_words() -> None:
    analysis = _analysis()

    report = render_executive_report(analysis)

    assert count_words(report) <= 400
