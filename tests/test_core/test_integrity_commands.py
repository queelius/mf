"""Tests for mf.core.integrity_commands CLI module."""

import json

import pytest
from click.testing import CliRunner
from unittest.mock import patch

from mf.core.integrity_commands import (
    integrity,
    integrity_check,
    integrity_fix,
    integrity_orphans,
)
from mf.core.integrity import (
    IntegrityIssue,
    IntegrityResult,
    IssueSeverity,
    IssueType,
)


@pytest.fixture
def runner():
    """Create a Click CLI test runner."""
    return CliRunner()


def _make_result(issues=None, checked=None):
    """Helper to create an IntegrityResult with given issues."""
    result = IntegrityResult()
    result.issues = issues or []
    result.checked = checked or {}
    return result


# ---------------------------------------------------------------------------
# integrity group tests
# ---------------------------------------------------------------------------


def test_integrity_group_help(runner):
    """Test that integrity group shows help."""
    result = runner.invoke(integrity, ["--help"])
    assert result.exit_code == 0
    assert "Database integrity checking" in result.output


# ---------------------------------------------------------------------------
# integrity check tests
# ---------------------------------------------------------------------------


def test_integrity_check_clean(runner):
    """Test integrity check on clean site (no issues)."""
    clean_result = _make_result(checked={"paper_db": 5, "projects_db": 3})

    with patch("mf.core.integrity.IntegrityChecker") as MockChecker:
        instance = MockChecker.return_value
        instance.check_all.return_value = clean_result

        result = runner.invoke(integrity_check, [])

    assert result.exit_code == 0
    assert "All integrity checks passed" in result.output


def test_integrity_check_with_errors(runner):
    """Test integrity check reporting errors."""
    issues = [
        IntegrityIssue(
            database="projects_db",
            entry_id="bad-project",
            issue_type=IssueType.INVALID_REFERENCE,
            message="Invalid related_posts reference: /post/nonexistent/",
            severity=IssueSeverity.ERROR,
        ),
    ]
    error_result = _make_result(issues=issues, checked={"projects_db": 3})

    with patch("mf.core.integrity.IntegrityChecker") as MockChecker:
        instance = MockChecker.return_value
        instance.check_all.return_value = error_result

        result = runner.invoke(integrity_check, [])

    assert result.exit_code == 0
    assert "Errors" in result.output or "error" in result.output.lower()


def test_integrity_check_json_output(runner):
    """Test integrity check --json outputs valid JSON."""
    clean_result = _make_result(checked={"paper_db": 5})

    with patch("mf.core.integrity.IntegrityChecker") as MockChecker:
        instance = MockChecker.return_value
        instance.check_all.return_value = clean_result

        result = runner.invoke(integrity_check, ["--json"])

    assert result.exit_code == 0
    data = json.loads(result.output)
    assert "issues" in data
    assert "checked" in data


def test_integrity_check_specific_db(runner):
    """Test integrity check for a specific database."""
    db_result = _make_result(checked={"paper_db": 5})

    with patch("mf.core.integrity.IntegrityChecker") as MockChecker:
        instance = MockChecker.return_value
        instance.check_database.return_value = db_result

        result = runner.invoke(integrity_check, ["--db", "paper_db"])

    assert result.exit_code == 0
    instance.check_database.assert_called_once_with("paper_db")


def test_integrity_check_with_fixable_issues(runner):
    """Test integrity check mentioning fixable issues."""
    issues = [
        IntegrityIssue(
            database="projects_cache",
            entry_id="stale-entry",
            issue_type=IssueType.STALE_CACHE,
            message="Stale cache entry",
            severity=IssueSeverity.INFO,
            fixable=True,
        ),
    ]
    fixable_result = _make_result(issues=issues, checked={"projects_cache": 3})

    with patch("mf.core.integrity.IntegrityChecker") as MockChecker:
        instance = MockChecker.return_value
        instance.check_all.return_value = fixable_result

        result = runner.invoke(integrity_check, [])

    assert result.exit_code == 0
    assert "fix" in result.output.lower()


# ---------------------------------------------------------------------------
# integrity fix tests
# ---------------------------------------------------------------------------


def test_integrity_fix_no_fixable_issues(runner):
    """Test integrity fix when nothing to fix."""
    clean_result = _make_result(checked={"paper_db": 5})

    with patch("mf.core.integrity.IntegrityChecker") as MockChecker:
        instance = MockChecker.return_value
        instance.check_all.return_value = clean_result

        result = runner.invoke(integrity_fix, [])

    assert result.exit_code == 0
    assert "No fixable issues" in result.output


def test_integrity_fix_dry_run(runner):
    """Test integrity fix --dry-run previews fixes."""
    issues = [
        IntegrityIssue(
            database="projects_cache",
            entry_id="stale-entry",
            issue_type=IssueType.STALE_CACHE,
            message="Stale cache entry",
            severity=IssueSeverity.INFO,
            fixable=True,
        ),
    ]
    fixable_result = _make_result(issues=issues, checked={"projects_cache": 3})

    with patch("mf.core.integrity.IntegrityChecker") as MockChecker:
        instance = MockChecker.return_value
        instance.check_all.return_value = fixable_result
        instance.fix_issues.return_value = (1, 0)

        result = runner.invoke(integrity_fix, ["--dry-run"])

    assert result.exit_code == 0
    assert "Dry run" in result.output or "dry run" in result.output.lower()
    instance.fix_issues.assert_called_once()
    # Verify dry_run=True was passed
    call_args = instance.fix_issues.call_args
    assert call_args.kwargs.get("dry_run") is True or call_args[1].get("dry_run") is True


def test_integrity_fix_yes(runner):
    """Test integrity fix --yes applies fixes without confirmation."""
    issues = [
        IntegrityIssue(
            database="projects_cache",
            entry_id="stale-entry",
            issue_type=IssueType.STALE_CACHE,
            message="Stale cache entry",
            severity=IssueSeverity.INFO,
            fixable=True,
        ),
    ]
    fixable_result = _make_result(issues=issues, checked={"projects_cache": 3})

    with patch("mf.core.integrity.IntegrityChecker") as MockChecker:
        instance = MockChecker.return_value
        instance.check_all.return_value = fixable_result
        instance.fix_issues.return_value = (1, 0)

        result = runner.invoke(integrity_fix, ["--yes"])

    assert result.exit_code == 0
    assert "Fixed: 1" in result.output


def test_integrity_fix_json_output(runner):
    """Test integrity fix --json outputs valid JSON."""
    issues = [
        IntegrityIssue(
            database="projects_cache",
            entry_id="stale-entry",
            issue_type=IssueType.STALE_CACHE,
            message="Stale cache entry",
            severity=IssueSeverity.INFO,
            fixable=True,
        ),
    ]
    fixable_result = _make_result(issues=issues, checked={"projects_cache": 3})

    with patch("mf.core.integrity.IntegrityChecker") as MockChecker:
        instance = MockChecker.return_value
        instance.check_all.return_value = fixable_result

        result = runner.invoke(integrity_fix, ["--json"])

    assert result.exit_code == 0
    data = json.loads(result.output)
    assert "fixable" in data
    assert data["count"] == 1


# ---------------------------------------------------------------------------
# integrity orphans tests
# ---------------------------------------------------------------------------


def test_integrity_orphans_none_found(runner):
    """Test integrity orphans when none exist."""
    clean_result = _make_result()

    with patch("mf.core.integrity.IntegrityChecker") as MockChecker:
        instance = MockChecker.return_value
        instance.find_orphans.return_value = clean_result

        result = runner.invoke(integrity_orphans, [])

    assert result.exit_code == 0
    assert "No orphaned entries" in result.output


def test_integrity_orphans_json_output(runner):
    """Test integrity orphans --json outputs valid JSON."""
    orphan_result = _make_result(
        issues=[
            IntegrityIssue(
                database="paper_db",
                entry_id="orphan-paper",
                issue_type=IssueType.ORPHANED_DB_ENTRY,
                message="Paper in database but no content",
                severity=IssueSeverity.WARNING,
            ),
        ]
    )

    with patch("mf.core.integrity.IntegrityChecker") as MockChecker:
        instance = MockChecker.return_value
        instance.find_orphans.return_value = orphan_result

        result = runner.invoke(integrity_orphans, ["--json"])

    assert result.exit_code == 0
    data = json.loads(result.output)
    assert len(data["issues"]) == 1
    assert data["issues"][0]["entry_id"] == "orphan-paper"


def test_integrity_orphans_table(runner):
    """Test integrity orphans displays a table."""
    orphan_result = _make_result(
        issues=[
            IntegrityIssue(
                database="paper_db",
                entry_id="orphan-paper",
                issue_type=IssueType.ORPHANED_DB_ENTRY,
                message="Paper in database but no content",
                severity=IssueSeverity.WARNING,
                fixable=False,
            ),
            IntegrityIssue(
                database="projects_cache",
                entry_id="stale-cache",
                issue_type=IssueType.STALE_CACHE,
                message="Stale cache entry",
                severity=IssueSeverity.INFO,
                fixable=True,
            ),
        ]
    )

    with patch("mf.core.integrity.IntegrityChecker") as MockChecker:
        instance = MockChecker.return_value
        instance.find_orphans.return_value = orphan_result

        result = runner.invoke(integrity_orphans, [])

    assert result.exit_code == 0
    assert "Orphaned Entries" in result.output
    assert "orphan-paper" in result.output
    assert "stale-cache" in result.output
