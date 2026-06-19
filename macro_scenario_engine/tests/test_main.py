from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from app import main as cli


class DummyOutput:
    markdown_report = "# Relatorio\n\nTexto final."

    def as_json_dict(self) -> dict:
        return {"ok": True}


def test_cli_uses_llm_and_saves_by_default(monkeypatch, capsys) -> None:
    calls: dict[str, object] = {}

    def fake_run_analysis(scenario, *, settings, use_llm):
        calls["scenario"] = scenario
        calls["settings"] = settings
        calls["use_llm"] = use_llm
        return DummyOutput()

    def fake_save_outputs(output, output_dir):
        calls["saved_output"] = output
        calls["output_dir"] = output_dir
        return Path("analysis.json"), Path("analysis.md")

    settings = SimpleNamespace(output_dir=Path("out"))
    monkeypatch.setattr(cli, "load_settings", lambda: settings)
    monkeypatch.setattr(cli, "run_analysis", fake_run_analysis)
    monkeypatch.setattr(cli, "save_outputs", fake_save_outputs)

    result = cli.main(["--scenario", "Selic em queda e credito em expansao."])

    captured = capsys.readouterr()
    assert result == 0
    assert calls["use_llm"] is True
    assert calls["output_dir"] == Path("out")
    assert "Arquivos salvos:" in captured.err
    assert '"ok": true' in captured.out


def test_cli_can_disable_llm_and_save(monkeypatch, capsys) -> None:
    calls: dict[str, object] = {}

    def fake_run_analysis(scenario, *, settings, use_llm):
        calls["use_llm"] = use_llm
        return DummyOutput()

    def fail_save_outputs(output, output_dir):
        raise AssertionError("save_outputs should not be called")

    monkeypatch.setattr(cli, "load_settings", lambda: SimpleNamespace(output_dir=Path("out")))
    monkeypatch.setattr(cli, "run_analysis", fake_run_analysis)
    monkeypatch.setattr(cli, "save_outputs", fail_save_outputs)

    result = cli.main(["--scenario", "Selic em queda e credito em expansao.", "--no-llm", "--no-save", "--markdown"])

    captured = capsys.readouterr()
    assert result == 0
    assert calls["use_llm"] is False
    assert captured.err == ""
    assert captured.out.startswith("# Relatorio")
