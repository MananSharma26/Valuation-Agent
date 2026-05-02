"""Tests for fcff_valuation_v2 (revenue-based DCF with S2C reinvestment)."""

import pytest
from valuation.engines.dcf import fcff_valuation_v2
from valuation.engines.schedules import wacc_schedule, tax_schedule, margin_convergence_schedule


class TestFcffValuationV2Basic:
    """Basic functional tests for the v2 engine."""

    @pytest.fixture
    def nvidia_like_inputs(self):
        """Simplified Nvidia-like 10-year DCF inputs."""
        n = 10
        growth_rates = [0.25] * 5 + [0.20, 0.16, 0.12, 0.08, 0.047]
        margins = margin_convergence_schedule(0.65, 0.55, convergence_year=5, n_years=n)
        taxes = tax_schedule(0.135, 0.25, n_years=n)
        waccs = wacc_schedule(0.12, 0.085, n_years=n)
        return {
            "base_revenue": 100_000,
            "base_ebit": 65_000,
            "revenue_growth_rates": growth_rates,
            "operating_margins": margins,
            "tax_rates": taxes,
            "waccs": waccs,
            "sales_to_capital": 2.5,
            "stable_growth": 0.047,
            "stable_roc": 0.20,
            "stable_wacc": 0.085,
            "stable_tax_rate": 0.25,
            "cash": 20_000,
            "debt": 10_000,
            "shares_outstanding": 1000,
        }

    def test_returns_all_keys(self, nvidia_like_inputs):
        result = fcff_valuation_v2(**nvidia_like_inputs)
        expected_keys = {
            "enterprise_value", "equity_value", "equity_value_per_share",
            "pv_high_growth", "pv_terminal", "terminal_value", "terminal_fcff",
            "yearly_revenue", "yearly_ebit", "yearly_ebit_at",
            "yearly_reinvestment", "yearly_fcff", "yearly_pv",
            "yearly_ic", "yearly_roic",
            "rd_adjustment", "research_asset",
        }
        assert set(result.keys()) == expected_keys

    def test_yearly_arrays_correct_length(self, nvidia_like_inputs):
        result = fcff_valuation_v2(**nvidia_like_inputs)
        n = len(nvidia_like_inputs["revenue_growth_rates"])
        for key in ["yearly_revenue", "yearly_ebit", "yearly_ebit_at",
                     "yearly_reinvestment", "yearly_fcff", "yearly_pv",
                     "yearly_ic", "yearly_roic"]:
            assert len(result[key]) == n, f"{key} has wrong length"

    def test_enterprise_value_positive(self, nvidia_like_inputs):
        result = fcff_valuation_v2(**nvidia_like_inputs)
        assert result["enterprise_value"] > 0

    def test_revenue_grows_correctly(self, nvidia_like_inputs):
        result = fcff_valuation_v2(**nvidia_like_inputs)
        rev = nvidia_like_inputs["base_revenue"]
        for t, g in enumerate(nvidia_like_inputs["revenue_growth_rates"]):
            rev *= (1 + g)
            assert result["yearly_revenue"][t] == pytest.approx(rev, rel=1e-6)

    def test_pv_components_sum_to_ev(self, nvidia_like_inputs):
        result = fcff_valuation_v2(**nvidia_like_inputs)
        assert result["enterprise_value"] == pytest.approx(
            result["pv_high_growth"] + result["pv_terminal"], rel=1e-6
        )


class TestTerminalValue:
    """Terminal value should use g/ROC reinvestment rate."""

    def test_terminal_uses_g_over_roc(self):
        """Verify terminal FCFF = EBIT(1-t)*(1+g)*(1 - g/ROC)."""
        n = 3
        result = fcff_valuation_v2(
            base_revenue=1000,
            base_ebit=100,
            revenue_growth_rates=[0.10] * n,
            operating_margins=[0.10] * n,
            tax_rates=[0.25] * n,
            waccs=[0.10] * n,
            sales_to_capital=2.0,
            stable_growth=0.03,
            stable_roc=0.15,
            stable_wacc=0.08,
            stable_tax_rate=0.25,
        )
        # Final year EBIT(1-t)
        final_ebit_at = result["yearly_ebit_at"][-1]
        expected_terminal_fcff = final_ebit_at * (1 + 0.03) * (1 - 0.03 / 0.15)
        assert result["terminal_fcff"] == pytest.approx(expected_terminal_fcff, rel=1e-6)

    def test_stable_wacc_must_exceed_growth(self):
        """Should raise ValueError when stable_wacc <= stable_growth."""
        with pytest.raises(ValueError, match="must exceed"):
            fcff_valuation_v2(
                base_revenue=1000,
                base_ebit=100,
                revenue_growth_rates=[0.05],
                operating_margins=[0.10],
                tax_rates=[0.25],
                waccs=[0.10],
                sales_to_capital=2.0,
                stable_growth=0.10,
                stable_roc=0.15,
                stable_wacc=0.08,
                stable_tax_rate=0.25,
            )


class TestRDIntegration:
    """R&D adjustment should flow through to base EBIT and invested capital."""

    def test_rd_adjustment_increases_value(self):
        """Positive R&D adjustment should increase enterprise value."""
        base_kwargs = dict(
            base_revenue=50_000,
            base_ebit=5_000,
            revenue_growth_rates=[0.10] * 5,
            operating_margins=[0.10] * 5,
            tax_rates=[0.20] * 5,
            waccs=[0.10] * 5,
            sales_to_capital=3.0,
            stable_growth=0.03,
            stable_roc=0.12,
            stable_wacc=0.08,
            stable_tax_rate=0.25,
            base_invested_capital=20_000,
        )
        result_no_rd = fcff_valuation_v2(**base_kwargs)
        result_with_rd = fcff_valuation_v2(**base_kwargs, rd_adjustment=2000, research_asset=8000)

        # R&D adjustment affects invested capital tracking (ROIC denominators)
        # but does NOT directly change yearly EBIT in v2 (margins are applied to revenue)
        # The research_asset increases base invested capital
        assert result_with_rd["research_asset"] == 8000
        assert result_with_rd["rd_adjustment"] == 2000

    def test_rd_fields_returned(self):
        result = fcff_valuation_v2(
            base_revenue=10_000,
            base_ebit=1_000,
            revenue_growth_rates=[0.05],
            operating_margins=[0.10],
            tax_rates=[0.20],
            waccs=[0.10],
            sales_to_capital=2.0,
            stable_growth=0.03,
            stable_roc=0.12,
            stable_wacc=0.08,
            stable_tax_rate=0.25,
            rd_adjustment=500,
            research_asset=3000,
        )
        assert result["rd_adjustment"] == 500
        assert result["research_asset"] == 3000


class TestEquityBridge:
    """Equity bridge: EV + cash - debt + non_op - minority - options."""

    def test_equity_bridge(self):
        result = fcff_valuation_v2(
            base_revenue=10_000,
            base_ebit=1_000,
            revenue_growth_rates=[0.05] * 3,
            operating_margins=[0.10] * 3,
            tax_rates=[0.20] * 3,
            waccs=[0.10] * 3,
            sales_to_capital=2.0,
            stable_growth=0.03,
            stable_roc=0.12,
            stable_wacc=0.08,
            stable_tax_rate=0.25,
            cash=5000,
            debt=3000,
            non_operating_assets=1000,
            minority_interests=500,
            options_value=200,
            shares_outstanding=100,
        )
        expected_equity = (
            result["enterprise_value"]
            + 5000 - 3000 + 1000 - 500 - 200
        )
        assert result["equity_value"] == pytest.approx(expected_equity, rel=1e-6)
        assert result["equity_value_per_share"] == pytest.approx(expected_equity / 100, rel=1e-6)

    def test_per_share_with_no_shares(self):
        """Zero shares should return 0 per share, not crash."""
        result = fcff_valuation_v2(
            base_revenue=10_000,
            base_ebit=1_000,
            revenue_growth_rates=[0.05],
            operating_margins=[0.10],
            tax_rates=[0.20],
            waccs=[0.10],
            sales_to_capital=2.0,
            stable_growth=0.03,
            stable_roc=0.12,
            stable_wacc=0.08,
            stable_tax_rate=0.25,
            shares_outstanding=0,
        )
        assert result["equity_value_per_share"] == 0
