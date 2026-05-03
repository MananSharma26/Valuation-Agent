# Sprint 5: Polish — System Prompts, Report Generator, CLAUDE.md Orchestrator, End-to-End Tests

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Tie the entire pipeline together so a user can say "Value AAPL" in Claude Code and get a structured valuation report. This sprint builds the system prompts that encode Damodaran methodology as decision rules, the deterministic report generator, and the CLAUDE.md orchestrator file. Ends with end-to-end integration tests across 3 company types.

**Architecture:** System prompts are static markdown files read by Claude Code at runtime — they encode methodology, not data. The report generator is pure deterministic Python string formatting (no LLM calls). CLAUDE.md is the master orchestrator that tells Claude Code what Python module to call at each step and how to interpret results.

**Tech Stack:** Python 3.12, Jinja2, pytest, dataclasses

**Depends on (assume complete):**
- Sprint 1: `damodaran_loader`, `api_client`, `wrds_client`, `normalizer`, `context`
- Sprint 2: `risk_assessor`, `dcf` (Gordon/FCFF/DDM), sensitivity tables
- Sprint 3: `industry_mapper`, `relative` engine, `classifier`
- Sprint 4: `growth_estimator`, `excess_returns` engine, `confidence` scorer, `cross_validator`

**Key constraints:**
- Report generator is deterministic Python — formats data into markdown, no LLM
- System prompts encode Damodaran methodology as decision rules for Claude Code's judgment
- CLAUDE.md is the orchestrator — it tells Claude Code what to call and when
- LLM never does math — it reads Python outputs and writes narrative
- No consensus estimates feed into any model — I/B/E/S shown as comparison only

---

## File Structure

| File | Responsibility |
|------|---------------|
| `config/prompts/orchestrator.md` | Conversation flow: ticker through report |
| `config/prompts/classifier.md` | Heuristics for ambiguous company classification |
| `config/prompts/growth_narrative.md` | How to reason about growth sustainability |
| `config/prompts/cross_validation.md` | How to interpret model divergence |
| `config/prompts/report.md` | Report narrative style (story + numbers) |
| `src/valuation/reports/generator.py` | Assemble ValuationContext into markdown report |
| `src/valuation/reports/templates/valuation_report.md` | Jinja2 template for the report |
| `CLAUDE.md` | Master orchestrator for Claude Code sessions |
| `tests/test_report_generator.py` | Tests for report generator |
| `tests/test_integration_e2e.py` | Full pipeline integration tests |

---

## Task 1: System Prompt — Orchestrator

**Files:**
- Create: `config/prompts/orchestrator.md`

- [ ] **Step 1: Write the orchestrator prompt**

`config/prompts/orchestrator.md`:
```markdown
# Orchestrator — Valuation Workflow

You are a valuation analyst following Aswath Damodaran's methodology. You guide
the user through a structured valuation workflow. At each step, you call
deterministic Python modules and interpret their outputs. You never perform
financial math yourself — all computation is done by the engines.

## Workflow Steps

### Step 1: Receive Ticker or Company Data

When the user says "Value [TICKER]":

1. Call `fetch_financials(ticker)` from `valuation.data.api_client`
2. If it returns None, ask the user to provide financial data manually as a JSON dict
3. Call `normalize(data)` from `valuation.data.normalizer` to create a `ValuationContext`
4. Confirm to the user: "[Company Name] — [Sector] — [Country/Region]"

If the user provides a non-US ticker (e.g., TCS.NS, 0700.HK), note the region
and inform them that country risk premium will be applied.

### Step 2: Classify the Company

1. Call `classify(ctx)` from `valuation.agents.classifier`
2. The classifier returns one of: mature, growth, young, distressed, cyclical, financial
3. Present the classification and reasoning to the user
4. Ask: "Does this classification look right, or would you like to override it?"

Classification determines the model path:
- **financial** → DDM + excess returns (skip DCF/FCFF)
- **mature** → FCFF DCF (shorter high-growth, lower rates)
- **growth** → FCFF DCF (longer high-growth, higher rates, possibly revenue-based)
- **young** → Revenue-based DCF with margin convergence
- **distressed** → DCF with negative growth, probability of failure
- **cyclical** → Normalized earnings DCF

### Step 3: Map to Damodaran Industry

1. Call `map_industry(ctx)` from `valuation.agents.industry_mapper`
2. If the fuzzy match score < 0.7, present the top 3 candidates and ask the user to pick
3. Once mapped, load industry benchmarks (beta, WACC, multiples, margins, growth)
4. Show the user: "Mapped to [Industry] — Industry beta: [X], Industry WACC: [X]%"

### Step 4: Assess Risk (Cost of Capital)

1. Call `assess_risk(ctx, loader)` from `valuation.agents.risk_assessor`
   - This computes: bottom-up beta, cost of equity (CAPM), synthetic rating,
     cost of debt, WACC
   - For non-US companies, it adds country risk premium with lambda
2. Present the full cost of capital breakdown to the user:
   - Risk-free rate, ERP, beta (unlevered → relevered), cost of equity
   - Synthetic rating, default spread, cost of debt
   - Capital structure weights, WACC
3. Ask: "These are the risk parameters. Would you like to adjust any?"

### Step 5: Estimate Growth

1. Call `estimate_growth(ctx, loader)` from `valuation.agents.growth_estimator`
   - This computes fundamental growth (retention x ROE, reinvestment x ROC)
   - It also retrieves historical growth rates and industry benchmarks
2. Read `config/prompts/growth_narrative.md` for reasoning guidance
3. Propose growth assumptions to the user:
   - High-growth rate and duration
   - Transition pattern (gradual or abrupt)
   - Terminal growth rate
   - Reinvestment rates per phase
4. Explain WHY you chose each rate — what is the story?
5. Ask: "Here are the growth assumptions. Would you like to adjust any?"

### Step 6: User Override Gate

This is the critical interactive checkpoint. Present ALL assumptions in a table:

| Parameter | Value | Source |
|-----------|-------|--------|
| WACC | X% | Computed (bottom-up beta) |
| Cost of equity | X% | CAPM |
| Growth (yr 1-5) | X% | Fundamental (retention x ROE) |
| Growth (yr 6-10) | X% | Interpolated to stable |
| Terminal growth | X% | GDP growth proxy |
| Reinvestment rate | X% | Industry average |
| Tax rate | X% | Effective (Damodaran data) |

The user can override any parameter. Track all overrides in
`ctx.assumptions.overrides` with original value and reason.

After overrides, proceed to computation. Do NOT re-ask — one gate is sufficient.

### Step 7: Run Valuation Engines

Based on classification:

**Non-financial companies:**
1. Run `fcff_valuation(...)` from `valuation.engines.dcf`
2. Run `relative_valuation(ctx, loader)` from `valuation.engines.relative`
3. Generate sensitivity table: WACC vs terminal growth (two-way)

**Financial companies:**
1. Run `ddm_valuation(...)` from `valuation.engines.dcf`
2. Run `excess_returns_valuation(ctx, loader)` from `valuation.engines.excess_returns`
3. Run `relative_valuation(ctx, loader)` from `valuation.engines.relative` (P/BV focus)
4. Generate sensitivity table: cost of equity vs stable growth

Store all results in `ctx.outputs`.

### Step 8: Cross-Validate

1. Call `cross_validate(ctx)` from `valuation.agents.cross_validator`
2. Read `config/prompts/cross_validation.md` for interpretation guidance
3. Present divergence analysis:
   - DCF value vs relative value vs excess returns value
   - Percentage divergence
   - Likely reasons for divergence
4. Call `compute_confidence(ctx)` from `valuation.scoring.confidence`

### Step 9: Generate Report

1. Call `generate_report(ctx)` from `valuation.reports.generator`
2. This produces a structured markdown report (deterministic, no LLM)
3. Present the report to the user
4. Offer: "Would you like me to adjust any assumptions and re-run?"

## Decision Rules

### When to Use 2-Stage vs 3-Stage
- 2-stage (abrupt): very stable companies, short projection (5 years)
- 3-stage (gradual): most companies, default choice for 10-year projection

### When to Use Revenue-Based DCF
- Negative operating income in most recent year
- Company classified as "young"
- Company has less than 3 years of positive EBIT

### Terminal Growth Cap
- Terminal growth must be <= risk-free rate
- If computed terminal growth > risk-free rate, cap at risk-free rate - 1%
- Warn the user when capping

### WACC Floor
- If WACC < terminal growth, refuse to compute
- Present error: "WACC (X%) is below terminal growth (Y%). Please adjust assumptions."

## What You Must Never Do

1. Never compute financial math yourself — always call Python modules
2. Never use analyst consensus estimates as inputs to DCF — show them only as comparison
3. Never skip the user override gate
4. Never present a valuation without a confidence score
5. Never claim precision — always present as a range (base case +/- sensitivity)
```

- [ ] **Step 2: Verify the file is readable**

Run: `wc -l config/prompts/orchestrator.md`

Expected: ~130-140 lines

- [ ] **Step 3: Commit**

```bash
git add config/prompts/orchestrator.md
git commit -m "feat: add orchestrator system prompt with 9-step valuation workflow"
```

---

## Task 2: System Prompt — Classifier Heuristics

**Files:**
- Create: `config/prompts/classifier.md`

- [ ] **Step 1: Write the classifier prompt**

`config/prompts/classifier.md`:
```markdown
# Classifier — Company Type Heuristics

When the rule-based classifier returns a result, you review it for ambiguous cases.
The classifier's Python output is the STARTING POINT, not the final answer.

## The Six Types

| Type | Key Indicators | Typical Examples |
|------|---------------|-----------------|
| **mature** | Stable revenue growth (<10%), positive FCF, established margins, regular dividends | 3M, Coca-Cola, P&G |
| **growth** | Revenue growth >15%, high reinvestment, expanding margins or market share, low/no dividends | Tesla (2020), Shopify, early-stage SaaS |
| **young** | <5 years of financials, negative operating income, revenue growing >30%, no clear path to profitability yet | Pre-profit biotech, recent IPO tech |
| **distressed** | Declining revenue, negative or shrinking margins, high debt/EBITDA, liquidity concerns | Sears, J.C. Penney |
| **cyclical** | Revenue swings >20% peak-to-trough, commodity/industrial exposure, margins track economic cycle | Steel producers, airlines, oil E&P |
| **financial** | SIC 6000-6999, revenue is primarily net interest income + fees, regulated capital requirements | Banks, brokerages, insurance, REITs |

## Ambiguous Cases — When Rules Disagree with Reality

### "Growth" vs "Mature" — The Transition Zone

A company is transitioning from growth to mature when:
- Revenue growth has decelerated from >20% to 8-15% over the past 3 years
- Margins have stabilized (not still expanding)
- Company has started paying dividends or doing buybacks
- Market cap > $50B and age > 10 years

**Decision rule:** If revenue growth CAGR (3yr) < 12% AND operating margin stable
(within 2pp of 3-year average), classify as **mature** even if the market treats
it as a growth stock. The market's growth premium is captured in relative valuation,
not in our DCF assumptions.

Examples of this transition:
- **Apple (2020s):** Revenue growth ~5-8%, massive buybacks, stable margins → **mature**
- **Amazon (2024+):** Revenue growth ~10-12%, margins stabilizing → borderline, lean **mature**
- **Google (2024):** Revenue growth ~10%, 20%+ margins, dividends started → **mature**

### "Distressed" vs "Cyclical" — Distinguishing Structural from Temporary

A company in a cyclical trough looks like a distressed company. Distinguish by:
- **History:** Has this company recovered from similar troughs before?
- **Industry:** Is the entire industry down, or just this company?
- **Balance sheet:** Does it have the liquidity to survive the trough?
- **Debt covenants:** Is it at risk of covenant violation?

**Decision rule:** If the INDUSTRY is in a down cycle (industry revenue growth negative)
AND the company's debt-to-EBITDA < 4x AND it has survived at least one prior cycle,
classify as **cyclical**. Otherwise, **distressed**.

### "Financial" Edge Cases

Not everything in SIC 6000-6999 is a traditional financial:
- **REITs:** Technically financial, but value more like real estate companies.
  Use DCF with FFO instead of earnings. Classify as **financial** but flag "REIT"
  in the context for the engine to handle.
- **Fintech:** If revenue is primarily from technology services (not lending/insurance),
  classify as **growth** or **mature** based on other indicators.
- **Insurance:** Traditional insurance = **financial**. Insurtech with SaaS revenue = **growth**.

**Decision rule:** If >60% of revenue comes from net interest income, underwriting
gains, or investment income, classify as **financial**. Otherwise, use the non-financial
classification path.

### "Young" vs "Growth" — When Does a Young Company Become a Growth Company?

- **Young:** Negative operating income, <3 years of financial data, business model
  not yet proven
- **Growth:** Positive operating income (or clear path), >3 years of data, business
  model validated

**Decision rule:** If the company has achieved positive operating income for at least
2 consecutive years, upgrade from **young** to **growth**.

## What to Tell the User

When classification is ambiguous, present it honestly:

> "I've classified [Company] as **[type]** based on [specific data points].
> However, there's a case for **[alternative type]** because [reason].
> The classification affects which valuation model we use:
> - As **[type]**: [model and implications]
> - As **[alternative]**: [model and implications]
> Which classification would you prefer, or should I proceed with **[type]**?"

Never silently choose in ambiguous cases. The user's judgment matters here.
```

- [ ] **Step 2: Commit**

```bash
git add config/prompts/classifier.md
git commit -m "feat: add classifier system prompt with ambiguous-case heuristics"
```

---

## Task 3: System Prompt — Growth Narrative

**Files:**
- Create: `config/prompts/growth_narrative.md`

- [ ] **Step 1: Write the growth narrative prompt**

`config/prompts/growth_narrative.md`:
```markdown
# Growth Narrative — How to Reason About Growth

When the growth estimator returns fundamental growth rates, you evaluate whether
they make sense as a STORY. Numbers without narrative are dangerous. Every growth
rate should answer: "Why will this company grow at this rate?"

## The Three Sources of Growth (Damodaran Ch. 4)

### 1. Historical Growth
- Computed by the growth estimator as CAGR over 3-5 years
- **Use with caution:** past growth does not predict future growth
- Most useful for stable companies with consistent trends
- Least useful for companies undergoing transformation

### 2. Analyst Consensus (I/B/E/S)
- Retrieved from WRDS or yfinance as comparison only
- **Never use as an input to our DCF model**
- Show side-by-side in the report: "Our estimate: X% | Analyst consensus: Y%"
- If our estimate diverges >5pp from consensus, explain why in the narrative

### 3. Fundamental Growth (Our Primary Source)
- **EPS growth** = Retention ratio x ROE
- **Operating income growth** = Reinvestment rate x ROC
- These are the rates the company CAN sustain given its capital allocation

## Evaluating Growth Sustainability

Ask these questions about each growth rate:

### Is the ROE/ROC Sustainable?
- If ROE > 25%, it is likely elevated by leverage or a temporary competitive advantage
- Industry median ROE is a gravitational pull — extreme ROEs revert
- Check: is the high ROE from high margins, high turnover, or high leverage?
  - High margins: sustainable if there's a moat (brand, patents, network effects)
  - High turnover: sustainable if operationally excellent
  - High leverage: risky, not sustainable if rates rise

### Is the Reinvestment Rate Sustainable?
- Reinvestment rate > 80%: company is plowing almost everything back — can it find
  enough good projects?
- Reinvestment rate < 0%: company is shrinking — is this intentional (returning capital)
  or distressed?
- Compare to industry: if company reinvests 2x the industry rate, what is the edge?

### Red Flags in Growth Assumptions
- Growth rate > 20% for > 5 years: almost no company sustains this
- Growth rate > GDP growth in terminal year: what company grows faster than
  the economy FOREVER?
- Negative growth with high reinvestment: capital is being destroyed
- Revenue growing but margins declining: growth is being bought, not earned
- Acquisitive growth (high goodwill): organic growth may be much lower

## Proposing Growth to the User

Structure your growth proposal as a STORY:

> "[Company] earned [ROC]% on its invested capital last year, and reinvested
> [reinvestment rate]% of its after-tax operating income. This implies a
> sustainable operating income growth rate of [X]%.
>
> I recommend using [Y]% for the high-growth period because [reason]:
> - [If Y > fundamental]: the company is expanding into [new market/product]
>   which should temporarily boost returns above the sustainable rate
> - [If Y < fundamental]: the current ROC of [Z]% is above the industry
>   median of [A]%, and I expect mean reversion over [N] years
> - [If Y = fundamental]: the company is in a stable competitive position
>   with consistent reinvestment patterns
>
> For the terminal phase, I recommend [T]% because [it should converge to
> GDP growth / the risk-free rate - 1% / the industry long-run average]."

## Growth Rate Guardrails

| Scenario | Max Recommended Growth | Reason |
|----------|----------------------|--------|
| Large-cap mature (>$100B) | 8-10% high-growth | Too big to grow fast |
| Mid-cap growth ($10-100B) | 15-20% high-growth | Room to expand |
| Small-cap growth (<$10B) | 20-30% high-growth | Addressable market headroom |
| Any company, terminal | Risk-free rate - 1% | Can't outgrow the economy forever |
| Financial company | ROE x (1 - payout) | Regulatory capital constrains growth |

## When Our Growth Diverges from Consensus

If |our_growth - consensus_growth| > 5 percentage points, explain:

1. What drives our estimate (fundamental: retention x ROE = X%)
2. What might drive consensus (likely includes expected margin expansion,
   new products, or management guidance we don't model)
3. Why the divergence is acceptable or a red flag
4. Let the user decide whether to adjust
```

- [ ] **Step 2: Commit**

```bash
git add config/prompts/growth_narrative.md
git commit -m "feat: add growth narrative system prompt with sustainability heuristics"
```

---

## Task 4: System Prompt — Cross-Validation Interpretation

**Files:**
- Create: `config/prompts/cross_validation.md`

- [ ] **Step 1: Write the cross-validation prompt**

`config/prompts/cross_validation.md`:
```markdown
# Cross-Validation — Interpreting Model Divergence

When DCF, relative valuation, and excess returns produce different values,
your job is to explain WHY they disagree and what that means for the
user's decision. Divergence is information, not error.

## Expected Divergence Ranges

| Divergence | Label | Interpretation |
|-----------|-------|----------------|
| < 15% | **Low** | Models agree well. High confidence in the range. |
| 15-30% | **Moderate** | Normal for most companies. Examine drivers. |
| 30-50% | **High** | Significant disagreement. One model may be more appropriate. |
| > 50% | **Very High** | Fundamental disconnect. Flag for user review. |

Divergence = |DCF_value - Relative_value| / average(DCF_value, Relative_value)

## Common Divergence Patterns and Explanations

### DCF > Relative Valuation
**Your DCF says $150/share, industry multiples say $90/share.**

Likely reasons:
1. **Growth assumptions too optimistic.** Your DCF projects higher growth than
   what the market prices into peers. Check: is your growth rate above the
   industry median? If so, you need a strong narrative for why this company
   will outgrow peers.

2. **Discount rate too low.** A lower WACC inflates the DCF value. Check: is
   your beta below the industry average? Did you underweight country risk?

3. **Industry is depressed.** If the entire industry trades at low multiples
   because of a temporary downturn, your DCF (which looks through the cycle)
   will be higher. This is a FEATURE, not a bug — but note it.

4. **Company has competitive advantages not captured in multiples.** If the
   company truly has a moat (higher margins, better growth), DCF should be
   higher than peer multiples. This is legitimate divergence.

### Relative > DCF
**Industry multiples say $150/share, your DCF says $90/share.**

Likely reasons:
1. **Growth assumptions too conservative.** Your fundamental growth rate
   may understate the company's actual growth trajectory. Check: is the
   company in an acceleration phase not captured by retention x ROE?

2. **Industry bubble.** If the entire sector trades at elevated multiples,
   relative valuation is inflated. Your DCF may be more grounded. Flag this.

3. **Discount rate too high.** An elevated WACC suppresses DCF value. Check:
   is your company-specific risk premium (beta, country risk) appropriate?

4. **Terminal value assumptions too conservative.** A low terminal growth
   rate or low terminal ROC compresses the perpetuity value.

### DCF and Relative Agree, Excess Returns Disagrees (Financial Firms)
**DDM says $80, excess returns says $120.**

This usually means:
- **ROE assumption differs.** Excess returns is very sensitive to the spread
  between ROE and cost of equity. A 1pp change in ROE can move value 10-15%.
- **Book value adjustments.** If the bank has significant unrealized losses
  on its bond portfolio, book value is overstated, making excess returns
  optimistic.
- **Regulatory capital impact.** Higher capital requirements reduce future
  ROE. Excess returns may not fully capture this.

## How to Present Divergence to the User

Structure your explanation as:

> **Cross-Validation Summary**
>
> | Model | Value/Share | Weight |
> |-------|-----------|--------|
> | DCF (FCFF) | $[X] | Primary |
> | Relative (EV/EBITDA) | $[Y] | Secondary |
> | Relative (PE) | $[Z] | Secondary |
>
> Divergence: [X]% — [Low/Moderate/High]
>
> The DCF value is [higher/lower] than relative valuation because [specific
> reason from analysis above]. Given [company characteristics], I weight
> the [DCF/relative] model more heavily because [reason].
>
> **Suggested value range:** $[low] — $[high] (based on sensitivity table)
> **Point estimate:** $[midpoint or weighted average]

## Weighting Models

| Company Type | Primary Model | Secondary Model | Why |
|-------------|--------------|-----------------|-----|
| Mature | FCFF DCF | EV/EBITDA, PE | DCF captures company-specific growth; multiples provide market check |
| Growth | FCFF DCF (revenue-based if needed) | EV/Sales, PEG | DCF captures the growth story; PS captures revenue trajectory |
| Financial | DDM + Excess Returns | P/BV | DDM for cash flows, P/BV for ROE vs cost of equity check |
| Distressed | DCF with probability of failure | EV/Sales | Earnings multiples meaningless; revenue multiples provide floor |
| Cyclical | Normalized-earnings DCF | Normalized PE | Must normalize to avoid cycle-dependent valuation |

## When to Override the Cross-Validator

Do NOT blindly average the models. If one model is clearly more appropriate:
- Tell the user which model you trust more and why
- Present the other model's value as a "market check"
- Never hide divergence — transparency builds trust
```

- [ ] **Step 2: Commit**

```bash
git add config/prompts/cross_validation.md
git commit -m "feat: add cross-validation system prompt with divergence interpretation rules"
```

---

## Task 5: System Prompt — Report Narrative Style

**Files:**
- Create: `config/prompts/report.md`

- [ ] **Step 1: Write the report prompt**

`config/prompts/report.md`:
```markdown
# Report Narrative — Story + Numbers

The report generator produces the structured data sections (deterministic Python).
Your job is to write the narrative sections that give the numbers meaning.
Follow Damodaran's "story to numbers" philosophy.

## Narrative Principles

### 1. Lead with the Story
Every valuation tells a story about the company's future. Before showing numbers,
state the thesis in one paragraph:

> "[Company] is a [classification] [industry] company that [key narrative].
> We value [Company] at $[X]/share, [above/below] the current market price
> of $[Y]/share, implying the stock is [overvalued/undervalued/fairly valued]
> by [Z]%."

### 2. Connect Every Number to a Decision
Don't just state "WACC = 8.5%." Instead:

> "We use a WACC of 8.5%, driven by [Company]'s bottom-up beta of 1.1
> (re-levered from the [Industry] industry unlevered beta of 0.95).
> The relatively low beta reflects [reason]."

### 3. Acknowledge Uncertainty
Never present a point estimate without a range:

> "Our base-case value of $[X]/share is most sensitive to [parameter],
> which shifts the value from $[low] to $[high] across reasonable
> assumptions (see sensitivity table)."

### 4. Compare, Don't Assert
Show how our estimate compares to market pricing and analyst consensus:

> | | Our Estimate | Market Price | Analyst Consensus |
> |---|------------|-------------|-------------------|
> | Value/share | $150 | $165 | $170 |
> | Implied growth | 8% | 10% | 11% |
>
> "The market appears to price in 10% growth, above our fundamental
> estimate of 8%. This gap likely reflects [reason]."

Note: analyst consensus is shown for COMPARISON ONLY. It does not feed
into our models.

### 5. Flag What Could Go Wrong
Every report must include a "Key Risks" paragraph:

> "This valuation is most vulnerable to: (1) [risk 1 — impact on value],
> (2) [risk 2 — impact on value], (3) [risk 3 — impact on value]."

## Section-by-Section Narrative Guidance

### Executive Summary (2-3 paragraphs)
- Paragraph 1: The story — what does this company do, what's its trajectory?
- Paragraph 2: The number — our valuation, how it compares, confidence level
- Paragraph 3: The caveat — key risks and sensitivity

### Company Profile (factual, no narrative needed)
- Generated by report generator from ctx data — no LLM writing required

### Key Assumptions (table + narrative)
- Table is generated by report generator
- You add: one sentence per assumption explaining the reasoning
- Flag any overrides: "User adjusted WACC from 8.5% to 9.0% because [reason]"

### DCF Valuation (generated + narrative)
- Cash flow table is generated by report generator
- You add: explain the growth trajectory in plain English
- You add: explain why terminal value is X% of total value (typical for growth companies)

### Relative Valuation (generated + narrative)
- Multiple comparison table is generated by report generator
- You add: which multiple is most appropriate and why
- You add: why the company trades at a premium/discount to peers

### Sensitivity Analysis (generated table, no narrative needed)
- Two-way sensitivity table is generated by report generator
- Highlight the cell that represents our base case

### Confidence Assessment (generated + narrative)
- Score breakdown is generated by report generator
- You add: what would increase confidence (better data, longer history, etc.)

### Appendix (factual, no narrative needed)
- Data sources, Damodaran industry mapping, methodology notes
- Generated by report generator

## Tone and Style

- Professional but not stuffy — imagine writing for a smart investor
- Use "we" not "I" — this is analysis, not opinion
- Avoid hedge fund jargon — no "alpha generation" or "asymmetric risk/reward"
- Be specific — "revenue grew 12% YoY" not "revenue showed strong growth"
- Numbers: use commas for thousands, 2 decimal places for percentages
- Currency: always specify (USD, INR, etc.)
```

- [ ] **Step 2: Commit**

```bash
git add config/prompts/report.md
git commit -m "feat: add report narrative system prompt with story-to-numbers style guide"
```

---

## Task 6: Report Template (Jinja2)

**Files:**
- Create: `src/valuation/reports/templates/valuation_report.md`

- [ ] **Step 1: Add Jinja2 dependency**

In `pyproject.toml`, add `"Jinja2>=3.1"` to the `dependencies` list.

- [ ] **Step 2: Write the Jinja2 template**

`src/valuation/reports/templates/valuation_report.md`:
```markdown
# Valuation Report: {{ company.name }} ({{ company.ticker }})

**Date:** {{ report_date }}
**Classification:** {{ company.classification | capitalize }}
**Industry (Damodaran):** {{ company.damodaran_industry }}
**Region:** {{ company.region }}

---

## Executive Summary

<!-- LLM writes this section using config/prompts/report.md guidance -->

**Valuation Range:** {{ currency }}{{ value_low | format_number }} — {{ currency }}{{ value_high | format_number }} per share
**Base Case:** {{ currency }}{{ value_base | format_number }} per share
**Current Market Price:** {{ currency }}{{ market_price | format_number }}
**Implied Upside/Downside:** {{ upside_pct }}%
**Confidence:** {{ confidence.label }} ({{ confidence.composite | pct }})

---

## Company Profile

| Attribute | Value |
|-----------|-------|
| Name | {{ company.name }} |
| Ticker | {{ company.ticker }} |
| Sector | {{ company.sector }} |
| Industry (yfinance) | {{ key_stats.industry_yfinance }} |
| Industry (Damodaran) | {{ company.damodaran_industry }} |
| Region | {{ company.region }} |
| Market Cap | {{ currency }}{{ key_stats.market_cap | format_number }} |
| Shares Outstanding | {{ key_stats.shares_outstanding | format_number }} |
| Current Price | {{ currency }}{{ key_stats.price | format_number }} |

---

## Key Assumptions

| Parameter | Value | Source | Override? |
|-----------|-------|--------|-----------|
| Risk-Free Rate | {{ assumptions.risk_free_rate | pct }} | {{ sources.risk_free_rate }} | {{ "Yes" if "risk_free_rate" in overrides else "No" }} |
| Equity Risk Premium | {{ assumptions.erp | pct }} | {{ sources.erp }} | {{ "Yes" if "erp" in overrides else "No" }} |
| Beta (levered) | {{ assumptions.beta | round4 }} | {{ sources.beta }} | {{ "Yes" if "beta" in overrides else "No" }} |
| Cost of Equity | {{ assumptions.cost_of_equity | pct }} | CAPM | No |
| Cost of Debt (pre-tax) | {{ assumptions.cost_of_debt | pct }} | Synthetic rating | {{ "Yes" if "cost_of_debt" in overrides else "No" }} |
| WACC | {{ assumptions.wacc | pct }} | Computed | {{ "Yes" if "wacc" in overrides else "No" }} |
| Tax Rate | {{ assumptions.tax_rate | pct }} | {{ sources.tax_rate }} | {{ "Yes" if "tax_rate" in overrides else "No" }} |
| Projection Years | {{ assumptions.projection_years }} | Default | No |
| Terminal Growth | {{ assumptions.terminal_growth | pct }} | {{ sources.terminal_growth }} | {{ "Yes" if "terminal_growth" in overrides else "No" }} |
{% if assumptions.country_risk_premium > 0 %}
| Country Risk Premium | {{ assumptions.country_risk_premium | pct }} | Damodaran ctryprem | {{ "Yes" if "country_risk_premium" in overrides else "No" }} |
{% endif %}

{% if overrides %}
### User Overrides

{% for param, details in overrides.items() %}
- **{{ param }}:** Changed from {{ details.original }} to {{ details.new }}{% if details.reason %} — _{{ details.reason }}_{% endif %}

{% endfor %}
{% endif %}

<!-- LLM adds narrative explaining each key assumption -->

---

## Growth Assumptions

| Year | Growth Rate | Reinvestment Rate | EBIT(1-t) |
|------|-----------|------------------|-----------|
{% for i in range(n_years) %}
| {{ i + 1 }} | {{ growth_rates[i] | pct }} | {{ reinvestment_rates[i] | pct }} | {{ currency }}{{ yearly_ebit_at[i] | format_number }} |
{% endfor %}
| Terminal | {{ assumptions.terminal_growth | pct }} | {{ stable_reinvestment | pct }} | — |

---

{% if dcf_fcff %}
## DCF Valuation (FCFF)

| Year | EBIT(1-t) | Reinvestment | FCFF | PV(FCFF) |
|------|----------|-------------|------|----------|
{% for i in range(n_years) %}
| {{ i + 1 }} | {{ currency }}{{ yearly_ebit_at[i] | format_number }} | {{ currency }}{{ (yearly_ebit_at[i] * reinvestment_rates[i]) | format_number }} | {{ currency }}{{ yearly_fcff[i] | format_number }} | {{ currency }}{{ yearly_pv[i] | format_number }} |
{% endfor %}

| Component | Value |
|-----------|-------|
| PV of High-Growth FCFFs | {{ currency }}{{ dcf_fcff.pv_high_growth | format_number }} |
| Terminal Value (undiscounted) | {{ currency }}{{ dcf_fcff.terminal_value | format_number }} |
| PV of Terminal Value | {{ currency }}{{ dcf_fcff.pv_terminal | format_number }} |
| **Enterprise Value** | **{{ currency }}{{ dcf_fcff.enterprise_value | format_number }}** |
| + Cash | {{ currency }}{{ bridge.cash | format_number }} |
| - Debt | {{ currency }}{{ bridge.debt | format_number }} |
{% if bridge.non_operating_assets %}| + Non-Operating Assets | {{ currency }}{{ bridge.non_operating_assets | format_number }} |{% endif %}
{% if bridge.options_value %}| - Employee Options | {{ currency }}{{ bridge.options_value | format_number }} |{% endif %}
| **Equity Value** | **{{ currency }}{{ dcf_fcff.equity_value | format_number }}** |
| Shares Outstanding | {{ key_stats.shares_outstanding | format_number }} |
| **Value per Share** | **{{ currency }}{{ dcf_fcff.equity_value_per_share | format_number }}** |

<!-- LLM adds narrative about the DCF -->
{% endif %}

{% if ddm %}
## DDM Valuation

| Year | EPS | Payout | DPS | PV(DPS) |
|------|-----|--------|-----|---------|
{% for i in range(n_years) %}
| {{ i + 1 }} | {{ currency }}{{ ddm.yearly_eps[i] | format_number }} | {{ payout_rates[i] | pct }} | {{ currency }}{{ ddm.yearly_dps[i] | format_number }} | {{ currency }}{{ ddm.yearly_pv[i] | format_number }} |
{% endfor %}

| Component | Value |
|-----------|-------|
| PV of Dividends | {{ currency }}{{ ddm.pv_dividends | format_number }} |
| Terminal Price | {{ currency }}{{ ddm.terminal_price | format_number }} |
| PV of Terminal Price | {{ currency }}{{ ddm.pv_terminal | format_number }} |
| **Value per Share** | **{{ currency }}{{ ddm.value_per_share | format_number }}** |

<!-- LLM adds narrative about the DDM -->
{% endif %}

{% if excess_returns %}
## Excess Returns Valuation

| Component | Value |
|-----------|-------|
| Book Value of Equity | {{ currency }}{{ excess_returns.book_equity | format_number }} |
| PV of Excess Returns | {{ currency }}{{ excess_returns.pv_excess | format_number }} |
| **Equity Value** | **{{ currency }}{{ excess_returns.equity_value | format_number }}** |
| **Value per Share** | **{{ currency }}{{ excess_returns.value_per_share | format_number }}** |
{% endif %}

---

## Relative Valuation

| Multiple | Company | Industry Median | Implied Value/Share |
|----------|---------|----------------|-------------------|
{% for name, data in relative.items() %}
| {{ name }} | {{ data.company_value | round4 }} | {{ data.industry_median | round4 }} | {{ currency }}{{ data.implied_value | format_number }} |
{% endfor %}

<!-- LLM adds narrative about relative valuation -->

---

## Cross-Validation

| Model | Value/Share | vs Base Case |
|-------|-----------|-------------|
{% for model_name, model_value in cross_validation_table.items() %}
| {{ model_name }} | {{ currency }}{{ model_value | format_number }} | {{ ((model_value - value_base) / value_base * 100) | round1 }}% |
{% endfor %}

**Model Divergence:** {{ divergence_pct }}% — {{ divergence_label }}

<!-- LLM adds divergence interpretation using config/prompts/cross_validation.md -->

---

## Sensitivity Analysis

### WACC vs Terminal Growth (Value per Share)

| | {% for tg in sensitivity_col_values %}{{ tg | pct }} | {% endfor %}
|---|{% for _ in sensitivity_col_values %}---|{% endfor %}

{% for wacc_val in sensitivity_row_values %}
| **{{ wacc_val | pct }}** | {% for tg in sensitivity_col_values %}{{ currency }}{{ sensitivity_table[wacc_val][tg] | format_number }} | {% endfor %}

{% endfor %}

_Base case highlighted: WACC={{ assumptions.wacc | pct }}, Terminal Growth={{ assumptions.terminal_growth | pct }}_

---

## Confidence Assessment

| Dimension | Score | Weight |
|-----------|-------|--------|
| Data Completeness | {{ confidence.data_completeness | pct }} | 30% |
| Model Agreement | {{ confidence.model_agreement | pct }} | 30% |
| Assumption Sensitivity | {{ confidence.assumption_sensitivity | pct }} | 25% |
| Industry Coverage | {{ confidence.industry_coverage | pct }} | 15% |
| **Composite** | **{{ confidence.composite | pct }}** | |
| **Label** | **{{ confidence.label }}** | |

{% if confidence.flags %}
### Flags

{% for flag in confidence.flags %}
- {{ flag }}
{% endfor %}
{% endif %}

<!-- LLM adds narrative about what would increase confidence -->

---

## Our Estimate vs Analyst Consensus

| Metric | Our Estimate | Analyst Consensus |
|--------|-------------|-------------------|
| Value/Share | {{ currency }}{{ value_base | format_number }} | {{ currency }}{{ consensus.target_price | format_number if consensus.target_price else "N/A" }} |
| Growth (5yr) | {{ our_growth_5yr | pct }} | {{ consensus.growth_5yr | pct if consensus.growth_5yr else "N/A" }} |
| EPS (next year) | {{ currency }}{{ our_eps_next | format_number if our_eps_next else "N/A" }} | {{ currency }}{{ consensus.eps_next | format_number if consensus.eps_next else "N/A" }} |

_Note: Analyst consensus is shown for comparison only. Our estimates are derived
independently from fundamental analysis using Damodaran methodology._

---

## Appendix

### Data Sources
- **Financial statements:** {{ data_source }} ({{ financials_years }} years)
- **Industry benchmarks:** Damodaran Online datasets ({{ damodaran_date }})
- **Risk-free rate:** {{ assumptions.risk_free_rate | pct }} (10-year US Treasury)
- **Equity risk premium:** {{ assumptions.erp | pct }} (Damodaran implied ERP)

### Methodology
- **DCF Model:** {{ dcf_model_type }}
- **Valuation approach:** Damodaran (Investment Valuation / The Dark Side of Valuation)
- **Beta:** Bottom-up, unlevered from {{ company.damodaran_industry }} industry, re-levered with company D/E
- **Growth:** Fundamental (reinvestment rate x return on capital)
- **Terminal value:** Perpetuity with stable growth, reinvestment = g/ROC

### Confidence Scoring
Composite = 0.30 x Data Completeness + 0.30 x Model Agreement + 0.25 x Assumption Sensitivity + 0.15 x Industry Coverage
```

- [ ] **Step 3: Commit**

```bash
git add src/valuation/reports/templates/valuation_report.md pyproject.toml
git commit -m "feat: add Jinja2 report template with all valuation sections"
```

---

## Task 7: Report Generator

**Files:**
- Create: `src/valuation/reports/generator.py`
- Create: `tests/test_report_generator.py`

- [ ] **Step 1: Write failing tests**

`tests/test_report_generator.py`:
```python
"""Tests for the deterministic report generator."""

import pytest
from valuation.context import ValuationContext
from valuation.reports.generator import generate_report, _format_number, _pct


class TestFormatHelpers:
    def test_format_number_positive(self):
        assert _format_number(1234567.89) == "1,234,567.89"

    def test_format_number_negative(self):
        assert _format_number(-500.1) == "-500.10"

    def test_format_number_zero(self):
        assert _format_number(0) == "0.00"

    def test_format_number_none(self):
        assert _format_number(None) == "N/A"

    def test_pct_normal(self):
        assert _pct(0.0895) == "8.95%"

    def test_pct_none(self):
        assert _pct(None) == "N/A"

    def test_pct_zero(self):
        assert _pct(0.0) == "0.00%"


def _build_complete_context() -> ValuationContext:
    """Build a ValuationContext with all fields populated for report testing."""
    ctx = ValuationContext(ticker="TEST")
    ctx.company.name = "Test Corporation"
    ctx.company.sector = "Technology"
    ctx.company.classification = "mature"
    ctx.company.damodaran_industry = "Software (System & Application)"
    ctx.company.region = "US"

    ctx.financials.key_stats = {
        "shares_outstanding": 1000.0,
        "market_cap": 50000.0,
        "price": 50.0,
        "beta": 1.1,
        "dividend_per_share": 1.5,
        "book_value_per_share": 30.0,
        "industry_yfinance": "Software—Application",
        "country": "United States",
    }

    ctx.assumptions.risk_free_rate = 0.0395
    ctx.assumptions.erp = 0.0446
    ctx.assumptions.beta = 1.1
    ctx.assumptions.cost_of_equity = 0.0886
    ctx.assumptions.cost_of_debt = 0.0484
    ctx.assumptions.wacc = 0.0850
    ctx.assumptions.tax_rate = 0.21
    ctx.assumptions.terminal_growth = 0.03
    ctx.assumptions.projection_years = 5
    ctx.assumptions.growth_rates = [0.08, 0.08, 0.065, 0.05, 0.04]

    ctx.outputs.dcf_fcff = {
        "enterprise_value": 55000.0,
        "equity_value": 48000.0,
        "equity_value_per_share": 48.0,
        "pv_high_growth": 15000.0,
        "pv_terminal": 40000.0,
        "terminal_value": 60000.0,
        "yearly_fcff": [5000.0, 5400.0, 5600.0, 5800.0, 5900.0],
        "yearly_pv": [4600.0, 4500.0, 4200.0, 3900.0, 3700.0],
        "yearly_ebit_at": [7000.0, 7560.0, 8050.0, 8453.0, 8791.0],
    }

    ctx.outputs.relative = {
        "PE": {
            "company_value": 20.0,
            "industry_median": 25.0,
            "implied_value": 62.5,
        },
        "EV/EBITDA": {
            "company_value": 12.0,
            "industry_median": 14.0,
            "implied_value": 58.3,
        },
    }

    ctx.outputs.sensitivity = {
        0.075: {0.02: 55.0, 0.03: 60.0, 0.04: 68.0},
        0.085: {0.02: 42.0, 0.03: 48.0, 0.04: 55.0},
        0.095: {0.02: 35.0, 0.03: 40.0, 0.04: 46.0},
    }

    ctx.confidence.data_completeness = 0.90
    ctx.confidence.model_agreement = 0.75
    ctx.confidence.assumption_sensitivity = 0.80
    ctx.confidence.industry_coverage = 0.95
    ctx.confidence.composite = 0.84
    ctx.confidence.flags = [
        "DCF and relative valuation diverge by 22%",
        "Terminal value represents 73% of enterprise value",
    ]

    return ctx


class TestGenerateReport:
    def test_report_returns_string(self):
        ctx = _build_complete_context()
        report = generate_report(ctx)
        assert isinstance(report, str)
        assert len(report) > 500

    def test_report_contains_company_name(self):
        ctx = _build_complete_context()
        report = generate_report(ctx)
        assert "Test Corporation" in report
        assert "TEST" in report

    def test_report_contains_executive_summary_section(self):
        ctx = _build_complete_context()
        report = generate_report(ctx)
        assert "## Executive Summary" in report

    def test_report_contains_key_assumptions_section(self):
        ctx = _build_complete_context()
        report = generate_report(ctx)
        assert "## Key Assumptions" in report
        assert "8.50%" in report  # WACC
        assert "3.00%" in report  # terminal growth

    def test_report_contains_dcf_section(self):
        ctx = _build_complete_context()
        report = generate_report(ctx)
        assert "## DCF Valuation" in report
        assert "48,000.00" in report  # equity value
        assert "48.00" in report  # per share

    def test_report_contains_relative_valuation(self):
        ctx = _build_complete_context()
        report = generate_report(ctx)
        assert "## Relative Valuation" in report
        assert "PE" in report
        assert "EV/EBITDA" in report

    def test_report_contains_sensitivity_table(self):
        ctx = _build_complete_context()
        report = generate_report(ctx)
        assert "## Sensitivity Analysis" in report

    def test_report_contains_confidence_section(self):
        ctx = _build_complete_context()
        report = generate_report(ctx)
        assert "## Confidence Assessment" in report
        assert "84.00%" in report  # composite
        assert "diverge by 22%" in report  # flag

    def test_report_contains_appendix(self):
        ctx = _build_complete_context()
        report = generate_report(ctx)
        assert "## Appendix" in report
        assert "Damodaran" in report

    def test_report_no_dcf_when_financial(self):
        ctx = _build_complete_context()
        ctx.company.classification = "financial"
        ctx.outputs.dcf_fcff = None
        ctx.outputs.excess_returns = {
            "book_equity": 30000.0,
            "pv_excess": 5000.0,
            "equity_value": 35000.0,
            "value_per_share": 35.0,
        }
        report = generate_report(ctx)
        assert "## DCF Valuation (FCFF)" not in report
        assert "## Excess Returns" in report

    def test_report_shows_overrides(self):
        ctx = _build_complete_context()
        ctx.assumptions.set_override("wacc", 0.09, reason="User thinks risk is higher")
        report = generate_report(ctx)
        assert "Override" in report or "override" in report
        assert "User thinks risk is higher" in report

    def test_report_with_ddm(self):
        ctx = _build_complete_context()
        ctx.company.classification = "financial"
        ctx.outputs.dcf_fcff = None
        ctx.outputs.dcf_fcfe = {
            "value_per_share": 55.0,
            "pv_dividends": 8.0,
            "pv_terminal": 47.0,
            "terminal_price": 80.0,
            "yearly_eps": [5.0, 5.5, 6.0],
            "yearly_dps": [2.0, 2.2, 2.5],
            "yearly_pv": [1.8, 1.9, 2.0],
        }
        report = generate_report(ctx)
        assert "## DDM Valuation" in report
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_report_generator.py -v`

Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write the report generator implementation**

`src/valuation/reports/generator.py`:
```python
"""Deterministic report generator — assembles ValuationContext into markdown.

No LLM calls. Pure string formatting. The LLM adds narrative sections
separately using the config/prompts/report.md guidance.
"""

from __future__ import annotations

import pathlib
from datetime import date
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

from valuation.context import ValuationContext


TEMPLATE_DIR = pathlib.Path(__file__).parent / "templates"


def _format_number(value: float | None, decimals: int = 2) -> str:
    """Format a number with comma separators and fixed decimals."""
    if value is None:
        return "N/A"
    return f"{value:,.{decimals}f}"


def _pct(value: float | None) -> str:
    """Format a decimal as a percentage string."""
    if value is None:
        return "N/A"
    return f"{value * 100:.2f}%"


def _round4(value: float | None) -> str:
    """Round to 4 decimal places."""
    if value is None:
        return "N/A"
    return f"{value:.4f}"


def _round1(value: float | None) -> str:
    """Round to 1 decimal place."""
    if value is None:
        return "N/A"
    return f"{value:.1f}"


def _confidence_label(composite: float | None) -> str:
    """Map composite confidence score to a human label."""
    if composite is None:
        return "Unknown"
    if composite >= 0.80:
        return "High"
    if composite >= 0.60:
        return "Moderate"
    if composite >= 0.40:
        return "Low"
    return "Speculative"


def _build_template_context(ctx: ValuationContext) -> dict[str, Any]:
    """Extract all template variables from a ValuationContext."""
    dcf = ctx.outputs.dcf_fcff
    ddm = ctx.outputs.dcf_fcfe
    excess = ctx.outputs.excess_returns
    relative = ctx.outputs.relative or {}
    sensitivity = ctx.outputs.sensitivity or {}

    # Determine base value from primary model
    if dcf:
        value_base = dcf["equity_value_per_share"]
    elif ddm:
        value_base = ddm["value_per_share"]
    elif excess:
        value_base = excess.get("value_per_share", 0)
    else:
        value_base = 0

    # Compute value range from sensitivity table
    all_values = []
    for row in sensitivity.values():
        if isinstance(row, dict):
            all_values.extend(v for v in row.values() if isinstance(v, (int, float)))
    value_low = min(all_values) if all_values else value_base * 0.8
    value_high = max(all_values) if all_values else value_base * 1.2

    market_price = ctx.financials.key_stats.get("price", 0) or 0
    upside_pct = ((value_base - market_price) / market_price * 100) if market_price else 0

    # Cross-validation table
    cross_validation_table = {}
    if dcf:
        cross_validation_table["DCF (FCFF)"] = dcf["equity_value_per_share"]
    if ddm:
        cross_validation_table["DDM"] = ddm["value_per_share"]
    if excess:
        cross_validation_table["Excess Returns"] = excess.get("value_per_share", 0)
    for mult_name, mult_data in relative.items():
        if isinstance(mult_data, dict) and "implied_value" in mult_data:
            cross_validation_table[f"Relative ({mult_name})"] = mult_data["implied_value"]

    # Divergence
    cv_values = [v for v in cross_validation_table.values() if v and v > 0]
    if len(cv_values) >= 2:
        divergence_pct = abs(max(cv_values) - min(cv_values)) / (sum(cv_values) / len(cv_values)) * 100
    else:
        divergence_pct = 0
    if divergence_pct < 15:
        divergence_label = "Low"
    elif divergence_pct < 30:
        divergence_label = "Moderate"
    elif divergence_pct < 50:
        divergence_label = "High"
    else:
        divergence_label = "Very High"

    # Growth rates and reinvestment rates
    growth_rates = ctx.assumptions.growth_rates or []
    n_years = len(growth_rates) or ctx.assumptions.projection_years

    # Reinvestment rates — extract from DCF output if available
    reinvestment_rates = []
    if dcf and "yearly_ebit_at" in dcf and "yearly_fcff" in dcf:
        for ebit, fcff in zip(dcf["yearly_ebit_at"], dcf["yearly_fcff"]):
            if ebit != 0:
                reinvestment_rates.append(1 - fcff / ebit)
            else:
                reinvestment_rates.append(0)
    else:
        reinvestment_rates = [0.30] * n_years  # fallback

    # Stable reinvestment
    stable_roc = 0.10  # default
    tg = ctx.assumptions.terminal_growth or 0.03
    stable_reinvestment = tg / stable_roc if stable_roc > 0 else 0

    # Bridge values
    bridge = {
        "cash": 0,
        "debt": 0,
        "non_operating_assets": 0,
        "options_value": 0,
    }

    # Sensitivity table structure
    sensitivity_row_values = sorted(sensitivity.keys()) if sensitivity else []
    sensitivity_col_values = sorted(list(sensitivity.values())[0].keys()) if sensitivity else []

    # Currency
    region = ctx.company.region
    currency_map = {"US": "$", "India": "₹", "Japan": "¥", "China": "¥", "Europe": "€"}
    currency = currency_map.get(region, "$")

    # Confidence
    confidence_data = {
        "data_completeness": ctx.confidence.data_completeness,
        "model_agreement": ctx.confidence.model_agreement,
        "assumption_sensitivity": ctx.confidence.assumption_sensitivity,
        "industry_coverage": ctx.confidence.industry_coverage,
        "composite": ctx.confidence.composite,
        "label": _confidence_label(ctx.confidence.composite),
        "flags": ctx.confidence.flags or [],
    }

    # Payout rates (for DDM display)
    payout_rates = []
    if ddm and "yearly_eps" in ddm and "yearly_dps" in ddm:
        for eps, dps in zip(ddm["yearly_eps"], ddm["yearly_dps"]):
            payout_rates.append(dps / eps if eps != 0 else 0)

    return {
        "company": ctx.company,
        "key_stats": ctx.financials.key_stats,
        "assumptions": ctx.assumptions,
        "overrides": ctx.assumptions.overrides,
        "sources": {
            "risk_free_rate": "10yr Treasury",
            "erp": "Damodaran implied ERP",
            "beta": f"Bottom-up ({ctx.company.damodaran_industry})",
            "tax_rate": "Effective (Damodaran)",
            "terminal_growth": "GDP growth proxy",
        },
        "growth_rates": growth_rates,
        "reinvestment_rates": reinvestment_rates,
        "stable_reinvestment": stable_reinvestment,
        "n_years": n_years,
        "dcf_fcff": dcf,
        "ddm": ddm,
        "excess_returns": excess,
        "relative": relative,
        "yearly_ebit_at": dcf.get("yearly_ebit_at", []) if dcf else [],
        "yearly_fcff": dcf.get("yearly_fcff", []) if dcf else [],
        "yearly_pv": dcf.get("yearly_pv", []) if dcf else [],
        "payout_rates": payout_rates,
        "bridge": bridge,
        "sensitivity_table": sensitivity,
        "sensitivity_row_values": sensitivity_row_values,
        "sensitivity_col_values": sensitivity_col_values,
        "cross_validation_table": cross_validation_table,
        "divergence_pct": f"{divergence_pct:.1f}",
        "divergence_label": divergence_label,
        "value_base": value_base,
        "value_low": value_low,
        "value_high": value_high,
        "market_price": market_price,
        "upside_pct": f"{upside_pct:.1f}",
        "currency": currency,
        "confidence": confidence_data,
        "report_date": date.today().isoformat(),
        "data_source": "Yahoo Finance",
        "financials_years": 5,
        "damodaran_date": "January 2026",
        "dcf_model_type": _dcf_model_label(ctx),
        "consensus": {
            "target_price": None,
            "growth_5yr": None,
            "eps_next": None,
        },
        "our_growth_5yr": growth_rates[0] if growth_rates else None,
        "our_eps_next": None,
    }


def _dcf_model_label(ctx: ValuationContext) -> str:
    """Return a human-readable label for the DCF model used."""
    cls = ctx.company.classification
    if cls == "financial":
        return "DDM (Dividend Discount Model) + Excess Returns"
    if cls == "young":
        return "Revenue-based FCFF DCF with margin convergence"
    if cls == "distressed":
        return "FCFF DCF with negative growth and probability of failure"
    if cls == "cyclical":
        return "FCFF DCF with normalized earnings"
    return "FCFF DCF (multi-stage)"


def generate_report(ctx: ValuationContext) -> str:
    """Generate a complete valuation report from a ValuationContext.

    Returns a markdown string. All data is deterministic — no LLM calls.
    Narrative placeholder comments are left for Claude Code to fill in.

    Parameters
    ----------
    ctx : ValuationContext
        Fully populated context with outputs from all engines.

    Returns
    -------
    str
        Markdown-formatted valuation report.
    """
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATE_DIR)),
        autoescape=select_autoescape([]),
        keep_trailing_newline=True,
    )

    # Register custom filters
    env.filters["format_number"] = _format_number
    env.filters["pct"] = _pct
    env.filters["round4"] = _round4
    env.filters["round1"] = _round1

    template = env.get_template("valuation_report.md")
    template_ctx = _build_template_context(ctx)
    return template.render(**template_ctx)
```

- [ ] **Step 4: Run tests**

Run: `python3 -m pytest tests/test_report_generator.py -v`

Expected: All 14 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/valuation/reports/generator.py tests/test_report_generator.py
git commit -m "feat: add deterministic report generator with Jinja2 templating"
```

---

## Task 8: CLAUDE.md — Master Orchestrator

**Files:**
- Create: `CLAUDE.md`

- [ ] **Step 1: Write CLAUDE.md**

`CLAUDE.md`:
```markdown
# Valuation Agent — Claude Code Instructions

You are a valuation analyst powered by Damodaran methodology. When a user asks
you to value a company, you follow the workflow below step by step, calling
Python modules at each stage. You NEVER perform financial math yourself.

## Quick Start

When the user says "Value [TICKER]" or "Analyze [TICKER]":

```bash
cd "/mnt/c/Users/Manan Sharma/Desktop/Coding projects/Valuation/0. Valuation Agent"
```

Then follow the workflow below.

## Environment Setup

```bash
# Activate the project (if not already)
pip install -e ".[dev]" 2>/dev/null
```

## Workflow

### Step 1: Fetch Data

```python
from valuation.data.api_client import fetch_financials
from valuation.data.normalizer import normalize

data = fetch_financials("TICKER")
if data is None:
    # Ask user for manual data input
    pass
ctx = normalize(data)
print(f"{ctx.company.name} — {ctx.company.sector} — {ctx.company.region}")
```

If the API fails, ask the user to provide data as a Python dict following the
`CompanyData` schema in `src/valuation/data/api_client.py`.

### Step 2: Load Damodaran Data

```python
from valuation.data.damodaran_loader import DamodaranLoader

DAMODARAN_DIR = "/mnt/c/Users/Manan Sharma/Desktop/Coding projects/Valuation/2. Damodaran_Data"
loader = DamodaranLoader(DAMODARAN_DIR)
```

### Step 3: Classify Company

```python
from valuation.agents.classifier import classify

classification = classify(ctx)
print(f"Classification: {ctx.company.classification} — {classification['reasoning']}")
```

Present the classification to the user. Ask if they agree. Read
`config/prompts/classifier.md` for guidance on ambiguous cases.

### Step 4: Map to Damodaran Industry

```python
from valuation.agents.industry_mapper import map_industry

mapping = map_industry(ctx, loader)
print(f"Industry: {ctx.company.damodaran_industry} (score: {mapping['score']:.2f})")
```

If the mapping score < 0.7, present the top 3 candidates and ask the user to pick.

### Step 5: Assess Risk

```python
from valuation.agents.risk_assessor import (
    compute_cost_of_equity, compute_cost_of_debt, compute_wacc,
    relever_beta, get_synthetic_rating
)

# Get industry beta from Damodaran
beta_row = loader.lookup("betas", ctx.company.damodaran_industry, region=ctx.company.region)
# ... compute bottom-up beta, CAPM, WACC
# Store results in ctx.assumptions
```

Present the full cost of capital breakdown. Ask if the user wants to adjust.

### Step 6: Estimate Growth

```python
from valuation.agents.growth_estimator import estimate_growth

growth = estimate_growth(ctx, loader)
print(growth['summary'])
```

Read `config/prompts/growth_narrative.md` for guidance on proposing growth rates.
Present growth assumptions. Ask if the user wants to adjust.

### Step 7: User Override Gate

Present ALL assumptions in a table. The user can override any parameter:

```python
# Example override
ctx.assumptions.set_override("wacc", 0.09, reason="User prefers higher discount rate")
```

### Step 8: Run Valuation Engines

**For non-financial companies:**

```python
from valuation.engines.dcf import fcff_valuation, interpolate_params, two_way_sensitivity_table
from valuation.engines.relative import relative_valuation

# Build parameter arrays
growth_rates = ctx.assumptions.growth_rates
reinvestment_rates = interpolate_params(...)
waccs = interpolate_params(...)

# Run FCFF DCF
result = fcff_valuation(
    current_ebit_after_tax=...,
    growth_rates=growth_rates,
    reinvestment_rates=reinvestment_rates,
    waccs=waccs,
    stable_growth=ctx.assumptions.terminal_growth,
    stable_roc=...,
    stable_wacc=...,
    cash=...,
    debt=...,
    shares_outstanding=ctx.financials.key_stats["shares_outstanding"],
)
ctx.outputs.dcf_fcff = result

# Run relative valuation
rel = relative_valuation(ctx, loader)
ctx.outputs.relative = rel

# Generate sensitivity table
sens = two_way_sensitivity_table(...)
ctx.outputs.sensitivity = sens
```

**For financial companies:**

```python
from valuation.engines.dcf import ddm_valuation
from valuation.engines.excess_returns import excess_returns_valuation

# Run DDM
ddm_result = ddm_valuation(...)
ctx.outputs.dcf_fcfe = ddm_result

# Run excess returns
excess = excess_returns_valuation(ctx, loader)
ctx.outputs.excess_returns = excess
```

### Step 9: Cross-Validate

```python
from valuation.agents.cross_validator import cross_validate
from valuation.scoring.confidence import compute_confidence

cross_validate(ctx)
compute_confidence(ctx)
```

Read `config/prompts/cross_validation.md` for guidance on interpreting divergence.

### Step 10: Generate Report

```python
from valuation.reports.generator import generate_report

report = generate_report(ctx)
print(report)
```

The report generator produces the structured data sections. You then add
narrative to the placeholder sections following `config/prompts/report.md`.

## System Prompts (Read These for Judgment Calls)

| File | When to Read |
|------|-------------|
| `config/prompts/orchestrator.md` | At session start — full workflow reference |
| `config/prompts/classifier.md` | When classification is ambiguous |
| `config/prompts/growth_narrative.md` | When proposing growth assumptions |
| `config/prompts/cross_validation.md` | When interpreting model divergence |
| `config/prompts/report.md` | When writing narrative sections of the report |

## Rules

1. **Never compute math yourself.** Call the Python engines.
2. **Never use consensus estimates as model inputs.** Show them for comparison only.
3. **Always present assumptions before computing.** Let the user override.
4. **Always include confidence score.** Never present a bare number.
5. **Present values as ranges**, not point estimates (use sensitivity table).
6. **Track every override** with `ctx.assumptions.set_override()`.
7. **Be transparent about data gaps.** If data is missing, say so.

## Testing

```bash
# Run all tests
python3 -m pytest tests/ -v -k "not network"

# Run with network (fetches real data)
python3 -m pytest tests/ -v

# Run golden tests only
python3 -m pytest tests/test_golden.py -v
```

## Project Structure

```
src/valuation/
├── context.py              # ValuationContext — shared data contract
├── data/
│   ├── api_client.py       # Yahoo Finance data fetching
│   ├── damodaran_loader.py # Damodaran Excel file parser
│   ├── normalizer.py       # Raw data → ValuationContext
│   └── wrds_client.py      # WRDS/Compustat client
├── agents/
│   ├── classifier.py       # Company type classification
│   ├── industry_mapper.py  # Map to Damodaran industry
│   ├── risk_assessor.py    # WACC, CAPM, beta, cost of debt
│   ├── growth_estimator.py # Growth rate estimation
│   └── cross_validator.py  # Model reconciliation
├── engines/
│   ├── dcf.py              # Gordon Growth, FCFF, DDM
│   ├── relative.py         # Multiples-based valuation
│   └── excess_returns.py   # Financial firm valuation
├── scoring/
│   └── confidence.py       # Confidence score computation
└── reports/
    ├── generator.py        # Deterministic report assembly
    └── templates/
        └── valuation_report.md  # Jinja2 template
```
```

- [ ] **Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "feat: add CLAUDE.md orchestrator with step-by-step valuation workflow"
```

---

## Task 9: End-to-End Integration Tests

**Files:**
- Create: `tests/test_integration_e2e.py`

These tests simulate the full pipeline using synthetic data (no network calls).
They verify that all modules wire together correctly from ticker to report.

- [ ] **Step 1: Write the integration tests**

`tests/test_integration_e2e.py`:
```python
"""End-to-end integration tests: full pipeline from context to report.

Uses synthetic data (no network calls, no API dependencies).
Tests 3 company archetypes: mature US, financial, emerging market.
"""

import pytest
from valuation.context import ValuationContext
from valuation.engines.dcf import (
    fcff_valuation,
    ddm_valuation,
    gordon_growth_value,
    interpolate_params,
    two_way_sensitivity_table,
)
from valuation.agents.risk_assessor import (
    compute_cost_of_equity,
    compute_cost_of_debt,
    compute_wacc,
    relever_beta,
    get_synthetic_rating,
)
from valuation.reports.generator import generate_report


def _build_mature_us_context() -> ValuationContext:
    """Simulate a mature US technology company (Apple-like)."""
    ctx = ValuationContext(ticker="MATURE", region="US")
    ctx.company.name = "Mature Tech Corp"
    ctx.company.sector = "Technology"
    ctx.company.classification = "mature"
    ctx.company.damodaran_industry = "Software (System & Application)"

    ctx.financials.key_stats = {
        "shares_outstanding": 15000.0,
        "market_cap": 3000000.0,
        "price": 200.0,
        "beta": 1.15,
        "dividend_per_share": 3.28,
        "book_value_per_share": 4.25,
        "industry_yfinance": "Consumer Electronics",
        "country": "United States",
    }

    # Risk assessment
    ctx.assumptions.risk_free_rate = 0.0395
    ctx.assumptions.erp = 0.0446
    ctx.assumptions.country_risk_premium = 0.0
    ctx.assumptions.beta = 1.15
    ctx.assumptions.cost_of_equity = compute_cost_of_equity(0.0395, 1.15, 0.0446)
    ctx.assumptions.cost_of_debt = compute_cost_of_debt(0.0395, 12.0, "large")
    ctx.assumptions.tax_rate = 0.21
    ctx.assumptions.wacc = compute_wacc(
        ctx.assumptions.cost_of_equity, ctx.assumptions.cost_of_debt,
        ctx.assumptions.tax_rate, 0.90, 0.10,
    )

    # Growth
    ctx.assumptions.growth_rates = [0.07, 0.07, 0.06, 0.05, 0.04]
    ctx.assumptions.terminal_growth = 0.03
    ctx.assumptions.projection_years = 5

    return ctx


def _build_financial_context() -> ValuationContext:
    """Simulate a large US bank (Goldman-like)."""
    ctx = ValuationContext(ticker="BANK", region="US")
    ctx.company.name = "Big Bank Corp"
    ctx.company.sector = "Financial Services"
    ctx.company.classification = "financial"
    ctx.company.damodaran_industry = "Banks (Money Center)"

    ctx.financials.key_stats = {
        "shares_outstanding": 340.0,
        "market_cap": 170000.0,
        "price": 500.0,
        "beta": 1.3,
        "dividend_per_share": 10.0,
        "book_value_per_share": 300.0,
        "industry_yfinance": "Banks—Diversified",
        "country": "United States",
    }

    ctx.assumptions.risk_free_rate = 0.0395
    ctx.assumptions.erp = 0.0446
    ctx.assumptions.beta = 1.3
    ctx.assumptions.cost_of_equity = compute_cost_of_equity(0.0395, 1.3, 0.0446)
    ctx.assumptions.tax_rate = 0.21
    ctx.assumptions.growth_rates = interpolate_params(0.10, 0.04, 10, gradual=True)
    ctx.assumptions.terminal_growth = 0.04
    ctx.assumptions.projection_years = 10

    return ctx


def _build_emerging_context() -> ValuationContext:
    """Simulate an Indian IT company (TCS-like)."""
    ctx = ValuationContext(ticker="EMRG", region="India")
    ctx.company.name = "Emerging Tech Ltd"
    ctx.company.sector = "Technology"
    ctx.company.classification = "growth"
    ctx.company.damodaran_industry = "IT Services"

    ctx.financials.key_stats = {
        "shares_outstanding": 3700.0,
        "market_cap": 14000000.0,
        "price": 3784.0,
        "beta": 0.75,
        "dividend_per_share": 75.0,
        "book_value_per_share": 250.0,
        "industry_yfinance": "Information Technology Services",
        "country": "India",
    }

    ctx.assumptions.risk_free_rate = 0.0395
    ctx.assumptions.erp = 0.0446
    ctx.assumptions.country_risk_premium = 0.0168
    ctx.assumptions.beta = 0.75
    ctx.assumptions.cost_of_equity = compute_cost_of_equity(
        0.0395, 0.75, 0.0446, country_risk_premium=0.0168, lambda_country=0.2,
    )
    ctx.assumptions.cost_of_debt = compute_cost_of_debt(0.0395, 8.0, "large")
    ctx.assumptions.tax_rate = 0.254
    ctx.assumptions.wacc = compute_wacc(
        ctx.assumptions.cost_of_equity, ctx.assumptions.cost_of_debt,
        ctx.assumptions.tax_rate, 0.95, 0.05,
    )
    ctx.assumptions.growth_rates = interpolate_params(0.12, 0.04, 10, gradual=True)
    ctx.assumptions.terminal_growth = 0.04
    ctx.assumptions.projection_years = 10

    return ctx


class TestMatureUSEndToEnd:
    """Full pipeline for a mature US company."""

    def test_risk_assessment_reasonable(self):
        ctx = _build_mature_us_context()
        assert 0.05 < ctx.assumptions.cost_of_equity < 0.15
        assert 0.03 < ctx.assumptions.cost_of_debt < 0.10
        assert 0.05 < ctx.assumptions.wacc < 0.12

    def test_dcf_produces_positive_value(self):
        ctx = _build_mature_us_context()
        current_ebit_at = 120000.0  # ~$120B EBIT(1-t) for Apple-scale
        reinv_rates = interpolate_params(0.25, 0.15, 5, gradual=True)

        result = fcff_valuation(
            current_ebit_after_tax=current_ebit_at,
            growth_rates=ctx.assumptions.growth_rates,
            reinvestment_rates=reinv_rates,
            waccs=[ctx.assumptions.wacc] * 5,
            stable_growth=0.03,
            stable_roc=0.20,
            stable_wacc=ctx.assumptions.wacc,
            cash=60000.0,
            debt=110000.0,
            shares_outstanding=ctx.financials.key_stats["shares_outstanding"],
        )
        ctx.outputs.dcf_fcff = result
        assert result["equity_value_per_share"] > 0
        assert result["enterprise_value"] > result["equity_value"]  # has net debt

    def test_sensitivity_table_has_right_shape(self):
        ctx = _build_mature_us_context()
        base_params = {
            "current_dividend": ctx.financials.key_stats["dividend_per_share"],
            "cost_of_equity": ctx.assumptions.cost_of_equity,
            "growth_rate": ctx.assumptions.terminal_growth,
        }
        table = two_way_sensitivity_table(
            base_params=base_params,
            row_param="growth_rate",
            row_values=[0.01, 0.02, 0.03, 0.04],
            col_param="cost_of_equity",
            col_values=[0.06, 0.07, 0.08, 0.09, 0.10],
            valuation_fn=gordon_growth_value,
        )
        assert len(table) == 4
        assert len(table[0.01]) == 5
        # Higher growth should mean higher value for same Ke
        assert table[0.03][0.08] > table[0.01][0.08]
        # Higher Ke should mean lower value for same growth
        assert table[0.02][0.06] > table[0.02][0.10]

    def test_full_report_generation(self):
        ctx = _build_mature_us_context()
        current_ebit_at = 120000.0
        reinv_rates = interpolate_params(0.25, 0.15, 5, gradual=True)

        result = fcff_valuation(
            current_ebit_after_tax=current_ebit_at,
            growth_rates=ctx.assumptions.growth_rates,
            reinvestment_rates=reinv_rates,
            waccs=[ctx.assumptions.wacc] * 5,
            stable_growth=0.03,
            stable_roc=0.20,
            stable_wacc=ctx.assumptions.wacc,
            cash=60000.0,
            debt=110000.0,
            shares_outstanding=ctx.financials.key_stats["shares_outstanding"],
        )
        ctx.outputs.dcf_fcff = result

        ctx.outputs.relative = {
            "PE": {"company_value": 28.0, "industry_median": 30.0, "implied_value": 214.3},
            "EV/EBITDA": {"company_value": 18.0, "industry_median": 20.0, "implied_value": 222.2},
        }

        ctx.outputs.sensitivity = {
            0.07: {0.02: 220.0, 0.03: 250.0, 0.04: 290.0},
            0.08: {0.02: 180.0, 0.03: 205.0, 0.04: 240.0},
            0.09: {0.02: 155.0, 0.03: 175.0, 0.04: 200.0},
        }

        ctx.confidence.data_completeness = 0.95
        ctx.confidence.model_agreement = 0.82
        ctx.confidence.assumption_sensitivity = 0.75
        ctx.confidence.industry_coverage = 0.90
        ctx.confidence.composite = 0.86
        ctx.confidence.flags = ["Terminal value is 68% of enterprise value"]

        report = generate_report(ctx)
        assert "Mature Tech Corp" in report
        assert "## Executive Summary" in report
        assert "## DCF Valuation" in report
        assert "## Relative Valuation" in report
        assert "## Sensitivity Analysis" in report
        assert "## Confidence Assessment" in report
        assert "86.00%" in report
        assert "## Appendix" in report
        assert "$" in report  # USD currency


class TestFinancialEndToEnd:
    """Full pipeline for a financial company."""

    def test_ddm_produces_positive_value(self):
        ctx = _build_financial_context()
        payout_rates = interpolate_params(0.12, 0.60, 10, gradual=True)
        ke_rates = interpolate_params(
            ctx.assumptions.cost_of_equity, 0.085, 10, gradual=True,
        )

        result = ddm_valuation(
            current_eps=40.0,
            growth_rates=ctx.assumptions.growth_rates,
            payout_rates=payout_rates,
            cost_of_equities=ke_rates,
            stable_growth=0.04,
            stable_roe=0.10,
            stable_ke=0.085,
        )
        ctx.outputs.dcf_fcfe = result
        assert result["value_per_share"] > 0
        assert result["pv_terminal"] > result["pv_dividends"]  # typical for low payout

    def test_financial_report_has_ddm_not_fcff(self):
        ctx = _build_financial_context()
        payout_rates = interpolate_params(0.12, 0.60, 10, gradual=True)
        ke_rates = interpolate_params(
            ctx.assumptions.cost_of_equity, 0.085, 10, gradual=True,
        )

        result = ddm_valuation(
            current_eps=40.0,
            growth_rates=ctx.assumptions.growth_rates,
            payout_rates=payout_rates,
            cost_of_equities=ke_rates,
            stable_growth=0.04,
            stable_roe=0.10,
            stable_ke=0.085,
        )
        ctx.outputs.dcf_fcfe = result
        ctx.outputs.relative = {
            "P/BV": {"company_value": 1.67, "industry_median": 1.2, "implied_value": 360.0},
        }
        ctx.outputs.sensitivity = {
            0.08: {0.03: 550.0, 0.04: 620.0},
            0.09: {0.03: 450.0, 0.04: 510.0},
        }
        ctx.confidence.data_completeness = 0.85
        ctx.confidence.model_agreement = 0.70
        ctx.confidence.assumption_sensitivity = 0.65
        ctx.confidence.industry_coverage = 0.80
        ctx.confidence.composite = 0.76
        ctx.confidence.flags = []

        report = generate_report(ctx)
        assert "## DDM Valuation" in report
        assert "## DCF Valuation (FCFF)" not in report
        assert "Big Bank Corp" in report
        assert "financial" in report.lower()


class TestEmergingMarketEndToEnd:
    """Full pipeline for an emerging market company."""

    def test_country_risk_applied(self):
        ctx = _build_emerging_context()
        # Cost of equity should include country risk premium
        ke_without_crp = 0.0395 + 0.75 * 0.0446  # ~7.3%
        assert ctx.assumptions.cost_of_equity > ke_without_crp

    def test_dcf_with_country_risk(self):
        ctx = _build_emerging_context()
        current_ebit_at = 500000.0  # in INR millions
        reinv_rates = interpolate_params(0.35, 0.20, 10, gradual=True)

        result = fcff_valuation(
            current_ebit_after_tax=current_ebit_at,
            growth_rates=ctx.assumptions.growth_rates,
            reinvestment_rates=reinv_rates,
            waccs=[ctx.assumptions.wacc] * 10,
            stable_growth=0.04,
            stable_roc=0.15,
            stable_wacc=ctx.assumptions.wacc,
            cash=200000.0,
            debt=50000.0,
            shares_outstanding=ctx.financials.key_stats["shares_outstanding"],
        )
        ctx.outputs.dcf_fcff = result
        assert result["equity_value_per_share"] > 0

    def test_emerging_report_uses_inr(self):
        ctx = _build_emerging_context()
        current_ebit_at = 500000.0
        reinv_rates = interpolate_params(0.35, 0.20, 10, gradual=True)

        result = fcff_valuation(
            current_ebit_after_tax=current_ebit_at,
            growth_rates=ctx.assumptions.growth_rates,
            reinvestment_rates=reinv_rates,
            waccs=[ctx.assumptions.wacc] * 10,
            stable_growth=0.04,
            stable_roc=0.15,
            stable_wacc=ctx.assumptions.wacc,
            cash=200000.0,
            debt=50000.0,
            shares_outstanding=ctx.financials.key_stats["shares_outstanding"],
        )
        ctx.outputs.dcf_fcff = result
        ctx.outputs.relative = {
            "PE": {"company_value": 30.0, "industry_median": 25.0, "implied_value": 3150.0},
        }
        ctx.outputs.sensitivity = {
            0.07: {0.03: 4000.0, 0.04: 4500.0},
            0.08: {0.03: 3200.0, 0.04: 3700.0},
        }
        ctx.confidence.data_completeness = 0.80
        ctx.confidence.model_agreement = 0.65
        ctx.confidence.assumption_sensitivity = 0.70
        ctx.confidence.industry_coverage = 0.75
        ctx.confidence.composite = 0.73
        ctx.confidence.flags = [
            "Country risk premium applied (India: 1.68%)",
            "3 of 12 financial fields imputed from industry averages",
        ]

        report = generate_report(ctx)
        assert "Emerging Tech Ltd" in report
        assert "\u20b9" in report  # INR symbol
        assert "Country Risk Premium" in report
        assert "India" in report


class TestOverrideTracking:
    """Verify that user overrides are tracked and visible in the report."""

    def test_override_appears_in_report(self):
        ctx = _build_mature_us_context()
        ctx.assumptions.set_override("wacc", 0.09, reason="Sector volatility elevated")
        ctx.assumptions.set_override("terminal_growth", 0.025, reason="Conservative GDP assumption")

        # Minimal outputs to generate report
        ctx.outputs.dcf_fcff = {
            "enterprise_value": 50000.0,
            "equity_value": 40000.0,
            "equity_value_per_share": 40.0,
            "pv_high_growth": 10000.0,
            "pv_terminal": 40000.0,
            "terminal_value": 55000.0,
            "yearly_fcff": [5000.0] * 5,
            "yearly_pv": [4000.0] * 5,
            "yearly_ebit_at": [7000.0] * 5,
        }
        ctx.outputs.relative = {}
        ctx.outputs.sensitivity = {}
        ctx.confidence.composite = 0.80
        ctx.confidence.data_completeness = 0.90
        ctx.confidence.model_agreement = 0.80
        ctx.confidence.assumption_sensitivity = 0.75
        ctx.confidence.industry_coverage = 0.85
        ctx.confidence.flags = []

        report = generate_report(ctx)
        assert "Sector volatility elevated" in report
        assert "Conservative GDP assumption" in report
        assert "9.00%" in report  # overridden WACC
        assert "2.50%" in report  # overridden terminal growth


class TestEdgeCases:
    """Test edge cases that should not crash."""

    def test_no_relative_valuation(self):
        ctx = _build_mature_us_context()
        ctx.outputs.dcf_fcff = {
            "enterprise_value": 50000.0,
            "equity_value": 40000.0,
            "equity_value_per_share": 40.0,
            "pv_high_growth": 10000.0,
            "pv_terminal": 40000.0,
            "terminal_value": 55000.0,
            "yearly_fcff": [5000.0] * 5,
            "yearly_pv": [4000.0] * 5,
            "yearly_ebit_at": [7000.0] * 5,
        }
        ctx.outputs.relative = {}
        ctx.outputs.sensitivity = {}
        ctx.confidence.composite = 0.50
        ctx.confidence.data_completeness = 0.60
        ctx.confidence.model_agreement = 0.50
        ctx.confidence.assumption_sensitivity = 0.40
        ctx.confidence.industry_coverage = 0.50
        ctx.confidence.flags = ["No relative valuation computed"]

        report = generate_report(ctx)
        assert isinstance(report, str)
        assert "Mature Tech Corp" in report

    def test_wacc_below_terminal_growth_raises(self):
        with pytest.raises(ValueError, match="wacc.*must.*greater.*stable_growth"):
            fcff_valuation(
                current_ebit_after_tax=100.0,
                growth_rates=[0.05],
                reinvestment_rates=[0.30],
                waccs=[0.02],
                stable_growth=0.03,
                stable_roc=0.10,
                stable_wacc=0.02,
            )

    def test_gordon_growth_rate_exceeds_ke_raises(self):
        with pytest.raises(ValueError, match="growth_rate.*must.*less.*cost_of_equity"):
            gordon_growth_value(
                current_dividend=2.0,
                cost_of_equity=0.05,
                growth_rate=0.06,
            )
```

- [ ] **Step 2: Run all integration tests**

Run: `python3 -m pytest tests/test_integration_e2e.py -v`

Expected: All tests PASS (14 tests across 5 test classes)

- [ ] **Step 3: Run full test suite**

Run: `python3 -m pytest -v -k "not network"`

Expected: All tests PASS across all test files

- [ ] **Step 4: Commit**

```bash
git add tests/test_integration_e2e.py
git commit -m "test: add end-to-end integration tests for mature US, financial, and emerging market companies"
```

---

## Task 10: Final Verification & Push

- [ ] **Step 1: Verify all files exist**

```bash
ls -la config/prompts/
# Should show: orchestrator.md, classifier.md, growth_narrative.md, cross_validation.md, report.md

ls -la src/valuation/reports/
# Should show: __init__.py, generator.py, templates/

ls -la src/valuation/reports/templates/
# Should show: valuation_report.md

ls -la CLAUDE.md
# Should exist
```

- [ ] **Step 2: Run full test suite**

Run: `python3 -m pytest -v -k "not network"`

Expected: All tests PASS — zero failures

- [ ] **Step 3: Verify report generator works standalone**

```bash
python3 -c "
from valuation.context import ValuationContext
from valuation.reports.generator import generate_report

ctx = ValuationContext(ticker='DEMO')
ctx.company.name = 'Demo Corp'
ctx.company.classification = 'mature'
ctx.company.damodaran_industry = 'Software'
ctx.assumptions.wacc = 0.085
ctx.assumptions.risk_free_rate = 0.04
ctx.assumptions.erp = 0.045
ctx.assumptions.beta = 1.1
ctx.assumptions.cost_of_equity = 0.09
ctx.assumptions.cost_of_debt = 0.05
ctx.assumptions.tax_rate = 0.21
ctx.assumptions.terminal_growth = 0.03
ctx.assumptions.growth_rates = [0.08, 0.06, 0.05]
ctx.financials.key_stats = {'shares_outstanding': 100, 'market_cap': 5000, 'price': 50.0, 'beta': 1.1, 'dividend_per_share': 1.0, 'book_value_per_share': 20.0, 'industry_yfinance': 'Software', 'country': 'US'}
ctx.outputs.dcf_fcff = {'enterprise_value': 6000, 'equity_value': 5500, 'equity_value_per_share': 55.0, 'pv_high_growth': 1500, 'pv_terminal': 4500, 'terminal_value': 6000, 'yearly_fcff': [400, 420, 440], 'yearly_pv': [370, 360, 350], 'yearly_ebit_at': [600, 636, 668]}
ctx.outputs.relative = {'PE': {'company_value': 22.0, 'industry_median': 25.0, 'implied_value': 56.8}}
ctx.outputs.sensitivity = {0.07: {0.02: 65.0, 0.03: 72.0}, 0.085: {0.02: 50.0, 0.03: 55.0}, 0.10: {0.02: 40.0, 0.03: 44.0}}
ctx.confidence.composite = 0.82
ctx.confidence.data_completeness = 0.90
ctx.confidence.model_agreement = 0.85
ctx.confidence.assumption_sensitivity = 0.78
ctx.confidence.industry_coverage = 0.80
ctx.confidence.flags = ['Terminal value is 75% of enterprise value']

report = generate_report(ctx)
print(report[:500])
print('...')
print(f'Report length: {len(report)} chars')
"
```

Expected: Report renders without errors, shows first 500 chars of formatted markdown

- [ ] **Step 4: Push**

```bash
git push origin main
```

---

## Sprint 5 Completion Checklist

After all tasks are done, verify these acceptance criteria:

- [ ] `python3 -m pytest -v -k "not network"` — all tests pass
- [ ] 5 system prompt files exist in `config/prompts/` (orchestrator, classifier, growth_narrative, cross_validation, report)
- [ ] Report generator produces valid markdown from a complete ValuationContext
- [ ] Report includes all required sections: Executive Summary, Company Profile, Key Assumptions, DCF/DDM, Relative Valuation, Sensitivity, Confidence, Appendix
- [ ] Report correctly switches between FCFF and DDM based on classification
- [ ] Report shows user overrides with original values and reasons
- [ ] Report uses correct currency symbol based on region (USD, INR, etc.)
- [ ] Jinja2 template renders without errors for all 3 company archetypes
- [ ] CLAUDE.md exists and describes the complete 10-step workflow
- [ ] End-to-end tests pass for: mature US company, financial company, emerging market company
- [ ] WACC < terminal_growth correctly raises ValueError
- [ ] Confidence score and flags appear in the generated report
- [ ] "Our Estimate vs Analyst Consensus" section present with comparison-only framing
- [ ] Sensitivity table renders as a proper 2D grid
