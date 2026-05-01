import pandas as pd
import pytest
from valuation.data.damodaran_loader import DamodaranLoader


class TestDamodaranLoaderInit:
    def test_loader_finds_data_dir(self, damodaran_data_dir):
        loader = DamodaranLoader(damodaran_data_dir)
        assert loader.data_dir.exists()

    def test_loader_discovers_categories(self, damodaran_data_dir):
        loader = DamodaranLoader(damodaran_data_dir)
        expected = {
            "risk_discount_rate",
            "multiples",
            "growth_rate_estimation",
            "cash_flow_estimation",
            "capital_structure",
            "dividend_policy",
            "investment_returns",
            "corporate_governance",
            "option_pricing",
        }
        assert expected.issubset(loader.categories)


class TestLoadIndustryFile:
    def test_load_betas_us(self, damodaran_data_dir):
        loader = DamodaranLoader(damodaran_data_dir)
        df = loader.load("betas", region="US")
        assert isinstance(df, pd.DataFrame)
        assert len(df) >= 90
        assert "Industry Name" in df.columns

    def test_load_betas_india(self, damodaran_data_dir):
        loader = DamodaranLoader(damodaran_data_dir)
        df = loader.load("betas", region="India")
        assert isinstance(df, pd.DataFrame)
        assert len(df) >= 90

    def test_load_wacc_us(self, damodaran_data_dir):
        loader = DamodaranLoader(damodaran_data_dir)
        df = loader.load("wacc", region="US")
        assert "Cost of Capital" in df.columns
        assert len(df) >= 90

    def test_load_pedata_us(self, damodaran_data_dir):
        loader = DamodaranLoader(damodaran_data_dir)
        df = loader.load("pedata", region="US")
        assert "Current PE" in df.columns

    def test_load_margin_global(self, damodaran_data_dir):
        loader = DamodaranLoader(damodaran_data_dir)
        df = loader.load("margin", region="Global")
        assert "Net Margin" in df.columns

    def test_load_nonexistent_raises(self, damodaran_data_dir):
        loader = DamodaranLoader(damodaran_data_dir)
        with pytest.raises(FileNotFoundError):
            loader.load("nonexistent_file", region="US")


class TestIndustryLookup:
    def test_lookup_beta_for_industry(self, damodaran_data_dir):
        loader = DamodaranLoader(damodaran_data_dir)
        row = loader.lookup("betas", "Software (System & Application)", region="US")
        assert row is not None

    def test_lookup_wacc_for_industry(self, damodaran_data_dir):
        loader = DamodaranLoader(damodaran_data_dir)
        row = loader.lookup("wacc", "Oil/Gas (Production and Exploration)", region="US")
        assert row is not None

    def test_lookup_nonexistent_industry(self, damodaran_data_dir):
        loader = DamodaranLoader(damodaran_data_dir)
        row = loader.lookup("betas", "Nonexistent Industry XYZ", region="US")
        assert row is None


class TestSpecialFiles:
    def test_load_histretsp(self, damodaran_data_dir):
        loader = DamodaranLoader(damodaran_data_dir)
        df = loader.load("histretSP", region="US")
        assert isinstance(df, pd.DataFrame)
        assert len(df) >= 50

    def test_load_histimpl(self, damodaran_data_dir):
        loader = DamodaranLoader(damodaran_data_dir)
        df = loader.load("histimpl", region="US")
        assert isinstance(df, pd.DataFrame)

    def test_load_ctryprem(self, damodaran_data_dir):
        loader = DamodaranLoader(damodaran_data_dir)
        df = loader.load("ctryprem", region="Global")
        assert isinstance(df, pd.DataFrame)
        assert len(df) >= 100

    def test_load_countrytaxrates(self, damodaran_data_dir):
        loader = DamodaranLoader(damodaran_data_dir)
        df = loader.load("countrytaxrates", region="Global")
        assert isinstance(df, pd.DataFrame)
        assert len(df) >= 200

    def test_load_ratings(self, damodaran_data_dir):
        loader = DamodaranLoader(damodaran_data_dir)
        df = loader.load("ratings", region="US")
        assert isinstance(df, pd.DataFrame)

    def test_load_mktcaprisk(self, damodaran_data_dir):
        loader = DamodaranLoader(damodaran_data_dir)
        df = loader.load("mktcaprisk", region="US")
        assert isinstance(df, pd.DataFrame)
        assert len(df) >= 10


class TestListIndustries:
    def test_list_all_industries(self, damodaran_data_dir):
        loader = DamodaranLoader(damodaran_data_dir)
        industries = loader.list_industries()
        assert len(industries) >= 90
        assert "Advertising" in industries


class TestAllFilesLoad:
    def test_all_244_files_parseable(self, damodaran_data_dir):
        """Acceptance criterion: All 244 Excel files parse without error."""
        loader = DamodaranLoader(damodaran_data_dir)
        errors = []
        count = 0
        for category_dir in damodaran_data_dir.iterdir():
            if not category_dir.is_dir():
                continue
            for f in category_dir.iterdir():
                if f.suffix in (".xls", ".xlsx"):
                    try:
                        loader.load_file(f)
                        count += 1
                    except Exception as e:
                        errors.append(f"{f.name}: {e}")
        assert count >= 240, f"Only loaded {count} files"
        assert errors == [], f"Failed files: {errors}"
