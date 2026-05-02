"""Sprint 2 integration: risk assessor + DCF engines + Damodaran data."""

import pytest
from valuation.agents.risk_assessor import (
    compute_cost_of_equity,
    compute_cost_of_debt,
    compute_wacc,
    get_synthetic_rating,
    relever_beta,
)
from valuation.engines.dcf import (
    fcff_valuation,
    ddm_valuation,
    gordon_growth_value,
    interpolate_params,
    sensitivity_table,
)
from valuation.data.damodaran_loader import DamodaranLoader


class TestRiskWithDamodaranData:
    def test_wacc_for_software_industry(self, damodaran_data_dir):
        loader = DamodaranLoader(damodaran_data_dir)
        beta_row = loader.lookup("betas", "Software (System & Application)")
        unlevered_beta = float(beta_row["Unlevered beta corrected for cash"])
        de_ratio = float(beta_row["D/E Ratio"])
        tax_rate = float(beta_row["Effective Tax rate"])
        levered_beta = relever_beta(unlevered_beta, de_ratio, tax_rate)
        ke = compute_cost_of_equity(risk_free_rate=0.0395, beta=levered_beta, erp=0.0446)
        wacc_row = loader.lookup("wacc", "Software (System & Application)")
        published_wacc = float(wacc_row["Cost of Capital"])
        assert 0.05 < ke < 0.20
        assert 0.05 < published_wacc < 0.20


class TestEndToEndValuation:
    def test_stable_utility_valuation(self):
        ke = compute_cost_of_equity(0.041, 0.80, 0.045)
        value = gordon_growth_value(2.32, ke, 0.021)
        assert 30 < value < 60

    def test_growth_company_fcff(self):
        ke = compute_cost_of_equity(0.03, 1.3, 0.045)
        wacc = compute_wacc(ke, 0.04, 0.25, 0.85, 0.15)
        growth_rates = interpolate_params(0.15, 0.03, 10, gradual=True)
        reinv_rates = interpolate_params(0.60, 0.30, 10, gradual=True)
        waccs = [wacc] * 10
        result = fcff_valuation(
            current_ebit_after_tax=1000.0,
            growth_rates=growth_rates,
            reinvestment_rates=reinv_rates,
            waccs=waccs,
            stable_growth=0.03,
            stable_roc=0.12,
            stable_wacc=wacc,
            cash=500.0,
            debt=2000.0,
            shares_outstanding=100.0,
        )
        assert result["equity_value_per_share"] > 0
        assert result["pv_terminal"] > result["pv_high_growth"]

    def test_financial_ddm(self):
        growth_rates = interpolate_params(0.10, 0.03, 5, gradual=True)
        payout_rates = interpolate_params(0.30, 0.70, 5, gradual=True)
        ke_rates = interpolate_params(0.12, 0.09, 5, gradual=True)
        result = ddm_valuation(
            current_eps=5.0,
            growth_rates=growth_rates,
            payout_rates=payout_rates,
            cost_of_equities=ke_rates,
            stable_growth=0.03,
            stable_roe=0.10,
            stable_ke=0.09,
        )
        assert result["value_per_share"] > 0

    def test_sensitivity_on_gordon(self):
        table = sensitivity_table(
            base_params={"current_dividend": 2.0, "cost_of_equity": 0.08, "growth_rate": 0.02},
            vary_param="growth_rate",
            vary_values=[0.01, 0.02, 0.03, 0.04],
            valuation_fn=gordon_growth_value,
        )
        assert table[0.01] < table[0.02] < table[0.03] < table[0.04]
