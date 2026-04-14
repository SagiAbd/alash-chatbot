"""Parse Alash-era scientific term glossary xlsx files into term chunks.

Detects the header row by column name rather than position, so the parser
is resilient to columns being added, removed, or reordered between exports.
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)

# (substring_to_match_in_header_cell, normalized_field_key)
# Lower-cased substring matching — resilient to minor wording differences.
_COLUMN_PATTERNS: list[tuple[str, str]] = [
    ("алаш термині", "alash_term"),
    ("заманауи термин", "modern_term"),
    ("сала", "field"),
    ("заманауи түсініктеме", "modern_definition"),
    ("алаш түсініктемесі", "alash_definition"),
    ("анықтама бар ма", "has_definition"),
    ("екі бет арасындағы мәтін", "context"),
    ("авторы", "author"),
    ("басталатын беті", "start_page"),
    ("аяқталу беті", "end_page"),
    ("жазылу жылы", "year"),
    ("сілтеме", "link"),
]


def _detect_column_mapping(row: list[str]) -> dict[int, str]:
    """Return {column_index: field_key} by scanning a header row."""
    mapping: dict[int, str] = {}
    for col_idx, cell in enumerate(row):
        normalized = (cell or "").strip().lower()
        if not normalized:
            continue
        for pattern, key in _COLUMN_PATTERNS:
            if pattern in normalized:
                if key not in mapping.values():  # first match wins
                    mapping[col_idx] = key
                break
    return mapping


def _build_page_content(term: dict[str, Any]) -> str:
    """Build a single searchable text blob from all non-empty term fields."""
    parts = []
    for key, label in [
        ("alash_term", "Алаш термині"),
        ("modern_term", "Заманауи термин"),
        ("field", "Сала"),
        ("author", "Автор"),
        ("modern_definition", "Анықтама"),
        ("alash_definition", "Алаш анықтамасы"),
        ("context", "Контекст"),
    ]:
        val = str(term.get(key) or "").strip()
        if val:
            parts.append(f"{label}: {val}")
    return " | ".join(parts)


def parse_glossary_xlsx(file_path: str) -> list[dict[str, Any]]:
    """Parse a glossary xlsx and return a list of term dicts.

    Each dict contains normalized field keys and a ``page_content`` key
    suitable for full-text search.  The header row is detected by column
    names, not by position, so the file layout can change without breaking
    parsing as long as at least three recognisable columns remain.

    Args:
        file_path: Local path to the xlsx file.

    Returns:
        List of term dicts.  Empty if no valid header was found.
    """
    import openpyxl

    wb = openpyxl.load_workbook(file_path, read_only=True, data_only=True)
    ws = wb.active

    col_mapping: dict[int, str] = {}
    terms: list[dict[str, Any]] = []

    for row in ws.iter_rows(values_only=True):
        row_values = [str(cell) if cell is not None else "" for cell in row]

        if not col_mapping:
            candidate = _detect_column_mapping(row_values)
            # Require at least 3 recognised columns AND the key identifier
            if len(candidate) >= 3 and "alash_term" in candidate.values():
                col_mapping = candidate
            continue

        term: dict[str, Any] = {}
        for col_idx, field_key in col_mapping.items():
            if col_idx < len(row_values):
                val = row_values[col_idx].strip()
                term[field_key] = val if val and val.lower() != "none" else ""

        alash_term = str(term.get("alash_term") or "").strip()
        if not alash_term:
            continue

        term["page_content"] = _build_page_content(term)
        terms.append(term)

    wb.close()
    logger.info("Parsed %d terms from %s", len(terms), file_path)
    return terms
