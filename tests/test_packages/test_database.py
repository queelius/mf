"""Tests for PackageDatabase and PackageEntry."""

import json

import pytest

from mf.packages.database import PackageDatabase, PackageEntry


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_packages_db(tmp_path):
    """Create a sample packages_db.json with 2 entries."""
    data = {
        "_comment": "Package metadata database.",
        "_schema_version": "1.0",
        "_example": {"name": "example"},
        "requests": {
            "name": "requests",
            "registry": "pypi",
            "description": "HTTP for Humans",
            "latest_version": "2.31.0",
            "featured": True,
            "tags": ["python", "http"],
            "project": "requests-project",
            "install_command": "pip install requests",
            "registry_url": "https://pypi.org/project/requests/",
            "license": "Apache-2.0",
            "downloads": 5000000,
            "last_synced": "2026-01-15T10:00:00",
            "stars": 51000,
        },
        "reliabilitytheory": {
            "name": "ReliabilityTheory",
            "registry": "cran",
            "description": "Reliability theory tools for R",
            "latest_version": "0.3.0",
            "featured": False,
            "tags": ["r", "statistics", "reliability"],
            "project": None,
            "install_command": "install.packages('ReliabilityTheory')",
            "registry_url": "https://cran.r-project.org/package=ReliabilityTheory",
            "license": "GPL-2",
            "downloads": 1200,
            "last_synced": "2026-01-10T08:00:00",
            "stars": 0,
        },
    }
    file_path = tmp_path / "packages_db.json"
    file_path.write_text(json.dumps(data, indent=2))
    return file_path


# ---------------------------------------------------------------------------
# TestPackageEntry
# ---------------------------------------------------------------------------


class TestPackageEntry:
    """Tests for PackageEntry dataclass."""

    def test_properties(self):
        """All fields are read correctly from data."""
        data = {
            "name": "requests",
            "registry": "pypi",
            "description": "HTTP for Humans",
            "latest_version": "2.31.0",
            "featured": True,
            "tags": ["python", "http"],
            "project": "requests-project",
            "install_command": "pip install requests",
            "registry_url": "https://pypi.org/project/requests/",
            "license": "Apache-2.0",
            "downloads": 5000000,
            "last_synced": "2026-01-15T10:00:00",
            "stars": 51000,
        }
        entry = PackageEntry(slug="requests", data=data)

        assert entry.name == "requests"
        assert entry.registry == "pypi"
        assert entry.description == "HTTP for Humans"
        assert entry.latest_version == "2.31.0"
        assert entry.featured is True
        assert entry.tags == ["python", "http"]
        assert entry.project == "requests-project"
        assert entry.install_command == "pip install requests"
        assert entry.registry_url == "https://pypi.org/project/requests/"
        assert entry.license == "Apache-2.0"
        assert entry.downloads == 5000000
        assert entry.last_synced == "2026-01-15T10:00:00"
        assert entry.stars == 51000

    def test_defaults(self):
        """Empty data produces sensible defaults."""
        entry = PackageEntry(slug="my-pkg", data={})

        assert entry.name == "my-pkg"  # defaults to slug
        assert entry.registry is None
        assert entry.description is None
        assert entry.latest_version is None
        assert entry.featured is False
        assert entry.tags == []
        assert entry.project is None
        assert entry.install_command is None
        assert entry.registry_url is None
        assert entry.license is None
        assert entry.downloads is None
        assert entry.last_synced is None
        assert entry.stars == 0

    def test_update(self):
        """update() merges kwargs into data."""
        entry = PackageEntry(slug="pkg", data={"name": "pkg"})
        entry.update(description="new desc", featured=True)

        assert entry.description == "new desc"
        assert entry.featured is True
        assert entry.name == "pkg"  # unchanged


# ---------------------------------------------------------------------------
# TestPackageDatabase
# ---------------------------------------------------------------------------


class TestPackageDatabase:
    """Tests for PackageDatabase."""

    def test_load_nonexistent(self, tmp_path, mock_site_root):
        """Loading a non-existent file creates empty db."""
        db = PackageDatabase(db_path=tmp_path / "does_not_exist.json")
        db.load()
        assert len(db) == 0

    def test_load_existing(self, sample_packages_db, mock_site_root):
        """Loading an existing file reads all entries."""
        db = PackageDatabase(db_path=sample_packages_db)
        db.load()
        assert len(db) == 2

    def test_get(self, sample_packages_db, mock_site_root):
        """get() returns a PackageEntry."""
        db = PackageDatabase(db_path=sample_packages_db)
        db.load()

        entry = db.get("requests")
        assert entry is not None
        assert isinstance(entry, PackageEntry)
        assert entry.slug == "requests"
        assert entry.name == "requests"
        assert entry.registry == "pypi"

    def test_get_not_found(self, sample_packages_db, mock_site_root):
        """get() returns None for missing slugs."""
        db = PackageDatabase(db_path=sample_packages_db)
        db.load()
        assert db.get("nonexistent") is None

    def test_get_special_key_returns_none(self, sample_packages_db, mock_site_root):
        """get() returns None for special keys like _comment."""
        db = PackageDatabase(db_path=sample_packages_db)
        db.load()
        assert db.get("_comment") is None
        assert db.get("_example") is None
        assert db.get("_schema_version") is None

    def test_set_and_get(self, tmp_path, mock_site_root):
        """set() stores data retrievable by get()."""
        db = PackageDatabase(db_path=tmp_path / "pkg.json")
        db.load()

        db.set("new-pkg", {"name": "New Package", "registry": "pypi"})
        entry = db.get("new-pkg")
        assert entry is not None
        assert entry.name == "New Package"
        assert entry.registry == "pypi"

    def test_set_rejects_special_key(self, tmp_path, mock_site_root):
        """set() raises ValueError for reserved keys."""
        db = PackageDatabase(db_path=tmp_path / "pkg.json")
        db.load()

        with pytest.raises(ValueError, match="Cannot use reserved key"):
            db.set("_comment", {"name": "bad"})

    def test_delete(self, sample_packages_db, mock_site_root):
        """delete() returns True for existing, False for missing."""
        db = PackageDatabase(db_path=sample_packages_db)
        db.load()

        assert db.delete("requests") is True
        assert db.get("requests") is None
        assert db.delete("requests") is False
        assert db.delete("nonexistent") is False

    def test_save_and_reload(self, tmp_path, mock_site_root):
        """Saved database can be loaded by a new instance."""
        db_path = tmp_path / ".mf" / "packages_db.json"
        db_path.parent.mkdir(parents=True, exist_ok=True)

        db = PackageDatabase(db_path=db_path)
        db.load()
        db.set("test-pkg", {"name": "Test", "registry": "pypi", "featured": True})
        db.save(create_backup=False)

        db2 = PackageDatabase(db_path=db_path)
        db2.load()
        entry = db2.get("test-pkg")
        assert entry is not None
        assert entry.name == "Test"
        assert entry.registry == "pypi"
        assert entry.featured is True

    def test_search_by_query(self, sample_packages_db, mock_site_root):
        """search() filters by text in name/description."""
        db = PackageDatabase(db_path=sample_packages_db)
        db.load()

        results = db.search(query="http")
        assert len(results) == 1
        assert results[0].slug == "requests"

        # Also matches description
        results = db.search(query="reliability")
        assert len(results) == 1
        assert results[0].slug == "reliabilitytheory"

    def test_search_by_registry(self, sample_packages_db, mock_site_root):
        """search() filters by registry."""
        db = PackageDatabase(db_path=sample_packages_db)
        db.load()

        results = db.search(registry="pypi")
        assert len(results) == 1
        assert results[0].slug == "requests"

        results = db.search(registry="cran")
        assert len(results) == 1
        assert results[0].slug == "reliabilitytheory"

        results = db.search(registry="npm")
        assert len(results) == 0

    def test_search_by_featured(self, sample_packages_db, mock_site_root):
        """search() filters by featured status."""
        db = PackageDatabase(db_path=sample_packages_db)
        db.load()

        results = db.search(featured=True)
        assert len(results) == 1
        assert results[0].slug == "requests"

        results = db.search(featured=False)
        assert len(results) == 1
        assert results[0].slug == "reliabilitytheory"

    def test_search_by_tags(self, sample_packages_db, mock_site_root):
        """search() filters by tags (any match)."""
        db = PackageDatabase(db_path=sample_packages_db)
        db.load()

        results = db.search(tags=["python"])
        assert len(results) == 1
        assert results[0].slug == "requests"

        results = db.search(tags=["statistics"])
        assert len(results) == 1
        assert results[0].slug == "reliabilitytheory"

        # Multiple tags: any match
        results = db.search(tags=["python", "r"])
        assert len(results) == 2

    def test_items(self, sample_packages_db, mock_site_root):
        """items() yields (slug, PackageEntry) pairs."""
        db = PackageDatabase(db_path=sample_packages_db)
        db.load()

        items = list(db.items())
        assert len(items) == 2
        slugs = {slug for slug, _entry in items}
        assert slugs == {"requests", "reliabilitytheory"}
        for _slug, entry in items:
            assert isinstance(entry, PackageEntry)

    def test_iter(self, sample_packages_db, mock_site_root):
        """__iter__ yields slugs only, excluding special keys."""
        db = PackageDatabase(db_path=sample_packages_db)
        db.load()

        slugs = list(db)
        assert "requests" in slugs
        assert "reliabilitytheory" in slugs
        assert "_comment" not in slugs
        assert "_example" not in slugs
        assert "_schema_version" not in slugs

    def test_contains(self, sample_packages_db, mock_site_root):
        """__contains__ checks for real entries, not special keys."""
        db = PackageDatabase(db_path=sample_packages_db)
        db.load()

        assert "requests" in db
        assert "reliabilitytheory" in db
        assert "nonexistent" not in db
        assert "_comment" not in db

    def test_len(self, sample_packages_db, mock_site_root):
        """__len__ counts only real entries."""
        db = PackageDatabase(db_path=sample_packages_db)
        db.load()
        assert len(db) == 2

    def test_special_keys_excluded(self, sample_packages_db, mock_site_root):
        """Special keys are excluded from iteration, contains, and len."""
        db = PackageDatabase(db_path=sample_packages_db)
        db.load()

        all_slugs = list(db)
        for key in PackageDatabase.SPECIAL_KEYS:
            assert key not in all_slugs
            assert key not in db

    def test_stats(self, sample_packages_db, mock_site_root):
        """stats() returns correct summary."""
        db = PackageDatabase(db_path=sample_packages_db)
        db.load()

        s = db.stats()
        assert s["total"] == 2
        assert s["featured"] == 1
        assert sorted(s["registries"]) == ["cran", "pypi"]

    def test_list_tags(self, sample_packages_db, mock_site_root):
        """list_tags() returns sorted unique tags."""
        db = PackageDatabase(db_path=sample_packages_db)
        db.load()

        tags = db.list_tags()
        assert isinstance(tags, list)
        assert tags == sorted(tags)
        assert "python" in tags
        assert "http" in tags
        assert "r" in tags
        assert "statistics" in tags
        assert "reliability" in tags

    def test_list_registries(self, sample_packages_db, mock_site_root):
        """list_registries() returns sorted unique registries."""
        db = PackageDatabase(db_path=sample_packages_db)
        db.load()

        registries = db.list_registries()
        assert registries == ["cran", "pypi"]

    def test_load_invalid_json(self, tmp_path, mock_site_root):
        """Loading invalid JSON exits with error."""
        db_path = tmp_path / "bad.json"
        db_path.write_text("{bad json")

        db = PackageDatabase(db_path=db_path)
        with pytest.raises(SystemExit):
            db.load()

    def test_save_without_load(self, tmp_path, mock_site_root):
        """save() raises RuntimeError if load() not called."""
        db = PackageDatabase(db_path=tmp_path / "pkg.json")
        with pytest.raises(RuntimeError, match="not loaded"):
            db.save()

    def test_save_fills_default_meta(self, tmp_path, mock_site_root):
        """save() adds missing DEFAULT_META keys."""
        db_path = tmp_path / ".mf" / "packages_db.json"
        db_path.parent.mkdir(parents=True, exist_ok=True)

        db = PackageDatabase(db_path=db_path)
        db.load()
        # Remove a default key to verify it gets re-added on save
        db._data.pop("_comment", None)
        db.save(create_backup=False)

        import json
        saved = json.loads(db_path.read_text())
        assert "_comment" in saved
        assert "_schema_version" in saved

    def test_default_db_path(self, mock_site_root):
        """PackageDatabase uses get_paths().packages_db when no path given."""
        from mf.core.config import get_paths
        db = PackageDatabase()
        assert db.db_path == get_paths().packages_db

    def test_update_method(self, sample_packages_db, mock_site_root):
        """update() modifies fields on existing entries."""
        db = PackageDatabase(db_path=sample_packages_db)
        db.load()

        db.update("requests", description="Updated description")
        entry = db.get("requests")
        assert entry is not None
        assert entry.description == "Updated description"

    def test_get_or_create_existing(self, sample_packages_db, mock_site_root):
        """get_or_create() returns existing entry."""
        db = PackageDatabase(db_path=sample_packages_db)
        db.load()

        entry = db.get_or_create("requests")
        assert entry.name == "requests"
        assert entry.registry == "pypi"

    def test_get_or_create_new(self, tmp_path, mock_site_root):
        """get_or_create() creates new entry if missing."""
        db = PackageDatabase(db_path=tmp_path / "pkg.json")
        db.load()

        entry = db.get_or_create("brand-new")
        assert entry.slug == "brand-new"
        assert entry.name == "brand-new"  # defaults to slug
        assert "brand-new" in db

    def test_search_no_filters(self, sample_packages_db, mock_site_root):
        """search() with no filters returns all entries."""
        db = PackageDatabase(db_path=sample_packages_db)
        db.load()

        results = db.search()
        assert len(results) == 2
