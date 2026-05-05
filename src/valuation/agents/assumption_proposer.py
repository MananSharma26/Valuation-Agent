"""Core judgment layer: reads ALL context, produces pointed assumption proposals.

This module examines the ValuationContext — including fundamental estimates,
Yahoo Finance data, industry benchmarks, analyst consensus, macro context,
and peer comparisons — and generates specific, actionable proposals for each
key assumption. Each proposal includes reasoning, confidence, and a
pre-formatted question for the user.

All math is performed by deterministic functions elsewhere. This module only
compares, selects, and formats.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from valuation.agents.risk_assessor import compute_cost_of_equity, compute_wacc
from valuation.context import ValuationContext


@dataclass
class Proposal:
    """A single assumption proposal with reasoning and a user-facing question."""

    parameter: str
    current_value: Any
    proposed_value: Any
    reasoning: str
    confidence: float  # 0.0 to 1.0
    references: list[str] = field(default_factory=list)
    question: str = ""


def propose_assumptions(ctx: ValuationContext) -> list[Proposal]:
    """Generate proposals for key assumptions by comparing all available data.

    Examines: fundamental estimates, Yahoo Finance profile, industry benchmarks,
    analyst consensus (for comparison), macro context, and peer data.

    Returns a list of Proposal objects for: growth_rate, wacc, terminal_growth,
    classification, and operating_margin.
    """
    proposals: list[Proposal] = []

    p = _propose_growth(ctx)
    if p:
        proposals.append(p)

    p = _propose_wacc(ctx)
    if p:
        proposals.append(p)

    p = _propose_terminal_growth(ctx)
    if p:
        proposals.append(p)

    p = _propose_classification(ctx)
    if p:
        proposals.append(p)

    p = _propose_margin(ctx)
    if p:
        proposals.append(p)

    return proposals


def _propose_growth(ctx: ValuationContext) -> Proposal | None:
    """Compare formula-based growth vs Yahoo YoY vs industry vs analyst consensus."""
    a = ctx.assumptions
    if not a.growth_rates:
        return None

    current_high_growth = a.growth_rates[0]
    profile = ctx.financials.key_stats.get("company_profile") or {}
    bm = ctx.benchmarks

    references: list[str] = []
    comparisons: list[str] = []

    # Yahoo Finance YoY growth
    yahoo_rev_growth = profile.get("revenue_growth")
    yahoo_earn_growth = profile.get("earnings_growth")
    if yahoo_rev_growth is not None:
        comparisons.append(f"Yahoo revenue growth (YoY): {yahoo_rev_growth:.1%}")
        references.append("Yahoo Finance")
    if yahoo_earn_growth is not None:
        comparisons.append(f"Yahoo earnings growth (YoY): {yahoo_earn_growth:.1%}")

    # Industry benchmark
    ind_growth = None
    if bm.industry_growth:
        ind_growth = bm.industry_growth.get("expected_growth_5y")
        if ind_growth:
            comparisons.append(f"Industry expected 5Y growth: {ind_growth:.1%}")
            references.append("Damodaran industry data")

    # Analyst consensus (comparison only)
    analyst_data = ctx.financials.key_stats.get("analyst_data") or {}
    ee = analyst_data.get("earnings_estimate") or {}
    consensus_growth = (ee.get("growth") or {}).get("+1y")
    if consensus_growth is not None:
        comparisons.append(f"Analyst consensus growth (+1Y): {consensus_growth:.1%}")
        references.append("Yahoo Finance consensus")

    if not comparisons:
        return None

    # Determine if current growth is significantly different from references
    ref_values = []
    if yahoo_rev_growth is not None:
        ref_values.append(yahoo_rev_growth)
    if ind_growth is not None:
        ref_values.append(ind_growth)

    proposed = current_high_growth
    reasoning_parts = [f"Current high-growth rate: {current_high_growth:.1%}"]
    reasoning_parts.extend(comparisons)

    confidence = 0.7
    if ref_values:
        avg_ref = sum(ref_values) / len(ref_values)
        diff = abs(current_high_growth - avg_ref)
        if diff > 0.05:
            reasoning_parts.append(
                f"Current estimate differs from reference average ({avg_ref:.1%}) by {diff:.1%}"
            )
            confidence = 0.5
        else:
            reasoning_parts.append("Current estimate is consistent with references")
            confidence = 0.8

    reasoning = ". ".join(reasoning_parts)

    question = (
        f"Growth: fundamental estimate gives {current_high_growth:.1%}. "
        + (f"Yahoo revenue growth is {yahoo_rev_growth:.1%}. " if yahoo_rev_growth else "")
        + (f"Industry benchmark is {ind_growth:.1%}. " if ind_growth else "")
        + f"Accept {current_high_growth:.1%}? [yes / adjust to ___]"
    )

    return Proposal(
        parameter="growth_rate",
        current_value=current_high_growth,
        proposed_value=proposed,
        reasoning=reasoning,
        confidence=confidence,
        references=references,
        question=question,
    )


def _propose_wacc(ctx: ValuationContext) -> Proposal | None:
    """Compare computed WACC to industry average and check Rf against live Treasury."""
    a = ctx.assumptions
    bm = ctx.benchmarks

    if a.wacc is None:
        return None

    references: list[str] = []
    reasoning_parts = [f"Computed WACC: {a.wacc:.2%}"]

    # Industry comparison
    if bm.industry_wacc:
        diff = a.wacc - bm.industry_wacc
        reasoning_parts.append(
            f"Industry WACC: {bm.industry_wacc:.2%} (diff: {diff:+.2%})"
        )
        references.append("Damodaran WACC")

    # Check Rf against macro context (live Treasury yields)
    macro = ctx.financials.key_stats.get("macro_context") or {}
    treasury_10y = macro.get("us_10yr_yield")
    if treasury_10y is not None and a.risk_free_rate is not None:
        rf_diff = abs(a.risk_free_rate - treasury_10y)
        if rf_diff > 0.005:
            reasoning_parts.append(
                f"Risk-free rate ({a.risk_free_rate:.2%}) differs from live 10Y Treasury "
                f"({treasury_10y:.2%}) by {rf_diff:.2%}"
            )
            references.append("Live Treasury yield")

    confidence = 0.7
    if bm.industry_wacc and abs(a.wacc - bm.industry_wacc) > 0.02:
        confidence = 0.5

    industry_str = f" Industry average is {bm.industry_wacc:.2%}." if bm.industry_wacc else ""
    question = (
        f"WACC is {a.wacc:.2%}.{industry_str} "
        f"Keep {a.wacc:.2%} or adjust? [keep / adjust to ___]"
    )

    # Check if company beta differs significantly from industry beta
    yf_beta = ctx.financials.key_stats.get("beta")
    rf = a.risk_free_rate or 0.0
    erp = a.erp or 0.0446
    lam = 1.0
    crp = a.country_risk_premium or 0.0
    if yf_beta and a.beta and abs(a.beta - yf_beta) / a.beta > 0.30:
        # Compute alt Ke and alt WACC using the company's own regression beta
        alt_ke = compute_cost_of_equity(rf, yf_beta, erp, crp, lam)
        # Infer debt/equity weights from existing Ke vs WACC relationship
        if a.cost_of_equity and a.cost_of_equity > 0 and a.wacc != a.cost_of_equity:
            dbt_w = max(0.0, 1.0 - (a.wacc / a.cost_of_equity))
        else:
            dbt_w = 0.0
        eq_w = 1.0 - dbt_w
        cod = a.cost_of_debt if a.cost_of_debt else (rf + 0.02)
        tax = a.tax_rate if a.tax_rate else 0.25
        alt_wacc = compute_wacc(alt_ke, cod, tax, eq_w, dbt_w)

        reasoning_parts.append(
            f"⚠ Company regression beta ({yf_beta:.2f}) is very different from "
            f"our industry beta ({a.beta:.2f}). Using company beta would give WACC ~{alt_wacc:.1%} "
            f"vs current {a.wacc:.1%}"
        )
        references.append("Yahoo Finance regression beta")
        confidence = 0.3

        # Update question to be more pointed
        question = (
            f"WACC is {a.wacc:.2%} (industry beta {a.beta:.2f}). "
            f"But company's own beta is {yf_beta:.2f} — "
            f"using it would give WACC ~{alt_wacc:.1%}.{industry_str} "
            f"Use industry beta or company beta? [industry {a.wacc:.2%} / company ~{alt_wacc:.1%} / blend ___]"
        )

    reasoning = ". ".join(reasoning_parts)

    return Proposal(
        parameter="wacc",
        current_value=a.wacc,
        proposed_value=a.wacc,
        reasoning=reasoning,
        confidence=confidence,
        references=references,
        question=question,
    )


def _propose_terminal_growth(ctx: ValuationContext) -> Proposal | None:
    """Check terminal growth vs GDP forecast and risk-free rate."""
    a = ctx.assumptions
    if a.terminal_growth is None:
        return None

    references: list[str] = []
    reasoning_parts = [f"Terminal growth: {a.terminal_growth:.2%}"]

    # GDP forecast from macro context
    macro = ctx.financials.key_stats.get("macro_context") or {}
    gdp_growth = macro.get("gdp_growth")
    if gdp_growth is not None:
        reasoning_parts.append(f"GDP growth forecast: {gdp_growth:.2%}")
        references.append("World Bank GDP forecast")

    # Terminal growth should not exceed risk-free rate
    if a.risk_free_rate is not None:
        if a.terminal_growth >= a.risk_free_rate:
            reasoning_parts.append(
                f"WARNING: Terminal growth ({a.terminal_growth:.2%}) >= risk-free rate "
                f"({a.risk_free_rate:.2%}). Should cap at Rf - 1%."
            )
        references.append("Damodaran methodology")

    confidence = 0.8
    if a.risk_free_rate and a.terminal_growth >= a.risk_free_rate:
        confidence = 0.3

    reasoning = ". ".join(reasoning_parts)

    gdp_str = f" GDP forecast is {gdp_growth:.2%}." if gdp_growth else ""
    question = (
        f"Terminal growth: {a.terminal_growth:.2%}.{gdp_str} "
        f"Acceptable? [yes / adjust to ___]"
    )

    return Proposal(
        parameter="terminal_growth",
        current_value=a.terminal_growth,
        proposed_value=a.terminal_growth,
        reasoning=reasoning,
        confidence=confidence,
        references=references,
        question=question,
    )


def _propose_classification(ctx: ValuationContext) -> Proposal | None:
    """Challenge classification if metrics don't match the label."""
    classification = ctx.company.classification
    if not classification:
        return None

    profile = ctx.financials.key_stats.get("company_profile") or {}
    references: list[str] = []
    issues: list[str] = []

    rev_growth = profile.get("revenue_growth")
    earn_growth = profile.get("earnings_growth")
    profit_margin = profile.get("profit_margins")

    if classification == "mature":
        if rev_growth is not None and rev_growth > 0.20:
            issues.append(
                f"Classified as 'mature' but revenue growth is {rev_growth:.1%} "
                f"(>20% suggests 'growth')"
            )
        if earn_growth is not None and earn_growth > 0.25:
            issues.append(
                f"Earnings growth is {earn_growth:.1%} — high for a mature company"
            )
    elif classification == "growth":
        if rev_growth is not None and rev_growth < 0.05:
            issues.append(
                f"Classified as 'growth' but revenue growth is only {rev_growth:.1%} "
                f"(<5% suggests 'mature')"
            )
        if profit_margin is not None and profit_margin > 0.25:
            issues.append(
                f"Profit margin is {profit_margin:.1%} — high margins with low growth "
                f"may indicate maturity"
            )

    if not issues:
        return None

    references.append("Yahoo Finance metrics")
    reasoning = f"Classification: {classification}. " + " ".join(issues)
    confidence = 0.4  # low confidence means user should review

    question = (
        f"Classification is '{classification}' but: {issues[0]}. "
        f"Keep '{classification}'? [yes / change to ___]"
    )

    return Proposal(
        parameter="classification",
        current_value=classification,
        proposed_value=classification,
        reasoning=reasoning,
        confidence=confidence,
        references=references,
        question=question,
    )


def _propose_margin(ctx: ValuationContext) -> Proposal | None:
    """Check operating margin vs peers and industry."""
    bm = ctx.benchmarks
    inc = ctx.financials.income_statement
    if inc is None or inc.empty:
        return None

    latest = inc.iloc[0]
    revenue = float(latest.get("Total Revenue", 0) or 0)
    ebit = float(latest.get("Operating Income", 0) or 0)
    if revenue <= 0:
        return None

    current_margin = ebit / revenue
    references: list[str] = []
    reasoning_parts = [f"Current operating margin: {current_margin:.1%}"]

    # Industry benchmark
    ind_margin = bm.industry_margins.get("operating_margin") if bm.industry_margins else None
    if ind_margin:
        diff = current_margin - ind_margin
        reasoning_parts.append(
            f"Industry operating margin: {ind_margin:.1%} (diff: {diff:+.1%})"
        )
        references.append("Damodaran industry margins")

    # Peer comparison
    peer_data = ctx.financials.key_stats.get("peer_comparison") or {}
    peer_median_margin = (peer_data.get("peer_median") or {}).get("profit_margin")
    if peer_median_margin is not None:
        reasoning_parts.append(f"Peer median profit margin: {peer_median_margin:.1%}")
        references.append("Peer analysis (WRDS + Yahoo)")

    if not references:
        return None

    confidence = 0.7
    if ind_margin and abs(current_margin - ind_margin) > 0.10:
        confidence = 0.5

    reasoning = ". ".join(reasoning_parts)

    ind_str = f" Industry average is {ind_margin:.1%}." if ind_margin else ""
    question = (
        f"Operating margin is {current_margin:.1%}.{ind_str} "
        f"This is used for margin convergence in DCF. Reasonable? [yes / comment]"
    )

    return Proposal(
        parameter="operating_margin",
        current_value=current_margin,
        proposed_value=current_margin,
        reasoning=reasoning,
        confidence=confidence,
        references=references,
        question=question,
    )


def format_proposals_for_report(proposals: list[Proposal]) -> str:
    """Render proposals as markdown for inclusion in the valuation report."""
    if not proposals:
        return ""

    lines = ["### Assumption Proposals", ""]

    for p in proposals:
        # confidence can be float (0-1) or string ("high"/"medium"/"low")
        if isinstance(p.confidence, str):
            conf_label = p.confidence.upper()
        elif isinstance(p.confidence, (int, float)):
            conf_label = (
                "HIGH" if p.confidence >= 0.7
                else "MEDIUM" if p.confidence >= 0.4
                else "LOW"
            )
        else:
            conf_label = "MEDIUM"
        lines.append(f"**{p.parameter}** (confidence: {conf_label})")
        lines.append(f"- Current: {_fmt_val(p.current_value)}")
        if p.proposed_value != p.current_value:
            lines.append(f"- Proposed: {_fmt_val(p.proposed_value)}")
        lines.append(f"- {p.reasoning}")
        if p.references:
            lines.append(f"- Sources: {', '.join(p.references)}")
        lines.append(f"- **Q:** {p.question}")
        lines.append("")

    return "\n".join(lines)


def _fmt_val(val: Any) -> str:
    """Format a value for display."""
    if val is None:
        return "N/A"
    if isinstance(val, float):
        if abs(val) < 1:
            return f"{val:.2%}"
        return f"{val:,.2f}"
    return str(val)
