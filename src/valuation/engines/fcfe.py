"""Free Cash Flow to Equity (FCFE) discount model.

For non-financial companies where dividends significantly differ from FCFE.
Damodaran (model.pdf slide 215): Use FCFE when dividends < 80% of FCFE
or dividends > 110% of FCFE over a 5-year period.

FCFE = Net Income - (1-delta)(CapEx - Depreciation) - (1-delta)(Change in WC) + New Debt
where delta = debt ratio (D/(D+E))
"""

from __future__ import annotations


def compute_fcfe(
    net_income: float,
    capex: float,
    depreciation: float,
    change_in_wc: float,
    debt_ratio: float,
    new_debt: float = 0,
) -> float:
    """Compute FCFE for a single period.

    FCFE = NI - (1-delta)(CapEx - Depr) - (1-delta)(delta WC) + New Debt
    """
    equity_share = 1 - debt_ratio
    net_capex = capex - depreciation
    fcfe = net_income - equity_share * net_capex - equity_share * change_in_wc + new_debt
    return fcfe


def fcfe_valuation(
    current_net_income: float,
    growth_rates: list[float],
    capex_to_depreciation: float,
    wc_to_revenue_change: float,
    debt_ratio: float,
    cost_of_equities: list[float],
    stable_growth: float,
    stable_roe: float,
    stable_ke: float,
    current_depreciation: float = 0,
    current_revenue: float = 0,
    revenue_growth_rates: list[float] | None = None,
    cash: float = 0,
    debt: float = 0,
    shares_outstanding: float = 1,
) -> dict:
    """FCFE discount model for non-financial companies.

    Discounts FCFE at cost of equity (not WACC).
    Appropriate for companies where dividends != FCFE.
    """
    n = len(growth_rates)
    if revenue_growth_rates is None:
        revenue_growth_rates = growth_rates

    ni = current_net_income
    depr = current_depreciation
    rev = current_revenue

    yearly_ni: list[float] = []
    yearly_fcfe: list[float] = []
    yearly_pv: list[float] = []

    cumulative_discount = 1.0

    for t in range(n):
        ni = ni * (1 + growth_rates[t])
        rev_new = rev * (1 + revenue_growth_rates[t])
        depr_t = depr * (1 + revenue_growth_rates[t])  # depreciation grows with revenue
        capex_t = depr_t * capex_to_depreciation
        wc_change = (rev_new - rev) * wc_to_revenue_change

        fcfe = compute_fcfe(ni, capex_t, depr_t, wc_change, debt_ratio)

        cumulative_discount *= (1 + cost_of_equities[t])
        pv = fcfe / cumulative_discount

        yearly_ni.append(ni)
        yearly_fcfe.append(fcfe)
        yearly_pv.append(pv)

        rev = rev_new

    pv_fcfe = sum(yearly_pv)

    # Terminal value
    stable_payout = 1 - stable_growth / stable_roe if stable_roe > 0 else 0.7
    terminal_ni = yearly_ni[-1] * (1 + stable_growth)
    terminal_fcfe = terminal_ni * stable_payout

    if stable_ke <= stable_growth:
        raise ValueError(f"stable_ke ({stable_ke}) must exceed stable_growth ({stable_growth})")

    terminal_value = terminal_fcfe / (stable_ke - stable_growth)
    pv_terminal = terminal_value / cumulative_discount

    equity_value = pv_fcfe + pv_terminal
    value_per_share = equity_value / shares_outstanding if shares_outstanding > 0 else 0

    return {
        "value_per_share": value_per_share,
        "equity_value": equity_value,
        "pv_fcfe": pv_fcfe,
        "pv_terminal": pv_terminal,
        "terminal_value": terminal_value,
        "yearly_ni": yearly_ni,
        "yearly_fcfe": yearly_fcfe,
        "yearly_pv": yearly_pv,
        "model": "fcfe",
    }


def should_use_fcfe(dividends_paid: float, fcfe: float, n_years: int = 5) -> bool:
    """Damodaran rule: use FCFE if dividends < 80% or > 110% of FCFE over 5 years."""
    if fcfe <= 0:
        return False
    ratio = dividends_paid / fcfe
    return ratio < 0.80 or ratio > 1.10
