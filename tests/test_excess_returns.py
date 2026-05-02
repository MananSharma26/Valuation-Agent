import pytest
from valuation.engines.excess_returns import (
    excess_return_valuation,
    compute_excess_return,
)
from valuation.engines.dcf import interpolate_params


class TestExcessReturnSingle:
    def test_positive_excess_return(self):
        """ROE > COE => positive excess return."""
        er = compute_excess_return(
            roe=0.15,
            coe=0.10,
            book_equity=1000.0,
        )
        # (0.15 - 0.10) * 1000 = 50
        assert abs(er - 50.0) < 0.01

    def test_negative_excess_return(self):
        """ROE < COE => negative excess return (value destruction)."""
        er = compute_excess_return(
            roe=0.08,
            coe=0.10,
            book_equity=1000.0,
        )
        # (0.08 - 0.10) * 1000 = -20
        assert abs(er - (-20.0)) < 0.01

    def test_zero_excess_return(self):
        """ROE = COE => zero excess return."""
        er = compute_excess_return(
            roe=0.10,
            coe=0.10,
            book_equity=1000.0,
        )
        assert abs(er) < 0.01


class TestExcessReturnValuation:
    def test_goldman_sachs(self):
        """Goldman: BV=$218.75, ROE=13.19%, COE=10.4%, 10yr HG, stable ROE=10%, stable COE=9.5%.

        Damodaran's excess return model for Goldman should yield a value
        in the neighborhood of $220-$260 per share.
        """
        n_years = 10
        roes = interpolate_params(0.1319, 0.10, n_years, gradual=True)
        coes = interpolate_params(0.104, 0.095, n_years, gradual=True)

        # EPS growth drives book equity growth; use fundamental EPS growth
        eps_growth_rates = interpolate_params(0.1209, 0.04, n_years, gradual=True)

        result = excess_return_valuation(
            current_book_equity_per_share=218.75,
            current_eps=16.77,
            eps_growth_rates=eps_growth_rates,
            payout_rates=interpolate_params(0.0835, 0.60, n_years, gradual=True),
            roes=roes,
            coes=coes,
            stable_growth=0.04,
            stable_roe=0.10,
            stable_coe=0.095,
        )
        assert result["value_per_share"] > 150.0
        assert result["value_per_share"] < 350.0
        assert result["current_book_equity"] == 218.75
        assert result["pv_excess_returns"] != 0  # Some excess return (positive or negative)
        assert result["pv_terminal_excess"] != 0
        assert len(result["yearly_excess_returns"]) == n_years
        assert len(result["yearly_pv"]) == n_years

    def test_wells_fargo(self):
        """Wells Fargo: BV=$15.99, ROE=13.5%, COE=9.6%, 5yr HG.

        Stable ROE=7.6%, stable COE=7.6% => excess return converges to 0.
        Value should be close to book equity in terminal.
        """
        n_years = 5
        roes = interpolate_params(0.135, 0.076, n_years, gradual=True)
        coes = interpolate_params(0.096, 0.076, n_years, gradual=True)
        eps_growth_rates = interpolate_params(0.061, 0.03, n_years, gradual=True)
        payout_rates = interpolate_params(0.546, 0.605, n_years, gradual=True)

        result = excess_return_valuation(
            current_book_equity_per_share=15.99,
            current_eps=2.16,
            eps_growth_rates=eps_growth_rates,
            payout_rates=payout_rates,
            roes=roes,
            coes=coes,
            stable_growth=0.03,
            stable_roe=0.076,
            stable_coe=0.076,
        )
        # When stable ROE = stable COE, terminal excess return = 0
        # Value should be approximately current BV + PV(HG excess returns)
        assert result["value_per_share"] > 10.0
        assert result["value_per_share"] < 40.0
        # Terminal excess value should be near zero since ROE ≈ COE in stable
        assert abs(result["pv_terminal_excess"]) < 5.0

    def test_roe_equals_coe_everywhere(self):
        """If ROE = COE for all periods, value = book equity."""
        result = excess_return_valuation(
            current_book_equity_per_share=100.0,
            current_eps=10.0,
            eps_growth_rates=[0.05, 0.05, 0.05],
            payout_rates=[0.50, 0.50, 0.50],
            roes=[0.10, 0.10, 0.10],
            coes=[0.10, 0.10, 0.10],
            stable_growth=0.03,
            stable_roe=0.10,
            stable_coe=0.10,
        )
        # Excess returns are zero in all periods; terminal excess is zero
        # Value = book equity
        assert abs(result["value_per_share"] - 100.0) < 1.0

    def test_length_mismatch_raises(self):
        """All per-year lists must have the same length."""
        with pytest.raises(ValueError, match="same length"):
            excess_return_valuation(
                current_book_equity_per_share=100.0,
                current_eps=10.0,
                eps_growth_rates=[0.05, 0.05],
                payout_rates=[0.50],
                roes=[0.10, 0.10],
                coes=[0.10, 0.10],
                stable_growth=0.03,
                stable_roe=0.10,
                stable_coe=0.10,
            )

    def test_stable_coe_equals_growth_raises(self):
        """Terminal value formula requires stable_coe > stable_growth."""
        with pytest.raises(ValueError, match="exceed"):
            excess_return_valuation(
                current_book_equity_per_share=100.0,
                current_eps=10.0,
                eps_growth_rates=[0.05],
                payout_rates=[0.50],
                roes=[0.10],
                coes=[0.10],
                stable_growth=0.05,
                stable_roe=0.10,
                stable_coe=0.05,
            )
