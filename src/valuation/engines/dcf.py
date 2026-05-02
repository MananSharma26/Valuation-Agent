"""
dcf.py — Deterministic DCF valuation engines.

Implements:
  - Gordon Growth Model (single-stage, for stable dividend-paying firms)
  - FCFF Multi-Stage DCF (high-growth + stable terminal phase)

No LLM calls. No consensus estimates. All inputs must be supplied by caller.

Methodology: Damodaran (Investment Valuation, 3rd ed.)
"""

from __future__ import annotations

import math
from typing import List


# ---------------------------------------------------------------------------
# Gordon Growth Model
# ---------------------------------------------------------------------------

def gordon_growth_value(current_dividend: float, cost_of_equity: float, growth_rate: float) -> float:
    """
    Compute intrinsic value via the Gordon Growth (Dividend Discount) Model.

    Formula: Value = DPS1 / (Ke - g)
           = DPS0 * (1 + g) / (Ke - g)

    Parameters
    ----------
    current_dividend : float
        Current annual dividend per share (DPS0).
    cost_of_equity : float
        Required return on equity as a decimal (e.g., 0.077 for 7.7%).
    growth_rate : float
        Perpetual dividend growth rate as a decimal.

    Returns
    -------
    float
        Estimated intrinsic value per share.

    Raises
    ------
    ValueError
        If growth_rate >= cost_of_equity (model undefined; negative or infinite value).

    Verification anchor (Damodaran ConEd example):
        DPS=2.32, Ke=7.7%, g=2.1% → Value ≈ $42.30
    """
    if growth_rate >= cost_of_equity:
        raise ValueError(
            f"growth_rate ({growth_rate:.4f}) must be strictly less than "
            f"cost_of_equity ({cost_of_equity:.4f}) for the Gordon Growth Model."
        )
    dps_next = current_dividend * (1.0 + growth_rate)
    return dps_next / (cost_of_equity - growth_rate)


def gordon_implied_growth(price: float, current_dividend: float, cost_of_equity: float) -> float:
    """
    Reverse-engineer the implied perpetual growth rate from a market price.

    Derivation from Value = DPS0*(1+g)/(Ke-g):
        P * (Ke - g) = DPS0 * (1 + g)
        P*Ke - P*g   = DPS0 + DPS0*g
        P*Ke - DPS0  = g * (P + DPS0)
        g = (P*Ke - DPS0) / (P + DPS0)

    Parameters
    ----------
    price : float
        Current market price per share.
    current_dividend : float
        Current annual dividend per share (DPS0).
    cost_of_equity : float
        Required return on equity as a decimal.

    Returns
    -------
    float
        Implied perpetual growth rate as a decimal.
    """
    return (price * cost_of_equity - current_dividend) / (price + current_dividend)


# ---------------------------------------------------------------------------
# FCFF Helpers
# ---------------------------------------------------------------------------

def compute_fcff(ebit_after_tax: float, reinvestment_rate: float) -> float:
    """
    Compute Free Cash Flow to Firm (FCFF) from after-tax EBIT.

    Formula: FCFF = EBIT(1-t) * (1 - reinvestment_rate)

    A negative reinvestment_rate represents a shrinking firm (asset liquidation).
    reinvestment_rate > 1 means the firm reinvests more than it earns (acquisition-heavy).

    Parameters
    ----------
    ebit_after_tax : float
        EBIT after taxes: EBIT * (1 - marginal_tax_rate).
    reinvestment_rate : float
        Fraction of EBIT(1-t) reinvested back into the business.

    Returns
    -------
    float
        FCFF for the period.
    """
    return ebit_after_tax * (1.0 - reinvestment_rate)


def compute_terminal_value(
    final_ebit_after_tax: float,
    stable_growth: float,
    stable_roc: float,
    wacc: float,
) -> float:
    """
    Compute the terminal (continuing) value at the end of the high-growth period.

    The stable reinvestment rate is derived from fundamentals:
        stable_reinvestment = stable_growth / stable_roc

    Then:
        FCFF_{n+1} = final_ebit_at * (1 + g) * (1 - stable_reinvestment)
        TV = FCFF_{n+1} / (WACC - g)

    Parameters
    ----------
    final_ebit_after_tax : float
        EBIT(1-t) in the final year of the high-growth phase (year n).
    stable_growth : float
        Perpetual growth rate in stable phase as a decimal.
    stable_roc : float
        Return on capital in stable phase as a decimal.
    wacc : float
        Stable-phase WACC as a decimal.

    Returns
    -------
    float
        Terminal value as of end of year n (before discounting to present).

    Raises
    ------
    ValueError
        If wacc <= stable_growth (terminal value undefined).
    """
    if wacc <= stable_growth:
        raise ValueError(
            f"wacc ({wacc:.4f}) must be strictly greater than stable_growth "
            f"({stable_growth:.4f}) for a finite terminal value."
        )
    stable_reinvestment = stable_growth / stable_roc
    fcff_terminal = final_ebit_after_tax * (1.0 + stable_growth) * (1.0 - stable_reinvestment)
    return fcff_terminal / (wacc - stable_growth)


def discount_cashflows(cashflows: List[float], waccs: List[float]) -> List[float]:
    """
    Discount a sequence of cash flows using cumulative (path-dependent) WACCs.

    PV_t = CF_t / product(1 + WACC_i, i=1..t)

    This handles time-varying discount rates correctly: each year's cash flow
    is discounted by the compounded product of all WACCs from year 1 through year t.

    Parameters
    ----------
    cashflows : list of float
        Cash flows at times t=1, 2, ..., n.
    waccs : list of float
        WACCs for periods 1, 2, ..., n. Must have the same length as cashflows.

    Returns
    -------
    list of float
        Present values corresponding to each cash flow.

    Raises
    ------
    ValueError
        If cashflows and waccs have different lengths.
    """
    if len(cashflows) != len(waccs):
        raise ValueError(
            f"cashflows (len={len(cashflows)}) and waccs (len={len(waccs)}) must have equal length."
        )
    present_values: List[float] = []
    cumulative_discount = 1.0
    for cf, w in zip(cashflows, waccs):
        cumulative_discount *= (1.0 + w)
        present_values.append(cf / cumulative_discount)
    return present_values


def interpolate_params(
    high_growth_value: float,
    stable_value: float,
    n_years: int,
    gradual: bool = True,
) -> List[float]:
    """
    Interpolate a parameter (e.g., growth rate, WACC, reinvestment rate) from a
    high-growth value toward a stable value over n_years.

    If gradual=True:
        - First half of years: hold at high_growth_value
        - Second half: linearly interpolate from high_growth_value to stable_value
          (inclusive of stable_value at the final year)

    If gradual=False:
        - All years set to high_growth_value (no transition; used when caller
          handles transition externally or wants a step function).

    Parameters
    ----------
    high_growth_value : float
        Starting value (high-growth phase).
    stable_value : float
        Ending value (stable phase).
    n_years : int
        Total number of projection years.
    gradual : bool
        Whether to apply gradual linear interpolation in the second half.

    Returns
    -------
    list of float
        Parameter values for years 1 through n_years (length = n_years).
    """
    if n_years <= 0:
        return []

    if not gradual:
        return [high_growth_value] * n_years

    transition_start = n_years // 2          # index (0-based) where interpolation begins
    transition_years = n_years - transition_start  # number of years in the interpolation window

    result: List[float] = []
    for i in range(n_years):
        if i < transition_start:
            result.append(high_growth_value)
        else:
            # i ranges from transition_start to n_years-1
            # fraction goes from 0 (at transition_start) to 1 (at n_years-1)
            step = i - transition_start
            fraction = step / (transition_years - 1) if transition_years > 1 else 1.0
            value = high_growth_value + fraction * (stable_value - high_growth_value)
            result.append(value)
    return result


# ---------------------------------------------------------------------------
# Full FCFF Valuation
# ---------------------------------------------------------------------------

def fcff_valuation(
    current_ebit_after_tax: float,
    growth_rates: List[float],
    reinvestment_rates: List[float],
    waccs: List[float],
    stable_growth: float,
    stable_roc: float,
    stable_wacc: float,
    cash: float = 0.0,
    debt: float = 0.0,
    non_operating_assets: float = 0.0,
    options_value: float = 0.0,
    shares_outstanding: float = 1.0,
) -> dict:
    """
    Perform a full multi-stage FCFF valuation.

    Steps:
      1. Project EBIT(1-t) forward: ebit_at_t = ebit_at_{t-1} * (1 + g_t)
      2. Compute FCFF for each year: FCFF_t = ebit_at_t * (1 - reinv_t)
      3. Discount FCFFs to present using cumulative WACCs
      4. Compute terminal value at end of final year using stable assumptions
      5. Discount terminal value to present
      6. Enterprise value = sum(PV_FCFF) + PV_terminal
      7. Equity value = EV + cash - debt + non_operating_assets - options_value
      8. Per-share value = equity_value / shares_outstanding

    Parameters
    ----------
    current_ebit_after_tax : float
        Base EBIT(1-t) (year 0, i.e., the most recent trailing value).
    growth_rates : list of float
        Year-by-year growth rates for the high-growth period (length = n).
    reinvestment_rates : list of float
        Year-by-year reinvestment rates (length = n).
    waccs : list of float
        Year-by-year WACCs for discounting (length = n).
    stable_growth : float
        Perpetual growth rate after year n.
    stable_roc : float
        Return on capital in stable phase.
    stable_wacc : float
        WACC in stable phase (used for terminal value denominator and discounting TV).
    cash : float
        Cash and near-cash assets (added to equity bridge). Default 0.
    debt : float
        Market value of debt (subtracted in equity bridge). Default 0.
    non_operating_assets : float
        Value of non-operating assets (added to equity bridge). Default 0.
    options_value : float
        Value of employee options / dilutive securities (subtracted). Default 0.
    shares_outstanding : float
        Diluted shares for per-share computation. Default 1.

    Returns
    -------
    dict with keys:
        enterprise_value       : float — EV = PV(FCFF) + PV(TV)
        equity_value           : float — EV + cash - debt + non_op - options
        equity_value_per_share : float — equity_value / shares_outstanding
        pv_high_growth         : float — sum of discounted high-growth FCFFs
        pv_terminal            : float — PV of terminal value
        terminal_value         : float — undiscounted terminal value
        yearly_fcff            : list[float] — FCFF for each projected year
        yearly_pv              : list[float] — PV of FCFF for each projected year
        yearly_ebit_at         : list[float] — EBIT(1-t) for each projected year

    Raises
    ------
    ValueError
        If growth_rates, reinvestment_rates, and waccs do not all have the same length,
        or if stable_wacc <= stable_growth.
    """
    n = len(growth_rates)
    if len(reinvestment_rates) != n or len(waccs) != n:
        raise ValueError(
            "growth_rates, reinvestment_rates, and waccs must all have the same length. "
            f"Got lengths: {n}, {len(reinvestment_rates)}, {len(waccs)}."
        )

    # Step 1 & 2: Project EBIT(1-t) and compute FCFF
    yearly_ebit_at: List[float] = []
    yearly_fcff: List[float] = []
    ebit_at = current_ebit_after_tax

    for g, reinv in zip(growth_rates, reinvestment_rates):
        ebit_at = ebit_at * (1.0 + g)
        yearly_ebit_at.append(ebit_at)
        yearly_fcff.append(compute_fcff(ebit_at, reinv))

    # Step 3: Discount FCFFs
    yearly_pv = discount_cashflows(yearly_fcff, waccs)
    pv_high_growth = sum(yearly_pv)

    # Step 4: Terminal value (at end of year n)
    final_ebit_at = yearly_ebit_at[-1] if yearly_ebit_at else current_ebit_after_tax
    terminal_value = compute_terminal_value(final_ebit_at, stable_growth, stable_roc, stable_wacc)

    # Step 5: PV of terminal value — discount through the same cumulative factor as year n,
    # then one additional stable_wacc period is already embedded in compute_terminal_value
    # (the TV formula uses FCFF_{n+1} in numerator, so TV is as-of end of year n).
    cumulative_discount_n = math.prod(1.0 + w for w in waccs) if waccs else 1.0
    pv_terminal = terminal_value / cumulative_discount_n

    # Step 6-8: Bridge to equity
    enterprise_value = pv_high_growth + pv_terminal
    equity_value = enterprise_value + cash - debt + non_operating_assets - options_value
    equity_value_per_share = equity_value / shares_outstanding

    return {
        "enterprise_value": enterprise_value,
        "equity_value": equity_value,
        "equity_value_per_share": equity_value_per_share,
        "pv_high_growth": pv_high_growth,
        "pv_terminal": pv_terminal,
        "terminal_value": terminal_value,
        "yearly_fcff": yearly_fcff,
        "yearly_pv": yearly_pv,
        "yearly_ebit_at": yearly_ebit_at,
    }
