"""Loader for Damodaran dataset Excel files.

Handles ~244 .xls/.xlsx files across 9 category subdirectories, with automatic
header detection, sheet selection, and industry lookup.
"""

from __future__ import annotations

import pathlib
from functools import lru_cache
from typing import Optional

import pandas as pd


# Maps base_name -> category subdirectory
_BASE_TO_CATEGORY: dict[str, str] = {
    # risk_discount_rate
    "betas": "risk_discount_rate",
    "beta": "risk_discount_rate",
    "totalbeta": "risk_discount_rate",
    "wacc": "risk_discount_rate",
    "taxrate": "risk_discount_rate",
    "countrytaxrates": "risk_discount_rate",
    "ctryprem": "risk_discount_rate",
    "ctrypremApr26": "risk_discount_rate",
    "ctrypremJuly25": "risk_discount_rate",
    "histimpl": "risk_discount_rate",
    "histretSP": "risk_discount_rate",
    "mktcaprisk": "risk_discount_rate",
    # multiples
    "pedata": "multiples",
    "pe": "multiples",
    "pbvdata": "multiples",
    "pbv": "multiples",
    "psdata": "multiples",
    "ps": "multiples",
    "vebitda": "multiples",
    "countrystats": "multiples",
    "mktcapmult": "multiples",
    # cash_flow_estimation
    "capex": "cash_flow_estimation",
    "margin": "cash_flow_estimation",
    "wcdata": "cash_flow_estimation",
    "R&D": "cash_flow_estimation",
    "finflows": "cash_flow_estimation",
    "goodwill": "cash_flow_estimation",
    # capital_structure
    "dbtfund": "capital_structure",
    "debtdetails": "capital_structure",
    "leaseeffect": "capital_structure",
    "macro": "capital_structure",
    "macrodur": "capital_structure",
    "ratings": "capital_structure",
    # growth_rate_estimation
    "fundgr": "growth_rate_estimation",
    "fundgrEB": "growth_rate_estimation",
    "histgr": "growth_rate_estimation",
    "roe": "growth_rate_estimation",
    # dividend_policy
    "divfcfe": "dividend_policy",
    "divfund": "dividend_policy",
    # investment_returns
    "DollarUS": "investment_returns",
    "Dollar": "investment_returns",
    "EVA": "investment_returns",
    "Employee": "investment_returns",
    "MktCap": "investment_returns",
    # corporate_governance
    "inshold": "corporate_governance",
    # option_pricing
    "optvar": "option_pricing",
}

# Region suffix mapping
_REGION_SUFFIXES: dict[str, str] = {
    "US": "",
    "Europe": "Europe",
    "Japan": "Japan",
    "India": "India",
    "China": "China",
    "Emerging": "emerg",
    "AusNZCanada": "Rest",
    "Global": "Global",
}

# Files that have no regional variants (single file, use as-is)
_SINGLE_FILES: set[str] = {
    "histretSP",
    "histimpl",
    "ctryprem",
    "ctrypremApr26",
    "ctrypremJuly25",
    "countrytaxrates",
    "mktcaprisk",
    "mktcapmult",
    "countrystats",
    "macro",
    "macrodur",
    "ratings",
}

# US filenames that differ from the regional base (US name -> regional base)
_US_SPECIAL_NAMES: dict[str, str] = {
    "betas": "beta",
    "pedata": "pe",
    "pbvdata": "pbv",
    "psdata": "ps",
    "DollarUS": "Dollar",
}

# Priority order for picking a data sheet
_SHEET_PRIORITY: list[str] = [
    "Industry Averages",
    "Industry Values",
    "ERPs by country",
    "Returns by year",
    "Historical Impl Premiums",
    "Start here Ratings sheet",
    "Annual Data",
]

# Keywords to detect the header row
_HEADER_KEYWORDS: set[str] = {
    "Industry Name",
    "Country",
    "Year",
    "Date",
    "Market Cap",
    "Market Cap Decile",
    "Market Cap in millions of US$",
}


class DamodaranLoader:
    """Loads and queries Damodaran industry/country/time-series Excel data."""

    def __init__(self, data_dir: str | pathlib.Path) -> None:
        self.data_dir = pathlib.Path(data_dir)
        if not self.data_dir.exists():
            raise FileNotFoundError(f"Data directory not found: {self.data_dir}")
        self.categories: set[str] = {
            d.name for d in self.data_dir.iterdir() if d.is_dir()
        }

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def load(self, base_name: str, region: str = "US") -> pd.DataFrame:
        """Load a Damodaran file by base name and region into a DataFrame."""
        path = self._resolve_path(base_name, region)
        return self.load_file(path)

    def load_file(self, path: str | pathlib.Path) -> pd.DataFrame:
        """Load any Damodaran Excel file, auto-detecting header and sheet."""
        path = pathlib.Path(path)
        return self._load_cached(str(path))

    def lookup(
        self,
        base_name: str,
        industry: str,
        region: str = "US",
    ) -> Optional[pd.Series]:
        """Return a single row (Series) for a given industry, or None."""
        df = self.load(base_name, region=region)
        # Find the industry name column
        key_col = self._find_key_column(df)
        if key_col is None:
            return None
        mask = df[key_col].astype(str).str.strip() == industry.strip()
        matches = df.loc[mask]
        if matches.empty:
            return None
        return matches.iloc[0]

    def list_industries(self, region: str = "US") -> list[str]:
        """Return a sorted list of industry names from the betas file."""
        df = self.load("betas", region=region)
        key_col = self._find_key_column(df)
        if key_col is None:
            return []
        names = df[key_col].dropna().astype(str).str.strip().tolist()
        # Filter out empty or aggregate rows
        names = [n for n in names if n and n != "Total Market"]
        return sorted(names)

    # ------------------------------------------------------------------
    # Path resolution
    # ------------------------------------------------------------------

    def _resolve_path(self, base_name: str, region: str) -> pathlib.Path:
        """Resolve base_name + region to an actual file path."""
        # Handle ctryprem special case: prefer most recent dated version
        if base_name == "ctryprem":
            for candidate in ("ctrypremApr26", "ctrypremJuly25", "ctryprem"):
                cat = _BASE_TO_CATEGORY.get(candidate, "risk_discount_rate")
                for ext in (".xlsx", ".xls"):
                    p = self.data_dir / cat / f"{candidate}{ext}"
                    if p.exists():
                        return p

        # Single files (no regional variants)
        if base_name in _SINGLE_FILES:
            return self._find_file(base_name)

        # Regional resolution
        suffix = _REGION_SUFFIXES.get(region, "")

        if suffix == "":
            # US version: use the base_name as-is (e.g. "betas", "pedata", "DollarUS")
            return self._find_file(base_name)
        else:
            # Regional version: need the regional base
            regional_base = _US_SPECIAL_NAMES.get(base_name, base_name)
            filename = f"{regional_base}{suffix}"
            return self._find_file(filename)

    def _find_file(self, name: str) -> pathlib.Path:
        """Find a file by name across all category dirs, trying .xls and .xlsx."""
        # First try using the category mapping
        cat = _BASE_TO_CATEGORY.get(name)
        if cat:
            for ext in (".xls", ".xlsx"):
                p = self.data_dir / cat / f"{name}{ext}"
                if p.exists():
                    return p

        # Fallback: scan all category directories
        for cat_dir in self.data_dir.iterdir():
            if not cat_dir.is_dir():
                continue
            for ext in (".xls", ".xlsx"):
                p = cat_dir / f"{name}{ext}"
                if p.exists():
                    return p

        raise FileNotFoundError(
            f"Cannot find file for '{name}' in {self.data_dir}"
        )

    # ------------------------------------------------------------------
    # Loading internals
    # ------------------------------------------------------------------

    @lru_cache(maxsize=256)
    def _load_cached(self, path_str: str) -> pd.DataFrame:
        path = pathlib.Path(path_str)
        engine = "xlrd" if path.suffix == ".xls" else "openpyxl"

        # Get sheet names
        xf = pd.ExcelFile(path, engine=engine)
        sheet_name = self._pick_data_sheet(xf.sheet_names)

        # Read raw (no header) to detect header row
        raw = pd.read_excel(
            xf, sheet_name=sheet_name, header=None, dtype=str
        )
        header_row = self._find_header_row(raw)

        # Re-read with the detected header
        df = pd.read_excel(
            xf, sheet_name=sheet_name, header=header_row
        )
        xf.close()

        # Clean up column names
        df.columns = [
            str(c).strip() if not str(c).startswith("Unnamed") else c
            for c in df.columns
        ]

        # Drop fully empty rows and columns
        df = df.dropna(how="all").dropna(axis=1, how="all")

        # Reset index
        df = df.reset_index(drop=True)

        return df

    @staticmethod
    def _pick_data_sheet(sheet_names: list[str]) -> str:
        """Choose the best data sheet from available sheet names."""
        for preferred in _SHEET_PRIORITY:
            if preferred in sheet_names:
                return preferred

        # Fallback: first sheet that isn't a FAQ / explanations / variables sheet
        skip = {"Explanations & FAQ", "Explanations and FAQ", "Variables & FAQ",
                "Explanation and FAQ", "Read me first"}
        for name in sheet_names:
            if name not in skip:
                return name

        # Last resort: first sheet
        return sheet_names[0]

    @staticmethod
    def _find_header_row(raw: pd.DataFrame) -> int:
        """Scan first 25 rows for a header row containing known keywords."""
        scan_limit = min(25, len(raw))
        for i in range(scan_limit):
            row_values = [str(v).strip() for v in raw.iloc[i].values]
            for kw in _HEADER_KEYWORDS:
                if kw in row_values:
                    return i
        # If no keyword found, look for a row where most cells are non-empty
        # strings (heuristic for header detection)
        for i in range(scan_limit):
            row_values = raw.iloc[i].values
            non_empty = sum(
                1 for v in row_values
                if pd.notna(v) and str(v).strip() != ""
            )
            if non_empty >= 3 and all(
                isinstance(v, str) or pd.isna(v) for v in row_values
            ):
                return i
        return 0

    @staticmethod
    def _find_key_column(df: pd.DataFrame) -> Optional[str]:
        """Find the primary key column (Industry Name, Country, etc.)."""
        for col in df.columns:
            col_clean = str(col).strip()
            if col_clean in (
                "Industry Name",
                "Country",
                "Year",
                "Market Cap Decile",
                "Market Cap in millions of US$",
            ):
                return col
        # Fallback: first column
        if len(df.columns) > 0:
            return df.columns[0]
        return None
