"""R&D capitalization and operating lease adjustments per Damodaran methodology."""

from __future__ import annotations


def capitalize_rd(
    current_rd: float,
    past_rd: list[float],
    amortization_years: int,
) -> dict:
    """Capitalize R&D expenses into a research asset.

    Args:
        current_rd: Current year R&D expense
        past_rd: List of past R&D expenses [year_-1, year_-2, ..., year_-N]
        amortization_years: Straight-line amortization period

    Returns dict with:
        research_asset: Total unamortized R&D (added to invested capital)
        total_amortization: This year's amortization charge
        ebit_adjustment: current_rd - total_amortization (added to EBIT)
    """
    research_asset = current_rd  # current year 100% unamortized
    total_amortization = 0.0

    for k, rd_expense in enumerate(past_rd, start=1):
        if k < amortization_years:
            unamortized_frac = (amortization_years - k) / amortization_years
            research_asset += rd_expense * unamortized_frac
        amort = rd_expense / amortization_years
        total_amortization += amort

    ebit_adjustment = current_rd - total_amortization
    return {
        "research_asset": research_asset,
        "total_amortization": total_amortization,
        "ebit_adjustment": ebit_adjustment,
    }


# Amortization period lookup
RD_AMORTIZATION_PERIODS = {
    "non_tech_service": 2,
    "retail_tech_service": 3,
    "software": 3,
    "light_manufacturing": 5,
    "semiconductor": 5,
    "heavy_manufacturing": 10,
    "pharma": 10,
    "research_patenting": 10,
}


def get_amortization_period(industry: str) -> int:
    """Look up amortization period for an industry. Default 5 years."""
    industry_lower = industry.lower() if industry else ""
    if "pharma" in industry_lower or "biotech" in industry_lower or "drug" in industry_lower:
        return 10
    if "semiconductor" in industry_lower or "chip" in industry_lower:
        return 5
    if "software" in industry_lower:
        return 3
    if "retail" in industry_lower:
        return 3
    return 5  # default


def estimate_lease_debt(
    lease_expense: float,
    cost_of_debt: float,
    avg_lease_life: float = 8.0,
) -> dict:
    """Estimate the debt value of operating leases.

    Damodaran approximation: PV of lease payments ≈ lease_expense × annuity factor
    Annuity factor = (1 - (1+r)^-n) / r

    Args:
        lease_expense: Annual operating lease/rent expense
        cost_of_debt: Pre-tax cost of debt (for discounting)
        avg_lease_life: Average remaining lease life (default 8 years)

    Returns dict with:
        lease_debt: PV of lease commitments (treat as debt)
        depreciation: lease_debt / avg_lease_life (lease depreciation)
        ebit_adjustment: lease_expense - depreciation (added to EBIT)
    """
    if lease_expense <= 0 or cost_of_debt <= 0:
        return {"lease_debt": 0, "depreciation": 0, "ebit_adjustment": 0}

    # Annuity factor
    r = cost_of_debt
    n = avg_lease_life
    annuity_factor = (1 - (1 + r) ** (-n)) / r

    lease_debt = lease_expense * annuity_factor
    depreciation = lease_debt / n
    ebit_adjustment = lease_expense - depreciation

    return {
        "lease_debt": lease_debt,
        "depreciation": depreciation,
        "ebit_adjustment": ebit_adjustment,
    }
