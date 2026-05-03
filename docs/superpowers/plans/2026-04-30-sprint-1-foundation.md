# Sprint 1: Foundation — Data Layer & Context Contract

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the data foundation — load all 244 Damodaran Excel files into queryable DataFrames, fetch company financials via yfinance, normalize them into a shared data contract, and wire up the project scaffolding.

**Architecture:** Three independent Python modules (`damodaran_loader`, `api_client`, `normalizer`) feed into a shared `ValuationContext` dataclass. All modules are pure deterministic Python with no LLM dependencies. The Damodaran data lives at `../2. Damodaran_Data/` (sibling directory) and is loaded by relative path.

**Tech Stack:** Python 3.12, pandas, xlrd (for .xls), openpyxl (for .xlsx), yfinance, pytest, dataclasses

**Damodaran data location:** `/mnt/c/Users/Manan Sharma/Desktop/Coding projects/Valuation/2. Damodaran_Data/` (sibling to project root)

**Example spreadsheets location:** `/mnt/c/Users/Manan Sharma/Desktop/Coding projects/Valuation/3. Valuation examples/`

---

## File Structure

| File | Responsibility |
|------|---------------|
| `pyproject.toml` | Project metadata, dependencies, pytest config |
| `src/valuation/__init__.py` | Package root |
| `src/valuation/context.py` | `ValuationContext` dataclass — shared data contract |
| `src/valuation/data/__init__.py` | Data subpackage |
| `src/valuation/data/damodaran_loader.py` | Parse all Damodaran Excel files into DataFrames by category/region |
| `src/valuation/data/api_client.py` | Fetch company financials from yfinance |
| `src/valuation/data/normalizer.py` | Standardize yfinance output into ValuationContext.financials |
| `tests/conftest.py` | Shared fixtures (paths to data dirs, sample tickers) |
| `tests/test_damodaran_loader.py` | Tests for Damodaran Excel parsing |
| `tests/test_api_client.py` | Tests for yfinance fetching |
| `tests/test_normalizer.py` | Tests for financial normalization |
| `tests/test_context.py` | Tests for ValuationContext creation and validation |

---

## Task 1: Project Scaffolding

**Files:**
- Create: `pyproject.toml`
- Create: `src/valuation/__init__.py`
- Create: `src/valuation/data/__init__.py`
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`

- [ ] **Step 1: Create project structure**

```bash
mkdir -p src/valuation/data src/valuation/agents src/valuation/engines src/valuation/scoring src/valuation/reports/templates tests/golden config/prompts
```

- [ ] **Step 2: Write pyproject.toml**

```toml
[project]
name = "valuation-agent"
version = "0.1.0"
description = "Multi-agent valuation system using Damodaran methodology"
requires-python = ">=3.12"
dependencies = [
    "pandas>=2.0",
    "xlrd>=2.0",
    "openpyxl>=3.1",
    "yfinance>=0.2",
    "thefuzz>=0.22",
]

[project.optional-dependencies]
dev = [
    "pytest>=9.0",
    "pytest-cov>=4.0",
]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["src"]

[build-system]
requires = ["setuptools>=68.0"]
build-backend = "setuptools.backends._legacy:_Backend"
```

- [ ] **Step 3: Write package init files**

`src/valuation/__init__.py`:
```python
"""Valuation Agent — Multi-agent valuation system using Damodaran methodology."""
```

`src/valuation/data/__init__.py`:
```python
"""Data loading and normalization modules."""
```

`tests/__init__.py`: empty file

- [ ] **Step 4: Write conftest.py with shared fixtures**

```python
import pathlib
import pytest

PROJECT_ROOT = pathlib.Path(__file__).parent.parent

@pytest.fixture
def damodaran_data_dir():
    """Path to the Damodaran datasets directory (sibling to project root)."""
    path = PROJECT_ROOT.parent / "2. Damodaran_Data"
    if not path.exists():
        pytest.skip(f"Damodaran data not found at {path}")
    return path

@pytest.fixture
def examples_dir():
    """Path to example valuation spreadsheets."""
    path = PROJECT_ROOT.parent / "3. Valuation examples"
    if not path.exists():
        pytest.skip(f"Examples not found at {path}")
    return path
```

- [ ] **Step 5: Verify pytest discovers the project**

Run: `cd "/mnt/c/Users/Manan Sharma/Desktop/Coding projects/Valuation/0. Valuation Agent" && python3 -m pytest --collect-only`

Expected: `no tests ran` (0 collected, no errors)

- [ ] **Step 6: Install project in dev mode**

Run: `pip install -e ".[dev]"`

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml src/ tests/
git commit -m "chore: scaffold project structure with pyproject.toml and test config"
```

---

## Task 2: ValuationContext Dataclass

**Files:**
- Create: `src/valuation/context.py`
- Create: `tests/test_context.py`

- [ ] **Step 1: Write the failing test**

`tests/test_context.py`:
```python
import pandas as pd
from valuation.context import ValuationContext


def test_create_empty_context():
    ctx = ValuationContext(ticker="AAPL")
    assert ctx.company.ticker == "AAPL"
    assert ctx.company.name is None
    assert ctx.company.classification is None
    assert ctx.financials.income_statement is None
    assert ctx.assumptions.wacc is None
    assert ctx.outputs.dcf_fcff is None
    assert ctx.confidence.composite is None
    assert ctx.confidence.flags == []


def test_context_set_financials():
    ctx = ValuationContext(ticker="AAPL")
    ctx.financials.income_statement = pd.DataFrame({"revenue": [100, 200]})
    assert len(ctx.financials.income_statement) == 2


def test_context_override_tracking():
    ctx = ValuationContext(ticker="AAPL")
    ctx.assumptions.wacc = 0.08
    ctx.assumptions.set_override("wacc", 0.10, reason="User thinks risk is higher")
    assert ctx.assumptions.wacc == 0.10
    assert "wacc" in ctx.assumptions.overrides
    assert ctx.assumptions.overrides["wacc"]["original"] == 0.08
    assert ctx.assumptions.overrides["wacc"]["reason"] == "User thinks risk is higher"


def test_context_to_dict():
    ctx = ValuationContext(ticker="MSFT")
    ctx.company.name = "Microsoft"
    d = ctx.to_summary_dict()
    assert d["ticker"] == "MSFT"
    assert d["name"] == "Microsoft"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_context.py -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'valuation.context'`

- [ ] **Step 3: Write the implementation**

`src/valuation/context.py`:
```python
"""Shared data contract for the valuation pipeline."""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from typing import Any

import pandas as pd


@dataclass
class CompanyInfo:
    ticker: str
    name: str | None = None
    sector: str | None = None
    sic_code: str | None = None
    classification: str | None = None  # mature|growth|young|distressed|cyclical|financial
    damodaran_industry: str | None = None
    region: str = "US"  # US|Europe|Japan|India|China|Emerging|Global


@dataclass
class Financials:
    income_statement: pd.DataFrame | None = None
    balance_sheet: pd.DataFrame | None = None
    cash_flow: pd.DataFrame | None = None
    key_stats: dict[str, Any] = field(default_factory=dict)


@dataclass
class Benchmarks:
    industry_beta: float | None = None
    industry_unlevered_beta: float | None = None
    industry_de_ratio: float | None = None
    industry_multiples: dict[str, float] = field(default_factory=dict)
    industry_margins: dict[str, float] = field(default_factory=dict)
    industry_growth: dict[str, float] = field(default_factory=dict)
    industry_wacc: float | None = None


@dataclass
class Assumptions:
    risk_free_rate: float | None = None
    erp: float | None = None
    country_risk_premium: float = 0.0
    beta: float | None = None
    cost_of_equity: float | None = None
    cost_of_debt: float | None = None
    wacc: float | None = None
    growth_rates: list[float] = field(default_factory=list)
    terminal_growth: float | None = None
    projection_years: int = 10
    tax_rate: float | None = None
    overrides: dict[str, dict] = field(default_factory=dict)

    def set_override(self, param: str, new_value: float, reason: str = "") -> None:
        original = getattr(self, param)
        self.overrides[param] = {
            "original": original,
            "new": new_value,
            "reason": reason,
        }
        setattr(self, param, new_value)


@dataclass
class Outputs:
    dcf_fcff: dict[str, Any] | None = None
    dcf_fcfe: dict[str, Any] | None = None
    relative: dict[str, Any] | None = None
    excess_returns: dict[str, Any] | None = None
    sensitivity: dict[str, Any] | None = None


@dataclass
class Confidence:
    data_completeness: float | None = None
    model_agreement: float | None = None
    assumption_sensitivity: float | None = None
    industry_coverage: float | None = None
    composite: float | None = None
    flags: list[str] = field(default_factory=list)


@dataclass
class ValuationContext:
    """Central data structure passed through the entire valuation pipeline."""

    company: CompanyInfo = field(init=False)
    financials: Financials = field(default_factory=Financials)
    benchmarks: Benchmarks = field(default_factory=Benchmarks)
    assumptions: Assumptions = field(default_factory=Assumptions)
    outputs: Outputs = field(default_factory=Outputs)
    confidence: Confidence = field(default_factory=Confidence)

    def __init__(self, ticker: str, region: str = "US"):
        self.company = CompanyInfo(ticker=ticker, region=region)
        self.financials = Financials()
        self.benchmarks = Benchmarks()
        self.assumptions = Assumptions()
        self.outputs = Outputs()
        self.confidence = Confidence()

    def to_summary_dict(self) -> dict[str, Any]:
        return {
            "ticker": self.company.ticker,
            "name": self.company.name,
            "classification": self.company.classification,
            "damodaran_industry": self.company.damodaran_industry,
            "region": self.company.region,
            "wacc": self.assumptions.wacc,
            "dcf_value": (
                self.outputs.dcf_fcff.get("equity_value_per_share")
                if self.outputs.dcf_fcff
                else None
            ),
            "confidence": self.confidence.composite,
            "overrides": list(self.assumptions.overrides.keys()),
        }
```

- [ ] **Step 4: Run tests**

Run: `python3 -m pytest tests/test_context.py -v`

Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add src/valuation/context.py tests/test_context.py
git commit -m "feat: add ValuationContext dataclass as shared pipeline contract"
```

---

## Task 3: Damodaran Data Loader

**Files:**
- Create: `src/valuation/data/damodaran_loader.py`
- Create: `tests/test_damodaran_loader.py`

- [ ] **Step 1: Write failing tests**

`tests/test_damodaran_loader.py`:
```python
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
        assert len(df) >= 90  # ~96 industries
        assert "Industry Name" in df.columns
        assert "Unlevered beta" in df.columns or "Unlevered beta corrected for cash" in df.columns

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
        assert "Beta" in row.index or "Beta " in row.index

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
        assert len(df) >= 50  # decades of data

    def test_load_histimpl(self, damodaran_data_dir):
        loader = DamodaranLoader(damodaran_data_dir)
        df = loader.load("histimpl", region="US")
        assert isinstance(df, pd.DataFrame)

    def test_load_ctryprem(self, damodaran_data_dir):
        loader = DamodaranLoader(damodaran_data_dir)
        df = loader.load("ctryprem", region="Global")
        assert isinstance(df, pd.DataFrame)
        assert len(df) >= 100  # ~200 countries

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
        assert len(df) >= 10  # 10 deciles


class TestListIndustries:
    def test_list_all_industries(self, damodaran_data_dir):
        loader = DamodaranLoader(damodaran_data_dir)
        industries = loader.list_industries()
        assert len(industries) >= 90
        assert "Advertising" in industries
        assert "Software (System & Application)" in industries


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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_damodaran_loader.py -v`

Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write the implementation**

`src/valuation/data/damodaran_loader.py`:
```python
"""Load and query Damodaran industry datasets from Excel files."""

from __future__ import annotations

import pathlib
from functools import lru_cache

import pandas as pd


# Maps base filename (without region suffix) to its category subdirectory
_FILE_CATEGORY: dict[str, str] = {
    "betas": "risk_discount_rate",
    "wacc": "risk_discount_rate",
    "taxrate": "risk_discount_rate",
    "totalbeta": "risk_discount_rate",
    "histretSP": "risk_discount_rate",
    "histimpl": "risk_discount_rate",
    "ctryprem": "risk_discount_rate",
    "countrytaxrates": "risk_discount_rate",
    "mktcaprisk": "risk_discount_rate",
    "pedata": "multiples",
    "pbvdata": "multiples",
    "psdata": "multiples",
    "vebitda": "multiples",
    "mktcapmult": "multiples",
    "countrystats": "multiples",
    "roe": "growth_rate_estimation",
    "fundgr": "growth_rate_estimation",
    "histgr": "growth_rate_estimation",
    "fundgrEB": "growth_rate_estimation",
    "capex": "cash_flow_estimation",
    "margin": "cash_flow_estimation",
    "wcdata": "cash_flow_estimation",
    "R&D": "cash_flow_estimation",
    "goodwill": "cash_flow_estimation",
    "finflows": "cash_flow_estimation",
    "debtdetails": "capital_structure",
    "dbtfund": "capital_structure",
    "leaseeffect": "capital_structure",
    "macro": "capital_structure",
    "ratings": "capital_structure",
    "divfcfe": "dividend_policy",
    "divfund": "dividend_policy",
    "EVA": "investment_returns",
    "MktCap": "investment_returns",
    "Employee": "investment_returns",
    "DollarUS": "investment_returns",
    "inshold": "corporate_governance",
    "optvar": "option_pricing",
}

# Region suffixes appended to base filename
_REGION_SUFFIX: dict[str, str] = {
    "US": "",
    "Europe": "Europe",
    "Japan": "Japan",
    "AusNZCanada": "Rest",
    "Emerging": "emerg",
    "China": "China",
    "India": "India",
    "Global": "Global",
}

# Files that exist only as a single version (no regional variants)
_SINGLE_FILES: set[str] = {
    "histretSP", "histimpl", "ctryprem", "countrytaxrates",
    "mktcaprisk", "mktcapmult", "countrystats", "macro", "ratings",
}

# Special files where the US version has a different name pattern
_US_NAME_OVERRIDES: dict[str, str] = {
    "DollarUS": "DollarUS",  # US version is "DollarUS", not "Dollar"
}


class DamodaranLoader:
    """Load and query Damodaran industry datasets."""

    def __init__(self, data_dir: str | pathlib.Path):
        self.data_dir = pathlib.Path(data_dir)
        if not self.data_dir.exists():
            raise FileNotFoundError(f"Data directory not found: {self.data_dir}")
        self.categories = {
            d.name for d in self.data_dir.iterdir() if d.is_dir()
        }

    def _resolve_path(self, base_name: str, region: str) -> pathlib.Path:
        """Resolve a base file name + region to an actual file path."""
        category = _FILE_CATEGORY.get(base_name)
        if category is None:
            raise FileNotFoundError(
                f"Unknown dataset: {base_name}. "
                f"Available: {sorted(_FILE_CATEGORY.keys())}"
            )

        if base_name in _SINGLE_FILES:
            # These files have no regional variants
            candidates = list((self.data_dir / category).glob(f"{base_name}*"))
            if not candidates:
                raise FileNotFoundError(f"File not found: {base_name} in {category}")
            return candidates[0]

        suffix = _REGION_SUFFIX.get(region, "")

        # Handle special US name overrides
        if region == "US" and base_name in _US_NAME_OVERRIDES:
            filename_base = _US_NAME_OVERRIDES[base_name]
        elif region == "US":
            filename_base = base_name
        else:
            # For Dollar files: DollarEurope, DollarJapan, etc.
            if base_name == "DollarUS":
                filename_base = f"Dollar{suffix}"
            else:
                filename_base = f"{base_name}{suffix}"

        # Try .xls then .xlsx
        category_dir = self.data_dir / category
        for ext in (".xls", ".xlsx"):
            path = category_dir / f"{filename_base}{ext}"
            if path.exists():
                return path

        raise FileNotFoundError(
            f"File not found: {filename_base}.xls(x) in {category_dir}"
        )

    @lru_cache(maxsize=256)
    def load(self, base_name: str, region: str = "US") -> pd.DataFrame:
        """Load a dataset by base name and region, return as DataFrame."""
        path = self._resolve_path(base_name, region)
        return self.load_file(path)

    def load_file(self, path: pathlib.Path) -> pd.DataFrame:
        """Load any Damodaran Excel file, auto-detecting the header row."""
        path = pathlib.Path(path)
        ext = path.suffix.lower()

        if ext == ".xls":
            engine = "xlrd"
        elif ext == ".xlsx":
            engine = "openpyxl"
        else:
            raise ValueError(f"Unsupported file type: {ext}")

        # Read all sheets, pick the data sheet
        xls = pd.ExcelFile(path, engine=engine)
        sheet_name = self._pick_data_sheet(xls.sheet_names)
        raw = pd.read_excel(xls, sheet_name=sheet_name, header=None)

        # Find the header row (first row containing "Industry Name", "Country", "Year", or "Date")
        header_row = self._find_header_row(raw)
        if header_row is None:
            # Fallback: just return with row 0 as header
            return pd.read_excel(xls, sheet_name=sheet_name, engine=engine)

        df = pd.read_excel(xls, sheet_name=sheet_name, header=header_row, engine=engine)

        # Drop fully empty rows and columns
        df = df.dropna(how="all").dropna(axis=1, how="all")

        # Strip whitespace from column names
        df.columns = [str(c).strip() for c in df.columns]

        return df

    def _pick_data_sheet(self, sheet_names: list[str]) -> str:
        """Pick the most likely data sheet from a workbook."""
        priorities = ["Industry Averages", "Industry Values", "ERPs by country"]
        for name in priorities:
            if name in sheet_names:
                return name
        # Skip FAQ/explanation sheets
        for name in sheet_names:
            lower = name.lower()
            if "faq" not in lower and "variable" not in lower and "explanation" not in lower:
                return name
        return sheet_names[0]

    def _find_header_row(self, df: pd.DataFrame) -> int | None:
        """Find the row index that contains column headers."""
        markers = {"industry name", "country", "year", "date", "market cap"}
        for i in range(min(25, len(df))):
            row_values = {str(v).strip().lower() for v in df.iloc[i] if pd.notna(v)}
            if row_values & markers:
                return i
        return None

    def lookup(
        self, base_name: str, industry: str, region: str = "US"
    ) -> pd.Series | None:
        """Look up a single industry row from a dataset."""
        df = self.load(base_name, region)
        name_col = None
        for col in df.columns:
            if "industry" in col.lower() and "name" in col.lower():
                name_col = col
                break
            if col.lower().strip() == "industry name":
                name_col = col
                break

        if name_col is None:
            return None

        matches = df[df[name_col].str.strip() == industry.strip()]
        if len(matches) == 0:
            return None
        return matches.iloc[0]

    def list_industries(self, region: str = "US") -> list[str]:
        """Return sorted list of all Damodaran industry names."""
        df = self.load("betas", region)
        for col in df.columns:
            if "industry" in col.lower():
                return sorted(df[col].dropna().str.strip().tolist())
        return []
```

- [ ] **Step 4: Run tests**

Run: `python3 -m pytest tests/test_damodaran_loader.py -v`

Expected: All tests pass. The `test_all_244_files_parseable` test may take 10-20 seconds.

- [ ] **Step 5: Fix any failing edge cases**

Some files have unusual structures (e.g., `ratings.xls` is interactive, `macro.xls` has two data sheets, `ctryprem.xlsx` has 14 sheets). Adjust `_pick_data_sheet` and `_find_header_row` as needed until all 244 files parse.

- [ ] **Step 6: Commit**

```bash
git add src/valuation/data/damodaran_loader.py tests/test_damodaran_loader.py
git commit -m "feat: add Damodaran data loader with industry lookup and 244-file parsing"
```

---

## Task 4: Yahoo Finance API Client

**Files:**
- Create: `src/valuation/data/api_client.py`
- Create: `tests/test_api_client.py`

- [ ] **Step 1: Install yfinance**

Run: `pip install yfinance`

- [ ] **Step 2: Write failing tests**

`tests/test_api_client.py`:
```python
import pandas as pd
import pytest
from valuation.data.api_client import fetch_financials, CompanyData


class TestFetchFinancials:
    @pytest.mark.network
    def test_fetch_aapl(self):
        data = fetch_financials("AAPL")
        assert isinstance(data, CompanyData)
        assert data.ticker == "AAPL"
        assert isinstance(data.income_statement, pd.DataFrame)
        assert len(data.income_statement) >= 1
        assert isinstance(data.balance_sheet, pd.DataFrame)
        assert isinstance(data.cash_flow, pd.DataFrame)
        assert data.name is not None
        assert data.sector is not None
        assert data.shares_outstanding > 0
        assert data.market_cap > 0

    @pytest.mark.network
    def test_fetch_includes_key_stats(self):
        data = fetch_financials("MSFT")
        assert data.beta is not None or data.beta == 0
        assert data.price > 0

    def test_fetch_invalid_ticker(self):
        data = fetch_financials("ZZZINVALIDZZZ")
        assert data is None

    @pytest.mark.network
    def test_fetch_indian_stock(self):
        data = fetch_financials("TCS.NS")
        assert data is not None
        assert isinstance(data.income_statement, pd.DataFrame)


class TestManualInput:
    def test_create_company_data_manually(self):
        data = CompanyData(
            ticker="PRIVATE",
            name="Private Corp",
            sector="Technology",
            sic_code="7372",
            income_statement=pd.DataFrame({"Total Revenue": [1000], "Net Income": [100]}),
            balance_sheet=pd.DataFrame({"Total Assets": [5000]}),
            cash_flow=pd.DataFrame({"Operating Cash Flow": [200]}),
            shares_outstanding=100,
            market_cap=5000,
            price=50.0,
            beta=1.2,
            country="US",
        )
        assert data.ticker == "PRIVATE"
        assert data.market_cap == 5000
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_api_client.py -v -k "not network"`

Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 4: Write the implementation**

`src/valuation/data/api_client.py`:
```python
"""Fetch company financial data from Yahoo Finance."""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd


@dataclass
class CompanyData:
    """Raw company financial data from API or manual input."""

    ticker: str
    name: str | None = None
    sector: str | None = None
    industry: str | None = None
    sic_code: str | None = None
    country: str | None = None
    income_statement: pd.DataFrame | None = None
    balance_sheet: pd.DataFrame | None = None
    cash_flow: pd.DataFrame | None = None
    shares_outstanding: float = 0
    market_cap: float = 0
    price: float = 0
    beta: float | None = None
    dividend_per_share: float = 0
    book_value_per_share: float = 0


def fetch_financials(ticker: str) -> CompanyData | None:
    """Fetch financial statements and key stats from Yahoo Finance.

    Returns None if the ticker is invalid or data cannot be fetched.
    """
    try:
        import yfinance as yf
    except ImportError:
        raise ImportError("yfinance is required: pip install yfinance")

    stock = yf.Ticker(ticker)

    # Check if ticker is valid by trying to get info
    info = stock.info
    if not info or info.get("regularMarketPrice") is None:
        return None

    income_stmt = stock.financials
    if income_stmt is None or income_stmt.empty:
        # Try quarterly
        income_stmt = stock.quarterly_financials

    balance = stock.balance_sheet
    if balance is None or balance.empty:
        balance = stock.quarterly_balance_sheet

    cashflow = stock.cashflow
    if cashflow is None or cashflow.empty:
        cashflow = stock.quarterly_cashflow

    # Transpose so rows = years, columns = line items (yfinance returns transposed)
    if income_stmt is not None and not income_stmt.empty:
        income_stmt = income_stmt.T
    if balance is not None and not balance.empty:
        balance = balance.T
    if cashflow is not None and not cashflow.empty:
        cashflow = cashflow.T

    return CompanyData(
        ticker=ticker.upper(),
        name=info.get("longName") or info.get("shortName"),
        sector=info.get("sector"),
        industry=info.get("industry"),
        sic_code=info.get("sic"),
        country=info.get("country"),
        income_statement=income_stmt,
        balance_sheet=balance,
        cash_flow=cashflow,
        shares_outstanding=info.get("sharesOutstanding", 0) or 0,
        market_cap=info.get("marketCap", 0) or 0,
        price=info.get("regularMarketPrice") or info.get("currentPrice", 0) or 0,
        beta=info.get("beta"),
        dividend_per_share=info.get("dividendRate", 0) or 0,
        book_value_per_share=info.get("bookValue", 0) or 0,
    )
```

- [ ] **Step 5: Run non-network tests**

Run: `python3 -m pytest tests/test_api_client.py -v -k "not network"`

Expected: `test_create_company_data_manually` PASS, `test_fetch_invalid_ticker` PASS

- [ ] **Step 6: Run network tests (requires internet)**

Run: `python3 -m pytest tests/test_api_client.py -v -m network`

Expected: All PASS (fetches real AAPL, MSFT, TCS.NS data)

- [ ] **Step 7: Commit**

```bash
git add src/valuation/data/api_client.py tests/test_api_client.py
git commit -m "feat: add Yahoo Finance API client with manual input fallback"
```

---

## Task 5: Financial Data Normalizer

**Files:**
- Create: `src/valuation/data/normalizer.py`
- Create: `tests/test_normalizer.py`

- [ ] **Step 1: Write failing tests**

`tests/test_normalizer.py`:
```python
import pandas as pd
import pytest
from valuation.context import ValuationContext
from valuation.data.api_client import CompanyData
from valuation.data.normalizer import normalize


def _make_sample_company_data() -> CompanyData:
    """Create a CompanyData with realistic financial data."""
    return CompanyData(
        ticker="TEST",
        name="Test Corp",
        sector="Technology",
        industry="Software",
        sic_code="7372",
        country="United States",
        income_statement=pd.DataFrame({
            "Total Revenue": [50000, 45000, 40000],
            "Operating Income": [10000, 9000, 8000],
            "Net Income": [8000, 7000, 6000],
            "EBITDA": [12000, 11000, 10000],
            "Interest Expense": [500, 600, 700],
            "Tax Provision": [2000, 1800, 1600],
            "Basic EPS": [10.0, 8.75, 7.5],
        }),
        balance_sheet=pd.DataFrame({
            "Total Assets": [100000, 90000, 80000],
            "Total Debt": [15000, 16000, 17000],
            "Total Stockholders Equity": [60000, 55000, 50000],
            "Cash And Cash Equivalents": [10000, 8000, 6000],
        }),
        cash_flow=pd.DataFrame({
            "Operating Cash Flow": [12000, 11000, 10000],
            "Capital Expenditure": [-3000, -2800, -2500],
            "Free Cash Flow": [9000, 8200, 7500],
        }),
        shares_outstanding=800,
        market_cap=40000,
        price=50.0,
        beta=1.1,
        dividend_per_share=1.5,
        book_value_per_share=75.0,
    )


def test_normalize_populates_context():
    data = _make_sample_company_data()
    ctx = normalize(data)
    assert isinstance(ctx, ValuationContext)
    assert ctx.company.ticker == "TEST"
    assert ctx.company.name == "Test Corp"
    assert ctx.company.sector == "Technology"


def test_normalize_financials_attached():
    data = _make_sample_company_data()
    ctx = normalize(data)
    assert ctx.financials.income_statement is not None
    assert ctx.financials.balance_sheet is not None
    assert ctx.financials.cash_flow is not None


def test_normalize_key_stats():
    data = _make_sample_company_data()
    ctx = normalize(data)
    stats = ctx.financials.key_stats
    assert stats["shares_outstanding"] == 800
    assert stats["market_cap"] == 40000
    assert stats["price"] == 50.0
    assert stats["beta"] == 1.1
    assert stats["dividend_per_share"] == 1.5
    assert stats["book_value_per_share"] == 75.0


def test_normalize_detects_region_us():
    data = _make_sample_company_data()
    data.country = "United States"
    ctx = normalize(data)
    assert ctx.company.region == "US"


def test_normalize_detects_region_india():
    data = _make_sample_company_data()
    data.country = "India"
    ctx = normalize(data)
    assert ctx.company.region == "India"


def test_normalize_detects_region_japan():
    data = _make_sample_company_data()
    data.country = "Japan"
    ctx = normalize(data)
    assert ctx.company.region == "Japan"


def test_normalize_none_data_returns_none():
    result = normalize(None)
    assert result is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_normalizer.py -v`

Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write the implementation**

`src/valuation/data/normalizer.py`:
```python
"""Normalize raw CompanyData into a ValuationContext."""

from __future__ import annotations

from valuation.context import ValuationContext
from valuation.data.api_client import CompanyData

_COUNTRY_TO_REGION: dict[str, str] = {
    "United States": "US",
    "Canada": "AusNZCanada",
    "Australia": "AusNZCanada",
    "New Zealand": "AusNZCanada",
    "Japan": "Japan",
    "India": "India",
    "China": "China",
    "Hong Kong": "China",
    "United Kingdom": "Europe",
    "Germany": "Europe",
    "France": "Europe",
    "Switzerland": "Europe",
    "Netherlands": "Europe",
    "Sweden": "Europe",
    "Spain": "Europe",
    "Italy": "Europe",
    "Norway": "Europe",
    "Denmark": "Europe",
    "Finland": "Europe",
    "Belgium": "Europe",
    "Ireland": "Europe",
    "Austria": "Europe",
    "Portugal": "Europe",
}


def _detect_region(country: str | None) -> str:
    if country is None:
        return "US"
    if country in _COUNTRY_TO_REGION:
        return _COUNTRY_TO_REGION[country]
    # Default emerging markets for unlisted countries
    return "Emerging"


def normalize(data: CompanyData | None) -> ValuationContext | None:
    """Convert raw CompanyData into a ValuationContext with populated fields."""
    if data is None:
        return None

    region = _detect_region(data.country)
    ctx = ValuationContext(ticker=data.ticker, region=region)

    ctx.company.name = data.name
    ctx.company.sector = data.sector
    ctx.company.sic_code = data.sic_code

    ctx.financials.income_statement = data.income_statement
    ctx.financials.balance_sheet = data.balance_sheet
    ctx.financials.cash_flow = data.cash_flow
    ctx.financials.key_stats = {
        "shares_outstanding": data.shares_outstanding,
        "market_cap": data.market_cap,
        "price": data.price,
        "beta": data.beta,
        "dividend_per_share": data.dividend_per_share,
        "book_value_per_share": data.book_value_per_share,
        "country": data.country,
        "industry_yfinance": data.industry,
    }

    return ctx
```

- [ ] **Step 4: Run tests**

Run: `python3 -m pytest tests/test_normalizer.py -v`

Expected: All 7 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/valuation/data/normalizer.py tests/test_normalizer.py
git commit -m "feat: add financial data normalizer mapping CompanyData to ValuationContext"
```

---

## Task 6: Integration Smoke Test

**Files:**
- Create: `tests/test_integration_sprint1.py`

- [ ] **Step 1: Write integration test**

`tests/test_integration_sprint1.py`:
```python
"""Sprint 1 integration: load Damodaran data, fetch a company, normalize, populate context."""

import pytest
from valuation.context import ValuationContext
from valuation.data.damodaran_loader import DamodaranLoader


class TestDamodaranDataIntegration:
    def test_load_and_lookup_software_beta(self, damodaran_data_dir):
        loader = DamodaranLoader(damodaran_data_dir)
        row = loader.lookup("betas", "Software (System & Application)")
        assert row is not None
        beta_col = "Beta" if "Beta" in row.index else "Beta "
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
```

- [ ] **Step 2: Run non-network integration tests**

Run: `python3 -m pytest tests/test_integration_sprint1.py -v -k "not network"`

Expected: All PASS

- [ ] **Step 3: Run full integration (with network)**

Run: `python3 -m pytest tests/test_integration_sprint1.py -v`

Expected: All PASS

- [ ] **Step 4: Run entire test suite**

Run: `python3 -m pytest -v`

Expected: All tests PASS across all test files

- [ ] **Step 5: Commit**

```bash
git add tests/test_integration_sprint1.py
git commit -m "test: add Sprint 1 integration smoke tests"
```

- [ ] **Step 6: Push**

```bash
git push origin main
```

---

## Sprint 1 Completion Checklist

After all tasks are done, verify these acceptance criteria:

- [ ] `python3 -m pytest -v` — all tests pass
- [ ] Damodaran loader can parse all 244 files without error
- [ ] `loader.lookup("betas", "Software (System & Application)")` returns a valid row
- [ ] `loader.list_industries()` returns 90+ industry names
- [ ] `fetch_financials("AAPL")` returns a populated `CompanyData`
- [ ] `normalize(data)` produces a `ValuationContext` with financials attached
- [ ] `ValuationContext.assumptions.set_override()` tracks original values
- [ ] Project installs cleanly with `pip install -e ".[dev]"`
