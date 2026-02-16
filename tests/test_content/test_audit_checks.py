"""Tests for mf.content.audit_checks module."""

import pytest
from datetime import datetime, timedelta
from pathlib import Path

from mf.content.audit_checks import (
    AuditCheck,
    CheckContext,
    CheckIssue,
    RequiredFieldsCheck,
    DateFormatCheck,
    OrphanedContentCheck,
    StaleDraftsCheck,
    RelatedContentCheck,
    InternalLinksCheck,
    AVAILABLE_CHECKS,
    get_check,
    get_all_checks,
    list_checks,
)
from mf.content.scanner import ContentItem


@pytest.fixture
def sample_context(tmp_path):
    """Create a sample CheckContext for testing."""
    return CheckContext(
        site_root=tmp_path,
        all_project_slugs={"project-a", "project-b", "hidden-project"},
        hidden_project_slugs={"hidden-project"},
        all_paper_slugs={"paper-1", "paper-2"},
        all_post_slugs={"post-1", "post-2"},
        all_content_paths={
            "/post/post-1/",
            "/post/post-2/",
            "/papers/paper-1/",
            "/papers/paper-2/",
            "/projects/project-a/",
            "/projects/project-b/",
        },
    )


@pytest.fixture
def sample_content_item(tmp_path):
    """Factory for creating sample ContentItem objects."""
    def _create(
        slug: str = "test-item",
        content_type: str = "post",
        front_matter: dict | None = None,
        body: str = "",
    ) -> ContentItem:
        path = tmp_path / "content" / content_type / slug / "index.md"
        path.parent.mkdir(parents=True, exist_ok=True)

        default_fm = {
            "title": f"Test {slug}",
            "date": "2024-06-15",
            "tags": ["test"],
            "categories": ["testing"],
        }
        if front_matter:
            default_fm.update(front_matter)

        return ContentItem(
            path=path,
            slug=slug,
            content_type=content_type,
            front_matter=default_fm,
            body=body,
        )

    return _create


class TestCheckIssue:
    """Tests for CheckIssue dataclass."""

    def test_to_dict(self):
        """Test CheckIssue.to_dict() serialization."""
        issue = CheckIssue(
            check_name="test_check",
            message="Test message",
            severity="error",
            field="title",
            extra={"key": "value"},
        )

        d = issue.to_dict()

        assert d["check"] == "test_check"
        assert d["message"] == "Test message"
        assert d["severity"] == "error"
        assert d["field"] == "title"
        assert d["extra"] == {"key": "value"}

    def test_to_dict_minimal(self):
        """Test to_dict with minimal fields."""
        issue = CheckIssue(
            check_name="test_check",
            message="Test message",
            severity="warning",
        )

        d = issue.to_dict()

        assert d["check"] == "test_check"
        assert "field" not in d
        assert "extra" not in d


class TestRequiredFieldsCheck:
    """Tests for RequiredFieldsCheck."""

    def test_check_valid_content(self, sample_context, sample_content_item):
        """Test check passes for valid content."""
        item = sample_content_item(front_matter={"title": "Valid", "date": "2024-01-01"})
        check = RequiredFieldsCheck()

        issues = check.check(item, sample_context)

        assert len(issues) == 0

    def test_check_missing_title(self, sample_context, sample_content_item):
        """Test check detects missing title."""
        item = sample_content_item(front_matter={"date": "2024-01-01"})
        del item.front_matter["title"]
        check = RequiredFieldsCheck()

        issues = check.check(item, sample_context)

        assert len(issues) == 1
        assert issues[0].field == "title"
        assert issues[0].severity == "error"

    def test_check_missing_date(self, sample_context, sample_content_item):
        """Test check detects missing date."""
        item = sample_content_item(front_matter={"title": "Test"})
        del item.front_matter["date"]
        check = RequiredFieldsCheck()

        issues = check.check(item, sample_context)

        assert len(issues) == 1
        assert issues[0].field == "date"

    def test_check_projects_dont_need_date(self, sample_context, sample_content_item):
        """Test that projects content type doesn't require date."""
        item = sample_content_item(content_type="projects", front_matter={"title": "Project"})
        del item.front_matter["date"]
        check = RequiredFieldsCheck()

        issues = check.check(item, sample_context)

        assert len(issues) == 0


class TestDateFormatCheck:
    """Tests for DateFormatCheck."""

    def test_check_valid_date_string(self, sample_context, sample_content_item):
        """Test check passes for valid date string."""
        item = sample_content_item(front_matter={"date": "2024-06-15"})
        check = DateFormatCheck()

        issues = check.check(item, sample_context)

        assert len(issues) == 0

    def test_check_valid_datetime_string(self, sample_context, sample_content_item):
        """Test check passes for valid datetime string."""
        item = sample_content_item(front_matter={"date": "2024-06-15T10:30:00"})
        check = DateFormatCheck()

        issues = check.check(item, sample_context)

        assert len(issues) == 0

    def test_check_valid_datetime_object(self, sample_context, sample_content_item):
        """Test check passes for datetime object."""
        item = sample_content_item(front_matter={"date": datetime(2024, 6, 15)})
        check = DateFormatCheck()

        issues = check.check(item, sample_context)

        assert len(issues) == 0

    def test_check_invalid_date_format(self, sample_context, sample_content_item):
        """Test check detects invalid date format."""
        item = sample_content_item(front_matter={"date": "15/06/2024"})
        check = DateFormatCheck()

        issues = check.check(item, sample_context)

        assert len(issues) == 1
        assert issues[0].check_name == "date_format"
        assert issues[0].severity == "warning"

    def test_check_missing_date_ignored(self, sample_context, sample_content_item):
        """Test that missing date is ignored (handled by RequiredFieldsCheck)."""
        item = sample_content_item(front_matter={})
        del item.front_matter["date"]
        check = DateFormatCheck()

        issues = check.check(item, sample_context)

        assert len(issues) == 0


class TestOrphanedContentCheck:
    """Tests for OrphanedContentCheck."""

    def test_check_content_with_tags(self, sample_context, sample_content_item):
        """Test check passes for content with tags."""
        item = sample_content_item(front_matter={"tags": ["tag1"]})
        check = OrphanedContentCheck()

        issues = check.check(item, sample_context)

        assert len(issues) == 0

    def test_check_content_with_categories(self, sample_context, sample_content_item):
        """Test check passes for content with categories."""
        item = sample_content_item(front_matter={"tags": [], "categories": ["cat1"]})
        check = OrphanedContentCheck()

        issues = check.check(item, sample_context)

        assert len(issues) == 0

    def test_check_orphaned_content(self, sample_context, sample_content_item):
        """Test check detects orphaned content."""
        item = sample_content_item(front_matter={"tags": [], "categories": []})
        check = OrphanedContentCheck()

        issues = check.check(item, sample_context)

        assert len(issues) == 1
        assert issues[0].check_name == "orphaned_content"
        assert issues[0].severity == "info"

    def test_check_projects_skipped(self, sample_context, sample_content_item):
        """Test that projects are skipped."""
        item = sample_content_item(content_type="projects", front_matter={"tags": [], "categories": []})
        check = OrphanedContentCheck()

        issues = check.check(item, sample_context)

        assert len(issues) == 0


class TestStaleDraftsCheck:
    """Tests for StaleDraftsCheck."""

    def test_check_published_content(self, sample_context, sample_content_item):
        """Test check ignores published content."""
        item = sample_content_item(front_matter={"draft": False})
        check = StaleDraftsCheck()

        issues = check.check(item, sample_context)

        assert len(issues) == 0

    def test_check_recent_draft(self, sample_context, sample_content_item):
        """Test check passes for recent draft."""
        recent_date = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
        item = sample_content_item(front_matter={"draft": True, "date": recent_date})
        check = StaleDraftsCheck()

        issues = check.check(item, sample_context)

        assert len(issues) == 0

    def test_check_stale_draft(self, sample_context, sample_content_item):
        """Test check detects stale draft."""
        old_date = (datetime.now() - timedelta(days=120)).strftime("%Y-%m-%d")
        item = sample_content_item(front_matter={"draft": True, "date": old_date})
        check = StaleDraftsCheck()

        issues = check.check(item, sample_context)

        assert len(issues) == 1
        assert issues[0].check_name == "stale_drafts"
        assert issues[0].severity == "info"
        assert issues[0].extra.get("days_old") > 90


class TestRelatedContentCheck:
    """Tests for RelatedContentCheck."""

    def test_check_valid_related_posts(self, sample_context, sample_content_item):
        """Test check passes for valid related_posts."""
        item = sample_content_item(front_matter={"related_posts": ["/post/post-1/"]})
        check = RelatedContentCheck()

        issues = check.check(item, sample_context)

        assert len(issues) == 0

    def test_check_invalid_related_posts(self, sample_context, sample_content_item):
        """Test check detects invalid related_posts."""
        item = sample_content_item(front_matter={"related_posts": ["/post/nonexistent/"]})
        check = RelatedContentCheck()

        issues = check.check(item, sample_context)

        assert len(issues) == 1
        assert issues[0].field == "related_posts"
        assert issues[0].severity == "error"

    def test_check_valid_related_projects(self, sample_context, sample_content_item):
        """Test check passes for valid related_projects."""
        item = sample_content_item(front_matter={"related_projects": ["/projects/project-a/"]})
        check = RelatedContentCheck()

        issues = check.check(item, sample_context)

        assert len(issues) == 0

    def test_check_valid_related_projects_slug(self, sample_context, sample_content_item):
        """Test check passes for valid related_projects slug."""
        item = sample_content_item(front_matter={"related_projects": ["project-b"]})
        check = RelatedContentCheck()

        issues = check.check(item, sample_context)

        assert len(issues) == 0

    def test_check_invalid_related_projects(self, sample_context, sample_content_item):
        """Test check detects invalid related_projects."""
        item = sample_content_item(front_matter={"related_projects": ["nonexistent"]})
        check = RelatedContentCheck()

        issues = check.check(item, sample_context)

        assert len(issues) == 1
        assert issues[0].field == "related_projects"


class TestInternalLinksCheck:
    """Tests for InternalLinksCheck."""

    def test_check_valid_internal_link(self, sample_context, sample_content_item):
        """Test check passes for valid internal link."""
        item = sample_content_item(body="Check out [this post](/post/post-1/).")
        check = InternalLinksCheck()

        issues = check.check(item, sample_context)

        assert len(issues) == 0

    def test_check_broken_internal_link(self, sample_context, sample_content_item):
        """Test check detects broken internal link."""
        item = sample_content_item(body="Check out [this post](/post/nonexistent/).")
        check = InternalLinksCheck()

        issues = check.check(item, sample_context)

        assert len(issues) == 1
        assert issues[0].check_name == "internal_links"
        assert issues[0].severity == "warning"

    def test_check_static_links_allowed(self, sample_context, sample_content_item):
        """Test that static file links are allowed."""
        item = sample_content_item(body="See [image](/images/photo.png).")
        check = InternalLinksCheck()

        issues = check.check(item, sample_context)

        assert len(issues) == 0

    def test_check_external_links_ignored(self, sample_context, sample_content_item):
        """Test that external links are ignored."""
        item = sample_content_item(body="Visit [Google](https://google.com).")
        check = InternalLinksCheck()

        issues = check.check(item, sample_context)

        assert len(issues) == 0


class TestCheckRegistry:
    """Tests for the check registry functions."""

    def test_available_checks(self):
        """Test that all expected checks are registered."""
        expected = {
            "required_fields",
            "date_format",
            "orphaned_content",
            "stale_drafts",
            "related_content",
            "internal_links",
        }
        assert set(AVAILABLE_CHECKS.keys()) == expected

    def test_get_check_valid(self):
        """Test get_check returns check instance."""
        check = get_check("required_fields")
        assert check is not None
        assert isinstance(check, RequiredFieldsCheck)

    def test_get_check_invalid(self):
        """Test get_check returns None for unknown check."""
        check = get_check("nonexistent")
        assert check is None

    def test_get_all_checks(self):
        """Test get_all_checks returns all instances."""
        checks = get_all_checks()
        assert len(checks) == len(AVAILABLE_CHECKS)
        assert all(isinstance(c, AuditCheck) for c in checks)

    def test_list_checks(self):
        """Test list_checks returns metadata."""
        checks = list_checks()
        assert len(checks) == len(AVAILABLE_CHECKS)
        for check in checks:
            assert "name" in check
            assert "description" in check
            assert "severity" in check
