"""Deterministic confidence scoring for valuation outputs.

Computes four sub-scores and a weighted composite:
  1. data_completeness (weight 0.30): % of required fields present
  2. model_agreement (weight 0.30): 1 - normalized divergence across models
  3. assumption_sensitivity (weight 0.25): 1 - (max-min)/base from sensitivity table
  4. industry_coverage (weight 0.15): fuzzy match score from industry mapper

Also generates human-readable warning flags.

All computation is deterministic Python — no LLM calls.
"""

from __future__ import annotations

from typing import Any

_WEIGHTS = {
    "data_completeness": 0.30,
    "model_agreement": 0.30,
    "assumption_sensitivity": 0.25,
    "industry_coverage": 0.15,
}


def score_data_completeness(fields: dict[str, bool]) -> float:
    """Compute data completeness as fraction of required fields present.

    Parameters
    ----------
    fields : dict[str, bool]
        Map of field name -> whether it is present and non-null.

    Returns
    -------
    float
        Score in [0.0, 1.0].
    """
    if not fields:
        return 0.0
    return sum(1 for v in fields.values() if v) / len(fields)


def score_model_agreement(values: dict[str, float]) -> float:
    """Compute model agreement as 1 - normalized divergence.

    Normalized divergence = (max - min) / mean of positive model values.

    Parameters
    ----------
    values : dict[str, float]
        Model name -> equity value per share. Negative values are excluded
        (they indicate a model failure).

    Returns
    -------
    float
        Score in [0.0, 1.0].
    """
    positive = [v for v in values.values() if v > 0]
    if len(positive) == 0:
        return 0.0
    if len(positive) == 1:
        return 1.0

    mean_val = sum(positive) / len(positive)
    if mean_val == 0:
        return 0.0

    divergence = (max(positive) - min(positive)) / mean_val
    return max(0.0, 1.0 - divergence)


def score_assumption_sensitivity(
    base_value: float,
    min_value: float,
    max_value: float,
) -> float:
    """Compute assumption sensitivity as 1 - (max-min)/base.

    Parameters
    ----------
    base_value : float
        Base-case valuation.
    min_value : float
        Minimum valuation from sensitivity analysis.
    max_value : float
        Maximum valuation from sensitivity analysis.

    Returns
    -------
    float
        Score in [0.0, 1.0].
    """
    if base_value == 0:
        return 0.0
    sensitivity = (max_value - min_value) / abs(base_value)
    return max(0.0, 1.0 - sensitivity)


def score_industry_coverage(match_score: float) -> float:
    """Convert a fuzzy match score (0-100) to a 0-1 score.

    Parameters
    ----------
    match_score : float
        Fuzzy match score from the industry mapper (0-100 scale).

    Returns
    -------
    float
        Score in [0.0, 1.0].
    """
    return max(0.0, min(1.0, match_score / 100.0))


def compute_composite_score(
    data_completeness: float,
    model_agreement: float,
    assumption_sensitivity: float,
    industry_coverage: float,
) -> float:
    """Compute the weighted composite confidence score.

    Weights: data_completeness=0.30, model_agreement=0.30,
             assumption_sensitivity=0.25, industry_coverage=0.15

    Parameters
    ----------
    data_completeness : float
        Score in [0, 1].
    model_agreement : float
        Score in [0, 1].
    assumption_sensitivity : float
        Score in [0, 1].
    industry_coverage : float
        Score in [0, 1].

    Returns
    -------
    float
        Composite score in [0.0, 1.0].
    """
    return (
        _WEIGHTS["data_completeness"] * data_completeness
        + _WEIGHTS["model_agreement"] * model_agreement
        + _WEIGHTS["assumption_sensitivity"] * assumption_sensitivity
        + _WEIGHTS["industry_coverage"] * industry_coverage
    )


def generate_flags(
    data_completeness: float,
    model_agreement: float,
    assumption_sensitivity: float,
    industry_coverage: float,
    model_values: dict[str, float] | None = None,
) -> list[str]:
    """Generate human-readable warning flags based on sub-scores.

    Parameters
    ----------
    data_completeness : float
    model_agreement : float
    assumption_sensitivity : float
    industry_coverage : float
    model_values : dict[str, float] or None
        Model name -> value, used to detect single-model valuations.

    Returns
    -------
    list[str]
        List of warning strings. Empty list if no warnings.
    """
    flags: list[str] = []

    if data_completeness < 0.5:
        flags.append(
            f"Low data completeness ({data_completeness:.0%}): "
            f"key financial fields are missing, which may reduce accuracy."
        )

    if model_agreement < 0.5:
        flags.append(
            f"Models diverge significantly (agreement={model_agreement:.0%}): "
            f"review assumptions across models."
        )

    if assumption_sensitivity < 0.5:
        flags.append(
            f"High sensitivity to assumptions (score={assumption_sensitivity:.0%}): "
            f"small changes in inputs cause large valuation swings."
        )

    if industry_coverage < 0.5:
        flags.append(
            f"Weak industry match (coverage={industry_coverage:.0%}): "
            f"industry benchmarks may not be representative."
        )

    if model_values is not None:
        positive_models = [k for k, v in model_values.items() if v > 0]
        if len(positive_models) == 1:
            flags.append(
                f"Only one model ({positive_models[0]}) produced a valid value: "
                f"cross-validation not possible."
            )

    return flags


def _extract_model_values(ctx: "ValuationContext") -> dict[str, float]:
    """Extract per-share values from all model outputs on the context."""
    values: dict[str, float] = {}

    if ctx.outputs.dcf_fcff and "equity_value_per_share" in ctx.outputs.dcf_fcff:
        values["dcf_fcff"] = ctx.outputs.dcf_fcff["equity_value_per_share"]

    if ctx.outputs.dcf_fcfe and "value_per_share" in ctx.outputs.dcf_fcfe:
        values["dcf_fcfe"] = ctx.outputs.dcf_fcfe["value_per_share"]

    if ctx.outputs.relative:
        # Take the average of available relative valuations
        rel_vals = [
            v for k, v in ctx.outputs.relative.items()
            if k.startswith("implied_value_") and isinstance(v, (int, float)) and v > 0
        ]
        if rel_vals:
            values["relative"] = sum(rel_vals) / len(rel_vals)

    if ctx.outputs.excess_returns and "value_per_share" in ctx.outputs.excess_returns:
        values["excess_returns"] = ctx.outputs.excess_returns["value_per_share"]

    return values


def _extract_field_presence(ctx: "ValuationContext") -> dict[str, bool]:
    """Check which required data fields are present."""
    stats = ctx.financials.key_stats or {}
    return {
        "income_statement": ctx.financials.income_statement is not None,
        "balance_sheet": ctx.financials.balance_sheet is not None,
        "cash_flow": ctx.financials.cash_flow is not None,
        "shares_outstanding": bool(stats.get("shares_outstanding")),
        "market_cap": bool(stats.get("market_cap")),
        "price": bool(stats.get("price")),
        "beta": stats.get("beta") is not None,
        "book_value_per_share": bool(stats.get("book_value_per_share")),
    }


def score_all(
    ctx: "ValuationContext",
    industry_match_score: float = 0.0,
    sensitivity_base: float | None = None,
    sensitivity_min: float | None = None,
    sensitivity_max: float | None = None,
) -> None:
    """Compute all confidence scores and populate ctx.confidence in-place.

    Parameters
    ----------
    ctx : ValuationContext
        Must have outputs and financials populated.
    industry_match_score : float
        Fuzzy match score (0-100) from the industry mapper.
    sensitivity_base : float or None
        Base-case valuation for sensitivity scoring. If None, uses DCF value.
    sensitivity_min : float or None
        Minimum valuation from sensitivity table.
    sensitivity_max : float or None
        Maximum valuation from sensitivity table.
    """
    # Data completeness
    field_presence = _extract_field_presence(ctx)
    dc = score_data_completeness(field_presence)

    # Model agreement
    model_values = _extract_model_values(ctx)
    ma = score_model_agreement(model_values)

    # Assumption sensitivity
    if sensitivity_base is not None and sensitivity_min is not None and sensitivity_max is not None:
        as_score = score_assumption_sensitivity(sensitivity_base, sensitivity_min, sensitivity_max)
    else:
        # Default: extract from sensitivity table on context if available
        if ctx.outputs.sensitivity and isinstance(ctx.outputs.sensitivity, dict):
            sens_vals = [
                v for v in ctx.outputs.sensitivity.values()
                if isinstance(v, (int, float)) and not isinstance(v, bool)
            ]
            if sens_vals and model_values:
                base = list(model_values.values())[0]
                as_score = score_assumption_sensitivity(base, min(sens_vals), max(sens_vals))
            else:
                as_score = 0.5  # neutral default
        else:
            as_score = 0.5  # neutral default

    # Industry coverage
    ic = score_industry_coverage(industry_match_score)

    # Composite
    composite = compute_composite_score(dc, ma, as_score, ic)

    # Flags
    flags = generate_flags(dc, ma, as_score, ic, model_values)

    # Populate context
    ctx.confidence.data_completeness = dc
    ctx.confidence.model_agreement = ma
    ctx.confidence.assumption_sensitivity = as_score
    ctx.confidence.industry_coverage = ic
    ctx.confidence.composite = composite
    ctx.confidence.flags = flags
