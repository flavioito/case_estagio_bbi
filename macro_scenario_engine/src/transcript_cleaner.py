from __future__ import annotations

import re
from collections import Counter
from typing import Any, Iterable


WORD_HYPHEN_BREAK_RE = re.compile(r"([^\W\d_]{2,})-\s*\n\s*([^\W\d_]{2,})", re.UNICODE)
SPACE_RE = re.compile(r"[ \t]+")

DEFAULT_NOISE_PATTERNS = (
    re.compile(r"^Earnings Webcast$", re.IGNORECASE),
    re.compile(r"^Banco do Brasil S/A \(BBAS3\)$", re.IGNORECASE),
    re.compile(r"^Earnings Webcast 1Q26 Transcription$", re.IGNORECASE),
    re.compile(r"^May 14th, 2026$", re.IGNORECASE),
)


def clean_transcript_pages(pages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Clean extracted PDF pages without rewriting transcript content."""
    repeated_line_keys = _detect_repeated_edge_lines(pages)
    cleaned_pages = []

    for page in pages:
        cleaned_pages.append(
            {
                "page": int(page["page"]),
                "text": clean_page_text(str(page.get("text", "")), repeated_line_keys),
            }
        )

    return cleaned_pages


def clean_page_text(raw_text: str, repeated_line_keys: set[str] | None = None) -> str:
    repeated_line_keys = repeated_line_keys or set()
    text = _normalize_unicode_spaces(raw_text)
    text = _fix_hyphenated_line_breaks(text)
    text = _remove_invalid_chars(text)

    filtered_lines: list[str] = []
    for raw_line in text.splitlines():
        line = SPACE_RE.sub(" ", raw_line).strip()
        if not line:
            filtered_lines.append("")
            continue
        if _is_default_noise_line(line):
            continue
        if _normalize_line_key(line) in repeated_line_keys and not _looks_like_speaker_line(line):
            continue
        filtered_lines.append(line)

    return _paragraphize(filtered_lines).strip()


def build_clean_text(cleaned_pages: list[dict[str, Any]], include_page_markers: bool = True) -> str:
    parts: list[str] = []
    for page in cleaned_pages:
        text = str(page.get("text", "")).strip()
        if not text:
            continue
        if include_page_markers:
            parts.append(f"[Page {int(page['page'])}]")
        parts.append(text)
    return "\n\n".join(parts).strip() + "\n"


def _normalize_unicode_spaces(text: str) -> str:
    return (
        text.replace("\r\n", "\n")
        .replace("\r", "\n")
        .replace("\u00a0", " ")
        .replace("\u202f", " ")
    )


def _fix_hyphenated_line_breaks(text: str) -> str:
    def replace(match: re.Match[str]) -> str:
        left, right = match.group(1), match.group(2)
        return left + "-" + right

    return WORD_HYPHEN_BREAK_RE.sub(replace, text)


def _remove_invalid_chars(text: str) -> str:
    return "".join(
        char
        for char in text
        if char in "\n\t" or (ord(char) >= 32 and ord(char) != 127)
    )


def _paragraphize(lines: Iterable[str]) -> str:
    paragraphs: list[str] = []
    current: list[str] = []

    def flush_current() -> None:
        if current:
            paragraphs.append(" ".join(current).strip())
            current.clear()

    for line in lines:
        if not line:
            flush_current()
            continue

        if _is_structural_line(line):
            flush_current()
            paragraphs.append(line)
            continue

        current.append(line)

    flush_current()
    return "\n".join(paragraph for paragraph in paragraphs if paragraph)


def _detect_repeated_edge_lines(pages: list[dict[str, Any]], edge_size: int = 5) -> set[str]:
    counter: Counter[str] = Counter()

    for page in pages:
        lines = [line.strip() for line in str(page.get("text", "")).splitlines() if line.strip()]
        for line in [*lines[:edge_size], *lines[-edge_size:]]:
            key = _normalize_line_key(line)
            if key and len(key) <= 120 and not _looks_like_speaker_line(line):
                counter[key] += 1

    return {key for key, count in counter.items() if count >= 2}


def _normalize_line_key(line: str) -> str:
    return SPACE_RE.sub(" ", line.strip()).casefold()


def _is_default_noise_line(line: str) -> bool:
    return any(pattern.match(line) for pattern in DEFAULT_NOISE_PATTERNS)


def _looks_like_speaker_line(line: str) -> bool:
    return line.endswith(":") and len(line) <= 120


def _is_structural_line(line: str) -> bool:
    if _looks_like_speaker_line(line):
        return True
    return line.strip().casefold() == "questions and answers session"
