from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

from src.pdf_loader import load_pdf_pages
from src.segmenter import build_qa_turns, segment_transcript
from src.transcript_cleaner import clean_transcript_pages


TOPIC_KEYWORDS = {
    "asset_quality": ["asset quality", "npl", "delinquency", "credit quality", "overdue"],
    "provisions_cost_of_credit": ["provision", "cost of credit", "allowance", "expected loss"],
    "agribusiness": ["agribusiness", "agro", "rural", "crop", "harvest"],
    "capital": ["capital", "cet1", "basel", "prudential"],
    "nii": ["nii", "net interest income", "spread", "selic", "margin"],
    "guidance": ["guidance", "outlook", "estimate", "projection"],
    "profitability": ["roe", "roa", "net income", "profitability", "earnings"],
    "tax": ["tax", "tax credit", "dta", "effective tax"],
    "portfolio_mix": ["portfolio", "individuals", "corporate", "mix"],
    "dividends": ["dividend", "payout", "shareholder remuneration"],
}

CAUTIOUS_WORDS = [
    "caution",
    "prudence",
    "uncertain",
    "uncertainty",
    "challenging",
    "pressure",
    "deterioration",
    "risk",
    "volatility",
]
POSITIVE_WORDS = [
    "resilient",
    "growth",
    "improvement",
    "strong",
    "solid",
    "record",
    "recovery",
    "positive",
]
RED_FLAG_PATTERNS = [
    "we don't know",
    "we do not know",
    "not possible to",
    "difficult to predict",
    "uncertainty",
    "challenging",
    "we wouldn't want",
]


def select_history_pdfs(
    input_dir: str | Path,
    *,
    years: set[int] | None = None,
    exclude_names: set[str] | None = None,
) -> list[Path]:
    """Select historical transcript PDFs from a directory."""
    directory = Path(input_dir)
    selected_years = years or {2024, 2025}
    excluded = {name.casefold() for name in (exclude_names or set())}
    pdfs: list[Path] = []

    for path in sorted(directory.glob("*.pdf"), key=lambda item: item.name.casefold()):
        if path.name.casefold() in excluded:
            continue
        quarter = extract_quarter_from_name(path.name)
        if not quarter:
            continue
        if quarter_to_year(quarter) in selected_years:
            pdfs.append(path)

    return sorted(pdfs, key=lambda item: quarter_sort_key(extract_quarter_from_name(item.name) or ""))


def build_history_context(
    pdf_paths: list[str | Path],
    *,
    ticker: str | None = None,
    company: str | None = None,
) -> dict[str, Any]:
    """Build a compact deterministic history context from prior transcripts."""
    calls = [summarize_historical_call(Path(path)) for path in pdf_paths]
    calls = sorted(calls, key=lambda item: quarter_sort_key(str(item.get("quarter") or "")))
    topic_counter: Counter[str] = Counter()
    question_counter: Counter[str] = Counter()

    for call in calls:
        topic_counter.update(call.get("dominant_topics", []))
        question_counter.update(call.get("analyst_question_topics", []))

    tone_trend = " -> ".join(
        f"{call.get('quarter')}: {call.get('management_tone_hint')}" for call in calls
    )
    return {
        "context_type": "historical_transcript_summary",
        "ticker": ticker or infer_ticker_from_calls(calls),
        "company": company or infer_company_from_calls(calls),
        "period_covered": "2024-2025",
        "source_count": len(calls),
        "source_files": [call["source_file"] for call in calls],
        "quarters": calls,
        "historical_patterns": {
            "tone_trend": tone_trend,
            "recurring_topics": [topic for topic, _ in topic_counter.most_common(8)],
            "recurring_analyst_question_topics": [
                topic for topic, _ in question_counter.most_common(6)
            ],
            "use_in_current_analysis": [
                "Treat repeated historical topics as recurring unless the current call materially changes language, guidance, or quantification.",
                "Use history to calibrate tone shifts, recurring analyst pressure, and whether a theme appears new versus persistent.",
                "Do not cite historical context as evidence for claims about the current call.",
            ],
        },
    }


def summarize_historical_call(pdf_path: Path) -> dict[str, Any]:
    pages = load_pdf_pages(pdf_path)
    cleaned_pages = clean_transcript_pages(pages)
    segments = segment_transcript(cleaned_pages)
    qa_turns = build_qa_turns(segments)
    full_text = " ".join(str(page.get("text", "")) for page in cleaned_pages)
    management_text = " ".join(
        str(segment.get("text", ""))
        for segment in segments
        if segment.get("speaker_type") == "management"
    )
    question_text = " ".join(
        " ".join(str(question.get("text", "")) for question in turn.get("questions", []))
        for turn in qa_turns
    ) or text_after_qa(full_text)
    quarter = extract_quarter_from_text(f"{pdf_path.name}\n{full_text}")
    red_flag_language = detect_red_flag_language(segments, full_text=full_text, limit=3)
    for item in red_flag_language:
        item["quarter"] = quarter

    return {
        "source_file": pdf_path.name,
        "quarter": quarter,
        "call_date": extract_call_date(full_text),
        "management_tone_hint": classify_tone_hint(management_text or full_text),
        "dominant_topics": detect_topics(full_text, limit=6),
        "guidance_topics": detect_guidance_topics(segments, full_text=full_text),
        "analyst_question_topics": detect_topics(question_text, limit=5),
        "recurring_red_flag_language": red_flag_language,
        "notable_management_quotes": select_notable_management_quotes(
            segments,
            full_text=full_text,
            limit=3,
        ),
        "segment_count": len(segments),
        "qa_turn_count": len(qa_turns),
    }


def write_history_context(context: dict[str, Any], output_path: str | Path) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(context, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def extract_quarter_from_name(name: str) -> str | None:
    return extract_quarter_from_text(name)


def extract_quarter_from_text(text: str) -> str | None:
    match = re.search(r"\b([1-4])Q(\d{2,4})\b", text, flags=re.IGNORECASE)
    if not match:
        return None
    quarter = match.group(1)
    year = match.group(2)
    if len(year) == 4:
        year = year[-2:]
    return f"{quarter}Q{year}"


def quarter_to_year(quarter: str) -> int | None:
    match = re.fullmatch(r"[1-4]Q(\d{2})", quarter, flags=re.IGNORECASE)
    if not match:
        return None
    return 2000 + int(match.group(1))


def quarter_sort_key(quarter: str) -> tuple[int, int]:
    match = re.fullmatch(r"([1-4])Q(\d{2})", quarter, flags=re.IGNORECASE)
    if not match:
        return (9999, 9)
    return (2000 + int(match.group(2)), int(match.group(1)))


def extract_call_date(text: str) -> str | None:
    months = (
        "January|February|March|April|May|June|July|August|September|"
        "October|November|December"
    )
    match = re.search(
        rf"\b({months})\s+\d{{1,2}}(?:st|nd|rd|th)?,\s+\d{{4}}\b",
        text,
        flags=re.IGNORECASE,
    )
    if match:
        return match.group(0)
    return None


def classify_tone_hint(text: str) -> str:
    normalized = text.casefold()
    cautious_score = sum(normalized.count(word) for word in CAUTIOUS_WORDS)
    positive_score = sum(normalized.count(word) for word in POSITIVE_WORDS)
    if cautious_score >= positive_score + 3:
        return "cautious"
    if positive_score >= cautious_score + 3:
        return "positive"
    if cautious_score and positive_score:
        return "mixed"
    return "neutral"


def detect_topics(text: str, *, limit: int) -> list[str]:
    normalized = text.casefold()
    scores = Counter(
        topic
        for topic, keywords in TOPIC_KEYWORDS.items()
        for keyword in keywords
        for _ in range(normalized.count(keyword))
    )
    return [topic for topic, _ in scores.most_common(limit)]


def detect_guidance_topics(segments: list[dict[str, Any]], *, full_text: str = "") -> list[str]:
    text = " ".join(
        str(segment.get("text", ""))
        for segment in segments
        if "guidance" in str(segment.get("text", "")).casefold()
        or "outlook" in str(segment.get("text", "")).casefold()
    )
    if not text:
        text = " ".join(
            sentence
            for sentence in split_sentences(full_text)
            if "guidance" in sentence.casefold() or "outlook" in sentence.casefold()
        )
    return detect_topics(text, limit=5)


def detect_red_flag_language(
    segments: list[dict[str, Any]],
    *,
    full_text: str = "",
    limit: int,
) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []
    for segment in segments:
        text = str(segment.get("text", ""))
        normalized = text.casefold()
        if not any(pattern in normalized for pattern in RED_FLAG_PATTERNS):
            continue
        quote = first_matching_sentence(text, RED_FLAG_PATTERNS)
        if quote:
            matches.append(
                {
                    "speaker": segment.get("speaker"),
                    "quote": quote,
                    "quarter": None,
                }
            )
        if len(matches) >= limit:
            break
    if matches:
        return matches

    for sentence in split_sentences(full_text):
        normalized = sentence.casefold()
        if not any(pattern in normalized for pattern in RED_FLAG_PATTERNS):
            continue
        matches.append({"speaker": None, "quote": clip_words(sentence, 24), "quarter": None})
        if len(matches) >= limit:
            break
    return matches


def select_notable_management_quotes(
    segments: list[dict[str, Any]],
    *,
    full_text: str = "",
    limit: int,
) -> list[dict[str, Any]]:
    quotes: list[dict[str, Any]] = []
    for segment in segments:
        if segment.get("speaker_type") != "management":
            continue
        text = str(segment.get("text", ""))
        if not any(keyword in text.casefold() for keyword in ["guidance", "capital", "credit", "nii", "npl"]):
            continue
        sentence = first_sentence(text)
        if not sentence or len(sentence.split()) < 6:
            continue
        quotes.append(
            {
                "speaker": segment.get("speaker"),
                "topic_tags": detect_topics(sentence, limit=3),
                "quote": clip_words(sentence, 28),
            }
        )
        if len(quotes) >= limit:
            break
    if quotes:
        return quotes

    for sentence in split_sentences(full_text):
        if not any(keyword in sentence.casefold() for keyword in ["guidance", "capital", "credit", "nii", "npl"]):
            continue
        quotes.append(
            {
                "speaker": None,
                "topic_tags": detect_topics(sentence, limit=3),
                "quote": clip_words(sentence, 28),
            }
        )
        if len(quotes) >= limit:
            break
    return quotes


def first_matching_sentence(text: str, patterns: list[str]) -> str | None:
    for sentence in split_sentences(text):
        normalized = sentence.casefold()
        if any(pattern in normalized for pattern in patterns):
            return clip_words(sentence, 24)
    return None


def first_sentence(text: str) -> str | None:
    sentences = split_sentences(text)
    return sentences[0] if sentences else None


def split_sentences(text: str) -> list[str]:
    normalized = " ".join(text.split())
    if not normalized:
        return []
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z])", normalized)
    return [part.strip(" .;:") for part in parts if part.strip(" .;:")]


def text_after_qa(text: str) -> str:
    match = re.search(
        r"(questions?\s+(?:and|&)\s+answers?|q\s*&\s*a|perguntas e respostas)",
        text,
        flags=re.IGNORECASE,
    )
    if not match:
        return ""
    return text[match.end() :]


def clip_words(text: str, limit: int) -> str:
    words = text.split()
    if len(words) <= limit:
        return text.strip(" .;:")
    return " ".join(words[:limit]).strip(" .;:")


def infer_ticker_from_calls(calls: list[dict[str, Any]]) -> str | None:
    joined = " ".join(str(call.get("source_file", "")) for call in calls)
    match = re.search(r"\b([A-Z]{4}\d{1,2})\b", joined)
    return match.group(1) if match else None


def infer_company_from_calls(calls: list[dict[str, Any]]) -> str | None:
    joined = " ".join(str(call.get("source_file", "")) for call in calls)
    if "bbas" in joined.casefold() or "banco do brasil" in joined.casefold():
        return "Banco do Brasil"
    return None
