from __future__ import annotations

from pathlib import Path

import pytest

from src.pdf_loader import PdfLoaderError, load_pdf_metadata_text, load_pdf_pages


def _make_pdf(
    path: Path,
    text: str = "Hello earnings call",
    metadata: dict[str, str] | None = None,
) -> None:
    import fitz

    document = fitz.open()
    if metadata:
        document.set_metadata(metadata)
    page = document.new_page()
    page.insert_text((72, 72), text)
    document.save(path)
    document.close()


def test_load_pdf_pages_returns_page_text(tmp_path: Path) -> None:
    pdf_path = tmp_path / "sample.pdf"
    _make_pdf(pdf_path)

    pages = load_pdf_pages(pdf_path)

    assert pages == [{"page": 1, "text": "Hello earnings call\n"}]


def test_load_pdf_pages_rejects_missing_file(tmp_path: Path) -> None:
    with pytest.raises(PdfLoaderError, match="nao encontrado"):
        load_pdf_pages(tmp_path / "missing.pdf")


def test_load_pdf_pages_rejects_non_pdf(tmp_path: Path) -> None:
    txt_path = tmp_path / "sample.txt"
    txt_path.write_text("not a pdf", encoding="utf-8")

    with pytest.raises(PdfLoaderError, match="extensao .pdf"):
        load_pdf_pages(txt_path)


def test_load_pdf_metadata_text_returns_raw_document_metadata(tmp_path: Path) -> None:
    pdf_path = tmp_path / "Transcript - Videoconference - 1Q26 (BBAS3).pdf"
    _make_pdf(
        pdf_path,
        metadata={
            "title": "Banco do Brasil 1Q26 Earnings Call",
            "subject": "May 14th, 2026",
            "keywords": "BBAS3",
        },
    )

    metadata_text = load_pdf_metadata_text(pdf_path)

    assert "Transcript - Videoconference - 1Q26 (BBAS3).pdf" in metadata_text
    assert "Banco do Brasil 1Q26 Earnings Call" in metadata_text
    assert "May 14th, 2026" in metadata_text
    assert "BBAS3" in metadata_text


def test_load_pdf_metadata_text_includes_first_page_header(tmp_path: Path) -> None:
    pdf_path = tmp_path / "Transcript.pdf"
    _make_pdf(
        pdf_path,
        text=(
            "Earnings Webcast\n"
            "Banco do Brasil S/A (BBAS3)\n"
            "Earnings Webcast 1Q26 Transcription\n"
            "May 14th, 2026\n\n"
            "Janaína Storti:\n"
            "Good morning, everyone."
        ),
    )

    metadata_text = load_pdf_metadata_text(pdf_path)

    assert "Banco do Brasil S/A (BBAS3)" in metadata_text
    assert "Earnings Webcast 1Q26 Transcription" in metadata_text
    assert "May 14th, 2026" in metadata_text
    assert "Good morning, everyone." not in metadata_text
