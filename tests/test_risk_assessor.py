"""
Tests for valuation.agents.risk_assessor

All expected values are derived from Damodaran methodology.
Verification anchors:
  - Goldman:  Ke = 10.40%  (Rf=4.1%, Beta=1.4, ERP=4.5%)
  - ConEd:    Ke =  7.70%  (Rf=4.1%, Beta=0.8, ERP=4.5%)
  - 3M:       Ke ~  9.16%, WACC ~ 8.65%
              (Rf=3.7%, ERP=4.0%, Bl=1.3638, D/E=0.088, t=35%, ICR~5.0)
"""

import pytest
from valuation.agents.risk_assessor import (
    get_synthetic_rating,
    get_default_spread,
    compute_cost_of_debt,
    compute_cost_of_equity,
    unlever_beta,
    relever_beta,
    compute_wacc,
)


# ---------------------------------------------------------------------------
# Synthetic rating — large firm
# ---------------------------------------------------------------------------

class TestSyntheticRatingLargeFirm:
    def test_high_coverage_gives_aaa(self):
        rating, spread = get_synthetic_rating(10.0, "large")
        assert rating == "Aaa/AAA"
        assert spread == pytest.approx(0.0040)

    def test_boundary_exactly_8_5_gives_aaa(self):
        # ICR >= 8.5 → Aaa/AAA (upper bound of Aa2/AA is 8.5, exclusive)
        rating, spread = get_synthetic_rating(8.5, "large")
        assert rating == "Aaa/AAA"

    def test_medium_coverage_bbb(self):
        # ICR 2.6 falls in 2.5–3.0 → Baa2/BBB
        rating, spread = get_synthetic_rating(2.6, "large")
        assert rating == "Baa2/BBB"
        assert spread == pytest.approx(0.0111)

    def test_low_coverage_b_minus(self):
        # ICR 1.3 falls in 1.25–1.5 → B3/B-
        rating, spread = get_synthetic_rating(1.3, "large")
        assert rating == "B3/B-"
        assert spread == pytest.approx(0.0509)

    def test_negative_coverage_gives_d(self):
        # Negative ICR (losses) → D2/D
        rating, spread = get_synthetic_rating(-5.0, "large")
        assert rating == "D2/D"
        assert spread == pytest.approx(0.1900)

    def test_a_minus_range(self):
        # ICR 3.5 falls in 3.0–4.25 → A3/A-
        rating, spread = get_synthetic_rating(3.5, "large")
        assert rating == "A3/A-"
        assert spread == pytest.approx(0.0089)


# ---------------------------------------------------------------------------
# Synthetic rating — small firm
# ---------------------------------------------------------------------------

class TestSyntheticRatingSmallFirm:
    def test_high_coverage_gives_aaa(self):
        # Small firm: >12.5 → Aaa/AAA
        rating, spread = get_synthetic_rating(15.0, "small")
        assert rating == "Aaa/AAA"
        assert spread == pytest.approx(0.0040)

    def test_same_icr_gives_lower_rating_than_large(self):
        # ICR=5.0 → A2/A for large, but A3/A- for small (needs higher coverage)
        large_rating, _ = get_synthetic_rating(5.0, "large")
        small_rating, _ = get_synthetic_rating(5.0, "small")
        assert large_rating == "A2/A"
        assert small_rating == "A3/A-"

    def test_low_coverage_gives_d(self):
        rating, spread = get_synthetic_rating(0.3, "small")
        assert rating == "D2/D"
        assert spread == pytest.approx(0.1900)

    def test_bb_range(self):
        # ICR 3.2 falls in 3.0–3.5 → Ba2/BB for small firm
        rating, spread = get_synthetic_rating(3.2, "small")
        assert rating == "Ba2/BB"
        assert spread == pytest.approx(0.0184)


# ---------------------------------------------------------------------------
# Synthetic rating — financial firm
# ---------------------------------------------------------------------------

class TestSyntheticRatingFinancialFirm:
    def test_high_coverage_gives_aaa(self):
        # Financial: >3.0 → Aaa/AAA
        rating, spread = get_synthetic_rating(4.0, "financial")
        assert rating == "Aaa/AAA"
        assert spread == pytest.approx(0.0040)

    def test_low_coverage_gives_d(self):
        # ICR 0.03 → D2/D for financial firm
        rating, spread = get_synthetic_rating(0.03, "financial")
        assert rating == "D2/D"
        assert spread == pytest.approx(0.1900)

    def test_bbb_range(self):
        # ICR 1.0 falls in 0.9–1.2 → Baa2/BBB
        rating, spread = get_synthetic_rating(1.0, "financial")
        assert rating == "Baa2/BBB"
        assert spread == pytest.approx(0.0111)

    def test_much_lower_threshold_than_large(self):
        # ICR=1.5 sits in [1.5, 2.0) → A2/A for financial, but only B2/B for large
        # This confirms financial firms receive far higher ratings at the same ICR
        financial_rating, _ = get_synthetic_rating(1.5, "financial")
        large_rating, _ = get_synthetic_rating(1.5, "large")
        assert financial_rating == "A2/A"
        assert large_rating == "B2/B"


# ---------------------------------------------------------------------------
# Cost of debt
# ---------------------------------------------------------------------------

class TestCostOfDebt:
    def test_cost_of_debt_equals_rf_plus_spread(self):
        rf = 0.037
        icr = 5.0       # large firm → A2/A, spread=0.78%
        kd = compute_cost_of_debt(rf, icr, "large")
        expected = rf + 0.0078
        assert kd == pytest.approx(expected, abs=1e-6)

    def test_get_default_spread_matches_table(self):
        spread = get_default_spread(2.6, "large")   # Baa2/BBB
        assert spread == pytest.approx(0.0111)

    def test_financial_firm_cost_of_debt(self):
        rf = 0.04
        kd = compute_cost_of_debt(rf, 1.0, "financial")  # Baa2/BBB → 1.11%
        assert kd == pytest.approx(0.04 + 0.0111, abs=1e-6)

    def test_invalid_firm_type_raises(self):
        with pytest.raises(ValueError, match="firm_type"):
            get_synthetic_rating(5.0, "mega")


# ---------------------------------------------------------------------------
# CAPM — cost of equity
# ---------------------------------------------------------------------------

class TestCAPM:
    def test_basic_capm_no_crp(self):
        # Rf=5%, Beta=1.0, ERP=5% → Ke=10%
        ke = compute_cost_of_equity(0.05, 1.0, 0.05)
        assert ke == pytest.approx(0.10, abs=1e-6)

    def test_goldman_ke(self):
        # Goldman: Rf=4.1%, Beta=1.4, ERP=4.5% → Ke=10.4%
        ke = compute_cost_of_equity(0.041, 1.4, 0.045)
        assert ke == pytest.approx(0.1040, abs=1e-4)

    def test_coned_ke(self):
        # ConEd: Rf=4.1%, Beta=0.8, ERP=4.5% → Ke=7.7%
        ke = compute_cost_of_equity(0.041, 0.8, 0.045)
        assert ke == pytest.approx(0.077, abs=1e-4)

    def test_capm_with_country_risk_premium(self):
        # India-like: Rf=2.5%, Beta=1.1, ERP=5.0%, CRP=2.0%, Lambda=1.5
        ke = compute_cost_of_equity(
            risk_free_rate=0.025,
            beta=1.1,
            erp=0.050,
            country_risk_premium=0.020,
            lambda_country=1.5,
        )
        expected = 0.025 + 1.1 * 0.050 + 1.5 * 0.020
        assert ke == pytest.approx(expected, abs=1e-6)

    def test_zero_beta_equals_rf(self):
        ke = compute_cost_of_equity(0.04, 0.0, 0.05)
        assert ke == pytest.approx(0.04, abs=1e-6)

    def test_crp_default_zero(self):
        ke_no_crp = compute_cost_of_equity(0.04, 1.0, 0.05)
        ke_zero_crp = compute_cost_of_equity(0.04, 1.0, 0.05, country_risk_premium=0.0)
        assert ke_no_crp == pytest.approx(ke_zero_crp)


# ---------------------------------------------------------------------------
# Beta levering / unlevering (Hamada)
# ---------------------------------------------------------------------------

class TestBeta:
    def test_unlever_3m(self):
        # 3M: Bl=1.3638, D/E=0.088, t=35%
        bu = unlever_beta(1.3638, 0.088, 0.35)
        assert bu == pytest.approx(1.2900, abs=1e-4)

    def test_relever_round_trip(self):
        # Unlever then relever at same D/E and tax rate must recover original beta
        bl_original = 1.3638
        de = 0.088
        t = 0.35
        bu = unlever_beta(bl_original, de, t)
        bl_recovered = relever_beta(bu, de, t)
        assert bl_recovered == pytest.approx(bl_original, abs=1e-6)

    def test_zero_leverage_unlever_is_identity(self):
        bl = 1.2
        bu = unlever_beta(bl, 0.0, 0.30)
        assert bu == pytest.approx(bl, abs=1e-6)

    def test_higher_leverage_increases_beta(self):
        bu = 1.0
        t = 0.30
        bl_low = relever_beta(bu, 0.2, t)
        bl_high = relever_beta(bu, 1.0, t)
        assert bl_high > bl_low

    def test_relever_different_de(self):
        # Relever at a different D/E than original unlevering
        bu = unlever_beta(1.5, 0.5, 0.30)
        bl_new = relever_beta(bu, 1.0, 0.30)
        expected = bu * (1 + 0.70 * 1.0)
        assert bl_new == pytest.approx(expected, abs=1e-6)


# ---------------------------------------------------------------------------
# WACC
# ---------------------------------------------------------------------------

class TestWACC:
    def test_basic_wacc(self):
        # Ke=10%, Kd=5%, t=30%, E/V=70%, D/V=30%
        wacc = compute_wacc(0.10, 0.05, 0.30, 0.70, 0.30)
        expected = 0.10 * 0.70 + 0.05 * 0.70 * 0.30
        assert wacc == pytest.approx(expected, abs=1e-6)

    def test_3m_wacc(self):
        """
        3M verification:
          Rf=3.7%, ERP=4.0%, Bl=1.3638, D/E=0.088, t=35%
          Ke = 3.7% + 1.3638*4.0% = 9.155% ~ 9.16%
          Kd = Rf + A2/A spread (0.78%) = 4.48%
          E/(D+E) = 1/1.088, D/(D+E) = 0.088/1.088
          WACC ~ 8.65%
        """
        rf = 0.037
        erp = 0.040
        bl = 1.3638
        de = 0.088
        t = 0.35

        ke = compute_cost_of_equity(rf, bl, erp)
        kd = compute_cost_of_debt(rf, 5.0, "large")   # ICR=5.0 → A2/A, spread=0.78%
        eq_w = 1.0 / (1.0 + de)
        dbt_w = de / (1.0 + de)
        wacc = compute_wacc(ke, kd, t, eq_w, dbt_w)

        assert ke == pytest.approx(0.0916, abs=1e-3)
        assert wacc == pytest.approx(0.0865, abs=1e-3)

    def test_all_equity_wacc_equals_ke(self):
        # No debt: WACC should equal Ke exactly
        ke = 0.10
        wacc = compute_wacc(ke, 0.05, 0.30, 1.0, 0.0)
        assert wacc == pytest.approx(ke, abs=1e-6)

    def test_weights_near_one_sum(self):
        # Weights should sum to ~1; test with unequal but summing weights
        ke = 0.09
        kd = 0.05
        t = 0.25
        wacc = compute_wacc(ke, kd, t, 0.60, 0.40)
        expected = 0.09 * 0.60 + 0.05 * 0.75 * 0.40
        assert wacc == pytest.approx(expected, abs=1e-6)
