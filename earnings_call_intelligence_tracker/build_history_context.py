from __future__ import annotations

from pathlib import Path

import typer

from src.history_context import build_history_context, select_history_pdfs, write_history_context
from src.pdf_loader import PdfLoaderError


DEFAULT_EXCLUDE = {"Transcript - Videoconference - 1Q26 (BBAS3).pdf"}


def main(
    input_dir: Path = typer.Option(
        Path("data"),
        "--input",
        "-i",
        help="Directory containing historical transcript PDFs.",
    ),
    output: Path = typer.Option(
        Path("context/BBAS3_history_context.json"),
        "--output",
        "-o",
        help="Path where the compact history context JSON will be written.",
    ),
    ticker: str = typer.Option(
        "BBAS3",
        "--ticker",
        help="Ticker to write in the history context.",
    ),
    company: str = typer.Option(
        "Banco do Brasil",
        "--company",
        help="Company name to write in the history context.",
    ),
) -> None:
    """Build compact 2024-2025 historical context from transcript PDFs."""
    try:
        pdf_paths = select_history_pdfs(
            input_dir,
            years={2024, 2025},
            exclude_names=DEFAULT_EXCLUDE,
        )
        if not pdf_paths:
            typer.secho("Nenhum PDF historico encontrado para 2024-2025.", fg=typer.colors.RED, err=True)
            raise typer.Exit(code=1)

        context = build_history_context(pdf_paths, ticker=ticker, company=company)
        written = write_history_context(context, output)
    except PdfLoaderError as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc
    except OSError as exc:
        typer.secho(f"Erro de arquivo: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc

    typer.secho("Contexto historico gerado com sucesso.", fg=typer.colors.GREEN)
    typer.echo(f"Arquivos processados: {len(pdf_paths)}")
    for path in pdf_paths:
        typer.echo(f"- {path.name}")
    typer.echo(f"Output: {written}")


if __name__ == "__main__":
    typer.run(main)
