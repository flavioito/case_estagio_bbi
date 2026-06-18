from __future__ import annotations

import difflib
import re
from copy import deepcopy
from typing import Any


MATCH_TYPES = {"exact", "normalized_exact", "approximate", "not_found"}
EVIDENCE_WARNING_THRESHOLD = 0.75


def validate_analysis_evidence(
    analysis_dict: dict[str, Any],
    full_transcript_text: str,
    *,
    transcript_segments: list[dict[str, Any]] | None = None,
    approximate_threshold: float = 0.86,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Annotate evidence quotes with transcript validation metadata."""
    validated = deepcopy(analysis_dict)
    full_text = str(full_transcript_text or "")
    normalized_full_text = _normalize_for_match(full_text)

    evidence_results: list[dict[str, Any]] = []

    for path, evidence in _iter_evidence_items(validated):
        result = validate_quote(
            quote=str(evidence.get("quote", "")),
            full_text=full_text,
            normalized_full_text=normalized_full_text,
            approximate_threshold=approximate_threshold,
        )
        segment_result = validate_quote_against_segments(
            quote=str(evidence.get("quote", "")),
            speaker=str(evidence.get("speaker", "")),
            transcript_segments=transcript_segments,
            approximate_threshold=approximate_threshold,
        )
        evidence.update(
            {
                "evidence_validated": result["evidence_validated"],
                "speaker_validated": segment_result["speaker_validated"],
                "source_block_ids": segment_result["source_block_ids"],
                "match_type": result["match_type"],
                "matched_text": result["matched_text"],
                "match_score": result["match_score"],
            }
        )
        evidence_results.append(
            {
                "path": path,
                "quote": evidence.get("quote"),
                "speaker": evidence.get("speaker"),
                "speaker_validated": segment_result["speaker_validated"],
                "source_block_ids": segment_result["source_block_ids"],
                **result,
            }
        )

    for path, red_flag in _iter_red_flag_items(validated):
        result = validate_quote(
            quote=str(red_flag.get("quote", "")),
            full_text=full_text,
            normalized_full_text=normalized_full_text,
            approximate_threshold=approximate_threshold,
        )
        segment_result = validate_quote_against_segments(
            quote=str(red_flag.get("quote", "")),
            speaker=str(red_flag.get("speaker", "")),
            transcript_segments=transcript_segments,
            approximate_threshold=approximate_threshold,
        )
        red_flag.update(
            {
                "evidence_validated": result["evidence_validated"],
                "speaker_validated": segment_result["speaker_validated"],
                "source_block_ids": segment_result["source_block_ids"],
                "match_type": result["match_type"],
                "matched_text": result["matched_text"],
                "match_score": result["match_score"],
            }
        )
        evidence_results.append(
            {
                "path": path,
                "quote": red_flag.get("quote"),
                "speaker": red_flag.get("speaker"),
                "speaker_validated": segment_result["speaker_validated"],
                "source_block_ids": segment_result["source_block_ids"],
                **result,
            }
        )

    report = build_validation_report(evidence_results)
    if report["summary"]["total_quotes"] and report["summary"]["valid_quote_rate"] < EVIDENCE_WARNING_THRESHOLD:
        report["warnings"].append(
            "Warning: many quotes were not validated. Review evidence before relying on the analysis."
        )

    return validated, report


def validate_quote_against_segments(
    *,
    quote: str,
    speaker: str,
    transcript_segments: list[dict[str, Any]] | None,
    approximate_threshold: float = 0.86,
) -> dict[str, Any]:
    if not transcript_segments:
        return {"speaker_validated": None, "source_block_ids": []}

    quote = quote.strip()
    if not quote:
        return {"speaker_validated": False, "source_block_ids": []}

    fragmented_result = _validate_fragmented_quote_against_segments(
        quote=quote,
        speaker=speaker,
        transcript_segments=transcript_segments,
        approximate_threshold=approximate_threshold,
    )
    if fragmented_result is not None:
        return fragmented_result

    same_speaker_matches = _matching_segment_ids(
        quote=quote,
        transcript_segments=[
            segment
            for segment in transcript_segments
            if _same_speaker(str(segment.get("speaker", "")), speaker)
        ],
        approximate_threshold=approximate_threshold,
    )
    if same_speaker_matches:
        return {
            "speaker_validated": True,
            "source_block_ids": same_speaker_matches,
        }

    any_speaker_matches = _matching_segment_ids(
        quote=quote,
        transcript_segments=transcript_segments,
        approximate_threshold=approximate_threshold,
    )
    return {
        "speaker_validated": False if any_speaker_matches else None,
        "source_block_ids": any_speaker_matches,
    }


def _validate_fragmented_quote_against_segments(
    *,
    quote: str,
    speaker: str,
    transcript_segments: list[dict[str, Any]],
    approximate_threshold: float,
) -> dict[str, Any] | None:
    fragments = [
        fragment.strip(" .;:")
        for fragment in re.split(r"\s*(?:\.{3}|â€¦)\s*", quote)
        if len(fragment.strip(" .;:").split()) >= 4
    ]
    if len(fragments) < 2:
        return None

    same_speaker_segments = [
        segment
        for segment in transcript_segments
        if _same_speaker(str(segment.get("speaker", "")), speaker)
    ]
    same_speaker_ids = _unique_ids(
        block_id
        for fragment in fragments
        for block_id in _matching_segment_ids(
            quote=fragment,
            transcript_segments=same_speaker_segments,
            approximate_threshold=approximate_threshold,
        )
    )
    if same_speaker_ids:
        return {"speaker_validated": True, "source_block_ids": same_speaker_ids}

    any_speaker_ids = _unique_ids(
        block_id
        for fragment in fragments
        for block_id in _matching_segment_ids(
            quote=fragment,
            transcript_segments=transcript_segments,
            approximate_threshold=approximate_threshold,
        )
    )
    if any_speaker_ids:
        return {"speaker_validated": False, "source_block_ids": any_speaker_ids}
    return None


def validate_quote(
    *,
    quote: str,
    full_text: str,
    normalized_full_text: str | None = None,
    approximate_threshold: float = 0.86,
) -> dict[str, Any]:
    quote = quote.strip()
    if not quote:
        return _result(False, "not_found", None, 0.0)

    fragment_result = _validate_fragmented_quote(
        quote=quote,
        full_text=full_text,
        normalized_full_text=normalized_full_text,
        approximate_threshold=approximate_threshold,
    )
    if fragment_result is not None:
        return fragment_result

    if quote in full_text:
        return _result(True, "exact", quote, 1.0)

    normalized_quote = _normalize_for_match(quote)
    normalized_text = normalized_full_text if normalized_full_text is not None else _normalize_for_match(full_text)
    if normalized_quote and normalized_quote in normalized_text:
        return _result(True, "normalized_exact", quote, 1.0)

    approximate = _find_approximate_quote(
        normalized_quote=normalized_quote,
        normalized_text=normalized_text,
        original_quote=quote,
        threshold=approximate_threshold,
    )
    if approximate is not None:
        return _result(
            True,
            "approximate",
            approximate["matched_text"],
            approximate["score"],
        )

    return _result(False, "not_found", None, 0.0)


def _matching_segment_ids(
    *,
    quote: str,
    transcript_segments: list[dict[str, Any]],
    approximate_threshold: float,
) -> list[str]:
    matches: list[str] = []
    approximate_candidates: list[tuple[float, dict[str, Any]]] = []
    quote_words = set(_normalize_for_match(quote).split())

    for segment in transcript_segments:
        text = str(segment.get("text", ""))
        if not text:
            continue

        result = _validate_exact_or_normalized_quote(
            quote=quote,
            full_text=text,
            normalized_full_text=_normalize_for_match(text),
        )
        if result["evidence_validated"]:
            block_id = segment.get("block_id")
            if block_id:
                matches.append(str(block_id))
            continue

        overlap = _word_overlap_score(quote_words, set(_normalize_for_match(text).split()))
        if overlap >= 0.35:
            approximate_candidates.append((overlap, segment))

    if matches:
        return matches

    for _overlap, segment in sorted(approximate_candidates, reverse=True, key=lambda item: item[0])[:5]:
        result = validate_quote(
            quote=quote,
            full_text=str(segment.get("text", "")),
            approximate_threshold=approximate_threshold,
        )
        if result["evidence_validated"]:
            block_id = segment.get("block_id")
            if block_id:
                matches.append(str(block_id))
    return matches


def _word_overlap_score(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left)


def _unique_ids(values) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            ordered.append(value)
    return ordered


def _same_speaker(left: str, right: str) -> bool:
    return _normalize_speaker(left) == _normalize_speaker(right)


def _normalize_speaker(value: str) -> str:
    normalized = _normalize_for_match(value)
    normalized = re.sub(r"[^\w\s]", "", normalized, flags=re.UNICODE)
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized.strip()


def _validate_exact_or_normalized_quote(
    *,
    quote: str,
    full_text: str,
    normalized_full_text: str,
) -> dict[str, Any]:
    fragments = [
        fragment.strip(" .;:")
        for fragment in re.split(r"\s*(?:\.{3}|â€¦)\s*", quote)
        if len(fragment.strip(" .;:").split()) >= 4
    ]
    if len(fragments) >= 2:
        results = [
            _validate_exact_or_normalized_quote(
                quote=fragment,
                full_text=full_text,
                normalized_full_text=normalized_full_text,
            )
            for fragment in fragments
        ]
        if all(result["evidence_validated"] for result in results):
            match_type = (
                "exact"
                if {result["match_type"] for result in results} == {"exact"}
                else "normalized_exact"
            )
            return _result(
                True,
                match_type,
                " ... ".join(str(result["matched_text"]) for result in results if result["matched_text"]),
                1.0,
            )

    if quote in full_text:
        return _result(True, "exact", quote, 1.0)

    normalized_quote = _normalize_for_match(quote)
    if normalized_quote and normalized_quote in normalized_full_text:
        return _result(True, "normalized_exact", quote, 1.0)

    return _result(False, "not_found", None, 0.0)


def _validate_fragmented_quote(
    *,
    quote: str,
    full_text: str,
    normalized_full_text: str | None,
    approximate_threshold: float,
) -> dict[str, Any] | None:
    fragments = [
        fragment.strip(" .;:")
        for fragment in re.split(r"\s*(?:\.{3}|…)\s*", quote)
        if len(fragment.strip(" .;:").split()) >= 4
    ]
    if len(fragments) < 2:
        return None

    results = [
        _validate_simple_quote(
            quote=fragment,
            full_text=full_text,
            normalized_full_text=normalized_full_text,
            approximate_threshold=approximate_threshold,
        )
        for fragment in fragments
    ]
    if not all(result["evidence_validated"] for result in results):
        return None

    match_types = {result["match_type"] for result in results}
    if match_types == {"exact"}:
        match_type = "exact"
    elif match_types <= {"exact", "normalized_exact"}:
        match_type = "normalized_exact"
    else:
        match_type = "approximate"

    return _result(
        True,
        match_type,
        " ... ".join(str(result["matched_text"]) for result in results if result["matched_text"]),
        min(float(result["match_score"]) for result in results),
    )


def _validate_simple_quote(
    *,
    quote: str,
    full_text: str,
    normalized_full_text: str | None,
    approximate_threshold: float,
) -> dict[str, Any]:
    if quote in full_text:
        return _result(True, "exact", quote, 1.0)

    normalized_quote = _normalize_for_match(quote)
    normalized_text = normalized_full_text if normalized_full_text is not None else _normalize_for_match(full_text)
    if normalized_quote and normalized_quote in normalized_text:
        return _result(True, "normalized_exact", quote, 1.0)

    approximate = _find_approximate_quote(
        normalized_quote=normalized_quote,
        normalized_text=normalized_text,
        original_quote=quote,
        threshold=approximate_threshold,
    )
    if approximate is not None:
        return _result(True, "approximate", approximate["matched_text"], approximate["score"])

    return _result(False, "not_found", None, 0.0)


def build_validation_report(evidence_results: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(evidence_results)
    valid = sum(1 for item in evidence_results if item["evidence_validated"])
    speaker_checked = [
        item for item in evidence_results if item.get("speaker_validated") is not None
    ]
    speaker_valid = sum(1 for item in speaker_checked if item.get("speaker_validated") is True)
    by_type: dict[str, int] = {match_type: 0 for match_type in MATCH_TYPES}
    for item in evidence_results:
        by_type[str(item["match_type"])] = by_type.get(str(item["match_type"]), 0) + 1

    return {
        "summary": {
            "total_quotes": total,
            "valid_quotes": valid,
            "invalid_quotes": total - valid,
            "valid_quote_rate": round(valid / total, 4) if total else 1.0,
            "speaker_checked_quotes": len(speaker_checked),
            "speaker_valid_quotes": speaker_valid,
            "speaker_invalid_quotes": len(speaker_checked) - speaker_valid,
            "speaker_valid_quote_rate": (
                round(speaker_valid / len(speaker_checked), 4)
                if speaker_checked
                else 1.0
            ),
            "match_type_counts": by_type,
        },
        "invalid_quotes": [
            item for item in evidence_results if not item["evidence_validated"]
        ],
        "all_quotes": evidence_results,
        "warnings": [],
    }


def _iter_evidence_items(root: dict[str, Any]):
    def walk(value: Any, path: str):
        if isinstance(value, dict):
            evidence = value.get("evidence")
            if isinstance(evidence, list):
                for index, item in enumerate(evidence):
                    if isinstance(item, dict) and "quote" in item:
                        yield f"{path}.evidence[{index}]", item
            for key, child in value.items():
                if key == "evidence":
                    continue
                yield from walk(child, f"{path}.{key}" if path else key)
        elif isinstance(value, list):
            for index, item in enumerate(value):
                yield from walk(item, f"{path}[{index}]")

    yield from walk(root, "")


def _iter_red_flag_items(root: dict[str, Any]):
    red_flags = root.get("red_flags")
    if not isinstance(red_flags, list):
        return
    for index, item in enumerate(red_flags):
        if isinstance(item, dict) and "quote" in item:
            yield f"red_flags[{index}]", item


def _find_approximate_quote(
    *,
    normalized_quote: str,
    normalized_text: str,
    original_quote: str,
    threshold: float,
) -> dict[str, Any] | None:
    quote_words = normalized_quote.split()
    if len(quote_words) < 4:
        return None

    text_words = normalized_text.split()
    window_size = len(quote_words)
    if not text_words or len(text_words) < window_size:
        return None

    best_score = 0.0
    best_window = ""
    quote_word_set = set(quote_words)
    for start in range(0, len(text_words) - window_size + 1):
        window_words = text_words[start : start + window_size]
        if _word_overlap_score(quote_word_set, set(window_words)) < 0.45:
            continue
        window = " ".join(window_words)
        score = difflib.SequenceMatcher(None, normalized_quote, window).ratio()
        if score > best_score:
            best_score = score
            best_window = window

    if best_score >= threshold:
        return {"matched_text": best_window or original_quote, "score": round(best_score, 4)}
    return None


def _normalize_for_match(text: str) -> str:
    normalized = text.casefold()
    normalized = normalized.replace("\u2019", "'").replace("\u2018", "'")
    normalized = normalized.replace("\u201c", '"').replace("\u201d", '"')
    normalized = normalized.replace("\u2013", "-").replace("\u2014", "-")
    normalized = re.sub(r"\([^)]{1,120}\)", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized.strip()


def _result(
    evidence_validated: bool,
    match_type: str,
    matched_text: str | None,
    match_score: float,
) -> dict[str, Any]:
    return {
        "evidence_validated": evidence_validated,
        "match_type": match_type,
        "matched_text": matched_text,
        "match_score": round(match_score, 4),
    }
