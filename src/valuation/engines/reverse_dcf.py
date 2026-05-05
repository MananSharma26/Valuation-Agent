"""Reverse DCF: solve for implied assumptions given market price.

Given a market price, work backwards to find what growth rate, operating margin,
or WACC would make the DCF equal to that price. This explains the gap between
our DCF and market — not by saying "the market is wrong" but by quantifying
what the market must be assuming.
"""

from __future__ import annotations

from valuation.engines.dcf import fcff_valuation_v2
from valuation.engines.schedules import wacc_schedule, tax_schedule, margin_convergence_schedule


def implied_growth_rate(
    market_price: float,
    base_revenue: float,
    base_ebit: float,
    operating_margin: float,
    tax_rate: float,
    wacc: float,
    stable_wacc: float,
    sales_to_capital: float,
    stable_growth: float,
    stable_roc: float,
    cash: float,
    debt: float,
    shares_outstanding: float,
    n_years: int = 10,
    tolerance: float = 0.5,  # within $0.50 of target
    max_iterations: int = 50,
) -> dict:
    """Binary search for the revenue growth rate that makes DCF value = market price.

    Uses a two-phase growth schedule: constant at the implied rate for the first
    half of the projection, then linearly converging to stable_growth by year n.

    Parameters
    ----------
    market_price : float
        Current market price per share.
    base_revenue : float
        Trailing twelve-month revenue (year 0).
    base_ebit : float
        Trailing EBIT (year 0), used to seed the valuation engine.
    operating_margin : float
        Constant operating margin applied across all projection years.
    tax_rate : float
        Effective tax rate (held flat; ramps to 25% marginal in years 6-10).
    wacc : float
        Initial WACC (held flat for first n_constant years, then ramps).
    stable_wacc : float
        Terminal WACC used for both the schedule and terminal value denominator.
    sales_to_capital : float
        Sales-to-capital ratio for reinvestment calculation.
    stable_growth : float
        Perpetual growth rate in the stable phase (lower bound of search).
    stable_roc : float
        Return on capital in stable phase.
    cash : float
        Cash and near-cash assets added to equity bridge.
    debt : float
        Market value of debt subtracted in equity bridge.
    shares_outstanding : float
        Diluted shares outstanding for per-share conversion.
    n_years : int
        Total projection years. Default 10.
    tolerance : float
        Convergence threshold in price per share. Default $0.50.
    max_iterations : int
        Maximum binary search iterations before declaring non-convergence.

    Returns
    -------
    dict with keys:
        implied_growth : float — implied revenue CAGR (high-growth phase)
        implied_value  : float — DCF value at implied_growth
        iterations     : int   — number of binary search iterations used
        converged      : bool  — whether tolerance was met
        summary        : str   — human-readable one-liner
    """
    n_constant = n_years // 2

    low, high = stable_growth, 0.50  # search between stable_growth and 50%
    mid = (low + high) / 2
    value = 0.0

    for i in range(max_iterations):
        mid = (low + high) / 2

        # Build growth schedule: constant for first half, then linear convergence
        n_ramp = n_years - n_constant
        growth_rates = []
        for t in range(1, n_years + 1):
            if t <= n_constant:
                growth_rates.append(mid)
            else:
                step = (t - n_constant)
                fraction = step / n_ramp if n_ramp > 0 else 1.0
                growth_rates.append(mid + fraction * (stable_growth - mid))

        margins = [operating_margin] * n_years
        taxes = tax_schedule(tax_rate, 0.25, n_years, n_constant)
        waccs = wacc_schedule(wacc, stable_wacc, n_years, n_constant)

        try:
            result = fcff_valuation_v2(
                base_revenue=base_revenue,
                base_ebit=base_ebit,
                revenue_growth_rates=growth_rates,
                operating_margins=margins,
                tax_rates=taxes,
                waccs=waccs,
                sales_to_capital=sales_to_capital,
                stable_growth=stable_growth,
                stable_roc=stable_roc,
                stable_wacc=stable_wacc,
                stable_tax_rate=0.25,
                cash=cash,
                debt=debt,
                shares_outstanding=shares_outstanding,
            )
            value = result["equity_value_per_share"]
        except (ValueError, ZeroDivisionError):
            value = 0.0

        if abs(value - market_price) < tolerance:
            return {
                "implied_growth": mid,
                "implied_value": value,
                "iterations": i + 1,
                "converged": True,
                "summary": f"Market implies {mid:.1%} revenue growth",
            }
        elif value < market_price:
            low = mid
        else:
            high = mid

    return {
        "implied_growth": mid,
        "implied_value": value,
        "iterations": max_iterations,
        "converged": False,
        "summary": f"Market implies >{high:.0%} growth (did not converge)",
    }


def implied_wacc(
    market_price: float,
    base_revenue: float,
    base_ebit: float,
    revenue_growth_rates: list[float],
    operating_margin: float,
    tax_rate: float,
    sales_to_capital: float,
    stable_growth: float,
    stable_roc: float,
    cash: float,
    debt: float,
    shares_outstanding: float,
    n_years: int = 10,
    tolerance: float = 0.5,
    max_iterations: int = 50,
) -> dict:
    """Binary search for WACC that makes DCF value = market price.

    A higher market price implies a lower discount rate (and vice versa), so the
    search is monotonically decreasing in WACC. The stable WACC is set to
    ``mid - 0.02`` to mirror the typical Damodaran pattern of a 200bp spread
    between current and terminal WACC.

    Parameters
    ----------
    market_price : float
        Current market price per share.
    base_revenue : float
        Trailing twelve-month revenue (year 0).
    base_ebit : float
        Trailing EBIT (year 0).
    revenue_growth_rates : list[float]
        Year-by-year revenue growth rates (length = n_years).
    operating_margin : float
        Constant operating margin applied across all projection years.
    tax_rate : float
        Effective tax rate (ramps to 25% marginal in second half).
    sales_to_capital : float
        Sales-to-capital ratio for reinvestment.
    stable_growth : float
        Perpetual terminal growth rate.
    stable_roc : float
        Return on capital in stable phase.
    cash : float
        Cash and near-cash assets.
    debt : float
        Market value of debt.
    shares_outstanding : float
        Diluted shares outstanding.
    n_years : int
        Total projection years. Default 10.
    tolerance : float
        Convergence threshold in price per share. Default $0.50.
    max_iterations : int
        Maximum binary search iterations.

    Returns
    -------
    dict with keys:
        implied_wacc   : float — discount rate implied by market price
        implied_value  : float — DCF value at implied_wacc
        iterations     : int   — iterations used
        converged      : bool  — whether tolerance was met
        summary        : str   — human-readable one-liner
    """
    n_constant = n_years // 2

    # Search between 4% and 20%; higher WACC → lower value
    low, high = 0.04, 0.20
    mid = (low + high) / 2
    value = 0.0

    for i in range(max_iterations):
        mid = (low + high) / 2
        stable_w = max(mid - 0.02, stable_growth + 0.001)  # ensure stable_wacc > stable_growth
        waccs = wacc_schedule(mid, stable_w, n_years, n_constant)
        margins = [operating_margin] * n_years
        taxes = tax_schedule(tax_rate, 0.25, n_years, n_constant)

        try:
            result = fcff_valuation_v2(
                base_revenue=base_revenue,
                base_ebit=base_ebit,
                revenue_growth_rates=revenue_growth_rates,
                operating_margins=margins,
                tax_rates=taxes,
                waccs=waccs,
                sales_to_capital=sales_to_capital,
                stable_growth=stable_growth,
                stable_roc=stable_roc,
                stable_wacc=stable_w,
                stable_tax_rate=0.25,
                cash=cash,
                debt=debt,
                shares_outstanding=shares_outstanding,
            )
            value = result["equity_value_per_share"]
        except (ValueError, ZeroDivisionError):
            value = float("inf")

        if abs(value - market_price) < tolerance:
            return {
                "implied_wacc": mid,
                "implied_value": value,
                "iterations": i + 1,
                "converged": True,
                "summary": f"Market implies WACC of {mid:.2%}",
            }
        elif value > market_price:
            # Value too high → WACC too low → raise WACC
            low = mid
        else:
            # Value too low → WACC too high → lower WACC
            high = mid

    return {
        "implied_wacc": mid,
        "implied_value": value,
        "iterations": max_iterations,
        "converged": False,
        "summary": f"Market implies WACC ~{mid:.2%} (approximate)",
    }


def reverse_dcf_summary(
    market_price: float,
    our_value: float,
    our_growth: float,
    our_wacc: float,
    implied_growth_result: dict,
    implied_wacc_result: dict,
) -> str:
    """Generate a human-readable summary of what the market price implies.

    Parameters
    ----------
    market_price : float
        Current market price per share.
    our_value : float
        Our DCF intrinsic value per share.
    our_growth : float
        Our assumed revenue growth rate (high-growth phase).
    our_wacc : float
        Our assumed WACC.
    implied_growth_result : dict
        Output of ``implied_growth_rate()``.
    implied_wacc_result : dict
        Output of ``implied_wacc()``.

    Returns
    -------
    str
        Multi-line summary string.
    """
    lines = [
        "REVERSE DCF: What does the market price imply?",
        f"  Market price: {market_price:,.2f}",
        f"  Our DCF value: {our_value:,.2f} ({(our_value / market_price - 1) * 100:+.1f}%)",
        "",
    ]

    if implied_growth_result.get("converged"):
        ig = implied_growth_result["implied_growth"]
        lines.append(f"  Implied growth: {ig:.1%} (we use {our_growth:.1%})")
        if ig > our_growth:
            lines.append(
                f"  \u2192 Market expects {(ig - our_growth) * 100:.1f}pp MORE growth than us"
            )
        else:
            lines.append(
                f"  \u2192 Market expects {(our_growth - ig) * 100:.1f}pp LESS growth than us"
            )
    else:
        lines.append(f"  Implied growth: {implied_growth_result.get('summary', 'N/A')}")

    if implied_wacc_result.get("converged"):
        iw = implied_wacc_result["implied_wacc"]
        lines.append(f"  Implied WACC: {iw:.2%} (we use {our_wacc:.2%})")
        if iw < our_wacc:
            lines.append(
                f"  \u2192 Market uses {(our_wacc - iw) * 100:.1f}pp LOWER discount rate"
            )
        else:
            lines.append(
                f"  \u2192 Market uses {(iw - our_wacc) * 100:.1f}pp HIGHER discount rate"
            )
    else:
        lines.append(f"  Implied WACC: {implied_wacc_result.get('summary', 'N/A')}")

    return "\n".join(lines)
