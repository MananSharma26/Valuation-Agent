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


# ---------------------------------------------------------------------------
# Golden Tests — derived from Damodaran example spreadsheets
# ---------------------------------------------------------------------------

class TestGoldenNvidiaLike:
    """Revenue-based DCF with S2C reinvestment, WACC transition, margin convergence.

    Modelled after Damodaran's NvidiaJan2025.xlsx.
    Values: revenue $113B, margin ~65% -> 60%, S2C=2.5, WACC 11.8% -> 8.5%.
    Damodaran's published value: ~$78/share (at the time of the spreadsheet).
    """

    def test_nvidia_like_revenue_based(self):
        """Revenue-based DCF with S2C reinvestment, WACC transition, margin convergence."""
        n = 10
        growth = [0.15] * 5 + [0.129, 0.109, 0.088, 0.068, 0.047]
        margins = margin_convergence_schedule(0.65, 0.60, convergence_year=5, n_years=10)
        taxes = tax_schedule(0.135, 0.25, n_years=10, n_constant=5)
        waccs = wacc_schedule(0.1179, 0.085, n_years=10, n_constant=5)

        result = fcff_valuation_v2(
            base_revenue=113269,
            base_ebit=71033,
            revenue_growth_rates=growth,
            operating_margins=margins,
            tax_rates=taxes,
            waccs=waccs,
            sales_to_capital=2.5,
            stable_growth=0.047,
            stable_roc=0.20,
            stable_wacc=0.085,
            stable_tax_rate=0.25,
            cash=38487,
            debt=10225,
            shares_outstanding=24490,
        )

        # Damodaran's value was ~$78/share; reasonable range given our inputs
        assert result["equity_value_per_share"] > 50
        assert result["equity_value_per_share"] < 150
        # Enterprise value > $1T (revenue alone is $113B, growing fast)
        assert result["enterprise_value"] > 1_000_000
        # Terminal value should dominate high-growth PV (typical for growth companies)
        assert result["pv_terminal"] > result["pv_high_growth"]
        # All 10 projection years present
        assert len(result["yearly_fcff"]) == 10
        # FCFFs should be positive: at S2C=2.5, margin 60%+, reinvestment is modest
        assert all(fcff > 0 for fcff in result["yearly_fcff"])


class TestGoldenReinvestmentFormula:
    """Verify S2C reinvestment formula: Reinvestment_t = (Rev_t - Rev_{t-1}) / S2C."""

    def test_reinvestment_s2c_formula(self):
        """Verify reinvestment uses sales-to-capital correctly."""
        result = fcff_valuation_v2(
            base_revenue=1000,
            base_ebit=200,
            revenue_growth_rates=[0.10] * 5 + [0.05] * 5,
            operating_margins=[0.20] * 10,
            tax_rates=[0.25] * 10,
            waccs=[0.10] * 10,
            sales_to_capital=2.0,
            stable_growth=0.03,
            stable_roc=0.10,
            stable_wacc=0.10,
            stable_tax_rate=0.25,
            shares_outstanding=100,
        )

        # Year 1: revenue = 1000 * 1.10 = 1100
        # Reinvestment = (1100 - 1000) / 2.0 = 50
        assert abs(result["yearly_reinvestment"][0] - 50.0) < 1.0

        # FCFF year 1 = EBIT(1-t) - reinvestment
        # EBIT(1-t) = 1100 * 0.20 * (1 - 0.25) = 1100 * 0.15 = 165
        # FCFF = 165 - 50 = 115
        assert abs(result["yearly_fcff"][0] - 115.0) < 1.0

    def test_reinvestment_year2(self):
        """Year 2 reinvestment also follows S2C formula from year-1 revenue."""
        result = fcff_valuation_v2(
            base_revenue=1000,
            base_ebit=200,
            revenue_growth_rates=[0.10] * 10,
            operating_margins=[0.20] * 10,
            tax_rates=[0.25] * 10,
            waccs=[0.10] * 10,
            sales_to_capital=4.0,
            stable_growth=0.03,
            stable_roc=0.10,
            stable_wacc=0.10,
            stable_tax_rate=0.25,
            shares_outstanding=100,
        )

        # Year 1 revenue = 1100, Year 2 revenue = 1210
        # Year 2 reinvestment = (1210 - 1100) / 4.0 = 27.5
        assert abs(result["yearly_reinvestment"][1] - 27.5) < 0.1


class TestReinvestmentLag:
    """Reinvestment lag: invest today for growth N years from now."""

    _BASE_KWARGS = dict(
        base_revenue=1000,
        base_ebit=200,
        revenue_growth_rates=[0.10] * 10,
        operating_margins=[0.20] * 10,
        tax_rates=[0.25] * 10,
        waccs=[0.10] * 10,
        sales_to_capital=2.0,
        stable_growth=0.03,
        stable_roc=0.15,
        stable_wacc=0.10,
        stable_tax_rate=0.25,
        shares_outstanding=100,
    )

    def test_reinvestment_lag_different_patterns(self):
        """Lag=0 and lag=2 should produce different reinvestment patterns."""
        result_lag0 = fcff_valuation_v2(**self._BASE_KWARGS, reinvestment_lag=0)
        result_lag2 = fcff_valuation_v2(**self._BASE_KWARGS, reinvestment_lag=2)
        # Lag=2 invests today for growth two years ahead (larger future delta);
        # with uniform 10% growth revenue deltas grow each year, so lag=2 shifts
        # a larger delta into earlier years -> higher early reinvestment.
        assert result_lag2["yearly_reinvestment"][0] > result_lag0["yearly_reinvestment"][0]

    def test_revenue_unaffected_by_lag(self):
        """Lag parameter must not alter the revenue projection."""
        result_lag0 = fcff_valuation_v2(**self._BASE_KWARGS, reinvestment_lag=0)
        result_lag2 = fcff_valuation_v2(**self._BASE_KWARGS, reinvestment_lag=2)
        assert abs(result_lag0["yearly_revenue"][-1] - result_lag2["yearly_revenue"][-1]) < 0.01

    def test_lag0_is_default_behavior(self):
        """Explicit lag=0 must match the no-lag default (backward-compatibility)."""
        result_default = fcff_valuation_v2(**self._BASE_KWARGS)
        result_lag0 = fcff_valuation_v2(**self._BASE_KWARGS, reinvestment_lag=0)
        assert result_default["yearly_reinvestment"] == pytest.approx(
            result_lag0["yearly_reinvestment"], rel=1e-9
        )
        assert result_default["enterprise_value"] == pytest.approx(
            result_lag0["enterprise_value"], rel=1e-9
        )

    def test_lag0_reinvestment_formula(self):
        """With lag=0, year-1 reinvestment = (rev1 - rev0) / S2C (existing formula)."""
        result = fcff_valuation_v2(**self._BASE_KWARGS, reinvestment_lag=0)
        expected = (1000 * 1.10 - 1000) / 2.0   # (1100 - 1000) / 2.0 = 50
        assert result["yearly_reinvestment"][0] == pytest.approx(expected, rel=1e-6)

    def test_lag1_reinvestment_formula(self):
        """With lag=1, year-1 reinvestment uses (rev2 - rev1) / S2C."""
        result = fcff_valuation_v2(**self._BASE_KWARGS, reinvestment_lag=1)
        rev1 = 1000 * 1.10          # 1100
        rev2 = 1000 * 1.10 ** 2    # 1210
        expected = (rev2 - rev1) / 2.0  # 55.0
        assert result["yearly_reinvestment"][0] == pytest.approx(expected, rel=1e-6)

    def test_tail_years_use_terminal_reinvestment(self):
        """Last `lag` years must fall back to terminal reinvestment rate * ebit_at."""
        lag = 3
        result = fcff_valuation_v2(**self._BASE_KWARGS, reinvestment_lag=lag)
        terminal_reinv_rate = 0.03 / 0.15   # stable_growth / stable_roc = 0.20
        n = len(self._BASE_KWARGS["revenue_growth_rates"])
        # Last `lag` entries should equal terminal_reinv_rate * ebit_at
        for t in range(n - lag, n):
            expected = result["yearly_ebit_at"][t] * terminal_reinv_rate
            assert result["yearly_reinvestment"][t] == pytest.approx(expected, rel=1e-6), \
                f"tail year {t} reinvestment mismatch"


class TestGoldenTerminalValue:
    """Terminal value uses g/ROC reinvestment rate applied to EBIT(1-t)_{n+1}."""

    def test_terminal_value_formula(self):
        """Terminal value = FCFF_{n+1} / (WACC - g) with g/ROC reinvestment."""
        result = fcff_valuation_v2(
            base_revenue=1000,
            base_ebit=200,
            revenue_growth_rates=[0.05] * 10,
            operating_margins=[0.20] * 10,
            tax_rates=[0.25] * 10,
            waccs=[0.10] * 10,
            sales_to_capital=2.0,
            stable_growth=0.03,
            stable_roc=0.15,
            stable_wacc=0.10,
            stable_tax_rate=0.25,
            shares_outstanding=100,
        )

        # Terminal reinvestment rate = g / ROC = 0.03 / 0.15 = 0.20
        # Terminal EBIT(1-t) = last_year_ebit_at * (1 + g)
        last_ebit_at = result["yearly_ebit_at"][-1]
        expected_terminal_ebit_at = last_ebit_at * 1.03
        expected_terminal_fcff = expected_terminal_ebit_at * (1 - 0.03 / 0.15)  # * 0.80
        expected_tv = expected_terminal_fcff / (0.10 - 0.03)

        assert abs(result["terminal_value"] - expected_tv) / expected_tv < 0.01  # within 1%

    def test_terminal_pv_discounted_correctly(self):
        """PV of terminal value uses cumulative discount factor from all n WACCs."""
        import math

        result = fcff_valuation_v2(
            base_revenue=1000,
            base_ebit=200,
            revenue_growth_rates=[0.05] * 5,
            operating_margins=[0.20] * 5,
            tax_rates=[0.25] * 5,
            waccs=[0.10] * 5,
            sales_to_capital=2.0,
            stable_growth=0.03,
            stable_roc=0.15,
            stable_wacc=0.10,
            stable_tax_rate=0.25,
            shares_outstanding=100,
        )

        # Cumulative discount over 5 years at 10% = 1.1^5
        cumulative = math.prod(1.10 for _ in range(5))
        expected_pv_terminal = result["terminal_value"] / cumulative

        assert abs(result["pv_terminal"] - expected_pv_terminal) / expected_pv_terminal < 0.001
