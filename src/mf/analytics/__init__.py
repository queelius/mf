"""
Analytics module for content insights and statistics.

Provides aggregated analytics across content, projects, and papers.
"""

from mf.analytics.aggregator import (
    ContentAnalytics,
    ContentGap,
    CrossReferenceSuggestion,
    ProjectLinkStats,
    TagStats,
    TimelineEntry,
)

__all__ = [
    "ContentAnalytics",
    "ProjectLinkStats",
    "ContentGap",
    "TagStats",
    "TimelineEntry",
    "CrossReferenceSuggestion",
]
