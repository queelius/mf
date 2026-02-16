"""Tests for mf.papers.generator module (Hugo content generation)."""

import json
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from mf.papers.generator import (
    find_pdf_file,
    find_html_file,
    format_file_size,
    extract_paper_metadata,
    generate_paper_content,
    generate_papers,
)
from mf.core.database import PaperDatabase, PaperEntry


# ---------------------------------------------------------------------------
# find_pdf_file / find_html_file
# ---------------------------------------------------------------------------


def test_find_pdf_file_exists(tmp_path):
    """Test finding a PDF file in a directory."""
    (tmp_path / "paper.pdf").write_bytes(b"%PDF-1.4 fake")
    result = find_pdf_file(tmp_path)
    assert result is not None
    assert result.name == "paper.pdf"


def test_find_pdf_file_none(tmp_path):
    """Test that None is returned when no PDF exists."""
    (tmp_path / "paper.html").write_text("<html></html>")
    result = find_pdf_file(tmp_path)
    assert result is None


def test_find_html_file_exists(tmp_path):
    """Test finding index.html in a directory."""
    (tmp_path / "index.html").write_text("<html>paper</html>")
    result = find_html_file(tmp_path)
    assert result is not None
    assert result.name == "index.html"


def test_find_html_file_none(tmp_path):
    """Test that None is returned when index.html does not exist."""
    (tmp_path / "other.html").write_text("<html></html>")
    result = find_html_file(tmp_path)
    assert result is None


# ---------------------------------------------------------------------------
# format_file_size
# ---------------------------------------------------------------------------


def test_format_file_size_bytes():
    """Test formatting small sizes in bytes."""
    assert format_file_size(500) == "500 B"


def test_format_file_size_kilobytes():
    """Test formatting kilobyte sizes."""
    assert format_file_size(2048) == "2.0 KB"


def test_format_file_size_megabytes():
    """Test formatting megabyte sizes."""
    assert format_file_size(1_500_000) == "1.4 MB"


def test_format_file_size_zero():
    """Test formatting zero bytes."""
    assert format_file_size(0) == "0 B"


# ---------------------------------------------------------------------------
# extract_paper_metadata
# ---------------------------------------------------------------------------


@patch("mf.papers.generator.extract_from_html")
@patch("mf.papers.generator.extract_from_pdf")
def test_extract_paper_metadata_html_only(mock_pdf, mock_html, tmp_path):
    """Test metadata extraction from HTML only (no PDF)."""
    paper_dir = tmp_path / "my-paper"
    paper_dir.mkdir()
    (paper_dir / "index.html").write_text("<html><title>My Paper</title></html>")

    from mf.papers.metadata import PaperMetadata
    mock_html.return_value = PaperMetadata(
        title="My Paper", authors=["Author One"], keywords=["test"]
    )
    mock_pdf.return_value = PaperMetadata()  # Empty, no PDF

    result = extract_paper_metadata("my-paper", paper_dir)

    assert result["title"] == "My Paper"
    assert result["authors"] == ["Author One"]
    assert result["tags"] == ["test"]
    mock_html.assert_called_once()


@patch("mf.papers.generator.extract_from_html")
@patch("mf.papers.generator.extract_from_pdf")
def test_extract_paper_metadata_pdf_overrides(mock_pdf, mock_html, tmp_path):
    """Test that PDF page count and file size override HTML metadata."""
    paper_dir = tmp_path / "my-paper"
    paper_dir.mkdir()
    (paper_dir / "index.html").write_text("<html></html>")
    pdf_file = paper_dir / "paper.pdf"
    pdf_file.write_bytes(b"%PDF fake content for testing")

    from mf.papers.metadata import PaperMetadata
    mock_html.return_value = PaperMetadata(title="HTML Title")
    mock_pdf.return_value = PaperMetadata(
        page_count=42, file_size_mb=1.5, title="PDF Title"
    )

    result = extract_paper_metadata("my-paper", paper_dir)

    # HTML title takes precedence over PDF title
    assert result["title"] == "HTML Title"
    # PDF page count and size should be present
    assert result["page_count"] == 42
    assert result["file_size_mb"] == 1.5


@patch("mf.papers.generator.extract_from_html")
@patch("mf.papers.generator.extract_from_pdf")
def test_extract_paper_metadata_pdf_title_fallback(mock_pdf, mock_html, tmp_path):
    """Test that PDF title is used when HTML title is absent."""
    paper_dir = tmp_path / "my-paper"
    paper_dir.mkdir()
    (paper_dir / "index.html").write_text("<html></html>")
    pdf_file = paper_dir / "paper.pdf"
    pdf_file.write_bytes(b"%PDF fake")

    from mf.papers.metadata import PaperMetadata
    mock_html.return_value = PaperMetadata()  # No title
    mock_pdf.return_value = PaperMetadata(title="PDF Title")

    result = extract_paper_metadata("my-paper", paper_dir)

    assert result.get("title") == "PDF Title"


# ---------------------------------------------------------------------------
# generate_paper_content
# ---------------------------------------------------------------------------


def test_generate_paper_content_no_paper_dir(mock_site_root):
    """Test that content generation fails when paper dir does not exist."""
    db = PaperDatabase(mock_site_root / ".mf" / "paper_db.json")
    db.load()
    db.set("nonexistent", {"title": "Nonexistent Paper"})

    result = generate_paper_content("nonexistent", db)
    assert result is False


def test_generate_paper_content_no_files(mock_site_root):
    """Test that generation fails with neither HTML nor PDF."""
    paper_dir = mock_site_root / "static" / "latex" / "empty-paper"
    paper_dir.mkdir(parents=True)

    db = PaperDatabase(mock_site_root / ".mf" / "paper_db.json")
    db.load()
    db.set("empty-paper", {"title": "Empty Paper"})

    result = generate_paper_content("empty-paper", db)
    assert result is False


@patch("mf.papers.generator.extract_paper_metadata")
def test_generate_paper_content_with_html_and_pdf(mock_extract, mock_site_root):
    """Test successful content generation with both HTML and PDF present."""
    slug = "full-paper"
    paper_dir = mock_site_root / "static" / "latex" / slug
    paper_dir.mkdir(parents=True)
    (paper_dir / "index.html").write_text("<html>paper content</html>")
    pdf_file = paper_dir / "paper.pdf"
    pdf_file.write_bytes(b"%PDF-1.4 fake pdf content for size calc")

    mock_extract.return_value = {
        "title": "Full Paper Title",
        "date": "2024-06-15",
        "authors": ["Author A"],
        "tags": ["test"],
    }

    db = PaperDatabase(mock_site_root / ".mf" / "paper_db.json")
    db.load()
    db.set(slug, {"title": "Full Paper Title", "category": "research paper"})

    result = generate_paper_content(slug, db)

    assert result is True
    content_file = mock_site_root / "content" / "papers" / slug / "index.md"
    assert content_file.exists()
    content = content_file.read_text()
    assert "Full Paper Title" in content
    assert "pdf_only: false" in content


@patch("mf.papers.generator.extract_paper_metadata")
def test_generate_paper_content_pdf_only(mock_extract, mock_site_root):
    """Test content generation with PDF only (no HTML)."""
    slug = "pdf-paper"
    paper_dir = mock_site_root / "static" / "latex" / slug
    paper_dir.mkdir(parents=True)
    pdf_file = paper_dir / "paper.pdf"
    pdf_file.write_bytes(b"%PDF-1.4 fake pdf")

    mock_extract.return_value = {
        "title": "PDF Only Paper",
        "date": "2024-01-01",
    }

    db = PaperDatabase(mock_site_root / ".mf" / "paper_db.json")
    db.load()
    db.set(slug, {"title": "PDF Only Paper"})

    result = generate_paper_content(slug, db)

    assert result is True
    content_file = mock_site_root / "content" / "papers" / slug / "index.md"
    assert content_file.exists()
    content = content_file.read_text()
    assert "pdf_only: true" in content


@patch("mf.papers.generator.extract_paper_metadata")
def test_generate_paper_content_dry_run(mock_extract, mock_site_root):
    """Test that dry_run does not write files."""
    slug = "dry-run-paper"
    paper_dir = mock_site_root / "static" / "latex" / slug
    paper_dir.mkdir(parents=True)
    (paper_dir / "index.html").write_text("<html></html>")
    (paper_dir / "paper.pdf").write_bytes(b"%PDF fake")

    mock_extract.return_value = {"title": "Dry Run", "date": "2024-01-01"}

    db = PaperDatabase(mock_site_root / ".mf" / "paper_db.json")
    db.load()
    db.set(slug, {"title": "Dry Run"})

    result = generate_paper_content(slug, db, dry_run=True)

    assert result is True
    content_file = mock_site_root / "content" / "papers" / slug / "index.md"
    assert not content_file.exists()


@patch("mf.papers.generator.extract_paper_metadata")
def test_generate_paper_content_manual_overrides(mock_extract, mock_site_root):
    """Test that manual database overrides take precedence over extracted metadata."""
    slug = "override-paper"
    paper_dir = mock_site_root / "static" / "latex" / slug
    paper_dir.mkdir(parents=True)
    (paper_dir / "index.html").write_text("<html></html>")
    (paper_dir / "paper.pdf").write_bytes(b"%PDF fake")

    mock_extract.return_value = {
        "title": "Extracted Title",
        "date": "2024-01-01",
    }

    db = PaperDatabase(mock_site_root / ".mf" / "paper_db.json")
    db.load()
    db.set(slug, {"title": "Manual Override Title", "stars": 5})

    result = generate_paper_content(slug, db)

    assert result is True
    content_file = mock_site_root / "content" / "papers" / slug / "index.md"
    content = content_file.read_text()
    # Manual title should win
    assert "Manual Override Title" in content
    assert "stars: 5" in content


@patch("mf.papers.generator.extract_paper_metadata")
def test_generate_paper_content_default_title(mock_extract, mock_site_root):
    """Test that slug-derived title is used when no title is available."""
    slug = "untitled-paper"
    paper_dir = mock_site_root / "static" / "latex" / slug
    paper_dir.mkdir(parents=True)
    (paper_dir / "index.html").write_text("<html></html>")
    (paper_dir / "paper.pdf").write_bytes(b"%PDF fake")

    mock_extract.return_value = {"date": "2024-01-01"}

    db = PaperDatabase(mock_site_root / ".mf" / "paper_db.json")
    db.load()
    db.set(slug, {})

    result = generate_paper_content(slug, db)

    assert result is True
    content_file = mock_site_root / "content" / "papers" / slug / "index.md"
    content = content_file.read_text()
    # Should fall back to slug-derived title
    assert "Untitled Paper" in content


# ---------------------------------------------------------------------------
# generate_papers (batch)
# ---------------------------------------------------------------------------


@patch("mf.papers.generator.generate_paper_content")
def test_generate_papers_all(mock_gen, mock_site_root):
    """Test generating content for all papers in static/latex/."""
    # Create two paper directories
    for slug in ["paper-a", "paper-b"]:
        d = mock_site_root / "static" / "latex" / slug
        d.mkdir(parents=True)

    mock_gen.return_value = True

    db_path = mock_site_root / ".mf" / "paper_db.json"
    db_path.write_text(json.dumps({
        "_comment": "test",
        "_schema_version": "2.0",
    }))

    generate_papers()

    assert mock_gen.call_count == 2


@patch("mf.papers.generator.generate_paper_content")
def test_generate_papers_single_slug(mock_gen, mock_site_root):
    """Test generating content for a single paper by slug."""
    mock_gen.return_value = True

    db_path = mock_site_root / ".mf" / "paper_db.json"
    db_path.write_text(json.dumps({
        "_comment": "test",
        "_schema_version": "2.0",
    }))

    generate_papers(slug="specific-paper")

    mock_gen.assert_called_once()
    call_args = mock_gen.call_args
    assert call_args[0][0] == "specific-paper"
