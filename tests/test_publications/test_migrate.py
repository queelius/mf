"""Tests for the paper_db -> pubs_db migration."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from mf.publications.migrate import SLUG_MAPPINGS, migrate_paper_db


# ──────────────────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────────────────


def _write_paper_db(tmp_path: Path, entries: dict) -> Path:
    """Write a minimal paper_db.json to *tmp_path* and return its path."""
    db_path = tmp_path / "paper_db.json"
    db_path.write_text(json.dumps(entries), encoding="utf-8")
    return db_path


def _pubs_db_path(tmp_path: Path) -> Path:
    return tmp_path / "pubs_db.json"


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────


def _load_entry(pubs_db_path: Path, slug: str) -> dict:
    data = json.loads(pubs_db_path.read_text(encoding="utf-8"))
    assert slug in data, f"slug {slug!r} not found in pubs_db; keys: {list(data)}"
    return data[slug]


# ──────────────────────────────────────────────────────────────────────────────
# Tests
# ──────────────────────────────────────────────────────────────────────────────


class TestPublishedPaperWithVenue:
    """A paper with a venue is included as status=published with correct artifacts."""

    def test_included_as_published(self, tmp_path):
        entries = {
            "my-conf-paper": {
                "title": "Great Paper",
                "date": "2025-06-01",
                "category": "conference paper",
                "venue": "NeurIPS 2025",
                "authors": [{"name": "Alex Towell", "email": "alex@example.com"}],
                "pdf_path": "/latex/my-conf-paper/paper.pdf",
                "cite_path": "/latex/my-conf-paper/cite.bib",
                "github_url": "https://github.com/queelius/my-conf-paper",
            }
        }
        paper_db = _write_paper_db(tmp_path, entries)
        pubs_db = _pubs_db_path(tmp_path)

        result = migrate_paper_db(paper_db, pubs_db)

        assert "my-conf-paper" in result["included"]
        entry = _load_entry(pubs_db, "my-conf-paper")
        assert entry["status"] == "published"

    def test_artifacts_mapped_correctly(self, tmp_path):
        entries = {
            "my-conf-paper": {
                "title": "Great Paper",
                "date": "2025-06-01",
                "category": "conference paper",
                "venue": "NeurIPS 2025",
                "pdf_path": "/latex/my-conf-paper/paper.pdf",
                "cite_path": "/latex/my-conf-paper/cite.bib",
                "github_url": "https://github.com/queelius/my-conf-paper",
            }
        }
        paper_db = _write_paper_db(tmp_path, entries)
        pubs_db = _pubs_db_path(tmp_path)
        migrate_paper_db(paper_db, pubs_db)

        entry = _load_entry(pubs_db, "my-conf-paper")
        assert entry["artifacts"]["pdf"] == "/latex/my-conf-paper/paper.pdf"
        assert entry["artifacts"]["bibtex"] == "/latex/my-conf-paper/cite.bib"
        assert entry["artifacts"]["code"] == "https://github.com/queelius/my-conf-paper"


class TestNovelIsSkipped:
    """Papers with category=novel (or essay/novella/short story) are skipped."""

    @pytest.mark.parametrize("category", ["novel", "essay", "novella", "short story"])
    def test_skip_category(self, tmp_path, category):
        entries = {
            "my-fiction": {
                "title": "My Novel",
                "date": "2025-01-01",
                "category": category,
                "pdf_path": "/latex/my-fiction/paper.pdf",
                "status": "published",
                "venue": "Self-published",
            }
        }
        paper_db = _write_paper_db(tmp_path, entries)
        pubs_db = _pubs_db_path(tmp_path)

        result = migrate_paper_db(paper_db, pubs_db)

        assert "my-fiction" in result["skipped"]
        assert "my-fiction" not in result["included"]
        data = json.loads(pubs_db.read_text(encoding="utf-8"))
        assert "my-fiction" not in data

    def test_novel_with_artifacts_still_skipped(self, tmp_path):
        """Category check must precede artifact check — novel with pdf is skipped."""
        entries = {
            "my-novel": {
                "title": "The Novel",
                "date": "2025-01-01",
                "category": "novel",
                "pdf_path": "/latex/my-novel/novel.pdf",
                "html_path": "/latex/my-novel/index.html",
            }
        }
        paper_db = _write_paper_db(tmp_path, entries)
        pubs_db = _pubs_db_path(tmp_path)

        result = migrate_paper_db(paper_db, pubs_db)

        assert "my-novel" in result["skipped"]
        assert "my-novel" not in result["included"]


class TestSlugMapping:
    """Slug mapping is applied so the output entry uses the canonical slug."""

    def test_cognitive_mri_slug_remapped(self, tmp_path):
        entries = {
            "cognitive-mri-ai-conversations": {
                "title": "Cognitive MRI",
                "date": "2025-12-09",
                "category": "conference paper",
                "status": "published",
                "venue": "Complex Networks 2025",
            }
        }
        paper_db = _write_paper_db(tmp_path, entries)
        pubs_db = _pubs_db_path(tmp_path)

        result = migrate_paper_db(paper_db, pubs_db)

        # Source slug appears in included list
        assert "cognitive-mri-ai-conversations" in result["included"]
        # But the stored slug is the mapped one
        data = json.loads(pubs_db.read_text(encoding="utf-8"))
        assert "cognitive-mri" in data
        assert "cognitive-mri-ai-conversations" not in data

    @pytest.mark.parametrize("raw_slug,expected_slug", list(SLUG_MAPPINGS.items()))
    def test_all_slug_mappings_applied(self, tmp_path, raw_slug, expected_slug):
        entries = {
            raw_slug: {
                "title": f"Paper for {raw_slug}",
                "date": "2024-01-01",
                "category": "research paper",
                "status": "published",
                "venue": "Some Conference",
            }
        }
        paper_db = _write_paper_db(tmp_path, entries)
        pubs_db = _pubs_db_path(tmp_path)
        migrate_paper_db(paper_db, pubs_db)

        data = json.loads(pubs_db.read_text(encoding="utf-8"))
        assert expected_slug in data, f"Expected mapped slug {expected_slug!r}"
        assert raw_slug not in data, f"Raw slug {raw_slug!r} should not appear"


class TestTimeline:
    """Each migrated entry has a 'migrated' timeline event seeded."""

    def test_timeline_has_migrated_event(self, tmp_path):
        entries = {
            "my-paper": {
                "title": "My Paper",
                "date": "2025-03-15",
                "category": "technical report",
                "pdf_path": "/latex/my-paper/paper.pdf",
            }
        }
        paper_db = _write_paper_db(tmp_path, entries)
        pubs_db = _pubs_db_path(tmp_path)
        migrate_paper_db(paper_db, pubs_db)

        entry = _load_entry(pubs_db, "my-paper")
        assert "timeline" in entry
        events = entry["timeline"]
        assert len(events) == 1
        ev = events[0]
        assert ev["event"] == "migrated"
        assert ev["note"] == "Migrated from paper_db"
        assert ev["date"] == "2025-03-15"


class TestAuthorsNormalization:
    """Bare string authors are wrapped as {"name": str}."""

    def test_string_author_wrapped(self, tmp_path):
        entries = {
            "my-paper": {
                "title": "My Paper",
                "date": "2025-01-01",
                "category": "conference paper",
                "venue": "ICML 2025",
                "authors": ["Alice Smith", "Bob Jones"],
            }
        }
        paper_db = _write_paper_db(tmp_path, entries)
        pubs_db = _pubs_db_path(tmp_path)
        migrate_paper_db(paper_db, pubs_db)

        entry = _load_entry(pubs_db, "my-paper")
        assert entry["authors"] == [{"name": "Alice Smith"}, {"name": "Bob Jones"}]

    def test_dict_author_preserved(self, tmp_path):
        entries = {
            "my-paper": {
                "title": "My Paper",
                "date": "2025-01-01",
                "category": "conference paper",
                "venue": "ICML 2025",
                "authors": [{"name": "Alice Smith", "email": "alice@example.com"}],
            }
        }
        paper_db = _write_paper_db(tmp_path, entries)
        pubs_db = _pubs_db_path(tmp_path)
        migrate_paper_db(paper_db, pubs_db)

        entry = _load_entry(pubs_db, "my-paper")
        assert entry["authors"][0]["email"] == "alice@example.com"

    def test_mixed_authors(self, tmp_path):
        """List can mix string and dict entries."""
        entries = {
            "my-paper": {
                "title": "My Paper",
                "date": "2025-01-01",
                "category": "conference paper",
                "venue": "ICLR",
                "authors": ["Alice Smith", {"name": "Bob Jones", "orcid": "0000-0000"}],
            }
        }
        paper_db = _write_paper_db(tmp_path, entries)
        pubs_db = _pubs_db_path(tmp_path)
        migrate_paper_db(paper_db, pubs_db)

        entry = _load_entry(pubs_db, "my-paper")
        assert entry["authors"][0] == {"name": "Alice Smith"}
        assert entry["authors"][1]["orcid"] == "0000-0000"


class TestSlidesFromLinks:
    """Slides URL is extracted from links[] into artifacts.slides."""

    @pytest.mark.parametrize("link_name", ["Slides", "Presentation", "Talk", "My Slides PDF"])
    def test_slides_extracted(self, tmp_path, link_name):
        entries = {
            "my-paper": {
                "title": "My Paper",
                "date": "2025-01-01",
                "category": "conference paper",
                "venue": "NeurIPS",
                "links": [
                    {"name": "GitHub", "url": "https://github.com/x"},
                    {"name": link_name, "url": "/latex/my-paper/slides.pdf"},
                ],
            }
        }
        paper_db = _write_paper_db(tmp_path, entries)
        pubs_db = _pubs_db_path(tmp_path)
        migrate_paper_db(paper_db, pubs_db)

        entry = _load_entry(pubs_db, "my-paper")
        assert entry.get("artifacts", {}).get("slides") == "/latex/my-paper/slides.pdf"

    def test_no_slides_link_no_slides_artifact(self, tmp_path):
        entries = {
            "my-paper": {
                "title": "My Paper",
                "date": "2025-01-01",
                "category": "conference paper",
                "venue": "NeurIPS",
                "links": [
                    {"name": "GitHub", "url": "https://github.com/x"},
                    {"name": "Paper", "url": "/papers/my-paper/"},
                ],
            }
        }
        paper_db = _write_paper_db(tmp_path, entries)
        pubs_db = _pubs_db_path(tmp_path)
        migrate_paper_db(paper_db, pubs_db)

        entry = _load_entry(pubs_db, "my-paper")
        assert "slides" not in entry.get("artifacts", {})


class TestInclusionCriteria:
    """Verify each inclusion rule works independently."""

    def test_published_status_included(self, tmp_path):
        entries = {
            "pub-paper": {
                "title": "Published",
                "date": "2024-01-01",
                "category": "research paper",
                "status": "published",
            }
        }
        paper_db = _write_paper_db(tmp_path, entries)
        pubs_db = _pubs_db_path(tmp_path)
        result = migrate_paper_db(paper_db, pubs_db)
        assert "pub-paper" in result["included"]
        assert _load_entry(pubs_db, "pub-paper")["status"] == "published"

    def test_arxiv_id_included_as_preprint(self, tmp_path):
        entries = {
            "arxiv-paper": {
                "title": "Arxiv Paper",
                "date": "2024-01-01",
                "category": "research paper",
                "arxiv_id": "2401.12345",
            }
        }
        paper_db = _write_paper_db(tmp_path, entries)
        pubs_db = _pubs_db_path(tmp_path)
        result = migrate_paper_db(paper_db, pubs_db)
        assert "arxiv-paper" in result["included"]
        assert _load_entry(pubs_db, "arxiv-paper")["status"] == "preprint"

    def test_pdf_only_included_as_draft(self, tmp_path):
        entries = {
            "draft-paper": {
                "title": "Draft Paper",
                "date": "2024-01-01",
                "category": "research paper",
                "pdf_path": "/latex/draft-paper/paper.pdf",
            }
        }
        paper_db = _write_paper_db(tmp_path, entries)
        pubs_db = _pubs_db_path(tmp_path)
        result = migrate_paper_db(paper_db, pubs_db)
        assert "draft-paper" in result["included"]
        assert _load_entry(pubs_db, "draft-paper")["status"] == "draft"

    def test_no_artifacts_skipped(self, tmp_path):
        entries = {
            "orphan-paper": {
                "title": "Orphan Paper",
                "date": "2024-01-01",
                "category": "research paper",
            }
        }
        paper_db = _write_paper_db(tmp_path, entries)
        pubs_db = _pubs_db_path(tmp_path)
        result = migrate_paper_db(paper_db, pubs_db)
        assert "orphan-paper" in result["skipped"]

    def test_non_arxiv_doi_included_as_published(self, tmp_path):
        entries = {
            "doi-paper": {
                "title": "DOI Paper",
                "date": "2024-01-01",
                "category": "conference paper",
                "doi": "10.1109/EXAMPLE.2024.001",
            }
        }
        paper_db = _write_paper_db(tmp_path, entries)
        pubs_db = _pubs_db_path(tmp_path)
        result = migrate_paper_db(paper_db, pubs_db)
        assert "doi-paper" in result["included"]
        assert _load_entry(pubs_db, "doi-paper")["status"] == "published"

    def test_special_keys_skipped(self, tmp_path):
        entries = {
            "_comment": "ignore me",
            "_example": {"title": "example"},
            "_schema_version": "2.0",
            "real-paper": {
                "title": "Real Paper",
                "date": "2024-01-01",
                "category": "conference paper",
                "venue": "ICML",
            },
        }
        paper_db = _write_paper_db(tmp_path, entries)
        pubs_db = _pubs_db_path(tmp_path)
        result = migrate_paper_db(paper_db, pubs_db)
        data = json.loads(pubs_db.read_text(encoding="utf-8"))
        for key in ("_comment", "_example"):
            assert key not in data
        assert "real-paper" in result["included"]


class TestSourceRepo:
    """source_path is stripped to repo-level path."""

    def test_strip_github_prefix(self, tmp_path):
        entries = {
            "my-paper": {
                "title": "My Paper",
                "date": "2024-01-01",
                "category": "technical report",
                "pdf_path": "/latex/my-paper/paper.pdf",
                "source_path": "/home/spinoza/github/beta/dreamlog/paper/dreamlog_paper.tex",
            }
        }
        paper_db = _write_paper_db(tmp_path, entries)
        pubs_db = _pubs_db_path(tmp_path)
        migrate_paper_db(paper_db, pubs_db)

        entry = _load_entry(pubs_db, "my-paper")
        assert entry.get("source_repo") == "beta/dreamlog"

    def test_no_source_path(self, tmp_path):
        entries = {
            "my-paper": {
                "title": "My Paper",
                "date": "2024-01-01",
                "category": "conference paper",
                "venue": "ICML",
            }
        }
        paper_db = _write_paper_db(tmp_path, entries)
        pubs_db = _pubs_db_path(tmp_path)
        migrate_paper_db(paper_db, pubs_db)

        entry = _load_entry(pubs_db, "my-paper")
        assert "source_repo" not in entry
