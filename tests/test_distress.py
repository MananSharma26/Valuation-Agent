"""Tests for valuation.engines.distress — failure probability adjustment module."""

import pytest
from valuation.engines.distress import (
    DEFAULT_RATES,
    get_failure_probability,
    estimate_distress_proceeds,
    failure_adjusted_valuation,
)


# ---------------------------------------------------------------------------
# get_failure_probability
# ---------------------------------------------------------------------------

class TestGetFailureProbability:
    def test_aaa_negligible(self):
        """AAA-rated firm has near-zero 10-year failure probability."""
        p = get_failure_probability("Aaa/AAA")
        assert p == pytest.approx(0.0001)
        assert p < 0.001  # negligible

    def test_ccc_large(self):
        """CCC-rated firm has large (20%) failure probability."""
        p = get_failure_probability("Caa/CCC")
        assert p == pytest.approx(0.20)

    def test_d_near_certain(self):
        """D-rated firm has 80% failure probability."""
        p = get_failure_probability("D2/D")
        assert p == pytest.approx(0.80)

    def test_investment_grade_bbb(self):
        """Investment-grade BBB has 0.5% failure probability."""
        p = get_failure_probability("Baa2/BBB")
        assert p == pytest.approx(0.005)

    def test_b_plus(self):
        """B+ (speculative) has 5% failure probability."""
        p = get_failure_probability("B1/B+")
        assert p == pytest.approx(0.05)

    def test_all_default_rates_in_range(self):
        """All default rates must be strictly between 0 and 1."""
        for rating, p in DEFAULT_RATES.items():
            assert 0.0 < p < 1.0, f"Rate for {rating} out of range: {p}"

    def test_default_rates_monotone(self):
        """Failure probabilities should be non-decreasing down the credit ladder."""
        ordered = list(DEFAULT_RATES.values())
        for i in range(len(ordered) - 1):
            assert ordered[i] <= ordered[i + 1], (
                f"Non-monotone at position {i}: {ordered[i]} > {ordered[i + 1]}"
            )

    def test_unknown_rating_raises(self):
        """Unknown rating string must raise KeyError."""
        with pytest.raises(KeyError, match="Unknown rating"):
            get_failure_probability("ZZZ/ZZZ")


# ---------------------------------------------------------------------------
# estimate_distress_proceeds
# ---------------------------------------------------------------------------

class TestEstimateDistressProceeds:
    def test_default_fifty_percent(self):
        """Default liquidation_pct = 0.50 halves book value."""
        proceeds = estimate_distress_proceeds(book_value_of_assets=1000.0)
        assert proceeds == pytest.approx(500.0)

    def test_custom_liquidation_pct(self):
        """Custom liquidation_pct is applied correctly."""
        proceeds = estimate_distress_proceeds(
            book_value_of_assets=400.0, liquidation_pct=0.25
        )
        assert proceeds == pytest.approx(100.0)

    def test_full_liquidation(self):
        """liquidation_pct = 1.0 means full book recovery (theoretical ceiling)."""
        proceeds = estimate_distress_proceeds(
            book_value_of_assets=200.0, liquidation_pct=1.0
        )
        assert proceeds == pytest.approx(200.0)

    def test_zero_assets(self):
        """Zero book value yields zero proceeds regardless of liquidation_pct."""
        proceeds = estimate_distress_proceeds(
            book_value_of_assets=0.0, liquidation_pct=0.60
        )
        assert proceeds == pytest.approx(0.0)

    def test_invalid_liquidation_pct_zero_raises(self):
        """liquidation_pct = 0 is meaningless; must raise ValueError."""
        with pytest.raises(ValueError, match="liquidation_pct"):
            estimate_distress_proceeds(1000.0, liquidation_pct=0.0)

    def test_invalid_liquidation_pct_negative_raises(self):
        """Negative liquidation_pct must raise ValueError."""
        with pytest.raises(ValueError, match="liquidation_pct"):
            estimate_distress_proceeds(1000.0, liquidation_pct=-0.1)

    def test_invalid_liquidation_pct_above_one_raises(self):
        """liquidation_pct > 1 must raise ValueError."""
        with pytest.raises(ValueError, match="liquidation_pct"):
            estimate_distress_proceeds(1000.0, liquidation_pct=1.01)


# ---------------------------------------------------------------------------
# failure_adjusted_valuation
# ---------------------------------------------------------------------------

class TestFailureAdjustedValuation:
    def test_zero_probability_value_unchanged(self):
        """Zero failure probability: adjusted value equals GC value."""
        result = failure_adjusted_valuation(
            going_concern_value=100.0,
            probability_of_failure=0.0,
            distress_proceeds=10.0,
        )
        assert result["adjusted_value"] == pytest.approx(100.0)
        assert result["value_lost_to_distress"] == pytest.approx(0.0)

    def test_one_probability_value_equals_distress(self):
        """Probability = 1.0: adjusted value equals distress proceeds."""
        result = failure_adjusted_valuation(
            going_concern_value=100.0,
            probability_of_failure=1.0,
            distress_proceeds=30.0,
        )
        assert result["adjusted_value"] == pytest.approx(30.0)
        assert result["value_lost_to_distress"] == pytest.approx(70.0)

    def test_fifty_percent_is_average(self):
        """50% probability: adjusted value is simple average of GC and distress."""
        gc = 80.0
        distress = 20.0
        result = failure_adjusted_valuation(
            going_concern_value=gc,
            probability_of_failure=0.50,
            distress_proceeds=distress,
        )
        expected = (gc + distress) / 2.0
        assert result["adjusted_value"] == pytest.approx(expected)
        assert result["value_lost_to_distress"] == pytest.approx(gc - expected)

    def test_aaa_adjustment_negligible(self):
        """AAA-rated company: distress adjustment barely moves the needle."""
        gc = 150.0
        distress = 20.0
        p = get_failure_probability("Aaa/AAA")  # 0.0001
        result = failure_adjusted_valuation(
            going_concern_value=gc,
            probability_of_failure=p,
            distress_proceeds=distress,
        )
        # Adjustment is tiny: 0.0001 * (150 - 20) = 0.013
        assert result["adjusted_value"] == pytest.approx(gc, abs=0.05)
        assert result["value_lost_to_distress"] < 0.05

    def test_ccc_adjustment_large(self):
        """CCC-rated company (P=20%): distress knocks a meaningful chunk off value."""
        gc = 50.0
        distress = 5.0
        p = get_failure_probability("Caa/CCC")  # 0.20
        result = failure_adjusted_valuation(
            going_concern_value=gc,
            probability_of_failure=p,
            distress_proceeds=distress,
        )
        # adjusted = 50 * 0.80 + 5 * 0.20 = 40 + 1 = 41
        assert result["adjusted_value"] == pytest.approx(41.0)
        assert result["value_lost_to_distress"] == pytest.approx(9.0)

    def test_negative_gc_value_edge_case(self):
        """Negative GC value (already in distress): formula still applies correctly."""
        gc = -10.0
        distress = 5.0
        p = 0.60
        result = failure_adjusted_valuation(
            going_concern_value=gc,
            probability_of_failure=p,
            distress_proceeds=distress,
        )
        # adjusted = -10 * 0.40 + 5 * 0.60 = -4 + 3 = -1
        assert result["adjusted_value"] == pytest.approx(-1.0)
        # value_lost = gc - adjusted = -10 - (-1) = -9
        # (negative means distress proceeds partially recover relative to GC)
        assert result["value_lost_to_distress"] == pytest.approx(-9.0)

    def test_distress_proceeds_zero(self):
        """Equity worth zero in distress: adjusted value scaled by survival probability."""
        gc = 60.0
        result = failure_adjusted_valuation(
            going_concern_value=gc,
            probability_of_failure=0.30,
            distress_proceeds=0.0,
        )
        # adjusted = 60 * 0.70 + 0 * 0.30 = 42
        assert result["adjusted_value"] == pytest.approx(42.0)
        assert result["value_lost_to_distress"] == pytest.approx(18.0)

    def test_output_keys_present(self):
        """Return dict contains exactly the expected keys."""
        result = failure_adjusted_valuation(
            going_concern_value=100.0,
            probability_of_failure=0.10,
            distress_proceeds=15.0,
        )
        expected_keys = {
            "adjusted_value",
            "going_concern_value",
            "failure_probability",
            "distress_proceeds",
            "value_lost_to_distress",
        }
        assert set(result.keys()) == expected_keys

    def test_passthrough_inputs_unchanged(self):
        """Input values are echoed back unchanged in the result dict."""
        gc = 75.0
        p = 0.15
        d = 12.0
        result = failure_adjusted_valuation(
            going_concern_value=gc,
            probability_of_failure=p,
            distress_proceeds=d,
        )
        assert result["going_concern_value"] == gc
        assert result["failure_probability"] == p
        assert result["distress_proceeds"] == d

    def test_invalid_probability_negative_raises(self):
        """Negative probability must raise ValueError."""
        with pytest.raises(ValueError, match="probability_of_failure"):
            failure_adjusted_valuation(
                going_concern_value=100.0,
                probability_of_failure=-0.01,
                distress_proceeds=10.0,
            )

    def test_invalid_probability_above_one_raises(self):
        """Probability > 1 must raise ValueError."""
        with pytest.raises(ValueError, match="probability_of_failure"):
            failure_adjusted_valuation(
                going_concern_value=100.0,
                probability_of_failure=1.01,
                distress_proceeds=10.0,
            )
