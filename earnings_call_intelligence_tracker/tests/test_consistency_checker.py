from __future__ import annotations

from copy import deepcopy

from src.consistency_checker import check_analysis_consistency


def _analysis_payload() -> dict:
    quote = "Management revised guidance because credit risk increased to 65 billion."
    evidence = {
        "quote": quote,
        "speaker": "Geovanne Tobias",
        "page": 2,
        "rationale": "The quote supports the statement.",
        "evidence_validated": True,
        "speaker_validated": True,
        "source_block_ids": ["seg_0001"],
        "match_type": "exact",
        "matched_text": quote,
        "match_score": 1.0,
    }
    return {
        "schema_version": "1.2",
        "management_tone": {
            "classification": "cautious",
            "summary": "Management was cautious.",
            "evidence": [evidence],
            "confidence": "high",
        },
        "guidance_changes": [
            {
                "topic": "Cost of credit",
                "metric_direction": "raised",
                "investment_implication": "negative",
                "statement_basis": "explicit",
                "current_statement": "Management revised guidance to 65 billion.",
                "previous_reference": None,
                "evidence": [evidence],
                "confidence": "high",
            }
        ],
        "critical_questions": [],
        "red_flags": [],
        "surprise_items": [],
        "consensus_surprises": [],
        "surprise_score_components": {
            "guidance_revision": 20,
            "analyst_pressure": 10,
            "tone_shift": 10,
            "new_material_numbers": 10,
            "external_context_adjustment": 0,
        },
        "transcript_surprise_score": 55,
        "consensus_surprise_score": None,
        "overall_surprise_score": 55,
        "surprise_score_confidence": "medium",
        "analysis_context": {
            "has_prior_quarter_transcript": False,
            "has_external_consensus": False,
            "surprise_score_is_transcript_only": True,
            "surprise_score_cap_applied": False,
        },
        "analysis_limitations": [
            "No external pre-call consensus was provided.",
            "Surprise score is inferred from transcript-only signals.",
        ],
    }


def _evidence_report(**summary_overrides: object) -> dict:
    summary = {
        "total_quotes": 3,
        "valid_quotes": 3,
        "invalid_quotes": 0,
        "valid_quote_rate": 1.0,
        "speaker_validated_quotes": 3,
        "speaker_invalid_quotes": 0,
        "speaker_validation_rate": 1.0,
    }
    summary.update(summary_overrides)
    return {"summary": summary, "warnings": [], "invalid_quotes": []}


def test_consistency_checker_passes_coherent_transcript_only_analysis() -> None:
    report = check_analysis_consistency(_analysis_payload(), _evidence_report())

    assert report["summary"]["passed"] is True
    assert report["summary"]["issues_count"] == 0


def test_consistency_checker_flags_invalid_evidence_as_high_severity() -> None:
    report = check_analysis_consistency(
        _analysis_payload(),
        _evidence_report(invalid_quotes=1, valid_quotes=2, valid_quote_rate=0.67),
    )

    assert report["summary"]["passed"] is False
    assert report["summary"]["high"] == 1
    assert report["issues"][0]["issue_type"] == "invalid_evidence"


def test_consistency_checker_flags_consensus_score_without_prior_context() -> None:
    analysis = _analysis_payload()
    analysis["consensus_surprise_score"] = 70

    report = check_analysis_consistency(analysis, _evidence_report())

    assert report["summary"]["passed"] is False
    assert any(issue["issue_type"] == "unexpected_consensus_score" for issue in report["issues"])


def test_consistency_checker_flags_stale_transcript_only_limitation_with_consensus() -> None:
    analysis = _analysis_payload()
    analysis["analysis_context"] = {
        "has_prior_quarter_transcript": False,
        "has_external_consensus": True,
        "surprise_score_is_transcript_only": False,
        "surprise_score_cap_applied": False,
    }
    analysis["consensus_surprise_score"] = 72
    analysis["overall_surprise_score"] = 72
    analysis["consensus_surprises"] = [
        {
            "topic": "Cost of credit",
            "pre_call_expectation": "No major revision expected.",
            "statement_basis": "explicit",
            "call_statement": "Management revised guidance to 65 billion.",
            "surprise_direction": "negative",
            "surprise_magnitude": "high",
            "already_in_consensus": False,
            "confidence": "high",
            "evidence": analysis["guidance_changes"][0]["evidence"],
        }
    ]
    analysis["analysis_limitations"] = ["Surprise score is inferred from transcript-only signals."]

    report = check_analysis_consistency(analysis, _evidence_report())

    assert report["summary"]["passed"] is True
    assert any(issue["issue_type"] == "stale_limitation" for issue in report["issues"])


def test_consistency_checker_flags_unsupported_explicit_numeric_statement() -> None:
    analysis = _analysis_payload()
    analysis["guidance_changes"][0]["current_statement"] = (
        "Management revised guidance to 65-70 billion."
    )

    report = check_analysis_consistency(analysis, _evidence_report())

    assert report["summary"]["passed"] is True
    assert any(
        issue["issue_type"] == "unsupported_explicit_numeric_claim"
        for issue in report["issues"]
    )


def test_consistency_checker_treats_inferred_numeric_gap_as_low_severity() -> None:
    analysis = deepcopy(_analysis_payload())
    analysis["guidance_changes"][0]["statement_basis"] = "inferred"
    analysis["guidance_changes"][0]["current_statement"] = (
        "Management implied a 65-70 billion range."
    )

    report = check_analysis_consistency(analysis, _evidence_report())

    assert report["summary"]["passed"] is True
    assert any(
        issue["severity"] == "low"
        and issue["issue_type"] == "unsupported_inferred_numeric_claim"
        for issue in report["issues"]
    )
