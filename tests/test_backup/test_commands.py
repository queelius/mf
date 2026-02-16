"""Tests for mf.backup.commands CLI module."""

import json
from datetime import datetime, timedelta

import pytest
from click.testing import CliRunner

from mf.backup.commands import (
    _format_age,
    backup,
    clean_cmd,
    list_cmd,
    rollback_cmd,
    status_cmd,
)


@pytest.fixture
def runner():
    """Create a Click CLI test runner."""
    return CliRunner()


@pytest.fixture
def mock_backup_site(mock_site_root):
    """Create mock site with backup files for testing."""
    root = mock_site_root
    mf_dir = root / ".mf"

    # Create paper database
    paper_db = {
        "_comment": "Test papers",
        "_schema_version": "2.0",
        "test-paper": {"title": "Test Paper"},
    }
    (mf_dir / "paper_db.json").write_text(json.dumps(paper_db, indent=2))

    # Create projects database
    projects_db = {
        "_comment": "Test projects",
        "_schema_version": "2.0",
    }
    (mf_dir / "projects_db.json").write_text(json.dumps(projects_db, indent=2))

    # Create series database
    series_db = {
        "_comment": "Test series",
        "_schema_version": "1.3",
    }
    (mf_dir / "series_db.json").write_text(json.dumps(series_db, indent=2))

    # Create some backup files for papers
    backups_dir = mf_dir / "backups" / "papers"
    now = datetime.now()
    for i in range(3):
        ts = (now - timedelta(days=i)).strftime("%Y%m%d_%H%M%S")
        backup_file = backups_dir / f"paper_db_{ts}.json"
        backup_file.write_text(json.dumps({"_comment": f"backup {i}"}))

    return root


# ---------------------------------------------------------------------------
# _format_age tests
# ---------------------------------------------------------------------------


def test_format_age_minutes():
    """Test formatting age less than an hour."""
    assert "m ago" in _format_age(0.01)


def test_format_age_hours():
    """Test formatting age in hours."""
    assert "h ago" in _format_age(0.2)


def test_format_age_days():
    """Test formatting age in days."""
    assert "d ago" in _format_age(3.0)


def test_format_age_weeks():
    """Test formatting age in weeks."""
    assert "w ago" in _format_age(14.0)


def test_format_age_months():
    """Test formatting age in months."""
    assert "mo ago" in _format_age(60.0)


# ---------------------------------------------------------------------------
# backup group tests
# ---------------------------------------------------------------------------


def test_backup_group_help(runner):
    """Test that backup group shows help."""
    result = runner.invoke(backup, ["--help"])
    assert result.exit_code == 0
    assert "Manage database backups" in result.output


# ---------------------------------------------------------------------------
# backup list tests
# ---------------------------------------------------------------------------


def test_backup_list_all(runner, mock_backup_site):
    """Test listing all backups."""
    result = runner.invoke(list_cmd, [])
    assert result.exit_code == 0
    assert "paper_db" in result.output


def test_backup_list_specific_db(runner, mock_backup_site):
    """Test listing backups for a specific database."""
    result = runner.invoke(list_cmd, ["--db", "paper_db"])
    assert result.exit_code == 0
    assert "paper_db" in result.output


def test_backup_list_no_backups(runner, mock_site_root):
    """Test listing when no backups exist."""
    # mock_site_root has empty backup directories
    mf_dir = mock_site_root / ".mf"
    (mf_dir / "paper_db.json").write_text('{"_comment": "test"}')
    (mf_dir / "projects_db.json").write_text('{"_comment": "test"}')
    (mf_dir / "series_db.json").write_text('{"_comment": "test"}')

    result = runner.invoke(list_cmd, [])
    assert result.exit_code == 0
    assert "No backups found" in result.output


# ---------------------------------------------------------------------------
# backup status tests
# ---------------------------------------------------------------------------


def test_backup_status(runner, mock_backup_site):
    """Test backup status command."""
    result = runner.invoke(status_cmd, [])
    assert result.exit_code == 0
    assert "Backup Status" in result.output
    assert "Retention Policy" in result.output


def test_backup_status_empty(runner, mock_site_root):
    """Test backup status when no backups exist."""
    mf_dir = mock_site_root / ".mf"
    (mf_dir / "paper_db.json").write_text('{"_comment": "test"}')
    (mf_dir / "projects_db.json").write_text('{"_comment": "test"}')
    (mf_dir / "series_db.json").write_text('{"_comment": "test"}')

    result = runner.invoke(status_cmd, [])
    assert result.exit_code == 0


# ---------------------------------------------------------------------------
# backup clean tests
# ---------------------------------------------------------------------------


def test_backup_clean_dry_run(runner, mock_backup_site):
    """Test backup clean --dry-run does not delete files."""
    # Create an old backup that should be cleaned
    root = mock_backup_site
    backups_dir = root / ".mf" / "backups" / "papers"
    old_ts = (datetime.now() - timedelta(days=60)).strftime("%Y%m%d_%H%M%S")
    old_backup = backups_dir / f"paper_db_{old_ts}.json"
    old_backup.write_text('{"_comment": "old"}')

    result = runner.invoke(
        clean_cmd, ["--dry-run", "--days", "1", "--keep", "1"]
    )
    assert result.exit_code == 0
    assert "DRY RUN" in result.output
    # File should still exist
    assert old_backup.exists()


def test_backup_clean_force(runner, mock_backup_site):
    """Test backup clean --force deletes old backups."""
    root = mock_backup_site
    backups_dir = root / ".mf" / "backups" / "papers"
    old_ts = (datetime.now() - timedelta(days=60)).strftime("%Y%m%d_%H%M%S")
    old_backup = backups_dir / f"paper_db_{old_ts}.json"
    old_backup.write_text('{"_comment": "old"}')

    result = runner.invoke(
        clean_cmd, ["--force", "--days", "1", "--keep", "1"]
    )
    assert result.exit_code == 0
    assert "Deleted" in result.output


def test_backup_clean_no_old_backups(runner, mock_site_root):
    """Test backup clean when nothing to clean."""
    mf_dir = mock_site_root / ".mf"
    (mf_dir / "paper_db.json").write_text('{"_comment": "test"}')
    (mf_dir / "projects_db.json").write_text('{"_comment": "test"}')
    (mf_dir / "series_db.json").write_text('{"_comment": "test"}')

    result = runner.invoke(clean_cmd, [])
    assert result.exit_code == 0
    assert "No old backups to clean up" in result.output


# ---------------------------------------------------------------------------
# backup rollback tests
# ---------------------------------------------------------------------------


def test_backup_rollback_dry_run(runner, mock_backup_site):
    """Test backup rollback --dry-run shows preview."""
    result = runner.invoke(rollback_cmd, ["paper_db", "--dry-run"])
    assert result.exit_code == 0
    assert "Rollback Preview" in result.output
    assert "DRY RUN" in result.output


def test_backup_rollback_force(runner, mock_backup_site):
    """Test backup rollback --force restores backup."""
    result = runner.invoke(rollback_cmd, ["paper_db", "--force"])
    assert result.exit_code == 0
    assert "Successfully restored" in result.output


def test_backup_rollback_no_backups(runner, mock_site_root):
    """Test backup rollback when no backups exist."""
    mf_dir = mock_site_root / ".mf"
    (mf_dir / "paper_db.json").write_text('{"_comment": "test"}')
    (mf_dir / "projects_db.json").write_text('{"_comment": "test"}')
    (mf_dir / "series_db.json").write_text('{"_comment": "test"}')

    result = runner.invoke(rollback_cmd, ["paper_db", "--force"])
    assert result.exit_code == 0
    assert "No backups found" in result.output


def test_backup_rollback_invalid_index(runner, mock_backup_site):
    """Test backup rollback with invalid index."""
    result = runner.invoke(rollback_cmd, ["paper_db", "--index", "999", "--force"])
    assert result.exit_code == 0
    assert "out of range" in result.output
