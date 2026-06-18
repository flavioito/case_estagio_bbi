from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


@dataclass(frozen=True)
class Settings:
    project_root: Path
    app_dir: Path
    data_dir: Path
    output_dir: Path
    prompts_dir: Path
    macro_factors_path: Path
    sector_taxonomy_path: Path
    sector_macro_scores_path: Path
    ticker_exposures_path: Path
    anthropic_api_key: str | None
    anthropic_model: str
    max_tokens: int
    parser_max_tokens: int
    report_max_tokens: int
    temperature: float
    report_max_words: int
    top_sectors: int
    top_tickers: int
    risk_count: int
    use_llm_default: bool
    use_llm_report_writer: bool


def load_settings() -> Settings:
    app_dir = Path(__file__).resolve().parent
    project_root = app_dir.parent
    _load_dotenv(project_root / ".env")

    data_dir = app_dir / "data"
    output_dir = app_dir / "output"

    return Settings(
        project_root=project_root,
        app_dir=app_dir,
        data_dir=data_dir,
        output_dir=output_dir,
        prompts_dir=app_dir / "prompts",
        macro_factors_path=data_dir / "macro_factors.yaml",
        sector_taxonomy_path=data_dir / "sector_taxonomy.yaml",
        sector_macro_scores_path=data_dir / "sector_macro_scores.yaml",
        ticker_exposures_path=Path(
            os.getenv("TICKER_EXPOSURES_PATH", data_dir / "curated" / "ticker_exposures_expanded.yaml")
        ),
        anthropic_api_key=os.getenv("ANTHROPIC_API_KEY") or None,
        anthropic_model=os.getenv("ANTHROPIC_MODEL", "claude-haiku-4-5"),
        max_tokens=int(os.getenv("MAX_TOKENS", "1200")),
        parser_max_tokens=int(os.getenv("ANTHROPIC_PARSER_MAX_TOKENS", "800")),
        report_max_tokens=int(os.getenv("ANTHROPIC_REPORT_MAX_TOKENS", "900")),
        temperature=float(os.getenv("TEMPERATURE", "0.2")),
        report_max_words=int(os.getenv("REPORT_MAX_WORDS", "500")),
        top_sectors=int(os.getenv("TOP_SECTORS", "5")),
        top_tickers=int(os.getenv("TOP_TICKERS", "3")),
        risk_count=int(os.getenv("RISK_COUNT", "3")),
        use_llm_default=os.getenv("USE_ANTHROPIC", "false").lower() in {"1", "true", "yes"},
        use_llm_report_writer=os.getenv("ANTHROPIC_WRITE_REPORT", "true").lower() in {"1", "true", "yes"},
    )
