import pandas as pd
from valuation.context import ValuationContext


def test_create_empty_context():
    ctx = ValuationContext(ticker="AAPL")
    assert ctx.company.ticker == "AAPL"
    assert ctx.company.name is None
    assert ctx.company.classification is None
    assert ctx.financials.income_statement is None
    assert ctx.assumptions.wacc is None
    assert ctx.outputs.dcf_fcff is None
    assert ctx.confidence.composite is None
    assert ctx.confidence.flags == []


def test_context_set_financials():
    ctx = ValuationContext(ticker="AAPL")
    ctx.financials.income_statement = pd.DataFrame({"revenue": [100, 200]})
    assert len(ctx.financials.income_statement) == 2


def test_context_override_tracking():
    ctx = ValuationContext(ticker="AAPL")
    ctx.assumptions.wacc = 0.08
    ctx.assumptions.set_override("wacc", 0.10, reason="User thinks risk is higher")
    assert ctx.assumptions.wacc == 0.10
    assert "wacc" in ctx.assumptions.overrides
    assert ctx.assumptions.overrides["wacc"]["original"] == 0.08
    assert ctx.assumptions.overrides["wacc"]["reason"] == "User thinks risk is higher"


def test_context_to_dict():
    ctx = ValuationContext(ticker="MSFT")
    ctx.company.name = "Microsoft"
    d = ctx.to_summary_dict()
    assert d["ticker"] == "MSFT"
    assert d["name"] == "Microsoft"
