from __future__ import annotations

from src.pipeline import (
    apply_surprise_score_policy,
    compact_prior_context_json,
    enrich_analysis_context,
    enrich_analysis_limitations,
    enrich_analysis_metadata,
    enrich_temporal_comparison,
    determine_self_critique_triggers,
    resolve_history_context_path,
    resolve_prior_context_path,
    should_use_sonnet_for_self_critique,
)
from src.schemas import EarningsCallAnalysis


def _minimal_valid_analysis(**overrides: object) -> EarningsCallAnalysis:
    evidence = {
        "quote": "the current context demands prudence",
        "speaker": "Geovanne Tobias",
        "page": 2,
        "rationale": "The speaker explicitly frames the environment as requiring caution.",
    }
    payload = {
        "schema_version": "1.2",
        "company_name": None,
        "ticker": None,
        "quarter": None,
        "call_date": None,
        "management_tone": {
            "classification": "cautious",
            "summary": "Management emphasized prudence and a tougher credit cycle.",
            "evidence": [evidence],
            "confidence": "high",
        },
        "guidance_changes": [],
        "critical_questions": [],
        "red_flags": [],
        "surprise_items": [],
        "consensus_surprises": [],
        "surprise_score_components": {
            "guidance_revision": 20,
            "analyst_pressure": 15,
            "tone_shift": 10,
            "new_material_numbers": 10,
            "external_context_adjustment": 0,
        },
        "transcript_surprise_score": 55,
        "consensus_surprise_score": None,
        "overall_surprise_score": 55,
        "surprise_score_confidence": "medium",
        "analysis_context": {
            "has_prior_quarter_transcript": False,
            "has_external_consensus": False,
            "surprise_score_is_transcript_only": True,
            "surprise_score_cap_applied": False,
        },
        "analysis_limitations": ["No external pre-call consensus file was provided."],
    }
    payload.update(overrides)
    return EarningsCallAnalysis.model_validate(payload)


def test_enrich_analysis_metadata_fills_blank_fields_from_transcript() -> None:
    analysis = _minimal_valid_analysis()
    transcript = (
        "Banco do Brasil S/A (BBAS3) Earnings Webcast 1Q26 Transcription\n"
        "May 14th, 2026\n"
    )

    enriched = enrich_analysis_metadata(
        analysis=analysis,
        full_transcript_text=transcript,
    )

    assert enriched.company_name == "Banco do Brasil"
    assert enriched.ticker == "BBAS3"
    assert enriched.quarter == "1Q26"
    assert enriched.call_date == "May 14th, 2026"


def test_enrich_analysis_limitations_adds_default_context_warnings() -> None:
    analysis = _minimal_valid_analysis(
        analysis_limitations=[
            "No external pre-call consensus or analyst expectations provided.",
            "Model-generated limitation 2.",
            "Model-generated limitation 3.",
            "Model-generated limitation 4.",
            "Model-generated limitation 5.",
        ]
    )

    enriched = enrich_analysis_limitations(
        analysis=analysis,
        has_previous_context=False,
        has_prior_context=False,
    )

    assert "No external pre-call consensus was provided." in enriched.analysis_limitations
    assert "Prior-quarter transcript was not provided." in enriched.analysis_limitations
    assert "Surprise score is inferred from transcript-only signals." in enriched.analysis_limitations
    assert len(enriched.analysis_limitations) == 5
    assert "No external pre-call consensus or analyst expectations provided." not in enriched.analysis_limitations


def test_enrich_analysis_limitations_removes_transcript_only_warning_with_prior_context() -> None:
    analysis = _minimal_valid_analysis(
        analysis_limitations=[
            "Surprise score is inferred from transcript-only signals.",
            "Model-generated limitation.",
        ]
    )

    enriched = enrich_analysis_limitations(
        analysis=analysis,
        has_previous_context=False,
        has_prior_context=True,
    )

    assert "External pre-call consensus was provided; surprise scores reflect comparison to documented pre-call expectations." in enriched.analysis_limitations
    assert "Surprise score is inferred from transcript-only signals." not in enriched.analysis_limitations
    assert "Prior-quarter transcript was not provided." in enriched.analysis_limitations


def test_apply_surprise_score_policy_caps_score_without_prior_context() -> None:
    analysis = _minimal_valid_analysis(
        transcript_surprise_score=85,
        overall_surprise_score=85,
        surprise_score_confidence="high",
        surprise_items=[
            {
                "item": "Guidance revision",
                "score": 82,
                "why_surprising": "The call states that guidance ranges were revised.",
                "evidence": [
                    {
                        "quote": "the current context demands prudence",
                        "speaker": "Geovanne Tobias",
                        "page": 2,
                        "rationale": "The quote supports a surprise assessment.",
                    }
                ],
                "confidence": "high",
                "limitation": "Transcript-only score.",
            }
        ],
    )

    capped = apply_surprise_score_policy(analysis=analysis, has_prior_context=False)

    assert capped.overall_surprise_score == 60
    assert capped.transcript_surprise_score == 60
    assert capped.consensus_surprise_score is None
    assert capped.consensus_surprises == []
    assert capped.surprise_items[0].score == 60
    assert capped.surprise_score_components.external_context_adjustment == 0
    assert capped.surprise_score_confidence == "medium"
    assert any("capped at 60" in item for item in capped.analysis_limitations)


def test_apply_surprise_score_policy_does_not_cap_with_prior_context() -> None:
    analysis = _minimal_valid_analysis(
        transcript_surprise_score=55,
        consensus_surprise_score=85,
        overall_surprise_score=55,
        consensus_surprises=[
            {
                "topic": "Guidance revision",
                "pre_call_expectation": "No major revision expected.",
                "statement_basis": "explicit",
                "call_statement": "Management revised guidance.",
                "surprise_direction": "negative",
                "surprise_magnitude": "high",
                "already_in_consensus": False,
                "confidence": "high",
                "evidence": [
                    {
                        "quote": "the current context demands prudence",
                        "speaker": "Geovanne Tobias",
                        "page": 2,
                        "rationale": "The quote supports a surprise assessment.",
                    }
                ],
            }
        ],
    )

    unchanged = apply_surprise_score_policy(analysis=analysis, has_prior_context=True)

    assert unchanged.overall_surprise_score == 85
    assert unchanged.consensus_surprise_score == 85


def test_apply_surprise_score_policy_removes_stale_cap_limitation_when_not_capped() -> None:
    analysis = _minimal_valid_analysis(
        transcript_surprise_score=55,
        overall_surprise_score=55,
        analysis_limitations=[
            "No external pre-call consensus was provided.",
            "Surprise score was capped at 60 because no external pre-call consensus was provided.",
        ],
    )

    unchanged = apply_surprise_score_policy(analysis=analysis, has_prior_context=False)

    assert unchanged.overall_surprise_score == 55
    assert not any("capped at 60" in item for item in unchanged.analysis_limitations)


def test_enrich_analysis_context_sets_structured_context_flags() -> None:
    analysis = _minimal_valid_analysis()

    enriched = enrich_analysis_context(
        analysis=analysis,
        has_previous_context=False,
        has_prior_context=False,
    )

    assert enriched.analysis_context.has_prior_quarter_transcript is False
    assert enriched.analysis_context.has_external_consensus is False
    assert enriched.analysis_context.surprise_score_is_transcript_only is True
    assert enriched.analysis_context.has_historical_context is False


def test_enrich_analysis_context_tracks_history_context() -> None:
    analysis = _minimal_valid_analysis()

    enriched = enrich_analysis_context(
        analysis=analysis,
        has_previous_context=False,
        has_prior_context=False,
        has_history_context=True,
    )

    assert enriched.analysis_context.has_historical_context is True


def test_enrich_analysis_metadata_does_not_overwrite_existing_fields() -> None:
    analysis = _minimal_valid_analysis(
        company_name="Banco do Brasil",
        ticker="CUSTOM3",
        quarter="Q1 2026",
        call_date="2026-05-14",
    )
    transcript = "Banco do Brasil S/A (BBAS3) Earnings Webcast 1Q26 May 14th, 2026"

    enriched = enrich_analysis_metadata(
        analysis=analysis,
        full_transcript_text=transcript,
    )

    assert enriched.ticker == "CUSTOM3"
    assert enriched.quarter == "Q1 2026"
    assert enriched.call_date == "2026-05-14"


def test_enrich_analysis_metadata_uses_source_filename_when_pdf_text_lacks_header() -> None:
    analysis = _minimal_valid_analysis()
    transcript = "Good morning. I am Head of Investor Relations at Banco do Brasil."

    enriched = enrich_analysis_metadata(
        analysis=analysis,
        full_transcript_text=transcript,
        source_text="Transcript - Videoconference - 1Q26 (BBAS3).pdf",
    )

    assert enriched.company_name == "Banco do Brasil"
    assert enriched.ticker == "BBAS3"
    assert enriched.quarter == "1Q26"
    assert enriched.call_date is None


def test_enrich_analysis_metadata_uses_raw_pdf_metadata_for_call_date() -> None:
    analysis = _minimal_valid_analysis()
    transcript = "Good morning. I am Head of Investor Relations at Banco do Brasil."
    raw_pdf_metadata = (
        "Transcript - Videoconference - 1Q26 (BBAS3).pdf\n"
        "title: Banco do Brasil 1Q26 Earnings Call\n"
        "subject: May 14th, 2026"
    )

    enriched = enrich_analysis_metadata(
        analysis=analysis,
        full_transcript_text=transcript,
        source_text=raw_pdf_metadata,
    )

    assert enriched.ticker == "BBAS3"
    assert enriched.quarter == "1Q26"
    assert enriched.call_date == "May 14th, 2026"


def test_compact_prior_context_json_keeps_surprise_inputs_and_drops_backtesting_actuals() -> None:
    raw = """
    {
      "document_title": "BBAS3 pre-call",
      "known_before_call": ["Agro stress was expected."],
      "unknown_before_call": ["Magnitude of guidance revision."],
      "expected_vs_surprise_framework": [
        {"topic": "Cost of credit", "what_would_be_surprising": "Above R$60bn"}
      ],
      "materiality_weights": {"guidance_revision": 0.3},
      "prior_formal_guidance": {"cost_of_credit_2026_brl_bn": [53, 58]},
      "pre_call_estimates_and_actuals": [
        {
          "metric": "adjusted_net_income_brl_bn",
          "estimate": 3.5,
          "actual": 3.4,
          "surprise_pct": -2.8,
          "within_range": true
        }
      ],
      "surprise_interpretation_rules": [
        {"guidance": "Revised from R$22-26bn to R$18-22bn."}
      ],
      "post_result_actuals_for_backtesting": {"cost_of_credit_2026_brl_bn": [65, 70]}
    }
    """

    compacted = compact_prior_context_json(raw)

    assert "known_before_call" in compacted
    assert "expected_vs_surprise_framework" in compacted
    assert "prior_formal_guidance" in compacted
    assert "post_result_actuals_for_backtesting" not in compacted
    assert '"actual"' not in compacted
    assert "surprise_pct" not in compacted
    assert "within_range" not in compacted
    assert "R$18-22bn" not in compacted
    assert "Do not treat post-result actuals as pre-call expectations" in compacted
    assert "Do not copy post-result/new guidance ranges into call_statement" in compacted


def test_resolve_prior_context_path_finds_matching_consensus_in_data_dir(tmp_path, monkeypatch) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    pdf_path = data_dir / "Transcript - Videoconference - 1Q26 (BBAS3).pdf"
    pdf_path.write_text("placeholder", encoding="utf-8")
    consensus = data_dir / "BBAS3_1Q26_pre_call_consensus.json"
    consensus.write_text("{}", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    resolved = resolve_prior_context_path(
        explicit_path=None,
        pdf_path=pdf_path,
        transcript_text="Banco do Brasil (BBAS3) 1Q26",
    )

    assert resolved == consensus


def test_resolve_history_context_path_finds_matching_context_dir_file(tmp_path, monkeypatch) -> None:
    data_dir = tmp_path / "data"
    context_dir = tmp_path / "context"
    data_dir.mkdir()
    context_dir.mkdir()
    pdf_path = data_dir / "Transcript - Videoconference - 1Q26 (BBAS3).pdf"
    pdf_path.write_text("placeholder", encoding="utf-8")
    history = context_dir / "BBAS3_history_context.json"
    history.write_text("{}", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    resolved = resolve_history_context_path(
        explicit_path=None,
        pdf_path=pdf_path,
        transcript_text="Banco do Brasil (BBAS3) 1Q26",
    )

    assert resolved == history


def test_explicit_context_paths_take_precedence(tmp_path) -> None:
    explicit = tmp_path / "custom_context.json"
    explicit.write_text("{}", encoding="utf-8")
    pdf_path = tmp_path / "Transcript - Videoconference - 1Q26 (BBAS3).pdf"

    assert (
        resolve_prior_context_path(
            explicit_path=explicit,
            pdf_path=pdf_path,
            transcript_text="Banco do Brasil (BBAS3) 1Q26",
        )
        == explicit
    )
    assert (
        resolve_history_context_path(
            explicit_path=explicit,
            pdf_path=pdf_path,
            transcript_text="Banco do Brasil (BBAS3) 1Q26",
        )
        == explicit
    )


def test_enrich_temporal_comparison_fills_conservative_fallback_from_history() -> None:
    analysis = _minimal_valid_analysis(
        guidance_changes=[
            {
                "topic": "Cost of credit",
                "metric_direction": "increased",
                "investment_implication": "negative",
                "statement_basis": "explicit",
                "current_statement": "Management linked the revision to credit deterioration.",
                "previous_reference": None,
                "evidence": [
                    {
                        "quote": "the current context demands prudence",
                        "speaker": "Geovanne Tobias",
                        "page": 2,
                        "rationale": "The quote supports a cautious tone assessment.",
                    }
                ],
                "confidence": "high",
            }
        ],
    )
    history_context = """
    Compacted historical transcript context JSON:
    {
      "quarters": [
        {"quarter": "4Q25", "management_tone_hint": "cautious"}
      ],
      "historical_patterns": {
        "recurring_topics": ["provisions_cost_of_credit", "capital"]
      }
    }
    """

    enriched = enrich_temporal_comparison(
        analysis=analysis,
        history_context_text=history_context,
    )

    assert enriched.temporal_comparison.recurring_topics == ["Cost of credit"]
    assert "Current tone was cautious" in (enriched.temporal_comparison.tone_change or "")


def test_self_critique_uses_haiku_path_when_quality_reports_are_clean() -> None:
    evidence_report = {"summary": {"valid_quote_rate": 0.95}}
    consistency_report = {"summary": {"high": 0, "medium": 0, "low": 1}}

    triggers = determine_self_critique_triggers(
        evidence_report=evidence_report,
        consistency_report=consistency_report,
    )

    assert triggers == ["routine_haiku_self_critique"]
    assert not should_use_sonnet_for_self_critique(
        evidence_report=evidence_report,
        consistency_report=consistency_report,
    )


def test_self_critique_escalates_to_sonnet_for_medium_or_high_consistency_issues() -> None:
    evidence_report = {"summary": {"valid_quote_rate": 0.95}}
    consistency_report = {"summary": {"high": 0, "medium": 1, "low": 0}}

    triggers = determine_self_critique_triggers(
        evidence_report=evidence_report,
        consistency_report=consistency_report,
    )

    assert "consistency_medium" in triggers
    assert should_use_sonnet_for_self_critique(
        evidence_report=evidence_report,
        consistency_report=consistency_report,
    )


def test_self_critique_escalates_to_sonnet_when_valid_quote_rate_is_low() -> None:
    evidence_report = {"summary": {"valid_quote_rate": 0.89}}
    consistency_report = {"summary": {"high": 0, "medium": 0, "low": 0}}

    triggers = determine_self_critique_triggers(
        evidence_report=evidence_report,
        consistency_report=consistency_report,
    )

    assert "valid_quote_rate_below_0_90" in triggers
    assert should_use_sonnet_for_self_critique(
        evidence_report=evidence_report,
        consistency_report=consistency_report,
    )
