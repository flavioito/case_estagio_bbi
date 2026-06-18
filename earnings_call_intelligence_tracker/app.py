from __future__ import annotations

import json
import textwrap
import tempfile
from datetime import datetime
from html import escape
from pathlib import Path
from typing import Any

import streamlit as st

from src.anthropic_client import AnthropicClientError
from src.config import get_settings
from src.pdf_loader import PdfLoaderError
from src.pipeline import AnalysisValidationError, run_day1_pipeline, run_day2_pipeline
from src.report_writer import ReportWriterError


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_OUTPUT_DIR = BASE_DIR / "output"
EXPECTED_FILES = [
    "analysis.json",
    "evidence_report.json",
    "consistency_report.json",
    "run_metadata.json",
    "executive_report.md",
    "clean_text.txt",
    "transcript_segments.json",
    "qa_turns.json",
]


def main() -> None:
    st.set_page_config(
        page_title="Earnings Call Intelligence Tracker",
        layout="centered",
        initial_sidebar_state="collapsed",
    )
    _apply_style()
    _render_upload_landing()

    if st.session_state.get("show_report_modal"):
        _show_executive_report_dialog()


def _render_upload_landing() -> None:
    st.markdown(
        """
        <div class="landing-shell">
            <h1>Earnings Call Intelligence Tracker</h1>
        </div>
        """,
        unsafe_allow_html=True,
    )

    with st.container(border=True):
        st.markdown(
            """
            <div class="upload-heading">
                <div class="upload-title">Insert the Transcript of Earnings Call in PDF format.</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        with st.form("transcript_upload_form", clear_on_submit=False):
            transcript_pdf = st.file_uploader(
                "Arquivo de transcricao",
                type=["pdf"],
                accept_multiple_files=False,
                label_visibility="collapsed",
            )
            confirmed = st.form_submit_button("Confirmar", type="primary", width="stretch")

    if confirmed:
        _run_transcript_summary(transcript_pdf)


def _run_transcript_summary(uploaded_file: Any) -> None:
    if uploaded_file is None:
        st.error("Insira o arquivo de transcricao antes de confirmar.")
        return

    settings = get_settings()
    if not settings.anthropic_api_key:
        st.error("ANTHROPIC_API_KEY nao configurada. Configure a chave antes de gerar o resumo.")
        return

    output_dir = DEFAULT_OUTPUT_DIR / f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    output_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="earnings_call_streamlit_") as temp_root:
        temp_dir = Path(temp_root)
        pdf_path = _save_uploaded_file(uploaded_file, temp_dir)

        try:
            with st.status("Gerando resumo da transcrição", expanded=True) as status:
                st.write("Extraindo a transcrição do PDF.")
                st.write("Analisando evidências e montando o relatório executivo.")
                result = run_day2_pipeline(
                    pdf_path=pdf_path,
                    output_dir=output_dir,
                    previous=None,
                    prior_context=None,
                    language="en-US",
                    debug=False,
                    self_critique=True,
                )
                status.update(label="Resumo gerado com sucesso.", state="complete")
        except (
            PdfLoaderError,
            AnthropicClientError,
            AnalysisValidationError,
            ReportWriterError,
            OSError,
        ) as exc:
            st.error(str(exc))
            return
        except Exception as exc:  # pragma: no cover - UI guardrail
            st.exception(exc)
            return

    report = _read_text(result.executive_report_path)
    st.session_state["last_output_dir"] = str(result.output_dir)
    st.session_state["executive_report_text"] = report or "Relatorio executivo nao encontrado."
    st.session_state["show_report_modal"] = True
    st.rerun()


@st.dialog("Relatório Executivo", width="large", dismissible=False)
def _show_executive_report_dialog() -> None:
    report = st.session_state.get("executive_report_text", "")
    output_dir = st.session_state.get("last_output_dir")
    output_path = Path(output_dir) if output_dir else None
    analysis = _load_json(output_path / "analysis.json") if output_path else None
    evidence_report = _load_json(output_path / "evidence_report.json") if output_path else None
    transcript_segments = _load_json(output_path / "transcript_segments.json") if output_path else None

    report_tab, citations_tab = st.tabs(["Relatório Executivo", "Citation Tracking"])

    with report_tab:
        st.markdown(report)
        if output_dir:
            pdf_bytes = _build_executive_report_pdf(report)
            st.download_button(
                "Baixar relatório executivo em PDF",
                data=pdf_bytes,
                file_name="executive_report.pdf",
                mime="application/pdf",
                width="stretch",
                key="modal_download_executive_report_pdf",
            )

    with citations_tab:
        _render_citation_tracking(
            analysis if isinstance(analysis, dict) else None,
            evidence_report if isinstance(evidence_report, dict) else None,
            transcript_segments if isinstance(transcript_segments, list) else None,
            key_prefix="modal",
        )

    st.divider()

    if st.button("Fechar", width="stretch"):
        st.session_state["show_report_modal"] = False
        st.rerun()


def _render_sidebar() -> dict[str, Any]:
    st.sidebar.markdown('<div class="sidebar-brand">Earnings Call Analyzer</div>', unsafe_allow_html=True)
    st.sidebar.markdown('<div class="sidebar-step">1. Main Transcript (PDF)</div>', unsafe_allow_html=True)
    transcript_pdf = st.sidebar.file_uploader(
        "Transcript PDF",
        type=["pdf"],
        label_visibility="collapsed",
    )
    st.sidebar.markdown('<div class="sidebar-step">2. Previous Quarter (Optional)</div>', unsafe_allow_html=True)
    previous_file = st.sidebar.file_uploader(
        "Trimestre anterior ou contexto",
        type=["pdf", "txt", "md"],
        label_visibility="collapsed",
    )
    st.sidebar.markdown('<div class="sidebar-step">3. Pre-Call Consensus (Optional)</div>', unsafe_allow_html=True)
    prior_context_file = st.sidebar.file_uploader(
        "Consenso pre-call",
        type=["pdf", "json", "txt", "md"],
        label_visibility="collapsed",
    )

    st.sidebar.markdown('<div class="sidebar-step">4. Mode</div>', unsafe_allow_html=True)
    mode = st.sidebar.radio(
        "Modo",
        ["Analise completa", "Extracao somente"],
        horizontal=False,
        label_visibility="collapsed",
    )
    language = st.sidebar.selectbox("Idioma do JSON", ["en-US", "pt-BR"], index=0)
    output_dir = st.sidebar.text_input("Pasta de saida", value="output")
    use_timestamp = st.sidebar.checkbox("Criar subpasta com timestamp", value=True)
    debug = st.sidebar.checkbox("Debug", value=False)
    self_critique = st.sidebar.checkbox("Self-critique loop", value=True)

    settings = get_settings()
    if mode == "Analise completa" and not settings.anthropic_api_key:
        st.sidebar.warning("ANTHROPIC_API_KEY nao configurada.")

    run_clicked = st.sidebar.button("Executar", type="primary", width="stretch")

    st.sidebar.markdown('<div class="sidebar-step subtle-step">Results</div>', unsafe_allow_html=True)
    existing_output_dir = st.sidebar.text_input("Abrir pasta existente", value="output")
    load_existing_clicked = st.sidebar.button("Carregar resultados", width="stretch")

    return {
        "transcript_pdf": transcript_pdf,
        "previous_file": previous_file,
        "prior_context_file": prior_context_file,
        "mode": mode,
        "language": language,
        "output_dir": output_dir,
        "use_timestamp": use_timestamp,
        "debug": debug,
        "self_critique": self_critique,
        "run_clicked": run_clicked,
        "existing_output_dir": existing_output_dir,
        "load_existing_clicked": load_existing_clicked,
    }


def _run_analysis(controls: dict[str, Any]) -> None:
    if controls["transcript_pdf"] is None:
        st.error("Envie um PDF de transcricao antes de executar.")
        return

    output_dir = _build_run_output_dir(
        controls["output_dir"],
        use_timestamp=controls["use_timestamp"],
    )
    output_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="earnings_call_streamlit_") as temp_root:
        temp_dir = Path(temp_root)
        pdf_path = _save_uploaded_file(controls["transcript_pdf"], temp_dir)
        previous_path = _save_optional_file(controls["previous_file"], temp_dir)
        prior_context_path = _save_optional_file(controls["prior_context_file"], temp_dir)

        try:
            with st.status("Executando pipeline...", expanded=True) as status:
                st.write("Lendo PDF e segmentando transcript.")
                if controls["mode"] == "Extracao somente":
                    result = run_day1_pipeline(
                        pdf_path=pdf_path,
                        output_dir=output_dir,
                        debug=controls["debug"],
                    )
                else:
                    st.write("Gerando JSON analitico e validando evidencias.")
                    result = run_day2_pipeline(
                        pdf_path=pdf_path,
                        output_dir=output_dir,
                        previous=previous_path,
                        prior_context=prior_context_path,
                        language=controls["language"],
                        debug=controls["debug"],
                        self_critique=controls["self_critique"],
                    )
                status.update(label="Pipeline concluido.", state="complete")
        except (
            PdfLoaderError,
            AnthropicClientError,
            AnalysisValidationError,
            ReportWriterError,
            OSError,
        ) as exc:
            st.error(str(exc))
            return
        except Exception as exc:  # pragma: no cover - UI guardrail
            st.exception(exc)
            return

    st.session_state["last_output_dir"] = str(result.output_dir)
    st.success(f"Resultado salvo em {result.output_dir}")


def _render_main(output_dir: Path) -> None:
    analysis = _load_json(output_dir / "analysis.json")
    evidence_report = _load_json(output_dir / "evidence_report.json")
    consistency_report = _load_json(output_dir / "consistency_report.json")
    metadata = _load_json(output_dir / "run_metadata.json")
    transcript_segments = _load_json(output_dir / "transcript_segments.json")
    executive_report = _read_text(output_dir / "executive_report.md")

    _render_app_header(output_dir, analysis, metadata)

    _render_metrics(analysis, evidence_report, metadata, output_dir)

    report_tab, summary_tab, evidence_tab, files_tab, logs_tab = st.tabs(
        ["Executive Report", "Analysis Summary", "Evidence Audit", "Files", "Logs"]
    )

    with report_tab:
        _render_report_tab(executive_report, output_dir, analysis, evidence_report, consistency_report)

    with summary_tab:
        _render_summary_tab(analysis)

    with evidence_tab:
        _render_evidence_tab(
            evidence_report if isinstance(evidence_report, dict) else None,
            analysis if isinstance(analysis, dict) else None,
            transcript_segments if isinstance(transcript_segments, list) else None,
        )

    with files_tab:
        _render_files_tab(output_dir)

    with logs_tab:
        _render_logs_tab(metadata, consistency_report)


def _render_metrics(
    analysis: dict[str, Any] | None,
    evidence_report: dict[str, Any] | None,
    metadata: dict[str, Any] | None,
    output_dir: Path,
) -> None:
    evidence_summary = (evidence_report or {}).get("summary", {})
    pages = _display_value((metadata or {}).get("page_count"))
    segments = _display_value((metadata or {}).get("segment_count"))
    valid_rate = _format_pct(evidence_summary.get("valid_quote_rate"))
    score = _display_value((analysis or metadata or {}).get("overall_surprise_score"))

    cols = st.columns(4)
    with cols[0]:
        _metric_card("Paginas", pages, "PDF extraido")
    with cols[1]:
        _metric_card("Segmentos", segments, "Blocos de fala")
    with cols[2]:
        _metric_card("Evidencias", valid_rate, "Quotes validas")
    with cols[3]:
        _metric_card("Surprise score", score, "0 a 100")

    if not output_dir.exists() or not any((output_dir / name).exists() for name in EXPECTED_FILES):
        st.info("Envie um transcript PDF pela sidebar ou carregue uma pasta de resultados existente.")


def _render_app_header(
    output_dir: Path,
    analysis: dict[str, Any] | None,
    metadata: dict[str, Any] | None,
) -> None:
    has_results = any((output_dir / name).exists() for name in EXPECTED_FILES)
    status_label = "Completed" if has_results else "Ready"
    status_class = "status-ok" if has_results else "status-idle"
    mode = "Full Analysis" if analysis else "Extraction"
    language = "English" if not metadata else metadata.get("language", "English")
    run_time = _display_value((metadata or {}).get("source_pdf"))
    if run_time != "-":
        run_time = Path(run_time).name

    st.markdown(
        f"""
        <div class="top-chrome">
            <div>Earnings Call Analyzer <span>v1.0.0</span></div>
            <div class="top-actions">Runs&nbsp;&nbsp; Settings</div>
        </div>
        <div class="hero-row">
            <div>
                <h1>Earnings Call Analyzer</h1>
                <div class="run-meta">
                    <span>{escape(run_time)}</span>
                    <span class="dot"></span>
                    <span class="status-pill {status_class}">{status_label}</span>
                    <span class="dot"></span>
                    <span>Mode: {escape(mode)}</span>
                    <span class="dot"></span>
                    <span>Language: {escape(str(language))}</span>
                </div>
            </div>
            <div class="output-path">{escape(str(output_dir))}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_report_tab(
    report: str | None,
    output_dir: Path,
    analysis: dict[str, Any] | None,
    evidence_report: dict[str, Any] | None,
    consistency_report: dict[str, Any] | None,
) -> None:
    if not report:
        st.empty()
        return

    left, right = st.columns([1.55, 1], gap="large")
    with left:
        with st.container(border=True):
            st.markdown(report)
            _download_button(
                output_dir / "executive_report.md",
                "Baixar Executive Report",
                key_prefix="report",
            )
    with right:
        _render_score_card(analysis)
        _render_quality_card(evidence_report, consistency_report)
        _render_context_card(analysis)


def _render_summary_tab(analysis: dict[str, Any] | None) -> None:
    if not analysis:
        st.empty()
        return

    meta_cols = st.columns(4)
    meta_cols[0].metric("Empresa", _display_value(analysis.get("company_name")))
    meta_cols[1].metric("Ticker", _display_value(analysis.get("ticker")))
    meta_cols[2].metric("Periodo", _display_value(analysis.get("quarter")))
    meta_cols[3].metric("Tom", _display_value((analysis.get("management_tone") or {}).get("classification")))

    tone = analysis.get("management_tone") or {}
    if tone.get("summary"):
        st.subheader("Management tone")
        st.write(tone["summary"])

    st.subheader("Guidance changes")
    _dataframe(_guidance_rows(analysis.get("guidance_changes", [])))

    st.subheader("Critical questions")
    _dataframe(_question_rows(analysis.get("critical_questions", [])))

    st.subheader("Red flags")
    _dataframe(_red_flag_rows(analysis.get("red_flags", [])))

    st.subheader("Surprise items")
    _dataframe(_surprise_rows(analysis.get("surprise_items", [])))

    limitations = analysis.get("analysis_limitations") or []
    if limitations:
        st.subheader("Limitations")
        for item in limitations:
            st.markdown(f"- {item}")


def _render_evidence_tab(
    evidence_report: dict[str, Any] | None,
    analysis: dict[str, Any] | None = None,
    transcript_segments: list[dict[str, Any]] | None = None,
) -> None:
    if not evidence_report:
        st.empty()
        return

    summary = evidence_report.get("summary", {})
    cols = st.columns(4)
    cols[0].metric("Total quotes", _display_value(summary.get("total_quotes")))
    cols[1].metric("Quotes validas", _display_value(summary.get("valid_quotes")))
    cols[2].metric("Quotes invalidas", _display_value(summary.get("invalid_quotes")))
    cols[3].metric("Speaker match", _format_pct(summary.get("speaker_valid_quote_rate")))

    _render_citation_tracking(
        analysis,
        evidence_report,
        transcript_segments,
        key_prefix="evidence_tab",
    )

    invalid_quotes = evidence_report.get("invalid_quotes") or []
    if invalid_quotes:
        with st.expander("Invalid quotes", expanded=False):
            _dataframe(invalid_quotes)

    with st.expander("All quotes", expanded=False):
        _dataframe(_evidence_rows(evidence_report.get("all_quotes", [])))

    warnings = evidence_report.get("warnings") or []
    if warnings:
        st.subheader("Warnings")
        for warning in warnings:
            st.warning(warning)


def _render_files_tab(output_dir: Path) -> None:
    st.subheader("Arquivos gerados")
    rows = []
    for name in EXPECTED_FILES:
        path = output_dir / name
        rows.append(
            {
                "file": name,
                "exists": path.exists(),
                "size_kb": round(path.stat().st_size / 1024, 1) if path.exists() else None,
            }
        )
    _dataframe(rows)

    for name in EXPECTED_FILES:
        _download_button(output_dir / name, f"Baixar {name}", key_prefix="files")


def _render_logs_tab(
    metadata: dict[str, Any] | None,
    consistency_report: dict[str, Any] | None,
) -> None:
    if metadata:
        st.subheader("Run metadata")
        st.json(metadata)
    if consistency_report:
        st.subheader("Consistency report")
        summary = consistency_report.get("summary", {})
        if summary:
            st.metric("Passed", str(summary.get("passed")))
        st.json(consistency_report)
    if not metadata and not consistency_report:
        st.empty()


def _render_score_card(analysis: dict[str, Any] | None) -> None:
    if not analysis:
        return

    components = analysis.get("surprise_score_components") or {}
    rows = [
        ("Guidance revision", components.get("guidance_revision")),
        ("Analyst pressure", components.get("analyst_pressure")),
        ("Tone shift", components.get("tone_shift")),
        ("New material numbers", components.get("new_material_numbers")),
        ("External adjustment", components.get("external_context_adjustment")),
    ]
    st.markdown('<div class="side-card-title">Surprise Score Breakdown</div>', unsafe_allow_html=True)
    with st.container(border=True):
        st.metric(
            "Total Surprise Score",
            _display_value(analysis.get("overall_surprise_score")),
            help="Score consolidado pelo pipeline.",
        )
        _dataframe(
            [
                {"category": label, "score": _display_value(value)}
                for label, value in rows
            ]
        )


def _render_quality_card(
    evidence_report: dict[str, Any] | None,
    consistency_report: dict[str, Any] | None,
) -> None:
    evidence_summary = (evidence_report or {}).get("summary", {})
    consistency_summary = (consistency_report or {}).get("summary", {})
    st.markdown('<div class="side-card-title">Run Quality</div>', unsafe_allow_html=True)
    with st.container(border=True):
        cols = st.columns(2)
        cols[0].metric("Evidence", _format_pct(evidence_summary.get("valid_quote_rate")))
        cols[1].metric("Consistency", "Pass" if consistency_summary.get("passed") else "-")
        st.caption(
            f"{_display_value(evidence_summary.get('valid_quotes'))} valid quotes, "
            f"{_display_value(evidence_summary.get('invalid_quotes'))} invalid."
        )


def _render_context_card(analysis: dict[str, Any] | None) -> None:
    if not analysis:
        return

    context = analysis.get("analysis_context") or {}
    tone = analysis.get("management_tone") or {}
    st.markdown('<div class="side-card-title">Management Tone</div>', unsafe_allow_html=True)
    with st.container(border=True):
        st.metric("Tone", _display_value(tone.get("classification")))
        st.caption(
            "Consensus context: "
            + ("provided" if context.get("has_external_consensus") else "not provided")
        )


def _guidance_rows(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "topic": item.get("topic"),
            "direction": item.get("metric_direction"),
            "implication": item.get("investment_implication"),
            "basis": item.get("statement_basis"),
            "confidence": item.get("confidence"),
            "statement": item.get("current_statement"),
        }
        for item in items
    ]


def _question_rows(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "analyst": item.get("analyst"),
            "institution": item.get("institution"),
            "topic": item.get("topic"),
            "answer_quality": item.get("answer_quality"),
            "confidence": item.get("confidence"),
            "response": item.get("management_response_summary"),
        }
        for item in items
    ]


def _red_flag_rows(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "type": item.get("type"),
            "severity": item.get("severity"),
            "confidence": item.get("confidence"),
            "speaker": item.get("speaker"),
            "quote_validated": item.get("evidence_validated"),
            "explanation": item.get("explanation"),
        }
        for item in items
    ]


def _surprise_rows(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "item": item.get("item"),
            "score": item.get("score"),
            "confidence": item.get("confidence"),
            "why_surprising": item.get("why_surprising"),
            "limitation": item.get("limitation"),
        }
        for item in items
    ]


def _evidence_rows(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "path": item.get("path"),
            "speaker": item.get("speaker"),
            "quote_validated": item.get("evidence_validated"),
            "speaker_validated": item.get("speaker_validated"),
            "match_type": item.get("match_type"),
            "match_score": item.get("match_score"),
            "quote": item.get("quote"),
        }
        for item in items
    ]


def _render_citation_tracking(
    analysis: dict[str, Any] | None,
    evidence_report: dict[str, Any] | None,
    transcript_segments: list[dict[str, Any]] | None,
    *,
    key_prefix: str,
) -> None:
    entries = _citation_entries(analysis, evidence_report)
    if not entries:
        st.caption("Nenhuma citacao validada foi encontrada nos arquivos de saida.")
        return

    section_options = ["All"] + sorted({entry["section"] for entry in entries})
    controls = st.columns([1.35, 1])
    selected_section = controls[0].selectbox(
        "Section",
        section_options,
        key=f"{key_prefix}_citation_section",
    )
    invalid_only = controls[1].checkbox(
        "Show only issues",
        value=False,
        key=f"{key_prefix}_citation_issues",
    )

    filtered_entries = entries
    if selected_section != "All":
        filtered_entries = [entry for entry in filtered_entries if entry["section"] == selected_section]
    if invalid_only:
        filtered_entries = [
            entry
            for entry in filtered_entries
            if _citation_status(entry)["kind"] in {"bad", "warn", "muted"}
        ]

    status_counts = {"ok": 0, "bad": 0, "warn": 0, "muted": 0}
    for entry in entries:
        status_counts[_citation_status(entry)["kind"]] += 1

    metric_cols = st.columns(4)
    metric_cols[0].metric("Validated", str(status_counts["ok"]))
    metric_cols[1].metric("Invalid", str(status_counts["bad"]))
    metric_cols[2].metric("Speaker issues", str(status_counts["warn"]))
    metric_cols[3].metric("Unchecked", str(status_counts["muted"]))

    lookup = _segment_lookup(transcript_segments or [])
    for index, entry in enumerate(filtered_entries):
        _render_citation_card(entry, lookup, key=f"{key_prefix}_citation_{index}")

    if not filtered_entries:
        st.caption("Nenhuma citacao corresponde aos filtros selecionados.")


def _render_citation_card(
    entry: dict[str, Any],
    segment_lookup: dict[str, dict[str, Any]],
    *,
    key: str,
) -> None:
    status = _citation_status(entry)
    quote = _clip_display_text(entry.get("quote") or "", limit=700)
    title = entry.get("title") or entry.get("path") or "Citation"
    speaker = _display_value(entry.get("speaker"))
    page = _display_value(entry.get("page"))
    match_type = _display_value(entry.get("match_type"))
    score = entry.get("match_score")
    score_text = f"{float(score):.2f}" if isinstance(score, (int, float)) else "-"

    st.markdown(
        f"""
        <div class="citation-card">
            <div class="citation-card-head">
                <span class="citation-section">{escape(str(entry.get("section") or "Evidence"))}</span>
                <span class="citation-badge citation-{status["kind"]}">{escape(status["label"])}</span>
            </div>
            <div class="citation-title">{escape(str(title))}</div>
            <div class="citation-meta">
                Speaker: {escape(speaker)} | Page: {escape(page)} | Match: {escape(match_type)} | Score: {escape(score_text)}
            </div>
            <div class="citation-quote">{escape(str(quote))}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    source_ids = [block_id for block_id in entry.get("source_block_ids", []) if block_id in segment_lookup]
    if source_ids:
        with st.expander("Source transcript blocks", expanded=False):
            for block_id in source_ids:
                segment = segment_lookup[block_id]
                pages = _segment_page_range(segment)
                segment_speaker = _display_value(segment.get("speaker"))
                role_title = _display_value(segment.get("role_title"))
                st.markdown(f"**{block_id} | {segment_speaker} | {role_title} | pages {pages}**")
                st.write(_clip_display_text(segment.get("text") or "", limit=1200))
    elif entry.get("matched_text"):
        with st.expander("Matched transcript text", expanded=False):
            st.write(_clip_display_text(entry.get("matched_text") or "", limit=1200))
    elif status["kind"] in {"bad", "muted"}:
        st.caption("Sem bloco de origem validado para esta citacao.")


def _citation_entries(
    analysis: dict[str, Any] | None,
    evidence_report: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    if not analysis:
        return _fallback_citation_entries(evidence_report)

    evidence_by_path = {
        item.get("path"): item
        for item in (evidence_report or {}).get("all_quotes", [])
        if isinstance(item, dict) and item.get("path")
    }
    entries: list[dict[str, Any]] = []

    tone = analysis.get("management_tone") or {}
    _extend_evidence_entries(
        entries,
        "Management tone",
        f"Tone: {_display_value(tone.get('classification'))}",
        tone.get("evidence") or [],
        "management_tone.evidence",
        evidence_by_path,
    )

    for index, item in enumerate(analysis.get("guidance_changes") or []):
        _extend_evidence_entries(
            entries,
            "Guidance changes",
            item.get("topic") or f"Guidance change {index + 1}",
            item.get("evidence") or [],
            f"guidance_changes[{index}].evidence",
            evidence_by_path,
        )

    for index, item in enumerate(analysis.get("critical_questions") or []):
        analyst = item.get("analyst") or "Analyst"
        institution = item.get("institution")
        title = f"{item.get('topic') or analyst} - {analyst}"
        if institution:
            title = f"{title} ({institution})"
        _extend_evidence_entries(
            entries,
            "Critical questions",
            title,
            item.get("evidence") or [],
            f"critical_questions[{index}].evidence",
            evidence_by_path,
        )

    for index, item in enumerate(analysis.get("red_flags") or []):
        path = f"red_flags[{index}]"
        entries.append(_normalize_citation_entry("Red flags", item.get("speaker") or "Red flag", item, path, evidence_by_path))

    for index, item in enumerate(analysis.get("surprise_items") or []):
        _extend_evidence_entries(
            entries,
            "Surprise items",
            item.get("item") or f"Surprise item {index + 1}",
            item.get("evidence") or [],
            f"surprise_items[{index}].evidence",
            evidence_by_path,
        )

    for index, item in enumerate(analysis.get("consensus_surprises") or []):
        _extend_evidence_entries(
            entries,
            "Consensus surprises",
            item.get("topic") or f"Consensus surprise {index + 1}",
            item.get("evidence") or [],
            f"consensus_surprises[{index}].evidence",
            evidence_by_path,
        )

    seen_paths: set[str] = set()
    deduped: list[dict[str, Any]] = []
    for entry in entries:
        path = entry.get("path")
        if path and path in seen_paths:
            continue
        if path:
            seen_paths.add(path)
        deduped.append(entry)
    return deduped


def _extend_evidence_entries(
    entries: list[dict[str, Any]],
    section: str,
    title: str,
    evidence_items: list[dict[str, Any]],
    path_prefix: str,
    evidence_by_path: dict[str, dict[str, Any]],
) -> None:
    for index, evidence in enumerate(evidence_items):
        if isinstance(evidence, dict):
            entries.append(
                _normalize_citation_entry(
                    section,
                    title,
                    evidence,
                    f"{path_prefix}[{index}]",
                    evidence_by_path,
                )
            )


def _normalize_citation_entry(
    section: str,
    title: str,
    evidence: dict[str, Any],
    path: str,
    evidence_by_path: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    report_match = evidence_by_path.get(path, {})
    merged = {**evidence, **report_match}
    merged["section"] = section
    merged["title"] = title
    merged["path"] = path
    return merged


def _fallback_citation_entries(evidence_report: dict[str, Any] | None) -> list[dict[str, Any]]:
    entries = []
    for item in (evidence_report or {}).get("all_quotes", []):
        if not isinstance(item, dict):
            continue
        path = item.get("path") or "evidence"
        entries.append(
            {
                **item,
                "section": _section_from_evidence_path(path),
                "title": path,
            }
        )
    return entries


def _section_from_evidence_path(path: str) -> str:
    if path.startswith("management_tone"):
        return "Management tone"
    if path.startswith("guidance_changes"):
        return "Guidance changes"
    if path.startswith("critical_questions"):
        return "Critical questions"
    if path.startswith("red_flags"):
        return "Red flags"
    if path.startswith("surprise_items"):
        return "Surprise items"
    if path.startswith("consensus_surprises"):
        return "Consensus surprises"
    return "Evidence"


def _citation_status(entry: dict[str, Any]) -> dict[str, str]:
    if entry.get("speaker_validated") is False:
        return {"kind": "warn", "label": "Speaker mismatch"}
    if entry.get("evidence_validated") is True:
        return {"kind": "ok", "label": "Validated"}
    if entry.get("evidence_validated") is False:
        return {"kind": "bad", "label": "Invalid"}
    return {"kind": "muted", "label": "Unchecked"}


def _segment_lookup(transcript_segments: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {
        str(segment.get("block_id")): segment
        for segment in transcript_segments
        if isinstance(segment, dict) and segment.get("block_id")
    }


def _segment_page_range(segment: dict[str, Any]) -> str:
    start = segment.get("page_start")
    end = segment.get("page_end")
    if start and end and start != end:
        return f"{start}-{end}"
    return _display_value(start or end)


def _clip_display_text(text: str, *, limit: int) -> str:
    normalized = " ".join(str(text).split())
    if len(normalized) <= limit:
        return normalized
    return normalized[: max(0, limit - 1)].rstrip() + "..."


def _dataframe(rows: list[dict[str, Any]]) -> None:
    if rows:
        st.dataframe(rows, width="stretch", hide_index=True)
    else:
        st.caption("Sem dados para exibir.")


def _metric_card(label: str, value: str, help_text: str) -> None:
    st.markdown(
        f"""
        <div class="metric-card">
            <div class="metric-label">{label}</div>
            <div class="metric-value">{value}</div>
            <div class="metric-help">{help_text}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _download_button(path: Path, label: str, *, key_prefix: str = "download") -> None:
    if not path.exists():
        return
    data = path.read_bytes()
    mime = "application/json" if path.suffix == ".json" else "text/plain"
    st.download_button(
        label=label,
        data=data,
        file_name=path.name,
        mime=mime,
        width="stretch",
        key=_download_key(path, label, key_prefix),
    )


def _load_json(path: Path) -> Any | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def _read_text(path: Path) -> str | None:
    if not path.exists():
        return None
    return path.read_text(encoding="utf-8")


def _save_optional_file(uploaded_file: Any, target_dir: Path) -> Path | None:
    if uploaded_file is None:
        return None
    return _save_uploaded_file(uploaded_file, target_dir)


def _save_uploaded_file(uploaded_file: Any, target_dir: Path) -> Path:
    safe_name = Path(uploaded_file.name).name
    path = target_dir / safe_name
    path.write_bytes(uploaded_file.getbuffer())
    return path


def _build_executive_report_pdf(markdown: str) -> bytes:
    try:
        import fitz
    except ImportError as exc:  # pragma: no cover - PyMuPDF is a project dependency
        raise RuntimeError("PyMuPDF nao esta instalado; nao foi possivel gerar o PDF.") from exc

    doc = fitz.open()
    page_width = 595
    page_height = 842
    margin = 54
    page = doc.new_page(width=page_width, height=page_height)
    y = margin

    def add_page() -> None:
        nonlocal page, y
        page = doc.new_page(width=page_width, height=page_height)
        y = margin

    def ensure_space(height: float) -> None:
        if y + height > page_height - margin:
            add_page()

    def write_rule() -> None:
        nonlocal y
        ensure_space(14)
        page.draw_line(
            fitz.Point(margin, y),
            fitz.Point(page_width - margin, y),
            color=(0.82, 0.85, 0.9),
            width=0.7,
        )
        y += 14

    def write_text(
        text: str,
        *,
        size: float,
        bold: bool = False,
        indent: float = 0,
        spacing_before: float = 0,
        spacing_after: float = 4,
    ) -> None:
        nonlocal y
        text = " ".join(text.split())
        if not text:
            y += spacing_after
            return

        y += spacing_before
        max_width = page_width - (2 * margin) - indent
        chars_per_line = max(32, int(max_width / (size * 0.52)))
        lines = textwrap.wrap(text, width=chars_per_line) or [""]
        line_height = size * 1.35
        font_name = "hebo" if bold else "helv"

        for line in lines:
            ensure_space(line_height)
            page.insert_text(
                fitz.Point(margin + indent, y),
                line,
                fontsize=size,
                fontname=font_name,
                color=(0.04, 0.07, 0.13),
            )
            y += line_height
        y += spacing_after

    for raw_line in markdown.splitlines():
        line = raw_line.strip()
        if not line:
            y += 4
            continue
        if line.startswith("# "):
            write_text(line[2:], size=18, bold=True, spacing_after=8)
            write_rule()
        elif line.startswith("## "):
            write_text(line[3:], size=13.5, bold=True, spacing_before=9, spacing_after=5)
        elif line.startswith("- "):
            write_text("- " + line[2:], size=10.2, indent=14, spacing_after=2)
        else:
            write_text(line, size=10.2, spacing_after=4)

    doc.set_metadata(
        {
            "title": "Executive Earnings Call Brief",
            "author": "Earnings Call Intelligence Tracker",
            "subject": "Executive report generated from earnings call transcript",
        }
    )
    pdf_bytes = doc.tobytes(garbage=4, deflate=True)
    doc.close()
    return pdf_bytes


def _build_run_output_dir(raw_output_dir: str, *, use_timestamp: bool) -> Path:
    output_dir = _resolve_output_dir(raw_output_dir)
    if use_timestamp:
        suffix = datetime.now().strftime("%Y%m%d_%H%M%S")
        return output_dir / f"run_{suffix}"
    return output_dir


def _resolve_output_dir(raw_output_dir: str) -> Path:
    raw = raw_output_dir.strip() or "output"
    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = BASE_DIR / path
    return path


def _display_value(value: Any) -> str:
    if value is None or value == "":
        return "-"
    return str(value)


def _format_pct(value: Any) -> str:
    if value is None:
        return "-"
    try:
        return f"{float(value):.0%}"
    except (TypeError, ValueError):
        return "-"


def _download_key(path: Path, label: str, key_prefix: str) -> str:
    token = f"{path.name}_{label}".replace(" ", "_").replace(".", "_").replace("-", "_")
    return f"{key_prefix}_{token}"


def _apply_style() -> None:
    st.markdown(
        """
        <style>
        :root {
            --app-bg: #f6f7f9;
            --surface: #ffffff;
            --text: #111827;
            --muted: #667085;
            --border: #d9dee7;
            --accent: #2563eb;
            --success: #16a34a;
            --warning: #f59e0b;
        }
        .stApp {
            background:
                linear-gradient(180deg, #f8fafc 0%, #f4f6f9 46%, #eef2f7 100%);
            color: var(--text);
        }
        .main .block-container {
            max-width: 1240px;
            padding-top: 1.15rem;
            padding-bottom: 3rem;
        }
        [data-testid="stSidebar"] {
            background: #ffffff;
            border-right: 1px solid var(--border);
        }
        [data-testid="stSidebar"] * {
            color: var(--text) !important;
        }
        [data-testid="stSidebar"] .stMarkdown p,
        [data-testid="stSidebar"] label,
        [data-testid="stSidebar"] [data-testid="stWidgetLabel"] {
            color: #344054 !important;
            font-size: 0.86rem;
            font-weight: 650;
        }
        [data-testid="stSidebar"] [data-testid="stFileUploaderDropzone"] {
            background: #ffffff !important;
            border: 1px solid var(--border) !important;
            border-radius: 8px !important;
            min-height: 78px !important;
        }
        [data-testid="stSidebar"] [data-testid="stFileUploaderDropzone"] button {
            background: #ffffff !important;
            border: 1px solid #cfd6e2 !important;
            color: #1d2939 !important;
            border-radius: 7px !important;
            font-weight: 700 !important;
        }
        [data-testid="stSidebar"] [data-testid="stFileUploaderDropzone"] small,
        [data-testid="stSidebar"] [data-testid="stFileUploaderDropzone"] span {
            color: #667085 !important;
        }
        [data-testid="stSidebar"] input,
        [data-testid="stSidebar"] textarea,
        [data-testid="stSidebar"] [data-baseweb="select"] > div {
            background: #ffffff !important;
            border-color: var(--border) !important;
            color: var(--text) !important;
        }
        .sidebar-brand {
            font-size: 1.2rem;
            font-weight: 760;
            color: var(--text);
            padding: 0.25rem 0 1rem;
            border-bottom: 1px solid #edf0f5;
            margin-bottom: 1.05rem;
        }
        .sidebar-step {
            font-size: 0.92rem;
            font-weight: 760;
            color: #1f2937;
            margin: 1.15rem 0 0.45rem;
        }
        .subtle-step {
            margin-top: 1.35rem;
            padding-top: 1.1rem;
            border-top: 1px solid #edf0f5;
        }
        .top-chrome {
            display: flex;
            justify-content: space-between;
            align-items: center;
            min-height: 42px;
            margin: -0.25rem 0 1.3rem;
            color: #344054;
            font-size: 0.92rem;
            border-bottom: 1px solid #e5e9f0;
        }
        .top-chrome span {
            color: #667085;
            margin-left: 0.35rem;
        }
        .top-actions {
            color: #1f2937;
            font-weight: 650;
        }
        .hero-row {
            display: flex;
            justify-content: space-between;
            align-items: flex-end;
            gap: 2rem;
            margin-bottom: 1.25rem;
        }
        .hero-row h1 {
            font-size: 2.05rem;
            line-height: 1.12;
            margin: 0 0 0.65rem;
            color: #0b1220;
            font-weight: 780;
        }
        .run-meta {
            display: flex;
            align-items: center;
            flex-wrap: wrap;
            gap: 0.58rem;
            color: #475467;
            font-size: 0.88rem;
        }
        .dot {
            width: 4px;
            height: 4px;
            border-radius: 999px;
            background: #98a2b3;
            display: inline-block;
        }
        .status-pill {
            border-radius: 999px;
            padding: 2px 10px;
            font-weight: 700;
            font-size: 0.78rem;
        }
        .status-ok {
            color: #087443;
            background: #dcfae6;
            border: 1px solid #abefc6;
        }
        .status-idle {
            color: #475467;
            background: #f2f4f7;
            border: 1px solid #d0d5dd;
        }
        .output-path {
            max-width: 380px;
            color: #667085;
            font-size: 0.82rem;
            text-align: right;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }
        h1, h2, h3 {
            letter-spacing: 0;
            color: #0b1220;
        }
        h2 {
            font-size: 1.55rem !important;
            margin-top: 0.9rem !important;
        }
        h3 {
            font-size: 1.18rem !important;
        }
        .metric-card {
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: 8px;
            padding: 16px 18px;
            min-height: 104px;
            box-shadow: 0 1px 2px rgba(16, 24, 40, 0.04);
        }
        .metric-label {
            color: var(--muted);
            font-size: 0.78rem;
            font-weight: 650;
            text-transform: uppercase;
        }
        .metric-value {
            color: var(--text);
            font-size: 1.9rem;
            font-weight: 760;
            line-height: 1.15;
            margin-top: 8px;
        }
        .metric-help {
            color: var(--muted);
            font-size: 0.86rem;
            margin-top: 8px;
        }
        [data-testid="stHorizontalBlock"] {
            gap: 1rem;
        }
        [data-testid="stTabs"] [role="tablist"] {
            border-bottom: 1px solid #d9dee7;
            gap: 0.7rem;
        }
        [data-testid="stTabs"] button[role="tab"] {
            color: #475467;
            font-size: 0.9rem;
            font-weight: 650;
            padding: 0.55rem 0.25rem;
        }
        [data-testid="stTabs"] button[aria-selected="true"] {
            color: var(--accent);
            border-bottom: 2px solid var(--accent);
        }
        div[data-testid="stVerticalBlockBorderWrapper"] {
            border-color: var(--border);
            border-radius: 8px;
            background: #ffffff;
            box-shadow: 0 1px 2px rgba(16, 24, 40, 0.035);
        }
        .side-card-title {
            color: #111827;
            font-size: 1.02rem;
            font-weight: 760;
            margin: 0.1rem 0 0.5rem;
        }
        .stMarkdown p,
        .stMarkdown li {
            color: #111827;
            line-height: 1.58;
        }
        div[data-testid="stMetric"] {
            background: #ffffff;
            border: 1px solid var(--border);
            border-radius: 8px;
            padding: 12px 14px;
        }
        div[data-testid="stDownloadButton"] > button,
        div[data-testid="stButton"] > button {
            border-radius: 8px;
            font-weight: 650;
        }
        .citation-card {
            background: #ffffff;
            border: 1px solid #d9dee7;
            border-radius: 8px;
            padding: 14px 16px;
            margin: 0.65rem 0 0.35rem;
            box-shadow: 0 1px 2px rgba(16, 24, 40, 0.035);
        }
        .citation-card-head {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 0.75rem;
            margin-bottom: 0.45rem;
        }
        .citation-section {
            color: #475467;
            font-size: 0.74rem;
            font-weight: 760;
            text-transform: uppercase;
        }
        .citation-badge {
            border-radius: 999px;
            padding: 2px 9px;
            font-size: 0.72rem;
            font-weight: 760;
            white-space: nowrap;
        }
        .citation-ok {
            color: #087443;
            background: #dcfae6;
            border: 1px solid #abefc6;
        }
        .citation-bad {
            color: #b42318;
            background: #fee4e2;
            border: 1px solid #fecdca;
        }
        .citation-warn {
            color: #93370d;
            background: #fef0c7;
            border: 1px solid #fedf89;
        }
        .citation-muted {
            color: #475467;
            background: #f2f4f7;
            border: 1px solid #d0d5dd;
        }
        .citation-title {
            color: #111827;
            font-size: 0.98rem;
            font-weight: 760;
            line-height: 1.35;
        }
        .citation-meta {
            color: #667085;
            font-size: 0.8rem;
            margin-top: 0.25rem;
        }
        .citation-quote {
            color: #1f2937;
            font-size: 0.92rem;
            line-height: 1.55;
            margin-top: 0.7rem;
            padding-left: 0.75rem;
            border-left: 3px solid #c7d7fe;
        }
        .stAlert {
            border-radius: 8px;
        }
        @media (max-width: 900px) {
            .hero-row {
                display: block;
            }
            .output-path {
                text-align: left;
                margin-top: 0.5rem;
                max-width: 100%;
            }
        }
        .main .block-container {
            max-width: 540px;
            padding-top: 11vh;
        }
        .landing-shell {
            text-align: center;
            margin-bottom: 1.65rem;
        }
        .landing-shell h1 {
            font-size: 2rem;
            line-height: 1.08;
            color: #0b1220;
            margin: 0;
            font-weight: 780;
            letter-spacing: 0;
        }
        .main div[data-testid="stVerticalBlockBorderWrapper"] {
            border: 1px solid #d8dee8 !important;
            border-radius: 10px !important;
            background: rgba(255, 255, 255, 0.92) !important;
            box-shadow: 0 18px 45px rgba(15, 23, 42, 0.08), 0 2px 8px rgba(15, 23, 42, 0.04) !important;
            padding: 0 !important;
        }
        .main div[data-testid="stVerticalBlockBorderWrapper"] > div {
            padding: 1.15rem 1.25rem 1.25rem !important;
        }
        .upload-heading {
            display: flex;
            align-items: center;
            justify-content: space-between;
            margin-bottom: 0.85rem;
            padding-bottom: 0.8rem;
            border-bottom: 1px solid #edf0f5;
        }
        .upload-title {
            color: #111827;
            font-size: 0.98rem;
            font-weight: 760;
        }
        .upload-format {
            color: #2563eb;
            background: #eff6ff;
            border: 1px solid #bfdbfe;
            border-radius: 999px;
            padding: 0.18rem 0.6rem;
            font-size: 0.75rem;
            font-weight: 760;
        }
        [data-testid="stFileUploaderDropzone"] {
            display: flex !important;
            align-items: center !important;
            justify-content: center !important;
            background: #f8fafc !important;
            border: 1px dashed #b7c4d8 !important;
            border-radius: 8px !important;
            min-height: 84px !important;
            padding: 0.9rem !important;
            text-align: center !important;
            transition: border-color 160ms ease, background 160ms ease, box-shadow 160ms ease;
        }
        [data-testid="stFileUploaderDropzone"]:hover {
            background: #ffffff !important;
            border-color: #2563eb !important;
            box-shadow: inset 0 0 0 1px rgba(37, 99, 235, 0.08);
        }
        [data-testid="stFileUploaderDropzone"] > div {
            display: flex !important;
            align-items: center !important;
            justify-content: center !important;
            gap: 1rem !important;
            width: auto !important;
        }
        [data-testid="stFileUploaderDropzone"] button {
            background: #ffffff !important;
            border: 1px solid #cfd6e2 !important;
            border-radius: 7px !important;
            color: #1d2939 !important;
            font-weight: 700 !important;
            min-height: 42px !important;
            padding: 0 1rem !important;
            box-shadow: 0 1px 2px rgba(15, 23, 42, 0.05);
        }
        [data-testid="stFileUploaderDropzone"] small {
            margin: 0 !important;
            color: #667085 !important;
            font-size: 0.88rem !important;
        }
        .main div[data-testid="stForm"] {
            border: 0 !important;
            padding: 0 !important;
        }
        .main div[data-testid="stFormSubmitButton"] button {
            margin-top: 0.75rem;
            min-height: 46px;
            background: #2563eb;
            border: 1px solid #2563eb;
            border-radius: 8px;
            font-weight: 760;
            box-shadow: 0 8px 18px rgba(37, 99, 235, 0.18);
        }
        .main div[data-testid="stFormSubmitButton"] button:hover {
            background: #1d4ed8;
            border-color: #1d4ed8;
        }
        div[data-testid="stDialog"] div[role="dialog"] {
            border-radius: 10px;
        }
        div[data-testid="stDialog"] div[role="dialog"] > div:first-child {
            padding-top: 0.85rem !important;
            padding-bottom: 0.35rem !important;
            min-height: 0 !important;
        }
        div[data-testid="stDialog"] div[role="dialog"] [data-testid="stVerticalBlock"] {
            gap: 0.5rem !important;
        }
        div[data-testid="stDialog"] div[role="dialog"] [data-testid="stMarkdownContainer"]:first-child h1 {
            margin-top: 0 !important;
        }
        div[data-testid="stDialog"] h2 {
            font-size: 1.35rem !important;
            margin-top: 1rem !important;
            margin-bottom: 0.55rem !important;
            color: #0b1220 !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    main()
