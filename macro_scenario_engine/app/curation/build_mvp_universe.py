#!/usr/bin/env python3
"""
build_mvp_universe.py

Cria o universo operacional do MVP a partir de uma lista fixa de tickers definida
para o projeto, cruzando com os arquivos processados de B3, COTAHIST e CVM.

Entradas esperadas:
- data/processed/b3_classificacao_setorial_YYYYMMDD.csv
- data/processed/b3_liquidity_ranking_YYYY.csv
- data/processed/cvm_companies.csv

Saídas:
- data/curated/mvp_universe.csv
- data/curated/ticker_exposures_template.yaml
- data/curated/missing_tickers.csv, se algum ticker definido não for encontrado

Uso:
python app/curation/build_mvp_universe.py --processed-dir data/processed --curated-dir data/curated

Observação:
O campo internal_sector é criado como "TODO" para ser preenchido manualmente.
O campo mvp_group preserva o grupo definido manualmente pelo projeto.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Any

import pandas as pd
import yaml


# =============================================================================
# Universo fixo do MVP
# =============================================================================
# Este universo reduzido substitui a seleção automática por liquidez.
# A liquidez ainda é usada como dado de apoio, mas não decide sozinha a seleção.
# O grupo abaixo é apenas a categoria definida para o MVP; o campo internal_sector
# será criado como TODO para curadoria manual posterior.

MVP_TICKER_GROUPS: dict[str, list[str]] = {
    "Bancos e Financeiros": [
        "ITUB4",
        "BBDC4",
        "BBAS3",
        "SANB11",
        "BPAC11",
    ],
    "Óleo e Gás": [
        "PETR4",
        "PRIO3",
    ],
    "Mineração e Siderurgia": [
        "VALE3",
        "CSNA3",
        "GGBR4",
        "USIM5",
        "RECV3",
    ],
    "Papel e Celulose": [
        "SUZB3",
        "KLBN11",
    ],
    "Varejo e Consumo": [
        "LREN3",
        "MGLU3",
        "VIVA3",
        "AZZA3",
        "ASAI3",
        "GMAT3",
        "ABEV3",
    ],
    "Construção, Imóveis e Shoppings": [
        "CYRE3",
        "MRVE3",
        "EZTC3",
        "MULT3",
        "IGTI11",
    ],
    "Utilities e Infraestrutura": [
        "CMIG4",
        "EGIE3",
        "TAEE11",
        "CPFE3",
        "SBSP3",
        "ENEV3",
    ],
    "Saúde e Educação": [
        "RDOR3",
        "HAPV3",
        "FLRY3",
        "YDUQ3",
        "COGN3",
    ],
    "Transporte, Telecom e Tecnologia": [
        "EMBJ3",
        "RAIL3",
        "VIVT3",
        "TIMS3",
        "TOTS3",
    ],
}


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
# Utilidades gerais
# =============================================================================

def latest_file(directory: Path, pattern: str) -> Path:
    files = sorted(directory.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)

    if not files:
        raise FileNotFoundError(
            f"Nenhum arquivo encontrado em {directory} com padrão {pattern}"
        )

    return files[0]


def normalize_ticker(value: object) -> str | None:
    if pd.isna(value):
        return None

    ticker = str(value).strip().upper()

    if re.fullmatch(r"[A-Z]{4}[0-9]{1,2}", ticker):
        return ticker

    return None


def normalize_code(value: object) -> str | None:
    if pd.isna(value):
        return None

    value = str(value).strip()

    if value.endswith(".0"):
        value = value[:-2]

    value = re.sub(r"\D", "", value)

    return value or None


def first_non_null(*values: Any) -> Any:
    for value in values:
        if value is None:
            continue
        if pd.isna(value):
            continue
        value_str = str(value).strip()
        if value_str and value_str.lower() not in {"nan", "none", "null"}:
            return value
    return None


def build_fixed_universe_dataframe() -> pd.DataFrame:
    rows = []

    order = 1
    for group, tickers in MVP_TICKER_GROUPS.items():
        for ticker in tickers:
            rows.append(
                {
                    "ticker": ticker,
                    "mvp_group": group,
                    "mvp_order": order,
                }
            )
            order += 1

    df = pd.DataFrame(rows)

    duplicated = df[df["ticker"].duplicated(keep=False)]
    if not duplicated.empty:
        raise ValueError(
            "Há tickers duplicados na lista fixa do MVP:\n"
            + duplicated.to_string(index=False)
        )

    return df


# =============================================================================
# Leitura e preparação das fontes
# =============================================================================

def load_inputs(processed_dir: Path) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    b3_path = latest_file(processed_dir, "b3_classificacao_setorial_20260615.csv")
    liq_path = latest_file(processed_dir, "b3_liquidity_ranking_2026.csv")
    cvm_path = processed_dir / "cvm_companies.csv"

    if not cvm_path.exists():
        raise FileNotFoundError(f"Arquivo não encontrado: {cvm_path}")

    print(f"Lendo B3 classificação: {b3_path}")
    print(f"Lendo ranking liquidez: {liq_path}")
    print(f"Lendo CVM empresas: {cvm_path}")

    b3 = pd.read_csv(b3_path, dtype=str)
    liquidity = pd.read_csv(liq_path, dtype=str)
    cvm = pd.read_csv(cvm_path, dtype=str)

    return b3, liquidity, cvm


def prepare_b3(b3: pd.DataFrame) -> pd.DataFrame:
    b3 = b3.copy()

    if "ticker" not in b3.columns:
        raise ValueError("Arquivo B3 não possui coluna 'ticker'.")

    b3["ticker"] = b3["ticker"].apply(normalize_ticker)

    if "code_cvm" in b3.columns:
        b3["code_cvm_norm"] = b3["code_cvm"].apply(normalize_code)
    else:
        b3["code_cvm_norm"] = None

    b3 = b3.dropna(subset=["ticker"])

    keep_cols = [
        "ticker",
        "isin",
        "issuing_company",
        "company_name",
        "trading_name",
        "cnpj",
        "code_cvm",
        "code_cvm_norm",
        "activity",
        "website",
        "status",
        "has_quotation",
        "market",
        "industry_classification",
        "b3_sector",
        "b3_subsector",
        "b3_segment",
    ]

    keep_cols = [c for c in keep_cols if c in b3.columns]

    return b3[keep_cols].drop_duplicates(subset=["ticker"])


def prepare_liquidity(liquidity: pd.DataFrame) -> pd.DataFrame:
    liquidity = liquidity.copy()

    if "ticker" not in liquidity.columns:
        raise ValueError("Arquivo de liquidez não possui coluna 'ticker'.")

    liquidity["ticker"] = liquidity["ticker"].apply(normalize_ticker)
    liquidity = liquidity.dropna(subset=["ticker"])

    numeric_cols = [
        "days_traded",
        "total_trades",
        "avg_trades_per_day",
        "total_quantity",
        "total_volume_brl",
        "avg_daily_volume_brl",
        "last_close",
        "liquidity_rank",
    ]

    for col in numeric_cols:
        if col in liquidity.columns:
            liquidity[col] = pd.to_numeric(liquidity[col], errors="coerce")

    if "mvp_candidate" in liquidity.columns:
        liquidity["mvp_candidate"] = (
            liquidity["mvp_candidate"]
            .astype(str)
            .str.lower()
            .isin(["true", "1", "yes", "sim"])
        )
    else:
        liquidity["mvp_candidate"] = False

    keep_cols = [
        "ticker",
        "days_traded",
        "total_trades",
        "avg_trades_per_day",
        "total_volume_brl",
        "avg_daily_volume_brl",
        "last_close",
        "liquidity_rank",
        "mvp_candidate",
    ]

    keep_cols = [c for c in keep_cols if c in liquidity.columns]

    return liquidity[keep_cols].drop_duplicates(subset=["ticker"])


def prepare_cvm(cvm: pd.DataFrame) -> pd.DataFrame:
    cvm = cvm.copy()

    if "cvm_code" in cvm.columns:
        cvm["cvm_code_norm"] = cvm["cvm_code"].apply(normalize_code)
    else:
        cvm["cvm_code_norm"] = None

    keep_cols = [
        "cvm_code_norm",
        "cvm_code",
        "cnpj",
        "legal_name",
        "commercial_name",
        "cvm_activity_sector",
        "registration_status",
        "registration_date",
    ]

    keep_cols = [c for c in keep_cols if c in cvm.columns]

    return cvm[keep_cols].drop_duplicates(subset=["cvm_code_norm"])


# =============================================================================
# Merge e geração do universo
# =============================================================================

def merge_fixed_universe(
    fixed_universe: pd.DataFrame,
    b3: pd.DataFrame,
    liquidity: pd.DataFrame,
    cvm: pd.DataFrame,
) -> pd.DataFrame:
    df = fixed_universe.merge(b3, on="ticker", how="left")
    df = df.merge(liquidity, on="ticker", how="left")

    if "code_cvm_norm" in df.columns and "cvm_code_norm" in cvm.columns:
        df = df.merge(
            cvm,
            left_on="code_cvm_norm",
            right_on="cvm_code_norm",
            how="left",
            suffixes=("", "_cvm"),
        )

    # Campos de controle para facilitar revisão.
    df["found_in_b3"] = df["b3_sector"].notna() if "b3_sector" in df.columns else False
    df["found_in_liquidity"] = (
        df["avg_daily_volume_brl"].notna()
        if "avg_daily_volume_brl" in df.columns
        else False
    )
    df["found_in_cvm"] = (
        df["legal_name"].notna()
        if "legal_name" in df.columns
        else False
    )

    # Campo pedido: criado para preenchimento manual.
    df["internal_sector"] = "TODO"

    # Campo de status para controlar a curadoria.
    df["curation_status"] = "pending"

    return df.sort_values("mvp_order")


def build_missing_tickers_report(universe: pd.DataFrame) -> pd.DataFrame:
    missing = universe[
        ~universe["found_in_b3"] | ~universe["found_in_liquidity"]
    ].copy()

    cols = [
        "ticker",
        "mvp_group",
        "found_in_b3",
        "found_in_liquidity",
        "found_in_cvm",
        "company_name",
        "trading_name",
        "b3_sector",
        "avg_daily_volume_brl",
    ]

    cols = [c for c in cols if c in missing.columns]

    return missing[cols]


def finalize_universe_columns(universe: pd.DataFrame) -> pd.DataFrame:
    final_cols = [
        "ticker",
        "mvp_group",
        "internal_sector",
        "curation_status",
        "company_name",
        "trading_name",
        "issuing_company",
        "b3_sector",
        "b3_subsector",
        "b3_segment",
        "industry_classification",
        "activity",
        "website",
        "cnpj",
        "code_cvm",
        "legal_name",
        "commercial_name",
        "cvm_activity_sector",
        "registration_status",
        "days_traded",
        "avg_daily_volume_brl",
        "total_volume_brl",
        "total_trades",
        "liquidity_rank",
        "found_in_b3",
        "found_in_liquidity",
        "found_in_cvm",
        "mvp_order",
    ]

    final_cols = [c for c in final_cols if c in universe.columns]

    return universe[final_cols]


# =============================================================================
# Template YAML para curadoria macro
# =============================================================================

def build_ticker_template(universe: pd.DataFrame) -> dict[str, dict[str, Any]]:
    template = {}

    for _, row in universe.iterrows():
        ticker = row["ticker"]

        company = first_non_null(
            row.get("company_name"),
            row.get("trading_name"),
            row.get("issuing_company"),
            row.get("legal_name"),
            ticker,
        )

        template[ticker] = {
            "company": str(company),
            "mvp_group": row.get("mvp_group"),
            "internal_sector": "TODO",
            "b3_sector": row.get("b3_sector"),
            "b3_subsector": row.get("b3_subsector"),
            "b3_segment": row.get("b3_segment"),
            "business_description": "TODO",
            "revenue_profile": {
                "currency": "TODO",
                "geography": "TODO",
                "commodity_linked": "TODO",
                "regulated": "TODO",
            },
            "positive_exposures": [],
            "negative_exposures": [],
            "exposure_scores": {factor: 0 for factor in MACRO_FACTORS},
            "company_characteristics": [],
            "rationale": "TODO",
            "confidence": "TODO",
            "curation_status": "pending",
            "sources": [
                "B3 classification",
                "B3 liquidity ranking",
                "CVM companies",
            ],
        }

    return template


def save_outputs(
    universe: pd.DataFrame,
    missing_tickers: pd.DataFrame,
    template: dict[str, dict[str, Any]],
    curated_dir: Path,
) -> tuple[Path, Path, Path | None]:
    curated_dir.mkdir(parents=True, exist_ok=True)

    universe_path = curated_dir / "mvp_universe.csv"
    template_path = curated_dir / "ticker_exposures_template.yaml"
    missing_path = curated_dir / "missing_tickers.csv"

    universe.to_csv(universe_path, index=False, encoding="utf-8-sig")

    with open(template_path, "w", encoding="utf-8") as file:
        yaml.safe_dump(
            template,
            file,
            allow_unicode=True,
            sort_keys=False,
            default_flow_style=False,
        )

    if not missing_tickers.empty:
        missing_tickers.to_csv(missing_path, index=False, encoding="utf-8-sig")
        return universe_path, template_path, missing_path

    if missing_path.exists():
        missing_path.unlink()

    return universe_path, template_path, None


# =============================================================================
# CLI
# =============================================================================

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--processed-dir",
        type=Path,
        default=Path("data/processed"),
        help="Diretório onde estão os arquivos processados de B3/CVM.",
    )

    parser.add_argument(
        "--curated-dir",
        type=Path,
        default=Path("data/curated"),
        help="Diretório onde serão salvos os arquivos curados.",
    )

    parser.add_argument(
        "--strict",
        action="store_true",
        help=(
            "Se ativado, gera erro quando algum ticker da lista fixa não for "
            "encontrado na B3 ou no ranking de liquidez."
        ),
    )

    return parser.parse_args()


def main() -> None:
    args = parse_args()

    fixed_universe = build_fixed_universe_dataframe()

    b3_raw, liquidity_raw, cvm_raw = load_inputs(args.processed_dir)

    b3 = prepare_b3(b3_raw)
    liquidity = prepare_liquidity(liquidity_raw)
    cvm = prepare_cvm(cvm_raw)

    merged = merge_fixed_universe(
        fixed_universe=fixed_universe,
        b3=b3,
        liquidity=liquidity,
        cvm=cvm,
    )

    universe = finalize_universe_columns(merged)
    missing_tickers = build_missing_tickers_report(universe)
    template = build_ticker_template(universe)

    universe_path, template_path, missing_path = save_outputs(
        universe=universe,
        missing_tickers=missing_tickers,
        template=template,
        curated_dir=args.curated_dir,
    )

    print("\nUniverso MVP fixo criado com sucesso.")
    print(f"Tickers definidos no MVP: {len(universe)}")
    print(f"Arquivo CSV: {universe_path}")
    print(f"Template YAML: {template_path}")

    print("\nDistribuição por grupo MVP:")
    print(universe["mvp_group"].value_counts(dropna=False).to_string())

    if "b3_sector" in universe.columns:
        print("\nDistribuição por setor B3:")
        print(universe["b3_sector"].value_counts(dropna=False).to_string())

    if missing_path:
        print("\nAtenção: alguns tickers não foram encontrados em uma ou mais fontes.")
        print(f"Relatório salvo em: {missing_path}")
        print(missing_tickers.to_string(index=False))

        if args.strict:
            raise RuntimeError(
                "Modo --strict ativado: há tickers ausentes em B3 ou liquidez."
            )

    print("\nPróxima etapa:")
    print("1. Abrir data/curated/mvp_universe.csv")
    print("2. Conferir tickers ausentes ou inconsistentes")
    print("3. Preencher internal_sector manualmente no YAML")
    print("4. Preencher business_description, exposures, scores e rationale")


if __name__ == "__main__":
    main()
