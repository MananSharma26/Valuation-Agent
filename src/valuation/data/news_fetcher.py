"""Fetch recent news and context for a company from Yahoo Finance."""

from __future__ import annotations


def fetch_company_news(ticker: str, max_items: int = 10) -> list[dict]:
    """Fetch recent news headlines for a company from Yahoo Finance.

    Returns list of dicts with: title, link, published, summary
    """
    try:
        import yfinance as yf
        stock = yf.Ticker(ticker)
        news = stock.news or []
        results = []
        for item in news[:max_items]:
            results.append({
                "title": item.get("title", ""),
                "link": item.get("link", ""),
                "publisher": item.get("publisher", ""),
                "published": item.get("providerPublishTime", ""),
                "summary": item.get("summary", item.get("title", "")),
            })
        return results
    except Exception:
        return []


def fetch_company_profile(ticker: str) -> dict:
    """Fetch company description and key context from Yahoo Finance.

    Returns dict with: description, fullTimeEmployees, website,
    recentEarnings, forwardPE, trailingPE, etc.
    """
    try:
        import yfinance as yf
        stock = yf.Ticker(ticker)
        info = stock.info or {}
        return {
            "description": info.get("longBusinessSummary", ""),
            "employees": info.get("fullTimeEmployees"),
            "website": info.get("website", ""),
            "forward_pe": info.get("forwardPE"),
            "trailing_pe": info.get("trailingPE"),
            "peg_ratio": info.get("pegRatio"),
            "profit_margins": info.get("profitMargins"),
            "revenue_growth": info.get("revenueGrowth"),
            "earnings_growth": info.get("earningsGrowth"),
            "target_mean_price": info.get("targetMeanPrice"),
            "recommendation_key": info.get("recommendationKey"),
            "total_cash": info.get("totalCash"),
            "total_debt": info.get("totalDebt"),
            "operating_cashflow": info.get("operatingCashflow"),
            "free_cashflow": info.get("freeCashflow"),
        }
    except Exception:
        return {}


def build_context_summary(ticker: str, company_name: str) -> str:
    """Build a text summary of recent context for LLM consumption.

    This text is NOT used as a model input — it's context for the LLM
    to make better judgment calls about growth, risk, and classification.
    """
    news = fetch_company_news(ticker)
    profile = fetch_company_profile(ticker)

    parts = []

    # Company description
    desc = profile.get("description", "")
    if desc:
        parts.append(f"COMPANY: {desc[:500]}")

    # Key metrics from Yahoo
    metrics = []
    if profile.get("revenue_growth"):
        metrics.append(f"Revenue Growth (YoY): {profile['revenue_growth']:.1%}")
    if profile.get("earnings_growth"):
        metrics.append(f"Earnings Growth (YoY): {profile['earnings_growth']:.1%}")
    if profile.get("profit_margins"):
        metrics.append(f"Profit Margins: {profile['profit_margins']:.1%}")
    if profile.get("recommendation_key"):
        metrics.append(f"Analyst Recommendation: {profile['recommendation_key']}")
    if profile.get("peg_ratio"):
        metrics.append(f"PEG Ratio: {profile['peg_ratio']:.2f}")
    if metrics:
        parts.append("KEY METRICS: " + " | ".join(metrics))

    # Recent news headlines
    if news:
        headlines = [f"- {n['title']}" for n in news[:7]]
        parts.append("RECENT NEWS:\n" + "\n".join(headlines))

    return "\n\n".join(parts)
