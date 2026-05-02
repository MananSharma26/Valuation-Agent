"""Generate a data sources transparency table from ValuationContext."""

from __future__ import annotations
from valuation.validation.sourced import SourcedValue


def sources_table(sourced_values: dict[str, SourcedValue]) -> list[dict]:
    """Convert a dict of named SourcedValues into a transparency table.

    Returns list of dicts with keys: field, value, source, confidence, note
    """
    rows = []
    for field, sv in sourced_values.items():
        rows.append({
            "field": field,
            "value": sv.value,
            "source": sv.source,
            "confidence": sv.confidence,
            "note": sv.note,
        })
    return rows


def format_sources_markdown(sourced_values: dict[str, SourcedValue]) -> str:
    """Format data sources as a markdown table."""
    lines = ["| Field | Value | Source | Confidence | Note |",
             "|-------|-------|--------|------------|------|"]
    for field, sv in sourced_values.items():
        val = f"{sv.value:.4f}" if sv.value is not None else "MISSING"
        conf = f"{sv.confidence:.0%}"
        lines.append(f"| {field} | {val} | {sv.source} | {conf} | {sv.note} |")
    return "\n".join(lines)


def count_by_source(sourced_values: dict[str, SourcedValue]) -> dict[str, int]:
    """Count how many values came from each source type."""
    counts: dict[str, int] = {}
    for sv in sourced_values.values():
        counts[sv.source] = counts.get(sv.source, 0) + 1
    return counts


def missing_fields(sourced_values: dict[str, SourcedValue]) -> list[str]:
    """Return names of fields that are missing."""
    return [name for name, sv in sourced_values.items() if not sv.is_available]


def proxy_fields(sourced_values: dict[str, SourcedValue]) -> list[str]:
    """Return names of fields using industry proxy or assumed defaults."""
    return [name for name, sv in sourced_values.items() if sv.is_proxy]
