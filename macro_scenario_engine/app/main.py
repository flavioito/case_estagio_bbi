from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.config import load_settings
from app.pipeline import run_analysis, save_outputs
from app.validators import MacroScenarioError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Traduz cenários macroeconômicos em análise setorial e tickers expostos na B3."
    )
    parser.add_argument("--scenario", "-s", help="Cenário macroeconômico em linguagem natural.")
    parser.add_argument(
        "--use-llm",
        action="store_true",
        help="Mantido por compatibilidade; o uso de LLM já é automático por padrão.",
    )
    parser.add_argument("--no-llm", action="store_true", help="Desativa Claude e usa apenas o parser heurístico local.")
    parser.add_argument("--markdown", action="store_true", help="Imprime apenas o relatório Markdown.")
    parser.add_argument(
        "--save",
        action="store_true",
        help="Mantido por compatibilidade; JSON e Markdown já são salvos automaticamente.",
    )
    parser.add_argument("--no-save", action="store_true", help="Não salva JSON e Markdown em app/output.")
    parser.add_argument("--log-level", default="WARNING", choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    logging.basicConfig(level=getattr(logging, args.log_level), format="%(levelname)s:%(name)s:%(message)s")

    scenario = args.scenario or sys.stdin.read().strip()
    settings = load_settings()
    use_llm = not args.no_llm

    try:
        output = run_analysis(scenario, settings=settings, use_llm=use_llm)
    except MacroScenarioError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except Exception as exc:
        print(f"Erro inesperado: {exc}", file=sys.stderr)
        return 1

    if not args.no_save:
        json_path, md_path = save_outputs(output, settings.output_dir)
        print(f"Arquivos salvos:\n- {json_path}\n- {md_path}", file=sys.stderr)

    if args.markdown:
        print(output.markdown_report)
    else:
        print(json.dumps(output.as_json_dict(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
