"""Source tracking for valuation data points.

Every numeric value flowing through the pipeline gets tagged with:
- where it came from (source)
- how confident we are in it (confidence)
- optional notes
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


Source = Literal[
    "compustat",
    "yahoo_finance",
    "damodaran_industry",
    "user_input",
    "assumed_default",
    "computed",
    "missing",
]


@dataclass
class SourcedValue:
    """A numeric value tagged with its data source and confidence."""

    value: float | None
    source: Source
    confidence: float  # 1.0=hard data, 0.7=computed, 0.5=industry proxy, 0.2=assumed default, 0.0=missing
    note: str = ""

    @property
    def is_available(self) -> bool:
        return self.value is not None and self.source != "missing"

    @property
    def is_proxy(self) -> bool:
        return self.source in ("damodaran_industry", "assumed_default")

    def __float__(self) -> float:
        if self.value is None:
            raise ValueError(f"Cannot convert missing SourcedValue to float (note: {self.note})")
        return float(self.value)

    def __repr__(self) -> str:
        if self.value is None:
            return f"SourcedValue(MISSING, source={self.source})"
        return f"SourcedValue({self.value}, source={self.source}, conf={self.confidence})"


def sourced(value: float | None, source: Source, confidence: float = 1.0, note: str = "") -> SourcedValue:
    """Convenience constructor."""
    if value is None:
        return SourcedValue(value=None, source="missing", confidence=0.0, note=note)
    return SourcedValue(value=value, source=source, confidence=confidence, note=note)


def from_yahoo(value: float | None, note: str = "") -> SourcedValue:
    return sourced(value, "yahoo_finance", 0.9, note)

def from_compustat(value: float | None, note: str = "") -> SourcedValue:
    return sourced(value, "compustat", 0.95, note)

def from_damodaran(value: float | None, note: str = "") -> SourcedValue:
    return sourced(value, "damodaran_industry", 0.5, note)

def from_user(value: float, note: str = "") -> SourcedValue:
    return sourced(value, "user_input", 1.0, note)

def computed(value: float | None, note: str = "") -> SourcedValue:
    return sourced(value, "computed", 0.7, note)

def missing(note: str = "") -> SourcedValue:
    return SourcedValue(value=None, source="missing", confidence=0.0, note=note)
