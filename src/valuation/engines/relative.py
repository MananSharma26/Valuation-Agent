"""
relative.py -- Relative (multiples-based) valuation engine.

Computes implied equity values from industry multiples:
  - P/E: implied_value = EPS * industry_PE
  - EV/EBITDA: implied_EV = EBITDA * industry_EV_EBITDA, then bridge to equity
  - P/BV: implied_value = BVPS * industry_PBV
  - P/S: implied_value = Revenue_per_share * industry_PS

All math is deterministic. No LLM calls. No consensus estimates.

Methodology: Damodaran (Investment Valuation, 3rd ed., Ch. 17-20)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from statistics import median
from typing import Any


@dataclass
class RelativeResult:
    """Result of a relative valuation across multiple multiples."""

    pe_value: float | None = None
    ev_ebitda_value: float | None = None
    pbv_value: float | None = None
    ps_value: float | None = None
    composite_value: float | None = None
    discount_to_composite: float | None = None
    market_price: float | None = None
    methods_used: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "pe_value": self.pe_value,
            "ev_ebitda_value": self.ev_ebitda_value,
            "pbv_value": self.pbv_value,
            "ps_value": self.ps_value,
            "composite_value": self.composite_value,
            "discount_to_composite": self.discount_to_composite,
            "market_price": self.market_price,
            "methods_used": self.methods_used,
        }


# ---------------------------------------------------------------------------
# Individual multiple valuation functions
# ---------------------------------------------------------------------------

def pe_implied_value(
    eps: float,
    industry_pe: float | None,
) -> float | None:
    """Compute implied equity value per share from P/E multiple.

    Formula: Implied Value = EPS * Industry PE

    Parameters
    ----------
    eps : float
        Earnings per share (trailing or forward). Must be positive.
    industry_pe : float or None
        Industry average P/E ratio from Damodaran.

    Returns
    -------
    float or None
        Implied value per share, or None if inputs are invalid.
    """
    if industry_pe is None or industry_pe <= 0:
        return None
    if eps is None or eps <= 0:
        return None
    return eps * industry_pe


def ev_ebitda_implied_value(
    ebitda: float | None,
    industry_ev_ebitda: float | None,
    debt: float,
    cash: float,
    shares_outstanding: float,
) -> float | None:
    """Compute implied equity value per share from EV/EBITDA multiple.

    Formula:
        Implied EV = EBITDA * Industry EV/EBITDA
        Implied Equity = EV - Debt + Cash
        Implied Per Share = Equity / Shares

    Parameters
    ----------
    ebitda : float or None
        Trailing EBITDA. Must be positive.
    industry_ev_ebitda : float or None
        Industry average EV/EBITDA from Damodaran.
    debt : float
        Total debt (book or market value).
    cash : float
        Cash and near-cash equivalents.
    shares_outstanding : float
        Diluted shares outstanding.

    Returns
    -------
    float or None
        Implied equity value per share, or None if inputs are invalid.
    """
    if industry_ev_ebitda is None or industry_ev_ebitda <= 0:
        return None
    if ebitda is None or ebitda <= 0:
        return None
    if shares_outstanding is None or shares_outstanding <= 0:
        return None
    implied_ev = ebitda * industry_ev_ebitda
    implied_equity = implied_ev - debt + cash
    return implied_equity / shares_outstanding


def pbv_implied_value(
    book_value_per_share: float | None,
    industry_pbv: float | None,
) -> float | None:
    """Compute implied equity value per share from P/BV multiple.

    Formula: Implied Value = BVPS * Industry P/BV

    Parameters
    ----------
    book_value_per_share : float or None
        Book value per share. Must be positive.
    industry_pbv : float or None
        Industry average price-to-book ratio from Damodaran.

    Returns
    -------
    float or None
        Implied value per share, or None if inputs are invalid.
    """
    if industry_pbv is None or industry_pbv <= 0:
        return None
    if book_value_per_share is None or book_value_per_share <= 0:
        return None
    return book_value_per_share * industry_pbv


def ps_implied_value(
    revenue_per_share: float | None,
    industry_ps: float | None,
) -> float | None:
    """Compute implied equity value per share from P/S multiple.

    Formula: Implied Value = Revenue Per Share * Industry P/S

    Parameters
    ----------
    revenue_per_share : float or None
        Revenue per share. Must be positive.
    industry_ps : float or None
        Industry average price-to-sales ratio from Damodaran.

    Returns
    -------
    float or None
        Implied value per share, or None if inputs are invalid.
    """
    if industry_ps is None or industry_ps <= 0:
        return None
    if revenue_per_share is None or revenue_per_share <= 0:
        return None
    return revenue_per_share * industry_ps


# ---------------------------------------------------------------------------
# Composite relative valuation
# ---------------------------------------------------------------------------

def relative_valuation(
    eps: float | None,
    ebitda: float | None,
    book_value_per_share: float | None,
    revenue_per_share: float | None,
    industry_multiples: dict[str, float | None],
    debt: float,
    cash: float,
    shares_outstanding: float,
    market_price: float | None = None,
) -> RelativeResult:
    """Compute implied values from all available multiples and produce a composite.

    The composite value is the median of all non-None implied values. This is
    more robust than a mean since it is less affected by outlier multiples.

    Parameters
    ----------
    eps : float or None
        Earnings per share (trailing).
    ebitda : float or None
        Trailing EBITDA (total, not per share).
    book_value_per_share : float or None
        Book value per share.
    revenue_per_share : float or None
        Revenue per share (total revenue / shares outstanding).
    industry_multiples : dict
        Dict with keys: current_pe, ev_ebitda, pbv, ps (from load_industry_benchmarks).
    debt : float
        Total debt.
    cash : float
        Cash and equivalents.
    shares_outstanding : float
        Diluted shares.
    market_price : float or None
        Current market price per share (for discount/premium calculation).

    Returns
    -------
    RelativeResult
        Dataclass with per-multiple implied values, composite, and discount/premium.
    """
    result = RelativeResult(market_price=market_price)

    # P/E
    result.pe_value = pe_implied_value(
        eps=eps,
        industry_pe=industry_multiples.get("current_pe"),
    )
    if result.pe_value is not None:
        result.methods_used.append("PE")

    # EV/EBITDA
    result.ev_ebitda_value = ev_ebitda_implied_value(
        ebitda=ebitda,
        industry_ev_ebitda=industry_multiples.get("ev_ebitda"),
        debt=debt,
        cash=cash,
        shares_outstanding=shares_outstanding,
    )
    if result.ev_ebitda_value is not None:
        result.methods_used.append("EV/EBITDA")

    # P/BV
    result.pbv_value = pbv_implied_value(
        book_value_per_share=book_value_per_share,
        industry_pbv=industry_multiples.get("pbv"),
    )
    if result.pbv_value is not None:
        result.methods_used.append("PBV")

    # P/S
    result.ps_value = ps_implied_value(
        revenue_per_share=revenue_per_share,
        industry_ps=industry_multiples.get("ps"),
    )
    if result.ps_value is not None:
        result.methods_used.append("PS")

    # Composite: median of all non-None values
    values = [
        v
        for v in [
            result.pe_value,
            result.ev_ebitda_value,
            result.pbv_value,
            result.ps_value,
        ]
        if v is not None
    ]
    if values:
        result.composite_value = median(values)

    # Discount/premium to composite
    if result.composite_value is not None and market_price is not None and market_price > 0:
        result.discount_to_composite = (
            result.composite_value - market_price
        ) / market_price

    return result
