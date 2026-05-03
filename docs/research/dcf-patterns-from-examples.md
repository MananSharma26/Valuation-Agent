# DCF Patterns Extracted from Damodaran Example Spreadsheets

**Date:** 2026-05-02
**Source files:** `/3. Valuation examples/` -- 3Mprecrisis.xls, AmazonSept18.xlsx, NvidiaJan2025.xlsx, tatasteel.xls, amgen.xls
**Purpose:** Extract exact formulas and transition logic for WACC, tax rate, reinvestment, and R&D capitalization

---

## 1. WACC Transition

### Two spreadsheet architectures

Damodaran uses two different spreadsheet designs:

1. **Old-style (xls):** Used for 3M, Tata Steel. Has a "Master Inputs" sheet with explicit high-growth and stable-growth parameters. The "Valuation Model" sheet computes WACC per year. The user can opt into "gradually adjust your high growth inputs in the second half" (a Yes/No toggle).

2. **New-style (xlsx):** Used for Amazon, Nvidia. Has an "Input sheet" with a single initial cost of capital and a terminal cost of capital. The "Valuation output" sheet handles the transition formulaically with a fixed 5-year linear ramp in years 6-10.

### Pattern A: Old-style (3M, Tata Steel) -- Gradual adjustment in second half

**3M (5-year high-growth period, gradual adjustment = Yes):**

| Year | WACC     | Growth  | Reinvestment Rate |
|------|----------|---------|-------------------|
| 1    | 8.629%   | 7.50%   | 30.00%            |
| 2    | 8.629%   | 7.50%   | 30.00%            |
| 3    | 8.255%   | 6.60%   | 32.88%            |
| 4    | 7.506%   | 4.80%   | 38.64%            |
| 5    | 6.757%   | 3.00%   | 44.40%            |
| Stable | 6.757% | 3.00%  | 44.40%            |

The transition starts at the midpoint of the high-growth period (year ceil(N/2)+1 = year 3 for N=5). From the midpoint to the end, WACC linearly interpolates from the high-growth WACC to the stable WACC.

**Stable WACC computation (old-style):**
```
Ke_stable = Rf + Beta_stable * ERP + Lambda * CRP_stable
WACC_stable = Ke_stable * (E/(D+E))_stable + Kd_stable * (1 - t_stable) * (D/(D+E))_stable
```

For 3M: Ke = 3.72% + 1.0 * 4% = 7.72%, WACC = 7.72% * 80% + 4.47% * (1-35%) * 20% = 6.757%

**Tata Steel (5-year, gradual adjustment = No):**

| Year | WACC     |
|------|----------|
| 1-5  | 13.787%  |
| Stable | 11.160% |

When gradual adjustment is off, WACC stays constant at the high-growth value through all years, then jumps to stable.

Stable WACC: Ke = 5% + 1.2 * 4.5% + 1.1 * 3% = 13.7%, WACC = 13.7% * 70.4% + 7.75% * (1-33.99%) * 29.6% = 11.16%

### Pattern B: New-style (Amazon, Nvidia) -- Always linear ramp in years 6-10

**Amazon (10-year projection):**

| Year | WACC    |
|------|---------|
| 1-5  | 7.970%  |
| 6    | 7.876%  |
| 7    | 7.782%  |
| 8    | 7.688%  |
| 9    | 7.594%  |
| 10   | 7.500%  |
| Terminal | 7.500% |

**Nvidia (10-year projection):**

| Year | WACC     |
|------|----------|
| 1-5  | 11.794%  |
| 6    | 11.135%  |
| 7    | 10.476%  |
| 8    | 9.817%   |
| 9    | 9.159%   |
| 10   | 8.500%   |
| Terminal | 8.500% |

**Exact formula (from Amazon row 12, new-style):**
```
Years 1-5:   WACC_t = initial_WACC                           (constant)
Year 6:      WACC_6 = WACC_5 - (WACC_5 - WACC_terminal) / 5
Year 7:      WACC_7 = WACC_6 - (WACC_5 - WACC_terminal) / 5
...
Year 10:     WACC_10 = WACC_9 - (WACC_5 - WACC_terminal) / 5 = WACC_terminal
```

This is a linear interpolation over 5 steps from year 5 value to terminal value.

**Terminal WACC formula (new-style):**
```
Default:  WACC_terminal = Rf + 4.5%
Override: User can specify a custom value

# Nvidia variant adds country risk premium:
WACC_terminal = Rf + 4.5% + country_risk_premium   (if no override)
```

Amazon: Rf=3%, default would be 7.5%. Override set to 7.5% (same).
Nvidia: Rf=4.7%, default would be 9.2%. Override set to 8.5%.

### Unified transition rule

Regardless of spreadsheet vintage:
- **High-growth phase:** WACC is constant at the computed initial value
- **Transition phase:** Linear interpolation from high-growth WACC to stable WACC
  - Old-style: transition starts at midpoint of N-year period (ceil(N/2)+1), ends at year N
  - New-style: transition is always years 6-10 (5 steps), high-growth is always years 1-5
- **Terminal:** WACC = user override, or default = Rf + 4.5% (+ country risk premium if applicable)

---

## 2. Tax Rate Transition

### Pattern: Same structure as WACC -- constant then linear ramp

**Amazon:**

| Year | Tax Rate |
|------|----------|
| 1-5  | 20.20%   |
| 6    | 20.96%   |
| 7    | 21.72%   |
| 8    | 22.48%   |
| 9    | 23.24%   |
| 10   | 24.00%   |
| Terminal | 24.00% |

**Nvidia:**

| Year | Tax Rate |
|------|----------|
| 1-5  | 13.50%   |
| 6    | 15.80%   |
| 7    | 18.10%   |
| 8    | 20.40%   |
| 9    | 22.70%   |
| 10   | 25.00%   |
| Terminal | 25.00% |

**3M:** Tax rate = 35% throughout (effective = marginal, so no transition needed).

**Tata Steel:** Tax rate = 28.90% in high growth (effective), 33.99% in stable (marginal). No gradual transition (since "gradually adjust" = No for this file, but the tax transition follows the same pattern as WACC).

**Exact formula (from Amazon row 6):**
```
Years 1-5 (high growth):   tax_t = effective_tax_rate
Year 6:                    tax_6 = tax_5 + (marginal - tax_5) / 5
Year 7:                    tax_7 = tax_6 + (marginal - tax_5) / 5
...
Year 10:                   tax_10 = marginal_tax_rate
Terminal:                  IF override = "Yes" THEN effective ELSE marginal
```

The step size is `(marginal_rate - effective_rate) / 5`, applied linearly over years 6-10.

**Override logic:**
- Default: terminal tax rate = marginal tax rate (transition happens)
- Override ("Do you want to override"): terminal tax rate stays at effective (no transition)

### NOL (Net Operating Loss) interaction

The EBIT(1-t) calculation is NOT simply `EBIT * (1-t)`. It accounts for NOL carryforwards:
```
IF EBIT > 0:
    IF EBIT < NOL_remaining:
        EBIT_after_tax = EBIT         (fully shielded, no tax)
    ELSE:
        EBIT_after_tax = EBIT - (EBIT - NOL_remaining) * tax_rate
ELSE:
    EBIT_after_tax = EBIT              (no tax on losses)
```

The NOL accumulates: `NOL_t = max(0, NOL_{t-1} - EBIT_t)` (decreases as income uses it up).

---

## 3. Sales-to-Capital Reinvestment

### Two approaches: Traditional vs. Sales-to-Capital

#### Traditional approach (3M, Tata Steel -- old-style spreadsheets)

Used when the company has stable, positive earnings and predictable capex patterns.

```
Reinvestment = (CapEx - Depreciation) + Change_in_Working_Capital
Reinvestment_Rate = Reinvestment / EBIT(1-t)
Growth = Reinvestment_Rate * ROC
```

3M: Reinvestment rate = 30% in high growth, 44.4% in stable.
Stable reinvestment rate derived from fundamentals: `g / ROC = 3% / 6.757% = 44.4%`

#### Sales-to-Capital approach (Amazon, Nvidia -- new-style spreadsheets)

Used for high-growth companies where reinvestment is driven by revenue growth rather than existing earnings.

**Core formula:**
```
Reinvestment_t = (Revenue_t - Revenue_{t-1}) / Sales_to_Capital_Ratio
```

This computes how much capital must be invested to support each dollar of revenue growth.

**Amazon values:**
- Sales-to-capital ratio: 5.947 (constant across all 10 years)
- Source: `'Input sheet'!B26` = single user input
- Applied identically in every year

**Amazon exact formula (row 8):**
```
Reinvestment_year_t = (Revenue_t - Revenue_{t-1}) / Sales_to_Capital
```

**Nvidia values:**
- Sales-to-capital ratio years 1-5: 2.5 (`'Input sheet'!B30`)
- Sales-to-capital ratio years 6-10: 2.5 (`'Input sheet'!B31`)
- Two separate inputs allow different efficiency in high-growth vs. transition

**Nvidia reinvestment lag feature:**
Nvidia introduces a reinvestment lag option (`'Input sheet'!B67-B68`). The lag shifts which year's revenue growth drives reinvestment:
```
lag=0: Reinvestment_t = (Revenue_t - Revenue_{t-1}) / S2C     (same year)
lag=1: Reinvestment_t = (Revenue_{t+1} - Revenue_t) / S2C     (next year, DEFAULT)
lag=2: Reinvestment_t = (Revenue_{t+2} - Revenue_{t+1}) / S2C (two years ahead)
lag=3: Reinvestment_t = (Revenue_{t+3} - Revenue_{t+2}) / S2C (three years ahead)
```

Nvidia uses lag=3, meaning reinvestment today funds growth 3 years from now. This is critical for capital-intensive businesses where investment takes years to generate revenue.

**Terminal year reinvestment (both Amazon and Nvidia):**
```
Terminal_Reinvestment = (g / ROC) * EBIT(1-t)_terminal
```
Where:
- g = terminal growth rate
- ROC = terminal return on capital (user override or WACC)
- This is the standard `g/ROC` fundamental reinvestment rate

**Amazon terminal:** `Reinvestment = (0.03 / 0.10) * 59,483 = 17,845`
(ROC overridden to 10%, terminal growth = 3%)

**Nvidia terminal:** `Reinvestment = (0.047 / 0.20) * EBIT(1-t)_terminal`
(ROC overridden to 20%, terminal growth = 4.7%)

**Invested capital tracking:**
```
IC_0 = Book_Equity + Book_Debt - Cash + Operating_Lease_Debt + R&D_Asset
IC_t = IC_{t-1} + Reinvestment_t
```

**ROIC is derived, not input:**
```
ROIC_t = EBIT(1-t)_t / IC_{t-1}
```

### Key insight: High-growth vs. stable reinvestment are structurally different

| Phase | Method | Formula |
|-------|--------|---------|
| High growth (S2C approach) | Revenue-driven | `(Rev_t - Rev_{t-1}) / S2C` |
| Terminal (always) | Fundamentals-driven | `(g / ROC) * EBIT(1-t)` |
| High growth (traditional) | Earnings-driven | `Reinvestment_Rate * EBIT(1-t)` |

---

## 4. R&D Capitalization

### Mechanics (identical across all files)

**Inputs:**
- Amortization period (N years) -- user-specified
- Current year R&D expense
- Prior N years of R&D expense history

**Amortization periods observed:**
- Amazon: N = 2 years (retail/tech service)
- Nvidia: N = 5 years (semiconductor / light manufacturing)
- Amgen: N = 10 years (pharma / research with patenting)

**Lookup table for amortization periods (from amgen.xls):**

| Industry Category | Period |
|-------------------|--------|
| Non-technological Service | 2 years |
| Retail, Tech Service | 3 years |
| Light Manufacturing | 5 years |
| Heavy Manufacturing | 10 years |
| Research, with Patenting | 10 years |

### Exact formulas

**Unamortized portion for year -k (where k = 1, 2, ..., N):**
```
Unamortized_fraction(-k) = (N - k) / N    if k < N
                         = 0               if k >= N
```

Example (Nvidia, N=5):
- Year -1: (5-1)/5 = 0.80
- Year -2: (5-2)/5 = 0.60
- Year -3: (5-3)/5 = 0.40
- Year -4: (5-4)/5 = 0.20
- Year -5: (5-5)/5 = 0.00

**Unamortized R&D value for each year:**
```
Unamortized_value(-k) = R&D_expense(-k) * Unamortized_fraction(-k)
```

**Current year R&D is always 100% unamortized (fraction = 1.0).**

**Research Asset (total unamortized R&D):**
```
Research_Asset = Current_R&D + SUM(R&D(-k) * (N-k)/N) for k=1..N
```

| Company | Research Asset |
|---------|---------------|
| Amazon  | $30,662.5M    |
| Nvidia  | $25,900.4M    |
| Amgen   | $10,112.8M    |

**Amortization this year (per vintage):**
```
Amortization(-k) = R&D_expense(-k) / N     for k = 1..N
```

Straight-line: each year's R&D is amortized equally over N years.

**Total amortization this year:**
```
Total_Amortization = SUM(R&D(-k) / N) for k=1..N
```

| Company | Total Amortization |
|---------|--------------------|
| Amazon  | $14,312.5M         |
| Nvidia  | $5,607.0M          |
| Amgen   | $1,149.9M          |

### Adjustments to financials

**Operating Income adjustment:**
```
Adjustment_to_EBIT = Current_R&D - Total_Amortization
Adjusted_EBIT = Reported_EBIT + Adjustment_to_EBIT
```

Intuition: We add back the current R&D expense (since we are now treating it as capex, not opex) and subtract the amortization of the research asset.

| Company | Current R&D | Amortization | Adjustment | Direction |
|---------|-------------|-------------|------------|-----------|
| Amazon  | $22,620M    | $14,312.5M  | +$8,307.5M | EBIT increases |
| Nvidia  | $11,665M    | $5,607.0M   | +$6,058.0M | EBIT increases |
| Amgen   | $3,366M     | $1,149.9M   | +$2,216.1M | EBIT increases |

**Invested Capital adjustment:**
```
Adjusted_IC = Book_Equity + Book_Debt - Cash + Research_Asset
```

The Research Asset is added to invested capital because it represents capitalized spending that is generating returns.

**Tax effect:**
```
Tax_Effect = Adjustment_to_EBIT * Marginal_Tax_Rate
```

This represents the tax benefit of expensing R&D vs. capitalizing it.

### How it feeds into the valuation

In the "Valuation output" sheet, when R&D capitalization is enabled:

1. **EBIT base year:** `Reported EBIT + R&D Adjustment` (from R&D converter D39)
2. **Invested Capital base year:** `BV_equity + BV_debt - Cash + Research_Asset` (from R&D converter D35)
3. **The rest of the projection** uses these adjusted values as starting points; future R&D is implicitly included in the reinvestment calculations.

Exact formula from Amazon Valuation output row 5 (base year EBIT):
```
IF capitalize_R&D = "Yes":
    IF capitalize_leases = "Yes":
        EBIT = Reported_EBIT + Lease_Adjustment + R&D_Adjustment
    ELSE:
        EBIT = Reported_EBIT + R&D_Adjustment
```

Exact formula from Amazon Valuation output row 39 (base year invested capital):
```
IF capitalize_R&D = "Yes":
    IF capitalize_leases = "Yes":
        IC = BV_equity + BV_debt - Cash + Lease_Debt + Research_Asset
    ELSE:
        IC = BV_equity + BV_debt - Cash + Research_Asset
```

---

## 5. Additional Patterns Discovered

### Operating margin convergence (new-style only)

Amazon and Nvidia use a linear convergence for operating margins, similar to WACC/tax:

```
IF year > convergence_year:
    margin = target_margin
ELSE:
    margin = target_margin - ((target_margin - current_margin) / convergence_year) * (convergence_year - year)
```

Amazon: Current margin 7.7% converging to 12.5% over 5 years.
Nvidia: Current margin 72.2% converging to 60% over 5 years (declining margins).

### Failure probability

```
Value_of_operating_assets = Value_as_going_concern * (1 - P_failure) + Distress_proceeds * P_failure
Distress_proceeds = Book_value_of_capital * liquidation_pct   (if tied to book)
                  = Fair_value * liquidation_pct               (if tied to value)
```

### Nvidia's multi-segment structure

Nvidia uniquely splits the business into 3 segments (Rest, AI Chips, Auto Chips), each with:
- Independent revenue projections (total market * market share)
- Independent operating margins
- Shared cost of capital and tax rate
- Independent reinvestment using the same sales-to-capital ratio
- Terminal values computed separately and summed

---

## 6. Summary: Implementation Rules for the Engine

### WACC transition
```python
def wacc_schedule(initial_wacc, terminal_wacc, n_high_growth, n_total=10):
    """Always 10-year projection. Constant years 1-5, linear ramp years 6-10."""
    schedule = []
    for t in range(1, n_total + 1):
        if t <= 5:
            schedule.append(initial_wacc)
        else:
            step = (initial_wacc - terminal_wacc) / 5
            schedule.append(initial_wacc - step * (t - 5))
    return schedule

# Terminal WACC default: Rf + 4.5% (+ country_risk_premium if emerging market)
```

### Tax rate transition
```python
def tax_schedule(effective_rate, marginal_rate, override_to_effective=False):
    """Same structure as WACC: constant years 1-5, linear ramp years 6-10."""
    terminal = effective_rate if override_to_effective else marginal_rate
    schedule = []
    for t in range(1, 11):
        if t <= 5:
            schedule.append(effective_rate)
        else:
            step = (terminal - effective_rate) / 5
            schedule.append(effective_rate + step * (t - 5))
    return schedule
```

### Reinvestment (sales-to-capital approach)
```python
def reinvestment_s2c(revenue_prev, revenue_curr, sales_to_capital):
    return (revenue_curr - revenue_prev) / sales_to_capital

def reinvestment_terminal(growth_rate, roc, ebit_after_tax):
    reinvestment_rate = growth_rate / roc
    return reinvestment_rate * ebit_after_tax
```

### R&D capitalization
```python
def capitalize_rd(current_rd, past_rd_list, amortization_years):
    """
    past_rd_list: [year_-1, year_-2, ..., year_-N]
    Returns: (research_asset, total_amortization, ebit_adjustment)
    """
    research_asset = current_rd  # current year is 100% unamortized
    total_amortization = 0

    for k, rd_expense in enumerate(past_rd_list, start=1):
        unamortized_frac = max(0, (amortization_years - k) / amortization_years)
        research_asset += rd_expense * unamortized_frac
        amort_this_year = rd_expense / amortization_years
        total_amortization += amort_this_year

    ebit_adjustment = current_rd - total_amortization
    return research_asset, total_amortization, ebit_adjustment
```
