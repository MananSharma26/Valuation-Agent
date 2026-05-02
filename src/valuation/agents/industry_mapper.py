"""Map a company to one of Damodaran's ~96 industry names using fuzzy matching.

Uses the thefuzz library for string similarity. The matching strategy:
1. Try exact match on the company's yfinance industry name
2. Try fuzzy match on industry name
3. Try fuzzy match on sector + industry combined
4. Try fuzzy match on description keywords
5. Apply keyword-prefix boost for the primary keyword in the industry query
6. Penalize single-word candidates to avoid generic overmatch (e.g. "Diversified")
7. Return best match above threshold, or None if below threshold

When score < threshold (default 70), returns None — caller should ask user.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from thefuzz import fuzz, process

from valuation.data.damodaran_loader import DamodaranLoader

# Words to ignore when extracting the primary keyword from an industry query
_STOPWORDS: frozenset[str] = frozenset(
    {"and", "or", "the", "a", "an", "of", "for", "in", "&", "-"}
)


@dataclass
class IndustryMatch:
    """Result of an industry fuzzy-match attempt."""

    matched_name: str
    score: int
    candidates: list[tuple[str, int]] = field(default_factory=list)


def _adjusted_score(query: str, candidate: str, base_score: int) -> int:
    """Penalize single-word candidates when the query has multiple words.

    Short single-word Damodaran industry names (e.g. "Diversified") can
    score very high via substring matching against multi-word queries like
    "Banks - Diversified", producing semantically wrong results. Penalizing
    them keeps the scores realistic.
    """
    q_words = len(query.split())
    c_words = len(
        re.sub(r"[/()\-]", " ", candidate).split()
    )
    if c_words <= 1 and q_words >= 2:
        return int(base_score * 0.6)
    return base_score


def match_industry(
    sector: str,
    industry: str,
    description: str,
    loader: DamodaranLoader,
    region: str = "US",
    threshold: int = 70,
) -> IndustryMatch | None:
    """Match a company's sector/industry/description to a Damodaran industry name.

    Parameters
    ----------
    sector : str
        Company sector from yfinance (e.g. "Technology").
    industry : str
        Company industry from yfinance (e.g. "Software - Application").
    description : str
        Company business description or keywords.
    loader : DamodaranLoader
        Loaded Damodaran data instance.
    region : str
        Damodaran region for industry list lookup.
    threshold : int
        Minimum fuzzy match score (0-100) to accept. Default 70.

    Returns
    -------
    IndustryMatch or None
        Best match above threshold with top candidates, or None if no match
        meets the threshold (caller should ask user to select).
    """
    industry_names = loader.list_industries(region=region)
    if not industry_names:
        return None

    # Build query strings to try
    queries: list[str] = []
    if industry:
        queries.append(industry)
    if sector and industry:
        queries.append(f"{sector} {industry}")
    if description:
        queries.append(description)

    if not queries:
        return None

    # Extract primary keyword from the industry query for a boost
    primary_keyword: str | None = None
    if industry:
        words = [
            w for w in re.split(r"[\s\-&/]+", industry)
            if w.lower() not in _STOPWORDS and len(w) > 2
        ]
        if words:
            primary_keyword = words[0].lower()

    # Score every candidate across all queries using token_sort_ratio
    candidate_scores: dict[str, int] = {}
    for query in queries:
        results = process.extract(
            query,
            industry_names,
            scorer=fuzz.token_sort_ratio,
            limit=len(industry_names),
        )
        for name, score, *_ in results:
            adj = _adjusted_score(query, name, score)
            if adj > candidate_scores.get(name, 0):
                candidate_scores[name] = adj

    # Boost candidates whose name starts with the primary keyword
    # This corrects cases like "Banks - Diversified" → prefers "Banks (Regional)"
    if primary_keyword:
        kw_stem = primary_keyword.rstrip("s")  # "banks" → "bank"
        for name in industry_names:
            name_lower = name.lower()
            if name_lower.startswith(primary_keyword) or name_lower.startswith(kw_stem):
                candidate_scores[name] = candidate_scores.get(name, 0) + 20

    # Sort and select best
    sorted_candidates = sorted(
        candidate_scores.items(), key=lambda x: x[1], reverse=True
    )[:5]

    if not sorted_candidates:
        return None

    best_name, best_score = sorted_candidates[0]

    if best_score < threshold:
        return None

    return IndustryMatch(
        matched_name=best_name,
        score=best_score,
        candidates=sorted_candidates,
    )


def _safe_float(value, default=None) -> float | None:
    """Safely convert a value to float, returning default on failure."""
    if value is None:
        return default
    try:
        result = float(value)
        if result != result:  # NaN check
            return default
        return result
    except (ValueError, TypeError):
        return default


def load_industry_benchmarks(
    industry_name: str,
    loader: DamodaranLoader,
    region: str = "US",
) -> dict | None:
    """Load all benchmark data for a Damodaran industry.

    Aggregates data from multiple Damodaran files (betas, wacc, pedata,
    pbvdata, psdata, vebitda) into a single dict.

    Parameters
    ----------
    industry_name : str
        Exact Damodaran industry name (e.g. "Software (System & Application)").
    loader : DamodaranLoader
        Loaded Damodaran data instance.
    region : str
        Damodaran region.

    Returns
    -------
    dict or None
        Dict with keys: beta, unlevered_beta, de_ratio, wacc, multiples,
        margins, growth. Returns None if industry not found in betas file.
    """
    # --- Beta data ---
    beta_row = loader.lookup("betas", industry_name, region=region)
    if beta_row is None:
        return None

    beta = _safe_float(beta_row.get("Beta") or beta_row.get("Beta "))
    unlevered_beta = _safe_float(
        beta_row.get("Unlevered beta corrected for cash")
        or beta_row.get("Unlevered beta")
    )
    de_ratio = _safe_float(beta_row.get("D/E Ratio"))

    # --- WACC ---
    wacc = None
    wacc_row = loader.lookup("wacc", industry_name, region=region)
    if wacc_row is not None:
        wacc = _safe_float(wacc_row.get("Cost of Capital"))

    # --- Multiples ---
    multiples: dict[str, float] = {}

    # PE data
    pe_row = loader.lookup("pedata", industry_name, region=region)
    if pe_row is not None:
        multiples["current_pe"] = _safe_float(pe_row.get("Current PE"))
        multiples["trailing_pe"] = _safe_float(pe_row.get("Trailing PE"))
        multiples["forward_pe"] = _safe_float(pe_row.get("Forward PE"))
        multiples["peg_ratio"] = _safe_float(pe_row.get("PEG Ratio"))

    # EV/EBITDA data
    vebitda_row = loader.lookup("vebitda", industry_name, region=region)
    if vebitda_row is not None:
        multiples["ev_ebitda"] = _safe_float(vebitda_row.get("EV/EBITDA"))
        multiples["ev_ebit"] = _safe_float(vebitda_row.get("EV/EBIT"))
        multiples["ev_ebitdar_and_d"] = _safe_float(
            vebitda_row.get("EV/EBITDAR&D")
        )

    # PBV data
    pbv_row = loader.lookup("pbvdata", industry_name, region=region)
    if pbv_row is not None:
        multiples["pbv"] = _safe_float(pbv_row.get("PBV"))
        multiples["ev_invested_capital"] = _safe_float(
            pbv_row.get("EV/ Invested Capital")
        )

    # PS data
    ps_row = loader.lookup("psdata", industry_name, region=region)
    if ps_row is not None:
        multiples["ps"] = _safe_float(ps_row.get("Price/Sales"))
        multiples["ev_sales"] = _safe_float(ps_row.get("EV/Sales"))

    # Remove None values from multiples
    multiples = {k: v for k, v in multiples.items() if v is not None}

    # --- Margins ---
    margins: dict[str, float] = {}
    if ps_row is not None:
        margins["net_margin"] = _safe_float(ps_row.get("Net Margin"))
        margins["operating_margin"] = _safe_float(
            ps_row.get("Pre-tax Operating Margin")
        )

    # ROE from PBV file
    if pbv_row is not None:
        margins["roe"] = _safe_float(pbv_row.get("ROE"))
        margins["roic"] = _safe_float(pbv_row.get("ROIC"))

    margins = {k: v for k, v in margins.items() if v is not None}

    # --- Growth ---
    growth: dict[str, float] = {}
    if pe_row is not None:
        growth["expected_growth_5y"] = _safe_float(
            pe_row.get("Expected growth - next 5 years")
        )

    growth = {k: v for k, v in growth.items() if v is not None}

    return {
        "beta": beta,
        "unlevered_beta": unlevered_beta,
        "de_ratio": de_ratio,
        "wacc": wacc,
        "multiples": multiples,
        "margins": margins,
        "growth": growth,
    }
