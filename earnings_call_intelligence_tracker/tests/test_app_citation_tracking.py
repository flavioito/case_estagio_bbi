from __future__ import annotations

from app import _citation_entries, _citation_status, _segment_lookup


def test_citation_entries_merge_analysis_with_evidence_report() -> None:
    analysis = {
        "management_tone": {
            "classification": "cautious",
            "evidence": [
                {
                    "quote": "The current context demands prudence.",
                    "speaker": "Geovanne Tobias",
                    "page": 2,
                }
            ],
        },
        "guidance_changes": [
            {
                "topic": "Cost of credit",
                "evidence": [
                    {
                        "quote": "The increase in provision incorporates this more negative scenario.",
                        "speaker": "Felipe Prince",
                    }
                ],
            }
        ],
        "red_flags": [
            {
                "quote": "We don't know how long this truce will last.",
                "speaker": "Geovanne Tobias",
                "evidence_validated": False,
            }
        ],
    }
    evidence_report = {
        "all_quotes": [
            {
                "path": "management_tone.evidence[0]",
                "evidence_validated": True,
                "speaker_validated": True,
                "source_block_ids": ["seg_0002"],
                "match_type": "exact",
                "match_score": 1.0,
            },
            {
                "path": "guidance_changes[0].evidence[0]",
                "evidence_validated": True,
                "speaker_validated": False,
                "source_block_ids": ["seg_0005"],
                "match_type": "normalized_exact",
                "match_score": 1.0,
            },
        ]
    }

    entries = _citation_entries(analysis, evidence_report)

    assert len(entries) == 3
    assert entries[0]["section"] == "Management tone"
    assert entries[0]["source_block_ids"] == ["seg_0002"]
    assert entries[1]["section"] == "Guidance changes"
    assert _citation_status(entries[0])["label"] == "Validated"
    assert _citation_status(entries[1])["label"] == "Speaker mismatch"
    assert _citation_status(entries[2])["label"] == "Invalid"


def test_citation_entries_fallback_to_evidence_report_without_analysis() -> None:
    evidence_report = {
        "all_quotes": [
            {
                "path": "surprise_items[0].evidence[0]",
                "quote": "This was not in our original guidance.",
                "speaker": "CFO",
                "evidence_validated": True,
            }
        ]
    }

    entries = _citation_entries(None, evidence_report)

    assert entries == [
        {
            "path": "surprise_items[0].evidence[0]",
            "quote": "This was not in our original guidance.",
            "speaker": "CFO",
            "evidence_validated": True,
            "section": "Surprise items",
            "title": "surprise_items[0].evidence[0]",
        }
    ]


def test_segment_lookup_indexes_segments_by_block_id() -> None:
    lookup = _segment_lookup(
        [
            {"block_id": "seg_0001", "speaker": "A"},
            {"speaker": "missing id"},
            {"block_id": "seg_0002", "speaker": "B"},
        ]
    )

    assert sorted(lookup) == ["seg_0001", "seg_0002"]
    assert lookup["seg_0002"]["speaker"] == "B"
