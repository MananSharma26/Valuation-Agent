"""Tests for reverse_dcf.py — implied growth rate and implied WACC solvers.

Strategy:
  1. Compute a reference DCF value with known inputs.
  2. Feed that value as market_price to the reverse solver.
  3. Verify the solver recovers the original assumption within tolerance.
"""

from __future__ import annotations

import pytest

from valuation.engines.dcf import fcff_valuation_v2
from valuation.engines.schedules import wacc_schedule, tax_schedule
from valuation.engines.reverse_dcf import (
    implied_growth_rate,
    implied_wacc,
    reverse_dcf_summary,
)


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def base_inputs():
    """Minimal but realistic base inputs shared across tests.

    Revenue $10,000, 20% margin, 20% tax, WACC 10%, S2C 2.5.
    """
    return dict(
        base_revenue=10_000,
        base_ebit=2_000,
        operating_margin=0.20,
        tax_rate=0.20,
        wacc=0.10,
        stable_wacc=0.08,
        sales_to_capital=2.5,
        stable_growth=0.03,
        stable_roc=0.12,
        cash=1_000,
        debt=500,
        shares_outstanding=100,
        n_years=10,
    )


def _dcf_at_growth(growth: float, inputs: dict) -> float:
    """Helper: compute DCF per-share value at a given revenue growth rate."""
    n = inputs["n_years"]
    n_constant = n // 2
    n_ramp = n - n_constant
    stable_growth = inputs["stable_growth"]

    growth_rates = []
    for t in range(1, n + 1):
        if t <= n_constant:
            growth_rates.append(growth)
        else:
            step = t - n_constant
            fraction = step / n_ramp
            growth_rates.append(growth + fraction * (stable_growth - growth))

    margins = [inputs["operating_margin"]] * n
    taxes = tax_schedule(inputs["tax_rate"], 0.25, n, n_constant)
    waccs = wacc_schedule(inputs["wacc"], inputs["stable_wacc"], n, n_constant)

    result = fcff_valuation_v2(
        base_revenue=inputs["base_revenue"],
        base_ebit=inputs["base_ebit"],
        revenue_growth_rates=growth_rates,
        operating_margins=margins,
        tax_rates=taxes,
        waccs=waccs,
        sales_to_capital=inputs["sales_to_capital"],
        stable_growth=inputs["stable_growth"],
        stable_roc=inputs["stable_roc"],
        stable_wacc=inputs["stable_wacc"],
        stable_tax_rate=0.25,
        cash=inputs["cash"],
        debt=inputs["debt"],
        shares_outstanding=inputs["shares_outstanding"],
    )
    return result["equity_value_per_share"]


def _dcf_at_wacc(wacc: float, growth_rates: list[float], inputs: dict) -> float:
    """Helper: compute DCF per-share value at a given WACC."""
    n = inputs["n_years"]
    n_constant = n // 2
    stable_w = max(wacc - 0.02, inputs["stable_growth"] + 0.001)
    waccs = wacc_schedule(wacc, stable_w, n, n_constant)
    margins = [inputs["operating_margin"]] * n
    taxes = tax_schedule(inputs["tax_rate"], 0.25, n, n_constant)

    result = fcff_valuation_v2(
        base_revenue=inputs["base_revenue"],
        base_ebit=inputs["base_ebit"],
        revenue_growth_rates=growth_rates,
        operating_margins=margins,
        tax_rates=taxes,
        waccs=waccs,
        sales_to_capital=inputs["sales_to_capital"],
        stable_growth=inputs["stable_growth"],
        stable_roc=inputs["stable_roc"],
        stable_wacc=stable_w,
        stable_tax_rate=0.25,
        cash=inputs["cash"],
        debt=inputs["debt"],
        shares_outstanding=inputs["shares_outstanding"],
    )
    return result["equity_value_per_share"]


# ---------------------------------------------------------------------------
# test_implied_growth_converges
# ---------------------------------------------------------------------------

class TestImpliedGrowthConverges:
    """Verify binary search recovers the original growth rate from a DCF-derived price."""

    def test_implied_growth_15pct(self, base_inputs):
        """Known case: growth=15% → price X. Solver should find ~15%."""
        known_growth = 0.15
        reference_price = _dcf_at_growth(known_growth, base_inputs)

        result = implied_growth_rate(
            market_price=reference_price,
            base_revenue=base_inputs["base_revenue"],
            base_ebit=base_inputs["base_ebit"],
            operating_margin=base_inputs["operating_margin"],
            tax_rate=base_inputs["tax_rate"],
            wacc=base_inputs["wacc"],
            stable_wacc=base_inputs["stable_wacc"],
            sales_to_capital=base_inputs["sales_to_capital"],
            stable_growth=base_inputs["stable_growth"],
            stable_roc=base_inputs["stable_roc"],
            cash=base_inputs["cash"],
            debt=base_inputs["debt"],
            shares_outstanding=base_inputs["shares_outstanding"],
            n_years=base_inputs["n_years"],
            tolerance=0.50,
        )

        assert result["converged"] is True, f"Did not converge: {result}"
        assert result["implied_growth"] == pytest.approx(known_growth, abs=0.02), (
            f"Expected ~{known_growth:.2%}, got {result['implied_growth']:.2%}"
        )
        assert abs(result["implied_value"] - reference_price) < 0.50

    def test_implied_growth_25pct(self, base_inputs):
        """Solver handles high growth (25%) correctly."""
        known_growth = 0.25
        reference_price = _dcf_at_growth(known_growth, base_inputs)

        result = implied_growth_rate(
            market_price=reference_price,
            base_revenue=base_inputs["base_revenue"],
            base_ebit=base_inputs["base_ebit"],
            operating_margin=base_inputs["operating_margin"],
            tax_rate=base_inputs["tax_rate"],
            wacc=base_inputs["wacc"],
            stable_wacc=base_inputs["stable_wacc"],
            sales_to_capital=base_inputs["sales_to_capital"],
            stable_growth=base_inputs["stable_growth"],
            stable_roc=base_inputs["stable_roc"],
            cash=base_inputs["cash"],
            debt=base_inputs["debt"],
            shares_outstanding=base_inputs["shares_outstanding"],
            n_years=base_inputs["n_years"],
            tolerance=0.50,
        )

        assert result["converged"] is True, f"Did not converge: {result}"
        assert result["implied_growth"] == pytest.approx(known_growth, abs=0.02)

    def test_convergence_result_keys(self, base_inputs):
        """Result dict must contain all required keys."""
        reference_price = _dcf_at_growth(0.10, base_inputs)

        result = implied_growth_rate(
            market_price=reference_price,
            base_revenue=base_inputs["base_revenue"],
            base_ebit=base_inputs["base_ebit"],
            operating_margin=base_inputs["operating_margin"],
            tax_rate=base_inputs["tax_rate"],
            wacc=base_inputs["wacc"],
            stable_wacc=base_inputs["stable_wacc"],
            sales_to_capital=base_inputs["sales_to_capital"],
            stable_growth=base_inputs["stable_growth"],
            stable_roc=base_inputs["stable_roc"],
            cash=base_inputs["cash"],
            debt=base_inputs["debt"],
            shares_outstanding=base_inputs["shares_outstanding"],
        )

        required_keys = {"implied_growth", "implied_value", "iterations", "converged", "summary"}
        assert required_keys.issubset(result.keys())

    def test_iterations_positive(self, base_inputs):
        """At least one iteration must be reported."""
        reference_price = _dcf_at_growth(0.12, base_inputs)

        result = implied_growth_rate(
            market_price=reference_price,
            base_revenue=base_inputs["base_revenue"],
            base_ebit=base_inputs["base_ebit"],
            operating_margin=base_inputs["operating_margin"],
            tax_rate=base_inputs["tax_rate"],
            wacc=base_inputs["wacc"],
            stable_wacc=base_inputs["stable_wacc"],
            sales_to_capital=base_inputs["sales_to_capital"],
            stable_growth=base_inputs["stable_growth"],
            stable_roc=base_inputs["stable_roc"],
            cash=base_inputs["cash"],
            debt=base_inputs["debt"],
            shares_outstanding=base_inputs["shares_outstanding"],
        )

        assert result["iterations"] >= 1
        assert result["iterations"] <= 50


# ---------------------------------------------------------------------------
# test_implied_wacc_converges
# ---------------------------------------------------------------------------

class TestImpliedWaccConverges:
    """Verify binary search recovers the original WACC from a DCF-derived price."""

    def _growth_rates_10pct(self, n=10):
        """Flat 10% growth schedule for WACC tests."""
        stable = 0.03
        n_constant = n // 2
        n_ramp = n - n_constant
        rates = []
        for t in range(1, n + 1):
            if t <= n_constant:
                rates.append(0.10)
            else:
                step = t - n_constant
                fraction = step / n_ramp
                rates.append(0.10 + fraction * (stable - 0.10))
        return rates

    def test_implied_wacc_10pct(self, base_inputs):
        """Known case: WACC=10% → price X. Solver should find ~10%."""
        known_wacc = 0.10
        growth_rates = self._growth_rates_10pct()
        reference_price = _dcf_at_wacc(known_wacc, growth_rates, base_inputs)

        result = implied_wacc(
            market_price=reference_price,
            base_revenue=base_inputs["base_revenue"],
            base_ebit=base_inputs["base_ebit"],
            revenue_growth_rates=growth_rates,
            operating_margin=base_inputs["operating_margin"],
            tax_rate=base_inputs["tax_rate"],
            sales_to_capital=base_inputs["sales_to_capital"],
            stable_growth=base_inputs["stable_growth"],
            stable_roc=base_inputs["stable_roc"],
            cash=base_inputs["cash"],
            debt=base_inputs["debt"],
            shares_outstanding=base_inputs["shares_outstanding"],
            n_years=base_inputs["n_years"],
            tolerance=0.50,
        )

        assert result["converged"] is True, f"Did not converge: {result}"
        assert result["implied_wacc"] == pytest.approx(known_wacc, abs=0.02), (
            f"Expected ~{known_wacc:.2%}, got {result['implied_wacc']:.2%}"
        )
        assert abs(result["implied_value"] - reference_price) < 0.50

    def test_implied_wacc_12pct(self, base_inputs):
        """Solver handles WACC=12% correctly."""
        known_wacc = 0.12
        growth_rates = self._growth_rates_10pct()
        reference_price = _dcf_at_wacc(known_wacc, growth_rates, base_inputs)

        result = implied_wacc(
            market_price=reference_price,
            base_revenue=base_inputs["base_revenue"],
            base_ebit=base_inputs["base_ebit"],
            revenue_growth_rates=growth_rates,
            operating_margin=base_inputs["operating_margin"],
            tax_rate=base_inputs["tax_rate"],
            sales_to_capital=base_inputs["sales_to_capital"],
            stable_growth=base_inputs["stable_growth"],
            stable_roc=base_inputs["stable_roc"],
            cash=base_inputs["cash"],
            debt=base_inputs["debt"],
            shares_outstanding=base_inputs["shares_outstanding"],
            n_years=base_inputs["n_years"],
            tolerance=0.50,
        )

        assert result["converged"] is True, f"Did not converge: {result}"
        assert result["implied_wacc"] == pytest.approx(known_wacc, abs=0.02)

    def test_wacc_result_keys(self, base_inputs):
        """WACC result dict must contain all required keys."""
        growth_rates = self._growth_rates_10pct()
        reference_price = _dcf_at_wacc(0.10, growth_rates, base_inputs)

        result = implied_wacc(
            market_price=reference_price,
            base_revenue=base_inputs["base_revenue"],
            base_ebit=base_inputs["base_ebit"],
            revenue_growth_rates=growth_rates,
            operating_margin=base_inputs["operating_margin"],
            tax_rate=base_inputs["tax_rate"],
            sales_to_capital=base_inputs["sales_to_capital"],
            stable_growth=base_inputs["stable_growth"],
            stable_roc=base_inputs["stable_roc"],
            cash=base_inputs["cash"],
            debt=base_inputs["debt"],
            shares_outstanding=base_inputs["shares_outstanding"],
        )

        required_keys = {"implied_wacc", "implied_value", "iterations", "converged", "summary"}
        assert required_keys.issubset(result.keys())


# ---------------------------------------------------------------------------
# test_high_price_implies_high_growth
# ---------------------------------------------------------------------------

class TestHighPriceImpliesHighGrowth:
    """If market price > our DCF value, implied growth must exceed our growth rate."""

    def test_premium_price_implies_higher_growth(self, base_inputs):
        """Price 30% above DCF → implied growth > our_growth."""
        our_growth = 0.12
        our_value = _dcf_at_growth(our_growth, base_inputs)
        premium_price = our_value * 1.30  # market pays 30% more than our estimate

        result = implied_growth_rate(
            market_price=premium_price,
            base_revenue=base_inputs["base_revenue"],
            base_ebit=base_inputs["base_ebit"],
            operating_margin=base_inputs["operating_margin"],
            tax_rate=base_inputs["tax_rate"],
            wacc=base_inputs["wacc"],
            stable_wacc=base_inputs["stable_wacc"],
            sales_to_capital=base_inputs["sales_to_capital"],
            stable_growth=base_inputs["stable_growth"],
            stable_roc=base_inputs["stable_roc"],
            cash=base_inputs["cash"],
            debt=base_inputs["debt"],
            shares_outstanding=base_inputs["shares_outstanding"],
            n_years=base_inputs["n_years"],
            tolerance=0.50,
        )

        # The implied growth must be strictly above our growth assumption
        assert result["implied_growth"] > our_growth, (
            f"Expected implied growth > {our_growth:.2%}, "
            f"got {result['implied_growth']:.2%} for a {premium_price:.2f} price "
            f"(our value = {our_value:.2f})"
        )

    def test_large_premium_implies_much_higher_growth(self, base_inputs):
        """Price 60% above DCF → implied growth meaningfully higher than our_growth."""
        our_growth = 0.10
        our_value = _dcf_at_growth(our_growth, base_inputs)
        premium_price = our_value * 1.60

        result = implied_growth_rate(
            market_price=premium_price,
            base_revenue=base_inputs["base_revenue"],
            base_ebit=base_inputs["base_ebit"],
            operating_margin=base_inputs["operating_margin"],
            tax_rate=base_inputs["tax_rate"],
            wacc=base_inputs["wacc"],
            stable_wacc=base_inputs["stable_wacc"],
            sales_to_capital=base_inputs["sales_to_capital"],
            stable_growth=base_inputs["stable_growth"],
            stable_roc=base_inputs["stable_roc"],
            cash=base_inputs["cash"],
            debt=base_inputs["debt"],
            shares_outstanding=base_inputs["shares_outstanding"],
            n_years=base_inputs["n_years"],
            tolerance=0.50,
        )

        # At 60% premium, implied growth should be noticeably higher (at least 3pp)
        assert result["implied_growth"] > our_growth + 0.03, (
            f"Expected implied growth > {our_growth + 0.03:.2%}, "
            f"got {result['implied_growth']:.2%}"
        )


# ---------------------------------------------------------------------------
# test_low_price_implies_low_growth
# ---------------------------------------------------------------------------

class TestLowPriceImpliesLowGrowth:
    """If market price < our DCF value, implied growth must be below our growth rate."""

    def test_discount_price_implies_lower_growth(self, base_inputs):
        """Price 30% below DCF → implied growth < our_growth."""
        our_growth = 0.15
        our_value = _dcf_at_growth(our_growth, base_inputs)
        discount_price = our_value * 0.70  # market pays 30% less than our estimate

        result = implied_growth_rate(
            market_price=discount_price,
            base_revenue=base_inputs["base_revenue"],
            base_ebit=base_inputs["base_ebit"],
            operating_margin=base_inputs["operating_margin"],
            tax_rate=base_inputs["tax_rate"],
            wacc=base_inputs["wacc"],
            stable_wacc=base_inputs["stable_wacc"],
            sales_to_capital=base_inputs["sales_to_capital"],
            stable_growth=base_inputs["stable_growth"],
            stable_roc=base_inputs["stable_roc"],
            cash=base_inputs["cash"],
            debt=base_inputs["debt"],
            shares_outstanding=base_inputs["shares_outstanding"],
            n_years=base_inputs["n_years"],
            tolerance=0.50,
        )

        assert result["implied_growth"] < our_growth, (
            f"Expected implied growth < {our_growth:.2%}, "
            f"got {result['implied_growth']:.2%} for a discounted price"
        )

    def test_large_discount_implies_much_lower_growth(self, base_inputs):
        """Price 50% below DCF → implied growth meaningfully lower than our_growth."""
        our_growth = 0.20
        our_value = _dcf_at_growth(our_growth, base_inputs)
        discount_price = our_value * 0.50

        result = implied_growth_rate(
            market_price=discount_price,
            base_revenue=base_inputs["base_revenue"],
            base_ebit=base_inputs["base_ebit"],
            operating_margin=base_inputs["operating_margin"],
            tax_rate=base_inputs["tax_rate"],
            wacc=base_inputs["wacc"],
            stable_wacc=base_inputs["stable_wacc"],
            sales_to_capital=base_inputs["sales_to_capital"],
            stable_growth=base_inputs["stable_growth"],
            stable_roc=base_inputs["stable_roc"],
            cash=base_inputs["cash"],
            debt=base_inputs["debt"],
            shares_outstanding=base_inputs["shares_outstanding"],
            n_years=base_inputs["n_years"],
            tolerance=0.50,
        )

        # At 50% discount, implied growth should be meaningfully lower (at least 5pp)
        assert result["implied_growth"] < our_growth - 0.05, (
            f"Expected implied growth < {our_growth - 0.05:.2%}, "
            f"got {result['implied_growth']:.2%}"
        )


# ---------------------------------------------------------------------------
# test_summary_output
# ---------------------------------------------------------------------------

class TestSummaryOutput:
    """reverse_dcf_summary should produce a non-empty, structured string."""

    def test_summary_non_empty(self, base_inputs):
        """Summary must be a non-empty string."""
        our_growth = 0.12
        our_wacc = 0.10
        our_value = _dcf_at_growth(our_growth, base_inputs)
        market_price = our_value * 1.20

        ig_result = implied_growth_rate(
            market_price=market_price,
            base_revenue=base_inputs["base_revenue"],
            base_ebit=base_inputs["base_ebit"],
            operating_margin=base_inputs["operating_margin"],
            tax_rate=base_inputs["tax_rate"],
            wacc=base_inputs["wacc"],
            stable_wacc=base_inputs["stable_wacc"],
            sales_to_capital=base_inputs["sales_to_capital"],
            stable_growth=base_inputs["stable_growth"],
            stable_roc=base_inputs["stable_roc"],
            cash=base_inputs["cash"],
            debt=base_inputs["debt"],
            shares_outstanding=base_inputs["shares_outstanding"],
        )

        n = base_inputs["n_years"]
        n_constant = n // 2
        n_ramp = n - n_constant
        stable = base_inputs["stable_growth"]
        growth_rates = []
        for t in range(1, n + 1):
            if t <= n_constant:
                growth_rates.append(our_growth)
            else:
                step = t - n_constant
                fraction = step / n_ramp
                growth_rates.append(our_growth + fraction * (stable - our_growth))

        iw_result = implied_wacc(
            market_price=market_price,
            base_revenue=base_inputs["base_revenue"],
            base_ebit=base_inputs["base_ebit"],
            revenue_growth_rates=growth_rates,
            operating_margin=base_inputs["operating_margin"],
            tax_rate=base_inputs["tax_rate"],
            sales_to_capital=base_inputs["sales_to_capital"],
            stable_growth=base_inputs["stable_growth"],
            stable_roc=base_inputs["stable_roc"],
            cash=base_inputs["cash"],
            debt=base_inputs["debt"],
            shares_outstanding=base_inputs["shares_outstanding"],
        )

        summary = reverse_dcf_summary(
            market_price=market_price,
            our_value=our_value,
            our_growth=our_growth,
            our_wacc=our_wacc,
            implied_growth_result=ig_result,
            implied_wacc_result=iw_result,
        )

        assert isinstance(summary, str)
        assert len(summary) > 0

    def test_summary_contains_market_price(self, base_inputs):
        """Summary string must include the market price."""
        our_value = _dcf_at_growth(0.10, base_inputs)
        market_price = our_value * 1.10

        ig_result = {"converged": False, "implied_growth": 0.12, "summary": "N/A"}
        iw_result = {"converged": False, "implied_wacc": 0.09, "summary": "N/A"}

        summary = reverse_dcf_summary(
            market_price=market_price,
            our_value=our_value,
            our_growth=0.10,
            our_wacc=0.10,
            implied_growth_result=ig_result,
            implied_wacc_result=iw_result,
        )

        assert "Market price" in summary

    def test_summary_contains_our_value(self, base_inputs):
        """Summary string must mention our DCF value."""
        our_value = _dcf_at_growth(0.10, base_inputs)
        market_price = our_value * 1.10

        ig_result = {"converged": False, "implied_growth": 0.12, "summary": "N/A"}
        iw_result = {"converged": False, "implied_wacc": 0.09, "summary": "N/A"}

        summary = reverse_dcf_summary(
            market_price=market_price,
            our_value=our_value,
            our_growth=0.10,
            our_wacc=0.10,
            implied_growth_result=ig_result,
            implied_wacc_result=iw_result,
        )

        assert "Our DCF value" in summary

    def test_summary_premium_market_says_more_growth(self, base_inputs):
        """When market price > our value, summary should say market expects MORE growth."""
        our_growth = 0.10
        our_value = _dcf_at_growth(our_growth, base_inputs)
        market_price = our_value * 1.30

        ig_result = implied_growth_rate(
            market_price=market_price,
            base_revenue=base_inputs["base_revenue"],
            base_ebit=base_inputs["base_ebit"],
            operating_margin=base_inputs["operating_margin"],
            tax_rate=base_inputs["tax_rate"],
            wacc=base_inputs["wacc"],
            stable_wacc=base_inputs["stable_wacc"],
            sales_to_capital=base_inputs["sales_to_capital"],
            stable_growth=base_inputs["stable_growth"],
            stable_roc=base_inputs["stable_roc"],
            cash=base_inputs["cash"],
            debt=base_inputs["debt"],
            shares_outstanding=base_inputs["shares_outstanding"],
        )
        iw_result = {"converged": False, "implied_wacc": 0.09, "summary": "N/A"}

        summary = reverse_dcf_summary(
            market_price=market_price,
            our_value=our_value,
            our_growth=our_growth,
            our_wacc=0.10,
            implied_growth_result=ig_result,
            implied_wacc_result=iw_result,
        )

        assert "MORE" in summary

    def test_summary_discount_market_says_less_growth(self, base_inputs):
        """When market price < our value, summary should say market expects LESS growth."""
        our_growth = 0.20
        our_value = _dcf_at_growth(our_growth, base_inputs)
        market_price = our_value * 0.70

        ig_result = implied_growth_rate(
            market_price=market_price,
            base_revenue=base_inputs["base_revenue"],
            base_ebit=base_inputs["base_ebit"],
            operating_margin=base_inputs["operating_margin"],
            tax_rate=base_inputs["tax_rate"],
            wacc=base_inputs["wacc"],
            stable_wacc=base_inputs["stable_wacc"],
            sales_to_capital=base_inputs["sales_to_capital"],
            stable_growth=base_inputs["stable_growth"],
            stable_roc=base_inputs["stable_roc"],
            cash=base_inputs["cash"],
            debt=base_inputs["debt"],
            shares_outstanding=base_inputs["shares_outstanding"],
        )
        iw_result = {"converged": False, "implied_wacc": 0.11, "summary": "N/A"}

        summary = reverse_dcf_summary(
            market_price=market_price,
            our_value=our_value,
            our_growth=our_growth,
            our_wacc=0.10,
            implied_growth_result=ig_result,
            implied_wacc_result=iw_result,
        )

        assert "LESS" in summary

    def test_summary_wacc_direction_lower(self, base_inputs):
        """When implied WACC < our WACC, summary should say market uses LOWER rate."""
        ig_result = {"converged": False, "implied_growth": 0.12, "summary": "N/A"}
        iw_result = {"converged": True, "implied_wacc": 0.07, "implied_value": 150.0}
        our_wacc = 0.10

        summary = reverse_dcf_summary(
            market_price=100.0,
            our_value=80.0,
            our_growth=0.10,
            our_wacc=our_wacc,
            implied_growth_result=ig_result,
            implied_wacc_result=iw_result,
        )

        assert "LOWER" in summary

    def test_summary_wacc_direction_higher(self, base_inputs):
        """When implied WACC > our WACC, summary should say market uses HIGHER rate."""
        ig_result = {"converged": False, "implied_growth": 0.08, "summary": "N/A"}
        iw_result = {"converged": True, "implied_wacc": 0.13, "implied_value": 60.0}
        our_wacc = 0.10

        summary = reverse_dcf_summary(
            market_price=100.0,
            our_value=120.0,
            our_growth=0.12,
            our_wacc=our_wacc,
            implied_growth_result=ig_result,
            implied_wacc_result=iw_result,
        )

        assert "HIGHER" in summary


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    """Edge cases and robustness checks."""

    def test_implied_growth_tolerance_respected(self, base_inputs):
        """Converged result must be within the specified tolerance."""
        reference_price = _dcf_at_growth(0.12, base_inputs)

        result = implied_growth_rate(
            market_price=reference_price,
            base_revenue=base_inputs["base_revenue"],
            base_ebit=base_inputs["base_ebit"],
            operating_margin=base_inputs["operating_margin"],
            tax_rate=base_inputs["tax_rate"],
            wacc=base_inputs["wacc"],
            stable_wacc=base_inputs["stable_wacc"],
            sales_to_capital=base_inputs["sales_to_capital"],
            stable_growth=base_inputs["stable_growth"],
            stable_roc=base_inputs["stable_roc"],
            cash=base_inputs["cash"],
            debt=base_inputs["debt"],
            shares_outstanding=base_inputs["shares_outstanding"],
            tolerance=0.50,
        )

        if result["converged"]:
            assert abs(result["implied_value"] - reference_price) < 0.50

    def test_implied_wacc_tolerance_respected(self, base_inputs):
        """Converged WACC result must be within tolerance."""
        n = base_inputs["n_years"]
        n_constant = n // 2
        n_ramp = n - n_constant
        stable = base_inputs["stable_growth"]
        growth_rates = []
        for t in range(1, n + 1):
            if t <= n_constant:
                growth_rates.append(0.10)
            else:
                step = t - n_constant
                fraction = step / n_ramp
                growth_rates.append(0.10 + fraction * (stable - 0.10))

        reference_price = _dcf_at_wacc(0.10, growth_rates, base_inputs)

        result = implied_wacc(
            market_price=reference_price,
            base_revenue=base_inputs["base_revenue"],
            base_ebit=base_inputs["base_ebit"],
            revenue_growth_rates=growth_rates,
            operating_margin=base_inputs["operating_margin"],
            tax_rate=base_inputs["tax_rate"],
            sales_to_capital=base_inputs["sales_to_capital"],
            stable_growth=base_inputs["stable_growth"],
            stable_roc=base_inputs["stable_roc"],
            cash=base_inputs["cash"],
            debt=base_inputs["debt"],
            shares_outstanding=base_inputs["shares_outstanding"],
            tolerance=0.50,
        )

        if result["converged"]:
            assert abs(result["implied_value"] - reference_price) < 0.50

    def test_summary_with_non_converged_results(self):
        """reverse_dcf_summary must not crash when both solvers report non-convergence."""
        ig = {"converged": False, "implied_growth": 0.30, "summary": "Market implies >50% growth"}
        iw = {"converged": False, "implied_wacc": 0.04, "summary": "Market implies WACC ~4%"}

        summary = reverse_dcf_summary(
            market_price=500.0,
            our_value=200.0,
            our_growth=0.15,
            our_wacc=0.10,
            implied_growth_result=ig,
            implied_wacc_result=iw,
        )

        assert isinstance(summary, str)
        assert len(summary) > 0
        assert "Market price" in summary
