from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.pipeline import run_analysis
from app.schemas import AnalysisOutput, count_words


def test_output_has_required_exact_counts() -> None:
    output = run_analysis("Petróleo em forte alta, real depreciado e risco fiscal elevado.", use_llm=False)

    assert isinstance(output, AnalysisOutput)
    assert len(output.benefited_sectors) == 5
    assert len(output.harmed_sectors) == 5
    assert len(output.short_term_benefited_sectors) == 5
    assert len(output.medium_term_harmed_sectors) == 5
    assert len(output.net_resilient_sectors) == 5
    assert len(output.top_relative_tickers) == 3
    assert len(output.negative_tickers) == 3
    assert len(output.risks) == 3
    assert count_words(output.markdown_report) <= 500


def test_confidence_values_are_valid() -> None:
    output = run_analysis("China desacelerando, minério em queda e aversão a risco em emergentes.", use_llm=False)
    values = [item.confidence for item in output.benefited_sectors + output.harmed_sectors]
    values += [item.confidence for item in output.top_relative_tickers + output.negative_tickers]

    assert set(values) <= {"low", "medium", "high"}


def test_schema_rejects_wrong_sector_count() -> None:
    output = run_analysis("Real forte, commodities em queda, inflação menor e início de ciclo de queda de juros.", use_llm=False)
    data = output.as_json_dict()
    data["benefited_sectors"] = data["benefited_sectors"][:4]

    with pytest.raises(ValidationError):
        AnalysisOutput.model_validate(data)
