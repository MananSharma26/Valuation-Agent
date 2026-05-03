# Sprint 2: Core Engine — Risk Assessor, DCF Engine, Golden Tests

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the deterministic financial math engines — risk assessment (WACC/CAPM) and DCF valuation (FCFF, DDM, Gordon Growth) — validated against Damodaran's own example spreadsheets as golden tests.

**Architecture:** All financial math is pure deterministic Python functions. No LLM calls. Every formula is unit-tested against known values from Damodaran's spreadsheets. The engines take parameters in, return numbers out.

**Tech Stack:** Python 3.12, pandas, numpy, pytest, dataclasses

**Key constraint:** LLM never does math. These engines are called by Claude Code with parameters — the engine computes, Claude Code interprets results.

**Key constraint:** No consensus/analyst estimates feed into these engines. All inputs come from company fundamentals + Damodaran industry data.

---

## File Structure

| File | Responsibility |
|------|---------------|
| `src/valuation/engines/__init__.py` | Already exists (empty) |
| `src/valuation/engines/dcf.py` | FCFF DCF, DDM, Gordon Growth — all deterministic math |
| `src/valuation/agents/risk_assessor.py` | WACC, cost of equity, cost of debt, synthetic rating, bottom-up beta |
| `tests/test_risk_assessor.py` | Tests for risk assessment against Damodaran data |
| `tests/test_dcf.py` | Tests for DCF engine formulas |
| `tests/golden/` | Golden test JSON files extracted from example spreadsheets |
| `tests/test_golden.py` | Golden tests validating engine output vs Damodaran examples |

---

## Task 1: Synthetic Rating & Cost of Debt Lookup Tables

**Files:**
- Create: `src/valuation/agents/risk_assessor.py`
- Create: `tests/test_risk_assessor.py`

- [ ] **Step 1: Write failing tests for synthetic rating**

`tests/test_risk_assessor.py`:
```python
import pytest
from valuation.agents.risk_assessor import (
    get_synthetic_rating,
    get_default_spread,
    compute_cost_of_debt,
)


class TestSyntheticRating:
    def test_large_firm_high_coverage(self):
        rating, spread = get_synthetic_rating(
            interest_coverage=10.0, firm_type="large"
        )
        assert rating == "Aaa/AAA"
        assert spread == 0.0040

    def test_large_firm_medium_coverage(self):
        rating, spread = get_synthetic_rating(
            interest_coverage=3.5, firm_type="large"
        )
        assert rating == "A3/A-"
        assert spread == 0.0089

    def test_large_firm_low_coverage(self):
        rating, spread = get_synthetic_rating(
            interest_coverage=0.5, firm_type="large"
        )
        assert rating == "C2/C"
        assert spread == 0.16

    def test_large_firm_negative_coverage(self):
        rating, spread = get_synthetic_rating(
            interest_coverage=-2.0, firm_type="large"
        )
        assert rating == "D2/D"
        assert spread == 0.19

    def test_small_firm_high_coverage(self):
        rating, spread = get_synthetic_rating(
            interest_coverage=15.0, firm_type="small"
        )
        assert rating == "Aaa/AAA"
        assert spread == 0.0040

    def test_small_firm_medium_coverage(self):
        rating, spread = get_synthetic_rating(
            interest_coverage=5.0, firm_type="small"
        )
        assert rating == "A3/A-"
        assert spread == 0.0089

    def test_financial_firm(self):
        rating, spread = get_synthetic_rating(
            interest_coverage=4.0, firm_type="financial"
        )
        assert rating == "Aaa/AAA"
        assert spread == 0.0040

    def test_financial_firm_low(self):
        rating, spread = get_synthetic_rating(
            interest_coverage=0.55, firm_type="financial"
        )
        assert rating == "B1/B+"
        assert spread == 0.0275


class TestCostOfDebt:
    def test_cost_of_debt_from_rating(self):
        cod = compute_cost_of_debt(
            risk_free_rate=0.0395,
            interest_coverage=5.0,
            firm_type="large",
        )
        # Rf 3.95% + A2/A spread 0.78% = 4.73%
        assert abs(cod - 0.0473) < 0.0001

    def test_cost_of_debt_distressed(self):
        cod = compute_cost_of_debt(
            risk_free_rate=0.0395,
            interest_coverage=0.1,
            firm_type="large",
        )
        # Rf 3.95% + D2/D spread 19% = 22.95%
        assert abs(cod - 0.2295) < 0.0001
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_risk_assessor.py::TestSyntheticRating -v`

Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write synthetic rating implementation**

`src/valuation/agents/risk_assessor.py`:
```python
"""Risk assessment: WACC, cost of equity, cost of debt, beta estimation.

All functions are deterministic. No LLM calls.
"""

from __future__ import annotations


# Interest Coverage Ratio -> (Rating, Default Spread) lookup tables
# Source: Damodaran ratings.xls, verified Jan 2026

_RATING_TABLE_LARGE: list[tuple[float, float, str, float]] = [
    (-1e6, 0.199999, "D2/D", 0.19),
    (0.20, 0.649999, "C2/C", 0.16),
    (0.65, 0.799999, "Ca2/CC", 0.1261),
    (0.80, 1.249999, "Caa/CCC", 0.0885),
    (1.25, 1.499999, "B3/B-", 0.0509),
    (1.50, 1.749999, "B2/B", 0.0321),
    (1.75, 1.999999, "B1/B+", 0.0275),
    (2.00, 2.249999, "Ba2/BB", 0.0184),
    (2.25, 2.49999, "Ba1/BB+", 0.0138),
    (2.50, 2.999999, "Baa2/BBB", 0.0111),
    (3.00, 4.249999, "A3/A-", 0.0089),
    (4.25, 5.499999, "A2/A", 0.0078),
    (5.50, 6.499999, "A1/A+", 0.0070),
    (6.50, 8.499999, "Aa2/AA", 0.0055),
    (8.50, 1e6, "Aaa/AAA", 0.0040),
]

_RATING_TABLE_SMALL: list[tuple[float, float, str, float]] = [
    (-1e6, 0.499999, "D2/D", 0.19),
    (0.50, 0.799999, "C2/C", 0.16),
    (0.80, 1.249999, "Ca2/CC", 0.1261),
    (1.25, 1.499999, "Caa/CCC", 0.0885),
    (1.50, 1.999999, "B3/B-", 0.0509),
    (2.00, 2.499999, "B2/B", 0.0321),
    (2.50, 2.999999, "B1/B+", 0.0275),
    (3.00, 3.499999, "Ba2/BB", 0.0184),
    (3.50, 3.999999, "Ba1/BB+", 0.0138),
    (4.00, 4.499999, "Baa2/BBB", 0.0111),
    (4.50, 5.999999, "A3/A-", 0.0089),
    (6.00, 7.499999, "A2/A", 0.0078),
    (7.50, 9.499999, "A1/A+", 0.0070),
    (9.50, 12.499999, "Aa2/AA", 0.0055),
    (12.50, 1e6, "Aaa/AAA", 0.0040),
]

_RATING_TABLE_FINANCIAL: list[tuple[float, float, str, float]] = [
    (-1e6, 0.049999, "D2/D", 0.19),
    (0.05, 0.099999, "C2/C", 0.16),
    (0.10, 0.199999, "Ca2/CC", 0.1261),
    (0.20, 0.299999, "Caa/CCC", 0.0885),
    (0.30, 0.399999, "B3/B-", 0.0509),
    (0.40, 0.499999, "B2/B", 0.0321),
    (0.50, 0.599999, "B1/B+", 0.0275),
    (0.60, 0.749999, "Ba2/BB", 0.0184),
    (0.75, 0.899999, "Ba1/BB+", 0.0138),
    (0.90, 1.199999, "Baa2/BBB", 0.0111),
    (1.20, 1.49999, "A3/A-", 0.0089),
    (1.50, 1.99999, "A2/A", 0.0078),
    (2.00, 2.49999, "A1/A+", 0.0070),
    (2.50, 2.99999, "Aa2/AA", 0.0055),
    (3.00, 1e6, "Aaa/AAA", 0.0040),
]

_RATING_TABLES = {
    "large": _RATING_TABLE_LARGE,
    "small": _RATING_TABLE_SMALL,
    "financial": _RATING_TABLE_FINANCIAL,
}


def get_synthetic_rating(
    interest_coverage: float, firm_type: str = "large"
) -> tuple[str, float]:
    """Map interest coverage ratio to a synthetic bond rating and default spread.

    Args:
        interest_coverage: EBIT / Interest Expense
        firm_type: "large" (>$5B), "small" (<$5B), or "financial"

    Returns:
        (rating_string, default_spread_decimal)
    """
    table = _RATING_TABLES.get(firm_type, _RATING_TABLE_LARGE)
    for low, high, rating, spread in table:
        if low <= interest_coverage <= high:
            return rating, spread
    # Fallback to worst rating
    return "D2/D", 0.19


def get_default_spread(interest_coverage: float, firm_type: str = "large") -> float:
    """Get just the default spread for a given coverage ratio."""
    _, spread = get_synthetic_rating(interest_coverage, firm_type)
    return spread


def compute_cost_of_debt(
    risk_free_rate: float,
    interest_coverage: float,
    firm_type: str = "large",
) -> float:
    """Compute pre-tax cost of debt = risk-free rate + default spread.

    Args:
        risk_free_rate: Current risk-free rate (decimal)
        interest_coverage: EBIT / Interest Expense
        firm_type: "large", "small", or "financial"

    Returns:
        Pre-tax cost of debt (decimal)
    """
    spread = get_default_spread(interest_coverage, firm_type)
    return risk_free_rate + spread
```

- [ ] **Step 4: Run tests**

Run: `python3 -m pytest tests/test_risk_assessor.py -v`

Expected: All 10 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/valuation/agents/risk_assessor.py tests/test_risk_assessor.py
git commit -m "feat: add synthetic rating lookup tables and cost of debt estimation"
```

---

## Task 2: Cost of Equity, Beta, and WACC

**Files:**
- Modify: `src/valuation/agents/risk_assessor.py`
- Modify: `tests/test_risk_assessor.py`

- [ ] **Step 1: Write failing tests for CAPM and WACC**

Append to `tests/test_risk_assessor.py`:
```python
from valuation.agents.risk_assessor import (
    compute_cost_of_equity,
    relever_beta,
    unlever_beta,
    compute_wacc,
)


class TestCostOfEquity:
    def test_capm_basic(self):
        ke = compute_cost_of_equity(
            risk_free_rate=0.0395,
            beta=1.0,
            erp=0.0446,
            country_risk_premium=0.0,
        )
        assert abs(ke - 0.0841) < 0.0001

    def test_capm_with_country_risk(self):
        # India example: Rf=3.95%, beta=1.05, ERP=4.46%, CRP=4.5%, lambda=0.2
        ke = compute_cost_of_equity(
            risk_free_rate=0.0395,
            beta=1.05,
            erp=0.0446,
            country_risk_premium=0.045,
            lambda_country=0.2,
        )
        # ke = 0.0395 + 1.05*0.0446 + 0.2*0.045 = 0.0395 + 0.04683 + 0.009 = 0.09533
        assert abs(ke - 0.09533) < 0.001

    def test_goldman_cost_of_equity(self):
        # Goldman: Rf=4.1%, Beta=1.4, ERP=4.5%
        ke = compute_cost_of_equity(
            risk_free_rate=0.041,
            beta=1.4,
            erp=0.045,
        )
        # 4.1% + 1.4*4.5% = 10.4%
        assert abs(ke - 0.104) < 0.001


class TestBeta:
    def test_unlever_beta(self):
        # Beta=1.3638, D/E=0.088, tax=35%
        bu = unlever_beta(levered_beta=1.3638, de_ratio=0.088, tax_rate=0.35)
        # Bu = Bl / (1 + (1-t)*D/E) = 1.3638 / (1 + 0.65*0.088) = 1.3638/1.0572
        assert abs(bu - 1.2898) < 0.01

    def test_relever_beta(self):
        # 3M: unlevered=1.2922, D/E=0.088, tax=35%
        bl = relever_beta(unlevered_beta=1.2922, de_ratio=0.088, tax_rate=0.35)
        # Bl = Bu * (1 + (1-t)*D/E) = 1.2922 * 1.0572 = 1.3662
        assert abs(bl - 1.3662) < 0.01

    def test_unlever_relever_round_trip(self):
        bl = 1.5
        de = 0.3
        t = 0.25
        bu = unlever_beta(bl, de, t)
        bl2 = relever_beta(bu, de, t)
        assert abs(bl - bl2) < 0.0001


class TestWACC:
    def test_wacc_basic(self):
        wacc = compute_wacc(
            cost_of_equity=0.104,
            cost_of_debt=0.045,
            tax_rate=0.25,
            equity_weight=0.80,
            debt_weight=0.20,
        )
        # 0.104*0.8 + 0.045*0.75*0.2 = 0.0832 + 0.00675 = 0.08995
        assert abs(wacc - 0.08995) < 0.001

    def test_wacc_3m(self):
        # 3M pre-crisis: Ke~9.16%, Kd~4.42%, tax=35%, E/(D+E)~92%, D/(D+E)~8%
        wacc = compute_wacc(
            cost_of_equity=0.0916,
            cost_of_debt=0.0442,
            tax_rate=0.35,
            equity_weight=0.919,
            debt_weight=0.081,
        )
        # 0.0916*0.919 + 0.0442*0.65*0.081 = 0.08418 + 0.00233 = 0.0865
        assert abs(wacc - 0.0865) < 0.002

    def test_wacc_all_equity(self):
        wacc = compute_wacc(
            cost_of_equity=0.10,
            cost_of_debt=0.05,
            tax_rate=0.25,
            equity_weight=1.0,
            debt_weight=0.0,
        )
        assert abs(wacc - 0.10) < 0.0001
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_risk_assessor.py -v -k "CostOfEquity or Beta or WACC"`

Expected: FAIL with `ImportError`

- [ ] **Step 3: Add CAPM, beta, and WACC functions to risk_assessor.py**

Append to `src/valuation/agents/risk_assessor.py`:
```python
def compute_cost_of_equity(
    risk_free_rate: float,
    beta: float,
    erp: float,
    country_risk_premium: float = 0.0,
    lambda_country: float = 1.0,
) -> float:
    """CAPM: Ke = Rf + Beta * ERP + Lambda * CRP.

    Args:
        risk_free_rate: Current risk-free rate (decimal)
        beta: Levered beta
        erp: Equity risk premium (decimal)
        country_risk_premium: Additional country risk premium (decimal)
        lambda_country: Firm-specific country risk exposure (0-1, default 1.0)

    Returns:
        Cost of equity (decimal)
    """
    return risk_free_rate + beta * erp + lambda_country * country_risk_premium


def unlever_beta(
    levered_beta: float, de_ratio: float, tax_rate: float
) -> float:
    """Unlever beta using Hamada equation: Bu = Bl / (1 + (1-t) * D/E)."""
    return levered_beta / (1 + (1 - tax_rate) * de_ratio)


def relever_beta(
    unlevered_beta: float, de_ratio: float, tax_rate: float
) -> float:
    """Re-lever beta using Hamada equation: Bl = Bu * (1 + (1-t) * D/E)."""
    return unlevered_beta * (1 + (1 - tax_rate) * de_ratio)


def compute_wacc(
    cost_of_equity: float,
    cost_of_debt: float,
    tax_rate: float,
    equity_weight: float,
    debt_weight: float,
) -> float:
    """WACC = Ke * (E/(D+E)) + Kd * (1-t) * (D/(D+E)).

    Args:
        cost_of_equity: Ke (decimal)
        cost_of_debt: Pre-tax Kd (decimal)
        tax_rate: Marginal tax rate (decimal)
        equity_weight: E / (D+E) (decimal)
        debt_weight: D / (D+E) (decimal)

    Returns:
        WACC (decimal)
    """
    return (
        cost_of_equity * equity_weight
        + cost_of_debt * (1 - tax_rate) * debt_weight
    )
```

- [ ] **Step 4: Run tests**

Run: `python3 -m pytest tests/test_risk_assessor.py -v`

Expected: All 18 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/valuation/agents/risk_assessor.py tests/test_risk_assessor.py
git commit -m "feat: add CAPM cost of equity, Hamada beta, and WACC computation"
```

---

## Task 3: DCF Engine — Gordon Growth Model

**Files:**
- Create: `src/valuation/engines/dcf.py`
- Create: `tests/test_dcf.py`

- [ ] **Step 1: Write failing tests**

`tests/test_dcf.py`:
```python
import pytest
from valuation.engines.dcf import gordon_growth_value


class TestGordonGrowth:
    def test_coned_valuation(self):
        # ConEd: DPS=2.32, ke=7.7%, g=2.1%
        value = gordon_growth_value(
            current_dividend=2.32,
            cost_of_equity=0.077,
            growth_rate=0.021,
        )
        assert abs(value - 42.30) < 0.1

    def test_implied_growth(self):
        from valuation.engines.dcf import gordon_implied_growth
        # ConEd: price=43.42, DPS=2.32, ke=7.7%
        g = gordon_implied_growth(
            price=43.42,
            current_dividend=2.32,
            cost_of_equity=0.077,
        )
        assert abs(g - 0.0224) < 0.005

    def test_gordon_zero_growth(self):
        value = gordon_growth_value(
            current_dividend=5.0,
            cost_of_equity=0.10,
            growth_rate=0.0,
        )
        # 5.0 / 0.10 = 50
        assert abs(value - 50.0) < 0.1

    def test_gordon_growth_exceeds_ke_raises(self):
        with pytest.raises(ValueError, match="growth.*exceed"):
            gordon_growth_value(
                current_dividend=2.0,
                cost_of_equity=0.05,
                growth_rate=0.06,
            )
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_dcf.py -v`

- [ ] **Step 3: Write Gordon Growth implementation**

`src/valuation/engines/dcf.py`:
```python
"""DCF valuation engines — all deterministic, no LLM calls.

Models:
- Gordon Growth (single-stage, stable firms)
- FCFF DCF (multi-stage, non-financial firms)
- DDM (multi-stage, financial firms)
"""

from __future__ import annotations


def gordon_growth_value(
    current_dividend: float,
    cost_of_equity: float,
    growth_rate: float,
) -> float:
    """Gordon Growth Model: Value = DPS * (1+g) / (Ke - g).

    For perfectly stable companies (utilities, etc.)

    Args:
        current_dividend: Current dividend per share
        cost_of_equity: Required return on equity (decimal)
        growth_rate: Perpetual growth rate (decimal)

    Returns:
        Intrinsic value per share
    """
    if growth_rate >= cost_of_equity:
        raise ValueError(
            f"growth rate ({growth_rate:.4f}) must not exceed "
            f"cost of equity ({cost_of_equity:.4f})"
        )
    return current_dividend * (1 + growth_rate) / (cost_of_equity - growth_rate)


def gordon_implied_growth(
    price: float,
    current_dividend: float,
    cost_of_equity: float,
) -> float:
    """Reverse-engineer implied growth rate from market price.

    g = (P * Ke - DPS) / (P + DPS)
    """
    return (price * cost_of_equity - current_dividend) / (price + current_dividend)
```

- [ ] **Step 4: Run tests**

Run: `python3 -m pytest tests/test_dcf.py -v`

Expected: All 4 PASS

- [ ] **Step 5: Commit**

```bash
git add src/valuation/engines/dcf.py tests/test_dcf.py
git commit -m "feat: add Gordon Growth model with implied growth rate"
```

---

## Task 4: DCF Engine — FCFF Multi-Stage Model

**Files:**
- Modify: `src/valuation/engines/dcf.py`
- Modify: `tests/test_dcf.py`

- [ ] **Step 1: Write failing tests for FCFF**

Append to `tests/test_dcf.py`:
```python
from valuation.engines.dcf import (
    compute_fcff,
    compute_terminal_value,
    discount_cashflows,
    fcff_valuation,
    interpolate_params,
)


class TestFCFF:
    def test_compute_fcff(self):
        fcff = compute_fcff(
            ebit_after_tax=100.0,
            reinvestment_rate=0.30,
        )
        # FCFF = EBIT(1-t) * (1 - reinvestment_rate) = 100 * 0.70 = 70
        assert abs(fcff - 70.0) < 0.01

    def test_compute_fcff_negative_reinvestment(self):
        # Distressed/declining: negative reinvestment = capital being returned
        fcff = compute_fcff(
            ebit_after_tax=100.0,
            reinvestment_rate=-0.30,
        )
        # FCFF = 100 * (1 - (-0.3)) = 100 * 1.3 = 130
        assert abs(fcff - 130.0) < 0.01


class TestTerminalValue:
    def test_terminal_value(self):
        tv = compute_terminal_value(
            final_ebit_after_tax=100.0,
            stable_growth=0.03,
            stable_roc=0.10,
            wacc=0.08,
        )
        # Stable reinvestment = g/ROC = 0.03/0.10 = 0.30
        # FCFF_terminal = 100*(1+0.03)*(1-0.30) = 103*0.70 = 72.1
        # TV = 72.1 / (0.08-0.03) = 72.1/0.05 = 1442.0
        assert abs(tv - 1442.0) < 1.0

    def test_terminal_value_wacc_equals_growth_raises(self):
        with pytest.raises(ValueError):
            compute_terminal_value(
                final_ebit_after_tax=100.0,
                stable_growth=0.05,
                stable_roc=0.10,
                wacc=0.05,
            )


class TestDiscount:
    def test_discount_constant_wacc(self):
        cashflows = [70.0, 70.0, 70.0]
        waccs = [0.10, 0.10, 0.10]
        pvs = discount_cashflows(cashflows, waccs)
        assert abs(pvs[0] - 63.636) < 0.01  # 70/1.10
        assert abs(pvs[1] - 57.851) < 0.01  # 70/1.21
        assert abs(pvs[2] - 52.592) < 0.01  # 70/1.331

    def test_discount_varying_wacc(self):
        cashflows = [100.0, 110.0]
        waccs = [0.10, 0.08]
        pvs = discount_cashflows(cashflows, waccs)
        assert abs(pvs[0] - 90.909) < 0.01  # 100/1.10
        assert abs(pvs[1] - 92.593) < 0.01  # 110/(1.10*1.08)


class TestInterpolation:
    def test_no_transition(self):
        # 5 years, no gradual adjust
        params = interpolate_params(
            high_growth_value=0.12,
            stable_value=0.04,
            n_years=5,
            gradual=False,
        )
        assert len(params) == 5
        assert all(p == 0.12 for p in params)

    def test_gradual_transition(self):
        # 10 years, first 5 at HG, years 6-10 interpolate
        params = interpolate_params(
            high_growth_value=0.12,
            stable_value=0.04,
            n_years=10,
            gradual=True,
        )
        assert len(params) == 10
        assert params[0] == 0.12  # year 1 full HG
        assert params[4] == 0.12  # year 5 full HG
        assert abs(params[9] - 0.04) < 0.001  # year 10 = stable


class TestFCFFValuation:
    def test_simple_valuation(self):
        result = fcff_valuation(
            current_ebit_after_tax=100.0,
            growth_rates=[0.05, 0.05, 0.05],
            reinvestment_rates=[0.30, 0.30, 0.30],
            waccs=[0.10, 0.10, 0.10],
            stable_growth=0.03,
            stable_roc=0.10,
            stable_wacc=0.10,
        )
        assert result["enterprise_value"] > 0
        assert result["pv_high_growth"] > 0
        assert result["pv_terminal"] > 0
        assert len(result["yearly_fcff"]) == 3
        assert len(result["yearly_pv"]) == 3

    def test_bridge_to_equity(self):
        result = fcff_valuation(
            current_ebit_after_tax=100.0,
            growth_rates=[0.05],
            reinvestment_rates=[0.30],
            waccs=[0.10],
            stable_growth=0.03,
            stable_roc=0.10,
            stable_wacc=0.10,
            cash=50.0,
            debt=200.0,
            shares_outstanding=10.0,
        )
        assert result["equity_value"] == result["enterprise_value"] + 50.0 - 200.0
        assert result["equity_value_per_share"] == result["equity_value"] / 10.0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_dcf.py -v -k "FCFF or Terminal or Discount or Interpolation"`

- [ ] **Step 3: Write FCFF implementation**

Append to `src/valuation/engines/dcf.py`:
```python
def compute_fcff(ebit_after_tax: float, reinvestment_rate: float) -> float:
    """FCFF = EBIT(1-t) * (1 - reinvestment_rate).

    Reinvestment_rate = (CapEx - Depreciation + Change_in_WC) / EBIT(1-t)
    Negative reinvestment means the firm is shrinking (distressed).
    """
    return ebit_after_tax * (1 - reinvestment_rate)


def compute_terminal_value(
    final_ebit_after_tax: float,
    stable_growth: float,
    stable_roc: float,
    wacc: float,
) -> float:
    """Terminal Value = FCFF_{n+1} / (WACC - g).

    Stable reinvestment = g / ROC (sustainable reinvestment in perpetuity).
    """
    if wacc <= stable_growth:
        raise ValueError(
            f"WACC ({wacc:.4f}) must exceed stable growth ({stable_growth:.4f})"
        )
    stable_reinvestment = stable_growth / stable_roc
    fcff_terminal = final_ebit_after_tax * (1 + stable_growth) * (1 - stable_reinvestment)
    return fcff_terminal / (wacc - stable_growth)


def discount_cashflows(
    cashflows: list[float], waccs: list[float]
) -> list[float]:
    """Discount a series of cash flows at (potentially varying) discount rates.

    Returns list of present values. Uses cumulative discounting:
    PV_t = CF_t / product(1 + WACC_i, i=1..t)
    """
    pvs = []
    cumulative = 1.0
    for cf, w in zip(cashflows, waccs):
        cumulative *= 1 + w
        pvs.append(cf / cumulative)
    return pvs


def interpolate_params(
    high_growth_value: float,
    stable_value: float,
    n_years: int,
    gradual: bool = True,
) -> list[float]:
    """Generate per-year parameter values with optional gradual transition.

    If gradual=True, first half stays at HG value, second half linearly
    interpolates to stable value. If gradual=False, all years use HG value.
    """
    if not gradual or n_years <= 1:
        return [high_growth_value] * n_years

    first_half = n_years // 2
    second_half = n_years - first_half
    result = [high_growth_value] * first_half
    for i in range(1, second_half + 1):
        frac = i / second_half
        value = high_growth_value + (stable_value - high_growth_value) * frac
        result.append(value)
    return result


def fcff_valuation(
    current_ebit_after_tax: float,
    growth_rates: list[float],
    reinvestment_rates: list[float],
    waccs: list[float],
    stable_growth: float,
    stable_roc: float,
    stable_wacc: float,
    cash: float = 0.0,
    debt: float = 0.0,
    non_operating_assets: float = 0.0,
    options_value: float = 0.0,
    shares_outstanding: float = 1.0,
) -> dict:
    """Full FCFF DCF valuation.

    Projects EBIT(1-t) forward using growth rates, computes FCFF using
    reinvestment rates, discounts at (potentially varying) WACCs,
    adds terminal value, and bridges to equity value per share.

    Args:
        current_ebit_after_tax: Starting EBIT * (1 - tax rate)
        growth_rates: Growth rate per projection year
        reinvestment_rates: Reinvestment rate per year
        waccs: WACC per year (can vary for gradual transition)
        stable_growth: Terminal growth rate
        stable_roc: Terminal return on capital
        stable_wacc: Terminal WACC
        cash: Cash & marketable securities
        debt: Total debt (including lease debt)
        non_operating_assets: Cross-holdings, other non-operating assets
        options_value: Value of employee stock options (subtracted)
        shares_outstanding: Number of shares

    Returns:
        Dict with enterprise_value, equity_value, equity_value_per_share,
        pv_high_growth, pv_terminal, yearly_fcff, yearly_pv, terminal_value
    """
    n = len(growth_rates)

    # Project EBIT(1-t) and FCFF for each year
    ebit_at = current_ebit_after_tax
    yearly_ebit_at = []
    yearly_fcff = []
    for g, r in zip(growth_rates, reinvestment_rates):
        ebit_at = ebit_at * (1 + g)
        yearly_ebit_at.append(ebit_at)
        yearly_fcff.append(compute_fcff(ebit_at, r))

    # Discount FCFF
    yearly_pv = discount_cashflows(yearly_fcff, waccs)
    pv_high_growth = sum(yearly_pv)

    # Terminal value
    terminal_value = compute_terminal_value(
        final_ebit_after_tax=yearly_ebit_at[-1] if yearly_ebit_at else current_ebit_after_tax,
        stable_growth=stable_growth,
        stable_roc=stable_roc,
        wacc=stable_wacc,
    )

    # Discount terminal value
    cumulative_discount = 1.0
    for w in waccs:
        cumulative_discount *= 1 + w
    pv_terminal = terminal_value / cumulative_discount

    # Enterprise value
    enterprise_value = pv_high_growth + pv_terminal

    # Bridge to equity
    equity_value = enterprise_value + cash - debt + non_operating_assets - options_value
    equity_value_per_share = equity_value / shares_outstanding if shares_outstanding > 0 else 0

    return {
        "enterprise_value": enterprise_value,
        "equity_value": equity_value,
        "equity_value_per_share": equity_value_per_share,
        "pv_high_growth": pv_high_growth,
        "pv_terminal": pv_terminal,
        "terminal_value": terminal_value,
        "yearly_fcff": yearly_fcff,
        "yearly_pv": yearly_pv,
        "yearly_ebit_at": yearly_ebit_at,
    }
```

- [ ] **Step 4: Run tests**

Run: `python3 -m pytest tests/test_dcf.py -v`

Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/valuation/engines/dcf.py tests/test_dcf.py
git commit -m "feat: add FCFF DCF engine with multi-stage projection and terminal value"
```

---

## Task 5: DCF Engine — DDM for Financial Firms

**Files:**
- Modify: `src/valuation/engines/dcf.py`
- Modify: `tests/test_dcf.py`

- [ ] **Step 1: Write failing tests for DDM**

Append to `tests/test_dcf.py`:
```python
from valuation.engines.dcf import ddm_valuation


class TestDDM:
    def test_goldman_valuation(self):
        # Goldman: EPS=16.77, DPS=1.40, ROE=13.19%, Ke=10.4%
        # 10yr HG, gradual transition, stable g=4%, stable ROE=10%, stable Ke=9.5%
        growth_rates = interpolate_params(0.1209, 0.04, 10, gradual=True)
        payout_rates = interpolate_params(0.0835, 0.60, 10, gradual=True)
        cost_of_equities = interpolate_params(0.104, 0.095, 10, gradual=True)

        result = ddm_valuation(
            current_eps=16.77,
            growth_rates=growth_rates,
            payout_rates=payout_rates,
            cost_of_equities=cost_of_equities,
            stable_growth=0.04,
            stable_roe=0.10,
            stable_ke=0.095,
        )
        # Damodaran gets $222.49
        assert abs(result["value_per_share"] - 222.49) < 15.0  # within 7%

    def test_wellsfargo_valuation(self):
        # Wells Fargo: EPS=2.16, DPS=1.18, ROE=13.5%, Ke=9.6%
        # 5yr HG, stable g=3%, stable ROE=7.6%, stable Ke=7.6%
        growth_rates = interpolate_params(0.061, 0.03, 5, gradual=True)
        payout_rates = interpolate_params(0.546, 0.605, 5, gradual=True)
        cost_of_equities = interpolate_params(0.096, 0.076, 5, gradual=True)

        result = ddm_valuation(
            current_eps=2.16,
            growth_rates=growth_rates,
            payout_rates=payout_rates,
            cost_of_equities=cost_of_equities,
            stable_growth=0.03,
            stable_roe=0.076,
            stable_ke=0.076,
        )
        # Damodaran gets $30.28
        assert abs(result["value_per_share"] - 30.28) < 5.0

    def test_ddm_simple(self):
        result = ddm_valuation(
            current_eps=10.0,
            growth_rates=[0.05, 0.05],
            payout_rates=[0.50, 0.50],
            cost_of_equities=[0.10, 0.10],
            stable_growth=0.03,
            stable_roe=0.10,
            stable_ke=0.10,
        )
        assert result["value_per_share"] > 0
        assert result["pv_dividends"] > 0
        assert result["pv_terminal"] > 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_dcf.py::TestDDM -v`

- [ ] **Step 3: Write DDM implementation**

Append to `src/valuation/engines/dcf.py`:
```python
def ddm_valuation(
    current_eps: float,
    growth_rates: list[float],
    payout_rates: list[float],
    cost_of_equities: list[float],
    stable_growth: float,
    stable_roe: float,
    stable_ke: float,
) -> dict:
    """Dividend Discount Model for financial firms.

    Projects EPS and DPS forward, discounts dividends at cost of equity,
    adds terminal value. No enterprise value bridge — direct equity value.

    Args:
        current_eps: Current earnings per share
        growth_rates: EPS growth rate per year
        payout_rates: Dividend payout ratio per year
        cost_of_equities: Cost of equity per year
        stable_growth: Terminal growth rate
        stable_roe: Terminal return on equity
        stable_ke: Terminal cost of equity

    Returns:
        Dict with value_per_share, pv_dividends, pv_terminal,
        terminal_price, yearly_eps, yearly_dps, yearly_pv
    """
    n = len(growth_rates)

    # Project EPS and DPS
    eps = current_eps
    yearly_eps = []
    yearly_dps = []
    for g, p in zip(growth_rates, payout_rates):
        eps = eps * (1 + g)
        dps = eps * p
        yearly_eps.append(eps)
        yearly_dps.append(dps)

    # Discount dividends
    yearly_pv = discount_cashflows(yearly_dps, cost_of_equities)
    pv_dividends = sum(yearly_pv)

    # Terminal price
    stable_payout = 1 - stable_growth / stable_roe if stable_roe > 0 else 1.0
    final_eps = yearly_eps[-1] if yearly_eps else current_eps
    terminal_dps = final_eps * (1 + stable_growth) * stable_payout
    if stable_ke <= stable_growth:
        raise ValueError(
            f"Stable Ke ({stable_ke:.4f}) must exceed stable growth ({stable_growth:.4f})"
        )
    terminal_price = terminal_dps / (stable_ke - stable_growth)

    # Discount terminal price
    cumulative_discount = 1.0
    for ke in cost_of_equities:
        cumulative_discount *= 1 + ke
    pv_terminal = terminal_price / cumulative_discount

    value_per_share = pv_dividends + pv_terminal

    return {
        "value_per_share": value_per_share,
        "pv_dividends": pv_dividends,
        "pv_terminal": pv_terminal,
        "terminal_price": terminal_price,
        "yearly_eps": yearly_eps,
        "yearly_dps": yearly_dps,
        "yearly_pv": yearly_pv,
    }
```

- [ ] **Step 4: Run tests**

Run: `python3 -m pytest tests/test_dcf.py -v`

Expected: All PASS (Goldman and Wells Fargo within tolerance)

- [ ] **Step 5: Commit**

```bash
git add src/valuation/engines/dcf.py tests/test_dcf.py
git commit -m "feat: add DDM engine for financial firm valuation"
```

---

## Task 6: Sensitivity Table Generator

**Files:**
- Modify: `src/valuation/engines/dcf.py`
- Modify: `tests/test_dcf.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_dcf.py`:
```python
from valuation.engines.dcf import sensitivity_table


class TestSensitivity:
    def test_gordon_sensitivity(self):
        table = sensitivity_table(
            base_params={"current_dividend": 2.32, "cost_of_equity": 0.077, "growth_rate": 0.021},
            vary_param="growth_rate",
            vary_values=[-0.01, 0.0, 0.01, 0.021, 0.03, 0.04],
            valuation_fn=gordon_growth_value,
        )
        assert len(table) == 6
        # g=2.1% should give ~42.30
        assert abs(table[0.021] - 42.30) < 0.5

    def test_two_way_sensitivity(self):
        from valuation.engines.dcf import two_way_sensitivity_table
        table = two_way_sensitivity_table(
            base_params={"current_dividend": 2.32, "cost_of_equity": 0.077, "growth_rate": 0.021},
            row_param="growth_rate",
            row_values=[0.01, 0.02, 0.03],
            col_param="cost_of_equity",
            col_values=[0.06, 0.07, 0.08],
            valuation_fn=gordon_growth_value,
        )
        assert len(table) == 3  # 3 rows
        assert len(table[0.01]) == 3  # 3 columns each
        # g=2%, ke=8% -> 2.32*1.02/(0.08-0.02) = 39.44
        assert abs(table[0.02][0.08] - 39.44) < 0.5
```

- [ ] **Step 2: Run tests, verify fail**

- [ ] **Step 3: Write implementation**

Append to `src/valuation/engines/dcf.py`:
```python
from typing import Callable


def sensitivity_table(
    base_params: dict,
    vary_param: str,
    vary_values: list[float],
    valuation_fn: Callable,
) -> dict[float, float]:
    """One-way sensitivity: vary one parameter, compute value for each.

    Returns {param_value: valuation_result}
    """
    results = {}
    for v in vary_values:
        params = {**base_params, vary_param: v}
        try:
            results[v] = valuation_fn(**params)
        except (ValueError, ZeroDivisionError):
            results[v] = float("nan")
    return results


def two_way_sensitivity_table(
    base_params: dict,
    row_param: str,
    row_values: list[float],
    col_param: str,
    col_values: list[float],
    valuation_fn: Callable,
) -> dict[float, dict[float, float]]:
    """Two-way sensitivity: vary two parameters.

    Returns {row_value: {col_value: valuation_result}}
    """
    results = {}
    for rv in row_values:
        results[rv] = {}
        for cv in col_values:
            params = {**base_params, row_param: rv, col_param: cv}
            try:
                results[rv][cv] = valuation_fn(**params)
            except (ValueError, ZeroDivisionError):
                results[rv][cv] = float("nan")
    return results
```

- [ ] **Step 4: Run tests**

Run: `python3 -m pytest tests/test_dcf.py -v`

Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/valuation/engines/dcf.py tests/test_dcf.py
git commit -m "feat: add one-way and two-way sensitivity table generators"
```

---

## Task 7: Golden Tests — Extract Ground Truth from Examples

**Files:**
- Create: `tests/golden/coned.json`
- Create: `tests/golden/goldman.json`
- Create: `tests/golden/3m_precrisis.json`
- Create: `tests/test_golden.py`

- [ ] **Step 1: Create golden test JSON files**

`tests/golden/coned.json`:
```json
{
    "company": "Consolidated Edison",
    "file": "coned08.xls",
    "model": "gordon_growth",
    "inputs": {
        "current_dividend": 2.32,
        "cost_of_equity": 0.077,
        "growth_rate": 0.021
    },
    "expected": {
        "value_per_share": 42.30
    },
    "tolerance": 0.5
}
```

`tests/golden/goldman.json`:
```json
{
    "company": "Goldman Sachs",
    "file": "goldman.xls",
    "model": "ddm",
    "inputs": {
        "current_eps": 16.77,
        "high_growth_rate": 0.1209,
        "stable_growth": 0.04,
        "high_payout": 0.0835,
        "stable_payout": 0.60,
        "high_ke": 0.104,
        "stable_ke": 0.095,
        "stable_roe": 0.10,
        "n_years": 10,
        "gradual": true
    },
    "expected": {
        "value_per_share": 222.49
    },
    "tolerance_pct": 0.10
}
```

`tests/golden/3m_precrisis.json`:
```json
{
    "company": "3M Pre-Crisis",
    "file": "3Mprecrisis.xls",
    "model": "fcff",
    "inputs": {
        "current_ebit": 5344.0,
        "tax_rate": 0.35,
        "roc": 0.25,
        "reinvestment_rate": 0.30,
        "risk_free_rate": 0.0372,
        "erp": 0.04,
        "beta": 1.36,
        "debt_ratio": 0.081,
        "cost_of_debt": 0.0442,
        "n_years": 5,
        "stable_growth": 0.03,
        "stable_roc": 0.25,
        "stable_beta": 1.0,
        "stable_debt_ratio": 0.20,
        "gradual": true,
        "cash": 3253.0,
        "debt": 5297.0,
        "options_value": 1216.0,
        "shares_outstanding": 699.0
    },
    "expected": {
        "value_per_share": 82.19
    },
    "tolerance_pct": 0.10
}
```

- [ ] **Step 2: Write golden test runner**

`tests/test_golden.py`:
```python
"""Golden tests: validate engine output against Damodaran's example spreadsheets."""

import json
import pathlib
import pytest
from valuation.engines.dcf import (
    gordon_growth_value,
    ddm_valuation,
    fcff_valuation,
    interpolate_params,
)
from valuation.agents.risk_assessor import compute_cost_of_equity, compute_wacc

GOLDEN_DIR = pathlib.Path(__file__).parent / "golden"


def test_coned_gordon_growth():
    with open(GOLDEN_DIR / "coned.json") as f:
        tc = json.load(f)
    value = gordon_growth_value(**tc["inputs"])
    expected = tc["expected"]["value_per_share"]
    assert abs(value - expected) < tc["tolerance"], (
        f"ConEd: got {value:.2f}, expected {expected:.2f}"
    )


def test_goldman_ddm():
    with open(GOLDEN_DIR / "goldman.json") as f:
        tc = json.load(f)
    inp = tc["inputs"]
    growth_rates = interpolate_params(inp["high_growth_rate"], inp["stable_growth"], inp["n_years"], inp["gradual"])
    payout_rates = interpolate_params(inp["high_payout"], inp["stable_payout"], inp["n_years"], inp["gradual"])
    ke_rates = interpolate_params(inp["high_ke"], inp["stable_ke"], inp["n_years"], inp["gradual"])

    result = ddm_valuation(
        current_eps=inp["current_eps"],
        growth_rates=growth_rates,
        payout_rates=payout_rates,
        cost_of_equities=ke_rates,
        stable_growth=inp["stable_growth"],
        stable_roe=inp["stable_roe"],
        stable_ke=inp["stable_ke"],
    )
    expected = tc["expected"]["value_per_share"]
    tolerance = expected * tc["tolerance_pct"]
    assert abs(result["value_per_share"] - expected) < tolerance, (
        f"Goldman: got {result['value_per_share']:.2f}, expected {expected:.2f}"
    )


def test_3m_fcff():
    with open(GOLDEN_DIR / "3m_precrisis.json") as f:
        tc = json.load(f)
    inp = tc["inputs"]

    ebit_after_tax = inp["current_ebit"] * (1 - inp["tax_rate"])

    # Compute WACC for high growth
    ke = compute_cost_of_equity(inp["risk_free_rate"], inp["beta"], inp["erp"])
    wacc_hg = compute_wacc(ke, inp["cost_of_debt"], inp["tax_rate"],
                           1 - inp["debt_ratio"], inp["debt_ratio"])

    ke_stable = compute_cost_of_equity(inp["risk_free_rate"], inp["stable_beta"], inp["erp"])
    wacc_stable = compute_wacc(ke_stable, inp["cost_of_debt"], inp["tax_rate"],
                               1 - inp["stable_debt_ratio"], inp["stable_debt_ratio"])

    growth_rate = inp["roc"] * inp["reinvestment_rate"]  # 7.5%
    growth_rates = interpolate_params(growth_rate, inp["stable_growth"], inp["n_years"], inp["gradual"])
    reinv_rates = interpolate_params(inp["reinvestment_rate"], inp["stable_growth"] / inp["stable_roc"], inp["n_years"], inp["gradual"])
    waccs = interpolate_params(wacc_hg, wacc_stable, inp["n_years"], inp["gradual"])

    result = fcff_valuation(
        current_ebit_after_tax=ebit_after_tax,
        growth_rates=growth_rates,
        reinvestment_rates=reinv_rates,
        waccs=waccs,
        stable_growth=inp["stable_growth"],
        stable_roc=inp["stable_roc"],
        stable_wacc=wacc_stable,
        cash=inp["cash"],
        debt=inp["debt"],
        options_value=inp["options_value"],
        shares_outstanding=inp["shares_outstanding"],
    )
    expected = tc["expected"]["value_per_share"]
    tolerance = expected * tc["tolerance_pct"]
    assert abs(result["equity_value_per_share"] - expected) < tolerance, (
        f"3M: got {result['equity_value_per_share']:.2f}, expected {expected:.2f}"
    )
```

- [ ] **Step 3: Run golden tests**

Run: `python3 -m pytest tests/test_golden.py -v`

Expected: All 3 PASS within tolerance (ConEd <$0.50, Goldman <10%, 3M <10%)

- [ ] **Step 4: Run full test suite**

Run: `python3 -m pytest -v -k "not network"`

Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add tests/golden/ tests/test_golden.py
git commit -m "test: add golden tests validating DCF engines against Damodaran examples"
```

---

## Task 8: Sprint 2 Integration Test & Push

**Files:**
- Create: `tests/test_integration_sprint2.py`

- [ ] **Step 1: Write integration test**

`tests/test_integration_sprint2.py`:
```python
"""Sprint 2 integration: risk assessor + DCF engines + Damodaran data."""

import pytest
from valuation.agents.risk_assessor import (
    compute_cost_of_equity,
    compute_cost_of_debt,
    compute_wacc,
    get_synthetic_rating,
    relever_beta,
)
from valuation.engines.dcf import (
    fcff_valuation,
    ddm_valuation,
    gordon_growth_value,
    interpolate_params,
    sensitivity_table,
)
from valuation.data.damodaran_loader import DamodaranLoader


class TestRiskWithDamodaranData:
    def test_wacc_for_software_industry(self, damodaran_data_dir):
        """Compute WACC using Damodaran data and verify it's close to published value."""
        loader = DamodaranLoader(damodaran_data_dir)

        # Get industry beta
        beta_row = loader.lookup("betas", "Software (System & Application)")
        unlevered_beta = float(beta_row["Unlevered beta corrected for cash"])
        de_ratio = float(beta_row["D/E Ratio"])
        tax_rate = float(beta_row["Effective Tax rate"])

        # Re-lever beta
        levered_beta = relever_beta(unlevered_beta, de_ratio, tax_rate)

        # Cost of equity
        ke = compute_cost_of_equity(
            risk_free_rate=0.0395, beta=levered_beta, erp=0.0446
        )

        # Get industry WACC for comparison
        wacc_row = loader.lookup("wacc", "Software (System & Application)")
        published_wacc = float(wacc_row["Cost of Capital"])

        # Our computed Ke should be in reasonable range
        assert 0.05 < ke < 0.20, f"Ke={ke} out of range"

        # Published WACC should be in reasonable range
        assert 0.05 < published_wacc < 0.20, f"Published WACC={published_wacc} out of range"


class TestEndToEndValuation:
    def test_stable_utility_valuation(self):
        """Gordon Growth for a utility: simple end-to-end."""
        ke = compute_cost_of_equity(0.041, 0.80, 0.045)
        value = gordon_growth_value(2.32, ke, 0.021)
        assert 30 < value < 60  # reasonable range for a utility

    def test_growth_company_fcff(self):
        """FCFF DCF for a growth company: end-to-end."""
        ke = compute_cost_of_equity(0.03, 1.3, 0.045)
        wacc = compute_wacc(ke, 0.04, 0.25, 0.85, 0.15)
        growth_rates = interpolate_params(0.15, 0.03, 10, gradual=True)
        reinv_rates = interpolate_params(0.60, 0.30, 10, gradual=True)
        waccs = [wacc] * 10

        result = fcff_valuation(
            current_ebit_after_tax=1000.0,
            growth_rates=growth_rates,
            reinvestment_rates=reinv_rates,
            waccs=waccs,
            stable_growth=0.03,
            stable_roc=0.12,
            stable_wacc=wacc,
            cash=500.0,
            debt=2000.0,
            shares_outstanding=100.0,
        )
        assert result["equity_value_per_share"] > 0
        assert result["pv_terminal"] > result["pv_high_growth"]  # typical for growth company
```

- [ ] **Step 2: Run all tests**

Run: `python3 -m pytest -v -k "not network"`

Expected: All PASS

- [ ] **Step 3: Commit and push**

```bash
git add tests/test_integration_sprint2.py
git commit -m "test: add Sprint 2 integration tests for risk + DCF engines"
git push origin main
```

---

## Sprint 2 Completion Checklist

- [ ] `python3 -m pytest -v -k "not network"` — all tests pass
- [ ] Synthetic rating tables cover all 3 firm types (15 bands each)
- [ ] CAPM, Hamada beta, WACC formulas are correct
- [ ] Gordon Growth reproduces ConEd ($42.30 ± $0.50)
- [ ] FCFF DCF reproduces 3M ($82.19 ± 10%)
- [ ] DDM reproduces Goldman ($222.49 ± 10%)
- [ ] Sensitivity tables work for any valuation function
- [ ] All engines are pure functions — no LLM, no side effects
- [ ] Gradual transition (3-stage) interpolation works correctly
