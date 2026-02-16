"""Tests for health checks."""

from __future__ import annotations

import json

import pytest
import yaml

from mf.health.checks import HealthChecker


class TestBrokenLinks:
    """Test broken internal link detection."""

    def test_detects_broken_internal_link(self, create_content_file):
        create_content_file(
            slug="post-a",
            body="See [other post](/post/nonexistent/) for details.",
        )
        checker = HealthChecker()
        issues = checker.check_links()
        assert len(issues) >= 1
        assert any("/post/nonexistent/" in i["link"] for i in issues)

    def test_valid_link_no_issue(self, create_content_file):
        create_content_file(slug="post-a", body="Normal text, no links.")
        create_content_file(slug="post-b", body="See [post A](/post/post-a/).")
        checker = HealthChecker()
        issues = checker.check_links()
        # post-b links to post-a which exists
        broken = [i for i in issues if i["slug"] == "post-b"]
        assert len(broken) == 0

    def test_ignores_external_links(self, create_content_file):
        create_content_file(
            slug="post-a",
            body="See [Google](https://google.com) for info.",
        )
        checker = HealthChecker()
        issues = checker.check_links()
        assert len(issues) == 0

    def test_ignores_anchor_links(self, create_content_file):
        create_content_file(
            slug="post-a",
            body="See [section](#introduction) below.",
        )
        checker = HealthChecker()
        issues = checker.check_links()
        assert len(issues) == 0

    def test_ignores_static_links(self, create_content_file):
        create_content_file(
            slug="post-a",
            body="Download the [PDF](/latex/my-paper/paper.pdf).",
        )
        checker = HealthChecker()
        issues = checker.check_links()
        assert len(issues) == 0


class TestMissingDescriptions:
    """Test missing description detection."""

    def test_detects_missing_description(self, create_content_file):
        create_content_file(slug="post-a")  # No description
        checker = HealthChecker()
        issues = checker.check_descriptions()
        assert len(issues) >= 1
        assert any(i["slug"] == "post-a" for i in issues)

    def test_has_description_no_issue(self, create_content_file):
        create_content_file(
            slug="post-a",
            extra_fm={"description": "A good post about things."},
        )
        checker = HealthChecker()
        issues = checker.check_descriptions()
        assert not any(i["slug"] == "post-a" for i in issues)

    def test_empty_description_is_issue(self, create_content_file):
        create_content_file(slug="post-a", extra_fm={"description": ""})
        checker = HealthChecker()
        issues = checker.check_descriptions()
        assert any(i["slug"] == "post-a" for i in issues)

    def test_whitespace_only_description_is_issue(self, create_content_file):
        create_content_file(slug="post-a", extra_fm={"description": "   "})
        checker = HealthChecker()
        issues = checker.check_descriptions()
        assert any(i["slug"] == "post-a" for i in issues)


class TestMissingImages:
    """Test missing featured_image detection."""

    def test_detects_missing_image(self, create_content_file):
        create_content_file(slug="post-a")  # No featured_image
        checker = HealthChecker()
        issues = checker.check_images()
        assert any(i["slug"] == "post-a" for i in issues)

    def test_has_image_no_issue(self, create_content_file):
        create_content_file(
            slug="post-a",
            extra_fm={"featured_image": "/images/hero.jpg"},
        )
        checker = HealthChecker()
        issues = checker.check_images()
        assert not any(i["slug"] == "post-a" for i in issues)


class TestDrafts:
    """Test draft listing with age."""

    def test_lists_drafts(self, create_content_file):
        create_content_file(slug="my-draft", draft=True)
        checker = HealthChecker()
        drafts = checker.check_drafts()
        assert len(drafts) >= 1
        assert any(d["slug"] == "my-draft" for d in drafts)

    def test_skips_non_drafts(self, create_content_file):
        create_content_file(slug="published", draft=False)
        checker = HealthChecker()
        drafts = checker.check_drafts()
        assert not any(d["slug"] == "published" for d in drafts)

    def test_draft_includes_age(self, create_content_file):
        create_content_file(slug="old-draft", draft=True)
        checker = HealthChecker()
        drafts = checker.check_drafts()
        draft = next(d for d in drafts if d["slug"] == "old-draft")
        assert "days_old" in draft

    def test_drafts_sorted_by_age(self, create_content_file):
        create_content_file(
            slug="newer-draft",
            draft=True,
            extra_fm={"date": "2025-01-01"},
        )
        create_content_file(
            slug="older-draft",
            draft=True,
            extra_fm={"date": "2020-01-01"},
        )
        checker = HealthChecker()
        drafts = checker.check_drafts()
        # Oldest first (sorted descending by days_old)
        slugs = [d["slug"] for d in drafts]
        assert slugs.index("older-draft") < slugs.index("newer-draft")


class TestStaleProjects:
    """Test stale project detection."""

    def test_detects_stale_project(self, mock_site_root):
        """Create a project page with different desc than DB."""
        # Set up projects_db with a description
        db_path = mock_site_root / ".mf" / "projects_db.json"
        db_data = {
            "my-proj": {
                "title": "My Project",
                "description": "New description from GitHub",
            }
        }
        db_path.write_text(json.dumps(db_data))

        # Create project content with old description
        proj_dir = mock_site_root / "content" / "projects" / "my-proj"
        proj_dir.mkdir(parents=True)
        fm = {
            "title": "My Project",
            "description": "Old description",
        }
        (proj_dir / "index.md").write_text(
            f"---\n{yaml.dump(fm)}---\n\nContent.\n"
        )

        checker = HealthChecker(site_root=mock_site_root)
        issues = checker.check_stale()
        assert len(issues) >= 1
        assert any(i["slug"] == "my-proj" for i in issues)

    def test_no_stale_when_descriptions_match(self, mock_site_root):
        """No issue when content and DB descriptions match."""
        db_path = mock_site_root / ".mf" / "projects_db.json"
        db_data = {
            "my-proj": {
                "title": "My Project",
                "description": "Same description",
            }
        }
        db_path.write_text(json.dumps(db_data))

        proj_dir = mock_site_root / "content" / "projects" / "my-proj"
        proj_dir.mkdir(parents=True)
        fm = {
            "title": "My Project",
            "description": "Same description",
        }
        (proj_dir / "index.md").write_text(
            f"---\n{yaml.dump(fm)}---\n\nContent.\n"
        )

        checker = HealthChecker(site_root=mock_site_root)
        issues = checker.check_stale()
        assert not any(i["slug"] == "my-proj" for i in issues)

    def test_no_db_returns_empty(self, mock_site_root):
        """No projects_db.json returns empty list."""
        checker = HealthChecker(site_root=mock_site_root)
        issues = checker.check_stale()
        assert issues == []
