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

    # Get financial data
    total_debt = 0
    if ctx.financials.balance_sheet is not None and len(ctx.financials.balance_sheet) > 0:
        total_debt = float(ctx.financials.balance_sheet.iloc[0].get('Total Debt', 0) or 0)

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
    if a.beta and yf_beta:
        diff = abs(a.beta - yf_beta)
        relative_diff = diff / a.beta if a.beta > 0 else 0
        if relative_diff > 0.40:  # >40% difference is critical
            reviews.append({
                "field": "beta",
                "value": a.beta,
                "benchmark": yf_beta,
                "flag": "mismatch",
                "comment": (
                    f"CRITICAL: Our beta ({a.beta:.2f}, industry bottom-up) is {relative_diff:.0%} different "
                    f"from company's regression beta ({yf_beta:.2f}). "
                    f"This alone swings value by {relative_diff*3:.0%}+. "
                    f"Consider: is this company atypical for its industry? "
                    f"(e.g., government-backed, monopoly, zero debt, locked-in revenue)"
                ),
                "severity": "critical",
            })
        elif diff > 0.3:
            reviews.append({
                "field": "beta",
                "value": a.beta,
                "benchmark": yf_beta,
                "flag": "mismatch",
                "comment": f"Our beta ({a.beta:.2f}) differs from yfinance ({yf_beta:.2f}) by {diff:.2f}",
                "severity": "warning",
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

    # 8. Government/PSU check — these companies often trade at much lower betas
    country = ctx.financials.key_stats.get("country") or ""
    company_name = (ctx.company.name or "").lower()
    industry = (ctx.financials.key_stats.get("industry_yfinance") or "").lower()

    is_psu_indicators = any([
        "limited" in company_name and country == "India",  # Most Indian PSUs end in "Limited"
        "hindustan" in company_name,
        "bharat" in company_name,
        "national" in company_name and country == "India",
        "indian" in company_name.split()[0:1],
    ])

    if is_psu_indicators and a.beta and a.beta > 1.0:
        reviews.append({
            "field": "company_type",
            "value": "possible_PSU",
            "benchmark": None,
            "flag": "mismatch",
            "comment": (
                f"Company name suggests a government/PSU entity. "
                f"Indian PSUs typically trade at beta 0.2-0.6 (government backing, monopoly). "
                f"Our beta ({a.beta:.2f}) uses industry average which may be too high. "
                f"Consider using company regression beta or a PSU-adjusted beta."
            ),
            "severity": "warning",
        })

    # 9. Zero debt anomaly — zero-debt companies may warrant lower beta
    if total_debt == 0 and a.beta and a.beta > 1.2:
        reviews.append({
            "field": "leverage_risk",
            "value": a.beta,
            "benchmark": 0,
            "flag": "high",
            "comment": (
                f"Company has ZERO debt but beta is {a.beta:.2f}. "
                f"Since beta is re-levered from industry (which has avg debt), "
                f"a zero-debt company should have lower operating risk. "
                f"The unlevered beta ({ctx.benchmarks.industry_unlevered_beta:.2f}) may be more appropriate."
                if ctx.benchmarks.industry_unlevered_beta
                else (
                    f"Company has ZERO debt but beta is {a.beta:.2f}. "
                    f"Since beta is re-levered from industry (which has avg debt), "
                    f"a zero-debt company should have lower operating risk."
                )
            ),
            "severity": "info",
        })

    # 10. Locked-in revenue / order book — check if WACC is appropriate
    transcript = ctx.financials.key_stats.get("earnings_transcript")
    if transcript and a.wacc and a.wacc > 0.12:
        text = transcript.get("transcript_text", "").lower()
        order_keywords = ["order book", "order backlog", "locked in", "visibility", "pipeline"]
        if any(kw in text for kw in order_keywords):
            reviews.append({
                "field": "revenue_visibility",
                "value": a.wacc,
                "benchmark": None,
                "flag": "high",
                "comment": (
                    f"Earnings call mentions order book/backlog/visibility. "
                    f"High revenue visibility reduces risk — current WACC ({a.wacc:.2%}) may be too high. "
                    f"Companies with locked-in revenue often warrant lower discount rates."
                ),
                "severity": "warning",
            })

    # 11. Implied ROC check — growth destroys value if ROC < WACC
    if ctx.outputs.dcf_fcff:
        yearly_roic = ctx.outputs.dcf_fcff.get("yearly_roic", [])
        if yearly_roic and a.wacc:
            avg_roic = sum(yearly_roic[:5]) / len(yearly_roic[:5]) if yearly_roic[:5] else 0
            if avg_roic > 0 and avg_roic < a.wacc:
                reviews.append({
                    "field": "value_creation",
                    "value": avg_roic,
                    "benchmark": a.wacc,
                    "flag": "mismatch",
                    "comment": (
                        f"CRITICAL: Implied ROIC ({avg_roic:.1%}) is BELOW WACC ({a.wacc:.2%}). "
                        f"This means growth DESTROYS value in the DCF. "
                        f"Either the Sales-to-Capital ratio is too low (needs more revenue per unit of capital), "
                        f"or WACC is too high, or margins are too low. "
                        f"The market clearly disagrees — check your S2C and beta assumptions."
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
