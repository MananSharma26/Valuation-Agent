"""Fetch company financial data from Yahoo Finance."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass
class CompanyData:
    """Raw company financial data from API or manual input."""
    ticker: str
    name: str | None = None
    sector: str | None = None
    industry: str | None = None
    sic_code: str | None = None
    country: str | None = None
    income_statement: pd.DataFrame | None = None
    balance_sheet: pd.DataFrame | None = None
    cash_flow: pd.DataFrame | None = None
    shares_outstanding: float = 0
    market_cap: float = 0
    price: float = 0
    beta: float | None = None
    dividend_per_share: float = 0
    book_value_per_share: float = 0


def fetch_analyst_data(ticker: str) -> dict | None:
    """Fetch analyst price targets and recommendations from Yahoo Finance.

    Parameters
    ----------
    ticker : str
        Stock ticker symbol (e.g., "AAPL", "TCS.NS").

    Returns
    -------
    dict | None
        Dictionary with keys:
        - "price_targets": dict with targetMean, targetHigh, targetLow,
          targetMedian, numberOfAnalysts (or None if unavailable)
        - "recommendations": list of recent recommendation dicts (or None)
        - "earnings_estimate": dict of forward EPS estimate data (or None)
        Returns None if yfinance is unavailable or the ticker is invalid.
    """
    try:
        import yfinance as yf
    except ImportError:
        raise ImportError("yfinance is required: pip install yfinance")

    try:
        stock = yf.Ticker(ticker)
        info = stock.info
        if not info:
            return None
    except Exception:
        return None

    result: dict = {}

    # --- Price targets ---
    try:
        pt = stock.analyst_price_targets
        if pt is not None and isinstance(pt, dict) and pt:
            result["price_targets"] = {
                "targetMean": pt.get("mean"),
                "targetHigh": pt.get("high"),
                "targetLow": pt.get("low"),
                "targetMedian": pt.get("median"),
                "numberOfAnalysts": pt.get("numberOfAnalysts"),
            }
        else:
            # Fall back to info dict fields
            mean = info.get("targetMeanPrice") or info.get("targetMedianPrice")
            if mean is not None:
                result["price_targets"] = {
                    "targetMean": info.get("targetMeanPrice"),
                    "targetHigh": info.get("targetHighPrice"),
                    "targetLow": info.get("targetLowPrice"),
                    "targetMedian": info.get("targetMedianPrice"),
                    "numberOfAnalysts": info.get("numberOfAnalystOpinions"),
                }
            else:
                result["price_targets"] = None
    except Exception:
        result["price_targets"] = None

    # --- Recommendations ---
    try:
        recs = stock.recommendations
        if recs is not None and not recs.empty:
            # Keep last 5 rows, convert to list of dicts (dates as strings)
            recent = recs.tail(5).reset_index()
            result["recommendations"] = recent.to_dict(orient="records")
        else:
            result["recommendations"] = None
    except Exception:
        result["recommendations"] = None

    # --- Earnings / EPS estimate ---
    try:
        ee = stock.earnings_estimate
        if ee is not None and not ee.empty:
            result["earnings_estimate"] = ee.to_dict()
        else:
            # Try growth_estimates as fallback
            ge = stock.growth_estimates
            if ge is not None and not ge.empty:
                result["earnings_estimate"] = ge.to_dict()
            else:
                result["earnings_estimate"] = None
    except Exception:
        result["earnings_estimate"] = None

    return result if result else None


def fetch_financials(ticker: str) -> CompanyData | None:
    """Fetch financial statements and key stats from Yahoo Finance.
    Returns None if the ticker is invalid or data cannot be fetched.
    """
    try:
        import yfinance as yf
    except ImportError:
        raise ImportError("yfinance is required: pip install yfinance")

    try:
        stock = yf.Ticker(ticker)
        info = stock.info
        if not info or info.get("regularMarketPrice") is None:
            return None
    except Exception:
        return None

    try:
        income_stmt = stock.financials
        if income_stmt is None or income_stmt.empty:
            income_stmt = stock.quarterly_financials

        balance = stock.balance_sheet
        if balance is None or balance.empty:
            balance = stock.quarterly_balance_sheet

        cashflow = stock.cashflow
        if cashflow is None or cashflow.empty:
            cashflow = stock.quarterly_cashflow

        # Transpose: yfinance returns line items as rows, dates as columns
        # We want rows=years, columns=line items
        if income_stmt is not None and not income_stmt.empty:
            income_stmt = income_stmt.T
        if balance is not None and not balance.empty:
            balance = balance.T
        if cashflow is not None and not cashflow.empty:
            cashflow = cashflow.T
    except Exception:
        income_stmt = None
        balance = None
        cashflow = None

    return CompanyData(
        ticker=ticker.upper(),
        name=info.get("longName") or info.get("shortName"),
        sector=info.get("sector"),
        industry=info.get("industry"),
        sic_code=info.get("sic"),
        country=info.get("country"),
        income_statement=income_stmt,
        balance_sheet=balance,
        cash_flow=cashflow,
        shares_outstanding=info.get("sharesOutstanding", 0) or 0,
        market_cap=info.get("marketCap", 0) or 0,
        price=info.get("regularMarketPrice") or info.get("currentPrice", 0) or 0,
        beta=info.get("beta"),
        dividend_per_share=info.get("dividendRate", 0) or 0,
        book_value_per_share=info.get("bookValue", 0) or 0,
    )
