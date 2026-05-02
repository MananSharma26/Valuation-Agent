"""
Tests for valuation.engines.dcf

Verification anchors:
  - Gordon Growth (ConEd): DPS=2.32, Ke=7.7%, g=2.1% → Value ≈ $42.30
  - All expected values derived from Damodaran methodology.
"""

import math
import pytest

from valuation.engines.dcf import (
    gordon_growth_value,
    gordon_implied_growth,
    compute_fcff,
    compute_terminal_value,
    discount_cashflows,
    interpolate_params,
    fcff_valuation,
)


# ---------------------------------------------------------------------------
# Gordon Growth Model
# ---------------------------------------------------------------------------

class TestGordonGrowthValue:
    def test_coned_anchor(self):
        """ConEd: DPS=2.32, Ke=7.7%, g=2.1% → ~$42.30 (Damodaran anchor)."""
        value = gordon_growth_value(2.32, 0.077, 0.021)
        assert value == pytest.approx(42.30, abs=0.01)

    def test_zero_growth(self):
        """With g=0, Value = DPS / Ke (perpetuity formula)."""
        value = gordon_growth_value(3.00, 0.10, 0.0)
        assert value == pytest.approx(3.00 / 0.10, rel=1e-9)

    def test_high_growth_near_ke(self):
        """Value increases as g approaches Ke from below."""
        value_low_g = gordon_growth_value(1.0, 0.10, 0.01)
        value_high_g = gordon_growth_value(1.0, 0.10, 0.09)
        assert value_high_g > value_low_g

    def test_g_equals_ke_raises(self):
        """g == Ke should raise ValueError (division by zero)."""
        with pytest.raises(ValueError, match="growth_rate"):
            gordon_growth_value(2.00, 0.08, 0.08)

    def test_g_exceeds_ke_raises(self):
        """g > Ke should raise ValueError (negative, nonsensical value)."""
        with pytest.raises(ValueError, match="growth_rate"):
            gordon_growth_value(2.00, 0.08, 0.10)

    def test_small_dividend(self):
        """Handles very small dividend amounts without error."""
        value = gordon_growth_value(0.01, 0.09, 0.03)
        expected = 0.01 * 1.03 / (0.09 - 0.03)
        assert value == pytest.approx(expected, rel=1e-9)


class TestGordonImpliedGrowth:
    def test_round_trip_coned(self):
        """Implied growth from ConEd anchor price should recover 2.1%."""
        price = gordon_growth_value(2.32, 0.077, 0.021)
        g_implied = gordon_implied_growth(price, 2.32, 0.077)
        assert g_implied == pytest.approx(0.021, abs=1e-6)

    def test_implied_growth_known_case(self):
        """Manual verification: P=50, DPS=2, Ke=0.10 → g = (50*0.10 - 2)/(50+2)."""
        expected = (50 * 0.10 - 2.0) / (50 + 2.0)
        assert gordon_implied_growth(50.0, 2.0, 0.10) == pytest.approx(expected, rel=1e-9)

    def test_high_price_implies_high_growth(self):
        """A higher market price implies a higher embedded growth expectation."""
        g_low = gordon_implied_growth(30.0, 2.0, 0.08)
        g_high = gordon_implied_growth(80.0, 2.0, 0.08)
        assert g_high > g_low


# ---------------------------------------------------------------------------
# compute_fcff
# ---------------------------------------------------------------------------

class TestComputeFcff:
    def test_standard_case(self):
        """FCFF = EBIT(1-t) * (1 - reinv_rate)."""
        assert compute_fcff(100.0, 0.30) == pytest.approx(70.0, rel=1e-9)

    def test_zero_reinvestment(self):
        """Zero reinvestment → FCFF equals EBIT(1-t)."""
        assert compute_fcff(200.0, 0.0) == pytest.approx(200.0, rel=1e-9)

    def test_full_reinvestment(self):
        """100% reinvestment → FCFF = 0."""
        assert compute_fcff(150.0, 1.0) == pytest.approx(0.0, abs=1e-9)

    def test_negative_reinvestment_shrinking_firm(self):
        """Negative reinvestment rate (asset liquidation) → FCFF > EBIT(1-t)."""
        fcff = compute_fcff(100.0, -0.20)
        assert fcff == pytest.approx(120.0, rel=1e-9)

    def test_over_reinvestment(self):
        """reinvestment_rate > 1 (acquisition spree) → negative FCFF."""
        fcff = compute_fcff(100.0, 1.50)
        assert fcff == pytest.approx(-50.0, rel=1e-9)


# ---------------------------------------------------------------------------
# compute_terminal_value
# ---------------------------------------------------------------------------

class TestComputeTerminalValue:
    def test_basic_terminal_value(self):
        """TV = FCFF_{n+1} / (WACC - g), where reinv = g/ROC."""
        # final_ebit_at=100, g=3%, ROC=12%, WACC=8%
        # stable_reinv = 0.03/0.12 = 0.25
        # FCFF_n+1 = 100 * 1.03 * (1 - 0.25) = 77.25
        # TV = 77.25 / (0.08 - 0.03) = 1545.0
        tv = compute_terminal_value(100.0, 0.03, 0.12, 0.08)
        assert tv == pytest.approx(1545.0, rel=1e-6)

    def test_zero_growth_terminal(self):
        """With g=0, reinvestment=0, TV = EBIT(1-t) / WACC."""
        tv = compute_terminal_value(100.0, 0.0, 0.10, 0.08)
        # FCFF = 100*1.0*(1-0) = 100; TV = 100/0.08 = 1250
        assert tv == pytest.approx(1250.0, rel=1e-6)

    def test_wacc_equals_growth_raises(self):
        """WACC == g → ValueError (infinite terminal value)."""
        with pytest.raises(ValueError, match="wacc"):
            compute_terminal_value(100.0, 0.05, 0.12, 0.05)

    def test_wacc_less_than_growth_raises(self):
        """WACC < g → ValueError (negative, economically meaningless TV)."""
        with pytest.raises(ValueError, match="wacc"):
            compute_terminal_value(100.0, 0.07, 0.12, 0.05)

    def test_high_roc_low_reinvestment(self):
        """High ROC means low reinvestment requirement → higher FCFF and TV."""
        tv_high_roc = compute_terminal_value(100.0, 0.03, 0.20, 0.08)
        tv_low_roc  = compute_terminal_value(100.0, 0.03, 0.08, 0.08)
        assert tv_high_roc > tv_low_roc


# ---------------------------------------------------------------------------
# discount_cashflows
# ---------------------------------------------------------------------------

class TestDiscountCashflows:
    def test_constant_wacc_single_period(self):
        """Single cash flow: PV = CF / (1 + WACC)."""
        pvs = discount_cashflows([110.0], [0.10])
        assert pvs == [pytest.approx(100.0, rel=1e-9)]

    def test_constant_wacc_multi_period(self):
        """Constant WACC: each PV_t = CF_t / (1+w)^t."""
        cfs = [100.0, 100.0, 100.0]
        w = 0.10
        pvs = discount_cashflows(cfs, [w, w, w])
        for t, pv in enumerate(pvs, start=1):
            assert pv == pytest.approx(100.0 / (1.10 ** t), rel=1e-9)

    def test_varying_wacc(self):
        """Varying WACCs: cumulative discounting, not period-by-period."""
        # Year 1: WACC=10%, PV = 110 / 1.10 = 100
        # Year 2: WACC=8%,  PV = 216 / (1.10 * 1.08) = 216/1.188 ≈ 181.818...
        cfs = [110.0, 216.0]
        waccs = [0.10, 0.08]
        pvs = discount_cashflows(cfs, waccs)
        assert pvs[0] == pytest.approx(110.0 / 1.10, rel=1e-9)
        assert pvs[1] == pytest.approx(216.0 / (1.10 * 1.08), rel=1e-9)

    def test_mismatched_lengths_raises(self):
        """Mismatched cashflows/waccs → ValueError."""
        with pytest.raises(ValueError, match="equal length"):
            discount_cashflows([100.0, 200.0], [0.10])

    def test_empty_inputs(self):
        """Empty inputs return empty list without error."""
        assert discount_cashflows([], []) == []


# ---------------------------------------------------------------------------
# interpolate_params
# ---------------------------------------------------------------------------

class TestInterpolateParams:
    def test_no_transition_all_high_growth(self):
        """gradual=False: all years at high_growth_value."""
        result = interpolate_params(0.15, 0.03, 5, gradual=False)
        assert result == [0.15] * 5

    def test_gradual_10_years(self):
        """10 years: first 5 at HG, years 6-10 linearly interpolate to stable."""
        result = interpolate_params(0.15, 0.03, 10, gradual=True)
        assert len(result) == 10
        # First half: all at 0.15
        for i in range(5):
            assert result[i] == pytest.approx(0.15, rel=1e-9)
        # Second half: linearly from 0.15 to 0.03
        # transition_start=5, transition_years=5
        # Year indices 5,6,7,8,9 → fractions 0/4, 1/4, 2/4, 3/4, 4/4
        expected_second = [0.15, 0.15 + 0.25*(0.03-0.15), 0.15 + 0.5*(0.03-0.15),
                           0.15 + 0.75*(0.03-0.15), 0.03]
        for i, exp in enumerate(expected_second):
            assert result[5 + i] == pytest.approx(exp, rel=1e-6)

    def test_gradual_last_value_equals_stable(self):
        """The final year must equal the stable value exactly."""
        result = interpolate_params(0.20, 0.05, 8, gradual=True)
        assert result[-1] == pytest.approx(0.05, rel=1e-9)

    def test_gradual_single_year(self):
        """Single year with gradual: that year is the stable value."""
        result = interpolate_params(0.15, 0.03, 1, gradual=True)
        assert len(result) == 1
        assert result[0] == pytest.approx(0.03, rel=1e-9)

    def test_zero_years_returns_empty(self):
        """n_years=0 returns empty list."""
        assert interpolate_params(0.10, 0.03, 0) == []

    def test_stable_equals_high_growth(self):
        """If HG == stable, all values are identical regardless of gradual."""
        result = interpolate_params(0.05, 0.05, 6, gradual=True)
        assert all(v == pytest.approx(0.05, rel=1e-9) for v in result)


# ---------------------------------------------------------------------------
# fcff_valuation — integration
# ---------------------------------------------------------------------------

class TestFcffValuation:
    def test_simple_case_keys_present(self):
        """Result dict has all required keys."""
        result = fcff_valuation(
            current_ebit_after_tax=100.0,
            growth_rates=[0.10, 0.10, 0.08],
            reinvestment_rates=[0.40, 0.40, 0.35],
            waccs=[0.09, 0.09, 0.09],
            stable_growth=0.03,
            stable_roc=0.12,
            stable_wacc=0.08,
        )
        expected_keys = {
            "enterprise_value", "equity_value", "equity_value_per_share",
            "pv_high_growth", "pv_terminal", "terminal_value",
            "yearly_fcff", "yearly_pv", "yearly_ebit_at",
        }
        assert expected_keys.issubset(result.keys())

    def test_yearly_lists_length(self):
        """yearly_* lists all have length equal to projection years."""
        n = 5
        result = fcff_valuation(
            current_ebit_after_tax=200.0,
            growth_rates=[0.12] * n,
            reinvestment_rates=[0.45] * n,
            waccs=[0.09] * n,
            stable_growth=0.03,
            stable_roc=0.10,
            stable_wacc=0.08,
        )
        assert len(result["yearly_fcff"]) == n
        assert len(result["yearly_pv"]) == n
        assert len(result["yearly_ebit_at"]) == n

    def test_ev_equals_pv_hg_plus_pv_terminal(self):
        """Enterprise value = pv_high_growth + pv_terminal."""
        result = fcff_valuation(
            current_ebit_after_tax=150.0,
            growth_rates=[0.10, 0.08, 0.06],
            reinvestment_rates=[0.40, 0.35, 0.30],
            waccs=[0.09, 0.09, 0.09],
            stable_growth=0.03,
            stable_roc=0.12,
            stable_wacc=0.08,
        )
        assert result["enterprise_value"] == pytest.approx(
            result["pv_high_growth"] + result["pv_terminal"], rel=1e-9
        )

    def test_equity_bridge(self):
        """equity_value = EV + cash - debt + non_op - options."""
        ev_result = fcff_valuation(
            current_ebit_after_tax=100.0,
            growth_rates=[0.10, 0.10],
            reinvestment_rates=[0.40, 0.40],
            waccs=[0.09, 0.09],
            stable_growth=0.03,
            stable_roc=0.12,
            stable_wacc=0.08,
            cash=50.0,
            debt=200.0,
            non_operating_assets=30.0,
            options_value=10.0,
            shares_outstanding=1.0,
        )
        expected_equity = (
            ev_result["enterprise_value"] + 50.0 - 200.0 + 30.0 - 10.0
        )
        assert ev_result["equity_value"] == pytest.approx(expected_equity, rel=1e-9)

    def test_per_share_division(self):
        """equity_value_per_share = equity_value / shares_outstanding."""
        result = fcff_valuation(
            current_ebit_after_tax=100.0,
            growth_rates=[0.10],
            reinvestment_rates=[0.40],
            waccs=[0.09],
            stable_growth=0.03,
            stable_roc=0.12,
            stable_wacc=0.08,
            shares_outstanding=100.0,
        )
        assert result["equity_value_per_share"] == pytest.approx(
            result["equity_value"] / 100.0, rel=1e-9
        )

    def test_mismatched_input_lengths_raises(self):
        """Mismatched growth_rates/reinvestment_rates/waccs → ValueError."""
        with pytest.raises(ValueError):
            fcff_valuation(
                current_ebit_after_tax=100.0,
                growth_rates=[0.10, 0.10],
                reinvestment_rates=[0.40],          # wrong length
                waccs=[0.09, 0.09],
                stable_growth=0.03,
                stable_roc=0.12,
                stable_wacc=0.08,
            )

    def test_ebit_projection_accuracy(self):
        """EBIT(1-t) grows by the specified growth rate each year."""
        result = fcff_valuation(
            current_ebit_after_tax=100.0,
            growth_rates=[0.10, 0.20, 0.05],
            reinvestment_rates=[0.0, 0.0, 0.0],
            waccs=[0.09, 0.09, 0.09],
            stable_growth=0.03,
            stable_roc=0.15,
            stable_wacc=0.08,
        )
        assert result["yearly_ebit_at"][0] == pytest.approx(110.0, rel=1e-9)
        assert result["yearly_ebit_at"][1] == pytest.approx(132.0, rel=1e-9)
        assert result["yearly_ebit_at"][2] == pytest.approx(138.6, rel=1e-6)

    def test_zero_reinvestment_fcff_equals_ebit(self):
        """With 0% reinvestment, FCFF equals EBIT(1-t) each year."""
        result = fcff_valuation(
            current_ebit_after_tax=100.0,
            growth_rates=[0.10, 0.10],
            reinvestment_rates=[0.0, 0.0],
            waccs=[0.09, 0.09],
            stable_growth=0.03,
            stable_roc=0.15,
            stable_wacc=0.08,
        )
        for fcff, ebit_at in zip(result["yearly_fcff"], result["yearly_ebit_at"]):
            assert fcff == pytest.approx(ebit_at, rel=1e-9)

    def test_terminal_value_reasonable_magnitude(self):
        """PV of terminal value should be positive and dominate high-growth PVs."""
        result = fcff_valuation(
            current_ebit_after_tax=100.0,
            growth_rates=[0.15, 0.15, 0.12, 0.10, 0.08],
            reinvestment_rates=[0.50, 0.50, 0.45, 0.40, 0.35],
            waccs=[0.10, 0.10, 0.10, 0.09, 0.09],
            stable_growth=0.03,
            stable_roc=0.12,
            stable_wacc=0.08,
        )
        assert result["pv_terminal"] > 0
        assert result["terminal_value"] > 0
        # For a growing firm, terminal value PV typically exceeds sum of explicit FCFFs
        assert result["pv_terminal"] > result["pv_high_growth"]
