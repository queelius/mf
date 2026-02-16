"""Tests for mf.analytics.aggregator module."""

import json
import pytest
from pathlib import Path

from mf.analytics.aggregator import (
    ContentAnalytics,
    ProjectLinkStats,
    ContentGap,
    TagStats,
    TimelineEntry,
    CrossReferenceSuggestion,
)


@pytest.fixture
def mock_analytics_site(tmp_path, monkeypatch):
    """Create a mock site structure for analytics testing."""
    # Create .mf/ directory structure
    mf_dir = tmp_path / ".mf"
    mf_dir.mkdir()
    (mf_dir / "cache").mkdir()
    (mf_dir / "backups" / "papers").mkdir(parents=True)
    (mf_dir / "backups" / "projects").mkdir(parents=True)

    # Create content directories
    (tmp_path / "content" / "post").mkdir(parents=True)
    (tmp_path / "content" / "papers").mkdir(parents=True)
    (tmp_path / "content" / "writing").mkdir(parents=True)
    (tmp_path / "content" / "projects").mkdir(parents=True)

    # Create projects database
    projects_db = {
        "_comment": "Test projects",
        "_schema_version": "2.0",
        "project-alpha": {
            "title": "Project Alpha",
            "tags": ["python", "testing"],
        },
        "project-beta": {
            "title": "Project Beta",
            "tags": ["rust"],
        },
        "hidden-project": {
            "title": "Hidden Project",
            "hide": True,
        },
    }
    (mf_dir / "projects_db.json").write_text(json.dumps(projects_db, indent=2))

    # Create projects cache
    projects_cache = {
        "cached-project": {
            "name": "Cached Project",
            "topics": ["testing"],
        },
    }
    (mf_dir / "cache" / "projects.json").write_text(json.dumps(projects_cache, indent=2))

    # Create paper database
    paper_db = {
        "_comment": "Test papers",
        "_schema_version": "2.0",
        "test-paper": {
            "title": "Test Paper",
            "tags": ["research"],
        },
    }
    (mf_dir / "paper_db.json").write_text(json.dumps(paper_db, indent=2))

    # Mock get_site_root
    from mf.core import config
    config.get_site_root.cache_clear()
    monkeypatch.setattr(config, "get_site_root", lambda: tmp_path)

    return tmp_path


@pytest.fixture
def create_content(mock_analytics_site):
    """Factory fixture to create test content files."""
    def _create(
        content_type: str,
        slug: str,
        linked_project: list | None = None,
        tags: list | None = None,
        date: str = "2024-06-15",
    ):
        content_dir = mock_analytics_site / "content" / content_type / slug
        content_dir.mkdir(parents=True, exist_ok=True)

        fm = {
            "title": f"Test {slug}",
            "date": date,
            "tags": tags or ["test"],
        }
        if linked_project is not None:
            fm["linked_project"] = linked_project

        content = "---\n"
        for key, value in fm.items():
            if isinstance(value, list):
                content += f"{key}:\n"
                for item in value:
                    content += f"  - {item}\n"
            else:
                content += f"{key}: {value}\n"
        content += "---\n\nTest content body.\n"

        (content_dir / "index.md").write_text(content)
        return content_dir / "index.md"

    return _create


class TestProjectLinkStats:
    """Tests for ProjectLinkStats dataclass."""

    def test_to_dict(self):
        """Test ProjectLinkStats.to_dict() serialization."""
        stats = ProjectLinkStats(
            slug="test-project",
            title="Test Project",
            linked_content_count=5,
            linked_posts=["/post/a/", "/post/b/"],
            linked_papers=["/papers/c/"],
            is_hidden=False,
        )

        d = stats.to_dict()

        assert d["slug"] == "test-project"
        assert d["linked_content_count"] == 5
        assert len(d["linked_posts"]) == 2
        assert not d["is_hidden"]


class TestContentGap:
    """Tests for ContentGap dataclass."""

    def test_to_dict(self):
        """Test ContentGap.to_dict() serialization."""
        gap = ContentGap(
            slug="orphan-project",
            title="Orphan Project",
            is_hidden=False,
            mentioned_in=["/post/mentions-it/"],
        )

        d = gap.to_dict()

        assert d["slug"] == "orphan-project"
        assert len(d["mentioned_in"]) == 1


class TestTagStats:
    """Tests for TagStats dataclass."""

    def test_to_dict(self):
        """Test TagStats.to_dict() serialization."""
        stats = TagStats(
            tag="python",
            count=10,
            content_types={"post": 5, "papers": 3, "projects": 2},
        )

        d = stats.to_dict()

        assert d["tag"] == "python"
        assert d["count"] == 10
        assert d["content_types"]["post"] == 5


class TestTimelineEntry:
    """Tests for TimelineEntry dataclass."""

    def test_total_property(self):
        """Test TimelineEntry.total property."""
        entry = TimelineEntry(
            month="2024-06",
            posts=5,
            papers=3,
            projects=2,
            other=1,
        )

        assert entry.total == 11

    def test_to_dict(self):
        """Test TimelineEntry.to_dict() serialization."""
        entry = TimelineEntry(month="2024-06", posts=5)

        d = entry.to_dict()

        assert d["month"] == "2024-06"
        assert d["posts"] == 5
        assert d["total"] == 5


class TestCrossReferenceSuggestion:
    """Tests for CrossReferenceSuggestion dataclass."""

    def test_to_dict(self, tmp_path):
        """Test CrossReferenceSuggestion.to_dict() serialization."""
        suggestion = CrossReferenceSuggestion(
            content_path=tmp_path / "content/post/test/index.md",
            content_title="Test Post",
            content_type="post",
            project_slug="project-a",
            project_title="Project A",
            confidence=0.85,
            reason="Contains GitHub URL",
        )

        d = suggestion.to_dict()

        assert d["content_title"] == "Test Post"
        assert d["project_slug"] == "project-a"
        assert d["confidence"] == 0.85


class TestContentAnalytics:
    """Tests for ContentAnalytics class."""

    def test_get_project_link_stats_no_content(self, mock_analytics_site):
        """Test get_project_link_stats with no content."""
        analytics = ContentAnalytics(mock_analytics_site)
        stats = analytics.get_project_link_stats()

        # Should return all non-hidden projects with 0 links
        assert len(stats) > 0
        assert all(s.linked_content_count == 0 for s in stats)

    def test_get_project_link_stats_with_content(self, mock_analytics_site, create_content):
        """Test get_project_link_stats with linked content."""
        create_content("post", "post-1", linked_project=["project-alpha"])
        create_content("post", "post-2", linked_project=["project-alpha"])
        create_content("papers", "paper-1", linked_project=["project-beta"])

        analytics = ContentAnalytics(mock_analytics_site)
        stats = analytics.get_project_link_stats()

        # Find project-alpha stats
        alpha_stats = next((s for s in stats if s.slug == "project-alpha"), None)
        assert alpha_stats is not None
        assert alpha_stats.linked_content_count == 2
        assert len(alpha_stats.linked_posts) == 2

        # Find project-beta stats
        beta_stats = next((s for s in stats if s.slug == "project-beta"), None)
        assert beta_stats is not None
        assert beta_stats.linked_content_count == 1
        assert len(beta_stats.linked_papers) == 1

    def test_get_project_link_stats_sorted(self, mock_analytics_site, create_content):
        """Test that stats are sorted by link count descending."""
        create_content("post", "post-1", linked_project=["project-alpha"])
        create_content("post", "post-2", linked_project=["project-alpha"])
        create_content("post", "post-3", linked_project=["project-beta"])

        analytics = ContentAnalytics(mock_analytics_site)
        stats = analytics.get_project_link_stats()

        # First should be project-alpha with 2 links
        assert stats[0].slug == "project-alpha"
        assert stats[0].linked_content_count == 2

    def test_get_content_gaps(self, mock_analytics_site, create_content):
        """Test get_content_gaps finds projects without content."""
        # Only link to project-alpha
        create_content("post", "post-1", linked_project=["project-alpha"])

        analytics = ContentAnalytics(mock_analytics_site)
        gaps = analytics.get_content_gaps()

        # Should include project-beta and cached-project
        slugs = [g.slug for g in gaps]
        assert "project-beta" in slugs

    def test_get_content_gaps_excludes_hidden(self, mock_analytics_site):
        """Test that hidden projects are excluded from gaps by default."""
        analytics = ContentAnalytics(mock_analytics_site)
        gaps = analytics.get_content_gaps(include_hidden=False)

        slugs = [g.slug for g in gaps]
        assert "hidden-project" not in slugs

    def test_get_tag_distribution(self, mock_analytics_site, create_content):
        """Test get_tag_distribution counts tags."""
        create_content("post", "post-1", tags=["python", "testing"])
        create_content("post", "post-2", tags=["python", "rust"])
        create_content("papers", "paper-1", tags=["research", "python"])

        analytics = ContentAnalytics(mock_analytics_site)
        tags = analytics.get_tag_distribution()

        # Python should be most common
        python_tag = next((t for t in tags if t.tag == "python"), None)
        assert python_tag is not None
        assert python_tag.count == 3

    def test_get_tag_distribution_with_limit(self, mock_analytics_site, create_content):
        """Test get_tag_distribution respects limit."""
        create_content("post", "post-1", tags=["a", "b", "c"])
        create_content("post", "post-2", tags=["d", "e", "f"])

        analytics = ContentAnalytics(mock_analytics_site)
        tags = analytics.get_tag_distribution(limit=3)

        assert len(tags) == 3

    def test_get_activity_timeline(self, mock_analytics_site, create_content):
        """Test get_activity_timeline groups by month."""
        create_content("post", "post-1", date="2024-06-15")
        create_content("post", "post-2", date="2024-06-20")
        create_content("post", "post-3", date="2024-05-10")
        create_content("papers", "paper-1", date="2024-06-25")

        analytics = ContentAnalytics(mock_analytics_site)
        timeline = analytics.get_activity_timeline()

        # Find June entry
        june = next((t for t in timeline if t.month == "2024-06"), None)
        assert june is not None
        assert june.posts == 2
        assert june.papers == 1

        # Find May entry
        may = next((t for t in timeline if t.month == "2024-05"), None)
        assert may is not None
        assert may.posts == 1

    def test_suggest_cross_references(self, mock_analytics_site, create_content, tmp_path):
        """Test suggest_cross_references finds mentions."""
        # Create a post that mentions project-beta but doesn't link to it
        content_dir = mock_analytics_site / "content" / "post" / "mentions-beta"
        content_dir.mkdir(parents=True, exist_ok=True)
        content = """---
title: Post About Beta
date: 2024-06-15
tags:
  - test
---

Check out github.com/queelius/project-beta for more info!
"""
        (content_dir / "index.md").write_text(content)

        analytics = ContentAnalytics(mock_analytics_site)
        suggestions = analytics.suggest_cross_references(confidence_threshold=0.5)

        # Should suggest linking mentions-beta to project-beta
        beta_suggestion = next(
            (s for s in suggestions if s.project_slug == "project-beta"),
            None
        )
        assert beta_suggestion is not None
        assert beta_suggestion.confidence >= 0.5

    def test_get_summary(self, mock_analytics_site, create_content):
        """Test get_summary returns comprehensive data."""
        create_content("post", "post-1", linked_project=["project-alpha"])

        analytics = ContentAnalytics(mock_analytics_site)
        summary = analytics.get_summary()

        assert "content" in summary
        assert "projects" in summary
        assert "top_linked_projects" in summary
        assert "content_gaps" in summary
        assert "top_tags" in summary
