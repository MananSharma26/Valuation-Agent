"""Golden tests: validate engine output against Damodaran's example spreadsheets."""

import json
import pathlib
import pytest
from valuation.engines.dcf import (
    gordon_growth_value,
    ddm_valuation,
    fcff_valuation,
    interpolate_params,
)

GOLDEN_DIR = pathlib.Path(__file__).parent / "golden"


def test_coned_gordon_growth():
    with open(GOLDEN_DIR / "coned.json") as f:
        tc = json.load(f)
    value = gordon_growth_value(**tc["inputs"])
    expected = tc["expected"]["value_per_share"]
    assert abs(value - expected) < tc["tolerance"], (
        f"ConEd: got {value:.2f}, expected {expected:.2f}"
    )


def test_goldman_ddm():
    with open(GOLDEN_DIR / "goldman.json") as f:
        tc = json.load(f)
    inp = tc["inputs"]
    growth_rates = interpolate_params(inp["high_growth_rate"], inp["stable_growth"], inp["n_years"], inp["gradual"])
    payout_rates = interpolate_params(inp["high_payout"], inp["stable_payout"], inp["n_years"], inp["gradual"])
    ke_rates = interpolate_params(inp["high_ke"], inp["stable_ke"], inp["n_years"], inp["gradual"])

    result = ddm_valuation(
        current_eps=inp["current_eps"],
        growth_rates=growth_rates,
        payout_rates=payout_rates,
        cost_of_equities=ke_rates,
        stable_growth=inp["stable_growth"],
        stable_roe=inp["stable_roe"],
        stable_ke=inp["stable_ke"],
    )
    expected = tc["expected"]["value_per_share"]
    tolerance = expected * tc["tolerance_pct"]
    assert abs(result["value_per_share"] - expected) < tolerance, (
        f"Goldman: got {result['value_per_share']:.2f}, expected {expected:.2f} (±{tolerance:.2f})"
    )


def test_3m_fcff():
    with open(GOLDEN_DIR / "3m_precrisis.json") as f:
        tc = json.load(f)
    inp = tc["inputs"]

    # Inputs are pre-computed year-by-year arrays directly from the spreadsheet
    result = fcff_valuation(
        current_ebit_after_tax=inp["current_ebit_after_tax"],
        growth_rates=inp["growth_rates"],
        reinvestment_rates=inp["reinvestment_rates"],
        waccs=inp["waccs"],
        stable_growth=inp["stable_growth"],
        stable_roc=inp["stable_roc"],
        stable_wacc=inp["stable_wacc"],
        cash=inp["cash"],
        debt=inp["debt"],
        options_value=inp["options_value"],
        shares_outstanding=inp["shares_outstanding"],
    )
    expected = tc["expected"]["value_per_share"]
    tolerance = expected * tc["tolerance_pct"]
    assert abs(result["equity_value_per_share"] - expected) < tolerance, (
        f"3M: got {result['equity_value_per_share']:.2f}, expected {expected:.2f} (±{tolerance:.2f})"
    )
