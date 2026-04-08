"""Tests for mf.publications.generate module."""

from __future__ import annotations

import pytest
import yaml

from mf.publications.database import PubEntry, PubsDatabase
from mf.publications.generate import (
    generate_publication_content,
    generate_publications,
    pub_to_frontmatter,
)


# ---------------------------------------------------------------------------
# pub_to_frontmatter tests
# ---------------------------------------------------------------------------


def _make_entry(**kwargs) -> PubEntry:
    """Create a minimal valid PubEntry, merging kwargs over defaults."""
    defaults = {
        "title": "Test Paper",
        "status": "published",
        "type": "conference paper",
    }
    defaults.update(kwargs)
    return PubEntry.from_dict(defaults.pop("slug", "test-slug"), defaults)


def test_pub_to_frontmatter_title():
    """Title is always included in frontmatter."""
    entry = _make_entry(title="My Great Paper")
    fm = pub_to_frontmatter(entry)
    assert fm["title"] == "My Great Paper"


def test_pub_to_frontmatter_abstract():
    """Abstract is included when present."""
    entry = _make_entry(abstract="A compelling abstract.")
    fm = pub_to_frontmatter(entry)
    assert fm["abstract"] == "A compelling abstract."


def test_pub_to_frontmatter_no_abstract():
    """Abstract key is absent when not set."""
    entry = _make_entry()
    fm = pub_to_frontmatter(entry)
    assert "abstract" not in fm


def test_pub_to_frontmatter_date_formatted():
    """Date is suffixed with T00:00:00Z in Hugo format."""
    entry = _make_entry(date="2024-06-15")
    fm = pub_to_frontmatter(entry)
    assert fm["date"] == "2024-06-15T00:00:00Z"


def test_pub_to_frontmatter_no_date():
    """Date key absent when entry has no date."""
    entry = _make_entry(date="")
    fm = pub_to_frontmatter(entry)
    assert "date" not in fm


def test_pub_to_frontmatter_authors():
    """Authors list is propagated."""
    entry = _make_entry(authors=[{"name": "Alice"}, {"name": "Bob"}])
    fm = pub_to_frontmatter(entry)
    assert fm["authors"] == [{"name": "Alice"}, {"name": "Bob"}]


def test_pub_to_frontmatter_tags():
    """Tags list is propagated."""
    entry = _make_entry(tags=["math", "statistics"])
    fm = pub_to_frontmatter(entry)
    assert fm["tags"] == ["math", "statistics"]


def test_pub_to_frontmatter_publication_block():
    """publication sub-dict contains type and status."""
    entry = _make_entry(
        type="conference paper",
        status="published",
        venue="NeurIPS 2024",
        doi="10.1234/test",
    )
    fm = pub_to_frontmatter(entry)
    assert "publication" in fm
    pub = fm["publication"]
    assert pub["type"] == "conference paper"
    assert pub["status"] == "published"
    assert pub["venue"] == "NeurIPS 2024"
    assert pub["doi"] == "10.1234/test"


def test_pub_to_frontmatter_year_derived_from_date():
    """Year inside publication block is derived from date."""
    entry = _make_entry(date="2024-03-10")
    fm = pub_to_frontmatter(entry)
    assert fm["publication"]["year"] == 2024


def test_pub_to_frontmatter_arxiv_id():
    """arxiv_id is mapped to publication.arxiv."""
    entry = _make_entry(arxiv_id="2401.12345")
    fm = pub_to_frontmatter(entry)
    assert fm["publication"]["arxiv"] == "2401.12345"


def test_pub_to_frontmatter_artifacts():
    """Non-empty artifacts are included."""
    entry = _make_entry(
        artifacts={"pdf": "/latex/test/paper.pdf", "bibtex": None}
    )
    fm = pub_to_frontmatter(entry)
    assert "artifacts" in fm
    # Only non-None values
    assert fm["artifacts"]["pdf"] == "/latex/test/paper.pdf"
    assert "bibtex" not in fm["artifacts"]


def test_pub_to_frontmatter_no_artifacts():
    """artifacts key absent when all artifact values are empty/None."""
    entry = _make_entry(artifacts={})
    fm = pub_to_frontmatter(entry)
    assert "artifacts" not in fm


def test_pub_to_frontmatter_links():
    """Links list is propagated."""
    links = [{"name": "GitHub", "url": "https://github.com/x"}]
    entry = _make_entry(links=links)
    fm = pub_to_frontmatter(entry)
    assert fm["links"] == links


# ---------------------------------------------------------------------------
# generate_publication_content tests
# ---------------------------------------------------------------------------


def test_generate_publication_content_format():
    """Generated content has proper YAML frontmatter delimiters."""
    fm = {"title": "Test", "tags": ["a", "b"]}
    content = generate_publication_content(fm)

    assert content.startswith("---\n")
    assert content.endswith("---\n")

    # Parse the YAML to verify it's valid
    yaml_part = content[4:-4]  # strip leading/trailing ---\n
    parsed = yaml.safe_load(yaml_part)
    assert parsed["title"] == "Test"
    assert parsed["tags"] == ["a", "b"]


def test_generate_publication_content_round_trips():
    """YAML in generated content can be round-tripped."""
    fm = {
        "title": "Unicode: café & résumé",
        "date": "2024-01-01T00:00:00Z",
        "publication": {"type": "journal article", "status": "published"},
    }
    content = generate_publication_content(fm)
    yaml_part = content[4:-4]
    parsed = yaml.safe_load(yaml_part)
    assert parsed["title"] == fm["title"]
    assert parsed["publication"]["type"] == "journal article"


# ---------------------------------------------------------------------------
# generate_publications integration tests
# ---------------------------------------------------------------------------


def _seed_pubs_db(mf_dir, entries: dict) -> None:
    """Write a minimal pubs_db.json file with the given slug -> data entries."""
    import json

    data = {"_schema_version": 1}
    data.update(entries)
    (mf_dir / "pubs_db.json").write_text(json.dumps(data, indent=2))


def test_generate_publications_creates_file(mock_site_root):
    """generate_publications creates index.md for each entry."""
    mf_dir = mock_site_root / ".mf"
    _seed_pubs_db(
        mf_dir,
        {
            "pub-paper": {
                "title": "Published Paper",
                "status": "published",
                "type": "conference paper",
                "date": "2024-01-15",
                "venue": "IEEE Conference",
            }
        },
    )

    generate_publications(force=True)

    pub_path = mock_site_root / "content" / "publications" / "pub-paper" / "index.md"
    assert pub_path.exists()
    content = pub_path.read_text()
    assert "Published Paper" in content


def test_generate_publications_dry_run_no_file(mock_site_root):
    """Dry run does not create files."""
    mf_dir = mock_site_root / ".mf"
    _seed_pubs_db(
        mf_dir,
        {
            "pub-paper": {
                "title": "Published Paper",
                "status": "published",
                "type": "conference paper",
            }
        },
    )

    generate_publications(dry_run=True)

    pub_path = mock_site_root / "content" / "publications" / "pub-paper" / "index.md"
    assert not pub_path.exists()


def test_generate_publications_specific_slug(mock_site_root):
    """Passing slug= generates only that publication."""
    mf_dir = mock_site_root / ".mf"
    _seed_pubs_db(
        mf_dir,
        {
            "pub-one": {
                "title": "Published One",
                "status": "published",
                "type": "conference paper",
            },
            "pub-two": {
                "title": "Published Two",
                "status": "published",
                "type": "conference paper",
            },
        },
    )

    generate_publications(slug="pub-one", force=True)

    root = mock_site_root
    assert (root / "content" / "publications" / "pub-one" / "index.md").exists()
    assert not (root / "content" / "publications" / "pub-two" / "index.md").exists()


def test_generate_publications_unknown_slug(mock_site_root, capsys):
    """Passing an unknown slug= does not crash and generates nothing."""
    mf_dir = mock_site_root / ".mf"
    _seed_pubs_db(mf_dir, {})

    generate_publications(slug="does-not-exist", force=True)

    pub_dir = mock_site_root / "content" / "publications"
    assert not list(pub_dir.iterdir())


def test_generate_publications_multiple_entries(mock_site_root):
    """All entries in pubs_db are generated when no slug filter given."""
    mf_dir = mock_site_root / ".mf"
    _seed_pubs_db(
        mf_dir,
        {
            "paper-a": {
                "title": "Paper A",
                "status": "draft",
                "type": "technical report",
            },
            "paper-b": {
                "title": "Paper B",
                "status": "preprint",
                "type": "preprint",
            },
        },
    )

    generate_publications(force=True)

    root = mock_site_root
    assert (root / "content" / "publications" / "paper-a" / "index.md").exists()
    assert (root / "content" / "publications" / "paper-b" / "index.md").exists()
