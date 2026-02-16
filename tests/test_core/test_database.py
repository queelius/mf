"""Tests for mf.core.database module."""

import json
import pytest
from pathlib import Path

from mf.core.database import PaperDatabase, ProjectsDatabase, ProjectsCache, SeriesDatabase


class TestPaperDatabase:
    """Tests for PaperDatabase class."""

    def test_load_existing_database(self, sample_paper_db, monkeypatch):
        """Test loading an existing database."""
        monkeypatch.setenv("MF_SITE_ROOT", str(sample_paper_db.parent.parent))

        db = PaperDatabase(sample_paper_db)
        db.load()

        assert "test-paper" in db
        assert len(db) == 2

    def test_load_creates_default_if_missing(self, tmp_path, monkeypatch):
        """Test that loading creates default structure if file missing."""
        monkeypatch.setenv("MF_SITE_ROOT", str(tmp_path))
        db_path = tmp_path / "nonexistent.json"

        db = PaperDatabase(db_path)
        db.load()

        assert db._loaded
        assert "_comment" in db._data

    def test_get_paper_entry(self, sample_paper_db, monkeypatch):
        """Test getting a paper entry."""
        monkeypatch.setenv("MF_SITE_ROOT", str(sample_paper_db.parent.parent))

        db = PaperDatabase(sample_paper_db)
        db.load()

        entry = db.get("test-paper")

        assert entry is not None
        assert entry.title == "Test Paper"
        assert entry.slug == "test-paper"

    def test_get_returns_none_for_missing(self, sample_paper_db, monkeypatch):
        """Test that get returns None for missing paper."""
        monkeypatch.setenv("MF_SITE_ROOT", str(sample_paper_db.parent.parent))

        db = PaperDatabase(sample_paper_db)
        db.load()

        entry = db.get("nonexistent")

        assert entry is None

    def test_get_or_create_creates_new(self, sample_paper_db, monkeypatch):
        """Test get_or_create creates new entry."""
        monkeypatch.setenv("MF_SITE_ROOT", str(sample_paper_db.parent.parent))

        db = PaperDatabase(sample_paper_db)
        db.load()

        entry = db.get_or_create("new-paper")

        assert entry is not None
        assert entry.slug == "new-paper"
        assert "new-paper" in db

    def test_iteration(self, sample_paper_db, monkeypatch):
        """Test iterating over papers."""
        monkeypatch.setenv("MF_SITE_ROOT", str(sample_paper_db.parent.parent))

        db = PaperDatabase(sample_paper_db)
        db.load()

        slugs = list(db)

        assert "test-paper" in slugs
        assert "another-paper" in slugs
        assert "_comment" not in slugs
        assert "_example" not in slugs

    def test_search_by_query(self, sample_paper_db, monkeypatch):
        """Test searching by text query."""
        monkeypatch.setenv("MF_SITE_ROOT", str(sample_paper_db.parent.parent))

        db = PaperDatabase(sample_paper_db)
        db.load()

        results = db.search(query="test")

        assert len(results) == 1
        assert results[0].slug == "test-paper"

    def test_search_by_category(self, sample_paper_db, monkeypatch):
        """Test searching by category."""
        monkeypatch.setenv("MF_SITE_ROOT", str(sample_paper_db.parent.parent))

        db = PaperDatabase(sample_paper_db)
        db.load()

        results = db.search(category="white paper")

        assert len(results) == 1
        assert results[0].slug == "another-paper"

    def test_search_by_tags(self, sample_paper_db, monkeypatch):
        """Test searching by tags."""
        monkeypatch.setenv("MF_SITE_ROOT", str(sample_paper_db.parent.parent))

        db = PaperDatabase(sample_paper_db)
        db.load()

        results = db.search(tags=["test"])

        assert len(results) == 1
        assert results[0].slug == "test-paper"

    def test_list_categories(self, sample_paper_db, monkeypatch):
        """Test listing all categories."""
        monkeypatch.setenv("MF_SITE_ROOT", str(sample_paper_db.parent.parent))

        db = PaperDatabase(sample_paper_db)
        db.load()

        categories = db.list_categories()

        assert "research paper" in categories
        assert "white paper" in categories

    def test_stats(self, sample_paper_db, monkeypatch):
        """Test getting database stats."""
        monkeypatch.setenv("MF_SITE_ROOT", str(sample_paper_db.parent.parent))

        db = PaperDatabase(sample_paper_db)
        db.load()

        stats = db.stats()

        assert stats["total"] == 2
        assert stats["category_count"] == 2


class TestProjectsDatabase:
    """Tests for ProjectsDatabase class."""

    def test_load_existing_database(self, sample_projects_db, monkeypatch):
        """Test loading an existing database."""
        monkeypatch.setenv("MF_SITE_ROOT", str(sample_projects_db.parent.parent))

        db = ProjectsDatabase(sample_projects_db)
        db.load()

        assert "test-project" in db

    def test_is_hidden(self, sample_projects_db, monkeypatch):
        """Test checking if project is hidden."""
        monkeypatch.setenv("MF_SITE_ROOT", str(sample_projects_db.parent.parent))

        db = ProjectsDatabase(sample_projects_db)
        db.load()

        assert not db.is_hidden("test-project")
        assert db.is_hidden("hidden-project")

    def test_search_featured(self, sample_projects_db, monkeypatch):
        """Test searching for featured projects."""
        monkeypatch.setenv("MF_SITE_ROOT", str(sample_projects_db.parent.parent))

        db = ProjectsDatabase(sample_projects_db)
        db.load()

        results = db.search(featured=True)

        assert len(results) == 1
        assert results[0][0] == "test-project"

    def test_search_hidden(self, sample_projects_db, monkeypatch):
        """Test searching for hidden projects."""
        monkeypatch.setenv("MF_SITE_ROOT", str(sample_projects_db.parent.parent))

        db = ProjectsDatabase(sample_projects_db)
        db.load()

        results = db.search(hidden=True)

        assert len(results) == 1
        assert results[0][0] == "hidden-project"


class TestProjectsCache:
    """Tests for ProjectsCache class."""

    def test_load_creates_empty_if_missing(self, tmp_path, monkeypatch):
        """Test that loading creates empty cache if file missing."""
        monkeypatch.setenv("MF_SITE_ROOT", str(tmp_path))
        cache_path = tmp_path / "cache.json"

        cache = ProjectsCache(cache_path)
        cache.load()

        assert cache._loaded
        assert len(list(cache)) == 0

    def test_set_and_get(self, tmp_path, monkeypatch):
        """Test setting and getting cache entries."""
        monkeypatch.setenv("MF_SITE_ROOT", str(tmp_path))
        cache_path = tmp_path / "cache.json"

        cache = ProjectsCache(cache_path)
        cache.load()

        cache.set("test", {"name": "test", "stars": 10})

        assert "test" in cache
        assert cache.get("test")["stars"] == 10

    def test_delete(self, tmp_path, monkeypatch):
        """Test deleting cache entry."""
        monkeypatch.setenv("MF_SITE_ROOT", str(tmp_path))
        cache_path = tmp_path / "cache.json"

        cache = ProjectsCache(cache_path)
        cache.load()
        cache.set("test", {"name": "test"})

        assert cache.delete("test") is True
        assert "test" not in cache

    def test_delete_nonexistent(self, tmp_path, monkeypatch):
        """Test deleting nonexistent entry returns False."""
        monkeypatch.setenv("MF_SITE_ROOT", str(tmp_path))
        cache_path = tmp_path / "cache.json"

        cache = ProjectsCache(cache_path)
        cache.load()

        assert cache.delete("nonexistent") is False


class TestSeriesDatabase:
    """Tests for SeriesDatabase class."""

    def test_load_existing_database(self, sample_series_db, monkeypatch):
        """Test loading an existing database."""
        monkeypatch.setenv("MF_SITE_ROOT", str(sample_series_db.parent.parent))

        db = SeriesDatabase(sample_series_db)
        db.load()

        assert "test-series" in db
        assert len(db) == 2

    def test_load_creates_default_if_missing(self, tmp_path, monkeypatch):
        """Test that loading creates default structure if file missing."""
        monkeypatch.setenv("MF_SITE_ROOT", str(tmp_path))
        db_path = tmp_path / "nonexistent.json"

        db = SeriesDatabase(db_path)
        db.load()

        assert db._loaded
        assert "_comment" in db._data

    def test_get_series_entry(self, sample_series_db, monkeypatch):
        """Test getting a series entry."""
        monkeypatch.setenv("MF_SITE_ROOT", str(sample_series_db.parent.parent))

        db = SeriesDatabase(sample_series_db)
        db.load()

        entry = db.get("test-series")

        assert entry is not None
        assert entry.title == "Test Series"
        assert entry.slug == "test-series"

    def test_get_returns_none_for_missing(self, sample_series_db, monkeypatch):
        """Test that get returns None for missing series."""
        monkeypatch.setenv("MF_SITE_ROOT", str(sample_series_db.parent.parent))

        db = SeriesDatabase(sample_series_db)
        db.load()

        entry = db.get("nonexistent")

        assert entry is None

    def test_get_or_create_creates_new(self, sample_series_db, monkeypatch):
        """Test get_or_create creates new entry."""
        monkeypatch.setenv("MF_SITE_ROOT", str(sample_series_db.parent.parent))

        db = SeriesDatabase(sample_series_db)
        db.load()

        entry = db.get_or_create("new-series")

        assert entry is not None
        assert entry.slug == "new-series"
        assert "new-series" in db

    def test_iteration(self, sample_series_db, monkeypatch):
        """Test iterating over series."""
        monkeypatch.setenv("MF_SITE_ROOT", str(sample_series_db.parent.parent))

        db = SeriesDatabase(sample_series_db)
        db.load()

        slugs = list(db)

        assert "test-series" in slugs
        assert "inactive-series" in slugs
        assert "_comment" not in slugs
        assert "_example" not in slugs

    def test_search_by_query(self, sample_series_db, monkeypatch):
        """Test searching by text query."""
        monkeypatch.setenv("MF_SITE_ROOT", str(sample_series_db.parent.parent))

        db = SeriesDatabase(sample_series_db)
        db.load()

        results = db.search(query="test")

        assert len(results) == 1
        assert results[0].slug == "test-series"

    def test_search_by_status(self, sample_series_db, monkeypatch):
        """Test searching by status."""
        monkeypatch.setenv("MF_SITE_ROOT", str(sample_series_db.parent.parent))

        db = SeriesDatabase(sample_series_db)
        db.load()

        results = db.search(status="archived")

        assert len(results) == 1
        assert results[0].slug == "inactive-series"

    def test_search_by_tags(self, sample_series_db, monkeypatch):
        """Test searching by tags."""
        monkeypatch.setenv("MF_SITE_ROOT", str(sample_series_db.parent.parent))

        db = SeriesDatabase(sample_series_db)
        db.load()

        results = db.search(tags=["test"])

        assert len(results) == 1
        assert results[0].slug == "test-series"

    def test_search_featured(self, sample_series_db, monkeypatch):
        """Test searching for featured series."""
        monkeypatch.setenv("MF_SITE_ROOT", str(sample_series_db.parent.parent))

        db = SeriesDatabase(sample_series_db)
        db.load()

        results = db.search(featured=True)

        assert len(results) == 1
        assert results[0].slug == "test-series"

    def test_stats(self, sample_series_db, monkeypatch):
        """Test getting database stats."""
        monkeypatch.setenv("MF_SITE_ROOT", str(sample_series_db.parent.parent))

        db = SeriesDatabase(sample_series_db)
        db.load()

        stats = db.stats()

        assert stats["total"] == 2
        assert stats["featured"] == 1
        assert stats["active"] == 1

    def test_series_entry_properties(self, sample_series_db, monkeypatch):
        """Test SeriesEntry property accessors."""
        monkeypatch.setenv("MF_SITE_ROOT", str(sample_series_db.parent.parent))

        db = SeriesDatabase(sample_series_db)
        db.load()

        entry = db.get("test-series")

        assert entry.title == "Test Series"
        assert entry.description == "A test series"
        assert entry.status == "active"
        assert entry.featured is True
        assert entry.tags == ["test", "sample"]

    def test_delete_series(self, sample_series_db, monkeypatch):
        """Test deleting a series entry."""
        monkeypatch.setenv("MF_SITE_ROOT", str(sample_series_db.parent.parent))

        db = SeriesDatabase(sample_series_db)
        db.load()

        assert db.delete("test-series") is True
        assert "test-series" not in db

    def test_delete_nonexistent(self, sample_series_db, monkeypatch):
        """Test deleting nonexistent entry returns False."""
        monkeypatch.setenv("MF_SITE_ROOT", str(sample_series_db.parent.parent))

        db = SeriesDatabase(sample_series_db)
        db.load()

        assert db.delete("nonexistent") is False
