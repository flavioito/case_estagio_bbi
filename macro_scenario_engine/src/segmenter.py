from __future__ import annotations

import re
from typing import Any, NamedTuple


UPPER = "A-ZÁÉÍÓÚÂÊÔÃÕÇ"
NAME_TOKEN = rf"[{UPPER}][\wÀ-ÿ'’.-]+"
LOWER_PARTICLE = r"(?:da|de|do|das|dos|van|von|del|de la)"
PERSON_NAME = rf"{NAME_TOKEN}(?:[ \t]+(?:{LOWER_PARTICLE}|{NAME_TOKEN})){{1,5}}"

BLOCK_TYPES = {
    "prepared_management",
    "prepared_moderator",
    "analyst_question",
    "management_answer",
    "ir_moderation",
    "ir_clarification",
    "management_clarification",
    "answer_fragment",
    "acknowledgement",
    "unknown",
}

SPEAKER_LINE_RE = re.compile(
    rf"^(?P<speaker>{PERSON_NAME}|Operator|Unknown Speaker)"
    r"(?:,\s*(?P<institution>[^:]{2,80}))?:\s*(?P<rest>.*)$",
    re.UNICODE,
)

TITLE_NAME_RE = re.compile(
    rf"\b(?P<title>(?i:CFO|CEO|CRO|COO|Chief [^,.;\n]+?|Head of Investor Relations))"
    rf",\s*(?P<name>{PERSON_NAME})\b",
    re.UNICODE,
)
NAME_TITLE_RE = re.compile(
    rf"(?i:\b(?:I am|I'm)\s+)(?P<name>{PERSON_NAME}),\s*"
    r"(?P<title>(?i:Head of Investor Relations|Investor Relations))",
    re.UNICODE,
)
CALL_FROM_RE = re.compile(
    rf"(?i:\bcall\s+)(?P<name>{PERSON_NAME})(?i:\s+from\s+)(?P<institution>[^.!\n]+)",
    re.UNICODE,
)
QUESTION_FROM_RE = re.compile(
    rf"(?i:\bquestion(?:\s+comes)?\s+from\s+)(?P<name>{PERSON_NAME})"
    r"(?i:\s+(?:from|of)\s+)(?P<institution>[^.!\n]+)",
    re.UNICODE,
)
ACKNOWLEDGEMENT_RE = re.compile(
    r"^(?:thank you|thanks|thank you very much|perfect|ok|okay)[.! ]*$",
    re.IGNORECASE,
)
SHORT_ANSWER_FRAGMENT_RE = re.compile(
    r"^(?:exactly|yes|correct|right|that'?s right|perfect|ok|okay)[.! ]*$",
    re.IGNORECASE,
)
MATERIAL_IR_RE = re.compile(
    r"\b("
    r"bottom line|npl|capital|prudential|tax|effective tax|4966|risk|"
    r"provision|expected loss|discount|cet1|bps|basis points|r\$|guidance|"
    r"delinquency|write-off|net income|ro[ae]|nii|fiduciary sale|guarantee|"
    r"guarantees|collateral|deducts?|reducer|mp 1314|1314"
    r")\b",
    re.IGNORECASE,
)
IR_MODERATION_START_RE = re.compile(
    r"(?:thank you,[^.]+?\.\s*)?"
    r"(?:(?:well|ok|okay)[,.]?\s*)?"
    r"(?:"
    r"to continue|to move on|moving on|let'?s move|"
    r"our next question|the next question|"
    r"i(?:'|’)?d like to (?:call|invite)|"
    r"i (?:want|would like) to call|"
    r"we(?:'|’)?ll move on|we will move on|let me call"
    r")\b",
    re.IGNORECASE,
)

QA_MARKERS = {
    "questions and answers session",
    "questions and answers",
    "question and answer session",
    "question and answer",
    "q&a",
    "q & a",
    "perguntas e respostas",
}


class SpeakerLine(NamedTuple):
    speaker: str
    institution: str | None
    rest: str


def segment_transcript(cleaned_pages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Convert cleaned transcript pages into speaker-level segments."""
    speaker_profiles = infer_role_hints(cleaned_pages)
    institution_hints = infer_institution_hints(cleaned_pages)

    segments: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    in_qa = False

    def finalize_current() -> None:
        nonlocal current
        if current is None:
            return

        text = _compact_text(" ".join(part.strip() for part in current.pop("_text_parts") if part.strip()))
        if text:
            base_segment = {key: value for key, value in current.items() if not key.startswith("_")}
            refined_block_type = refine_block_type(
                speaker_type=str(base_segment["speaker_type"]),
                block_type=str(base_segment["block_type"]),
                text=text,
            )
            for block_type, block_text in split_ir_block_if_needed(
                text=text,
                block_type=refined_block_type,
                speaker_type=str(base_segment["speaker_type"]),
                section=str(base_segment["section"]),
            ):
                segment = dict(base_segment)
                segment["block_type"] = block_type
                segment["legacy_section"] = legacy_section_for(
                    section=str(segment["section"]),
                    block_type=block_type,
                )
                segment["text"] = block_text
                segment["word_count"] = len(block_text.split())
                segment["has_question"] = "?" in block_text
                segments.append(segment)
        current = None

    for page in cleaned_pages:
        page_number = int(page["page"])
        for raw_line in str(page.get("text", "")).splitlines():
            line = raw_line.strip()
            if not line:
                continue

            if _is_qa_heading(line):
                finalize_current()
                in_qa = True
                continue

            parsed = parse_speaker_line(line)
            if parsed:
                finalize_current()

                speaker = parsed.speaker
                institution = parsed.institution or institution_hints.get(speaker)
                profile = speaker_profile_for(
                    speaker=speaker,
                    in_qa=in_qa,
                    speaker_profiles=speaker_profiles,
                )
                section, block_type = classify_section_and_block_type(
                    speaker_type=str(profile["speaker_type"]),
                    in_qa=in_qa,
                )

                current = {
                    "block_id": None,
                    "speaker": speaker,
                    "role": profile["speaker_type"],  # Backward-compatible alias.
                    "speaker_type": profile["speaker_type"],
                    "role_title": profile["role_title"],
                    "institution": institution,
                    "section": section,
                    "block_type": block_type,
                    "legacy_section": legacy_section_for(section=section, block_type=block_type),
                    "qa_turn_id": None,
                    "page_start": page_number,
                    "page_end": page_number,
                    "word_count": None,
                    "has_question": None,
                    "_text_parts": [],
                }
                if parsed.rest:
                    current["_text_parts"].append(parsed.rest)
                continue

            if current is None:
                if not segments and not in_qa:
                    continue
                section = "qa" if in_qa else "prepared_remarks"
                block_type = "unknown"
                current = {
                    "block_id": None,
                    "speaker": "Unknown",
                    "role": "unknown",
                    "speaker_type": "unknown",
                    "role_title": None,
                    "institution": None,
                    "section": section,
                    "block_type": block_type,
                    "legacy_section": legacy_section_for(section=section, block_type=block_type),
                    "qa_turn_id": None,
                    "page_start": page_number,
                    "page_end": page_number,
                    "word_count": None,
                    "has_question": None,
                    "_text_parts": [],
                }

            current["_text_parts"].append(line)
            current["page_end"] = page_number

    finalize_current()
    merge_short_adjacent_segments(segments)
    annotate_segment_ids_and_turns(segments)
    return segments


def build_qa_turns(segments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    turns: dict[str, dict[str, Any]] = {}

    for segment in segments:
        qa_turn_id = segment.get("qa_turn_id")
        if not qa_turn_id:
            continue

        if qa_turn_id not in turns:
            turns[qa_turn_id] = {
                "qa_turn_id": qa_turn_id,
                "analyst": None,
                "institution": None,
                "questions": [],
                "answers": [],
                "ir_clarifications": [],
                "other_blocks": [],
            }

        turn = turns[qa_turn_id]
        block_type = segment.get("block_type") or segment.get("legacy_section")

        if block_type == "analyst_question":
            turn["analyst"] = segment.get("speaker")
            turn["institution"] = segment.get("institution")
            turn["questions"].append(_qa_turn_block(segment))
        elif block_type in {"management_answer", "management_clarification", "answer_fragment"}:
            turn["answers"].append(_qa_turn_block(segment))
        elif block_type == "ir_clarification":
            turn["ir_clarifications"].append(_qa_turn_block(segment))
        elif block_type != "acknowledgement":
            turn["other_blocks"].append(_qa_turn_block(segment))

    return list(turns.values())


def parse_speaker_line(line: str) -> SpeakerLine | None:
    if ":" not in line or len(line) > 160:
        return None

    match = SPEAKER_LINE_RE.match(line)
    if not match:
        return None

    speaker = _normalize_name(match.group("speaker"))
    institution = match.group("institution")
    rest = match.group("rest").strip()

    if institution:
        institution = _clean_institution(institution)

    return SpeakerLine(speaker=speaker, institution=institution, rest=rest)


def infer_role_hints(cleaned_pages: list[dict[str, Any]]) -> dict[str, dict[str, str | None]]:
    text = "\n".join(str(page.get("text", "")) for page in cleaned_pages)
    profiles: dict[str, dict[str, str | None]] = {}

    for match in TITLE_NAME_RE.finditer(text):
        title = _normalize_role_title(match.group("title"))
        name = _normalize_name(match.group("name"))
        if "investor relations" in title.casefold():
            _set_profile(profiles, name, speaker_type="operator_ir", role_title=title)
        else:
            _set_profile(profiles, name, speaker_type="management", role_title=title)

    for match in NAME_TITLE_RE.finditer(text):
        _set_profile(
            profiles,
            _normalize_name(match.group("name")),
            speaker_type="operator_ir",
            role_title="Head of Investor Relations",
        )

    before_qa = _get_text_before_qa(text)
    for line in before_qa.splitlines():
        parsed = parse_speaker_line(line.strip())
        if parsed and profiles.get(parsed.speaker, {}).get("speaker_type") != "operator_ir":
            _set_profile(profiles, parsed.speaker, speaker_type="management", role_title=None)

    return profiles


def infer_institution_hints(cleaned_pages: list[dict[str, Any]]) -> dict[str, str]:
    text = "\n".join(str(page.get("text", "")) for page in cleaned_pages)
    hints: dict[str, str] = {}

    for regex in (CALL_FROM_RE, QUESTION_FROM_RE):
        for match in regex.finditer(text):
            name = _normalize_name(match.group("name"))
            institution = _clean_institution(match.group("institution"))
            if institution:
                hints[name] = institution

    for line in text.splitlines():
        parsed = parse_speaker_line(line.strip())
        if parsed and parsed.institution:
            hints[parsed.speaker] = parsed.institution

    return hints


def speaker_profile_for(
    *,
    speaker: str,
    in_qa: bool,
    speaker_profiles: dict[str, dict[str, str | None]],
) -> dict[str, str | None]:
    if speaker in speaker_profiles:
        return speaker_profiles[speaker]
    if speaker.casefold() == "operator":
        return {"speaker_type": "operator_ir", "role_title": "Operator"}
    if speaker.casefold() == "unknown speaker":
        return {"speaker_type": "unknown", "role_title": None}
    if in_qa:
        return {"speaker_type": "analyst", "role_title": None}
    return {"speaker_type": "unknown", "role_title": None}


def classify_section_and_block_type(speaker_type: str, in_qa: bool) -> tuple[str, str]:
    if not in_qa:
        if speaker_type == "management":
            return "prepared_remarks", "prepared_management"
        if speaker_type == "operator_ir":
            return "prepared_remarks", "prepared_moderator"
        return "prepared_remarks", "unknown"

    if speaker_type == "management":
        return "qa", "management_answer"
    if speaker_type == "operator_ir":
        return "qa", "ir_moderation"
    if speaker_type == "analyst":
        return "qa", "analyst_question"
    return "qa", "unknown"


def refine_block_type(speaker_type: str, block_type: str, text: str) -> str:
    normalized = _compact_text(text)

    if block_type == "analyst_question" and speaker_type == "analyst":
        if _is_acknowledgement(normalized):
            return "acknowledgement"
        return block_type

    if block_type == "ir_moderation" and speaker_type == "operator_ir":
        if _is_material_ir_clarification(normalized):
            return "ir_clarification"
        return block_type

    if block_type == "management_answer" and speaker_type == "management":
        if _is_short_management_question(normalized):
            return "management_clarification"
        if _is_short_answer_fragment(normalized):
            return "answer_fragment"

    return block_type


def split_ir_block_if_needed(
    *,
    text: str,
    block_type: str,
    speaker_type: str,
    section: str,
) -> list[tuple[str, str]]:
    if speaker_type != "operator_ir" or section != "qa" or block_type != "ir_clarification":
        return [(block_type, text)]

    match = IR_MODERATION_START_RE.search(text)
    if not match or match.start() <= 0:
        return [(block_type, text)]

    clarification = _compact_text(text[: match.start()])
    moderation = _compact_text(text[match.start() :])
    if not clarification or not moderation:
        return [(block_type, text)]
    if not _is_material_ir_clarification(clarification):
        return [(block_type, text)]

    return [("ir_clarification", clarification), ("ir_moderation", moderation)]


def annotate_segment_ids_and_turns(segments: list[dict[str, Any]]) -> None:
    current_qa_turn_id: str | None = None
    current_analyst: str | None = None
    turn_counter = 0

    for index, segment in enumerate(segments, start=1):
        segment["block_id"] = f"seg_{index:04d}"

        if segment.get("section") != "qa":
            segment["qa_turn_id"] = None
            continue

        block_type = segment.get("block_type")
        if block_type == "analyst_question":
            speaker = str(segment.get("speaker") or "")
            if current_qa_turn_id is None or speaker != current_analyst:
                turn_counter += 1
                current_qa_turn_id = f"qa_{turn_counter:04d}"
                current_analyst = speaker
            segment["qa_turn_id"] = current_qa_turn_id
        elif block_type == "acknowledgement":
            segment["qa_turn_id"] = current_qa_turn_id
        elif block_type == "ir_moderation":
            segment["qa_turn_id"] = None
        else:
            segment["qa_turn_id"] = current_qa_turn_id


def merge_short_adjacent_segments(segments: list[dict[str, Any]], max_short_words: int = 30) -> None:
    if not segments:
        return

    merged: list[dict[str, Any]] = []
    for segment in segments:
        if merged and _should_merge_adjacent_segments(merged[-1], segment, max_short_words):
            previous = merged[-1]
            previous["text"] = _compact_text(f"{previous['text']} {segment['text']}")
            previous["block_type"] = _merged_block_type(
                str(previous.get("block_type")),
                str(segment.get("block_type")),
            )
            previous["legacy_section"] = legacy_section_for(
                section=str(previous["section"]),
                block_type=str(previous["block_type"]),
            )
            previous["page_end"] = max(int(previous["page_end"]), int(segment["page_end"]))
            previous["word_count"] = len(str(previous["text"]).split())
            previous["has_question"] = bool(previous.get("has_question")) or bool(segment.get("has_question"))
            continue
        merged.append(segment)

    segments[:] = merged


def _should_merge_adjacent_segments(
    previous: dict[str, Any],
    current: dict[str, Any],
    max_short_words: int,
) -> bool:
    if previous.get("speaker") != current.get("speaker"):
        return False
    if previous.get("speaker_type") != current.get("speaker_type"):
        return False
    if previous.get("section") != current.get("section"):
        return False
    if not _compatible_merge_block_types(
        str(previous.get("block_type")),
        str(current.get("block_type")),
    ):
        return False
    if previous.get("institution") != current.get("institution"):
        return False
    if previous.get("role_title") != current.get("role_title"):
        return False
    if current.get("block_type") in {"ir_moderation", "acknowledgement"}:
        return False
    if int(current.get("page_start") or 0) > int(previous.get("page_end") or 0) + 1:
        return False

    previous_words = int(previous.get("word_count") or len(str(previous.get("text", "")).split()))
    current_words = int(current.get("word_count") or len(str(current.get("text", "")).split()))
    if previous_words > max_short_words and current_words > max_short_words:
        return False
    if previous.get("block_type") == "analyst_question" and previous.get("has_question") and current.get("has_question"):
        return False

    return True


def _compatible_merge_block_types(previous_block_type: str, current_block_type: str) -> bool:
    if previous_block_type == current_block_type:
        return True
    return {previous_block_type, current_block_type} == {"answer_fragment", "management_answer"}


def _merged_block_type(previous_block_type: str, current_block_type: str) -> str:
    if {previous_block_type, current_block_type} == {"answer_fragment", "management_answer"}:
        return "management_answer"
    return previous_block_type


def legacy_section_for(section: str, block_type: str) -> str:
    if section == "prepared_remarks":
        return "prepared_remarks"
    return {
        "analyst_question": "qa_question",
        "management_answer": "qa_answer",
        "ir_moderation": "qa_moderation",
        "ir_clarification": "qa_ir_clarification",
        "management_clarification": "qa_management_clarification",
        "answer_fragment": "qa_answer_fragment",
        "acknowledgement": "qa_acknowledgement",
        "unknown": "qa_unknown",
    }.get(block_type, "qa_unknown")


def _qa_turn_block(segment: dict[str, Any]) -> dict[str, Any]:
    return {
        "block_id": segment.get("block_id"),
        "speaker": segment.get("speaker"),
        "speaker_type": segment.get("speaker_type"),
        "role_title": segment.get("role_title"),
        "institution": segment.get("institution"),
        "block_type": segment.get("block_type"),
        "page_start": segment.get("page_start"),
        "page_end": segment.get("page_end"),
        "word_count": segment.get("word_count"),
        "has_question": segment.get("has_question"),
        "text": segment.get("text"),
    }


def _is_qa_heading(line: str) -> bool:
    normalized = re.sub(r"\s+", " ", line.strip().casefold())
    return normalized in QA_MARKERS


def _get_text_before_qa(text: str) -> str:
    collected: list[str] = []
    for line in text.splitlines():
        if _is_qa_heading(line):
            break
        collected.append(line)
    return "\n".join(collected)


def _set_profile(
    profiles: dict[str, dict[str, str | None]],
    name: str,
    *,
    speaker_type: str,
    role_title: str | None,
) -> None:
    existing = profiles.get(name)
    if existing is None:
        profiles[name] = {"speaker_type": speaker_type, "role_title": role_title}
        return

    if existing.get("role_title") is None and role_title:
        existing["role_title"] = role_title
    if existing.get("speaker_type") == "unknown":
        existing["speaker_type"] = speaker_type


def _normalize_role_title(title: str) -> str:
    cleaned = _compact_text(title).strip(" ,.;")
    upper_titles = {"cfo", "ceo", "cro", "coo"}
    if cleaned.casefold() in upper_titles:
        return cleaned.upper()
    if cleaned.casefold() == "investor relations":
        return "Head of Investor Relations"
    if cleaned.casefold() == "head of investor relations":
        return "Head of Investor Relations"
    return cleaned


def _normalize_name(name: str) -> str:
    cleaned = re.sub(r"\s+", " ", name.strip())
    cleaned = re.split(rf"\.\s+(?=[{UPPER}])", cleaned, maxsplit=1)[0]
    cleaned = re.sub(r"\s+(?:And|But|So|Now)$", "", cleaned)
    return cleaned.strip(" .")


def _clean_institution(institution: str) -> str | None:
    cleaned = re.sub(r"\s+", " ", institution).strip(" .")
    if not cleaned:
        return None
    return cleaned


def _compact_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _is_acknowledgement(text: str) -> bool:
    return bool(ACKNOWLEDGEMENT_RE.match(text))


def _is_material_ir_clarification(text: str) -> bool:
    if len(text.split()) < 4:
        return False
    return bool(MATERIAL_IR_RE.search(text))


def _is_short_management_question(text: str) -> bool:
    return text.endswith("?") and len(text.split()) <= 18


def _is_short_answer_fragment(text: str) -> bool:
    return bool(SHORT_ANSWER_FRAGMENT_RE.match(text))
