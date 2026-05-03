# Sprint 4: Intelligence — Growth Estimation, Excess Returns, Confidence Scoring, Cross-Validation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the intelligence layer — estimate growth rates from fundamentals only (no analyst consensus), value financial firms via excess returns, score confidence deterministically, and cross-validate outputs across models.

**Architecture:** Four independent Python modules. All math is deterministic Python — no LLM calls. Growth estimator uses company financials + Damodaran industry data only. I/B/E/S data is never an input; it appears in the final report as a comparison alongside our estimate. The excess returns model is equity-side only (no WACC, no enterprise value).

**Tech Stack:** Python 3.12, pandas, numpy, pytest, dataclasses

**Key constraints:**
- ALL math deterministic Python, no LLM
- Growth estimator uses ONLY company fundamentals + Damodaran industry data, NEVER analyst consensus
- I/B/E/S data is comparison-only (shown in report alongside our estimate, never an input)
- Excess returns model is equity-side only (no WACC, no enterprise value)
- Claude Code picks/adjusts growth rates later — the estimator returns all three methods with reasoning

**Assumes Sprint 3 is complete:**
- `src/valuation/agents/industry_mapper.py` — maps company to Damodaran industry, returns benchmarks
- `src/valuation/engines/relative.py` — computes implied values from PE, EV/EBITDA, PBV, PS vs industry
- `src/valuation/agents/classifier.py` — classifies as mature|growth|young|distressed|cyclical|financial

---

## File Structure

| File | Responsibility |
|------|---------------|
| `src/valuation/agents/growth_estimator.py` | Compute growth rates from fundamentals: historical CAGR, fundamental EPS growth, fundamental EBIT growth |
| `src/valuation/engines/excess_returns.py` | Equity excess return model for financial firms (banks) |
| `src/valuation/scoring/confidence.py` | Deterministic confidence scoring: data completeness, model agreement, assumption sensitivity, industry coverage |
| `src/valuation/agents/cross_validator.py` | Compare outputs across DCF, relative, excess returns; compute divergence and flags |
| `tests/test_growth_estimator.py` | Tests for growth estimation |
| `tests/test_excess_returns.py` | Tests for excess returns engine (includes Goldman and Wells Fargo golden tests) |
| `tests/test_confidence.py` | Tests for confidence scoring |
| `tests/test_cross_validator.py` | Tests for cross-validation |
| `tests/test_integration_sprint4.py` | End-to-end integration test |

---

## Task 1: Growth Estimator — Historical CAGR

**Files:**
- Create: `src/valuation/agents/growth_estimator.py`
- Create: `tests/test_growth_estimator.py`

- [ ] **Step 1: Write failing tests for historical CAGR**

`tests/test_growth_estimator.py`:
```python
import pandas as pd
import pytest
from valuation.agents.growth_estimator import (
    compute_historical_cagr,
    GrowthEstimate,
)


class TestHistoricalCAGR:
    def test_revenue_cagr_positive(self):
        """Revenue growing from 100 to 146.41 over 4 years = 10% CAGR."""
        income = pd.DataFrame({
            "Total Revenue": [100.0, 110.0, 121.0, 133.1, 146.41],
        })
        result = compute_historical_cagr(income, column="Total Revenue")
        assert isinstance(result, GrowthEstimate)
        assert abs(result.value - 0.10) < 0.005
        assert result.method == "historical_cagr"
        assert "Total Revenue" in result.reasoning

    def test_revenue_cagr_negative(self):
        """Declining revenue: 200, 180, 162, 145.8 => CAGR ~ -10%."""
        income = pd.DataFrame({
            "Total Revenue": [200.0, 180.0, 162.0, 145.8],
        })
        result = compute_historical_cagr(income, column="Total Revenue")
        assert abs(result.value - (-0.10)) < 0.005

    def test_net_income_cagr(self):
        """Net income CAGR from 50 to 80 over 3 years."""
        income = pd.DataFrame({
            "Net Income": [50.0, 60.0, 70.0, 80.0],
        })
        result = compute_historical_cagr(income, column="Net Income")
        # CAGR = (80/50)^(1/3) - 1 = 0.1696
        assert abs(result.value - 0.1696) < 0.005

    def test_cagr_single_row_returns_none(self):
        """Cannot compute CAGR with fewer than 2 data points."""
        income = pd.DataFrame({"Total Revenue": [100.0]})
        result = compute_historical_cagr(income, column="Total Revenue")
        assert result is None

    def test_cagr_zero_start_returns_none(self):
        """CAGR undefined when starting value is zero."""
        income = pd.DataFrame({"Total Revenue": [0.0, 100.0, 200.0]})
        result = compute_historical_cagr(income, column="Total Revenue")
        assert result is None

    def test_cagr_negative_start_returns_none(self):
        """CAGR undefined when starting value is negative."""
        income = pd.DataFrame({"Net Income": [-50.0, 20.0, 40.0]})
        result = compute_historical_cagr(income, column="Net Income")
        assert result is None

    def test_cagr_missing_column_returns_none(self):
        """Returns None if the requested column doesn't exist."""
        income = pd.DataFrame({"Other Column": [100.0, 200.0]})
        result = compute_historical_cagr(income, column="Total Revenue")
        assert result is None

    def test_cagr_with_nan_drops_them(self):
        """NaN values are dropped before computing CAGR."""
        income = pd.DataFrame({
            "Total Revenue": [100.0, float("nan"), 121.0],
        })
        result = compute_historical_cagr(income, column="Total Revenue")
        # After dropping NaN: [100, 121], 1 period => CAGR = 0.21
        assert abs(result.value - 0.21) < 0.005
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_growth_estimator.py -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'valuation.agents.growth_estimator'`

- [ ] **Step 3: Write the GrowthEstimate dataclass and historical CAGR**

`src/valuation/agents/growth_estimator.py`:
```python
"""Growth rate estimation from company fundamentals.

Three methods:
  1. Historical CAGR — compound annual growth rate of revenue or net income
  2. Fundamental EPS growth — retention_ratio x ROE
  3. Fundamental EBIT growth — reinvestment_rate x ROC

All methods are deterministic. No LLM calls. No analyst consensus estimates.
I/B/E/S data is never used as an input — it is comparison-only in the final report.

Claude Code picks and adjusts the final growth rate after reviewing all three.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd


@dataclass
class GrowthEstimate:
    """A single growth rate estimate with method and reasoning."""

    value: float
    method: str
    reasoning: str
    inputs: dict[str, Any] | None = None


def compute_historical_cagr(
    financial_df: pd.DataFrame,
    column: str,
) -> GrowthEstimate | None:
    """Compute the CAGR of a financial line item across available years.

    Assumes rows are ordered oldest-first (row 0 = earliest year).
    If the DataFrame is in reverse chronological order (newest first),
    we detect this by comparing index values and reverse.

    Parameters
    ----------
    financial_df : pd.DataFrame
        Income statement or other financial statement DataFrame.
    column : str
        Column name to compute CAGR for (e.g. "Total Revenue", "Net Income").

    Returns
    -------
    GrowthEstimate or None
        None if CAGR cannot be computed (missing data, <2 points, zero/negative start).
    """
    if column not in financial_df.columns:
        return None

    series = financial_df[column].dropna()
    if len(series) < 2:
        return None

    # Ensure oldest-first ordering: if the DataFrame index is a DatetimeIndex
    # or monotonically decreasing integers, reverse it
    values = series.values.tolist()
    if hasattr(series.index, 'year') or (
        len(series.index) > 1
        and isinstance(series.index[0], (int, float))
        and series.index[0] > series.index[-1]
    ):
        values = list(reversed(values))

    start_val = float(values[0])
    end_val = float(values[-1])
    n_periods = len(values) - 1

    if start_val <= 0:
        return None

    if end_val <= 0:
        # Negative ending value: CAGR is not meaningful
        return None

    cagr = (end_val / start_val) ** (1.0 / n_periods) - 1.0

    return GrowthEstimate(
        value=cagr,
        method="historical_cagr",
        reasoning=(
            f"{column} CAGR over {n_periods} periods: "
            f"from {start_val:,.2f} to {end_val:,.2f} = {cagr:.2%}"
        ),
        inputs={
            "column": column,
            "start_value": start_val,
            "end_value": end_val,
            "n_periods": n_periods,
        },
    )
```

- [ ] **Step 4: Run tests**

Run: `python3 -m pytest tests/test_growth_estimator.py -v`

Expected: All 8 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/valuation/agents/growth_estimator.py tests/test_growth_estimator.py
git commit -m "feat: add historical CAGR growth estimator"
```

---

## Task 2: Growth Estimator — Fundamental EPS and EBIT Growth

**Files:**
- Modify: `src/valuation/agents/growth_estimator.py`
- Modify: `tests/test_growth_estimator.py`

- [ ] **Step 1: Write failing tests for fundamental growth**

Append to `tests/test_growth_estimator.py`:
```python
from valuation.agents.growth_estimator import (
    compute_fundamental_eps_growth,
    compute_fundamental_ebit_growth,
    estimate_all_growth_rates,
)
from valuation.context import ValuationContext


class TestFundamentalEPSGrowth:
    def test_basic_eps_growth(self):
        """g_EPS = retention_ratio x ROE = 0.40 x 0.15 = 6%."""
        result = compute_fundamental_eps_growth(
            net_income=150.0,
            book_equity=1000.0,
            dividends_paid=90.0,
        )
        assert isinstance(result, GrowthEstimate)
        # retention = 1 - 90/150 = 0.40, ROE = 150/1000 = 0.15
        # g = 0.40 * 0.15 = 0.06
        assert abs(result.value - 0.06) < 0.001
        assert result.method == "fundamental_eps"
        assert "retention" in result.reasoning.lower()

    def test_eps_growth_no_dividends(self):
        """If no dividends, retention = 1.0, g = ROE."""
        result = compute_fundamental_eps_growth(
            net_income=200.0,
            book_equity=1000.0,
            dividends_paid=0.0,
        )
        # retention = 1.0, ROE = 0.20, g = 0.20
        assert abs(result.value - 0.20) < 0.001

    def test_eps_growth_full_payout(self):
        """If 100% payout, retention = 0, g = 0."""
        result = compute_fundamental_eps_growth(
            net_income=100.0,
            book_equity=1000.0,
            dividends_paid=100.0,
        )
        assert abs(result.value - 0.0) < 0.001

    def test_eps_growth_negative_income_returns_none(self):
        """Cannot compute fundamental growth with negative earnings."""
        result = compute_fundamental_eps_growth(
            net_income=-50.0,
            book_equity=1000.0,
            dividends_paid=0.0,
        )
        assert result is None

    def test_eps_growth_zero_equity_returns_none(self):
        """Cannot compute ROE with zero equity."""
        result = compute_fundamental_eps_growth(
            net_income=100.0,
            book_equity=0.0,
            dividends_paid=0.0,
        )
        assert result is None

    def test_eps_growth_negative_equity_returns_none(self):
        """Negative equity makes ROE meaningless."""
        result = compute_fundamental_eps_growth(
            net_income=100.0,
            book_equity=-500.0,
            dividends_paid=0.0,
        )
        assert result is None

    def test_eps_growth_goldman(self):
        """Goldman: ROE=13.19%, Payout=8.35%, Retention=91.65%, g=12.09%."""
        result = compute_fundamental_eps_growth(
            net_income=13.19,
            book_equity=100.0,
            dividends_paid=13.19 * 0.0835,
        )
        # retention = 1 - 0.0835 = 0.9165
        # ROE = 13.19/100 = 0.1319
        # g = 0.9165 * 0.1319 = 0.1209
        assert abs(result.value - 0.1209) < 0.002


class TestFundamentalEBITGrowth:
    def test_basic_ebit_growth(self):
        """g_EBIT = reinvestment_rate x ROC = 0.30 x 0.25 = 7.5%."""
        result = compute_fundamental_ebit_growth(
            ebit_after_tax=250.0,
            total_capital=1000.0,
            net_capex=50.0,
            change_in_wc=25.0,
        )
        assert isinstance(result, GrowthEstimate)
        # reinvestment = (50 + 25) / 250 = 0.30
        # ROC = 250 / 1000 = 0.25
        # g = 0.30 * 0.25 = 0.075
        assert abs(result.value - 0.075) < 0.001
        assert result.method == "fundamental_ebit"
        assert "reinvestment" in result.reasoning.lower()

    def test_ebit_growth_zero_reinvestment(self):
        """No reinvestment => zero growth."""
        result = compute_fundamental_ebit_growth(
            ebit_after_tax=200.0,
            total_capital=1000.0,
            net_capex=0.0,
            change_in_wc=0.0,
        )
        assert abs(result.value - 0.0) < 0.001

    def test_ebit_growth_negative_reinvestment(self):
        """Negative reinvestment (shrinking firm) => negative growth."""
        result = compute_fundamental_ebit_growth(
            ebit_after_tax=200.0,
            total_capital=1000.0,
            net_capex=-50.0,
            change_in_wc=-25.0,
        )
        # reinvestment = (-50 + -25) / 200 = -0.375
        # ROC = 200/1000 = 0.20
        # g = -0.375 * 0.20 = -0.075
        assert abs(result.value - (-0.075)) < 0.001

    def test_ebit_growth_zero_capital_returns_none(self):
        """Cannot compute ROC with zero capital."""
        result = compute_fundamental_ebit_growth(
            ebit_after_tax=200.0,
            total_capital=0.0,
            net_capex=50.0,
            change_in_wc=0.0,
        )
        assert result is None

    def test_ebit_growth_zero_ebit_returns_none(self):
        """Zero EBIT makes reinvestment rate undefined."""
        result = compute_fundamental_ebit_growth(
            ebit_after_tax=0.0,
            total_capital=1000.0,
            net_capex=50.0,
            change_in_wc=0.0,
        )
        assert result is None

    def test_ebit_growth_3m(self):
        """3M pre-crisis: ROC=25%, reinvestment_rate=30%, g=7.5%."""
        result = compute_fundamental_ebit_growth(
            ebit_after_tax=3473.6,  # 5344 * (1-0.35)
            total_capital=13894.4,  # 3473.6 / 0.25
            net_capex=700.0,
            change_in_wc=342.08,  # to make reinv = 0.30
        )
        # reinvestment = (700 + 342.08) / 3473.6 = 0.30
        # ROC = 3473.6 / 13894.4 = 0.25
        # g = 0.30 * 0.25 = 0.075
        assert abs(result.value - 0.075) < 0.002


class TestEstimateAllGrowthRates:
    def test_returns_all_three_methods(self):
        """estimate_all_growth_rates returns a dict with up to 3 GrowthEstimate values."""
        ctx = ValuationContext(ticker="TEST")
        ctx.financials.income_statement = pd.DataFrame({
            "Total Revenue": [100.0, 110.0, 121.0, 133.1],
            "Net Income": [20.0, 22.0, 24.2, 26.62],
            "EBIT": [30.0, 33.0, 36.3, 39.93],
            "Interest Expense": [5.0, 5.0, 5.0, 5.0],
            "Tax Provision": [8.0, 9.0, 10.0, 11.0],
        })
        ctx.financials.balance_sheet = pd.DataFrame({
            "Total Stockholders Equity": [200.0, 210.0, 220.0, 230.0],
            "Total Debt": [100.0, 100.0, 100.0, 100.0],
            "Cash And Cash Equivalents": [20.0, 22.0, 24.0, 26.0],
        })
        ctx.financials.cash_flow = pd.DataFrame({
            "Capital Expenditure": [-15.0, -16.0, -17.0, -18.0],
            "Depreciation And Amortization": [10.0, 10.0, 10.0, 10.0],
        })
        ctx.financials.key_stats = {
            "dividend_per_share": 1.0,
            "shares_outstanding": 10.0,
        }
        ctx.assumptions.tax_rate = 0.25

        result = estimate_all_growth_rates(ctx)
        assert "historical_revenue" in result
        assert "historical_net_income" in result
        assert isinstance(result["historical_revenue"], GrowthEstimate)
        assert isinstance(result["historical_net_income"], GrowthEstimate)

    def test_missing_financials_returns_partial(self):
        """If income_statement is None, historical methods return None."""
        ctx = ValuationContext(ticker="TEST")
        result = estimate_all_growth_rates(ctx)
        assert result["historical_revenue"] is None
        assert result["historical_net_income"] is None
        assert result["fundamental_eps"] is None
        assert result["fundamental_ebit"] is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_growth_estimator.py -v -k "Fundamental or EstimateAll"`

Expected: FAIL with `ImportError`

- [ ] **Step 3: Write fundamental growth implementations**

Append to `src/valuation/agents/growth_estimator.py`:
```python
def compute_fundamental_eps_growth(
    net_income: float,
    book_equity: float,
    dividends_paid: float,
) -> GrowthEstimate | None:
    """Fundamental EPS growth = retention_ratio x ROE.

    Parameters
    ----------
    net_income : float
        Net income for the most recent year.
    book_equity : float
        Total stockholders' equity (book value of equity).
    dividends_paid : float
        Total dividends paid (absolute value, not per-share).

    Returns
    -------
    GrowthEstimate or None
        None if inputs make the calculation undefined.
    """
    if net_income <= 0 or book_equity <= 0:
        return None

    roe = net_income / book_equity
    payout_ratio = dividends_paid / net_income if net_income > 0 else 0.0
    payout_ratio = max(0.0, min(1.0, payout_ratio))  # clamp to [0, 1]
    retention_ratio = 1.0 - payout_ratio
    growth = retention_ratio * roe

    return GrowthEstimate(
        value=growth,
        method="fundamental_eps",
        reasoning=(
            f"Fundamental EPS growth: retention ratio {retention_ratio:.2%} "
            f"x ROE {roe:.2%} = {growth:.2%}. "
            f"(Net income={net_income:,.2f}, Book equity={book_equity:,.2f}, "
            f"Dividends={dividends_paid:,.2f})"
        ),
        inputs={
            "net_income": net_income,
            "book_equity": book_equity,
            "dividends_paid": dividends_paid,
            "roe": roe,
            "retention_ratio": retention_ratio,
            "payout_ratio": payout_ratio,
        },
    )


def compute_fundamental_ebit_growth(
    ebit_after_tax: float,
    total_capital: float,
    net_capex: float,
    change_in_wc: float,
) -> GrowthEstimate | None:
    """Fundamental EBIT growth = reinvestment_rate x ROC.

    Parameters
    ----------
    ebit_after_tax : float
        EBIT * (1 - tax_rate) for the most recent year.
    total_capital : float
        Total invested capital = book equity + total debt - cash.
    net_capex : float
        Capital expenditure minus depreciation.
    change_in_wc : float
        Change in non-cash working capital.

    Returns
    -------
    GrowthEstimate or None
        None if inputs make the calculation undefined.
    """
    if total_capital <= 0 or ebit_after_tax == 0:
        return None

    roc = ebit_after_tax / total_capital
    reinvestment = net_capex + change_in_wc
    reinvestment_rate = reinvestment / ebit_after_tax
    growth = reinvestment_rate * roc

    return GrowthEstimate(
        value=growth,
        method="fundamental_ebit",
        reasoning=(
            f"Fundamental EBIT growth: reinvestment rate {reinvestment_rate:.2%} "
            f"x ROC {roc:.2%} = {growth:.2%}. "
            f"(EBIT(1-t)={ebit_after_tax:,.2f}, Capital={total_capital:,.2f}, "
            f"Net CapEx={net_capex:,.2f}, dWC={change_in_wc:,.2f})"
        ),
        inputs={
            "ebit_after_tax": ebit_after_tax,
            "total_capital": total_capital,
            "net_capex": net_capex,
            "change_in_wc": change_in_wc,
            "roc": roc,
            "reinvestment_rate": reinvestment_rate,
        },
    )


def _safe_float(df: pd.DataFrame, col: str, row: int = -1) -> float | None:
    """Safely extract a float from a DataFrame cell. Returns None on failure."""
    if col not in df.columns:
        return None
    try:
        val = float(df[col].iloc[row])
        if pd.isna(val):
            return None
        return val
    except (IndexError, ValueError, TypeError):
        return None


def estimate_all_growth_rates(
    ctx: "ValuationContext",
) -> dict[str, GrowthEstimate | None]:
    """Compute all available growth rate estimates from a ValuationContext.

    Returns a dict with keys:
      - "historical_revenue": CAGR of Total Revenue
      - "historical_net_income": CAGR of Net Income
      - "fundamental_eps": retention_ratio x ROE
      - "fundamental_ebit": reinvestment_rate x ROC

    Each value is a GrowthEstimate or None if data is insufficient.

    Parameters
    ----------
    ctx : ValuationContext
        Must have financials populated (income_statement, balance_sheet,
        cash_flow, key_stats).

    Returns
    -------
    dict[str, GrowthEstimate | None]
    """
    result: dict[str, GrowthEstimate | None] = {
        "historical_revenue": None,
        "historical_net_income": None,
        "fundamental_eps": None,
        "fundamental_ebit": None,
    }

    inc = ctx.financials.income_statement
    bs = ctx.financials.balance_sheet
    cf = ctx.financials.cash_flow
    stats = ctx.financials.key_stats

    # --- Historical CAGRs ---
    if inc is not None and not inc.empty:
        result["historical_revenue"] = compute_historical_cagr(inc, "Total Revenue")
        result["historical_net_income"] = compute_historical_cagr(inc, "Net Income")

    # --- Fundamental EPS growth ---
    if inc is not None and bs is not None and not inc.empty and not bs.empty:
        net_income = _safe_float(inc, "Net Income")
        book_equity = _safe_float(bs, "Total Stockholders Equity")

        # Compute total dividends paid
        dividends_paid = 0.0
        dps = stats.get("dividend_per_share", 0) if stats else 0
        shares = stats.get("shares_outstanding", 0) if stats else 0
        if dps and shares:
            dividends_paid = float(dps) * float(shares)

        if net_income is not None and book_equity is not None:
            result["fundamental_eps"] = compute_fundamental_eps_growth(
                net_income=net_income,
                book_equity=book_equity,
                dividends_paid=dividends_paid,
            )

    # --- Fundamental EBIT growth ---
    if (
        inc is not None
        and bs is not None
        and cf is not None
        and not inc.empty
        and not bs.empty
        and not cf.empty
    ):
        # EBIT after tax
        ebit = _safe_float(inc, "EBIT")
        tax_rate = ctx.assumptions.tax_rate
        if ebit is not None and tax_rate is not None:
            ebit_after_tax = ebit * (1.0 - tax_rate)
        else:
            ebit_after_tax = None

        # Total capital = equity + debt - cash
        equity = _safe_float(bs, "Total Stockholders Equity")
        debt = _safe_float(bs, "Total Debt")
        cash = _safe_float(bs, "Cash And Cash Equivalents")
        if equity is not None:
            total_capital = equity + (debt or 0.0) - (cash or 0.0)
        else:
            total_capital = None

        # Net CapEx = CapEx - Depreciation
        capex = _safe_float(cf, "Capital Expenditure")
        dep = _safe_float(cf, "Depreciation And Amortization")
        if capex is not None:
            net_capex = abs(capex) - (dep or 0.0)  # CapEx is often negative in yfinance
        else:
            net_capex = None

        # Change in working capital (use 0 if not available)
        change_wc = 0.0

        if ebit_after_tax is not None and total_capital is not None and net_capex is not None:
            result["fundamental_ebit"] = compute_fundamental_ebit_growth(
                ebit_after_tax=ebit_after_tax,
                total_capital=total_capital,
                net_capex=net_capex,
                change_in_wc=change_wc,
            )

    return result
```

- [ ] **Step 4: Run tests**

Run: `python3 -m pytest tests/test_growth_estimator.py -v`

Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/valuation/agents/growth_estimator.py tests/test_growth_estimator.py
git commit -m "feat: add fundamental EPS and EBIT growth estimators"
```

---

## Task 3: Excess Returns Engine

**Files:**
- Create: `src/valuation/engines/excess_returns.py`
- Create: `tests/test_excess_returns.py`

- [ ] **Step 1: Write failing tests**

`tests/test_excess_returns.py`:
```python
import pytest
from valuation.engines.excess_returns import (
    excess_return_valuation,
    compute_excess_return,
)
from valuation.engines.dcf import interpolate_params


class TestExcessReturnSingle:
    def test_positive_excess_return(self):
        """ROE > COE => positive excess return."""
        er = compute_excess_return(
            roe=0.15,
            coe=0.10,
            book_equity=1000.0,
        )
        # (0.15 - 0.10) * 1000 = 50
        assert abs(er - 50.0) < 0.01

    def test_negative_excess_return(self):
        """ROE < COE => negative excess return (value destruction)."""
        er = compute_excess_return(
            roe=0.08,
            coe=0.10,
            book_equity=1000.0,
        )
        # (0.08 - 0.10) * 1000 = -20
        assert abs(er - (-20.0)) < 0.01

    def test_zero_excess_return(self):
        """ROE = COE => zero excess return."""
        er = compute_excess_return(
            roe=0.10,
            coe=0.10,
            book_equity=1000.0,
        )
        assert abs(er) < 0.01


class TestExcessReturnValuation:
    def test_goldman_sachs(self):
        """Goldman: BV=$218.75, ROE=13.19%, COE=10.4%, 10yr HG, stable ROE=10%, stable COE=9.5%.

        Damodaran's excess return model for Goldman should yield a value
        in the neighborhood of $220-$260 per share.
        """
        n_years = 10
        roes = interpolate_params(0.1319, 0.10, n_years, gradual=True)
        coes = interpolate_params(0.104, 0.095, n_years, gradual=True)

        # EPS growth drives book equity growth; use fundamental EPS growth
        eps_growth_rates = interpolate_params(0.1209, 0.04, n_years, gradual=True)

        result = excess_return_valuation(
            current_book_equity_per_share=218.75,
            current_eps=16.77,
            eps_growth_rates=eps_growth_rates,
            payout_rates=interpolate_params(0.0835, 0.60, n_years, gradual=True),
            roes=roes,
            coes=coes,
            stable_growth=0.04,
            stable_roe=0.10,
            stable_coe=0.095,
        )
        assert result["value_per_share"] > 150.0
        assert result["value_per_share"] < 350.0
        assert result["current_book_equity"] == 218.75
        assert result["pv_excess_returns"] != 0  # Some excess return (positive or negative)
        assert result["pv_terminal_excess"] != 0
        assert len(result["yearly_excess_returns"]) == n_years
        assert len(result["yearly_pv"]) == n_years

    def test_wells_fargo(self):
        """Wells Fargo: BV=$15.99, ROE=13.5%, COE=9.6%, 5yr HG.

        Stable ROE=7.6%, stable COE=7.6% => excess return converges to 0.
        Value should be close to book equity in terminal.
        """
        n_years = 5
        roes = interpolate_params(0.135, 0.076, n_years, gradual=True)
        coes = interpolate_params(0.096, 0.076, n_years, gradual=True)
        eps_growth_rates = interpolate_params(0.061, 0.03, n_years, gradual=True)
        payout_rates = interpolate_params(0.546, 0.605, n_years, gradual=True)

        result = excess_return_valuation(
            current_book_equity_per_share=15.99,
            current_eps=2.16,
            eps_growth_rates=eps_growth_rates,
            payout_rates=payout_rates,
            roes=roes,
            coes=coes,
            stable_growth=0.03,
            stable_roe=0.076,
            stable_coe=0.076,
        )
        # When stable ROE = stable COE, terminal excess return = 0
        # Value should be approximately current BV + PV(HG excess returns)
        assert result["value_per_share"] > 10.0
        assert result["value_per_share"] < 40.0
        # Terminal excess value should be near zero since ROE ≈ COE in stable
        assert abs(result["pv_terminal_excess"]) < 5.0

    def test_roe_equals_coe_everywhere(self):
        """If ROE = COE for all periods, value = book equity."""
        result = excess_return_valuation(
            current_book_equity_per_share=100.0,
            current_eps=10.0,
            eps_growth_rates=[0.05, 0.05, 0.05],
            payout_rates=[0.50, 0.50, 0.50],
            roes=[0.10, 0.10, 0.10],
            coes=[0.10, 0.10, 0.10],
            stable_growth=0.03,
            stable_roe=0.10,
            stable_coe=0.10,
        )
        # Excess returns are zero in all periods; terminal excess is zero
        # Value = book equity
        assert abs(result["value_per_share"] - 100.0) < 1.0

    def test_length_mismatch_raises(self):
        """All per-year lists must have the same length."""
        with pytest.raises(ValueError, match="same length"):
            excess_return_valuation(
                current_book_equity_per_share=100.0,
                current_eps=10.0,
                eps_growth_rates=[0.05, 0.05],
                payout_rates=[0.50],
                roes=[0.10, 0.10],
                coes=[0.10, 0.10],
                stable_growth=0.03,
                stable_roe=0.10,
                stable_coe=0.10,
            )

    def test_stable_coe_equals_growth_raises(self):
        """Terminal value formula requires stable_coe > stable_growth."""
        with pytest.raises(ValueError, match="exceed"):
            excess_return_valuation(
                current_book_equity_per_share=100.0,
                current_eps=10.0,
                eps_growth_rates=[0.05],
                payout_rates=[0.50],
                roes=[0.10],
                coes=[0.10],
                stable_growth=0.05,
                stable_roe=0.10,
                stable_coe=0.05,
            )
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_excess_returns.py -v`

Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write the excess returns engine**

`src/valuation/engines/excess_returns.py`:
```python
"""Equity Excess Return valuation model for financial firms.

This model values a financial firm's equity by decomposing it into:
  Value = Current Book Equity + PV(Excess Returns) + PV(Terminal Excess Return)

Excess Return_t = (ROE_t - COE_t) * Book Equity_{t-1}

This is an equity-side-only model: no WACC, no enterprise value, no debt bridge.
Appropriate for banks, brokerages, insurance companies where debt is a raw
material and FCFF is not meaningful.

Methodology: Damodaran (Investment Valuation, 3rd ed., Chapter 14)
"""

from __future__ import annotations

import math
from typing import List


def compute_excess_return(
    roe: float,
    coe: float,
    book_equity: float,
) -> float:
    """Compute excess return for a single period.

    Excess Return = (ROE - COE) * Book Equity

    Parameters
    ----------
    roe : float
        Return on equity for the period (decimal).
    coe : float
        Cost of equity for the period (decimal).
    book_equity : float
        Beginning-of-period book value of equity.

    Returns
    -------
    float
        Excess return for the period ($).
    """
    return (roe - coe) * book_equity


def excess_return_valuation(
    current_book_equity_per_share: float,
    current_eps: float,
    eps_growth_rates: List[float],
    payout_rates: List[float],
    roes: List[float],
    coes: List[float],
    stable_growth: float,
    stable_roe: float,
    stable_coe: float,
) -> dict:
    """Full equity excess return valuation for a financial firm.

    Steps:
      1. Project EPS forward using eps_growth_rates
      2. Compute DPS = EPS * payout_rate for each year
      3. Update book equity: BV_t = BV_{t-1} + EPS_t - DPS_t
      4. Compute excess return: ER_t = (ROE_t - COE_t) * BV_{t-1}
      5. Discount excess returns using cumulative COE
      6. Terminal excess return:
           ER_{n+1} = (stable_ROE - stable_COE) * BV_n
           TV = ER_{n+1} / (stable_COE - stable_growth)
      7. Value = current BV + PV(excess returns) + PV(terminal excess)

    Parameters
    ----------
    current_book_equity_per_share : float
        Current book value of equity per share (BV_0).
    current_eps : float
        Trailing EPS (EPS_0).
    eps_growth_rates : list of float
        Year-by-year EPS growth rates (length = n).
    payout_rates : list of float
        Year-by-year dividend payout ratios (length = n).
    roes : list of float
        Year-by-year ROE (length = n).
    coes : list of float
        Year-by-year cost of equity (length = n).
    stable_growth : float
        Perpetual earnings growth rate in stable phase.
    stable_roe : float
        ROE in stable phase.
    stable_coe : float
        Cost of equity in stable phase.

    Returns
    -------
    dict with keys:
        value_per_share       : float
        current_book_equity   : float
        pv_excess_returns     : float
        pv_terminal_excess    : float
        terminal_excess_value : float (undiscounted)
        yearly_eps            : list[float]
        yearly_dps            : list[float]
        yearly_bv             : list[float]
        yearly_excess_returns : list[float]
        yearly_pv             : list[float]

    Raises
    ------
    ValueError
        If list lengths don't match, or stable_coe <= stable_growth.
    """
    n = len(eps_growth_rates)
    if len(payout_rates) != n or len(roes) != n or len(coes) != n:
        raise ValueError(
            "eps_growth_rates, payout_rates, roes, and coes must all have the same length. "
            f"Got lengths: {n}, {len(payout_rates)}, {len(roes)}, {len(coes)}."
        )
    if stable_coe <= stable_growth:
        raise ValueError(
            f"stable_coe ({stable_coe:.4f}) must exceed stable_growth ({stable_growth:.4f}) "
            f"for a finite terminal value."
        )

    # Step 1-4: Project EPS, DPS, BV, and excess returns
    eps = current_eps
    bv = current_book_equity_per_share

    yearly_eps: List[float] = []
    yearly_dps: List[float] = []
    yearly_bv: List[float] = []
    yearly_excess_returns: List[float] = []

    for g, payout, roe, coe in zip(eps_growth_rates, payout_rates, roes, coes):
        eps = eps * (1.0 + g)
        dps = eps * payout
        er = compute_excess_return(roe, coe, bv)
        bv_new = bv + eps - dps

        yearly_eps.append(eps)
        yearly_dps.append(dps)
        yearly_excess_returns.append(er)
        yearly_bv.append(bv_new)
        bv = bv_new

    # Step 5: Discount excess returns using cumulative COE
    yearly_pv: List[float] = []
    cumulative_discount = 1.0
    for er, coe in zip(yearly_excess_returns, coes):
        cumulative_discount *= (1.0 + coe)
        yearly_pv.append(er / cumulative_discount)
    pv_excess_returns = sum(yearly_pv)

    # Step 6: Terminal excess return
    final_bv = yearly_bv[-1] if yearly_bv else current_book_equity_per_share
    terminal_er = (stable_roe - stable_coe) * final_bv
    terminal_excess_value = terminal_er / (stable_coe - stable_growth)

    # Discount terminal excess value
    cumulative_discount_n = math.prod(1.0 + coe for coe in coes) if coes else 1.0
    pv_terminal_excess = terminal_excess_value / cumulative_discount_n

    # Step 7: Value = BV + PV(excess returns) + PV(terminal excess)
    value_per_share = current_book_equity_per_share + pv_excess_returns + pv_terminal_excess

    return {
        "value_per_share": value_per_share,
        "current_book_equity": current_book_equity_per_share,
        "pv_excess_returns": pv_excess_returns,
        "pv_terminal_excess": pv_terminal_excess,
        "terminal_excess_value": terminal_excess_value,
        "yearly_eps": yearly_eps,
        "yearly_dps": yearly_dps,
        "yearly_bv": yearly_bv,
        "yearly_excess_returns": yearly_excess_returns,
        "yearly_pv": yearly_pv,
    }
```

- [ ] **Step 4: Run tests**

Run: `python3 -m pytest tests/test_excess_returns.py -v`

Expected: All 8 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/valuation/engines/excess_returns.py tests/test_excess_returns.py
git commit -m "feat: add equity excess return valuation engine for financial firms"
```

---

## Task 4: Confidence Scoring

**Files:**
- Create: `src/valuation/scoring/confidence.py`
- Create: `tests/test_confidence.py`

- [ ] **Step 1: Write failing tests**

`tests/test_confidence.py`:
```python
import pytest
from valuation.scoring.confidence import (
    score_data_completeness,
    score_model_agreement,
    score_assumption_sensitivity,
    score_industry_coverage,
    compute_composite_score,
    generate_flags,
    score_all,
)
from valuation.context import ValuationContext
import pandas as pd


class TestDataCompleteness:
    def test_all_fields_present(self):
        """All required fields present => score 1.0."""
        fields = {
            "income_statement": True,
            "balance_sheet": True,
            "cash_flow": True,
            "shares_outstanding": True,
            "market_cap": True,
            "price": True,
            "beta": True,
            "book_value_per_share": True,
        }
        score = score_data_completeness(fields)
        assert score == 1.0

    def test_no_fields_present(self):
        """No fields present => score 0.0."""
        fields = {
            "income_statement": False,
            "balance_sheet": False,
            "cash_flow": False,
            "shares_outstanding": False,
            "market_cap": False,
            "price": False,
            "beta": False,
            "book_value_per_share": False,
        }
        score = score_data_completeness(fields)
        assert score == 0.0

    def test_partial_fields(self):
        """Half fields present => score 0.5."""
        fields = {
            "income_statement": True,
            "balance_sheet": True,
            "cash_flow": True,
            "shares_outstanding": True,
            "market_cap": False,
            "price": False,
            "beta": False,
            "book_value_per_share": False,
        }
        score = score_data_completeness(fields)
        assert abs(score - 0.5) < 0.01


class TestModelAgreement:
    def test_all_models_agree(self):
        """All models return the same value => score 1.0."""
        values = {"dcf": 100.0, "relative": 100.0, "excess_returns": 100.0}
        score = score_model_agreement(values)
        assert score == 1.0

    def test_max_divergence(self):
        """Wide divergence => low score."""
        values = {"dcf": 50.0, "relative": 150.0}
        score = score_model_agreement(values)
        # normalized divergence = (150-50)/100 = 1.0 => score = 1 - 1.0 = 0.0
        assert score == 0.0

    def test_moderate_divergence(self):
        """20% divergence => 0.80 score."""
        values = {"dcf": 90.0, "relative": 110.0}
        score = score_model_agreement(values)
        # mean=100, divergence = (110-90)/100 = 0.20 => score = 0.80
        assert abs(score - 0.80) < 0.01

    def test_single_model(self):
        """Single model => score 1.0 (no divergence possible)."""
        values = {"dcf": 100.0}
        score = score_model_agreement(values)
        assert score == 1.0

    def test_no_models(self):
        """No models => score 0.0."""
        values = {}
        score = score_model_agreement(values)
        assert score == 0.0

    def test_negative_values_excluded(self):
        """Negative values (failed models) are excluded."""
        values = {"dcf": 100.0, "relative": -50.0, "excess_returns": 120.0}
        score = score_model_agreement(values)
        # Only dcf=100 and excess_returns=120 counted
        # mean=110, divergence = (120-100)/110 = 0.1818 => score ≈ 0.818
        assert 0.7 < score < 0.9


class TestAssumptionSensitivity:
    def test_low_sensitivity(self):
        """Small range relative to base => high score."""
        score = score_assumption_sensitivity(
            base_value=100.0,
            min_value=95.0,
            max_value=105.0,
        )
        # sensitivity = (105-95)/100 = 0.10 => score = 1 - 0.10 = 0.90
        assert abs(score - 0.90) < 0.01

    def test_high_sensitivity(self):
        """Large range relative to base => low score."""
        score = score_assumption_sensitivity(
            base_value=100.0,
            min_value=50.0,
            max_value=200.0,
        )
        # sensitivity = (200-50)/100 = 1.50 => score = max(0, 1 - 1.50) = 0.0
        assert score == 0.0

    def test_zero_base_returns_zero(self):
        """Base value of zero => score 0.0."""
        score = score_assumption_sensitivity(
            base_value=0.0,
            min_value=-10.0,
            max_value=10.0,
        )
        assert score == 0.0


class TestIndustryCoverage:
    def test_exact_match(self):
        """Exact industry match => score 1.0."""
        score = score_industry_coverage(match_score=100)
        assert score == 1.0

    def test_no_match(self):
        """No match => score 0.0."""
        score = score_industry_coverage(match_score=0)
        assert score == 0.0

    def test_partial_match(self):
        """75% fuzzy match => score 0.75."""
        score = score_industry_coverage(match_score=75)
        assert abs(score - 0.75) < 0.01


class TestCompositeScore:
    def test_all_perfect(self):
        """All sub-scores 1.0 => composite 1.0."""
        composite = compute_composite_score(
            data_completeness=1.0,
            model_agreement=1.0,
            assumption_sensitivity=1.0,
            industry_coverage=1.0,
        )
        assert abs(composite - 1.0) < 0.01

    def test_all_zero(self):
        """All sub-scores 0.0 => composite 0.0."""
        composite = compute_composite_score(
            data_completeness=0.0,
            model_agreement=0.0,
            assumption_sensitivity=0.0,
            industry_coverage=0.0,
        )
        assert composite == 0.0

    def test_weighted_average(self):
        """Verify weights: 0.30, 0.30, 0.25, 0.15."""
        composite = compute_composite_score(
            data_completeness=1.0,
            model_agreement=0.0,
            assumption_sensitivity=0.0,
            industry_coverage=0.0,
        )
        # Only data_completeness contributes: 1.0 * 0.30 = 0.30
        assert abs(composite - 0.30) < 0.01

    def test_industry_weight(self):
        """Industry coverage alone: 1.0 * 0.15 = 0.15."""
        composite = compute_composite_score(
            data_completeness=0.0,
            model_agreement=0.0,
            assumption_sensitivity=0.0,
            industry_coverage=1.0,
        )
        assert abs(composite - 0.15) < 0.01


class TestFlags:
    def test_no_flags_on_perfect_scores(self):
        flags = generate_flags(
            data_completeness=1.0,
            model_agreement=1.0,
            assumption_sensitivity=1.0,
            industry_coverage=1.0,
            model_values={"dcf": 100.0, "relative": 100.0},
        )
        assert flags == []

    def test_low_data_completeness_flag(self):
        flags = generate_flags(
            data_completeness=0.4,
            model_agreement=1.0,
            assumption_sensitivity=1.0,
            industry_coverage=1.0,
            model_values={"dcf": 100.0},
        )
        assert any("data" in f.lower() for f in flags)

    def test_low_model_agreement_flag(self):
        flags = generate_flags(
            data_completeness=1.0,
            model_agreement=0.3,
            assumption_sensitivity=1.0,
            industry_coverage=1.0,
            model_values={"dcf": 50.0, "relative": 150.0},
        )
        assert any("disagree" in f.lower() or "diverge" in f.lower() for f in flags)

    def test_high_sensitivity_flag(self):
        flags = generate_flags(
            data_completeness=1.0,
            model_agreement=1.0,
            assumption_sensitivity=0.2,
            industry_coverage=1.0,
            model_values={"dcf": 100.0},
        )
        assert any("sensitiv" in f.lower() for f in flags)

    def test_low_industry_coverage_flag(self):
        flags = generate_flags(
            data_completeness=1.0,
            model_agreement=1.0,
            assumption_sensitivity=1.0,
            industry_coverage=0.3,
            model_values={"dcf": 100.0},
        )
        assert any("industry" in f.lower() for f in flags)

    def test_single_model_flag(self):
        flags = generate_flags(
            data_completeness=1.0,
            model_agreement=1.0,
            assumption_sensitivity=1.0,
            industry_coverage=1.0,
            model_values={"dcf": 100.0},
        )
        assert any("single" in f.lower() or "one model" in f.lower() for f in flags)


class TestScoreAll:
    def test_score_all_populates_context(self):
        ctx = ValuationContext(ticker="TEST")
        ctx.financials.income_statement = pd.DataFrame({"Total Revenue": [100]})
        ctx.financials.balance_sheet = pd.DataFrame({"Total Assets": [500]})
        ctx.financials.cash_flow = pd.DataFrame({"Operating Cash Flow": [50]})
        ctx.financials.key_stats = {
            "shares_outstanding": 10,
            "market_cap": 500,
            "price": 50.0,
            "beta": 1.1,
            "book_value_per_share": 30.0,
            "dividend_per_share": 1.0,
        }
        ctx.outputs.dcf_fcff = {"equity_value_per_share": 55.0}
        ctx.outputs.relative = {"implied_value_pe": 50.0, "implied_value_eveb": 52.0}
        ctx.benchmarks.industry_multiples = {"pe": 20.0}

        score_all(ctx, industry_match_score=85)
        assert ctx.confidence.data_completeness is not None
        assert ctx.confidence.model_agreement is not None
        assert ctx.confidence.composite is not None
        assert isinstance(ctx.confidence.flags, list)
        assert 0.0 <= ctx.confidence.composite <= 1.0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_confidence.py -v`

Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write the confidence scoring implementation**

`src/valuation/scoring/confidence.py`:
```python
"""Deterministic confidence scoring for valuation outputs.

Computes four sub-scores and a weighted composite:
  1. data_completeness (weight 0.30): % of required fields present
  2. model_agreement (weight 0.30): 1 - normalized divergence across models
  3. assumption_sensitivity (weight 0.25): 1 - (max-min)/base from sensitivity table
  4. industry_coverage (weight 0.15): fuzzy match score from industry mapper

Also generates human-readable warning flags.

All computation is deterministic Python — no LLM calls.
"""

from __future__ import annotations

from typing import Any

_WEIGHTS = {
    "data_completeness": 0.30,
    "model_agreement": 0.30,
    "assumption_sensitivity": 0.25,
    "industry_coverage": 0.15,
}


def score_data_completeness(fields: dict[str, bool]) -> float:
    """Compute data completeness as fraction of required fields present.

    Parameters
    ----------
    fields : dict[str, bool]
        Map of field name -> whether it is present and non-null.

    Returns
    -------
    float
        Score in [0.0, 1.0].
    """
    if not fields:
        return 0.0
    return sum(1 for v in fields.values() if v) / len(fields)


def score_model_agreement(values: dict[str, float]) -> float:
    """Compute model agreement as 1 - normalized divergence.

    Normalized divergence = (max - min) / mean of positive model values.

    Parameters
    ----------
    values : dict[str, float]
        Model name -> equity value per share. Negative values are excluded
        (they indicate a model failure).

    Returns
    -------
    float
        Score in [0.0, 1.0].
    """
    positive = [v for v in values.values() if v > 0]
    if len(positive) == 0:
        return 0.0
    if len(positive) == 1:
        return 1.0

    mean_val = sum(positive) / len(positive)
    if mean_val == 0:
        return 0.0

    divergence = (max(positive) - min(positive)) / mean_val
    return max(0.0, 1.0 - divergence)


def score_assumption_sensitivity(
    base_value: float,
    min_value: float,
    max_value: float,
) -> float:
    """Compute assumption sensitivity as 1 - (max-min)/base.

    Parameters
    ----------
    base_value : float
        Base-case valuation.
    min_value : float
        Minimum valuation from sensitivity analysis.
    max_value : float
        Maximum valuation from sensitivity analysis.

    Returns
    -------
    float
        Score in [0.0, 1.0].
    """
    if base_value == 0:
        return 0.0
    sensitivity = (max_value - min_value) / abs(base_value)
    return max(0.0, 1.0 - sensitivity)


def score_industry_coverage(match_score: float) -> float:
    """Convert a fuzzy match score (0-100) to a 0-1 score.

    Parameters
    ----------
    match_score : float
        Fuzzy match score from the industry mapper (0-100 scale).

    Returns
    -------
    float
        Score in [0.0, 1.0].
    """
    return max(0.0, min(1.0, match_score / 100.0))


def compute_composite_score(
    data_completeness: float,
    model_agreement: float,
    assumption_sensitivity: float,
    industry_coverage: float,
) -> float:
    """Compute the weighted composite confidence score.

    Weights: data_completeness=0.30, model_agreement=0.30,
             assumption_sensitivity=0.25, industry_coverage=0.15

    Parameters
    ----------
    data_completeness : float
        Score in [0, 1].
    model_agreement : float
        Score in [0, 1].
    assumption_sensitivity : float
        Score in [0, 1].
    industry_coverage : float
        Score in [0, 1].

    Returns
    -------
    float
        Composite score in [0.0, 1.0].
    """
    return (
        _WEIGHTS["data_completeness"] * data_completeness
        + _WEIGHTS["model_agreement"] * model_agreement
        + _WEIGHTS["assumption_sensitivity"] * assumption_sensitivity
        + _WEIGHTS["industry_coverage"] * industry_coverage
    )


def generate_flags(
    data_completeness: float,
    model_agreement: float,
    assumption_sensitivity: float,
    industry_coverage: float,
    model_values: dict[str, float] | None = None,
) -> list[str]:
    """Generate human-readable warning flags based on sub-scores.

    Parameters
    ----------
    data_completeness : float
    model_agreement : float
    assumption_sensitivity : float
    industry_coverage : float
    model_values : dict[str, float] or None
        Model name -> value, used to detect single-model valuations.

    Returns
    -------
    list[str]
        List of warning strings. Empty list if no warnings.
    """
    flags: list[str] = []

    if data_completeness < 0.5:
        flags.append(
            f"Low data completeness ({data_completeness:.0%}): "
            f"key financial fields are missing, which may reduce accuracy."
        )

    if model_agreement < 0.5:
        flags.append(
            f"Models diverge significantly (agreement={model_agreement:.0%}): "
            f"review assumptions across models."
        )

    if assumption_sensitivity < 0.5:
        flags.append(
            f"High sensitivity to assumptions (score={assumption_sensitivity:.0%}): "
            f"small changes in inputs cause large valuation swings."
        )

    if industry_coverage < 0.5:
        flags.append(
            f"Weak industry match (coverage={industry_coverage:.0%}): "
            f"industry benchmarks may not be representative."
        )

    if model_values is not None:
        positive_models = [k for k, v in model_values.items() if v > 0]
        if len(positive_models) == 1:
            flags.append(
                f"Only one model ({positive_models[0]}) produced a valid value: "
                f"cross-validation not possible."
            )

    return flags


def _extract_model_values(ctx: "ValuationContext") -> dict[str, float]:
    """Extract per-share values from all model outputs on the context."""
    values: dict[str, float] = {}

    if ctx.outputs.dcf_fcff and "equity_value_per_share" in ctx.outputs.dcf_fcff:
        values["dcf_fcff"] = ctx.outputs.dcf_fcff["equity_value_per_share"]

    if ctx.outputs.dcf_fcfe and "value_per_share" in ctx.outputs.dcf_fcfe:
        values["dcf_fcfe"] = ctx.outputs.dcf_fcfe["value_per_share"]

    if ctx.outputs.relative:
        # Take the average of available relative valuations
        rel_vals = [
            v for k, v in ctx.outputs.relative.items()
            if k.startswith("implied_value_") and isinstance(v, (int, float)) and v > 0
        ]
        if rel_vals:
            values["relative"] = sum(rel_vals) / len(rel_vals)

    if ctx.outputs.excess_returns and "value_per_share" in ctx.outputs.excess_returns:
        values["excess_returns"] = ctx.outputs.excess_returns["value_per_share"]

    return values


def _extract_field_presence(ctx: "ValuationContext") -> dict[str, bool]:
    """Check which required data fields are present."""
    stats = ctx.financials.key_stats or {}
    return {
        "income_statement": ctx.financials.income_statement is not None,
        "balance_sheet": ctx.financials.balance_sheet is not None,
        "cash_flow": ctx.financials.cash_flow is not None,
        "shares_outstanding": bool(stats.get("shares_outstanding")),
        "market_cap": bool(stats.get("market_cap")),
        "price": bool(stats.get("price")),
        "beta": stats.get("beta") is not None,
        "book_value_per_share": bool(stats.get("book_value_per_share")),
    }


def score_all(
    ctx: "ValuationContext",
    industry_match_score: float = 0.0,
    sensitivity_base: float | None = None,
    sensitivity_min: float | None = None,
    sensitivity_max: float | None = None,
) -> None:
    """Compute all confidence scores and populate ctx.confidence in-place.

    Parameters
    ----------
    ctx : ValuationContext
        Must have outputs and financials populated.
    industry_match_score : float
        Fuzzy match score (0-100) from the industry mapper.
    sensitivity_base : float or None
        Base-case valuation for sensitivity scoring. If None, uses DCF value.
    sensitivity_min : float or None
        Minimum valuation from sensitivity table.
    sensitivity_max : float or None
        Maximum valuation from sensitivity table.
    """
    # Data completeness
    field_presence = _extract_field_presence(ctx)
    dc = score_data_completeness(field_presence)

    # Model agreement
    model_values = _extract_model_values(ctx)
    ma = score_model_agreement(model_values)

    # Assumption sensitivity
    if sensitivity_base is not None and sensitivity_min is not None and sensitivity_max is not None:
        as_score = score_assumption_sensitivity(sensitivity_base, sensitivity_min, sensitivity_max)
    else:
        # Default: extract from sensitivity table on context if available
        if ctx.outputs.sensitivity and isinstance(ctx.outputs.sensitivity, dict):
            sens_vals = [
                v for v in ctx.outputs.sensitivity.values()
                if isinstance(v, (int, float)) and not isinstance(v, bool)
            ]
            if sens_vals and model_values:
                base = list(model_values.values())[0]
                as_score = score_assumption_sensitivity(base, min(sens_vals), max(sens_vals))
            else:
                as_score = 0.5  # neutral default
        else:
            as_score = 0.5  # neutral default

    # Industry coverage
    ic = score_industry_coverage(industry_match_score)

    # Composite
    composite = compute_composite_score(dc, ma, as_score, ic)

    # Flags
    flags = generate_flags(dc, ma, as_score, ic, model_values)

    # Populate context
    ctx.confidence.data_completeness = dc
    ctx.confidence.model_agreement = ma
    ctx.confidence.assumption_sensitivity = as_score
    ctx.confidence.industry_coverage = ic
    ctx.confidence.composite = composite
    ctx.confidence.flags = flags
```

- [ ] **Step 4: Run tests**

Run: `python3 -m pytest tests/test_confidence.py -v`

Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/valuation/scoring/confidence.py tests/test_confidence.py
git commit -m "feat: add deterministic confidence scoring with weighted composite and flags"
```

---

## Task 5: Cross-Validator

**Files:**
- Create: `src/valuation/agents/cross_validator.py`
- Create: `tests/test_cross_validator.py`

- [ ] **Step 1: Write failing tests**

`tests/test_cross_validator.py`:
```python
import pytest
from valuation.agents.cross_validator import (
    cross_validate,
    CrossValidationResult,
)


class TestCrossValidate:
    def test_all_models_agree(self):
        """All models produce similar values => low divergence, no flags."""
        result = cross_validate(
            model_outputs={
                "dcf_fcff": {"equity_value_per_share": 100.0},
                "relative": {"implied_value_pe": 95.0, "implied_value_eveb": 105.0},
            },
            price=98.0,
        )
        assert isinstance(result, CrossValidationResult)
        assert result.mean_value > 0
        assert result.median_value > 0
        assert abs(result.mean_value - 100.0) < 5.0
        assert result.max_divergence_pct < 0.15
        assert result.num_models == 3
        assert len(result.flags) == 0

    def test_large_divergence_flagged(self):
        """Models diverge >50% => flag raised."""
        result = cross_validate(
            model_outputs={
                "dcf_fcff": {"equity_value_per_share": 50.0},
                "relative": {"implied_value_pe": 150.0},
            },
            price=100.0,
        )
        assert result.max_divergence_pct > 0.50
        assert any("diverge" in f.lower() or "spread" in f.lower() for f in result.flags)

    def test_value_vs_price_premium(self):
        """Value significantly above price => premium flag."""
        result = cross_validate(
            model_outputs={
                "dcf_fcff": {"equity_value_per_share": 150.0},
                "relative": {"implied_value_pe": 140.0},
            },
            price=100.0,
        )
        assert result.price_vs_value_pct > 0.30
        assert any("undervalued" in f.lower() or "premium" in f.lower() for f in result.flags)

    def test_value_vs_price_discount(self):
        """Value significantly below price => discount flag."""
        result = cross_validate(
            model_outputs={
                "dcf_fcff": {"equity_value_per_share": 60.0},
                "relative": {"implied_value_pe": 70.0},
            },
            price=100.0,
        )
        assert result.price_vs_value_pct < -0.20
        assert any("overvalued" in f.lower() or "discount" in f.lower() for f in result.flags)

    def test_single_model_no_divergence(self):
        """Single model => divergence is 0."""
        result = cross_validate(
            model_outputs={
                "dcf_fcff": {"equity_value_per_share": 100.0},
            },
            price=100.0,
        )
        assert result.max_divergence_pct == 0.0
        assert result.num_models == 1

    def test_empty_models(self):
        """No valid model outputs => all zeros."""
        result = cross_validate(
            model_outputs={},
            price=100.0,
        )
        assert result.num_models == 0
        assert result.mean_value == 0.0

    def test_excess_returns_included(self):
        """Excess returns model output is picked up."""
        result = cross_validate(
            model_outputs={
                "dcf_fcff": {"equity_value_per_share": 100.0},
                "excess_returns": {"value_per_share": 110.0},
            },
            price=105.0,
        )
        assert result.num_models == 2
        assert abs(result.mean_value - 105.0) < 1.0

    def test_negative_values_excluded(self):
        """Negative model values are excluded from statistics."""
        result = cross_validate(
            model_outputs={
                "dcf_fcff": {"equity_value_per_share": -50.0},
                "relative": {"implied_value_pe": 100.0},
            },
            price=90.0,
        )
        assert result.num_models == 1
        assert result.mean_value == 100.0

    def test_result_contains_individual_values(self):
        """Result dict includes per-model values."""
        result = cross_validate(
            model_outputs={
                "dcf_fcff": {"equity_value_per_share": 100.0},
                "relative": {"implied_value_pe": 90.0, "implied_value_eveb": 110.0},
            },
            price=100.0,
        )
        assert "dcf_fcff" in result.individual_values
        assert "relative_pe" in result.individual_values
        assert "relative_eveb" in result.individual_values
        assert result.individual_values["dcf_fcff"] == 100.0

    def test_to_dict(self):
        """CrossValidationResult can be serialized to dict."""
        result = cross_validate(
            model_outputs={
                "dcf_fcff": {"equity_value_per_share": 100.0},
            },
            price=95.0,
        )
        d = result.to_dict()
        assert isinstance(d, dict)
        assert "mean_value" in d
        assert "flags" in d
        assert "individual_values" in d
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_cross_validator.py -v`

Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write the cross-validator**

`src/valuation/agents/cross_validator.py`:
```python
"""Cross-validate valuation outputs across models.

Compares outputs from DCF (FCFF/FCFE), relative valuation, and excess returns.
Computes divergence, flags outliers, and returns a structured comparison.

All computation is deterministic — the LLM interprets results later.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from typing import Any


@dataclass
class CrossValidationResult:
    """Structured result from cross-validating multiple valuation models."""

    individual_values: dict[str, float] = field(default_factory=dict)
    mean_value: float = 0.0
    median_value: float = 0.0
    min_value: float = 0.0
    max_value: float = 0.0
    max_divergence_pct: float = 0.0
    price_vs_value_pct: float = 0.0
    num_models: int = 0
    flags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dict for JSON output or context storage."""
        return {
            "individual_values": self.individual_values,
            "mean_value": self.mean_value,
            "median_value": self.median_value,
            "min_value": self.min_value,
            "max_value": self.max_value,
            "max_divergence_pct": self.max_divergence_pct,
            "price_vs_value_pct": self.price_vs_value_pct,
            "num_models": self.num_models,
            "flags": self.flags,
        }


def _extract_values(model_outputs: dict[str, dict]) -> dict[str, float]:
    """Extract per-share values from model output dicts.

    Handles different output formats:
      - dcf_fcff / dcf_fcfe: key "equity_value_per_share" or "value_per_share"
      - relative: keys like "implied_value_pe", "implied_value_eveb", etc.
      - excess_returns: key "value_per_share"

    Returns dict mapping descriptive name -> value.
    Excludes negative values (model failures).
    """
    values: dict[str, float] = {}

    for model_name, output in model_outputs.items():
        if not isinstance(output, dict):
            continue

        if model_name in ("dcf_fcff", "dcf_fcfe"):
            for key in ("equity_value_per_share", "value_per_share"):
                if key in output:
                    val = float(output[key])
                    if val > 0:
                        values[model_name] = val
                    break

        elif model_name == "relative":
            for key, val in output.items():
                if key.startswith("implied_value_") and isinstance(val, (int, float)):
                    fval = float(val)
                    if fval > 0:
                        # e.g. "implied_value_pe" -> "relative_pe"
                        suffix = key.replace("implied_value_", "")
                        values[f"relative_{suffix}"] = fval

        elif model_name == "excess_returns":
            if "value_per_share" in output:
                val = float(output["value_per_share"])
                if val > 0:
                    values["excess_returns"] = val

        else:
            # Generic: look for common value keys
            for key in ("equity_value_per_share", "value_per_share", "value"):
                if key in output:
                    val = float(output[key])
                    if val > 0:
                        values[model_name] = val
                    break

    return values


def cross_validate(
    model_outputs: dict[str, dict],
    price: float,
) -> CrossValidationResult:
    """Cross-validate valuation model outputs.

    Parameters
    ----------
    model_outputs : dict[str, dict]
        Map of model name -> model output dict. Expected keys:
        "dcf_fcff", "dcf_fcfe", "relative", "excess_returns".
    price : float
        Current market price per share.

    Returns
    -------
    CrossValidationResult
        Structured comparison with divergence metrics and flags.
    """
    values = _extract_values(model_outputs)
    result = CrossValidationResult()
    result.individual_values = values

    if not values:
        return result

    val_list = list(values.values())
    result.num_models = len(val_list)
    result.mean_value = statistics.mean(val_list)
    result.median_value = statistics.median(val_list)
    result.min_value = min(val_list)
    result.max_value = max(val_list)

    # Divergence: (max - min) / mean
    if result.mean_value > 0 and result.num_models > 1:
        result.max_divergence_pct = (result.max_value - result.min_value) / result.mean_value
    else:
        result.max_divergence_pct = 0.0

    # Price vs intrinsic value: (mean_value - price) / price
    if price > 0:
        result.price_vs_value_pct = (result.mean_value - price) / price
    else:
        result.price_vs_value_pct = 0.0

    # --- Generate flags ---
    flags: list[str] = []

    # Flag: large model divergence (>30%)
    if result.max_divergence_pct > 0.30:
        spread = result.max_value - result.min_value
        flags.append(
            f"Large model spread: ${spread:,.2f} ({result.max_divergence_pct:.0%} divergence). "
            f"Range: ${result.min_value:,.2f} to ${result.max_value:,.2f}."
        )

    # Flag: significant undervaluation (>25% upside)
    if result.price_vs_value_pct > 0.25:
        flags.append(
            f"Potentially undervalued: intrinsic value (${result.mean_value:,.2f}) is "
            f"{result.price_vs_value_pct:.0%} above market price (${price:,.2f})."
        )

    # Flag: significant overvaluation (>25% downside)
    if result.price_vs_value_pct < -0.25:
        flags.append(
            f"Potentially overvalued: intrinsic value (${result.mean_value:,.2f}) is "
            f"{abs(result.price_vs_value_pct):.0%} below market price (${price:,.2f})."
        )

    # Flag: individual model outlier (>2x or <0.5x the median)
    if result.num_models >= 3:
        for name, val in values.items():
            if val > 2 * result.median_value:
                flags.append(
                    f"Outlier: {name} (${val:,.2f}) is >2x the median (${result.median_value:,.2f})."
                )
            elif val < 0.5 * result.median_value:
                flags.append(
                    f"Outlier: {name} (${val:,.2f}) is <0.5x the median (${result.median_value:,.2f})."
                )

    result.flags = flags
    return result
```

- [ ] **Step 4: Run tests**

Run: `python3 -m pytest tests/test_cross_validator.py -v`

Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/valuation/agents/cross_validator.py tests/test_cross_validator.py
git commit -m "feat: add cross-validator for multi-model valuation comparison"
```

---

## Task 6: Sprint 4 Integration Test & Push

**Files:**
- Create: `tests/test_integration_sprint4.py`

- [ ] **Step 1: Write integration test**

`tests/test_integration_sprint4.py`:
```python
"""Sprint 4 integration: growth estimation, excess returns, confidence, cross-validation."""

import pandas as pd
import pytest
from valuation.context import ValuationContext
from valuation.agents.growth_estimator import (
    compute_historical_cagr,
    compute_fundamental_eps_growth,
    compute_fundamental_ebit_growth,
    estimate_all_growth_rates,
)
from valuation.engines.excess_returns import excess_return_valuation
from valuation.engines.dcf import interpolate_params, fcff_valuation
from valuation.agents.risk_assessor import compute_cost_of_equity, compute_wacc
from valuation.scoring.confidence import score_all
from valuation.agents.cross_validator import cross_validate


class TestGrowthEstimationEndToEnd:
    def test_growth_from_context(self):
        """Populate a context, estimate all growth rates, verify consistency."""
        ctx = ValuationContext(ticker="TEST")
        ctx.financials.income_statement = pd.DataFrame({
            "Total Revenue": [40000.0, 45000.0, 50000.0],
            "Net Income": [6000.0, 7000.0, 8000.0],
            "EBIT": [8000.0, 9000.0, 10000.0],
        })
        ctx.financials.balance_sheet = pd.DataFrame({
            "Total Stockholders Equity": [50000.0, 55000.0, 60000.0],
            "Total Debt": [15000.0, 15000.0, 15000.0],
            "Cash And Cash Equivalents": [5000.0, 6000.0, 7000.0],
        })
        ctx.financials.cash_flow = pd.DataFrame({
            "Capital Expenditure": [-3000.0, -3200.0, -3500.0],
            "Depreciation And Amortization": [2000.0, 2100.0, 2200.0],
        })
        ctx.financials.key_stats = {
            "dividend_per_share": 2.0,
            "shares_outstanding": 1000,
        }
        ctx.assumptions.tax_rate = 0.25

        rates = estimate_all_growth_rates(ctx)

        # Revenue CAGR: (50000/40000)^(1/2) - 1 ≈ 11.8%
        assert rates["historical_revenue"] is not None
        assert 0.10 < rates["historical_revenue"].value < 0.15

        # Net income CAGR: (8000/6000)^(1/2) - 1 ≈ 15.5%
        assert rates["historical_net_income"] is not None
        assert 0.10 < rates["historical_net_income"].value < 0.20

        # Fundamental EPS: retention * ROE
        assert rates["fundamental_eps"] is not None
        assert rates["fundamental_eps"].value > 0

        # Fundamental EBIT: reinvestment_rate * ROC
        assert rates["fundamental_ebit"] is not None
        assert rates["fundamental_ebit"].value > 0


class TestExcessReturnsEndToEnd:
    def test_bank_valuation_pipeline(self):
        """Run full excess returns valuation for a hypothetical bank."""
        # Step 1: Set up bank parameters
        bv_per_share = 50.0
        eps = 6.0
        roe = eps / bv_per_share  # 12%
        ke = compute_cost_of_equity(0.04, 1.2, 0.045)  # ≈ 9.4%

        # Step 2: Run excess returns model
        n_years = 5
        result = excess_return_valuation(
            current_book_equity_per_share=bv_per_share,
            current_eps=eps,
            eps_growth_rates=interpolate_params(0.08, 0.03, n_years, gradual=True),
            payout_rates=interpolate_params(0.40, 0.60, n_years, gradual=True),
            roes=interpolate_params(roe, 0.10, n_years, gradual=True),
            coes=interpolate_params(ke, 0.09, n_years, gradual=True),
            stable_growth=0.03,
            stable_roe=0.10,
            stable_coe=0.09,
        )

        # Value should be above book (ROE > COE)
        assert result["value_per_share"] > bv_per_share
        assert result["pv_excess_returns"] > 0
        assert len(result["yearly_bv"]) == n_years
        # Book value should grow over time
        assert result["yearly_bv"][-1] > bv_per_share


class TestFullPipelineWithConfidence:
    def test_dcf_plus_cross_validation_plus_confidence(self):
        """Full pipeline: DCF -> cross-validate -> confidence score."""
        # Step 1: Run a simple DCF
        ke = compute_cost_of_equity(0.04, 1.1, 0.045)
        wacc = compute_wacc(ke, 0.05, 0.25, 0.85, 0.15)
        growth_rates = interpolate_params(0.10, 0.03, 5, gradual=True)
        reinv_rates = interpolate_params(0.40, 0.25, 5, gradual=True)

        dcf_result = fcff_valuation(
            current_ebit_after_tax=500.0,
            growth_rates=growth_rates,
            reinvestment_rates=reinv_rates,
            waccs=[wacc] * 5,
            stable_growth=0.03,
            stable_roc=0.12,
            stable_wacc=wacc,
            cash=200.0,
            debt=1000.0,
            shares_outstanding=50.0,
        )

        # Step 2: Set up context with outputs
        ctx = ValuationContext(ticker="TEST")
        ctx.financials.income_statement = pd.DataFrame({
            "Total Revenue": [1000.0, 1100.0, 1200.0],
        })
        ctx.financials.balance_sheet = pd.DataFrame({
            "Total Assets": [5000.0],
        })
        ctx.financials.cash_flow = pd.DataFrame({
            "Operating Cash Flow": [400.0],
        })
        ctx.financials.key_stats = {
            "shares_outstanding": 50,
            "market_cap": 5000,
            "price": 100.0,
            "beta": 1.1,
            "book_value_per_share": 60.0,
            "dividend_per_share": 2.0,
        }
        ctx.outputs.dcf_fcff = dcf_result
        ctx.outputs.relative = {
            "implied_value_pe": dcf_result["equity_value_per_share"] * 0.95,
            "implied_value_eveb": dcf_result["equity_value_per_share"] * 1.05,
        }

        # Step 3: Cross-validate
        cv_result = cross_validate(
            model_outputs={
                "dcf_fcff": dcf_result,
                "relative": ctx.outputs.relative,
            },
            price=100.0,
        )
        assert cv_result.num_models == 3  # dcf + relative_pe + relative_eveb

        # Step 4: Confidence scoring
        score_all(ctx, industry_match_score=90)
        assert ctx.confidence.composite > 0
        assert ctx.confidence.data_completeness > 0
        assert isinstance(ctx.confidence.flags, list)


class TestGrowthConsistencyChecks:
    def test_fundamental_vs_historical_comparable(self):
        """For a stable company, fundamental and historical growth should be in the same ballpark."""
        # Stable company: 10% ROE, 40% payout, historical revenue growing ~6%
        hist = compute_historical_cagr(
            pd.DataFrame({"Total Revenue": [100, 106, 112.36, 119.10]}),
            "Total Revenue",
        )
        fund = compute_fundamental_eps_growth(
            net_income=100.0,
            book_equity=1000.0,
            dividends_paid=40.0,
        )

        assert hist is not None
        assert fund is not None
        # Historical ~6%, fundamental = 0.60 * 0.10 = 6%
        assert abs(hist.value - fund.value) < 0.02

    def test_ebit_growth_3m_matches_golden(self):
        """3M pre-crisis: ROC=25%, reinvestment=30%, expected g=7.5%."""
        result = compute_fundamental_ebit_growth(
            ebit_after_tax=3473.6,
            total_capital=3473.6 / 0.25,
            net_capex=700.0,
            change_in_wc=342.08,
        )
        assert result is not None
        assert abs(result.value - 0.075) < 0.005

    def test_goldman_eps_growth_matches_golden(self):
        """Goldman: ROE=13.19%, retention=91.65%, expected g=12.09%."""
        result = compute_fundamental_eps_growth(
            net_income=16.77,
            book_equity=16.77 / 0.1319,
            dividends_paid=16.77 * 0.0835,
        )
        assert result is not None
        assert abs(result.value - 0.1209) < 0.005
```

- [ ] **Step 2: Run all Sprint 4 tests**

Run: `python3 -m pytest tests/test_growth_estimator.py tests/test_excess_returns.py tests/test_confidence.py tests/test_cross_validator.py tests/test_integration_sprint4.py -v`

Expected: All PASS

- [ ] **Step 3: Run full test suite**

Run: `python3 -m pytest -v -k "not network"`

Expected: All tests PASS across all sprint test files

- [ ] **Step 4: Commit and push**

```bash
git add tests/test_integration_sprint4.py
git commit -m "test: add Sprint 4 integration tests for growth, excess returns, confidence, cross-validation"
git push origin main
```

---

## Sprint 4 Completion Checklist

- [ ] `python3 -m pytest -v -k "not network"` -- all tests pass
- [ ] Historical CAGR correctly computes revenue and net income growth rates
- [ ] Fundamental EPS growth = retention_ratio x ROE, verified against Goldman (12.09%)
- [ ] Fundamental EBIT growth = reinvestment_rate x ROC, verified against 3M (7.50%)
- [ ] Growth estimator NEVER uses analyst consensus / I/B/E/S as input
- [ ] Excess returns model is equity-side only (no WACC, no enterprise value bridge)
- [ ] Excess returns Goldman test: value in $150-$350 range
- [ ] Excess returns Wells Fargo test: terminal excess near zero (ROE converges to COE)
- [ ] Confidence composite uses weights 0.30/0.30/0.25/0.15
- [ ] Confidence flags fire for low data (<50%), high divergence, high sensitivity, weak industry match
- [ ] Cross-validator extracts values from DCF, relative, and excess returns outputs
- [ ] Cross-validator flags large spread (>30%), under/overvaluation (>25%)
- [ ] All engines are pure functions -- no LLM, no side effects
- [ ] All four modules are independent and can be developed in parallel
