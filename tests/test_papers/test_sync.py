"""Tests for mf.papers.sync module (paper synchronization and staleness)."""

import json
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from mf.papers.sync import (
    SyncStatus,
    SyncResults,
    ProcessingResult,
    check_paper_staleness,
    check_all_papers,
    print_sync_status,
)
from mf.core.database import PaperDatabase, PaperEntry


# ---------------------------------------------------------------------------
# SyncResults / ProcessingResult dataclasses
# ---------------------------------------------------------------------------


def test_sync_results_empty():
    """Test SyncResults with no results."""
    results = SyncResults()
    assert results.success_count == 0
    assert results.failure_count == 0


def test_sync_results_counts():
    """Test SyncResults success and failure counts."""
    results = SyncResults()
    results.succeeded.append(ProcessingResult(slug="a", success=True, duration=1.0))
    results.succeeded.append(ProcessingResult(slug="b", success=True, duration=2.0))
    results.failed.append(ProcessingResult(slug="c", success=False, error="fail", duration=0.5))

    assert results.success_count == 2
    assert results.failure_count == 1


def test_processing_result_fields():
    """Test ProcessingResult dataclass fields."""
    r = ProcessingResult(slug="test", success=True, duration=3.5)
    assert r.slug == "test"
    assert r.success is True
    assert r.error is None
    assert r.duration == 3.5


def test_sync_results_print_summary(capsys):
    """Test that print_summary runs without errors."""
    results = SyncResults()
    results.succeeded.append(ProcessingResult(slug="ok", success=True, duration=1.0))
    results.failed.append(ProcessingResult(slug="bad", success=False, error="timeout"))
    # Should not raise
    results.print_summary()


# ---------------------------------------------------------------------------
# check_paper_staleness
# ---------------------------------------------------------------------------


def test_staleness_non_tex_format():
    """Test that non-tex source format is skipped."""
    entry = PaperEntry(slug="docx-paper", data={
        "source_path": "/some/file.docx",
        "source_format": "docx",
    })
    status, path = check_paper_staleness(entry)
    assert status == "skipped_non_tex"


def test_staleness_no_source_path():
    """Test that missing source_path is skipped."""
    entry = PaperEntry(slug="no-source", data={})
    status, path = check_paper_staleness(entry)
    assert status == "skipped"
    assert path is None


def test_staleness_missing_file(tmp_path):
    """Test that a nonexistent source file is reported as missing."""
    missing = tmp_path / "nonexistent.tex"
    entry = PaperEntry(slug="missing", data={
        "source_path": str(missing),
    })
    status, path = check_paper_staleness(entry)
    assert status == "missing"
    assert path == missing


def test_staleness_directory_source(tmp_path):
    """Test that a directory source path is skipped."""
    dir_path = tmp_path / "paper_dir"
    dir_path.mkdir()
    entry = PaperEntry(slug="dir-paper", data={
        "source_path": str(dir_path),
    })
    status, path = check_paper_staleness(entry)
    assert status == "skipped"


def test_staleness_no_hash(tmp_path):
    """Test that a file without stored hash is reported as no_hash (stale)."""
    tex_file = tmp_path / "paper.tex"
    tex_file.write_text(r"\documentclass{article}")
    entry = PaperEntry(slug="no-hash", data={
        "source_path": str(tex_file),
        # No source_hash
    })
    status, path = check_paper_staleness(entry)
    assert status == "no_hash"
    assert path == tex_file


@patch("mf.papers.sync.verify_file_hash")
def test_staleness_up_to_date(mock_verify, tmp_path):
    """Test that matching hash is reported as up_to_date."""
    tex_file = tmp_path / "paper.tex"
    tex_file.write_text(r"\documentclass{article}")
    mock_verify.return_value = True

    entry = PaperEntry(slug="current", data={
        "source_path": str(tex_file),
        "source_hash": "sha256:abc123",
    })
    status, path = check_paper_staleness(entry)
    assert status == "up_to_date"
    mock_verify.assert_called_once_with(tex_file, "sha256:abc123")


@patch("mf.papers.sync.verify_file_hash")
def test_staleness_stale(mock_verify, tmp_path):
    """Test that mismatched hash is reported as stale."""
    tex_file = tmp_path / "paper.tex"
    tex_file.write_text(r"\documentclass{article}")
    mock_verify.return_value = False

    entry = PaperEntry(slug="stale", data={
        "source_path": str(tex_file),
        "source_hash": "sha256:old_hash",
    })
    status, path = check_paper_staleness(entry)
    assert status == "stale"


# ---------------------------------------------------------------------------
# check_all_papers
# ---------------------------------------------------------------------------


@patch("mf.papers.sync.check_paper_staleness")
def test_check_all_papers_categorization(mock_check, mock_site_root):
    """Test that check_all_papers correctly categorizes papers."""
    db = PaperDatabase(mock_site_root / ".mf" / "paper_db.json")
    db.load()

    # Create entries with source_path so they appear in papers_with_source()
    db.set("up-paper", {
        "title": "Up-to-date",
        "source_path": "/some/up.tex",
    })
    db.set("stale-paper", {
        "title": "Stale",
        "source_path": "/some/stale.tex",
    })
    db.set("missing-paper", {
        "title": "Missing",
        "source_path": "/some/missing.tex",
    })

    def staleness_side_effect(entry):
        if entry.slug == "up-paper":
            return ("up_to_date", Path("/some/up.tex"))
        elif entry.slug == "stale-paper":
            return ("stale", Path("/some/stale.tex"))
        elif entry.slug == "missing-paper":
            return ("missing", Path("/some/missing.tex"))
        return ("skipped", None)

    mock_check.side_effect = staleness_side_effect

    status = check_all_papers(db)

    assert isinstance(status, SyncStatus)
    assert len(status.up_to_date) == 1
    assert len(status.stale) == 1
    assert len(status.missing) == 1


@patch("mf.papers.sync.check_paper_staleness")
def test_check_all_papers_no_hash_is_stale(mock_check, mock_site_root):
    """Test that no_hash entries are categorized as stale."""
    db = PaperDatabase(mock_site_root / ".mf" / "paper_db.json")
    db.load()
    db.set("nohash-paper", {
        "title": "No Hash",
        "source_path": "/some/nohash.tex",
    })

    mock_check.return_value = ("no_hash", Path("/some/nohash.tex"))

    status = check_all_papers(db)

    assert len(status.stale) == 1
    # Verify the reason is "no hash"
    _, _, reason = status.stale[0]
    assert reason == "no hash"


# ---------------------------------------------------------------------------
# print_sync_status
# ---------------------------------------------------------------------------


def test_print_sync_status_empty():
    """Test printing an empty sync status without errors."""
    status = SyncStatus(stale=[], missing=[], up_to_date=[], skipped=[])
    # Should not raise
    print_sync_status(status)


def test_print_sync_status_with_data():
    """Test printing sync status with mixed data."""
    up_entry = PaperEntry(slug="good-paper", data={"title": "Good"})
    stale_entry = PaperEntry(slug="old-paper", data={"title": "Old"})
    missing_entry = PaperEntry(slug="gone-paper", data={"title": "Gone"})
    skipped_entry = PaperEntry(slug="skip-paper", data={"title": "Skip"})

    status = SyncStatus(
        up_to_date=[(up_entry, Path("/src/good.tex"))],
        stale=[(stale_entry, Path("/src/old.tex"), "changed")],
        missing=[(missing_entry, "/src/gone.tex")],
        skipped=[(skipped_entry, "directory reference")],
    )
    # Should not raise
    print_sync_status(status)
