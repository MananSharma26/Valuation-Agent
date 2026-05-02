"""Integration tests for the validation layer.

Wires SourcedValue tracking, data_sources utilities, and bounds checking
into a realistic end-to-end valuation flow.  The pre_engine module is
imported lazily with importorskip so the suite degrades gracefully if
that module has not yet been written by the parallel agent.
"""

from __future__ import annotations

import pytest

from valuation.context import ValuationContext
from valuation.validation.sourced import (
    from_compustat,
    from_damodaran,
    from_user,
    from_yahoo,
    computed,
    missing,
    sourced,
)
from valuation.validation.data_sources import (
    count_by_source,
    format_sources_markdown,
    missing_fields,
    proxy_fields,
    sources_table,
)
from valuation.validation.bounds import (
    BoundsReport,
    Severity,
    check_all_inputs,
    check_terminal_vs_wacc,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _healthy_assumptions() -> dict[str, float]:
    """Return a dict of valid DCF assumptions that should pass every check."""
    return {
        "beta": 1.1,
        "wacc": 0.11,
        "terminal_growth": 0.03,
        "revenue_growth": 0.12,
        "operating_margin": 0.18,
        "shares_outstanding": 500.0,
        "reinvestment_rate": 0.40,
        "debt_to_capital": 0.30,
        "cost_of_equity": 0.13,
        "cost_of_debt": 0.07,
    }


def _healthy_context() -> ValuationContext:
    """Return a ValuationContext with a complete, reasonable set of assumptions."""
    ctx = ValuationContext(ticker="TEST")
    ctx.company.sector = "Technology"
    ctx.company.classification = "growth"
    ctx.assumptions.wacc = 0.11
    ctx.assumptions.terminal_growth = 0.03
    ctx.assumptions.beta = 1.1
    ctx.assumptions.cost_of_equity = 0.13
    ctx.assumptions.cost_of_debt = 0.07
    ctx.assumptions.tax_rate = 0.25
    ctx.assumptions.risk_free_rate = 0.04
    ctx.assumptions.erp = 0.055
    ctx.assumptions.growth_rates = [0.15] * 5 + [0.10] * 5
    ctx.assumptions.projection_years = 10
    # shares_outstanding is read from key_stats by pre_engine (not from assumptions)
    ctx.financials.key_stats["shares_outstanding"] = 500.0
    return ctx


# ---------------------------------------------------------------------------
# 1. Full validation pipeline — can_proceed=True, no halts
# ---------------------------------------------------------------------------

class TestFullValidationPipeline:
    """End-to-end: build context -> run pre-engine validate -> run bounds -> no halts."""

    def test_validate_for_dcf_can_proceed(self):
        """validate_for_dcf returns can_proceed=True for a healthy context."""
        pre_engine = pytest.importorskip("valuation.validation.pre_engine")
        ctx = _healthy_context()
        result = pre_engine.validate_for_dcf(ctx)
        assert result.can_proceed is True, (
            f"Expected can_proceed=True but got False. "
            f"Reason: {getattr(result, 'reason', 'unknown')}"
        )

    def test_bounds_no_halts_on_healthy_assumptions(self):
        """check_all_inputs with normal values produces no HALT severities."""
        report = check_all_inputs(_healthy_assumptions())
        assert not report.has_halt, (
            f"Unexpected HALTs: {[c.message for c in report.halts]}"
        )

    def test_bounds_no_warnings_on_healthy_assumptions(self):
        """check_all_inputs with normal values produces no WARN severities."""
        report = check_all_inputs(_healthy_assumptions())
        assert not report.has_warnings, (
            f"Unexpected WARNs: {[c.message for c in report.warnings]}"
        )

    def test_bounds_all_ok_on_healthy_assumptions(self):
        """Every check should be OK for well-formed inputs."""
        report = check_all_inputs(_healthy_assumptions())
        # +1 for the cross-field terminal_growth_vs_wacc check
        expected_checks = len(_healthy_assumptions()) + 1
        assert len(report.checks) == expected_checks
        assert report.ok_count == expected_checks


# ---------------------------------------------------------------------------
# 2. Source tracking through pipeline
# ---------------------------------------------------------------------------

class TestSourceTrackingThroughPipeline:
    """Build a sourced_values dict mixing multiple sources and verify all utilities."""

    def _build_sourced(self) -> dict:
        return {
            "revenue": from_compustat(5_000_000.0, note="FY2024 consolidated"),
            "beta": from_yahoo(1.25, note="5Y monthly"),
            "industry_margin": from_damodaran(0.18, note="Software median"),
            "wacc": from_user(0.11, note="analyst override"),
            "net_income": from_compustat(800_000.0),
            "fcff": computed(450_000.0, note="EBIT*(1-t) - Reinvestment"),
            "goodwill": missing(note="not disclosed"),
        }

    def test_format_sources_markdown_is_valid_markdown(self):
        """Output must include header, separator, and one row per entry."""
        md = format_sources_markdown(self._build_sourced())
        assert isinstance(md, str)
        assert "| Field |" in md
        assert "|-------|" in md
        lines = md.strip().split("\n")
        # header + separator + 7 data rows
        assert len(lines) == 9

    def test_format_sources_markdown_contains_all_source_types(self):
        md = format_sources_markdown(self._build_sourced())
        assert "compustat" in md
        assert "yahoo_finance" in md
        assert "damodaran_industry" in md
        assert "user_input" in md
        assert "computed" in md
        assert "MISSING" in md  # goodwill

    def test_count_by_source_correct_totals(self):
        counts = count_by_source(self._build_sourced())
        assert counts.get("compustat", 0) == 2
        assert counts.get("yahoo_finance", 0) == 1
        assert counts.get("damodaran_industry", 0) == 1
        assert counts.get("user_input", 0) == 1
        assert counts.get("computed", 0) == 1
        assert counts.get("missing", 0) == 1

    def test_count_by_source_total_matches_dict_length(self):
        sv = self._build_sourced()
        counts = count_by_source(sv)
        assert sum(counts.values()) == len(sv)

    def test_proxy_fields_identifies_damodaran(self):
        pf = proxy_fields(self._build_sourced())
        assert "industry_margin" in pf

    def test_proxy_fields_excludes_hard_data(self):
        pf = proxy_fields(self._build_sourced())
        assert "revenue" not in pf
        assert "beta" not in pf
        assert "wacc" not in pf

    def test_missing_fields_identifies_goodwill(self):
        mf = missing_fields(self._build_sourced())
        assert "goodwill" in mf

    def test_missing_fields_excludes_available(self):
        mf = missing_fields(self._build_sourced())
        assert "revenue" not in mf
        assert "wacc" not in mf


# ---------------------------------------------------------------------------
# 3. Bounds catch bad WACC
# ---------------------------------------------------------------------------

class TestBoundsCatchBadWacc:
    """WACC=0.55 is above the halt threshold of 0.50 — must halt."""

    def test_wacc_055_halts_bounds_check(self):
        report = check_all_inputs({"wacc": 0.55})
        assert report.has_halt
        halt_fields = [c.field for c in report.halts]
        assert "wacc" in halt_fields

    def test_wacc_055_halt_message_mentions_threshold(self):
        report = check_all_inputs({"wacc": 0.55})
        wacc_halt = next(c for c in report.halts if c.field == "wacc")
        assert "0.55" in wacc_halt.message or "above" in wacc_halt.message.lower()

    def test_validate_for_dcf_halts_on_bad_wacc(self):
        """Pre-engine validate_for_dcf should halt when WACC is 0.55."""
        pre_engine = pytest.importorskip("valuation.validation.pre_engine")
        ctx = _healthy_context()
        ctx.assumptions.wacc = 0.55
        result = pre_engine.validate_for_dcf(ctx)
        assert result.can_proceed is False


# ---------------------------------------------------------------------------
# 4. Missing critical field halts
# ---------------------------------------------------------------------------

class TestMissingCriticalFieldHalts:
    """Context with no WACC set must not proceed for FCFF valuation."""

    def test_validate_for_dcf_halts_when_wacc_missing(self):
        pre_engine = pytest.importorskip("valuation.validation.pre_engine")
        ctx = _healthy_context()
        ctx.assumptions.wacc = None  # explicitly unset
        result = pre_engine.validate_for_dcf(ctx)
        assert result.can_proceed is False

    def test_validate_for_dcf_result_has_suggestion_when_wacc_missing(self):
        pre_engine = pytest.importorskip("valuation.validation.pre_engine")
        ctx = _healthy_context()
        ctx.assumptions.wacc = None
        result = pre_engine.validate_for_dcf(ctx)
        # The result should carry some diagnostic: a reason, message, or suggestions list
        has_diagnostic = (
            getattr(result, "reason", None)
            or getattr(result, "message", None)
            or getattr(result, "suggestions", None)
            or getattr(result, "missing_fields", None)
            or getattr(result, "halts", None)
        )
        assert has_diagnostic, (
            "Expected validate_for_dcf result to carry a diagnostic when WACC is missing"
        )

    def test_bounds_none_wacc_warns_not_halts(self):
        """At the bounds layer, a None WACC produces a WARN (handled upstream)."""
        report = check_all_inputs({"wacc": None})
        assert report.has_warnings
        assert not report.has_halt


# ---------------------------------------------------------------------------
# 5. Terminal growth vs WACC cross-check
# ---------------------------------------------------------------------------

class TestTerminalGrowthVsWaccCrossCheck:
    """terminal_growth=0.05 with WACC=0.04 must halt (growth >= wacc)."""

    def test_growth_above_wacc_halts(self):
        report = check_all_inputs({"terminal_growth": 0.05, "wacc": 0.04})
        assert report.has_halt
        halt_fields = [c.field for c in report.halts]
        assert "terminal_growth_vs_wacc" in halt_fields

    def test_growth_equal_to_wacc_halts(self):
        report = check_all_inputs({"terminal_growth": 0.04, "wacc": 0.04})
        assert report.has_halt
        halt_fields = [c.field for c in report.halts]
        assert "terminal_growth_vs_wacc" in halt_fields

    def test_halt_message_mentions_perpetuity(self):
        result = check_terminal_vs_wacc(0.05, 0.04)
        assert result.severity == Severity.HALT
        assert "perpetuity" in result.message.lower() or ">=" in result.message

    def test_validate_for_dcf_halts_on_terminal_growth_exceeds_wacc(self):
        pre_engine = pytest.importorskip("valuation.validation.pre_engine")
        ctx = _healthy_context()
        ctx.assumptions.terminal_growth = 0.05
        ctx.assumptions.wacc = 0.04
        result = pre_engine.validate_for_dcf(ctx)
        assert result.can_proceed is False

    def test_growth_well_below_wacc_ok(self):
        report = check_all_inputs({"terminal_growth": 0.03, "wacc": 0.11})
        tg_check = next(c for c in report.checks if c.field == "terminal_growth_vs_wacc")
        assert tg_check.severity == Severity.OK


# ---------------------------------------------------------------------------
# 6. Healthy context passes all checks
# ---------------------------------------------------------------------------

class TestHealthyContextPassesAll:
    """A fully-populated context with reasonable values should pass everything."""

    def test_healthy_bounds_no_halt(self):
        report = check_all_inputs(_healthy_assumptions())
        assert not report.has_halt

    def test_healthy_bounds_no_warnings(self):
        report = check_all_inputs(_healthy_assumptions())
        assert not report.has_warnings

    def test_healthy_bounds_ok_count(self):
        inputs = _healthy_assumptions()
        report = check_all_inputs(inputs)
        # All individual checks + cross-field check should be OK
        assert report.ok_count == len(inputs) + 1

    def test_healthy_terminal_vs_wacc_ok(self):
        result = check_terminal_vs_wacc(
            terminal_growth=_healthy_assumptions()["terminal_growth"],
            wacc=_healthy_assumptions()["wacc"],
        )
        assert result.severity == Severity.OK

    def test_healthy_context_validate_for_dcf(self):
        pre_engine = pytest.importorskip("valuation.validation.pre_engine")
        ctx = _healthy_context()
        result = pre_engine.validate_for_dcf(ctx)
        assert result.can_proceed is True


# ---------------------------------------------------------------------------
# 7. Data source transparency report
# ---------------------------------------------------------------------------

class TestDataSourceTransparencyReport:
    """Build a sourced_values dict representing a real valuation's inputs
    and verify the markdown table has the right number of rows and contains
    all expected source types.
    """

    def _valuation_inputs(self) -> dict:
        """Realistic mix of inputs for an Indian software company DCF."""
        return {
            # Hard financial data from Compustat
            "revenue": from_compustat(120_000.0, note="Compustat gvkey=123456 FY2024"),
            "ebit": from_compustat(22_000.0, note="Operating income FY2024"),
            "net_income": from_compustat(18_000.0),
            "total_debt": from_compustat(15_000.0),
            "cash": from_compustat(8_000.0),
            # Market data from Yahoo Finance
            "beta": from_yahoo(1.35, note="5Y monthly vs NSE500"),
            "market_price": from_yahoo(450.0, note="closing price"),
            "shares_outstanding": from_yahoo(500.0),
            # Industry proxies from Damodaran
            "industry_ebit_margin": from_damodaran(0.19, note="Software India"),
            "industry_beta": from_damodaran(1.20, note="Software (System & Application)"),
            "industry_wacc": from_damodaran(0.12, note="India Software sector median"),
            # User overrides
            "wacc": from_user(0.13, note="analyst adjusted for country risk"),
            "terminal_growth": from_user(0.05, note="India nominal GDP growth"),
            # Computed outputs
            "levered_beta": computed(1.42, note="Hamada unlevered * (1 + D/E*(1-t))"),
            "cost_of_equity": computed(0.145, note="CAPM: rf + beta*ERP + CRP"),
            # Missing
            "capex_maintenance": missing(note="not separately disclosed"),
        }

    def test_table_has_correct_row_count(self):
        sv = self._valuation_inputs()
        rows = sources_table(sv)
        assert len(rows) == len(sv)  # 16 fields

    def test_markdown_has_correct_line_count(self):
        sv = self._valuation_inputs()
        md = format_sources_markdown(sv)
        lines = md.strip().split("\n")
        # header + separator + one per field
        assert len(lines) == 2 + len(sv)

    def test_markdown_contains_compustat_source(self):
        md = format_sources_markdown(self._valuation_inputs())
        assert "compustat" in md

    def test_markdown_contains_yahoo_finance_source(self):
        md = format_sources_markdown(self._valuation_inputs())
        assert "yahoo_finance" in md

    def test_markdown_contains_damodaran_industry_source(self):
        md = format_sources_markdown(self._valuation_inputs())
        assert "damodaran_industry" in md

    def test_markdown_contains_user_input_source(self):
        md = format_sources_markdown(self._valuation_inputs())
        assert "user_input" in md

    def test_markdown_contains_computed_source(self):
        md = format_sources_markdown(self._valuation_inputs())
        assert "computed" in md

    def test_markdown_shows_missing_field(self):
        md = format_sources_markdown(self._valuation_inputs())
        assert "MISSING" in md

    def test_count_by_source_five_distinct_sources(self):
        counts = count_by_source(self._valuation_inputs())
        assert len(counts) == 6  # compustat, yahoo_finance, damodaran_industry,
        #                           user_input, computed, missing

    def test_count_by_source_compustat_count(self):
        counts = count_by_source(self._valuation_inputs())
        assert counts["compustat"] == 5

    def test_count_by_source_damodaran_count(self):
        counts = count_by_source(self._valuation_inputs())
        assert counts["damodaran_industry"] == 3

    def test_proxy_fields_are_damodaran_and_assumed(self):
        pf = proxy_fields(self._valuation_inputs())
        assert "industry_ebit_margin" in pf
        assert "industry_beta" in pf
        assert "industry_wacc" in pf

    def test_proxy_fields_does_not_include_hard_data(self):
        pf = proxy_fields(self._valuation_inputs())
        assert "revenue" not in pf
        assert "wacc" not in pf  # user_input is not a proxy

    def test_missing_fields_only_capex_maintenance(self):
        mf = missing_fields(self._valuation_inputs())
        assert "capex_maintenance" in mf
        assert len(mf) == 1

    def test_sources_table_all_rows_have_required_keys(self):
        rows = sources_table(self._valuation_inputs())
        required_keys = {"field", "value", "source", "confidence", "note"}
        for row in rows:
            assert set(row.keys()) == required_keys, (
                f"Row for '{row.get('field')}' is missing keys"
            )

    def test_sources_table_field_names_preserved(self):
        sv = self._valuation_inputs()
        rows = sources_table(sv)
        row_fields = {r["field"] for r in rows}
        assert row_fields == set(sv.keys())
