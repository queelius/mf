"""Tests for mf.content.auditor module."""

import json
import pytest
from pathlib import Path

from mf.content.auditor import (
    ContentAuditor,
    AuditResult,
    AuditIssue,
    AuditStats,
    IssueType,
    IssueSeverity,
)


@pytest.fixture
def mock_audit_site(tmp_path, monkeypatch):
    """Create a mock site structure with content and project databases."""
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
        "valid-project": {
            "title": "Valid Project",
            "abstract": "A valid test project",
            "tags": ["python"],
        },
        "another-valid": {
            "title": "Another Valid Project",
            "tags": ["rust"],
        },
        "hidden-project": {
            "title": "Hidden Project",
            "hide": True,
        },
    }
    (mf_dir / "projects_db.json").write_text(json.dumps(projects_db, indent=2))

    # Create projects cache (simulates GitHub API data)
    projects_cache = {
        "cached-project": {
            "name": "Cached Project",
            "topics": ["testing"],
        },
    }
    (mf_dir / "cache" / "projects.json").write_text(json.dumps(projects_cache, indent=2))

    # Mock get_site_root
    from mf.core import config
    config.get_site_root.cache_clear()
    monkeypatch.setattr(config, "get_site_root", lambda: tmp_path)

    return tmp_path


@pytest.fixture
def create_content(mock_audit_site):
    """Factory fixture to create test content files."""
    def _create(content_type: str, slug: str, linked_project: list | None = None, draft: bool = False):
        content_dir = mock_audit_site / "content" / content_type / slug
        content_dir.mkdir(parents=True, exist_ok=True)

        fm = {
            "title": f"Test {slug}",
            "date": "2024-01-01",
            "draft": draft,
        }
        if linked_project is not None:
            fm["linked_project"] = linked_project

        content = f"---\n"
        for key, value in fm.items():
            if isinstance(value, list):
                content += f"{key}:\n"
                for item in value:
                    content += f"  - {item}\n"
            elif isinstance(value, bool):
                content += f"{key}: {'true' if value else 'false'}\n"
            else:
                content += f"{key}: {value}\n"
        content += "---\n\nTest content body.\n"

        (content_dir / "index.md").write_text(content)
        return content_dir / "index.md"

    return _create


class TestAuditIssue:
    """Tests for AuditIssue dataclass."""

    def test_to_dict(self, tmp_path):
        """Test AuditIssue.to_dict() serialization."""
        issue = AuditIssue(
            path=tmp_path / "test.md",
            title="Test Post",
            project_slug="missing-project",
            issue_type=IssueType.MISSING_PROJECT,
            message="Project not found",
            severity=IssueSeverity.ERROR,
        )

        d = issue.to_dict()

        assert d["title"] == "Test Post"
        assert d["project_slug"] == "missing-project"
        assert d["issue_type"] == "missing_project"
        assert d["severity"] == "error"
        assert "test.md" in d["path"]


class TestAuditStats:
    """Tests for AuditStats dataclass."""

    def test_default_values(self):
        """Test AuditStats has correct default values."""
        stats = AuditStats()

        assert stats.content_audited == 0
        assert stats.with_project_links == 0
        assert stats.valid_links == 0
        assert stats.broken_links == 0

    def test_to_dict(self):
        """Test AuditStats.to_dict() serialization."""
        stats = AuditStats(content_audited=10, valid_links=5, broken_links=2)

        d = stats.to_dict()

        assert d["content_audited"] == 10
        assert d["valid_links"] == 5
        assert d["broken_links"] == 2


class TestAuditResult:
    """Tests for AuditResult dataclass."""

    def test_has_errors(self, tmp_path):
        """Test has_errors property."""
        result = AuditResult()
        assert not result.has_errors

        result.issues.append(
            AuditIssue(
                path=tmp_path / "test.md",
                title="Test",
                project_slug="missing",
                issue_type=IssueType.MISSING_PROJECT,
                message="Not found",
                severity=IssueSeverity.ERROR,
            )
        )
        assert result.has_errors

    def test_has_warnings(self, tmp_path):
        """Test has_warnings property."""
        result = AuditResult()
        assert not result.has_warnings

        result.issues.append(
            AuditIssue(
                path=tmp_path / "test.md",
                title="Test",
                project_slug="hidden",
                issue_type=IssueType.HIDDEN_PROJECT,
                message="Hidden",
                severity=IssueSeverity.WARNING,
            )
        )
        assert result.has_warnings

    def test_errors_and_warnings_methods(self, tmp_path):
        """Test errors() and warnings() filtering methods."""
        result = AuditResult()

        error_issue = AuditIssue(
            path=tmp_path / "test.md",
            title="Test",
            project_slug="missing",
            issue_type=IssueType.MISSING_PROJECT,
            message="Not found",
            severity=IssueSeverity.ERROR,
        )
        warning_issue = AuditIssue(
            path=tmp_path / "test2.md",
            title="Test2",
            project_slug="hidden",
            issue_type=IssueType.HIDDEN_PROJECT,
            message="Hidden",
            severity=IssueSeverity.WARNING,
        )

        result.issues.extend([error_issue, warning_issue])

        assert len(result.errors()) == 1
        assert result.errors()[0].project_slug == "missing"

        assert len(result.warnings()) == 1
        assert result.warnings()[0].project_slug == "hidden"

    def test_to_json(self, tmp_path):
        """Test JSON serialization."""
        result = AuditResult()
        result.stats.content_audited = 5

        json_str = result.to_json()
        data = json.loads(json_str)

        assert data["stats"]["content_audited"] == 5
        assert data["issues"] == []


class TestContentAuditor:
    """Tests for ContentAuditor class."""

    def test_audit_no_content(self, mock_audit_site):
        """Test auditing with no content files."""
        auditor = ContentAuditor(mock_audit_site)
        result = auditor.audit()

        assert result.stats.content_audited == 0
        assert len(result.issues) == 0

    def test_audit_valid_links(self, mock_audit_site, create_content):
        """Test auditing content with valid project links."""
        create_content("post", "post-1", linked_project=["valid-project"])
        create_content("post", "post-2", linked_project=["another-valid"])
        create_content("post", "post-3", linked_project=["cached-project"])

        auditor = ContentAuditor(mock_audit_site)
        result = auditor.audit()

        assert result.stats.content_audited == 3
        assert result.stats.with_project_links == 3
        assert result.stats.valid_links == 3
        assert result.stats.broken_links == 0
        assert len(result.issues) == 0

    def test_audit_missing_project(self, mock_audit_site, create_content):
        """Test auditing content with missing project references."""
        create_content("post", "post-1", linked_project=["nonexistent-project"])

        auditor = ContentAuditor(mock_audit_site)
        result = auditor.audit()

        assert result.stats.broken_links == 1
        assert len(result.issues) == 1
        assert result.issues[0].issue_type == IssueType.MISSING_PROJECT
        assert result.issues[0].severity == IssueSeverity.ERROR

    def test_audit_hidden_project(self, mock_audit_site, create_content):
        """Test auditing content linking to hidden projects."""
        create_content("post", "post-1", linked_project=["hidden-project"])

        auditor = ContentAuditor(mock_audit_site)
        result = auditor.audit()

        assert result.stats.hidden_project_links == 1
        assert len(result.issues) == 1
        assert result.issues[0].issue_type == IssueType.HIDDEN_PROJECT
        assert result.issues[0].severity == IssueSeverity.WARNING

    def test_audit_invalid_format_path(self, mock_audit_site, create_content):
        """Test auditing content with path instead of slug."""
        create_content("post", "post-1", linked_project=["/projects/valid-project/"])

        auditor = ContentAuditor(mock_audit_site)
        result = auditor.audit()

        assert result.stats.invalid_format_links == 1
        assert len(result.issues) == 1
        assert result.issues[0].issue_type == IssueType.INVALID_FORMAT
        assert "did you mean 'valid-project'" in result.issues[0].message

    def test_audit_content_without_links(self, mock_audit_site, create_content):
        """Test auditing content without any project links."""
        create_content("post", "post-1", linked_project=None)
        create_content("post", "post-2", linked_project=None)

        auditor = ContentAuditor(mock_audit_site)
        result = auditor.audit()

        assert result.stats.content_audited == 2
        assert result.stats.without_links == 2
        assert result.stats.with_project_links == 0

    def test_audit_mixed_issues(self, mock_audit_site, create_content):
        """Test auditing content with mix of valid and invalid links."""
        create_content("post", "post-1", linked_project=["valid-project"])
        create_content("post", "post-2", linked_project=["nonexistent"])
        create_content("post", "post-3", linked_project=["hidden-project"])
        create_content("post", "post-4", linked_project=None)

        auditor = ContentAuditor(mock_audit_site)
        result = auditor.audit()

        assert result.stats.content_audited == 4
        assert result.stats.with_project_links == 3
        assert result.stats.without_links == 1
        assert result.stats.valid_links == 1
        assert result.stats.broken_links == 1
        assert result.stats.hidden_project_links == 1
        assert len(result.issues) == 2

    def test_audit_multiple_links_per_content(self, mock_audit_site, create_content):
        """Test content with multiple linked_project entries."""
        create_content("post", "post-1", linked_project=["valid-project", "nonexistent", "another-valid"])

        auditor = ContentAuditor(mock_audit_site)
        result = auditor.audit()

        assert result.stats.valid_links == 2
        assert result.stats.broken_links == 1
        assert len(result.issues) == 1

    def test_audit_exclude_drafts_by_default(self, mock_audit_site, create_content):
        """Test that drafts are excluded by default."""
        create_content("post", "post-1", linked_project=["valid-project"], draft=False)
        create_content("post", "post-2", linked_project=["nonexistent"], draft=True)

        auditor = ContentAuditor(mock_audit_site)
        result = auditor.audit(include_drafts=False)

        assert result.stats.content_audited == 1
        # Only the valid link should be counted
        assert result.stats.broken_links == 0

    def test_audit_include_drafts(self, mock_audit_site, create_content):
        """Test including drafts in audit."""
        create_content("post", "post-1", linked_project=["valid-project"], draft=False)
        create_content("post", "post-2", linked_project=["nonexistent"], draft=True)

        auditor = ContentAuditor(mock_audit_site)
        result = auditor.audit(include_drafts=True)

        assert result.stats.content_audited == 2
        assert result.stats.broken_links == 1

    def test_audit_specific_content_types(self, mock_audit_site, create_content):
        """Test auditing specific content types only."""
        create_content("post", "post-1", linked_project=["valid-project"])
        create_content("papers", "paper-1", linked_project=["nonexistent"])

        auditor = ContentAuditor(mock_audit_site)
        result = auditor.audit(content_types=["post"])

        assert result.stats.content_audited == 1
        assert result.stats.broken_links == 0

    def test_audit_projects_with_content_stats(self, mock_audit_site, create_content):
        """Test project coverage statistics."""
        create_content("post", "post-1", linked_project=["valid-project"])
        create_content("post", "post-2", linked_project=["valid-project", "another-valid"])

        auditor = ContentAuditor(mock_audit_site)
        result = auditor.audit()

        # 4 total projects: valid-project, another-valid, hidden-project (in DB), cached-project (in cache)
        assert result.stats.projects_total == 4
        # 2 projects have content linking to them: valid-project, another-valid
        assert result.stats.projects_with_content == 2

    def test_fix_issues_removes_broken_links(self, mock_audit_site, create_content):
        """Test fix_issues removes broken project links."""
        content_path = create_content("post", "post-1", linked_project=["nonexistent", "valid-project"])

        auditor = ContentAuditor(mock_audit_site)
        result = auditor.audit()

        assert result.stats.broken_links == 1

        # Fix the issues
        fixed, failed = auditor.fix_issues(result.issues, dry_run=False)

        assert fixed == 1
        assert failed == 0

        # Verify the file was updated
        content = content_path.read_text()
        assert "nonexistent" not in content
        assert "valid-project" in content

    def test_fix_issues_dry_run(self, mock_audit_site, create_content):
        """Test fix_issues dry run doesn't modify files."""
        content_path = create_content("post", "post-1", linked_project=["nonexistent"])

        auditor = ContentAuditor(mock_audit_site)
        result = auditor.audit()

        original_content = content_path.read_text()

        fixed, failed = auditor.fix_issues(result.issues, dry_run=True)

        assert fixed == 1
        # File should not be modified
        assert content_path.read_text() == original_content

    def test_fix_issues_only_fixes_missing(self, mock_audit_site, create_content):
        """Test fix_issues only removes MISSING_PROJECT issues."""
        create_content("post", "post-1", linked_project=["hidden-project"])

        auditor = ContentAuditor(mock_audit_site)
        result = auditor.audit()

        # Should be a warning, not auto-fixed
        assert result.stats.hidden_project_links == 1

        fixed, failed = auditor.fix_issues(result.issues, dry_run=False)

        # Hidden project links should not be auto-fixed
        assert fixed == 0


class TestFormatValidation:
    """Tests for format validation methods."""

    def test_is_valid_format_slug(self, mock_audit_site):
        """Test valid slug formats."""
        auditor = ContentAuditor(mock_audit_site)
        auditor._load_projects()

        assert auditor._is_valid_format("my-project")
        assert auditor._is_valid_format("project_name")
        assert auditor._is_valid_format("project123")
        assert auditor._is_valid_format("a")

    def test_is_valid_format_invalid(self, mock_audit_site):
        """Test invalid format detection."""
        auditor = ContentAuditor(mock_audit_site)
        auditor._load_projects()

        assert not auditor._is_valid_format("/projects/my-project/")
        assert not auditor._is_valid_format("projects/my-project")
        assert not auditor._is_valid_format("/my-project")
        assert not auditor._is_valid_format("my-project/")
        assert not auditor._is_valid_format("./my-project")

    def test_extract_slug_from_path(self, mock_audit_site):
        """Test slug extraction from path references."""
        auditor = ContentAuditor(mock_audit_site)

        assert auditor._extract_slug_from_path("/projects/my-project/") == "my-project"
        assert auditor._extract_slug_from_path("projects/my-project") == "my-project"
        assert auditor._extract_slug_from_path("/project/my-project/") == "my-project"
        assert auditor._extract_slug_from_path("my-project") is None
        assert auditor._extract_slug_from_path("/other/path/") is None
