"""Shared severity vocabulary and summary rendering for diagnostic commands.

Severity-based findings share this spine for consistent color rendering.
`series audit` uses the full spine (SEVERITY_STYLE + severity_summary).
`integrity check` adopts only SEVERITY_STYLE; it uses its own IssueSeverity
enum whose WARNING member has value "warning" (not "warn"), so SEVERITY_STYLE
maps both "warn" and "warning" to yellow so integrity can look up colors
directly without inline normalization.

The status-based render-drift family (core/drift.py: current/stale/missing/
orphan) is a different axis and is intentionally NOT unified here.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import TypeVar

# Severity vocabulary (error > warn > info).
ERROR = "error"
WARN = "warn"
INFO = "info"

SEVERITY_STYLE: dict[str, str] = {
    "error": "red",
    "warn": "yellow",
    "warning": "yellow",  # alias for integrity's IssueSeverity.WARNING value
    "info": "blue",
}

_T = TypeVar("_T")


def severity_counts(
    findings: Iterable[_T],
    *,
    severity_of: Callable[[_T], str] = lambda f: f.severity,  # type: ignore[attr-defined]
) -> dict[str, int]:
    """Count findings by severity. severity_of extracts the severity string."""
    counts: dict[str, int] = {"error": 0, "warn": 0, "info": 0}
    for f in findings:
        s = severity_of(f)
        counts[s] = counts.get(s, 0) + 1
    return counts


def severity_summary(
    findings: Iterable[_T],
    *,
    severity_of: Callable[[_T], str] = lambda f: f.severity,  # type: ignore[attr-defined]
) -> str:
    """Build a 'N errors · M warnings · K info' Rich-markup summary line.

    Returns an empty string if there are no findings. The separator is a
    middle dot (U+00B7). Only nonzero categories appear.
    """
    counts = severity_counts(findings, severity_of=severity_of)
    parts: list[str] = []
    if counts["error"]:
        parts.append(f"[red]{counts['error']} error{'s' if counts['error'] != 1 else ''}[/red]")
    if counts["warn"]:
        parts.append(
            f"[yellow]{counts['warn']} warning{'s' if counts['warn'] != 1 else ''}[/yellow]"
        )
    if counts["info"]:
        parts.append(f"[blue]{counts['info']} info[/blue]")
    return " · ".join(parts)
