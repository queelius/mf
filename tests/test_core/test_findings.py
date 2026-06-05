from dataclasses import dataclass

from mf.core.findings import (
    SEVERITY_STYLE,
    severity_counts,
    severity_summary,
)


@dataclass
class _F:
    severity: str


def test_severity_style_has_three_levels():
    assert SEVERITY_STYLE == {"error": "red", "warn": "yellow", "info": "blue"}


def test_severity_counts():
    findings = [_F("error"), _F("warn"), _F("warn"), _F("info")]
    assert severity_counts(findings) == {"error": 1, "warn": 2, "info": 1}


def test_severity_summary_pluralizes_and_skips_zero():
    findings = [_F("error"), _F("warn"), _F("warn")]
    out = severity_summary(findings)
    assert "1 error" in out
    assert "2 warnings" in out
    assert "info" not in out


def test_severity_summary_empty_is_empty_string():
    assert severity_summary([]) == ""


def test_severity_summary_custom_extractor():
    items = [{"sev": "error"}, {"sev": "info"}]
    out = severity_summary(items, severity_of=lambda d: d["sev"])
    assert "1 error" in out
    assert "1 info" in out
