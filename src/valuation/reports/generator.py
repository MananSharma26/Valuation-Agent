"""
generator.py — Deterministic markdown report generator.

Takes a completed ValuationContext and formats all pipeline outputs into a
structured markdown report string. Pure Python string formatting — no Jinja2,
no LLM calls.

Methodology: Damodaran (Investment Valuation, 3rd ed.)
"""

from __future__ import annotations

import json
import pathlib
from datetime import date
from typing import Any

from valuation.context import ValuationContext

# Default reports directory (project root / reports)
_REPORTS_DIR = pathlib.Path(__file__).parent.parent.parent.parent / "reports"

# Module-level currency symbol; overridden per-report inside generate_report()
_CURRENCY = "$"


def _currency_symbol(region: str | None) -> str:
    """Return the currency symbol for a given region string."""
    return {
        "India": "\u20b9",   # ₹
        "Japan": "\u00a5",   # ¥
        "China": "\u00a5",   # ¥
        "Europe": "\u20ac",  # €
        "UK": "\u00a3",      # £
    }.get(region or "", "$")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def generate_report(ctx: ValuationContext) -> str:
    """Generate a markdown valuation report from a completed ValuationContext.

    Parameters
    ----------
    ctx : ValuationContext
        Must have company info populated. All other sections are optional —
        missing data is gracefully omitted or noted as unavailable.

    Returns
    -------
    str
        A non-empty markdown string suitable for display or saving.
    """
    global _CURRENCY
    _CURRENCY = _currency_symbol(ctx.company.region)

    sections: list[str] = [
        _section_executive_summary(ctx),
        _section_company_profile(ctx),
        _section_company_context(ctx),
        _section_key_assumptions(ctx),
        _section_dcf_valuation(ctx),
        _section_relative_valuation(ctx),
        _section_cross_validation(ctx),
        _section_analyst_consensus(ctx),
        _section_sensitivity_analysis(ctx),
        _section_confidence_assessment(ctx),
        _section_data_sources(ctx),
    ]
    # Filter out empty sections (returns empty string when data is absent)
    body = "\n\n---\n\n".join(s for s in sections if s.strip())
    return body + "\n"


def save_report(ctx: ValuationContext, reports_dir: str | pathlib.Path | None = None) -> pathlib.Path:
    """Generate and save a valuation report + JSON summary to disk.

    Creates: reports/<CompanyName>/YYYY-MM-DD_<TICKER>.md
             reports/<CompanyName>/YYYY-MM-DD_<TICKER>.json

    Args:
        ctx: Completed ValuationContext
        reports_dir: Override reports directory (default: project root / reports)

    Returns:
        Path to the saved markdown report
    """
    base = pathlib.Path(reports_dir) if reports_dir else _REPORTS_DIR
    company_name = (ctx.company.name or ctx.company.ticker).replace("/", "-").replace("\\", "-")
    company_dir = base / company_name
    company_dir.mkdir(parents=True, exist_ok=True)

    today = date.today().isoformat()
    ticker = ctx.company.ticker.replace(":", "-")
    md_path = company_dir / f"{today}_{ticker}.md"
    json_path = company_dir / f"{today}_{ticker}.json"

    # Save markdown report
    report = generate_report(ctx)
    md_path.write_text(report, encoding="utf-8")

    # Save JSON summary
    summary = ctx.to_summary_dict()
    # Add full outputs for programmatic use
    summary["outputs"] = {
        "dcf_fcff": ctx.outputs.dcf_fcff,
        "dcf_fcfe": ctx.outputs.dcf_fcfe,
        "relative": ctx.outputs.relative,
        "excess_returns": ctx.outputs.excess_returns,
        "sensitivity": ctx.outputs.sensitivity,
    }
    summary["assumptions"] = {
        "risk_free_rate": ctx.assumptions.risk_free_rate,
        "erp": ctx.assumptions.erp,
        "country_risk_premium": ctx.assumptions.country_risk_premium,
        "beta": ctx.assumptions.beta,
        "cost_of_equity": ctx.assumptions.cost_of_equity,
        "cost_of_debt": ctx.assumptions.cost_of_debt,
        "wacc": ctx.assumptions.wacc,
        "growth_rates": ctx.assumptions.growth_rates,
        "terminal_growth": ctx.assumptions.terminal_growth,
        "tax_rate": ctx.assumptions.tax_rate,
    }
    summary["confidence"] = {
        "data_completeness": ctx.confidence.data_completeness,
        "model_agreement": ctx.confidence.model_agreement,
        "assumption_sensitivity": ctx.confidence.assumption_sensitivity,
        "industry_coverage": ctx.confidence.industry_coverage,
        "composite": ctx.confidence.composite,
        "flags": ctx.confidence.flags,
    }
    summary["date"] = today

    json_path.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")

    return md_path


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fmt(value: float | None, decimals: int = 2, prefix: str = "") -> str:
    """Format a float with a prefix (e.g. '$') or return 'N/A'.

    When prefix is the literal "$", the module-level _CURRENCY symbol is used
    instead so that reports for non-USD companies show the correct symbol.
    """
    if value is None:
        return "N/A"
    resolved_prefix = _CURRENCY if prefix == "$" else prefix
    return f"{resolved_prefix}{value:,.{decimals}f}"


def _fmt_pct(value: float | None, decimals: int = 1) -> str:
    """Format a float as a percentage or return 'N/A'."""
    if value is None:
        return "N/A"
    return f"{value * 100:.{decimals}f}%"


def _confidence_label(score: float | None) -> str:
    """Convert a 0-1 score to a human-readable label."""
    if score is None:
        return "N/A"
    if score >= 0.75:
        return f"HIGH ({score:.0%})"
    if score >= 0.50:
        return f"MEDIUM ({score:.0%})"
    return f"LOW ({score:.0%})"


# ---------------------------------------------------------------------------
# Section builders
# ---------------------------------------------------------------------------


def _section_executive_summary(ctx: ValuationContext) -> str:
    co = ctx.company
    name = co.name or co.ticker
    ticker = co.ticker
    classification = co.classification or "Unclassified"
    confidence = _confidence_label(ctx.confidence.composite)

    # Determine primary value range from available outputs
    values: list[float] = []
    if ctx.outputs.dcf_fcff:
        v = ctx.outputs.dcf_fcff.get("equity_value_per_share")
        if v is not None:
            values.append(float(v))
    if ctx.outputs.dcf_fcfe:
        v = ctx.outputs.dcf_fcfe.get("value_per_share")
        if v is not None:
            values.append(float(v))
    if ctx.outputs.relative:
        v = ctx.outputs.relative.get("composite_value")
        if v is not None:
            values.append(float(v))
    if ctx.outputs.excess_returns:
        v = ctx.outputs.excess_returns.get("value_per_share")
        if v is not None:
            values.append(float(v))

    if values:
        lo, hi = min(values), max(values)
        if lo == hi:
            value_range = _fmt(lo, prefix="$")
        else:
            value_range = f"{_fmt(lo, prefix='$')} – {_fmt(hi, prefix='$')}"
    else:
        value_range = "N/A (no models run)"

    # Market price for context
    price = None
    if ctx.financials.key_stats:
        price = ctx.financials.key_stats.get("price")
    price_str = _fmt(price, prefix="$") if price else "N/A"

    lines = [
        f"# Valuation Report: {name} ({ticker})",
        "",
        "## Executive Summary",
        "",
        f"| Item | Value |",
        f"|------|-------|",
        f"| Company | {name} ({ticker}) |",
        f"| Classification | {classification} |",
        f"| Intrinsic Value Range | {value_range} |",
        f"| Market Price | {price_str} |",
        f"| Confidence | {confidence} |",
    ]

    # Upside/downside vs market price
    if values and price and float(price) > 0:
        mid = sum(values) / len(values)
        upside_pct = (mid - float(price)) / float(price) * 100
        direction = "upside" if upside_pct >= 0 else "downside"
        lines.append(
            f"| Implied {direction.capitalize()} | {abs(upside_pct):.1f}% {direction} vs market |"
        )

    return "\n".join(lines)


def _section_company_profile(ctx: ValuationContext) -> str:
    co = ctx.company
    rows = [
        ("Ticker", co.ticker),
        ("Name", co.name or "N/A"),
        ("Sector", co.sector or "N/A"),
        ("SIC Code", co.sic_code or "N/A"),
        ("Classification", co.classification or "N/A"),
        ("Damodaran Industry", co.damodaran_industry or "N/A"),
        ("Region", co.region or "N/A"),
    ]
    table = _md_table(["Field", "Value"], rows)
    return "## Company Profile\n\n" + table


def _section_company_context(ctx: ValuationContext) -> str:
    """Company context: business description, recent news, key metrics."""
    profile = ctx.financials.key_stats.get("company_profile") or {}
    news = ctx.financials.key_stats.get("company_news") or []

    if not profile and not news:
        return ""

    lines = ["## Company Context"]

    desc = profile.get("description", "")
    if desc:
        lines += ["", desc[:800]]

    # Key metrics
    metrics = []
    if profile.get("revenue_growth"):
        metrics.append(("Revenue Growth (YoY)", _fmt_pct(profile["revenue_growth"])))
    if profile.get("earnings_growth"):
        metrics.append(("Earnings Growth (YoY)", _fmt_pct(profile["earnings_growth"])))
    if profile.get("profit_margins"):
        metrics.append(("Profit Margins", _fmt_pct(profile["profit_margins"])))
    if profile.get("peg_ratio"):
        metrics.append(("PEG Ratio", f"{profile['peg_ratio']:.2f}"))
    if profile.get("recommendation_key"):
        metrics.append(("Analyst Consensus", profile["recommendation_key"]))
    if profile.get("employees"):
        metrics.append(("Employees", f"{profile['employees']:,}"))
    if metrics:
        lines += ["", _md_table(["Metric", "Value"], metrics)]

    # Recent news
    if news:
        lines += ["", "### Recent News", ""]
        for n in news[:5]:
            title = n.get("title", "")
            publisher = n.get("publisher", "")
            lines.append(f"- **{title}** ({publisher})")

    return "\n".join(lines)


def _section_key_assumptions(ctx: ValuationContext) -> str:
    a = ctx.assumptions

    rows = [
        ("Risk-Free Rate", _fmt_pct(a.risk_free_rate)),
        ("Equity Risk Premium (ERP)", _fmt_pct(a.erp)),
        ("Country Risk Premium", _fmt_pct(a.country_risk_premium)),
        ("Beta (levered)", _fmt(a.beta, decimals=3)),
        ("Cost of Equity", _fmt_pct(a.cost_of_equity)),
        ("Cost of Debt (pre-tax)", _fmt_pct(a.cost_of_debt)),
        ("WACC", _fmt_pct(a.wacc)),
        ("Tax Rate", _fmt_pct(a.tax_rate)),
        ("Terminal Growth Rate", _fmt_pct(a.terminal_growth)),
        ("Projection Years", str(a.projection_years)),
    ]

    lines = ["## Key Assumptions", "", _md_table(["Parameter", "Value"], rows)]

    # Growth rate schedule
    if a.growth_rates:
        lines.append("")
        lines.append("**Growth Rate Schedule:**")
        lines.append("")
        gr_rows = [
            (f"Year {i + 1}", _fmt_pct(g))
            for i, g in enumerate(a.growth_rates)
        ]
        lines.append(_md_table(["Year", "Growth Rate"], gr_rows))

    # Overrides
    if a.overrides:
        lines.append("")
        lines.append("**Analyst Overrides:**")
        lines.append("")
        ov_rows = []
        for param, info in a.overrides.items():
            orig = info.get("original")
            new = info.get("new")
            reason = info.get("reason", "")
            ov_rows.append((
                param,
                _fmt(orig, decimals=4) if isinstance(orig, float) else str(orig),
                _fmt(new, decimals=4) if isinstance(new, float) else str(new),
                reason or "—",
            ))
        lines.append(_md_table(["Parameter", "Original", "Override", "Reason"], ov_rows))

    # Assumption reviews/flags
    reviews = ctx.financials.key_stats.get("assumption_reviews") or []
    if reviews:
        from valuation.agents.assumption_reviewer import format_review_for_report
        review_text = format_review_for_report(reviews)
        if review_text:
            lines.append("")
            lines.append(review_text)

    return "\n".join(lines)


def _section_dcf_valuation(ctx: ValuationContext) -> str:
    has_fcff = bool(ctx.outputs.dcf_fcff)
    has_fcfe = bool(ctx.outputs.dcf_fcfe)

    if not has_fcff and not has_fcfe:
        return ""

    lines = ["## DCF Valuation"]

    # --- FCFF block ---
    if has_fcff:
        d = ctx.outputs.dcf_fcff
        lines += [
            "",
            "### FCFF Multi-Stage DCF",
            "",
            _md_table(["Metric", "Value"], [
                ("Enterprise Value", _fmt(d.get("enterprise_value"), prefix="$")),
                ("Equity Value", _fmt(d.get("equity_value"), prefix="$")),
                ("Equity Value per Share", _fmt(d.get("equity_value_per_share"), prefix="$")),
                ("PV of High-Growth FCFFs", _fmt(d.get("pv_high_growth"), prefix="$")),
                ("PV of Terminal Value", _fmt(d.get("pv_terminal"), prefix="$")),
                ("Terminal Value (undiscounted)", _fmt(d.get("terminal_value"), prefix="$")),
            ]),
        ]

        # Year-by-year projections table
        yearly_fcff = d.get("yearly_fcff") or []
        yearly_pv = d.get("yearly_pv") or []
        yearly_ebit_at = d.get("yearly_ebit_at") or []
        if yearly_fcff:
            lines.append("")
            lines.append("**Year-by-Year Projections (FCFF):**")
            lines.append("")
            proj_rows = []
            for i, fcff in enumerate(yearly_fcff):
                pv = yearly_pv[i] if i < len(yearly_pv) else None
                ebit_at = yearly_ebit_at[i] if i < len(yearly_ebit_at) else None
                proj_rows.append((
                    str(i + 1),
                    _fmt(ebit_at, prefix="$"),
                    _fmt(fcff, prefix="$"),
                    _fmt(pv, prefix="$"),
                ))
            lines.append(_md_table(
                ["Year", "EBIT(1-t)", "FCFF", "PV of FCFF"],
                proj_rows,
            ))

    # --- DDM block (stored in dcf_fcfe slot for financial firms) ---
    if has_fcfe:
        d = ctx.outputs.dcf_fcfe
        lines += [
            "",
            "### DDM (Dividend Discount Model)",
            "",
            _md_table(["Metric", "Value"], [
                ("Value per Share", _fmt(d.get("value_per_share"), prefix="$")),
                ("PV of Dividends", _fmt(d.get("pv_dividends"), prefix="$")),
                ("PV of Terminal Price", _fmt(d.get("pv_terminal"), prefix="$")),
                ("Terminal Price (undiscounted)", _fmt(d.get("terminal_price"), prefix="$")),
            ]),
        ]

        yearly_eps = d.get("yearly_eps") or []
        yearly_dps = d.get("yearly_dps") or []
        yearly_pv = d.get("yearly_pv") or []
        if yearly_eps:
            lines.append("")
            lines.append("**Year-by-Year Projections (DDM):**")
            lines.append("")
            proj_rows = []
            for i, eps in enumerate(yearly_eps):
                dps = yearly_dps[i] if i < len(yearly_dps) else None
                pv = yearly_pv[i] if i < len(yearly_pv) else None
                proj_rows.append((
                    str(i + 1),
                    _fmt(eps, prefix="$"),
                    _fmt(dps, prefix="$"),
                    _fmt(pv, prefix="$"),
                ))
            lines.append(_md_table(
                ["Year", "EPS", "DPS", "PV of DPS"],
                proj_rows,
            ))

    return "\n".join(lines)


def _section_relative_valuation(ctx: ValuationContext) -> str:
    if not ctx.outputs.relative:
        return ""

    d = ctx.outputs.relative
    rows = [
        ("P/E Implied Value", _fmt(d.get("pe_value"), prefix="$")),
        ("EV/EBITDA Implied Value", _fmt(d.get("ev_ebitda_value"), prefix="$")),
        ("P/BV Implied Value", _fmt(d.get("pbv_value"), prefix="$")),
        ("P/S Implied Value", _fmt(d.get("ps_value"), prefix="$")),
        ("Composite Value (median)", _fmt(d.get("composite_value"), prefix="$")),
        ("Market Price", _fmt(d.get("market_price"), prefix="$")),
        ("Discount / Premium to Composite", _fmt_pct(d.get("discount_to_composite"))),
    ]

    methods = d.get("methods_used") or []
    if methods:
        rows.append(("Methods Used", ", ".join(methods)))

    return "## Relative Valuation\n\n" + _md_table(["Metric", "Value"], rows)


def _section_cross_validation(ctx: ValuationContext) -> str:
    # Cross-validation result may live in outputs or as a standalone dict;
    # check for a stored cross_validation key first, then try to reconstruct
    # from individual model outputs.
    cv: dict[str, Any] | None = None
    if ctx.outputs.dcf_fcff or ctx.outputs.relative or ctx.outputs.dcf_fcfe:
        # Try to find a cross_validation result stored anywhere on outputs
        for attr in ("cross_validation", "cross_val"):
            obj = getattr(ctx.outputs, attr, None)
            if obj is not None:
                cv = obj if isinstance(obj, dict) else getattr(obj, "to_dict", lambda: None)()
                break

    if cv is None:
        # Silently build a lightweight table from whatever model values exist
        model_values: dict[str, float] = {}
        if ctx.outputs.dcf_fcff:
            v = ctx.outputs.dcf_fcff.get("equity_value_per_share")
            if v is not None:
                model_values["DCF (FCFF)"] = float(v)
        if ctx.outputs.dcf_fcfe:
            v = ctx.outputs.dcf_fcfe.get("value_per_share")
            if v is not None:
                model_values["DDM"] = float(v)
        if ctx.outputs.relative:
            v = ctx.outputs.relative.get("composite_value")
            if v is not None:
                model_values["Relative (composite)"] = float(v)
        if ctx.outputs.excess_returns:
            v = ctx.outputs.excess_returns.get("value_per_share")
            if v is not None:
                model_values["Excess Returns"] = float(v)

        if not model_values:
            return ""

        rows = [(model, _fmt(val, prefix="$")) for model, val in model_values.items()]
        vals = list(model_values.values())
        if len(vals) > 1:
            import statistics
            rows += [
                ("Mean", _fmt(statistics.mean(vals), prefix="$")),
                ("Median", _fmt(statistics.median(vals), prefix="$")),
                ("Min", _fmt(min(vals), prefix="$")),
                ("Max", _fmt(max(vals), prefix="$")),
            ]

        lines = ["## Cross-Validation", "", _md_table(["Model", "Implied Value per Share"], rows)]

        # Divergence explanation
        explanation = ctx.financials.key_stats.get("divergence_explanation") if ctx.financials.key_stats else None
        if explanation:
            lines.append("")
            lines.append("**Model Divergence Analysis:**")
            lines.append("")
            for line in explanation.splitlines():
                lines.append(line)

        return "\n".join(lines)

    # Full CrossValidationResult dict
    rows = [
        (model, _fmt(val, prefix="$"))
        for model, val in (cv.get("individual_values") or {}).items()
    ]
    summary_rows = [
        ("Mean Value", _fmt(cv.get("mean_value"), prefix="$")),
        ("Median Value", _fmt(cv.get("median_value"), prefix="$")),
        ("Min Value", _fmt(cv.get("min_value"), prefix="$")),
        ("Max Value", _fmt(cv.get("max_value"), prefix="$")),
        ("Max Divergence", _fmt_pct(cv.get("max_divergence_pct"))),
        ("Price vs Intrinsic", _fmt_pct(cv.get("price_vs_value_pct"))),
        ("Number of Models", str(cv.get("num_models", "N/A"))),
    ]

    lines = [
        "## Cross-Validation",
        "",
        "**Model Values:**",
        "",
        _md_table(["Model", "Implied Value per Share"], rows),
        "",
        "**Summary Statistics:**",
        "",
        _md_table(["Metric", "Value"], summary_rows),
    ]

    flags = cv.get("flags") or []
    if flags:
        lines.append("")
        lines.append("**Flags:**")
        lines.append("")
        for flag in flags:
            lines.append(f"- {flag}")

    # Divergence explanation
    explanation = ctx.financials.key_stats.get("divergence_explanation") if ctx.financials.key_stats else None
    if explanation:
        lines.append("")
        lines.append("**Model Divergence Analysis:**")
        lines.append("")
        for line in explanation.splitlines():
            lines.append(line)

    return "\n".join(lines)


def _section_analyst_consensus(ctx: ValuationContext) -> str:
    """Render the Analyst Coverage & Consensus section.

    Data sources (all optional):
    - ctx.financials.key_stats["analyst_data"]  — from fetch_analyst_data()
    - ctx.financials.key_stats["ibes_data"]     — from WRDS I/B/E/S fetch
    - ctx.financials.key_stats["price"]         — current market price
    - ctx.outputs.dcf_fcff / dcf_fcfe / relative — our own model values
    """
    ks = ctx.financials.key_stats or {}
    analyst_data: dict | None = ks.get("analyst_data")
    ibes_data: dict | None = ks.get("ibes_data")

    has_price_targets = bool(
        analyst_data and analyst_data.get("price_targets")
    )
    has_ibes = bool(ibes_data and ibes_data.get("estimates") is not None)

    if not has_price_targets and not has_ibes:
        return ""

    lines = [
        "## Analyst Coverage & Consensus",
        "",
        "> Consensus estimates shown for COMPARISON — not used as DCF inputs.",
    ]

    # ----------------------------------------------------------------
    # Price Targets block
    # ----------------------------------------------------------------
    if has_price_targets:
        pt = analyst_data["price_targets"]  # type: ignore[index]
        pt_rows = [
            ("Mean Target", _fmt(pt.get("targetMean"), prefix="$")),
            ("Median Target", _fmt(pt.get("targetMedian"), prefix="$")),
            ("High Target", _fmt(pt.get("targetHigh"), prefix="$")),
            ("Low Target", _fmt(pt.get("targetLow"), prefix="$")),
            ("# Analysts", str(pt.get("numberOfAnalysts") or "N/A")),
        ]
        lines += ["", "### Price Targets", "", _md_table(["Metric", "Value"], pt_rows)]

    # ----------------------------------------------------------------
    # Our Estimate vs Consensus comparison table
    # ----------------------------------------------------------------
    market_price: float | None = ks.get("price")

    # Collect our own model values
    our_values: list[tuple[str, float]] = []
    if ctx.outputs.dcf_fcff:
        v = ctx.outputs.dcf_fcff.get("equity_value_per_share")
        if v is not None:
            our_values.append(("Our DCF (FCFF)", float(v)))
    if ctx.outputs.dcf_fcfe:
        v = ctx.outputs.dcf_fcfe.get("value_per_share")
        if v is not None:
            our_values.append(("Our DDM", float(v)))
    if ctx.outputs.relative:
        v = ctx.outputs.relative.get("composite_value")
        if v is not None:
            our_values.append(("Our Relative (composite)", float(v)))

    analyst_mean: float | None = None
    if has_price_targets:
        pt = analyst_data["price_targets"]  # type: ignore[index]
        analyst_mean = pt.get("targetMean")

    if our_values or analyst_mean is not None or market_price is not None:
        lines += ["", "### Our Estimate vs Consensus", ""]

        def _vs_market(val: float | None, price: float | None) -> str:
            if val is None or price is None or float(price) == 0:
                return "—"
            pct = (val - float(price)) / float(price) * 100
            sign = "+" if pct >= 0 else ""
            return f"{sign}{pct:.1f}%"

        comparison_rows: list[tuple[str, str, str]] = []
        for model_name, model_val in our_values:
            comparison_rows.append((
                model_name,
                _fmt(model_val, prefix="$"),
                _vs_market(model_val, market_price),
            ))
        if analyst_mean is not None:
            comparison_rows.append((
                "Analyst Mean Target",
                _fmt(analyst_mean, prefix="$"),
                _vs_market(analyst_mean, market_price),
            ))
        if market_price is not None:
            comparison_rows.append(("Market Price", _fmt(market_price, prefix="$"), "—"))

        lines.append(_md_table(["Model", "Value", "vs Market"], comparison_rows))

    # ----------------------------------------------------------------
    # I/B/E/S Estimates block
    # ----------------------------------------------------------------
    if has_ibes:
        estimates = ibes_data["estimates"]  # type: ignore[index]
        ibes_ticker = ibes_data.get("ticker", "N/A")  # type: ignore[index]

        lines += [
            "",
            f"### I/B/E/S Estimates (ticker: {ibes_ticker})",
            "",
        ]

        try:
            import pandas as pd  # noqa: PLC0415

            if isinstance(estimates, pd.DataFrame) and not estimates.empty:
                ibes_rows: list[tuple] = []
                for _, row in estimates.head(8).iterrows():
                    period = str(row.get("statpers", row.get("fpedats", "N/A")))
                    mean_eps = row.get("meanest", row.get("mean", None))
                    median_eps = row.get("medest", row.get("median", None))
                    num_est = row.get("numest", row.get("numanalysts", None))
                    ibes_rows.append((
                        period,
                        _fmt(float(mean_eps), decimals=2) if mean_eps is not None else "N/A",
                        _fmt(float(median_eps), decimals=2) if median_eps is not None else "N/A",
                        str(int(num_est)) if num_est is not None else "N/A",
                    ))
                if ibes_rows:
                    lines.append(_md_table(
                        ["Period", "Mean EPS", "Median EPS", "# Analysts"],
                        ibes_rows,
                    ))
                else:
                    lines.append("_No estimate rows available._")
            else:
                lines.append("_No I/B/E/S estimate data available._")
        except Exception:
            lines.append("_I/B/E/S data could not be rendered._")

    # ----------------------------------------------------------------
    # Top Analysts block (accuracy-ranked)
    # ----------------------------------------------------------------
    top_analysts = ibes_data.get("top_analysts") if ibes_data else None
    if top_analysts is not None:
        try:
            import pandas as pd  # noqa: PLC0415

            if isinstance(top_analysts, pd.DataFrame) and not top_analysts.empty:
                lines += [
                    "",
                    "### Top Analysts (Ranked by Forecast Accuracy)",
                    "",
                    "> Accuracy = 1 - avg(|estimate - actual| / |actual|) over recent fiscal periods.",
                    "",
                ]
                analyst_rows: list[tuple] = []
                for _, row in top_analysts.iterrows():
                    name = str(row.get("analyst_name") or "N/A")
                    firm = str(row.get("firm") or "N/A")
                    acc = row.get("accuracy_pct")
                    acc_str = f"{acc:.0f}%" if acc is not None else "N/A"
                    target = row.get("target")
                    target_str = _fmt(float(target), prefix="$") if target is not None else "N/A"
                    rec = str(row.get("recommendation") or "N/A")
                    num_est = row.get("num_estimates")
                    num_str = str(int(num_est)) if num_est is not None else "N/A"
                    analyst_rows.append((name, firm, acc_str, target_str, rec, num_str))
                if analyst_rows:
                    lines.append(_md_table(
                        ["Analyst", "Firm", "Accuracy", "Target", "Recommendation", "# Estimates"],
                        analyst_rows,
                    ))
        except Exception:
            pass  # Silently skip if top_analysts data cannot be rendered

    return "\n".join(lines)


def _section_sensitivity_analysis(ctx: ValuationContext) -> str:
    if not ctx.outputs.sensitivity:
        return ""

    d = ctx.outputs.sensitivity

    lines = ["## Sensitivity Analysis", ""]

    # The sensitivity dict may contain nested tables (one-way or two-way)
    # or flat key→value pairs. Render what we can.
    nested_tables = {k: v for k, v in d.items() if isinstance(v, dict)}
    scalar_vals = {k: v for k, v in d.items() if isinstance(v, (int, float)) and not isinstance(v, bool)}

    if scalar_vals:
        rows = [(k, _fmt(v, prefix="$")) for k, v in scalar_vals.items()]
        lines.append(_md_table(["Scenario", "Value per Share"], rows))

    for table_name, table_data in nested_tables.items():
        if not isinstance(table_data, dict):
            continue
        lines.append("")
        lines.append(f"**{table_name}:**")
        lines.append("")
        # Render as a flat key-value table or nested grid
        inner_rows = []
        for row_key, row_val in table_data.items():
            if isinstance(row_val, dict):
                for col_key, cell_val in row_val.items():
                    inner_rows.append((f"{row_key} / {col_key}", _fmt(cell_val, prefix="$")))
            else:
                inner_rows.append((str(row_key), _fmt(row_val, prefix="$")))
        if inner_rows:
            lines.append(_md_table(["Key", "Value"], inner_rows))

    return "\n".join(lines)


def _section_confidence_assessment(ctx: ValuationContext) -> str:
    c = ctx.confidence

    has_any = any(
        x is not None
        for x in [
            c.data_completeness,
            c.model_agreement,
            c.assumption_sensitivity,
            c.industry_coverage,
            c.composite,
        ]
    )
    if not has_any and not c.flags:
        return ""

    rows = [
        ("Data Completeness", _fmt_pct(c.data_completeness)),
        ("Model Agreement", _fmt_pct(c.model_agreement)),
        ("Assumption Sensitivity", _fmt_pct(c.assumption_sensitivity)),
        ("Industry Coverage", _fmt_pct(c.industry_coverage)),
        ("Composite Score", _confidence_label(c.composite)),
    ]

    lines = ["## Confidence Assessment", "", _md_table(["Dimension", "Score"], rows)]

    if c.flags:
        lines.append("")
        lines.append("**Flags / Warnings:**")
        lines.append("")
        for flag in c.flags:
            lines.append(f"- {flag}")

    return "\n".join(lines)


def _section_data_sources(ctx: ValuationContext) -> str:
    """Render a data sources transparency table."""
    sourced = ctx.financials.key_stats.get("sourced_inputs") if ctx.financials.key_stats else None
    if not sourced:
        return ""
    from valuation.validation.data_sources import format_sources_markdown
    return "## Data Sources\n\n" + format_sources_markdown(sourced)


# ---------------------------------------------------------------------------
# Markdown table helper
# ---------------------------------------------------------------------------


def _md_table(headers: list[str], rows: list[tuple]) -> str:
    """Render a simple markdown table.

    Parameters
    ----------
    headers : list of str
        Column header labels.
    rows : list of tuple
        Each tuple is a row; values are converted to str.

    Returns
    -------
    str
        Markdown table string.
    """
    col_count = len(headers)
    lines = [
        "| " + " | ".join(headers) + " |",
        "|" + "|".join("---" for _ in range(col_count)) + "|",
    ]
    for row in rows:
        cells = list(row) + [""] * (col_count - len(row))
        lines.append("| " + " | ".join(str(c) for c in cells[:col_count]) + " |")
    return "\n".join(lines)
