"""Tests for mf.core.integrity module."""

import json
import pytest
from pathlib import Path

from mf.core.integrity import (
    IntegrityChecker,
    IntegrityResult,
    IntegrityIssue,
    IssueType,
    IssueSeverity,
)


@pytest.fixture
def mock_integrity_site(tmp_path, monkeypatch):
    """Create a mock site structure for integrity testing."""
    # Create .mf/ directory structure
    mf_dir = tmp_path / ".mf"
    mf_dir.mkdir()
    (mf_dir / "cache").mkdir()
    (mf_dir / "backups" / "papers").mkdir(parents=True)
    (mf_dir / "backups" / "projects").mkdir(parents=True)
    (mf_dir / "backups" / "series").mkdir(parents=True)

    # Create content directories
    (tmp_path / "content" / "post").mkdir(parents=True)
    (tmp_path / "content" / "papers").mkdir(parents=True)
    (tmp_path / "content" / "projects").mkdir(parents=True)
    (tmp_path / "content" / "series").mkdir(parents=True)

    # Mock get_site_root
    from mf.core import config
    config.get_site_root.cache_clear()
    monkeypatch.setattr(config, "get_site_root", lambda: tmp_path)

    return tmp_path


@pytest.fixture
def setup_databases(mock_integrity_site):
    """Create test databases."""
    mf_dir = mock_integrity_site / ".mf"

    # Paper database with entries
    paper_db = {
        "_comment": "Test papers",
        "_schema_version": "2.0",
        "paper-with-content": {
            "title": "Paper With Content",
            "source_path": str(mock_integrity_site / "latex" / "paper.tex"),
        },
        "paper-no-content": {
            "title": "Paper Without Content",
        },
    }
    (mf_dir / "paper_db.json").write_text(json.dumps(paper_db, indent=2))

    # Create content file for paper-with-content
    paper_dir = mock_integrity_site / "content" / "papers" / "paper-with-content"
    paper_dir.mkdir(parents=True)
    (paper_dir / "index.md").write_text("---\ntitle: Paper With Content\n---\n")

    # Projects database
    projects_db = {
        "_comment": "Test projects",
        "_schema_version": "2.0",
        "project-with-content": {
            "title": "Project With Content",
        },
        "project-no-content": {
            "title": "Project Without Content",
            "related_posts": ["/post/nonexistent/"],  # Invalid reference
        },
    }
    (mf_dir / "projects_db.json").write_text(json.dumps(projects_db, indent=2))

    # Create content file for project-with-content
    proj_dir = mock_integrity_site / "content" / "projects" / "project-with-content"
    proj_dir.mkdir(parents=True)
    (proj_dir / "index.md").write_text("---\ntitle: Project With Content\n---\n")

    # Projects cache with orphan
    projects_cache = {
        "cached-project": {
            "name": "Cached Project",
        },
        "orphan-cache-entry": {
            "name": "Orphan in Cache",
        },
    }
    (mf_dir / "cache" / "projects.json").write_text(json.dumps(projects_cache, indent=2))

    # Create content for cached-project
    cached_dir = mock_integrity_site / "content" / "projects" / "cached-project"
    cached_dir.mkdir(parents=True)
    (cached_dir / "index.md").write_text("---\ntitle: Cached Project\n---\n")

    # Series database with sync state
    series_db = {
        "_comment": "Test series",
        "_schema_version": "1.3",
        "test-series": {
            "title": "Test Series",
            "related_projects": ["project-with-content", "nonexistent-project"],
            "_sync_state": {
                "existing-post": {"source_hash": "abc123"},
                "orphan-post": {"source_hash": "def456"},  # No content
            },
        },
    }
    (mf_dir / "series_db.json").write_text(json.dumps(series_db, indent=2))

    # Create series content directory with existing post
    series_dir = mock_integrity_site / "content" / "series" / "test-series"
    series_dir.mkdir(parents=True)
    (series_dir / "_index.md").write_text("---\ntitle: Test Series\n---\n")
    post_dir = series_dir / "existing-post"
    post_dir.mkdir()
    (post_dir / "index.md").write_text("---\ntitle: Existing Post\n---\n")

    return mock_integrity_site


class TestIntegrityIssue:
    """Tests for IntegrityIssue dataclass."""

    def test_to_dict(self):
        """Test IntegrityIssue.to_dict() serialization."""
        issue = IntegrityIssue(
            database="paper_db",
            entry_id="test-paper",
            issue_type=IssueType.ORPHANED_DB_ENTRY,
            message="Test message",
            severity=IssueSeverity.WARNING,
            fixable=True,
            extra={"key": "value"},
        )

        d = issue.to_dict()

        assert d["database"] == "paper_db"
        assert d["entry_id"] == "test-paper"
        assert d["issue_type"] == "orphaned_db_entry"
        assert d["severity"] == "warning"
        assert d["fixable"] is True
        assert d["extra"] == {"key": "value"}


class TestIntegrityResult:
    """Tests for IntegrityResult dataclass."""

    def test_has_errors(self):
        """Test has_errors property."""
        result = IntegrityResult()
        assert not result.has_errors

        result.issues.append(
            IntegrityIssue(
                database="test",
                entry_id="test",
                issue_type=IssueType.INVALID_REFERENCE,
                message="Test",
                severity=IssueSeverity.ERROR,
            )
        )
        assert result.has_errors

    def test_has_fixable(self):
        """Test has_fixable property."""
        result = IntegrityResult()
        assert not result.has_fixable

        result.issues.append(
            IntegrityIssue(
                database="test",
                entry_id="test",
                issue_type=IssueType.STALE_CACHE,
                message="Test",
                fixable=True,
            )
        )
        assert result.has_fixable

    def test_group_by_database(self):
        """Test _group_by_database method."""
        result = IntegrityResult()
        result.issues.append(
            IntegrityIssue("paper_db", "a", IssueType.ORPHANED_DB_ENTRY, "Test")
        )
        result.issues.append(
            IntegrityIssue("paper_db", "b", IssueType.MISSING_SOURCE, "Test")
        )
        result.issues.append(
            IntegrityIssue("projects_db", "c", IssueType.INVALID_REFERENCE, "Test")
        )

        by_db = result._group_by_database()

        assert by_db["paper_db"] == 2
        assert by_db["projects_db"] == 1

    def test_group_by_severity(self):
        """Test _group_by_severity method."""
        result = IntegrityResult()
        result.issues.append(
            IntegrityIssue(
                "test", "a", IssueType.INVALID_REFERENCE, "Test",
                severity=IssueSeverity.ERROR
            )
        )
        result.issues.append(
            IntegrityIssue(
                "test", "b", IssueType.ORPHANED_DB_ENTRY, "Test",
                severity=IssueSeverity.WARNING
            )
        )

        by_sev = result._group_by_severity()

        assert by_sev["error"] == 1
        assert by_sev["warning"] == 1

    def test_to_json(self):
        """Test JSON serialization."""
        result = IntegrityResult()
        result.checked["paper_db"] = 5

        json_str = result.to_json()
        data = json.loads(json_str)

        assert data["checked"]["paper_db"] == 5


class TestIntegrityChecker:
    """Tests for IntegrityChecker class."""

    def test_check_all_clean_site(self, mock_integrity_site):
        """Test check_all on a clean site with no databases."""
        checker = IntegrityChecker(mock_integrity_site)
        result = checker.check_all()

        # Should have some checked counts but no issues
        assert isinstance(result, IntegrityResult)

    def test_check_paper_db_orphan(self, setup_databases):
        """Test detection of orphaned paper database entry."""
        checker = IntegrityChecker(setup_databases)
        result = checker.check_database("paper_db")

        # Should find paper-no-content as orphaned
        orphans = [i for i in result.issues if i.issue_type == IssueType.ORPHANED_DB_ENTRY]
        assert any(i.entry_id == "paper-no-content" for i in orphans)

    def test_check_projects_db_invalid_reference(self, setup_databases):
        """Test detection of invalid reference in projects database."""
        checker = IntegrityChecker(setup_databases)
        result = checker.check_database("projects_db")

        # Should find invalid related_posts reference
        invalid_refs = [i for i in result.issues if i.issue_type == IssueType.INVALID_REFERENCE]
        assert len(invalid_refs) > 0
        assert any("related_posts" in i.message for i in invalid_refs)

    def test_check_projects_cache_stale(self, setup_databases):
        """Test detection of stale cache entry."""
        checker = IntegrityChecker(setup_databases)
        result = checker.check_database("projects_cache")

        # Should find orphan-cache-entry as stale
        stale = [i for i in result.issues if i.issue_type == IssueType.STALE_CACHE]
        assert any(i.entry_id == "orphan-cache-entry" for i in stale)
        assert all(i.fixable for i in stale)

    def test_check_series_db_invalid_project_ref(self, setup_databases):
        """Test detection of invalid project reference in series."""
        checker = IntegrityChecker(setup_databases)
        result = checker.check_database("series_db")

        # Should find nonexistent-project reference
        invalid_refs = [i for i in result.issues if i.issue_type == IssueType.INVALID_REFERENCE]
        assert any("nonexistent-project" in i.message for i in invalid_refs)

    def test_check_series_db_sync_state_orphan(self, setup_databases):
        """Test detection of orphaned sync state entry."""
        checker = IntegrityChecker(setup_databases)
        result = checker.check_database("series_db")

        # Should find orphan-post sync state
        orphans = [i for i in result.issues if i.issue_type == IssueType.SYNC_STATE_ORPHAN]
        assert any("orphan-post" in i.entry_id for i in orphans)
        assert all(i.fixable for i in orphans)

    def test_find_orphans(self, setup_databases):
        """Test find_orphans returns only orphan-type issues."""
        checker = IntegrityChecker(setup_databases)
        result = checker.find_orphans()

        # All issues should be orphan-related
        orphan_types = {
            IssueType.ORPHANED_DB_ENTRY,
            IssueType.STALE_CACHE,
            IssueType.SYNC_STATE_ORPHAN,
        }
        assert all(i.issue_type in orphan_types for i in result.issues)

    def test_fix_stale_cache_dry_run(self, setup_databases):
        """Test fix_issues dry run for stale cache."""
        checker = IntegrityChecker(setup_databases)
        result = checker.check_database("projects_cache")
        stale = [i for i in result.issues if i.fixable]

        fixed, failed = checker.fix_issues(stale, dry_run=True)

        assert fixed > 0
        assert failed == 0

        # Cache entry should still exist after dry run
        checker.projects_cache.load()
        assert "orphan-cache-entry" in checker.projects_cache

    def test_fix_stale_cache_actual(self, setup_databases):
        """Test fix_issues actually removes stale cache entry."""
        checker = IntegrityChecker(setup_databases)
        result = checker.check_database("projects_cache")
        stale = [i for i in result.issues if i.issue_type == IssueType.STALE_CACHE]

        fixed, failed = checker.fix_issues(stale, dry_run=False)

        assert fixed > 0
        assert failed == 0

        # Cache entry should be removed
        checker.projects_cache.load()
        assert "orphan-cache-entry" not in checker.projects_cache

    def test_check_specific_database(self, setup_databases):
        """Test checking a specific database."""
        checker = IntegrityChecker(setup_databases)

        result = checker.check_database("paper_db")

        assert "paper_db" in result.checked
        assert result.checked["paper_db"] > 0
        # Should not check other databases
        assert "projects_db" not in result.checked

    def test_check_unknown_database(self, setup_databases, capsys):
        """Test checking an unknown database name."""
        checker = IntegrityChecker(setup_databases)

        result = checker.check_database("unknown_db")

        # Should return empty result
        assert len(result.issues) == 0


class TestIssueTypes:
    """Tests for issue type enums."""

    def test_issue_type_values(self):
        """Test IssueType enum values."""
        assert IssueType.ORPHANED_DB_ENTRY.value == "orphaned_db_entry"
        assert IssueType.STALE_CACHE.value == "stale_cache"
        assert IssueType.INVALID_REFERENCE.value == "invalid_reference"
        assert IssueType.MISSING_SOURCE.value == "missing_source"

    def test_severity_values(self):
        """Test IssueSeverity enum values."""
        assert IssueSeverity.ERROR.value == "error"
        assert IssueSeverity.WARNING.value == "warning"
        assert IssueSeverity.INFO.value == "info"


class TestStaticAssetChecks:
    """Tests for static asset integrity checks."""

    def test_missing_pdf_path(self, mock_integrity_site):
        """Test detection of missing PDF file referenced in paper_db."""
        mf_dir = mock_integrity_site / ".mf"

        # Paper with pdf_path pointing to non-existent file
        paper_db = {
            "_comment": "Test papers",
            "_schema_version": "2.0",
            "paper-with-missing-pdf": {
                "title": "Paper With Missing PDF",
                "pdf_path": "/latex/missing-paper/paper.pdf",
            },
        }
        (mf_dir / "paper_db.json").write_text(json.dumps(paper_db, indent=2))

        # Create content file so it's not flagged as orphan
        paper_dir = mock_integrity_site / "content" / "papers" / "paper-with-missing-pdf"
        paper_dir.mkdir(parents=True)
        (paper_dir / "index.md").write_text("---\ntitle: Paper\n---\n")

        checker = IntegrityChecker(mock_integrity_site)
        result = checker.check_all()

        # Should find missing static asset
        missing_assets = [i for i in result.issues if i.issue_type == IssueType.MISSING_STATIC_ASSET]
        assert len(missing_assets) == 1
        assert missing_assets[0].entry_id == "paper-with-missing-pdf"
        assert "pdf_path" in missing_assets[0].extra.get("field", "")
        assert missing_assets[0].severity == IssueSeverity.WARNING
        assert not missing_assets[0].fixable

    def test_missing_html_path(self, mock_integrity_site):
        """Test detection of missing HTML file referenced in paper_db."""
        mf_dir = mock_integrity_site / ".mf"

        paper_db = {
            "_comment": "Test papers",
            "_schema_version": "2.0",
            "paper-with-missing-html": {
                "title": "Paper With Missing HTML",
                "html_path": "/latex/missing-paper/index.html",
            },
        }
        (mf_dir / "paper_db.json").write_text(json.dumps(paper_db, indent=2))

        # Create content file
        paper_dir = mock_integrity_site / "content" / "papers" / "paper-with-missing-html"
        paper_dir.mkdir(parents=True)
        (paper_dir / "index.md").write_text("---\ntitle: Paper\n---\n")

        checker = IntegrityChecker(mock_integrity_site)
        result = checker.check_all()

        missing_assets = [i for i in result.issues if i.issue_type == IssueType.MISSING_STATIC_ASSET]
        assert len(missing_assets) == 1
        assert "html_path" in missing_assets[0].extra.get("field", "")

    def test_missing_cite_path(self, mock_integrity_site):
        """Test detection of missing BibTeX citation file referenced in paper_db."""
        mf_dir = mock_integrity_site / ".mf"

        paper_db = {
            "_comment": "Test papers",
            "_schema_version": "2.0",
            "paper-with-missing-cite": {
                "title": "Paper With Missing Citation",
                "cite_path": "/latex/missing-paper/cite.bib",
            },
        }
        (mf_dir / "paper_db.json").write_text(json.dumps(paper_db, indent=2))

        # Create content file
        paper_dir = mock_integrity_site / "content" / "papers" / "paper-with-missing-cite"
        paper_dir.mkdir(parents=True)
        (paper_dir / "index.md").write_text("---\ntitle: Paper\n---\n")

        checker = IntegrityChecker(mock_integrity_site)
        result = checker.check_all()

        missing_assets = [i for i in result.issues if i.issue_type == IssueType.MISSING_STATIC_ASSET]
        assert len(missing_assets) == 1
        assert "cite_path" in missing_assets[0].extra.get("field", "")

    def test_valid_static_assets_no_issues(self, mock_integrity_site):
        """Test that valid static asset paths don't generate issues."""
        mf_dir = mock_integrity_site / ".mf"

        # Create static directory and files
        latex_dir = mock_integrity_site / "static" / "latex" / "good-paper"
        latex_dir.mkdir(parents=True)
        (latex_dir / "paper.pdf").write_bytes(b"%PDF-1.4 test")
        (latex_dir / "index.html").write_text("<html>Test</html>")
        (latex_dir / "cite.bib").write_text("@article{test, title={Test}}")

        paper_db = {
            "_comment": "Test papers",
            "_schema_version": "2.0",
            "good-paper": {
                "title": "Good Paper",
                "pdf_path": "/latex/good-paper/paper.pdf",
                "html_path": "/latex/good-paper/index.html",
                "cite_path": "/latex/good-paper/cite.bib",
            },
        }
        (mf_dir / "paper_db.json").write_text(json.dumps(paper_db, indent=2))

        # Create content file
        paper_dir = mock_integrity_site / "content" / "papers" / "good-paper"
        paper_dir.mkdir(parents=True)
        (paper_dir / "index.md").write_text("---\ntitle: Good Paper\n---\n")

        checker = IntegrityChecker(mock_integrity_site)
        result = checker.check_all()

        # Should have no MISSING_STATIC_ASSET issues
        missing_assets = [i for i in result.issues if i.issue_type == IssueType.MISSING_STATIC_ASSET]
        assert len(missing_assets) == 0

    def test_multiple_missing_assets(self, mock_integrity_site):
        """Test detection of multiple missing assets in same paper."""
        mf_dir = mock_integrity_site / ".mf"

        paper_db = {
            "_comment": "Test papers",
            "_schema_version": "2.0",
            "paper-with-all-missing": {
                "title": "Paper With All Missing",
                "pdf_path": "/latex/missing/paper.pdf",
                "html_path": "/latex/missing/index.html",
                "cite_path": "/latex/missing/cite.bib",
            },
        }
        (mf_dir / "paper_db.json").write_text(json.dumps(paper_db, indent=2))

        # Create content file
        paper_dir = mock_integrity_site / "content" / "papers" / "paper-with-all-missing"
        paper_dir.mkdir(parents=True)
        (paper_dir / "index.md").write_text("---\ntitle: Paper\n---\n")

        checker = IntegrityChecker(mock_integrity_site)
        result = checker.check_all()

        missing_assets = [i for i in result.issues if i.issue_type == IssueType.MISSING_STATIC_ASSET]
        assert len(missing_assets) == 3

        # Check that all fields are represented
        fields = {i.extra.get("field") for i in missing_assets}
        assert fields == {"pdf_path", "html_path", "cite_path"}

    def test_static_assets_checked_count(self, mock_integrity_site):
        """Test that static_assets check count is recorded in result."""
        mf_dir = mock_integrity_site / ".mf"

        paper_db = {
            "_comment": "Test papers",
            "_schema_version": "2.0",
            "paper-one": {"title": "Paper One"},
            "paper-two": {"title": "Paper Two"},
        }
        (mf_dir / "paper_db.json").write_text(json.dumps(paper_db, indent=2))

        checker = IntegrityChecker(mock_integrity_site)
        result = checker.check_all()

        # Should record the count of papers checked for static assets
        assert "static_assets" in result.checked
        assert result.checked["static_assets"] == 2
