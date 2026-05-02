"""Pre-engine validation: ensure all required inputs exist and are sane before running valuation engines."""

from __future__ import annotations

from dataclasses import dataclass, field

from valuation.context import ValuationContext
from valuation.validation.bounds import check_all_inputs, BoundsReport, Severity


@dataclass
class MissingField:
    """A required field that is missing."""
    name: str
    impact: str  # "critical" | "moderate" | "low"
    suggestion: str  # what to do about it


@dataclass
class ValidationReport:
    """Result of pre-engine validation."""
    can_proceed: bool
    missing_fields: list[MissingField] = field(default_factory=list)
    bounds_report: BoundsReport | None = None
    warnings: list[str] = field(default_factory=list)

    @property
    def critical_missing(self) -> list[MissingField]:
        return [f for f in self.missing_fields if f.impact == "critical"]

    @property
    def summary(self) -> str:
        if self.can_proceed and not self.warnings:
            return "All inputs validated — clear to run engines"
        parts = []
        if self.critical_missing:
            parts.append(f"{len(self.critical_missing)} critical fields missing — HALTED")
        if self.warnings:
            parts.append(f"{len(self.warnings)} warnings")
        if self.bounds_report and self.bounds_report.has_halt:
            parts.append(f"{len(self.bounds_report.halts)} bounds violations — HALTED")
        return "; ".join(parts) if parts else "Validated with warnings"


# Define required fields per model type
FCFF_REQUIRED = {
    "critical": ["wacc", "terminal_growth", "shares_outstanding"],
    "moderate": ["beta", "tax_rate", "cost_of_equity", "cost_of_debt"],
    "low": ["growth_rates"],
}

DDM_REQUIRED = {
    "critical": ["cost_of_equity", "terminal_growth", "shares_outstanding"],
    "moderate": ["beta", "tax_rate"],
    "low": ["growth_rates"],
}

GORDON_REQUIRED = {
    "critical": ["cost_of_equity", "terminal_growth"],
    "moderate": [],
    "low": [],
}


def _get_assumption_value(ctx: ValuationContext, field_name: str) -> float | None:
    """Extract a value from assumptions or key_stats."""
    val = getattr(ctx.assumptions, field_name, None)
    if val is not None:
        return val
    return ctx.financials.key_stats.get(field_name)


def validate_for_dcf(ctx: ValuationContext, model: str = "fcff") -> ValidationReport:
    """Validate that a ValuationContext has all required inputs for a DCF model.

    Args:
        ctx: The valuation context to validate
        model: "fcff", "ddm", or "gordon_growth"

    Returns:
        ValidationReport indicating whether engines can proceed
    """
    if model == "ddm":
        required = DDM_REQUIRED
    elif model == "gordon_growth":
        required = GORDON_REQUIRED
    else:
        required = FCFF_REQUIRED

    report = ValidationReport(can_proceed=True)

    # Check missing fields
    for impact, fields in required.items():
        for f in fields:
            val = _get_assumption_value(ctx, f)
            if val is None:
                suggestion = _suggest_fix(f)
                report.missing_fields.append(MissingField(name=f, impact=impact, suggestion=suggestion))
                if impact == "critical":
                    report.can_proceed = False

    # Run bounds checks on available values
    bounds_inputs = {}
    for f in ["beta", "wacc", "terminal_growth", "cost_of_equity", "cost_of_debt",
              "tax_rate"]:
        val = _get_assumption_value(ctx, f)
        if val is not None:
            bounds_inputs[f] = val

    shares = ctx.financials.key_stats.get("shares_outstanding")
    if shares is not None:
        bounds_inputs["shares_outstanding"] = shares

    report.bounds_report = check_all_inputs(bounds_inputs)

    if report.bounds_report.has_halt:
        report.can_proceed = False
        for halt in report.bounds_report.halts:
            report.warnings.append(f"HALT: {halt.message}")

    for warn in report.bounds_report.warnings:
        report.warnings.append(f"WARNING: {warn.message}")

    return report


def _suggest_fix(field_name: str) -> str:
    """Suggest how to fix a missing field."""
    suggestions = {
        "wacc": "Run risk_assessor.compute_wacc() with beta, ERP, and cost of debt",
        "terminal_growth": "Set to risk-free rate minus 1% (Damodaran convention)",
        "shares_outstanding": "Fetch from API or enter manually",
        "beta": "Use industry unlevered beta from Damodaran betas.xls, re-lever with company D/E",
        "tax_rate": "Use effective tax rate from financials or marginal rate from Damodaran",
        "cost_of_equity": "Compute via CAPM: Rf + Beta * ERP + Lambda * CRP",
        "cost_of_debt": "Compute via synthetic rating from interest coverage ratio",
        "growth_rates": "Run growth_estimator.estimate_all_growth_rates(ctx)",
    }
    return suggestions.get(field_name, "Provide this value manually")
