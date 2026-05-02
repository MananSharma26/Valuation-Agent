"""Tests for sanity bounds checker (bounds.py)."""

import pytest

from valuation.validation.bounds import (
    BoundsCheck,
    BoundsReport,
    Severity,
    check_all_inputs,
    check_bound,
    check_terminal_vs_wacc,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ok(result: BoundsCheck) -> None:
    assert result.severity == Severity.OK, f"Expected OK, got {result.severity}: {result.message}"


def _warn(result: BoundsCheck) -> None:
    assert result.severity == Severity.WARN, f"Expected WARN, got {result.severity}: {result.message}"


def _halt(result: BoundsCheck) -> None:
    assert result.severity == Severity.HALT, f"Expected HALT, got {result.severity}: {result.message}"


# ---------------------------------------------------------------------------
# Normal values should return OK
# ---------------------------------------------------------------------------

class TestNormalValuesOK:
    def test_beta_normal(self):
        _ok(check_bound("beta", 1.0))

    def test_wacc_normal(self):
        _ok(check_bound("wacc", 0.10))

    def test_terminal_growth_normal(self):
        _ok(check_bound("terminal_growth", 0.03))

    def test_revenue_growth_normal(self):
        _ok(check_bound("revenue_growth", 0.15))

    def test_operating_margin_normal(self):
        _ok(check_bound("operating_margin", 0.20))

    def test_shares_outstanding_normal(self):
        _ok(check_bound("shares_outstanding", 1000.0))

    def test_reinvestment_rate_normal(self):
        _ok(check_bound("reinvestment_rate", 0.5))

    def test_debt_to_capital_normal(self):
        _ok(check_bound("debt_to_capital", 0.40))

    def test_cost_of_equity_normal(self):
        _ok(check_bound("cost_of_equity", 0.12))

    def test_cost_of_debt_normal(self):
        _ok(check_bound("cost_of_debt", 0.06))

    def test_equity_value_per_share_positive(self):
        # positive equity value: within warn range (warn_lo=0.0)
        _ok(check_bound("equity_value_per_share", 50.0))


# ---------------------------------------------------------------------------
# Values in warn range return WARN
# ---------------------------------------------------------------------------

class TestWarnRange:
    def test_beta_below_warn(self):
        # warn_lo=0.3, halt_lo=0.0 — value between halt_lo and warn_lo
        result = check_bound("beta", 0.2)
        _warn(result)

    def test_beta_above_warn(self):
        # warn_hi=3.5, halt_hi=5.0
        result = check_bound("beta", 4.0)
        _warn(result)

    def test_wacc_below_warn(self):
        # warn_lo=0.03, halt_lo=0.0
        result = check_bound("wacc", 0.01)
        _warn(result)

    def test_wacc_above_warn(self):
        # warn_hi=0.30, halt_hi=0.50
        result = check_bound("wacc", 0.40)
        _warn(result)

    def test_terminal_growth_below_warn(self):
        # warn_lo=-0.02, halt_lo=-0.10
        result = check_bound("terminal_growth", -0.05)
        _warn(result)

    def test_terminal_growth_above_warn(self):
        # warn_hi=0.06, halt_hi=0.10
        result = check_bound("terminal_growth", 0.08)
        _warn(result)

    def test_revenue_growth_below_warn(self):
        result = check_bound("revenue_growth", -0.50)
        _warn(result)

    def test_revenue_growth_above_warn(self):
        result = check_bound("revenue_growth", 0.80)
        _warn(result)

    def test_operating_margin_below_warn(self):
        result = check_bound("operating_margin", -0.70)
        _warn(result)

    def test_shares_outstanding_below_warn(self):
        # warn_lo=1.0, halt_lo=0.01 — value between halt_lo and warn_lo
        result = check_bound("shares_outstanding", 0.5)
        _warn(result)

    def test_debt_to_capital_above_warn(self):
        # warn_hi=0.95, halt_hi=1.0
        result = check_bound("debt_to_capital", 0.97)
        _warn(result)

    def test_equity_value_per_share_negative_warns(self):
        # warn_lo=0.0, halt_lo=None — negative value triggers WARN (no halt on low side)
        result = check_bound("equity_value_per_share", -10.0)
        _warn(result)


# ---------------------------------------------------------------------------
# Values in halt range return HALT
# ---------------------------------------------------------------------------

class TestHaltRange:
    def test_beta_negative_halts(self):
        result = check_bound("beta", -0.5)
        _halt(result)

    def test_beta_extreme_high_halts(self):
        result = check_bound("beta", 6.0)
        _halt(result)

    def test_wacc_negative_halts(self):
        result = check_bound("wacc", -0.01)
        _halt(result)

    def test_wacc_extreme_high_halts(self):
        result = check_bound("wacc", 0.60)
        _halt(result)

    def test_terminal_growth_extreme_low_halts(self):
        result = check_bound("terminal_growth", -0.15)
        _halt(result)

    def test_terminal_growth_extreme_high_halts(self):
        result = check_bound("terminal_growth", 0.12)
        _halt(result)

    def test_revenue_growth_extreme_low_halts(self):
        result = check_bound("revenue_growth", -0.90)
        _halt(result)

    def test_revenue_growth_extreme_high_halts(self):
        result = check_bound("revenue_growth", 2.0)
        _halt(result)

    def test_operating_margin_below_halt(self):
        result = check_bound("operating_margin", -1.5)
        _halt(result)

    def test_operating_margin_above_halt(self):
        result = check_bound("operating_margin", 1.1)
        _halt(result)

    def test_shares_outstanding_zero_halts(self):
        result = check_bound("shares_outstanding", 0.0)
        _halt(result)

    def test_shares_outstanding_near_zero_halts(self):
        result = check_bound("shares_outstanding", 0.005)
        _halt(result)

    def test_debt_to_capital_above_one_halts(self):
        result = check_bound("debt_to_capital", 1.05)
        _halt(result)

    def test_debt_to_capital_below_halt_halts(self):
        result = check_bound("debt_to_capital", -0.2)
        _halt(result)

    def test_cost_of_equity_negative_halts(self):
        result = check_bound("cost_of_equity", -0.01)
        _halt(result)

    def test_cost_of_debt_extreme_high_halts(self):
        result = check_bound("cost_of_debt", 0.55)
        _halt(result)

    def test_reinvestment_rate_extreme_low_halts(self):
        result = check_bound("reinvestment_rate", -4.0)
        _halt(result)

    def test_reinvestment_rate_extreme_high_halts(self):
        result = check_bound("reinvestment_rate", 6.0)
        _halt(result)


# ---------------------------------------------------------------------------
# None values return WARN
# ---------------------------------------------------------------------------

class TestNoneValues:
    def test_none_beta_warns(self):
        result = check_bound("beta", None)
        _warn(result)
        assert result.value is None
        assert "None" in result.message or "missing" in result.message

    def test_none_wacc_warns(self):
        result = check_bound("wacc", None)
        _warn(result)

    def test_none_unknown_field_warns(self):
        result = check_bound("some_custom_field", None)
        _warn(result)

    def test_none_value_field_attribute(self):
        result = check_bound("terminal_growth", None)
        assert result.value is None
        assert result.field == "terminal_growth"


# ---------------------------------------------------------------------------
# Unknown field returns OK (no bounds defined)
# ---------------------------------------------------------------------------

class TestUnknownField:
    def test_unknown_field_ok(self):
        result = check_bound("totally_made_up_field", 42.0)
        _ok(result)
        assert "no bounds defined" in result.message

    def test_unknown_field_stores_value(self):
        result = check_bound("custom_metric", 3.14)
        assert result.value == pytest.approx(3.14)
        assert result.field == "custom_metric"


# ---------------------------------------------------------------------------
# BoundsReport properties
# ---------------------------------------------------------------------------

class TestBoundsReport:
    def _make_report(self, severities: list[Severity]) -> BoundsReport:
        checks = [
            BoundsCheck(field=f"f{i}", value=float(i), severity=s, message="")
            for i, s in enumerate(severities)
        ]
        return BoundsReport(checks=checks)

    def test_has_halt_true(self):
        report = self._make_report([Severity.OK, Severity.HALT])
        assert report.has_halt is True

    def test_has_halt_false(self):
        report = self._make_report([Severity.OK, Severity.WARN])
        assert report.has_halt is False

    def test_has_warnings_true(self):
        report = self._make_report([Severity.OK, Severity.WARN])
        assert report.has_warnings is True

    def test_has_warnings_false(self):
        report = self._make_report([Severity.OK, Severity.OK])
        assert report.has_warnings is False

    def test_ok_count(self):
        report = self._make_report([Severity.OK, Severity.OK, Severity.WARN, Severity.HALT])
        assert report.ok_count == 2

    def test_ok_count_all_ok(self):
        report = self._make_report([Severity.OK, Severity.OK, Severity.OK])
        assert report.ok_count == 3

    def test_ok_count_none_ok(self):
        report = self._make_report([Severity.WARN, Severity.HALT])
        assert report.ok_count == 0

    def test_warnings_list(self):
        report = self._make_report([Severity.OK, Severity.WARN, Severity.WARN, Severity.HALT])
        assert len(report.warnings) == 2
        assert all(c.severity == Severity.WARN for c in report.warnings)

    def test_halts_list(self):
        report = self._make_report([Severity.HALT, Severity.OK, Severity.HALT])
        assert len(report.halts) == 2
        assert all(c.severity == Severity.HALT for c in report.halts)

    def test_empty_report(self):
        report = BoundsReport()
        assert report.has_halt is False
        assert report.has_warnings is False
        assert report.ok_count == 0
        assert report.warnings == []
        assert report.halts == []


# ---------------------------------------------------------------------------
# Terminal growth vs WACC special check
# ---------------------------------------------------------------------------

class TestTerminalVsWacc:
    def test_equal_halts(self):
        # terminal_growth == wacc => perpetuity formula invalid
        result = check_terminal_vs_wacc(0.10, 0.10)
        _halt(result)
        assert "perpetuity" in result.message.lower() or ">=" in result.message

    def test_growth_above_wacc_halts(self):
        result = check_terminal_vs_wacc(0.12, 0.10)
        _halt(result)

    def test_growth_very_close_to_wacc_warns(self):
        # terminal_growth > wacc - 0.01 but < wacc
        result = check_terminal_vs_wacc(0.095, 0.10)
        _warn(result)
        assert "sensitive" in result.message.lower() or "close" in result.message.lower()

    def test_growth_comfortably_below_wacc_ok(self):
        result = check_terminal_vs_wacc(0.03, 0.10)
        _ok(result)

    def test_none_terminal_growth_warns(self):
        result = check_terminal_vs_wacc(None, 0.10)
        _warn(result)
        assert result.value is None

    def test_none_wacc_warns(self):
        result = check_terminal_vs_wacc(0.03, None)
        _warn(result)

    def test_both_none_warns(self):
        result = check_terminal_vs_wacc(None, None)
        _warn(result)

    def test_field_name(self):
        result = check_terminal_vs_wacc(0.03, 0.10)
        assert result.field == "terminal_growth_vs_wacc"

    def test_value_is_difference(self):
        # value should be terminal_growth - wacc
        result = check_terminal_vs_wacc(0.03, 0.10)
        assert result.value == pytest.approx(0.03 - 0.10)


# ---------------------------------------------------------------------------
# check_all_inputs integration
# ---------------------------------------------------------------------------

class TestCheckAllInputs:
    def test_all_normal_inputs(self):
        inputs = {
            "beta": 1.0,
            "wacc": 0.10,
            "terminal_growth": 0.03,
            "revenue_growth": 0.15,
        }
        report = check_all_inputs(inputs)
        # terminal_growth vs wacc cross-check is also added
        assert len(report.checks) == 5
        assert not report.has_halt
        assert not report.has_warnings

    def test_mixed_results(self):
        inputs = {
            "beta": 1.0,        # OK
            "wacc": 0.10,       # OK
            "terminal_growth": 0.03,  # OK
            "shares_outstanding": 0.0,  # HALT
        }
        report = check_all_inputs(inputs)
        assert report.has_halt
        halt_fields = [c.field for c in report.halts]
        assert "shares_outstanding" in halt_fields

    def test_cross_field_check_added(self):
        inputs = {"terminal_growth": 0.03, "wacc": 0.10}
        report = check_all_inputs(inputs)
        fields = [c.field for c in report.checks]
        assert "terminal_growth_vs_wacc" in fields

    def test_cross_field_check_not_added_if_missing_wacc(self):
        inputs = {"terminal_growth": 0.03, "beta": 1.0}
        report = check_all_inputs(inputs)
        fields = [c.field for c in report.checks]
        assert "terminal_growth_vs_wacc" not in fields

    def test_cross_field_check_not_added_if_missing_terminal_growth(self):
        inputs = {"wacc": 0.10, "beta": 1.0}
        report = check_all_inputs(inputs)
        fields = [c.field for c in report.checks]
        assert "terminal_growth_vs_wacc" not in fields

    def test_terminal_growth_exceeds_wacc_halts_report(self):
        inputs = {"terminal_growth": 0.15, "wacc": 0.10}
        report = check_all_inputs(inputs)
        assert report.has_halt
        halt_fields = [c.field for c in report.halts]
        assert "terminal_growth_vs_wacc" in halt_fields

    def test_none_value_warns(self):
        inputs = {"beta": None, "wacc": 0.10, "terminal_growth": 0.03}
        report = check_all_inputs(inputs)
        assert report.has_warnings
        warn_fields = [c.field for c in report.warnings]
        assert "beta" in warn_fields

    def test_empty_inputs(self):
        report = check_all_inputs({})
        assert len(report.checks) == 0
        assert not report.has_halt
        assert not report.has_warnings

    def test_unknown_field_does_not_cause_error(self):
        inputs = {"some_novel_field": 99.9}
        report = check_all_inputs(inputs)
        assert len(report.checks) == 1
        _ok(report.checks[0])


# ---------------------------------------------------------------------------
# Specific named scenarios from requirements
# ---------------------------------------------------------------------------

class TestSpecificScenarios:
    def test_negative_beta_halts(self):
        result = check_bound("beta", -1.0)
        _halt(result)

    def test_zero_shares_outstanding_halts(self):
        result = check_bound("shares_outstanding", 0.0)
        _halt(result)

    def test_debt_to_capital_096_warns(self):
        result = check_bound("debt_to_capital", 0.96)
        _warn(result)

    def test_debt_to_capital_101_halts(self):
        result = check_bound("debt_to_capital", 1.01)
        _halt(result)

    def test_debt_to_capital_at_warn_boundary(self):
        # exactly at 0.95 — within warn range (not exceeding warn_hi)
        result = check_bound("debt_to_capital", 0.95)
        _ok(result)

    def test_debt_to_capital_at_halt_boundary(self):
        # exactly at 1.0 — not above halt_hi so should be WARN (between warn_hi and halt_hi)
        result = check_bound("debt_to_capital", 1.0)
        _warn(result)
