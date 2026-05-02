"""Tests for WACC/tax/margin/reinvestment schedule generators."""

import pytest
from valuation.engines.schedules import (
    wacc_schedule,
    tax_schedule,
    margin_convergence_schedule,
    reinvestment_s2c,
    reinvestment_terminal,
    terminal_wacc_default,
)


class TestWaccSchedule:
    def test_nvidia_wacc(self):
        """Nvidia: initial=11.794%, terminal=8.5%, 10yr."""
        sched = wacc_schedule(0.11794, 0.085, n_years=10, n_constant=5)
        assert len(sched) == 10
        # Years 1-5 constant
        for t in range(5):
            assert sched[t] == pytest.approx(0.11794, rel=1e-6)
        # Year 10 = terminal
        assert sched[9] == pytest.approx(0.085, rel=1e-4)
        # Linear ramp: step = (0.11794 - 0.085) / 5 = 0.006588
        step = (0.11794 - 0.085) / 5
        assert sched[5] == pytest.approx(0.11794 - step, rel=1e-4)  # year 6
        assert sched[6] == pytest.approx(0.11794 - 2 * step, rel=1e-4)  # year 7

    def test_amazon_wacc(self):
        """Amazon: initial=7.97%, terminal=7.5%."""
        sched = wacc_schedule(0.0797, 0.075)
        assert sched[0] == pytest.approx(0.0797, rel=1e-6)
        assert sched[4] == pytest.approx(0.0797, rel=1e-6)
        assert sched[9] == pytest.approx(0.075, rel=1e-4)

    def test_constant_wacc(self):
        """When initial == terminal, all values should be equal."""
        sched = wacc_schedule(0.10, 0.10)
        for v in sched:
            assert v == pytest.approx(0.10, abs=1e-10)

    def test_length(self):
        sched = wacc_schedule(0.12, 0.08, n_years=5, n_constant=3)
        assert len(sched) == 5


class TestTaxSchedule:
    def test_nvidia_tax(self):
        """Nvidia: effective=13.5%, marginal=25%."""
        sched = tax_schedule(0.135, 0.25, n_years=10, n_constant=5)
        assert len(sched) == 10
        # Years 1-5 = effective
        for t in range(5):
            assert sched[t] == pytest.approx(0.135, rel=1e-6)
        # Year 10 = marginal
        assert sched[9] == pytest.approx(0.25, rel=1e-4)
        # Step = (0.25 - 0.135) / 5 = 0.023
        step = (0.25 - 0.135) / 5
        assert sched[5] == pytest.approx(0.135 + step, rel=1e-4)  # year 6

    def test_no_transition_needed(self):
        """When effective == marginal, no ramp."""
        sched = tax_schedule(0.25, 0.25)
        for v in sched:
            assert v == pytest.approx(0.25, abs=1e-10)


class TestMarginConvergence:
    def test_nvidia_declining_margin(self):
        """Nvidia: current=72%, target=60%, convergence_year=5."""
        sched = margin_convergence_schedule(0.72, 0.60, convergence_year=5, n_years=10)
        assert len(sched) == 10
        # Year 1: 0.72 + (0.60 - 0.72) * 1/5 = 0.72 - 0.024 = 0.696
        assert sched[0] == pytest.approx(0.696, rel=1e-4)
        # Year 5 and beyond = target
        assert sched[4] == pytest.approx(0.60, rel=1e-6)
        assert sched[9] == pytest.approx(0.60, rel=1e-6)

    def test_amazon_rising_margin(self):
        """Amazon: current=7.7%, target=12.5%, convergence_year=5."""
        sched = margin_convergence_schedule(0.077, 0.125, convergence_year=5, n_years=10)
        assert sched[0] == pytest.approx(0.077 + (0.125 - 0.077) * 0.2, rel=1e-4)
        assert sched[4] == pytest.approx(0.125, rel=1e-6)
        assert sched[9] == pytest.approx(0.125, rel=1e-6)


class TestReinvestmentS2C:
    def test_basic(self):
        """Simple S2C reinvestment calculation."""
        result = reinvestment_s2c(100, 120, 2.5)
        assert result == pytest.approx(8.0, rel=1e-6)

    def test_zero_growth(self):
        result = reinvestment_s2c(100, 100, 5.0)
        assert result == pytest.approx(0.0, abs=1e-10)

    def test_zero_s2c(self):
        """Zero S2C returns 0 (guard against division by zero)."""
        result = reinvestment_s2c(100, 120, 0)
        assert result == 0.0

    def test_negative_s2c(self):
        result = reinvestment_s2c(100, 120, -1)
        assert result == 0.0


class TestReinvestmentTerminal:
    def test_amazon_terminal(self):
        """Amazon terminal: g=3%, ROC=10%, EBIT(1-t)=59483."""
        result = reinvestment_terminal(0.03, 0.10, 59483)
        assert result == pytest.approx(17844.9, rel=1e-3)

    def test_zero_roc(self):
        result = reinvestment_terminal(0.03, 0, 50000)
        assert result == 0.0


class TestTerminalWaccDefault:
    def test_basic(self):
        """Rf=4.7%, CRP=0 -> 9.2%."""
        result = terminal_wacc_default(0.047)
        assert result == pytest.approx(0.092, rel=1e-6)

    def test_with_crp(self):
        """Rf=5%, CRP=3% -> 12.5%."""
        result = terminal_wacc_default(0.05, 0.03)
        assert result == pytest.approx(0.125, rel=1e-6)
