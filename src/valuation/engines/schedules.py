"""Generate year-by-year schedules for WACC, tax, growth, and reinvestment.

Implements Damodaran's transition patterns:
- Years 1-5: constant at high-growth value
- Years 6-10: linear ramp to terminal value
"""

from __future__ import annotations


def wacc_schedule(
    initial_wacc: float,
    terminal_wacc: float,
    n_years: int = 10,
    n_constant: int = 5,
) -> list[float]:
    """WACC schedule: constant for n_constant years, then linear ramp to terminal.

    Default terminal WACC = Rf + 4.5% (+ CRP for emerging markets).
    """
    schedule = []
    n_ramp = n_years - n_constant
    step = (initial_wacc - terminal_wacc) / n_ramp if n_ramp > 0 else 0
    for t in range(1, n_years + 1):
        if t <= n_constant:
            schedule.append(initial_wacc)
        else:
            schedule.append(initial_wacc - step * (t - n_constant))
    return schedule


def tax_schedule(
    effective_rate: float,
    marginal_rate: float,
    n_years: int = 10,
    n_constant: int = 5,
) -> list[float]:
    """Tax rate schedule: effective for n_constant years, ramp to marginal."""
    schedule = []
    n_ramp = n_years - n_constant
    step = (marginal_rate - effective_rate) / n_ramp if n_ramp > 0 else 0
    for t in range(1, n_years + 1):
        if t <= n_constant:
            schedule.append(effective_rate)
        else:
            schedule.append(effective_rate + step * (t - n_constant))
    return schedule


def margin_convergence_schedule(
    current_margin: float,
    target_margin: float,
    convergence_year: int = 5,
    n_years: int = 10,
) -> list[float]:
    """Operating margin convergence: linear from current to target over convergence_year, then constant."""
    schedule = []
    for t in range(1, n_years + 1):
        if t >= convergence_year:
            schedule.append(target_margin)
        else:
            progress = t / convergence_year
            schedule.append(current_margin + (target_margin - current_margin) * progress)
    return schedule


def reinvestment_s2c(
    revenue_prev: float,
    revenue_curr: float,
    sales_to_capital: float,
) -> float:
    """Sales-to-capital reinvestment: Reinvestment = (Rev_t - Rev_{t-1}) / S2C."""
    if sales_to_capital <= 0:
        return 0.0
    return (revenue_curr - revenue_prev) / sales_to_capital


def reinvestment_terminal(
    growth_rate: float,
    roc: float,
    ebit_after_tax: float,
) -> float:
    """Terminal reinvestment = (g / ROC) * EBIT(1-t)."""
    if roc <= 0:
        return 0.0
    return (growth_rate / roc) * ebit_after_tax


def terminal_wacc_default(
    risk_free_rate: float,
    country_risk_premium: float = 0.0,
) -> float:
    """Default terminal WACC = Rf + 4.5% + CRP (Damodaran convention)."""
    return risk_free_rate + 0.045 + country_risk_premium
