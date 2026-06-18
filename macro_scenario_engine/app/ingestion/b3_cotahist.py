#!/usr/bin/env python3
"""
b3_cotahist.py

Baixa e processa o arquivo COTAHIST anual da B3/BM&FBovespa.

Objetivo no projeto:
- Medir liquidez dos ativos.
- Filtrar o universo bruto para um MVP com ações negociáveis/relevantes.
- Gerar ranking por volume financeiro, negócios e dias negociados.

Fonte usual dos arquivos anuais:
    https://bvmf.bmfbovespa.com.br/InstDados/SerHist/COTAHIST_A{ANO}.ZIP

Uso:
    python b3_cotahist.py --year 2026 --out-dir data/raw/b3 --processed-dir data/processed
"""

from __future__ import annotations

import argparse
import datetime as dt
import io
import re
import zipfile
from pathlib import Path

import pandas as pd
import requests


COTAHIST_URL_TEMPLATE = "https://bvmf.bmfbovespa.com.br/InstDados/SerHist/COTAHIST_A{year}.ZIP"

COTAHIST_COLSPECS = [
    (0, 2), (2, 10), (10, 12), (12, 24), (24, 27), (27, 39),
    (39, 49), (49, 52), (52, 56), (56, 69), (69, 82), (82, 95),
    (95, 108), (108, 121), (121, 134), (134, 147), (147, 152),
    (152, 170), (170, 188), (188, 201), (201, 202), (202, 210),
    (210, 217), (217, 230), (230, 242), (242, 245),
]

COTAHIST_COLUMNS = [
    "tipo_registro", "data_pregao", "cod_bdi", "ticker", "tipo_mercado",
    "nome_resumido", "especificacao", "prazo_termo", "moeda", "preco_abertura",
    "preco_maximo", "preco_minimo", "preco_medio", "preco_ultimo",
    "preco_melhor_compra", "preco_melhor_venda", "negocios", "quantidade",
    "volume", "preco_exercicio", "indicador_correcao_precos", "data_vencimento",
    "fator_cotacao", "preco_exercicio_pontos", "codigo_isin", "numero_distribuicao",
]

MONEY_COLUMNS = [
    "preco_abertura", "preco_maximo", "preco_minimo", "preco_medio",
    "preco_ultimo", "preco_melhor_compra", "preco_melhor_venda", "volume",
    "preco_exercicio", "preco_exercicio_pontos",
]


def ensure_dirs(*paths: Path) -> None:
    for path in paths:
        path.mkdir(parents=True, exist_ok=True)


def download_cotahist(year: int, out_dir: Path, timeout: int = 120) -> Path:
    ensure_dirs(out_dir)
    url = COTAHIST_URL_TEMPLATE.format(year=year)
    zip_path = out_dir / f"COTAHIST_A{year}.ZIP"

    if zip_path.exists() and zip_path.stat().st_size > 0:
        print(f"Arquivo já existe, pulando download: {zip_path}")
        return zip_path

    headers = {"User-Agent": "Mozilla/5.0 (compatible; macro-sector-agent/0.1)"}
    response = requests.get(url, headers=headers, timeout=timeout)
    response.raise_for_status()
    zip_path.write_bytes(response.content)
    print(f"Download concluído: {zip_path}")
    return zip_path


def find_txt_inside_zip(zip_path: Path) -> str:
    with zipfile.ZipFile(zip_path) as zf:
        names = zf.namelist()
        txt_files = [name for name in names if name.upper().endswith(".TXT")]
        if not txt_files:
            txt_files = names
        if not txt_files:
            raise RuntimeError(f"ZIP vazio: {zip_path}")
        return txt_files[0]


def parse_cotahist_zip(zip_path: Path) -> pd.DataFrame:
    txt_name = find_txt_inside_zip(zip_path)
    with zipfile.ZipFile(zip_path) as zf:
        raw = zf.read(txt_name)

    df = pd.read_fwf(
        io.BytesIO(raw),
        colspecs=COTAHIST_COLSPECS,
        names=COTAHIST_COLUMNS,
        dtype=str,
        encoding="latin1",
    )

    df = df[df["tipo_registro"] == "01"].copy()

    for col in ["ticker", "nome_resumido", "especificacao", "moeda", "codigo_isin"]:
        df[col] = df[col].astype(str).str.strip()

    df["data_pregao"] = pd.to_datetime(df["data_pregao"], format="%Y%m%d", errors="coerce")

    for col in ["tipo_mercado", "negocios", "quantidade", "fator_cotacao", "numero_distribuicao"]:
        df[col] = pd.to_numeric(df[col].str.strip(), errors="coerce")

    for col in MONEY_COLUMNS:
        df[col] = pd.to_numeric(df[col].str.strip(), errors="coerce") / 100

    return df


def is_likely_cash_equity_ticker(ticker: str) -> bool:
    if not isinstance(ticker, str):
        return False
    ticker = ticker.strip().upper()
    return bool(re.fullmatch(r"[A-Z]{4}[0-9]{1,2}", ticker))


def filter_cash_equities(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out = out[out["tipo_mercado"] == 10]
    out = out[out["ticker"].apply(is_likely_cash_equity_ticker)]
    return out


def build_liquidity_ranking(df: pd.DataFrame) -> pd.DataFrame:
    grouped = (
        df.groupby("ticker", as_index=False)
        .agg(
            trading_name=("nome_resumido", "last"),
            days_traded=("data_pregao", "nunique"),
            first_date=("data_pregao", "min"),
            last_date=("data_pregao", "max"),
            total_trades=("negocios", "sum"),
            avg_trades_per_day=("negocios", "mean"),
            total_quantity=("quantidade", "sum"),
            total_volume_brl=("volume", "sum"),
            avg_daily_volume_brl=("volume", "mean"),
            last_close=("preco_ultimo", "last"),
        )
        .sort_values("avg_daily_volume_brl", ascending=False)
    )
    grouped["liquidity_rank"] = range(1, len(grouped) + 1)
    max_days = grouped["days_traded"].max() if not grouped.empty else 0
    grouped["mvp_candidate"] = (
        (grouped["avg_daily_volume_brl"] >= 5_000_000)
        & (grouped["days_traded"] >= max(20, int(max_days * 0.5)))
    )
    return grouped


def process_cotahist(year: int, out_dir: Path, processed_dir: Path) -> tuple[Path, Path]:
    ensure_dirs(out_dir, processed_dir)
    zip_path = download_cotahist(year, out_dir)
    daily = parse_cotahist_zip(zip_path)
    cash_equities = filter_cash_equities(daily)
    ranking = build_liquidity_ranking(cash_equities)

    daily_path = processed_dir / f"b3_cotahist_{year}_daily.csv"
    ranking_path = processed_dir / f"b3_liquidity_ranking_{year}.csv"
    cash_equities.to_csv(daily_path, index=False, encoding="utf-8-sig")
    ranking.to_csv(ranking_path, index=False, encoding="utf-8-sig")
    return daily_path, ranking_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--year", type=int, default=dt.date.today().year)
    parser.add_argument("--out-dir", default="data/raw/b3", type=Path)
    parser.add_argument("--processed-dir", default="data/processed", type=Path)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    daily_path, ranking_path = process_cotahist(args.year, args.out_dir, args.processed_dir)
    print(f"Arquivo diário salvo em: {daily_path}")
    print(f"Ranking de liquidez salvo em: {ranking_path}")


if __name__ == "__main__":
    main()
