# Valuation Agent v1 — Blueprint

**Date:** 2026-04-30
**Status:** Design — not yet implemented
**Runtime:** Claude Code (Max subscription) as LLM orchestrator + deterministic Python modules

---

## 1. Multi-Agent Architecture

The system is a set of **Python modules** orchestrated by **Claude Code**. Claude Code acts as the conversational orchestrator — it calls Python tools, interprets results, proposes assumptions to the user, and handles overrides. There are no separate API calls to LLMs; all judgment happens within the Claude Code session.

### Agent Registry

| # | Agent | Type | Role | Input | Output |
|---|-------|------|------|-------|--------|
| 1 | **Orchestrator** | LLM (Claude Code) | Route conversation, call modules, manage interactive loop | User request | Calls to all other agents |
| 2 | **Data Ingestion** | Deterministic Python | Fetch & normalize company financials | Ticker or manual data | Standardized financials dict |
| 3 | **Company Classifier** | Hybrid (rules + LLM) | Classify company type | Financials + sector info | `{mature\|growth\|young\|distressed\|cyclical\|financial}` + reasoning |
| 4 | **Industry Mapper** | Hybrid (fuzzy match + LLM) | Map company to Damodaran industry | SIC/NAICS, description | Damodaran industry key + benchmark data |
| 5 | **Risk Assessor** | Deterministic Python | Compute cost of capital | Beta, ERP, country risk, debt | Cost of equity, cost of debt, WACC |
| 6 | **Growth Estimator** | Hybrid (formulas + LLM narrative) | Propose growth assumptions | Historical data, industry benchmarks | Growth rates per year + terminal + reasoning |
| 7 | **DCF Engine** | Deterministic Python | FCFF and FCFE models | Projected financials, WACC, growth | Enterprise value, equity value, sensitivity table |
| 8 | **Relative Valuation Engine** | Deterministic Python | Multiples-based comparison | Company financials, industry multiples | Implied values from PE, EV/EBITDA, PBV, PS |
| 9 | **Excess Returns Engine** | Deterministic Python | Value financial companies | ROE, COE, book value, growth | Equity value for banks/financials |
| 10 | **Cross-Validator** | Hybrid (math + LLM) | Reconcile models, score confidence | All model outputs | Value range, confidence score, divergence flags |
| 11 | **Report Generator** | LLM + templates | Produce final report | All outputs | Structured markdown report |

### What "Hybrid" Means

A hybrid agent is a Python module that does deterministic work first, then formats a prompt for Claude Code to interpret. Example: the Growth Estimator computes fundamental growth (retention × ROE) in Python, then Claude Code evaluates whether that rate makes sense given the company's narrative and proposes adjustments.

---

## 2. Data Flow

```
USER: "Value AAPL"
         │
         ▼
┌─────────────────┐
│   ORCHESTRATOR   │ ◄── Claude Code session
│  (Claude Code)   │
└────────┬────────┘
         │
    ┌────┴────┐
    ▼         ▼
┌────────┐ ┌──────────┐
│ DATA   │ │ INDUSTRY │
│INGEST  │ │ MAPPER   │
│(Python)│ │(Py+LLM)  │
└───┬────┘ └────┬─────┘
    │           │
    ▼           ▼
┌─────────────────────┐
│  COMPANY CLASSIFIER  │
│   (Rules + LLM)      │
└──────────┬──────────┘
           │
     ┌─────┴─────┐
     ▼           ▼
┌─────────┐ ┌──────────┐
│  RISK   │ │  GROWTH  │
│ASSESSOR │ │ESTIMATOR │
│(Python) │ │(Py+LLM)  │
└────┬────┘ └────┬─────┘
     │           │
     ▼           ▼
┌─────────────────────────────────┐
│  USER REVIEWS & OVERRIDES       │
│  (Interactive assumption gate)  │
└──────────────┬──────────────────┘
               │
    ┌──────────┼──────────┐
    ▼          ▼          ▼
┌───────┐ ┌────────┐ ┌─────────┐
│  DCF  │ │RELATIVE│ │ EXCESS  │
│ENGINE │ │VALUAT. │ │RETURNS  │
│(Py)   │ │(Py)    │ │(Py)     │
└───┬───┘ └───┬────┘ └────┬────┘
    │         │           │
    └─────────┼───────────┘
              ▼
     ┌────────────────┐
     │CROSS-VALIDATOR │
     │  (Py + LLM)    │
     └───────┬────────┘
             ▼
     ┌────────────────┐
     │REPORT GENERATOR│
     │  (LLM + tmpl)  │
     └───────┬────────┘
             ▼
         FINAL REPORT
```

### Inter-Agent Data Contract

All agents communicate via a shared `ValuationContext` dict that accumulates through the pipeline:

```python
ValuationContext = {
    "company": {
        "ticker": str,
        "name": str,
        "sector": str,
        "sic_code": str,
        "classification": str,          # mature|growth|young|distressed|cyclical|financial
        "damodaran_industry": str,       # mapped industry name
        "region": str,                   # US|Europe|Japan|India|China|Emerging|Global
    },
    "financials": {
        "income_statement": DataFrame,   # 5+ years
        "balance_sheet": DataFrame,
        "cash_flow": DataFrame,
        "key_stats": dict,               # shares outstanding, market cap, etc.
    },
    "benchmarks": {
        "industry_beta": float,
        "industry_multiples": dict,      # PE, EV/EBITDA, PBV, PS
        "industry_margins": dict,
        "industry_growth": dict,
        "industry_wacc": float,
    },
    "assumptions": {
        "risk_free_rate": float,
        "erp": float,
        "country_risk_premium": float,
        "beta": float,
        "cost_of_equity": float,
        "cost_of_debt": float,
        "wacc": float,
        "growth_rates": list[float],     # per projection year
        "terminal_growth": float,
        "projection_years": int,
        "tax_rate": float,
        "overrides": dict,               # user overrides tracked here
    },
    "outputs": {
        "dcf_fcff": dict,                # enterprise_value, equity_value, per_share
        "dcf_fcfe": dict,
        "relative": dict,                # implied values by multiple
        "excess_returns": dict | None,   # only for financials
        "sensitivity": dict,             # sensitivity table
    },
    "confidence": {
        "data_completeness": float,      # 0-1
        "model_agreement": float,        # 0-1
        "assumption_sensitivity": float, # 0-1
        "composite": float,              # 0-1
        "flags": list[str],             # human-readable warnings
    },
}
```

---

## 3. Knowledge Sources — The Three Pillars

Each source serves a distinct purpose. Getting this wrong means the system hallucinates data or ignores methodology.

| Source | Purpose | How it's used |
|--------|---------|---------------|
| **Books** (2 PDFs) | **Method** — formulas, decision frameworks, heuristics, "how to think" | Extracted into system prompts in `config/prompts/`. Claude Code uses these for judgment calls. |
| **Damodaran Data Files** (244 Excel) | **Data** — actual numeric parameters: betas, ERP, WACC, multiples, margins, growth rates, tax rates, country risk | Loaded at runtime into DataFrames by `damodaran_loader.py`. Agents query these for real values. Never hardcoded. |
| **Example Spreadsheets** (20 unique) | **Workflow & Validation** — show how Damodaran structures models (sheet flow, toggles, order of operations) and provide ground truth for testing | Parsed once to extract golden test cases. Also studied to inform engine architecture (which template, which adjustments). |

### 3.1 Books → Method (What goes into system prompts)

**"Damodaran on Valuation" (2nd ed.)** — the foundational mechanics textbook:

| Chapter(s) | Method taught | Agent that uses it |
|-------------|--------------|-------------------|
| Ch. 1 | Three approaches taxonomy (DCF, relative, contingent claim); when to use each | **Orchestrator**, **Classifier** |
| Ch. 2 | CAPM formula, risk-free rate estimation, bottom-up beta methodology, unlevering/relevering formula, cost of debt from coverage ratios, WACC formula, total beta for private firms | **Risk Assessor** (formula structure) |
| Ch. 3 | FCFE formula, FCFF formula, R&D capitalization method, operating lease conversion, earnings normalization | **DCF Engine** (formula structure) |
| Ch. 4 | Three sources of growth (historical, analyst, fundamental); fundamental growth = retention × ROE and reinvestment × ROC; quality of growth framework | **Growth Estimator** |
| Ch. 5 | Terminal value formulas (stable-growth, liquidation, exit multiple); constraints on stable growth; adjusting beta/reinvestment/ROC for stable state | **DCF Engine** |
| Ch. 6 | DDM, FCFE discount, FCFF discount, excess return model; decision tree for choosing model variant | **Orchestrator**, **DCF Engine**, **Excess Returns Engine** |
| Ch. 7–9 | Multiple derivation from DCF (PE = payout × (1+g)/(ke-g), etc.); companion variable per multiple; cross-sectional regression methodology | **Relative Engine**, **Cross-Validator** |
| Ch. 10 | Why DDM/excess returns for banks (debt = raw material); P/BV vs ROE regression for banks; regulatory capital constraints | **Classifier** (routing), **Excess Returns Engine** |
| Ch. 12–13 | Revenue-based DCF for negative earnings; margin convergence; probability of failure adjustment; TAM-based revenue for startups | **Classifier**, **DCF Engine** (distressed/young paths) |

**"The Dark Side of Valuation" (2nd ed.)** — the edge-case handbook:

| Chapter(s) | Method taught | Agent that uses it |
|-------------|--------------|-------------------|
| Ch. 1 | Life cycle classification: young → growth → mature → decline; five problem categories | **Classifier** |
| Ch. 3 | Monte Carlo simulation for DCF inputs (probability distributions, correlations) | **Future v2** |
| Ch. 6–7 | Risk-free rate in different currencies; stripping default risk; ERP methods (historical, implied, survey); lambda for firm-specific country risk | **Risk Assessor** (prompt context for judgment) |
| Ch. 9–10 | TAM revenue estimation; scaling growth rates; margin convergence to industry; sales-to-capital ratio method; employee option valuation (3 methods) | **Growth Estimator**, **DCF Engine** |
| Ch. 12 | Declining firms: negative reinvestment, divestiture modeling; equity as call option on firm value | **Classifier**, **DCF Engine** |
| Ch. 13 | Normalizing earnings across cycles; adaptive growth tied to cycle position; normalized-earnings multiples | **Growth Estimator**, **Relative Engine** |
| Ch. 14 | Three models for banks (DDM, FCFE, excess return); regulatory capital as growth limiter; insurance firm differences | **Excess Returns Engine** |
| Ch. 15 | R&D capitalization (amortization period selection); lease capitalization; modified Black-Scholes for employee options | **DCF Engine** (adjustment modules) |

### 3.2 Damodaran Data Files → Actual Parameters (What agents look up at runtime)

Each agent below queries specific files for specific columns. This is the authoritative data source mapping.

#### Risk Assessor — queries these files for cost of capital inputs:

| File | Lookup key | Columns used | What for |
|------|-----------|-------------|----------|
| `betas.xls` | Industry name | Beta, Unlevered beta (cash-corrected), D/E Ratio, Effective Tax Rate, HiLo Risk, Std Dev equity | Bottom-up beta estimation; re-levering with company's own D/E |
| `wacc.xls` | Industry name | Cost of Equity, Cost of Debt, After-tax Cost of Debt, E/(D+E), D/(D+E), Cost of Capital (USD + local) | Industry WACC benchmark; pre-built cost of debt from std dev lookup |
| `totalbeta.xls` | Industry name | Total Unlevered Beta, Total Levered Beta, Correlation with market | Private company / undiversified investor valuations |
| `histretSP.xls` | Year | S&P 500 returns, T-Bond rate, T-Bill rate, Inflation, Risk premiums (stocks-bonds, stocks-bills) | Current risk-free rate; historical ERP (arithmetic/geometric, multiple periods) |
| `histimpl.xls` | Year | Implied ERP (FCFE), Implied ERP (DDM), T-Bond Rate, S&P 500, Earnings Yield | Forward-looking implied equity risk premium (preferred over historical) |
| `ctryprem.xlsx` | Country name | Moody's rating, Default Spread, Total ERP, Country Risk Premium (rating + CDS), Corporate Tax Rate, GDP, Lambda | Country risk premium for non-US companies; sovereign rating |
| `countrytaxrates.xls` | Country name | Corporate Tax Rate, Tax Rate with Global Minimum | Marginal tax rate for WACC |
| `taxrate.xls` | Industry name | Effective Tax Rate (3 methods), Cash Tax Rate (2 methods) | Effective vs. marginal tax rate decision |
| `mktcaprisk.xlsx` | Market cap decile | Beta, Total Beta, Correlation, Std Dev, Interest Coverage | Size-based risk adjustments (small-cap premium) |
| `ratings.xls` | Interest coverage ratio | Synthetic rating lookup tables (3 firm types), Default spread | Estimating cost of debt when no market bond data |

#### Growth Estimator — queries these files for growth parameters:

| File | Lookup key | Columns used | What for |
|------|-----------|-------------|----------|
| `fundgr.xls` | Industry name | ROE, Retention Ratio, Fundamental Growth (ROE × retention) | Sustainable EPS growth benchmark |
| `fundgrEB.xls` | Industry name | ROC, Reinvestment Rate, Expected Growth in EBIT (ROC × reinvestment) | Sustainable operating income growth benchmark |
| `histgr.xls` | Industry name | CAGR Net Income (5yr), CAGR Revenues (5yr), Expected Revenue Growth (2yr, 5yr), Expected EPS Growth (5yr) | Historical and analyst consensus growth benchmarks |
| `roe.xls` | Industry name | ROE (unadjusted), ROE (R&D adjusted) | Return on equity for fundamental growth; R&D adjustment |
| `capex.xls` | Industry name | Net Cap Ex/Sales, Net Cap Ex/EBIT(1-t), Sales/Invested Capital | Reinvestment rate and sales-to-capital ratio for growth |

#### DCF Engine — queries these files for cash flow projection parameters:

| File | Lookup key | Columns used | What for |
|------|-----------|-------------|----------|
| `margin.xls` | Industry name | Gross Margin, Net Margin, Pre-tax Operating Margin (6 variants: unadjusted, lease-adj, R&D-adj), EBITDA/Sales, COGS/Sales, R&D/Sales, SG&A/Sales, Stock Comp/Sales | Target margins for margin convergence; expense benchmarking |
| `capex.xls` | Industry name | Cap Ex, Depreciation, Cap Ex/Deprecn, Acquisitions, Net R&D, Net Cap Ex/Sales, Sales/Invested Capital | Reinvestment rate; capex-to-depreciation ratios; sales-to-capital |
| `wcdata.xls` | Industry name | Acc Rec/Sales, Inventory/Sales, Acc Pay/Sales, Non-cash WC/Sales | Working capital as % of sales for projection |
| `R&D.xls` | Industry name | Capitalized R&D, R&D as % of Revenue, R&D history (5 years), CAGR in R&D | R&D capitalization adjustments |
| `leaseeffect.xls` | Industry name | Lease Debt, Lease Expense/Sales, ROIC with/without leases, Margins with/without leases | Operating lease adjustments |
| `debtdetails.xls` | Industry name | Lease Debt, Conventional Debt, Total Debt, Interest Expense, Book Interest Rate | Debt structure for bridge from enterprise to equity value |
| `divfcfe.xls` | Industry name | FCFE (pre-debt, post-debt), Dividends, Buybacks, Payout, Net Cash Returned/FCFE | FCFE model cash flow calibration |
| `finflows.xls` | Industry name | Dividends, Buybacks, Equity Issuance, Net Debt Change | Financing flow assumptions for FCFE model |
| `goodwill.xls` | Industry name | Goodwill as % of Total Assets, Impairment as % of Goodwill | Acquisition adjustment for ROC calculation |

#### Relative Valuation Engine — queries these files for comparable multiples:

| File | Lookup key | Columns used | What for |
|------|-----------|-------------|----------|
| `pedata.xls` | Industry name | Current PE, Trailing PE, Forward PE, PEG Ratio, Expected Growth (5yr), % Money-Losing firms | PE and PEG comparison with companion variable (growth) |
| `pbvdata.xls` | Industry name | PBV, ROE, EV/Invested Capital, ROIC | PBV comparison with companion variable (ROE); EV/IC with ROIC |
| `psdata.xls` | Industry name | Price/Sales, Net Margin, EV/Sales, Pre-tax Operating Margin | PS comparison with companion variable (margin) |
| `vebitda.xls` | Industry name | EV/EBITDA, EV/EBIT, EV/EBIT(1-t), EV/EBITDA+R&D (positive-EBITDA and all-firms) | EV/EBITDA comparison; handles negative-EBITDA industries |
| `mktcapmult.xlsx` | Market cap decile | Trailing PE, Forward PE, PEG, PBV, P/S, EV/EBIT, EV/EBITDA, EV/Sales, ROE, ROIC, Margins | Size-adjusted multiple benchmarks |
| `countrystats.xls` | Country name | Median PE, PBV, PS, EV/EBIT, EV/EBITDA, EV/IC, Dividend Yield (127 countries) | Country-level multiple benchmarks for international comparables |

#### Excess Returns Engine — queries these files for financial firm parameters:

| File | Lookup key | Columns used | What for |
|------|-----------|-------------|----------|
| `EVA.xls` | Industry name | ROE, Cost of Equity, (ROE-COE), BV of Equity, Equity EVA, ROC, WACC, (ROC-WACC), BV Capital, EVA | Industry excess return benchmarks; pre-computed cost of capital components |
| `pbvdata.xls` | Industry name | PBV, ROE | P/BV vs ROE regression for bank comparables (per book ch. 10) |
| `divfcfe.xls` | Industry name | Payout, Dividends, FCFE | Payout ratio for DDM dividend projection |

#### Option Pricing Data (v2 scope, but partially useful in v1):

| File | Lookup key | Columns used | What for |
|------|-----------|-------------|----------|
| `optvar.xls` | Industry name | Std Deviation in Equity, Std Deviation in Firm Value, E/(D+E), D/(D+E) | Firm value volatility for distressed-firm equity-as-call-option (v2); equity std dev also usable by Risk Assessor as alternative risk measure; config inputs: relative bond std dev (0.4), stock-bond correlation (0.5) |

#### Cross-Validator — queries these files for sanity checks:

| File | Lookup key | Columns used | What for |
|------|-----------|-------------|----------|
| `DollarUS.xls` | Industry name | Market Cap, Enterprise Value, Revenues, EBITDA, EBIT, Net Income, Total Debt, Book Equity, Avg Company Age | Absolute-value sanity check — is our valuation in a plausible range for this industry? |
| `MktCap.xls` | Industry name | Market cap 2020-2025, annual % changes, quarterly changes | Market context — is the industry hot/cold right now? |
| `Employee.xls` | Industry name | Market Cap per Employee, Revenue per Employee, Stock Comp % Revenue | Productivity sanity check |
| `inshold.xls` | Industry name | Institutional Holdings, Insider Holdings, CEO Holding | Governance context for discount/premium |
| `dbtfund.xls` | Industry name | Book D/Capital, Market D/Capital, Interest Coverage, Debt/EBITDA, Institutional Holdings | Capital structure sanity check vs. assumptions |

### 3.3 Example Spreadsheets → Workflow Templates & Golden Tests

The examples serve two purposes and are NOT a data source:

**Purpose 1: Workflow template extraction** — Each example reveals Damodaran's exact model structure:

| Template | Example files | Sheets / flow | Agent informed |
|----------|--------------|---------------|----------------|
| **FCFF (non-financial)** | 3M, Amgen, Sears, Hormel, Tata Steel, TCS | Master Inputs → [Earnings Normalizer] → [R&D converter] → [Op Lease converter] → Valuation Model → Option Value → Bottom-up Beta → Ratings Estimator → Industry Averages | **DCF Engine** architecture: which adjustments are toggles, what order, what the "Valuation Model" sheet computes |
| **FCFF (growth/revenue-based)** | Amazon 2018 | Input sheet → Valuation → Stories to Numbers → Cost of Capital Worksheet → Synthetic Rating → R&D/Lease converters | **DCF Engine**: revenue-based projection with margin convergence; "Stories to Numbers" informs **Report Generator** |
| **DDM (financial)** | Goldman, Wells Fargo, CIB Egypt | Inputs → Normalized Earnings → Valuation → [ERP calculator] | **Excess Returns Engine**: direct equity valuation via dividends, no WACC, no enterprise value |
| **Gordon Growth (utility)** | ConEd | Single-formula sheet | **DCF Engine**: simplest path for perfectly stable firms |
| **Multi-approach IPO** | Aramco | 3 parallel sheets (Dividends, FCFE, FCFF) | **Orchestrator**: parallel valuation approach pattern |

Key architectural patterns extracted from examples:
- **Toggle switches:** Yes/No cells control R&D capitalization, lease conversion, earnings normalization, fundamental vs. direct growth, 2-stage vs. 3-stage
- **Gradual adjustment:** 3-stage model option where growth/beta/debt ratio transition linearly from high-growth to stable
- **Embedded tools:** Ratings estimator, bottom-up beta calculator, R&D/lease converters are self-contained modules within each spreadsheet
- **Country risk (emerging market files):** Lambda parameter for firm-specific country risk exposure; dual currency columns
- **Cross-holdings (Indian companies):** Separate valuation of subsidiary holdings added to equity value

**Purpose 2: Golden test cases** — Expected inputs → outputs for engine validation:

| Company | File | Model type | Key test values |
|---------|------|-----------|-----------------|
| Amazon 2018 | AmazonSept18.xlsx | FCFF (revenue-based) | Value/share: $1,255; 15% rev growth, 12.5% target margin, WACC 7.97% |
| 3M pre-crisis | 3Mprecrisis.xls | FCFF (mature) | Value/share: $82.19; ROC 25%, reinvestment 30%, WACC 8.63% |
| Amgen | amgen.xls | FCFF (pharma, R&D-adj) | R&D +$2,216 adjustment; 10yr amortization; beta 1.73 |
| Tata Steel | tatasteel.xls | FCFF (emerging cyclical) | Lambda 1.1, country ERP 4.5%, cross-holdings ₹467B |
| TCS | tcs.xls | FCFF (emerging growth) | Lambda 0.2, ROC 40.6%, value/share ₹727.66 |
| ConEd | coned08.xls | Gordon Growth | Value = $42.30; DPS $2.32, ke 7.7%, g 2.1% |
| Sears | sears.xls | FCFF (distressed) | Negative growth -1.5%, negative reinvestment -30%, value/share $87.29 |
| Hormel | hormel.xls | FCFF (near-stable) | Only 3yr high growth at 2.75%, near-Gordon equivalent |
| Goldman | goldman.xls | DDM (financial) | Value $222.49; ROE 13.2%, payout ramps 8.3%→60% |
| Wells Fargo | wellsfargo2008.xls | DDM (financial) | Value $30.28; 2008 crisis; stable ROE 7.6% |
| CIB Egypt | CIBEgypt2016.xls | DDM (emerging financial) | COE 23.25%, ERP 15.7%, risk-free 10.53% (EGP) |
| Aramco | AramcoIPO.xlsx | Multi-approach | 50yr finite life; regime change discount 20%; 3 parallel valuations |

### 3.4 How Knowledge Is Encoded

```
BOOKS ──────────► config/prompts/*.md          (system prompt context for Claude Code)
                  └── Decision rules, formulas, heuristics, classification logic
                  └── NOT data values — never hardcode a beta or ERP from a book

DATA FILES ─────► damodaran_loader.py → DataFrame  (queried at runtime)
                  └── Every numeric parameter comes from here
                  └── Industry betas, ERP, WACC, multiples, margins, growth, tax rates
                  └── Updated by re-running download_damodaran.sh

EXAMPLES ───────► tests/golden/*.json           (extracted once, used for validation)
                  └── Input assumptions + expected output values
                  └── Also informs engine architecture (which adjustments, which toggles)
```

---

## 4. Deterministic Python vs. LLM-Driven

### Deterministic Python (must never hallucinate)

| Component | Why deterministic |
|-----------|-------------------|
| `data/api_client.py` | API calls are mechanical |
| `data/damodaran_loader.py` | Excel parsing is mechanical |
| `data/normalizer.py` | Field mapping is a fixed schema |
| `engines/dcf.py` | Financial math must be exact |
| `engines/relative.py` | Multiple comparisons are arithmetic |
| `engines/excess_returns.py` | Excess return formula is fixed |
| `scoring/confidence.py` | Scoring formula is defined |
| `agents/risk_assessor.py` | WACC is a formula, not judgment |

### LLM-Driven (requires judgment, creativity, or natural language)

| Component | Why LLM |
|-----------|---------|
| Orchestrator (Claude Code) | Conversation management, routing decisions |
| Company classification (ambiguous cases) | "Is Tesla a growth or mature company?" requires judgment |
| Growth narrative | "Why will growth slow?" is a qualitative question |
| Assumption proposals | "I recommend 8% growth because..." needs reasoning |
| Cross-validation interpretation | "DCF says $150, multiples say $90 — here's why..." |
| Report narrative | Natural language synthesis |
| User interaction | Understanding overrides, answering questions |

### Hybrid Components

| Component | Deterministic part | LLM part |
|-----------|-------------------|----------|
| `agents/classifier.py` | Rule-based pre-filter (SIC code, negative earnings → distressed, bank SIC → financial) | Ambiguous cases ("is this growth or mature?") |
| `agents/industry_mapper.py` | Fuzzy string match on company description vs. Damodaran industry names | Disambiguation when top 3 matches are close |
| `agents/growth_estimator.py` | Fundamental growth = retention × ROE; historical CAGR | Narrative adjustment, reconciliation of conflicting signals |
| `agents/cross_validator.py` | Divergence = abs(dcf - relative) / avg | Explanation of why models disagree |

---

## 5. Fallback Rules

| Situation | Detection | Fallback | Confidence impact |
|-----------|-----------|----------|-------------------|
| API data unavailable | `yfinance` returns None/error | Prompt user for manual input (provide template) | -0 (manual data is fine) |
| Partial financials | Required fields missing after fetch | Use industry averages from Damodaran datasets; flag which fields are imputed | -0.15 per imputed field |
| Industry mapping ambiguous | Top fuzzy match score < 0.7 | Present top 3 matches to user, ask them to pick | -0 after user picks |
| No company-level beta | Beta not in API response | Use industry unlevered beta from `betas.xls`, re-lever with company D/E | -0.05 |
| Country risk unknown | Country not in `ctryprem.xlsx` | Use regional average (Emerging Markets, etc.) | -0.10 |
| Negative earnings | Net income < 0 for latest year | Use revenue-based DCF (project revenue → apply target margin); flag | -0.10 |
| Negative EBITDA | EBITDA < 0 | Skip EV/EBITDA multiple; use PS instead | -0.05 |
| Financial company detected | SIC 6000-6999 or classifier output | Route to excess returns engine; skip DCF | -0 (correct routing) |
| Model divergence > 40% | abs(dcf - relative) / avg > 0.4 | Flag for user review; present both values with reasoning | -0.20 |
| Insufficient history (< 3 years) | Financials have < 3 annual periods | Shorten projection to 3 years; widen confidence band | -0.15 |
| Terminal growth > risk-free rate | terminal_growth > risk_free_rate | Cap at risk-free rate - 1%; warn user | -0.05 |
| WACC < terminal growth | Mathematical impossibility for perpetuity | Error: refuse to compute; ask user to adjust assumptions | Block |

---

## 6. Confidence Scoring

### Components

```
composite_confidence = (
    0.30 × data_completeness +
    0.30 × model_agreement +
    0.25 × assumption_sensitivity +
    0.15 × industry_coverage
)
```

| Dimension | Calculation | Score range |
|-----------|-------------|-------------|
| **Data Completeness** | % of required financial fields present (not imputed) | 0.0 – 1.0 |
| **Model Agreement** | 1 - normalized_divergence across DCF, relative, excess returns | 0.0 – 1.0 |
| **Assumption Sensitivity** | 1 - (max_value - min_value) / base_value from sensitivity table | 0.0 – 1.0 |
| **Industry Coverage** | Fuzzy match score of company-to-Damodaran-industry mapping | 0.0 – 1.0 |

### Confidence Bands

| Composite | Label | Interpretation |
|-----------|-------|----------------|
| 0.80 – 1.00 | **High** | Strong data, models agree, stable assumptions |
| 0.60 – 0.79 | **Moderate** | Some gaps or divergence; review flagged items |
| 0.40 – 0.59 | **Low** | Significant data gaps or model disagreement |
| 0.00 – 0.39 | **Speculative** | Major issues; treat as directional only |

### Flags (appended to confidence output)

Human-readable warnings, e.g.:
- "3 of 12 financial fields imputed from industry averages"
- "DCF and relative valuation diverge by 47% — likely driven by growth assumptions"
- "Company has only 2 years of history; projections are less reliable"
- "Excess returns model not applicable — company is not a financial"

---

## 7. Repo Structure

```
valuation-agent/
├── CLAUDE.md                          # Claude Code instructions for running valuations
├── pyproject.toml                     # Python project config (dependencies, scripts)
├── config/
│   └── prompts/                       # System prompt fragments for LLM-driven agents
│       ├── orchestrator.md            #   Conversation routing + workflow
│       ├── classifier.md              #   Company classification heuristics
│       ├── growth_narrative.md        #   Growth estimation reasoning
│       ├── cross_validation.md        #   Model divergence interpretation
│       └── report.md                  #   Report narrative style
│
├── knowledge/
│   ├── resource_map_enriched.csv      # Catalog of all 281 resources
│   └── learning_plan.json             # Phased learning plan
│
├── data/
│   └── damodaran/                     # 244 industry datasets (committed or symlinked)
│       ├── risk_discount_rate/
│       ├── multiples/
│       ├── growth_rate_estimation/
│       ├── cash_flow_estimation/
│       ├── capital_structure/
│       ├── dividend_policy/
│       ├── investment_returns/
│       ├── corporate_governance/
│       └── option_pricing/
│
├── examples/                          # Damodaran example valuations (ground truth)
│   ├── AmazonSept18.xlsx
│   ├── goldman.xls
│   ├── tatasteel.xls
│   └── ...
│
├── src/
│   └── valuation/
│       ├── __init__.py
│       ├── context.py                 # ValuationContext dataclass
│       ├── agents/
│       │   ├── __init__.py
│       │   ├── classifier.py          # Company type classification
│       │   ├── data_ingestion.py      # Fetch financials (yfinance + manual)
│       │   ├── industry_mapper.py     # Map to Damodaran industry
│       │   ├── risk_assessor.py       # Beta, ERP, WACC computation
│       │   ├── growth_estimator.py    # Growth rate estimation
│       │   └── cross_validator.py     # Reconcile model outputs
│       │
│       ├── engines/
│       │   ├── __init__.py
│       │   ├── dcf.py                 # FCFF + FCFE models
│       │   ├── relative.py            # Multiples-based valuation
│       │   └── excess_returns.py      # Financial company model
│       │
│       ├── data/
│       │   ├── __init__.py
│       │   ├── api_client.py          # Yahoo Finance wrapper
│       │   ├── damodaran_loader.py    # Parse all Damodaran Excel files
│       │   └── normalizer.py          # Standardize financial data
│       │
│       ├── scoring/
│       │   ├── __init__.py
│       │   └── confidence.py          # Confidence score computation
│       │
│       └── reports/
│           ├── __init__.py
│           ├── generator.py           # Assemble report from context
│           └── templates/
│               └── valuation_report.md
│
└── tests/
    ├── conftest.py
    ├── test_damodaran_loader.py
    ├── test_dcf.py
    ├── test_relative.py
    ├── test_excess_returns.py
    ├── test_risk_assessor.py
    ├── test_confidence.py
    └── golden/                        # Expected outputs extracted from examples
        ├── amazon_2018.json
        ├── goldman.json
        ├── tata_steel.json
        └── ...
```

---

## 8. Acceptance Criteria for v1

### Must-Have (v1 ships only when ALL pass)

1. **Data ingestion works.** Given any US public company ticker, fetch income statement, balance sheet, and cash flow statement via yfinance. If API fails, accept manual input via structured dict/JSON.

2. **Damodaran data loads.** All 244 Excel files parse into queryable DataFrames. Query by industry name + region returns correct data.

3. **Company classification is correct.** System correctly classifies all 20 example companies (tested against manually-labeled ground truth).

4. **DCF engine reproduces known valuations.** FCFF model output is within 10% of Damodaran's values for: Amazon 2018, 3M, Amgen, Tata Steel, ConEd.

5. **Relative valuation works.** Given a company and its Damodaran industry, compute PE/EV-EBITDA/PBV/PS and compare to industry median. Implied values are mathematically correct.

6. **Excess returns for financials.** Goldman Sachs, Wells Fargo, Deutsche Bank valuations are within 15% of Damodaran's spreadsheet values.

7. **Risk assessment is sound.** WACC computation matches Damodaran's published industry WACCs for 10+ industries (within 50bps).

8. **Interactive overrides work.** User can override any assumption (growth rate, WACC, terminal growth, beta) and the valuation recalculates correctly.

9. **Confidence score is meaningful.** High-confidence valuations (>0.8) have model divergence <20%. Low-confidence valuations (<0.5) have divergence >30% or significant data gaps.

10. **Report is produced.** System outputs a structured markdown report containing: executive summary, company classification, key assumptions (with sources), DCF valuation, relative valuation, sensitivity table, confidence score, and narrative.

### Nice-to-Have (v1.1)

- PDF export of report
- Multiple region support (non-US companies with country risk)
- Historical valuation comparison (value today vs. 1 year ago)
- Batch mode (value a list of tickers)

### Explicitly Out of Scope for v1

- Real options valuation (v2 — requires Dark Side ch. 4-8)
- Automated financial statement extraction from PDFs/10-Ks
- Live market data streaming
- Portfolio-level analysis
- Web UI (CLI/Claude Code only for v1)

---

## 9. Suggested Next Git Commit Message

```
feat: add v1 blueprint, knowledge layer, and Damodaran data

- Add knowledge/resource_map_enriched.csv (281 resources cataloged)
- Add knowledge/learning_plan.json (10-phase build plan)
- Add v1 architecture design spec with multi-agent blueprint
- Add 244 Damodaran industry datasets across 9 categories
- Add download_damodaran.sh for reproducible data refresh

This establishes the design foundation for the valuation agent:
multi-agent architecture with deterministic Python engines for
financial math and Claude Code as the LLM orchestrator for
judgment, narrative, and user interaction.
```

---

## 10. Implementation Order

| Order | Component | Depends on | Est. complexity | Why this order |
|-------|-----------|------------|-----------------|----------------|
| **1** | `data/damodaran_loader.py` | — | Medium | Everything else needs Damodaran data |
| **2** | `data/api_client.py` + `normalizer.py` | — | Medium | Need company financials before any model |
| **3** | `context.py` (ValuationContext) | — | Low | Shared data contract for all agents |
| **4** | `engines/dcf.py` | #3 | High | Core valuation model; validate against examples first |
| **5** | `tests/golden/` extraction | #4 | Medium | Extract expected values from example spreadsheets |
| **6** | `agents/risk_assessor.py` | #1, #3 | Medium | DCF needs WACC; risk assessor needs Damodaran betas/ERP |
| **7** | `agents/industry_mapper.py` | #1, #3 | Medium | Risk assessor and relative engine need industry mapping |
| **8** | `engines/relative.py` | #1, #7 | Medium | Second valuation method; cross-check for DCF |
| **9** | `agents/classifier.py` | #2, #3 | Medium | Routes to correct engine; needs financials to classify |
| **10** | `agents/growth_estimator.py` | #1, #2, #6 | High | Hardest hybrid agent; needs data + Damodaran benchmarks |
| **11** | `engines/excess_returns.py` | #6, #9 | Medium | Only for financials; needs classifier to route here |
| **12** | `scoring/confidence.py` | #4, #8 | Low | Formula over model outputs |
| **13** | `agents/cross_validator.py` | #4, #8, #11, #12 | Medium | Needs all model outputs to reconcile |
| **14** | `config/prompts/` | #9, #10, #13 | Medium | System prompts for all LLM-driven agents |
| **15** | `reports/generator.py` + templates | #13 | Medium | Assembles everything into final output |
| **16** | `CLAUDE.md` (orchestrator instructions) | #14, #15 | Low | Ties it all together for Claude Code |
| **17** | End-to-end integration test | All | High | Full pipeline: ticker → report |

### Suggested Build Sprints

- **Sprint 1 (Foundation):** #1–3 — Data layer + context contract
- **Sprint 2 (Core Engine):** #4–6 — DCF + golden tests + risk assessment
- **Sprint 3 (Breadth):** #7–9 — Industry mapping + relative valuation + classifier
- **Sprint 4 (Intelligence):** #10–13 — Growth estimation + excess returns + confidence
- **Sprint 5 (Polish):** #14–17 — Prompts + reports + orchestrator + integration
