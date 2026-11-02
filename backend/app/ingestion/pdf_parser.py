"""
Lightweight, Layout-Aware & Table-Preserving PDF-to-Markdown Parser (Milestone 1).
Primary engine: PyMuPDF4LLM (`pymupdf4llm.to_markdown(..., page_chunks=True)`)
Fallback engine: `pdfplumber` (page-by-page text + GitHub-flavored Markdown table reconstruction)
Ensures 100% page-number fidelity and intact Markdown pipe tables on any CPU environment.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from app.schemas.api_models import ParsedDocument, ParsedPage


def _clean_cell(cell: Any) -> str:
    """Normalizes a table cell value for Markdown pipe table rendering."""
    if cell is None:
        return ""
    text = str(cell).replace("\n", " ").replace("|", "/").strip()
    return re.sub(r"\s+", " ", text)


def _table_to_markdown(table: list[list[Any]]) -> str:
    """Converts a 2D list of extracted table cells into a standard Markdown pipe table."""
    cleaned_rows = [[_clean_cell(c) for c in row] for row in table if row and any(_clean_cell(c) for c in row)]
    if not cleaned_rows:
        return ""

    num_cols = max(len(r) for r in cleaned_rows)
    normalized = [r + [""] * (num_cols - len(r)) for r in cleaned_rows]

    header = normalized[0]
    separator = ["---"] * num_cols
    lines = [
        "| " + " | ".join(header) + " |",
        "| " + " | ".join(separator) + " |",
    ]
    for row in normalized[1:]:
        lines.append("| " + " | ".join(row) + " |")

    return "\n".join(lines)


def _count_markdown_tables(md_text: str) -> int:
    """Counts Markdown pipe tables present in a page's Markdown string."""
    pattern = re.compile(r"^\s*\|.*\|\s*\n\s*\|\s*[-:]+", re.MULTILINE)
    return len(pattern.findall(md_text))


class PolicyPDFParser:
    """
    Extracts structured, page-indexed Markdown from insurance policy & IRDAI PDFs.
    Automatically uses `pymupdf4llm` when installed and falls back to `pdfplumber`
    while preserving Markdown headers and pipe tables.
    """

    def __init__(self, prefer_pymupdf4llm: bool = True) -> None:
        self.prefer_pymupdf4llm = prefer_pymupdf4llm

    def parse_pdf(self, pdf_path: str | Path, custom_metadata: dict[str, Any] | None = None) -> ParsedDocument:
        path = Path(pdf_path).resolve()
        if not path.exists():
            raise FileNotFoundError(f"PDF file not found: {path}")

        pages: list[ParsedPage] | None = None
        if self.prefer_pymupdf4llm:
            pages = self._try_parse_with_pymupdf4llm(path)

        if pages is None:
            pages = self._parse_with_pdfplumber(path)

        return ParsedDocument(
            file_name=path.name,
            file_path=str(path),
            total_pages=len(pages),
            pages=pages,
            metadata=custom_metadata or {},
        )

    def _try_parse_with_pymupdf4llm(self, path: Path) -> list[ParsedPage] | None:
        """Extracts page-level Markdown using `pymupdf4llm` if available."""
        try:
            import pymupdf4llm  # type: ignore
        except ImportError:
            return None

        raw_chunks = pymupdf4llm.to_markdown(
            str(path),
            page_chunks=True,
            write_images=False,
            table_strategy="lines_strict",
        )
        parsed_pages: list[ParsedPage] = []
        for idx, chunk in enumerate(raw_chunks, start=1):
            md_text = (chunk.get("text") or "").strip()
            page_num = int(chunk.get("metadata", {}).get("page", idx))
            table_count = _count_markdown_tables(md_text)
            parsed_pages.append(
                ParsedPage(
                    page_number=page_num,
                    markdown_text=md_text,
                    has_tables=table_count > 0,
                    table_count=table_count,
                    extraction_engine="pymupdf4llm",
                )
            )
        return parsed_pages

    def _parse_with_pdfplumber(self, path: Path) -> list[ParsedPage]:
        """
        Extracts layout text and reconstructs Markdown pipe tables using `pdfplumber`.
        Guarantees table preservation even in environments without PyMuPDF.
        """
        import pdfplumber

        parsed_pages: list[ParsedPage] = []
        with pdfplumber.open(str(path)) as pdf:
            for page_idx, page in enumerate(pdf.pages, start=1):
                raw_text = (page.extract_text(layout=False) or "").strip()
                extracted_tables = page.extract_tables() or []

                md_tables: list[str] = []
                for tbl in extracted_tables:
                    md_tbl = _table_to_markdown(tbl)
                    if md_tbl:
                        md_tables.append(md_tbl)

                blocks: list[str] = []
                if raw_text:
                    blocks.append(raw_text)
                if md_tables:
                    blocks.append("\n\n### Structured Policy Table (Page " + str(page_idx) + ")\n" + "\n\n".join(md_tables))

                combined_md = "\n\n".join(blocks).strip()
                parsed_pages.append(
                    ParsedPage(
                        page_number=page_idx,
                        markdown_text=combined_md,
                        has_tables=len(md_tables) > 0,
                        table_count=len(md_tables),
                        extraction_engine="pdfplumber",
                    )
                )

        return parsed_pages
