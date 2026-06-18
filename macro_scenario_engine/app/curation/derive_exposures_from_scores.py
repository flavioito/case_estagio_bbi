#!/usr/bin/env python3

from __future__ import annotations

import argparse
from pathlib import Path

import yaml


def load_yaml(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as file:
        return yaml.safe_load(file)


def save_yaml(data: dict, path: Path) -> None:
    with path.open("w", encoding="utf-8") as file:
        yaml.safe_dump(
            data,
            file,
            allow_unicode=True,
            sort_keys=False,
            default_flow_style=False,
            width=120,
        )


def derive_exposures(data: dict, min_abs_score: int = 2) -> dict:
    for ticker, info in data.items():
        scores = info.get("exposure_scores", {})

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

        info["positive_exposures"] = sorted(
            positive,
            key=lambda factor: scores[factor],
            reverse=True,
        )

        info["negative_exposures"] = sorted(
            negative,
            key=lambda factor: scores[factor],
        )

    return data


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--min-abs-score", type=int, default=2)
    return parser.parse_args()


def main():
    args = parse_args()

    data = load_yaml(args.input)
    data = derive_exposures(data, min_abs_score=args.min_abs_score)
    save_yaml(data, args.output)

    print(f"Arquivo salvo em: {args.output}")


if __name__ == "__main__":
    main()