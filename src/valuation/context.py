"""Shared data contract for the valuation pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd


@dataclass
class CompanyInfo:
    ticker: str
    name: str | None = None
    sector: str | None = None
    sic_code: str | None = None
    classification: str | None = None
    damodaran_industry: str | None = None
    region: str = "US"


@dataclass
class Financials:
    income_statement: pd.DataFrame | None = None
    balance_sheet: pd.DataFrame | None = None
    cash_flow: pd.DataFrame | None = None
    key_stats: dict[str, Any] = field(default_factory=dict)


@dataclass
class Benchmarks:
    industry_beta: float | None = None
    industry_unlevered_beta: float | None = None
    industry_de_ratio: float | None = None
    industry_multiples: dict[str, float] = field(default_factory=dict)
    industry_margins: dict[str, float] = field(default_factory=dict)
    industry_growth: dict[str, float] = field(default_factory=dict)
    industry_wacc: float | None = None


@dataclass
class Assumptions:
    risk_free_rate: float | None = None
    erp: float | None = None
    country_risk_premium: float = 0.0
    beta: float | None = None
    cost_of_equity: float | None = None
    cost_of_debt: float | None = None
    wacc: float | None = None
    growth_rates: list[float] = field(default_factory=list)
    terminal_growth: float | None = None
    projection_years: int = 10
    tax_rate: float | None = None
    overrides: dict[str, dict] = field(default_factory=dict)

    def set_override(self, param: str, new_value: float, reason: str = "") -> None:
        original = getattr(self, param)
        self.overrides[param] = {
            "original": original,
            "new": new_value,
            "reason": reason,
        }
        setattr(self, param, new_value)


@dataclass
class Outputs:
    dcf_fcff: dict[str, Any] | None = None
    dcf_fcfe: dict[str, Any] | None = None
    relative: dict[str, Any] | None = None
    excess_returns: dict[str, Any] | None = None
    sensitivity: dict[str, Any] | None = None


@dataclass
class Confidence:
    data_completeness: float | None = None
    model_agreement: float | None = None
    assumption_sensitivity: float | None = None
    industry_coverage: float | None = None
    composite: float | None = None
    flags: list[str] = field(default_factory=list)


@dataclass
class ValuationContext:
    """Central data structure passed through the entire valuation pipeline."""

    company: CompanyInfo = field(init=False)
    financials: Financials = field(default_factory=Financials)
    benchmarks: Benchmarks = field(default_factory=Benchmarks)
    assumptions: Assumptions = field(default_factory=Assumptions)
    outputs: Outputs = field(default_factory=Outputs)
    confidence: Confidence = field(default_factory=Confidence)

    def __init__(self, ticker: str, region: str = "US"):
        self.company = CompanyInfo(ticker=ticker, region=region)
        self.financials = Financials()
        self.benchmarks = Benchmarks()
        self.assumptions = Assumptions()
        self.outputs = Outputs()
        self.confidence = Confidence()

    def to_summary_dict(self) -> dict[str, Any]:
        return {
            "ticker": self.company.ticker,
            "name": self.company.name,
            "classification": self.company.classification,
            "damodaran_industry": self.company.damodaran_industry,
            "region": self.company.region,
            "wacc": self.assumptions.wacc,
            "dcf_value": (
                self.outputs.dcf_fcff.get("equity_value_per_share")
                if self.outputs.dcf_fcff
                else None
            ),
            "confidence": self.confidence.composite,
            "overrides": list(self.assumptions.overrides.keys()),
        }
