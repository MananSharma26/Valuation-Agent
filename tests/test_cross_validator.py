import pytest
from valuation.agents.cross_validator import (
    cross_validate,
    CrossValidationResult,
)


class TestCrossValidate:
    def test_all_models_agree(self):
        """All models produce similar values => low divergence, no flags."""
        result = cross_validate(
            model_outputs={
                "dcf_fcff": {"equity_value_per_share": 100.0},
                "relative": {"implied_value_pe": 95.0, "implied_value_eveb": 105.0},
            },
            price=98.0,
        )
        assert isinstance(result, CrossValidationResult)
        assert result.mean_value > 0
        assert result.median_value > 0
        assert abs(result.mean_value - 100.0) < 5.0
        assert result.max_divergence_pct < 0.15
        assert result.num_models == 3
        assert len(result.flags) == 0

    def test_large_divergence_flagged(self):
        """Models diverge >50% => flag raised."""
        result = cross_validate(
            model_outputs={
                "dcf_fcff": {"equity_value_per_share": 50.0},
                "relative": {"implied_value_pe": 150.0},
            },
            price=100.0,
        )
        assert result.max_divergence_pct > 0.50
        assert any("diverge" in f.lower() or "spread" in f.lower() for f in result.flags)

    def test_value_vs_price_premium(self):
        """Value significantly above price => premium flag."""
        result = cross_validate(
            model_outputs={
                "dcf_fcff": {"equity_value_per_share": 150.0},
                "relative": {"implied_value_pe": 140.0},
            },
            price=100.0,
        )
        assert result.price_vs_value_pct > 0.30
        assert any("undervalued" in f.lower() or "premium" in f.lower() for f in result.flags)

    def test_value_vs_price_discount(self):
        """Value significantly below price => discount flag."""
        result = cross_validate(
            model_outputs={
                "dcf_fcff": {"equity_value_per_share": 60.0},
                "relative": {"implied_value_pe": 70.0},
            },
            price=100.0,
        )
        assert result.price_vs_value_pct < -0.20
        assert any("overvalued" in f.lower() or "discount" in f.lower() for f in result.flags)

    def test_single_model_no_divergence(self):
        """Single model => divergence is 0."""
        result = cross_validate(
            model_outputs={
                "dcf_fcff": {"equity_value_per_share": 100.0},
            },
            price=100.0,
        )
        assert result.max_divergence_pct == 0.0
        assert result.num_models == 1

    def test_empty_models(self):
        """No valid model outputs => all zeros."""
        result = cross_validate(
            model_outputs={},
            price=100.0,
        )
        assert result.num_models == 0
        assert result.mean_value == 0.0

    def test_excess_returns_included(self):
        """Excess returns model output is picked up."""
        result = cross_validate(
            model_outputs={
                "dcf_fcff": {"equity_value_per_share": 100.0},
                "excess_returns": {"value_per_share": 110.0},
            },
            price=105.0,
        )
        assert result.num_models == 2
        assert abs(result.mean_value - 105.0) < 1.0

    def test_negative_values_excluded(self):
        """Negative model values are excluded from statistics."""
        result = cross_validate(
            model_outputs={
                "dcf_fcff": {"equity_value_per_share": -50.0},
                "relative": {"implied_value_pe": 100.0},
            },
            price=90.0,
        )
        assert result.num_models == 1
        assert result.mean_value == 100.0

    def test_result_contains_individual_values(self):
        """Result dict includes per-model values."""
        result = cross_validate(
            model_outputs={
                "dcf_fcff": {"equity_value_per_share": 100.0},
                "relative": {"implied_value_pe": 90.0, "implied_value_eveb": 110.0},
            },
            price=100.0,
        )
        assert "dcf_fcff" in result.individual_values
        assert "relative_pe" in result.individual_values
        assert "relative_eveb" in result.individual_values
        assert result.individual_values["dcf_fcff"] == 100.0

    def test_to_dict(self):
        """CrossValidationResult can be serialized to dict."""
        result = cross_validate(
            model_outputs={
                "dcf_fcff": {"equity_value_per_share": 100.0},
            },
            price=95.0,
        )
        d = result.to_dict()
        assert isinstance(d, dict)
        assert "mean_value" in d
        assert "flags" in d
        assert "individual_values" in d
