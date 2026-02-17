"""Tests for mf.packages.generator -- Hugo content generation for packages."""

import json

import pytest

from mf.packages.database import PackageDatabase
from mf.packages.generator import generate_all_packages, generate_package_content


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def pkg_db(mock_site_root, tmp_path):
    """PackageDatabase with two test entries."""
    db_path = mock_site_root / ".mf" / "packages_db.json"
    data = {
        "_comment": "test",
        "_schema_version": "1.0",
        "alpha-pkg": {
            "name": "alpha-pkg",
            "registry": "pypi",
            "description": "Alpha package for testing",
            "latest_version": "1.2.3",
            "install_command": "pip install alpha-pkg",
            "registry_url": "https://pypi.org/project/alpha-pkg/",
            "license": "MIT",
            "downloads": 5000,
            "featured": True,
            "tags": ["python", "testing"],
            "project": "alpha-project",
            "aliases": ["/pkg/alpha/"],
        },
        "beta-pkg": {
            "name": "beta-pkg",
            "registry": "cran",
            "description": "Beta package for CRAN",
            "latest_version": "0.5.0",
            "install_command": "install.packages('beta-pkg')",
            "tags": ["r", "statistics"],
        },
    }
    db_path.write_text(json.dumps(data, indent=2))
    db = PackageDatabase(db_path)
    db.load()
    return db


# ---------------------------------------------------------------------------
# generate_package_content tests
# ---------------------------------------------------------------------------


def test_generates_index_md(mock_site_root, pkg_db):
    """Generated file should exist at content/packages/{slug}/index.md."""
    entry = pkg_db.get("alpha-pkg")
    generate_package_content("alpha-pkg", entry)

    content_file = mock_site_root / "content" / "packages" / "alpha-pkg" / "index.md"
    assert content_file.exists()


def test_frontmatter_fields(mock_site_root, pkg_db):
    """Key fields should appear in the generated frontmatter."""
    entry = pkg_db.get("alpha-pkg")
    generate_package_content("alpha-pkg", entry)

    text = (mock_site_root / "content" / "packages" / "alpha-pkg" / "index.md").read_text()
    assert 'title: "alpha-pkg"' in text
    assert 'slug: "alpha-pkg"' in text
    assert 'registry: "pypi"' in text
    assert 'latest_version: "1.2.3"' in text
    assert 'install_command: "pip install alpha-pkg"' in text
    assert 'license: "MIT"' in text
    assert "downloads: 5000" in text
    assert "featured: true" in text


def test_dry_run_no_file(mock_site_root, pkg_db):
    """Dry run should not create any files."""
    entry = pkg_db.get("alpha-pkg")
    result = generate_package_content("alpha-pkg", entry, dry_run=True)

    assert result is True
    content_file = mock_site_root / "content" / "packages" / "alpha-pkg" / "index.md"
    assert not content_file.exists()


def test_tags_in_frontmatter(mock_site_root, pkg_db):
    """Tags should be listed in YAML format."""
    entry = pkg_db.get("alpha-pkg")
    generate_package_content("alpha-pkg", entry)

    text = (mock_site_root / "content" / "packages" / "alpha-pkg" / "index.md").read_text()
    assert "tags:" in text
    assert '"python"' in text
    assert '"testing"' in text


def test_linked_project(mock_site_root, pkg_db):
    """linked_project should appear when project is set."""
    entry = pkg_db.get("alpha-pkg")
    generate_package_content("alpha-pkg", entry)

    text = (mock_site_root / "content" / "packages" / "alpha-pkg" / "index.md").read_text()
    assert 'linked_project: "/projects/alpha-project/"' in text


def test_no_linked_project(mock_site_root, pkg_db):
    """linked_project should not appear when project is None."""
    entry = pkg_db.get("beta-pkg")
    generate_package_content("beta-pkg", entry)

    text = (mock_site_root / "content" / "packages" / "beta-pkg" / "index.md").read_text()
    assert "linked_project" not in text


def test_generate_all(mock_site_root, pkg_db):
    """generate_all_packages should create files for all entries."""
    success, failed = generate_all_packages(pkg_db)

    assert success == 2
    assert failed == 0
    assert (mock_site_root / "content" / "packages" / "alpha-pkg" / "index.md").exists()
    assert (mock_site_root / "content" / "packages" / "beta-pkg" / "index.md").exists()


def test_optional_fields_omitted(mock_site_root, pkg_db):
    """Fields with None values should not appear in output."""
    entry = pkg_db.get("beta-pkg")
    generate_package_content("beta-pkg", entry)

    text = (mock_site_root / "content" / "packages" / "beta-pkg" / "index.md").read_text()
    # beta-pkg has no project, license, downloads, aliases, or registry_url
    assert "linked_project" not in text
    assert "aliases" not in text
    assert "registry_url" not in text
    # But it does have fields that are set
    assert 'registry: "cran"' in text
    assert 'description: "Beta package for CRAN"' in text
