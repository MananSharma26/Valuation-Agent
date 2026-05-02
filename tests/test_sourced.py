"""Tests for SourcedValue wrapper and data_sources utilities."""

import pytest

from valuation.validation.sourced import (
    SourcedValue,
    sourced,
    from_yahoo,
    from_compustat,
    from_damodaran,
    from_user,
    computed,
    missing,
)
from valuation.validation.data_sources import (
    sources_table,
    format_sources_markdown,
    count_by_source,
    missing_fields,
    proxy_fields,
)


# ---------------------------------------------------------------------------
# SourcedValue creation
# ---------------------------------------------------------------------------

class TestSourcedValueCreation:
    def test_basic_creation(self):
        sv = SourcedValue(value=42.0, source="compustat", confidence=0.95)
        assert sv.value == 42.0
        assert sv.source == "compustat"
        assert sv.confidence == 0.95
        assert sv.note == ""

    def test_creation_with_note(self):
        sv = SourcedValue(value=0.12, source="yahoo_finance", confidence=0.9, note="beta from yahoo")
        assert sv.note == "beta from yahoo"

    def test_missing_value_creation(self):
        sv = SourcedValue(value=None, source="missing", confidence=0.0)
        assert sv.value is None
        assert sv.source == "missing"

    def test_all_source_types(self):
        sources = [
            "compustat",
            "yahoo_finance",
            "damodaran_industry",
            "user_input",
            "assumed_default",
            "computed",
            "missing",
        ]
        for src in sources:
            sv = SourcedValue(value=1.0, source=src, confidence=0.5)
            assert sv.source == src


# ---------------------------------------------------------------------------
# is_available property
# ---------------------------------------------------------------------------

class TestIsAvailable:
    def test_available_for_real_data(self):
        sv = SourcedValue(value=10.5, source="compustat", confidence=0.95)
        assert sv.is_available is True

    def test_not_available_for_none_value(self):
        sv = SourcedValue(value=None, source="missing", confidence=0.0)
        assert sv.is_available is False

    def test_not_available_for_missing_source(self):
        # Even if value is set, source="missing" means not available
        sv = SourcedValue(value=5.0, source="missing", confidence=0.0)
        assert sv.is_available is False

    def test_available_for_all_non_missing_sources(self):
        non_missing_sources = [
            "compustat", "yahoo_finance", "damodaran_industry",
            "user_input", "assumed_default", "computed",
        ]
        for src in non_missing_sources:
            sv = SourcedValue(value=1.0, source=src, confidence=0.5)
            assert sv.is_available is True, f"Expected is_available=True for source={src}"


# ---------------------------------------------------------------------------
# is_proxy property
# ---------------------------------------------------------------------------

class TestIsProxy:
    def test_proxy_for_damodaran_industry(self):
        sv = SourcedValue(value=0.5, source="damodaran_industry", confidence=0.5)
        assert sv.is_proxy is True

    def test_proxy_for_assumed_default(self):
        sv = SourcedValue(value=0.2, source="assumed_default", confidence=0.2)
        assert sv.is_proxy is True

    def test_not_proxy_for_compustat(self):
        sv = SourcedValue(value=100.0, source="compustat", confidence=0.95)
        assert sv.is_proxy is False

    def test_not_proxy_for_yahoo_finance(self):
        sv = SourcedValue(value=1.2, source="yahoo_finance", confidence=0.9)
        assert sv.is_proxy is False

    def test_not_proxy_for_user_input(self):
        sv = SourcedValue(value=0.08, source="user_input", confidence=1.0)
        assert sv.is_proxy is False

    def test_not_proxy_for_computed(self):
        sv = SourcedValue(value=0.15, source="computed", confidence=0.7)
        assert sv.is_proxy is False

    def test_not_proxy_for_missing(self):
        sv = SourcedValue(value=None, source="missing", confidence=0.0)
        assert sv.is_proxy is False


# ---------------------------------------------------------------------------
# float() conversion
# ---------------------------------------------------------------------------

class TestFloatConversion:
    def test_float_conversion_works_for_value(self):
        sv = SourcedValue(value=3.14, source="compustat", confidence=0.95)
        assert float(sv) == pytest.approx(3.14)

    def test_float_conversion_zero(self):
        sv = SourcedValue(value=0.0, source="computed", confidence=0.7)
        assert float(sv) == pytest.approx(0.0)

    def test_float_conversion_raises_for_none(self):
        sv = SourcedValue(value=None, source="missing", confidence=0.0, note="no data")
        with pytest.raises(ValueError, match="Cannot convert missing SourcedValue to float"):
            float(sv)

    def test_float_conversion_error_includes_note(self):
        sv = SourcedValue(value=None, source="missing", confidence=0.0, note="EBIT not found")
        with pytest.raises(ValueError, match="EBIT not found"):
            float(sv)


# ---------------------------------------------------------------------------
# __repr__
# ---------------------------------------------------------------------------

class TestRepr:
    def test_repr_with_value(self):
        sv = SourcedValue(value=42.0, source="compustat", confidence=0.95)
        r = repr(sv)
        assert "42.0" in r
        assert "compustat" in r
        assert "0.95" in r

    def test_repr_missing(self):
        sv = SourcedValue(value=None, source="missing", confidence=0.0)
        r = repr(sv)
        assert "MISSING" in r
        assert "missing" in r


# ---------------------------------------------------------------------------
# Convenience constructors
# ---------------------------------------------------------------------------

class TestConvenienceConstructors:
    def test_from_yahoo(self):
        sv = from_yahoo(1.5, note="beta")
        assert sv.value == 1.5
        assert sv.source == "yahoo_finance"
        assert sv.confidence == pytest.approx(0.9)
        assert sv.note == "beta"

    def test_from_yahoo_none(self):
        sv = from_yahoo(None)
        assert sv.value is None
        assert sv.source == "missing"
        assert sv.confidence == pytest.approx(0.0)

    def test_from_compustat(self):
        sv = from_compustat(500_000.0, note="revenue FY2024")
        assert sv.value == 500_000.0
        assert sv.source == "compustat"
        assert sv.confidence == pytest.approx(0.95)

    def test_from_compustat_none(self):
        sv = from_compustat(None)
        assert sv.source == "missing"

    def test_from_damodaran(self):
        sv = from_damodaran(0.25, note="industry beta")
        assert sv.value == 0.25
        assert sv.source == "damodaran_industry"
        assert sv.confidence == pytest.approx(0.5)

    def test_from_damodaran_none(self):
        sv = from_damodaran(None)
        assert sv.source == "missing"

    def test_from_user(self):
        sv = from_user(0.10, note="manual WACC override")
        assert sv.value == 0.10
        assert sv.source == "user_input"
        assert sv.confidence == pytest.approx(1.0)

    def test_computed(self):
        sv = computed(0.08, note="FCFF / Revenue")
        assert sv.value == 0.08
        assert sv.source == "computed"
        assert sv.confidence == pytest.approx(0.7)

    def test_computed_none(self):
        sv = computed(None)
        assert sv.source == "missing"

    def test_missing_constructor(self):
        sv = missing(note="data unavailable")
        assert sv.value is None
        assert sv.source == "missing"
        assert sv.confidence == pytest.approx(0.0)
        assert sv.note == "data unavailable"

    def test_sourced_generic(self):
        sv = sourced(99.9, "compustat", confidence=0.95, note="test")
        assert sv.value == 99.9
        assert sv.source == "compustat"
        assert sv.confidence == pytest.approx(0.95)

    def test_sourced_none_always_becomes_missing(self):
        sv = sourced(None, "compustat", confidence=0.95)
        assert sv.source == "missing"
        assert sv.confidence == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# sources_table
# ---------------------------------------------------------------------------

class TestSourcesTable:
    def _sample(self) -> dict:
        return {
            "revenue": from_compustat(1_000_000.0, note="FY2024"),
            "beta": from_yahoo(1.2),
            "wacc": computed(0.10),
            "terminal_growth": missing(note="not set"),
        }

    def test_row_count(self):
        rows = sources_table(self._sample())
        assert len(rows) == 4

    def test_row_keys(self):
        rows = sources_table(self._sample())
        for row in rows:
            assert set(row.keys()) == {"field", "value", "source", "confidence", "note"}

    def test_field_names_preserved(self):
        rows = sources_table(self._sample())
        fields = [r["field"] for r in rows]
        assert "revenue" in fields
        assert "terminal_growth" in fields

    def test_missing_value_in_table(self):
        rows = sources_table(self._sample())
        missing_row = next(r for r in rows if r["field"] == "terminal_growth")
        assert missing_row["value"] is None
        assert missing_row["source"] == "missing"

    def test_empty_dict(self):
        rows = sources_table({})
        assert rows == []


# ---------------------------------------------------------------------------
# format_sources_markdown
# ---------------------------------------------------------------------------

class TestFormatSourcesMarkdown:
    def _sample(self) -> dict:
        return {
            "ebit": from_compustat(200_000.0),
            "beta": from_yahoo(None),
        }

    def test_returns_string(self):
        md = format_sources_markdown(self._sample())
        assert isinstance(md, str)

    def test_has_header_row(self):
        md = format_sources_markdown(self._sample())
        assert "| Field |" in md
        assert "| Value |" in md
        assert "| Source |" in md
        assert "| Confidence |" in md
        assert "| Note |" in md

    def test_has_separator_row(self):
        md = format_sources_markdown(self._sample())
        assert "|-------|" in md

    def test_missing_shows_MISSING(self):
        md = format_sources_markdown(self._sample())
        assert "MISSING" in md

    def test_value_formatted_to_4dp(self):
        md = format_sources_markdown({"ebit": from_compustat(200_000.0)})
        assert "200000.0000" in md

    def test_confidence_as_percentage(self):
        md = format_sources_markdown({"ebit": from_compustat(1.0)})
        assert "95%" in md

    def test_row_count_matches(self):
        sample = self._sample()
        md = format_sources_markdown(sample)
        # header + separator + one row per entry
        lines = md.strip().split("\n")
        assert len(lines) == 2 + len(sample)

    def test_empty_dict(self):
        md = format_sources_markdown({})
        lines = md.strip().split("\n")
        assert len(lines) == 2  # just header and separator


# ---------------------------------------------------------------------------
# missing_fields and proxy_fields
# ---------------------------------------------------------------------------

class TestMissingAndProxyFields:
    def _sample(self) -> dict:
        return {
            "revenue": from_compustat(1_000_000.0),
            "beta": from_yahoo(None),              # missing
            "ebit_margin": from_damodaran(0.15),   # proxy
            "capex": missing(note="no data"),      # missing
            "wacc": from_user(0.10),
            "terminal_growth": computed(None),     # missing
            "reinvestment_rate": sourced(0.3, "assumed_default", 0.2),  # proxy
        }

    def test_missing_fields_returns_correct_names(self):
        mf = missing_fields(self._sample())
        assert "beta" in mf
        assert "capex" in mf
        assert "terminal_growth" in mf

    def test_missing_fields_excludes_available(self):
        mf = missing_fields(self._sample())
        assert "revenue" not in mf
        assert "wacc" not in mf

    def test_proxy_fields_returns_correct_names(self):
        pf = proxy_fields(self._sample())
        assert "ebit_margin" in pf
        assert "reinvestment_rate" in pf

    def test_proxy_fields_excludes_non_proxy(self):
        pf = proxy_fields(self._sample())
        assert "revenue" not in pf
        assert "wacc" not in pf

    def test_empty_dict(self):
        assert missing_fields({}) == []
        assert proxy_fields({}) == []


# ---------------------------------------------------------------------------
# count_by_source
# ---------------------------------------------------------------------------

class TestCountBySource:
    def test_counts_correctly(self):
        data = {
            "a": from_compustat(1.0),
            "b": from_compustat(2.0),
            "c": from_yahoo(3.0),
            "d": missing(),
        }
        counts = count_by_source(data)
        assert counts["compustat"] == 2
        assert counts["yahoo_finance"] == 1
        assert counts["missing"] == 1

    def test_empty_dict(self):
        assert count_by_source({}) == {}

    def test_all_same_source(self):
        data = {f"field_{i}": from_user(float(i)) for i in range(5)}
        counts = count_by_source(data)
        assert counts["user_input"] == 5
        assert len(counts) == 1

    def test_total_count_matches_inputs(self):
        sample = {
            "x": from_compustat(1.0),
            "y": from_damodaran(0.5),
            "z": missing(),
        }
        counts = count_by_source(sample)
        assert sum(counts.values()) == len(sample)
