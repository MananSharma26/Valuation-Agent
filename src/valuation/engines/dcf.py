"""
dcf.py — Deterministic DCF valuation engines.

Implements:
  - Gordon Growth Model (single-stage, for stable dividend-paying firms)
  - FCFF Multi-Stage DCF (high-growth + stable terminal phase)
  - DDM Multi-Stage (Dividend Discount Model, for financial firms)

No LLM calls. No consensus estimates. All inputs must be supplied by caller.

Methodology: Damodaran (Investment Valuation, 3rd ed.)
"""

from __future__ import annotations

import math
from typing import Callable, List

from valuation.engines.schedules import reinvestment_s2c


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


# ---------------------------------------------------------------------------
# DDM — Dividend Discount Model (for financial firms)
# ---------------------------------------------------------------------------

def ddm_valuation(
    current_eps: float,
    growth_rates: List[float],
    payout_rates: List[float],
    cost_of_equities: List[float],
    stable_growth: float,
    stable_roe: float,
    stable_ke: float,
) -> dict:
    """
    Perform a multi-stage Dividend Discount Model (DDM) valuation.

    Appropriate for financial firms (banks, brokerages, insurance) where debt
    is a raw material and FCFF is not meaningful. Equity is valued directly
    via dividends paid to shareholders.

    Steps:
      1. Project EPS forward: eps_t = eps_{t-1} * (1 + g_t)
      2. Compute DPS for each year: dps_t = eps_t * payout_t
      3. Discount dividends to present using cumulative cost of equity
      4. Terminal price (Gordon Growth on stable EPS):
             stable_payout = 1 - stable_growth / stable_roe
             terminal_price = EPS_n * (1 + stable_growth) * stable_payout
                              / (stable_ke - stable_growth)
      5. PV of terminal price = terminal_price / cumulative_discount_n
      6. Value per share = sum(PV_dividends) + PV_terminal

    Parameters
    ----------
    current_eps : float
        Trailing earnings per share (EPS0).
    growth_rates : list of float
        Year-by-year EPS growth rates (length = n).
    payout_rates : list of float
        Year-by-year dividend payout ratios as a decimal (length = n).
    cost_of_equities : list of float
        Year-by-year cost of equity for discounting (length = n).
    stable_growth : float
        Perpetual EPS growth rate in the stable phase.
    stable_roe : float
        Return on equity in the stable phase (used to derive stable payout).
    stable_ke : float
        Cost of equity in the stable phase.

    Returns
    -------
    dict with keys:
        value_per_share : float — intrinsic equity value per share
        pv_dividends    : float — sum of PV of explicit-period dividends
        pv_terminal     : float — PV of the terminal price
        terminal_price  : float — undiscounted terminal price at end of year n
        yearly_eps      : list[float] — projected EPS for each year
        yearly_dps      : list[float] — projected DPS for each year
        yearly_pv       : list[float] — PV of DPS for each year

    Raises
    ------
    ValueError
        If stable_ke <= stable_growth (terminal price undefined / negative).
        If growth_rates, payout_rates, and cost_of_equities differ in length.
    """
    n = len(growth_rates)
    if len(payout_rates) != n or len(cost_of_equities) != n:
        raise ValueError(
            "growth_rates, payout_rates, and cost_of_equities must all have the same length. "
            f"Got lengths: {n}, {len(payout_rates)}, {len(cost_of_equities)}."
        )
    if stable_ke <= stable_growth:
        raise ValueError(
            f"stable_ke ({stable_ke:.4f}) must be strictly greater than "
            f"stable_growth ({stable_growth:.4f}) for a finite terminal price."
        )

    # Step 1 & 2: Project EPS and compute DPS
    yearly_eps: List[float] = []
    yearly_dps: List[float] = []
    eps = current_eps
    for g, payout in zip(growth_rates, payout_rates):
        eps = eps * (1.0 + g)
        yearly_eps.append(eps)
        yearly_dps.append(eps * payout)

    # Step 3: Discount dividends using cumulative cost of equity
    yearly_pv = discount_cashflows(yearly_dps, cost_of_equities)
    pv_dividends = sum(yearly_pv)

    # Step 4: Terminal price at end of year n
    final_eps = yearly_eps[-1] if yearly_eps else current_eps
    stable_payout = 1.0 - stable_growth / stable_roe
    terminal_price = final_eps * (1.0 + stable_growth) * stable_payout / (stable_ke - stable_growth)

    # Step 5: Discount terminal price through cumulative Ke at year n
    cumulative_discount_n = math.prod(1.0 + ke for ke in cost_of_equities) if cost_of_equities else 1.0
    pv_terminal = terminal_price / cumulative_discount_n

    # Step 6: Total equity value per share
    value_per_share = pv_dividends + pv_terminal

    return {
        "value_per_share": value_per_share,
        "pv_dividends": pv_dividends,
        "pv_terminal": pv_terminal,
        "terminal_price": terminal_price,
        "yearly_eps": yearly_eps,
        "yearly_dps": yearly_dps,
        "yearly_pv": yearly_pv,
    }


# ---------------------------------------------------------------------------
# Revenue-Based FCFF Valuation (v2) — Damodaran new-style spreadsheets
# ---------------------------------------------------------------------------

def fcff_valuation_v2(
    base_revenue: float,
    base_ebit: float,
    revenue_growth_rates: list[float],
    operating_margins: list[float],
    tax_rates: list[float],
    waccs: list[float],
    sales_to_capital: float,
    stable_growth: float,
    stable_roc: float,
    stable_wacc: float,
    stable_tax_rate: float,
    cash: float = 0.0,
    debt: float = 0.0,
    non_operating_assets: float = 0.0,
    minority_interests: float = 0.0,
    options_value: float = 0.0,
    shares_outstanding: float = 1.0,
    rd_adjustment: float = 0.0,
    research_asset: float = 0.0,
    base_invested_capital: float = 0.0,
) -> dict:
    """Revenue-based FCFF DCF with Damodaran-style transitions.

    Key differences from fcff_valuation:
    - Revenue-driven projections (not EBIT-driven)
    - Operating margin convergence
    - Sales-to-capital reinvestment
    - Per-year WACC and tax rate (supports transitions)
    - R&D adjustment to base EBIT and invested capital
    - Tracks invested capital and ROIC

    Parameters
    ----------
    base_revenue : float
        Trailing twelve-month revenue (year 0).
    base_ebit : float
        Trailing EBIT before R&D adjustment (year 0).
    revenue_growth_rates : list of float
        Year-by-year revenue growth rates (length = n).
    operating_margins : list of float
        Year-by-year operating margins (length = n).
    tax_rates : list of float
        Year-by-year tax rates (length = n).
    waccs : list of float
        Year-by-year WACCs (length = n).
    sales_to_capital : float
        Sales-to-capital ratio for reinvestment calculation.
    stable_growth : float
        Terminal perpetual growth rate.
    stable_roc : float
        Terminal return on capital.
    stable_wacc : float
        Terminal WACC.
    stable_tax_rate : float
        Terminal marginal tax rate.
    cash : float
        Cash and near-cash assets.
    debt : float
        Market value of debt.
    non_operating_assets : float
        Non-operating assets (cross-holdings, etc.).
    minority_interests : float
        Minority interests (subtracted from equity).
    options_value : float
        Value of employee stock options (subtracted from equity).
    shares_outstanding : float
        Diluted shares outstanding.
    rd_adjustment : float
        EBIT adjustment from R&D capitalization (current_rd - amortization).
    research_asset : float
        Total unamortized R&D asset (added to invested capital).
    base_invested_capital : float
        Book equity + book debt - cash (before R&D adjustment).

    Returns
    -------
    dict
        Comprehensive valuation output including yearly projections.

    Raises
    ------
    ValueError
        If stable_wacc <= stable_growth.
    """
    n = len(revenue_growth_rates)

    # Adjust base EBIT for R&D if applicable
    adjusted_base_ebit = base_ebit + rd_adjustment

    # Track invested capital
    invested_capital = base_invested_capital + research_asset
    if invested_capital <= 0:
        invested_capital = base_revenue / sales_to_capital if sales_to_capital > 0 else base_revenue

    # Project year by year
    revenue = base_revenue
    yearly_revenue: List[float] = []
    yearly_ebit: List[float] = []
    yearly_ebit_at: List[float] = []
    yearly_reinvestment: List[float] = []
    yearly_fcff: List[float] = []
    yearly_ic: List[float] = []
    yearly_roic: List[float] = []

    for t in range(n):
        prev_revenue = revenue
        revenue = revenue * (1 + revenue_growth_rates[t])
        ebit = revenue * operating_margins[t]
        ebit_at = ebit * (1 - tax_rates[t])
        reinvestment = reinvestment_s2c(prev_revenue, revenue, sales_to_capital)
        fcff = ebit_at - reinvestment

        roic = ebit_at / invested_capital if invested_capital > 0 else 0
        invested_capital = invested_capital + reinvestment

        yearly_revenue.append(revenue)
        yearly_ebit.append(ebit)
        yearly_ebit_at.append(ebit_at)
        yearly_reinvestment.append(reinvestment)
        yearly_fcff.append(fcff)
        yearly_ic.append(invested_capital)
        yearly_roic.append(roic)

    # Discount FCFFs
    yearly_pv = discount_cashflows(yearly_fcff, waccs)
    pv_high_growth = sum(yearly_pv)

    # Terminal value
    terminal_ebit_at = yearly_ebit_at[-1] * (1 + stable_growth)
    terminal_reinvestment_rate = stable_growth / stable_roc if stable_roc > 0 else 0
    terminal_fcff = terminal_ebit_at * (1 - terminal_reinvestment_rate)

    if stable_wacc <= stable_growth:
        raise ValueError(f"stable_wacc ({stable_wacc}) must exceed stable_growth ({stable_growth})")

    terminal_value = terminal_fcff / (stable_wacc - stable_growth)

    # Discount terminal value
    cumulative_discount = 1.0
    for w in waccs:
        cumulative_discount *= (1 + w)
    pv_terminal = terminal_value / cumulative_discount

    # Enterprise value
    enterprise_value = pv_high_growth + pv_terminal

    # Bridge to equity
    equity_value = enterprise_value + cash - debt + non_operating_assets - minority_interests - options_value
    equity_value_per_share = equity_value / shares_outstanding if shares_outstanding > 0 else 0

    return {
        "enterprise_value": enterprise_value,
        "equity_value": equity_value,
        "equity_value_per_share": equity_value_per_share,
        "pv_high_growth": pv_high_growth,
        "pv_terminal": pv_terminal,
        "terminal_value": terminal_value,
        "terminal_fcff": terminal_fcff,
        "yearly_revenue": yearly_revenue,
        "yearly_ebit": yearly_ebit,
        "yearly_ebit_at": yearly_ebit_at,
        "yearly_reinvestment": yearly_reinvestment,
        "yearly_fcff": yearly_fcff,
        "yearly_pv": yearly_pv,
        "yearly_ic": yearly_ic,
        "yearly_roic": yearly_roic,
        "rd_adjustment": rd_adjustment,
        "research_asset": research_asset,
    }


# ---------------------------------------------------------------------------
# Sensitivity Table Generators
# ---------------------------------------------------------------------------

def sensitivity_table(
    base_params: dict,
    vary_param: str,
    vary_values: list[float],
    valuation_fn: Callable,
) -> dict[float, float]:
    """One-way sensitivity: vary one parameter, compute value for each.
    Returns {param_value: valuation_result}. Catches ValueError/ZeroDivisionError as NaN."""
    results = {}
    for v in vary_values:
        params = {**base_params, vary_param: v}
        try:
            results[v] = valuation_fn(**params)
        except (ValueError, ZeroDivisionError):
            results[v] = float("nan")
    return results


def two_way_sensitivity_table(
    base_params: dict,
    row_param: str,
    row_values: list[float],
    col_param: str,
    col_values: list[float],
    valuation_fn: Callable,
) -> dict[float, dict[float, float]]:
    """Two-way sensitivity: vary two parameters.
    Returns {row_value: {col_value: valuation_result}}."""
    results = {}
    for rv in row_values:
        results[rv] = {}
        for cv in col_values:
            params = {**base_params, row_param: rv, col_param: cv}
            try:
                results[rv][cv] = valuation_fn(**params)
            except (ValueError, ZeroDivisionError):
                results[rv][cv] = float("nan")
    return results
