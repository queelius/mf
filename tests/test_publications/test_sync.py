"""Tests for mf.publications.sync module."""

import json

import pytest

from mf.publications.sync import (
    extract_frontmatter,
    extract_paper_slug_from_pdf_path,
    map_publication_to_paper,
    sync_publications,
)


# ---------------------------------------------------------------------------
# extract_frontmatter tests
# ---------------------------------------------------------------------------


def test_extract_frontmatter_basic():
    """Test extraction of simple YAML frontmatter."""
    content = "---\ntitle: My Paper\ndate: 2024-01-15\n---\nBody text.\n"
    fm = extract_frontmatter(content)

    assert fm["title"] == "My Paper"
    assert fm["date"] == "2024-01-15"


def test_extract_frontmatter_with_list():
    """Test extraction of YAML list values."""
    content = "---\ntitle: Paper\ntags:\n  - math\n  - stats\n---\n"
    fm = extract_frontmatter(content)

    assert fm["tags"] == ["math", "stats"]


def test_extract_frontmatter_inline_list():
    """Test extraction of inline list values."""
    content = '---\ntitle: Paper\ntags: [math, stats]\n---\n'
    fm = extract_frontmatter(content)

    assert fm["tags"] == ["math", "stats"]


def test_extract_frontmatter_no_frontmatter():
    """Test that content without frontmatter returns empty dict."""
    content = "No frontmatter here.\n"
    fm = extract_frontmatter(content)

    assert fm == {}


def test_extract_frontmatter_empty_string():
    """Test empty string returns empty dict."""
    fm = extract_frontmatter("")
    assert fm == {}


def test_extract_frontmatter_quoted_values():
    """Test that quoted values are handled (quotes stripped)."""
    content = '---\ntitle: "My Paper"\n---\n'
    fm = extract_frontmatter(content)

    assert fm["title"] == "My Paper"


# ---------------------------------------------------------------------------
# extract_paper_slug_from_pdf_path tests
# ---------------------------------------------------------------------------


def test_extract_slug_from_pdf_path_standard():
    """Test extracting slug from standard /latex/slug/file.pdf path."""
    slug = extract_paper_slug_from_pdf_path("/latex/my-paper/paper.pdf")
    assert slug == "my-paper"


def test_extract_slug_from_pdf_path_no_latex():
    """Test that paths without /latex/ return None."""
    slug = extract_paper_slug_from_pdf_path("/other/path/file.pdf")
    assert slug is None


def test_extract_slug_from_pdf_path_empty():
    """Test that empty string returns None."""
    slug = extract_paper_slug_from_pdf_path("")
    assert slug is None


def test_extract_slug_from_pdf_path_none():
    """Test that None returns None."""
    slug = extract_paper_slug_from_pdf_path(None)
    assert slug is None


# ---------------------------------------------------------------------------
# map_publication_to_paper tests
# ---------------------------------------------------------------------------


def test_map_publication_basic_fields():
    """Test mapping basic fields from publication frontmatter to paper format."""
    pub_data = {
        "title": "Published Paper",
        "abstract": "A great paper.",
        "date": "2024-01-15T00:00:00Z",
        "tags": ["math", "stats"],
    }
    paper = map_publication_to_paper(pub_data)

    assert paper["title"] == "Published Paper"
    assert paper["abstract"] == "A great paper."
    assert paper["date"] == "2024-01-15"  # Only date part
    assert paper["tags"] == ["math", "stats"]


def test_map_publication_authors_dicts():
    """Test mapping authors in dict format."""
    pub_data = {
        "authors": [{"name": "Alice"}, {"name": "Bob"}],
    }
    paper = map_publication_to_paper(pub_data)

    assert paper["authors"] == ["Alice", "Bob"]


def test_map_publication_authors_strings():
    """Test mapping authors as plain strings."""
    pub_data = {
        "authors": ["Alice", "Bob"],
    }
    paper = map_publication_to_paper(pub_data)

    assert paper["authors"] == ["Alice", "Bob"]


def test_map_publication_links_github():
    """Test that GitHub links are extracted."""
    pub_data = {
        "links": [
            {"name": "GitHub", "url": "https://github.com/user/repo"},
        ],
    }
    paper = map_publication_to_paper(pub_data)

    assert paper["github_url"] == "https://github.com/user/repo"


def test_map_publication_links_arxiv():
    """Test that arXiv links extract the ID."""
    pub_data = {
        "links": [
            {"name": "arXiv", "url": "https://arxiv.org/abs/2401.12345"},
        ],
    }
    paper = map_publication_to_paper(pub_data)

    assert paper["arxiv_id"] == "2401.12345"


def test_map_publication_pdf():
    """Test mapping of pdf field."""
    pub_data = {
        "pdf": "/latex/paper/paper.pdf",
    }
    paper = map_publication_to_paper(pub_data)

    assert paper["pdf_path"] == "/latex/paper/paper.pdf"


def test_map_publication_doi():
    """Test mapping of DOI field."""
    pub_data = {
        "doi": "10.1234/example",
    }
    paper = map_publication_to_paper(pub_data)

    assert paper["doi"] == "10.1234/example"


def test_map_publication_empty():
    """Test mapping of empty publication data."""
    paper = map_publication_to_paper({})
    assert paper == {}


# ---------------------------------------------------------------------------
# sync_publications integration tests
# ---------------------------------------------------------------------------


def test_sync_publications_no_directory(mock_site_root, capsys):
    """Test sync when publications directory has no files."""
    root = mock_site_root
    mf_dir = root / ".mf"

    # Create paper db
    paper_db = {
        "_comment": "Test papers",
        "_schema_version": "2.0",
    }
    (mf_dir / "paper_db.json").write_text(json.dumps(paper_db, indent=2))

    # publications directory exists but is empty
    sync_publications()
    # Should not raise, just report 0 found


def test_sync_publications_dry_run(mock_site_root):
    """Test that dry run does not modify database."""
    root = mock_site_root
    mf_dir = root / ".mf"

    # Create paper database
    paper_db = {
        "_comment": "Test papers",
        "_schema_version": "2.0",
    }
    (mf_dir / "paper_db.json").write_text(json.dumps(paper_db, indent=2))

    # Create a publication file with a corresponding latex directory
    pub_dir = root / "content" / "publications" / "test-pub"
    pub_dir.mkdir(parents=True)
    (pub_dir / "index.md").write_text(
        "---\ntitle: Test Publication\npdf: /latex/test-pub/paper.pdf\n---\n"
    )

    # Create the latex directory so sync doesn't skip
    latex_dir = root / "static" / "latex" / "test-pub"
    latex_dir.mkdir(parents=True)

    sync_publications(dry_run=True)

    # Database should not have been modified (still just metadata)
    db_content = json.loads((mf_dir / "paper_db.json").read_text())
    assert "test-pub" not in db_content
