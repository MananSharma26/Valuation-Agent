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
    fcff_valuation, fcff_valuation_v2, ddm_valuation, gordon_growth_value,
    interpolate_params, sensitivity_table, two_way_sensitivity_table,
)
from valuation.engines.schedules import (
    wacc_schedule, tax_schedule, margin_convergence_schedule,
    terminal_wacc_default,
)
from valuation.engines.adjustments import capitalize_rd, get_amortization_period
from valuation.engines.relative import relative_valuation
from valuation.engines.excess_returns import excess_return_valuation
from valuation.agents.cross_validator import cross_validate
from valuation.scoring.confidence import score_all
from valuation.reports.generator import generate_report, save_report
from valuation.reports.excel_writer import generate_excel
from valuation.validation.pre_engine import validate_for_dcf
from valuation.validation.sourced import from_yahoo, from_damodaran, from_user, computed, missing


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


def fetch_ibes_consensus(company_name: str, ticker: str = "", currency: str = "INR") -> dict | None:
    """Try to fetch I/B/E/S analyst consensus. Returns None if WRDS unavailable.

    Tries multiple name variants since I/B/E/S uses abbreviated names.
    """
    try:
        from valuation.data.wrds_client import WRDSClient
        w = WRDSClient()

        # Try multiple search queries — I/B/E/S uses short names
        queries = []
        # Ticker symbol (without exchange suffix)
        base_ticker = ticker.split(".")[0] if ticker else ""
        if base_ticker:
            queries.append(base_ticker)
        # First two words of company name
        words = company_name.split()
        if len(words) >= 2:
            queries.append(f"{words[0]} {words[1]}")
        if len(words) >= 1:
            queries.append(words[0])
        # Full name as fallback
        queries.append(company_name)

        region = "us" if currency == "USD" else "int"
        for q in queries:
            results = w.search_ibes_ticker(q, country_code=currency)
            if results is not None and len(results) > 0:
                ibes_ticker = results.iloc[0]["ticker"]
                estimates = w.fetch_ibes_estimates(ibes_ticker, region=region)
                top_analysts = w.fetch_top_analysts(ibes_ticker, region=region, top_n=10)
                w.close()
                return {
                    "ticker": ibes_ticker,
                    "estimates": estimates,
                    "top_analysts": top_analysts,
                    "search_results": results,
                }

        w.close()
    except Exception as e:
        print(f"  WRDS error: {e}")
    return None


def run(ticker: str, growth_override: float | None = None,
        terminal_override: float | None = None,
        classification_override: str | None = None) -> None:
    """Run full valuation pipeline."""

    print(f"\n{'='*70}")
    print(f"  VALUATION: {ticker}")
    print(f"  Date: {date.today().isoformat()}")
    print(f"{'='*70}")

    # Source tracking dict — populated throughout the pipeline
    sourced_inputs: dict = {}

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

    # Tag Yahoo Finance inputs
    sourced_inputs["price"] = from_yahoo(data.price)
    sourced_inputs["market_cap"] = from_yahoo(data.market_cap)
    sourced_inputs["shares"] = from_yahoo(data.shares_outstanding)
    sourced_inputs["beta_yfinance"] = from_yahoo(data.beta)

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
        sourced_inputs["industry_beta"] = from_damodaran(bm["beta"], "betas.xls")
        sourced_inputs["industry_wacc"] = from_damodaran(bm["wacc"], "wacc.xls")
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
        ctx.assumptions.overrides["classification"] = {
            "original": cl.classification,
            "new": classification_override,
            "reason": "CLI override",
        }
        print(f"  Override: {classification_override} (original: {cl.classification})")
    else:
        ctx.company.classification = cl.classification
    print(f"  Classification: {ctx.company.classification} ({cl.confidence:.0%})")
    print(f"  Reasoning: {cl.reasoning}")
    print(f"  Model: {cl.suggested_model}")

    # ================================================================
    # STEP 4.5: Gather Context (news, profile) — for LLM narrative
    # ================================================================
    print(f"\n--- Step 4.5: Gather Context ---")
    from valuation.data.news_fetcher import build_context_summary, fetch_company_news, fetch_company_profile

    company_profile = fetch_company_profile(ticker)
    company_news = fetch_company_news(ticker)
    context_summary = build_context_summary(ticker, data.name or ticker)

    # Store for report
    ctx.financials.key_stats["company_profile"] = company_profile
    ctx.financials.key_stats["company_news"] = company_news
    ctx.financials.key_stats["context_summary"] = context_summary

    # SEC filings (US companies only)
    try:
        from valuation.data.sec_fetcher import fetch_sec_filings
        sec_data = fetch_sec_filings(ticker.split(".")[0], country=data.country or "")
        if sec_data:
            ctx.financials.key_stats["sec_filings"] = sec_data
            print(f"  SEC 10-K: filed {sec_data.get('filing_date', 'N/A')}")
            if sec_data.get("risk_factors"):
                print(f"  Risk Factors: {len(sec_data['risk_factors']):,} chars")
            if sec_data.get("mda"):
                print(f"  MD&A: {len(sec_data['mda']):,} chars")
        else:
            print(f"  SEC filings: N/A (non-US or not found)")
    except Exception as e:
        print(f"  SEC filings error: {e}")

    # Macro context: Treasury yields, VIX, GDP forecast
    try:
        from valuation.data.news_fetcher import fetch_macro_context, fetch_gdp_forecast
        macro = fetch_macro_context()
        ctx.financials.key_stats["macro_context"] = macro
        if macro.get("commentary"):
            print(f"  Macro: {macro['commentary']}")

        country_name = data.country or "United States"
        gdp = fetch_gdp_forecast(country_name)
        if gdp.get("gdp_growth") is not None:
            macro["gdp_growth"] = gdp["gdp_growth"]
            print(f"  GDP growth ({gdp['country_code']}): {gdp['gdp_growth']:.2%}")
        ctx.financials.key_stats["macro_context"] = macro
    except Exception as e:
        print(f"  Macro context error: {e}")

    # Peer comparison (WRDS + Yahoo)
    try:
        from valuation.data.peer_analysis import fetch_peer_comparison
        sic = data.sic_code or ""
        if sic:
            profile_metrics = {
                "pe": (company_profile.get("trailing_pe")
                       if company_profile else None),
                "profit_margin": (company_profile.get("profit_margins")
                                  if company_profile else None),
                "revenue_growth": (company_profile.get("revenue_growth")
                                   if company_profile else None),
                "beta": data.beta,
            }
            peer_comp = fetch_peer_comparison(
                sic_code=sic,
                company_name=data.name or "",
                company_metrics=profile_metrics,
                region=ctx.company.region,
            )
            if peer_comp:
                ctx.financials.key_stats["peer_comparison"] = peer_comp
                print(f"  Peers: {peer_comp.get('num_peers_wrds', 0)} from WRDS, "
                      f"{peer_comp.get('num_peers_enriched', 0)} enriched via Yahoo")
            else:
                print(f"  Peer comparison: no peers found")
        else:
            print(f"  Peer comparison: no SIC code available")
    except Exception as e:
        print(f"  Peer comparison error: {e}")

    if company_profile.get("description"):
        print(f"  Profile: {company_profile['description'][:150]}...")
    if company_profile.get("revenue_growth"):
        print(f"  Revenue Growth (YoY): {company_profile['revenue_growth']:.1%}")
    if company_profile.get("earnings_growth"):
        print(f"  Earnings Growth (YoY): {company_profile['earnings_growth']:.1%}")
    if company_news:
        print(f"  Recent news: {len(company_news)} articles")
        for n in company_news[:3]:
            print(f"    - {n['title'][:80]}")

    # Earnings call transcript (from WRDS Capital IQ)
    earnings_transcript = None
    try:
        from valuation.data.wrds_client import WRDSClient
        w = WRDSClient()
        # Try multiple name variants
        for name_query in [data.name, ticker.split(".")[0]]:
            if name_query:
                earnings_transcript = w.fetch_earnings_transcript(name_query)
                if earnings_transcript:
                    break
        w.close()
    except Exception as e:
        print(f"  Transcript error: {e}")

    if earnings_transcript:
        ctx.financials.key_stats["earnings_transcript"] = earnings_transcript
        print(f"  Earnings call: {earnings_transcript['headline']}")
        print(f"  Date: {earnings_transcript['date']}")
        print(f"  Length: {len(earnings_transcript['transcript_text']):,} chars")
    else:
        print(f"  No earnings transcript available")

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
    macro = ctx.financials.key_stats.get("macro_context") or {}
    live_rf = macro.get("us_10yr_yield")

    # --- Risk-free rate: Live Treasury → Damodaran data → hardcoded fallback ---
    # Read Damodaran's latest T-Bond rate and implied ERP from histimpl.xls
    damodaran_rf = None
    damodaran_erp = None
    try:
        df_impl = loader.load("histimpl", "US")
        tbond_cols = [c for c in df_impl.columns if "T.Bond Rate" in c]
        if tbond_cols:
            damodaran_rf = float(df_impl[tbond_cols[0]].dropna().iloc[-1])
        erp_cols = [c for c in df_impl.columns if "risk adjusted" in c.lower() and "erp" in c.lower()]
        if not erp_cols:
            erp_cols = [c for c in df_impl.columns if "Implied ERP (FCFE)" in c]
        if erp_cols:
            damodaran_erp = float(df_impl[erp_cols[0]].dropna().iloc[-1])
    except Exception:
        pass

    # Country risk premium from ctryprem.xlsx
    damodaran_crp = 0.0
    country_name = ctx.financials.key_stats.get("country") or ""
    if country_name and country_name != "United States":
        try:
            df_crp = loader.load("ctryprem", "Global")
            country_col = [c for c in df_crp.columns if "country" in c.lower()][0]
            crp_col = [c for c in df_crp.columns if c == "Country Risk Premium"][0]
            row = df_crp[df_crp[country_col].str.contains(country_name, case=False, na=False)]
            if len(row) > 0:
                damodaran_crp = float(row.iloc[0][crp_col])
        except Exception:
            pass

    # Priority: Live Treasury (US only) → Damodaran → hardcoded
    # Damodaran approach for ALL countries: Rf = US Treasury rate
    # Country risk is added via CRP × Lambda, NOT embedded in Rf
    # This allows terminal growth (5% for India) < Rf + CRP without violating the cap
    if is_india:
        rf = live_rf if (live_rf and 0.01 < live_rf < 0.10) else (damodaran_rf or 0.0418)
        crp = damodaran_crp or 0.032  # India CRP from Damodaran ctryprem.xlsx
        # Lambda: firm-specific country risk exposure
        # Damodaran's approach: Lambda ≈ domestic revenue / total revenue
        # Primary: try WRDS Compustat geographic segments
        # Fallback: sector-based heuristic (Damodaran examples as reference)
        lam = None
        try:
            from valuation.data.wrds_client import WRDSClient
            wc = WRDSClient()
            dbc = wc._connect()
            # Search for company in Compustat, get gvkey
            search = wc.search_company(data.name.split()[0] if data.name else "", loc="IND")
            if search is not None and len(search) > 0:
                gvkey = search.iloc[0]["gvkey"]
                geo = dbc.raw_sql('''
                    SELECT f.revts, g.gareat
                    FROM comp_segments_hist_daily.seg_annfund f
                    JOIN comp_segments_hist_daily.wrds_seg_geo g
                        ON f.gvkey = g.gvkey AND f.sid = g.sid
                    WHERE f.gvkey = %(gvkey)s AND f.stype = %(stype)s
                    AND f.revts IS NOT NULL AND f.revts > 0
                    ORDER BY f.datadate DESC
                    LIMIT 20
                ''', params={'gvkey': gvkey, 'stype': 'GEOG'})
                if len(geo) > 0:
                    total_rev = geo["revts"].sum()
                    india_rev = geo[geo["gareat"].str.contains("India|IND|Domestic", case=False, na=False)]["revts"].sum()
                    if total_rev > 0:
                        lam = round(india_rev / total_rev, 2)
                        print(f"  Lambda: {lam} (from WRDS geo segments: {india_rev:.0f}/{total_rev:.0f} domestic)")
            wc.close()
        except Exception:
            pass

        # Fallback: sector-based heuristic per Damodaran examples
        if lam is None:
            sector = (ctx.company.sector or "").lower()
            industry = (ctx.financials.key_stats.get("industry_yfinance") or "").lower()
            if "technology" in sector or "software" in industry or "it " in industry or "information tech" in industry:
                lam = 0.25  # IT exporters: Damodaran uses 0.2 for TCS
            elif "pharmaceutical" in industry or "drug" in industry or "biotech" in industry:
                lam = 0.5  # Pharma: significant exports
            elif "auto" in industry and "part" not in industry:
                lam = 0.8  # Auto: Damodaran uses 0.8 for Tata Motors (JLR global)
            elif "chemical" in industry:
                lam = 0.75  # Chemicals: Damodaran uses 0.75 for Tata Chemicals
            elif "bank" in industry or "financial" in sector or "insurance" in industry:
                lam = 1.0  # Financials: fully domestic
            elif "defense" in industry or "aerospace" in industry:
                lam = 1.0  # Defense: government customer, fully domestic
            elif "steel" in industry or "mining" in industry or "metal" in industry:
                lam = 1.1  # Commodities: Damodaran uses 1.1 for Tata Steel (more risky than avg)
            elif "real estate" in industry or "construction" in industry:
                lam = 1.0  # Fully domestic
            elif "telecom" in industry or "utility" in industry:
                lam = 1.0  # Domestic infrastructure
            else:
                lam = 0.8  # Default: mostly domestic
            print(f"  Lambda: {lam} (sector heuristic: {sector}/{industry})")
        print(f"  Rf: {rf:.2%} (US Treasury — Damodaran convention) | CRP: {crp:.2%} × Lambda: {lam}")
    elif is_japan:
        rf = 0.01  # Japan has its own yield curve
        crp = damodaran_crp or 0.0
        lam = 1.0
    else:
        # US: prefer live Treasury, fallback to Damodaran
        if live_rf and 0.01 < live_rf < 0.10:
            rf = live_rf
            print(f"  Rf: {rf:.2%} (live US 10yr from Yahoo Finance)")
        elif damodaran_rf:
            rf = damodaran_rf
            print(f"  Rf: {rf:.2%} (Damodaran histimpl.xls)")
        else:
            rf = 0.0395
            print(f"  Rf: {rf:.2%} (hardcoded fallback)")
        crp = damodaran_crp
        lam = 1.0

    erp = damodaran_erp or 0.0446
    print(f"  ERP: {erp:.2%} (Damodaran implied{'— live' if damodaran_erp else '— fallback'})")

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

    sourced_inputs["risk_free_rate"] = from_damodaran(rf, "histretSP.xls / local Rf")
    sourced_inputs["erp"] = from_damodaran(erp, "histimpl.xls")
    sourced_inputs["beta"] = computed(beta, "Industry unlevered beta re-levered")
    sourced_inputs["cost_of_equity"] = computed(ke, "CAPM: Rf + beta*(ERP+CRP)")
    sourced_inputs["cost_of_debt"] = computed(cod, "Rf + synthetic spread from ICR")
    sourced_inputs["wacc"] = computed(wacc, "Ke*E/(D+E) + Kd*(1-t)*D/(D+E)")
    sourced_inputs["tax_rate"] = computed(tax_rate, "Tax Provision / Pretax Income")

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

    if terminal_override is not None:
        ctx.assumptions.set_override("terminal_growth", terminal_growth,
            f"CLI override: terminal growth set to {terminal_override}")

    # Smart growth selection (Damodaran hierarchy)
    rev_g = growth_dict.get("historical_revenue")
    ni_g = growth_dict.get("historical_net_income")

    # Fundamental growth recomputed from local roe/retention for selection logic
    fundamental = roe * retention if roe > 0 and retention > 0 else None

    # Industry benchmark
    industry_g = (
        ctx.benchmarks.industry_growth.get("expected_growth_5y")
        if ctx.benchmarks.industry_growth
        else None
    )

    # Build candidate dict for display
    candidates: dict[str, float] = {}
    if rev_g and rev_g.value > 0:
        candidates["historical_revenue"] = rev_g.value
    if ni_g and ni_g.value > 0:
        candidates["historical_net_income"] = ni_g.value
    if fundamental and fundamental > 0:
        candidates["fundamental_roe_x_retention"] = fundamental

    if growth_override is not None:
        high_growth = growth_override
        print(f"  Growth override: {high_growth:.2%}")
    elif ctx.company.classification == "growth":
        # Growth companies: use higher of fundamental and revenue CAGR
        if fundamental and fundamental > 0:
            high_growth = max(fundamental, candidates.get("historical_revenue", 0))
        elif "historical_revenue" in candidates:
            high_growth = candidates["historical_revenue"]
        else:
            high_growth = 0.10
        # Cap at industry * 1.5 or 25%
        if industry_g and industry_g > 0:
            high_growth = min(high_growth, industry_g * 1.5)
        high_growth = min(high_growth, 0.25)
        print(f"  Selected: {high_growth:.2%} (growth company — higher of fundamental/historical, capped)")
    elif ctx.company.classification == "mature":
        # Mature companies: fundamental growth is most sustainable
        if fundamental and fundamental > 0:
            high_growth = fundamental
        elif "historical_revenue" in candidates:
            high_growth = candidates["historical_revenue"]
        else:
            high_growth = 0.05
        high_growth = min(high_growth, 0.15)  # mature companies rarely grow > 15%
        print(f"  Selected: {high_growth:.2%} (mature company — fundamental preferred)")
    else:
        # Default: use revenue CAGR
        high_growth = candidates.get("historical_revenue", 0.08)
        high_growth = max(min(high_growth, 0.25), 0.02)
        print(f"  Selected: {high_growth:.2%} (default — revenue CAGR)")

    print(f"  Candidates: {', '.join(f'{k}={v:.2%}' for k, v in candidates.items())}")
    if industry_g:
        print(f"  Industry benchmark: {industry_g:.2%}")

    growth_rates = interpolate_params(high_growth, terminal_growth, n_years, gradual=True)
    ctx.assumptions.growth_rates = growth_rates
    ctx.assumptions.terminal_growth = terminal_growth
    ctx.assumptions.projection_years = n_years

    if growth_override is not None:
        ctx.assumptions.set_override("growth_rates", growth_rates,
            f"CLI override: high growth set to {growth_override:.2%}")

    print(f"\n  → Using: {high_growth:.2%} high-growth → {terminal_growth:.2%} terminal over {n_years} years")

    if growth_override is not None:
        sourced_inputs["high_growth"] = from_user(high_growth, f"CLI override: {growth_override:.2%}")
    else:
        sourced_inputs["high_growth"] = computed(high_growth, "Damodaran hierarchy (ROE*retention / revenue CAGR)")
    if terminal_override is not None:
        sourced_inputs["terminal_growth"] = from_user(terminal_growth, f"CLI override: {terminal_override:.2%}")
    else:
        sourced_inputs["terminal_growth"] = computed(terminal_growth, "Nominal GDP proxy")

    # ================================================================
    # STEP 6.5: Assumption Proposals
    # ================================================================
    print(f"\n--- Step 6.5: Assumption Proposals ---")
    try:
        from valuation.agents.assumption_proposer import propose_assumptions, format_proposals_for_report

        proposals = propose_assumptions(ctx)
        ctx.financials.key_stats["assumption_proposals"] = proposals
        if proposals:
            for p in proposals:
                conf_label = "HIGH" if p.confidence >= 0.7 else "MED" if p.confidence >= 0.4 else "LOW"
                print(f"  [{conf_label}] {p.parameter}: {p.question}")
        else:
            print(f"  No specific proposals generated")
    except Exception as e:
        print(f"  Proposal generation error: {e}")
        proposals = []

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
    # STEP 7.5: Assumption Review
    # ================================================================
    print(f"\n--- Step 7.5: Assumption Review ---")
    from valuation.agents.assumption_reviewer import review_assumptions, format_review_for_report

    reviews = review_assumptions(ctx)
    ctx.financials.key_stats["assumption_reviews"] = reviews

    warnings_7 = [r for r in reviews if r["severity"] in ("warning", "critical")]
    if warnings_7:
        for r in warnings_7:
            icon = "✗" if r["severity"] == "critical" else "⚠"
            print(f"  {icon} {r['field']}: {r['comment']}")
    else:
        print(f"  All assumptions within expected ranges")

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
        print(f"  [Financial routing] Using DDM + Excess Returns (not FCFF)")
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
        # FCFF v2 — revenue-based with Damodaran transitions
        # R&D capitalization
        rd_adj = 0.0
        research_asset = 0.0
        rd_col = None
        for col in inc.columns:
            if 'research' in col.lower() and 'development' in col.lower():
                rd_col = col
                break
        if rd_col:
            current_rd = abs(float(latest_inc.get(rd_col, 0) or 0))
            if current_rd > 0:
                past_rd = []
                for i in range(1, min(len(inc), 6)):
                    val = abs(float(inc.iloc[i].get(rd_col, 0) or 0))
                    if val > 0:
                        past_rd.append(val)
                amort_years = get_amortization_period(ctx.company.damodaran_industry or "")
                rd_result = capitalize_rd(current_rd, past_rd, amort_years)
                rd_adj = rd_result["ebit_adjustment"]
                research_asset = rd_result["research_asset"]
                print(f"  [R&D Cap] Current R&D: {current_rd:,.0f} | Asset: {research_asset:,.0f} | EBIT adj: +{rd_adj:,.0f}")

        # Terminal WACC (Damodaran: Rf + 4.5% + CRP)
        t_wacc = terminal_wacc_default(rf, crp if crp else 0.0)
        # Allow override if user specified stable WACC lower
        stable_roc = 0.20  # competitive advantage persists for quality companies

        # Generate Damodaran-style schedules
        wacc_sched = wacc_schedule(wacc, t_wacc, n_years, n_constant=5)
        tax_sched = tax_schedule(tax_rate, 0.25, n_years, n_constant=5)

        # Operating margin convergence
        current_margin = ebit / revenue if revenue > 0 else 0.15
        target_margin = min(current_margin, 0.60)  # cap at 60% (Damodaran Nvidia convention)
        if current_margin < 0.15:
            target_margin = max(current_margin, ctx.benchmarks.industry_margins.get("operating_margin", 0.15) or 0.15)
        margin_sched = margin_convergence_schedule(current_margin, target_margin, convergence_year=5, n_years=n_years)

        # Sales-to-capital ratio from financials
        total_assets = float(latest_bs.get('Total Assets', 0) or 0)
        invested_capital = total_assets - cash + research_asset
        s2c = revenue / invested_capital if invested_capital > 0 else 2.5
        s2c = max(min(s2c, 10.0), 0.5)  # bound

        sourced_inputs["sales_to_capital"] = computed(s2c, "Revenue / Invested Capital (from balance sheet)")
        print(f"  [Schedules] WACC: {wacc:.2%} → {t_wacc:.2%} | Tax: {tax_rate:.1%} → 25%")
        print(f"  [Schedules] Margin: {current_margin:.1%} → {target_margin:.1%} | S2C: {s2c:.2f}")

        fcff_result = fcff_valuation_v2(
            base_revenue=revenue,
            base_ebit=ebit,
            revenue_growth_rates=growth_rates,
            operating_margins=margin_sched,
            tax_rates=tax_sched,
            waccs=wacc_sched,
            sales_to_capital=s2c,
            stable_growth=terminal_growth,
            stable_roc=stable_roc,
            stable_wacc=t_wacc,
            stable_tax_rate=0.25,
            cash=cash,
            debt=total_debt,
            non_operating_assets=0.0,
            minority_interests=0.0,
            options_value=0.0,
            shares_outstanding=data.shares_outstanding,
            rd_adjustment=rd_adj,
            research_asset=research_asset,
            base_invested_capital=invested_capital,
        )
        ctx.outputs.dcf_fcff = fcff_result
        print(f"  [FCFF DCF v2] Value/Share: {fcff_result['equity_value_per_share']:,.2f}")
        print(f"    EV: {fcff_result['enterprise_value']:,.0f} | PV HG: {fcff_result['pv_high_growth']:,.0f} | PV TV: {fcff_result['pv_terminal']:,.0f}")

        # Also run Gordon Growth for stable dividend-paying companies
        if (ctx.company.classification == "mature"
                and data.dividend_per_share and data.dividend_per_share > 0
                and ctx.assumptions.cost_of_equity and ctx.assumptions.terminal_growth):
            try:
                gg_value = gordon_growth_value(
                    current_dividend=data.dividend_per_share,
                    cost_of_equity=ctx.assumptions.cost_of_equity,
                    growth_rate=ctx.assumptions.terminal_growth,
                )
                if not ctx.outputs.dcf_fcfe:
                    ctx.outputs.dcf_fcfe = {"value_per_share": gg_value, "model": "gordon_growth"}
                print(f"  [Gordon Growth] Value/Share: {gg_value:,.2f}")
            except (ValueError, ZeroDivisionError):
                pass

    # Store sourced inputs in context for report transparency
    ctx.financials.key_stats["sourced_inputs"] = sourced_inputs

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

    # Validate outputs against sanity bounds
    from valuation.validation.bounds import check_all_inputs
    output_checks: dict[str, float | None] = {}
    if ctx.outputs.dcf_fcff:
        per_share = ctx.outputs.dcf_fcff.get("equity_value_per_share", 0)
        output_checks["equity_value_per_share"] = per_share
        if data.price > 0 and per_share and per_share > 0:
            ratio = per_share / data.price
            if ratio > 5:
                print(f"  DCF value ({per_share:,.0f}) is {ratio:.1f}x market price — check assumptions")
            elif ratio < 0.1:
                print(f"  DCF value ({per_share:,.0f}) is only {ratio:.0%} of market price — check assumptions")
    # Add key assumption bounds checks
    output_checks["wacc"] = ctx.assumptions.wacc
    output_checks["terminal_growth"] = ctx.assumptions.terminal_growth
    output_checks["beta"] = ctx.assumptions.beta
    output_checks["cost_of_equity"] = ctx.assumptions.cost_of_equity
    output_checks["cost_of_debt"] = ctx.assumptions.cost_of_debt
    bounds_report = check_all_inputs(output_checks)
    for bc in bounds_report.warnings:
        print(f"  Bounds WARN: {bc.message}")
    for bc in bounds_report.halts:
        print(f"  Bounds HALT: {bc.message}")

    # ================================================================
    # STEP 9: Sensitivity Analysis
    # ================================================================
    print(f"\n--- Step 9: Sensitivity Analysis ---")
    if ctx.outputs.dcf_fcff and ctx.company.classification != "financial":
        base_params = dict(
            base_revenue=revenue,
            base_ebit=ebit,
            revenue_growth_rates=growth_rates,
            operating_margins=margin_sched,
            tax_rates=tax_sched,
            waccs=wacc_sched,
            sales_to_capital=s2c,
            stable_growth=terminal_growth,
            stable_roc=stable_roc,
            stable_wacc=t_wacc,
            stable_tax_rate=0.25,
            cash=cash, debt=total_debt,
            shares_outstanding=data.shares_outstanding,
            rd_adjustment=rd_adj,
            research_asset=research_asset,
            base_invested_capital=invested_capital,
        )
        extract_fn = lambda **kw: fcff_valuation_v2(**kw)["equity_value_per_share"]

        # One-way: vary terminal WACC (which drives the schedule)
        base_t_wacc = t_wacc if ctx.company.classification != "financial" else wacc
        wacc_offsets = [-0.02, -0.01, 0, 0.01, 0.02]
        wacc_sens = {}
        for offset in wacc_offsets:
            w_val = base_t_wacc + offset
            try:
                new_sched = wacc_schedule(wacc + offset, w_val, n_years, n_constant=5)
                p = {**base_params, "waccs": new_sched, "stable_wacc": w_val}
                wacc_sens[round(w_val, 4)] = extract_fn(**p)
            except (ValueError, ZeroDivisionError):
                wacc_sens[round(w_val, 4)] = float("nan")

        # Two-way: terminal WACC vs terminal growth
        tg_values = [terminal_growth - 0.02, terminal_growth - 0.01, terminal_growth, terminal_growth + 0.01]
        two_way = {}
        for offset in wacc_offsets:
            w_val = base_t_wacc + offset
            two_way[round(w_val, 4)] = {}
            for tg_val in tg_values:
                try:
                    new_sched = wacc_schedule(wacc + offset, w_val, n_years, n_constant=5)
                    p = {**base_params, "waccs": new_sched, "stable_wacc": w_val, "stable_growth": tg_val}
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
    ibes_data = fetch_ibes_consensus(data.name or ticker, ticker=ticker, currency=currency)
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

    from valuation.agents.cross_validator import explain_divergence
    divergence_explanation = explain_divergence(cv, ctx)
    if divergence_explanation:
        for line in divergence_explanation.splitlines():
            print(f"  {line}")
    ctx.financials.key_stats["divergence_explanation"] = divergence_explanation

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
