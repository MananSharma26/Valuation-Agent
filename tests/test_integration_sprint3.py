"""Sprint 3 integration: industry mapper + relative valuation + classifier."""

import pytest
import pandas as pd
from valuation.context import ValuationContext
from valuation.data.damodaran_loader import DamodaranLoader
from valuation.agents.industry_mapper import match_industry, load_industry_benchmarks
from valuation.agents.classifier import classify_company
from valuation.engines.relative import relative_valuation


class TestMapAndValue:
    """Test the full flow: map industry -> load benchmarks -> relative valuation."""

    def test_software_company_end_to_end(self, damodaran_data_dir):
        loader = DamodaranLoader(damodaran_data_dir)

        # Step 1: Map industry
        match = match_industry(
            sector="Technology",
            industry="Software - Application",
            description="enterprise software",
            loader=loader,
        )
        assert match is not None
        assert "Software" in match.matched_name

        # Step 2: Load benchmarks
        benchmarks = load_industry_benchmarks(
            industry_name=match.matched_name,
            loader=loader,
        )
        assert benchmarks is not None
        assert "current_pe" in benchmarks["multiples"]

        # Step 3: Relative valuation
        result = relative_valuation(
            eps=5.0,
            ebitda=2000.0,
            book_value_per_share=30.0,
            revenue_per_share=80.0,
            industry_multiples=benchmarks["multiples"],
            debt=5000.0,
            cash=3000.0,
            shares_outstanding=500.0,
            market_price=120.0,
        )
        assert len(result.methods_used) >= 2
        assert result.composite_value is not None
        assert result.composite_value > 0
        assert result.discount_to_composite is not None

    def test_oil_company_end_to_end(self, damodaran_data_dir):
        loader = DamodaranLoader(damodaran_data_dir)
        match = match_industry(
            sector="Energy",
            industry="Oil & Gas E&P",
            description="oil exploration",
            loader=loader,
        )
        assert match is not None
        benchmarks = load_industry_benchmarks(
            industry_name=match.matched_name,
            loader=loader,
        )
        assert benchmarks is not None
        assert benchmarks["beta"] is not None


class TestClassifyAndRoute:
    """Test classifier + verify routing implications."""

    def test_classify_then_populate_context(self, damodaran_data_dir):
        loader = DamodaranLoader(damodaran_data_dir)
        ctx = ValuationContext(ticker="MSFT")
        ctx.company.sector = "Technology"
        ctx.financials.income_statement = pd.DataFrame({
            "Total Revenue": [60000, 52000],
            "Net Income": [8000, 7000],
            "Operating Income": [10000, 9000],
            "Interest Expense": [500, 600],
        })
        ctx.financials.balance_sheet = pd.DataFrame({
            "Total Debt": [10000],
            "Total Stockholders Equity": [50000],
        })
        ctx.financials.key_stats = {
            "market_cap": 300000,
            "price": 350.0,
            "shares_outstanding": 857,
            "industry_yfinance": "Software - Infrastructure",
        }

        # Classify
        classification = classify_company(ctx)
        ctx.company.classification = classification.classification
        assert ctx.company.classification in ("mature", "growth")

        # Map industry
        match = match_industry(
            sector=ctx.company.sector or "",
            industry=ctx.financials.key_stats.get("industry_yfinance", ""),
            description="",
            loader=loader,
        )
        assert match is not None
        ctx.company.damodaran_industry = match.matched_name

        # Load benchmarks
        benchmarks = load_industry_benchmarks(
            industry_name=match.matched_name,
            loader=loader,
        )
        assert benchmarks is not None
        ctx.benchmarks.industry_beta = benchmarks["beta"]
        ctx.benchmarks.industry_multiples = benchmarks["multiples"]
        ctx.benchmarks.industry_wacc = benchmarks["wacc"]

        # Verify context is populated
        summary = ctx.to_summary_dict()
        assert summary["damodaran_industry"] is not None
        assert summary["classification"] is not None

    def test_financial_company_routes_to_ddm(self):
        """Financial classification should route to DDM, not FCFF."""
        ctx = ValuationContext(ticker="JPM")
        ctx.company.sector = "Financial Services"
        ctx.company.sic_code = "6021"
        ctx.financials.income_statement = pd.DataFrame({
            "Total Revenue": [100000, 95000],
            "Net Income": [20000, 18000],
        })
        result = classify_company(ctx)
        assert result.classification == "financial"
        # Implication: pipeline should use DDM, not FCFF (tested elsewhere)


class TestRelativeWithDamodaranData:
    """Test relative valuation using actual Damodaran multiples."""

    def test_valuation_uses_real_multiples(self, damodaran_data_dir):
        loader = DamodaranLoader(damodaran_data_dir)
        benchmarks = load_industry_benchmarks(
            industry_name="Software (System & Application)",
            loader=loader,
        )
        assert benchmarks is not None

        result = relative_valuation(
            eps=5.0,
            ebitda=2000.0,
            book_value_per_share=30.0,
            revenue_per_share=80.0,
            industry_multiples=benchmarks["multiples"],
            debt=5000.0,
            cash=3000.0,
            shares_outstanding=500.0,
            market_price=120.0,
        )
        # With real data, we should get at least 3 methods
        assert len(result.methods_used) >= 3
        # All values should be positive
        for v in [result.pe_value, result.ev_ebitda_value, result.pbv_value, result.ps_value]:
            if v is not None:
                assert v > 0
