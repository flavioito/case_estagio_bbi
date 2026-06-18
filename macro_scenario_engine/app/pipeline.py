from __future__ import annotations

import json
import logging
import re
import unicodedata
from datetime import UTC, datetime
from pathlib import Path

from pydantic import ValidationError

from app.config import Settings, load_settings
from app.llm_client import AnthropicLLMClient, LLMClientError
from app.schemas import AnalysisMetadata, AnalysisOutput, RiskItem, SectorImpact, TickerImpact
from app.scoring import (
    DataCatalog,
    ScoredSector,
    ScoredTicker,
    calculate_sector_scores,
    calculate_ticker_scores,
    load_catalog,
    select_horizon_sector_rankings,
    select_top_sectors,
    select_top_tickers,
)
from app.validators import (
    OutputValidationError,
    validate_input_scenario,
    validate_known_factors,
    validate_universe,
)

logger = logging.getLogger(__name__)


FACTOR_PATTERNS: list[tuple[str, list[str]]] = [
    ("selic_down", [r"selic[^,.]{0,40}(queda|cai|caindo|reduz)", r"queda da selic", r"reduzindo a selic", r"corte[s]? de juros", r"ciclo de queda de juros", r"juros (menores|em queda|baixos|caindo)", r"afrouxamento monetario"]),
    ("selic_up", [r"selic[^,.]{0,40}alta", r"alta da selic", r"juros (altos|em alta|subindo)", r"juros altos por mais tempo", r"aperto monetario"]),
    ("long_rates_down", [r"juros longos[^,.]{0,40}queda", r"taxas longas[^,.]{0,40}queda", r"curva de juros[^,.]{0,60}(fechando|queda)"]),
    ("long_rates_up", [r"juros longos[^,.]{0,40}(alta|sobem|sobendo|subindo|elevad)", r"taxas longas[^,.]{0,40}(alta|sobem|sobendo|subindo|elevad)", r"curva de juros[^,.]{0,60}(abrindo|alta|abre)", r"premios longos[^,.]{0,40}pression", r"juros altos por mais tempo"]),
    ("inflation_down", [r"inflacao (controlada|menor|baixa|cedendo)", r"inflacao[^,.]{0,60}converg", r"ipca (baixo|menor|cedendo)", r"queda da inflacao", r"desinflacao"]),
    ("inflation_up", [r"inflacao (alta|elevada|pressionada|persistente|reacelerando)", r"inflacao[^,.]{0,60}(alta|elevada|pressionada|persistente|desancorad|sobe|sobem|subindo|acelera|acelerando)", r"expectativas[^,.]{0,40}desancorad", r"acelerando a inflacao", r"inflacao de servicos.*persistente", r"ipca (alto|elevado|pressionado)", r"pressao inflacionaria"]),
    ("brl_appreciation", [r"real (forte|apreciad)", r"brl (forte|apreciad)", r"dolar (fraco|em queda|caindo)", r"cambio apreciad"]),
    ("brl_depreciation", [r"real (fraco|depreciad)", r"real[^,.]{0,40}(deprecia|depreciando)", r"brl (fraco|depreciad)", r"dolar (forte|em alta|subindo)", r"cambio depreciad"]),
    ("domestic_growth_up", [r"atividade domestica[^,.]{0,60}(melhor|(?<!des)aceler)", r"crescimento domestico[^,.]{0,60}(melhor|(?<!des)aceler|forte)", r"pib[^,.]{0,40}((?<!des)aceler|forte|melhor)", r"demanda domestica[^,.]{0,40}forte"]),
    ("domestic_growth_down", [r"atividade domestica[^,.]{0,60}(fraca|perdendo tracao|desaceler)", r"desaceleracao da atividade domestica", r"crescimento domestico[^,.]{0,60}(fraco|desaceler)", r"pib[^,.]{0,40}(fraco|desaceler)", r"recessao", r"demanda domestica[^,.]{0,40}fraca"]),
    ("unemployment_down", [r"desemprego[^,.]{0,40}queda", r"emprego (forte|melhor)", r"mercado de trabalho[^,.]{0,60}(forte|aquecido)"]),
    ("unemployment_up", [r"desemprego[^,.]{0,40}alta", r"emprego[^,.]{0,40}fraco", r"mercado de trabalho[^,.]{0,60}(fraco|deterior|piora|piorando)", r"piora do mercado de trabalho"]),
    ("credit_growth_up", [r"credito[^,.]{0,60}(crescendo|expansao|retomando|forte)", r"expansao do credito", r"credito voltando a crescer"]),
    ("credit_growth_down", [r"credito[^,.]{0,60}(contraindo|restrito|fraco|apertado)", r"contracao do credito", r"restricao de credito"]),
    ("oil_price_up", [r"petroleo[^,.]{0,40}(alta|forte|sobe|sobem|subindo|caro|elevad)", r"brent[^,.]{0,40}(alta|forte|sobe|sobem|subindo|elevad)", r"oil[^,.]{0,20}up", r"commodities[^,.]{0,40}alta"]),
    ("oil_price_down", [r"petroleo[^,.]{0,40}(queda|cai|caindo|fraco)", r"brent[^,.]{0,40}(queda|cai|caindo|fraco)", r"oil[^,.]{0,20}down", r"commodities[^,.]{0,40}queda"]),
    ("iron_ore_up", [r"minerio[^,.]{0,40}(alta|forte|subindo)", r"iron ore[^,.]{0,20}up", r"commodities[^,.]{0,40}alta"]),
    ("iron_ore_down", [r"minerio[^,.]{0,80}(queda|cai|caindo|fraco|enfraquec)", r"demanda por minerio[^.]{0,120}(queda|enfraquec)", r"commodities metalicas[^,.]{0,80}(queda|enfraquec)", r"iron ore[^,.]{0,20}down", r"commodities[^,.]{0,40}queda"]),
    ("china_growth_up", [r"china[^,.]{0,60}((?<!des)aceler|forte|melhor|crescendo)", r"demanda chinesa[^,.]{0,40}(forte|melhor)"]),
    ("china_growth_down", [r"china[^,.]{0,60}(fraca|desaceler|pior|queda)", r"economia chinesa[^,.]{0,80}(fraca|desaceler|pior|queda)", r"demanda chinesa[^,.]{0,40}(fraca|pior|queda|enfraquec)"]),
    ("global_risk_on", [r"risk[- ]?on", r"apetite global[^,.]{0,40}risco", r"ambiente externo[^,.]{0,60}favoravel", r"emergentes[^,.]{0,60}favoravel", r"fluxo[^,.]{0,40}emergentes"]),
    ("global_risk_off", [r"risk[- ]?off", r"aversao[^,.]{0,40}risco", r"ambiente externo[^,.]{0,60}desfavoravel", r"emergentes[^,.]{0,40}press", r"saida de capital", r"percepcao de risco", r"dolar global forte"]),
    ("fiscal_risk_down", [r"risco fiscal[^,.]{0,40}(queda|menor|baixo|melhor)", r"fiscal[^,.]{0,40}(melhor|ancorad|favoravel)"]),
    ("fiscal_risk_up", [r"risco fiscal[^,.]{0,40}(alta|elevado|maior|pior)", r"fiscal[^,.]{0,60}(pior|deterior|pressionado|expansao|expansionista|flexibilizacao)", r"expansao fiscal", r"metas fiscais[^,.]{0,40}flexibil", r"duvidas[^,.]{0,80}fiscal", r"sustentabilidade fiscal", r"trajetoria da divida"]),
    ("regulatory_risk_down", [r"risco regulatorio[^,.]{0,40}(queda|menor|baixo|melhor)", r"regulacao[^,.]{0,40}(favoravel|melhor)"]),
    ("regulatory_risk_up", [r"risco regulatorio[^,.]{0,40}(alta|elevado|maior|pior)", r"regulacao[^,.]{0,40}(pior|incerta|adversa)"]),
]


def normalize_for_matching(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text.lower())
    without_accents = "".join(char for char in normalized if not unicodedata.combining(char))
    return re.sub(r"\s+", " ", without_accents)


def extract_macro_factors_heuristic(scenario: str, catalog: DataCatalog) -> list[str]:
    normalized = normalize_for_matching(scenario)
    factors: list[str] = []
    for factor, patterns in FACTOR_PATTERNS:
        if factor not in catalog.allowed_factors:
            continue
        if any(re.search(pattern, normalized) for pattern in patterns):
            factors.append(factor)
    return list(dict.fromkeys(factors))


def extract_macro_factors_with_llm(scenario: str, catalog: DataCatalog, settings: Settings) -> list[str]:
    client = AnthropicLLMClient(settings)
    allowed = "\n".join(f"- {factor}: {catalog.factor_label(factor)}" for factor in sorted(catalog.allowed_factors))
    system_prompt = _read_prompt(settings.prompts_dir / "system_prompt.md")
    macro_prompt = _read_prompt(settings.prompts_dir / "macro_parser.md")
    user_prompt = macro_prompt.format(macro_factor_list=allowed, scenario=scenario)
    parsed = client.complete_json(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        max_tokens=settings.parser_max_tokens,
    )

    if isinstance(parsed, list):
        return [str(item) for item in parsed]
    if isinstance(parsed, dict):
        values = parsed.get("macro_factors") or parsed.get("factors") or parsed.get("detected_factors") or []
        return [str(item) for item in values]
    raise LLMClientError("Formato inesperado no parser macroeconômico.")


def run_analysis(
    scenario: str,
    *,
    settings: Settings | None = None,
    use_llm: bool | None = None,
) -> AnalysisOutput:
    settings = settings or load_settings()
    catalog = load_catalog(
        macro_factors_path=settings.macro_factors_path,
        sector_taxonomy_path=settings.sector_taxonomy_path,
        ticker_exposures_path=settings.ticker_exposures_path,
    )

    cleaned_scenario = validate_input_scenario(scenario)
    should_use_llm = settings.use_llm_default if use_llm is None else use_llm
    used_llm = False

    factors: list[str] = []
    if should_use_llm:
        try:
            factors = extract_macro_factors_with_llm(cleaned_scenario, catalog, settings)
            used_llm = True
        except Exception as exc:
            logger.warning("Parser Claude indisponível; usando fallback heurístico. Motivo: %s", exc)

    if not factors:
        factors = extract_macro_factors_heuristic(cleaned_scenario, catalog)

    factors = validate_known_factors(factors, catalog.allowed_factors)

    sector_scores = calculate_sector_scores(factors, catalog)
    ticker_scores = calculate_ticker_scores(factors, catalog)
    benefited_sectors, harmed_sectors = select_top_sectors(sector_scores, settings.top_sectors)
    short_term_benefited_sectors, medium_term_harmed_sectors, net_resilient_sectors = select_horizon_sector_rankings(
        sector_scores,
        settings.top_sectors,
    )
    top_relative_tickers, negative_tickers = select_top_tickers(ticker_scores, settings.top_tickers)
    risks = build_risks(factors, catalog, settings.risk_count)
    scenario_summary = build_scenario_summary(factors, catalog)
    markdown_report = build_markdown_report(
        scenario_summary=scenario_summary,
        benefited_sectors=benefited_sectors,
        harmed_sectors=harmed_sectors,
        short_term_benefited_sectors=short_term_benefited_sectors,
        medium_term_harmed_sectors=medium_term_harmed_sectors,
        net_resilient_sectors=net_resilient_sectors,
        top_relative_tickers=top_relative_tickers,
        negative_tickers=negative_tickers,
        risks=risks,
    )
    if used_llm and settings.use_llm_report_writer:
        markdown_report = rewrite_report_with_llm(
            markdown_report=markdown_report,
            scenario_summary=scenario_summary,
            benefited_sectors=benefited_sectors,
            harmed_sectors=harmed_sectors,
            short_term_benefited_sectors=short_term_benefited_sectors,
            medium_term_harmed_sectors=medium_term_harmed_sectors,
            net_resilient_sectors=net_resilient_sectors,
            top_relative_tickers=top_relative_tickers,
            negative_tickers=negative_tickers,
            risks=risks,
            settings=settings,
        )

    try:
        output = AnalysisOutput(
            scenario=cleaned_scenario,
            scenario_summary=scenario_summary,
            macro_factors=factors,
            benefited_sectors=[sector_to_schema(item) for item in benefited_sectors],
            harmed_sectors=[sector_to_schema(item) for item in harmed_sectors],
            short_term_benefited_sectors=[sector_to_schema(item) for item in short_term_benefited_sectors],
            medium_term_harmed_sectors=[sector_to_schema(item) for item in medium_term_harmed_sectors],
            net_resilient_sectors=[sector_to_schema(item) for item in net_resilient_sectors],
            top_relative_tickers=[ticker_to_schema(item) for item in top_relative_tickers],
            negative_tickers=[ticker_to_schema(item) for item in negative_tickers],
            risks=risks,
            markdown_report=markdown_report,
            limitations=default_limitations(),
            metadata=AnalysisMetadata(
                generated_at=datetime.now(UTC),
                model_used=settings.anthropic_model if used_llm else "local-heuristic-parser",
                used_llm=used_llm,
                data_source=relative_to_project(settings.ticker_exposures_path, settings.project_root),
                factor_count=len(factors),
                ticker_universe_size=len(catalog.ticker_exposures),
            ),
        )
        validate_universe(
            output,
            allowed_sector_ids=catalog.allowed_sector_ids,
            allowed_tickers=catalog.allowed_tickers,
            allowed_factors=catalog.allowed_factors,
        )
        return output
    except ValidationError as exc:
        raise OutputValidationError(f"Falha de schema na saída final: {exc}") from exc


def sector_to_schema(item: ScoredSector) -> SectorImpact:
    return SectorImpact(
        sector_id=item.sector_id,
        sector_name=item.sector_name,
        score=item.score,
        raw_score=item.raw_score,
        relative_score=item.relative_score,
        short_term_score=item.short_term_score,
        medium_term_score=item.medium_term_score,
        impact_label=item.impact_label,
        matched_factors=item.matched_factors,
        rationale=item.rationale,
        confidence=item.confidence,
    )


def ticker_to_schema(item: ScoredTicker) -> TickerImpact:
    return TickerImpact(
        ticker=item.ticker,
        company=item.company,
        sector_id=item.sector_id,
        sector_name=item.sector_name,
        score=item.score,
        raw_score=item.raw_score,
        relative_score=item.relative_score,
        short_term_score=item.short_term_score,
        medium_term_score=item.medium_term_score,
        impact_label=item.impact_label,
        matched_positive_factors=item.matched_positive_factors,
        matched_negative_factors=item.matched_negative_factors,
        rationale=item.rationale,
        confidence=item.confidence,
    )


def build_scenario_summary(factors: list[str], catalog: DataCatalog) -> str:
    labels = [catalog.factor_label(factor) for factor in factors]
    if len(labels) == 1:
        factor_text = labels[0]
    else:
        factor_text = ", ".join(labels[:-1]) + " e " + labels[-1]
    return f"O cenário indica {factor_text}, com impactos diferenciados entre setores domésticos, exportadores e regulados."


def build_risks(factors: list[str], catalog: DataCatalog, limit: int = 3) -> list[RiskItem]:
    factor_set = set(factors)
    candidates: list[RiskItem] = []

    def related(*items: str) -> list[str]:
        return [item for item in items if item in factor_set]

    if related("selic_down", "selic_up", "long_rates_down", "long_rates_up", "inflation_down", "inflation_up"):
        candidates.append(
            RiskItem(
                risk="Reversão de inflação e juros",
                rationale=(
                    "Uma mudança na trajetória de inflação ou no tom do Banco Central pode alterar rapidamente "
                    "o custo de capital, o crédito e a atratividade relativa dos setores sensíveis a duration."
                ),
                related_factors=related("selic_down", "selic_up", "long_rates_down", "long_rates_up", "inflation_down", "inflation_up"),
            )
        )

    if related("credit_growth_up", "credit_growth_down"):
        candidates.append(
            RiskItem(
                risk="Crédito não se materializa",
                rationale=(
                    "Mesmo com juros menores, bancos podem manter concessão seletiva se inadimplência, spreads ou apetite "
                    "a risco não melhorarem. Isso reduziria o impulso esperado para varejo, construção e empresas dependentes "
                    "de financiamento ao consumidor."
                ),
                related_factors=related("credit_growth_up", "credit_growth_down", "selic_down", "selic_up"),
            )
        )

    if related("domestic_growth_up", "domestic_growth_down", "unemployment_down", "unemployment_up"):
        candidates.append(
            RiskItem(
                risk="Frustração do ciclo doméstico",
                rationale=(
                    "Se atividade e emprego não acompanharem a melhora esperada, a transmissão para renda disponível, "
                    "tráfego em lojas, lançamentos imobiliários e inadimplência pode ser mais fraca que o cenário sugere."
                ),
                related_factors=related(
                    "domestic_growth_up",
                    "domestic_growth_down",
                    "unemployment_down",
                    "unemployment_up",
                ),
            )
        )

    if related("brl_appreciation", "brl_depreciation"):
        candidates.append(
            RiskItem(
                risk="Reversão cambial",
                rationale=(
                    "Movimento oposto do câmbio mudaria a leitura entre exportadoras, empresas com custos dolarizados "
                    "e companhias domésticas dependentes de insumos importados."
                ),
                related_factors=related("brl_appreciation", "brl_depreciation"),
            )
        )

    if related("oil_price_up", "oil_price_down", "iron_ore_up", "iron_ore_down", "china_growth_up", "china_growth_down"):
        candidates.append(
            RiskItem(
                risk="Commodities e China",
                rationale=(
                    "Preços de petróleo, minério e demanda chinesa podem reprecificar rapidamente empresas exportadoras, "
                    "produtoras de commodities e setores que dependem de custo de energia ou frete."
                ),
                related_factors=related("oil_price_up", "oil_price_down", "iron_ore_up", "iron_ore_down", "china_growth_up", "china_growth_down"),
            )
        )

    if related("global_risk_on", "global_risk_off"):
        candidates.append(
            RiskItem(
                risk="Apetite global por risco",
                rationale=(
                    "Mudanças em liquidez externa, juros globais ou fluxo para emergentes podem afetar múltiplos, "
                    "câmbio e setores mais dependentes de mercado de capitais."
                ),
                related_factors=related("global_risk_on", "global_risk_off"),
            )
        )

    if related("fiscal_risk_up", "fiscal_risk_down", "regulatory_risk_up", "regulatory_risk_down"):
        candidates.append(
            RiskItem(
                risk="Risco fiscal, político e regulatório",
                rationale=(
                    "Deterioração fiscal, intervenção estatal ou mudança regulatória pode sobrepor o efeito macro base, "
                    "especialmente em bancos públicos, utilities, petróleo, saúde e educação."
                ),
                related_factors=related("fiscal_risk_up", "fiscal_risk_down", "regulatory_risk_up", "regulatory_risk_down"),
            )
        )

    fallbacks = [
        RiskItem(
            risk="Rotação setorial menor que o esperado",
            rationale=(
                "Mesmo que o cenário macro se confirme, fluxos de mercado podem permanecer concentrados em setores "
                "defensivos ou exportadores se investidores exigirem confirmação adicional de lucro e crescimento."
            ),
            related_factors=[],
        ),
        RiskItem(
            risk="Execução micro das companhias",
            rationale=(
                "Empresas sensíveis ao ciclo podem não capturar integralmente o cenário favorável se enfrentarem "
                "pressão competitiva, estoques elevados, custos acima do esperado ou execução operacional fraca."
            ),
            related_factors=[],
        ),
        RiskItem(
            risk="Relações macro podem mudar",
            rationale="Sensibilidades históricas e qualitativas podem perder validade diante de choques corporativos ou mudanças estruturais.",
            related_factors=[],
        ),
    ]

    candidates = sorted(candidates, key=lambda item: risk_priority(item, factor_set), reverse=True)
    for fallback in fallbacks:
        if len(candidates) >= limit:
            break
        candidates.append(fallback)
    return candidates[:limit]


def risk_priority(item: RiskItem, factor_set: set[str]) -> int:
    factor_weights = {
        "fiscal_risk_up": 30,
        "fiscal_risk_down": 22,
        "regulatory_risk_up": 20,
        "regulatory_risk_down": 12,
        "oil_price_up": 22,
        "oil_price_down": 18,
        "iron_ore_up": 20,
        "iron_ore_down": 20,
        "china_growth_up": 18,
        "china_growth_down": 22,
        "credit_growth_up": 20,
        "credit_growth_down": 20,
        "long_rates_up": 18,
        "long_rates_down": 14,
        "selic_up": 16,
        "selic_down": 16,
        "inflation_up": 16,
        "inflation_down": 14,
        "domestic_growth_up": 14,
        "domestic_growth_down": 16,
        "unemployment_up": 14,
        "unemployment_down": 12,
        "brl_depreciation": 14,
        "brl_appreciation": 12,
        "global_risk_off": 12,
        "global_risk_on": 10,
    }
    priority = sum(factor_weights.get(factor, 0) for factor in item.related_factors if factor in factor_set)
    if item.risk.startswith("Risco fiscal") and "fiscal_risk_up" in factor_set:
        priority += 20
    return priority


def build_markdown_report(
    *,
    scenario_summary: str,
    benefited_sectors: list[ScoredSector],
    harmed_sectors: list[ScoredSector],
    short_term_benefited_sectors: list[ScoredSector],
    medium_term_harmed_sectors: list[ScoredSector],
    net_resilient_sectors: list[ScoredSector],
    top_relative_tickers: list[ScoredTicker],
    negative_tickers: list[ScoredTicker],
    risks: list[RiskItem],
) -> str:
    benefited_heading = positive_or_resilient_heading(benefited_sectors, "Setores")
    harmed_heading = relative_or_negative_heading(harmed_sectors, "Setores")
    top_relative_ticker_heading = positive_or_resilient_heading(top_relative_tickers, "Tickers")
    negative_ticker_heading = relative_or_negative_heading(negative_tickers, "Tickers")
    benefited = ", ".join(score_label(item) for item in benefited_sectors)
    harmed = ", ".join(score_label(item) for item in harmed_sectors)
    top_relative = ", ".join(ticker_score_label(item) for item in top_relative_tickers)
    negative = ", ".join(ticker_score_label(item) for item in negative_tickers)
    horizon = build_horizon_summary(short_term_benefited_sectors, medium_term_harmed_sectors)
    risk_text = "; ".join(f"{item.risk}: {item.rationale}" for item in risks)

    return "\n\n".join(
        [
            "# Análise macro-setorial",
            f"**Cenário.** {scenario_summary}",
            f"**Horizonte.** {horizon}",
            f"**{benefited_heading}.** {benefited}.",
            f"**{harmed_heading}.** {harmed}.",
            f"**{top_relative_ticker_heading}.** {top_relative}.",
            f"**{negative_ticker_heading}.** {negative}.",
            f"**Riscos principais.** {risk_text}",
            (
                "**Limitação.** Esta é uma análise qualitativa de sensibilidade macro, não uma recomendação "
                "personalizada de investimento, preço-alvo ou garantia de retorno."
            ),
        ]
    )


def positive_or_resilient_heading(items: list[ScoredSector] | list[ScoredTicker], noun: str) -> str:
    if all(item.raw_score < 0 for item in items):
        return f"{noun} menos pressionados"
    if all(item.raw_score <= 0 for item in items):
        return f"{noun} neutros ou menos pressionados"
    if any(item.raw_score <= 0 for item in items):
        return f"{noun} com ganho absoluto ou resiliência"
    if noun == "Setores":
        return "Setores favorecidos"
    return "Tickers com exposição positiva"


def relative_or_negative_heading(items: list[ScoredSector] | list[ScoredTicker], noun: str) -> str:
    if all(item.raw_score >= 0 for item in items):
        return f"{noun} com menor exposição relativa"
    return f"{noun} pressionados"


def score_label(item: ScoredSector) -> str:
    return (
        f"{item.sector_name} (rel. {item.relative_score:+.1f}; abs. {item.raw_score:+.1f}; "
        f"curto {item.short_term_score:+.1f}; médio {item.medium_term_score:+.1f})"
    )


def ticker_score_label(item: ScoredTicker) -> str:
    return (
        f"{item.ticker} ({item.company}, rel. {item.relative_score:+.1f}; abs. {item.raw_score:+.1f}; "
        f"curto {item.short_term_score:+.1f}; médio {item.medium_term_score:+.1f})"
    )


def build_horizon_summary(
    short_term_benefited_sectors: list[ScoredSector],
    medium_term_harmed_sectors: list[ScoredSector],
) -> str:
    short_leaders = short_term_benefited_sectors[:3]
    medium_laggards = medium_term_harmed_sectors[:3]
    short_text = ", ".join(f"{item.sector_name} ({item.short_term_score:+.1f})" for item in short_leaders)
    medium_text = ", ".join(f"{item.sector_name} ({item.medium_term_score:+.1f})" for item in medium_laggards)
    if all(item.short_term_score > 0 for item in short_leaders):
        short_label = "maior impulso positivo"
    elif any(item.short_term_score > 0 for item in short_leaders):
        short_label = "melhor leitura relativa"
    else:
        short_label = "menor pressão imediata"
    medium_label = "maiores pontos de pressão" if any(item.medium_term_score < 0 for item in medium_laggards) else "menor impulso relativo"
    return (
        f"No curto prazo, os setores com {short_label} são {short_text}. "
        f"No médio prazo, os setores com {medium_label} são {medium_text}."
    )


def rewrite_report_with_llm(
    *,
    markdown_report: str,
    scenario_summary: str,
    benefited_sectors: list[ScoredSector],
    harmed_sectors: list[ScoredSector],
    short_term_benefited_sectors: list[ScoredSector],
    medium_term_harmed_sectors: list[ScoredSector],
    net_resilient_sectors: list[ScoredSector],
    top_relative_tickers: list[ScoredTicker],
    negative_tickers: list[ScoredTicker],
    risks: list[RiskItem],
    settings: Settings,
) -> str:
    try:
        client = AnthropicLLMClient(settings)
        if not client.available:
            return markdown_report

        system_prompt = _read_prompt(settings.prompts_dir / "system_prompt.md")
        report_prompt = _read_prompt(settings.prompts_dir / "report_writer.md")
        user_prompt = "\n\n".join(
            [
                report_prompt,
                "Dados estruturados para o relatório:",
                json.dumps(
                    {
                        "scenario_summary": scenario_summary,
                        "benefited_sectors": [sector_report_dict(item) for item in benefited_sectors],
                        "lower_relative_or_harmed_sectors": [sector_report_dict(item) for item in harmed_sectors],
                        "short_term_benefited_sectors": [
                            sector_report_dict(item) for item in short_term_benefited_sectors
                        ],
                        "medium_term_harmed_sectors": [
                            sector_report_dict(item) for item in medium_term_harmed_sectors
                        ],
                        "net_resilient_sectors": [sector_report_dict(item) for item in net_resilient_sectors],
                        "top_relative_tickers": [ticker_report_dict(item) for item in top_relative_tickers],
                        "lower_relative_or_negative_tickers": [ticker_report_dict(item) for item in negative_tickers],
                        "risks": [risk.model_dump(mode="json") for risk in risks],
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                (
                    "Escreva apenas o Markdown final. Se todos os itens da lista negativa tiverem raw_score positivo, "
                    "chame a seção de 'menor exposição relativa', não de exposição negativa."
                ),
            ]
        )
        rewritten = client.complete(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            max_tokens=settings.report_max_tokens,
        ).strip()
        if is_complete_markdown_report(rewritten, settings.report_max_words):
            return rewritten
    except Exception as exc:
        logger.warning("Report writer Claude indisponível; usando relatório determinístico. Motivo: %s", exc)
    return markdown_report


def is_complete_markdown_report(markdown_report: str, max_words: int) -> bool:
    text = markdown_report.strip()
    if not text:
        return False
    if len(text.split()) > max_words:
        return False
    if not text.endswith((".", "!", "?", "**")):
        return False

    lowered = normalize_for_matching(text)
    has_disclaimer = (
        "nao constitui recomendacao" in lowered
        or "nao e uma recomendacao" in lowered
        or "nao uma recomendacao" in lowered
    )
    if not has_disclaimer:
        return False

    last_line = text.splitlines()[-1].strip()
    if last_line.startswith("|") or last_line.endswith("|"):
        return False
    return True


def sector_report_dict(item: ScoredSector) -> dict:
    return {
        "sector_name": item.sector_name,
        "relative_score": item.relative_score,
        "raw_score": item.raw_score,
        "short_term_score": item.short_term_score,
        "medium_term_score": item.medium_term_score,
        "impact_label": item.impact_label,
        "rationale": item.rationale,
    }


def ticker_report_dict(item: ScoredTicker) -> dict:
    return {
        "ticker": item.ticker,
        "company": item.company,
        "sector_name": item.sector_name,
        "relative_score": item.relative_score,
        "raw_score": item.raw_score,
        "short_term_score": item.short_term_score,
        "medium_term_score": item.medium_term_score,
        "impact_label": item.impact_label,
        "rationale": item.rationale,
    }


def default_limitations() -> list[str]:
    return [
        "A ferramenta não fornece recomendação personalizada de investimento.",
        "A análise é qualitativa e baseada em uma matriz curada de sensibilidade macro.",
        "Não há cálculo de valuation, preço-alvo, múltiplos ou upside.",
        "O universo de tickers do MVP é limitado e deve ser revisado por analista humano.",
        "Eventos corporativos recentes podem não estar refletidos na base curada.",
    ]


def save_outputs(output: AnalysisOutput, output_dir: Path) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    json_path = output_dir / f"analysis_{timestamp}.json"
    md_path = output_dir / f"analysis_{timestamp}.md"
    json_path.write_text(json.dumps(output.as_json_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(output.markdown_report, encoding="utf-8")
    return json_path, md_path


def _read_prompt(path: Path) -> str:
    if path.exists():
        return path.read_text(encoding="utf-8")
    return ""


def relative_to_project(path: Path, project_root: Path) -> str:
    try:
        return str(path.relative_to(project_root)).replace("\\", "/")
    except ValueError:
        return str(path)
