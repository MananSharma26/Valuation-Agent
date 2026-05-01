import pandas as pd
import pytest
from valuation.context import ValuationContext
from valuation.data.api_client import CompanyData
from valuation.data.normalizer import normalize


def _make_sample_company_data() -> CompanyData:
    return CompanyData(
        ticker="TEST",
        name="Test Corp",
        sector="Technology",
        industry="Software",
        sic_code="7372",
        country="United States",
        income_statement=pd.DataFrame({
            "Total Revenue": [50000, 45000, 40000],
            "Operating Income": [10000, 9000, 8000],
            "Net Income": [8000, 7000, 6000],
        }),
        balance_sheet=pd.DataFrame({
            "Total Assets": [100000, 90000, 80000],
            "Total Debt": [15000, 16000, 17000],
            "Total Stockholders Equity": [60000, 55000, 50000],
            "Cash And Cash Equivalents": [10000, 8000, 6000],
        }),
        cash_flow=pd.DataFrame({
            "Operating Cash Flow": [12000, 11000, 10000],
            "Capital Expenditure": [-3000, -2800, -2500],
        }),
        shares_outstanding=800,
        market_cap=40000,
        price=50.0,
        beta=1.1,
        dividend_per_share=1.5,
        book_value_per_share=75.0,
    )


def test_normalize_populates_context():
    data = _make_sample_company_data()
    ctx = normalize(data)
    assert isinstance(ctx, ValuationContext)
    assert ctx.company.ticker == "TEST"
    assert ctx.company.name == "Test Corp"
    assert ctx.company.sector == "Technology"


def test_normalize_financials_attached():
    data = _make_sample_company_data()
    ctx = normalize(data)
    assert ctx.financials.income_statement is not None
    assert ctx.financials.balance_sheet is not None
    assert ctx.financials.cash_flow is not None


def test_normalize_key_stats():
    data = _make_sample_company_data()
    ctx = normalize(data)
    stats = ctx.financials.key_stats
    assert stats["shares_outstanding"] == 800
    assert stats["market_cap"] == 40000
    assert stats["price"] == 50.0
    assert stats["beta"] == 1.1


def test_normalize_detects_region_us():
    data = _make_sample_company_data()
    data.country = "United States"
    ctx = normalize(data)
    assert ctx.company.region == "US"


def test_normalize_detects_region_india():
    data = _make_sample_company_data()
    data.country = "India"
    ctx = normalize(data)
    assert ctx.company.region == "India"


def test_normalize_detects_region_japan():
    data = _make_sample_company_data()
    data.country = "Japan"
    ctx = normalize(data)
    assert ctx.company.region == "Japan"


def test_normalize_none_data_returns_none():
    result = normalize(None)
    assert result is None
