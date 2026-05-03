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
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

from valuation.context import ValuationContext


# ---------------------------------------------------------------------------
# Colour / style constants
# ---------------------------------------------------------------------------

_DARK_BLUE = "1F3864"       # header row background
_LIGHT_GRAY = "D9D9D9"      # section-title background
_WHITE = "FFFFFF"
_GREEN = "00B050"            # positive upside
_RED = "FF0000"              # negative
_LIGHT_GREEN_BG = "E2EFDA"  # highlight base-case cell background
_YELLOW_BG = "FFFF00"       # base-case cell fill

_HEADER_FONT = Font(name="Calibri", bold=True, size=12, color=_WHITE)
_SECTION_FONT = Font(name="Calibri", bold=True, size=11, color="000000")
_NORMAL_FONT = Font(name="Calibri", size=10)
_BOLD_FONT = Font(name="Calibri", bold=True, size=10)

_HEADER_FILL = PatternFill("solid", fgColor=_DARK_BLUE)
_SECTION_FILL = PatternFill("solid", fgColor=_LIGHT_GRAY)
_WHITE_FILL = PatternFill("solid", fgColor=_WHITE)

_THIN = Side(style="thin")
_THIN_BORDER = Border(bottom=_THIN)

_CENTER = Alignment(horizontal="center", vertical="center")
_LEFT = Alignment(horizontal="left", vertical="center")
_RIGHT = Alignment(horizontal="right", vertical="center")

# Number format strings
_FMT_INT = "#,##0"
_FMT_DEC = "#,##0.00"
_FMT_PCT = "0.0%"
_FMT_PCT2 = "0.00%"
_FMT_PRICE = "#,##0.00"


# ---------------------------------------------------------------------------
# Low-level helpers
# ---------------------------------------------------------------------------

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


def _ws(writer: pd.ExcelWriter, sheet_name: str):
    """Return the openpyxl worksheet for the given sheet name."""
    return writer.sheets[sheet_name]


def _style_header_row(ws, row: int, n_cols: int) -> None:
    """Apply dark-blue header styling to an entire row."""
    for col in range(1, n_cols + 1):
        cell = ws.cell(row=row, column=col)
        cell.font = _HEADER_FONT
        cell.fill = _HEADER_FILL
        cell.alignment = _CENTER if col > 1 else _LEFT


def _style_section_title(ws, row: int, n_cols: int) -> None:
    """Apply light-gray section-title styling to a row."""
    for col in range(1, n_cols + 1):
        cell = ws.cell(row=row, column=col)
        cell.font = _SECTION_FONT
        cell.fill = _SECTION_FILL
        cell.alignment = _LEFT


def _autofit_columns(ws, min_label_width: int = 30, data_width: int = 16) -> None:
    """Set column A wider (for labels) and remaining columns to data_width."""
    ws.column_dimensions["A"].width = min_label_width
    for col_idx in range(2, ws.max_column + 1):
        ws.column_dimensions[get_column_letter(col_idx)].width = data_width


def _freeze_top_row(ws) -> None:
    ws.freeze_panes = "A2"


def _is_section_title(val: Any) -> bool:
    """Heuristic: a cell is a section title if it's an ALL-CAPS string."""
    if not isinstance(val, str):
        return False
    stripped = val.strip()
    return stripped == stripped.upper() and len(stripped) > 2 and stripped != ""


def _is_pct_label(label: str) -> bool:
    """Return True if the label suggests the value is a percentage."""
    label_lower = label.lower() if isinstance(label, str) else ""
    # Beta, D/E, S2C, PEG are ratios, NOT percentages
    non_pct = ("beta", "d/e", "sales to capital", "peg", "pe ", "pbv",
               "ev_ebitda", "ev_ebit", "ev_sales", "ev_invested", "current_pe",
               "trailing_pe", "forward_pe")
    if any(kw in label_lower for kw in non_pct):
        return False
    pct_keywords = ("rate", "growth", "yield", "wacc", "margin",
                    "upside", "downside", "completeness", "agreement",
                    "sensitivity", "score", "coverage", "premium", "discount",
                    "cost of equity", "cost of debt", "cost of capital",
                    "roe", "roic", "roc")
    return any(kw in label_lower for kw in pct_keywords)


def _apply_number_format(cell, label: str = "") -> None:
    """Apply number format based on value type and label hints."""
    val = cell.value
    if not isinstance(val, (int, float)):
        return
    if _is_pct_label(label) and abs(val) <= 3:
        # Likely stored as decimal fraction (e.g. 0.085 = 8.5%)
        cell.number_format = _FMT_PCT
    elif isinstance(val, float) and abs(val) < 1000 and abs(val) > 0:
        cell.number_format = _FMT_PRICE
    else:
        cell.number_format = _FMT_INT


def _apply_upside_color(cell) -> None:
    """Color a percentage upside/downside cell green or red."""
    val = cell.value
    if not isinstance(val, (int, float)):
        return
    if val > 0:
        cell.font = Font(name="Calibri", size=10, color=_GREEN)
    elif val < 0:
        cell.font = Font(name="Calibri", size=10, color=_RED)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

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

    # If file is locked (e.g., open in Excel), add a suffix
    if output_path.exists():
        try:
            output_path.unlink()
        except PermissionError:
            stem = output_path.stem
            output_path = output_path.with_name(f"{stem}_{date.today().strftime('%H%M%S')}.xlsx")

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


# ---------------------------------------------------------------------------
# Sheet writers
# ---------------------------------------------------------------------------

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

    has_upside = any(len(r) > 2 for r in rows)
    for model_name, val in models.items():
        if val is not None:
            upside = (val - price) / price if price and price > 0 else None
            rows.append([model_name, val, upside])
            has_upside = True
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

    cols = ["Item", "Value", "vs Market"] if has_upside else ["Item", "Value"]
    # Pad rows to match column count
    ncols = len(cols)
    for r in rows:
        while len(r) < ncols:
            r.append("")

    df = pd.DataFrame(rows, columns=cols)
    df.to_excel(writer, sheet_name="Summary", index=False)

    ws = _ws(writer, "Summary")

    # Company name as prominent title in A1 (merged)
    company_label = ctx.company.name or ctx.company.ticker
    ws.cell(row=1, column=1).value = f"Valuation Report — {company_label}"
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=ncols)
    ws.cell(row=1, column=1).font = Font(name="Calibri", bold=True, size=14, color=_WHITE)
    ws.cell(row=1, column=1).fill = _HEADER_FILL
    ws.cell(row=1, column=1).alignment = _CENTER

    # Walk through and apply styles
    pct_labels = {"risk-free rate", "equity risk premium", "beta", "cost of equity",
                  "wacc", "terminal growth", "data completeness", "model agreement",
                  "assumption sensitivity", "composite score", "implied upside/downside"}

    for row_idx in range(2, ws.max_row + 1):
        label_cell = ws.cell(row=row_idx, column=1)
        label = label_cell.value or ""

        if _is_section_title(label):
            _style_section_title(ws, row_idx, ncols)
            continue

        label_cell.font = _BOLD_FONT if label and not isinstance(label, (int, float)) else _NORMAL_FONT
        label_cell.alignment = _LEFT

        # Value cell
        val_cell = ws.cell(row=row_idx, column=2)
        val = val_cell.value
        if isinstance(val, (int, float)):
            label_lower = label.lower()
            if label_lower in pct_labels and abs(val) <= 3:
                val_cell.number_format = _FMT_PCT
            elif label_lower in ("current price", "value range (low)", "value range (high)", "mean"):
                val_cell.number_format = _FMT_PRICE
            elif label_lower in ("market cap", "shares outstanding"):
                val_cell.number_format = _FMT_INT
            else:
                val_cell.number_format = _FMT_DEC
            val_cell.alignment = _RIGHT

        # vs Market column (upside/downside)
        if ncols >= 3:
            upside_cell = ws.cell(row=row_idx, column=3)
            if isinstance(upside_cell.value, (int, float)):
                upside_cell.number_format = _FMT_PCT
                _apply_upside_color(upside_cell)
                upside_cell.alignment = _RIGHT

    # Row 1 is now our merged title; the old header row (DataFrame headers) is row 2
    # Style the DataFrame header row (first row of the DataFrame = row 2 in worksheet
    # because to_excel writes header at row index 0 → Excel row 1, but we overwrote it)
    # Actually to_excel with index=False writes header at row 1, data from row 2.
    # We replaced row 1's content with the merged title above.
    # The column headers from df are ALREADY in row 1; we overwrote A1 with our title.
    # Re-apply header style to row 1 for columns 2..n (which still have df column names)
    for col in range(1, ncols + 1):
        cell = ws.cell(row=1, column=col)
        cell.font = Font(name="Calibri", bold=True, size=14, color=_WHITE)
        cell.fill = _HEADER_FILL
        cell.alignment = _CENTER

    _autofit_columns(ws)
    _freeze_top_row(ws)


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

    pct_params = {"risk-free rate", "equity risk premium", "country risk premium",
                  "beta (levered)", "cost of equity", "cost of debt (pre-tax)",
                  "wacc", "tax rate", "terminal growth", "industry wacc",
                  "industry beta", "industry unlevered beta"}
    growth_keywords = ("year ", "growth")

    df = pd.DataFrame(rows, columns=["Parameter", "Value", "Source"])
    df.to_excel(writer, sheet_name="Assumptions", index=False)

    ws = _ws(writer, "Assumptions")
    _style_header_row(ws, 1, 3)

    for row_idx in range(2, ws.max_row + 1):
        label = ws.cell(row=row_idx, column=1).value or ""
        val_cell = ws.cell(row=row_idx, column=2)

        if _is_section_title(label):
            _style_section_title(ws, row_idx, 3)
            continue

        ws.cell(row=row_idx, column=1).font = _NORMAL_FONT

        if isinstance(val_cell.value, (int, float)):
            label_lower = str(label).lower()
            if label_lower in pct_params and abs(val_cell.value) <= 3:
                val_cell.number_format = _FMT_PCT
            elif any(kw in label_lower for kw in growth_keywords) and abs(val_cell.value) <= 3:
                val_cell.number_format = _FMT_PCT
            else:
                val_cell.number_format = _FMT_DEC
            val_cell.alignment = _RIGHT

    _autofit_columns(ws)
    _freeze_top_row(ws)


def _write_dcf_model(writer: pd.ExcelWriter, ctx: ValuationContext) -> None:
    """Sheet 3: DCF year-by-year projections — full Damodaran-style calculation flow."""
    if ctx.outputs.dcf_fcff:
        d = ctx.outputs.dcf_fcff
        a = ctx.assumptions

        yearly_revenue = d.get("yearly_revenue", [])
        yearly_ebit = d.get("yearly_ebit", [])
        yearly_ebit_at = d.get("yearly_ebit_at", [])
        yearly_reinvestment = d.get("yearly_reinvestment", [])
        yearly_fcff = d.get("yearly_fcff", [])
        yearly_pv = d.get("yearly_pv", [])
        n = len(yearly_fcff)

        # Detect v2 (revenue-based) vs v1 (ebit-based) by presence of yearly_revenue
        is_v2 = bool(yearly_revenue)

        if is_v2:
            # --- Reconstruct per-year schedules from output data ---
            base_revenue = d.get("base_revenue")
            base_ebit = d.get("base_ebit")

            # Back-calculate base revenue from first projection year + growth rate
            if base_revenue is None and yearly_revenue and a.growth_rates:
                g0 = a.growth_rates[0]
                base_revenue = yearly_revenue[0] / (1 + g0) if g0 != -1 else yearly_revenue[0]

            # Revenue growth rates per year (derived from data)
            rev_growth: list = []
            for t in range(n):
                prev = base_revenue if t == 0 else yearly_revenue[t - 1]
                if prev and prev != 0:
                    rev_growth.append(yearly_revenue[t] / prev - 1)
                elif a.growth_rates and t < len(a.growth_rates):
                    rev_growth.append(a.growth_rates[t])
                else:
                    rev_growth.append("")

            # Operating margin per year: ebit / revenue
            op_margins: list = []
            for t in range(n):
                rev = yearly_revenue[t] if t < len(yearly_revenue) else 0
                ebt = yearly_ebit[t] if t < len(yearly_ebit) else 0
                if rev and rev != 0:
                    op_margins.append(ebt / rev)
                else:
                    op_margins.append("")

            # Tax rate per year: 1 - ebit_at / ebit
            tax_rates_y: list = []
            for t in range(n):
                ebt = yearly_ebit[t] if t < len(yearly_ebit) else 0
                ebt_at = yearly_ebit_at[t] if t < len(yearly_ebit_at) else 0
                if ebt and ebt != 0:
                    tax_rates_y.append(1 - ebt_at / ebt)
                else:
                    tax_rates_y.append(a.tax_rate if a.tax_rate is not None else "")

            # Cumulated discount factor: |fcff / pv|
            cum_discount: list = []
            for t in range(n):
                fcff_t = yearly_fcff[t] if t < len(yearly_fcff) else 0
                pv_t = yearly_pv[t] if t < len(yearly_pv) else 0
                if fcff_t and fcff_t != 0 and pv_t and pv_t != 0:
                    cum_discount.append(abs(fcff_t / pv_t))
                else:
                    cum_discount.append("")

            # Per-year WACC: cum[t]/cum[t-1] - 1
            wacc_y: list = []
            for t in range(n):
                cd = cum_discount[t]
                if isinstance(cd, float):
                    if t == 0:
                        wacc_y.append(cd - 1)
                    else:
                        prev_cd = cum_discount[t - 1]
                        if isinstance(prev_cd, float) and prev_cd != 0:
                            wacc_y.append(cd / prev_cd - 1)
                        else:
                            wacc_y.append(a.wacc if a.wacc is not None else "")
                else:
                    wacc_y.append(a.wacc if a.wacc is not None else "")

            # Terminal period values
            terminal_growth = a.terminal_growth
            terminal_margin = op_margins[-1] if op_margins and isinstance(op_margins[-1], float) else ""
            terminal_tax = a.tax_rate if a.tax_rate is not None else (
                tax_rates_y[-1] if tax_rates_y and isinstance(tax_rates_y[-1], float) else ""
            )
            base_margin = (base_ebit / base_revenue) if (base_ebit is not None and base_revenue) else ""
            base_ebit_at = (base_ebit * (1 - a.tax_rate)) if (base_ebit is not None and a.tax_rate is not None) else ""

            def _yr_vals(lst: list) -> list:
                """Pad/trim list to exactly n elements as _safe values."""
                return [_safe(lst[t]) if t < len(lst) else "" for t in range(n)]

            def _make_row(label: str, base_val, yearly_vals: list, terminal_val="") -> list:
                row = [label, _safe(base_val)] + _yr_vals(yearly_vals) + [_safe(terminal_val)]
                return row

            rows: list = []

            # Year-label header row
            rows.append([""] + ["Base"] + [str(t + 1) for t in range(n)] + ["Terminal"])

            # REVENUE PROJECTIONS block
            rows.append(["REVENUE PROJECTIONS"] + [""] * (n + 2))
            rows.append(_make_row("Revenue Growth Rate", "", rev_growth, terminal_growth))
            rows.append(_make_row("Revenues", base_revenue, yearly_revenue, ""))
            rows.append(_make_row("Operating Margin", base_margin, op_margins, terminal_margin))
            rows.append(_make_row("Operating Income (EBIT)", base_ebit, yearly_ebit, ""))

            # TAX & REINVESTMENT block
            rows.append([""] + [""] * (n + 2))
            rows.append(["TAX & REINVESTMENT"] + [""] * (n + 2))
            rows.append(_make_row("Tax Rate", a.tax_rate, tax_rates_y, terminal_tax))
            rows.append(_make_row("EBIT(1-t)", base_ebit_at, yearly_ebit_at, ""))
            rows.append(_make_row("- Reinvestment", "", yearly_reinvestment, ""))
            rows.append(_make_row("= FCFF", "", yearly_fcff, _safe(d.get("terminal_fcff"))))

            # DISCOUNT RATES block
            rows.append([""] + [""] * (n + 2))
            rows.append(["DISCOUNT RATES"] + [""] * (n + 2))
            rows.append(_make_row("Cost of Capital (WACC)", a.wacc, wacc_y, ""))
            rows.append(_make_row("Cumulated Discount Factor", "", cum_discount, ""))
            rows.append(_make_row("PV(FCFF)", "", yearly_pv, ""))

            # TERMINAL VALUE block
            rows.append([""] + [""] * (n + 2))
            rows.append(["TERMINAL VALUE"] + [""] * (n + 2))
            # Terminal value and PV go in the Terminal column (last column)
            rows.append(["Terminal Value"] + [""] * (n + 1) + [_safe(d.get("terminal_value"))])
            rows.append(["PV(Terminal Value)"] + [""] * (n + 1) + [_safe(d.get("pv_terminal"))])

            # EQUITY VALUE BRIDGE block
            price = ctx.financials.key_stats.get("price")
            shares = ctx.financials.key_stats.get("shares_outstanding")
            vps = d.get("equity_value_per_share")
            upside = (vps - price) / price if (vps and price and price > 0) else None

            rows.append([""] + [""] * (n + 2))
            rows.append(["EQUITY VALUE BRIDGE"] + [""] * (n + 2))
            for label, val in [
                ("Value of Operating Assets", d.get("enterprise_value")),
                ("+ Cash", d.get("cash")),
                ("- Debt", d.get("debt")),
                ("+ Non-operating Assets", d.get("non_operating_assets")),
                ("= Value of Equity", d.get("equity_value")),
                ("/ Shares Outstanding", shares),
                ("= Value per Share", vps),
                ("Market Price", price),
                ("% Under / Over Valued", upside),
            ]:
                rows.append([label, _safe(val)] + [""] * (n + 1))

        else:
            # --- v1 fallback: EBIT-driven (no revenue data) ---
            rows = [[""] + [str(t + 1) for t in range(n)] + ["Terminal"]]
            rows.append(["EBIT(1-t)"] + [_safe(v) for v in yearly_ebit_at] + [""])
            rows.append(["FCFF"] + [_safe(v) for v in yearly_fcff] + [_safe(d.get("terminal_value"))])
            rows.append(["PV of FCFF"] + [_safe(v) for v in yearly_pv] + [_safe(d.get("pv_terminal"))])
            rows.append([""] * (n + 2))
            rows.append(["PV of High-Growth Phase", _safe(d.get("pv_high_growth"))] + [""] * (n + 1))
            rows.append(["PV of Terminal Value", _safe(d.get("pv_terminal"))] + [""] * (n + 1))
            rows.append(["Enterprise Value", _safe(d.get("enterprise_value"))] + [""] * (n + 1))
            rows.append(["Equity Value", _safe(d.get("equity_value"))] + [""] * (n + 1))
            rows.append(["Value per Share", _safe(d.get("equity_value_per_share"))] + [""] * (n + 1))

        max_cols = max(len(r) for r in rows)
        for r in rows:
            while len(r) < max_cols:
                r.append("")

        df = pd.DataFrame(rows)
        df.to_excel(writer, sheet_name="DCF Model", index=False, header=False)

        ws = _ws(writer, "DCF Model")

        _pct_labels_dcf = {
            "revenue growth rate", "operating margin", "tax rate",
            "cost of capital (wacc)",
        }
        _price_labels_dcf = {"= value per share", "market price"}
        _factor_labels_dcf = {"cumulated discount factor"}
        _section_labels_dcf = {
            "revenue projections", "tax & reinvestment",
            "discount rates", "terminal value", "equity value bridge",
        }

        for row_idx in range(1, ws.max_row + 1):
            label_cell = ws.cell(row=row_idx, column=1)
            label_raw = label_cell.value or ""
            label_lower = str(label_raw).strip().lower()

            # Year-label header row (row 1)
            if row_idx == 1:
                _style_header_row(ws, row_idx, max_cols)
                continue

            # Blank separator rows
            if label_lower == "":
                continue

            # Section title rows
            if label_lower in _section_labels_dcf:
                _style_section_title(ws, row_idx, max_cols)
                continue

            label_cell.font = _BOLD_FONT
            label_cell.alignment = _LEFT

            for col_idx in range(2, max_cols + 1):
                cell = ws.cell(row=row_idx, column=col_idx)
                val = cell.value
                if not isinstance(val, (int, float)):
                    continue

                if label_lower in _pct_labels_dcf and abs(val) <= 3:
                    cell.number_format = _FMT_PCT
                elif label_lower in _price_labels_dcf:
                    cell.number_format = _FMT_PRICE
                elif label_lower in _factor_labels_dcf:
                    cell.number_format = "#,##0.000"
                elif label_lower == "% under / over valued":
                    cell.number_format = _FMT_PCT
                    _apply_upside_color(cell)
                else:
                    cell.number_format = _FMT_INT
                cell.alignment = _RIGHT

        # Column widths
        ws.column_dimensions["A"].width = 30
        for col_idx in range(2, max_cols + 1):
            ws.column_dimensions[get_column_letter(col_idx)].width = 15

        ws.freeze_panes = "B2"

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

        ws = _ws(writer, "DCF Model (DDM)")
        _style_header_row(ws, 1, 4)

        for row_idx in range(2, ws.max_row + 1):
            year_cell = ws.cell(row=row_idx, column=1)
            year_val = year_cell.value
            if isinstance(year_val, str) and year_val.strip():
                year_cell.font = _BOLD_FONT
            for col_idx in range(2, 5):
                cell = ws.cell(row=row_idx, column=col_idx)
                if isinstance(cell.value, (int, float)):
                    cell.number_format = _FMT_PRICE
                    cell.alignment = _RIGHT

        _autofit_columns(ws, min_label_width=20)
        _freeze_top_row(ws)


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

    if ctx.benchmarks.industry_multiples:
        rows.append(["", "", ""])
        rows.append(["INDUSTRY MULTIPLES", "Value", ""])
        for k, v in ctx.benchmarks.industry_multiples.items():
            rows.append([k, _safe(v), ""])

    df = pd.DataFrame(rows, columns=["Multiple", "Implied Value", "vs Market"])
    df.to_excel(writer, sheet_name="Relative Valuation", index=False)

    ws = _ws(writer, "Relative Valuation")
    _style_header_row(ws, 1, 3)

    for row_idx in range(2, ws.max_row + 1):
        label = ws.cell(row=row_idx, column=1).value or ""

        if _is_section_title(label):
            _style_section_title(ws, row_idx, 3)
            continue

        val_cell = ws.cell(row=row_idx, column=2)
        if isinstance(val_cell.value, (int, float)):
            val_cell.number_format = _FMT_PRICE
            val_cell.alignment = _RIGHT

        vs_cell = ws.cell(row=row_idx, column=3)
        if isinstance(vs_cell.value, (int, float)):
            vs_cell.number_format = _FMT_PCT
            _apply_upside_color(vs_cell)
            vs_cell.alignment = _RIGHT

    _autofit_columns(ws)
    _freeze_top_row(ws)


def _write_sensitivity(writer: pd.ExcelWriter, ctx: ValuationContext) -> None:
    """Sheet 5: Sensitivity tables — formatted as proper grids with WACC vs terminal growth."""
    if not ctx.outputs.sensitivity:
        return

    sens = ctx.outputs.sensitivity

    # Detect if there are two-way tables present
    has_two_way = any(
        isinstance(v, dict) and isinstance(next(iter(v.values()), None), dict)
        for v in sens.values()
        if isinstance(v, dict)
    )

    # Build base case value for highlighting (look for dcf value)
    base_case_val = None
    if ctx.outputs.dcf_fcff:
        base_case_val = ctx.outputs.dcf_fcff.get("equity_value_per_share")
    elif ctx.outputs.dcf_fcfe:
        base_case_val = ctx.outputs.dcf_fcfe.get("value_per_share")

    # Determine base WACC and terminal growth for highlight
    base_wacc = ctx.assumptions.wacc
    base_tg = ctx.assumptions.terminal_growth

    all_rows = []
    table_positions: list[dict] = []  # track where two-way tables start for formatting

    current_excel_row = 1  # 1-indexed, accounts for header=False

    for table_name, table_data in sens.items():
        if isinstance(table_data, dict):
            first_val = next(iter(table_data.values()), None)
            if isinstance(first_val, dict):
                # Two-way table: rows = param1 values, cols = param2 values
                col_keys = sorted(first_val.keys())
                header = [table_name] + [
                    f"{c:.4f}" if isinstance(c, float) else str(c) for c in col_keys
                ]
                all_rows.append(header)
                table_start_row = current_excel_row
                current_excel_row += 1

                row_keys = sorted(table_data.keys())
                data_start_row = current_excel_row
                for row_key in row_keys:
                    row = [f"{row_key:.4f}" if isinstance(row_key, float) else str(row_key)]
                    for ck in col_keys:
                        val = table_data[row_key].get(ck, "")
                        row.append(_safe(val))
                    all_rows.append(row)
                    current_excel_row += 1

                table_positions.append({
                    "name": table_name,
                    "header_row": table_start_row,
                    "data_start_row": data_start_row,
                    "data_end_row": current_excel_row - 1,
                    "col_keys": col_keys,
                    "row_keys": row_keys,
                    "n_cols": len(col_keys) + 1,
                    "base_wacc": base_wacc,
                    "base_tg": base_tg,
                })
            else:
                # One-way table
                all_rows.append([table_name, "Value per Share"])
                current_excel_row += 1
                for k, v in table_data.items():
                    all_rows.append([k, _safe(v)])
                    current_excel_row += 1
            # Blank spacer row
            all_rows.append(["", ""])
            current_excel_row += 1

    if not all_rows:
        return

    max_cols = max(len(r) for r in all_rows)
    for r in all_rows:
        while len(r) < max_cols:
            r.append("")

    df = pd.DataFrame(all_rows)
    df.to_excel(writer, sheet_name="Sensitivity", index=False, header=False)

    ws = _ws(writer, "Sensitivity")

    # Style two-way tables
    for tbl in table_positions:
        hrow = tbl["header_row"]
        ncols = tbl["n_cols"]

        # Style the table header row
        _style_section_title(ws, hrow, ncols)
        ws.cell(row=hrow, column=1).font = Font(name="Calibri", bold=True, size=11)

        col_keys = tbl["col_keys"]
        row_keys = tbl["row_keys"]

        # Style column label cells (row header row = first data row's row_key labels)
        for ci, ck in enumerate(col_keys, start=2):
            cell = ws.cell(row=hrow, column=ci)
            cell.font = _BOLD_FONT
            cell.alignment = _CENTER
            if isinstance(ck, float):
                cell.value = ck
                cell.number_format = _FMT_PCT

        for ri, rk in enumerate(row_keys):
            excel_row = tbl["data_start_row"] + ri
            # Row label
            lbl_cell = ws.cell(row=excel_row, column=1)
            lbl_cell.font = _BOLD_FONT
            if isinstance(rk, float):
                lbl_cell.value = rk
                lbl_cell.number_format = _FMT_PCT
            lbl_cell.alignment = _RIGHT

            for ci, ck in enumerate(col_keys, start=2):
                cell = ws.cell(row=excel_row, column=ci)
                val = cell.value
                if val == "" or val is None:
                    continue
                try:
                    fval = float(val)
                    cell.value = fval
                    cell.number_format = _FMT_PRICE
                    cell.alignment = _RIGHT

                    # Highlight base-case cell
                    is_base_row = (
                        base_wacc is not None
                        and isinstance(rk, float)
                        and abs(rk - base_wacc) < 1e-6
                    )
                    is_base_col = (
                        base_tg is not None
                        and isinstance(ck, float)
                        and abs(ck - base_tg) < 1e-6
                    )
                    if is_base_row and is_base_col:
                        cell.fill = PatternFill("solid", fgColor=_YELLOW_BG)
                        cell.font = Font(name="Calibri", bold=True, size=10)
                    elif base_case_val is not None:
                        # Conditional coloring: green if above base, red if below
                        if fval > base_case_val * 1.05:
                            cell.fill = PatternFill("solid", fgColor="C6EFCE")
                        elif fval < base_case_val * 0.95:
                            cell.fill = PatternFill("solid", fgColor="FFC7CE")
                except (ValueError, TypeError):
                    pass

    # Style one-way table headers (rows not covered by table_positions)
    covered_rows = set()
    for tbl in table_positions:
        covered_rows.update(range(tbl["header_row"], tbl["data_end_row"] + 1))

    for row_idx in range(1, ws.max_row + 1):
        if row_idx in covered_rows:
            continue
        cell = ws.cell(row=row_idx, column=1)
        val = cell.value
        if val and isinstance(val, str) and val.strip() and not val.strip().startswith("0."):
            if val.strip() not in ("", "Value per Share"):
                _style_section_title(ws, row_idx, 2)
            elif val.strip() == "Value per Share":
                ws.cell(row=row_idx, column=2).font = _BOLD_FONT

    _autofit_columns(ws)
    ws.freeze_panes = None  # Sensitivity tables don't need freeze


def _write_analyst_consensus(
    writer: pd.ExcelWriter, ctx: ValuationContext, ibes_data: dict | None
) -> None:
    """Sheet 6: Analyst consensus comparison — Yahoo Finance + I/B/E/S."""
    analyst_data = ctx.financials.key_stats.get("analyst_data") or {}
    price = ctx.financials.key_stats.get("price")
    pt = analyst_data.get("price_targets") or {}
    recs = analyst_data.get("recommendations") or []
    ee = analyst_data.get("earnings_estimate") or {}

    rows = [
        ["ANALYST CONSENSUS vs OUR ESTIMATE", "", "", ""],
        ["(Consensus is for COMPARISON ONLY — not used as DCF input)", "", "", ""],
        ["", "", "", ""],
    ]

    # --- Price Targets ---
    if pt:
        rows.append(["PRICE TARGETS (Yahoo Finance)", "", "", ""])
        rows.append(["Mean Target", _safe(pt.get("targetMean")), "", ""])
        rows.append(["Median Target", _safe(pt.get("targetMedian")), "", ""])
        rows.append(["High Target", _safe(pt.get("targetHigh")), "", ""])
        rows.append(["Low Target", _safe(pt.get("targetLow")), "", ""])
        if pt.get("numberOfAnalysts"):
            rows.append(["# Analysts", pt["numberOfAnalysts"], "", ""])
        rows.append(["", "", "", ""])

    # --- Analyst Recommendations ---
    if recs:
        rows.append(["ANALYST RECOMMENDATIONS", "", "", ""])
        rows.append(["Period", "Strong Buy", "Buy", "Hold / Sell"])
        for rec in recs[:4]:
            period = rec.get("period", "")
            sb = rec.get("strongBuy", 0)
            b = rec.get("buy", 0)
            h = rec.get("hold", 0)
            s = rec.get("sell", 0) + rec.get("strongSell", 0)
            rows.append([period, sb, b, f"{h} / {s}"])
        total_latest = recs[0] if recs else {}
        total = sum(total_latest.get(k, 0) for k in ("strongBuy", "buy", "hold", "sell", "strongSell"))
        if total > 0:
            buy_pct = (total_latest.get("strongBuy", 0) + total_latest.get("buy", 0)) / total
            rows.append(["% Buy/Strong Buy", buy_pct, "", f"of {total} analysts"])
        rows.append(["", "", "", ""])

    # --- Earnings Estimates ---
    if ee and "avg" in ee:
        rows.append(["CONSENSUS EPS ESTIMATES", "Average", "Low", "High"])
        avg = ee.get("avg", {})
        low = ee.get("low", {})
        high = ee.get("high", {})
        growth = ee.get("growth", {})
        num = ee.get("numberOfAnalysts", {})
        for period, label in [("0q", "Current Quarter"), ("+1q", "Next Quarter"),
                               ("0y", "Current Year"), ("+1y", "Next Year")]:
            if period in avg:
                rows.append([
                    f"{label} ({period})",
                    _safe(avg.get(period)),
                    _safe(low.get(period)),
                    _safe(high.get(period)),
                ])
        rows.append(["", "", "", ""])
        rows.append(["CONSENSUS GROWTH ESTIMATES", "Growth Rate", "# Analysts", ""])
        for period, label in [("0q", "Current Qtr"), ("+1q", "Next Qtr"),
                               ("0y", "Current Year"), ("+1y", "Next Year")]:
            if period in growth:
                rows.append([label, _safe(growth.get(period)), _safe(num.get(period)), ""])
        rows.append(["", "", "", ""])

    # --- I/B/E/S (if available) ---
    if ibes_data and "estimates" in ibes_data:
        est = ibes_data["estimates"]
        if est is not None and not est.empty:
            rows.append(["I/B/E/S CONSENSUS (WRDS)", "", "", ""])
            rows.append(["Period", "Mean EPS", "Median EPS", "# Analysts"])
            for _, row in est.head(6).iterrows():
                rows.append([
                    str(row.get("statpers", "")),
                    _safe(row.get("meanest")),
                    _safe(row.get("medest")),
                    _safe(row.get("numest")),
                ])
            rows.append(["", "", "", ""])

    # --- Top Analysts (accuracy-ranked) ---
    top_analysts = ibes_data.get("top_analysts") if ibes_data else None
    if top_analysts is not None and not top_analysts.empty:
        rows.append(["TOP ANALYSTS (Ranked by EPS Forecast Accuracy)", "", "", ""])
        rows.append(["Analyst", "Firm", "Accuracy", "Target", "Recommendation", "# Estimates"])
        # Extend to 6 columns — pad existing rows below
        for _, row in top_analysts.iterrows():
            analyst_name = str(row.get("analyst_name") or "N/A")
            firm = str(row.get("firm") or "N/A")
            acc = row.get("accuracy_pct")
            target = row.get("target")
            rec = str(row.get("recommendation") or "N/A")
            num_est = row.get("num_estimates")
            rows.append([
                analyst_name,
                firm,
                _safe(acc / 100.0) if acc is not None else "",
                _safe(target) if target is not None else "",
                rec,
                _safe(num_est) if num_est is not None else "",
            ])
        rows.append(["", "", "", "", "", ""])

    # --- Our Estimate vs Consensus ---
    rows.append(["OUR ESTIMATE vs CONSENSUS", "Value", "vs Market", ""])
    our_dcf = None
    if ctx.outputs.dcf_fcff:
        our_dcf = ctx.outputs.dcf_fcff.get("equity_value_per_share")
        vs = (our_dcf - price) / price if price and price > 0 and our_dcf else None
        rows.append(["Our DCF (FCFF)", _safe(our_dcf), _safe(vs), "Independent fundamental"])
    if ctx.outputs.dcf_fcfe:
        our_ddm = ctx.outputs.dcf_fcfe.get("value_per_share")
        vs = (our_ddm - price) / price if price and price > 0 and our_ddm else None
        rows.append(["Our DDM", _safe(our_ddm), _safe(vs), "Independent fundamental"])
    if ctx.outputs.relative and ctx.outputs.relative.get("composite_value"):
        comp = ctx.outputs.relative["composite_value"]
        vs = (comp - price) / price if price and price > 0 else None
        rows.append(["Our Relative (composite)", _safe(comp), _safe(vs), "Industry multiples"])
    if pt.get("targetMean"):
        vs = (pt["targetMean"] - price) / price if price and price > 0 else None
        rows.append(["Analyst Mean Target", _safe(pt["targetMean"]), _safe(vs), "Yahoo Finance consensus"])
    rows.append(["Market Price", _safe(price), "", "Current"])
    rows.append(["", "", "", ""])

    # --- Why Our Valuation Differs ---
    rows.append(["WHY OUR VALUATION MAY DIFFER FROM CONSENSUS", "", "", ""])
    if our_dcf and pt.get("targetMean") and price:
        diff = our_dcf - pt["targetMean"]
        if abs(diff) > price * 0.05:
            if our_dcf < pt["targetMean"]:
                rows.append(["Our DCF is BELOW analyst targets", "", "", ""])
                rows.append(["Possible reasons:", "", "", ""])
                rows.append(["  1. We use fundamental growth (ROE×retention)", "", "", "not analyst forecasts"])
                rows.append(["  2. Our WACC may be higher (more conservative)", "", "", ""])
                rows.append(["  3. Analysts may factor in optionality/catalysts", "", "", "we don't"])
                rows.append(["  4. Our terminal growth may be lower", "", "", ""])
            else:
                rows.append(["Our DCF is ABOVE analyst targets", "", "", ""])
                rows.append(["Possible reasons:", "", "", ""])
                rows.append(["  1. Our fundamental growth may be more optimistic", "", "", ""])
                rows.append(["  2. Our WACC may be lower", "", "", ""])
                rows.append(["  3. Analysts may see risks we haven't captured", "", "", ""])
        else:
            rows.append(["Our DCF is roughly aligned with analyst targets", "", "", ""])

    # --- Growth comparison ---
    rows.append(["", "", "", ""])
    rows.append(["GROWTH: OUR ESTIMATE vs CONSENSUS", "Our", "Consensus", ""])
    if ctx.assumptions.growth_rates:
        our_g = ctx.assumptions.growth_rates[0]
        cons_g = ee.get("growth", {}).get("+1y")
        rows.append(["Year 1 Growth", _safe(our_g), _safe(cons_g), ""])
    rows.append(["Terminal Growth", _safe(ctx.assumptions.terminal_growth), "N/A", "Nominal GDP"])

    # Pad all rows to 6 columns
    n_cols = 6
    for r in rows:
        while len(r) < n_cols:
            r.append("")

    df = pd.DataFrame(rows, columns=["Item", "Value 1", "Value 2", "Notes", "Col5", "Col6"])
    df.to_excel(writer, sheet_name="Analyst Consensus", index=False)

    ws = _ws(writer, "Analyst Consensus")
    _style_header_row(ws, 1, n_cols)

    pct_rows = {"year 1 growth", "terminal growth", "accuracy"}
    in_top_analysts = False
    for row_idx in range(2, ws.max_row + 1):
        label = ws.cell(row=row_idx, column=1).value or ""
        label_lower = str(label).strip().lower()

        if _is_section_title(label):
            _style_section_title(ws, row_idx, n_cols)
            if "top analysts" in label_lower:
                in_top_analysts = True
            elif label_lower != "":
                in_top_analysts = False
            continue

        # Style top analysts sub-header row (Analyst | Firm | Accuracy | ...)
        if label_lower == "analyst":
            _style_header_row(ws, row_idx, n_cols)
            in_top_analysts = True
            continue

        # Format accuracy column (col 3) as percentage in top analysts block
        if in_top_analysts:
            acc_cell = ws.cell(row=row_idx, column=3)
            if isinstance(acc_cell.value, (int, float)) and abs(acc_cell.value) <= 1:
                acc_cell.number_format = _FMT_PCT
                acc_cell.alignment = _RIGHT
            tgt_cell = ws.cell(row=row_idx, column=4)
            if isinstance(tgt_cell.value, (int, float)):
                tgt_cell.number_format = _FMT_PRICE
                tgt_cell.alignment = _RIGHT

        val_cell = ws.cell(row=row_idx, column=2)
        if isinstance(val_cell.value, (int, float)):
            if label_lower in pct_rows and abs(val_cell.value) <= 3:
                val_cell.number_format = _FMT_PCT
            else:
                val_cell.number_format = _FMT_DEC
            val_cell.alignment = _RIGHT

    _autofit_columns(ws)
    _freeze_top_row(ws)


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

    rows.append(["MARKET DATA", "", ""])
    rows.append(["Price", _safe(stats.get("price")), "Yahoo Finance"])
    rows.append(["Market Cap", _safe(stats.get("market_cap")), "Yahoo Finance"])
    rows.append(["Shares Outstanding", _safe(stats.get("shares_outstanding")), "Yahoo Finance"])
    rows.append(["Beta (yfinance)", _safe(stats.get("beta")), "Yahoo Finance"])
    rows.append(["Book Value/Share", _safe(stats.get("book_value_per_share")), "Yahoo Finance"])
    rows.append(["Dividend/Share", _safe(stats.get("dividend_per_share")), "Yahoo Finance"])

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

    rows.append(["", "", ""])
    rows.append(["GROWTH INPUTS", "", ""])
    rows.append(["Terminal Growth", _safe(a.terminal_growth), "Nominal GDP growth"])
    if a.growth_rates:
        rows.append(["High Growth Rate", _safe(a.growth_rates[0]), "See Assumptions sheet"])

    rows.append(["", "", ""])
    rows.append(["FINANCIAL DATA", "", ""])
    if ctx.financials.income_statement is not None:
        rows.append(["Income Statement", f"{ctx.financials.income_statement.shape[0]} years", "Yahoo Finance"])
    if ctx.financials.balance_sheet is not None:
        rows.append(["Balance Sheet", f"{ctx.financials.balance_sheet.shape[0]} years", "Yahoo Finance"])
    if ctx.financials.cash_flow is not None:
        rows.append(["Cash Flow", f"{ctx.financials.cash_flow.shape[0]} years", "Yahoo Finance"])

    rows.append(["", "", ""])
    rows.append(["INDUSTRY BENCHMARKS", "", ""])
    rows.append(["Damodaran Industry", ctx.company.damodaran_industry or "N/A", "Fuzzy match"])
    rows.append(["Industry WACC", _safe(ctx.benchmarks.industry_wacc), f"Damodaran wacc ({ctx.company.region})"])

    pct_labels_ds = {"risk-free rate", "erp", "crp", "cost of equity", "cost of debt",
                     "wacc", "tax rate", "terminal growth", "industry wacc",
                     "beta (re-levered)", "industry unlevered beta"}

    df = pd.DataFrame(rows, columns=["Input", "Value", "Source"])
    df.to_excel(writer, sheet_name="Data Sources", index=False)

    ws = _ws(writer, "Data Sources")
    _style_header_row(ws, 1, 3)

    for row_idx in range(2, ws.max_row + 1):
        label = ws.cell(row=row_idx, column=1).value or ""

        if _is_section_title(label):
            _style_section_title(ws, row_idx, 3)
            continue

        val_cell = ws.cell(row=row_idx, column=2)
        if isinstance(val_cell.value, (int, float)):
            label_lower = str(label).lower()
            if label_lower in pct_labels_ds and abs(val_cell.value) <= 3:
                val_cell.number_format = _FMT_PCT
            elif label_lower in ("price", "book value/share", "dividend/share"):
                val_cell.number_format = _FMT_PRICE
            elif label_lower in ("market cap", "shares outstanding"):
                val_cell.number_format = _FMT_INT
            else:
                val_cell.number_format = _FMT_DEC
            val_cell.alignment = _RIGHT

    _autofit_columns(ws)
    _freeze_top_row(ws)


_IS_COL_ORDER: dict[str, list[str]] = {
    "Income Statement": [
        "Total Revenue", "Cost Of Revenue", "Gross Profit",
        "Operating Expense", "Selling General And Administration", "Research And Development",
        "Operating Income", "Interest Expense", "Other Income Expense",
        "Pretax Income", "Tax Provision", "Net Income",
        "EBITDA", "EBIT", "Basic EPS", "Diluted EPS",
    ],
    "Balance Sheet": [
        "Cash And Cash Equivalents", "Current Assets", "Total Assets",
        "Current Liabilities", "Long Term Debt", "Total Debt", "Total Liabilities",
        "Total Stockholders Equity", "Share Issued",
    ],
    "Cash Flow": [
        "Operating Cash Flow", "Capital Expenditure", "Free Cash Flow",
        "Depreciation And Amortization", "Stock Based Compensation",
        "Change In Working Capital", "Investing Cash Flow", "Financing Cash Flow",
    ],
}


def _reorder_financial_rows(df: pd.DataFrame, sheet_name: str) -> pd.DataFrame:
    """Reorder rows (line items) of a financial statement DataFrame into standard order.

    Rows whose index label matches a known canonical name are placed first in the
    prescribed order; any remaining rows are appended afterward.
    """
    canonical = _IS_COL_ORDER.get(sheet_name, [])
    if not canonical:
        return df

    # Build a case-insensitive lookup: lower(label) → original index label
    existing = {str(idx).lower(): idx for idx in df.index}

    ordered_idx: list = []
    seen: set = set()
    for name in canonical:
        key = name.lower()
        if key in existing:
            orig = existing[key]
            ordered_idx.append(orig)
            seen.add(orig)

    # Append any remaining rows not in the canonical list
    for idx in df.index:
        if idx not in seen:
            ordered_idx.append(idx)

    return df.loc[ordered_idx]


def _write_financials(writer: pd.ExcelWriter, ctx: ValuationContext) -> None:
    """Sheet 8: Raw financial statements — rows=line items, columns=fiscal years."""
    sheets = [
        ("income_statement", "Income Statement"),
        ("balance_sheet", "Balance Sheet"),
        ("cash_flow", "Cash Flow"),
    ]

    for attr, sheet_name in sheets:
        df_raw: pd.DataFrame | None = getattr(ctx.financials, attr, None)
        if df_raw is None:
            continue

        # Normalise orientation: rows = line items, columns = fiscal years
        # yfinance returns DataFrames where rows=dates, columns=items OR
        # rows=items, columns=dates. We want rows=items, columns=dates (years).
        # Heuristic: if the index looks like dates (Timestamp / string year)
        # and the columns look like item names (strings), we transpose.
        df = df_raw.copy()

        index_is_dates = _looks_like_dates(df.index)
        cols_are_dates = _looks_like_dates(df.columns)

        if index_is_dates and not cols_are_dates:
            # rows=dates, cols=items → transpose to rows=items, cols=dates
            df = df.T
        elif cols_are_dates:
            # Already rows=items, cols=dates — nothing to do
            pass
        # else: ambiguous; leave as-is

        # Sort columns (fiscal years) descending (most recent first)
        try:
            df = df.sort_index(axis=1, ascending=False)
        except TypeError:
            pass  # Mixed types in columns; skip sort

        # Reorder rows into standard reporting order
        df = _reorder_financial_rows(df, sheet_name)

        # Write to Excel
        df.to_excel(writer, sheet_name=sheet_name)

        ws = _ws(writer, sheet_name)
        n_cols = df.shape[1] + 1  # +1 for index column

        # Header row styling
        _style_header_row(ws, 1, n_cols)

        # Format values
        for row_idx in range(2, ws.max_row + 1):
            label_cell = ws.cell(row=row_idx, column=1)
            label = label_cell.value or ""
            label_cell.font = _NORMAL_FONT
            label_cell.alignment = _LEFT

            for col_idx in range(2, n_cols + 1):
                cell = ws.cell(row=row_idx, column=col_idx)
                if isinstance(cell.value, (int, float)):
                    label_lower = str(label).lower()
                    # Margin/ratio/rate rows → percentage format
                    if any(kw in label_lower for kw in ("margin", "rate", "ratio", "yield", "growth")):
                        if abs(cell.value) <= 5:
                            cell.number_format = _FMT_PCT
                        else:
                            cell.number_format = _FMT_INT
                    else:
                        cell.number_format = _FMT_INT
                    cell.alignment = _RIGHT

                    # Negative numbers in red
                    if cell.value < 0:
                        cell.font = Font(name="Calibri", size=10, color=_RED)

        # Column widths: label column wider, data columns narrower
        ws.column_dimensions["A"].width = 35
        for col_idx in range(2, n_cols + 1):
            ws.column_dimensions[get_column_letter(col_idx)].width = 15

        _freeze_top_row(ws)


# ---------------------------------------------------------------------------
# Internal helpers for financials orientation detection
# ---------------------------------------------------------------------------

def _looks_like_dates(index) -> bool:
    """Return True if the index/columns appear to contain date-like values."""
    if len(index) == 0:
        return False
    sample = index[0]
    # pd.Timestamp
    if isinstance(sample, pd.Timestamp):
        return True
    # datetime.date / datetime.datetime
    try:
        from datetime import date as _date, datetime as _datetime
        if isinstance(sample, (_date, _datetime)):
            return True
    except ImportError:
        pass
    # String that looks like a year or ISO date
    if isinstance(sample, str):
        s = sample.strip()
        if len(s) == 4 and s.isdigit():
            return True
        if len(s) >= 7 and s[:4].isdigit() and s[4] in ("-", "/"):
            return True
    return False
