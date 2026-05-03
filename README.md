# Valuation Agent

A multi-agent valuation system that values public companies using Aswath Damodaran's methodology. Built as a Claude Code orchestrator + deterministic Python engines.

**The LLM interprets and narrates. Python does all the math.**

## Quick Start

```bash
# Value any public company
python3 run_valuation.py AAPL
python3 run_valuation.py TCS.NS
python3 run_valuation.py NVDA --growth 0.20 --terminal 0.025

# With overrides
python3 run_valuation.py HDFCBANK.NS --classification financial
python3 run_valuation.py TSLA --growth 0.25 --terminal 0.03
```

Or in Claude Code, just say: **"Value NVIDIA"**

## What It Does

Given a ticker, the system runs a 13-step valuation pipeline:

| Step | What | Engine |
|------|------|--------|
| 1 | Fetch financials (Yahoo Finance) | `api_client.py` |
| 2 | Normalize into standard format | `normalizer.py` |
| 3 | Map to Damodaran industry (fuzzy match) | `industry_mapper.py` |
| 4 | Classify company (mature/growth/financial/distressed) | `classifier.py` |
| 5 | Compute WACC (CAPM, bottom-up beta, synthetic rating) | `risk_assessor.py` |
| 6 | Estimate growth (fundamental: ROE x retention, historical CAGR) | `growth_estimator.py` |
| 7 | Validate inputs (bounds checks, missing data) | `pre_engine.py` |
| 8 | Run DCF (FCFF v2 with revenue projection, margin convergence, WACC/tax transitions) | `dcf.py` |
| 9 | Run relative valuation (PE, EV/EBITDA, PBV, PS vs industry) | `relative.py` |
| 10 | Fetch analyst consensus (I/B/E/S via WRDS + Yahoo Finance) — comparison only | `wrds_client.py` |
| 11 | Cross-validate all models, flag divergence | `cross_validator.py` |
| 12 | Score confidence (data quality, model agreement, sensitivity) | `confidence.py` |
| 13 | Generate reports (Markdown + Excel + JSON) | `generator.py`, `excel_writer.py` |

## Output

```
reports/
└── NVIDIA Corporation/
    ├── 2026-05-02_NVDA.md       # Full markdown report (9 sections)
    ├── 2026-05-02_NVDA.xlsx     # Excel workbook (8+ sheets)
    └── 2026-05-02_NVDA.json     # Structured data
```

### Excel Workbook Sheets
1. **Summary** — Value per share, market price, upside/downside, confidence
2. **Assumptions** — All inputs with sources, overrides, industry benchmarks
3. **DCF Model** — Full year-by-year: Revenue → EBIT → FCFF → PV → Enterprise Value → Equity bridge
4. **Relative Valuation** — PE, EV/EBITDA, PBV, PS implied values vs industry
5. **Sensitivity** — WACC vs terminal growth two-way grid
6. **Analyst Consensus** — Yahoo Finance targets + I/B/E/S estimates + accuracy-ranked analysts with firm names
7. **Data Sources** — Where every input came from
8. **Financial Statements** — Income statement, balance sheet, cash flow (standard ordering)

## Architecture

```
Claude Code (LLM)              Python Engines (deterministic)
─────────────────              ─────────────────────────────
Interprets results             DCF (FCFF, DDM, Gordon Growth)
Writes narrative               Relative valuation (4 multiples)
Flags anomalies                Excess returns (financial firms)
Proposes assumptions           Risk assessment (CAPM, WACC)
Handles user overrides         Growth estimation (fundamentals)
                               Sensitivity tables
                               Confidence scoring
                               R&D capitalization
                               WACC/tax/margin transitions
```

### Key Rules
1. **LLM never does math** — All calculations are deterministic Python functions with unit tests
2. **No consensus in DCF** — Analyst estimates (I/B/E/S) are for comparison only, never as model inputs
3. **Fundamental growth only** — Growth = retention x ROE or reinvestment x ROC, not analyst forecasts
4. **Present assumptions before running** — User reviews and can override any input

## Data Sources

| Source | What | Coverage |
|--------|------|----------|
| **Yahoo Finance** | Company financials, price, market cap | Global |
| **Damodaran Data** (244 Excel files) | Industry betas, WACC, multiples, margins, growth, tax rates | 96 industries x 8 regions |
| **WRDS Compustat** | Standardized financials (15+ years) | 5,418 Indian firms, global |
| **WRDS I/B/E/S** | Analyst EPS estimates, price targets, recommendations, accuracy | US (55 analysts for NVDA) + India (43 for TCS) |

## DCF Engine (v2)

Implements Damodaran's exact spreadsheet methodology:

- **Revenue-based projection** with operating margin convergence
- **WACC transition**: constant years 1-5, linear ramp years 6-10 to Rf + 4.5%
- **Tax transition**: effective rate → marginal rate over years 6-10
- **Sales-to-capital reinvestment**: `(Revenue_t - Revenue_{t-1}) / S2C ratio`
- **R&D capitalization**: straight-line amortization (2-10 years by industry)
- **Terminal value**: `FCFF_{n+1} / (WACC - g)` with `reinvestment = g / ROC`

Validated against Damodaran's own spreadsheets: ConEd ($42.30), Goldman ($222.49), 3M ($82.19).

## Project Structure

```
src/valuation/
├── data/               # Data fetching & loading
│   ├── api_client.py       # Yahoo Finance
│   ├── wrds_client.py      # WRDS (Compustat + I/B/E/S)
│   ├── damodaran_loader.py # 244 Damodaran Excel files
│   └── normalizer.py       # Standardize into ValuationContext
├── agents/             # Analysis modules
│   ├── classifier.py       # Company type classification
│   ├── industry_mapper.py  # Fuzzy match to Damodaran industry
│   ├── risk_assessor.py    # CAPM, WACC, synthetic rating, beta
│   ├── growth_estimator.py # Fundamental growth estimation
│   └── cross_validator.py  # Model comparison & divergence
├── engines/            # Valuation math (deterministic)
│   ├── dcf.py              # FCFF v1/v2, DDM, Gordon Growth, sensitivity
│   ├── relative.py         # PE, EV/EBITDA, PBV, PS multiples
│   ├── excess_returns.py   # Financial firm equity model
│   ├── schedules.py        # WACC/tax/margin transition generators
│   └── adjustments.py      # R&D capitalization
├── scoring/
│   └── confidence.py       # Data completeness, model agreement, sensitivity
├── validation/
│   ├── sourced.py          # SourcedValue tracking
│   ├── bounds.py           # Sanity bounds (warn/halt)
│   └── pre_engine.py       # Pre-engine validation gate
└── reports/
    ├── generator.py        # Markdown report (9 sections)
    └── excel_writer.py     # Excel workbook (8+ sheets)
```

## Setup

```bash
pip install -e ".[dev]"

# Optional: WRDS access for I/B/E/S analyst data
pip install wrds
python -c "import wrds; db = wrds.Connection()"  # one-time auth
```

## Tests

```bash
python3 -m pytest -v -k "not network"   # 576 tests, no internet needed
python3 -m pytest -v -m network          # network tests (yfinance, WRDS)
```

## GitHub Actions

- **Tests**: Run automatically on every push to main
- **Run Valuation**: Manual trigger — type a ticker on GitHub Actions, get step-by-step logs + downloadable report

## Methodology

Based on Aswath Damodaran's valuation framework:
- *Damodaran on Valuation* (2nd ed.) — DCF mechanics, multiples, cost of capital
- *The Dark Side of Valuation* (2nd ed.) — Growth, distressed, financial firms
- Damodaran's NYU Stern datasets (updated January 2026)

---

Built with [Claude Code](https://claude.ai/code)
