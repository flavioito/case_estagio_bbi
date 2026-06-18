from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


DEFAULT_FACTOR_LABELS = {
    "selic_up": "Selic em alta",
    "selic_down": "Selic em queda",
    "long_rates_up": "juros longos em alta",
    "long_rates_down": "juros longos em queda",
    "inflation_up": "inflação em alta",
    "inflation_down": "inflação em queda",
    "brl_appreciation": "real apreciado",
    "brl_depreciation": "real depreciado",
    "domestic_growth_up": "atividade doméstica em melhora",
    "domestic_growth_down": "atividade doméstica em desaceleração",
    "unemployment_up": "desemprego em alta",
    "unemployment_down": "desemprego em queda",
    "credit_growth_up": "crédito em expansão",
    "credit_growth_down": "crédito em contração",
    "oil_price_up": "petróleo em alta",
    "oil_price_down": "petróleo em queda",
    "iron_ore_up": "minério de ferro em alta",
    "iron_ore_down": "minério de ferro em queda",
    "china_growth_up": "China em aceleração",
    "china_growth_down": "China em desaceleração",
    "global_risk_on": "apetite global por risco",
    "global_risk_off": "aversão global a risco",
    "fiscal_risk_up": "risco fiscal em alta",
    "fiscal_risk_down": "risco fiscal em queda",
    "regulatory_risk_up": "risco regulatório em alta",
    "regulatory_risk_down": "risco regulatório em queda",
}

SHORT_TERM_WEIGHTS = {
    "selic_down": 2.5,
    "selic_up": 2.0,
    "brl_appreciation": 1.3,
    "brl_depreciation": 1.3,
    "oil_price_up": 1.4,
    "oil_price_down": 1.4,
    "iron_ore_up": 1.3,
    "iron_ore_down": 1.3,
    "china_growth_up": 1.1,
    "china_growth_down": 1.1,
    "global_risk_on": 1.1,
    "global_risk_off": 1.1,
    "long_rates_up": 0.5,
    "long_rates_down": 0.7,
    "inflation_up": 0.5,
    "inflation_down": 0.7,
    "fiscal_risk_up": 0.4,
    "fiscal_risk_down": 0.6,
    "domestic_growth_up": 0.6,
    "domestic_growth_down": 0.5,
    "unemployment_up": 0.5,
    "unemployment_down": 0.6,
    "credit_growth_up": 1.2,
    "credit_growth_down": 0.8,
}

MEDIUM_TERM_WEIGHTS = {
    "selic_down": 0.8,
    "selic_up": 0.8,
    "brl_appreciation": 1.0,
    "brl_depreciation": 1.0,
    "oil_price_up": 1.0,
    "oil_price_down": 1.0,
    "iron_ore_up": 1.1,
    "iron_ore_down": 1.1,
    "china_growth_up": 1.3,
    "china_growth_down": 1.3,
    "global_risk_on": 1.2,
    "global_risk_off": 1.2,
    "long_rates_up": 1.5,
    "long_rates_down": 1.5,
    "inflation_up": 1.4,
    "inflation_down": 1.3,
    "fiscal_risk_up": 1.5,
    "fiscal_risk_down": 1.4,
    "domestic_growth_up": 1.4,
    "domestic_growth_down": 1.4,
    "unemployment_up": 1.3,
    "unemployment_down": 1.3,
    "credit_growth_up": 1.3,
    "credit_growth_down": 1.3,
}

DEFENSIVE_SECTOR_BONUS = {
    "utilities": 3.0,
    "telecom": 3.0,
    "food_retail": 2.2,
    "beverages": 1.8,
    "insurance": 1.5,
    "healthcare": 1.2,
    "banks": 0.7,
    "pulp_paper": 0.5,
    "oil_gas": 0.3,
    "mining": 0.2,
    "steel": -0.5,
    "logistics": -0.8,
    "aerospace": -1.0,
    "capital_markets": -1.2,
    "technology": -1.5,
    "education": -1.5,
    "shopping_malls": -1.8,
    "discretionary_retail": -2.2,
    "real_estate": -2.4,
}

SHORT_TERM_FACTOR_SECTOR_BONUS = {
    "selic_down": {
        "real_estate": 0.8,
        "shopping_malls": 0.7,
        "education": 0.6,
        "discretionary_retail": 0.5,
        "technology": 0.2,
    },
}


@dataclass(frozen=True)
class DataCatalog:
    macro_factors: dict[str, str]
    sectors: dict[str, dict[str, Any]]
    internal_sector_map: dict[str, str]
    ticker_exposures: dict[str, dict[str, Any]]
    data_source: str

    @property
    def allowed_factors(self) -> set[str]:
        return set(self.macro_factors)

    @property
    def allowed_sector_ids(self) -> set[str]:
        return set(self.sectors)

    @property
    def allowed_tickers(self) -> set[str]:
        return set(self.ticker_exposures)

    def sector_id_for_ticker(self, ticker: str) -> str:
        meta = self.ticker_exposures[ticker]
        internal_sector = meta.get("internal_sector", "")
        sector_id = self.internal_sector_map.get(internal_sector)
        if not sector_id:
            raise KeyError(f"internal_sector sem mapeamento na taxonomia: {internal_sector}")
        return sector_id

    def sector_name(self, sector_id: str) -> str:
        return self.sectors[sector_id]["name"]

    def factor_label(self, factor: str) -> str:
        return self.macro_factors.get(factor, DEFAULT_FACTOR_LABELS.get(factor, factor))


@dataclass(frozen=True)
class ScoredSector:
    sector_id: str
    sector_name: str
    score: float
    raw_score: float
    relative_score: float
    short_term_score: float
    medium_term_score: float
    impact_label: str
    matched_factors: list[str]
    factor_scores: dict[str, float]
    ticker_count: int
    rationale: str
    confidence: str


@dataclass(frozen=True)
class ScoredTicker:
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
    matched_positive_factors: list[str]
    matched_negative_factors: list[str]
    rationale: str
    confidence: str


def load_yaml_dict(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    return loaded or {}


def load_macro_factors(path: Path) -> dict[str, str]:
    raw = load_yaml_dict(path).get("macro_factors", {})
    factors: dict[str, str] = {}

    for entries in raw.values():
        if isinstance(entries, list):
            for factor in entries:
                factors[str(factor)] = DEFAULT_FACTOR_LABELS.get(str(factor), str(factor))
        elif isinstance(entries, dict):
            for factor, meta in entries.items():
                if isinstance(meta, dict):
                    factors[str(factor)] = str(meta.get("label") or DEFAULT_FACTOR_LABELS.get(str(factor), factor))
                else:
                    factors[str(factor)] = str(meta or DEFAULT_FACTOR_LABELS.get(str(factor), factor))

    if not factors:
        factors = dict(DEFAULT_FACTOR_LABELS)
    return factors


def load_sector_taxonomy(path: Path) -> tuple[dict[str, dict[str, Any]], dict[str, str]]:
    sectors = load_yaml_dict(path).get("sectors", {})
    if not sectors:
        raise ValueError("sector_taxonomy.yaml está vazio ou sem a chave 'sectors'.")

    internal_sector_map: dict[str, str] = {}
    for sector_id, meta in sectors.items():
        for internal_sector in meta.get("internal_sectors", []):
            if internal_sector in internal_sector_map:
                raise ValueError(f"internal_sector duplicado na taxonomia: {internal_sector}")
            internal_sector_map[internal_sector] = sector_id

    return sectors, internal_sector_map


def load_catalog(
    *,
    macro_factors_path: Path,
    sector_taxonomy_path: Path,
    ticker_exposures_path: Path,
) -> DataCatalog:
    macro_factors = load_macro_factors(macro_factors_path)
    sectors, internal_sector_map = load_sector_taxonomy(sector_taxonomy_path)
    ticker_exposures = load_yaml_dict(ticker_exposures_path)
    if not ticker_exposures:
        raise ValueError("Base curada de tickers vazia.")

    missing = sorted(
        {
            meta.get("internal_sector", "")
            for meta in ticker_exposures.values()
            if meta.get("internal_sector", "") not in internal_sector_map
        }
    )
    if missing:
        raise ValueError(f"internal_sector sem mapeamento na taxonomia: {', '.join(missing)}")

    return DataCatalog(
        macro_factors=macro_factors,
        sectors=sectors,
        internal_sector_map=internal_sector_map,
        ticker_exposures=ticker_exposures,
        data_source=str(ticker_exposures_path),
    )


def confidence_from_score(score: float) -> str:
    absolute = abs(score)
    if absolute >= 5:
        return "high"
    if absolute >= 2:
        return "medium"
    return "low"


def format_factor_labels(factors: list[str], catalog: DataCatalog, limit: int = 3) -> str:
    selected = factors[:limit]
    if not selected:
        return "fatores de baixa intensidade"
    labels = [catalog.factor_label(factor) for factor in selected]
    if len(labels) == 1:
        return labels[0]
    return ", ".join(labels[:-1]) + " e " + labels[-1]


def sector_rationale(
    sector_id: str,
    relative_score: float,
    raw_score: float,
    matched_factors: list[str],
    factor_scores: dict[str, float],
    catalog: DataCatalog,
) -> str:
    meta = catalog.sectors[sector_id]
    top_factors = sorted(matched_factors, key=lambda factor: abs(factor_scores.get(factor, 0)), reverse=True)
    labels = format_factor_labels(top_factors, catalog)
    if raw_score < 0:
        direction = "negativa"
        mechanism = "têm impacto negativo sobre"
    elif raw_score == 0:
        direction = "neutra em termos absolutos, com resiliência relativa"
        mechanism = "pressionam pouco"
    elif relative_score < 0:
        direction = "positiva em termos absolutos, mas abaixo da média do universo"
        mechanism = "favorecem menos"
    else:
        direction = "positiva"
        mechanism = "favorecem"
    return (
        f"{meta['name']} tem exposição agregada {direction} ao cenário porque {labels} "
        f"{mechanism} os principais tickers do setor na base curada. {meta['description']}"
    )


def impact_label(raw_score: float, relative_score: float) -> str:
    if raw_score < 0:
        return "impacto negativo absoluto"
    if raw_score == 0:
        return "neutro defensivo"
    if relative_score < 0:
        return "menor exposição relativa"
    return "impacto positivo"


def calculate_sector_scores(factors: list[str], catalog: DataCatalog) -> list[ScoredSector]:
    tickers_by_sector: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for ticker, meta in catalog.ticker_exposures.items():
        sector_id = catalog.sector_id_for_ticker(ticker)
        tickers_by_sector[sector_id].append(meta)

    raw_records: list[tuple[str, dict[str, Any], dict[str, float], float, float, float, list[str], int]] = []
    for sector_id, sector_meta in catalog.sectors.items():
        metas = tickers_by_sector.get(sector_id, [])
        if not metas:
            continue
        factor_scores: dict[str, float] = {}
        for factor in factors:
            scores = [float((meta.get("exposure_scores") or {}).get(factor, 0)) for meta in metas]
            factor_scores[factor] = sum(scores) / len(scores) if scores else 0.0

        raw_score = round(sum(factor_scores.values()), 2)
        short_score = round(weighted_factor_score(factor_scores, SHORT_TERM_WEIGHTS), 2)
        medium_score = round(weighted_factor_score(factor_scores, MEDIUM_TERM_WEIGHTS), 2)
        matched_factors = [factor for factor, value in factor_scores.items() if value != 0]
        raw_records.append((sector_id, sector_meta, factor_scores, raw_score, short_score, medium_score, matched_factors, len(metas)))

    universe_average = sum(record[3] for record in raw_records) / len(raw_records) if raw_records else 0.0
    scored: list[ScoredSector] = []
    for sector_id, sector_meta, factor_scores, raw_score, short_score, medium_score, matched_factors, ticker_count in raw_records:
        relative_score = round(raw_score - universe_average, 2)
        rationale = sector_rationale(sector_id, relative_score, raw_score, matched_factors, factor_scores, catalog)
        scored.append(
            ScoredSector(
                sector_id=sector_id,
                sector_name=str(sector_meta["name"]),
                score=relative_score,
                raw_score=raw_score,
                relative_score=relative_score,
                short_term_score=short_score,
                medium_term_score=medium_score,
                impact_label=impact_label(raw_score, relative_score),
                matched_factors=matched_factors,
                factor_scores=factor_scores,
                ticker_count=ticker_count,
                rationale=rationale,
                confidence=confidence_from_score(relative_score),
            )
        )

    return scored


def _first_sentence(text: str) -> str:
    text = " ".join((text or "").split())
    if not text:
        return ""
    pieces = text.split(". ")
    sentence = pieces[0].strip()
    if not sentence.endswith("."):
        sentence += "."
    return sentence


def ticker_rationale(
    ticker: str,
    meta: dict[str, Any],
    relative_score: float,
    raw_score: float,
    positive_factors: list[str],
    negative_factors: list[str],
    catalog: DataCatalog,
) -> str:
    factor_list = positive_factors if raw_score >= 0 else negative_factors
    labels = format_factor_labels(factor_list, catalog)
    source_rationale = _first_sentence(str(meta.get("rationale") or meta.get("business_description") or ""))
    if raw_score < 0:
        direction = "negativa"
    elif raw_score == 0:
        direction = "neutra em termos absolutos, mas defensiva em termos relativos"
    elif relative_score < 0:
        direction = "positiva em termos absolutos, mas menor que a média do universo"
    else:
        direction = "positiva"
    return (
        f"{ticker} apresenta exposição {direction} ao cenário por {labels}. "
        f"{source_rationale}"
    ).strip()


def calculate_ticker_scores(factors: list[str], catalog: DataCatalog) -> list[ScoredTicker]:
    raw_records: list[tuple[str, dict[str, Any], dict[str, float], float, float, float, list[str], list[str], str]] = []
    for ticker, meta in catalog.ticker_exposures.items():
        scores_by_factor = {factor: float((meta.get("exposure_scores") or {}).get(factor, 0)) for factor in factors}
        raw_score = round(sum(scores_by_factor.values()), 2)
        short_score = round(weighted_factor_score(scores_by_factor, SHORT_TERM_WEIGHTS), 2)
        medium_score = round(weighted_factor_score(scores_by_factor, MEDIUM_TERM_WEIGHTS), 2)
        positive_factors = [factor for factor, value in scores_by_factor.items() if value > 0]
        negative_factors = [factor for factor, value in scores_by_factor.items() if value < 0]
        sector_id = catalog.sector_id_for_ticker(ticker)
        raw_records.append((ticker, meta, scores_by_factor, raw_score, short_score, medium_score, positive_factors, negative_factors, sector_id))

    universe_average = sum(record[3] for record in raw_records) / len(raw_records) if raw_records else 0.0
    scored: list[ScoredTicker] = []
    for ticker, meta, _scores_by_factor, raw_score, short_score, medium_score, positive_factors, negative_factors, sector_id in raw_records:
        relative_score = round(raw_score - universe_average, 2)
        rationale = ticker_rationale(ticker, meta, relative_score, raw_score, positive_factors, negative_factors, catalog)
        scored.append(
            ScoredTicker(
                ticker=ticker,
                company=str(meta.get("company", ticker)),
                sector_id=sector_id,
                sector_name=catalog.sector_name(sector_id),
                score=relative_score,
                raw_score=raw_score,
                relative_score=relative_score,
                short_term_score=short_score,
                medium_term_score=medium_score,
                impact_label=impact_label(raw_score, relative_score),
                matched_positive_factors=positive_factors,
                matched_negative_factors=negative_factors,
                rationale=rationale,
                confidence=confidence_from_score(relative_score),
            )
        )
    return scored


def select_top_sectors(scored: list[ScoredSector], limit: int = 5) -> tuple[list[ScoredSector], list[ScoredSector]]:
    if scored and all(item.raw_score < 0 for item in scored):
        benefited = sorted(scored, key=lambda item: (defensive_adjusted_score(item), item.score, item.sector_name), reverse=True)[:limit]
    else:
        benefited = sorted(scored, key=lambda item: (item.score, item.sector_name), reverse=True)[:limit]
    benefited_ids = {item.sector_id for item in benefited}

    harmed_candidates = [item for item in sorted(scored, key=lambda item: (item.score, item.sector_name)) if item.sector_id not in benefited_ids]
    harmed = harmed_candidates[:limit]
    if len(harmed) < limit:
        harmed = sorted(scored, key=lambda item: (item.score, item.sector_name))[:limit]
    return benefited, harmed


def select_horizon_sector_rankings(
    scored: list[ScoredSector],
    limit: int = 5,
) -> tuple[list[ScoredSector], list[ScoredSector], list[ScoredSector]]:
    short_term_benefited = sorted(
        scored,
        key=lambda item: (
            short_term_thesis_score(item),
            short_term_positive_impulse(item),
            item.short_term_score,
            item.relative_score,
            item.sector_name,
        ),
        reverse=True,
    )[:limit]
    medium_term_harmed = sorted(
        scored,
        key=lambda item: (item.medium_term_score, item.relative_score, item.sector_name),
    )[:limit]

    if scored and all(item.raw_score <= 0 for item in scored):
        net_resilient = sorted(
            scored,
            key=lambda item: (defensive_adjusted_score(item), item.raw_score, item.sector_name),
            reverse=True,
        )[:limit]
    else:
        net_resilient = sorted(
            scored,
            key=lambda item: (item.raw_score, item.relative_score, defensive_adjusted_score(item), item.sector_name),
            reverse=True,
        )[:limit]
    return short_term_benefited, medium_term_harmed, net_resilient


def weighted_factor_score(factor_scores: dict[str, float], weights: dict[str, float]) -> float:
    return sum(value * weights.get(factor, 1.0) for factor, value in factor_scores.items())


def short_term_positive_impulse(item: ScoredSector) -> float:
    return round(
        sum(
            max(0.0, value) * SHORT_TERM_WEIGHTS.get(factor, 1.0)
            for factor, value in item.factor_scores.items()
        ),
        2,
    )


def short_term_thesis_score(item: ScoredSector) -> float:
    bonus = 0.0
    for factor, sector_bonus in SHORT_TERM_FACTOR_SECTOR_BONUS.items():
        if item.factor_scores.get(factor, 0.0) > 0:
            bonus += sector_bonus.get(item.sector_id, 0.0)
    return round(short_term_positive_impulse(item) + bonus, 2)


def defensive_adjusted_score(item: ScoredSector) -> float:
    return item.score + DEFENSIVE_SECTOR_BONUS.get(item.sector_id, 0.0)


def select_diversified_tickers(
    candidates: list[ScoredTicker],
    *,
    limit: int = 3,
    score_tolerance: float = 1.5,
) -> list[ScoredTicker]:
    ranked = sorted(candidates, key=lambda item: (item.score, item.raw_score, item.ticker), reverse=True)
    if len(ranked) <= limit:
        return ranked

    selected: list[ScoredTicker] = []
    selected_tickers: set[str] = set()
    selected_sectors: set[str] = set()
    best_score = ranked[0].score
    diversified_pool = [item for item in ranked if best_score - item.score <= score_tolerance]

    for item in diversified_pool:
        if item.sector_id in selected_sectors:
            continue
        selected.append(item)
        selected_tickers.add(item.ticker)
        selected_sectors.add(item.sector_id)
        if len(selected) == limit:
            return selected

    for item in ranked:
        if item.ticker in selected_tickers:
            continue
        selected.append(item)
        selected_tickers.add(item.ticker)
        if len(selected) == limit:
            return selected

    return selected


def select_bottom_tickers_diversified(
    candidates: list[ScoredTicker],
    *,
    excluded_tickers: set[str],
    limit: int = 3,
    score_tolerance: float = 1.5,
) -> list[ScoredTicker]:
    ranked = [
        item
        for item in sorted(candidates, key=lambda item: (item.score, item.raw_score, item.ticker))
        if item.ticker not in excluded_tickers
    ]
    if len(ranked) <= limit:
        return ranked

    selected: list[ScoredTicker] = []
    selected_tickers: set[str] = set()
    selected_sectors: set[str] = set()
    worst_score = ranked[0].score
    diversified_pool = [item for item in ranked if item.score - worst_score <= score_tolerance]

    for item in diversified_pool:
        if item.sector_id in selected_sectors:
            continue
        selected.append(item)
        selected_tickers.add(item.ticker)
        selected_sectors.add(item.sector_id)
        if len(selected) == limit:
            return selected

    for item in ranked:
        if item.ticker in selected_tickers:
            continue
        selected.append(item)
        selected_tickers.add(item.ticker)
        if len(selected) == limit:
            return selected

    return selected


def select_top_tickers(scored: list[ScoredTicker], limit: int = 3) -> tuple[list[ScoredTicker], list[ScoredTicker]]:
    positive = [item for item in sorted(scored, key=lambda item: (item.score, item.ticker), reverse=True) if item.score > 0]
    if len(positive) < limit:
        positive = sorted(scored, key=lambda item: (item.score, item.ticker), reverse=True)
    positive = select_diversified_tickers(positive, limit=limit)

    top_relative_ticker_ids = {item.ticker for item in positive}
    negative_candidates = [
        item
        for item in sorted(scored, key=lambda item: (item.score, item.ticker))
        if item.ticker not in top_relative_ticker_ids and item.score < 0
    ]
    if len(negative_candidates) < limit:
        negative_candidates = [
            item
            for item in sorted(scored, key=lambda item: (item.score, item.ticker))
            if item.ticker not in top_relative_ticker_ids
        ]
    negative = select_bottom_tickers_diversified(
        negative_candidates,
        excluded_tickers=top_relative_ticker_ids,
        limit=limit,
    )
    return positive, negative


def derive_sector_macro_scores(catalog: DataCatalog) -> dict[str, dict[str, float]]:
    all_factors = sorted(catalog.allowed_factors)
    sector_scores = calculate_sector_scores(all_factors, catalog)
    return {
        scored.sector_id: {factor: scored.factor_scores.get(factor, 0.0) for factor in all_factors}
        for scored in sector_scores
    }
