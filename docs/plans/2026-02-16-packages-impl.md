# Packages System Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement a first-class `mf packages` module with registry adapter discovery, database, CLI, and Hugo content generation.

**Architecture:** Plugin-like registry adapters (Protocol + importlib discovery) with built-ins in `src/mf/packages/registries/` and user overrides in `.mf/registries/`. Database follows the existing `SeriesDatabase`/`SeriesEntry` pattern. CLI follows the existing `series/commands.py` pattern.

**Tech Stack:** Python 3.10+, Click (CLI), Rich (output), urllib (HTTP for registry APIs), pytest (testing)

---

### Task 1: SitePaths + conftest infrastructure

**Files:**
- Modify: `src/mf/core/config.py` (SitePaths dataclass + get_paths)
- Modify: `src/mf/cli.py` (init command — add backups/packages dir)
- Modify: `tests/conftest.py` (mock_site_root fixture)
- Create: `tests/test_packages/__init__.py`

**Step 1: Write the failing test**

Create `tests/test_packages/__init__.py` (empty) and `tests/test_packages/test_config_integration.py`:

```python
"""Verify SitePaths includes packages paths."""

from mf.core.config import get_paths


def test_site_paths_has_packages_fields(mock_site_root):
    paths = get_paths(mock_site_root)
    assert paths.packages == mock_site_root / "content" / "packages"
    assert paths.packages_db == mock_site_root / ".mf" / "packages_db.json"
    assert paths.packages_backups == mock_site_root / ".mf" / "backups" / "packages"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_packages/test_config_integration.py -v`
Expected: FAIL with `AttributeError: 'SitePaths' has no attribute 'packages'`

**Step 3: Add fields to SitePaths and get_paths**

In `src/mf/core/config.py`, add three fields to the `SitePaths` dataclass (after `series_db`):

```python
    # Packages
    packages: Path
    packages_db: Path
    packages_backups: Path
```

In `get_paths()`, add to the return statement:

```python
        # Packages
        packages=site_root / "content" / "packages",
        packages_db=mf_dir / "packages_db.json",
        packages_backups=mf_dir / "backups" / "packages",
```

In `cli.py` `init` command, add to `dirs_to_create`:

```python
        mf_dir / "backups" / "packages",
```

In `tests/conftest.py` `mock_site_root`, add:

```python
    (mf_dir / "backups" / "packages").mkdir(parents=True)
    (tmp_path / "content" / "packages").mkdir(parents=True)
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_packages/test_config_integration.py -v`
Expected: PASS

**Step 5: Run full test suite to check nothing broke**

Run: `pytest --tb=short -q`
Expected: All existing tests pass (1113+)

**Step 6: Commit**

```bash
git add src/mf/core/config.py src/mf/cli.py tests/conftest.py tests/test_packages/
git commit -m "feat(packages): add SitePaths fields and test infrastructure"
```

---

### Task 2: Registry adapter protocol + discovery

**Files:**
- Create: `src/mf/packages/__init__.py`
- Create: `src/mf/packages/registries/__init__.py`
- Create: `tests/test_packages/test_registries.py`

**Step 1: Write the failing tests**

Create `tests/test_packages/test_registries.py`:

```python
"""Tests for registry adapter protocol and discovery."""

import pytest
from pathlib import Path
from mf.packages.registries import (
    PackageMetadata,
    RegistryAdapter,
    discover_registries,
)


class TestPackageMetadata:
    def test_required_fields(self):
        meta = PackageMetadata(
            name="foo",
            registry="pypi",
            latest_version="1.0.0",
            description="A package",
        )
        assert meta.name == "foo"
        assert meta.registry == "pypi"
        assert meta.latest_version == "1.0.0"
        assert meta.description == "A package"

    def test_optional_fields_default_none(self):
        meta = PackageMetadata(
            name="foo", registry="pypi",
            latest_version="1.0.0", description="A package",
        )
        assert meta.homepage is None
        assert meta.license is None
        assert meta.downloads is None
        assert meta.versions is None
        assert meta.install_command is None
        assert meta.registry_url is None
        assert meta.last_updated is None

    def test_all_fields(self):
        meta = PackageMetadata(
            name="foo", registry="pypi",
            latest_version="2.0.0", description="desc",
            homepage="https://foo.dev", license="MIT",
            downloads=1000, versions=["2.0.0", "1.0.0"],
            install_command="pip install foo",
            registry_url="https://pypi.org/project/foo/",
            last_updated="2026-01-01",
        )
        assert meta.downloads == 1000
        assert len(meta.versions) == 2


class TestDiscoverRegistries:
    def test_discovers_builtin_adapters(self):
        """Built-in registries (pypi, cran) are discovered."""
        adapters = discover_registries()
        assert "pypi" in adapters
        assert "cran" in adapters

    def test_user_dir_overrides_builtin(self, tmp_path):
        """A user pypi.py overrides the built-in pypi adapter."""
        user_dir = tmp_path / "registries"
        user_dir.mkdir()
        # Write a minimal adapter module
        (user_dir / "pypi.py").write_text(
            'from mf.packages.registries import PackageMetadata, RegistryAdapter\n'
            '\n'
            'class _Custom:\n'
            '    name = "pypi"\n'
            '    def fetch_metadata(self, package_name):\n'
            '        return PackageMetadata(\n'
            '            name=package_name, registry="custom-pypi",\n'
            '            latest_version="0.0.0", description="overridden",\n'
            '        )\n'
            '\n'
            'adapter = _Custom()\n'
        )

        adapters = discover_registries(extra_dirs=[user_dir])
        assert adapters["pypi"].name == "pypi"
        meta = adapters["pypi"].fetch_metadata("test")
        assert meta is not None
        assert meta.registry == "custom-pypi"

    def test_user_dir_adds_new_registry(self, tmp_path):
        """A user homebrew.py adds a new registry."""
        user_dir = tmp_path / "registries"
        user_dir.mkdir()
        (user_dir / "homebrew.py").write_text(
            'from mf.packages.registries import PackageMetadata\n'
            '\n'
            'class _Homebrew:\n'
            '    name = "homebrew"\n'
            '    def fetch_metadata(self, package_name):\n'
            '        return PackageMetadata(\n'
            '            name=package_name, registry="homebrew",\n'
            '            latest_version="1.0", description="brew",\n'
            '        )\n'
            '\n'
            'adapter = _Homebrew()\n'
        )

        adapters = discover_registries(extra_dirs=[user_dir])
        assert "homebrew" in adapters

    def test_skips_init_file(self):
        """__init__.py in extra dirs is not loaded as an adapter."""
        adapters = discover_registries()
        assert "__init__" not in adapters

    def test_adapter_has_name_and_fetch(self):
        """Each discovered adapter has name attribute and fetch_metadata method."""
        adapters = discover_registries()
        for name, adapter in adapters.items():
            assert hasattr(adapter, "name")
            assert hasattr(adapter, "fetch_metadata")
            assert callable(adapter.fetch_metadata)
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_packages/test_registries.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'mf.packages'`

**Step 3: Implement protocol and discovery**

Create `src/mf/packages/__init__.py`:

```python
"""First-class package registry management for mf."""
```

Create `src/mf/packages/registries/__init__.py`:

```python
"""Registry adapter protocol and discovery.

Built-in adapters live as sibling .py files in this package.
Users can override or extend them by placing .py files in .mf/registries/.
Each module must define a module-level ``adapter`` instance with a ``name``
attribute and a ``fetch_metadata(package_name)`` method.
"""

from __future__ import annotations

import importlib.util
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, runtime_checkable


@dataclass
class PackageMetadata:
    """Standardized metadata returned by any registry adapter."""

    name: str
    registry: str
    latest_version: str
    description: str
    homepage: str | None = None
    license: str | None = None
    downloads: int | None = None
    versions: list[str] | None = None
    install_command: str | None = None
    registry_url: str | None = None
    last_updated: str | None = None


@runtime_checkable
class RegistryAdapter(Protocol):
    """Contract for registry adapters."""

    name: str

    def fetch_metadata(self, package_name: str) -> PackageMetadata | None:
        """Fetch package metadata. Returns None if not found."""
        ...


def _load_adapter_from_file(filepath: Path) -> RegistryAdapter | None:
    """Import a .py file and return its ``adapter`` object, or None."""
    module_name = f"_mf_registry_{filepath.stem}"
    spec = importlib.util.spec_from_file_location(module_name, filepath)
    if spec is None or spec.loader is None:
        return None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = mod
    try:
        spec.loader.exec_module(mod)
    except Exception:
        del sys.modules[module_name]
        return None
    adapter = getattr(mod, "adapter", None)
    if adapter is None or not hasattr(adapter, "name") or not hasattr(adapter, "fetch_metadata"):
        return None
    return adapter


def discover_registries(
    extra_dirs: list[Path] | None = None,
) -> dict[str, RegistryAdapter]:
    """Scan built-in + user dirs, return name -> adapter map.

    Resolution order (last wins):
      1. Built-in: sibling .py files in this package
      2. Each directory in *extra_dirs*
    """
    adapters: dict[str, RegistryAdapter] = {}

    # 1. Built-in adapters (sibling .py files)
    builtin_dir = Path(__file__).parent
    for py_file in sorted(builtin_dir.glob("*.py")):
        if py_file.name.startswith("_"):
            continue
        adapter = _load_adapter_from_file(py_file)
        if adapter is not None:
            adapters[adapter.name] = adapter

    # 2. Extra dirs (user overrides)
    for extra_dir in extra_dirs or []:
        extra_path = Path(extra_dir)
        if not extra_path.is_dir():
            continue
        for py_file in sorted(extra_path.glob("*.py")):
            if py_file.name.startswith("_"):
                continue
            adapter = _load_adapter_from_file(py_file)
            if adapter is not None:
                adapters[adapter.name] = adapter

    return adapters
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_packages/test_registries.py -v`
Expected: Some tests pass (protocol + metadata), discovery tests fail because pypi.py/cran.py don't exist yet. That's expected — we'll fix in Task 3.

**Step 5: Commit**

```bash
git add src/mf/packages/ tests/test_packages/
git commit -m "feat(packages): add registry adapter protocol and discovery"
```

---

### Task 3: PyPI + CRAN built-in adapters

**Files:**
- Create: `src/mf/packages/registries/pypi.py`
- Create: `src/mf/packages/registries/cran.py`
- Create: `tests/test_packages/test_pypi.py`
- Create: `tests/test_packages/test_cran.py`

**Step 1: Write failing tests for PyPI adapter**

Create `tests/test_packages/test_pypi.py`:

```python
"""Tests for PyPI registry adapter."""

import json
import pytest
from unittest.mock import patch, MagicMock
from mf.packages.registries.pypi import PyPIAdapter, adapter


SAMPLE_PYPI_RESPONSE = {
    "info": {
        "name": "requests",
        "version": "2.31.0",
        "summary": "Python HTTP for Humans.",
        "home_page": "https://requests.readthedocs.io",
        "license": "Apache-2.0",
        "project_url": "https://pypi.org/project/requests/",
        "project_urls": {
            "Homepage": "https://requests.readthedocs.io",
        },
    },
    "releases": {
        "2.31.0": [{"upload_time": "2023-05-22T00:00:00"}],
        "2.30.0": [{"upload_time": "2023-05-03T00:00:00"}],
        "2.29.0": [{"upload_time": "2023-04-26T00:00:00"}],
    },
}

SAMPLE_PYPISTATS_RESPONSE = {
    "data": {"last_month": 450000000},
    "type": "overall_stats",
}


class TestPyPIAdapter:
    def test_adapter_module_level_instance(self):
        assert adapter.name == "pypi"

    @patch("mf.packages.registries.pypi._fetch_json")
    def test_fetch_metadata_success(self, mock_fetch):
        mock_fetch.side_effect = [SAMPLE_PYPI_RESPONSE, SAMPLE_PYPISTATS_RESPONSE]
        meta = adapter.fetch_metadata("requests")

        assert meta is not None
        assert meta.name == "requests"
        assert meta.registry == "pypi"
        assert meta.latest_version == "2.31.0"
        assert meta.description == "Python HTTP for Humans."
        assert meta.install_command == "pip install requests"
        assert meta.registry_url == "https://pypi.org/project/requests/"
        assert meta.license == "Apache-2.0"
        assert meta.downloads == 450000000

    @patch("mf.packages.registries.pypi._fetch_json")
    def test_fetch_metadata_not_found(self, mock_fetch):
        mock_fetch.return_value = None
        meta = adapter.fetch_metadata("nonexistent-pkg-xyz")
        assert meta is None

    @patch("mf.packages.registries.pypi._fetch_json")
    def test_fetch_metadata_no_stats(self, mock_fetch):
        """If pypistats fails, downloads is None but metadata still works."""
        mock_fetch.side_effect = [SAMPLE_PYPI_RESPONSE, None]
        meta = adapter.fetch_metadata("requests")
        assert meta is not None
        assert meta.downloads is None

    @patch("mf.packages.registries.pypi._fetch_json")
    def test_versions_limited(self, mock_fetch):
        """Only last 10 versions are returned."""
        releases = {f"1.{i}.0": [{"upload_time": f"2023-01-{i+1:02d}"}] for i in range(20)}
        resp = dict(SAMPLE_PYPI_RESPONSE)
        resp["releases"] = releases
        mock_fetch.side_effect = [resp, SAMPLE_PYPISTATS_RESPONSE]
        meta = adapter.fetch_metadata("requests")
        assert meta is not None
        assert meta.versions is not None
        assert len(meta.versions) <= 10
```

Create `tests/test_packages/test_cran.py`:

```python
"""Tests for CRAN registry adapter."""

import pytest
from unittest.mock import patch
from mf.packages.registries.cran import CRANAdapter, adapter


SAMPLE_CRANDB_RESPONSE = {
    "Package": "reliabilitytheory",
    "Version": "0.3.0",
    "Title": "Reliability Theory Tools",
    "Description": "Tools for structural reliability theory.",
    "License": "MIT + file LICENSE",
    "URL": "https://github.com/queelius/reliabilitytheory",
    "Date/Publication": "2024-03-15",
}


class TestCRANAdapter:
    def test_adapter_module_level_instance(self):
        assert adapter.name == "cran"

    @patch("mf.packages.registries.cran._fetch_json")
    def test_fetch_metadata_success(self, mock_fetch):
        mock_fetch.return_value = SAMPLE_CRANDB_RESPONSE
        meta = adapter.fetch_metadata("reliabilitytheory")

        assert meta is not None
        assert meta.name == "reliabilitytheory"
        assert meta.registry == "cran"
        assert meta.latest_version == "0.3.0"
        assert meta.description == "Reliability Theory Tools"
        assert meta.install_command == "install.packages('reliabilitytheory')"
        assert meta.registry_url == "https://cran.r-project.org/package=reliabilitytheory"

    @patch("mf.packages.registries.cran._fetch_json")
    def test_fetch_metadata_not_found(self, mock_fetch):
        mock_fetch.return_value = None
        meta = adapter.fetch_metadata("nonexistent")
        assert meta is None
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_packages/test_pypi.py tests/test_packages/test_cran.py -v`
Expected: FAIL with `ModuleNotFoundError`

**Step 3: Implement PyPI adapter**

Create `src/mf/packages/registries/pypi.py`:

```python
"""PyPI registry adapter.

Uses the PyPI JSON API (https://pypi.org/pypi/{name}/json) and
pypistats (https://pypistats.org/api/packages/{name}/recent) for download counts.
"""

from __future__ import annotations

import json
import urllib.request
import urllib.error
from typing import Any

from mf.packages.registries import PackageMetadata


def _fetch_json(url: str, timeout: int = 10) -> dict[str, Any] | None:
    """Fetch JSON from a URL. Returns None on any error."""
    try:
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode())
    except (urllib.error.URLError, json.JSONDecodeError, OSError):
        return None


class PyPIAdapter:
    """Fetch package metadata from PyPI."""

    name = "pypi"

    def fetch_metadata(self, package_name: str) -> PackageMetadata | None:
        """Fetch metadata from PyPI JSON API."""
        data = _fetch_json(f"https://pypi.org/pypi/{package_name}/json")
        if data is None:
            return None

        info = data.get("info", {})
        releases = data.get("releases", {})

        # Sort versions by upload time (newest first), take last 10
        version_dates: list[tuple[str, str]] = []
        for ver, files in releases.items():
            if files:
                version_dates.append((ver, files[0].get("upload_time", "")))
        version_dates.sort(key=lambda x: x[1], reverse=True)
        versions = [v for v, _ in version_dates[:10]]

        last_updated = version_dates[0][1][:10] if version_dates else None

        # Fetch download stats (best-effort)
        downloads = None
        stats = _fetch_json(
            f"https://pypistats.org/api/packages/{package_name}/recent"
        )
        if stats and "data" in stats:
            downloads = stats["data"].get("last_month")

        return PackageMetadata(
            name=info.get("name", package_name),
            registry="pypi",
            latest_version=info.get("version", ""),
            description=info.get("summary", ""),
            homepage=info.get("home_page") or info.get("project_urls", {}).get("Homepage"),
            license=info.get("license") or None,
            downloads=downloads,
            versions=versions or None,
            install_command=f"pip install {package_name}",
            registry_url=f"https://pypi.org/project/{package_name}/",
            last_updated=last_updated,
        )


adapter = PyPIAdapter()
```

**Step 4: Implement CRAN adapter**

Create `src/mf/packages/registries/cran.py`:

```python
"""CRAN registry adapter.

Uses the crandb API (https://crandb.r-pkg.org/{name}) for package metadata.
"""

from __future__ import annotations

import json
import urllib.request
import urllib.error
from typing import Any

from mf.packages.registries import PackageMetadata


def _fetch_json(url: str, timeout: int = 10) -> dict[str, Any] | None:
    """Fetch JSON from a URL. Returns None on any error."""
    try:
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode())
    except (urllib.error.URLError, json.JSONDecodeError, OSError):
        return None


class CRANAdapter:
    """Fetch package metadata from CRAN."""

    name = "cran"

    def fetch_metadata(self, package_name: str) -> PackageMetadata | None:
        """Fetch metadata from crandb API."""
        data = _fetch_json(f"https://crandb.r-pkg.org/{package_name}")
        if data is None:
            return None

        # crandb returns an error key for missing packages
        if "error" in data:
            return None

        title = data.get("Title", "")
        version = data.get("Version", "")
        license_str = data.get("License", "")
        url = data.get("URL", "")
        pub_date = data.get("Date/Publication", "")

        # Clean up license (remove "+ file LICENSE" suffix)
        if "+" in license_str:
            license_str = license_str.split("+")[0].strip()

        return PackageMetadata(
            name=data.get("Package", package_name),
            registry="cran",
            latest_version=version,
            description=title,
            homepage=url.split(",")[0].strip() if url else None,
            license=license_str or None,
            downloads=None,  # CRAN doesn't expose download stats easily
            versions=None,
            install_command=f"install.packages('{package_name}')",
            registry_url=f"https://cran.r-project.org/package={package_name}",
            last_updated=pub_date[:10] if pub_date else None,
        )


adapter = CRANAdapter()
```

**Step 5: Run all registry tests**

Run: `pytest tests/test_packages/ -v`
Expected: ALL PASS

**Step 6: Commit**

```bash
git add src/mf/packages/registries/pypi.py src/mf/packages/registries/cran.py tests/test_packages/
git commit -m "feat(packages): add PyPI and CRAN registry adapters"
```

---

### Task 4: PackageDatabase + PackageEntry

**Files:**
- Create: `src/mf/packages/database.py`
- Modify: `src/mf/core/database.py` (add re-export for discoverability)
- Create: `tests/test_packages/test_database.py`

**Step 1: Write failing tests**

Create `tests/test_packages/test_database.py`:

```python
"""Tests for PackageDatabase and PackageEntry."""

import json
import pytest
from pathlib import Path
from mf.packages.database import PackageDatabase, PackageEntry


@pytest.fixture
def sample_packages_db(tmp_path):
    data = {
        "_comment": "Test packages",
        "_schema_version": "1.0",
        "_example": {"name": "example"},
        "requests": {
            "name": "requests",
            "registry": "pypi",
            "description": "HTTP for Humans",
            "latest_version": "2.31.0",
            "tags": ["http", "api"],
            "featured": True,
            "project": "requests",
        },
        "reliabilitytheory": {
            "name": "reliabilitytheory",
            "registry": "cran",
            "description": "Reliability Theory Tools",
            "latest_version": "0.3.0",
        },
    }
    file_path = tmp_path / "packages_db.json"
    file_path.write_text(json.dumps(data, indent=2))
    return file_path


class TestPackageEntry:
    def test_properties(self):
        entry = PackageEntry(slug="foo", data={
            "name": "foo", "registry": "pypi",
            "description": "A pkg", "latest_version": "1.0",
            "featured": True, "tags": ["test"],
            "project": "foo-project",
        })
        assert entry.name == "foo"
        assert entry.registry == "pypi"
        assert entry.description == "A pkg"
        assert entry.latest_version == "1.0"
        assert entry.featured is True
        assert entry.tags == ["test"]
        assert entry.project == "foo-project"

    def test_defaults(self):
        entry = PackageEntry(slug="bar", data={})
        assert entry.name == "bar"
        assert entry.registry is None
        assert entry.description is None
        assert entry.featured is False
        assert entry.tags == []
        assert entry.project is None


class TestPackageDatabase:
    def test_load_nonexistent(self, tmp_path):
        db = PackageDatabase(tmp_path / "nope.json")
        db.load()
        assert len(db) == 0

    def test_load_existing(self, sample_packages_db):
        db = PackageDatabase(sample_packages_db)
        db.load()
        assert len(db) == 2
        assert "requests" in db

    def test_get(self, sample_packages_db):
        db = PackageDatabase(sample_packages_db)
        db.load()
        entry = db.get("requests")
        assert entry is not None
        assert entry.name == "requests"
        assert entry.registry == "pypi"

    def test_get_not_found(self, sample_packages_db):
        db = PackageDatabase(sample_packages_db)
        db.load()
        assert db.get("nonexistent") is None

    def test_set_and_get(self, sample_packages_db):
        db = PackageDatabase(sample_packages_db)
        db.load()
        db.set("new-pkg", {"name": "new-pkg", "registry": "pypi"})
        entry = db.get("new-pkg")
        assert entry is not None
        assert entry.registry == "pypi"

    def test_delete(self, sample_packages_db):
        db = PackageDatabase(sample_packages_db)
        db.load()
        assert db.delete("requests") is True
        assert "requests" not in db
        assert db.delete("requests") is False

    def test_save_and_reload(self, sample_packages_db, tmp_path):
        # Create backup dir so save works
        (tmp_path / "backups").mkdir(exist_ok=True)
        db = PackageDatabase(sample_packages_db)
        db.load()
        db.set("new-pkg", {"name": "new-pkg", "registry": "cran"})
        db.save(create_backup=False)

        db2 = PackageDatabase(sample_packages_db)
        db2.load()
        assert "new-pkg" in db2

    def test_search_by_query(self, sample_packages_db):
        db = PackageDatabase(sample_packages_db)
        db.load()
        results = db.search(query="http")
        assert len(results) == 1
        assert results[0].slug == "requests"

    def test_search_by_registry(self, sample_packages_db):
        db = PackageDatabase(sample_packages_db)
        db.load()
        results = db.search(registry="cran")
        assert len(results) == 1

    def test_search_by_featured(self, sample_packages_db):
        db = PackageDatabase(sample_packages_db)
        db.load()
        results = db.search(featured=True)
        assert len(results) == 1
        assert results[0].slug == "requests"

    def test_search_by_tags(self, sample_packages_db):
        db = PackageDatabase(sample_packages_db)
        db.load()
        results = db.search(tags=["http"])
        assert len(results) == 1

    def test_items(self, sample_packages_db):
        db = PackageDatabase(sample_packages_db)
        db.load()
        items = list(db.items())
        assert len(items) == 2

    def test_iter(self, sample_packages_db):
        db = PackageDatabase(sample_packages_db)
        db.load()
        slugs = list(db)
        assert "requests" in slugs
        assert "reliabilitytheory" in slugs

    def test_special_keys_excluded(self, sample_packages_db):
        db = PackageDatabase(sample_packages_db)
        db.load()
        assert "_comment" not in db
        assert "_example" not in list(db)

    def test_stats(self, sample_packages_db):
        db = PackageDatabase(sample_packages_db)
        db.load()
        s = db.stats()
        assert s["total"] == 2
        assert s["featured"] == 1
        assert "pypi" in s["registries"]
        assert "cran" in s["registries"]
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_packages/test_database.py -v`
Expected: FAIL with `ModuleNotFoundError`

**Step 3: Implement PackageDatabase + PackageEntry**

Create `src/mf/packages/database.py` following the exact `SeriesDatabase`/`SeriesEntry` pattern from `core/database.py`. The implementation should match lines 756-1183 of `core/database.py` structurally but with package-specific fields and search filters.

Key differences from SeriesDatabase:
- `PackageEntry` has: `name`, `registry`, `description`, `latest_version`, `featured`, `tags`, `project`, `install_command`, `registry_url`, `license`, `downloads`, `last_synced`
- `search()` accepts: `query`, `tags`, `registry`, `featured`
- `stats()` returns: `total`, `featured`, `registries` (list of unique registries)
- `save()` uses `get_paths().packages_backups` as backup dir

**Step 4: Run tests**

Run: `pytest tests/test_packages/test_database.py -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add src/mf/packages/database.py tests/test_packages/test_database.py
git commit -m "feat(packages): add PackageDatabase and PackageEntry"
```

---

### Task 5: Field operations (PACKAGES_SCHEMA + wrappers)

**Files:**
- Create: `src/mf/packages/field_ops.py`
- Create: `tests/test_packages/test_field_ops.py`

**Step 1: Write failing tests**

Create `tests/test_packages/test_field_ops.py`:

```python
"""Tests for packages field_ops -- schema and wrappers."""

import json
import pytest
from mf.packages.field_ops import (
    PACKAGES_SCHEMA,
    validate_package_field,
    set_package_field,
    unset_package_field,
    modify_package_list_field,
)
from mf.core.field_ops import FieldType
from mf.packages.database import PackageDatabase


class TestPackagesSchema:
    def test_has_core_fields(self):
        for field in ("name", "registry", "description", "latest_version"):
            assert field in PACKAGES_SCHEMA

    def test_has_classification_fields(self):
        assert "tags" in PACKAGES_SCHEMA
        assert PACKAGES_SCHEMA["tags"].field_type == FieldType.STRING_LIST
        assert "featured" in PACKAGES_SCHEMA
        assert PACKAGES_SCHEMA["featured"].field_type == FieldType.BOOL

    def test_registry_choices(self):
        schema = PACKAGES_SCHEMA["registry"]
        assert schema.choices is not None
        assert "pypi" in schema.choices
        assert "cran" in schema.choices

    def test_stars_range(self):
        schema = PACKAGES_SCHEMA["stars"]
        assert schema.min_val == 0
        assert schema.max_val == 5

    def test_downloads_is_int(self):
        assert PACKAGES_SCHEMA["downloads"].field_type == FieldType.INT


class TestValidation:
    def test_valid_registry(self):
        errors = validate_package_field("registry", "pypi")
        assert errors == []

    def test_invalid_registry(self):
        errors = validate_package_field("registry", "maven")
        assert len(errors) > 0

    def test_valid_stars(self):
        assert validate_package_field("stars", 3) == []

    def test_invalid_stars(self):
        assert len(validate_package_field("stars", 10)) > 0


class TestSetUnset:
    @pytest.fixture
    def pkg_db(self, tmp_path):
        data = {
            "_comment": "test",
            "_schema_version": "1.0",
            "foo": {"name": "foo", "registry": "pypi"},
        }
        path = tmp_path / "packages_db.json"
        path.write_text(json.dumps(data))
        db = PackageDatabase(path)
        db.load()
        return db

    def test_set_field(self, pkg_db):
        result = set_package_field(pkg_db, "foo", "description", "A package")
        assert result.new_value == "A package"
        entry = pkg_db.get("foo")
        assert entry.description == "A package"

    def test_unset_field(self, pkg_db):
        set_package_field(pkg_db, "foo", "description", "temp")
        result = unset_package_field(pkg_db, "foo", "description")
        assert result.old_value == "temp"

    def test_modify_tags(self, pkg_db):
        result = modify_package_list_field(
            pkg_db, "foo", "tags", add=["http", "api"]
        )
        assert result.new_value == ["http", "api"]
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_packages/test_field_ops.py -v`
Expected: FAIL

**Step 3: Implement field_ops**

Create `src/mf/packages/field_ops.py` following the exact pattern from `series/field_ops.py` (lines 1-115). Uses `EntryDatabaseAdapter` since `PackageDatabase.get()` returns `PackageEntry`.

**Step 4: Run tests**

Run: `pytest tests/test_packages/test_field_ops.py -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add src/mf/packages/field_ops.py tests/test_packages/test_field_ops.py
git commit -m "feat(packages): add PACKAGES_SCHEMA and field operation wrappers"
```

---

### Task 6: Hugo content generator

**Files:**
- Create: `src/mf/packages/generator.py`
- Create: `tests/test_packages/test_generator.py`

**Step 1: Write failing tests**

Create `tests/test_packages/test_generator.py`:

```python
"""Tests for packages Hugo content generation."""

import json
import pytest
from pathlib import Path
from mf.packages.database import PackageDatabase
from mf.packages.generator import generate_package_content, generate_all_packages


@pytest.fixture
def pkg_db(tmp_path):
    data = {
        "_comment": "test",
        "_schema_version": "1.0",
        "requests": {
            "name": "requests",
            "registry": "pypi",
            "description": "HTTP for Humans",
            "latest_version": "2.31.0",
            "install_command": "pip install requests",
            "registry_url": "https://pypi.org/project/requests/",
            "license": "Apache-2.0",
            "downloads": 450000000,
            "featured": True,
            "project": "requests",
            "tags": ["http", "api"],
        },
        "reliabilitytheory": {
            "name": "reliabilitytheory",
            "registry": "cran",
            "description": "Reliability Theory Tools",
            "latest_version": "0.3.0",
            "install_command": "install.packages('reliabilitytheory')",
            "registry_url": "https://cran.r-project.org/package=reliabilitytheory",
        },
    }
    path = tmp_path / "packages_db.json"
    path.write_text(json.dumps(data))
    db = PackageDatabase(path)
    db.load()
    return db


class TestGeneratePackageContent:
    def test_generates_index_md(self, mock_site_root, pkg_db):
        result = generate_package_content("requests", pkg_db.get("requests"))
        assert result is True
        index_md = mock_site_root / "content" / "packages" / "requests" / "index.md"
        assert index_md.exists()

    def test_frontmatter_fields(self, mock_site_root, pkg_db):
        generate_package_content("requests", pkg_db.get("requests"))
        index_md = mock_site_root / "content" / "packages" / "requests" / "index.md"
        content = index_md.read_text()
        assert 'title: "requests"' in content
        assert 'registry: "pypi"' in content
        assert 'latest_version: "2.31.0"' in content
        assert 'install_command: "pip install requests"' in content
        assert "featured: true" in content
        assert 'linked_project: "/projects/requests/"' in content

    def test_dry_run_no_file(self, mock_site_root, pkg_db):
        result = generate_package_content("requests", pkg_db.get("requests"), dry_run=True)
        assert result is True
        index_md = mock_site_root / "content" / "packages" / "requests" / "index.md"
        assert not index_md.exists()

    def test_tags_in_frontmatter(self, mock_site_root, pkg_db):
        generate_package_content("requests", pkg_db.get("requests"))
        content = (mock_site_root / "content" / "packages" / "requests" / "index.md").read_text()
        assert "tags:" in content
        assert '"http"' in content


class TestGenerateAllPackages:
    def test_generates_all(self, mock_site_root, pkg_db):
        success, failed = generate_all_packages(pkg_db, dry_run=False)
        assert success == 2
        assert failed == 0
        assert (mock_site_root / "content" / "packages" / "requests" / "index.md").exists()
        assert (mock_site_root / "content" / "packages" / "reliabilitytheory" / "index.md").exists()
```

**Step 2: Run tests to verify failure**

Run: `pytest tests/test_packages/test_generator.py -v`

**Step 3: Implement generator**

Create `src/mf/packages/generator.py` following the pattern from `projects/generator.py` but much simpler (no GitHub data merging, no branch bundles). Generates leaf bundle `content/packages/{name}/index.md` with YAML frontmatter.

Key function signatures:
- `generate_package_content(slug, entry, dry_run=False) -> bool`
- `generate_all_packages(db, dry_run=False) -> tuple[int, int]`

**Step 4: Run tests**

Run: `pytest tests/test_packages/test_generator.py -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add src/mf/packages/generator.py tests/test_packages/test_generator.py
git commit -m "feat(packages): add Hugo content generator"
```

---

### Task 7: CLI commands

**Files:**
- Create: `src/mf/packages/commands.py`
- Modify: `src/mf/cli.py` (register packages command group)
- Create: `tests/test_packages/test_commands.py`

**Step 1: Write failing tests**

Create `tests/test_packages/test_commands.py`:

```python
"""Tests for mf packages CLI commands."""

import json
import pytest
from click.testing import CliRunner
from mf.cli import main


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def pkg_db_file(mock_site_root):
    """Create a packages database in mock site."""
    data = {
        "_comment": "test",
        "_schema_version": "1.0",
        "requests": {
            "name": "requests",
            "registry": "pypi",
            "description": "HTTP for Humans",
            "latest_version": "2.31.0",
            "tags": ["http"],
            "featured": True,
        },
    }
    path = mock_site_root / ".mf" / "packages_db.json"
    path.write_text(json.dumps(data, indent=2))
    return path


class TestPackagesList:
    def test_list_empty(self, runner, mock_site_root):
        result = runner.invoke(main, ["packages", "list"])
        assert result.exit_code == 0

    def test_list_with_packages(self, runner, pkg_db_file):
        result = runner.invoke(main, ["packages", "list"])
        assert result.exit_code == 0
        assert "requests" in result.output

    def test_list_json(self, runner, pkg_db_file):
        result = runner.invoke(main, ["packages", "list", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert len(data) == 1
        assert data[0]["slug"] == "requests"


class TestPackagesShow:
    def test_show_existing(self, runner, pkg_db_file):
        result = runner.invoke(main, ["packages", "show", "requests"])
        assert result.exit_code == 0
        assert "requests" in result.output

    def test_show_not_found(self, runner, pkg_db_file):
        result = runner.invoke(main, ["packages", "show", "nonexistent"])
        assert result.exit_code == 0
        assert "not found" in result.output.lower()


class TestPackagesAdd:
    def test_add_dry_run(self, runner, mock_site_root):
        result = runner.invoke(main, [
            "--dry-run", "packages", "add", "test-pkg", "--registry", "pypi",
        ])
        assert result.exit_code == 0

    def test_add_creates_entry(self, runner, mock_site_root):
        result = runner.invoke(main, [
            "packages", "add", "my-pkg", "--registry", "pypi", "--no-sync",
        ])
        assert result.exit_code == 0
        db_path = mock_site_root / ".mf" / "packages_db.json"
        assert db_path.exists()
        data = json.loads(db_path.read_text())
        assert "my-pkg" in data


class TestPackagesRemove:
    def test_remove_existing(self, runner, pkg_db_file, mock_site_root):
        result = runner.invoke(main, ["packages", "remove", "requests", "-y"])
        assert result.exit_code == 0
        data = json.loads(pkg_db_file.read_text())
        assert "requests" not in data

    def test_remove_not_found(self, runner, pkg_db_file):
        result = runner.invoke(main, ["packages", "remove", "nonexistent", "-y"])
        assert result.exit_code == 0
        assert "not found" in result.output.lower()


class TestPackagesSetUnset:
    def test_set_field(self, runner, pkg_db_file):
        result = runner.invoke(main, [
            "packages", "set", "requests", "description", "Updated desc",
        ])
        assert result.exit_code == 0
        data = json.loads(pkg_db_file.read_text())
        assert data["requests"]["description"] == "Updated desc"

    def test_unset_field(self, runner, pkg_db_file):
        result = runner.invoke(main, [
            "packages", "unset", "requests", "description",
        ])
        assert result.exit_code == 0

    def test_set_unknown_field(self, runner, pkg_db_file):
        result = runner.invoke(main, [
            "packages", "set", "requests", "nonexistent_field", "value",
        ])
        assert result.exit_code == 0
        assert "unknown" in result.output.lower() or "Unknown" in result.output


class TestPackagesGenerate:
    def test_generate_all(self, runner, pkg_db_file, mock_site_root):
        result = runner.invoke(main, ["packages", "generate"])
        assert result.exit_code == 0
        assert (mock_site_root / "content" / "packages" / "requests" / "index.md").exists()

    def test_generate_single(self, runner, pkg_db_file, mock_site_root):
        result = runner.invoke(main, ["packages", "generate", "requests"])
        assert result.exit_code == 0
        assert (mock_site_root / "content" / "packages" / "requests" / "index.md").exists()
```

**Step 2: Run tests to verify failure**

Run: `pytest tests/test_packages/test_commands.py -v`

**Step 3: Implement CLI commands**

Create `src/mf/packages/commands.py` following the `series/commands.py` pattern. Commands:
- `list` — table output with Rich, `--json` option
- `show` — panel display of package details
- `add` — create entry + optionally sync from registry (`--no-sync` to skip)
- `remove` — delete entry with `-y` confirmation
- `set` / `unset` — field operations (reuse field_ops pattern)
- `feature` — toggle featured flag
- `tag` — manage tags
- `fields` — list schema
- `generate` — generate Hugo content (all or single)
- `sync` — refresh from registry APIs (all or single)
- `stats` — database statistics

Register in `src/mf/cli.py`:
```python
from mf.packages.commands import packages  # noqa: E402
main.add_command(packages)
```

**Step 4: Run tests**

Run: `pytest tests/test_packages/test_commands.py -v`
Expected: ALL PASS

**Step 5: Run full test suite**

Run: `pytest --tb=short -q`
Expected: All tests pass

**Step 6: Commit**

```bash
git add src/mf/packages/commands.py src/mf/cli.py tests/test_packages/test_commands.py
git commit -m "feat(packages): add CLI commands and register in main CLI"
```

---

### Task 8: Integration, CLAUDE.md, and SITE_CONTRACT.md updates

**Files:**
- Modify: `CLAUDE.md` (add packages to module table, CLI listing)
- Modify: `SITE_CONTRACT.md` (add packages content section)
- Modify: `src/mf/core/integrity.py` (if it validates cross-DB references, add packages)

**Step 1: Update CLAUDE.md**

Add `packages/` to the module structure table:
```
| `packages/` | Package registry management and Hugo content generation | `packages_db.json` |
```

Add to CLI structure:
```
- `mf packages` — add, remove, sync, generate, set/unset, feature, tag, stats, show, list, fields
```

Add to data files:
```
  packages_db.json        # Package metadata
```

**Step 2: Update SITE_CONTRACT.md**

Add a `/packages/` section documenting:
- Front matter fields generated (title, slug, registry, latest_version, etc.)
- Required Hugo layout: `layouts/packages/single.html` (or `layouts/packages/list.html`)
- Content path: `content/packages/{name}/index.md`

**Step 3: Run full test suite one final time**

Run: `pytest --tb=short -q`
Expected: All tests pass (previous 1113 + new ~40-50 package tests)

**Step 4: Run coverage to identify gaps**

Run: `pytest --cov=mf.packages --cov-report=term-missing tests/test_packages/`
Review any uncovered lines and add tests if significant.

**Step 5: Commit**

```bash
git add CLAUDE.md SITE_CONTRACT.md
git commit -m "docs: update CLAUDE.md and SITE_CONTRACT.md for packages system"
```

---

## Summary

| Task | What | Files | Tests |
|------|------|-------|-------|
| 1 | SitePaths + infrastructure | config.py, cli.py, conftest.py | 1 |
| 2 | Registry protocol + discovery | registries/__init__.py | ~6 |
| 3 | PyPI + CRAN adapters | pypi.py, cran.py | ~8 |
| 4 | PackageDatabase + PackageEntry | database.py | ~16 |
| 5 | PACKAGES_SCHEMA + field_ops | field_ops.py | ~9 |
| 6 | Hugo content generator | generator.py | ~5 |
| 7 | CLI commands | commands.py, cli.py | ~12 |
| 8 | Docs + integration | CLAUDE.md, SITE_CONTRACT.md | 0 (coverage check) |

Total: ~8 commits, ~57 new tests, ~7 new files
