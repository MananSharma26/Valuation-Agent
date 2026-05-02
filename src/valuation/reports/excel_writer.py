"""Generate Excel valuation workbook with multiple sheets.

Produces a structured Excel file similar to Damodaran's example spreadsheets,
with sheets for: Summary, Assumptions, DCF Model, Relative Valuation,
Sensitivity, Analyst Consensus, and Data Sources.

All formatting is deterministic Python — no LLM calls.
"""

from __future__ import annotations

import pathlib
from datetime import date
from typing import Any

import pandas as pd

from valuation.context import ValuationContext


def _safe(val: Any, fmt: str = ",.2f") -> Any:
    """Safe format: return value or empty string for None/NaN."""
    if val is None:
        return ""
    try:
        if isinstance(val, float) and val != val:  # NaN
            return ""
        return val
    except (TypeError, ValueError):
        return ""


def generate_excel(
    ctx: ValuationContext,
    ibes_data: dict | None = None,
    output_path: str | pathlib.Path | None = None,
) -> pathlib.Path:
    """Generate a multi-sheet Excel valuation workbook.

    Args:
        ctx: Completed ValuationContext with all outputs populated
        ibes_data: Optional dict with I/B/E/S analyst consensus data
        output_path: Where to save. If None, auto-generates path.

    Returns:
        Path to saved Excel file
    """
    if output_path is None:
        reports_dir = pathlib.Path(__file__).parent.parent.parent.parent / "reports"
        company_name = (ctx.company.name or ctx.company.ticker).replace("/", "-").replace("\\", "-")
        company_dir = reports_dir / company_name
        company_dir.mkdir(parents=True, exist_ok=True)
        ticker = ctx.company.ticker.replace(":", "-")
        output_path = company_dir / f"{date.today().isoformat()}_{ticker}.xlsx"

    output_path = pathlib.Path(output_path)

    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        _write_summary(writer, ctx)
        _write_assumptions(writer, ctx)
        _write_dcf_model(writer, ctx)
        _write_relative_valuation(writer, ctx)
        _write_sensitivity(writer, ctx)
        _write_analyst_consensus(writer, ctx, ibes_data)
        _write_data_sources(writer, ctx)
        _write_financials(writer, ctx)

    return output_path


def _write_summary(writer: pd.ExcelWriter, ctx: ValuationContext) -> None:
    """Sheet 1: Executive Summary — key results at a glance."""
    a = ctx.assumptions
    price = ctx.financials.key_stats.get("price")

    # Collect all model values
    models = {}
    if ctx.outputs.dcf_fcff:
        models["DCF (FCFF)"] = ctx.outputs.dcf_fcff.get("equity_value_per_share")
    if ctx.outputs.dcf_fcfe:
        models["DDM"] = ctx.outputs.dcf_fcfe.get("value_per_share")
    if ctx.outputs.relative:
        models["Relative (PE)"] = ctx.outputs.relative.get("pe_value")
        models["Relative (EV/EBITDA)"] = ctx.outputs.relative.get("ev_ebitda_value")
        models["Relative (PBV)"] = ctx.outputs.relative.get("pbv_value")
        models["Relative (PS)"] = ctx.outputs.relative.get("ps_value")
        models["Relative (Composite)"] = ctx.outputs.relative.get("composite_value")
    if ctx.outputs.excess_returns:
        models["Excess Returns"] = ctx.outputs.excess_returns.get("value_per_share")

    values = [v for v in models.values() if v is not None and v > 0]

    rows = [
        ["VALUATION SUMMARY", ""],
        ["Date", date.today().isoformat()],
        ["", ""],
        ["Company", ctx.company.name or ctx.company.ticker],
        ["Ticker", ctx.company.ticker],
        ["Classification", ctx.company.classification],
        ["Damodaran Industry", ctx.company.damodaran_industry],
        ["Region", ctx.company.region],
        ["", ""],
        ["MARKET DATA", ""],
        ["Current Price", _safe(price)],
        ["Market Cap", _safe(ctx.financials.key_stats.get("market_cap"))],
        ["Shares Outstanding", _safe(ctx.financials.key_stats.get("shares_outstanding"))],
        ["", ""],
        ["KEY ASSUMPTIONS", ""],
        ["Risk-Free Rate", _safe(a.risk_free_rate)],
        ["Equity Risk Premium", _safe(a.erp)],
        ["Beta", _safe(a.beta)],
        ["Cost of Equity", _safe(a.cost_of_equity)],
        ["WACC", _safe(a.wacc)],
        ["Terminal Growth", _safe(a.terminal_growth)],
        ["", ""],
        ["VALUATION RESULTS", ""],
    ]

    for model_name, val in models.items():
        if val is not None:
            upside = (val - price) / price if price and price > 0 else None
            rows.append([model_name, val, upside])
        else:
            rows.append([model_name, "N/A", ""])

    rows.append(["", ""])
    if values:
        rows.append(["Value Range (Low)", min(values)])
        rows.append(["Value Range (High)", max(values)])
        rows.append(["Mean", sum(values) / len(values)])
        if price and price > 0:
            mean_val = sum(values) / len(values)
            rows.append(["Implied Upside/Downside", (mean_val - price) / price])

    rows.append(["", ""])
    rows.append(["CONFIDENCE", ""])
    rows.append(["Data Completeness", _safe(ctx.confidence.data_completeness)])
    rows.append(["Model Agreement", _safe(ctx.confidence.model_agreement)])
    rows.append(["Assumption Sensitivity", _safe(ctx.confidence.assumption_sensitivity)])
    rows.append(["Composite Score", _safe(ctx.confidence.composite)])

    if ctx.confidence.flags:
        rows.append(["", ""])
        rows.append(["FLAGS", ""])
        for flag in ctx.confidence.flags:
            rows.append([flag, ""])

    df = pd.DataFrame(rows, columns=["Item", "Value", "vs Market"] if any(len(r) > 2 for r in rows) else ["Item", "Value"])
    df.to_excel(writer, sheet_name="Summary", index=False)


def _write_assumptions(writer: pd.ExcelWriter, ctx: ValuationContext) -> None:
    """Sheet 2: All assumptions with sources and overrides."""
    a = ctx.assumptions
    rows = [
        ["RISK PARAMETERS", "", ""],
        ["Risk-Free Rate", a.risk_free_rate, "Damodaran / Govt bond yield"],
        ["Equity Risk Premium", a.erp, "Damodaran implied ERP"],
        ["Country Risk Premium", a.country_risk_premium, "Damodaran ctryprem"],
        ["Beta (levered)", a.beta, "Industry bottom-up, re-levered"],
        ["Cost of Equity", a.cost_of_equity, "CAPM: Rf + Beta*ERP + Lambda*CRP"],
        ["Cost of Debt (pre-tax)", a.cost_of_debt, "Synthetic rating"],
        ["WACC", a.wacc, "Ke*E/(D+E) + Kd*(1-t)*D/(D+E)"],
        ["Tax Rate", a.tax_rate, "Effective from financials"],
        ["", "", ""],
        ["GROWTH PARAMETERS", "", ""],
        ["Terminal Growth", a.terminal_growth, "Nominal GDP growth"],
        ["Projection Years", a.projection_years, ""],
    ]

    if a.growth_rates:
        rows.append(["", "", ""])
        rows.append(["YEAR-BY-YEAR GROWTH", "", ""])
        for i, g in enumerate(a.growth_rates):
            rows.append([f"Year {i+1}", g, ""])

    if a.overrides:
        rows.append(["", "", ""])
        rows.append(["ANALYST OVERRIDES", "New Value", "Reason"])
        for param, info in a.overrides.items():
            rows.append([param, info.get("new"), info.get("reason", "")])

    # Industry benchmarks
    bm = ctx.benchmarks
    rows.append(["", "", ""])
    rows.append(["INDUSTRY BENCHMARKS", "", "Source"])
    rows.append(["Industry Beta", _safe(bm.industry_beta), "Damodaran betas"])
    rows.append(["Industry Unlevered Beta", _safe(bm.industry_unlevered_beta), "Damodaran betas"])
    rows.append(["Industry D/E", _safe(bm.industry_de_ratio), "Damodaran betas"])
    rows.append(["Industry WACC", _safe(bm.industry_wacc), "Damodaran wacc"])

    if bm.industry_multiples:
        rows.append(["", "", ""])
        rows.append(["INDUSTRY MULTIPLES", "", ""])
        for k, v in bm.industry_multiples.items():
            rows.append([k, _safe(v), "Damodaran"])

    if bm.industry_margins:
        rows.append(["", "", ""])
        rows.append(["INDUSTRY MARGINS", "", ""])
        for k, v in bm.industry_margins.items():
            rows.append([k, _safe(v), "Damodaran"])

    df = pd.DataFrame(rows, columns=["Parameter", "Value", "Source"])
    df.to_excel(writer, sheet_name="Assumptions", index=False)


def _write_dcf_model(writer: pd.ExcelWriter, ctx: ValuationContext) -> None:
    """Sheet 3: DCF year-by-year projections."""
    if ctx.outputs.dcf_fcff:
        d = ctx.outputs.dcf_fcff
        n = len(d.get("yearly_fcff", []))

        rows = {
            "Year": list(range(1, n + 1)),
            "EBIT(1-t)": d.get("yearly_ebit_at", []),
            "FCFF": d.get("yearly_fcff", []),
            "PV of FCFF": d.get("yearly_pv", []),
        }
        df = pd.DataFrame(rows)

        # Add summary below
        summary = pd.DataFrame([
            {"Year": "", "EBIT(1-t)": "", "FCFF": "", "PV of FCFF": ""},
            {"Year": "PV of High-Growth", "EBIT(1-t)": "", "FCFF": "", "PV of FCFF": d.get("pv_high_growth")},
            {"Year": "Terminal Value", "EBIT(1-t)": "", "FCFF": d.get("terminal_value"), "PV of FCFF": d.get("pv_terminal")},
            {"Year": "Enterprise Value", "EBIT(1-t)": "", "FCFF": "", "PV of FCFF": d.get("enterprise_value")},
            {"Year": "Equity Value", "EBIT(1-t)": "", "FCFF": "", "PV of FCFF": d.get("equity_value")},
            {"Year": "Value per Share", "EBIT(1-t)": "", "FCFF": "", "PV of FCFF": d.get("equity_value_per_share")},
        ])
        df = pd.concat([df, summary], ignore_index=True)
        df.to_excel(writer, sheet_name="DCF Model", index=False)

    elif ctx.outputs.dcf_fcfe:
        d = ctx.outputs.dcf_fcfe
        n = len(d.get("yearly_eps", []))
        rows = {
            "Year": list(range(1, n + 1)),
            "EPS": d.get("yearly_eps", []),
            "DPS": d.get("yearly_dps", []),
            "PV of DPS": d.get("yearly_pv", []),
        }
        df = pd.DataFrame(rows)
        summary = pd.DataFrame([
            {"Year": "", "EPS": "", "DPS": "", "PV of DPS": ""},
            {"Year": "PV of Dividends", "EPS": "", "DPS": "", "PV of DPS": d.get("pv_dividends")},
            {"Year": "Terminal Price", "EPS": "", "DPS": d.get("terminal_price"), "PV of DPS": d.get("pv_terminal")},
            {"Year": "Value per Share", "EPS": "", "DPS": "", "PV of DPS": d.get("value_per_share")},
        ])
        df = pd.concat([df, summary], ignore_index=True)
        df.to_excel(writer, sheet_name="DCF Model (DDM)", index=False)


def _write_relative_valuation(writer: pd.ExcelWriter, ctx: ValuationContext) -> None:
    """Sheet 4: Relative valuation comparison."""
    if not ctx.outputs.relative:
        return

    d = ctx.outputs.relative
    price = ctx.financials.key_stats.get("price")

    rows = []
    multiples = [
        ("P/E", "pe_value"),
        ("EV/EBITDA", "ev_ebitda_value"),
        ("P/BV", "pbv_value"),
        ("P/S", "ps_value"),
        ("Composite (Median)", "composite_value"),
    ]
    for label, key in multiples:
        val = d.get(key)
        vs_market = (val - price) / price if val and price and price > 0 else None
        rows.append([label, _safe(val), _safe(vs_market)])

    rows.append(["", "", ""])
    rows.append(["Market Price", _safe(price), ""])
    rows.append(["Discount/Premium to Composite", _safe(d.get("discount_to_composite")), ""])
    rows.append(["Methods Used", ", ".join(d.get("methods_used", [])), ""])

    # Industry multiples reference
    if ctx.benchmarks.industry_multiples:
        rows.append(["", "", ""])
        rows.append(["INDUSTRY MULTIPLES", "Value", ""])
        for k, v in ctx.benchmarks.industry_multiples.items():
            rows.append([k, _safe(v), ""])

    df = pd.DataFrame(rows, columns=["Multiple", "Implied Value", "vs Market"])
    df.to_excel(writer, sheet_name="Relative Valuation", index=False)


def _write_sensitivity(writer: pd.ExcelWriter, ctx: ValuationContext) -> None:
    """Sheet 5: Sensitivity tables."""
    if not ctx.outputs.sensitivity:
        return

    sens = ctx.outputs.sensitivity
    all_rows = []

    for table_name, table_data in sens.items():
        if isinstance(table_data, dict):
            # Check if it's a two-way table (nested dicts) or one-way
            first_val = next(iter(table_data.values()), None)
            if isinstance(first_val, dict):
                # Two-way: rows = param1 values, cols = param2 values
                col_keys = sorted(first_val.keys())
                header = [table_name] + [f"{c:.4f}" if isinstance(c, float) else str(c) for c in col_keys]
                all_rows.append(header)
                for row_key in sorted(table_data.keys()):
                    row = [f"{row_key:.4f}" if isinstance(row_key, float) else str(row_key)]
                    for ck in col_keys:
                        val = table_data[row_key].get(ck, "")
                        row.append(_safe(val))
                    all_rows.append(row)
            else:
                # One-way
                all_rows.append([table_name, "Value per Share"])
                for k, v in table_data.items():
                    all_rows.append([k, _safe(v)])
            all_rows.append(["", ""])

    if all_rows:
        max_cols = max(len(r) for r in all_rows)
        for r in all_rows:
            while len(r) < max_cols:
                r.append("")
        df = pd.DataFrame(all_rows)
        df.to_excel(writer, sheet_name="Sensitivity", index=False, header=False)


def _write_analyst_consensus(
    writer: pd.ExcelWriter, ctx: ValuationContext, ibes_data: dict | None
) -> None:
    """Sheet 6: Analyst consensus comparison (I/B/E/S data shown alongside our estimates)."""
    rows = [
        ["ANALYST CONSENSUS vs OUR ESTIMATE", "", "", ""],
        ["(Consensus is for COMPARISON ONLY — not used as DCF input)", "", "", ""],
        ["", "", "", ""],
    ]

    if ibes_data and "estimates" in ibes_data:
        est = ibes_data["estimates"]
        if est is not None and not est.empty:
            rows.append(["I/B/E/S Consensus Estimates", "", "", ""])
            rows.append(["Period", "Mean EPS", "Median EPS", "# Analysts"])
            for _, row in est.iterrows():
                rows.append([
                    str(row.get("statpers", "")),
                    _safe(row.get("meanest")),
                    _safe(row.get("medest")),
                    _safe(row.get("numest")),
                ])
            rows.append(["", "", "", ""])

        if "ticker" in ibes_data:
            rows.append(["I/B/E/S Ticker", ibes_data["ticker"], "", ""])

    # Our estimates
    rows.append(["", "", "", ""])
    rows.append(["OUR FUNDAMENTAL ESTIMATES", "", "", ""])

    # DCF value
    if ctx.outputs.dcf_fcff:
        rows.append(["DCF (FCFF) Value/Share", ctx.outputs.dcf_fcff.get("equity_value_per_share"), "", ""])
    if ctx.outputs.dcf_fcfe:
        rows.append(["DDM Value/Share", ctx.outputs.dcf_fcfe.get("value_per_share"), "", ""])

    # Growth comparison
    rows.append(["", "", "", ""])
    rows.append(["GROWTH COMPARISON", "Our Estimate", "Consensus", "Source"])
    if ctx.assumptions.growth_rates:
        rows.append(["Year 1 Growth", ctx.assumptions.growth_rates[0], "", "Fundamental"])
    if ctx.assumptions.terminal_growth:
        rows.append(["Terminal Growth", ctx.assumptions.terminal_growth, "", "Nominal GDP"])

    price = ctx.financials.key_stats.get("price")
    if price:
        rows.append(["", "", "", ""])
        rows.append(["Market Price", price, "", "Yahoo Finance"])

    df = pd.DataFrame(rows, columns=["Item", "Value 1", "Value 2", "Notes"])
    df.to_excel(writer, sheet_name="Analyst Consensus", index=False)


def _write_data_sources(writer: pd.ExcelWriter, ctx: ValuationContext) -> None:
    """Sheet 7: Data source transparency — where every input came from."""
    rows = [
        ["DATA SOURCE TRANSPARENCY", "", ""],
        ["Every input is traced to its source", "", ""],
        ["", "", ""],
        ["Input", "Value", "Source"],
    ]

    stats = ctx.financials.key_stats
    a = ctx.assumptions

    # Market data
    rows.append(["MARKET DATA", "", ""])
    rows.append(["Price", _safe(stats.get("price")), "Yahoo Finance"])
    rows.append(["Market Cap", _safe(stats.get("market_cap")), "Yahoo Finance"])
    rows.append(["Shares Outstanding", _safe(stats.get("shares_outstanding")), "Yahoo Finance"])
    rows.append(["Beta (yfinance)", _safe(stats.get("beta")), "Yahoo Finance"])
    rows.append(["Book Value/Share", _safe(stats.get("book_value_per_share")), "Yahoo Finance"])
    rows.append(["Dividend/Share", _safe(stats.get("dividend_per_share")), "Yahoo Finance"])

    # Risk
    rows.append(["", "", ""])
    rows.append(["RISK INPUTS", "", ""])
    rows.append(["Risk-Free Rate", _safe(a.risk_free_rate), "Govt bond yield"])
    rows.append(["ERP", _safe(a.erp), "Damodaran histimpl.xls"])
    rows.append(["CRP", _safe(a.country_risk_premium), "Damodaran ctryprem.xlsx"])
    rows.append(["Industry Unlevered Beta", _safe(ctx.benchmarks.industry_unlevered_beta), f"Damodaran betas ({ctx.company.region})"])
    rows.append(["Beta (re-levered)", _safe(a.beta), "Computed: Bu*(1+(1-t)*D/E)"])
    rows.append(["Cost of Equity", _safe(a.cost_of_equity), "Computed: CAPM"])
    rows.append(["Cost of Debt", _safe(a.cost_of_debt), "Computed: Rf + synthetic spread"])
    rows.append(["WACC", _safe(a.wacc), "Computed"])
    rows.append(["Tax Rate", _safe(a.tax_rate), "Computed from financials"])

    # Growth
    rows.append(["", "", ""])
    rows.append(["GROWTH INPUTS", "", ""])
    rows.append(["Terminal Growth", _safe(a.terminal_growth), "Nominal GDP growth"])
    if a.growth_rates:
        rows.append(["High Growth Rate", _safe(a.growth_rates[0]), "See Assumptions sheet"])

    # Financial data
    rows.append(["", "", ""])
    rows.append(["FINANCIAL DATA", "", ""])
    if ctx.financials.income_statement is not None:
        rows.append(["Income Statement", f"{ctx.financials.income_statement.shape[0]} years", "Yahoo Finance"])
    if ctx.financials.balance_sheet is not None:
        rows.append(["Balance Sheet", f"{ctx.financials.balance_sheet.shape[0]} years", "Yahoo Finance"])
    if ctx.financials.cash_flow is not None:
        rows.append(["Cash Flow", f"{ctx.financials.cash_flow.shape[0]} years", "Yahoo Finance"])

    # Industry benchmarks
    rows.append(["", "", ""])
    rows.append(["INDUSTRY BENCHMARKS", "", ""])
    rows.append(["Damodaran Industry", ctx.company.damodaran_industry or "N/A", "Fuzzy match"])
    rows.append(["Industry WACC", _safe(ctx.benchmarks.industry_wacc), f"Damodaran wacc ({ctx.company.region})"])

    df = pd.DataFrame(rows, columns=["Input", "Value", "Source"])
    df.to_excel(writer, sheet_name="Data Sources", index=False)


def _write_financials(writer: pd.ExcelWriter, ctx: ValuationContext) -> None:
    """Sheet 8: Raw financial statements from API."""
    if ctx.financials.income_statement is not None:
        ctx.financials.income_statement.to_excel(writer, sheet_name="Income Statement")
    if ctx.financials.balance_sheet is not None:
        ctx.financials.balance_sheet.to_excel(writer, sheet_name="Balance Sheet")
    if ctx.financials.cash_flow is not None:
        ctx.financials.cash_flow.to_excel(writer, sheet_name="Cash Flow")
