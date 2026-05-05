"""Tests for the FCFE engine."""

import pytest
from valuation.engines.fcfe import compute_fcfe, fcfe_valuation, should_use_fcfe


class TestComputeFcfe:
    def test_zero_debt_ratio(self):
        """With zero debt, equity share = 1, all reinvestment borne by equity."""
        result = compute_fcfe(
            net_income=100,
            capex=30,
            depreciation=10,
            change_in_wc=5,
            debt_ratio=0.0,
        )
        # FCFE = 100 - 1.0*(30-10) - 1.0*5 + 0 = 100 - 20 - 5 = 75
        assert result == pytest.approx(75.0)

    def test_with_debt_ratio(self):
        """With 30% debt ratio, equity bears only 70% of reinvestment."""
        result = compute_fcfe(
            net_income=100,
            capex=30,
            depreciation=10,
            change_in_wc=5,
            debt_ratio=0.30,
        )
        # FCFE = 100 - 0.7*(30-10) - 0.7*5 + 0 = 100 - 14 - 3.5 = 82.5
        assert result == pytest.approx(82.5)

    def test_with_new_debt(self):
        """New debt issuance adds to FCFE."""
        result = compute_fcfe(
            net_income=100,
            capex=30,
            depreciation=10,
            change_in_wc=5,
            debt_ratio=0.0,
            new_debt=20,
        )
        # FCFE = 100 - 1.0*20 - 1.0*5 + 20 = 95
        assert result == pytest.approx(95.0)

    def test_negative_wc_change(self):
        """Negative WC change (release of working capital) increases FCFE."""
        result = compute_fcfe(
            net_income=100,
            capex=20,
            depreciation=10,
            change_in_wc=-5,
            debt_ratio=0.0,
        )
        # FCFE = 100 - 1.0*(20-10) - 1.0*(-5) = 100 - 10 + 5 = 95
        assert result == pytest.approx(95.0)


class TestFcfeValuation:
    def test_produces_positive_value(self):
        """Basic sanity: FCFE valuation produces a positive value per share."""
        result = fcfe_valuation(
            current_net_income=1000,
            growth_rates=[0.10] * 5,
            capex_to_depreciation=1.5,
            wc_to_revenue_change=0.05,
            debt_ratio=0.20,
            cost_of_equities=[0.10] * 5,
            stable_growth=0.03,
            stable_roe=0.12,
            stable_ke=0.10,
            current_depreciation=200,
            current_revenue=5000,
            shares_outstanding=100,
        )
        assert result["value_per_share"] > 0
        assert result["equity_value"] > 0
        assert result["model"] == "fcfe"
        assert len(result["yearly_fcfe"]) == 5

    def test_higher_growth_gives_higher_value(self):
        """Higher growth rate should produce higher valuation."""
        base_params = dict(
            current_net_income=1000,
            capex_to_depreciation=1.5,
            wc_to_revenue_change=0.05,
            debt_ratio=0.20,
            cost_of_equities=[0.10] * 5,
            stable_growth=0.03,
            stable_roe=0.12,
            stable_ke=0.10,
            current_depreciation=200,
            current_revenue=5000,
            shares_outstanding=100,
        )
        low = fcfe_valuation(growth_rates=[0.05] * 5, **base_params)
        high = fcfe_valuation(growth_rates=[0.15] * 5, **base_params)
        assert high["value_per_share"] > low["value_per_share"]

    def test_raises_when_ke_below_growth(self):
        """Should raise ValueError when stable_ke <= stable_growth."""
        with pytest.raises(ValueError):
            fcfe_valuation(
                current_net_income=1000,
                growth_rates=[0.10] * 5,
                capex_to_depreciation=1.5,
                wc_to_revenue_change=0.05,
                debt_ratio=0.20,
                cost_of_equities=[0.10] * 5,
                stable_growth=0.12,
                stable_roe=0.15,
                stable_ke=0.10,  # less than stable_growth
                current_depreciation=200,
                current_revenue=5000,
                shares_outstanding=100,
            )


class TestShouldUseFcfe:
    def test_low_payout_returns_true(self):
        """When dividends < 80% of FCFE, should use FCFE model."""
        assert should_use_fcfe(dividends_paid=50, fcfe=100) is True

    def test_high_payout_returns_true(self):
        """When dividends > 110% of FCFE, should use FCFE model."""
        assert should_use_fcfe(dividends_paid=120, fcfe=100) is True

    def test_normal_payout_returns_false(self):
        """When dividends ~= FCFE (80-110%), DDM is fine."""
        assert should_use_fcfe(dividends_paid=95, fcfe=100) is False

    def test_negative_fcfe_returns_false(self):
        """With negative FCFE, the ratio is meaningless."""
        assert should_use_fcfe(dividends_paid=50, fcfe=-10) is False

    def test_zero_fcfe_returns_false(self):
        """With zero FCFE, cannot compute ratio."""
        assert should_use_fcfe(dividends_paid=50, fcfe=0) is False
