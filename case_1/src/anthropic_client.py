from __future__ import annotations

import logging

from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

from src.config import Settings, get_settings


logger = logging.getLogger(__name__)


class AnthropicClientError(Exception):
    """Raised when Anthropic cannot be called successfully."""


def _is_retryable_anthropic_error(exc: BaseException) -> bool:
    status_code = getattr(exc, "status_code", None)
    if status_code is None:
        return True
    return status_code in {408, 409, 429, 500, 502, 503, 504}


class AnthropicClient:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        if not self.settings.anthropic_api_key:
            raise AnthropicClientError(
                "ANTHROPIC_API_KEY nao configurada. Crie um .env ou exporte a variavel."
            )

        try:
            from anthropic import Anthropic
        except ImportError as exc:
            raise AnthropicClientError(
                "Dependencia anthropic ausente. Instale com: python -m pip install anthropic"
            ) from exc

        self._client = Anthropic(api_key=self.settings.anthropic_api_key)

    def send_message(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        model: str | None = None,
    ) -> str:
        try:
            message = self._create_message(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                model=model or self.settings.anthropic_model,
            )
        except Exception as exc:
            raise AnthropicClientError(
                "Erro ao chamar a API da Anthropic. Verifique a chave, conexao e limites de uso."
            ) from exc

        text = self._extract_text(message)
        if not text.strip():
            raise AnthropicClientError("A API da Anthropic retornou uma resposta vazia.")
        return text

    @retry(
        reraise=True,
        retry=retry_if_exception(_is_retryable_anthropic_error),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        before_sleep=before_sleep_log(logger, logging.WARNING),
    )
    def _create_message(self, *, system_prompt: str, user_prompt: str, model: str):
        return self._client.messages.create(
            model=model,
            max_tokens=self.settings.max_output_tokens,
            temperature=self.settings.temperature,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )

    @staticmethod
    def _extract_text(message) -> str:
        parts: list[str] = []
        for block in getattr(message, "content", []):
            text = getattr(block, "text", None)
            if text:
                parts.append(text)
        return "\n".join(parts)
