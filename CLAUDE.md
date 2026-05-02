# Valuation Agent v1 -- Claude Code Orchestrator Instructions

## Quick Start

When a user says **"Value \<TICKER\>"**, run the full pipeline:

```bash
python3 run_valuation.py <TICKER>
```

Examples:
```bash
python3 run_valuation.py TATAELXSI.NS                          # auto everything
python3 run_valuation.py AAPL --growth 0.12 --terminal 0.025    # with overrides
python3 run_valuation.py HDFCBANK.NS --classification financial # force financial model
```

This runs ALL 13 steps, fetches analyst consensus from I/B/E/S, runs sensitivity tables, and saves both markdown + Excel reports to `reports/<CompanyName>/`.

For interactive overrides, present assumptions first (see Step 7 below), then rerun with `--growth`, `--terminal`, or `--classification` flags.

## Project Overview

This is a **multi-agent valuation system** that values public companies using Damodaran methodology. Claude Code is the orchestrator: it calls deterministic Python modules for all financial math, interprets results, proposes assumptions to the user, handles overrides, and assembles a final report.

**Architecture:** Claude Code (LLM orchestrator) + Python engines (deterministic math)
**Data sources:** Yahoo Finance (company data) + Damodaran Excel files (industry benchmarks) + WRDS (Compustat + I/B/E/S for comparison)
**Damodaran data path:** `data/damodaran/` or `../2. Damodaran_Data/`

---

## Rules -- Read These First

### Rule 1: LLM never does math
All financial calculations are done by deterministic Python functions. Claude Code NEVER computes WACC, DCF, FCF, terminal value, growth rates, betas, implied values, or any other numeric result. Call the function, read the output, present it.

### Rule 2: No consensus estimates in DCF
Analyst consensus (I/B/E/S) is NEVER used as a DCF input. Growth rates come from fundamentals only:
- Historical CAGR of revenue or net income
- Fundamental EPS growth = retention ratio x ROE
- Fundamental EBIT growth = reinvestment rate x ROC

I/B/E/S consensus may appear in the final report as a **comparison point** (e.g., "Our fundamental growth estimate of 8% compares to the analyst consensus of 10%"), but it is never fed into any engine.

### Rule 3: Present assumptions before running engines
After computing risk and growth parameters, STOP and present them to the user. Let the user review and override before running valuation engines. After any override, recalculate everything downstream.

### Rule 4: Deterministic engines only
Never approximate or shortcut a calculation. If a function exists for it, call the function.

### Rule 5: Track all overrides
When the user changes an assumption, use `ctx.assumptions.set_override(param, new_value, reason)` so the report can show what was changed and why.

---

## Valuation Workflow

When a user says **"Value \<TICKER\>"**, execute the following steps in order.

### Step 1: Fetch Company Data

```python
from valuation.data.api_client import fetch_financials

data = fetch_financials("AAPL")
if data is None:
    # Ticker invalid or API failed -- ask user for manual input
    pass
```

Returns a `CompanyData` dataclass with: `ticker`, `name`, `sector`, `industry`, `sic_code`, `country`, `income_statement` (DataFrame), `balance_sheet` (DataFrame), `cash_flow` (DataFrame), `shares_outstanding`, `market_cap`, `price`, `beta`, `dividend_per_share`, `book_value_per_share`.

### Step 2: Normalize into ValuationContext

```python
from valuation.data.normalizer import normalize

ctx = normalize(data)
if ctx is None:
    # Data was None -- cannot proceed
    pass
```

This creates a `ValuationContext` with `ctx.company`, `ctx.financials`, `ctx.benchmarks`, `ctx.assumptions`, `ctx.outputs`, `ctx.confidence`. Region is auto-detected from country.

### Step 3: Map to Damodaran Industry

```python
from valuation.data.damodaran_loader import DamodaranLoader
from valuation.agents.industry_mapper import match_industry, load_industry_benchmarks

loader = DamodaranLoader("../2. Damodaran_Data/")

match = match_industry(
    sector=ctx.financials.key_stats.get("industry_yfinance", "") or ctx.company.sector or "",
    industry=ctx.financials.key_stats.get("industry_yfinance", "") or "",
    description=ctx.company.name or "",
    loader=loader,
    region=ctx.company.region,
)

if match is None or match.score < 70:
    # Present top candidates to user, ask them to pick
    # match.candidates has top 5 [(name, score), ...]
    pass
else:
    ctx.company.damodaran_industry = match.matched_name
```

Then load benchmarks:

```python
benchmarks = load_industry_benchmarks(
    ctx.company.damodaran_industry,
    loader,
    region=ctx.company.region,
)

if benchmarks:
    ctx.benchmarks.industry_beta = benchmarks["beta"]
    ctx.benchmarks.industry_unlevered_beta = benchmarks["unlevered_beta"]
    ctx.benchmarks.industry_de_ratio = benchmarks["de_ratio"]
    ctx.benchmarks.industry_wacc = benchmarks["wacc"]
    ctx.benchmarks.industry_multiples = benchmarks["multiples"]
    ctx.benchmarks.industry_margins = benchmarks["margins"]
    ctx.benchmarks.industry_growth = benchmarks["growth"]
```

### Step 4: Classify Company

```python
from valuation.agents.classifier import classify_company

classification = classify_company(ctx)
ctx.company.classification = classification.classification
# classification.suggested_model is one of: "dcf_fcff", "ddm", "gordon_growth"
# classification.reasoning explains why
# classification.confidence is 0.0-1.0
```

Classifications: `mature`, `growth`, `young`, `distressed`, `cyclical`, `financial`.
Model routing: `financial` -> DDM/excess returns, all others -> DCF FCFF.

Present the classification and reasoning to the user. If ambiguous (confidence < 0.7), ask user to confirm.

### Step 5: Compute Risk Parameters (Cost of Capital)

```python
from valuation.agents.risk_assessor import (
    compute_cost_of_equity,
    compute_cost_of_debt,
    compute_wacc,
    relever_beta,
    get_synthetic_rating,
)

# Get risk-free rate and ERP from Damodaran data
# Use histimpl.xls for implied ERP (preferred), histretSP.xls for risk-free rate
# Use ctryprem.xlsx for country risk premium if non-US

# Bottom-up beta: use industry unlevered beta, re-lever with company's own D/E
company_de = ...  # from balance sheet: Total Debt / Market Cap
tax_rate = ...    # from Damodaran countrytaxrates or taxrate file
beta = relever_beta(ctx.benchmarks.industry_unlevered_beta, company_de, tax_rate)

# Cost of equity (CAPM)
ke = compute_cost_of_equity(
    risk_free_rate=rf,
    beta=beta,
    erp=erp,
    country_risk_premium=crp,    # 0 for US
    lambda_country=1.0,          # firm-specific country exposure
)

# Cost of debt (synthetic rating)
rating, spread = get_synthetic_rating(interest_coverage, firm_type="large")
kd = compute_cost_of_debt(rf, interest_coverage, firm_type="large")

# WACC
equity_weight = ctx.financials.key_stats["market_cap"] / (ctx.financials.key_stats["market_cap"] + total_debt)
debt_weight = 1.0 - equity_weight

wacc = compute_wacc(ke, kd, tax_rate, equity_weight, debt_weight)

# Store in context
ctx.assumptions.risk_free_rate = rf
ctx.assumptions.erp = erp
ctx.assumptions.country_risk_premium = crp
ctx.assumptions.beta = beta
ctx.assumptions.cost_of_equity = ke
ctx.assumptions.cost_of_debt = kd
ctx.assumptions.wacc = wacc
ctx.assumptions.tax_rate = tax_rate
```

### Step 6: Estimate Growth Rates

```python
from valuation.agents.growth_estimator import estimate_all_growth_rates

growth_estimates = estimate_all_growth_rates(ctx)
# Returns dict with keys:
#   "historical_revenue": GrowthEstimate or None
#   "historical_net_income": GrowthEstimate or None
#   "fundamental_eps": GrowthEstimate or None  (retention x ROE)
#   "fundamental_ebit": GrowthEstimate or None (reinvestment x ROC)
```

Claude Code reviews all estimates and picks the most appropriate one based on:
- Company classification (growth companies lean on revenue CAGR, mature on fundamental)
- Consistency across methods
- Reasonableness vs industry benchmarks (`ctx.benchmarks.industry_growth`)

Set `ctx.assumptions.growth_rates` (list of per-year rates) and `ctx.assumptions.terminal_growth`.

Use `interpolate_params()` from dcf.py if you need gradual transition from high-growth to stable:

```python
from valuation.engines.dcf import interpolate_params

growth_rates = interpolate_params(
    high_growth_value=0.12,
    stable_value=0.025,
    n_years=10,
    gradual=True,
)
```

### Step 7: PRESENT ASSUMPTIONS TO USER -- INTERACTIVE GATE

**STOP HERE.** Before running any engine, present a summary of all assumptions:

```
ASSUMPTIONS FOR REVIEW:
  Company: Apple Inc. (AAPL)
  Classification: mature (confidence: 0.85)
  Damodaran Industry: Computers/Peripherals
  Region: US

  Risk-Free Rate: 3.70%
  Equity Risk Premium: 4.60%
  Beta: 1.15 (bottom-up, re-levered)
  Cost of Equity: 8.99%
  Cost of Debt: 4.81%
  WACC: 8.23%

  Growth (years 1-5): 12.0% -> 10.0%
  Growth (years 6-10): 10.0% -> 2.5%
  Terminal Growth: 2.5%
  Projection Years: 10

  Tax Rate: 21.0%
```

**After the table, ask POINTED questions — not open-ended ones.**

For each assumption where the computed value differs meaningfully from a
benchmark or where confidence is low, ask a specific question that states the
value, the reference, your recommendation, and a bracketed reply shorthand.
Then close with ONE open-ended question.

Example questions (adapt to the actual numbers):

- "WACC is 8.23%. Industry average is 9.1%. Keep 8.23% or adjust? [keep / adjust to ___]"
- "Beta: 1.15 (industry bottom-up, re-levered). Company beta from yfinance is 0.95. Use 1.15? [yes / use 0.95 / other]"
- "Growth: fundamental ROE×retention gives 12.0%. Historical revenue CAGR is 8.4%. I recommend 12.0% given strong buyback program. Accept 12.0%? [yes / adjust to ___]"
- "Terminal growth: 2.5% (US nominal GDP). Acceptable? [yes / adjust]"
- "Any other adjustments before I run the engines?"

**Never ask:** "Would you like to change any assumptions?" or "Any changes?" — these are too vague and not actionable.

If the user overrides anything:
```python
ctx.assumptions.set_override("wacc", 0.09, "User increased WACC to account for execution risk")
```

After override, recalculate all downstream values (e.g., if beta changes, recompute cost_of_equity, then WACC, then re-run engines).

### Step 8: Run Valuation Engines

#### 8a: DCF FCFF (for non-financial companies)

```python
from valuation.engines.dcf import fcff_valuation, interpolate_params

n = ctx.assumptions.projection_years
growth_rates = ctx.assumptions.growth_rates  # list of n floats
reinvestment_rates = interpolate_params(0.50, 0.30, n, gradual=True)  # example
waccs = [ctx.assumptions.wacc] * n  # or interpolate if transitioning

result = fcff_valuation(
    current_ebit_after_tax=ebit * (1 - ctx.assumptions.tax_rate),
    growth_rates=growth_rates,
    reinvestment_rates=reinvestment_rates,
    waccs=waccs,
    stable_growth=ctx.assumptions.terminal_growth,
    stable_roc=0.10,       # industry ROC in stable state
    stable_wacc=ctx.assumptions.wacc,
    cash=cash,
    debt=total_debt,
    non_operating_assets=0.0,
    options_value=0.0,
    shares_outstanding=ctx.financials.key_stats["shares_outstanding"],
)

ctx.outputs.dcf_fcff = result
# result keys: enterprise_value, equity_value, equity_value_per_share,
#              pv_high_growth, pv_terminal, terminal_value,
#              yearly_fcff, yearly_pv, yearly_ebit_at
```

#### 8b: DDM (for financial companies)

```python
from valuation.engines.dcf import ddm_valuation

result = ddm_valuation(
    current_eps=eps,
    growth_rates=growth_rates,       # list of n floats
    payout_rates=payout_rates,       # list of n floats (ramp from low to high)
    cost_of_equities=[ke] * n,
    stable_growth=ctx.assumptions.terminal_growth,
    stable_roe=target_roe,
    stable_ke=ke,
)

ctx.outputs.dcf_fcfe = result
# result keys: value_per_share, pv_dividends, pv_terminal, terminal_price,
#              yearly_eps, yearly_dps, yearly_pv
```

#### 8c: Gordon Growth (for very stable mature companies)

```python
from valuation.engines.dcf import gordon_growth_value

value = gordon_growth_value(
    current_dividend=ctx.financials.key_stats["dividend_per_share"],
    cost_of_equity=ctx.assumptions.cost_of_equity,
    growth_rate=ctx.assumptions.terminal_growth,
)
```

#### 8d: Relative Valuation (always run alongside DCF)

```python
from valuation.engines.relative import relative_valuation

# Extract company metrics
eps = ...  # Net Income / Shares Outstanding
ebitda = ...  # from income statement
revenue_per_share = ...  # Total Revenue / Shares Outstanding

rel_result = relative_valuation(
    eps=eps,
    ebitda=ebitda,
    book_value_per_share=ctx.financials.key_stats["book_value_per_share"],
    revenue_per_share=revenue_per_share,
    industry_multiples=ctx.benchmarks.industry_multiples,
    debt=total_debt,
    cash=cash,
    shares_outstanding=ctx.financials.key_stats["shares_outstanding"],
    market_price=ctx.financials.key_stats["price"],
)

ctx.outputs.relative = rel_result.to_dict()
# result keys: pe_value, ev_ebitda_value, pbv_value, ps_value,
#              composite_value, discount_to_composite, methods_used
```

#### 8e: Excess Returns (only for financial companies)

```python
from valuation.engines.excess_returns import excess_return_valuation

if ctx.company.classification == "financial":
    result = excess_return_valuation(
        current_book_equity_per_share=ctx.financials.key_stats["book_value_per_share"],
        current_eps=eps,
        eps_growth_rates=growth_rates,
        payout_rates=payout_rates,
        roes=roes,              # list of n floats
        coes=[ke] * n,
        stable_growth=ctx.assumptions.terminal_growth,
        stable_roe=target_roe,
        stable_coe=ke,
    )
    ctx.outputs.excess_returns = result
    # result keys: value_per_share, current_book_equity, pv_excess_returns,
    #              pv_terminal_excess, terminal_excess_value,
    #              yearly_eps, yearly_dps, yearly_bv, yearly_excess_returns, yearly_pv
```

### Step 9: Sensitivity Analysis

```python
from valuation.engines.dcf import sensitivity_table, two_way_sensitivity_table

# One-way: vary WACC
wacc_sens = sensitivity_table(
    base_params={...},  # all params for fcff_valuation
    vary_param="stable_wacc",
    vary_values=[wacc - 0.02, wacc - 0.01, wacc, wacc + 0.01, wacc + 0.02],
    valuation_fn=lambda **kw: fcff_valuation(**kw)["equity_value_per_share"],
)

# Two-way: WACC vs terminal growth
two_way = two_way_sensitivity_table(
    base_params={...},
    row_param="stable_wacc",
    row_values=[wacc - 0.02, wacc - 0.01, wacc, wacc + 0.01, wacc + 0.02],
    col_param="stable_growth",
    col_values=[0.01, 0.015, 0.02, 0.025, 0.03],
    valuation_fn=lambda **kw: fcff_valuation(**kw)["equity_value_per_share"],
)

ctx.outputs.sensitivity = {"wacc_sensitivity": wacc_sens, "two_way": two_way}
```

### Step 10: Cross-Validate Models

```python
from valuation.agents.cross_validator import cross_validate

xval = cross_validate(
    model_outputs={
        "dcf_fcff": ctx.outputs.dcf_fcff,
        "relative": ctx.outputs.relative,
        # "excess_returns": ctx.outputs.excess_returns,  # if financial
    },
    price=ctx.financials.key_stats["price"],
)

# xval.mean_value, xval.median_value, xval.max_divergence_pct
# xval.price_vs_value_pct, xval.flags (list of warning strings)
```

If `xval.max_divergence_pct > 0.40`, flag for user review and explain why models disagree.

### Step 11: Confidence Scoring

```python
from valuation.scoring.confidence import score_all

score_all(
    ctx,
    industry_match_score=match.score if match else 0,
    sensitivity_base=ctx.outputs.dcf_fcff["equity_value_per_share"],
    sensitivity_min=min(wacc_sens.values()),
    sensitivity_max=max(wacc_sens.values()),
)

# ctx.confidence.composite is now set (0.0-1.0)
# ctx.confidence.flags has human-readable warnings
```

Confidence bands:
- 0.80-1.00: **High** -- strong data, models agree
- 0.60-0.79: **Moderate** -- some gaps or divergence
- 0.40-0.59: **Low** -- significant issues
- 0.00-0.39: **Speculative** -- directional only

### Step 12: Generate Report

```python
from valuation.reports.generator import generate_report

report = generate_report(ctx)
```

The report includes: executive summary, company classification, key assumptions (with sources and overrides), DCF valuation, relative valuation, sensitivity table, cross-validation, confidence score, and narrative.

---

## Interactive Overrides

The user can change assumptions at any point during the workflow. Common overrides:

| What user says | Parameter to change | Downstream recalculation |
|---------------|--------------------|-----------------------|
| "Use beta of 1.2" | `ctx.assumptions.beta` | cost_of_equity -> WACC -> all engines |
| "Set WACC to 9%" | `ctx.assumptions.wacc` | all engines |
| "Growth should be 15% for 5 years" | `ctx.assumptions.growth_rates` | all engines |
| "Terminal growth 3%" | `ctx.assumptions.terminal_growth` | all engines |
| "Use 10 year projection" | `ctx.assumptions.projection_years` | recompute growth_rates list length -> all engines |
| "Change industry to Software" | `ctx.company.damodaran_industry` | reload benchmarks -> risk -> growth -> all engines |
| "Tax rate is 25%" | `ctx.assumptions.tax_rate` | WACC -> all engines |

After any override:
1. Call `ctx.assumptions.set_override(param, value, reason)` to track it
2. Recalculate everything downstream of the changed parameter
3. Re-run all engines
4. Re-run cross-validation and confidence scoring
5. Present updated results

---

## Fallback Rules

| Situation | Action |
|-----------|--------|
| API data unavailable | Ask user for manual input (structured dict/JSON) |
| Partial financials | Use industry averages from Damodaran; flag imputed fields |
| Industry mapping ambiguous (score < 70) | Present top 3 matches, ask user to pick |
| No company-level beta | Use industry unlevered beta, re-lever with company D/E |
| Country risk unknown | Use regional average |
| Negative earnings | Use revenue-based DCF (project revenue, apply target margin) |
| Negative EBITDA | Skip EV/EBITDA multiple, use P/S instead |
| Financial company | Route to DDM + excess returns; skip DCF FCFF |
| Model divergence > 40% | Flag for user review with explanation |
| Terminal growth > risk-free rate | Cap at risk_free_rate - 1%; warn user |
| WACC < terminal growth | Refuse to compute; ask user to adjust |

---

## Module Reference

### Data Layer

| Module | Key Functions | Purpose |
|--------|--------------|---------|
| `valuation.data.api_client` | `fetch_financials(ticker) -> CompanyData \| None` | Fetch from Yahoo Finance |
| `valuation.data.normalizer` | `normalize(data) -> ValuationContext \| None` | Raw data -> ValuationContext |
| `valuation.data.damodaran_loader` | `DamodaranLoader(path)`, `.load(base_name, region)`, `.lookup(base_name, industry, region)`, `.list_industries(region)` | Load/query Damodaran Excel files |

### Agents

| Module | Key Functions | Purpose |
|--------|--------------|---------|
| `valuation.agents.industry_mapper` | `match_industry(sector, industry, description, loader, region, threshold) -> IndustryMatch \| None`, `load_industry_benchmarks(industry_name, loader, region) -> dict \| None` | Map company to Damodaran industry; load all benchmarks |
| `valuation.agents.classifier` | `classify_company(ctx) -> ClassificationResult` | Classify as mature/growth/young/distressed/cyclical/financial |
| `valuation.agents.risk_assessor` | `compute_cost_of_equity(rf, beta, erp, crp, lambda)`, `compute_cost_of_debt(rf, icr, firm_type)`, `compute_wacc(ke, kd, tax, e_weight, d_weight)`, `relever_beta(bu, de, tax)`, `unlever_beta(bl, de, tax)`, `get_synthetic_rating(icr, firm_type)` | All cost-of-capital calculations |
| `valuation.agents.growth_estimator` | `estimate_all_growth_rates(ctx) -> dict[str, GrowthEstimate \| None]`, `compute_historical_cagr(df, col)`, `compute_fundamental_eps_growth(ni, bv, div)`, `compute_fundamental_ebit_growth(ebit_at, capital, capex, wc)` | Growth rate estimation from fundamentals |
| `valuation.agents.cross_validator` | `cross_validate(model_outputs, price) -> CrossValidationResult` | Compare model outputs, flag divergence |

### Engines

| Module | Key Functions | Purpose |
|--------|--------------|---------|
| `valuation.engines.dcf` | `fcff_valuation(...)`, `ddm_valuation(...)`, `gordon_growth_value(div, ke, g)`, `gordon_implied_growth(price, div, ke)`, `interpolate_params(high, stable, n, gradual)`, `sensitivity_table(...)`, `two_way_sensitivity_table(...)` | DCF, DDM, Gordon Growth, sensitivity |
| `valuation.engines.relative` | `relative_valuation(eps, ebitda, bvps, rps, multiples, debt, cash, shares, price) -> RelativeResult` | Multiples-based valuation (PE, EV/EBITDA, PBV, PS) |
| `valuation.engines.excess_returns` | `excess_return_valuation(bv, eps, growth_rates, payouts, roes, coes, stable_g, stable_roe, stable_coe) -> dict` | Equity excess return model for financial firms |

### Scoring & Reports

| Module | Key Functions | Purpose |
|--------|--------------|---------|
| `valuation.scoring.confidence` | `score_all(ctx, industry_match_score, sensitivity_base, sensitivity_min, sensitivity_max)` | Compute composite confidence score; populates `ctx.confidence` |
| `valuation.reports.generator` | `generate_report(ctx)` | Assemble final markdown report |

### Shared Data Contract

| Module | Key Classes | Purpose |
|--------|------------|---------|
| `valuation.context` | `ValuationContext`, `CompanyInfo`, `Financials`, `Benchmarks`, `Assumptions`, `Outputs`, `Confidence` | Central data structure for the pipeline |

Key `Assumptions` method: `set_override(param, new_value, reason)` -- tracks original value, new value, and reason for change.

### Damodaran Data Files -- Quick Lookup

All loaded via `DamodaranLoader("../2. Damodaran_Data/")`:

| Agent | Files | What for |
|-------|-------|----------|
| Risk Assessor | `betas`, `wacc`, `totalbeta`, `histretSP`, `histimpl`, `ctryprem`, `countrytaxrates`, `taxrate`, `mktcaprisk`, `ratings` | Beta, ERP, WACC, tax rates, ratings |
| Growth Estimator | `fundgr`, `fundgrEB`, `histgr`, `roe`, `capex` | Fundamental and historical growth benchmarks |
| DCF Engine | `margin`, `capex`, `wcdata`, `R&D`, `leaseeffect`, `debtdetails`, `divfcfe`, `finflows`, `goodwill` | Cash flow projection parameters |
| Relative Engine | `pedata`, `pbvdata`, `psdata`, `vebitda`, `mktcapmult`, `countrystats` | Industry multiples |
| Excess Returns | `EVA`, `pbvdata`, `divfcfe` | ROE-COE spreads, payout ratios |
| Cross-Validator | `DollarUS`, `MktCap`, `Employee`, `inshold`, `dbtfund` | Sanity checks |
