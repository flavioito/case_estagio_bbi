from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


load_dotenv()


@dataclass(frozen=True)
class Settings:
    anthropic_api_key: str | None
    anthropic_model: str
    anthropic_review_model: str
    output_dir: Path
    temperature: float
    max_output_tokens: int
    debug: bool


def _as_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def get_settings() -> Settings:
    return Settings(
        anthropic_api_key=os.getenv("ANTHROPIC_API_KEY"),
        anthropic_model=os.getenv("ANTHROPIC_MODEL", "claude-haiku-4-5"),
        anthropic_review_model=os.getenv("ANTHROPIC_REVIEW_MODEL", "claude-sonnet-4-6"),
        output_dir=Path(os.getenv("OUTPUT_DIR", "output")),
        temperature=float(os.getenv("TEMPERATURE", "0.1")),
        max_output_tokens=int(os.getenv("MAX_OUTPUT_TOKENS", os.getenv("MAX_TOKENS", "6000"))),
        debug=_as_bool(os.getenv("DEBUG"), default=False),
    )
