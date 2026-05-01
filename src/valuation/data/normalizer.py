"""Normalize raw CompanyData into a ValuationContext."""

from __future__ import annotations

from valuation.context import ValuationContext
from valuation.data.api_client import CompanyData

_COUNTRY_TO_REGION: dict[str, str] = {
    "United States": "US",
    "Canada": "AusNZCanada",
    "Australia": "AusNZCanada",
    "New Zealand": "AusNZCanada",
    "Japan": "Japan",
    "India": "India",
    "China": "China",
    "Hong Kong": "China",
    "United Kingdom": "Europe",
    "Germany": "Europe",
    "France": "Europe",
    "Switzerland": "Europe",
    "Netherlands": "Europe",
    "Sweden": "Europe",
    "Spain": "Europe",
    "Italy": "Europe",
    "Norway": "Europe",
    "Denmark": "Europe",
    "Finland": "Europe",
    "Belgium": "Europe",
    "Ireland": "Europe",
    "Austria": "Europe",
    "Portugal": "Europe",
}


def _detect_region(country: str | None) -> str:
    if country is None:
        return "US"
    if country in _COUNTRY_TO_REGION:
        return _COUNTRY_TO_REGION[country]
    return "Emerging"


def normalize(data: CompanyData | None) -> ValuationContext | None:
    if data is None:
        return None

    region = _detect_region(data.country)
    ctx = ValuationContext(ticker=data.ticker, region=region)

    ctx.company.name = data.name
    ctx.company.sector = data.sector
    ctx.company.sic_code = data.sic_code

    ctx.financials.income_statement = data.income_statement
    ctx.financials.balance_sheet = data.balance_sheet
    ctx.financials.cash_flow = data.cash_flow
    ctx.financials.key_stats = {
        "shares_outstanding": data.shares_outstanding,
        "market_cap": data.market_cap,
        "price": data.price,
        "beta": data.beta,
        "dividend_per_share": data.dividend_per_share,
        "book_value_per_share": data.book_value_per_share,
        "country": data.country,
        "industry_yfinance": data.industry,
    }

    return ctx
