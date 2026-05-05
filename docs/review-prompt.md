# Comprehensive Codebase Review Prompt

Use this prompt with any LLM that has access to local files or can browse the GitHub repo.

---

## Prompt

You are reviewing a valuation agent that values public companies using Aswath Damodaran's DCF methodology. The system is built as Python deterministic engines + LLM orchestrator (Claude Code). Your job is to give the most thorough, honest, and actionable review possible — as if Damodaran himself were auditing this.

### Access

- **GitHub (public):** https://github.com/MananSharma26/Valuation-Agent
- **Local path:** `/mnt/c/Users/Manan Sharma/Desktop/Coding projects/Valuation/0. Valuation Agent`
- **Damodaran example spreadsheets:** `/mnt/c/Users/Manan Sharma/Desktop/Coding projects/Valuation/3. Valuation examples/` (includes NvidiaJan2025.xlsx, 3Mprecrisis.xls, tatasteel.xls, tcs.xls, goldman.xls, AmazonSept18.xlsx, etc.)
- **Damodaran books:** `/mnt/c/Users/Manan Sharma/Desktop/Coding projects/Valuation/1. Books and references/` (Damodaran on Valuation 2ed, The Dark Side of Valuation 2ed)

### Key Files to Read

**Core engine (read these fully):**
- `src/valuation/engines/dcf.py` — FCFF v1, v2, DDM, Gordon Growth, sensitivity tables
- `src/valuation/engines/schedules.py` — WACC/tax/margin transition generators
- `src/valuation/engines/adjustments.py` — R&D capitalization
- `src/valuation/engines/relative.py` — PE, EV/EBITDA, PBV, PS multiples
- `src/valuation/engines/excess_returns.py` — Financial firm model
- `src/valuation/agents/risk_assessor.py` — CAPM, beta, WACC, synthetic rating

**Pipeline (read this fully — it's the main orchestrator):**
- `run_valuation.py` — 13-step pipeline that calls everything

**Agents:**
- `src/valuation/agents/growth_estimator.py` — Historical CAGR + fundamental growth
- `src/valuation/agents/classifier.py` — Company lifecycle classification
- `src/valuation/agents/industry_mapper.py` — Fuzzy match to Damodaran industries
- `src/valuation/agents/assumption_proposer.py` — Proposes assumptions with reasoning
- `src/valuation/agents/assumption_reviewer.py` — Flags assumption issues
- `src/valuation/agents/cross_validator.py` — Model divergence analysis

**Data:**
- `src/valuation/data/damodaran_loader.py` — Loads 244 Damodaran Excel files
- `src/valuation/data/wrds_client.py` — WRDS Compustat + I/B/E/S
- `src/valuation/data/api_client.py` — Yahoo Finance
- `src/valuation/data/peer_analysis.py` — Peer comparison
- `src/valuation/data/sec_fetcher.py` — SEC EDGAR 10-K
- `src/valuation/data/news_fetcher.py` — News + macro context

**Reports:**
- `src/valuation/reports/generator.py` — Markdown report
- `src/valuation/reports/excel_writer.py` — Excel workbook

**Validation:**
- `src/valuation/validation/pre_engine.py` — Pre-engine checks
- `src/valuation/validation/bounds.py` — Sanity bounds
- `src/valuation/validation/sourced.py` — Data source tracking

**Design docs:**
- `docs/superpowers/specs/2026-04-30-valuation-agent-v1-design.md` — Architecture spec
- `docs/research/dcf-patterns-from-examples.md` — Formulas extracted from Damodaran's spreadsheets
- `CLAUDE.md` — Orchestrator instructions
- `config/prompts/` — System prompts for LLM judgment calls

**Recent valuation outputs:**
- `reports/NVIDIA Corporation/` — NVIDIA valuation
- `reports/Hindustan Aeronautics Limited/` — HAL valuation (shows the 77% undervaluation problem)
- `reports/Tata Consultancy Services Limited/` — TCS valuation

### The Problem

Our DCF valuations consistently come in **50-80% below market prices**, especially for Indian companies:
- HAL: DCF ₹1,023 vs market ₹4,560 (-77%)
- TCS: DCF ₹1,815 vs market ₹2,475 (-27%)
- NVIDIA: DCF $188 vs market $198 (-5%) — this one is close

The relative valuations (PE, EV/EBITDA, PBV, PS) are much closer to market. The DCF is the outlier.

### What We Know

1. **Damodaran's own NVIDIA valuation** (Jan 2025, NvidiaJan2025.xlsx) gives $78 when stock was $123 — so Damodaran ALSO values below market (he's conservative). But our gap is MUCH larger than his for Indian companies.

2. **The S2C ratio is a known issue** — for HAL, S2C = 0.50 means reinvestment exceeds NOPAT, making FCFF negative during high-growth. This needs calibration.

3. **Our Ke formula is correct** — `Ke = Rf + Beta × ERP + Lambda × CRP` matches Damodaran's Option B exactly. No double-counting.

4. **Terminal growth = 5% for India** matches Damodaran's TCS/Tata Steel examples exactly.

### What I Want You To Do

**1. Full Methodology Review:**
- Read the DCF engine (`dcf.py`, especially `fcff_valuation_v2`) and compare every formula to Damodaran's books and spreadsheet examples
- Check: are we implementing FCFF correctly? Terminal value correctly? Equity bridge correctly?
- Check: is our reinvestment calculation (S2C approach) implemented the way Damodaran does it in his Amazon/NVIDIA spreadsheets?
- Check: do our transitions (WACC, tax, margin) match his spreadsheet patterns?

**2. Identify What's Missing:**
- What does Damodaran ALWAYS do that we don't?
- What adjustments does he make that we skip? (operating leases, SBC, cross-holdings, NOLs, options, etc.)
- Is there a systematic bias in our approach?

**3. Root Cause the Undervaluation:**
- Why specifically is our DCF 50-80% below market for Indian companies?
- Is it the WACC? The growth rate? The reinvestment? The terminal value? The missing adjustments?
- Compare our HAL DCF step-by-step to how Damodaran would value a similar company

**4. What Should NOT Be Deterministic:**
- Are there judgment calls currently hardcoded that should involve human/LLM input?
- Is our growth rate selection too mechanical?
- Is S2C the right approach for all companies, or should some use traditional reinvestment?
- Should Lambda be a user input rather than auto-detected?

**5. What Would Make This "As Good As Damodaran Doing It Himself":**
- What's the gap between our system and a manual Damodaran valuation?
- What would close that gap?
- Be specific — code-level recommendations

**6. Architecture Feedback:**
- Is the separation of deterministic engines + LLM judgment correct?
- Should any currently-deterministic component have LLM judgment instead?
- Is the data pipeline (yfinance → Damodaran benchmarks → WRDS) comprehensive enough?
- What data sources are we missing?

### Format

Structure your response as:
1. **Executive Summary** (3 sentences: what's the biggest problem, what's done well, what's the fix)
2. **Critical Issues** (would change the valuation by >20%)
3. **Important Issues** (would change by 5-20%)
4. **Minor Issues** (correctness improvements <5% impact)
5. **Missing Features** (Damodaran does this, we don't)
6. **Architecture Recommendations**
7. **Prioritized Fix List** (numbered, most impactful first)

Be brutally honest. If something is correct, say so. If something is fundamentally broken, say so. Reference specific file:line numbers and Damodaran's exact formulas from his books.
