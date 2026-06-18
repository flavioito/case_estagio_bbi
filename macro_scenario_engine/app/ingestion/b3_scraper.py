#!/usr/bin/env python3
"""
b3_scraper.py

Coleta empresas listadas da B3 usando os endpoints internos do site
sistemaswebb3-listados.b3.com.br.

Este script substitui a tentativa de extrair tabela HTML da página de
classificação setorial, porque a página atual da B3 não expõe a tabela
diretamente no HTML.

Saídas:
- data/raw/b3/b3_initial_companies_raw_YYYYMMDD.json
- data/raw/b3/b3_company_details_raw_YYYYMMDD.json
- data/processed/b3_classificacao_setorial_YYYYMMDD.csv
"""

from __future__ import annotations

import argparse
import base64
import datetime as dt
import json
import time
from pathlib import Path
from typing import Any

import pandas as pd
import requests


BASE_URL = "https://sistemaswebb3-listados.b3.com.br/listedCompaniesProxy/CompanyCall"

INITIAL_COMPANIES_ENDPOINT = f"{BASE_URL}/GetInitialCompanies"
DETAIL_ENDPOINT = f"{BASE_URL}/GetDetail"

LANGUAGE = "pt-br"


def today_str() -> str:
    return dt.date.today().strftime("%Y%m%d")


def ensure_dirs(*paths: Path) -> None:
    for path in paths:
        path.mkdir(parents=True, exist_ok=True)


def b3_token(payload: dict[str, Any]) -> str:
    """
    A B3 usa parâmetros JSON codificados em base64 na URL.
    Equivalente ao btoa(JSON.stringify(payload)) no navegador.
    """
    payload_json = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return base64.b64encode(payload_json.encode("utf-8")).decode("utf-8")


def get_json(url: str, timeout: int = 30) -> dict[str, Any]:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0 Safari/537.36"
        ),
        "Accept": "application/json, text/plain, */*",
        "Referer": "https://sistemaswebb3-listados.b3.com.br/listedCompaniesPage/",
    }

    response = requests.get(url, headers=headers, timeout=timeout)
    response.raise_for_status()

    try:
        return response.json()
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"A resposta da B3 não veio em JSON. Status={response.status_code}. "
            f"Trecho inicial: {response.text[:300]}"
        ) from exc


def fetch_initial_companies(page_size: int = 120, sleep_seconds: float = 0.2) -> list[dict[str, Any]]:
    """
    Busca a lista inicial de empresas.

    A API é paginada. Vamos até uma página retornar lista vazia.
    """
    all_results: list[dict[str, Any]] = []
    page = 1

    while True:
        payload = {
            "language": LANGUAGE,
            "pageNumber": page,
            "pageSize": page_size,
        }

        token = b3_token(payload)
        url = f"{INITIAL_COMPANIES_ENDPOINT}/{token}"

        data = get_json(url)
        results = data.get("results", [])

        if not results:
            break

        all_results.extend(results)

        print(f"Página {page}: {len(results)} empresas coletadas")

        page += 1
        time.sleep(sleep_seconds)

    return all_results


def fetch_company_detail(code_cvm: str, sleep_seconds: float = 0.15) -> dict[str, Any] | None:
    """
    Busca detalhes de uma companhia pelo código CVM.
    """
    if not code_cvm:
        return None

    payload = {
        "codeCVM": str(code_cvm),
        "language": LANGUAGE,
    }

    token = b3_token(payload)
    url = f"{DETAIL_ENDPOINT}/{token}"

    try:
        data = get_json(url)
        time.sleep(sleep_seconds)
        return data
    except requests.HTTPError as exc:
        print(f"Aviso: erro HTTP ao buscar codeCVM={code_cvm}: {exc}")
        return None
    except Exception as exc:
        print(f"Aviso: erro ao buscar codeCVM={code_cvm}: {exc}")
        return None


def split_industry_classification(value: str | None) -> tuple[str | None, str | None, str | None]:
    """
    A B3 costuma retornar classificação como:
    'Financeiro / Intermediários Financeiros / Bancos'
    """
    if not value:
        return None, None, None

    parts = [part.strip() for part in str(value).split("/")]

    sector = parts[0] if len(parts) >= 1 else None
    subsector = parts[1] if len(parts) >= 2 else None
    segment = parts[2] if len(parts) >= 3 else None

    return sector, subsector, segment


def normalize_company_details(details: list[dict[str, Any]]) -> pd.DataFrame:
    """
    Transforma o JSON detalhado da B3 em uma tabela por ticker.

    Como uma empresa pode ter múltiplos códigos de negociação, expandimos
    otherCodes para uma linha por ticker.
    """
    rows = []

    for item in details:
        if not item:
            continue

        industry = item.get("industryClassification")
        sector, subsector, segment = split_industry_classification(industry)

        other_codes = item.get("otherCodes") or []

        # Se não vier otherCodes, tenta usar o campo code.
        if not other_codes and item.get("code"):
            other_codes = [{"code": item.get("code"), "isin": None}]

        for code_info in other_codes:
            ticker = code_info.get("code")

            if not ticker:
                continue

            rows.append(
                {
                    "ticker": str(ticker).strip().upper(),
                    "isin": code_info.get("isin"),
                    "issuing_company": item.get("issuingCompany"),
                    "company_name": item.get("companyName"),
                    "trading_name": item.get("tradingName"),
                    "cnpj": item.get("cnpj"),
                    "code_cvm": item.get("codeCVM"),
                    "activity": item.get("activity"),
                    "website": item.get("website"),
                    "status": item.get("status"),
                    "has_quotation": item.get("hasQuotation"),
                    "market": item.get("market"),
                    "market_indicator": item.get("marketIndicator"),
                    "date_quotation": item.get("dateQuotation"),
                    "industry_classification": industry,
                    "b3_sector": sector,
                    "b3_subsector": subsector,
                    "b3_segment": segment,
                    "source": "B3 sistemaswebb3-listados",
                    "extracted_at": dt.datetime.now().isoformat(timespec="seconds"),
                }
            )

    df = pd.DataFrame(rows)

    if df.empty:
        return df

    # Remove duplicatas exatas.
    df = df.drop_duplicates(subset=["ticker", "code_cvm"], keep="first")

    # Filtro leve: mantém tickers com cara de ação/unit brasileira.
    # Ex.: PETR4, VALE3, SANB11.
    df = df[df["ticker"].str.match(r"^[A-Z]{4}[0-9]{1,2}$", na=False)].copy()

    return df.sort_values(["b3_sector", "b3_subsector", "b3_segment", "ticker"])


def scrape_b3_companies(out_dir: Path, processed_dir: Path) -> Path:
    ensure_dirs(out_dir, processed_dir)

    stamp = today_str()

    raw_initial_path = out_dir / f"b3_initial_companies_raw_{stamp}.json"
    raw_details_path = out_dir / f"b3_company_details_raw_{stamp}.json"
    processed_path = processed_dir / f"b3_classificacao_setorial_{stamp}.csv"

    print("Coletando lista inicial de empresas da B3...")
    initial_companies = fetch_initial_companies()

    raw_initial_path.write_text(
        json.dumps(initial_companies, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"Total de registros iniciais: {len(initial_companies)}")

    code_cvms = []
    for item in initial_companies:
        code = item.get("codeCVM") or item.get("codeCvm") or item.get("cvmCode")
        if code:
            code_cvms.append(str(code))

    code_cvms = sorted(set(code_cvms))

    print(f"Total de códigos CVM únicos: {len(code_cvms)}")
    print("Coletando detalhes por código CVM...")

    details = []
    for i, code_cvm in enumerate(code_cvms, start=1):
        detail = fetch_company_detail(code_cvm)
        if detail:
            details.append(detail)

        if i % 25 == 0:
            print(f"{i}/{len(code_cvms)} detalhes coletados")

    raw_details_path.write_text(
        json.dumps(details, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    df = normalize_company_details(details)

    if df.empty:
        raise RuntimeError(
            "A coleta retornou vazia após normalização. "
            "Verifique os arquivos JSON salvos em data/raw/b3."
        )

    df.to_csv(processed_path, index=False, encoding="utf-8-sig")

    print(f"Arquivo processado salvo em: {processed_path}")
    print(f"Linhas finais: {len(df)}")
    print(f"Setores B3 encontrados: {df['b3_sector'].nunique()}")

    return processed_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", default="data/raw/b3", type=Path)
    parser.add_argument("--processed-dir", default="data/processed", type=Path)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    scrape_b3_companies(
        out_dir=args.out_dir,
        processed_dir=args.processed_dir,
    )


if __name__ == "__main__":
    main()