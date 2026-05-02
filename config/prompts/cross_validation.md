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
