from __future__ import annotations

from src.evidence_checker import (
    validate_analysis_evidence,
    validate_quote,
    validate_quote_against_segments,
)


def test_validate_quote_exact_match() -> None:
    result = validate_quote(
        quote="the current context demands prudence",
        full_text="Management said the current context demands prudence during the call.",
    )

    assert result["evidence_validated"] is True
    assert result["match_type"] == "exact"


def test_validate_quote_normalized_match() -> None:
    result = validate_quote(
        quote="That’s right",
        full_text="That's right, exactly.",
    )

    assert result["evidence_validated"] is True
    assert result["match_type"] == "normalized_exact"


def test_validate_quote_approximate_match() -> None:
    result = validate_quote(
        quote="we anticipate expected credit losses",
        full_text="In this quarter, we anticipated expected credit losses in our models.",
        approximate_threshold=0.80,
    )

    assert result["evidence_validated"] is True
    assert result["match_type"] == "approximate"


def test_validate_quote_not_found() -> None:
    result = validate_quote(
        quote="we are very concerned about credit quality",
        full_text="The transcript does not contain that claim.",
    )

    assert result["evidence_validated"] is False
    assert result["match_type"] == "not_found"


def test_validate_quote_fragmented_with_ellipsis() -> None:
    result = validate_quote(
        quote="the current context demands prudence...many more uncertainties and challenges",
        full_text=(
            "The speaker said the current context demands prudence. "
            "Later he noted many more uncertainties and challenges than before."
        ),
    )

    assert result["evidence_validated"] is True
    assert result["match_type"] in {"exact", "normalized_exact"}


def test_validate_quote_ignores_parenthetical_expansion_in_transcript() -> None:
    result = validate_quote(
        quote="1314 offsets the CGPE issue",
        full_text="So, 1314 offsets the CGPE (Working Capital for Business Preservation) issue.",
    )

    assert result["evidence_validated"] is True
    assert result["match_type"] == "normalized_exact"


def test_validate_analysis_evidence_marks_nested_evidence_and_red_flags() -> None:
    analysis = {
        "management_tone": {
            "evidence": [
                {
                    "quote": "the current context demands prudence",
                    "speaker": "Geovanne Tobias",
                    "page": 2,
                    "rationale": "Literal caution language.",
                }
            ]
        },
        "red_flags": [
            {
                "quote": "we are very concerned about credit quality",
                "speaker": "Felipe Prince",
            }
        ],
    }

    validated, report = validate_analysis_evidence(
        analysis_dict=analysis,
        full_transcript_text="Geovanne said the current context demands prudence.",
    )

    evidence = validated["management_tone"]["evidence"][0]
    red_flag = validated["red_flags"][0]
    assert evidence["evidence_validated"] is True
    assert red_flag["evidence_validated"] is False
    assert report["summary"]["total_quotes"] == 2
    assert report["summary"]["valid_quotes"] == 1


def test_validate_quote_against_segments_returns_source_block_ids_for_same_speaker() -> None:
    result = validate_quote_against_segments(
        quote="the current context demands prudence",
        speaker="Geovanne Tobias",
        transcript_segments=[
            {
                "block_id": "seg_0001",
                "speaker": "Geovanne Tobias",
                "text": "Management said the current context demands prudence.",
            }
        ],
    )

    assert result["speaker_validated"] is True
    assert result["source_block_ids"] == ["seg_0001"]


def test_validate_quote_against_segments_flags_speaker_mismatch() -> None:
    result = validate_quote_against_segments(
        quote="the current context demands prudence",
        speaker="Felipe Prince",
        transcript_segments=[
            {
                "block_id": "seg_0001",
                "speaker": "Geovanne Tobias",
                "text": "Management said the current context demands prudence.",
            }
        ],
    )

    assert result["speaker_validated"] is False
    assert result["source_block_ids"] == ["seg_0001"]


def test_validate_analysis_evidence_adds_source_block_ids_and_speaker_summary() -> None:
    analysis = {
        "management_tone": {
            "evidence": [
                {
                    "quote": "the current context demands prudence",
                    "speaker": "Geovanne Tobias",
                    "page": 2,
                    "rationale": "Literal caution language.",
                }
            ]
        },
        "red_flags": [],
    }

    validated, report = validate_analysis_evidence(
        analysis_dict=analysis,
        full_transcript_text="Geovanne said the current context demands prudence.",
        transcript_segments=[
            {
                "block_id": "seg_0001",
                "speaker": "Geovanne Tobias",
                "text": "Geovanne said the current context demands prudence.",
            }
        ],
    )

    evidence = validated["management_tone"]["evidence"][0]
    assert evidence["source_block_ids"] == ["seg_0001"]
    assert evidence["speaker_validated"] is True
    assert report["summary"]["speaker_valid_quote_rate"] == 1.0
