"""Model router: selects the appropriate valuation engine based on company type.

Separates classification (what IS the company) from model selection (HOW to value it).
"""

from __future__ import annotations
from dataclasses import dataclass, field
from valuation.context import ValuationContext


@dataclass
class ModelSelection:
    primary_model: str  # "fcff_traditional" | "fcff_revenue_s2c" | "ddm" | "gordon_growth"
    secondary_models: list[str] = field(default_factory=list)
    use_normalization: bool = False
    use_failure_probability: bool = False
    reinvestment_lag: int = 0
    reasoning: str = ""


def select_model(ctx: ValuationContext) -> ModelSelection:
    """Select valuation engine based on classification and financial characteristics."""
    classification = ctx.company.classification or "mature"
    stats = ctx.financials.key_stats

    div_yield = 0
    if stats.get("dividend_per_share") and stats.get("price"):
        div_yield = stats["dividend_per_share"] / stats["price"]

    growth = ctx.assumptions.growth_rates[0] if ctx.assumptions.growth_rates else 0

    if classification == "financial":
        return ModelSelection(
            primary_model="ddm",
            secondary_models=["excess_returns"],
            reasoning="Financial firm — debt is raw material, use DDM + excess returns",
        )

    if classification == "mature":
        if div_yield > 0.03 and growth < 0.05:
            return ModelSelection(
                primary_model="gordon_growth",
                secondary_models=["fcff_traditional"],
                reasoning=f"Stable mature with {div_yield:.1%} dividend yield and {growth:.1%} growth — Gordon Growth primary",
            )
        return ModelSelection(
            primary_model="fcff_traditional",
            secondary_models=["gordon_growth"] if div_yield > 0.02 else [],
            reasoning="Mature company — traditional earnings-driven FCFF",
        )

    if classification == "growth" or classification == "young":
        lag = 0
        # Capital-intensive growth companies may have reinvestment lag
        s2c = ctx.financials.key_stats.get("sales_to_capital", 2.0)
        if isinstance(s2c, (int, float)) and s2c < 1.0:
            lag = 2  # Heavy capex companies invest ahead
        return ModelSelection(
            primary_model="fcff_revenue_s2c",
            reinvestment_lag=lag,
            reasoning=f"Growth company — revenue-based FCFF v2 with S2C approach (lag={lag})",
        )

    if classification == "cyclical":
        return ModelSelection(
            primary_model="fcff_traditional",
            use_normalization=True,
            reasoning="Cyclical — traditional FCFF with normalized mid-cycle earnings",
        )

    if classification == "distressed":
        return ModelSelection(
            primary_model="fcff_traditional",
            use_failure_probability=True,
            reasoning="Distressed — traditional FCFF with failure probability adjustment",
        )

    # Default
    return ModelSelection(
        primary_model="fcff_traditional",
        reasoning="Default — traditional earnings-driven FCFF",
    )
