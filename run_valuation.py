#!/usr/bin/env python3
"""Full valuation pipeline — run all 12 steps, produce markdown + Excel output.

Usage:
    python3 run_valuation.py TATAELXSI.NS
    python3 run_valuation.py AAPL --growth 0.12 --terminal 0.025
    python3 run_valuation.py HDFCBANK.NS --classification financial
"""

from __future__ import annotations

import argparse
import math
import pathlib
import sys
from datetime import date

# ---- All imports ----
from valuation.data.api_client import fetch_financials, fetch_analyst_data
from valuation.data.normalizer import normalize
from valuation.data.damodaran_loader import DamodaranLoader
from valuation.agents.industry_mapper import match_industry, load_industry_benchmarks
from valuation.agents.classifier import classify_company
from valuation.agents.risk_assessor import (
    compute_cost_of_equity, compute_wacc, relever_beta,
    get_synthetic_rating, compute_cost_of_debt,
)
from valuation.agents.growth_estimator import estimate_all_growth_rates
from valuation.engines.dcf import (
    fcff_valuation, ddm_valuation, gordon_growth_value,
    interpolate_params, sensitivity_table, two_way_sensitivity_table,
)
from valuation.engines.relative import relative_valuation
from valuation.engines.excess_returns import excess_return_valuation
from valuation.agents.cross_validator import cross_validate
from valuation.scoring.confidence import score_all
from valuation.reports.generator import generate_report, save_report
from valuation.reports.excel_writer import generate_excel
from valuation.validation.pre_engine import validate_for_dcf


def find_damodaran_dir() -> pathlib.Path:
    """Find Damodaran data directory — in-repo or sibling."""
    project_root = pathlib.Path(__file__).parent
    in_repo = project_root / "data" / "damodaran"
    sibling = project_root.parent / "2. Damodaran_Data"
    if in_repo.exists():
        return in_repo
    if sibling.exists():
        return sibling
    raise FileNotFoundError("Damodaran data not found. Run download_damodaran.sh or check data/damodaran/")


def fetch_ibes_consensus(company_name: str, currency: str = "INR") -> dict | None:
    """Try to fetch I/B/E/S analyst consensus. Returns None if WRDS unavailable."""
    try:
        from valuation.data.wrds_client import WRDSClient
        w = WRDSClient()
        results = w.search_ibes_ticker(company_name, country_code=currency)
        if results is not None and len(results) > 0:
            ticker = results.iloc[0]["ticker"]
            estimates = w.fetch_ibes_estimates(ticker)
            w.close()
            return {"ticker": ticker, "estimates": estimates, "search_results": results}
        w.close()
    except Exception:
        pass
    return None


def run(ticker: str, growth_override: float | None = None,
        terminal_override: float | None = None,
        classification_override: str | None = None) -> None:
    """Run full valuation pipeline."""

    print(f"\n{'='*70}")
    print(f"  VALUATION: {ticker}")
    print(f"  Date: {date.today().isoformat()}")
    print(f"{'='*70}")

    # ================================================================
    # STEP 1: Fetch Company Data
    # ================================================================
    print(f"\n--- Step 1: Fetch Company Data ---")
    data = fetch_financials(ticker)
    if data is None:
        print(f"ERROR: Failed to fetch data for {ticker}")
        sys.exit(1)

    print(f"  Company: {data.name}")
    print(f"  Sector: {data.sector} | Industry: {data.industry}")
    print(f"  Country: {data.country}")
    print(f"  Price: {data.price:,.2f} | Market Cap: {data.market_cap:,.0f}")
    print(f"  Shares: {data.shares_outstanding:,.0f}")

    # ================================================================
    # STEP 2: Normalize
    # ================================================================
    print(f"\n--- Step 2: Normalize ---")
    ctx = normalize(data)
    if ctx is None:
        print("ERROR: Normalization failed")
        sys.exit(1)
    print(f"  Region: {ctx.company.region}")
    ctx.financials.key_stats["shares_outstanding"] = data.shares_outstanding

    # ================================================================
    # STEP 3: Map to Damodaran Industry
    # ================================================================
    print(f"\n--- Step 3: Industry Mapping ---")
    loader = DamodaranLoader(find_damodaran_dir())
    match = match_industry(
        sector=ctx.company.sector or "",
        industry=data.industry or "",
        description=data.name or "",
        loader=loader,
        region=ctx.company.region,
    )
    if match and match.score >= 70:
        ctx.company.damodaran_industry = match.matched_name
        bm = load_industry_benchmarks(match.matched_name, loader, ctx.company.region)
        if bm:
            ctx.benchmarks.industry_beta = bm["beta"]
            ctx.benchmarks.industry_unlevered_beta = bm["unlevered_beta"]
            ctx.benchmarks.industry_de_ratio = bm["de_ratio"]
            ctx.benchmarks.industry_wacc = bm["wacc"]
            ctx.benchmarks.industry_multiples = bm["multiples"]
            ctx.benchmarks.industry_margins = bm["margins"]
            ctx.benchmarks.industry_growth = bm["growth"]
        print(f"  Matched: {match.matched_name} (score {match.score})")
        print(f"  Industry Beta: {bm['beta']:.2f} | WACC: {bm['wacc']:.2%}")
    else:
        print(f"  WARNING: No strong industry match (best: {match.matched_name if match else 'none'}, score {match.score if match else 0})")
        print(f"  Candidates: {match.candidates[:3] if match else []}")

    # ================================================================
    # STEP 4: Classify Company
    # ================================================================
    print(f"\n--- Step 4: Classify Company ---")
    cl = classify_company(ctx)
    if classification_override:
        ctx.company.classification = classification_override
        print(f"  Override: {classification_override} (original: {cl.classification})")
    else:
        ctx.company.classification = cl.classification
    print(f"  Classification: {ctx.company.classification} ({cl.confidence:.0%})")
    print(f"  Reasoning: {cl.reasoning}")
    print(f"  Model: {cl.suggested_model}")

    # ================================================================
    # STEP 5: Risk Assessment
    # ================================================================
    print(f"\n--- Step 5: Risk Assessment ---")
    inc = ctx.financials.income_statement
    bs = ctx.financials.balance_sheet
    cf = ctx.financials.cash_flow
    latest_inc = inc.iloc[0]
    latest_bs = bs.iloc[0]

    total_debt = float(latest_bs.get('Total Debt', 0) or 0)
    market_cap = data.market_cap
    company_de = total_debt / market_cap if market_cap > 0 else 0

    tax_prov = float(latest_inc.get('Tax Provision', 0) or 0)
    pretax = float(latest_inc.get('Pretax Income', 0) or 0)
    tax_rate = tax_prov / pretax if pretax > 0 else 0.25

    ebit = float(latest_inc.get('Operating Income', 0) or 0)
    interest = float(latest_inc.get('Interest Expense', 0) or 0)
    icr = ebit / interest if interest > 0 else 50

    is_india = ctx.company.region == "India"
    is_japan = ctx.company.region == "Japan"
    rf = 0.07 if is_india else (0.01 if is_japan else 0.0395)
    erp = 0.0446
    crp = 0.0  # embedded in local Rf for India
    lam = 0.5 if is_india else 1.0

    if ctx.benchmarks.industry_unlevered_beta:
        beta = relever_beta(ctx.benchmarks.industry_unlevered_beta, company_de, tax_rate)
    else:
        beta = data.beta or 1.0

    ke = compute_cost_of_equity(rf, beta, erp, crp, lam)
    rating, spread = get_synthetic_rating(icr, "large")
    cod = rf + spread
    eq_w = market_cap / (market_cap + total_debt) if (market_cap + total_debt) > 0 else 1.0
    dbt_w = 1 - eq_w
    wacc = compute_wacc(ke, cod, tax_rate, eq_w, dbt_w)

    ctx.assumptions.beta = beta
    ctx.assumptions.risk_free_rate = rf
    ctx.assumptions.erp = erp
    ctx.assumptions.country_risk_premium = crp
    ctx.assumptions.cost_of_equity = ke
    ctx.assumptions.cost_of_debt = cod
    ctx.assumptions.wacc = wacc
    ctx.assumptions.tax_rate = tax_rate

    print(f"  Rf: {rf:.2%} | ERP: {erp:.2%} | CRP: {crp:.2%}")
    print(f"  Beta: {beta:.3f} (industry bottom-up, re-levered)")
    print(f"  Ke: {ke:.2%} | Kd: {cod:.2%} ({rating})")
    print(f"  WACC: {wacc:.2%} | D/E: {company_de:.4f} | Tax: {tax_rate:.1%}")

    # ================================================================
    # STEP 6: Growth Estimation
    # ================================================================
    print(f"\n--- Step 6: Growth Estimation ---")
    growth_dict = estimate_all_growth_rates(ctx)
    for name, est in growth_dict.items():
        if est:
            print(f"  {name}: {est.value:.2%} — {est.reasoning}")
        else:
            print(f"  {name}: N/A")

    # Compute actual company metrics
    net_income = float(latest_inc.get('Net Income', 0) or 0)
    revenue = float(latest_inc.get('Total Revenue', 0) or 0)
    equity_bv = data.book_value_per_share * data.shares_outstanding if data.book_value_per_share else 0
    roe = net_income / equity_bv if equity_bv > 0 else 0
    dividends = data.dividend_per_share * data.shares_outstanding if data.dividend_per_share else 0
    retention = 1 - (dividends / net_income) if net_income > 0 else 0.5
    fundamental_growth = roe * retention
    print(f"  ROE: {roe:.1%} | Retention: {retention:.1%} | Fundamental (ROE×ret): {fundamental_growth:.1%}")

    if ctx.benchmarks.industry_growth:
        print(f"  Industry growth benchmark: {ctx.benchmarks.industry_growth}")

    # Determine growth
    n_years = 10
    is_india = ctx.company.region == "India"
    default_terminal = 0.05 if is_india else 0.025
    terminal_growth = terminal_override if terminal_override is not None else default_terminal

    if growth_override is not None:
        high_growth = growth_override
    else:
        rev_g = growth_dict.get("historical_revenue")
        if rev_g and rev_g.value > 0:
            high_growth = min(rev_g.value, 0.25)
        elif fundamental_growth > 0:
            high_growth = min(fundamental_growth, 0.25)
        else:
            high_growth = 0.08

    growth_rates = interpolate_params(high_growth, terminal_growth, n_years, gradual=True)
    ctx.assumptions.growth_rates = growth_rates
    ctx.assumptions.terminal_growth = terminal_growth
    ctx.assumptions.projection_years = n_years

    print(f"\n  → Using: {high_growth:.2%} high-growth → {terminal_growth:.2%} terminal over {n_years} years")

    # ================================================================
    # STEP 7: Validate Before Engines
    # ================================================================
    print(f"\n--- Step 7: Pre-Engine Validation ---")
    model = "ddm" if ctx.company.classification == "financial" else "dcf_fcff"
    val = validate_for_dcf(ctx, model=model)
    print(f"  Can proceed: {val.can_proceed}")
    for w in val.warnings:
        print(f"  ⚠ {w}")
    if not val.can_proceed:
        for m in val.critical_missing:
            print(f"  MISSING: {m.name} — {m.suggestion}")
        print("ERROR: Cannot proceed — fix missing inputs")
        sys.exit(1)

    # ================================================================
    # STEP 8: Run Valuation Engines
    # ================================================================
    print(f"\n--- Step 8: Valuation Engines ---")
    ebit_at = ebit * (1 - tax_rate)
    ebitda = float(latest_inc.get('EBITDA', 0) or 0)
    cash = float(latest_bs.get('Cash And Cash Equivalents', 0) or 0)

    capex = abs(float(cf.iloc[0].get('Capital Expenditure', 0) or 0)) if cf is not None and len(cf) > 0 else 0
    depr = float(cf.iloc[0].get('Depreciation And Amortization', 0) or 0) if cf is not None and len(cf) > 0 else 0

    if ctx.company.classification == "financial":
        # DDM for financial firms
        eps = net_income / data.shares_outstanding if data.shares_outstanding > 0 else 0
        payout_rates = interpolate_params(
            dividends / net_income if net_income > 0 else 0.30,
            0.70, n_years, gradual=True
        )
        ke_rates = [ke] * n_years
        stable_roe = min(roe, 0.15) if roe > 0 else 0.12

        ddm_result = ddm_valuation(
            current_eps=eps, growth_rates=growth_rates,
            payout_rates=payout_rates, cost_of_equities=ke_rates,
            stable_growth=terminal_growth, stable_roe=stable_roe, stable_ke=ke,
        )
        ctx.outputs.dcf_fcfe = ddm_result
        print(f"  [DDM] Value/Share: {ddm_result['value_per_share']:,.2f}")

        # Also run excess returns
        roes = [roe] * n_years
        coes = [ke] * n_years
        er_result = excess_return_valuation(
            current_book_equity_per_share=data.book_value_per_share or 0,
            current_eps=eps,
            eps_growth_rates=growth_rates,
            payout_rates=payout_rates,
            roes=roes, coes=coes,
            stable_growth=terminal_growth,
            stable_roe=stable_roe, stable_coe=ke,
        )
        ctx.outputs.excess_returns = er_result
        print(f"  [Excess Returns] Value/Share: {er_result['value_per_share']:,.2f}")
    else:
        # FCFF for non-financial
        actual_reinv = (capex - depr) / ebit_at if ebit_at > 0 else 0.3
        actual_reinv = max(actual_reinv, -0.15)
        stable_roc = 0.15
        reinv_stable = terminal_growth / stable_roc
        reinv_rates = interpolate_params(actual_reinv, reinv_stable, n_years, gradual=True)

        fcff_result = fcff_valuation(
            current_ebit_after_tax=ebit_at,
            growth_rates=growth_rates, reinvestment_rates=reinv_rates,
            waccs=[wacc] * n_years,
            stable_growth=terminal_growth, stable_roc=stable_roc, stable_wacc=wacc,
            cash=cash, debt=total_debt,
            shares_outstanding=data.shares_outstanding,
        )
        ctx.outputs.dcf_fcff = fcff_result
        print(f"  [FCFF DCF] Value/Share: {fcff_result['equity_value_per_share']:,.2f}")
        print(f"    EV: {fcff_result['enterprise_value']:,.0f} | PV HG: {fcff_result['pv_high_growth']:,.0f} | PV TV: {fcff_result['pv_terminal']:,.0f}")

    # Relative valuation (always run)
    eps = net_income / data.shares_outstanding if data.shares_outstanding > 0 else 0
    rev_ps = revenue / data.shares_outstanding if data.shares_outstanding > 0 else 0

    rel = relative_valuation(
        eps=eps, ebitda=ebitda, book_value_per_share=data.book_value_per_share,
        revenue_per_share=rev_ps, industry_multiples=ctx.benchmarks.industry_multiples,
        debt=total_debt, cash=cash, shares_outstanding=data.shares_outstanding,
        market_price=data.price,
    )
    ctx.outputs.relative = rel.to_dict()
    print(f"\n  [Relative Valuation]")
    if rel.pe_value: print(f"    PE implied: {rel.pe_value:,.2f}")
    if rel.ev_ebitda_value: print(f"    EV/EBITDA implied: {rel.ev_ebitda_value:,.2f}")
    if rel.pbv_value: print(f"    PBV implied: {rel.pbv_value:,.2f}")
    if rel.ps_value: print(f"    PS implied: {rel.ps_value:,.2f}")
    if rel.composite_value: print(f"    Composite (median): {rel.composite_value:,.2f}")
    if rel.discount_to_composite is not None:
        print(f"    vs Market: {rel.discount_to_composite:+.1%}")

    # ================================================================
    # STEP 9: Sensitivity Analysis
    # ================================================================
    print(f"\n--- Step 9: Sensitivity Analysis ---")
    if ctx.outputs.dcf_fcff:
        base_params = dict(
            current_ebit_after_tax=ebit_at,
            growth_rates=growth_rates, reinvestment_rates=reinv_rates,
            waccs=[wacc] * n_years,
            stable_growth=terminal_growth, stable_roc=stable_roc, stable_wacc=wacc,
            cash=cash, debt=total_debt,
            shares_outstanding=data.shares_outstanding,
        )
        extract_fn = lambda **kw: fcff_valuation(**kw)["equity_value_per_share"]

        # One-way: WACC
        wacc_values = [wacc - 0.02, wacc - 0.01, wacc, wacc + 0.01, wacc + 0.02]
        wacc_sens = {}
        for w_val in wacc_values:
            try:
                p = {**base_params, "waccs": [w_val] * n_years, "stable_wacc": w_val}
                wacc_sens[round(w_val, 4)] = extract_fn(**p)
            except (ValueError, ZeroDivisionError):
                wacc_sens[round(w_val, 4)] = float("nan")

        # Two-way: WACC vs terminal growth
        tg_values = [terminal_growth - 0.02, terminal_growth - 0.01, terminal_growth, terminal_growth + 0.01]
        two_way = {}
        for w_val in wacc_values:
            two_way[round(w_val, 4)] = {}
            for tg_val in tg_values:
                try:
                    p = {**base_params, "waccs": [w_val] * n_years, "stable_wacc": w_val, "stable_growth": tg_val}
                    two_way[round(w_val, 4)][round(tg_val, 4)] = extract_fn(**p)
                except (ValueError, ZeroDivisionError):
                    two_way[round(w_val, 4)][round(tg_val, 4)] = float("nan")

        ctx.outputs.sensitivity = {
            "wacc_sensitivity": wacc_sens,
            "wacc_vs_terminal_growth": two_way,
        }

        print(f"  WACC Sensitivity:")
        for w_val, v in wacc_sens.items():
            marker = " ◀ base" if abs(w_val - wacc) < 0.001 else ""
            v_str = f"{v:,.0f}" if not math.isnan(v) else "N/A"
            print(f"    WACC {w_val:.2%} → {v_str}{marker}")

        sens_values = [v for v in wacc_sens.values() if not math.isnan(v)]
        if sens_values:
            print(f"  Range: {min(sens_values):,.0f} to {max(sens_values):,.0f}")

    # ================================================================
    # STEP 10: Analyst Consensus (comparison only)
    # ================================================================
    print(f"\n--- Step 10: Analyst Consensus (comparison only) ---")
    currency_map = {"India": "INR", "US": "USD", "Japan": "JPY", "China": "CNY"}
    currency = currency_map.get(ctx.company.region, "USD")
    ibes_data = fetch_ibes_consensus(data.name or ticker, currency)
    if ibes_data and ibes_data.get("estimates") is not None:
        est = ibes_data["estimates"]
        print(f"  I/B/E/S ticker: {ibes_data['ticker']}")
        print(f"  Latest estimates ({len(est)} records):")
        for _, row in est.head(4).iterrows():
            print(f"    {row.get('statpers','')}: Mean EPS={row.get('meanest','N/A')}, Analysts={row.get('numest','N/A')}")
        print(f"  (Shown for COMPARISON — NOT used as DCF input)")
        ctx.financials.key_stats["ibes_data"] = ibes_data
    else:
        print(f"  No I/B/E/S data available (WRDS may not be configured)")

    # Yahoo Finance analyst price targets & recommendations
    print(f"  Fetching Yahoo Finance analyst data for {ticker}...")
    analyst_data = fetch_analyst_data(ticker)
    if analyst_data:
        pt = analyst_data.get("price_targets")
        if pt:
            print(f"  Analyst Mean Target: {pt.get('targetMean', 'N/A')} | # Analysts: {pt.get('numberOfAnalysts', 'N/A')}")
        else:
            print(f"  No price target data from Yahoo Finance")
        ctx.financials.key_stats["analyst_data"] = analyst_data
    else:
        print(f"  No analyst data available from Yahoo Finance")
    print(f"  (Shown for COMPARISON — NOT used as DCF input)")

    # ================================================================
    # STEP 11: Cross-Validation
    # ================================================================
    print(f"\n--- Step 11: Cross-Validation ---")
    outputs = {}
    if ctx.outputs.dcf_fcff: outputs["dcf_fcff"] = ctx.outputs.dcf_fcff
    if ctx.outputs.dcf_fcfe: outputs["dcf_fcfe"] = ctx.outputs.dcf_fcfe
    if ctx.outputs.relative: outputs["relative"] = ctx.outputs.relative
    if ctx.outputs.excess_returns: outputs["excess_returns"] = ctx.outputs.excess_returns

    cv = cross_validate(outputs, data.price)
    if cv.mean_value:
        print(f"  Models: {cv.num_models} | Mean: {cv.mean_value:,.0f} | Median: {cv.median_value:,.0f}")
        print(f"  Range: {cv.min_value:,.0f} — {cv.max_value:,.0f}")
        if cv.max_divergence_pct:
            print(f"  Max Divergence: {cv.max_divergence_pct:.1%}")
    for f in cv.flags:
        print(f"  ⚠ {f}")

    # ================================================================
    # STEP 12: Confidence Scoring
    # ================================================================
    print(f"\n--- Step 12: Confidence Scoring ---")
    sens_base = None
    sens_min_val = None
    sens_max_val = None
    if ctx.outputs.sensitivity and "wacc_sensitivity" in ctx.outputs.sensitivity:
        sv = [v for v in ctx.outputs.sensitivity["wacc_sensitivity"].values() if not math.isnan(v)]
        if sv:
            if ctx.outputs.dcf_fcff:
                sens_base = ctx.outputs.dcf_fcff.get("equity_value_per_share")
            sens_min_val = min(sv)
            sens_max_val = max(sv)

    score_all(
        ctx,
        industry_match_score=match.score if match else 0,
        sensitivity_base=sens_base,
        sensitivity_min=sens_min_val,
        sensitivity_max=sens_max_val,
    )
    if ctx.confidence.composite:
        label = "HIGH" if ctx.confidence.composite >= 0.75 else "MEDIUM" if ctx.confidence.composite >= 0.5 else "LOW"
        print(f"  Composite: {ctx.confidence.composite:.0%} ({label})")
        print(f"  Data Completeness: {ctx.confidence.data_completeness:.0%}" if ctx.confidence.data_completeness else "")
        print(f"  Model Agreement: {ctx.confidence.model_agreement:.0%}" if ctx.confidence.model_agreement else "")
        print(f"  Assumption Sensitivity: {ctx.confidence.assumption_sensitivity:.0%}" if ctx.confidence.assumption_sensitivity else "")
    for f in ctx.confidence.flags:
        print(f"  ⚠ {f}")

    # ================================================================
    # STEP 13: Generate Reports (Markdown + Excel)
    # ================================================================
    print(f"\n--- Step 13: Generate Reports ---")
    md_path = save_report(ctx)
    print(f"  Markdown: {md_path}")

    excel_path = generate_excel(ctx, ibes_data=ibes_data)
    print(f"  Excel: {excel_path}")

    # ================================================================
    # FINAL SUMMARY
    # ================================================================
    print(f"\n{'='*70}")
    print(f"  FINAL RESULTS: {data.name} ({ticker})")
    print(f"{'='*70}")

    all_values = {}
    if ctx.outputs.dcf_fcff:
        all_values["DCF (FCFF)"] = ctx.outputs.dcf_fcff["equity_value_per_share"]
    if ctx.outputs.dcf_fcfe:
        all_values["DDM"] = ctx.outputs.dcf_fcfe["value_per_share"]
    if ctx.outputs.excess_returns:
        all_values["Excess Returns"] = ctx.outputs.excess_returns["value_per_share"]
    if rel.pe_value: all_values["PE implied"] = rel.pe_value
    if rel.ev_ebitda_value: all_values["EV/EBITDA implied"] = rel.ev_ebitda_value
    if rel.pbv_value: all_values["PBV implied"] = rel.pbv_value
    if rel.ps_value: all_values["PS implied"] = rel.ps_value
    if rel.composite_value: all_values["Relative (composite)"] = rel.composite_value

    for model_name, val in all_values.items():
        upside = (val - data.price) / data.price * 100 if data.price > 0 else 0
        print(f"  {model_name:25s}  {val:>12,.2f}  ({upside:+.1f}%)")

    print(f"\n  Market Price:               {data.price:>12,.2f}")
    values = list(all_values.values())
    if values:
        mean_val = sum(values) / len(values)
        upside = (mean_val - data.price) / data.price * 100 if data.price > 0 else 0
        print(f"  Mean Intrinsic:             {mean_val:>12,.2f}  ({upside:+.1f}%)")
        print(f"  Range:                      {min(values):>12,.2f} — {max(values):,.2f}")

    if ctx.confidence.composite:
        print(f"  Confidence:                 {ctx.confidence.composite:.0%}")

    print(f"\n  Reports saved:")
    print(f"    {md_path}")
    print(f"    {excel_path}")
    print(f"{'='*70}\n")


def main():
    parser = argparse.ArgumentParser(description="Value a public company")
    parser.add_argument("ticker", help="Stock ticker (e.g., AAPL, TCS.NS)")
    parser.add_argument("--growth", type=float, default=None, help="Override high-growth rate (e.g., 0.12)")
    parser.add_argument("--terminal", type=float, default=None, help="Override terminal growth (e.g., 0.025)")
    parser.add_argument("--classification", type=str, default=None,
                        choices=["mature", "growth", "young", "distressed", "cyclical", "financial"],
                        help="Override company classification")
    args = parser.parse_args()
    run(args.ticker, args.growth, args.terminal, args.classification)


if __name__ == "__main__":
    main()
