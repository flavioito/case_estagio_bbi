from __future__ import annotations

from pathlib import Path

import typer

from src.anthropic_client import AnthropicClientError
from src.pdf_loader import PdfLoaderError
from src.pipeline import AnalysisValidationError, run_day1_pipeline, run_day2_pipeline
from src.report_writer import ReportWriterError


def main(
    pdf_path: Path = typer.Argument(
        ...,
        help="Path to the earnings call transcript PDF.",
    ),
    output: Path = typer.Option(
        Path("output"),
        "--output",
        "-o",
        help="Directory where intermediate outputs will be saved.",
    ),
    debug: bool = typer.Option(
        False,
        "--debug",
        help="Print extra execution details.",
    ),
    extract_only: bool = typer.Option(
        False,
        "--extract-only",
        help="Only run Day 1 extraction and segmentation without Claude.",
    ),
    previous: Path | None = typer.Option(
        None,
        "--previous",
        help="Optional previous-quarter transcript or context file.",
    ),
    prior_context: Path | None = typer.Option(
        None,
        "--prior-context",
        help="Optional pre-call consensus or analyst context file.",
    ),
    history_context: Path | None = typer.Option(
        None,
        "--history-context",
        help="Optional compact historical transcript context JSON.",
    ),
    language: str = typer.Option(
        "en-US",
        "--language",
        help="Language preference for summaries inside the JSON.",
    ),
    self_critique: bool = typer.Option(
        True,
        "--self-critique/--no-self-critique",
        help="Run a self-critique pass after evidence and consistency checks. Uses Haiku by default and Sonnet only for quality issues.",
    ),
) -> None:
    """Run the earnings call analyzer pipeline."""
    try:
        if extract_only:
            result = run_day1_pipeline(pdf_path=pdf_path, output_dir=output, debug=debug)
        else:
            result = run_day2_pipeline(
                pdf_path=pdf_path,
                output_dir=output,
                previous=previous,
                prior_context=prior_context,
                history_context=history_context,
                language=language,
                debug=debug,
                self_critique=self_critique,
            )
    except PdfLoaderError as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc
    except AnthropicClientError as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc
    except AnalysisValidationError as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc
    except ReportWriterError as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc
    except OSError as exc:
        typer.secho(f"Erro de arquivo: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc

    if extract_only:
        typer.secho("Dia 1 concluido com sucesso.", fg=typer.colors.GREEN)
    else:
        typer.secho("Dia 2 concluido com sucesso.", fg=typer.colors.GREEN)

    typer.echo(f"Paginas extraidas: {result.page_count}")
    typer.echo(f"Segmentos gerados: {result.segment_count}")
    typer.echo(f"Texto limpo: {result.clean_text_path}")
    typer.echo(f"Segmentos: {result.segments_path}")
    typer.echo(f"Q&A agrupado: {result.qa_turns_path}")
    if hasattr(result, "analysis_path"):
        typer.echo(f"Analise JSON: {result.analysis_path}")
        typer.echo(f"Relatorio de evidencias: {result.evidence_report_path}")
        typer.echo(f"Relatorio de consistencia: {result.consistency_report_path}")
        typer.echo(f"Metadados da execucao: {result.run_metadata_path}")
        typer.echo(f"Relatorio executivo: {result.executive_report_path}")
        if result.prior_context_path:
            typer.echo(f"Contexto pre-call: {result.prior_context_path}")
        if result.history_context_path:
            typer.echo(f"Contexto historico: {result.history_context_path}")
        typer.echo(f"Modelo principal: {result.analysis_model}")
        if result.self_critique_used:
            typer.echo(f"Self-critique: {result.self_critique_model}")
            if result.self_critique_triggers:
                typer.echo(f"Gatilhos self-critique: {', '.join(result.self_critique_triggers)}")
        typer.echo(f"Tentativas de reparo JSON: {result.repair_attempts}")

    if debug:
        typer.echo(f"PDF: {result.pdf_path}")
        typer.echo(f"Output dir: {result.output_dir}")


if __name__ == "__main__":
    typer.run(main)
