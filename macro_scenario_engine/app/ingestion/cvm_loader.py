#!/usr/bin/env python3
"""
cvm_loader.py

Baixa e processa dados abertos da CVM para companhias abertas.

Objetivo no projeto:
- Obter cadastro de companhias abertas.
- Baixar arquivos ITR por ano, se desejado.
- Criar uma base processada de companhias para cruzar com tickers/setores da B3.

Uso:
    python cvm_loader.py --out-dir data/raw/cvm --processed-dir data/processed --itr-years 2025 2026
"""

from __future__ import annotations

import argparse
import datetime as dt
import zipfile
from pathlib import Path

import pandas as pd
import requests


CVM_CADASTRO_URL = "https://dados.cvm.gov.br/dados/CIA_ABERTA/CAD/DADOS/cad_cia_aberta.csv"
CVM_ITR_URL_TEMPLATE = "https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/ITR/DADOS/itr_cia_aberta_{year}.zip"


def ensure_dirs(*paths: Path) -> None:
    for path in paths:
        path.mkdir(parents=True, exist_ok=True)


def download_file(url: str, output_path: Path, timeout: int = 120, overwrite: bool = False) -> Path:
    ensure_dirs(output_path.parent)
    if output_path.exists() and output_path.stat().st_size > 0 and not overwrite:
        print(f"Arquivo já existe, pulando download: {output_path}")
        return output_path

    headers = {"User-Agent": "Mozilla/5.0 (compatible; macro-sector-agent/0.1)"}
    response = requests.get(url, headers=headers, timeout=timeout)
    response.raise_for_status()
    output_path.write_bytes(response.content)
    print(f"Download concluído: {output_path}")
    return output_path


def load_cvm_cadastro(raw_path: Path) -> pd.DataFrame:
    df = pd.read_csv(raw_path, sep=";", encoding="latin1", dtype=str)
    df.columns = (
        df.columns
        .str.strip()
        .str.lower()
        .str.normalize("NFKD")
        .str.encode("ascii", errors="ignore")
        .str.decode("utf-8")
        .str.replace(r"[^a-z0-9]+", "_", regex=True)
        .str.strip("_")
    )

    for col in df.columns:
        if df[col].dtype == "object":
            df[col] = df[col].astype(str).str.strip()
            df.loc[df[col].isin(["", "nan", "None"]), col] = None

    if "cnpj_cia" in df.columns:
        df["cnpj_cia_digits"] = df["cnpj_cia"].str.replace(r"\D", "", regex=True)

    rename_candidates = {
        "cd_cvm": "cvm_code",
        "cnpj_cia": "cnpj",
        "denom_social": "legal_name",
        "denom_comerc": "commercial_name",
        "setor_atividade": "cvm_activity_sector",
        "sit": "registration_status",
        "dt_reg": "registration_date",
    }
    for old, new in rename_candidates.items():
        if old in df.columns and new not in df.columns:
            df[new] = df[old]

    df["source_url"] = CVM_CADASTRO_URL
    df["extracted_at"] = dt.datetime.now().isoformat(timespec="seconds")

    preferred = [
        "cvm_code", "cnpj", "cnpj_cia_digits", "legal_name", "commercial_name",
        "cvm_activity_sector", "registration_status", "registration_date",
        "source_url", "extracted_at",
    ]
    remaining = [c for c in df.columns if c not in preferred]
    return df[[c for c in preferred if c in df.columns] + remaining]


def download_cvm_cadastro(out_dir: Path, processed_dir: Path, overwrite: bool = False) -> Path:
    ensure_dirs(out_dir, processed_dir)
    raw_path = out_dir / "cad_cia_aberta.csv"
    processed_path = processed_dir / "cvm_companies.csv"
    download_file(CVM_CADASTRO_URL, raw_path, overwrite=overwrite)
    companies = load_cvm_cadastro(raw_path)
    companies.to_csv(processed_path, index=False, encoding="utf-8-sig")
    return processed_path


def download_and_extract_itr(year: int, out_dir: Path, overwrite: bool = False) -> list[Path]:
    itr_dir = out_dir / "itr" / str(year)
    ensure_dirs(itr_dir)
    zip_path = itr_dir / f"itr_cia_aberta_{year}.zip"
    url = CVM_ITR_URL_TEMPLATE.format(year=year)
    download_file(url, zip_path, overwrite=overwrite)

    extracted_files = []
    with zipfile.ZipFile(zip_path) as zf:
        for member in zf.namelist():
            target = itr_dir / member
            if target.exists() and target.stat().st_size > 0 and not overwrite:
                extracted_files.append(target)
                continue
            zf.extract(member, itr_dir)
            extracted_files.append(target)
    print(f"ITR {year}: {len(extracted_files)} arquivos extraídos em {itr_dir}")
    return extracted_files


def build_itr_file_index(itr_files: list[Path], processed_dir: Path) -> Path:
    ensure_dirs(processed_dir)
    rows = []
    for file in itr_files:
        rows.append({
            "year": file.parent.name,
            "file_name": file.name,
            "path": str(file),
            "size_bytes": file.stat().st_size if file.exists() else None,
            "suffix": file.suffix.lower(),
        })
    index = pd.DataFrame(rows)
    index_path = processed_dir / "cvm_itr_file_index.csv"
    if index_path.exists():
        old = pd.read_csv(index_path)
        index = pd.concat([old, index], ignore_index=True).drop_duplicates(subset=["path"], keep="last")
    index.to_csv(index_path, index=False, encoding="utf-8-sig")
    return index_path


def load_itr_statement_file(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, sep=";", encoding="latin1", dtype=str)
    df.columns = (
        df.columns
        .str.strip()
        .str.lower()
        .str.normalize("NFKD")
        .str.encode("ascii", errors="ignore")
        .str.decode("utf-8")
        .str.replace(r"[^a-z0-9]+", "_", regex=True)
        .str.strip("_")
    )
    return df


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", default="data/raw/cvm", type=Path)
    parser.add_argument("--processed-dir", default="data/processed", type=Path)
    parser.add_argument("--itr-years", nargs="*", type=int, default=[dt.date.today().year])
    parser.add_argument("--skip-itr", action="store_true")
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    companies_path = download_cvm_cadastro(args.out_dir, args.processed_dir, overwrite=args.overwrite)
    print(f"Cadastro CVM processado salvo em: {companies_path}")

    if not args.skip_itr:
        all_itr_files: list[Path] = []
        for year in args.itr_years:
            try:
                all_itr_files.extend(download_and_extract_itr(year, args.out_dir, overwrite=args.overwrite))
            except requests.HTTPError as exc:
                print(f"Aviso: não foi possível baixar ITR de {year}: {exc}")
        if all_itr_files:
            index_path = build_itr_file_index(all_itr_files, args.processed_dir)
            print(f"Índice de arquivos ITR salvo em: {index_path}")


if __name__ == "__main__":
    main()
