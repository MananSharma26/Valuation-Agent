# Comprehensive Codebase Review Prompt

Give this prompt to any LLM that can browse URLs (ChatGPT, Gemini, Claude with web access, etc.). The repo is public — no local file access needed.

---

## Prompt

You are reviewing a valuation agent that values public companies using Aswath Damodaran's DCF methodology. The system is built as Python deterministic engines + LLM orchestrator (Claude Code). Your job is to give the most thorough, honest, and actionable review possible — as if Damodaran himself were auditing this.

### Repository

**GitHub:** https://github.com/MananSharma26/Valuation-Agent

### Files to Read (in priority order)

**Start here — the pipeline that ties everything together:**
- `run_valuation.py` — the 13-step orchestrator. Read this FULLY.

**Core valuation engines (deterministic math):**
- `src/valuation/engines/dcf.py` — FCFF v1/v2, DDM, Gordon Growth, sensitivity tables
- `src/valuation/engines/schedules.py` — WACC/tax/margin transition generators
- `src/valuation/engines/adjustments.py` — R&D capitalization, operating lease capitalization
- `src/valuation/engines/relative.py` — PE, EV/EBITDA, PBV, PS implied values
- `src/valuation/engines/excess_returns.py` — Equity excess return model for banks

**Risk and growth (where most judgment happens):**
- `src/valuation/agents/risk_assessor.py` — CAPM, beta, WACC, synthetic rating
- `src/valuation/agents/growth_estimator.py` — Historical CAGR + fundamental growth
- `src/valuation/agents/assumption_reviewer.py` — Flags assumption issues (beta mismatch, PSU detection, ROIC<WACC)
- `src/valuation/agents/assumption_proposer.py` — Proposes assumptions with pointed questions

**Data sources:**
- `src/valuation/data/wrds_client.py` — WRDS (Compustat, I/B/E/S, Capital IQ transcripts)
- `src/valuation/data/damodaran_loader.py` — Loads 244 Damodaran Excel files
- `src/valuation/data/api_client.py` — Yahoo Finance
- `src/valuation/data/peer_analysis.py` — WRDS peer selection + Yahoo enrichment
- `src/valuation/data/sec_fetcher.py` — SEC EDGAR 10-K risk factors
- `src/valuation/data/news_fetcher.py` — News, macro context, GDP forecasts

**Reference documents:**
- `docs/research/dcf-patterns-from-examples.md` — Exact formulas extracted from Damodaran's spreadsheets
- `docs/superpowers/specs/2026-04-30-valuation-agent-v1-design.md` — Original architecture spec
- `CLAUDE.md` — Master orchestrator instructions
- `config/prompts/` — System prompts for LLM judgment calls
- `README.md` — Project overview

**Test files (to understand expected behavior):**
- `tests/golden/` — Ground truth values from Damodaran's own spreadsheets
- `tests/test_dcf.py`, `tests/test_risk_assessor.py` — Unit tests with known values

### Background

This system was built to replicate Damodaran's valuation methodology programmatically. It uses:
- **Yahoo Finance** for company financial data (5 years)
- **WRDS Compustat** for longer history + standardized data (15+ years)
- **WRDS I/B/E/S** for analyst consensus (comparison only, NEVER as DCF input)
- **WRDS Capital IQ** for earnings call transcripts
- **Damodaran's 244 Excel datasets** for industry betas, WACC, multiples, margins, growth rates, tax rates, country risk premiums
- **SEC EDGAR** for 10-K risk factors (US companies)
- **World Bank API** for GDP growth forecasts

Key design rules:
1. **LLM never does math** — all financial calculations are deterministic Python
2. **No consensus estimates as DCF inputs** — analyst data is for comparison only
3. **Growth from fundamentals** — ROE × retention or reinvestment × ROC, never analyst forecasts
4. **Present assumptions before running** — user reviews and can override

### The Problem We're Trying to Solve

Our DCF valuations consistently come in **50-80% below market prices** for Indian companies:
- **HAL** (defense manufacturer): DCF ₹1,023 vs market ₹4,560 (-77%)
- **TCS** (IT services): DCF ₹1,815 vs market ₹2,475 (-27%)
- **NVIDIA** (US semiconductor): DCF $188 vs market $198 (-5%) — this one is close

The relative valuations (PE, EV/EBITDA, PBV, PS) are much closer to market. The DCF is the systematic outlier.

### What We Already Know

1. **The biggest driver is WACC** — dropping WACC from 14% to 9% changes HAL's value from ₹906 to ₹4,663 (5x). Growth rate changes barely matter (±9%).

2. **The S2C ratio causes negative FCFF** — for HAL, Sales-to-Capital = 0.50 means reinvestment (30% of revenue) exceeds NOPAT (21.6%), making FCFF negative during high-growth. Implied ROC < WACC means growth destroys value.

3. **Industry beta vs company beta** — Damodaran's industry file says Aerospace/Defense beta = 1.40. HAL's actual regression beta (Yahoo Finance) is 0.55. Indian PSUs trade at 0.2-0.6 betas because of government backing. Using industry beta gives WACC ~14%; using company beta gives ~9%.

4. **Our Ke formula is correct** — `Ke = Rf + Beta × ERP + Lambda × CRP` matches Damodaran's approach. ERP (4.46%) is mature market implied from Damodaran's `histimpl.xls`, CRP (3.21%) is from `ctryprem.xlsx`. No double-counting.

5. **Terminal growth = 5% for India, capped at Rf** — matches Damodaran's TCS/Tata Steel spreadsheets.

6. **Damodaran ALSO values below market** — his NVIDIA was $78 vs $123 market (-37%). But his gap is smaller than ours for Indian companies.

### What I Want You to Assess

**1. Methodology Correctness:**
- Is our DCF engine (`fcff_valuation_v2` in `dcf.py`) mathematically correct?
- Are transitions (WACC, tax, margin) implemented correctly per `docs/research/dcf-patterns-from-examples.md`?
- Is the equity bridge (EV → equity) correct?
- Is the terminal value formula correct?
- Compare our reinvestment calculation to Damodaran's Amazon/NVIDIA spreadsheets

**2. Root Cause of Undervaluation:**
- Why 50-80% below market for Indian companies specifically?
- Is it the beta/WACC? The S2C reinvestment? Both? Something else?
- Should we be using company regression beta instead of industry beta for PSUs?
- Is Damodaran's methodology inherently conservative, or are we implementing it incorrectly?

**3. What's Missing:**
- What does Damodaran ALWAYS do that our code skips?
- Operating leases? (we just added a basic version)
- Employee stock options?
- Cross-holdings?
- Segment-level valuation?
- Probability of failure?
- NOL carryforwards?

**4. What Should NOT Be Deterministic:**
- Where should human/LLM judgment override the formula?
- Is the growth rate selection (mechanical: historical CAGR vs fundamental) too simplistic?
- Should beta be a user input for PSUs rather than auto-computed from industry?
- Should S2C be validated against the company's actual Revenue/Invested Capital?
- Where does Damodaran use subjective judgment that we've hardcoded?

**5. Is Our Approach Fundamentally Sound?**
- Is "deterministic Python engines + LLM for interpretation/narrative" the right architecture?
- Or should the LLM be more involved in assumption-setting (not just reviewing after the fact)?
- What would make this system produce valuations as defensible as Damodaran doing it manually?

**6. Data & Sources:**
- Are we using the Damodaran data files correctly? (betas, WACC, multiples, margins by industry)
- Is yfinance reliable enough for the financial data, or do we need better sources?
- Are there data sources we're missing that would materially improve accuracy?

### Damodaran Reference Points

From his actual spreadsheets (available in the repo under the examples referenced in `docs/research/dcf-patterns-from-examples.md`):

**TCS (India IT):** Rf=5%, ERP=4.5%, CRP=4.5%, Lambda=0.2, Beta=1.05, Ke=10.6%, Terminal g=5%, Stable ROC=15%

**Tata Steel (India cyclical):** Rf=5%, ERP=4.5%, CRP=4.5%, Lambda=1.1, Beta=1.57, Ke=17.0%, Terminal g=5%, Stable ROC=11.2%

**NVIDIA (US growth):** Rf=4.7%, ERP=4.46%, Beta=1.5, WACC=11.8%→8.5% (transitions), Terminal g=4.7%, S2C=2.5, 3-segment valuation (Gaming+AI+Auto), R&D capitalized 5yr

**Amazon (US growth):** Rf=3%, WACC=7.97%→7.5%, Terminal g=3%, S2C=5.95, Revenue-based with margin convergence 7.7%→12.5%

### Output Format

Structure your response as:

1. **Executive Summary** (3-5 sentences: biggest problem, what's done well, the fix)
2. **Critical Issues** (would change valuation by >20%)
3. **Important Issues** (5-20% impact)
4. **Minor Issues** (<5% impact)
5. **Missing Features** (what Damodaran does that we don't)
6. **Judgment Calls** (what should NOT be deterministic)
7. **Architecture Feedback** (is the overall approach sound?)
8. **Prioritized Fix List** (numbered, most impactful first, with specific file:function references)

Be brutally honest. Reference specific functions and line numbers from the GitHub repo. If something is correct, say so explicitly. If something is fundamentally broken, say so. If our approach is fine and the market is just optimistic, say that too.
