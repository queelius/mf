"""Tests for mf.publications.generate module."""

import json

import pytest
import yaml

from mf.core.database import PaperEntry
from mf.publications.generate import (
    generate_publication_content,
    generate_publications,
    get_publication_slug,
    is_publication,
    map_paper_to_publication,
)


# ---------------------------------------------------------------------------
# is_publication tests
# ---------------------------------------------------------------------------


def test_is_publication_with_published_status():
    """Paper with status='published' qualifies as publication."""
    entry = PaperEntry(slug="test", data={"status": "published"})
    assert is_publication(entry) is True


def test_is_publication_with_venue():
    """Paper with a venue qualifies as publication."""
    entry = PaperEntry(slug="test", data={"venue": "IEEE Conference"})
    assert is_publication(entry) is True


def test_is_publication_with_non_arxiv_doi():
    """Paper with non-arxiv DOI qualifies as publication."""
    entry = PaperEntry(slug="test", data={"doi": "10.1234/example"})
    assert is_publication(entry) is True


def test_is_publication_arxiv_doi_excluded():
    """Paper with arxiv DOI does not qualify as publication."""
    entry = PaperEntry(slug="test", data={"doi": "10.48550/arXiv.2401.12345"})
    assert is_publication(entry) is False


def test_is_publication_no_qualifying_fields():
    """Paper without venue, status, or DOI does not qualify."""
    entry = PaperEntry(slug="test", data={"title": "Draft Paper"})
    assert is_publication(entry) is False


def test_is_publication_draft_status():
    """Paper with status='draft' does not qualify."""
    entry = PaperEntry(slug="test", data={"status": "draft"})
    assert is_publication(entry) is False


# ---------------------------------------------------------------------------
# map_paper_to_publication tests
# ---------------------------------------------------------------------------


def test_map_paper_basic_fields():
    """Test mapping of basic fields (title, abstract, date, tags)."""
    entry = PaperEntry(
        slug="test-paper",
        data={
            "title": "My Paper",
            "abstract": "A long abstract.",
            "date": "2024-06-15",
            "tags": ["math", "statistics"],
        },
    )
    fm = map_paper_to_publication(entry)

    assert fm["title"] == "My Paper"
    assert fm["abstract"] == "A long abstract."
    assert fm["date"] == "2024-06-15T00:00:00Z"
    assert fm["tags"] == ["math", "statistics"]


def test_map_paper_authors_as_strings():
    """Test mapping authors provided as plain strings."""
    entry = PaperEntry(
        slug="test",
        data={"title": "P", "authors": ["Alice", "Bob"]},
    )
    fm = map_paper_to_publication(entry)

    assert fm["authors"] == [{"name": "Alice"}, {"name": "Bob"}]


def test_map_paper_authors_as_dicts():
    """Test mapping authors already in dict format."""
    author_dict = {"name": "Alice", "email": "alice@example.com"}
    entry = PaperEntry(
        slug="test",
        data={"title": "P", "authors": [author_dict]},
    )
    fm = map_paper_to_publication(entry)

    assert fm["authors"] == [author_dict]


def test_map_paper_publication_metadata():
    """Test publication metadata mapping (venue, status, doi, year, category)."""
    entry = PaperEntry(
        slug="test",
        data={
            "title": "P",
            "category": "conference paper",
            "venue": "IEEE CCTS",
            "status": "published",
            "doi": "10.1234/test",
            "year": 2024,
        },
    )
    fm = map_paper_to_publication(entry)

    assert "publication" in fm
    pub = fm["publication"]
    assert pub["type"] == "conference paper"
    assert pub["venue"] == "IEEE CCTS"
    assert pub["status"] == "published"
    assert pub["doi"] == "10.1234/test"
    assert pub["year"] == 2024


def test_map_paper_links():
    """Test link generation including github, external, and paper page link."""
    entry = PaperEntry(
        slug="my-paper",
        data={
            "title": "P",
            "github_url": "https://github.com/user/repo",
            "external_url": "https://example.com",
        },
    )
    fm = map_paper_to_publication(entry)

    names = [link["name"] for link in fm["links"]]
    assert "GitHub" in names
    assert "External" in names
    assert "Paper" in names
    paper_link = next(l for l in fm["links"] if l["name"] == "Paper")
    assert paper_link["url"] == "/papers/my-paper/"


def test_map_paper_static_paths():
    """Test mapping of pdf_path, html_path, cite_path."""
    entry = PaperEntry(
        slug="test",
        data={
            "title": "P",
            "pdf_path": "/latex/test/paper.pdf",
            "html_path": "/latex/test/index.html",
            "cite_path": "/latex/test/cite.bib",
        },
    )
    fm = map_paper_to_publication(entry)

    assert fm["pdf"] == "/latex/test/paper.pdf"
    assert fm["html"] == "/latex/test/"  # index.html stripped
    assert fm["cite"] == "/latex/test/cite.bib"


# ---------------------------------------------------------------------------
# generate_publication_content tests
# ---------------------------------------------------------------------------


def test_generate_publication_content_format():
    """Test that generated content has proper YAML frontmatter delimiters."""
    fm = {"title": "Test", "tags": ["a", "b"]}
    content = generate_publication_content(fm)

    assert content.startswith("---\n")
    assert content.endswith("---\n")

    # Parse the YAML to verify it's valid
    yaml_part = content[4:-4]  # strip leading/trailing ---\n
    parsed = yaml.safe_load(yaml_part)
    assert parsed["title"] == "Test"
    assert parsed["tags"] == ["a", "b"]


# ---------------------------------------------------------------------------
# get_publication_slug tests
# ---------------------------------------------------------------------------


def test_get_publication_slug_mapped():
    """Test known slug mapping."""
    entry = PaperEntry(slug="reliability-estimation-in-series-systems", data={})
    assert get_publication_slug(entry) == "math-proj"


def test_get_publication_slug_unmapped():
    """Test that unmapped slugs return themselves."""
    entry = PaperEntry(slug="some-unknown-paper", data={})
    assert get_publication_slug(entry) == "some-unknown-paper"


# ---------------------------------------------------------------------------
# generate_publications integration tests
# ---------------------------------------------------------------------------


def test_generate_publications_creates_files(mock_site_root):
    """Test that generate_publications creates publication files."""
    root = mock_site_root
    mf_dir = root / ".mf"

    paper_db = {
        "_comment": "Test papers",
        "_schema_version": "2.0",
        "pub-paper": {
            "title": "Published Paper",
            "status": "published",
            "venue": "IEEE Conference",
            "date": "2024-01-15",
        },
    }
    (mf_dir / "paper_db.json").write_text(json.dumps(paper_db, indent=2))

    generate_publications(force=True)

    pub_path = root / "content" / "publications" / "pub-paper" / "index.md"
    assert pub_path.exists()
    content = pub_path.read_text()
    assert "Published Paper" in content


def test_generate_publications_skips_non_publications(mock_site_root):
    """Test that non-qualifying papers are skipped."""
    root = mock_site_root
    mf_dir = root / ".mf"

    paper_db = {
        "_comment": "Test papers",
        "_schema_version": "2.0",
        "draft-paper": {
            "title": "Draft Paper",
            "status": "draft",
        },
    }
    (mf_dir / "paper_db.json").write_text(json.dumps(paper_db, indent=2))

    generate_publications(force=True)

    pub_path = root / "content" / "publications" / "draft-paper" / "index.md"
    assert not pub_path.exists()


def test_generate_publications_dry_run(mock_site_root):
    """Test that dry run does not create files."""
    root = mock_site_root
    mf_dir = root / ".mf"

    paper_db = {
        "_comment": "Test papers",
        "_schema_version": "2.0",
        "pub-paper": {
            "title": "Published Paper",
            "status": "published",
        },
    }
    (mf_dir / "paper_db.json").write_text(json.dumps(paper_db, indent=2))

    generate_publications(dry_run=True)

    pub_path = root / "content" / "publications" / "pub-paper" / "index.md"
    assert not pub_path.exists()


def test_generate_publications_specific_slug(mock_site_root):
    """Test generating a specific publication by slug."""
    root = mock_site_root
    mf_dir = root / ".mf"

    paper_db = {
        "_comment": "Test papers",
        "_schema_version": "2.0",
        "pub-one": {
            "title": "Published One",
            "status": "published",
        },
        "pub-two": {
            "title": "Published Two",
            "status": "published",
        },
    }
    (mf_dir / "paper_db.json").write_text(json.dumps(paper_db, indent=2))

    generate_publications(slug="pub-one", force=True)

    assert (root / "content" / "publications" / "pub-one" / "index.md").exists()
    assert not (root / "content" / "publications" / "pub-two" / "index.md").exists()


def test_generate_publications_update_existing(mock_site_root):
    """Test that existing publication files are updated (not overwritten) without --force."""
    root = mock_site_root
    mf_dir = root / ".mf"

    # Create existing publication with custom body
    pub_dir = root / "content" / "publications" / "existing-pub"
    pub_dir.mkdir(parents=True)
    (pub_dir / "index.md").write_text(
        "---\ntitle: Old Title\ncustom_field: keep_me\n---\nCustom body\n"
    )

    paper_db = {
        "_comment": "Test papers",
        "_schema_version": "2.0",
        "existing-pub": {
            "title": "New Title",
            "status": "published",
            "pdf_path": "/latex/existing-pub/paper.pdf",
        },
    }
    (mf_dir / "paper_db.json").write_text(json.dumps(paper_db, indent=2))

    generate_publications()  # without force => update mode

    content = (pub_dir / "index.md").read_text()
    # The body should be preserved
    assert "Custom body" in content
    # pdf field should be updated
    assert "pdf" in content
