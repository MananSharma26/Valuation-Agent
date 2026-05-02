"""
classifier.py -- Rule-based company lifecycle classification.

Classifies a company as one of:
  - mature:     Stable earnings, moderate growth, established business
  - growth:     High revenue growth (>20%), positive or near-positive earnings
  - young:      Pre-profit or early-stage, high burn rate, short operating history
  - distressed: Negative earnings, high leverage, declining revenue
  - cyclical:   Sector-driven cyclicality (materials, energy, autos, etc.)
  - financial:  Banks, insurance, brokerages (SIC 60xx-67xx or Financial sector)

All logic is rule-based with deterministic scoring. Produces a reasoning
string that a future LLM layer can refine.

No LLM calls. No consensus estimates.

Model routing:
  - financial   -> "ddm"
  - distressed  -> "dcf_fcff"
  - young       -> "dcf_fcff"
  - growth      -> "dcf_fcff"
  - cyclical    -> "dcf_fcff"
  - mature      -> "dcf_fcff" (or "gordon_growth" if very stable)
"""

from __future__ import annotations

from dataclasses import dataclass, field

from valuation.context import ValuationContext


@dataclass
class ClassificationResult:
    """Result of company classification."""

    classification: str          # mature|growth|young|distressed|cyclical|financial
    confidence: float            # 0.0 to 1.0
    reasoning: str               # Human-readable explanation for LLM to refine
    suggested_model: str = "dcf_fcff"  # dcf_fcff|ddm|gordon_growth


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# SIC code ranges for financial firms
_FINANCIAL_SIC_RANGES = [
    (6000, 6799),  # Finance, Insurance, Real Estate
]

# Sectors that indicate cyclical businesses
_CYCLICAL_SECTORS = {
    "Basic Materials",
    "Energy",
    "Consumer Cyclical",
    "Industrials",
    # Plan also lists "Materials", "Real Estate", "Consumer Discretionary"
    "Materials",
    "Real Estate",
    "Consumer Discretionary",
}

# Sectors that indicate financial firms
_FINANCIAL_SECTORS = {
    "Financial Services",
    "Financial",
}

# Model routing table
_MODEL_ROUTING: dict[str, str] = {
    "financial": "ddm",
    "distressed": "dcf_fcff",
    "young": "dcf_fcff",
    "growth": "dcf_fcff",
    "cyclical": "dcf_fcff",
    "mature": "dcf_fcff",
}


# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------

def _safe_get_col(df, col_name: str, row: int = 0, default=None):
    """Safely extract a value from a DataFrame column."""
    if df is None:
        return default
    if col_name not in df.columns:
        return default
    try:
        val = df[col_name].iloc[row]
        return float(val) if val is not None else default
    except (IndexError, ValueError, TypeError):
        return default


def _compute_revenue_growth(ctx: ValuationContext) -> float | None:
    """Compute YoY revenue growth from income statement (row 0 = latest)."""
    is_df = ctx.financials.income_statement
    if is_df is None or "Total Revenue" not in is_df.columns:
        return None
    try:
        revenues = is_df["Total Revenue"].dropna().tolist()
        if len(revenues) < 2:
            return None
        latest = float(revenues[0])
        prev = float(revenues[1])
        if prev <= 0:
            return None
        return (latest - prev) / abs(prev)
    except (ValueError, TypeError, IndexError):
        return None


def _has_consecutive_losses(ctx: ValuationContext) -> bool:
    """Check if the company has negative net income in the latest periods.

    Returns True if:
    - 2+ periods available and both are negative, OR
    - only 1 period available and it is negative (single data point).
    """
    is_df = ctx.financials.income_statement
    if is_df is None or "Net Income" not in is_df.columns:
        return False
    try:
        incomes = is_df["Net Income"].dropna().tolist()
        if len(incomes) == 0:
            return False
        if len(incomes) == 1:
            return float(incomes[0]) < 0
        return float(incomes[0]) < 0 and float(incomes[1]) < 0
    except (ValueError, TypeError, IndexError):
        return False


def _is_negative_earnings(ctx: ValuationContext) -> bool:
    """Check if the latest net income is negative."""
    is_df = ctx.financials.income_statement
    if is_df is None or "Net Income" not in is_df.columns:
        return False
    try:
        return float(is_df["Net Income"].iloc[0]) < 0
    except (ValueError, TypeError, IndexError):
        return False


def _debt_to_equity(ctx: ValuationContext) -> float | None:
    """Compute debt-to-equity ratio from balance sheet."""
    bs = ctx.financials.balance_sheet
    if bs is None:
        return None
    debt = _safe_get_col(bs, "Total Debt")
    equity = _safe_get_col(bs, "Total Stockholders Equity")
    if debt is None or equity is None or equity <= 0:
        return None
    return debt / equity


def _interest_coverage(ctx: ValuationContext) -> float | None:
    """Compute interest coverage ratio = Operating Income / Interest Expense."""
    oi = _safe_get_col(ctx.financials.income_statement, "Operating Income")
    ie = _safe_get_col(ctx.financials.income_statement, "Interest Expense")
    if oi is None or ie is None or ie == 0:
        return None
    return oi / abs(ie)


def _is_financial_by_sic(sic_code: str | None) -> bool:
    """Return True if the SIC code falls in the financial services range (6000-6799)."""
    if sic_code is None:
        return False
    try:
        code = int(str(sic_code).strip()[:4])
        for low, high in _FINANCIAL_SIC_RANGES:
            if low <= code <= high:
                return True
    except (ValueError, TypeError):
        pass
    return False


def _get_company_age(ctx: ValuationContext) -> int | None:
    """Get company age in years from key_stats, if available."""
    return ctx.financials.key_stats.get("company_age_years")


# ---------------------------------------------------------------------------
# Main classifier
# ---------------------------------------------------------------------------

def classify_company(ctx: ValuationContext) -> ClassificationResult:
    """Classify a company into a lifecycle stage based on its financials.

    Classification priority (checked in order):
      1. Financial   -- by SIC code (6000-6799) or Financial sector
      2. Distressed  -- consecutive losses + high leverage or low coverage
      3. Young       -- short operating history + negative earnings
      4. Growth      -- revenue growth > 20%
      5. Cyclical    -- cyclical sector (Energy, Materials, Industrials, etc.)
      6. Mature      -- default for stable, profitable companies

    Parameters
    ----------
    ctx : ValuationContext
        Context with populated financials and company info.

    Returns
    -------
    ClassificationResult
        Classification label, confidence score, reasoning string, and
        suggested valuation model.
    """
    reasons: list[str] = []
    scores: dict[str, float] = {
        "mature": 0.0,
        "growth": 0.0,
        "young": 0.0,
        "distressed": 0.0,
        "cyclical": 0.0,
        "financial": 0.0,
    }

    # ------------------------------------------------------------------
    # Rule 1: Financial firm detection (highest priority)
    # ------------------------------------------------------------------
    if _is_financial_by_sic(ctx.company.sic_code):
        scores["financial"] += 5.0
        reasons.append(
            f"SIC code {ctx.company.sic_code} is in the financial services range (6000-6799)."
        )

    if ctx.company.sector in _FINANCIAL_SECTORS:
        scores["financial"] += 3.0
        reasons.append(f"Sector '{ctx.company.sector}' indicates a financial firm.")

    if scores["financial"] >= 3.0:
        return ClassificationResult(
            classification="financial",
            confidence=min(0.95, 0.5 + scores["financial"] * 0.1),
            reasoning=" ".join(reasons),
            suggested_model=_MODEL_ROUTING["financial"],
        )

    # ------------------------------------------------------------------
    # Gather metrics used by remaining rules
    # ------------------------------------------------------------------
    revenue_growth = _compute_revenue_growth(ctx)
    consecutive_losses = _has_consecutive_losses(ctx)
    negative_earnings = _is_negative_earnings(ctx)
    de_ratio = _debt_to_equity(ctx)
    coverage = _interest_coverage(ctx)
    age = _get_company_age(ctx)

    # ------------------------------------------------------------------
    # Rule 2: Distressed detection
    # ------------------------------------------------------------------
    if consecutive_losses:
        scores["distressed"] += 2.0
        reasons.append("Consecutive periods of negative net income.")

    if de_ratio is not None and de_ratio > 3.0:
        scores["distressed"] += 2.0
        reasons.append(f"High debt-to-equity ratio ({de_ratio:.1f}x).")

    if coverage is not None and coverage < 1.0:
        scores["distressed"] += 2.0
        reasons.append(f"Interest coverage below 1.0x ({coverage:.2f}x).")

    if revenue_growth is not None and revenue_growth < -0.10:
        scores["distressed"] += 1.0
        reasons.append(f"Revenue declining ({revenue_growth:.1%} YoY).")

    if scores["distressed"] >= 4.0:
        return ClassificationResult(
            classification="distressed",
            confidence=min(0.90, 0.4 + scores["distressed"] * 0.1),
            reasoning=" ".join(reasons),
            suggested_model=_MODEL_ROUTING["distressed"],
        )

    # ------------------------------------------------------------------
    # Rule 3: Young company detection
    # ------------------------------------------------------------------
    is_young = False

    if age is not None and age <= 5:
        scores["young"] += 2.0
        reasons.append(f"Company is {age} years old (young).")
        is_young = True

    if negative_earnings and revenue_growth is not None and revenue_growth > 0.50:
        scores["young"] += 2.0
        reasons.append(
            f"Negative earnings with very high revenue growth ({revenue_growth:.1%}), "
            "suggesting early-stage company."
        )
        is_young = True

    if is_young and negative_earnings:
        scores["young"] += 1.0
        reasons.append("Pre-profit stage.")

    if scores["young"] >= 3.0:
        return ClassificationResult(
            classification="young",
            confidence=min(0.85, 0.4 + scores["young"] * 0.1),
            reasoning=" ".join(reasons),
            suggested_model=_MODEL_ROUTING["young"],
        )

    # ------------------------------------------------------------------
    # Rule 4: Growth detection
    # ------------------------------------------------------------------
    if revenue_growth is not None and revenue_growth > 0.20:
        scores["growth"] += 3.0
        reasons.append(f"Revenue growth of {revenue_growth:.1%} exceeds 20% threshold.")

    if revenue_growth is not None and 0.10 < revenue_growth <= 0.20:
        scores["growth"] += 1.5
        reasons.append(f"Moderate-high revenue growth ({revenue_growth:.1%}).")

    if not negative_earnings and revenue_growth is not None and revenue_growth > 0.10:
        scores["growth"] += 1.0
        reasons.append("Positive earnings combined with strong revenue growth.")

    if scores["growth"] >= 2.5:
        return ClassificationResult(
            classification="growth",
            confidence=min(0.85, 0.4 + scores["growth"] * 0.1),
            reasoning=" ".join(reasons),
            suggested_model=_MODEL_ROUTING["growth"],
        )

    # ------------------------------------------------------------------
    # Rule 5: Cyclical detection
    # ------------------------------------------------------------------
    if ctx.company.sector in _CYCLICAL_SECTORS:
        scores["cyclical"] += 3.0
        reasons.append(f"Sector '{ctx.company.sector}' is classified as cyclical.")

    if scores["cyclical"] >= 3.0 and not negative_earnings:
        return ClassificationResult(
            classification="cyclical",
            confidence=min(0.80, 0.4 + scores["cyclical"] * 0.1),
            reasoning=" ".join(reasons),
            suggested_model=_MODEL_ROUTING["cyclical"],
        )

    # ------------------------------------------------------------------
    # Rule 6: Mature (default)
    # ------------------------------------------------------------------
    if not negative_earnings:
        scores["mature"] += 2.0
        reasons.append("Positive earnings indicate established business.")

    if revenue_growth is not None and abs(revenue_growth) <= 0.10:
        scores["mature"] += 1.0
        reasons.append(f"Stable revenue growth ({revenue_growth:.1%}).")

    if de_ratio is not None and de_ratio < 2.0:
        scores["mature"] += 0.5
        reasons.append(f"Moderate leverage (D/E={de_ratio:.1f}x).")

    if not reasons:
        reasons.append(
            "Insufficient data for confident classification; defaulting to mature."
        )

    # Confidence is lower if we fell through to the default
    confidence = min(0.75, 0.2 + scores["mature"] * 0.1)
    has_data = ctx.financials.income_statement is not None
    confidence = max(confidence, 0.3 if has_data else 0.2)

    # Use gordon_growth for very stable mature companies (low growth, positive earnings)
    suggested = "gordon_growth" if (
        scores["mature"] >= 3.0
        and revenue_growth is not None
        and abs(revenue_growth) <= 0.05
        and not negative_earnings
    ) else "dcf_fcff"

    return ClassificationResult(
        classification="mature",
        confidence=confidence,
        reasoning=" ".join(reasons),
        suggested_model=suggested,
    )
