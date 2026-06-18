from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from typing import Any

from app.config import Settings

logger = logging.getLogger(__name__)


class LLMClientError(Exception):
    """Raised when the LLM call fails or returns unusable content."""


@dataclass
class AnthropicLLMClient:
    settings: Settings
    timeout_seconds: float = 30.0
    max_retries: int = 2

    def __post_init__(self) -> None:
        self._client = None
        if not self.settings.anthropic_api_key:
            return
        try:
            from anthropic import Anthropic

            self._client = Anthropic(api_key=self.settings.anthropic_api_key, timeout=self.timeout_seconds)
        except Exception as exc:  # pragma: no cover - depends on optional external package.
            raise LLMClientError(f"Falha ao inicializar cliente Anthropic: {exc}") from exc

    @property
    def available(self) -> bool:
        return self._client is not None

    def complete(self, *, system_prompt: str, user_prompt: str, max_tokens: int | None = None) -> str:
        if not self.available:
            raise LLMClientError("ANTHROPIC_API_KEY não configurada.")

        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                response = self._client.messages.create(
                    model=self.settings.anthropic_model,
                    max_tokens=max_tokens or self.settings.max_tokens,
                    temperature=self.settings.temperature,
                    system=system_prompt,
                    messages=[{"role": "user", "content": user_prompt}],
                )
                chunks: list[str] = []
                for block in response.content:
                    text = getattr(block, "text", None)
                    if text:
                        chunks.append(text)
                result = "\n".join(chunks).strip()
                if not result:
                    raise LLMClientError("Resposta vazia do modelo.")
                return result
            except Exception as exc:  # pragma: no cover - requires network/API.
                last_error = exc
                logger.warning("Falha na chamada Anthropic, tentativa %s: %s", attempt + 1, exc)
                if attempt < self.max_retries:
                    time.sleep(1.5 * (attempt + 1))

        raise LLMClientError(f"Falha na chamada Anthropic: {last_error}") from last_error

    def complete_json(self, *, system_prompt: str, user_prompt: str, max_tokens: int | None = None) -> Any:
        raw = self.complete(system_prompt=system_prompt, user_prompt=user_prompt, max_tokens=max_tokens)
        try:
            return json.loads(_extract_json(raw))
        except json.JSONDecodeError as exc:
            raise LLMClientError(f"Modelo retornou JSON inválido: {raw[:500]}") from exc


def _extract_json(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = [line for line in stripped.splitlines() if not line.strip().startswith("```")]
        stripped = "\n".join(lines).strip()

    first_object = stripped.find("{")
    first_array = stripped.find("[")
    starts = [idx for idx in [first_object, first_array] if idx >= 0]
    if not starts:
        return stripped
    start = min(starts)

    last_object = stripped.rfind("}")
    last_array = stripped.rfind("]")
    end = max(last_object, last_array)
    if end <= start:
        return stripped
    return stripped[start : end + 1]
