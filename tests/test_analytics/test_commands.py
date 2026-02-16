"""Tests for mf.analytics.commands CLI module."""

import json

import pytest
from click.testing import CliRunner
from unittest.mock import patch

from mf.analytics.commands import (
    analytics,
    analytics_gaps,
    analytics_projects,
    analytics_suggestions,
    analytics_summary,
    analytics_tags,
    analytics_timeline,
)
from mf.analytics.aggregator import (
    ContentGap,
    CrossReferenceSuggestion,
    ProjectLinkStats,
    TagStats,
    TimelineEntry,
)


@pytest.fixture
def runner():
    """Create a Click CLI test runner."""
    return CliRunner()


# ---------------------------------------------------------------------------
# analytics group tests
# ---------------------------------------------------------------------------


def test_analytics_group_help(runner):
    """Test that analytics group shows help."""
    result = runner.invoke(analytics, ["--help"])
    assert result.exit_code == 0
    assert "Content analytics" in result.output


# ---------------------------------------------------------------------------
# analytics projects tests
# ---------------------------------------------------------------------------


def test_analytics_projects_json(runner):
    """Test analytics projects --json outputs valid JSON."""
    mock_stats = [
        ProjectLinkStats(
            slug="proj-a",
            title="Project A",
            linked_content_count=3,
            linked_posts=["/post/p1/", "/post/p2/"],
            linked_papers=["/papers/a/"],
        ),
    ]

    with patch("mf.analytics.ContentAnalytics") as MockAnalytics:
        instance = MockAnalytics.return_value
        instance.get_project_link_stats.return_value = mock_stats

        result = runner.invoke(analytics_projects, ["--json"])

    assert result.exit_code == 0
    data = json.loads(result.output)
    assert len(data) == 1
    assert data[0]["slug"] == "proj-a"
    assert data[0]["linked_content_count"] == 3


def test_analytics_projects_table(runner):
    """Test analytics projects renders a table."""
    mock_stats = [
        ProjectLinkStats(
            slug="proj-a",
            title="Project A",
            linked_content_count=2,
            linked_posts=["/post/p1/"],
            linked_papers=["/papers/a/"],
        ),
    ]

    with patch("mf.analytics.ContentAnalytics") as MockAnalytics:
        instance = MockAnalytics.return_value
        instance.get_project_link_stats.return_value = mock_stats

        result = runner.invoke(analytics_projects, [])

    assert result.exit_code == 0
    assert "proj-a" in result.output


def test_analytics_projects_with_limit(runner):
    """Test analytics projects --limit limits output."""
    mock_stats = [
        ProjectLinkStats(slug=f"proj-{i}", title=f"Project {i}", linked_content_count=i)
        for i in range(5)
    ]

    with patch("mf.analytics.ContentAnalytics") as MockAnalytics:
        instance = MockAnalytics.return_value
        instance.get_project_link_stats.return_value = mock_stats

        result = runner.invoke(analytics_projects, ["--json", "--limit", "2"])

    assert result.exit_code == 0
    data = json.loads(result.output)
    assert len(data) == 2


# ---------------------------------------------------------------------------
# analytics gaps tests
# ---------------------------------------------------------------------------


def test_analytics_gaps_json(runner):
    """Test analytics gaps --json outputs valid JSON."""
    mock_gaps = [
        ContentGap(slug="orphan", title="Orphan Project", is_hidden=False),
    ]

    with patch("mf.analytics.ContentAnalytics") as MockAnalytics:
        instance = MockAnalytics.return_value
        instance.get_content_gaps.return_value = mock_gaps

        result = runner.invoke(analytics_gaps, ["--json"])

    assert result.exit_code == 0
    data = json.loads(result.output)
    assert len(data) == 1
    assert data[0]["slug"] == "orphan"


def test_analytics_gaps_no_gaps(runner):
    """Test analytics gaps when no gaps exist."""
    with patch("mf.analytics.ContentAnalytics") as MockAnalytics:
        instance = MockAnalytics.return_value
        instance.get_content_gaps.return_value = []

        result = runner.invoke(analytics_gaps, [])

    assert result.exit_code == 0
    assert "No content gaps found" in result.output


# ---------------------------------------------------------------------------
# analytics tags tests
# ---------------------------------------------------------------------------


def test_analytics_tags_json(runner):
    """Test analytics tags --json outputs valid JSON."""
    mock_tags = [
        TagStats(tag="python", count=10, content_types={"post": 5, "papers": 3}),
        TagStats(tag="math", count=5, content_types={"papers": 5}),
    ]

    with patch("mf.analytics.ContentAnalytics") as MockAnalytics:
        instance = MockAnalytics.return_value
        instance.get_tag_distribution.return_value = mock_tags

        result = runner.invoke(analytics_tags, ["--json"])

    assert result.exit_code == 0
    data = json.loads(result.output)
    assert len(data) == 2
    assert data[0]["tag"] == "python"


# ---------------------------------------------------------------------------
# analytics timeline tests
# ---------------------------------------------------------------------------


def test_analytics_timeline_json(runner):
    """Test analytics timeline --json outputs valid JSON."""
    mock_timeline = [
        TimelineEntry(month="2024-05", posts=3, papers=1),
        TimelineEntry(month="2024-06", posts=5, papers=2),
    ]

    with patch("mf.analytics.ContentAnalytics") as MockAnalytics:
        instance = MockAnalytics.return_value
        instance.get_activity_timeline.return_value = mock_timeline

        result = runner.invoke(analytics_timeline, ["--json"])

    assert result.exit_code == 0
    data = json.loads(result.output)
    assert len(data) == 2
    assert data[1]["month"] == "2024-06"
    assert data[1]["total"] == 7


def test_analytics_timeline_no_data(runner):
    """Test analytics timeline with no data."""
    with patch("mf.analytics.ContentAnalytics") as MockAnalytics:
        instance = MockAnalytics.return_value
        instance.get_activity_timeline.return_value = []

        result = runner.invoke(analytics_timeline, [])

    assert result.exit_code == 0
    assert "No timeline data" in result.output


# ---------------------------------------------------------------------------
# analytics summary tests
# ---------------------------------------------------------------------------


def test_analytics_summary_json(runner):
    """Test analytics summary --json outputs valid JSON."""
    mock_summary = {
        "content": {"total": 50, "published": 45, "drafts": 5, "by_type": {"post": 30}},
        "projects": {"total": 10, "with_content": 7, "without_content": 3, "hidden": 1},
        "top_linked_projects": [],
        "content_gaps": [],
        "top_tags": [],
        "recent_activity": [],
    }

    with patch("mf.analytics.ContentAnalytics") as MockAnalytics:
        instance = MockAnalytics.return_value
        instance.get_summary.return_value = mock_summary

        result = runner.invoke(analytics_summary, ["--json"])

    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["content"]["total"] == 50


def test_analytics_summary_table(runner):
    """Test analytics summary renders text output."""
    mock_summary = {
        "content": {"total": 50, "published": 45, "drafts": 5, "by_type": {"post": 30}},
        "projects": {"total": 10, "with_content": 7, "without_content": 3, "hidden": 1},
        "top_linked_projects": [{"slug": "top-proj", "linked_content_count": 5}],
        "content_gaps": [{"slug": "gap-proj"}],
        "top_tags": [{"tag": "python", "count": 10}],
        "recent_activity": [{"month": "2024-06", "total": 8}],
    }

    with patch("mf.analytics.ContentAnalytics") as MockAnalytics:
        instance = MockAnalytics.return_value
        instance.get_summary.return_value = mock_summary

        result = runner.invoke(analytics_summary, [])

    assert result.exit_code == 0
    assert "Content Overview" in result.output
    assert "Project Overview" in result.output
