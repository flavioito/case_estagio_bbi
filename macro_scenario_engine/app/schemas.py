from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


Confidence = Literal["low", "medium", "high"]


def count_words(text: str) -> int:
    return len([word for word in text.split() if word.strip()])


class SectorImpact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sector_id: str
    sector_name: str
    score: float
    raw_score: float
    relative_score: float
    short_term_score: float
    medium_term_score: float
    impact_label: str
    matched_factors: list[str] = Field(default_factory=list)
    rationale: str
    confidence: Confidence

    @field_validator("sector_id", "sector_name", "rationale")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("campo obrigatório vazio")
        return value


class TickerImpact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ticker: str
    company: str
    sector_id: str
    sector_name: str
    score: float
    raw_score: float
    relative_score: float
    short_term_score: float
    medium_term_score: float
    impact_label: str
    matched_positive_factors: list[str] = Field(default_factory=list)
    matched_negative_factors: list[str] = Field(default_factory=list)
    rationale: str
    confidence: Confidence

    @field_validator("ticker", "company", "sector_id", "sector_name", "rationale")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("campo obrigatório vazio")
        return value

    @field_validator("ticker")
    @classmethod
    def _ticker_upper(cls, value: str) -> str:
        return value.upper()


class RiskItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    risk: str
    rationale: str
    related_factors: list[str] = Field(default_factory=list)

    @field_validator("risk", "rationale")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("campo obrigatório vazio")
        return value


class AnalysisMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    generated_at: datetime
    engine_version: str = "mvp-0.1.0"
    model_used: str
    used_llm: bool
    data_source: str
    factor_count: int
    ticker_universe_size: int


class AnalysisOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scenario: str
    scenario_summary: str
    macro_factors: list[str]
    benefited_sectors: list[SectorImpact]
    harmed_sectors: list[SectorImpact]
    short_term_benefited_sectors: list[SectorImpact]
    medium_term_harmed_sectors: list[SectorImpact]
    net_resilient_sectors: list[SectorImpact]
    positive_tickers: list[TickerImpact]
    negative_tickers: list[TickerImpact]
    risks: list[RiskItem]
    markdown_report: str
    metadata: AnalysisMetadata

    @field_validator(
        "benefited_sectors",
        "harmed_sectors",
        "short_term_benefited_sectors",
        "medium_term_harmed_sectors",
        "net_resilient_sectors",
    )
    @classmethod
    def _exactly_five_sectors(cls, value: list[SectorImpact]) -> list[SectorImpact]:
        if len(value) != 5:
            raise ValueError("a saída deve conter exatamente 5 setores")
        if len({item.sector_id for item in value}) != len(value):
            raise ValueError("setores duplicados na mesma lista")
        return value

    @field_validator("positive_tickers", "negative_tickers")
    @classmethod
    def _exactly_three_tickers(cls, value: list[TickerImpact]) -> list[TickerImpact]:
        if len(value) != 3:
            raise ValueError("a saída deve conter exatamente 3 tickers")
        if len({item.ticker for item in value}) != len(value):
            raise ValueError("tickers duplicados na mesma lista")
        return value

    @field_validator("risks")
    @classmethod
    def _exactly_three_risks(cls, value: list[RiskItem]) -> list[RiskItem]:
        if len(value) != 3:
            raise ValueError("a saída deve conter exatamente 3 riscos")
        return value

    @field_validator("macro_factors")
    @classmethod
    def _macro_factors_not_empty(cls, value: list[str]) -> list[str]:
        if not value:
            raise ValueError("ao menos um fator macroeconômico deve ser identificado")
        if len(set(value)) != len(value):
            raise ValueError("fatores macroeconômicos duplicados")
        return value

    @field_validator("markdown_report")
    @classmethod
    def _report_under_500_words(cls, value: str) -> str:
        if count_words(value) > 500:
            raise ValueError("relatório Markdown excede 500 palavras")
        return value

    def as_json_dict(self) -> dict:
        return self.model_dump(mode="json")
