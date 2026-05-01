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
