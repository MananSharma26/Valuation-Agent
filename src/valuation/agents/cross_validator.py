"""Cross-validate valuation outputs across models.

Compares outputs from DCF (FCFF/FCFE), relative valuation, and excess returns.
Computes divergence, flags outliers, and returns a structured comparison.

All computation is deterministic — the LLM interprets results later.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from typing import Any


@dataclass
class CrossValidationResult:
    """Structured result from cross-validating multiple valuation models."""

    individual_values: dict[str, float] = field(default_factory=dict)
    mean_value: float = 0.0
    median_value: float = 0.0
    min_value: float = 0.0
    max_value: float = 0.0
    max_divergence_pct: float = 0.0
    price_vs_value_pct: float = 0.0
    num_models: int = 0
    flags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dict for JSON output or context storage."""
        return {
            "individual_values": self.individual_values,
            "mean_value": self.mean_value,
            "median_value": self.median_value,
            "min_value": self.min_value,
            "max_value": self.max_value,
            "max_divergence_pct": self.max_divergence_pct,
            "price_vs_value_pct": self.price_vs_value_pct,
            "num_models": self.num_models,
            "flags": self.flags,
        }


def _extract_values(model_outputs: dict[str, dict]) -> dict[str, float]:
    """Extract per-share values from model output dicts.

    Handles different output formats:
      - dcf_fcff / dcf_fcfe: key "equity_value_per_share" or "value_per_share"
      - relative: keys like "implied_value_pe", "implied_value_eveb", etc.
      - excess_returns: key "value_per_share"

    Returns dict mapping descriptive name -> value.
    Excludes negative values (model failures).
    """
    values: dict[str, float] = {}

    for model_name, output in model_outputs.items():
        if not isinstance(output, dict):
            continue

        if model_name in ("dcf_fcff", "dcf_fcfe"):
            for key in ("equity_value_per_share", "value_per_share"):
                if key in output:
                    val = float(output[key])
                    if val > 0:
                        values[model_name] = val
                    break

        elif model_name == "relative":
            # Check both naming conventions
            rel_keys = {
                "pe_value": "relative_pe",
                "ev_ebitda_value": "relative_ev_ebitda",
                "pbv_value": "relative_pbv",
                "ps_value": "relative_ps",
                "composite_value": "relative_composite",
            }
            for key, label in rel_keys.items():
                if key in output and output[key] is not None:
                    fval = float(output[key])
                    if fval > 0:
                        values[label] = fval
            # Also check implied_value_ prefix
            for key, val in output.items():
                if key.startswith("implied_value_") and isinstance(val, (int, float)):
                    fval = float(val)
                    if fval > 0:
                        suffix = key.replace("implied_value_", "")
                        values[f"relative_{suffix}"] = fval

        elif model_name == "excess_returns":
            if "value_per_share" in output:
                val = float(output["value_per_share"])
                if val > 0:
                    values["excess_returns"] = val

        else:
            # Generic: look for common value keys
            for key in ("equity_value_per_share", "value_per_share", "value"):
                if key in output:
                    val = float(output[key])
                    if val > 0:
                        values[model_name] = val
                    break

    return values


def cross_validate(
    model_outputs: dict[str, dict],
    price: float,
) -> CrossValidationResult:
    """Cross-validate valuation model outputs.

    Parameters
    ----------
    model_outputs : dict[str, dict]
        Map of model name -> model output dict. Expected keys:
        "dcf_fcff", "dcf_fcfe", "relative", "excess_returns".
    price : float
        Current market price per share.

    Returns
    -------
    CrossValidationResult
        Structured comparison with divergence metrics and flags.
    """
    values = _extract_values(model_outputs)
    result = CrossValidationResult()
    result.individual_values = values

    if not values:
        return result

    val_list = list(values.values())
    result.num_models = len(val_list)
    result.mean_value = statistics.mean(val_list)
    result.median_value = statistics.median(val_list)
    result.min_value = min(val_list)
    result.max_value = max(val_list)

    # Divergence: (max - min) / mean
    if result.mean_value > 0 and result.num_models > 1:
        result.max_divergence_pct = (result.max_value - result.min_value) / result.mean_value
    else:
        result.max_divergence_pct = 0.0

    # Price vs intrinsic value: (mean_value - price) / price
    if price > 0:
        result.price_vs_value_pct = (result.mean_value - price) / price
    else:
        result.price_vs_value_pct = 0.0

    # --- Generate flags ---
    flags: list[str] = []

    # Flag: large model divergence (>30%)
    if result.max_divergence_pct > 0.30:
        spread = result.max_value - result.min_value
        flags.append(
            f"Large model spread: ${spread:,.2f} ({result.max_divergence_pct:.0%} divergence). "
            f"Range: ${result.min_value:,.2f} to ${result.max_value:,.2f}."
        )

    # Flag: significant undervaluation (>25% upside)
    if result.price_vs_value_pct > 0.25:
        flags.append(
            f"Potentially undervalued: intrinsic value (${result.mean_value:,.2f}) is "
            f"{result.price_vs_value_pct:.0%} above market price (${price:,.2f})."
        )

    # Flag: significant overvaluation (>25% downside)
    if result.price_vs_value_pct < -0.25:
        flags.append(
            f"Potentially overvalued: intrinsic value (${result.mean_value:,.2f}) is "
            f"{abs(result.price_vs_value_pct):.0%} below market price (${price:,.2f})."
        )

    # Flag: individual model outlier (>2x or <0.5x the median)
    if result.num_models >= 3:
        for name, val in values.items():
            if val > 2 * result.median_value:
                flags.append(
                    f"Outlier: {name} (${val:,.2f}) is >2x the median (${result.median_value:,.2f})."
                )
            elif val < 0.5 * result.median_value:
                flags.append(
                    f"Outlier: {name} (${val:,.2f}) is <0.5x the median (${result.median_value:,.2f})."
                )

    result.flags = flags
    return result


def explain_divergence(result: CrossValidationResult, ctx: Any = None) -> str:
    """Generate a text explanation of model divergence for the report.

    This is deterministic text — the LLM can elaborate on it.
    """
    if result.num_models < 2:
        return ""

    if result.max_divergence_pct < 0.15:
        return "Models are in strong agreement (divergence < 15%)."

    lines = []
    vals = result.individual_values

    dcf_val = vals.get("dcf_fcff") or vals.get("dcf_fcfe")
    rel_val = vals.get("relative_composite")

    if dcf_val and rel_val:
        if dcf_val < rel_val:
            lines.append(
                f"DCF ({dcf_val:,.0f}) is below relative valuation ({rel_val:,.0f})."
            )
            lines.append("Possible reasons:")
            lines.append(
                "- Our growth/margin assumptions may be conservative vs what the market prices in"
            )
            lines.append(
                "- Industry multiples may be elevated due to sector momentum"
            )
            lines.append(
                "- DCF captures company-specific risk that multiples averaging smooths out"
            )
        else:
            lines.append(
                f"DCF ({dcf_val:,.0f}) is above relative valuation ({rel_val:,.0f})."
            )
            lines.append("Possible reasons:")
            lines.append(
                "- Our growth assumptions may be more optimistic than the market"
            )
            lines.append(
                "- Industry multiples may be depressed (sector rotation, sentiment)"
            )
            lines.append(
                "- Company may have competitive advantages not reflected in peer multiples"
            )

    if result.max_divergence_pct > 0.40:
        lines.append("")
        lines.append(
            f"High divergence ({result.max_divergence_pct:.0%}) — treat valuation range with caution."
        )

    return "\n".join(lines)
