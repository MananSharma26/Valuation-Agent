"""Fetch SEC EDGAR filings (10-K) for US companies.

Uses only stdlib (urllib, json, re) — no third-party dependencies.
Extracts Risk Factors (Item 1A) and MD&A (Item 7) sections from 10-K filings.
"""

from __future__ import annotations

import json
import re
import urllib.request
import urllib.error
from typing import Any

_USER_AGENT = "ValuationAgent/1.0 valuation@example.com"
_TIMEOUT = 15


def _get_cik(ticker: str) -> str | None:
    """Look up CIK number for a ticker from SEC's company_tickers.json.

    Returns the zero-padded CIK string, or None if not found.
    """
    url = "https://www.sec.gov/files/company_tickers.json"
    req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, OSError):
        return None

    ticker_upper = ticker.upper().split(".")[0]  # strip exchange suffix
    for entry in data.values():
        if str(entry.get("ticker", "")).upper() == ticker_upper:
            cik = str(entry["cik_str"])
            return cik.zfill(10)
    return None


def _get_latest_10k_url(cik: str) -> tuple[str, str] | None:
    """Fetch the most recent 10-K filing URL and date from EDGAR submissions.

    Returns (filing_url, filing_date) or None.
    """
    url = f"https://data.sec.gov/submissions/CIK{cik}.json"
    req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, OSError):
        return None

    recent = data.get("filings", {}).get("recent", {})
    forms = recent.get("form", [])
    accessions = recent.get("accessionNumber", [])
    dates = recent.get("filingDate", [])
    primary_docs = recent.get("primaryDocument", [])

    for i, form in enumerate(forms):
        if form == "10-K":
            accession = accessions[i].replace("-", "")
            doc = primary_docs[i] if i < len(primary_docs) else ""
            filing_url = (
                f"https://www.sec.gov/Archives/edgar/data/"
                f"{cik.lstrip('0')}/{accession}/{doc}"
            )
            filing_date = dates[i] if i < len(dates) else ""
            return filing_url, filing_date

    return None


def _extract_section(
    text: str,
    start_pattern: str,
    end_pattern: str,
    max_chars: int = 5000,
) -> str:
    """Extract text between two Item markers using regex.

    Returns the extracted text (up to max_chars), or empty string.
    """
    match = re.search(start_pattern, text, re.IGNORECASE | re.DOTALL)
    if not match:
        return ""
    start_pos = match.end()

    end_match = re.search(end_pattern, text[start_pos:], re.IGNORECASE | re.DOTALL)
    if end_match:
        section = text[start_pos : start_pos + end_match.start()]
    else:
        section = text[start_pos:]

    # Clean up HTML tags and excessive whitespace
    section = re.sub(r"<[^>]+>", " ", section)
    section = re.sub(r"&nbsp;", " ", section)
    section = re.sub(r"&amp;", "&", section)
    section = re.sub(r"&lt;", "<", section)
    section = re.sub(r"&gt;", ">", section)
    section = re.sub(r"\s+", " ", section).strip()

    return section[:max_chars]


def fetch_sec_filings(
    ticker: str,
    country: str = "United States",
) -> dict[str, Any] | None:
    """Fetch SEC 10-K filing data for a US company.

    Returns None for non-US companies. For US companies, returns a dict with:
        risk_factors: str — Item 1A Risk Factors text (up to 5000 chars)
        mda: str — Item 7 MD&A text (up to 5000 chars)
        filing_date: str — date of the 10-K filing
        filing_url: str — URL to the filing on EDGAR
        raw_context: str — fallback if sections couldn't be extracted

    Returns None on any failure.
    """
    if country not in ("United States", "US", "USA"):
        return None

    cik = _get_cik(ticker)
    if cik is None:
        return None

    filing_info = _get_latest_10k_url(cik)
    if filing_info is None:
        return None

    filing_url, filing_date = filing_info

    # Fetch the filing document
    req = urllib.request.Request(filing_url, headers={"User-Agent": _USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            text = resp.read().decode("utf-8", errors="replace")
    except (urllib.error.URLError, urllib.error.HTTPError, OSError):
        # Return metadata even if we can't fetch the document
        return {
            "risk_factors": "",
            "mda": "",
            "filing_date": filing_date,
            "filing_url": filing_url,
            "raw_context": "",
        }

    # Extract key sections
    risk_factors = _extract_section(
        text,
        start_pattern=r"item\s+1a[\.\s\-\:]*risk\s+factors",
        end_pattern=r"item\s+1b[\.\s\-\:]",
        max_chars=5000,
    )

    mda = _extract_section(
        text,
        start_pattern=r"item\s+7[\.\s\-\:]*management.{0,5}s?\s+discussion",
        end_pattern=r"item\s+7a[\.\s\-\:]",
        max_chars=5000,
    )

    result: dict[str, Any] = {
        "risk_factors": risk_factors,
        "mda": mda,
        "filing_date": filing_date,
        "filing_url": filing_url,
    }

    # Fallback: if both sections are empty, grab first 5000 chars as raw context
    if not risk_factors and not mda:
        # Strip HTML for raw context
        raw = re.sub(r"<[^>]+>", " ", text)
        raw = re.sub(r"\s+", " ", raw).strip()
        result["raw_context"] = raw[:5000]
    else:
        result["raw_context"] = ""

    return result
