from __future__ import annotations

import json
from pathlib import Path

from src.history_context import (
    build_history_context,
    classify_tone_hint,
    detect_topics,
    extract_quarter_from_name,
    quarter_sort_key,
    select_history_pdfs,
)
from src.pipeline import compact_history_context_json


def test_select_history_pdfs_keeps_2024_2025_and_excludes_current_call(tmp_path: Path) -> None:
    names = [
        "Transcript Earnings Videoconference 1Q24.pdf",
        "Transcription Earnings 2Q24.pdf",
        "Transcript - Videoconference - 4Q25.pdf",
        "Transcript - Videoconference - 1Q26 (BBAS3).pdf",
        "notes.txt",
    ]
    for name in names:
        (tmp_path / name).write_text("placeholder", encoding="utf-8")

    selected = select_history_pdfs(
        tmp_path,
        years={2024, 2025},
        exclude_names={"Transcript - Videoconference - 1Q26 (BBAS3).pdf"},
    )

    assert [path.name for path in selected] == [
        "Transcript Earnings Videoconference 1Q24.pdf",
        "Transcription Earnings 2Q24.pdf",
        "Transcript - Videoconference - 4Q25.pdf",
    ]


def test_extract_quarter_from_name_and_sort_key() -> None:
    assert extract_quarter_from_name("Transcript - Videoconference - 3Q25.pdf") == "3Q25"
    assert quarter_sort_key("4Q24") < quarter_sort_key("1Q25")


def test_detect_topics_and_tone_hint() -> None:
    text = "Cost of credit, provisions, NPL and capital were under pressure and uncertainty."

    topics = detect_topics(text, limit=3)
    assert "asset_quality" in topics
    assert "provisions_cost_of_credit" in topics
    assert classify_tone_hint(text) == "cautious"


def test_build_history_context_aggregates_summarized_calls(monkeypatch) -> None:
    calls = [
        {
            "source_file": "1Q24.pdf",
            "quarter": "1Q24",
            "dominant_topics": ["capital", "nii"],
            "analyst_question_topics": ["capital"],
        },
        {
            "source_file": "2Q24.pdf",
            "quarter": "2Q24",
            "dominant_topics": ["capital", "asset_quality"],
            "analyst_question_topics": ["asset_quality"],
        },
    ]

    def fake_summarize(path: Path) -> dict:
        return calls[0] if "1Q24" in path.name else calls[1]

    monkeypatch.setattr("src.history_context.summarize_historical_call", fake_summarize)

    context = build_history_context(["1Q24.pdf", "2Q24.pdf"], ticker="BBAS3")

    assert context["ticker"] == "BBAS3"
    assert context["source_count"] == 2
    assert context["historical_patterns"]["recurring_topics"][0] == "capital"


def test_compact_history_context_json_drops_processing_counts() -> None:
    raw = json.dumps(
        {
            "context_type": "historical_transcript_summary",
            "ticker": "BBAS3",
            "quarters": [
                {
                    "quarter": "1Q24",
                    "segment_count": 100,
                    "qa_turn_count": 10,
                    "notable_management_quotes": [{"quote": "a"}, {"quote": "b"}, {"quote": "c"}],
                    "recurring_red_flag_language": [{"quote": "x"}, {"quote": "y"}, {"quote": "z"}],
                }
            ],
            "historical_patterns": {"recurring_topics": ["capital"]},
        }
    )

    compacted = compact_history_context_json(raw)

    assert "segment_count" not in compacted
    assert "qa_turn_count" not in compacted
    assert "Use this only as historical context" in compacted
    assert compacted.count('"quote"') == 4
