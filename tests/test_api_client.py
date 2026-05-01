import pandas as pd
import pytest
from valuation.data.api_client import fetch_financials, CompanyData


class TestFetchFinancials:
    @pytest.mark.network
    def test_fetch_aapl(self):
        data = fetch_financials("AAPL")
        assert isinstance(data, CompanyData)
        assert data.ticker == "AAPL"
        assert isinstance(data.income_statement, pd.DataFrame)
        assert len(data.income_statement) >= 1
        assert isinstance(data.balance_sheet, pd.DataFrame)
        assert isinstance(data.cash_flow, pd.DataFrame)
        assert data.name is not None
        assert data.sector is not None
        assert data.shares_outstanding > 0
        assert data.market_cap > 0

    @pytest.mark.network
    def test_fetch_includes_key_stats(self):
        data = fetch_financials("MSFT")
        assert data.beta is not None or data.beta == 0
        assert data.price > 0

    def test_fetch_invalid_ticker(self):
        data = fetch_financials("ZZZINVALIDZZZ")
        assert data is None

    @pytest.mark.network
    def test_fetch_indian_stock(self):
        data = fetch_financials("TCS.NS")
        assert data is not None
        assert isinstance(data.income_statement, pd.DataFrame)


class TestManualInput:
    def test_create_company_data_manually(self):
        data = CompanyData(
            ticker="PRIVATE",
            name="Private Corp",
            sector="Technology",
            sic_code="7372",
            income_statement=pd.DataFrame({"Total Revenue": [1000], "Net Income": [100]}),
            balance_sheet=pd.DataFrame({"Total Assets": [5000]}),
            cash_flow=pd.DataFrame({"Operating Cash Flow": [200]}),
            shares_outstanding=100,
            market_cap=5000,
            price=50.0,
            beta=1.2,
            country="US",
        )
        assert data.ticker == "PRIVATE"
        assert data.market_cap == 5000
