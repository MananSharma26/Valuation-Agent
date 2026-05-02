"""Sanity bounds checking for valuation inputs and outputs.

Two severity levels:
- WARN: value is unusual but computation proceeds, flag in output
- HALT: value is impossible/dangerous, computation must stop
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Severity(Enum):
    WARN = "warn"
    HALT = "halt"
    OK = "ok"


@dataclass
class BoundsCheck:
    """Result of a single bounds check."""
    field: str
    value: float | None
    severity: Severity
    message: str
    warn_range: tuple[float, float] | None = None
    halt_range: tuple[float, float] | None = None


@dataclass
class BoundsReport:
    """Aggregated results of all bounds checks."""
    checks: list[BoundsCheck] = field(default_factory=list)

    @property
    def has_halt(self) -> bool:
        return any(c.severity == Severity.HALT for c in self.checks)

    @property
    def has_warnings(self) -> bool:
        return any(c.severity == Severity.WARN for c in self.checks)

    @property
    def warnings(self) -> list[BoundsCheck]:
        return [c for c in self.checks if c.severity == Severity.WARN]

    @property
    def halts(self) -> list[BoundsCheck]:
        return [c for c in self.checks if c.severity == Severity.HALT]

    @property
    def ok_count(self) -> int:
        return sum(1 for c in self.checks if c.severity == Severity.OK)


# Define bounds: (warn_low, warn_high, halt_low, halt_high)
# None means no bound on that side
BOUNDS: dict[str, dict] = {
    "beta": {
        "warn": (0.3, 3.5),
        "halt": (0.0, 5.0),
    },
    "wacc": {
        "warn": (0.03, 0.30),
        "halt": (0.0, 0.50),
    },
    "terminal_growth": {
        "warn": (-0.02, 0.06),
        "halt": (-0.10, 0.10),
    },
    "revenue_growth": {
        "warn": (-0.30, 0.60),
        "halt": (-0.80, 1.50),
    },
    "operating_margin": {
        "warn": (-0.50, 0.80),
        "halt": (-1.0, 1.0),
    },
    "shares_outstanding": {
        "warn": (1.0, None),  # must be positive
        "halt": (0.01, None),  # absolutely must be > 0
    },
    "reinvestment_rate": {
        "warn": (-1.0, 2.0),
        "halt": (-3.0, 5.0),
    },
    "debt_to_capital": {
        "warn": (0.0, 0.95),
        "halt": (-0.1, 1.0),
    },
    "cost_of_equity": {
        "warn": (0.02, 0.35),
        "halt": (0.0, 0.60),
    },
    "cost_of_debt": {
        "warn": (0.01, 0.25),
        "halt": (0.0, 0.50),
    },
    "equity_value_per_share": {
        "warn": (0.0, None),
        "halt": (None, None),  # negative equity value is a valid signal for distressed
    },
}


def check_bound(field_name: str, value: float | None) -> BoundsCheck:
    """Check a single value against its defined bounds.

    Returns BoundsCheck with severity OK, WARN, or HALT.
    """
    if value is None:
        return BoundsCheck(
            field=field_name, value=None, severity=Severity.WARN,
            message=f"{field_name} is None (missing data)"
        )

    bounds = BOUNDS.get(field_name)
    if bounds is None:
        return BoundsCheck(
            field=field_name, value=value, severity=Severity.OK,
            message=f"{field_name} = {value:.4f} (no bounds defined)"
        )

    warn_lo, warn_hi = bounds["warn"]
    halt_lo, halt_hi = bounds["halt"]

    # Check halt bounds first
    if halt_lo is not None and value < halt_lo:
        return BoundsCheck(
            field=field_name, value=value, severity=Severity.HALT,
            message=f"{field_name} = {value:.4f} is below halt threshold {halt_lo}",
            warn_range=bounds["warn"], halt_range=bounds["halt"],
        )
    if halt_hi is not None and value > halt_hi:
        return BoundsCheck(
            field=field_name, value=value, severity=Severity.HALT,
            message=f"{field_name} = {value:.4f} is above halt threshold {halt_hi}",
            warn_range=bounds["warn"], halt_range=bounds["halt"],
        )

    # Check warn bounds
    if warn_lo is not None and value < warn_lo:
        return BoundsCheck(
            field=field_name, value=value, severity=Severity.WARN,
            message=f"{field_name} = {value:.4f} is below typical range ({warn_lo}, {warn_hi})",
            warn_range=bounds["warn"], halt_range=bounds["halt"],
        )
    if warn_hi is not None and value > warn_hi:
        return BoundsCheck(
            field=field_name, value=value, severity=Severity.WARN,
            message=f"{field_name} = {value:.4f} is above typical range ({warn_lo}, {warn_hi})",
            warn_range=bounds["warn"], halt_range=bounds["halt"],
        )

    return BoundsCheck(
        field=field_name, value=value, severity=Severity.OK,
        message=f"{field_name} = {value:.4f} is within normal range",
        warn_range=bounds["warn"], halt_range=bounds["halt"],
    )


def check_terminal_vs_wacc(terminal_growth: float | None, wacc: float | None) -> BoundsCheck:
    """Special check: terminal growth must be less than WACC."""
    if terminal_growth is None or wacc is None:
        return BoundsCheck(
            field="terminal_growth_vs_wacc", value=None, severity=Severity.WARN,
            message="Cannot compare terminal growth to WACC (one or both missing)"
        )
    if terminal_growth >= wacc:
        return BoundsCheck(
            field="terminal_growth_vs_wacc", value=terminal_growth - wacc,
            severity=Severity.HALT,
            message=f"Terminal growth ({terminal_growth:.4f}) >= WACC ({wacc:.4f}) — perpetuity formula invalid"
        )
    if terminal_growth > wacc - 0.01:
        return BoundsCheck(
            field="terminal_growth_vs_wacc", value=terminal_growth - wacc,
            severity=Severity.WARN,
            message=f"Terminal growth ({terminal_growth:.4f}) very close to WACC ({wacc:.4f}) — value will be extremely sensitive"
        )
    return BoundsCheck(
        field="terminal_growth_vs_wacc", value=terminal_growth - wacc,
        severity=Severity.OK,
        message=f"Terminal growth ({terminal_growth:.4f}) < WACC ({wacc:.4f}) — OK"
    )


def check_all_inputs(inputs: dict[str, float | None]) -> BoundsReport:
    """Run bounds checks on all provided inputs.

    Args:
        inputs: dict mapping field names to values (field names must match BOUNDS keys)

    Returns:
        BoundsReport with all check results
    """
    report = BoundsReport()
    for field_name, value in inputs.items():
        report.checks.append(check_bound(field_name, value))

    # Special cross-field checks
    if "terminal_growth" in inputs and "wacc" in inputs:
        report.checks.append(check_terminal_vs_wacc(inputs["terminal_growth"], inputs["wacc"]))

    return report
