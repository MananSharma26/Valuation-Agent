"""Tests for valuation.reports.generator.generate_report.

Coverage:
- Report generated for a fully populated context
- Report contains expected ## section headers
- Report includes company name and ticker
- Report handles missing data gracefully (no crash when DCF not run)
- Report output is valid markdown (non-empty string)
- Sensitivity section rendered when data present
- Confidence flags rendered when present
- Overrides rendered when present
"""

from __future__ import annotations

import pytest

from valuation.context import ValuationContext
from valuation.reports.generator import generate_report, _md_table


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_minimal_ctx(ticker: str = "AAPL") -> ValuationContext:
    """Context with only company info populated."""
    ctx = ValuationContext(ticker=ticker)
    ctx.company.name = "Apple Inc."
    ctx.company.sector = "Technology"
    ctx.company.classification = "mature"
    ctx.company.region = "US"
    return ctx


def _make_full_ctx() -> ValuationContext:
    """Context with all major sections populated."""
    ctx = ValuationContext("MSFT")
    ctx.company.name = "Microsoft Corporation"
    ctx.company.sector = "Technology"
    ctx.company.sic_code = "7372"
    ctx.company.classification = "mature"
    ctx.company.damodaran_industry = "Software (System & Application)"
    ctx.company.region = "US"

    # Financials key stats
    ctx.financials.key_stats = {
        "price": 420.50,
        "shares_outstanding": 7_430_000_000,
        "market_cap": 3_123_000_000_000,
        "beta": 0.90,
        "book_value_per_share": 28.00,
    }

    # Assumptions
    ctx.assumptions.risk_free_rate = 0.0425
    ctx.assumptions.erp = 0.055
    ctx.assumptions.country_risk_premium = 0.0
    ctx.assumptions.beta = 0.90
    ctx.assumptions.cost_of_equity = 0.0920
    ctx.assumptions.cost_of_debt = 0.0350
    ctx.assumptions.wacc = 0.0850
    ctx.assumptions.tax_rate = 0.21
    ctx.assumptions.terminal_growth = 0.03
    ctx.assumptions.projection_years = 10
    ctx.assumptions.growth_rates = [0.15, 0.14, 0.13, 0.12, 0.11, 0.10, 0.09, 0.08, 0.07, 0.06]

    # DCF FCFF output
    ctx.outputs.dcf_fcff = {
        "enterprise_value": 3_000_000_000_000.0,
        "equity_value": 2_900_000_000_000.0,
        "equity_value_per_share": 390.31,
        "pv_high_growth": 800_000_000_000.0,
        "pv_terminal": 2_200_000_000_000.0,
        "terminal_value": 4_100_000_000_000.0,
        "yearly_fcff": [85e9, 90e9, 95e9, 100e9, 105e9],
        "yearly_pv": [78e9, 76e9, 74e9, 72e9, 70e9],
        "yearly_ebit_at": [100e9, 108e9, 115e9, 122e9, 130e9],
    }

    # Relative valuation output
    ctx.outputs.relative = {
        "pe_value": 380.00,
        "ev_ebitda_value": 395.50,
        "pbv_value": 350.00,
        "ps_value": 410.00,
        "composite_value": 387.75,
        "discount_to_composite": -0.082,
        "market_price": 420.50,
        "methods_used": ["PE", "EV/EBITDA", "PBV", "PS"],
    }

    # Sensitivity output
    ctx.outputs.sensitivity = {
        "base_case": 390.31,
        "bear_case": 310.00,
        "bull_case": 480.00,
    }

    # Confidence scores
    ctx.confidence.data_completeness = 0.875
    ctx.confidence.model_agreement = 0.78
    ctx.confidence.assumption_sensitivity = 0.62
    ctx.confidence.industry_coverage = 0.92
    ctx.confidence.composite = 0.77
    ctx.confidence.flags = []

    return ctx


def _make_ddm_ctx() -> ValuationContext:
    """Context with DDM output stored in dcf_fcfe slot."""
    ctx = ValuationContext("JPM")
    ctx.company.name = "JPMorgan Chase"
    ctx.company.classification = "financial"
    ctx.company.region = "US"

    ctx.assumptions.cost_of_equity = 0.10
    ctx.assumptions.terminal_growth = 0.03

    ctx.outputs.dcf_fcfe = {
        "value_per_share": 185.20,
        "pv_dividends": 45.80,
        "pv_terminal": 139.40,
        "terminal_price": 220.00,
        "yearly_eps": [12.0, 13.0, 14.0],
        "yearly_dps": [4.80, 5.20, 5.60],
        "yearly_pv": [4.36, 4.30, 4.20],
    }

    return ctx


# ---------------------------------------------------------------------------
# Basic output validity
# ---------------------------------------------------------------------------


class TestReportBasicValidity:
    def test_returns_string(self):
        ctx = _make_minimal_ctx()
        result = generate_report(ctx)
        assert isinstance(result, str)

    def test_non_empty(self):
        ctx = _make_minimal_ctx()
        result = generate_report(ctx)
        assert len(result.strip()) > 0

    def test_ends_with_newline(self):
        ctx = _make_minimal_ctx()
        result = generate_report(ctx)
        assert result.endswith("\n")

    def test_full_context_returns_string(self):
        ctx = _make_full_ctx()
        result = generate_report(ctx)
        assert isinstance(result, str)
        assert len(result.strip()) > 100  # substantive output


# ---------------------------------------------------------------------------
# Company name and ticker
# ---------------------------------------------------------------------------


class TestCompanyIdentifiers:
    def test_ticker_in_report(self):
        ctx = _make_minimal_ctx("AAPL")
        report = generate_report(ctx)
        assert "AAPL" in report

    def test_company_name_in_report(self):
        ctx = _make_minimal_ctx("AAPL")
        report = generate_report(ctx)
        assert "Apple Inc." in report

    def test_ticker_only_when_name_missing(self):
        ctx = ValuationContext("XYZ")
        # No name set — ticker should still appear
        report = generate_report(ctx)
        assert "XYZ" in report

    def test_different_tickers(self):
        for ticker in ("TSLA", "GOOGL", "TCS.NS"):
            ctx = ValuationContext(ticker)
            ctx.company.name = f"Company {ticker}"
            report = generate_report(ctx)
            assert ticker in report


# ---------------------------------------------------------------------------
# Section headers
# ---------------------------------------------------------------------------


EXPECTED_HEADERS = [
    "## Executive Summary",
    "## Company Profile",
    "## Key Assumptions",
    "## DCF Valuation",
    "## Relative Valuation",
    "## Sensitivity Analysis",
    "## Confidence Assessment",
]


class TestSectionHeaders:
    def test_all_headers_present_in_full_report(self):
        ctx = _make_full_ctx()
        report = generate_report(ctx)
        for header in EXPECTED_HEADERS:
            assert header in report, f"Missing section: {header}"

    def test_cross_validation_header_present(self):
        ctx = _make_full_ctx()
        report = generate_report(ctx)
        assert "## Cross-Validation" in report

    def test_report_title_present(self):
        ctx = _make_full_ctx()
        report = generate_report(ctx)
        assert "# Valuation Report:" in report


# ---------------------------------------------------------------------------
# Missing data — graceful handling
# ---------------------------------------------------------------------------


class TestMissingDataGraceful:
    def test_no_crash_without_dcf(self):
        """Report should not crash when DCF has not been run."""
        ctx = _make_minimal_ctx()
        # outputs are all None by default
        report = generate_report(ctx)
        assert isinstance(report, str)
        assert "AAPL" in report

    def test_no_crash_without_relative(self):
        ctx = _make_minimal_ctx()
        ctx.outputs.dcf_fcff = {
            "enterprise_value": 1e12,
            "equity_value": 9e11,
            "equity_value_per_share": 150.0,
            "pv_high_growth": 3e11,
            "pv_terminal": 6e11,
            "terminal_value": 1.2e12,
            "yearly_fcff": [],
            "yearly_pv": [],
            "yearly_ebit_at": [],
        }
        report = generate_report(ctx)
        assert isinstance(report, str)
        # DCF section should be present; relative section absent
        assert "## DCF Valuation" in report
        assert "## Relative Valuation" not in report

    def test_no_crash_without_confidence_scores(self):
        ctx = _make_minimal_ctx()
        # confidence scores default to None
        report = generate_report(ctx)
        assert isinstance(report, str)

    def test_no_crash_empty_context(self):
        ctx = ValuationContext("EMPTY")
        report = generate_report(ctx)
        assert isinstance(report, str)
        assert "EMPTY" in report

    def test_no_crash_without_assumptions(self):
        ctx = ValuationContext("BARE")
        ctx.company.name = "Bare Co"
        # All assumptions remain at defaults (None)
        report = generate_report(ctx)
        assert isinstance(report, str)
        assert "BARE" in report

    def test_dcf_section_absent_when_not_run(self):
        ctx = _make_minimal_ctx()
        report = generate_report(ctx)
        assert "## DCF Valuation" not in report

    def test_relative_section_absent_when_not_run(self):
        ctx = _make_minimal_ctx()
        report = generate_report(ctx)
        assert "## Relative Valuation" not in report


# ---------------------------------------------------------------------------
# DCF section content
# ---------------------------------------------------------------------------


class TestDCFSection:
    def test_equity_value_per_share_in_report(self):
        ctx = _make_full_ctx()
        report = generate_report(ctx)
        assert "390.31" in report

    def test_enterprise_value_in_report(self):
        ctx = _make_full_ctx()
        report = generate_report(ctx)
        # Large number formatted with commas
        assert "Enterprise Value" in report

    def test_yearly_projections_table_present(self):
        ctx = _make_full_ctx()
        report = generate_report(ctx)
        assert "Year-by-Year Projections (FCFF)" in report

    def test_ddm_section_rendered(self):
        ctx = _make_ddm_ctx()
        report = generate_report(ctx)
        assert "## DCF Valuation" in report
        assert "DDM" in report
        assert "185.20" in report

    def test_ddm_yearly_projections_rendered(self):
        ctx = _make_ddm_ctx()
        report = generate_report(ctx)
        assert "Year-by-Year Projections (DDM)" in report


# ---------------------------------------------------------------------------
# Relative valuation section content
# ---------------------------------------------------------------------------


class TestRelativeSection:
    def test_composite_value_in_report(self):
        ctx = _make_full_ctx()
        report = generate_report(ctx)
        assert "387.75" in report

    def test_methods_used_listed(self):
        ctx = _make_full_ctx()
        report = generate_report(ctx)
        assert "PE" in report
        assert "EV/EBITDA" in report

    def test_discount_premium_present(self):
        ctx = _make_full_ctx()
        report = generate_report(ctx)
        assert "Discount / Premium" in report


# ---------------------------------------------------------------------------
# Sensitivity section
# ---------------------------------------------------------------------------


class TestSensitivitySection:
    def test_sensitivity_section_present_when_data_exists(self):
        ctx = _make_full_ctx()
        report = generate_report(ctx)
        assert "## Sensitivity Analysis" in report

    def test_sensitivity_values_in_report(self):
        ctx = _make_full_ctx()
        report = generate_report(ctx)
        assert "310.00" in report  # bear_case
        assert "480.00" in report  # bull_case

    def test_sensitivity_section_absent_when_no_data(self):
        ctx = _make_minimal_ctx()
        report = generate_report(ctx)
        assert "## Sensitivity Analysis" not in report


# ---------------------------------------------------------------------------
# Confidence section
# ---------------------------------------------------------------------------


class TestConfidenceSection:
    def test_confidence_section_present_with_scores(self):
        ctx = _make_full_ctx()
        report = generate_report(ctx)
        assert "## Confidence Assessment" in report

    def test_composite_score_label_in_report(self):
        ctx = _make_full_ctx()
        report = generate_report(ctx)
        # composite=0.77 => HIGH label
        assert "HIGH" in report

    def test_flags_rendered_when_present(self):
        ctx = _make_minimal_ctx()
        ctx.confidence.composite = 0.30
        ctx.confidence.data_completeness = 0.40
        ctx.confidence.flags = ["Low data completeness: key fields missing."]
        report = generate_report(ctx)
        assert "Low data completeness" in report

    def test_confidence_section_absent_without_scores(self):
        ctx = ValuationContext("NOCONF")
        # All confidence fields default None, no flags
        report = generate_report(ctx)
        assert "## Confidence Assessment" not in report


# ---------------------------------------------------------------------------
# Key Assumptions section
# ---------------------------------------------------------------------------


class TestAssumptionsSection:
    def test_wacc_in_report(self):
        ctx = _make_full_ctx()
        report = generate_report(ctx)
        assert "WACC" in report
        assert "8.5%" in report

    def test_terminal_growth_in_report(self):
        ctx = _make_full_ctx()
        report = generate_report(ctx)
        assert "Terminal Growth" in report
        assert "3.0%" in report

    def test_growth_schedule_rendered(self):
        ctx = _make_full_ctx()
        report = generate_report(ctx)
        assert "Growth Rate Schedule" in report

    def test_overrides_table_rendered_when_present(self):
        ctx = _make_full_ctx()
        ctx.assumptions.set_override("beta", 1.10, reason="Adjusted for leverage")
        report = generate_report(ctx)
        assert "Analyst Overrides" in report
        assert "Adjusted for leverage" in report


# ---------------------------------------------------------------------------
# Executive Summary section
# ---------------------------------------------------------------------------


class TestExecutiveSummary:
    def test_classification_in_summary(self):
        ctx = _make_full_ctx()
        report = generate_report(ctx)
        assert "mature" in report

    def test_value_range_in_summary(self):
        ctx = _make_full_ctx()
        report = generate_report(ctx)
        # Both dcf and relative values present
        assert "Intrinsic Value Range" in report

    def test_market_price_shown_when_available(self):
        ctx = _make_full_ctx()
        report = generate_report(ctx)
        assert "420.50" in report

    def test_upside_downside_shown_when_price_available(self):
        ctx = _make_full_ctx()
        report = generate_report(ctx)
        # Market price 420.50 vs intrinsic ~390 => downside
        assert "downside" in report.lower() or "upside" in report.lower()


# ---------------------------------------------------------------------------
# _md_table helper unit tests
# ---------------------------------------------------------------------------


class TestMdTableHelper:
    def test_basic_table(self):
        result = _md_table(["Col A", "Col B"], [("x", "1"), ("y", "2")])
        assert "| Col A | Col B |" in result
        assert "| x | 1 |" in result

    def test_separator_row(self):
        result = _md_table(["H1", "H2"], [])
        lines = result.splitlines()
        assert lines[1].startswith("|---")

    def test_empty_rows(self):
        result = _md_table(["H"], [])
        assert isinstance(result, str)
        assert "H" in result
