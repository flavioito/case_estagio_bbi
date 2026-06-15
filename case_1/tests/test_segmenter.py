from __future__ import annotations

from src.segmenter import build_qa_turns, segment_transcript


def test_segment_transcript_detects_two_speakers() -> None:
    pages = [
        {
            "page": 1,
            "text": "Jane Doe:\nHello.\n\nJohn Smith:\nQuestion.",
        }
    ]

    segments = segment_transcript(pages)

    assert len(segments) == 2
    assert segments[0]["speaker"] == "Jane Doe"
    assert segments[0]["text"] == "Hello."
    assert segments[1]["speaker"] == "John Smith"
    assert segments[1]["text"] == "Question."


def test_segment_transcript_classifies_qna_roles() -> None:
    pages = [
        {
            "page": 1,
            "text": (
                "I have with me today our CFO, Jane Doe.\n"
                "Jane Doe:\nPrepared remarks.\n"
                "Questions and Answers Session\n"
                "Analyst One, Test Bank:\nWhy did provisions rise?\n"
                "Jane Doe:\nWe anticipated expected losses."
            ),
        }
    ]

    segments = segment_transcript(pages)

    assert segments[0]["role"] == "management"
    assert segments[0]["section"] == "prepared_remarks"
    assert segments[0]["block_type"] == "prepared_management"
    assert segments[0]["legacy_section"] == "prepared_remarks"
    assert segments[0]["speaker_type"] == "management"
    assert segments[0]["role_title"] == "CFO"
    assert segments[1]["role"] == "analyst"
    assert segments[1]["institution"] == "Test Bank"
    assert segments[1]["section"] == "qa"
    assert segments[1]["block_type"] == "analyst_question"
    assert segments[1]["legacy_section"] == "qa_question"
    assert segments[2]["role"] == "management"
    assert segments[2]["section"] == "qa"
    assert segments[2]["block_type"] == "management_answer"
    assert segments[2]["legacy_section"] == "qa_answer"
    assert segments[1]["qa_turn_id"] == "qa_0001"
    assert segments[2]["qa_turn_id"] == "qa_0001"


def test_segment_transcript_marks_material_ir_clarification() -> None:
    pages = [
        {
            "page": 1,
            "text": (
                "I am Janaína Storti, Head of Investor Relations at Banco do Brasil.\n"
                "Questions and Answers Session\n"
                "Janaína Storti:\n"
                "Just to clarify, the discount and expected loss had zero effect on the bottom line and NPL +90 remains stable."
            ),
        }
    ]

    segments = segment_transcript(pages)

    assert segments[0]["role"] == "operator_ir"
    assert segments[0]["section"] == "qa"
    assert segments[0]["block_type"] == "ir_clarification"
    assert segments[0]["legacy_section"] == "qa_ir_clarification"


def test_segment_transcript_marks_short_technical_ir_clarification() -> None:
    pages = [
        {
            "page": 1,
            "text": (
                "I am Janaína Storti, Head of Investor Relations at Banco do Brasil.\n"
                "Questions and Answers Session\n"
                "Janaína Storti:\n"
                "That’s right, exactly. It deducts this reducer."
            ),
        }
    ]

    segments = segment_transcript(pages)

    assert segments[0]["block_type"] == "ir_clarification"


def test_segment_transcript_marks_fiduciary_sale_ir_clarification() -> None:
    pages = [
        {
            "page": 1,
            "text": (
                "I am Janaína Storti, Head of Investor Relations at Banco do Brasil.\n"
                "Questions and Answers Session\n"
                "Janaína Storti:\n"
                "It was almost 75% with fiduciary sale before moving to the next question."
            ),
        }
    ]

    segments = segment_transcript(pages)

    assert segments[0]["block_type"] == "ir_clarification"


def test_segment_transcript_compacts_internal_page_breaks() -> None:
    pages = [
        {
            "page": 1,
            "text": (
                "I have with me today our CFO, Jane Doe.\n"
                "Questions and Answers Session\n"
                "Jane Doe:\n"
                "The capital\n\nbase remains adequate."
            ),
        }
    ]

    segments = segment_transcript(pages)

    assert segments[0]["text"] == "The capital base remains adequate."
    assert segments[0]["word_count"] == 5
    assert segments[0]["has_question"] is False


def test_segment_transcript_marks_analyst_acknowledgement() -> None:
    pages = [
        {
            "page": 1,
            "text": (
                "Questions and Answers Session\n"
                "Carlos Gomez-Lopez:\n"
                "Thank you very much."
            ),
        }
    ]

    segments = segment_transcript(pages)

    assert segments[0]["section"] == "qa"
    assert segments[0]["block_type"] == "acknowledgement"
    assert segments[0]["legacy_section"] == "qa_acknowledgement"
    assert segments[0]["qa_turn_id"] is None


def test_segment_transcript_marks_short_management_question_fragment() -> None:
    pages = [
        {
            "page": 1,
            "text": (
                "I have with me today our CFO, Geovanne Tobias.\n"
                "Questions and Answers Session\n"
                "Geovanne Tobias:\n"
                "So, this discount is a one-off?"
            ),
        }
    ]

    segments = segment_transcript(pages)

    assert segments[0]["role"] == "management"
    assert segments[0]["section"] == "qa"
    assert segments[0]["block_type"] == "management_clarification"
    assert segments[0]["legacy_section"] == "qa_management_clarification"


def test_segment_transcript_keeps_followup_in_same_qa_turn() -> None:
    pages = [
        {
            "page": 1,
            "text": (
                "I have with me today our CFO, Jane Doe.\n"
                "Questions and Answers Session\n"
                "Analyst One, Test Bank:\n"
                "Why did provisions rise?\n"
                "Jane Doe:\n"
                "We anticipated expected losses.\n"
                "Analyst One, Test Bank:\n"
                "And should they fall next quarter?\n"
                "Jane Doe:\n"
                "We expect normalization."
            ),
        }
    ]

    segments = segment_transcript(pages)

    assert {segment["qa_turn_id"] for segment in segments} == {"qa_0001"}


def test_segment_transcript_increments_qa_turn_for_new_analyst() -> None:
    pages = [
        {
            "page": 1,
            "text": (
                "I have with me today our CFO, Jane Doe.\n"
                "Questions and Answers Session\n"
                "Analyst One, Test Bank:\n"
                "Why did provisions rise?\n"
                "Jane Doe:\n"
                "We anticipated losses.\n"
                "Analyst Two, Other Bank:\n"
                "What about capital?"
            ),
        }
    ]

    segments = segment_transcript(pages)

    questions = [segment for segment in segments if segment["block_type"] == "analyst_question"]
    assert questions[0]["qa_turn_id"] == "qa_0001"
    assert questions[1]["qa_turn_id"] == "qa_0002"


def test_segment_transcript_splits_ir_clarification_from_moderation() -> None:
    pages = [
        {
            "page": 1,
            "text": (
                "I am Janaína Storti, Head of Investor Relations at Banco do Brasil.\n"
                "Questions and Answers Session\n"
                "Analyst One, Test Bank:\n"
                "What is the guarantee level?\n"
                "Janaína Storti:\n"
                "It was almost 75% with fiduciary sale. Thank you, Analyst. To continue, I’d like to call Daniel Vaz from Safra.\n"
                "Daniel Vaz, Safra:\n"
                "Can you discuss capital?"
            ),
        }
    ]

    segments = segment_transcript(pages)
    jana_segments = [segment for segment in segments if segment["speaker"] == "Janaína Storti"]

    assert [segment["block_type"] for segment in jana_segments] == [
        "ir_clarification",
        "ir_moderation",
    ]
    assert jana_segments[0]["qa_turn_id"] == "qa_0001"
    assert jana_segments[1]["qa_turn_id"] is None


def test_build_qa_turns_groups_questions_answers_and_ir_clarifications() -> None:
    pages = [
        {
            "page": 1,
            "text": (
                "I am Janaína Storti, Head of Investor Relations at Banco do Brasil.\n"
                "I have with me today our CFO, Jane Doe.\n"
                "Questions and Answers Session\n"
                "Analyst One, Test Bank:\n"
                "Why did provisions rise?\n"
                "Jane Doe:\n"
                "We anticipated expected losses.\n"
                "Janaína Storti:\n"
                "The expected loss had zero effect on the bottom line."
            ),
        }
    ]

    turns = build_qa_turns(segment_transcript(pages))

    assert len(turns) == 1
    assert turns[0]["qa_turn_id"] == "qa_0001"
    assert turns[0]["analyst"] == "Analyst One"
    assert turns[0]["institution"] == "Test Bank"
    assert len(turns[0]["questions"]) == 1
    assert turns[0]["answers"][0]["role_title"] == "CFO"
    assert len(turns[0]["ir_clarifications"]) == 1


def test_segment_transcript_merges_short_adjacent_blocks_from_same_speaker() -> None:
    pages = [
        {
            "page": 1,
            "text": (
                "I have with me today our CFO, Jane Doe.\n"
                "Questions and Answers Session\n"
                "Jane Doe:\n"
                "Yes.\n"
                "Jane Doe:\n"
                "We expect normalization."
            ),
        }
    ]

    segments = segment_transcript(pages)

    assert len(segments) == 1
    assert segments[0]["speaker"] == "Jane Doe"
    assert segments[0]["block_type"] == "management_answer"
    assert segments[0]["text"] == "Yes. We expect normalization."


def test_segment_transcript_does_not_merge_different_block_types() -> None:
    pages = [
        {
            "page": 1,
            "text": (
                "I am Janaína Storti, Head of Investor Relations at Banco do Brasil.\n"
                "Questions and Answers Session\n"
                "Janaína Storti:\n"
                "It was almost 75% with fiduciary sale. To continue, I’d like to call Daniel Vaz from Safra."
            ),
        }
    ]

    segments = segment_transcript(pages)

    assert [segment["block_type"] for segment in segments] == ["ir_clarification", "ir_moderation"]


def test_segment_transcript_accepts_qa_heading_variants() -> None:
    pages = [
        {
            "page": 1,
            "text": "Q&A\nAnalyst One, Test Bank:\nWhat changed?",
        }
    ]

    segments = segment_transcript(pages)

    assert segments[0]["section"] == "qa"
    assert segments[0]["block_type"] == "analyst_question"


def test_segment_transcript_accepts_names_with_particles() -> None:
    pages = [
        {
            "page": 1,
            "text": "Perguntas e Respostas\nJoão da Silva, Example Bank:\nQual foi o impacto?",
        }
    ]

    segments = segment_transcript(pages)

    assert segments[0]["speaker"] == "João da Silva"
    assert segments[0]["institution"] == "Example Bank"
    assert segments[0]["block_type"] == "analyst_question"
