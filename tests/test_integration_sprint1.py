"""Sprint 1 integration: load Damodaran data, fetch a company, normalize, populate context."""

import pytest
from valuation.context import ValuationContext
from valuation.data.damodaran_loader import DamodaranLoader


class TestDamodaranDataIntegration:
    def test_load_and_lookup_software_beta(self, damodaran_data_dir):
        loader = DamodaranLoader(damodaran_data_dir)
        row = loader.lookup("betas", "Software (System & Application)")
        assert row is not None
        # Column may have trailing space
        beta_col = next(c for c in row.index if c.strip().startswith("Beta") and "unlevered" not in c.lower() and ":" not in c)
        beta = float(row[beta_col])
        assert 0.5 < beta < 3.0, f"Software beta {beta} out of reasonable range"

    def test_load_and_lookup_wacc_range(self, damodaran_data_dir):
        loader = DamodaranLoader(damodaran_data_dir)
        row = loader.lookup("wacc", "Software (System & Application)")
        assert row is not None
        wacc = float(row["Cost of Capital"])
        assert 0.03 < wacc < 0.25, f"WACC {wacc} out of range"

    def test_context_round_trip(self):
        ctx = ValuationContext(ticker="AAPL")
        ctx.company.name = "Apple Inc."
        ctx.company.classification = "mature"
        ctx.assumptions.wacc = 0.09
        ctx.assumptions.set_override("wacc", 0.10, reason="Higher risk")
        summary = ctx.to_summary_dict()
        assert summary["ticker"] == "AAPL"
        assert summary["wacc"] == 0.10
        assert "wacc" in summary["overrides"]


class TestNetworkIntegration:
    @pytest.mark.network
    def test_fetch_and_normalize(self):
        from valuation.data.api_client import fetch_financials
        from valuation.data.normalizer import normalize

        data = fetch_financials("AAPL")
        assert data is not None
        ctx = normalize(data)
        assert ctx.company.ticker == "AAPL"
        assert ctx.company.name is not None
        assert ctx.financials.income_statement is not None
        assert ctx.financials.key_stats["market_cap"] > 0
