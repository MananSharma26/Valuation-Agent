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


def fetch_macro_context() -> dict:
    """Fetch current macro context: Treasury yields, S&P 500 PE, VIX.

    Uses yfinance to pull live market data for:
    - ^TNX: 10-Year Treasury yield
    - ^IRX: 13-Week Treasury Bill rate
    - ^FVX: 5-Year Treasury yield
    - ^GSPC: S&P 500 (for PE ratio)
    - ^VIX: CBOE Volatility Index

    Returns dict with yields, vix, sp500_pe, and commentary string.
    """
    result: dict = {
        "treasury_10y": None,
        "treasury_3m": None,
        "treasury_5y": None,
        "vix": None,
        "sp500_pe": None,
        "commentary": "",
    }

    try:
        import yfinance as yf

        tickers = {
            "^TNX": "treasury_10y",
            "^IRX": "treasury_3m",
            "^FVX": "treasury_5y",
            "^VIX": "vix",
        }

        for symbol, key in tickers.items():
            try:
                t = yf.Ticker(symbol)
                info = t.info or {}
                price = info.get("regularMarketPrice") or info.get("previousClose")
                if price is not None:
                    # Treasury yields are quoted as percentages (e.g., 4.5 = 4.5%)
                    if "treasury" in key:
                        result[key] = price / 100.0
                    else:
                        result[key] = price
            except Exception:
                continue

        # S&P 500 trailing PE
        try:
            sp = yf.Ticker("^GSPC")
            sp_info = sp.info or {}
            result["sp500_pe"] = sp_info.get("trailingPE")
        except Exception:
            pass

        # Generate commentary
        commentary_parts = []
        if result["treasury_10y"]:
            commentary_parts.append(f"10Y Treasury: {result['treasury_10y']:.2%}")
        if result["treasury_3m"]:
            commentary_parts.append(f"3M T-Bill: {result['treasury_3m']:.2%}")
        if result["vix"]:
            vix = result["vix"]
            vol_label = "low" if vix < 15 else "moderate" if vix < 25 else "high"
            commentary_parts.append(f"VIX: {vix:.1f} ({vol_label} volatility)")
        if result["sp500_pe"]:
            commentary_parts.append(f"S&P 500 PE: {result['sp500_pe']:.1f}")

        # Yield curve signal
        if result["treasury_10y"] and result["treasury_3m"]:
            spread = result["treasury_10y"] - result["treasury_3m"]
            if spread < 0:
                commentary_parts.append("Yield curve: INVERTED (recession signal)")
            elif spread < 0.005:
                commentary_parts.append("Yield curve: FLAT")
            else:
                commentary_parts.append(f"Yield curve: normal (spread {spread:.2%})")

        result["commentary"] = " | ".join(commentary_parts)

    except ImportError:
        result["commentary"] = "yfinance not available"

    return result


def fetch_gdp_forecast(country: str = "United States") -> dict:
    """Fetch GDP growth forecast from World Bank API.

    Queries the World Bank Indicators API for real GDP growth
    (NY.GDP.MKTP.KD.ZG) for the specified country.

    Returns dict with: country_code, gdp_growth (latest available),
    gdp_history (list of recent values), source.
    """
    import json
    import urllib.request
    import urllib.error

    # Map country names to ISO 3166-1 alpha-3 codes
    country_codes = {
        "United States": "USA",
        "US": "USA",
        "India": "IND",
        "Japan": "JPN",
        "China": "CHN",
        "United Kingdom": "GBR",
        "UK": "GBR",
        "Germany": "DEU",
        "France": "FRA",
        "Canada": "CAN",
        "Australia": "AUS",
        "Brazil": "BRA",
        "South Korea": "KOR",
        "Mexico": "MEX",
    }

    code = country_codes.get(country, "USA")

    result: dict = {
        "country_code": code,
        "gdp_growth": None,
        "gdp_history": [],
        "source": "World Bank",
    }

    url = (
        f"https://api.worldbank.org/v2/country/{code}/"
        f"indicator/NY.GDP.MKTP.KD.ZG?format=json&per_page=5&mrv=5"
    )

    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        if len(data) >= 2 and isinstance(data[1], list):
            entries = data[1]
            for entry in entries:
                val = entry.get("value")
                year = entry.get("date")
                if val is not None:
                    result["gdp_history"].append({
                        "year": year,
                        "growth": val / 100.0,  # convert percentage to decimal
                    })
                    if result["gdp_growth"] is None:
                        result["gdp_growth"] = val / 100.0
    except (urllib.error.URLError, urllib.error.HTTPError, OSError, ValueError):
        pass

    return result
