from __future__ import annotations

import pytest

from app.config import load_settings
from app.pipeline import extract_macro_factors_heuristic, is_complete_markdown_report, run_analysis
from app.scoring import load_catalog
from app.validators import InputValidationError


@pytest.fixture(scope="module")
def catalog():
    settings = load_settings()
    return load_catalog(
        macro_factors_path=settings.macro_factors_path,
        sector_taxonomy_path=settings.sector_taxonomy_path,
        ticker_exposures_path=settings.ticker_exposures_path,
    )


def test_pipeline_returns_valid_schema_and_markdown(catalog) -> None:
    output = run_analysis(
        "Selic em queda, inflação controlada, crédito voltando a crescer e atividade doméstica acelerando.",
        use_llm=False,
    )

    assert len(output.benefited_sectors) == 5
    assert len(output.harmed_sectors) == 5
    assert len(output.short_term_benefited_sectors) == 5
    assert len(output.medium_term_harmed_sectors) == 5
    assert len(output.net_resilient_sectors) == 5
    assert len(output.top_relative_tickers) == 3
    assert len(output.negative_tickers) == 3
    assert len(output.risks) == 3
    assert output.markdown_report.startswith("# Análise macro-setorial")
    assert "**Horizonte.**" in output.markdown_report
    assert "Setores com menor exposição relativa" in output.markdown_report
    assert "Tickers com menor exposição relativa" in output.markdown_report
    assert "rel." in output.markdown_report
    assert "abs." in output.markdown_report
    assert {item.ticker for item in output.top_relative_tickers + output.negative_tickers} <= catalog.allowed_tickers
    assert {item.sector_id for item in output.benefited_sectors + output.harmed_sectors} <= catalog.allowed_sector_ids
    assert all(item.raw_score >= 0 for item in output.negative_tickers)
    assert all(item.relative_score < 0 for item in output.negative_tickers)
    assert all(isinstance(item.short_term_score, float) for item in output.benefited_sectors)
    assert all(isinstance(item.medium_term_score, float) for item in output.benefited_sectors)
    assert output.medium_term_harmed_sectors == sorted(
        output.medium_term_harmed_sectors,
        key=lambda item: (item.medium_term_score, item.relative_score, item.sector_name),
    )


def test_pipeline_raises_when_no_macro_factor_is_identified() -> None:
    with pytest.raises(InputValidationError):
        run_analysis("Este texto fala apenas sobre preferências genéricas sem variável econômica clara.", use_llm=False)


def test_parser_does_not_turn_desacelerando_into_acceleration(catalog) -> None:
    factors = extract_macro_factors_heuristic(
        "China desacelerando, minério em queda, dólar global forte e aversão a risco em emergentes.",
        catalog,
    )

    assert "china_growth_down" in factors
    assert "china_growth_up" not in factors
    assert "iron_ore_down" in factors
    assert "iron_ore_up" not in factors


def test_parser_captures_extreme_scenario_phrasings(catalog) -> None:
    oil_factors = extract_macro_factors_heuristic(
        "Petróleo sobe de forma abrupta, Brent elevado, real deprecia, aversão global a risco e inflação acelerando.",
        catalog,
    )
    china_factors = extract_macro_factors_heuristic(
        "A economia chinesa entra em desaceleração intensa e a demanda por minério de ferro enfraquece.",
        catalog,
    )

    assert {"oil_price_up", "brl_depreciation", "global_risk_off", "inflation_up"} <= set(oil_factors)
    assert {"china_growth_down", "iron_ore_down"} <= set(china_factors)


def test_extreme_easing_scenario_surfaces_short_term_rate_sensitives() -> None:
    output = run_analysis(
        "Banco Central em afrouxamento monetário, reduzindo a Selic, com atividade doméstica desacelerando, "
        "mercado de trabalho piorando, inflação elevada, juros longos abrindo e dúvidas sobre sustentabilidade fiscal.",
        use_llm=False,
    )
    short_term_names = {item.sector_name for item in output.short_term_benefited_sectors}
    expected_rate_sensitives = {
        "Construção e incorporação",
        "Varejo discricionário",
        "Shoppings",
        "Educação",
    }

    assert len(short_term_names & expected_rate_sensitives) >= 3
    assert "Construção e incorporação" in short_term_names


def test_domestic_positive_scenario_has_specific_risks() -> None:
    output = run_analysis(
        "Selic em queda, inflação controlada, crédito voltando a crescer e atividade doméstica acelerando.",
        use_llm=False,
    )
    risk_names = {risk.risk for risk in output.risks}

    assert "Reversão de inflação e juros" in risk_names
    assert "Crédito não se materializa" in risk_names
    assert "Frustração do ciclo doméstico" in risk_names


def test_adverse_scenario_uses_resilience_heading_instead_of_positive_label() -> None:
    output = run_analysis(
        "China desacelerando, minério em queda, dólar global forte e aversão a risco em emergentes.",
        use_llm=False,
    )

    assert "Setores menos pressionados" in output.markdown_report
    assert "setores com menor pressão imediata" in output.markdown_report
    assert "setores com maior impulso positivo são Construção" not in output.markdown_report
    assert (
        "Tickers menos pressionados" in output.markdown_report
        or "Tickers neutros ou menos pressionados" in output.markdown_report
        or "Tickers favorecidos ou resilientes" in output.markdown_report
    )
    assert "Tickers com exposição positiva" not in output.markdown_report
    assert "Companhias aéreas" not in {item.sector_name for item in output.benefited_sectors}


def test_fiscal_stress_scenario_prioritizes_fiscal_risk() -> None:
    output = run_analysis(
        "Expansão fiscal relevante, flexibilização das metas fiscais, trajetória da dívida questionada, "
        "juros longos em alta, real depreciado, inflação pressionada e aversão global a risco.",
        use_llm=False,
    )
    risk_names = [risk.risk for risk in output.risks]

    assert "Risco fiscal, político e regulatório" in risk_names


def test_truncated_llm_report_is_rejected() -> None:
    assert not is_complete_markdown_report(
        "## Riscos\n1. Aversão global a risco pode afetar",
        max_words=500,
    )
    assert is_complete_markdown_report(
        "## Ressalva\nEsta análise não constitui recomendação personalizada de investimento.",
        max_words=500,
    )
