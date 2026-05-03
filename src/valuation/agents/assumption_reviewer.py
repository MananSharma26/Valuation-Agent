"""Generate structured assumption review for LLM to interpret.

This is NOT an LLM — it's deterministic Python that highlights
potential issues in assumptions. The LLM reads this output and
decides what to propose to the user.
"""

from __future__ import annotations

from valuation.context import ValuationContext


def review_assumptions(ctx: ValuationContext) -> list[dict]:
    """Review all assumptions against benchmarks and context.

    Returns a list of review items, each with:
        field: str — which assumption
        value: float — current value
        benchmark: float | None — industry/market benchmark
        flag: str — "ok" | "high" | "low" | "mismatch" | "missing"
        comment: str — human-readable observation
        severity: str — "info" | "warning" | "critical"
    """
    reviews = []
    a = ctx.assumptions
    bm = ctx.benchmarks
    profile = ctx.financials.key_stats.get("company_profile") or {}

    # 1. WACC vs industry
    if a.wacc and bm.industry_wacc:
        diff = a.wacc - bm.industry_wacc
        if abs(diff) > 0.02:
            reviews.append({
                "field": "wacc",
                "value": a.wacc,
                "benchmark": bm.industry_wacc,
                "flag": "high" if diff > 0 else "low",
                "comment": (
                    f"WACC ({a.wacc:.2%}) is {'above' if diff > 0 else 'below'} "
                    f"industry average ({bm.industry_wacc:.2%}) by {abs(diff):.2%}"
                ),
                "severity": "warning",
            })
        else:
            reviews.append({
                "field": "wacc",
                "value": a.wacc,
                "benchmark": bm.industry_wacc,
                "flag": "ok",
                "comment": (
                    f"WACC ({a.wacc:.2%}) is aligned with industry ({bm.industry_wacc:.2%})"
                ),
                "severity": "info",
            })

    # 2. Growth vs company fundamentals and profile
    if a.growth_rates:
        high_g = a.growth_rates[0]
        yf_rev_growth = profile.get("revenue_growth")
        yf_earn_growth = profile.get("earnings_growth")

        if yf_rev_growth is not None and abs(high_g - yf_rev_growth) > 0.05:
            reviews.append({
                "field": "growth_rate",
                "value": high_g,
                "benchmark": yf_rev_growth,
                "flag": "mismatch",
                "comment": (
                    f"Our growth ({high_g:.2%}) differs from Yahoo Finance revenue growth "
                    f"({yf_rev_growth:.1%}) by {abs(high_g - yf_rev_growth):.2%}"
                ),
                "severity": "warning",
            })

        if yf_earn_growth is not None and abs(high_g - yf_earn_growth) > 0.10:
            reviews.append({
                "field": "growth_rate_vs_earnings",
                "value": high_g,
                "benchmark": yf_earn_growth,
                "flag": "mismatch",
                "comment": (
                    f"Our growth ({high_g:.2%}) differs from Yahoo Finance earnings growth "
                    f"({yf_earn_growth:.1%}) by {abs(high_g - yf_earn_growth):.2%}"
                ),
                "severity": "info",
            })

        industry_g = (
            bm.industry_growth.get("expected_growth_5y")
            if bm.industry_growth
            else None
        )
        if industry_g and high_g > industry_g * 2:
            reviews.append({
                "field": "growth_rate",
                "value": high_g,
                "benchmark": industry_g,
                "flag": "high",
                "comment": (
                    f"Our growth ({high_g:.2%}) is >2x industry average "
                    f"({industry_g:.1%}) — needs strong justification"
                ),
                "severity": "warning",
            })

    # 3. Terminal growth vs risk-free rate
    if a.terminal_growth is not None and a.risk_free_rate is not None:
        if a.terminal_growth > a.risk_free_rate:
            reviews.append({
                "field": "terminal_growth",
                "value": a.terminal_growth,
                "benchmark": a.risk_free_rate,
                "flag": "high",
                "comment": (
                    f"Terminal growth ({a.terminal_growth:.2%}) exceeds risk-free rate "
                    f"({a.risk_free_rate:.2%}) — Damodaran says cap at Rf"
                ),
                "severity": "critical",
            })

    # 4. Beta vs company beta from yfinance
    yf_beta = ctx.financials.key_stats.get("beta")
    if a.beta and yf_beta and abs(a.beta - yf_beta) > 0.3:
        reviews.append({
            "field": "beta",
            "value": a.beta,
            "benchmark": yf_beta,
            "flag": "mismatch",
            "comment": (
                f"Our beta ({a.beta:.2f}, bottom-up) differs from yfinance regression beta "
                f"({yf_beta:.2f}) by {abs(a.beta - yf_beta):.2f}"
            ),
            "severity": "info",
        })

    # 5. Classification check
    cls = ctx.company.classification
    if cls == "mature" and profile.get("revenue_growth") and profile["revenue_growth"] > 0.20:
        reviews.append({
            "field": "classification",
            "value": cls,
            "benchmark": None,
            "flag": "mismatch",
            "comment": (
                f"Classified as 'mature' but Yahoo shows {profile['revenue_growth']:.0%} "
                f"revenue growth — consider 'growth'"
            ),
            "severity": "warning",
        })
    elif cls == "growth" and profile.get("revenue_growth") and profile["revenue_growth"] < 0.05:
        reviews.append({
            "field": "classification",
            "value": cls,
            "benchmark": None,
            "flag": "mismatch",
            "comment": (
                f"Classified as 'growth' but Yahoo shows only {profile['revenue_growth']:.0%} "
                f"revenue growth — consider 'mature'"
            ),
            "severity": "warning",
        })

    # 6. Margin sustainability
    if ctx.financials.income_statement is not None and len(ctx.financials.income_statement) > 0:
        latest = ctx.financials.income_statement.iloc[0]
        rev = float(latest.get("Total Revenue", 0) or 0)
        ebit = float(latest.get("Operating Income", 0) or 0)
        margin = ebit / rev if rev > 0 else 0
        industry_margin = bm.industry_margins.get("operating_margin") if bm.industry_margins else None
        if industry_margin and margin > industry_margin * 2 and margin > 0.15:
            reviews.append({
                "field": "operating_margin",
                "value": margin,
                "benchmark": industry_margin,
                "flag": "high",
                "comment": (
                    f"Operating margin ({margin:.1%}) is >2x industry ({industry_margin:.1%}) "
                    f"— may not be sustainable"
                ),
                "severity": "info",
            })

    # 7. WACC vs terminal growth — the hard floor
    if a.wacc is not None and a.terminal_growth is not None:
        if a.wacc <= a.terminal_growth:
            reviews.append({
                "field": "wacc_vs_terminal",
                "value": a.wacc,
                "benchmark": a.terminal_growth,
                "flag": "mismatch",
                "comment": (
                    f"WACC ({a.wacc:.2%}) is not greater than terminal growth "
                    f"({a.terminal_growth:.2%}) — DCF math breaks down (infinite/negative value)"
                ),
                "severity": "critical",
            })

    return reviews


def format_review_for_report(reviews: list[dict]) -> str:
    """Format assumption reviews as markdown for the report."""
    if not reviews:
        return ""

    warnings = [r for r in reviews if r["severity"] in ("warning", "critical")]
    if not warnings:
        return ""

    lines = ["### Assumption Flags", ""]
    for r in warnings:
        icon = "⚠️" if r["severity"] == "warning" else "🔴"
        lines.append(f"- {icon} **{r['field']}**: {r['comment']}")

    return "\n".join(lines)
