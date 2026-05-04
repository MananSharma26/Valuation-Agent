"""Peer analysis: WRDS (Compustat) selects peers, Yahoo Finance enriches.

Provides peer comparison tables for valuation context — company metrics
vs peer median across margins, growth, valuation multiples, and beta.
"""

from __future__ import annotations

from typing import Any


def fetch_peers_wrds(
    sic_code: str,
    region: str = "US",
    top_n: int = 10,
) -> list[dict[str, Any]]:
    """Query Compustat for peers by 2-digit SIC code, ranked by revenue.

    Uses comp.funda for US companies, comp_global_daily.g_funda for international.

    Returns list of dicts with: name, gvkey, revenue, net_income, total_assets, country.
    Returns empty list on failure.
    """
    try:
        from valuation.data.wrds_client import WRDSClient
    except ImportError:
        return []

    sic_2digit = str(sic_code)[:2] if sic_code else ""
    if not sic_2digit:
        return []

    try:
        w = WRDSClient()
        db = w._connect()

        if region == "US":
            query = """
                SELECT DISTINCT ON (conm) gvkey, conm, revt, ni, at, loc
                FROM comp.funda
                WHERE sic LIKE %(sic_prefix)s
                AND datafmt='STD' AND indfmt='INDL' AND consol='C' AND popsrc='D'
                AND fyear = (SELECT MAX(fyear) FROM comp.funda
                             WHERE sic LIKE %(sic_prefix)s
                             AND datafmt='STD' AND indfmt='INDL'
                             AND consol='C' AND popsrc='D')
                AND revt IS NOT NULL AND revt > 0
                ORDER BY conm, revt DESC
            """
        else:
            query = """
                SELECT DISTINCT ON (conm) gvkey, conm, revt, nicon AS ni, at, loc
                FROM comp_global_daily.g_funda
                WHERE sic LIKE %(sic_prefix)s
                AND datafmt='HIST_STD' AND indfmt='INDL' AND consol='C'
                AND fyear = (SELECT MAX(fyear) FROM comp_global_daily.g_funda
                             WHERE sic LIKE %(sic_prefix)s
                             AND datafmt='HIST_STD' AND indfmt='INDL' AND consol='C')
                AND revt IS NOT NULL AND revt > 0
                ORDER BY conm, revt DESC
            """

        params = {"sic_prefix": f"{sic_2digit}%"}
        result = db.raw_sql(query, params=params)
        w.close()

        if result is None or result.empty:
            return []

        # Sort by revenue descending and take top_n
        result = result.sort_values("revt", ascending=False).head(top_n)

        peers = []
        for _, row in result.iterrows():
            peers.append({
                "name": str(row.get("conm", "")),
                "gvkey": str(row.get("gvkey", "")),
                "revenue": float(row["revt"]) if row.get("revt") is not None else None,
                "net_income": float(row["ni"]) if row.get("ni") is not None else None,
                "total_assets": float(row["at"]) if row.get("at") is not None else None,
                "country": str(row.get("loc", "")),
            })
        return peers

    except Exception:
        return []


def enrich_peers_yahoo(peer_names: list[str]) -> list[dict[str, Any]]:
    """Best-effort enrichment of peer companies via yfinance.

    Tries to find each peer by name using yfinance search. Returns a list
    of dicts with: name, ticker, price, pe, profit_margin, revenue_growth, beta.
    """
    enriched = []
    try:
        import yfinance as yf
    except ImportError:
        return enriched

    for name in peer_names[:15]:  # cap at 15 to avoid rate limits
        try:
            # Search for ticker by company name
            search = yf.Search(name)
            quotes = search.quotes if hasattr(search, "quotes") else []
            if not quotes:
                continue

            ticker_str = quotes[0].get("symbol", "")
            if not ticker_str:
                continue

            stock = yf.Ticker(ticker_str)
            info = stock.info or {}

            enriched.append({
                "name": name,
                "ticker": ticker_str,
                "price": info.get("currentPrice") or info.get("regularMarketPrice"),
                "pe": info.get("trailingPE"),
                "forward_pe": info.get("forwardPE"),
                "profit_margin": info.get("profitMargins"),
                "revenue_growth": info.get("revenueGrowth"),
                "earnings_growth": info.get("earningsGrowth"),
                "beta": info.get("beta"),
                "market_cap": info.get("marketCap"),
                "ev_to_ebitda": info.get("enterpriseToEbitda"),
            })
        except Exception:
            continue

    return enriched


def fetch_peer_comparison(
    sic_code: str,
    company_name: str,
    company_metrics: dict[str, Any],
    region: str = "US",
    top_n: int = 10,
) -> dict[str, Any] | None:
    """Full peer comparison pipeline: WRDS select + Yahoo enrich + comparison.

    Args:
        sic_code: Company SIC code (uses 2-digit for peer matching)
        company_name: Company name (excluded from peer list)
        company_metrics: Dict with keys like pe, profit_margin, revenue_growth,
                        beta, ev_to_ebitda for comparison
        region: "US" or other region string
        top_n: Number of peers to fetch from WRDS

    Returns dict with:
        peers: list of enriched peer dicts
        peer_median: dict of median metrics across peers
        company_vs_median: dict showing company metric vs peer median
    Returns None if no peers found.
    """
    # Step 1: Get peer names from WRDS
    wrds_peers = fetch_peers_wrds(sic_code, region=region, top_n=top_n + 5)

    # Filter out the company itself
    name_lower = company_name.lower() if company_name else ""
    wrds_peers = [
        p for p in wrds_peers
        if name_lower not in p["name"].lower()
    ][:top_n]

    if not wrds_peers:
        return None

    # Step 2: Enrich with Yahoo Finance
    peer_names = [p["name"] for p in wrds_peers]
    enriched = enrich_peers_yahoo(peer_names)

    if not enriched:
        # Return WRDS-only data
        return {
            "peers": wrds_peers,
            "peer_median": {},
            "company_vs_median": {},
            "source": "wrds_only",
        }

    # Step 3: Compute peer medians
    def _median(values: list[float]) -> float | None:
        clean = sorted(v for v in values if v is not None and v == v)  # exclude NaN
        if not clean:
            return None
        n = len(clean)
        if n % 2 == 1:
            return clean[n // 2]
        return (clean[n // 2 - 1] + clean[n // 2]) / 2

    metrics_keys = ["pe", "forward_pe", "profit_margin", "revenue_growth",
                    "beta", "ev_to_ebitda", "earnings_growth"]
    peer_median: dict[str, Any] = {}
    for key in metrics_keys:
        values = [p.get(key) for p in enriched if p.get(key) is not None]
        med = _median(values)
        if med is not None:
            peer_median[key] = med

    # Step 4: Compare company vs peer median
    company_vs_median: dict[str, dict] = {}
    for key in metrics_keys:
        co_val = company_metrics.get(key)
        med_val = peer_median.get(key)
        if co_val is not None and med_val is not None and med_val != 0:
            diff_pct = (co_val - med_val) / abs(med_val)
            company_vs_median[key] = {
                "company": co_val,
                "peer_median": med_val,
                "diff_pct": diff_pct,
                "assessment": (
                    "above peers" if diff_pct > 0.1
                    else "below peers" if diff_pct < -0.1
                    else "in line with peers"
                ),
            }

    return {
        "peers": enriched,
        "peer_median": peer_median,
        "company_vs_median": company_vs_median,
        "source": "wrds_yahoo",
        "num_peers_wrds": len(wrds_peers),
        "num_peers_enriched": len(enriched),
    }
