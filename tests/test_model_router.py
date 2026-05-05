import pytest
from valuation.context import ValuationContext
from valuation.agents.model_router import select_model, ModelSelection


def test_financial_routes_to_ddm():
    ctx = ValuationContext(ticker="TEST")
    ctx.company.classification = "financial"
    result = select_model(ctx)
    assert result.primary_model == "ddm"
    assert "excess_returns" in result.secondary_models


def test_mature_routes_to_traditional():
    ctx = ValuationContext(ticker="TEST")
    ctx.company.classification = "mature"
    ctx.assumptions.growth_rates = [0.08]
    ctx.financials.key_stats = {"dividend_per_share": 2, "price": 100}
    result = select_model(ctx)
    assert result.primary_model == "fcff_traditional"


def test_mature_high_dividend_routes_to_gordon():
    ctx = ValuationContext(ticker="TEST")
    ctx.company.classification = "mature"
    ctx.assumptions.growth_rates = [0.03]
    ctx.financials.key_stats = {"dividend_per_share": 5, "price": 100}  # 5% yield
    result = select_model(ctx)
    assert result.primary_model == "gordon_growth"


def test_growth_routes_to_v2():
    ctx = ValuationContext(ticker="TEST")
    ctx.company.classification = "growth"
    ctx.assumptions.growth_rates = [0.20]
    ctx.financials.key_stats = {}
    result = select_model(ctx)
    assert result.primary_model == "fcff_revenue_s2c"


def test_cyclical_uses_normalization():
    ctx = ValuationContext(ticker="TEST")
    ctx.company.classification = "cyclical"
    ctx.assumptions.growth_rates = [0.05]
    ctx.financials.key_stats = {}
    result = select_model(ctx)
    assert result.primary_model == "fcff_traditional"
    assert result.use_normalization is True


def test_distressed_uses_failure_prob():
    ctx = ValuationContext(ticker="TEST")
    ctx.company.classification = "distressed"
    ctx.assumptions.growth_rates = [0.02]
    ctx.financials.key_stats = {}
    result = select_model(ctx)
    assert result.use_failure_probability is True
