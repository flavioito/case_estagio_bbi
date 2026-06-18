from __future__ import annotations

from src.transcript_cleaner import clean_transcript_pages, clean_page_text


def test_clean_page_text_preserves_hyphenated_financial_terms() -> None:
    text = "The short-\nterm indicators and risk-\nadjusted return improved."

    assert "short-term indicators" in clean_page_text(text)
    assert "risk-adjusted return" in clean_page_text(text)


def test_clean_page_text_preserves_uppercase_hyphenated_terms() -> None:
    text = "Lines such as PRONAMPE and PEAC-\nFGI reached 60%."

    assert "PEAC-FGI" in clean_page_text(text)


def test_clean_transcript_pages_removes_repeated_headers() -> None:
    pages = [
        {"page": 1, "text": "Repeated Header\nSpeaker One:\nHello."},
        {"page": 2, "text": "Repeated Header\nSpeaker Two:\nQuestion."},
    ]

    cleaned = clean_transcript_pages(pages)

    assert "Repeated Header" not in cleaned[0]["text"]
    assert "Repeated Header" not in cleaned[1]["text"]
