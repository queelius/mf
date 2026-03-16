"""Tests for mf.papers.processor module (artifact ingestion)."""

import shutil
from pathlib import Path

import pytest

from mf.papers.processor import (
    backup_existing_paper,
    copy_to_static,
    restore_backup,
)


# ---------------------------------------------------------------------------
# backup_existing_paper
# ---------------------------------------------------------------------------


def test_backup_existing_paper_no_existing_dir(mock_site_root):
    """Test backup returns None when paper directory does not exist."""
    result = backup_existing_paper("nonexistent-paper")
    assert result is None


def test_backup_existing_paper_creates_backup(mock_site_root):
    """Test that an existing paper directory is moved to backup."""
    # Create a paper directory in static/latex/
    paper_dir = mock_site_root / "static" / "latex" / "my-paper"
    paper_dir.mkdir(parents=True)
    (paper_dir / "index.html").write_text("<html>test</html>")

    result = backup_existing_paper("my-paper")

    assert result is not None
    # Original should be gone (moved)
    assert not paper_dir.exists()
    # Backup should exist
    assert result.exists()


def test_backup_existing_paper_dry_run(mock_site_root):
    """Test dry_run returns a backup path but does not move files."""
    paper_dir = mock_site_root / "static" / "latex" / "my-paper"
    paper_dir.mkdir(parents=True)
    (paper_dir / "index.html").write_text("<html>test</html>")

    result = backup_existing_paper("my-paper", dry_run=True)

    assert result is not None
    # Original should still exist
    assert paper_dir.exists()


# ---------------------------------------------------------------------------
# copy_to_static
# ---------------------------------------------------------------------------


def test_copy_to_static(mock_site_root, tmp_path):
    """Test copying generated files to /static/latex/{slug}/."""
    source_dir = tmp_path / "generated"
    source_dir.mkdir()
    (source_dir / "index.html").write_text("<html>paper</html>")
    (source_dir / "paper.css").write_text("body { color: red; }")
    sub = source_dir / "images"
    sub.mkdir()
    (sub / "fig1.png").write_bytes(b"\x89PNG")

    result = copy_to_static(source_dir, "test-paper")

    assert result is True
    target = mock_site_root / "static" / "latex" / "test-paper"
    assert (target / "index.html").exists()
    assert (target / "paper.css").exists()
    assert (target / "images" / "fig1.png").exists()


def test_copy_to_static_dry_run(mock_site_root, tmp_path):
    """Test that dry_run does not copy files."""
    source_dir = tmp_path / "generated"
    source_dir.mkdir()
    (source_dir / "index.html").write_text("<html>paper</html>")

    result = copy_to_static(source_dir, "test-paper", dry_run=True)

    assert result is True
    target = mock_site_root / "static" / "latex" / "test-paper"
    assert not target.exists()


# ---------------------------------------------------------------------------
# restore_backup
# ---------------------------------------------------------------------------


def test_restore_backup(mock_site_root, tmp_path):
    """Test restoring a backup to the latex directory."""
    slug = "restored-paper"
    # Create a fake backup
    backup_dir = tmp_path / "backup_source"
    backup_dir.mkdir()
    (backup_dir / "index.html").write_text("<html>backup</html>")

    restore_backup(backup_dir, slug)

    target = mock_site_root / "static" / "latex" / slug
    assert target.exists()
    assert (target / "index.html").read_text() == "<html>backup</html>"


def test_restore_backup_none_path(mock_site_root):
    """Test that restore_backup does nothing for None path."""
    # Should not raise
    restore_backup(None, "some-slug")


def test_restore_backup_nonexistent_path(mock_site_root, tmp_path):
    """Test that restore_backup does nothing for nonexistent path."""
    fake_path = tmp_path / "does_not_exist"
    # Should not raise
    restore_backup(fake_path, "some-slug")
