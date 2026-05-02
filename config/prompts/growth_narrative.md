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
