import pytest
from valuation.engines.relative import (
    pe_implied_value,
    ev_ebitda_implied_value,
    pbv_implied_value,
    ps_implied_value,
    relative_valuation,
    RelativeResult,
)


class TestPEImpliedValue:
    def test_basic_pe(self):
        # EPS=5.0, industry PE=20 -> implied value = 100
        value = pe_implied_value(eps=5.0, industry_pe=20.0)
        assert abs(value - 100.0) < 0.01

    def test_negative_eps_returns_none(self):
        value = pe_implied_value(eps=-2.0, industry_pe=20.0)
        assert value is None

    def test_zero_pe_returns_none(self):
        value = pe_implied_value(eps=5.0, industry_pe=0.0)
        assert value is None

    def test_none_pe_returns_none(self):
        value = pe_implied_value(eps=5.0, industry_pe=None)
        assert value is None


class TestEVEBITDAImpliedValue:
    def test_basic_ev_ebitda(self):
        # EBITDA=500, industry EV/EBITDA=12, debt=1000, cash=200, shares=100
        # EV = 500*12 = 6000, equity = 6000 - 1000 + 200 = 5200
        # per share = 5200/100 = 52
        value = ev_ebitda_implied_value(
            ebitda=500.0,
            industry_ev_ebitda=12.0,
            debt=1000.0,
            cash=200.0,
            shares_outstanding=100.0,
        )
        assert abs(value - 52.0) < 0.01

    def test_negative_ebitda_returns_none(self):
        value = ev_ebitda_implied_value(
            ebitda=-500.0,
            industry_ev_ebitda=12.0,
            debt=1000.0,
            cash=200.0,
            shares_outstanding=100.0,
        )
        assert value is None

    def test_zero_ebitda_returns_none(self):
        value = ev_ebitda_implied_value(
            ebitda=0.0,
            industry_ev_ebitda=12.0,
            debt=1000.0,
            cash=200.0,
            shares_outstanding=100.0,
        )
        assert value is None


class TestPBVImpliedValue:
    def test_basic_pbv(self):
        # BVPS=25, industry PBV=3 -> implied value = 75
        value = pbv_implied_value(
            book_value_per_share=25.0,
            industry_pbv=3.0,
        )
        assert abs(value - 75.0) < 0.01

    def test_negative_bvps_returns_none(self):
        value = pbv_implied_value(
            book_value_per_share=-10.0,
            industry_pbv=3.0,
        )
        assert value is None

    def test_none_pbv_returns_none(self):
        value = pbv_implied_value(
            book_value_per_share=25.0,
            industry_pbv=None,
        )
        assert value is None


class TestPSImpliedValue:
    def test_basic_ps(self):
        # Revenue per share = 50, industry PS=4 -> implied value = 200
        value = ps_implied_value(
            revenue_per_share=50.0,
            industry_ps=4.0,
        )
        assert abs(value - 200.0) < 0.01

    def test_zero_revenue_returns_none(self):
        value = ps_implied_value(
            revenue_per_share=0.0,
            industry_ps=4.0,
        )
        assert value is None


class TestRelativeValuation:
    def test_full_relative_valuation(self):
        result = relative_valuation(
            eps=5.0,
            ebitda=500.0,
            book_value_per_share=25.0,
            revenue_per_share=50.0,
            industry_multiples={
                "current_pe": 20.0,
                "ev_ebitda": 12.0,
                "pbv": 3.0,
                "ps": 4.0,
            },
            debt=1000.0,
            cash=200.0,
            shares_outstanding=100.0,
            market_price=80.0,
        )
        assert isinstance(result, RelativeResult)
        assert result.pe_value == pytest.approx(100.0, abs=0.1)
        assert result.ev_ebitda_value == pytest.approx(52.0, abs=0.1)
        assert result.pbv_value == pytest.approx(75.0, abs=0.1)
        assert result.ps_value == pytest.approx(200.0, abs=0.1)

        # Composite is the median of non-None values
        assert result.composite_value is not None

        # Discount/premium vs market price
        assert result.discount_to_composite is not None

    def test_partial_data(self):
        # Missing EBITDA and book value
        result = relative_valuation(
            eps=5.0,
            ebitda=None,
            book_value_per_share=None,
            revenue_per_share=50.0,
            industry_multiples={
                "current_pe": 20.0,
                "ps": 4.0,
            },
            debt=0.0,
            cash=0.0,
            shares_outstanding=100.0,
            market_price=80.0,
        )
        assert result.pe_value == pytest.approx(100.0, abs=0.1)
        assert result.ev_ebitda_value is None
        assert result.pbv_value is None
        assert result.ps_value == pytest.approx(200.0, abs=0.1)
        assert result.composite_value is not None

    def test_all_missing_returns_none_composite(self):
        result = relative_valuation(
            eps=-5.0,
            ebitda=-100.0,
            book_value_per_share=-10.0,
            revenue_per_share=0.0,
            industry_multiples={},
            debt=0.0,
            cash=0.0,
            shares_outstanding=100.0,
            market_price=80.0,
        )
        assert result.composite_value is None

    def test_to_dict(self):
        result = relative_valuation(
            eps=5.0,
            ebitda=500.0,
            book_value_per_share=25.0,
            revenue_per_share=50.0,
            industry_multiples={
                "current_pe": 20.0,
                "ev_ebitda": 12.0,
                "pbv": 3.0,
                "ps": 4.0,
            },
            debt=1000.0,
            cash=200.0,
            shares_outstanding=100.0,
            market_price=80.0,
        )
        d = result.to_dict()
        assert "pe_value" in d
        assert "ev_ebitda_value" in d
        assert "pbv_value" in d
        assert "ps_value" in d
        assert "composite_value" in d
        assert "discount_to_composite" in d
        assert "methods_used" in d
