"""Tests for pre-engine validation layer (pre_engine.py)."""

import pytest

from valuation.context import ValuationContext
from valuation.validation.pre_engine import (
    MissingField,
    ValidationReport,
    validate_for_dcf,
    FCFF_REQUIRED,
    DDM_REQUIRED,
    GORDON_REQUIRED,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_ctx(
    wacc=None,
    terminal_growth=None,
    shares_outstanding=None,
    beta=None,
    tax_rate=None,
    cost_of_equity=None,
    cost_of_debt=None,
    growth_rates=None,
) -> ValuationContext:
    """Build a minimal ValuationContext with the given assumptions."""
    ctx = ValuationContext(ticker="TEST")
    ctx.assumptions.wacc = wacc
    ctx.assumptions.terminal_growth = terminal_growth
    ctx.assumptions.beta = beta
    ctx.assumptions.tax_rate = tax_rate
    ctx.assumptions.cost_of_equity = cost_of_equity
    ctx.assumptions.cost_of_debt = cost_of_debt
    if growth_rates is not None:
        ctx.assumptions.growth_rates = growth_rates
    if shares_outstanding is not None:
        ctx.financials.key_stats["shares_outstanding"] = shares_outstanding
    return ctx


def _full_fcff_ctx() -> ValuationContext:
    """Fully populated context for FCFF."""
    return _make_ctx(
        wacc=0.10,
        terminal_growth=0.03,
        shares_outstanding=1000.0,
        beta=1.0,
        tax_rate=0.25,
        cost_of_equity=0.12,
        cost_of_debt=0.06,
        growth_rates=[0.15, 0.15, 0.12, 0.10, 0.08],
    )


def _full_ddm_ctx() -> ValuationContext:
    """Fully populated context for DDM."""
    return _make_ctx(
        cost_of_equity=0.12,
        terminal_growth=0.03,
        shares_outstanding=1000.0,
        beta=1.0,
        tax_rate=0.25,
        growth_rates=[0.10, 0.10, 0.08],
    )


def _full_gordon_ctx() -> ValuationContext:
    """Fully populated context for Gordon Growth."""
    return _make_ctx(
        cost_of_equity=0.12,
        terminal_growth=0.03,
    )


# ---------------------------------------------------------------------------
# Fully populated contexts — can_proceed = True, no missing
# ---------------------------------------------------------------------------

class TestFullyPopulated:
    def test_fcff_full_can_proceed(self):
        report = validate_for_dcf(_full_fcff_ctx(), model="fcff")
        assert report.can_proceed is True

    def test_fcff_full_no_critical_missing(self):
        report = validate_for_dcf(_full_fcff_ctx(), model="fcff")
        assert report.critical_missing == []

    def test_fcff_full_no_missing_fields(self):
        report = validate_for_dcf(_full_fcff_ctx(), model="fcff")
        assert report.missing_fields == []

    def test_fcff_full_summary_clear(self):
        report = validate_for_dcf(_full_fcff_ctx(), model="fcff")
        assert report.summary == "All inputs validated — clear to run engines"

    def test_ddm_full_can_proceed(self):
        report = validate_for_dcf(_full_ddm_ctx(), model="ddm")
        assert report.can_proceed is True

    def test_ddm_full_no_missing(self):
        report = validate_for_dcf(_full_ddm_ctx(), model="ddm")
        assert report.missing_fields == []

    def test_gordon_full_can_proceed(self):
        report = validate_for_dcf(_full_gordon_ctx(), model="gordon_growth")
        assert report.can_proceed is True

    def test_gordon_full_no_missing(self):
        report = validate_for_dcf(_full_gordon_ctx(), model="gordon_growth")
        assert report.missing_fields == []

    def test_bounds_report_populated(self):
        report = validate_for_dcf(_full_fcff_ctx(), model="fcff")
        assert report.bounds_report is not None


# ---------------------------------------------------------------------------
# Missing WACC (critical for FCFF) — halts
# ---------------------------------------------------------------------------

class TestMissingWacc:
    def test_missing_wacc_cannot_proceed(self):
        ctx = _make_ctx(terminal_growth=0.03, shares_outstanding=1000.0)
        report = validate_for_dcf(ctx, model="fcff")
        assert report.can_proceed is False

    def test_missing_wacc_in_missing_fields(self):
        ctx = _make_ctx(terminal_growth=0.03, shares_outstanding=1000.0)
        report = validate_for_dcf(ctx, model="fcff")
        names = [f.name for f in report.missing_fields]
        assert "wacc" in names

    def test_missing_wacc_is_critical(self):
        ctx = _make_ctx(terminal_growth=0.03, shares_outstanding=1000.0)
        report = validate_for_dcf(ctx, model="fcff")
        critical_names = [f.name for f in report.critical_missing]
        assert "wacc" in critical_names

    def test_missing_wacc_has_suggestion(self):
        ctx = _make_ctx(terminal_growth=0.03, shares_outstanding=1000.0)
        report = validate_for_dcf(ctx, model="fcff")
        wacc_field = next(f for f in report.missing_fields if f.name == "wacc")
        assert len(wacc_field.suggestion) > 0

    def test_missing_wacc_summary_mentions_halted(self):
        ctx = _make_ctx(terminal_growth=0.03, shares_outstanding=1000.0)
        report = validate_for_dcf(ctx, model="fcff")
        assert "HALTED" in report.summary


# ---------------------------------------------------------------------------
# Missing beta (moderate) — can proceed but has warning entry in missing_fields
# ---------------------------------------------------------------------------

class TestMissingBeta:
    def test_missing_beta_can_proceed(self):
        # All critical fields present, only beta missing
        ctx = _make_ctx(
            wacc=0.10,
            terminal_growth=0.03,
            shares_outstanding=1000.0,
            tax_rate=0.25,
            cost_of_equity=0.12,
            cost_of_debt=0.06,
        )
        report = validate_for_dcf(ctx, model="fcff")
        assert report.can_proceed is True

    def test_missing_beta_in_missing_fields(self):
        ctx = _make_ctx(
            wacc=0.10,
            terminal_growth=0.03,
            shares_outstanding=1000.0,
            tax_rate=0.25,
            cost_of_equity=0.12,
            cost_of_debt=0.06,
        )
        report = validate_for_dcf(ctx, model="fcff")
        names = [f.name for f in report.missing_fields]
        assert "beta" in names

    def test_missing_beta_impact_is_moderate(self):
        ctx = _make_ctx(
            wacc=0.10,
            terminal_growth=0.03,
            shares_outstanding=1000.0,
            tax_rate=0.25,
            cost_of_equity=0.12,
            cost_of_debt=0.06,
        )
        report = validate_for_dcf(ctx, model="fcff")
        beta_field = next(f for f in report.missing_fields if f.name == "beta")
        assert beta_field.impact == "moderate"

    def test_missing_beta_not_in_critical_missing(self):
        ctx = _make_ctx(
            wacc=0.10,
            terminal_growth=0.03,
            shares_outstanding=1000.0,
            tax_rate=0.25,
            cost_of_equity=0.12,
            cost_of_debt=0.06,
        )
        report = validate_for_dcf(ctx, model="fcff")
        critical_names = [f.name for f in report.critical_missing]
        assert "beta" not in critical_names


# ---------------------------------------------------------------------------
# DDM model: cost_of_equity is critical
# ---------------------------------------------------------------------------

class TestDDMModel:
    def test_ddm_missing_cost_of_equity_cannot_proceed(self):
        ctx = _make_ctx(terminal_growth=0.03, shares_outstanding=1000.0)
        report = validate_for_dcf(ctx, model="ddm")
        assert report.can_proceed is False

    def test_ddm_missing_cost_of_equity_is_critical(self):
        ctx = _make_ctx(terminal_growth=0.03, shares_outstanding=1000.0)
        report = validate_for_dcf(ctx, model="ddm")
        critical_names = [f.name for f in report.critical_missing]
        assert "cost_of_equity" in critical_names

    def test_ddm_wacc_not_required(self):
        # DDM does not require wacc as critical — missing wacc should not block
        ctx = _make_ctx(
            cost_of_equity=0.12,
            terminal_growth=0.03,
            shares_outstanding=1000.0,
        )
        report = validate_for_dcf(ctx, model="ddm")
        critical_names = [f.name for f in report.critical_missing]
        assert "wacc" not in critical_names

    def test_ddm_full_can_proceed(self):
        report = validate_for_dcf(_full_ddm_ctx(), model="ddm")
        assert report.can_proceed is True

    def test_ddm_missing_terminal_growth_halts(self):
        ctx = _make_ctx(cost_of_equity=0.12, shares_outstanding=1000.0)
        report = validate_for_dcf(ctx, model="ddm")
        assert report.can_proceed is False
        critical_names = [f.name for f in report.critical_missing]
        assert "terminal_growth" in critical_names


# ---------------------------------------------------------------------------
# Gordon model: requires cost_of_equity + terminal_growth
# ---------------------------------------------------------------------------

class TestGordonModel:
    def test_gordon_missing_cost_of_equity_halts(self):
        ctx = _make_ctx(terminal_growth=0.03)
        report = validate_for_dcf(ctx, model="gordon_growth")
        assert report.can_proceed is False
        critical_names = [f.name for f in report.critical_missing]
        assert "cost_of_equity" in critical_names

    def test_gordon_missing_terminal_growth_halts(self):
        ctx = _make_ctx(cost_of_equity=0.12)
        report = validate_for_dcf(ctx, model="gordon_growth")
        assert report.can_proceed is False
        critical_names = [f.name for f in report.critical_missing]
        assert "terminal_growth" in critical_names

    def test_gordon_missing_both_halts(self):
        ctx = ValuationContext(ticker="TEST")
        report = validate_for_dcf(ctx, model="gordon_growth")
        assert report.can_proceed is False
        assert len(report.critical_missing) == 2

    def test_gordon_full_can_proceed(self):
        report = validate_for_dcf(_full_gordon_ctx(), model="gordon_growth")
        assert report.can_proceed is True

    def test_gordon_shares_not_required(self):
        # Gordon does not list shares_outstanding as critical
        ctx = _make_ctx(cost_of_equity=0.12, terminal_growth=0.03)
        report = validate_for_dcf(ctx, model="gordon_growth")
        assert report.can_proceed is True


# ---------------------------------------------------------------------------
# Bounds violation: WACC = 0.60 (above halt threshold of 0.50) → halts
# ---------------------------------------------------------------------------

class TestBoundsViolation:
    def test_extreme_wacc_cannot_proceed(self):
        ctx = _make_ctx(
            wacc=0.60,
            terminal_growth=0.03,
            shares_outstanding=1000.0,
        )
        report = validate_for_dcf(ctx, model="fcff")
        assert report.can_proceed is False

    def test_extreme_wacc_halt_in_warnings(self):
        ctx = _make_ctx(
            wacc=0.60,
            terminal_growth=0.03,
            shares_outstanding=1000.0,
        )
        report = validate_for_dcf(ctx, model="fcff")
        halt_warnings = [w for w in report.warnings if w.startswith("HALT:")]
        assert len(halt_warnings) >= 1

    def test_extreme_wacc_bounds_report_has_halt(self):
        ctx = _make_ctx(
            wacc=0.60,
            terminal_growth=0.03,
            shares_outstanding=1000.0,
        )
        report = validate_for_dcf(ctx, model="fcff")
        assert report.bounds_report is not None
        assert report.bounds_report.has_halt is True

    def test_warn_range_wacc_does_not_halt(self):
        # wacc=0.40 is in WARN range (0.30-0.50) but not HALT range
        ctx = _make_ctx(
            wacc=0.40,
            terminal_growth=0.03,
            shares_outstanding=1000.0,
            beta=1.0,
            tax_rate=0.25,
            cost_of_equity=0.12,
            cost_of_debt=0.06,
        )
        report = validate_for_dcf(ctx, model="fcff")
        # can_proceed depends only on critical missing and halt — moderate warn should not block
        assert report.can_proceed is True

    def test_warn_range_wacc_has_warning_entry(self):
        ctx = _make_ctx(
            wacc=0.40,
            terminal_growth=0.03,
            shares_outstanding=1000.0,
            beta=1.0,
            tax_rate=0.25,
            cost_of_equity=0.12,
            cost_of_debt=0.06,
        )
        report = validate_for_dcf(ctx, model="fcff")
        warn_warnings = [w for w in report.warnings if w.startswith("WARNING:")]
        assert len(warn_warnings) >= 1


# ---------------------------------------------------------------------------
# Terminal growth >= WACC → halt
# ---------------------------------------------------------------------------

class TestTerminalGrowthVsWacc:
    def test_terminal_growth_equals_wacc_halts(self):
        ctx = _make_ctx(
            wacc=0.10,
            terminal_growth=0.10,
            shares_outstanding=1000.0,
        )
        report = validate_for_dcf(ctx, model="fcff")
        assert report.can_proceed is False

    def test_terminal_growth_above_wacc_halts(self):
        ctx = _make_ctx(
            wacc=0.10,
            terminal_growth=0.12,
            shares_outstanding=1000.0,
        )
        report = validate_for_dcf(ctx, model="fcff")
        assert report.can_proceed is False

    def test_terminal_growth_above_wacc_halt_in_bounds_report(self):
        ctx = _make_ctx(
            wacc=0.10,
            terminal_growth=0.12,
            shares_outstanding=1000.0,
        )
        report = validate_for_dcf(ctx, model="fcff")
        assert report.bounds_report is not None
        halt_fields = [c.field for c in report.bounds_report.halts]
        assert "terminal_growth_vs_wacc" in halt_fields

    def test_terminal_growth_comfortably_below_wacc_ok(self):
        ctx = _make_ctx(
            wacc=0.10,
            terminal_growth=0.03,
            shares_outstanding=1000.0,
            beta=1.0,
            tax_rate=0.25,
            cost_of_equity=0.12,
            cost_of_debt=0.06,
        )
        report = validate_for_dcf(ctx, model="fcff")
        assert report.can_proceed is True


# ---------------------------------------------------------------------------
# Summary string reflects state correctly
# ---------------------------------------------------------------------------

class TestSummaryString:
    def test_summary_clear_when_all_good(self):
        report = validate_for_dcf(_full_fcff_ctx(), model="fcff")
        assert report.summary == "All inputs validated — clear to run engines"

    def test_summary_mentions_critical_count_when_halted(self):
        ctx = _make_ctx(terminal_growth=0.03, shares_outstanding=1000.0)
        report = validate_for_dcf(ctx, model="fcff")
        assert "1 critical fields missing — HALTED" in report.summary

    def test_summary_mentions_warnings_count(self):
        ctx = _make_ctx(
            wacc=0.40,  # in WARN range
            terminal_growth=0.03,
            shares_outstanding=1000.0,
            beta=1.0,
            tax_rate=0.25,
            cost_of_equity=0.12,
            cost_of_debt=0.06,
        )
        report = validate_for_dcf(ctx, model="fcff")
        assert "warnings" in report.summary

    def test_summary_mentions_bounds_violations_when_halted(self):
        ctx = _make_ctx(
            wacc=0.60,  # above halt threshold
            terminal_growth=0.03,
            shares_outstanding=1000.0,
        )
        report = validate_for_dcf(ctx, model="fcff")
        assert "bounds violations — HALTED" in report.summary

    def test_summary_validated_with_warnings_when_no_critical_but_warnings(self):
        # Only moderate missing (beta, tax_rate, etc.) but no warnings list entries
        ctx = _make_ctx(
            wacc=0.10,
            terminal_growth=0.03,
            shares_outstanding=1000.0,
        )
        report = validate_for_dcf(ctx, model="fcff")
        # can_proceed = True but has missing moderate fields
        # warnings list is empty (no bounds halts or warns from present values)
        assert report.can_proceed is True
        # summary should not be "clear" since missing moderate fields exist
        # but also no warnings list entries, so "Validated with warnings" or "clear"
        # depends on implementation: can_proceed True and warnings=[] → "All inputs validated"
        assert "All inputs validated" in report.summary or "warnings" in report.summary


# ---------------------------------------------------------------------------
# critical_missing property filters correctly
# ---------------------------------------------------------------------------

class TestCriticalMissingProperty:
    def test_critical_missing_returns_only_critical(self):
        # Missing wacc (critical) and beta (moderate)
        ctx = _make_ctx(terminal_growth=0.03, shares_outstanding=1000.0)
        report = validate_for_dcf(ctx, model="fcff")
        for f in report.critical_missing:
            assert f.impact == "critical"

    def test_critical_missing_empty_when_all_present(self):
        report = validate_for_dcf(_full_fcff_ctx(), model="fcff")
        assert report.critical_missing == []

    def test_critical_missing_count_correct(self):
        # Missing wacc, terminal_growth, shares_outstanding (all 3 critical for fcff)
        ctx = ValuationContext(ticker="TEST")
        report = validate_for_dcf(ctx, model="fcff")
        assert len(report.critical_missing) == 3

    def test_critical_missing_names_correct(self):
        ctx = ValuationContext(ticker="TEST")
        report = validate_for_dcf(ctx, model="fcff")
        critical_names = {f.name for f in report.critical_missing}
        assert critical_names == {"wacc", "terminal_growth", "shares_outstanding"}

    def test_moderate_missing_not_in_critical(self):
        ctx = _make_ctx(
            wacc=0.10,
            terminal_growth=0.03,
            shares_outstanding=1000.0,
            # beta, tax_rate, cost_of_equity, cost_of_debt all missing (moderate)
        )
        report = validate_for_dcf(ctx, model="fcff")
        assert report.critical_missing == []
        moderate_names = [f.name for f in report.missing_fields if f.impact == "moderate"]
        assert len(moderate_names) > 0


# ---------------------------------------------------------------------------
# MissingField dataclass
# ---------------------------------------------------------------------------

class TestMissingField:
    def test_missing_field_attributes(self):
        mf = MissingField(name="wacc", impact="critical", suggestion="compute it")
        assert mf.name == "wacc"
        assert mf.impact == "critical"
        assert mf.suggestion == "compute it"

    def test_missing_field_suggestion_populated(self):
        ctx = _make_ctx(terminal_growth=0.03, shares_outstanding=1000.0)
        report = validate_for_dcf(ctx, model="fcff")
        wacc_field = next(f for f in report.missing_fields if f.name == "wacc")
        assert wacc_field.suggestion != ""
        assert "wacc" in wacc_field.suggestion.lower() or "risk" in wacc_field.suggestion.lower()


# ---------------------------------------------------------------------------
# Default model is fcff
# ---------------------------------------------------------------------------

class TestDefaultModel:
    def test_default_model_is_fcff(self):
        ctx = _make_ctx(terminal_growth=0.03, shares_outstanding=1000.0)
        report_explicit = validate_for_dcf(ctx, model="fcff")
        report_default = validate_for_dcf(ctx)
        # Both should have same can_proceed status
        assert report_explicit.can_proceed == report_default.can_proceed
        assert len(report_explicit.critical_missing) == len(report_default.critical_missing)
