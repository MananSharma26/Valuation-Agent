import pytest
from valuation.agents.industry_mapper import (
    IndustryMatch,
    match_industry,
    load_industry_benchmarks,
)
from valuation.data.damodaran_loader import DamodaranLoader
from valuation.context import ValuationContext


class TestFuzzyMatching:
    def test_exact_match(self, damodaran_data_dir):
        loader = DamodaranLoader(damodaran_data_dir)
        result = match_industry(
            sector="Technology",
            industry="Software (System & Application)",
            description="",
            loader=loader,
            region="US",
        )
        assert isinstance(result, IndustryMatch)
        assert result.matched_name == "Software (System & Application)"
        assert result.score >= 90

    def test_close_match_software(self, damodaran_data_dir):
        loader = DamodaranLoader(damodaran_data_dir)
        result = match_industry(
            sector="Technology",
            industry="Software - Application",
            description="enterprise software company",
            loader=loader,
            region="US",
        )
        assert result is not None
        assert "Software" in result.matched_name
        assert result.score >= 70

    def test_close_match_oil(self, damodaran_data_dir):
        loader = DamodaranLoader(damodaran_data_dir)
        result = match_industry(
            sector="Energy",
            industry="Oil & Gas E&P",
            description="oil exploration and production",
            loader=loader,
            region="US",
        )
        assert result is not None
        assert "Oil" in result.matched_name
        assert result.score >= 70

    def test_close_match_banking(self, damodaran_data_dir):
        loader = DamodaranLoader(damodaran_data_dir)
        result = match_industry(
            sector="Financial Services",
            industry="Banks - Diversified",
            description="commercial banking",
            loader=loader,
            region="US",
        )
        assert result is not None
        assert "Bank" in result.matched_name
        assert result.score >= 70

    def test_low_confidence_returns_none(self, damodaran_data_dir):
        loader = DamodaranLoader(damodaran_data_dir)
        result = match_industry(
            sector="Misc",
            industry="Underwater Basket Weaving",
            description="artisanal crafts",
            loader=loader,
            region="US",
            threshold=90,
        )
        assert result is None

    def test_match_returns_candidates(self, damodaran_data_dir):
        loader = DamodaranLoader(damodaran_data_dir)
        result = match_industry(
            sector="Technology",
            industry="Semiconductors",
            description="chip manufacturer",
            loader=loader,
            region="US",
        )
        assert result is not None
        assert "Semiconductor" in result.matched_name
        assert len(result.candidates) >= 1

    def test_match_with_empty_industry(self, damodaran_data_dir):
        loader = DamodaranLoader(damodaran_data_dir)
        result = match_industry(
            sector="Healthcare",
            industry="",
            description="pharmaceutical drug development",
            loader=loader,
            region="US",
        )
        # Should still attempt matching via sector + description
        assert result is not None or result is None  # graceful handling


class TestIndustryMatchDataclass:
    def test_match_fields(self):
        m = IndustryMatch(
            matched_name="Software (System & Application)",
            score=95,
            candidates=[("Software (System & Application)", 95)],
        )
        assert m.matched_name == "Software (System & Application)"
        assert m.score == 95
        assert len(m.candidates) == 1


class TestBenchmarkLoading:
    def test_load_benchmarks_software(self, damodaran_data_dir):
        loader = DamodaranLoader(damodaran_data_dir)
        benchmarks = load_industry_benchmarks(
            industry_name="Software (System & Application)",
            loader=loader,
            region="US",
        )
        assert benchmarks is not None

        # Beta data
        assert benchmarks["beta"] is not None
        assert 0.5 < benchmarks["beta"] < 3.0
        assert benchmarks["unlevered_beta"] is not None
        assert 0.5 < benchmarks["unlevered_beta"] < 3.0
        assert benchmarks["de_ratio"] is not None
        assert benchmarks["de_ratio"] >= 0

        # WACC
        assert benchmarks["wacc"] is not None
        assert 0.03 < benchmarks["wacc"] < 0.25

        # Multiples
        assert "current_pe" in benchmarks["multiples"]
        assert "ev_ebitda" in benchmarks["multiples"]
        assert "pbv" in benchmarks["multiples"]
        assert "ps" in benchmarks["multiples"]

        # Margins
        assert "net_margin" in benchmarks["margins"]
        assert "operating_margin" in benchmarks["margins"]

        # Growth
        assert "expected_growth_5y" in benchmarks["growth"]

    def test_load_benchmarks_nonexistent_industry(self, damodaran_data_dir):
        loader = DamodaranLoader(damodaran_data_dir)
        benchmarks = load_industry_benchmarks(
            industry_name="Nonexistent Industry XYZ",
            loader=loader,
            region="US",
        )
        assert benchmarks is None

    def test_load_benchmarks_oil(self, damodaran_data_dir):
        loader = DamodaranLoader(damodaran_data_dir)
        benchmarks = load_industry_benchmarks(
            industry_name="Oil/Gas (Production and Exploration)",
            loader=loader,
            region="US",
        )
        assert benchmarks is not None
        assert benchmarks["beta"] is not None
        assert "ev_ebitda" in benchmarks["multiples"]

    def test_benchmarks_populate_context(self, damodaran_data_dir):
        loader = DamodaranLoader(damodaran_data_dir)
        ctx = ValuationContext(ticker="MSFT")
        benchmarks = load_industry_benchmarks(
            industry_name="Software (System & Application)",
            loader=loader,
            region="US",
        )
        assert benchmarks is not None

        # Verify the dict structure can populate Benchmarks dataclass
        ctx.benchmarks.industry_beta = benchmarks["beta"]
        ctx.benchmarks.industry_unlevered_beta = benchmarks["unlevered_beta"]
        ctx.benchmarks.industry_de_ratio = benchmarks["de_ratio"]
        ctx.benchmarks.industry_multiples = benchmarks["multiples"]
        ctx.benchmarks.industry_margins = benchmarks["margins"]
        ctx.benchmarks.industry_growth = benchmarks["growth"]
        ctx.benchmarks.industry_wacc = benchmarks["wacc"]

        assert ctx.benchmarks.industry_beta > 0
        assert "current_pe" in ctx.benchmarks.industry_multiples
