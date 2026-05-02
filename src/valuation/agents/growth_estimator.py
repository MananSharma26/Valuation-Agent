"""Growth rate estimation from company fundamentals.

Three methods:
  1. Historical CAGR — compound annual growth rate of revenue or net income
  2. Fundamental EPS growth — retention_ratio x ROE
  3. Fundamental EBIT growth — reinvestment_rate x ROC

All methods are deterministic. No LLM calls. No analyst consensus estimates.
I/B/E/S data is never used as an input — it is comparison-only in the final report.

Claude Code picks and adjusts the final growth rate after reviewing all three.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd


@dataclass
class GrowthEstimate:
    """A single growth rate estimate with method and reasoning."""

    value: float
    method: str
    reasoning: str
    inputs: dict[str, Any] | None = None


def compute_historical_cagr(
    financial_df: pd.DataFrame,
    column: str,
) -> GrowthEstimate | None:
    """Compute the CAGR of a financial line item across available years.

    Assumes rows are ordered oldest-first (row 0 = earliest year).
    If the DataFrame is in reverse chronological order (newest first),
    we detect this by comparing index values and reverse.

    Parameters
    ----------
    financial_df : pd.DataFrame
        Income statement or other financial statement DataFrame.
    column : str
        Column name to compute CAGR for (e.g. "Total Revenue", "Net Income").

    Returns
    -------
    GrowthEstimate or None
        None if CAGR cannot be computed (missing data, <2 points, zero/negative start).
    """
    if column not in financial_df.columns:
        return None

    series = financial_df[column].dropna()
    if len(series) < 2:
        return None

    # Ensure oldest-first ordering: if the DataFrame index is a DatetimeIndex
    # or monotonically decreasing integers, reverse it
    values = series.values.tolist()
    if hasattr(series.index, 'year') or (
        len(series.index) > 1
        and isinstance(series.index[0], (int, float))
        and series.index[0] > series.index[-1]
    ):
        values = list(reversed(values))

    start_val = float(values[0])
    end_val = float(values[-1])
    n_periods = len(values) - 1

    if start_val <= 0:
        return None

    if end_val <= 0:
        # Negative ending value: CAGR is not meaningful
        return None

    cagr = (end_val / start_val) ** (1.0 / n_periods) - 1.0

    return GrowthEstimate(
        value=cagr,
        method="historical_cagr",
        reasoning=(
            f"{column} CAGR over {n_periods} periods: "
            f"from {start_val:,.2f} to {end_val:,.2f} = {cagr:.2%}"
        ),
        inputs={
            "column": column,
            "start_value": start_val,
            "end_value": end_val,
            "n_periods": n_periods,
        },
    )


def compute_fundamental_eps_growth(
    net_income: float,
    book_equity: float,
    dividends_paid: float,
) -> GrowthEstimate | None:
    """Fundamental EPS growth = retention_ratio x ROE.

    Parameters
    ----------
    net_income : float
        Net income for the most recent year.
    book_equity : float
        Total stockholders' equity (book value of equity).
    dividends_paid : float
        Total dividends paid (absolute value, not per-share).

    Returns
    -------
    GrowthEstimate or None
        None if inputs make the calculation undefined.
    """
    if net_income <= 0 or book_equity <= 0:
        return None

    roe = net_income / book_equity
    payout_ratio = dividends_paid / net_income if net_income > 0 else 0.0
    payout_ratio = max(0.0, min(1.0, payout_ratio))  # clamp to [0, 1]
    retention_ratio = 1.0 - payout_ratio
    growth = retention_ratio * roe

    return GrowthEstimate(
        value=growth,
        method="fundamental_eps",
        reasoning=(
            f"Fundamental EPS growth: retention ratio {retention_ratio:.2%} "
            f"x ROE {roe:.2%} = {growth:.2%}. "
            f"(Net income={net_income:,.2f}, Book equity={book_equity:,.2f}, "
            f"Dividends={dividends_paid:,.2f})"
        ),
        inputs={
            "net_income": net_income,
            "book_equity": book_equity,
            "dividends_paid": dividends_paid,
            "roe": roe,
            "retention_ratio": retention_ratio,
            "payout_ratio": payout_ratio,
        },
    )


def compute_fundamental_ebit_growth(
    ebit_after_tax: float,
    total_capital: float,
    net_capex: float,
    change_in_wc: float,
) -> GrowthEstimate | None:
    """Fundamental EBIT growth = reinvestment_rate x ROC.

    Parameters
    ----------
    ebit_after_tax : float
        EBIT * (1 - tax_rate) for the most recent year.
    total_capital : float
        Total invested capital = book equity + total debt - cash.
    net_capex : float
        Capital expenditure minus depreciation.
    change_in_wc : float
        Change in non-cash working capital.

    Returns
    -------
    GrowthEstimate or None
        None if inputs make the calculation undefined.
    """
    if total_capital <= 0 or ebit_after_tax == 0:
        return None

    roc = ebit_after_tax / total_capital
    reinvestment = net_capex + change_in_wc
    reinvestment_rate = reinvestment / ebit_after_tax
    growth = reinvestment_rate * roc

    return GrowthEstimate(
        value=growth,
        method="fundamental_ebit",
        reasoning=(
            f"Fundamental EBIT growth: reinvestment rate {reinvestment_rate:.2%} "
            f"x ROC {roc:.2%} = {growth:.2%}. "
            f"(EBIT(1-t)={ebit_after_tax:,.2f}, Capital={total_capital:,.2f}, "
            f"Net CapEx={net_capex:,.2f}, dWC={change_in_wc:,.2f})"
        ),
        inputs={
            "ebit_after_tax": ebit_after_tax,
            "total_capital": total_capital,
            "net_capex": net_capex,
            "change_in_wc": change_in_wc,
            "roc": roc,
            "reinvestment_rate": reinvestment_rate,
        },
    )


def _safe_float(df: pd.DataFrame, col: str, row: int = -1) -> float | None:
    """Safely extract a float from a DataFrame cell. Returns None on failure."""
    if col not in df.columns:
        return None
    try:
        val = float(df[col].iloc[row])
        if pd.isna(val):
            return None
        return val
    except (IndexError, ValueError, TypeError):
        return None


def estimate_all_growth_rates(
    ctx: "ValuationContext",
) -> dict[str, GrowthEstimate | None]:
    """Compute all available growth rate estimates from a ValuationContext.

    Returns a dict with keys:
      - "historical_revenue": CAGR of Total Revenue
      - "historical_net_income": CAGR of Net Income
      - "fundamental_eps": retention_ratio x ROE
      - "fundamental_ebit": reinvestment_rate x ROC

    Each value is a GrowthEstimate or None if data is insufficient.

    Parameters
    ----------
    ctx : ValuationContext
        Must have financials populated (income_statement, balance_sheet,
        cash_flow, key_stats).

    Returns
    -------
    dict[str, GrowthEstimate | None]
    """
    result: dict[str, GrowthEstimate | None] = {
        "historical_revenue": None,
        "historical_net_income": None,
        "fundamental_eps": None,
        "fundamental_ebit": None,
    }

    inc = ctx.financials.income_statement
    bs = ctx.financials.balance_sheet
    cf = ctx.financials.cash_flow
    stats = ctx.financials.key_stats

    # --- Historical CAGRs ---
    if inc is not None and not inc.empty:
        result["historical_revenue"] = compute_historical_cagr(inc, "Total Revenue")
        result["historical_net_income"] = compute_historical_cagr(inc, "Net Income")

    # --- Fundamental EPS growth ---
    if inc is not None and bs is not None and not inc.empty and not bs.empty:
        net_income = _safe_float(inc, "Net Income")
        book_equity = _safe_float(bs, "Total Stockholders Equity")

        # Compute total dividends paid
        dividends_paid = 0.0
        dps = stats.get("dividend_per_share", 0) if stats else 0
        shares = stats.get("shares_outstanding", 0) if stats else 0
        if dps and shares:
            dividends_paid = float(dps) * float(shares)

        if net_income is not None and book_equity is not None:
            result["fundamental_eps"] = compute_fundamental_eps_growth(
                net_income=net_income,
                book_equity=book_equity,
                dividends_paid=dividends_paid,
            )

    # --- Fundamental EBIT growth ---
    if (
        inc is not None
        and bs is not None
        and cf is not None
        and not inc.empty
        and not bs.empty
        and not cf.empty
    ):
        # EBIT after tax
        ebit = _safe_float(inc, "EBIT")
        tax_rate = ctx.assumptions.tax_rate
        if ebit is not None and tax_rate is not None:
            ebit_after_tax = ebit * (1.0 - tax_rate)
        else:
            ebit_after_tax = None

        # Total capital = equity + debt - cash
        equity = _safe_float(bs, "Total Stockholders Equity")
        debt = _safe_float(bs, "Total Debt")
        cash = _safe_float(bs, "Cash And Cash Equivalents")
        if equity is not None:
            total_capital = equity + (debt or 0.0) - (cash or 0.0)
        else:
            total_capital = None

        # Net CapEx = CapEx - Depreciation
        capex = _safe_float(cf, "Capital Expenditure")
        dep = _safe_float(cf, "Depreciation And Amortization")
        if capex is not None:
            net_capex = abs(capex) - (dep or 0.0)  # CapEx is often negative in yfinance
        else:
            net_capex = None

        # Change in working capital (use 0 if not available)
        change_wc = 0.0

        if ebit_after_tax is not None and total_capital is not None and net_capex is not None:
            result["fundamental_ebit"] = compute_fundamental_ebit_growth(
                ebit_after_tax=ebit_after_tax,
                total_capital=total_capital,
                net_capex=net_capex,
                change_in_wc=change_wc,
            )

    return result
