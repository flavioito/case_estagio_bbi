#!/usr/bin/env python3
"""
add_new_tickers_to_yaml.py

Adiciona novos tickers à base YAML já curada, sem sobrescrever os tickers existentes.

Este script foi pensado para expandir a base de 42 tickers para uma versão mais completa
do MVP, adicionando novos nomes setoriais relevantes.

Uso:
python app/curation/add_new_tickers_to_yaml.py \
  --input data/curated/ticker_exposures_curated.yaml \
  --output data/curated/ticker_exposures_expanded.yaml

Depois de rodar:
1. Revise os novos tickers no YAML.
2. Ajuste manualmente exposure_scores, se necessário.
3. Rode derive_exposures_from_scores.py.
4. Rode o validador da base.

Observação sobre aéreas:
- O padrão abaixo usa AZUL3, pois é o ticker atual exibido pela B3 para Azul.
- Se quiser forçar AZUL4 ou GOLL4/GOLL54, altere AIRLINE_TICKER e AIRLINE_ENTRY.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import yaml


MACRO_FACTORS = [
    "selic_up",
    "selic_down",
    "long_rates_up",
    "long_rates_down",
    "inflation_up",
    "inflation_down",
    "brl_appreciation",
    "brl_depreciation",
    "domestic_growth_up",
    "domestic_growth_down",
    "unemployment_up",
    "unemployment_down",
    "credit_growth_up",
    "credit_growth_down",
    "oil_price_up",
    "oil_price_down",
    "iron_ore_up",
    "iron_ore_down",
    "china_growth_up",
    "china_growth_down",
    "global_risk_on",
    "global_risk_off",
    "fiscal_risk_up",
    "fiscal_risk_down",
    "regulatory_risk_up",
    "regulatory_risk_down",
]


# =============================================================================
# Escolha da aérea
# =============================================================================
# Recomendado: AZUL3.
# Alternativas possíveis, mas menos recomendadas para MVP:
# - AZUL4: ticker antigo/legado em várias bases.
# - GOLL4/GOLL54: ticker com alto ruído societário/restruturação.
AIRLINE_TICKER = "AZUL3"


def default_scores() -> dict[str, int]:
    return {factor: 0 for factor in MACRO_FACTORS}


def merge_scores(custom_scores: dict[str, int]) -> dict[str, int]:
    scores = default_scores()
    for factor, score in custom_scores.items():
        if factor not in scores:
            raise ValueError(f"Fator macro inválido em scores: {factor}")
        if not isinstance(score, int) or score < -3 or score > 3:
            raise ValueError(f"Score inválido para {factor}: {score}. Use inteiro de -3 a +3.")
        scores[factor] = score
    return scores


def derive_exposures_from_scores(scores: dict[str, int], min_abs_score: int = 2) -> tuple[list[str], list[str]]:
    positive = [
        factor
        for factor, score in scores.items()
        if isinstance(score, int) and score >= min_abs_score
    ]

    negative = [
        factor
        for factor, score in scores.items()
        if isinstance(score, int) and score <= -min_abs_score
    ]

    positive = sorted(positive, key=lambda factor: scores[factor], reverse=True)
    negative = sorted(negative, key=lambda factor: scores[factor])

    return positive, negative


def build_entry(
    *,
    company: str,
    mvp_group: str,
    internal_sector: str,
    b3_sector: str | None,
    b3_subsector: str | None,
    b3_segment: str | None,
    business_description: str,
    revenue_profile: dict[str, Any],
    company_characteristics: list[str],
    rationale: str,
    confidence: str,
    scores: dict[str, int],
    sources: list[str] | None = None,
) -> dict[str, Any]:
    full_scores = merge_scores(scores)
    positive_exposures, negative_exposures = derive_exposures_from_scores(full_scores)

    return {
        "company": company,
        "mvp_group": mvp_group,
        "internal_sector": internal_sector,
        "b3_sector": b3_sector,
        "b3_subsector": b3_subsector,
        "b3_segment": b3_segment,
        "business_description": business_description,
        "revenue_profile": revenue_profile,
        "positive_exposures": positive_exposures,
        "negative_exposures": negative_exposures,
        "exposure_scores": full_scores,
        "company_characteristics": company_characteristics,
        "rationale": rationale,
        "confidence": confidence,
        "curation_status": "needs_review",
        "sources": sources or [
            "manual addition",
            "B3 classification to verify",
            "CVM companies to verify",
        ],
    }


# =============================================================================
# Novos tickers recomendados
# =============================================================================

NEW_TICKERS: dict[str, dict[str, Any]] = {
    # -------------------------------------------------------------------------
    # 14 tickers sugeridos anteriormente
    # -------------------------------------------------------------------------
    "B3SA3": build_entry(
        company="B3",
        mvp_group="Bancos e Financeiros",
        internal_sector="market_infrastructure",
        b3_sector="Financeiro",
        b3_subsector="Serviços Financeiros Diversos",
        b3_segment="Serviços Financeiros Diversos",
        business_description=(
            "Operadora da bolsa brasileira e infraestrutura de mercado, com receitas ligadas a negociação, "
            "pós-negociação, registro, depositária e serviços de dados."
        ),
        revenue_profile={
            "currency": "brl",
            "geography": "brazil",
            "commodity_linked": False,
            "regulated": True,
        },
        company_characteristics=[
            "infraestrutura de mercado",
            "sensível a volume negociado",
            "exposição a mercado de capitais",
            "beneficiada por maior apetite a risco",
        ],
        rationale=(
            "A B3 é sensível ao apetite por risco, volume negociado, emissões e atividade de mercado de capitais. "
            "Cenários de queda de juros, risk-on e melhora de fluxo para bolsa tendem a favorecer receitas de negociação "
            "e pós-negociação, enquanto aversão a risco e fechamento do mercado de capitais reduzem volumes."
        ),
        confidence="high",
        scores={
            "selic_up": -1,
            "selic_down": 2,
            "long_rates_up": -2,
            "long_rates_down": 2,
            "domestic_growth_up": 2,
            "domestic_growth_down": -2,
            "credit_growth_up": 1,
            "credit_growth_down": -1,
            "global_risk_on": 3,
            "global_risk_off": -3,
            "fiscal_risk_up": -2,
            "fiscal_risk_down": 1,
            "regulatory_risk_up": -1,
            "regulatory_risk_down": 1,
        },
    ),

    "BBSE3": build_entry(
        company="BB Seguridade",
        mvp_group="Bancos e Financeiros",
        internal_sector="insurance",
        b3_sector="Financeiro",
        b3_subsector="Previdência e Seguros",
        b3_segment="Seguradoras",
        business_description=(
            "Holding de seguros, previdência, capitalização e corretagem ligada ao ecossistema Banco do Brasil."
        ),
        revenue_profile={
            "currency": "brl",
            "geography": "brazil",
            "commodity_linked": False,
            "regulated": True,
        },
        company_characteristics=[
            "seguradora",
            "resultado financeiro relevante",
            "exposição a juros",
            "perfil relativamente defensivo",
        ],
        rationale=(
            "BB Seguridade combina exposição a seguros, previdência e resultado financeiro, sendo impactada por juros, "
            "inflação, sinistralidade e renda doméstica. A relação com juros é relevante, mas não totalmente linear, pois "
            "juros altos podem favorecer resultado financeiro enquanto atividade fraca pode afetar crescimento de prêmios."
        ),
        confidence="medium",
        scores={
            "selic_up": 2,
            "selic_down": -1,
            "long_rates_up": 1,
            "long_rates_down": -1,
            "inflation_up": -1,
            "inflation_down": 1,
            "domestic_growth_up": 1,
            "domestic_growth_down": -1,
            "unemployment_up": -1,
            "unemployment_down": 1,
            "global_risk_off": -1,
            "fiscal_risk_up": -1,
            "regulatory_risk_up": -2,
            "regulatory_risk_down": 1,
        },
    ),

    "PSSA3": build_entry(
        company="Porto Seguro",
        mvp_group="Bancos e Financeiros",
        internal_sector="insurance",
        b3_sector="Financeiro",
        b3_subsector="Previdência e Seguros",
        b3_segment="Seguradoras",
        business_description=(
            "Seguradora privada com atuação em seguros auto, residência, saúde, serviços financeiros e negócios adjacentes."
        ),
        revenue_profile={
            "currency": "brl",
            "geography": "brazil",
            "commodity_linked": False,
            "regulated": True,
        },
        company_characteristics=[
            "seguradora privada",
            "exposição a resultado financeiro",
            "sensível a sinistralidade",
            "exposição a renda doméstica",
        ],
        rationale=(
            "Porto Seguro é afetada por juros, resultado financeiro, sinistralidade e atividade doméstica. Juros mais altos "
            "podem favorecer receitas financeiras, mas atividade fraca e inflação de custos podem pressionar crescimento e margens."
        ),
        confidence="medium",
        scores={
            "selic_up": 2,
            "selic_down": -1,
            "inflation_up": -2,
            "inflation_down": 1,
            "domestic_growth_up": 1,
            "domestic_growth_down": -1,
            "unemployment_up": -1,
            "unemployment_down": 1,
            "credit_growth_up": 1,
            "credit_growth_down": -1,
            "fiscal_risk_up": -1,
            "regulatory_risk_up": -2,
        },
    ),

    "RENT3": build_entry(
        company="Localiza",
        mvp_group="Transporte, Telecom e Tecnologia",
        internal_sector="car_rental_mobility",
        b3_sector="Consumo Cíclico",
        b3_subsector="Diversos",
        b3_segment="Aluguel de carros",
        business_description=(
            "Empresa de aluguel de veículos, gestão de frotas e venda de seminovos, com exposição ao ciclo doméstico, "
            "juros e preços de veículos."
        ),
        revenue_profile={
            "currency": "brl",
            "geography": "brazil",
            "commodity_linked": False,
            "regulated": False,
        },
        company_characteristics=[
            "locação de veículos",
            "capital intensivo",
            "sensível a juros",
            "exposição a preço de seminovos",
        ],
        rationale=(
            "Localiza é sensível a juros, custo de capital, demanda corporativa e preço de seminovos. Queda de juros e "
            "melhora da atividade tendem a favorecer expansão de frota e demanda, enquanto juros altos pressionam custo "
            "financeiro e valuation."
        ),
        confidence="high",
        scores={
            "selic_up": -3,
            "selic_down": 3,
            "long_rates_up": -2,
            "long_rates_down": 2,
            "inflation_up": -1,
            "inflation_down": 1,
            "domestic_growth_up": 3,
            "domestic_growth_down": -3,
            "unemployment_up": -1,
            "unemployment_down": 1,
            "credit_growth_up": 2,
            "credit_growth_down": -2,
            "global_risk_on": 1,
            "global_risk_off": -1,
            "fiscal_risk_up": -1,
        },
    ),

    "RADL3": build_entry(
        company="Raia Drogasil",
        mvp_group="Saúde e Educação",
        internal_sector="healthcare_retail",
        b3_sector="Saúde",
        b3_subsector="Comércio e Distribuição",
        b3_segment="Medicamentos e Outros Produtos",
        business_description=(
            "Rede de farmácias com exposição a consumo defensivo, saúde, renda doméstica e inflação de medicamentos."
        ),
        revenue_profile={
            "currency": "brl",
            "geography": "brazil",
            "commodity_linked": False,
            "regulated": True,
        },
        company_characteristics=[
            "varejo farmacêutico",
            "consumo defensivo",
            "exposição a renda doméstica",
            "menor ciclicidade que varejo discricionário",
        ],
        rationale=(
            "Raia Drogasil possui perfil mais defensivo por atuar em medicamentos e produtos de saúde, mas ainda é sensível "
            "à renda doméstica, inflação regulada de medicamentos e custo de expansão. Em cenários de desaceleração, tende "
            "a ser mais resiliente que varejo discricionário."
        ),
        confidence="medium",
        scores={
            "selic_up": -1,
            "selic_down": 1,
            "long_rates_up": -1,
            "long_rates_down": 1,
            "inflation_up": -1,
            "inflation_down": 1,
            "domestic_growth_up": 2,
            "domestic_growth_down": -1,
            "unemployment_up": -1,
            "unemployment_down": 1,
            "credit_growth_up": 1,
            "credit_growth_down": -1,
            "global_risk_off": -1,
            "regulatory_risk_up": -2,
        },
    ),

    "WEGE3": build_entry(
        company="WEG",
        mvp_group="Transporte, Telecom e Tecnologia",
        internal_sector="industrials_exporter",
        b3_sector="Bens Industriais",
        b3_subsector="Máquinas e Equipamentos",
        b3_segment="Motores, Compressores e Outros",
        business_description=(
            "Empresa industrial global com atuação em motores, automação, energia e equipamentos elétricos, com exposição "
            "a ciclo global, câmbio e capex."
        ),
        revenue_profile={
            "currency": "mixed",
            "geography": "global",
            "commodity_linked": False,
            "regulated": False,
        },
        company_characteristics=[
            "industrial exportadora",
            "receita global",
            "exposição a capex",
            "sensível a câmbio e ciclo global",
        ],
        rationale=(
            "WEG combina exposição ao ciclo industrial global, investimentos em energia, automação e câmbio. Real depreciado "
            "e capex global forte tendem a favorecer receitas, enquanto juros longos altos e risk-off podem pressionar "
            "valuation de empresas de crescimento."
        ),
        confidence="medium",
        scores={
            "selic_up": -1,
            "selic_down": 1,
            "long_rates_up": -2,
            "long_rates_down": 2,
            "brl_appreciation": -1,
            "brl_depreciation": 2,
            "domestic_growth_up": 1,
            "domestic_growth_down": -1,
            "china_growth_up": 1,
            "china_growth_down": -1,
            "global_risk_on": 2,
            "global_risk_off": -2,
            "fiscal_risk_up": -1,
        },
    ),

    "VBBR3": build_entry(
        company="Vibra Energia",
        mvp_group="Óleo e Gás",
        internal_sector="fuel_distribution",
        b3_sector="Petróleo, Gás e Biocombustíveis",
        b3_subsector="Petróleo, Gás e Biocombustíveis",
        b3_segment="Exploração, Refino e Distribuição",
        business_description=(
            "Distribuidora de combustíveis com exposição a volumes domésticos, margens de distribuição, atividade econômica "
            "e preços de combustíveis."
        ),
        revenue_profile={
            "currency": "brl",
            "geography": "brazil",
            "commodity_linked": True,
            "regulated": True,
        },
        company_characteristics=[
            "distribuição de combustíveis",
            "exposição a volumes domésticos",
            "sensível a atividade econômica",
            "margens influenciadas por dinâmica de combustíveis",
        ],
        rationale=(
            "Vibra é mais exposta a volumes, margens de distribuição e atividade doméstica do que ao preço do petróleo em si. "
            "Crescimento econômico tende a favorecer demanda por combustíveis, enquanto volatilidade de preços, regulação e "
            "compressão de margens podem prejudicar resultados."
        ),
        confidence="medium",
        scores={
            "selic_up": -1,
            "selic_down": 1,
            "inflation_up": -1,
            "inflation_down": 1,
            "domestic_growth_up": 2,
            "domestic_growth_down": -2,
            "unemployment_up": -1,
            "unemployment_down": 1,
            "oil_price_up": -1,
            "oil_price_down": 1,
            "global_risk_off": -1,
            "fiscal_risk_up": -2,
            "regulatory_risk_up": -2,
            "regulatory_risk_down": 1,
        },
    ),

    "EQTL3": build_entry(
        company="Equatorial Energia",
        mvp_group="Utilities e Infraestrutura",
        internal_sector="electric_utilities_distribution",
        b3_sector="Utilidade Pública",
        b3_subsector="Energia Elétrica",
        b3_segment="Energia Elétrica",
        business_description=(
            "Grupo de utilities com forte atuação em distribuição de energia, transmissão, saneamento e infraestrutura regulada."
        ),
        revenue_profile={
            "currency": "brl",
            "geography": "brazil",
            "commodity_linked": False,
            "regulated": True,
        },
        company_characteristics=[
            "utility regulada",
            "distribuição de energia",
            "exposição a regulação",
            "sensível a juros e inflação regulatória",
        ],
        rationale=(
            "Equatorial possui exposição relevante a ativos regulados de energia e infraestrutura, com receitas influenciadas "
            "por revisões tarifárias, inflação e custo de capital. Queda de juros tende a beneficiar utilities reguladas, "
            "enquanto risco regulatório e fiscal podem pressionar valuation."
        ),
        confidence="high",
        scores={
            "selic_up": -2,
            "selic_down": 2,
            "long_rates_up": -2,
            "long_rates_down": 2,
            "inflation_up": 1,
            "inflation_down": -1,
            "domestic_growth_up": 1,
            "domestic_growth_down": -1,
            "credit_growth_up": 1,
            "credit_growth_down": -1,
            "global_risk_off": -1,
            "fiscal_risk_up": -2,
            "fiscal_risk_down": 1,
            "regulatory_risk_up": -3,
            "regulatory_risk_down": 2,
        },
    ),

    "AURE3": build_entry(
        company="Auren Energia",
        mvp_group="Utilities e Infraestrutura",
        internal_sector="renewable_power_generation",
        b3_sector="Utilidade Pública",
        b3_subsector="Energia Elétrica",
        b3_segment="Energia Elétrica",
        business_description=(
            "Geradora e comercializadora de energia com portfólio relevante em fontes renováveis e exposição a preços de energia, "
            "hidrologia, contratos e custo de capital."
        ),
        revenue_profile={
            "currency": "brl",
            "geography": "brazil",
            "commodity_linked": False,
            "regulated": True,
        },
        company_characteristics=[
            "geração renovável",
            "exposição a preços de energia",
            "sensível a juros",
            "perfil de duration longa",
        ],
        rationale=(
            "Auren é sensível a preços de energia, hidrologia, contratos e custo de capital. Juros menores tendem a favorecer "
            "ativos de energia de duration longa, enquanto risco regulatório, preços baixos de energia e juros altos pressionam a tese."
        ),
        confidence="medium",
        scores={
            "selic_up": -2,
            "selic_down": 2,
            "long_rates_up": -2,
            "long_rates_down": 2,
            "inflation_up": 1,
            "inflation_down": -1,
            "domestic_growth_up": 1,
            "domestic_growth_down": -1,
            "global_risk_off": -1,
            "fiscal_risk_up": -1,
            "regulatory_risk_up": -3,
            "regulatory_risk_down": 2,
        },
    ),

    "CSMG3": build_entry(
        company="Copasa",
        mvp_group="Utilities e Infraestrutura",
        internal_sector="water_sanitation",
        b3_sector="Utilidade Pública",
        b3_subsector="Água e Saneamento",
        b3_segment="Água e Saneamento",
        business_description=(
            "Empresa de saneamento com atuação regional, exposição a tarifas, regulação, investimentos e custo de capital."
        ),
        revenue_profile={
            "currency": "brl",
            "geography": "brazil",
            "commodity_linked": False,
            "regulated": True,
        },
        company_characteristics=[
            "saneamento",
            "receita regulada",
            "sensível a juros",
            "exposição a regulação e investimentos",
        ],
        rationale=(
            "Copasa é uma utility de saneamento com receitas reguladas e necessidade relevante de investimento. Juros menores "
            "favorecem ativos de duration longa e reduzem custo de capital, enquanto risco regulatório, fiscal ou atraso tarifário "
            "podem prejudicar a tese."
        ),
        confidence="high",
        scores={
            "selic_up": -2,
            "selic_down": 2,
            "long_rates_up": -2,
            "long_rates_down": 2,
            "inflation_up": 1,
            "inflation_down": -1,
            "domestic_growth_up": 1,
            "domestic_growth_down": -1,
            "global_risk_off": -1,
            "fiscal_risk_up": -2,
            "fiscal_risk_down": 1,
            "regulatory_risk_up": -3,
            "regulatory_risk_down": 2,
        },
    ),

    "BRFS3": build_entry(
        company="BRF",
        mvp_group="Varejo e Consumo",
        internal_sector="proteins_food_exports",
        b3_sector="Consumo não Cíclico",
        b3_subsector="Alimentos Processados",
        b3_segment="Carnes e Derivados",
        business_description=(
            "Empresa de alimentos e proteínas com exposição a exportações, câmbio, grãos, demanda doméstica e demanda global por alimentos."
        ),
        revenue_profile={
            "currency": "mixed",
            "geography": "brazil_and_exports",
            "commodity_linked": True,
            "regulated": False,
        },
        company_characteristics=[
            "proteínas e alimentos processados",
            "exposição a exportações",
            "custos ligados a grãos",
            "sensível a câmbio e demanda global",
        ],
        rationale=(
            "BRF possui exposição a proteínas, câmbio, demanda doméstica e exportações, mas também é impactada por custos de grãos "
            "e ciclo operacional. Real depreciado pode favorecer exportações, enquanto alta de insumos e desaceleração de consumo "
            "podem pressionar margens."
        ),
        confidence="medium",
        scores={
            "selic_up": -1,
            "selic_down": 1,
            "inflation_up": -2,
            "inflation_down": 1,
            "brl_appreciation": -1,
            "brl_depreciation": 2,
            "domestic_growth_up": 1,
            "domestic_growth_down": -2,
            "unemployment_up": -1,
            "unemployment_down": 1,
            "china_growth_up": 1,
            "china_growth_down": -1,
            "global_risk_on": 1,
            "global_risk_off": -2,
            "fiscal_risk_up": -1,
            "regulatory_risk_up": -1,
        },
    ),

    "BRKM5": build_entry(
        company="Braskem",
        mvp_group="Mineração e Siderurgia",
        internal_sector="petrochemicals",
        b3_sector="Materiais Básicos",
        b3_subsector="Químicos",
        b3_segment="Petroquímicos",
        business_description=(
            "Petroquímica com exposição a spreads internacionais, petróleo/nafta, câmbio, ciclo industrial e riscos idiossincráticos."
        ),
        revenue_profile={
            "currency": "mixed",
            "geography": "brazil_and_exports",
            "commodity_linked": True,
            "regulated": False,
        },
        company_characteristics=[
            "petroquímica",
            "exposição a spreads internacionais",
            "sensível ao ciclo industrial",
            "risco idiossincrático relevante",
        ],
        rationale=(
            "Braskem é sensível a spreads petroquímicos, petróleo/nafta, câmbio e ciclo industrial global. A relação macro é relevante, "
            "mas tem baixa previsibilidade por causa de fatores específicos da empresa, alavancagem e riscos extraordinários."
        ),
        confidence="low",
        scores={
            "selic_up": -2,
            "selic_down": 1,
            "long_rates_up": -2,
            "long_rates_down": 1,
            "brl_appreciation": -1,
            "brl_depreciation": 1,
            "domestic_growth_up": 1,
            "domestic_growth_down": -2,
            "oil_price_up": -1,
            "oil_price_down": 1,
            "china_growth_up": 2,
            "china_growth_down": -2,
            "global_risk_on": 2,
            "global_risk_off": -2,
            "fiscal_risk_up": -1,
            "regulatory_risk_up": -2,
        },
    ),

    "BRAV3": build_entry(
        company="Brava Energia",
        mvp_group="Óleo e Gás",
        internal_sector="oil_gas_independent_e_and_p",
        b3_sector="Petróleo, Gás e Biocombustíveis",
        b3_subsector="Petróleo, Gás e Biocombustíveis",
        b3_segment="Exploração, Refino e Distribuição",
        business_description=(
            "Companhia independente de exploração e produção de óleo e gás, com exposição direta ao Brent, câmbio e execução operacional."
        ),
        revenue_profile={
            "currency": "mostly_usd",
            "geography": "brazil",
            "commodity_linked": True,
            "regulated": True,
        },
        company_characteristics=[
            "exploração e produção de petróleo",
            "exposição ao Brent",
            "receita ligada a commodity",
            "sensível a execução operacional",
        ],
        rationale=(
            "Brava Energia possui exposição direta a preço do petróleo, câmbio e produção. Petróleo em alta e real depreciado tendem "
            "a favorecer receitas, enquanto queda do Brent, risco regulatório e aversão a risco prejudicam a tese."
        ),
        confidence="high",
        scores={
            "selic_up": -1,
            "selic_down": 1,
            "long_rates_up": -1,
            "long_rates_down": 1,
            "brl_appreciation": -1,
            "brl_depreciation": 2,
            "domestic_growth_down": -1,
            "oil_price_up": 3,
            "oil_price_down": -3,
            "global_risk_on": 1,
            "global_risk_off": -2,
            "fiscal_risk_up": -1,
            "regulatory_risk_up": -2,
            "regulatory_risk_down": 1,
        },
    ),

    "CURY3": build_entry(
        company="Cury",
        mvp_group="Construção, Imóveis e Shoppings",
        internal_sector="low_income_homebuilders",
        b3_sector="Consumo Cíclico",
        b3_subsector="Construção Civil",
        b3_segment="Incorporações",
        business_description=(
            "Incorporadora residencial com foco em baixa renda, exposta a crédito habitacional, renda das famílias, juros e programas habitacionais."
        ),
        revenue_profile={
            "currency": "brl",
            "geography": "brazil",
            "commodity_linked": False,
            "regulated": False,
        },
        company_characteristics=[
            "incorporadora de baixa renda",
            "sensível a crédito habitacional",
            "exposição a programas habitacionais",
            "dependente de renda e emprego",
        ],
        rationale=(
            "Cury é sensível ao ciclo imobiliário de baixa renda, crédito habitacional, subsídios e renda das famílias. Juros menores "
            "e expansão do crédito tendem a favorecer vendas e lançamentos, enquanto juros altos e desemprego pressionam demanda."
        ),
        confidence="high",
        scores={
            "selic_up": -3,
            "selic_down": 3,
            "long_rates_up": -3,
            "long_rates_down": 3,
            "inflation_up": -1,
            "inflation_down": 1,
            "domestic_growth_up": 2,
            "domestic_growth_down": -2,
            "unemployment_up": -2,
            "unemployment_down": 2,
            "credit_growth_up": 3,
            "credit_growth_down": -3,
            "global_risk_on": 1,
            "global_risk_off": -1,
            "fiscal_risk_up": -1,
        },
    ),

    # -------------------------------------------------------------------------
    # Tickers adicionais pedidos agora
    # -------------------------------------------------------------------------
    "NTCO3": build_entry(
        company="Natura",
        mvp_group="Varejo e Consumo",
        internal_sector="beauty_personal_care",
        b3_sector="Consumo não Cíclico",
        b3_subsector="Produtos de Uso Pessoal e de Limpeza",
        b3_segment="Produtos de Uso Pessoal",
        business_description=(
            "Empresa de cosméticos e produtos de beleza, com exposição a consumo, renda doméstica, câmbio, canais de venda e mercados internacionais."
        ),
        revenue_profile={
            "currency": "mixed",
            "geography": "brazil_and_international",
            "commodity_linked": False,
            "regulated": False,
        },
        company_characteristics=[
            "cosméticos e beleza",
            "exposição a consumo",
            "operação internacional",
            "sensível a câmbio e renda",
        ],
        rationale=(
            "Natura é sensível a consumo, renda disponível, câmbio e execução em mercados internacionais. Melhora de atividade e renda "
            "tende a favorecer vendas, enquanto inflação, câmbio adverso, juros altos e desaceleração do consumo pressionam margens e valuation."
        ),
        confidence="medium",
        scores={
            "selic_up": -2,
            "selic_down": 2,
            "long_rates_up": -2,
            "long_rates_down": 2,
            "inflation_up": -2,
            "inflation_down": 1,
            "brl_appreciation": 1,
            "brl_depreciation": -1,
            "domestic_growth_up": 2,
            "domestic_growth_down": -2,
            "unemployment_up": -2,
            "unemployment_down": 2,
            "credit_growth_up": 1,
            "credit_growth_down": -1,
            "global_risk_on": 1,
            "global_risk_off": -2,
            "fiscal_risk_up": -1,
        },
    ),

    "JBSS3": build_entry(
        company="JBS",
        mvp_group="Varejo e Consumo",
        internal_sector="proteins_food_exports",
        b3_sector="Consumo não Cíclico",
        b3_subsector="Alimentos Processados",
        b3_segment="Carnes e Derivados",
        business_description=(
            "Empresa global de proteínas com exposição a exportações, câmbio, ciclo global de carnes, grãos, demanda doméstica e mercados internacionais."
        ),
        revenue_profile={
            "currency": "mostly_usd",
            "geography": "global",
            "commodity_linked": True,
            "regulated": False,
        },
        company_characteristics=[
            "proteínas globais",
            "receita internacional",
            "exposição a câmbio",
            "custos ligados a grãos e gado",
        ],
        rationale=(
            "JBS tem forte exposição global e receita dolarizada, sendo beneficiada por real depreciado e demanda externa por proteínas. "
            "A tese pode ser prejudicada por alta de insumos, restrições sanitárias, desaceleração global ou aversão a risco."
        ),
        confidence="medium",
        scores={
            "selic_up": -1,
            "selic_down": 1,
            "inflation_up": -1,
            "inflation_down": 1,
            "brl_appreciation": -2,
            "brl_depreciation": 3,
            "domestic_growth_up": 1,
            "domestic_growth_down": -1,
            "china_growth_up": 2,
            "china_growth_down": -2,
            "global_risk_on": 1,
            "global_risk_off": -2,
            "fiscal_risk_up": -1,
            "regulatory_risk_up": -1,
        },
    ),

    "BEEF3": build_entry(
        company="Minerva",
        mvp_group="Varejo e Consumo",
        internal_sector="proteins_food_exports",
        b3_sector="Consumo não Cíclico",
        b3_subsector="Alimentos Processados",
        b3_segment="Carnes e Derivados",
        business_description=(
            "Empresa de carne bovina com forte exposição a exportações, câmbio, ciclo do boi, demanda internacional e custos agropecuários."
        ),
        revenue_profile={
            "currency": "mostly_usd",
            "geography": "brazil_and_exports",
            "commodity_linked": True,
            "regulated": False,
        },
        company_characteristics=[
            "proteína bovina",
            "exportadora",
            "sensível ao câmbio",
            "exposição a ciclo do boi",
        ],
        rationale=(
            "Minerva é beneficiada por real depreciado e demanda externa por carne bovina, mas sofre com alta do boi, barreiras sanitárias, "
            "desaceleração global e aversão a risco. A exposição macro é clara, mas margens dependem muito de spreads operacionais."
        ),
        confidence="medium",
        scores={
            "selic_up": -1,
            "selic_down": 1,
            "inflation_up": -1,
            "inflation_down": 1,
            "brl_appreciation": -2,
            "brl_depreciation": 3,
            "domestic_growth_up": 1,
            "domestic_growth_down": -1,
            "china_growth_up": 2,
            "china_growth_down": -2,
            "global_risk_on": 1,
            "global_risk_off": -2,
            "fiscal_risk_up": -1,
            "regulatory_risk_up": -1,
        },
    ),

    "HYPE3": build_entry(
        company="Hypera",
        mvp_group="Saúde e Educação",
        internal_sector="pharmaceuticals",
        b3_sector="Saúde",
        b3_subsector="Medicamentos e Outros Produtos",
        b3_segment="Medicamentos e Outros Produtos",
        business_description=(
            "Empresa farmacêutica com portfólio de medicamentos e produtos de saúde, exposta a consumo defensivo, inflação, renda e regulação."
        ),
        revenue_profile={
            "currency": "brl",
            "geography": "brazil",
            "commodity_linked": False,
            "regulated": True,
        },
        company_characteristics=[
            "farmacêutica",
            "consumo defensivo",
            "exposição a regulação de medicamentos",
            "sensível a juros via alavancagem/valuation",
        ],
        rationale=(
            "Hypera tem perfil relativamente defensivo por atuar em medicamentos, mas é afetada por inflação, regulação de preços, renda doméstica "
            "e custo de capital. Em cenários de desaceleração, tende a ser mais resiliente que consumo discricionário."
        ),
        confidence="medium",
        scores={
            "selic_up": -1,
            "selic_down": 1,
            "long_rates_up": -1,
            "long_rates_down": 1,
            "inflation_up": -1,
            "inflation_down": 2,
            "domestic_growth_up": 1,
            "domestic_growth_down": -1,
            "unemployment_up": -1,
            "unemployment_down": 1,
            "global_risk_off": -1,
            "fiscal_risk_up": -1,
            "regulatory_risk_up": -2,
            "regulatory_risk_down": 1,
        },
    ),

    "SIMH3": build_entry(
        company="Simpar",
        mvp_group="Transporte, Telecom e Tecnologia",
        internal_sector="logistics_mobility_holding",
        b3_sector="Bens Industriais",
        b3_subsector="Transporte",
        b3_segment="Transporte Rodoviário",
        business_description=(
            "Holding de logística, locação, mobilidade e serviços, com exposição a juros, alavancagem, atividade doméstica e demanda corporativa."
        ),
        revenue_profile={
            "currency": "brl",
            "geography": "brazil",
            "commodity_linked": False,
            "regulated": False,
        },
        company_characteristics=[
            "holding de mobilidade e logística",
            "empresa alavancada",
            "sensível a juros",
            "exposição a atividade doméstica",
        ],
        rationale=(
            "Simpar é altamente sensível a juros, custo de dívida, atividade doméstica e demanda por logística/mobilidade. Queda de juros e melhora "
            "da economia tendem a favorecer a tese, enquanto juros altos e crédito apertado pressionam alavancagem e valuation."
        ),
        confidence="medium",
        scores={
            "selic_up": -3,
            "selic_down": 3,
            "long_rates_up": -3,
            "long_rates_down": 3,
            "inflation_up": -1,
            "inflation_down": 1,
            "domestic_growth_up": 2,
            "domestic_growth_down": -2,
            "unemployment_up": -1,
            "unemployment_down": 1,
            "credit_growth_up": 2,
            "credit_growth_down": -3,
            "global_risk_on": 1,
            "global_risk_off": -2,
            "fiscal_risk_up": -2,
        },
    ),

    "CCRO3": build_entry(
        company="CCR",
        mvp_group="Transporte, Telecom e Tecnologia",
        internal_sector="transport_infrastructure_concessions",
        b3_sector="Bens Industriais",
        b3_subsector="Transporte",
        b3_segment="Exploração de Rodovias",
        business_description=(
            "Operadora de concessões de infraestrutura de transporte, incluindo rodovias, mobilidade urbana e aeroportos."
        ),
        revenue_profile={
            "currency": "brl",
            "geography": "brazil",
            "commodity_linked": False,
            "regulated": True,
        },
        company_characteristics=[
            "concessões de infraestrutura",
            "receita regulada/contratada",
            "sensível a juros",
            "exposição a tráfego e atividade econômica",
        ],
        rationale=(
            "CCR combina exposição a tráfego, atividade econômica, contratos de concessão, inflação tarifária e custo de capital. Juros menores "
            "favorecem ativos de infraestrutura de duration longa, enquanto risco regulatório, fiscal e desaceleração reduzem atratividade da tese."
        ),
        confidence="high",
        scores={
            "selic_up": -2,
            "selic_down": 2,
            "long_rates_up": -3,
            "long_rates_down": 3,
            "inflation_up": 1,
            "inflation_down": -1,
            "domestic_growth_up": 2,
            "domestic_growth_down": -2,
            "unemployment_up": -1,
            "unemployment_down": 1,
            "global_risk_on": 1,
            "global_risk_off": -1,
            "fiscal_risk_up": -2,
            "fiscal_risk_down": 1,
            "regulatory_risk_up": -3,
            "regulatory_risk_down": 2,
        },
    ),
}


AIRLINE_ENTRIES: dict[str, dict[str, Any]] = {
    "AZUL3": build_entry(
        company="Azul",
        mvp_group="Transporte, Telecom e Tecnologia",
        internal_sector="airlines",
        b3_sector="Bens Industriais",
        b3_subsector="Transporte",
        b3_segment="Transporte Aéreo",
        business_description=(
            "Companhia aérea brasileira com exposição a demanda doméstica, câmbio, combustível, leasing, turismo e atividade econômica."
        ),
        revenue_profile={
            "currency": "brl",
            "geography": "brazil",
            "commodity_linked": False,
            "regulated": True,
        },
        company_characteristics=[
            "companhia aérea",
            "custos relevantes dolarizados",
            "sensível a petróleo/combustível",
            "exposição a demanda doméstica",
        ],
        rationale=(
            "Azul é sensível a atividade doméstica, demanda por viagens, câmbio e combustível. Real depreciado e petróleo em alta prejudicam custos, "
            "enquanto crescimento doméstico, real forte e petróleo em queda tendem a favorecer margens e demanda."
        ),
        confidence="high",
        scores={
            "selic_up": -2,
            "selic_down": 2,
            "long_rates_up": -2,
            "long_rates_down": 2,
            "inflation_up": -2,
            "inflation_down": 1,
            "brl_appreciation": 3,
            "brl_depreciation": -3,
            "domestic_growth_up": 3,
            "domestic_growth_down": -3,
            "unemployment_up": -2,
            "unemployment_down": 2,
            "credit_growth_up": 1,
            "credit_growth_down": -1,
            "oil_price_up": -3,
            "oil_price_down": 3,
            "global_risk_on": 1,
            "global_risk_off": -2,
            "fiscal_risk_up": -1,
            "regulatory_risk_up": -1,
        },
    ),

    "AZUL4": build_entry(
        company="Azul",
        mvp_group="Transporte, Telecom e Tecnologia",
        internal_sector="airlines",
        b3_sector="Bens Industriais",
        b3_subsector="Transporte",
        b3_segment="Transporte Aéreo",
        business_description=(
            "Companhia aérea brasileira com exposição a demanda doméstica, câmbio, combustível, leasing, turismo e atividade econômica. "
            "Ticker mantido como opção legada; verificar se ainda está presente na base B3/COTAHIST."
        ),
        revenue_profile={
            "currency": "brl",
            "geography": "brazil",
            "commodity_linked": False,
            "regulated": True,
        },
        company_characteristics=[
            "companhia aérea",
            "custos relevantes dolarizados",
            "sensível a petróleo/combustível",
            "exposição a demanda doméstica",
            "ticker legado a validar",
        ],
        rationale=(
            "Azul é sensível a atividade doméstica, demanda por viagens, câmbio e combustível. Real depreciado e petróleo em alta prejudicam custos, "
            "enquanto crescimento doméstico, real forte e petróleo em queda tendem a favorecer margens e demanda."
        ),
        confidence="high",
        scores={
            "selic_up": -2,
            "selic_down": 2,
            "long_rates_up": -2,
            "long_rates_down": 2,
            "inflation_up": -2,
            "inflation_down": 1,
            "brl_appreciation": 3,
            "brl_depreciation": -3,
            "domestic_growth_up": 3,
            "domestic_growth_down": -3,
            "unemployment_up": -2,
            "unemployment_down": 2,
            "oil_price_up": -3,
            "oil_price_down": 3,
            "global_risk_off": -2,
            "fiscal_risk_up": -1,
            "regulatory_risk_up": -1,
        },
    ),

    "GOLL4": build_entry(
        company="Gol",
        mvp_group="Transporte, Telecom e Tecnologia",
        internal_sector="airlines",
        b3_sector="Bens Industriais",
        b3_subsector="Transporte",
        b3_segment="Transporte Aéreo",
        business_description=(
            "Companhia aérea brasileira com exposição a demanda doméstica, câmbio, combustível e alavancagem. "
            "Ticker com alto ruído societário; usar apenas se aparecer validamente na base B3/COTAHIST."
        ),
        revenue_profile={
            "currency": "brl",
            "geography": "brazil",
            "commodity_linked": False,
            "regulated": True,
        },
        company_characteristics=[
            "companhia aérea",
            "custos dolarizados",
            "sensível a petróleo/combustível",
            "alto risco idiossincrático",
            "ticker a validar",
        ],
        rationale=(
            "Gol é sensível a demanda doméstica, câmbio, combustível e estrutura de capital. Embora a exposição macro seja clara, "
            "a tese possui alto ruído idiossincrático por eventos societários e financeiros, exigindo validação antes de uso no MVP."
        ),
        confidence="low",
        scores={
            "selic_up": -2,
            "selic_down": 2,
            "long_rates_up": -2,
            "long_rates_down": 2,
            "inflation_up": -2,
            "inflation_down": 1,
            "brl_appreciation": 3,
            "brl_depreciation": -3,
            "domestic_growth_up": 3,
            "domestic_growth_down": -3,
            "unemployment_up": -2,
            "unemployment_down": 2,
            "oil_price_up": -3,
            "oil_price_down": 3,
            "global_risk_off": -3,
            "fiscal_risk_up": -1,
            "regulatory_risk_up": -1,
        },
    ),
}


def load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as file:
        return yaml.safe_load(file)


def save_yaml(data: dict[str, Any], path: Path) -> None:
    with path.open("w", encoding="utf-8") as file:
        yaml.safe_dump(
            data,
            file,
            allow_unicode=True,
            sort_keys=False,
            default_flow_style=False,
            width=120,
        )


def validate_new_tickers(data: dict[str, Any]) -> list[str]:
    issues: list[str] = []

    for ticker, info in data.items():
        scores = info.get("exposure_scores", {})

        missing = [factor for factor in MACRO_FACTORS if factor not in scores]
        extra = [factor for factor in scores if factor not in MACRO_FACTORS]

        if missing:
            issues.append(f"{ticker}: fatores ausentes em exposure_scores: {missing}")
        if extra:
            issues.append(f"{ticker}: fatores extras em exposure_scores: {extra}")

        for factor, score in scores.items():
            if not isinstance(score, int) or score < -3 or score > 3:
                issues.append(f"{ticker}: score inválido em {factor}: {score}")

        if info.get("confidence") not in {"high", "medium", "low"}:
            issues.append(f"{ticker}: confidence inválido: {info.get('confidence')}")

        if not info.get("positive_exposures"):
            issues.append(f"{ticker}: positive_exposures vazio")

        if not info.get("negative_exposures"):
            issues.append(f"{ticker}: negative_exposures vazio")

    return issues


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()

    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)

    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Se ativado, sobrescreve tickers já existentes. Por padrão, preserva os existentes.",
    )

    parser.add_argument(
        "--airline",
        choices=sorted(AIRLINE_ENTRIES.keys()),
        default=AIRLINE_TICKER,
        help="Escolhe qual ticker de aérea adicionar. Recomendado: AZUL3.",
    )

    parser.add_argument(
        "--skip-airline",
        action="store_true",
        help="Não adiciona nenhuma aérea.",
    )

    return parser.parse_args()


def main() -> None:
    args = parse_args()

    data = load_yaml(args.input)

    tickers_to_add = dict(NEW_TICKERS)

    if not args.skip_airline:
        tickers_to_add[args.airline] = AIRLINE_ENTRIES[args.airline]

    issues = validate_new_tickers(tickers_to_add)
    if issues:
        raise ValueError("Problemas encontrados nos novos tickers:\n" + "\n".join(issues))

    added = []
    skipped = []

    for ticker, info in tickers_to_add.items():
        if ticker in data and not args.overwrite:
            skipped.append(ticker)
            continue

        data[ticker] = info
        added.append(ticker)

    save_yaml(data, args.output)

    print(f"Arquivo original: {args.input}")
    print(f"Arquivo expandido: {args.output}")
    print(f"Tickers adicionados: {len(added)}")
    print(f"Tickers ignorados porque já existiam: {len(skipped)}")
    print(f"Total final de tickers: {len(data)}")

    if added:
        print("\nAdicionados:")
        for ticker in added:
            print(f"- {ticker}")

    if skipped:
        print("\nIgnorados:")
        for ticker in skipped:
            print(f"- {ticker}")

    print("\nPróximo passo:")
    print("1. Cruzar os novos tickers contra B3/COTAHIST para verificar presença e liquidez.")
    print("2. Revisar manualmente os scores marcados como needs_review.")
    print("3. Rodar o validador geral da base.")
    print("4. Quando aprovado, renomear o output para ticker_exposures_curated.yaml.")


if __name__ == "__main__":
    main()
