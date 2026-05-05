"""Failure probability adjustment for distressed companies.

Damodaran: Value = GC_Value × (1 - P_failure) + Distress_Proceeds × P_failure

Reference: Damodaran, "The Dark Side of Valuation" (2nd ed.), Chapter 13
           and Investment Valuation (3rd ed.), Chapter 24.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Default 10-year cumulative failure probabilities by synthetic rating.
# Source: Damodaran — calibrated from Moody's/S&P historical default studies.
# ---------------------------------------------------------------------------
DEFAULT_RATES: dict[str, float] = {
    "Aaa/AAA": 0.0001,
    "Aa2/AA":  0.0002,
    "A1/A+":   0.001,
    "A2/A":    0.001,
    "A3/A-":   0.002,
    "Baa2/BBB": 0.005,
    "Ba1/BB+": 0.01,
    "Ba2/BB":  0.02,
    "B1/B+":   0.05,
    "B2/B":    0.08,
    "B3/B-":   0.12,
    "Caa/CCC": 0.20,
    "Ca2/CC":  0.35,
    "C2/C":    0.50,
    "D2/D":    0.80,
}


def get_failure_probability(rating: str) -> float:
    """Get 10-year cumulative probability of failure from a synthetic rating.

    Parameters
    ----------
    rating : str
        Synthetic rating string matching one of the keys in DEFAULT_RATES
        (e.g. ``"B2/B"``, ``"Caa/CCC"``).

    Returns
    -------
    float
        10-year cumulative default probability (decimal, 0–1).

    Raises
    ------
    KeyError
        If ``rating`` is not found in DEFAULT_RATES.
    """
    try:
        return DEFAULT_RATES[rating]
    except KeyError:
        valid = ", ".join(DEFAULT_RATES.keys())
        raise KeyError(
            f"Unknown rating '{rating}'. Valid ratings: {valid}"
        )


def estimate_distress_proceeds(
    book_value_of_assets: float,
    liquidation_pct: float = 0.50,
) -> float:
    """Estimate what shareholders receive if the firm fails (distress proceeds).

    In distress, assets are typically sold at a discount to book value.
    Creditors are paid first; the residual — often zero or negative — goes
    to shareholders.  This function returns the gross liquidation value of
    assets (before debt repayment) as a per-share proxy, which the caller
    should net against debt where appropriate.

    A ``liquidation_pct`` of 0.50 means assets fetch 50 cents on the dollar,
    consistent with Damodaran's mid-range assumption.  Typical range: 25–75%.

    Parameters
    ----------
    book_value_of_assets : float
        Total book value of assets ($).  Use total assets from the balance
        sheet, not net assets.
    liquidation_pct : float, optional
        Fraction of book value realised in a distress sale.  Default 0.50.

    Returns
    -------
    float
        Estimated proceeds from asset liquidation ($).

    Raises
    ------
    ValueError
        If ``liquidation_pct`` is not in (0, 1].
    """
    if not (0.0 < liquidation_pct <= 1.0):
        raise ValueError(
            f"liquidation_pct must be in (0, 1], got {liquidation_pct}."
        )
    return book_value_of_assets * liquidation_pct


def failure_adjusted_valuation(
    going_concern_value: float,
    probability_of_failure: float,
    distress_proceeds: float,
) -> dict:
    """Apply failure probability to a going-concern valuation.

    Damodaran's formula:

        Adjusted Value = GC_Value × (1 − P_failure)
                       + Distress_Proceeds × P_failure

    The result is always a weighted average of the two scenarios.  When
    ``going_concern_value`` is already negative the firm is effectively
    already in financial distress; the adjustment still applies but
    ``value_lost_to_distress`` will be small (or negative, indicating that
    distress proceeds partially recover value).

    Parameters
    ----------
    going_concern_value : float
        Intrinsic value per share (or total equity) from the DCF/DDM engine
        before any distress adjustment.
    probability_of_failure : float
        Probability the firm defaults / fails (decimal, 0–1).
    distress_proceeds : float
        Estimated equity value per share (or total) in a distress scenario.
        Often close to zero when debt exceeds liquidation value.

    Returns
    -------
    dict with keys:
        adjusted_value          : float  — weighted-average value
        going_concern_value     : float  — input GC value (unchanged)
        failure_probability     : float  — input probability (unchanged)
        distress_proceeds       : float  — input distress proceeds (unchanged)
        value_lost_to_distress  : float  — GC_value − adjusted_value
                                          (positive = value destroyed by
                                           distress risk)

    Raises
    ------
    ValueError
        If ``probability_of_failure`` is not in [0, 1].
    """
    if not (0.0 <= probability_of_failure <= 1.0):
        raise ValueError(
            f"probability_of_failure must be in [0, 1], got {probability_of_failure}."
        )

    adjusted_value = (
        going_concern_value * (1.0 - probability_of_failure)
        + distress_proceeds * probability_of_failure
    )
    value_lost_to_distress = going_concern_value - adjusted_value

    return {
        "adjusted_value": adjusted_value,
        "going_concern_value": going_concern_value,
        "failure_probability": probability_of_failure,
        "distress_proceeds": distress_proceeds,
        "value_lost_to_distress": value_lost_to_distress,
    }
