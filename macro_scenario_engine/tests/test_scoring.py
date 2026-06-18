from __future__ import annotations

import pytest

from app.config import load_settings
from app.scoring import calculate_sector_scores, calculate_ticker_scores, load_catalog, select_top_tickers


@pytest.fixture(scope="module")
def catalog():
    settings = load_settings()
    return load_catalog(
        macro_factors_path=settings.macro_factors_path,
        sector_taxonomy_path=settings.sector_taxonomy_path,
        ticker_exposures_path=settings.ticker_exposures_path,
    )


def sector_score_map(factors: list[str], catalog) -> dict[str, float]:
    return {item.sector_id: item.score for item in calculate_sector_scores(factors, catalog)}


def test_selic_down_benefits_retail_and_real_estate(catalog) -> None:
    scores = sector_score_map(["selic_down", "domestic_growth_up", "credit_growth_up"], catalog)

    assert scores["discretionary_retail"] > 0
    assert scores["real_estate"] > 0
    assert scores["mining"] < 0


def test_oil_up_and_brl_depreciation_benefit_oil_gas(catalog) -> None:
    scores = sector_score_map(["oil_price_up", "brl_depreciation"], catalog)

    assert scores["oil_gas"] > 0
    assert scores["discretionary_retail"] < 0


def test_china_down_and_iron_ore_down_harm_mining_and_steel(catalog) -> None:
    scores = sector_score_map(["china_growth_down", "iron_ore_down", "global_risk_off"], catalog)

    assert scores["mining"] < 0
    assert scores["steel"] < 0


def test_ticker_selection_stays_inside_curated_universe(catalog) -> None:
    scored = calculate_ticker_scores(["oil_price_up", "brl_depreciation", "fiscal_risk_up"], catalog)
    positive, negative = select_top_tickers(scored)

    assert len(positive) == 3
    assert len(negative) == 3
    assert {item.ticker for item in positive + negative} <= catalog.allowed_tickers
    assert not ({item.ticker for item in positive} & {item.ticker for item in negative})


def test_positive_ticker_selection_diversifies_close_scores(catalog) -> None:
    scored = calculate_ticker_scores(
        ["selic_down", "inflation_down", "domestic_growth_up", "credit_growth_up"],
        catalog,
    )
    positive, _negative = select_top_tickers(scored)

    assert len({item.sector_id for item in positive}) == 3
    assert {item.ticker for item in positive} == {"MRVE3", "MGLU3", "YDUQ3"}
