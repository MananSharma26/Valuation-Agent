"""Equity Excess Return valuation model for financial firms.

This model values a financial firm's equity by decomposing it into:
  Value = Current Book Equity + PV(Excess Returns) + PV(Terminal Excess Return)

Excess Return_t = (ROE_t - COE_t) * Book Equity_{t-1}

This is an equity-side-only model: no WACC, no enterprise value, no debt bridge.
Appropriate for banks, brokerages, insurance companies where debt is a raw
material and FCFF is not meaningful.

Methodology: Damodaran (Investment Valuation, 3rd ed., Chapter 14)
"""

from __future__ import annotations

import math
from typing import List


def compute_excess_return(
    roe: float,
    coe: float,
    book_equity: float,
) -> float:
    """Compute excess return for a single period.

    Excess Return = (ROE - COE) * Book Equity

    Parameters
    ----------
    roe : float
        Return on equity for the period (decimal).
    coe : float
        Cost of equity for the period (decimal).
    book_equity : float
        Beginning-of-period book value of equity.

    Returns
    -------
    float
        Excess return for the period ($).
    """
    return (roe - coe) * book_equity


def excess_return_valuation(
    current_book_equity_per_share: float,
    current_eps: float,
    eps_growth_rates: List[float],
    payout_rates: List[float],
    roes: List[float],
    coes: List[float],
    stable_growth: float,
    stable_roe: float,
    stable_coe: float,
) -> dict:
    """Full equity excess return valuation for a financial firm.

    Steps:
      1. Project EPS forward using eps_growth_rates
      2. Compute DPS = EPS * payout_rate for each year
      3. Update book equity: BV_t = BV_{t-1} + EPS_t - DPS_t
      4. Compute excess return: ER_t = (ROE_t - COE_t) * BV_{t-1}
      5. Discount excess returns using cumulative COE
      6. Terminal excess return:
           ER_{n+1} = (stable_ROE - stable_COE) * BV_n
           TV = ER_{n+1} / (stable_COE - stable_growth)
      7. Value = current BV + PV(excess returns) + PV(terminal excess)

    Parameters
    ----------
    current_book_equity_per_share : float
        Current book value of equity per share (BV_0).
    current_eps : float
        Trailing EPS (EPS_0).
    eps_growth_rates : list of float
        Year-by-year EPS growth rates (length = n).
    payout_rates : list of float
        Year-by-year dividend payout ratios (length = n).
    roes : list of float
        Year-by-year ROE (length = n).
    coes : list of float
        Year-by-year cost of equity (length = n).
    stable_growth : float
        Perpetual earnings growth rate in stable phase.
    stable_roe : float
        ROE in stable phase.
    stable_coe : float
        Cost of equity in stable phase.

    Returns
    -------
    dict with keys:
        value_per_share       : float
        current_book_equity   : float
        pv_excess_returns     : float
        pv_terminal_excess    : float
        terminal_excess_value : float (undiscounted)
        yearly_eps            : list[float]
        yearly_dps            : list[float]
        yearly_bv             : list[float]
        yearly_excess_returns : list[float]
        yearly_pv             : list[float]

    Raises
    ------
    ValueError
        If list lengths don't match, or stable_coe <= stable_growth.
    """
    n = len(eps_growth_rates)
    if len(payout_rates) != n or len(roes) != n or len(coes) != n:
        raise ValueError(
            "eps_growth_rates, payout_rates, roes, and coes must all have the same length. "
            f"Got lengths: {n}, {len(payout_rates)}, {len(roes)}, {len(coes)}."
        )
    if stable_coe <= stable_growth:
        raise ValueError(
            f"stable_coe ({stable_coe:.4f}) must exceed stable_growth ({stable_growth:.4f}) "
            f"for a finite terminal value."
        )

    # Step 1-4: Project EPS, DPS, BV, and excess returns
    eps = current_eps
    bv = current_book_equity_per_share

    yearly_eps: List[float] = []
    yearly_dps: List[float] = []
    yearly_bv: List[float] = []
    yearly_excess_returns: List[float] = []

    for g, payout, roe, coe in zip(eps_growth_rates, payout_rates, roes, coes):
        eps = eps * (1.0 + g)
        dps = eps * payout
        er = compute_excess_return(roe, coe, bv)
        bv_new = bv + eps - dps

        yearly_eps.append(eps)
        yearly_dps.append(dps)
        yearly_excess_returns.append(er)
        yearly_bv.append(bv_new)
        bv = bv_new

    # Step 5: Discount excess returns using cumulative COE
    yearly_pv: List[float] = []
    cumulative_discount = 1.0
    for er, coe in zip(yearly_excess_returns, coes):
        cumulative_discount *= (1.0 + coe)
        yearly_pv.append(er / cumulative_discount)
    pv_excess_returns = sum(yearly_pv)

    # Step 6: Terminal excess return
    final_bv = yearly_bv[-1] if yearly_bv else current_book_equity_per_share
    terminal_er = (stable_roe - stable_coe) * final_bv
    terminal_excess_value = terminal_er / (stable_coe - stable_growth)

    # Discount terminal excess value
    cumulative_discount_n = math.prod(1.0 + coe for coe in coes) if coes else 1.0
    pv_terminal_excess = terminal_excess_value / cumulative_discount_n

    # Step 7: Value = BV + PV(excess returns) + PV(terminal excess)
    value_per_share = current_book_equity_per_share + pv_excess_returns + pv_terminal_excess

    return {
        "value_per_share": value_per_share,
        "current_book_equity": current_book_equity_per_share,
        "pv_excess_returns": pv_excess_returns,
        "pv_terminal_excess": pv_terminal_excess,
        "terminal_excess_value": terminal_excess_value,
        "yearly_eps": yearly_eps,
        "yearly_dps": yearly_dps,
        "yearly_bv": yearly_bv,
        "yearly_excess_returns": yearly_excess_returns,
        "yearly_pv": yearly_pv,
    }
