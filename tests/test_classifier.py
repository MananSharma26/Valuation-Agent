import pytest
import pandas as pd
from valuation.agents.classifier import (
    classify_company,
    ClassificationResult,
)
from valuation.context import ValuationContext


def _make_ctx(
    ticker: str = "TEST",
    sector: str | None = None,
    sic_code: str | None = None,
    revenue_growth: float | None = None,
    net_income_latest: float | None = None,
    net_income_prev: float | None = None,
    revenue_latest: float | None = None,
    revenue_prev: float | None = None,
    total_debt: float | None = None,
    total_equity: float | None = None,
    operating_income: float | None = None,
    interest_expense: float | None = None,
    market_cap: float = 50000.0,
    age_years: int | None = None,
) -> ValuationContext:
    """Helper to build a ValuationContext with controlled financials."""
    ctx = ValuationContext(ticker=ticker)
    ctx.company.sector = sector
    ctx.company.sic_code = sic_code

    # Build income statement
    income_data = {}
    if revenue_latest is not None:
        income_data["Total Revenue"] = [revenue_latest]
        if revenue_prev is not None:
            income_data["Total Revenue"] = [revenue_latest, revenue_prev]
    if net_income_latest is not None:
        income_data["Net Income"] = [net_income_latest]
        if net_income_prev is not None:
            income_data["Net Income"] = [net_income_latest, net_income_prev]
    if operating_income is not None:
        income_data["Operating Income"] = [operating_income]
    if interest_expense is not None:
        income_data["Interest Expense"] = [interest_expense]
    if income_data:
        ctx.financials.income_statement = pd.DataFrame(income_data)

    # Build balance sheet
    balance_data = {}
    if total_debt is not None:
        balance_data["Total Debt"] = [total_debt]
    if total_equity is not None:
        balance_data["Total Stockholders Equity"] = [total_equity]
    if balance_data:
        ctx.financials.balance_sheet = pd.DataFrame(balance_data)

    ctx.financials.key_stats["market_cap"] = market_cap
    if age_years is not None:
        ctx.financials.key_stats["company_age_years"] = age_years

    return ctx


class TestClassificationResult:
    def test_result_fields(self):
        r = ClassificationResult(
            classification="mature",
            confidence=0.85,
            reasoning="Stable revenue, positive earnings, moderate growth.",
        )
        assert r.classification == "mature"
        assert r.confidence == 0.85
        assert "Stable" in r.reasoning

    def test_suggested_model_default(self):
        r = ClassificationResult(
            classification="mature",
            confidence=0.75,
            reasoning="Default.",
        )
        assert r.suggested_model in ("dcf_fcff", "ddm", "gordon_growth")

    def test_financial_suggests_ddm(self):
        r = ClassificationResult(
            classification="financial",
            confidence=0.90,
            reasoning="Financial firm.",
            suggested_model="ddm",
        )
        assert r.suggested_model == "ddm"


class TestFinancialClassification:
    def test_bank_by_sic_code(self):
        ctx = _make_ctx(
            sic_code="6021",
            sector="Financial Services",
            revenue_latest=50000,
            net_income_latest=5000,
        )
        result = classify_company(ctx)
        assert result.classification == "financial"
        assert "SIC" in result.reasoning or "financial" in result.reasoning.lower()

    def test_insurance_by_sic_code(self):
        ctx = _make_ctx(
            sic_code="6311",
            sector="Financial Services",
            revenue_latest=30000,
            net_income_latest=3000,
        )
        result = classify_company(ctx)
        assert result.classification == "financial"

    def test_bank_by_sector(self):
        ctx = _make_ctx(
            sector="Financial Services",
            revenue_latest=50000,
            net_income_latest=5000,
        )
        result = classify_company(ctx)
        assert result.classification == "financial"

    def test_financial_suggests_ddm(self):
        ctx = _make_ctx(
            sic_code="6021",
            sector="Financial Services",
            revenue_latest=50000,
            net_income_latest=5000,
        )
        result = classify_company(ctx)
        assert result.suggested_model == "ddm"


class TestDistressedClassification:
    def test_negative_earnings_multiple_years(self):
        ctx = _make_ctx(
            revenue_latest=10000,
            revenue_prev=12000,
            net_income_latest=-2000,
            net_income_prev=-1500,
            total_debt=30000,
            total_equity=5000,
        )
        result = classify_company(ctx)
        assert result.classification == "distressed"
        assert "negative" in result.reasoning.lower() or "loss" in result.reasoning.lower()

    def test_high_leverage_negative_income(self):
        ctx = _make_ctx(
            revenue_latest=10000,
            net_income_latest=-500,
            total_debt=50000,
            total_equity=5000,
            operating_income=1000,
            interest_expense=3000,
        )
        result = classify_company(ctx)
        assert result.classification == "distressed"

    def test_distressed_suggests_dcf_fcff(self):
        ctx = _make_ctx(
            net_income_latest=-2000,
            net_income_prev=-1500,
            total_debt=30000,
            total_equity=5000,
        )
        result = classify_company(ctx)
        assert result.suggested_model == "dcf_fcff"


class TestGrowthClassification:
    def test_high_revenue_growth(self):
        ctx = _make_ctx(
            revenue_latest=50000,
            revenue_prev=30000,
            net_income_latest=2000,
            net_income_prev=500,
            market_cap=200000,
        )
        result = classify_company(ctx)
        assert result.classification == "growth"
        assert "growth" in result.reasoning.lower() or "revenue" in result.reasoning.lower()

    def test_moderate_growth_positive_earnings(self):
        ctx = _make_ctx(
            revenue_latest=20000,
            revenue_prev=15000,
            net_income_latest=2000,
            net_income_prev=1500,
        )
        result = classify_company(ctx)
        assert result.classification == "growth"

    def test_growth_suggests_dcf_fcff(self):
        ctx = _make_ctx(
            revenue_latest=50000,
            revenue_prev=30000,
            net_income_latest=2000,
            net_income_prev=1000,
        )
        result = classify_company(ctx)
        assert result.suggested_model == "dcf_fcff"


class TestYoungClassification:
    def test_young_company_no_earnings(self):
        ctx = _make_ctx(
            revenue_latest=5000,
            revenue_prev=1000,
            net_income_latest=-3000,
            net_income_prev=-2000,
            market_cap=50000,
            age_years=3,
        )
        result = classify_company(ctx)
        assert result.classification == "young"

    def test_pre_revenue(self):
        ctx = _make_ctx(
            revenue_latest=100,
            net_income_latest=-5000,
            market_cap=100000,
            age_years=2,
        )
        result = classify_company(ctx)
        assert result.classification == "young"

    def test_young_suggests_dcf_fcff(self):
        ctx = _make_ctx(
            revenue_latest=5000,
            revenue_prev=1000,
            net_income_latest=-3000,
            net_income_prev=-2000,
            age_years=3,
        )
        result = classify_company(ctx)
        assert result.suggested_model == "dcf_fcff"


class TestMatureClassification:
    def test_stable_utility(self):
        ctx = _make_ctx(
            sector="Utilities",
            revenue_latest=20000,
            revenue_prev=19500,
            net_income_latest=3000,
            net_income_prev=2900,
            total_debt=15000,
            total_equity=20000,
        )
        result = classify_company(ctx)
        assert result.classification == "mature"

    def test_stable_consumer_staple(self):
        ctx = _make_ctx(
            revenue_latest=50000,
            revenue_prev=48000,
            net_income_latest=5000,
            net_income_prev=4800,
            total_debt=10000,
            total_equity=30000,
        )
        result = classify_company(ctx)
        assert result.classification == "mature"


class TestCyclicalClassification:
    def test_cyclical_by_sector(self):
        ctx = _make_ctx(
            sector="Basic Materials",
            revenue_latest=10000,
            revenue_prev=10500,
            net_income_latest=1000,
            net_income_prev=1200,
        )
        result = classify_company(ctx)
        assert result.classification == "cyclical"

    def test_auto_sector(self):
        ctx = _make_ctx(
            sector="Consumer Cyclical",
            revenue_latest=50000,
            revenue_prev=48000,
            net_income_latest=3000,
            net_income_prev=3500,
        )
        result = classify_company(ctx)
        assert result.classification == "cyclical"

    def test_cyclical_suggests_dcf_fcff(self):
        ctx = _make_ctx(
            sector="Energy",
            revenue_latest=10000,
            revenue_prev=10500,
            net_income_latest=1000,
            net_income_prev=1200,
        )
        result = classify_company(ctx)
        assert result.suggested_model == "dcf_fcff"


class TestEdgeCases:
    def test_minimal_data(self):
        ctx = ValuationContext(ticker="UNKNOWN")
        result = classify_company(ctx)
        assert result.classification in (
            "mature", "growth", "young", "distressed", "cyclical", "financial"
        )
        assert result.confidence < 0.5  # low confidence with minimal data

    def test_classification_populates_context(self):
        ctx = _make_ctx(
            revenue_latest=50000,
            revenue_prev=48000,
            net_income_latest=5000,
            net_income_prev=4800,
        )
        result = classify_company(ctx)
        # Verify the result can populate context
        ctx.company.classification = result.classification
        assert ctx.company.classification in (
            "mature", "growth", "young", "distressed", "cyclical", "financial"
        )

    def test_reasoning_is_non_empty(self):
        ctx = _make_ctx(
            revenue_latest=50000,
            net_income_latest=3000,
        )
        result = classify_company(ctx)
        assert len(result.reasoning) > 0

    def test_confidence_range(self):
        ctx = _make_ctx(
            revenue_latest=50000,
            revenue_prev=48000,
            net_income_latest=5000,
            net_income_prev=4800,
        )
        result = classify_company(ctx)
        assert 0.0 <= result.confidence <= 1.0
