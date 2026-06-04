"""Tests for render-drift engine integration with the packages module."""

from mf.core.drift import check_render_drift


def _seed(mock_site_root):
    from mf.packages.database import PackageDatabase

    db = PackageDatabase()
    db.load()
    db.set("requests", {"name": "requests", "registry": "pypi", "date_added": "2024-01-02"})
    db.save()
    return db


def test_render_package_page_is_deterministic(mock_site_root):
    from mf.packages.database import PackageDatabase
    from mf.packages.generator import render_package_page

    _seed(mock_site_root)
    db = PackageDatabase()
    db.load()
    entry = db.get("requests")
    first = render_package_page("requests", entry)
    second = render_package_page("requests", entry)
    assert first == second
    assert "date: 2024-01-02" in first


def test_render_package_page_no_wallclock_date_when_missing(mock_site_root):
    from datetime import date

    from mf.packages.database import PackageDatabase
    from mf.packages.generator import render_package_page

    db = PackageDatabase()
    db.load()
    db.set("nodate", {"name": "nodate", "registry": "pypi"})
    db.save()
    entry = db.get("nodate")
    rendered = render_package_page("nodate", entry)
    # No wall-clock date leaks in: today's date must not appear.
    assert date.today().isoformat() not in rendered


def test_packages_drift_missing_then_current(mock_site_root):
    from mf.core.config import get_paths
    from mf.packages.database import PackageDatabase
    from mf.packages.generator import PackagesRenderer, generate_all_packages

    _seed(mock_site_root)
    db = PackageDatabase()
    db.load()
    renderer = PackagesRenderer(db, get_paths())
    assert {f.slug: f.status for f in check_render_drift(renderer)}["requests"] == "missing"

    generate_all_packages(db, dry_run=False)
    assert {f.slug: f.status for f in check_render_drift(renderer)}["requests"] == "current"


def test_packages_diff_cli_reports_missing(mock_site_root):
    from click.testing import CliRunner

    from mf.cli import main

    _seed(mock_site_root)
    result = CliRunner().invoke(main, ["packages", "diff"])
    assert result.exit_code == 0
    assert "missing" in result.output


def test_packages_generate_dry_run_says_would_create(mock_site_root):
    from click.testing import CliRunner

    from mf.cli import main

    _seed(mock_site_root)
    result = CliRunner().invoke(main, ["--dry-run", "packages", "generate"])
    assert result.exit_code == 0
    assert "would create" in result.output
