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
