from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.schemas import EarningsCallAnalysis, analysis_schema_json


def _minimal_valid_analysis() -> dict:
    evidence = {
        "quote": "the current context demands prudence",
        "speaker": "Geovanne Tobias",
        "page": 2,
        "rationale": "The speaker explicitly frames the environment as requiring caution.",
    }
    return {
        "schema_version": "1.2",
        "company_name": "Banco do Brasil",
        "ticker": "BBAS3",
        "quarter": "1Q26",
        "call_date": "May 14th, 2026",
        "management_tone": {
            "classification": "cautious",
            "summary": "Management emphasized prudence and a tougher credit cycle.",
            "evidence": [evidence],
            "confidence": "high",
        },
        "guidance_changes": [
            {
                "topic": "Cost of credit",
                "metric_direction": "increased",
                "investment_implication": "negative",
                "statement_basis": "explicit",
                "current_statement": "Management linked the revision to expected loss deterioration.",
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
                "why_critical": "The question tested confidence in the new provision path.",
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
                "explanation": "The phrasing signals a less predictable operating environment.",
                "severity": "medium",
                "confidence": "medium",
            }
        ],
        "surprise_items": [
            {
                "item": "Guidance revision",
                "score": 70,
                "why_surprising": "The call states that guidance ranges were revised.",
                "evidence": [evidence],
                "confidence": "medium",
                "limitation": "No external pre-call consensus file was provided; score is inferred from transcript evidence and should not be interpreted as a verified market consensus gap.",
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
        "surprise_score_confidence": "medium",
        "analysis_context": {
            "has_prior_quarter_transcript": False,
            "has_external_consensus": False,
            "surprise_score_is_transcript_only": True,
            "surprise_score_cap_applied": False,
        },
        "analysis_limitations": [
            "No external pre-call consensus file was provided.",
        ],
    }


def test_earnings_call_analysis_accepts_minimal_valid_json() -> None:
    analysis = EarningsCallAnalysis.model_validate(_minimal_valid_analysis())

    assert analysis.management_tone.classification == "cautious"
    assert analysis.critical_questions[0].answer_quality == "adequate"


def test_earnings_call_analysis_rejects_invalid_answer_quality() -> None:
    payload = _minimal_valid_analysis()
    payload["critical_questions"][0]["answer_quality"] = "pretty_good"

    with pytest.raises(ValidationError):
        EarningsCallAnalysis.model_validate(payload)


def test_earnings_call_analysis_rejects_missing_evidence_quote() -> None:
    payload = _minimal_valid_analysis()
    payload["management_tone"]["evidence"][0]["quote"] = "prudence"

    with pytest.raises(ValidationError):
        EarningsCallAnalysis.model_validate(payload)


def test_analysis_schema_json_contains_main_model_name() -> None:
    schema = analysis_schema_json()

    assert "EarningsCallAnalysis" in schema


def test_earnings_call_analysis_rejects_unknown_report_markdown_field() -> None:
    payload = _minimal_valid_analysis()
    payload["executive_report_markdown"] = "# Should not be accepted"

    with pytest.raises(ValidationError):
        EarningsCallAnalysis.model_validate(payload)


def test_earnings_call_analysis_rejects_too_many_guidance_items() -> None:
    payload = _minimal_valid_analysis()
    payload["guidance_changes"] = payload["guidance_changes"] * 5

    with pytest.raises(ValidationError):
        EarningsCallAnalysis.model_validate(payload)


def test_earnings_call_analysis_requires_guidance_confidence() -> None:
    payload = _minimal_valid_analysis()
    del payload["guidance_changes"][0]["confidence"]

    with pytest.raises(ValidationError):
        EarningsCallAnalysis.model_validate(payload)


def test_earnings_call_analysis_requires_guidance_statement_basis() -> None:
    payload = _minimal_valid_analysis()
    del payload["guidance_changes"][0]["statement_basis"]

    with pytest.raises(ValidationError):
        EarningsCallAnalysis.model_validate(payload)


def test_earnings_call_analysis_rejects_too_many_red_flags() -> None:
    payload = _minimal_valid_analysis()
    payload["red_flags"] = payload["red_flags"] * 6

    with pytest.raises(ValidationError):
        EarningsCallAnalysis.model_validate(payload)
