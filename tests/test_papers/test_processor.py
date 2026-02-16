"""Tests for mf.papers.processor module (LaTeX paper processing)."""

import json
import shutil
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from mf.papers.processor import (
    find_tex_files,
    run_command,
    generate_html,
    generate_pdf,
    backup_existing_paper,
    copy_to_static,
    restore_backup,
)


# ---------------------------------------------------------------------------
# find_tex_files
# ---------------------------------------------------------------------------


def test_find_tex_files_single_file(tmp_path):
    """Test finding a single .tex file when given a direct path."""
    tex = tmp_path / "paper.tex"
    tex.write_text(r"\documentclass{article}")
    result = find_tex_files(tex)
    assert len(result) == 1
    assert result[0] == tex.resolve()


def test_find_tex_files_in_directory(tmp_path):
    """Test finding .tex files recursively in a directory."""
    (tmp_path / "a.tex").write_text(r"\documentclass{article}")
    sub = tmp_path / "subdir"
    sub.mkdir()
    (sub / "b.tex").write_text(r"\documentclass{article}")
    # Non-tex file should be ignored
    (tmp_path / "readme.md").write_text("# Hello")

    result = find_tex_files(tmp_path)
    assert len(result) == 2
    names = {p.name for p in result}
    assert names == {"a.tex", "b.tex"}


def test_find_tex_files_no_tex_files(tmp_path):
    """Test that an empty list is returned when no .tex files exist."""
    (tmp_path / "readme.md").write_text("# Hello")
    result = find_tex_files(tmp_path)
    assert result == []


def test_find_tex_files_non_tex_file(tmp_path):
    """Test that a non-.tex file path returns empty list."""
    md_file = tmp_path / "paper.md"
    md_file.write_text("# Paper")
    result = find_tex_files(md_file)
    assert result == []


def test_find_tex_files_nonexistent_path(tmp_path):
    """Test that a nonexistent path returns empty list."""
    result = find_tex_files(tmp_path / "does_not_exist")
    assert result == []


# ---------------------------------------------------------------------------
# run_command
# ---------------------------------------------------------------------------


def test_run_command_dry_run():
    """Test that dry_run mode returns True without executing."""
    result = run_command(["echo", "hello"], dry_run=True)
    assert result is True


def test_run_command_success():
    """Test running a simple successful command."""
    result = run_command(["echo", "hello"], capture=True)
    assert result is True


def test_run_command_failure():
    """Test running a command that returns non-zero exit code."""
    result = run_command(["false"], capture=True)
    assert result is False


def test_run_command_nonexistent_binary():
    """Test running a command that does not exist returns False."""
    result = run_command(["nonexistent_command_xyz123"], capture=True)
    assert result is False


# ---------------------------------------------------------------------------
# generate_html
# ---------------------------------------------------------------------------


@patch("mf.papers.processor.run_command")
def test_generate_html_calls_tex2any(mock_run):
    """Test that generate_html invokes tex2any with correct args."""
    mock_run.return_value = True
    tex_file = Path("/tmp/claude/paper.tex")
    output_dir = Path("/tmp/claude/html_out")

    result = generate_html(tex_file, output_dir)

    assert result is True
    mock_run.assert_called_once()
    cmd = mock_run.call_args[0][0]
    assert cmd[0] == "tex2any"
    assert str(tex_file) in cmd
    assert str(output_dir) in cmd


@patch("mf.papers.processor.run_command")
def test_generate_html_dry_run(mock_run):
    """Test that generate_html passes dry_run to run_command."""
    mock_run.return_value = True
    tex_file = Path("/tmp/claude/paper.tex")
    output_dir = Path("/tmp/claude/html_out")

    generate_html(tex_file, output_dir, dry_run=True)

    _, kwargs = mock_run.call_args
    assert kwargs.get("dry_run") is True


# ---------------------------------------------------------------------------
# generate_pdf
# ---------------------------------------------------------------------------


@patch("mf.papers.processor.run_command")
def test_generate_pdf_dry_run(mock_run, tmp_path):
    """Test PDF generation in dry_run mode returns expected path."""
    mock_run.return_value = True
    tex_file = tmp_path / "paper.tex"
    tex_file.write_text(r"\documentclass{article}")
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    result = generate_pdf(tex_file, output_dir, dry_run=True)

    assert result is not None
    assert result == output_dir / "paper.pdf"
    # Should have called pdflatex 5 times (3+2) plus bibtex
    assert mock_run.call_count >= 5


@patch("mf.papers.processor.run_command")
def test_generate_pdf_success(mock_run, tmp_path):
    """Test PDF generation when pdflatex creates the PDF file."""
    mock_run.return_value = True
    tex_file = tmp_path / "paper.tex"
    tex_file.write_text(r"\documentclass{article}")

    # Create the PDF that pdflatex would produce
    pdf_in_texdir = tmp_path / "paper.pdf"
    pdf_in_texdir.write_text("fake pdf content")

    # Also create .aux file so bibtex step runs
    aux_file = tmp_path / "paper.aux"
    aux_file.write_text("fake aux")

    output_dir = tmp_path / "output"
    output_dir.mkdir()

    result = generate_pdf(tex_file, output_dir)

    assert result is not None
    assert result == output_dir / "paper.pdf"
    assert (output_dir / "paper.pdf").exists()


@patch("mf.papers.processor.run_command")
def test_generate_pdf_no_pdf_created(mock_run, tmp_path):
    """Test PDF generation returns None when pdflatex fails to create PDF."""
    mock_run.return_value = True
    tex_file = tmp_path / "paper.tex"
    tex_file.write_text(r"\documentclass{article}")

    output_dir = tmp_path / "output"
    output_dir.mkdir()

    # No PDF file is created by pdflatex -> should return None
    result = generate_pdf(tex_file, output_dir)
    assert result is None


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
