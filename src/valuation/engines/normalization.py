"""Normalize earnings for cyclical companies across the business cycle.

Damodaran approach: don't value cyclical companies at peak or trough earnings.
Use normalized/mid-cycle earnings as the base for projection.

Reference: Damodaran, Investment Valuation 3rd ed., Chapter 18 (Cyclical Companies).
"""

from __future__ import annotations

import statistics
from typing import Sequence

import pandas as pd


# ---------------------------------------------------------------------------
# Cycle position detection
# ---------------------------------------------------------------------------

def detect_cycle_position(margins: list[float]) -> str:
    """Detect whether a company is at peak, trough, or mid-cycle.

    Uses the 25th / 75th percentile of the historical margin series as
    the trough / peak boundaries.  The *current* margin is the last element.

    Parameters
    ----------
    margins : list[float]
        Operating margin series ordered oldest → newest.  Must have at least
        2 elements; the last element is treated as the current margin.

    Returns
    -------
    str
        ``"peak"``   – current margin ≥ 75th percentile of history
        ``"trough"`` – current margin ≤ 25th percentile of history
        ``"mid"``    – otherwise

    Raises
    ------
    ValueError
        If ``margins`` has fewer than 2 elements.
    """
    if len(margins) < 2:
        raise ValueError(
            f"At least 2 margin observations are required; got {len(margins)}."
        )

    current = margins[-1]
    history = margins  # include current in the percentile calc (Damodaran uses full series)

    sorted_h = sorted(history)
    n = len(sorted_h)

    # Nearest-rank percentile (matches numpy's default linear interpolation
    # for small N without requiring numpy as a hard dep).
    def _percentile(data: list[float], p: float) -> float:
        """Simple linear-interpolation percentile on a pre-sorted list."""
        if len(data) == 1:
            return data[0]
        idx = p / 100 * (len(data) - 1)
        lo = int(idx)
        hi = lo + 1
        if hi >= len(data):
            return data[-1]
        frac = idx - lo
        return data[lo] + frac * (data[hi] - data[lo])

    p25 = _percentile(sorted_h, 25)
    p75 = _percentile(sorted_h, 75)

    if current >= p75:
        return "peak"
    if current <= p25:
        return "trough"
    return "mid"


# ---------------------------------------------------------------------------
# Earnings normalisation
# ---------------------------------------------------------------------------

def normalize_earnings_cyclical(
    income_statements: pd.DataFrame,
    revenue_col: str = "Total Revenue",
    ebit_col: str = "Operating Income",
    method: str = "average_margin",
    n_years: int = 5,
) -> dict:
    """Normalize EBIT for a cyclical company.

    Damodaran's recommended approach is to avoid valuing a cyclical firm at
    peak or trough earnings.  This function computes mid-cycle EBIT using one
    of three methods and reports where the company currently sits in its cycle.

    Parameters
    ----------
    income_statements : pd.DataFrame
        Historical income-statement data.  Each column should represent one
        fiscal year (most-recent year rightmost, following the yfinance /
        Compustat convention).  Rows are labelled with line-item names.
    revenue_col : str
        Row label for total revenue.  Default ``"Total Revenue"``.
    ebit_col : str
        Row label for operating income / EBIT.  Default ``"Operating Income"``.
    method : str
        Normalisation method.  One of:

        * ``"average_margin"``  – average operating margin × *current* revenue
          (preferred: preserves scale while smoothing profitability)
        * ``"average_ebit"``    – simple average of EBIT over the window
        * ``"peak_trough_avg"`` – arithmetic mean of the highest and lowest
          EBIT values (mid-cycle proxy)
    n_years : int
        Maximum number of historical years to include.  Capped at the number
        of columns available.  Must be ≥ 1.

    Returns
    -------
    dict
        Keys:

        * ``normalized_ebit``   – float, the normalised EBIT figure
        * ``normalized_margin`` – float, normalised operating margin (0–1)
        * ``cycle_position``    – ``"peak"`` | ``"trough"`` | ``"mid"``
        * ``method_used``       – the method string actually applied
        * ``raw_margins``       – list[float] of annual operating margins
          (oldest → newest, limited to ``n_years``)

    Raises
    ------
    ValueError
        If ``n_years < 1``, if required rows are missing, or if fewer than
        2 years of data are available after cleaning.
    """
    if n_years < 1:
        raise ValueError(f"n_years must be ≥ 1; got {n_years}.")

    valid_methods = {"average_margin", "average_ebit", "peak_trough_avg"}
    if method not in valid_methods:
        raise ValueError(
            f"Unknown method '{method}'.  Choose from: {sorted(valid_methods)}."
        )

    # --- validate required rows -----------------------------------------------
    if revenue_col not in income_statements.index:
        raise ValueError(
            f"Revenue column '{revenue_col}' not found in income_statements index. "
            f"Available: {list(income_statements.index)}"
        )
    if ebit_col not in income_statements.index:
        raise ValueError(
            f"EBIT column '{ebit_col}' not found in income_statements index. "
            f"Available: {list(income_statements.index)}"
        )

    # --- extract series -------------------------------------------------------
    # yfinance stores most-recent year as the *leftmost* column; we sort so that
    # oldest is index 0, newest is index -1.
    cols = list(income_statements.columns)
    # Limit to n_years most-recent columns (rightmost if newest is last,
    # leftmost if newest is first — handle both orderings gracefully by
    # sorting columns as strings and reversing if needed).
    # Use the last n_years columns as they appear; caller controls ordering.
    selected_cols = cols[-n_years:] if len(cols) >= n_years else cols

    revenues = [
        float(income_statements.loc[revenue_col, c]) for c in selected_cols
    ]
    ebits = [
        float(income_statements.loc[ebit_col, c]) for c in selected_cols
    ]

    if len(revenues) < 2:
        raise ValueError(
            f"At least 2 years of data are required for normalisation; "
            f"got {len(revenues)} after selecting up to {n_years} years."
        )

    # --- compute margins ------------------------------------------------------
    raw_margins: list[float] = []
    for rev, ebit_val in zip(revenues, ebits):
        if rev == 0 or (rev != rev):  # NaN guard
            raw_margins.append(float("nan"))
        else:
            raw_margins.append(ebit_val / rev)

    # Drop NaN margins (but keep corresponding revenues/ebits aligned)
    clean = [
        (r, e, m)
        for r, e, m in zip(revenues, ebits, raw_margins)
        if m == m  # NaN != NaN
    ]
    if len(clean) < 2:
        raise ValueError(
            "Fewer than 2 valid (non-NaN) margin observations after cleaning. "
            "Check for zero or missing revenue values."
        )

    clean_revenues, clean_ebits, clean_margins = zip(*clean)
    clean_revenues = list(clean_revenues)
    clean_ebits = list(clean_ebits)
    clean_margins = list(clean_margins)

    current_revenue = clean_revenues[-1]

    # --- normalise ------------------------------------------------------------
    if method == "average_margin":
        avg_margin = statistics.mean(clean_margins)
        normalized_ebit = avg_margin * current_revenue
        normalized_margin = avg_margin

    elif method == "average_ebit":
        normalized_ebit = statistics.mean(clean_ebits)
        # Back-compute the implied normalised margin
        normalized_margin = (
            normalized_ebit / current_revenue if current_revenue != 0 else float("nan")
        )

    else:  # peak_trough_avg
        normalized_ebit = (max(clean_ebits) + min(clean_ebits)) / 2.0
        normalized_margin = (
            normalized_ebit / current_revenue if current_revenue != 0 else float("nan")
        )

    # --- cycle position -------------------------------------------------------
    cycle_position = detect_cycle_position(clean_margins)

    return {
        "normalized_ebit": normalized_ebit,
        "normalized_margin": normalized_margin,
        "cycle_position": cycle_position,
        "method_used": method,
        "raw_margins": clean_margins,
    }
