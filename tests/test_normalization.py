"""Tests for valuation.engines.normalization.

Covers:
  - Normal 5-year case for all three methods
  - Peak / trough / mid cycle-position detection
  - Each method produces different but economically reasonable results
  - Edge case: only 2 years of data
  - Edge case: negative EBIT in some years
  - Input-validation errors
"""

import pytest
import pandas as pd

from valuation.engines.normalization import (
    detect_cycle_position,
    normalize_earnings_cyclical,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_income_stmt(revenues: list[float], ebits: list[float]) -> pd.DataFrame:
    """Build a minimal income-statement DataFrame (rows = line items, cols = years)."""
    years = [f"FY{i+1}" for i in range(len(revenues))]
    return pd.DataFrame(
        {
            "Total Revenue": revenues,
            "Operating Income": ebits,
        },
        index=years,
    ).T  # rows = line items, cols = years


# ---------------------------------------------------------------------------
# detect_cycle_position
# ---------------------------------------------------------------------------

class TestDetectCyclePosition:

    def test_peak_detection(self):
        """Current margin above 75th percentile → 'peak'."""
        # margins: [0.05, 0.08, 0.09, 0.10, 0.20]
        # p75 of these 5 values (linear interp): 0.10
        # current = 0.20 >= p75 → peak
        margins = [0.05, 0.08, 0.09, 0.10, 0.20]
        assert detect_cycle_position(margins) == "peak"

    def test_trough_detection(self):
        """Current margin below 25th percentile → 'trough'."""
        # margins: [0.01, 0.10, 0.12, 0.15, 0.18]
        # p25 of these 5 values (linear interp): 0.10
        # current = 0.01 <= p25 → trough
        margins = [0.10, 0.12, 0.15, 0.18, 0.01]
        assert detect_cycle_position(margins) == "trough"

    def test_mid_cycle_detection(self):
        """Current margin between 25th and 75th percentile → 'mid'."""
        margins = [0.05, 0.08, 0.12, 0.15, 0.10]
        # sorted: [0.05, 0.08, 0.10, 0.12, 0.15]
        # p25 = 0.08 (index 1), p75 = 0.12 (index 3)
        # current = 0.10 → mid
        assert detect_cycle_position(margins) == "mid"

    def test_exactly_at_75th_percentile_is_peak(self):
        """A margin exactly equal to p75 should be classified as 'peak'."""
        margins = [0.05, 0.10, 0.15, 0.20, 0.15]
        # sorted: [0.05, 0.10, 0.15, 0.15, 0.20]
        # p75 at index 3 = 0.15; current = 0.15 → peak (>=)
        result = detect_cycle_position(margins)
        assert result == "peak"

    def test_exactly_at_25th_percentile_is_trough(self):
        """A margin exactly equal to p25 should be classified as 'trough'."""
        margins = [0.05, 0.10, 0.15, 0.20, 0.05]
        # sorted: [0.05, 0.05, 0.10, 0.15, 0.20]
        # p25 at index 1 = 0.05; current = 0.05 → trough (<=)
        result = detect_cycle_position(margins)
        assert result == "trough"

    def test_two_elements_minimum(self):
        """Two-element list should work without error."""
        assert detect_cycle_position([0.10, 0.20]) == "peak"
        assert detect_cycle_position([0.20, 0.10]) == "trough"

    def test_single_element_raises(self):
        """Fewer than 2 elements should raise ValueError."""
        with pytest.raises(ValueError, match="2"):
            detect_cycle_position([0.10])

    def test_empty_raises(self):
        """Empty list should raise ValueError."""
        with pytest.raises(ValueError, match="2"):
            detect_cycle_position([])


# ---------------------------------------------------------------------------
# normalize_earnings_cyclical — normal 5-year case
# ---------------------------------------------------------------------------

class TestNormalizeEarningsCyclical:
    """Five years of varying margins (a typical cyclical profile)."""

    # Revenue steady at 1000; EBIT cycles: 80, 120, 150, 100, 60
    # Margins:  0.08, 0.12, 0.15, 0.10, 0.06
    # Current (last col) revenue = 1000, EBIT = 60 (trough-ish)
    REVENUES = [1000, 1000, 1000, 1000, 1000]
    EBITS = [80, 120, 150, 100, 60]

    @pytest.fixture
    def df(self):
        return _make_income_stmt(self.REVENUES, self.EBITS)

    def test_average_margin_method(self, df):
        result = normalize_earnings_cyclical(df, method="average_margin", n_years=5)
        assert result["method_used"] == "average_margin"
        # avg margin = (0.08+0.12+0.15+0.10+0.06)/5 = 0.51/5 = 0.102
        # normalized_ebit = 0.102 * 1000 = 102.0
        assert result["normalized_ebit"] == pytest.approx(102.0, rel=1e-6)
        assert result["normalized_margin"] == pytest.approx(0.102, rel=1e-6)

    def test_average_ebit_method(self, df):
        result = normalize_earnings_cyclical(df, method="average_ebit", n_years=5)
        assert result["method_used"] == "average_ebit"
        # avg EBIT = (80+120+150+100+60)/5 = 102.0
        assert result["normalized_ebit"] == pytest.approx(102.0, rel=1e-6)

    def test_peak_trough_avg_method(self, df):
        result = normalize_earnings_cyclical(df, method="peak_trough_avg", n_years=5)
        assert result["method_used"] == "peak_trough_avg"
        # (max=150 + min=60) / 2 = 105.0
        assert result["normalized_ebit"] == pytest.approx(105.0, rel=1e-6)

    def test_methods_produce_different_values(self):
        """All three methods produce distinct results when revenues vary across years.

        When revenues are constant, average_margin × current_revenue equals
        average_ebit exactly.  We use a dataset with growing revenues to break
        that degeneracy so all three methods diverge.
        """
        # Revenues grow, EBIT cycles → margins are uneven
        # Rev:  800, 900, 1000, 1100, 1200
        # EBIT:  80, 135,  150,   88,   60
        # Margins: 0.100, 0.150, 0.150, 0.080, 0.050
        # avg_margin = 0.106; norm_ebit_am = 0.106 * 1200 = 127.2
        # avg_ebit   = (80+135+150+88+60)/5 = 102.6
        # peak_trough = (150+60)/2 = 105.0
        df_varying = _make_income_stmt(
            revenues=[800, 900, 1000, 1100, 1200],
            ebits=[80, 135, 150, 88, 60],
        )
        r_am = normalize_earnings_cyclical(df_varying, method="average_margin", n_years=5)
        r_ae = normalize_earnings_cyclical(df_varying, method="average_ebit", n_years=5)
        r_pt = normalize_earnings_cyclical(df_varying, method="peak_trough_avg", n_years=5)

        values = {
            round(r_am["normalized_ebit"], 6),
            round(r_ae["normalized_ebit"], 6),
            round(r_pt["normalized_ebit"], 6),
        }
        assert len(values) == 3, (
            f"Expected three distinct normalised EBIT values; got {values}"
        )

    def test_all_methods_produce_reasonable_values(self, df):
        """Normalised EBIT should be between the historical min and max."""
        ebit_min, ebit_max = min(self.EBITS), max(self.EBITS)
        for method in ("average_margin", "average_ebit", "peak_trough_avg"):
            result = normalize_earnings_cyclical(df, method=method, n_years=5)
            assert ebit_min <= result["normalized_ebit"] <= ebit_max, (
                f"Method '{method}' returned {result['normalized_ebit']}, "
                f"outside [{ebit_min}, {ebit_max}]."
            )

    def test_raw_margins_returned(self, df):
        result = normalize_earnings_cyclical(df, method="average_margin", n_years=5)
        assert result["raw_margins"] == pytest.approx(
            [0.08, 0.12, 0.15, 0.10, 0.06], rel=1e-6
        )

    def test_cycle_position_is_trough(self, df):
        """Current EBIT=60 (margin=0.06) is the lowest → trough."""
        result = normalize_earnings_cyclical(df, method="average_margin", n_years=5)
        assert result["cycle_position"] == "trough"

    def test_cycle_position_is_peak_when_at_top(self):
        """When current earnings are at historical high, cycle_position == 'peak'."""
        df = _make_income_stmt(
            revenues=[1000, 1000, 1000, 1000, 1000],
            ebits=[60, 80, 100, 120, 150],
        )
        result = normalize_earnings_cyclical(df, method="average_margin", n_years=5)
        assert result["cycle_position"] == "peak"

    def test_cycle_position_mid(self):
        """Mid-cycle current earnings should return 'mid'."""
        # margins: 0.04, 0.08, 0.12, 0.16, 0.10
        # sorted:  [0.04, 0.08, 0.10, 0.12, 0.16]
        # p25 (index 1) = 0.08, p75 (index 3) = 0.12
        # current = 0.10: strictly between p25 and p75 → mid
        df = _make_income_stmt(
            revenues=[1000, 1000, 1000, 1000, 1000],
            ebits=[40, 80, 120, 160, 100],
        )
        result = normalize_earnings_cyclical(df, method="average_margin", n_years=5)
        assert result["cycle_position"] == "mid"


# ---------------------------------------------------------------------------
# Edge case: only 2 years of data
# ---------------------------------------------------------------------------

class TestEdgeCaseTwoYears:

    def test_two_years_average_margin(self):
        """Should work with just 2 years, not raise."""
        df = _make_income_stmt(revenues=[500, 600], ebits=[50, 90])
        result = normalize_earnings_cyclical(df, method="average_margin", n_years=5)
        # avg margin = (0.10 + 0.15) / 2 = 0.125; current rev = 600
        assert result["normalized_ebit"] == pytest.approx(0.125 * 600, rel=1e-6)
        assert result["normalized_margin"] == pytest.approx(0.125, rel=1e-6)

    def test_two_years_average_ebit(self):
        df = _make_income_stmt(revenues=[500, 600], ebits=[50, 90])
        result = normalize_earnings_cyclical(df, method="average_ebit", n_years=5)
        assert result["normalized_ebit"] == pytest.approx(70.0, rel=1e-6)

    def test_two_years_peak_trough_avg(self):
        df = _make_income_stmt(revenues=[500, 600], ebits=[50, 90])
        result = normalize_earnings_cyclical(df, method="peak_trough_avg", n_years=5)
        # (90 + 50) / 2 = 70
        assert result["normalized_ebit"] == pytest.approx(70.0, rel=1e-6)

    def test_two_years_raw_margins_length(self):
        df = _make_income_stmt(revenues=[500, 600], ebits=[50, 90])
        result = normalize_earnings_cyclical(df, method="average_margin", n_years=2)
        assert len(result["raw_margins"]) == 2

    def test_n_years_one_column_raises(self):
        """n_years=1 produces only 1 year of data which is below the 2-year minimum."""
        df = _make_income_stmt(revenues=[500, 600], ebits=[50, 90])
        with pytest.raises(ValueError, match="2"):
            normalize_earnings_cyclical(df, method="average_margin", n_years=1)


# ---------------------------------------------------------------------------
# Edge case: negative EBIT in some years
# ---------------------------------------------------------------------------

class TestNegativeEBIT:

    # A company with a loss year in the middle of the cycle
    REVENUES = [1000, 1000, 1000, 1000, 1000]
    EBITS = [100, -50, 80, 120, 90]  # year 2 is a loss

    @pytest.fixture
    def df(self):
        return _make_income_stmt(self.REVENUES, self.EBITS)

    def test_average_margin_handles_negative(self, df):
        """average_margin should include the negative margin in the average."""
        result = normalize_earnings_cyclical(df, method="average_margin", n_years=5)
        # margins: 0.10, -0.05, 0.08, 0.12, 0.09
        # avg = (0.10 - 0.05 + 0.08 + 0.12 + 0.09) / 5 = 0.34 / 5 = 0.068
        assert result["normalized_ebit"] == pytest.approx(0.068 * 1000, rel=1e-6)
        assert result["normalized_margin"] == pytest.approx(0.068, rel=1e-6)

    def test_average_ebit_handles_negative(self, df):
        result = normalize_earnings_cyclical(df, method="average_ebit", n_years=5)
        # avg = (100 - 50 + 80 + 120 + 90) / 5 = 340 / 5 = 68.0
        assert result["normalized_ebit"] == pytest.approx(68.0, rel=1e-6)

    def test_peak_trough_avg_handles_negative(self, df):
        result = normalize_earnings_cyclical(df, method="peak_trough_avg", n_years=5)
        # (max=120 + min=-50) / 2 = 35.0
        assert result["normalized_ebit"] == pytest.approx(35.0, rel=1e-6)

    def test_negative_normalized_ebit_allowed(self):
        """If all years are loss-making, normalized_ebit should be negative."""
        df = _make_income_stmt(
            revenues=[1000, 1000, 1000],
            ebits=[-100, -80, -60],
        )
        result = normalize_earnings_cyclical(df, method="average_ebit", n_years=3)
        assert result["normalized_ebit"] < 0

    def test_raw_margins_include_negative(self, df):
        result = normalize_earnings_cyclical(df, method="average_margin", n_years=5)
        assert any(m < 0 for m in result["raw_margins"])


# ---------------------------------------------------------------------------
# n_years window behaviour
# ---------------------------------------------------------------------------

class TestNYearsWindow:

    def test_n_years_limits_history(self):
        """Requesting fewer years should use only the most-recent n columns."""
        df = _make_income_stmt(
            revenues=[1000, 1000, 1000, 1000, 1000],
            ebits=[200, 150, 100, 80, 60],
        )
        result_5 = normalize_earnings_cyclical(df, method="average_ebit", n_years=5)
        result_3 = normalize_earnings_cyclical(df, method="average_ebit", n_years=3)

        # 5-year avg: (200+150+100+80+60)/5 = 118
        assert result_5["normalized_ebit"] == pytest.approx(118.0, rel=1e-6)
        # 3-year avg (last 3 cols): (100+80+60)/3 = 80
        assert result_3["normalized_ebit"] == pytest.approx(80.0, rel=1e-6)

    def test_n_years_larger_than_available_columns(self):
        """n_years > available columns should use all available data without error."""
        df = _make_income_stmt(revenues=[500, 600], ebits=[50, 60])
        result = normalize_earnings_cyclical(df, method="average_ebit", n_years=10)
        assert result["normalized_ebit"] == pytest.approx(55.0, rel=1e-6)


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------

class TestInputValidation:

    @pytest.fixture
    def valid_df(self):
        return _make_income_stmt(
            revenues=[1000, 1000, 1000],
            ebits=[80, 100, 90],
        )

    def test_invalid_method_raises(self, valid_df):
        with pytest.raises(ValueError, match="method"):
            normalize_earnings_cyclical(valid_df, method="invalid_method")

    def test_n_years_zero_raises(self, valid_df):
        with pytest.raises(ValueError, match="n_years"):
            normalize_earnings_cyclical(valid_df, n_years=0)

    def test_missing_revenue_col_raises(self, valid_df):
        with pytest.raises(ValueError, match="Revenue"):
            normalize_earnings_cyclical(
                valid_df, revenue_col="NonExistent Revenue", n_years=3
            )

    def test_missing_ebit_col_raises(self, valid_df):
        with pytest.raises(ValueError, match="EBIT"):
            normalize_earnings_cyclical(
                valid_df, ebit_col="NonExistent EBIT", n_years=3
            )

    def test_custom_column_names(self):
        """Should work with non-default column names."""
        df = pd.DataFrame(
            {
                "Sales": [800.0, 900.0, 1000.0],
                "EBIT": [80.0, 90.0, 100.0],
            },
            index=["FY1", "FY2", "FY3"],
        ).T
        result = normalize_earnings_cyclical(
            df,
            revenue_col="Sales",
            ebit_col="EBIT",
            method="average_ebit",
            n_years=3,
        )
        assert result["normalized_ebit"] == pytest.approx(90.0, rel=1e-6)
