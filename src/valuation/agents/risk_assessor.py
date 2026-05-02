"""
risk_assessor.py — Deterministic risk and cost-of-capital calculations.

Implements:
  - Synthetic credit rating and default spread (Damodaran methodology)
  - CAPM cost of equity
  - Hamada beta levering/unlevering
  - WACC

No LLM calls. No consensus estimates. All inputs must be supplied by caller.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Synthetic rating lookup tables
# Each entry: (upper_bound_exclusive, rating_label, default_spread)
# The lower bound is the previous entry's upper bound (or -inf for first).
# ---------------------------------------------------------------------------

_LARGE_FIRM_TABLE: list[tuple[float, str, float]] = [
    (0.20,  "D2/D",      0.1900),
    (0.65,  "C2/C",      0.1600),
    (0.80,  "Ca2/CC",    0.1261),
    (1.25,  "Caa/CCC",   0.0885),
    (1.50,  "B3/B-",     0.0509),
    (1.75,  "B2/B",      0.0321),
    (2.00,  "B1/B+",     0.0275),
    (2.25,  "Ba2/BB",    0.0184),
    (2.50,  "Ba1/BB+",   0.0138),
    (3.00,  "Baa2/BBB",  0.0111),
    (4.25,  "A3/A-",     0.0089),
    (5.50,  "A2/A",      0.0078),
    (6.50,  "A1/A+",     0.0070),
    (8.50,  "Aa2/AA",    0.0055),
    (float("inf"), "Aaa/AAA", 0.0040),
]

_SMALL_FIRM_TABLE: list[tuple[float, str, float]] = [
    (0.50,   "D2/D",      0.1900),
    (0.80,   "C2/C",      0.1600),
    (1.25,   "Ca2/CC",    0.1261),
    (1.50,   "Caa/CCC",   0.0885),
    (2.00,   "B3/B-",     0.0509),
    (2.50,   "B2/B",      0.0321),
    (3.00,   "B1/B+",     0.0275),
    (3.50,   "Ba2/BB",    0.0184),
    (4.00,   "Ba1/BB+",   0.0138),
    (4.50,   "Baa2/BBB",  0.0111),
    (6.00,   "A3/A-",     0.0089),
    (7.50,   "A2/A",      0.0078),
    (9.50,   "A1/A+",     0.0070),
    (12.50,  "Aa2/AA",    0.0055),
    (float("inf"), "Aaa/AAA", 0.0040),
]

_FINANCIAL_FIRM_TABLE: list[tuple[float, str, float]] = [
    (0.05,  "D2/D",      0.1900),
    (0.10,  "C2/C",      0.1600),
    (0.20,  "Ca2/CC",    0.1261),
    (0.30,  "Caa/CCC",   0.0885),
    (0.40,  "B3/B-",     0.0509),
    (0.50,  "B2/B",      0.0321),
    (0.60,  "B1/B+",     0.0275),
    (0.75,  "Ba2/BB",    0.0184),
    (0.90,  "Ba1/BB+",   0.0138),
    (1.20,  "Baa2/BBB",  0.0111),
    (1.50,  "A3/A-",     0.0089),
    (2.00,  "A2/A",      0.0078),
    (2.50,  "A1/A+",     0.0070),
    (3.00,  "Aa2/AA",    0.0055),
    (float("inf"), "Aaa/AAA", 0.0040),
]

_TABLES: dict[str, list[tuple[float, str, float]]] = {
    "large":     _LARGE_FIRM_TABLE,
    "small":     _SMALL_FIRM_TABLE,
    "financial": _FINANCIAL_FIRM_TABLE,
}

_VALID_FIRM_TYPES = frozenset(_TABLES)


def _lookup(interest_coverage: float, firm_type: str) -> tuple[str, float]:
    """Internal: walk the correct table and return (rating, spread)."""
    firm_type = firm_type.lower()
    if firm_type not in _VALID_FIRM_TYPES:
        raise ValueError(
            f"firm_type must be one of {sorted(_VALID_FIRM_TYPES)!r}, got {firm_type!r}"
        )
    table = _TABLES[firm_type]
    for upper, rating, spread in table:
        if interest_coverage < upper:
            return rating, spread
    # Unreachable: last row has upper=inf
    raise RuntimeError("Lookup table is malformed — no matching row found.")


# ---------------------------------------------------------------------------
# Public API — Synthetic Rating
# ---------------------------------------------------------------------------

def get_synthetic_rating(interest_coverage: float, firm_type: str) -> tuple[str, float]:
    """Return (rating_label, default_spread) for the given ICR and firm type.

    Parameters
    ----------
    interest_coverage : float
        EBIT / Interest expense.  May be negative (maps to lowest rating).
    firm_type : str
        One of "large", "small", or "financial".

    Returns
    -------
    tuple[str, float]
        Moody's/S&P rating label (e.g. "Baa2/BBB") and annual default spread
        as a decimal (e.g. 0.0111 for 1.11%).
    """
    return _lookup(interest_coverage, firm_type)


def get_default_spread(interest_coverage: float, firm_type: str) -> float:
    """Return the default spread (decimal) implied by the synthetic rating."""
    _, spread = _lookup(interest_coverage, firm_type)
    return spread


def compute_cost_of_debt(
    risk_free_rate: float,
    interest_coverage: float,
    firm_type: str,
) -> float:
    """Return the pre-tax cost of debt: Rf + default spread.

    Parameters
    ----------
    risk_free_rate : float
        Risk-free rate as a decimal (e.g. 0.037 for 3.7%).
    interest_coverage : float
        EBIT / Interest expense.
    firm_type : str
        One of "large", "small", or "financial".

    Returns
    -------
    float
        Pre-tax cost of debt as a decimal.
    """
    spread = get_default_spread(interest_coverage, firm_type)
    return risk_free_rate + spread


# ---------------------------------------------------------------------------
# Public API — CAPM
# ---------------------------------------------------------------------------

def compute_cost_of_equity(
    risk_free_rate: float,
    beta: float,
    erp: float,
    country_risk_premium: float = 0.0,
    lambda_country: float = 1.0,
) -> float:
    """Return the CAPM cost of equity.

    Formula: Ke = Rf + Beta * ERP + Lambda * CRP

    Parameters
    ----------
    risk_free_rate : float
        Risk-free rate as a decimal.
    beta : float
        Equity beta (levered).
    erp : float
        Equity risk premium (mature market) as a decimal.
    country_risk_premium : float, optional
        Additional country risk premium as a decimal.  Default 0.
    lambda_country : float, optional
        Country risk exposure multiplier (1.0 = full exposure).  Default 1.

    Returns
    -------
    float
        Cost of equity as a decimal.
    """
    return risk_free_rate + beta * erp + lambda_country * country_risk_premium


# ---------------------------------------------------------------------------
# Public API — Beta (Hamada equations)
# ---------------------------------------------------------------------------

def unlever_beta(levered_beta: float, de_ratio: float, tax_rate: float) -> float:
    """Remove financial leverage from beta (Hamada equation).

    Bu = Bl / (1 + (1 - t) * D/E)

    Parameters
    ----------
    levered_beta : float
        Observed equity beta.
    de_ratio : float
        Debt-to-equity ratio (market values preferred).
    tax_rate : float
        Marginal corporate tax rate as a decimal.

    Returns
    -------
    float
        Unlevered (asset) beta.
    """
    return levered_beta / (1 + (1 - tax_rate) * de_ratio)


def relever_beta(unlevered_beta: float, de_ratio: float, tax_rate: float) -> float:
    """Add financial leverage to an unlevered beta (Hamada equation).

    Bl = Bu * (1 + (1 - t) * D/E)

    Parameters
    ----------
    unlevered_beta : float
        Unlevered (asset) beta.
    de_ratio : float
        Target debt-to-equity ratio (market values preferred).
    tax_rate : float
        Marginal corporate tax rate as a decimal.

    Returns
    -------
    float
        Relevered equity beta.
    """
    return unlevered_beta * (1 + (1 - tax_rate) * de_ratio)


# ---------------------------------------------------------------------------
# Public API — WACC
# ---------------------------------------------------------------------------

def compute_wacc(
    cost_of_equity: float,
    cost_of_debt: float,
    tax_rate: float,
    equity_weight: float,
    debt_weight: float,
) -> float:
    """Return the weighted average cost of capital.

    Formula: WACC = Ke * E/(D+E) + Kd * (1-t) * D/(D+E)

    Parameters
    ----------
    cost_of_equity : float
        Cost of equity as a decimal.
    cost_of_debt : float
        Pre-tax cost of debt as a decimal.
    tax_rate : float
        Marginal corporate tax rate as a decimal.
    equity_weight : float
        E / (D + E) — must sum to 1 with debt_weight.
    debt_weight : float
        D / (D + E).

    Returns
    -------
    float
        WACC as a decimal.
    """
    return cost_of_equity * equity_weight + cost_of_debt * (1 - tax_rate) * debt_weight
