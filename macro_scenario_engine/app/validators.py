from __future__ import annotations

import re
from collections.abc import Iterable

from app.schemas import AnalysisOutput, count_words


class MacroScenarioError(Exception):
    """Base exception for expected pipeline failures."""


class InputValidationError(MacroScenarioError):
    """Raised when the user scenario is empty, too short, or out of scope."""


class OutputValidationError(MacroScenarioError):
    """Raised when the structured analysis violates project constraints."""


OUT_OF_SCOPE_PATTERNS = [
    r"\bqual\s+a[cç][aã]o\s+(devo|eu\s+devo)\s+comprar\b",
    r"\b(devo|posso)\s+comprar\b",
    r"\b(devo|posso)\s+vender\b",
    r"\brecomende\s+(uma\s+)?a[cç][aã]o\b",
    r"\bindique\s+(uma\s+)?a[cç][aã]o\b",
    r"\bpre[cç]o[-\s]?alvo\b",
    r"\bretorno\s+garantido\b",
]


def validate_input_scenario(scenario: str, min_chars: int = 20) -> str:
    cleaned = " ".join((scenario or "").strip().split())
    if not cleaned:
        raise InputValidationError("Erro: o cenário macroeconômico precisa conter uma descrição mínima.")
    if len(cleaned) < min_chars:
        raise InputValidationError("Erro: descreva o cenário macroeconômico com um pouco mais de contexto.")

    lowered = cleaned.lower()
    if any(re.search(pattern, lowered) for pattern in OUT_OF_SCOPE_PATTERNS):
        raise InputValidationError(
            "A ferramenta não fornece recomendação personalizada de investimento. "
            "Reformule como um cenário macroeconômico."
        )
    return cleaned


def validate_known_factors(factors: Iterable[str], allowed_factors: set[str]) -> list[str]:
    unique_factors = list(dict.fromkeys(factors))
    invalid = sorted(set(unique_factors) - allowed_factors)
    if invalid:
        raise OutputValidationError(f"Fatores macroeconômicos fora da base permitida: {', '.join(invalid)}")
    if not unique_factors:
        raise InputValidationError(
            "Não foi possível identificar fatores macroeconômicos claros. Inclua variáveis como juros, "
            "inflação, câmbio, crescimento, commodities, China, fiscal ou crédito."
        )
    return unique_factors


def validate_report_word_count(markdown_report: str, max_words: int = 500) -> None:
    total = count_words(markdown_report)
    if total > max_words:
        raise OutputValidationError(f"Relatório Markdown excede {max_words} palavras: {total} palavras.")


def validate_universe(
    output: AnalysisOutput,
    *,
    allowed_sector_ids: set[str],
    allowed_tickers: set[str],
    allowed_factors: set[str],
) -> None:
    all_sector_lists = (
        output.benefited_sectors
        + output.harmed_sectors
        + output.short_term_benefited_sectors
        + output.medium_term_harmed_sectors
        + output.net_resilient_sectors
    )
    sector_ids = {item.sector_id for item in all_sector_lists}
    unknown_sectors = sorted(sector_ids - allowed_sector_ids)
    if unknown_sectors:
        raise OutputValidationError(f"Setores fora da taxonomia: {', '.join(unknown_sectors)}")

    tickers = {item.ticker for item in output.top_relative_tickers + output.negative_tickers}
    unknown_tickers = sorted(tickers - allowed_tickers)
    if unknown_tickers:
        raise OutputValidationError(f"Tickers fora da base curada: {', '.join(unknown_tickers)}")

    used_factors = set(output.macro_factors)
    for sector in all_sector_lists:
        used_factors.update(sector.matched_factors)
    for ticker in output.top_relative_tickers + output.negative_tickers:
        used_factors.update(ticker.matched_positive_factors)
        used_factors.update(ticker.matched_negative_factors)
    for risk in output.risks:
        used_factors.update(risk.related_factors)

    unknown_factors = sorted(used_factors - allowed_factors)
    if unknown_factors:
        raise OutputValidationError(f"Fatores fora da base permitida: {', '.join(unknown_factors)}")

    validate_report_word_count(output.markdown_report)
