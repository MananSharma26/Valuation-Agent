# Sprint 3: Data Validation & Transparency Layer

Implement the data validation and transparency layer for the valuation agent. The goal is: never silently produce a wrong answer. Every number must be traceable, every assumption flagged, every missing input surfaced.

## IMPLEMENTATION ORDER (critical — do not rearrange)

Phase A: Add new structures and validation layer (nothing breaks, old defaults still in place)
Phase B: Wire validation into the pipeline (engine now checks before running)
Phase C: Remove silent defaults (safe because Phase B catches None before it reaches math)

---

## Phase A: New Structures

### A1. Source Tracking

Add a `source` tag to every data point that flows into ValuationContext. Create a wrapper:

```python
@dataclass
class SourcedValue:
    value: float | None
    source: Literal["compustat", "yahoo_finance", "damodaran_industry", "user_input", "assumed_default", "missing"]
    confidence: float  # 1.0 for hard data, 0.5 for industry proxy, 0.2 for assumed default, 0.0 for missing
```

Refactor CompanyData and ValuationContext to use SourcedValue for all numeric fields. Every data client (api_client.py, wrds_client.py, damodaran_loader.py) must tag its outputs.

### A2. Sanity Bounds Definition

Add a bounds checker module. Define ranges:

- beta: 0.3 to 3.5 (warn), 0 to 5.0 (hard error)
- WACC: 3% to 30% (warn), outside = halt
- terminal_growth: must be < risk_free_rate (cap at rf - 1% per Damodaran)
- revenue_growth: -30% to +60% (warn if outside)
- operating_margin: -50% to 80% (warn if outside)
- shares_outstanding: must be > 0 (halt if zero)
- reinvestment_rate: -1.0 to 2.0 (warn if outside)
- debt_to_capital: 0 to 0.95 (warn if outside)

### A3. Confidence Score Calculator

Implement the confidence penalty system:
- Start at 1.0
- -0.15 per critical field that used an industry proxy instead of company data
- -0.10 per moderate field that used assumed default
- -0.05 per sanity bound warning triggered
- Floor at 0.1

---

## Phase B: Wire Into Pipeline

### B1. Pre-Engine Validation

Before any engine runs, validate all required inputs. Produce a MissingDataReport listing every None field, its impact level (critical/moderate/low), and suggested action (use industry proxy, ask user, or halt).

- Critical fields that MUST halt if missing: revenue, shares_outstanding, risk_free_rate, equity_risk_premium
- Fields that can use industry proxy with a flag: beta, growth_rate, cost_of_debt, tax_rate

### B2. Sanity Bounds Enforcement

Run bounds checker before and after engine computation:
- Before: validate inputs are in range
- After: validate outputs make sense (e.g., per-share value > 0, not astronomical)

If a value is outside warn range, flag it in output. If outside hard range, halt with error.

### B3. Sensitivity Analysis

After computing base-case valuation, run ±10% perturbation on: WACC, terminal_growth, revenue_growth_rate, operating_margin, tax_rate. Record % change in per-share value for each. Tag the top 3 most sensitive inputs.

Populate the existing `sensitivity: dict` and `assumption_sensitivity: float` fields in Outputs/Confidence dataclasses.

---

## Phase C: Remove Silent Defaults

NOW it is safe to:
- Remove all `or 0` / `default=0` patterns in api_client.py and normalizer.py
- If a field is None, store as SourcedValue(value=None, source="missing", confidence=0.0)
- The Phase B validation layer will catch these before they reach the engine

---

## Output Transparency

The final valuation output must include:
- A "Data Sources" table showing every key input, its value, source, and confidence
- An "Assumptions & Flags" section listing every assumption made, especially where data was missing
- A "Sensitivity" section showing which inputs move the needle most
- An overall confidence score with breakdown

## Constraints
- All validation logic must be deterministic Python — no LLM calls for math or bounds checking
- Write tests for: missing data halt, sanity bound triggers, confidence penalty calculation, sensitivity computation
- Do not break existing DCF engine math — this is a layer around it, not a rewrite
- Run existing tests after each phase to confirm nothing regresses
