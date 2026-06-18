from __future__ import annotations

import logging
from pathlib import Path
from typing import Any


logger = logging.getLogger(__name__)


class PdfLoaderError(Exception):
    """Base error for PDF loading failures."""


class PdfTextExtractionError(PdfLoaderError):
    """Raised when a PDF has no extractable text in the MVP pipeline."""


def load_pdf_pages(pdf_path: str | Path) -> list[dict[str, Any]]:
    """Extract text from a PDF page by page, preserving page numbers."""
    path = _resolve_pdf_path(pdf_path)

    try:
        import fitz
    except ImportError as exc:
        raise PdfLoaderError(
            "Dependencia PyMuPDF ausente. Instale com: python -m pip install PyMuPDF"
        ) from exc

    pages: list[dict[str, Any]] = []

    try:
        with fitz.open(path) as document:
            for page_index in range(document.page_count):
                page_number = page_index + 1
                try:
                    page = document.load_page(page_index)
                    text = page.get_text("text")
                except Exception as exc:  # pragma: no cover - defensive around PDF internals
                    logger.warning("Failed to extract page %s from %s: %s", page_number, path, exc)
                    continue

                pages.append({"page": page_number, "text": text or ""})
    except Exception as exc:
        raise PdfLoaderError(f"Falha ao abrir ou ler o PDF: {exc}") from exc

    if not pages or not any(str(page["text"]).strip() for page in pages):
        raise PdfTextExtractionError(
            "O PDF nao possui texto extraivel. Esta versao do MVP nao implementa OCR."
        )

    return pages


def load_pdf_metadata_text(pdf_path: str | Path) -> str:
    """Return searchable raw PDF metadata text without depending on page extraction."""
    path = _resolve_pdf_path(pdf_path)

    try:
        import fitz
    except ImportError as exc:
        raise PdfLoaderError(
            "Dependencia PyMuPDF ausente. Instale com: python -m pip install PyMuPDF"
        ) from exc

    try:
        with fitz.open(path) as document:
            parts: list[str] = [path.name]
            first_page_header = _extract_first_page_header_text(document)
            if first_page_header:
                parts.append(first_page_header)

            for key, value in sorted((document.metadata or {}).items()):
                if value:
                    parts.append(f"{key}: {value}")

            try:
                xml_metadata = document.get_xml_metadata()
            except Exception:  # pragma: no cover - defensive around PDF internals
                xml_metadata = ""
            if xml_metadata:
                parts.append(xml_metadata)

            for item in document.get_toc(simple=True):
                if len(item) >= 2 and item[1]:
                    parts.append(str(item[1]))

            return "\n".join(parts)
    except Exception as exc:
        raise PdfLoaderError(f"Falha ao abrir ou ler metadados do PDF: {exc}") from exc


def _extract_first_page_header_text(document: Any) -> str:
    if document.page_count < 1:
        return ""

    page = document.load_page(0)
    text = page.get_text("text") or ""
    header_lines: list[str] = []

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if _looks_like_speaker_line(line):
            break
        header_lines.append(line)
        if len(header_lines) >= 12:
            break

    return "\n".join(header_lines)


def _looks_like_speaker_line(line: str) -> bool:
    return line.endswith(":") and 2 <= len(line) <= 120


def _resolve_pdf_path(pdf_path: str | Path) -> Path:
    path = Path(pdf_path).expanduser()

    if not path.exists():
        raise PdfLoaderError("Arquivo PDF nao encontrado. Verifique o caminho informado.")
    if not path.is_file():
        raise PdfLoaderError("O caminho informado nao aponta para um arquivo PDF.")
    if path.suffix.lower() != ".pdf":
        raise PdfLoaderError("Arquivo invalido. Informe um arquivo com extensao .pdf.")

    return path
