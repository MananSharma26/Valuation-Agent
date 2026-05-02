import pandas as pd
import pytest
from valuation.agents.growth_estimator import (
    compute_historical_cagr,
    GrowthEstimate,
)


class TestHistoricalCAGR:
    def test_revenue_cagr_positive(self):
        """Revenue growing from 100 to 146.41 over 4 years = 10% CAGR."""
        income = pd.DataFrame({
            "Total Revenue": [100.0, 110.0, 121.0, 133.1, 146.41],
        })
        result = compute_historical_cagr(income, column="Total Revenue")
        assert isinstance(result, GrowthEstimate)
        assert abs(result.value - 0.10) < 0.005
        assert result.method == "historical_cagr"
        assert "Total Revenue" in result.reasoning

    def test_revenue_cagr_negative(self):
        """Declining revenue: 200, 180, 162, 145.8 => CAGR ~ -10%."""
        income = pd.DataFrame({
            "Total Revenue": [200.0, 180.0, 162.0, 145.8],
        })
        result = compute_historical_cagr(income, column="Total Revenue")
        assert abs(result.value - (-0.10)) < 0.005

    def test_net_income_cagr(self):
        """Net income CAGR from 50 to 80 over 3 years."""
        income = pd.DataFrame({
            "Net Income": [50.0, 60.0, 70.0, 80.0],
        })
        result = compute_historical_cagr(income, column="Net Income")
        # CAGR = (80/50)^(1/3) - 1 = 0.1696
        assert abs(result.value - 0.1696) < 0.005

    def test_cagr_single_row_returns_none(self):
        """Cannot compute CAGR with fewer than 2 data points."""
        income = pd.DataFrame({"Total Revenue": [100.0]})
        result = compute_historical_cagr(income, column="Total Revenue")
        assert result is None

    def test_cagr_zero_start_returns_none(self):
        """CAGR undefined when starting value is zero."""
        income = pd.DataFrame({"Total Revenue": [0.0, 100.0, 200.0]})
        result = compute_historical_cagr(income, column="Total Revenue")
        assert result is None

    def test_cagr_negative_start_returns_none(self):
        """CAGR undefined when starting value is negative."""
        income = pd.DataFrame({"Net Income": [-50.0, 20.0, 40.0]})
        result = compute_historical_cagr(income, column="Net Income")
        assert result is None

    def test_cagr_missing_column_returns_none(self):
        """Returns None if the requested column doesn't exist."""
        income = pd.DataFrame({"Other Column": [100.0, 200.0]})
        result = compute_historical_cagr(income, column="Total Revenue")
        assert result is None

    def test_cagr_with_nan_drops_them(self):
        """NaN values are dropped before computing CAGR."""
        income = pd.DataFrame({
            "Total Revenue": [100.0, float("nan"), 121.0],
        })
        result = compute_historical_cagr(income, column="Total Revenue")
        # After dropping NaN: [100, 121], 1 period => CAGR = 0.21
        assert abs(result.value - 0.21) < 0.005


from valuation.agents.growth_estimator import (
    compute_fundamental_eps_growth,
    compute_fundamental_ebit_growth,
    estimate_all_growth_rates,
)
from valuation.context import ValuationContext


class TestFundamentalEPSGrowth:
    def test_basic_eps_growth(self):
        """g_EPS = retention_ratio x ROE = 0.40 x 0.15 = 6%."""
        result = compute_fundamental_eps_growth(
            net_income=150.0,
            book_equity=1000.0,
            dividends_paid=90.0,
        )
        assert isinstance(result, GrowthEstimate)
        # retention = 1 - 90/150 = 0.40, ROE = 150/1000 = 0.15
        # g = 0.40 * 0.15 = 0.06
        assert abs(result.value - 0.06) < 0.001
        assert result.method == "fundamental_eps"
        assert "retention" in result.reasoning.lower()

    def test_eps_growth_no_dividends(self):
        """If no dividends, retention = 1.0, g = ROE."""
        result = compute_fundamental_eps_growth(
            net_income=200.0,
            book_equity=1000.0,
            dividends_paid=0.0,
        )
        # retention = 1.0, ROE = 0.20, g = 0.20
        assert abs(result.value - 0.20) < 0.001

    def test_eps_growth_full_payout(self):
        """If 100% payout, retention = 0, g = 0."""
        result = compute_fundamental_eps_growth(
            net_income=100.0,
            book_equity=1000.0,
            dividends_paid=100.0,
        )
        assert abs(result.value - 0.0) < 0.001

    def test_eps_growth_negative_income_returns_none(self):
        """Cannot compute fundamental growth with negative earnings."""
        result = compute_fundamental_eps_growth(
            net_income=-50.0,
            book_equity=1000.0,
            dividends_paid=0.0,
        )
        assert result is None

    def test_eps_growth_zero_equity_returns_none(self):
        """Cannot compute ROE with zero equity."""
        result = compute_fundamental_eps_growth(
            net_income=100.0,
            book_equity=0.0,
            dividends_paid=0.0,
        )
        assert result is None

    def test_eps_growth_negative_equity_returns_none(self):
        """Negative equity makes ROE meaningless."""
        result = compute_fundamental_eps_growth(
            net_income=100.0,
            book_equity=-500.0,
            dividends_paid=0.0,
        )
        assert result is None

    def test_eps_growth_goldman(self):
        """Goldman: ROE=13.19%, Payout=8.35%, Retention=91.65%, g=12.09%."""
        result = compute_fundamental_eps_growth(
            net_income=13.19,
            book_equity=100.0,
            dividends_paid=13.19 * 0.0835,
        )
        # retention = 1 - 0.0835 = 0.9165
        # ROE = 13.19/100 = 0.1319
        # g = 0.9165 * 0.1319 = 0.1209
        assert abs(result.value - 0.1209) < 0.002


class TestFundamentalEBITGrowth:
    def test_basic_ebit_growth(self):
        """g_EBIT = reinvestment_rate x ROC = 0.30 x 0.25 = 7.5%."""
        result = compute_fundamental_ebit_growth(
            ebit_after_tax=250.0,
            total_capital=1000.0,
            net_capex=50.0,
            change_in_wc=25.0,
        )
        assert isinstance(result, GrowthEstimate)
        # reinvestment = (50 + 25) / 250 = 0.30
        # ROC = 250 / 1000 = 0.25
        # g = 0.30 * 0.25 = 0.075
        assert abs(result.value - 0.075) < 0.001
        assert result.method == "fundamental_ebit"
        assert "reinvestment" in result.reasoning.lower()

    def test_ebit_growth_zero_reinvestment(self):
        """No reinvestment => zero growth."""
        result = compute_fundamental_ebit_growth(
            ebit_after_tax=200.0,
            total_capital=1000.0,
            net_capex=0.0,
            change_in_wc=0.0,
        )
        assert abs(result.value - 0.0) < 0.001

    def test_ebit_growth_negative_reinvestment(self):
        """Negative reinvestment (shrinking firm) => negative growth."""
        result = compute_fundamental_ebit_growth(
            ebit_after_tax=200.0,
            total_capital=1000.0,
            net_capex=-50.0,
            change_in_wc=-25.0,
        )
        # reinvestment = (-50 + -25) / 200 = -0.375
        # ROC = 200/1000 = 0.20
        # g = -0.375 * 0.20 = -0.075
        assert abs(result.value - (-0.075)) < 0.001

    def test_ebit_growth_zero_capital_returns_none(self):
        """Cannot compute ROC with zero capital."""
        result = compute_fundamental_ebit_growth(
            ebit_after_tax=200.0,
            total_capital=0.0,
            net_capex=50.0,
            change_in_wc=0.0,
        )
        assert result is None

    def test_ebit_growth_zero_ebit_returns_none(self):
        """Zero EBIT makes reinvestment rate undefined."""
        result = compute_fundamental_ebit_growth(
            ebit_after_tax=0.0,
            total_capital=1000.0,
            net_capex=50.0,
            change_in_wc=0.0,
        )
        assert result is None

    def test_ebit_growth_3m(self):
        """3M pre-crisis: ROC=25%, reinvestment_rate=30%, g=7.5%."""
        result = compute_fundamental_ebit_growth(
            ebit_after_tax=3473.6,  # 5344 * (1-0.35)
            total_capital=13894.4,  # 3473.6 / 0.25
            net_capex=700.0,
            change_in_wc=342.08,  # to make reinv = 0.30
        )
        # reinvestment = (700 + 342.08) / 3473.6 = 0.30
        # ROC = 3473.6 / 13894.4 = 0.25
        # g = 0.30 * 0.25 = 0.075
        assert abs(result.value - 0.075) < 0.002


class TestEstimateAllGrowthRates:
    def test_returns_all_three_methods(self):
        """estimate_all_growth_rates returns a dict with up to 3 GrowthEstimate values."""
        ctx = ValuationContext(ticker="TEST")
        ctx.financials.income_statement = pd.DataFrame({
            "Total Revenue": [100.0, 110.0, 121.0, 133.1],
            "Net Income": [20.0, 22.0, 24.2, 26.62],
            "EBIT": [30.0, 33.0, 36.3, 39.93],
            "Interest Expense": [5.0, 5.0, 5.0, 5.0],
            "Tax Provision": [8.0, 9.0, 10.0, 11.0],
        })
        ctx.financials.balance_sheet = pd.DataFrame({
            "Total Stockholders Equity": [200.0, 210.0, 220.0, 230.0],
            "Total Debt": [100.0, 100.0, 100.0, 100.0],
            "Cash And Cash Equivalents": [20.0, 22.0, 24.0, 26.0],
        })
        ctx.financials.cash_flow = pd.DataFrame({
            "Capital Expenditure": [-15.0, -16.0, -17.0, -18.0],
            "Depreciation And Amortization": [10.0, 10.0, 10.0, 10.0],
        })
        ctx.financials.key_stats = {
            "dividend_per_share": 1.0,
            "shares_outstanding": 10.0,
        }
        ctx.assumptions.tax_rate = 0.25

        result = estimate_all_growth_rates(ctx)
        assert "historical_revenue" in result
        assert "historical_net_income" in result
        assert isinstance(result["historical_revenue"], GrowthEstimate)
        assert isinstance(result["historical_net_income"], GrowthEstimate)

    def test_missing_financials_returns_partial(self):
        """If income_statement is None, historical methods return None."""
        ctx = ValuationContext(ticker="TEST")
        result = estimate_all_growth_rates(ctx)
        assert result["historical_revenue"] is None
        assert result["historical_net_income"] is None
        assert result["fundamental_eps"] is None
        assert result["fundamental_ebit"] is None
