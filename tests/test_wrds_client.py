import pytest
from valuation.data.wrds_client import WRDSClient


@pytest.fixture
def wrds():
    client = WRDSClient()
    yield client
    client.close()


class TestWRDSSearch:
    @pytest.mark.network
    def test_search_tcs(self, wrds):
        results = wrds.search_company("TATA CONSULTANCY", loc="IND")
        assert len(results) >= 1
        assert "TATA CONSULTANCY" in results.iloc[0]["conm"].upper()

    @pytest.mark.network
    def test_search_reliance(self, wrds):
        results = wrds.search_company("RELIANCE IND", loc="IND")
        assert len(results) >= 1


class TestWRDSFetch:
    @pytest.mark.network
    def test_fetch_tcs(self, wrds):
        # TCS gvkey = 270885
        data = wrds.fetch_financials_global("270885")
        assert data is not None
        assert "TATA CONSULTANCY" in data.name.upper()
        assert data.country == "India"
        assert data.income_statement is not None
        assert len(data.income_statement) >= 5
        # Check revenue exists and is reasonable (in INR millions)
        rev = data.income_statement["Total Revenue"].dropna()
        assert len(rev) > 0
        assert rev.iloc[-1] > 1000000  # > 1M (it's actually ~2.6T)

    @pytest.mark.network
    def test_fetch_invalid_gvkey(self, wrds):
        data = wrds.fetch_financials_global("999999999")
        assert data is None


class TestWRDSIBES:
    @pytest.mark.network
    def test_search_ibes_tcs(self, wrds):
        results = wrds.search_ibes_ticker("TATA CONSULT", country_code="INR")
        assert len(results) >= 1

    @pytest.mark.network
    def test_fetch_estimates(self, wrds):
        # First find TCS IBES ticker
        results = wrds.search_ibes_ticker("TATA CONSULT", country_code="INR")
        if len(results) > 0:
            ticker = results.iloc[0]["ticker"]
            estimates = wrds.fetch_ibes_estimates(ticker)
            # May or may not have estimates
            if estimates is not None:
                assert "meanest" in estimates.columns
