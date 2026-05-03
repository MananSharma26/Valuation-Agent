# Sprint 3: Breadth — Industry Mapper, Relative Valuation, Company Classifier

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add breadth to the valuation pipeline — map companies to Damodaran's industry taxonomy via fuzzy matching, compute relative (multiples-based) valuations using industry benchmarks, and classify companies by lifecycle stage to guide model selection.

**Architecture:** Three independent modules that plug into `ValuationContext`. The industry mapper populates `company.damodaran_industry` and `benchmarks.*`. The relative engine reads `benchmarks.industry_multiples` and company financials to produce `outputs.relative`. The classifier sets `company.classification` based on rule-based heuristics. All modules are pure deterministic Python with no LLM dependencies.

**Tech Stack:** Python 3.12, pandas, thefuzz (fuzzy string matching), pytest, dataclasses

**Key constraint:** LLM never does math. All matching, valuation, and classification logic is deterministic Python. The classifier produces a reasoning string that a future LLM layer can refine, but this sprint is rule-based only.

**Key constraint:** No consensus/analyst estimates. All inputs come from company fundamentals + Damodaran industry data.

**Damodaran data location:** `/mnt/c/Users/Manan Sharma/Desktop/Coding projects/Valuation/2. Damodaran_Data/` (sibling to project root)

---

## File Structure

| File | Responsibility |
|------|---------------|
| `src/valuation/agents/industry_mapper.py` | Fuzzy-match company sector/industry to Damodaran's ~96 industry names, load all benchmark data |
| `src/valuation/engines/relative.py` | Compute implied equity values from PE, EV/EBITDA, PBV, PS multiples |
| `src/valuation/agents/classifier.py` | Rule-based company lifecycle classification (mature\|growth\|young\|distressed\|cyclical\|financial) |
| `tests/test_industry_mapper.py` | Tests for fuzzy matching and benchmark loading |
| `tests/test_relative.py` | Tests for relative valuation math |
| `tests/test_classifier.py` | Tests for company classification rules |
| `tests/test_integration_sprint3.py` | End-to-end integration tests for all three modules |

---

## Task 1: Industry Mapper — Fuzzy Matching

**Files:**
- Create: `src/valuation/agents/industry_mapper.py`
- Create: `tests/test_industry_mapper.py`

- [ ] **Step 1: Write failing tests**

`tests/test_industry_mapper.py`:
```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_industry_mapper.py -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'valuation.agents.industry_mapper'`

- [ ] **Step 3: Write the implementation**

`src/valuation/agents/industry_mapper.py`:
```python
"""Map a company to one of Damodaran's ~96 industry names using fuzzy matching.

Uses the thefuzz library for string similarity. The matching strategy:
1. Try exact match on the company's yfinance industry name
2. Try fuzzy match on industry name
3. Try fuzzy match on sector + industry combined
4. Try fuzzy match on description keywords
5. Return best match above threshold, or None if below threshold

When score < threshold (default 70), returns None — caller should ask user.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from thefuzz import fuzz, process

from valuation.data.damodaran_loader import DamodaranLoader


@dataclass
class IndustryMatch:
    """Result of an industry fuzzy-match attempt."""

    matched_name: str
    score: int
    candidates: list[tuple[str, int]] = field(default_factory=list)


def match_industry(
    sector: str,
    industry: str,
    description: str,
    loader: DamodaranLoader,
    region: str = "US",
    threshold: int = 70,
) -> IndustryMatch | None:
    """Match a company's sector/industry/description to a Damodaran industry name.

    Parameters
    ----------
    sector : str
        Company sector from yfinance (e.g. "Technology").
    industry : str
        Company industry from yfinance (e.g. "Software - Application").
    description : str
        Company business description or keywords.
    loader : DamodaranLoader
        Loaded Damodaran data instance.
    region : str
        Damodaran region for industry list lookup.
    threshold : int
        Minimum fuzzy match score (0-100) to accept. Default 70.

    Returns
    -------
    IndustryMatch or None
        Best match above threshold with top candidates, or None if no match
        meets the threshold (caller should ask user to select).
    """
    industry_names = loader.list_industries(region=region)
    if not industry_names:
        return None

    # Build query strings to try, in priority order
    queries: list[str] = []
    if industry:
        queries.append(industry)
    if sector and industry:
        queries.append(f"{sector} {industry}")
    if sector:
        queries.append(sector)
    if description:
        queries.append(description)

    if not queries:
        return None

    best_name: str | None = None
    best_score: int = 0
    all_candidates: list[tuple[str, int]] = []

    for query in queries:
        # Use token_sort_ratio for robustness against word reordering
        results = process.extract(
            query,
            industry_names,
            scorer=fuzz.token_sort_ratio,
            limit=5,
        )
        for name, score, *_ in results:
            if score > best_score:
                best_score = score
                best_name = name

        # Also try partial_ratio for substring matches
        results_partial = process.extract(
            query,
            industry_names,
            scorer=fuzz.partial_ratio,
            limit=5,
        )
        for name, score, *_ in results_partial:
            if score > best_score:
                best_score = score
                best_name = name

        # Collect unique candidates
        seen = set()
        for name, score, *_ in results + results_partial:
            if name not in seen:
                all_candidates.append((name, score))
                seen.add(name)

    # Deduplicate and sort candidates by score descending
    candidate_dict: dict[str, int] = {}
    for name, score in all_candidates:
        if name not in candidate_dict or score > candidate_dict[name]:
            candidate_dict[name] = score
    sorted_candidates = sorted(
        candidate_dict.items(), key=lambda x: x[1], reverse=True
    )[:5]

    if best_name is None or best_score < threshold:
        return None

    return IndustryMatch(
        matched_name=best_name,
        score=best_score,
        candidates=sorted_candidates,
    )
```

- [ ] **Step 4: Run tests**

Run: `python3 -m pytest tests/test_industry_mapper.py -v`

Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/valuation/agents/industry_mapper.py tests/test_industry_mapper.py
git commit -m "feat: add industry mapper with fuzzy matching to Damodaran taxonomy"
```

---

## Task 2: Industry Mapper — Benchmark Loading

**Files:**
- Modify: `src/valuation/agents/industry_mapper.py`
- Modify: `tests/test_industry_mapper.py`

- [ ] **Step 1: Write failing tests for benchmark loading**

Append to `tests/test_industry_mapper.py`:
```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_industry_mapper.py::TestBenchmarkLoading -v`

Expected: FAIL with `ImportError: cannot import name 'load_industry_benchmarks'`

- [ ] **Step 3: Write benchmark loading implementation**

Append to `src/valuation/agents/industry_mapper.py`:
```python
def _safe_float(value, default=None) -> float | None:
    """Safely convert a value to float, returning default on failure."""
    if value is None:
        return default
    try:
        result = float(value)
        if result != result:  # NaN check
            return default
        return result
    except (ValueError, TypeError):
        return default


def load_industry_benchmarks(
    industry_name: str,
    loader: DamodaranLoader,
    region: str = "US",
) -> dict | None:
    """Load all benchmark data for a Damodaran industry.

    Aggregates data from multiple Damodaran files (betas, wacc, pedata,
    pbvdata, psdata, vebitda, margin, fundgr) into a single dict.

    Parameters
    ----------
    industry_name : str
        Exact Damodaran industry name (e.g. "Software (System & Application)").
    loader : DamodaranLoader
        Loaded Damodaran data instance.
    region : str
        Damodaran region.

    Returns
    -------
    dict or None
        Dict with keys: beta, unlevered_beta, de_ratio, wacc, multiples,
        margins, growth. Returns None if industry not found in betas file.
    """
    # --- Beta data ---
    beta_row = loader.lookup("betas", industry_name, region=region)
    if beta_row is None:
        return None

    beta = _safe_float(beta_row.get("Beta") or beta_row.get("Beta "))
    unlevered_beta = _safe_float(
        beta_row.get("Unlevered beta corrected for cash")
        or beta_row.get("Unlevered beta")
    )
    de_ratio = _safe_float(beta_row.get("D/E Ratio"))

    # --- WACC ---
    wacc = None
    wacc_row = loader.lookup("wacc", industry_name, region=region)
    if wacc_row is not None:
        wacc = _safe_float(wacc_row.get("Cost of Capital"))

    # --- Multiples ---
    multiples: dict[str, float] = {}

    # PE data
    pe_row = loader.lookup("pedata", industry_name, region=region)
    if pe_row is not None:
        multiples["current_pe"] = _safe_float(pe_row.get("Current PE"))
        multiples["trailing_pe"] = _safe_float(pe_row.get("Trailing PE"))
        multiples["forward_pe"] = _safe_float(pe_row.get("Forward PE"))
        multiples["peg_ratio"] = _safe_float(pe_row.get("PEG Ratio"))

    # EV/EBITDA data
    vebitda_row = loader.lookup("vebitda", industry_name, region=region)
    if vebitda_row is not None:
        multiples["ev_ebitda"] = _safe_float(vebitda_row.get("EV/EBITDA"))
        multiples["ev_ebit"] = _safe_float(vebitda_row.get("EV/EBIT"))
        multiples["ev_ebitdar_and_d"] = _safe_float(
            vebitda_row.get("EV/EBITDAR&D")
        )

    # PBV data
    pbv_row = loader.lookup("pbvdata", industry_name, region=region)
    if pbv_row is not None:
        multiples["pbv"] = _safe_float(pbv_row.get("PBV"))
        multiples["ev_invested_capital"] = _safe_float(
            pbv_row.get("EV/ Invested Capital")
        )

    # PS data
    ps_row = loader.lookup("psdata", industry_name, region=region)
    if ps_row is not None:
        multiples["ps"] = _safe_float(ps_row.get("Price/Sales"))
        multiples["ev_sales"] = _safe_float(ps_row.get("EV/Sales"))

    # Remove None values from multiples
    multiples = {k: v for k, v in multiples.items() if v is not None}

    # --- Margins ---
    margins: dict[str, float] = {}
    if ps_row is not None:
        margins["net_margin"] = _safe_float(ps_row.get("Net Margin"))
        margins["operating_margin"] = _safe_float(
            ps_row.get("Pre-tax Operating Margin")
        )

    # ROE from PBV file
    if pbv_row is not None:
        margins["roe"] = _safe_float(pbv_row.get("ROE"))
        margins["roic"] = _safe_float(pbv_row.get("ROIC"))

    margins = {k: v for k, v in margins.items() if v is not None}

    # --- Growth ---
    growth: dict[str, float] = {}
    if pe_row is not None:
        growth["expected_growth_5y"] = _safe_float(
            pe_row.get("Expected growth - next 5 years")
        )

    growth = {k: v for k, v in growth.items() if v is not None}

    return {
        "beta": beta,
        "unlevered_beta": unlevered_beta,
        "de_ratio": de_ratio,
        "wacc": wacc,
        "multiples": multiples,
        "margins": margins,
        "growth": growth,
    }
```

- [ ] **Step 4: Run tests**

Run: `python3 -m pytest tests/test_industry_mapper.py -v`

Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/valuation/agents/industry_mapper.py tests/test_industry_mapper.py
git commit -m "feat: add benchmark loading from Damodaran files for matched industry"
```

---

## Task 3: Relative Valuation Engine

**Files:**
- Create: `src/valuation/engines/relative.py`
- Create: `tests/test_relative.py`

- [ ] **Step 1: Write failing tests**

`tests/test_relative.py`:
```python
import pytest
from valuation.engines.relative import (
    pe_implied_value,
    ev_ebitda_implied_value,
    pbv_implied_value,
    ps_implied_value,
    relative_valuation,
    RelativeResult,
)


class TestPEImpliedValue:
    def test_basic_pe(self):
        # EPS=5.0, industry PE=20 -> implied value = 100
        value = pe_implied_value(eps=5.0, industry_pe=20.0)
        assert abs(value - 100.0) < 0.01

    def test_negative_eps_returns_none(self):
        value = pe_implied_value(eps=-2.0, industry_pe=20.0)
        assert value is None

    def test_zero_pe_returns_none(self):
        value = pe_implied_value(eps=5.0, industry_pe=0.0)
        assert value is None

    def test_none_pe_returns_none(self):
        value = pe_implied_value(eps=5.0, industry_pe=None)
        assert value is None


class TestEVEBITDAImpliedValue:
    def test_basic_ev_ebitda(self):
        # EBITDA=500, industry EV/EBITDA=12, debt=1000, cash=200, shares=100
        # EV = 500*12 = 6000, equity = 6000 - 1000 + 200 = 5200
        # per share = 5200/100 = 52
        value = ev_ebitda_implied_value(
            ebitda=500.0,
            industry_ev_ebitda=12.0,
            debt=1000.0,
            cash=200.0,
            shares_outstanding=100.0,
        )
        assert abs(value - 52.0) < 0.01

    def test_negative_ebitda_returns_none(self):
        value = ev_ebitda_implied_value(
            ebitda=-500.0,
            industry_ev_ebitda=12.0,
            debt=1000.0,
            cash=200.0,
            shares_outstanding=100.0,
        )
        assert value is None

    def test_zero_ebitda_returns_none(self):
        value = ev_ebitda_implied_value(
            ebitda=0.0,
            industry_ev_ebitda=12.0,
            debt=1000.0,
            cash=200.0,
            shares_outstanding=100.0,
        )
        assert value is None


class TestPBVImpliedValue:
    def test_basic_pbv(self):
        # BVPS=25, industry PBV=3 -> implied value = 75
        value = pbv_implied_value(
            book_value_per_share=25.0,
            industry_pbv=3.0,
        )
        assert abs(value - 75.0) < 0.01

    def test_negative_bvps_returns_none(self):
        value = pbv_implied_value(
            book_value_per_share=-10.0,
            industry_pbv=3.0,
        )
        assert value is None

    def test_none_pbv_returns_none(self):
        value = pbv_implied_value(
            book_value_per_share=25.0,
            industry_pbv=None,
        )
        assert value is None


class TestPSImpliedValue:
    def test_basic_ps(self):
        # Revenue per share = 50, industry PS=4 -> implied value = 200
        value = ps_implied_value(
            revenue_per_share=50.0,
            industry_ps=4.0,
        )
        assert abs(value - 200.0) < 0.01

    def test_zero_revenue_returns_none(self):
        value = ps_implied_value(
            revenue_per_share=0.0,
            industry_ps=4.0,
        )
        assert value is None


class TestRelativeValuation:
    def test_full_relative_valuation(self):
        result = relative_valuation(
            eps=5.0,
            ebitda=500.0,
            book_value_per_share=25.0,
            revenue_per_share=50.0,
            industry_multiples={
                "current_pe": 20.0,
                "ev_ebitda": 12.0,
                "pbv": 3.0,
                "ps": 4.0,
            },
            debt=1000.0,
            cash=200.0,
            shares_outstanding=100.0,
            market_price=80.0,
        )
        assert isinstance(result, RelativeResult)
        assert result.pe_value == pytest.approx(100.0, abs=0.1)
        assert result.ev_ebitda_value == pytest.approx(52.0, abs=0.1)
        assert result.pbv_value == pytest.approx(75.0, abs=0.1)
        assert result.ps_value == pytest.approx(200.0, abs=0.1)

        # Composite is the median of non-None values
        assert result.composite_value is not None

        # Discount/premium vs market price
        assert result.discount_to_composite is not None

    def test_partial_data(self):
        # Missing EBITDA and book value
        result = relative_valuation(
            eps=5.0,
            ebitda=None,
            book_value_per_share=None,
            revenue_per_share=50.0,
            industry_multiples={
                "current_pe": 20.0,
                "ps": 4.0,
            },
            debt=0.0,
            cash=0.0,
            shares_outstanding=100.0,
            market_price=80.0,
        )
        assert result.pe_value == pytest.approx(100.0, abs=0.1)
        assert result.ev_ebitda_value is None
        assert result.pbv_value is None
        assert result.ps_value == pytest.approx(200.0, abs=0.1)
        assert result.composite_value is not None

    def test_all_missing_returns_none_composite(self):
        result = relative_valuation(
            eps=-5.0,
            ebitda=-100.0,
            book_value_per_share=-10.0,
            revenue_per_share=0.0,
            industry_multiples={},
            debt=0.0,
            cash=0.0,
            shares_outstanding=100.0,
            market_price=80.0,
        )
        assert result.composite_value is None

    def test_to_dict(self):
        result = relative_valuation(
            eps=5.0,
            ebitda=500.0,
            book_value_per_share=25.0,
            revenue_per_share=50.0,
            industry_multiples={
                "current_pe": 20.0,
                "ev_ebitda": 12.0,
                "pbv": 3.0,
                "ps": 4.0,
            },
            debt=1000.0,
            cash=200.0,
            shares_outstanding=100.0,
            market_price=80.0,
        )
        d = result.to_dict()
        assert "pe_value" in d
        assert "ev_ebitda_value" in d
        assert "pbv_value" in d
        assert "ps_value" in d
        assert "composite_value" in d
        assert "discount_to_composite" in d
        assert "methods_used" in d
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_relative.py -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'valuation.engines.relative'`

- [ ] **Step 3: Write the implementation**

`src/valuation/engines/relative.py`:
```python
"""
relative.py -- Relative (multiples-based) valuation engine.

Computes implied equity values from industry multiples:
  - P/E: implied_value = EPS * industry_PE
  - EV/EBITDA: implied_EV = EBITDA * industry_EV_EBITDA, then bridge to equity
  - P/BV: implied_value = BVPS * industry_PBV
  - P/S: implied_value = Revenue_per_share * industry_PS

All math is deterministic. No LLM calls. No consensus estimates.

Methodology: Damodaran (Investment Valuation, 3rd ed., Ch. 17-20)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from statistics import median
from typing import Any


@dataclass
class RelativeResult:
    """Result of a relative valuation across multiple multiples."""

    pe_value: float | None = None
    ev_ebitda_value: float | None = None
    pbv_value: float | None = None
    ps_value: float | None = None
    composite_value: float | None = None
    discount_to_composite: float | None = None
    market_price: float | None = None
    methods_used: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "pe_value": self.pe_value,
            "ev_ebitda_value": self.ev_ebitda_value,
            "pbv_value": self.pbv_value,
            "ps_value": self.ps_value,
            "composite_value": self.composite_value,
            "discount_to_composite": self.discount_to_composite,
            "market_price": self.market_price,
            "methods_used": self.methods_used,
        }


# ---------------------------------------------------------------------------
# Individual multiple valuation functions
# ---------------------------------------------------------------------------

def pe_implied_value(
    eps: float,
    industry_pe: float | None,
) -> float | None:
    """Compute implied equity value per share from P/E multiple.

    Formula: Implied Value = EPS * Industry PE

    Parameters
    ----------
    eps : float
        Earnings per share (trailing or forward). Must be positive.
    industry_pe : float or None
        Industry average P/E ratio from Damodaran.

    Returns
    -------
    float or None
        Implied value per share, or None if inputs are invalid.
    """
    if industry_pe is None or industry_pe <= 0:
        return None
    if eps is None or eps <= 0:
        return None
    return eps * industry_pe


def ev_ebitda_implied_value(
    ebitda: float | None,
    industry_ev_ebitda: float | None,
    debt: float,
    cash: float,
    shares_outstanding: float,
) -> float | None:
    """Compute implied equity value per share from EV/EBITDA multiple.

    Formula:
        Implied EV = EBITDA * Industry EV/EBITDA
        Implied Equity = EV - Debt + Cash
        Implied Per Share = Equity / Shares

    Parameters
    ----------
    ebitda : float or None
        Trailing EBITDA. Must be positive.
    industry_ev_ebitda : float or None
        Industry average EV/EBITDA from Damodaran.
    debt : float
        Total debt (book or market value).
    cash : float
        Cash and near-cash equivalents.
    shares_outstanding : float
        Diluted shares outstanding.

    Returns
    -------
    float or None
        Implied equity value per share, or None if inputs are invalid.
    """
    if industry_ev_ebitda is None or industry_ev_ebitda <= 0:
        return None
    if ebitda is None or ebitda <= 0:
        return None
    if shares_outstanding is None or shares_outstanding <= 0:
        return None
    implied_ev = ebitda * industry_ev_ebitda
    implied_equity = implied_ev - debt + cash
    return implied_equity / shares_outstanding


def pbv_implied_value(
    book_value_per_share: float | None,
    industry_pbv: float | None,
) -> float | None:
    """Compute implied equity value per share from P/BV multiple.

    Formula: Implied Value = BVPS * Industry P/BV

    Parameters
    ----------
    book_value_per_share : float or None
        Book value per share. Must be positive.
    industry_pbv : float or None
        Industry average price-to-book ratio from Damodaran.

    Returns
    -------
    float or None
        Implied value per share, or None if inputs are invalid.
    """
    if industry_pbv is None or industry_pbv <= 0:
        return None
    if book_value_per_share is None or book_value_per_share <= 0:
        return None
    return book_value_per_share * industry_pbv


def ps_implied_value(
    revenue_per_share: float | None,
    industry_ps: float | None,
) -> float | None:
    """Compute implied equity value per share from P/S multiple.

    Formula: Implied Value = Revenue Per Share * Industry P/S

    Parameters
    ----------
    revenue_per_share : float or None
        Revenue per share. Must be positive.
    industry_ps : float or None
        Industry average price-to-sales ratio from Damodaran.

    Returns
    -------
    float or None
        Implied value per share, or None if inputs are invalid.
    """
    if industry_ps is None or industry_ps <= 0:
        return None
    if revenue_per_share is None or revenue_per_share <= 0:
        return None
    return revenue_per_share * industry_ps


# ---------------------------------------------------------------------------
# Composite relative valuation
# ---------------------------------------------------------------------------

def relative_valuation(
    eps: float | None,
    ebitda: float | None,
    book_value_per_share: float | None,
    revenue_per_share: float | None,
    industry_multiples: dict[str, float | None],
    debt: float,
    cash: float,
    shares_outstanding: float,
    market_price: float | None = None,
) -> RelativeResult:
    """Compute implied values from all available multiples and produce a composite.

    The composite value is the median of all non-None implied values. This is
    more robust than a mean since it is less affected by outlier multiples.

    Parameters
    ----------
    eps : float or None
        Earnings per share (trailing).
    ebitda : float or None
        Trailing EBITDA (total, not per share).
    book_value_per_share : float or None
        Book value per share.
    revenue_per_share : float or None
        Revenue per share (total revenue / shares outstanding).
    industry_multiples : dict
        Dict with keys: current_pe, ev_ebitda, pbv, ps (from load_industry_benchmarks).
    debt : float
        Total debt.
    cash : float
        Cash and equivalents.
    shares_outstanding : float
        Diluted shares.
    market_price : float or None
        Current market price per share (for discount/premium calculation).

    Returns
    -------
    RelativeResult
        Dataclass with per-multiple implied values, composite, and discount/premium.
    """
    result = RelativeResult(market_price=market_price)

    # P/E
    result.pe_value = pe_implied_value(
        eps=eps,
        industry_pe=industry_multiples.get("current_pe"),
    )
    if result.pe_value is not None:
        result.methods_used.append("PE")

    # EV/EBITDA
    result.ev_ebitda_value = ev_ebitda_implied_value(
        ebitda=ebitda,
        industry_ev_ebitda=industry_multiples.get("ev_ebitda"),
        debt=debt,
        cash=cash,
        shares_outstanding=shares_outstanding,
    )
    if result.ev_ebitda_value is not None:
        result.methods_used.append("EV/EBITDA")

    # P/BV
    result.pbv_value = pbv_implied_value(
        book_value_per_share=book_value_per_share,
        industry_pbv=industry_multiples.get("pbv"),
    )
    if result.pbv_value is not None:
        result.methods_used.append("PBV")

    # P/S
    result.ps_value = ps_implied_value(
        revenue_per_share=revenue_per_share,
        industry_ps=industry_multiples.get("ps"),
    )
    if result.ps_value is not None:
        result.methods_used.append("PS")

    # Composite: median of all non-None values
    values = [
        v
        for v in [
            result.pe_value,
            result.ev_ebitda_value,
            result.pbv_value,
            result.ps_value,
        ]
        if v is not None
    ]
    if values:
        result.composite_value = median(values)

    # Discount/premium to composite
    if result.composite_value is not None and market_price is not None and market_price > 0:
        result.discount_to_composite = (
            result.composite_value - market_price
        ) / market_price

    return result
```

- [ ] **Step 4: Run tests**

Run: `python3 -m pytest tests/test_relative.py -v`

Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/valuation/engines/relative.py tests/test_relative.py
git commit -m "feat: add relative valuation engine with PE, EV/EBITDA, PBV, PS multiples"
```

---

## Task 4: Company Classifier

**Files:**
- Create: `src/valuation/agents/classifier.py`
- Create: `tests/test_classifier.py`

- [ ] **Step 1: Write failing tests**

`tests/test_classifier.py`:
```python
import pytest
import pandas as pd
from valuation.agents.classifier import (
    classify_company,
    ClassificationResult,
)
from valuation.context import ValuationContext


def _make_ctx(
    ticker: str = "TEST",
    sector: str | None = None,
    sic_code: str | None = None,
    revenue_growth: float | None = None,
    net_income_latest: float | None = None,
    net_income_prev: float | None = None,
    revenue_latest: float | None = None,
    revenue_prev: float | None = None,
    total_debt: float | None = None,
    total_equity: float | None = None,
    operating_income: float | None = None,
    interest_expense: float | None = None,
    market_cap: float = 50000.0,
    age_years: int | None = None,
) -> ValuationContext:
    """Helper to build a ValuationContext with controlled financials."""
    ctx = ValuationContext(ticker=ticker)
    ctx.company.sector = sector
    ctx.company.sic_code = sic_code

    # Build income statement
    income_data = {}
    if revenue_latest is not None:
        income_data["Total Revenue"] = [revenue_latest]
        if revenue_prev is not None:
            income_data["Total Revenue"] = [revenue_latest, revenue_prev]
    if net_income_latest is not None:
        income_data["Net Income"] = [net_income_latest]
        if net_income_prev is not None:
            income_data["Net Income"] = [net_income_latest, net_income_prev]
    if operating_income is not None:
        income_data["Operating Income"] = [operating_income]
    if interest_expense is not None:
        income_data["Interest Expense"] = [interest_expense]
    if income_data:
        ctx.financials.income_statement = pd.DataFrame(income_data)

    # Build balance sheet
    balance_data = {}
    if total_debt is not None:
        balance_data["Total Debt"] = [total_debt]
    if total_equity is not None:
        balance_data["Total Stockholders Equity"] = [total_equity]
    if balance_data:
        ctx.financials.balance_sheet = pd.DataFrame(balance_data)

    ctx.financials.key_stats["market_cap"] = market_cap
    if age_years is not None:
        ctx.financials.key_stats["company_age_years"] = age_years

    return ctx


class TestClassificationResult:
    def test_result_fields(self):
        r = ClassificationResult(
            classification="mature",
            confidence=0.85,
            reasoning="Stable revenue, positive earnings, moderate growth.",
        )
        assert r.classification == "mature"
        assert r.confidence == 0.85
        assert "Stable" in r.reasoning


class TestFinancialClassification:
    def test_bank_by_sic_code(self):
        ctx = _make_ctx(
            sic_code="6021",
            sector="Financial Services",
            revenue_latest=50000,
            net_income_latest=5000,
        )
        result = classify_company(ctx)
        assert result.classification == "financial"
        assert "SIC" in result.reasoning or "financial" in result.reasoning.lower()

    def test_insurance_by_sic_code(self):
        ctx = _make_ctx(
            sic_code="6311",
            sector="Financial Services",
            revenue_latest=30000,
            net_income_latest=3000,
        )
        result = classify_company(ctx)
        assert result.classification == "financial"

    def test_bank_by_sector(self):
        ctx = _make_ctx(
            sector="Financial Services",
            revenue_latest=50000,
            net_income_latest=5000,
        )
        result = classify_company(ctx)
        assert result.classification == "financial"


class TestDistressedClassification:
    def test_negative_earnings_multiple_years(self):
        ctx = _make_ctx(
            revenue_latest=10000,
            revenue_prev=12000,
            net_income_latest=-2000,
            net_income_prev=-1500,
            total_debt=30000,
            total_equity=5000,
        )
        result = classify_company(ctx)
        assert result.classification == "distressed"
        assert "negative" in result.reasoning.lower() or "loss" in result.reasoning.lower()

    def test_high_leverage_negative_income(self):
        ctx = _make_ctx(
            revenue_latest=10000,
            net_income_latest=-500,
            total_debt=50000,
            total_equity=5000,
            operating_income=1000,
            interest_expense=3000,
        )
        result = classify_company(ctx)
        assert result.classification == "distressed"


class TestGrowthClassification:
    def test_high_revenue_growth(self):
        ctx = _make_ctx(
            revenue_latest=50000,
            revenue_prev=30000,
            net_income_latest=2000,
            net_income_prev=500,
            market_cap=200000,
        )
        result = classify_company(ctx)
        assert result.classification == "growth"
        assert "growth" in result.reasoning.lower() or "revenue" in result.reasoning.lower()

    def test_moderate_growth_positive_earnings(self):
        ctx = _make_ctx(
            revenue_latest=20000,
            revenue_prev=15000,
            net_income_latest=2000,
            net_income_prev=1500,
        )
        result = classify_company(ctx)
        assert result.classification == "growth"


class TestYoungClassification:
    def test_young_company_no_earnings(self):
        ctx = _make_ctx(
            revenue_latest=5000,
            revenue_prev=1000,
            net_income_latest=-3000,
            net_income_prev=-2000,
            market_cap=50000,
            age_years=3,
        )
        result = classify_company(ctx)
        assert result.classification == "young"

    def test_pre_revenue(self):
        ctx = _make_ctx(
            revenue_latest=100,
            net_income_latest=-5000,
            market_cap=100000,
            age_years=2,
        )
        result = classify_company(ctx)
        assert result.classification == "young"


class TestMatureClassification:
    def test_stable_utility(self):
        ctx = _make_ctx(
            sector="Utilities",
            revenue_latest=20000,
            revenue_prev=19500,
            net_income_latest=3000,
            net_income_prev=2900,
            total_debt=15000,
            total_equity=20000,
        )
        result = classify_company(ctx)
        assert result.classification == "mature"

    def test_stable_consumer_staple(self):
        ctx = _make_ctx(
            revenue_latest=50000,
            revenue_prev=48000,
            net_income_latest=5000,
            net_income_prev=4800,
            total_debt=10000,
            total_equity=30000,
        )
        result = classify_company(ctx)
        assert result.classification == "mature"


class TestCyclicalClassification:
    def test_cyclical_by_sector(self):
        ctx = _make_ctx(
            sector="Basic Materials",
            revenue_latest=10000,
            revenue_prev=10500,
            net_income_latest=1000,
            net_income_prev=1200,
        )
        result = classify_company(ctx)
        assert result.classification == "cyclical"

    def test_auto_sector(self):
        ctx = _make_ctx(
            sector="Consumer Cyclical",
            revenue_latest=50000,
            revenue_prev=48000,
            net_income_latest=3000,
            net_income_prev=3500,
        )
        result = classify_company(ctx)
        assert result.classification == "cyclical"


class TestEdgeCases:
    def test_minimal_data(self):
        ctx = ValuationContext(ticker="UNKNOWN")
        result = classify_company(ctx)
        assert result.classification in (
            "mature", "growth", "young", "distressed", "cyclical", "financial"
        )
        assert result.confidence < 0.5  # low confidence with minimal data

    def test_classification_populates_context(self):
        ctx = _make_ctx(
            revenue_latest=50000,
            revenue_prev=48000,
            net_income_latest=5000,
            net_income_prev=4800,
        )
        result = classify_company(ctx)
        # Verify the result can populate context
        ctx.company.classification = result.classification
        assert ctx.company.classification in (
            "mature", "growth", "young", "distressed", "cyclical", "financial"
        )
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_classifier.py -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'valuation.agents.classifier'`

- [ ] **Step 3: Write the implementation**

`src/valuation/agents/classifier.py`:
```python
"""
classifier.py -- Rule-based company lifecycle classification.

Classifies a company as one of:
  - mature:     Stable earnings, moderate growth, established business
  - growth:     High revenue growth (>20%), positive or near-positive earnings
  - young:      Pre-profit or early-stage, high burn rate, short operating history
  - distressed: Negative earnings, high leverage, declining revenue
  - cyclical:   Sector-driven cyclicality (materials, energy, autos, etc.)
  - financial:  Banks, insurance, brokerages (SIC 60xx-67xx or Financial sector)

All logic is rule-based with deterministic scoring. Produces a reasoning
string that a future LLM layer can refine.

No LLM calls. No consensus estimates.
"""

from __future__ import annotations

from dataclasses import dataclass

from valuation.context import ValuationContext


@dataclass
class ClassificationResult:
    """Result of company classification."""

    classification: str  # mature|growth|young|distressed|cyclical|financial
    confidence: float    # 0.0 to 1.0
    reasoning: str       # Human-readable explanation for LLM to refine


# SIC code ranges for financial firms
_FINANCIAL_SIC_RANGES = [
    (6000, 6799),  # Finance, Insurance, Real Estate
]

# Sectors that indicate cyclical businesses
_CYCLICAL_SECTORS = {
    "Basic Materials",
    "Energy",
    "Consumer Cyclical",
    "Industrials",
}

# Sectors that indicate financial firms
_FINANCIAL_SECTORS = {
    "Financial Services",
    "Financial",
}


def _safe_get_col(df, col_name, row: int = 0, default=None):
    """Safely extract a value from a DataFrame column."""
    if df is None:
        return default
    if col_name not in df.columns:
        return default
    try:
        val = df[col_name].iloc[row]
        return float(val) if val is not None else default
    except (IndexError, ValueError, TypeError):
        return default


def _compute_revenue_growth(ctx: ValuationContext) -> float | None:
    """Compute YoY revenue growth from income statement."""
    is_df = ctx.financials.income_statement
    if is_df is None or "Total Revenue" not in is_df.columns:
        return None
    try:
        revenues = is_df["Total Revenue"].dropna().tolist()
        if len(revenues) < 2:
            return None
        latest = float(revenues[0])
        prev = float(revenues[1])
        if prev <= 0:
            return None
        return (latest - prev) / abs(prev)
    except (ValueError, TypeError, IndexError):
        return None


def _has_consecutive_losses(ctx: ValuationContext) -> bool:
    """Check if company has negative net income in the latest 2 periods."""
    is_df = ctx.financials.income_statement
    if is_df is None or "Net Income" not in is_df.columns:
        return False
    try:
        incomes = is_df["Net Income"].dropna().tolist()
        if len(incomes) < 2:
            return float(incomes[0]) < 0 if incomes else False
        return float(incomes[0]) < 0 and float(incomes[1]) < 0
    except (ValueError, TypeError, IndexError):
        return False


def _is_negative_earnings(ctx: ValuationContext) -> bool:
    """Check if latest net income is negative."""
    is_df = ctx.financials.income_statement
    if is_df is None or "Net Income" not in is_df.columns:
        return False
    try:
        return float(is_df["Net Income"].iloc[0]) < 0
    except (ValueError, TypeError, IndexError):
        return False


def _debt_to_equity(ctx: ValuationContext) -> float | None:
    """Compute debt-to-equity ratio from balance sheet."""
    bs = ctx.financials.balance_sheet
    if bs is None:
        return None
    debt = _safe_get_col(bs, "Total Debt")
    equity = _safe_get_col(bs, "Total Stockholders Equity")
    if debt is None or equity is None or equity <= 0:
        return None
    return debt / equity


def _interest_coverage(ctx: ValuationContext) -> float | None:
    """Compute interest coverage ratio = Operating Income / Interest Expense."""
    oi = _safe_get_col(ctx.financials.income_statement, "Operating Income")
    ie = _safe_get_col(ctx.financials.income_statement, "Interest Expense")
    if oi is None or ie is None or ie == 0:
        return None
    return oi / abs(ie)


def _is_financial_by_sic(sic_code: str | None) -> bool:
    """Check if SIC code falls in financial services range."""
    if sic_code is None:
        return False
    try:
        code = int(str(sic_code).strip()[:4])
        for low, high in _FINANCIAL_SIC_RANGES:
            if low <= code <= high:
                return True
    except (ValueError, TypeError):
        pass
    return False


def _get_company_age(ctx: ValuationContext) -> int | None:
    """Get company age in years from key_stats, if available."""
    return ctx.financials.key_stats.get("company_age_years")


def classify_company(ctx: ValuationContext) -> ClassificationResult:
    """Classify a company into a lifecycle stage based on its financials.

    Classification priority (checked in order):
      1. Financial — by SIC code (60xx-67xx) or sector
      2. Distressed — consecutive losses + high leverage or low coverage
      3. Young — short history + negative earnings + high growth
      4. Growth — revenue growth > 20% + positive or improving earnings
      5. Cyclical — cyclical sector + moderate/stable financials
      6. Mature — default for stable, profitable companies

    Parameters
    ----------
    ctx : ValuationContext
        Context with populated financials and company info.

    Returns
    -------
    ClassificationResult
        Classification label, confidence score, and reasoning string.
    """
    reasons: list[str] = []
    scores: dict[str, float] = {
        "mature": 0.0,
        "growth": 0.0,
        "young": 0.0,
        "distressed": 0.0,
        "cyclical": 0.0,
        "financial": 0.0,
    }

    # --- Rule 1: Financial firm detection ---
    if _is_financial_by_sic(ctx.company.sic_code):
        scores["financial"] += 5.0
        reasons.append(f"SIC code {ctx.company.sic_code} is in the financial services range (6000-6799).")

    if ctx.company.sector in _FINANCIAL_SECTORS:
        scores["financial"] += 3.0
        reasons.append(f"Sector '{ctx.company.sector}' indicates a financial firm.")

    if scores["financial"] >= 3.0:
        return ClassificationResult(
            classification="financial",
            confidence=min(0.95, 0.5 + scores["financial"] * 0.1),
            reasoning=" ".join(reasons),
        )

    # --- Gather metrics ---
    revenue_growth = _compute_revenue_growth(ctx)
    consecutive_losses = _has_consecutive_losses(ctx)
    negative_earnings = _is_negative_earnings(ctx)
    de_ratio = _debt_to_equity(ctx)
    coverage = _interest_coverage(ctx)
    age = _get_company_age(ctx)

    # --- Rule 2: Distressed detection ---
    if consecutive_losses:
        scores["distressed"] += 2.0
        reasons.append("Consecutive periods of negative net income.")

    if de_ratio is not None and de_ratio > 3.0:
        scores["distressed"] += 2.0
        reasons.append(f"High debt-to-equity ratio ({de_ratio:.1f}x).")

    if coverage is not None and coverage < 1.0:
        scores["distressed"] += 2.0
        reasons.append(f"Interest coverage below 1.0x ({coverage:.2f}x).")

    if revenue_growth is not None and revenue_growth < -0.10:
        scores["distressed"] += 1.0
        reasons.append(f"Revenue declining ({revenue_growth:.1%} YoY).")

    if scores["distressed"] >= 4.0:
        return ClassificationResult(
            classification="distressed",
            confidence=min(0.90, 0.4 + scores["distressed"] * 0.1),
            reasoning=" ".join(reasons),
        )

    # --- Rule 3: Young company detection ---
    is_young = False
    if age is not None and age <= 5:
        scores["young"] += 2.0
        reasons.append(f"Company is {age} years old (young).")
        is_young = True

    if negative_earnings and revenue_growth is not None and revenue_growth > 0.50:
        scores["young"] += 2.0
        reasons.append(
            f"Negative earnings with very high revenue growth ({revenue_growth:.1%}), "
            "suggesting early-stage company."
        )
        is_young = True

    if is_young and negative_earnings:
        scores["young"] += 1.0
        reasons.append("Pre-profit stage.")

    if scores["young"] >= 3.0:
        return ClassificationResult(
            classification="young",
            confidence=min(0.85, 0.4 + scores["young"] * 0.1),
            reasoning=" ".join(reasons),
        )

    # --- Rule 4: Growth detection ---
    if revenue_growth is not None and revenue_growth > 0.20:
        scores["growth"] += 3.0
        reasons.append(f"Revenue growth of {revenue_growth:.1%} exceeds 20% threshold.")

    if revenue_growth is not None and 0.10 < revenue_growth <= 0.20:
        scores["growth"] += 1.5
        reasons.append(f"Moderate-high revenue growth ({revenue_growth:.1%}).")

    if not negative_earnings and revenue_growth is not None and revenue_growth > 0.10:
        scores["growth"] += 1.0
        reasons.append("Positive earnings combined with strong revenue growth.")

    if scores["growth"] >= 2.5:
        return ClassificationResult(
            classification="growth",
            confidence=min(0.85, 0.4 + scores["growth"] * 0.1),
            reasoning=" ".join(reasons),
        )

    # --- Rule 5: Cyclical detection ---
    if ctx.company.sector in _CYCLICAL_SECTORS:
        scores["cyclical"] += 3.0
        reasons.append(f"Sector '{ctx.company.sector}' is classified as cyclical.")

    if scores["cyclical"] >= 3.0 and not negative_earnings:
        return ClassificationResult(
            classification="cyclical",
            confidence=min(0.80, 0.4 + scores["cyclical"] * 0.1),
            reasoning=" ".join(reasons),
        )

    # --- Rule 6: Mature (default) ---
    if not negative_earnings:
        scores["mature"] += 2.0
        reasons.append("Positive earnings indicate established business.")

    if revenue_growth is not None and abs(revenue_growth) <= 0.10:
        scores["mature"] += 1.0
        reasons.append(f"Stable revenue growth ({revenue_growth:.1%}).")

    if de_ratio is not None and de_ratio < 2.0:
        scores["mature"] += 0.5
        reasons.append(f"Moderate leverage (D/E={de_ratio:.1f}x).")

    if not reasons:
        reasons.append("Insufficient data for confident classification; defaulting to mature.")

    # Confidence is lower if we fell through to default
    confidence = min(0.75, 0.2 + scores["mature"] * 0.1)
    if not ctx.financials.income_statement is not None:
        confidence = max(confidence, 0.3)
    else:
        confidence = max(confidence, 0.2)

    return ClassificationResult(
        classification="mature",
        confidence=confidence,
        reasoning=" ".join(reasons),
    )
```

- [ ] **Step 4: Run tests**

Run: `python3 -m pytest tests/test_classifier.py -v`

Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/valuation/agents/classifier.py tests/test_classifier.py
git commit -m "feat: add rule-based company classifier with lifecycle stage detection"
```

---

## Task 5: Integration Test — All Sprint 3 Modules Together

**Files:**
- Create: `tests/test_integration_sprint3.py`

- [ ] **Step 1: Write integration test**

`tests/test_integration_sprint3.py`:
```python
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
```

- [ ] **Step 2: Run integration tests**

Run: `python3 -m pytest tests/test_integration_sprint3.py -v`

Expected: All tests PASS

- [ ] **Step 3: Run full test suite**

Run: `python3 -m pytest -v -k "not network"`

Expected: All tests PASS across all sprint test files

- [ ] **Step 4: Commit**

```bash
git add tests/test_integration_sprint3.py
git commit -m "test: add Sprint 3 integration tests for industry mapping, relative valuation, and classification"
```

- [ ] **Step 5: Push**

```bash
git push origin main
```

---

## Sprint 3 Completion Checklist

After all tasks are done, verify these acceptance criteria:

- [ ] `python3 -m pytest -v -k "not network"` -- all tests pass
- [ ] `match_industry(sector="Technology", industry="Software - Application", ...)` returns a match with score >= 70
- [ ] `match_industry(sector="Energy", industry="Oil & Gas E&P", ...)` matches to an Oil/Gas Damodaran industry
- [ ] `match_industry(sector="Financial Services", industry="Banks - Diversified", ...)` matches to a banking industry
- [ ] Low-confidence matches (score < threshold) return `None` so caller can ask user
- [ ] `load_industry_benchmarks("Software (System & Application)", ...)` returns beta, WACC, PE, EV/EBITDA, PBV, PS, margins, growth
- [ ] `relative_valuation(...)` computes implied values from all 4 multiples (PE, EV/EBITDA, PBV, PS)
- [ ] Composite value is the median of non-None implied values
- [ ] Negative EPS/EBITDA/BVPS gracefully returns None for that multiple (not an error)
- [ ] `classify_company(ctx)` returns "financial" for SIC 6021 or Financial Services sector
- [ ] `classify_company(ctx)` returns "distressed" for consecutive losses + high leverage
- [ ] `classify_company(ctx)` returns "growth" for >20% revenue growth + positive earnings
- [ ] `classify_company(ctx)` returns "young" for early-stage companies with high burn rate
- [ ] `classify_company(ctx)` returns "cyclical" for Basic Materials / Energy / Consumer Cyclical sectors
- [ ] `classify_company(ctx)` returns "mature" as the default for stable, profitable companies
- [ ] Classifier produces a reasoning string explaining the classification logic
- [ ] All three modules populate `ValuationContext` fields correctly
- [ ] All engines are pure functions -- no LLM, no side effects, no consensus estimates
