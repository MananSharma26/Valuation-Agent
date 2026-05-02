import pytest
from valuation.scoring.confidence import (
    score_data_completeness,
    score_model_agreement,
    score_assumption_sensitivity,
    score_industry_coverage,
    compute_composite_score,
    generate_flags,
    score_all,
)
from valuation.context import ValuationContext
import pandas as pd


class TestDataCompleteness:
    def test_all_fields_present(self):
        """All required fields present => score 1.0."""
        fields = {
            "income_statement": True,
            "balance_sheet": True,
            "cash_flow": True,
            "shares_outstanding": True,
            "market_cap": True,
            "price": True,
            "beta": True,
            "book_value_per_share": True,
        }
        score = score_data_completeness(fields)
        assert score == 1.0

    def test_no_fields_present(self):
        """No fields present => score 0.0."""
        fields = {
            "income_statement": False,
            "balance_sheet": False,
            "cash_flow": False,
            "shares_outstanding": False,
            "market_cap": False,
            "price": False,
            "beta": False,
            "book_value_per_share": False,
        }
        score = score_data_completeness(fields)
        assert score == 0.0

    def test_partial_fields(self):
        """Half fields present => score 0.5."""
        fields = {
            "income_statement": True,
            "balance_sheet": True,
            "cash_flow": True,
            "shares_outstanding": True,
            "market_cap": False,
            "price": False,
            "beta": False,
            "book_value_per_share": False,
        }
        score = score_data_completeness(fields)
        assert abs(score - 0.5) < 0.01


class TestModelAgreement:
    def test_all_models_agree(self):
        """All models return the same value => score 1.0."""
        values = {"dcf": 100.0, "relative": 100.0, "excess_returns": 100.0}
        score = score_model_agreement(values)
        assert score == 1.0

    def test_max_divergence(self):
        """Wide divergence => low score."""
        values = {"dcf": 50.0, "relative": 150.0}
        score = score_model_agreement(values)
        # normalized divergence = (150-50)/100 = 1.0 => score = 1 - 1.0 = 0.0
        assert score == 0.0

    def test_moderate_divergence(self):
        """20% divergence => 0.80 score."""
        values = {"dcf": 90.0, "relative": 110.0}
        score = score_model_agreement(values)
        # mean=100, divergence = (110-90)/100 = 0.20 => score = 0.80
        assert abs(score - 0.80) < 0.01

    def test_single_model(self):
        """Single model => score 1.0 (no divergence possible)."""
        values = {"dcf": 100.0}
        score = score_model_agreement(values)
        assert score == 1.0

    def test_no_models(self):
        """No models => score 0.0."""
        values = {}
        score = score_model_agreement(values)
        assert score == 0.0

    def test_negative_values_excluded(self):
        """Negative values (failed models) are excluded."""
        values = {"dcf": 100.0, "relative": -50.0, "excess_returns": 120.0}
        score = score_model_agreement(values)
        # Only dcf=100 and excess_returns=120 counted
        # mean=110, divergence = (120-100)/110 = 0.1818 => score ≈ 0.818
        assert 0.7 < score < 0.9


class TestAssumptionSensitivity:
    def test_low_sensitivity(self):
        """Small range relative to base => high score."""
        score = score_assumption_sensitivity(
            base_value=100.0,
            min_value=95.0,
            max_value=105.0,
        )
        # sensitivity = (105-95)/100 = 0.10 => score = 1 - 0.10 = 0.90
        assert abs(score - 0.90) < 0.01

    def test_high_sensitivity(self):
        """Large range relative to base => low score."""
        score = score_assumption_sensitivity(
            base_value=100.0,
            min_value=50.0,
            max_value=200.0,
        )
        # sensitivity = (200-50)/100 = 1.50 => score = max(0, 1 - 1.50) = 0.0
        assert score == 0.0

    def test_zero_base_returns_zero(self):
        """Base value of zero => score 0.0."""
        score = score_assumption_sensitivity(
            base_value=0.0,
            min_value=-10.0,
            max_value=10.0,
        )
        assert score == 0.0


class TestIndustryCoverage:
    def test_exact_match(self):
        """Exact industry match => score 1.0."""
        score = score_industry_coverage(match_score=100)
        assert score == 1.0

    def test_no_match(self):
        """No match => score 0.0."""
        score = score_industry_coverage(match_score=0)
        assert score == 0.0

    def test_partial_match(self):
        """75% fuzzy match => score 0.75."""
        score = score_industry_coverage(match_score=75)
        assert abs(score - 0.75) < 0.01


class TestCompositeScore:
    def test_all_perfect(self):
        """All sub-scores 1.0 => composite 1.0."""
        composite = compute_composite_score(
            data_completeness=1.0,
            model_agreement=1.0,
            assumption_sensitivity=1.0,
            industry_coverage=1.0,
        )
        assert abs(composite - 1.0) < 0.01

    def test_all_zero(self):
        """All sub-scores 0.0 => composite 0.0."""
        composite = compute_composite_score(
            data_completeness=0.0,
            model_agreement=0.0,
            assumption_sensitivity=0.0,
            industry_coverage=0.0,
        )
        assert composite == 0.0

    def test_weighted_average(self):
        """Verify weights: 0.30, 0.30, 0.25, 0.15."""
        composite = compute_composite_score(
            data_completeness=1.0,
            model_agreement=0.0,
            assumption_sensitivity=0.0,
            industry_coverage=0.0,
        )
        # Only data_completeness contributes: 1.0 * 0.30 = 0.30
        assert abs(composite - 0.30) < 0.01

    def test_industry_weight(self):
        """Industry coverage alone: 1.0 * 0.15 = 0.15."""
        composite = compute_composite_score(
            data_completeness=0.0,
            model_agreement=0.0,
            assumption_sensitivity=0.0,
            industry_coverage=1.0,
        )
        assert abs(composite - 0.15) < 0.01


class TestFlags:
    def test_no_flags_on_perfect_scores(self):
        flags = generate_flags(
            data_completeness=1.0,
            model_agreement=1.0,
            assumption_sensitivity=1.0,
            industry_coverage=1.0,
            model_values={"dcf": 100.0, "relative": 100.0},
        )
        assert flags == []

    def test_low_data_completeness_flag(self):
        flags = generate_flags(
            data_completeness=0.4,
            model_agreement=1.0,
            assumption_sensitivity=1.0,
            industry_coverage=1.0,
            model_values={"dcf": 100.0},
        )
        assert any("data" in f.lower() for f in flags)

    def test_low_model_agreement_flag(self):
        flags = generate_flags(
            data_completeness=1.0,
            model_agreement=0.3,
            assumption_sensitivity=1.0,
            industry_coverage=1.0,
            model_values={"dcf": 50.0, "relative": 150.0},
        )
        assert any("disagree" in f.lower() or "diverge" in f.lower() for f in flags)

    def test_high_sensitivity_flag(self):
        flags = generate_flags(
            data_completeness=1.0,
            model_agreement=1.0,
            assumption_sensitivity=0.2,
            industry_coverage=1.0,
            model_values={"dcf": 100.0},
        )
        assert any("sensitiv" in f.lower() for f in flags)

    def test_low_industry_coverage_flag(self):
        flags = generate_flags(
            data_completeness=1.0,
            model_agreement=1.0,
            assumption_sensitivity=1.0,
            industry_coverage=0.3,
            model_values={"dcf": 100.0},
        )
        assert any("industry" in f.lower() for f in flags)

    def test_single_model_flag(self):
        flags = generate_flags(
            data_completeness=1.0,
            model_agreement=1.0,
            assumption_sensitivity=1.0,
            industry_coverage=1.0,
            model_values={"dcf": 100.0},
        )
        assert any("single" in f.lower() or "one model" in f.lower() for f in flags)


class TestScoreAll:
    def test_score_all_populates_context(self):
        ctx = ValuationContext(ticker="TEST")
        ctx.financials.income_statement = pd.DataFrame({"Total Revenue": [100]})
        ctx.financials.balance_sheet = pd.DataFrame({"Total Assets": [500]})
        ctx.financials.cash_flow = pd.DataFrame({"Operating Cash Flow": [50]})
        ctx.financials.key_stats = {
            "shares_outstanding": 10,
            "market_cap": 500,
            "price": 50.0,
            "beta": 1.1,
            "book_value_per_share": 30.0,
            "dividend_per_share": 1.0,
        }
        ctx.outputs.dcf_fcff = {"equity_value_per_share": 55.0}
        ctx.outputs.relative = {"implied_value_pe": 50.0, "implied_value_eveb": 52.0}
        ctx.benchmarks.industry_multiples = {"pe": 20.0}

        score_all(ctx, industry_match_score=85)
        assert ctx.confidence.data_completeness is not None
        assert ctx.confidence.model_agreement is not None
        assert ctx.confidence.composite is not None
        assert isinstance(ctx.confidence.flags, list)
        assert 0.0 <= ctx.confidence.composite <= 1.0
