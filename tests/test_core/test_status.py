from mf.core.status import collect_status


def _seed(mock_site_root):
    """Seed one entry in each module so status has something to report."""
    from mf.packages.database import PackageDatabase
    from mf.publications.database import PubEntry, PubsDatabase

    pdb = PubsDatabase()
    pdb.load()
    pdb.set(PubEntry(slug="p1", title="P1", status="published", type="preprint", date="2024-01-02"))
    pdb.save()

    pkg = PackageDatabase()
    pkg.load()
    pkg.set("requests", {"name": "requests", "registry": "pypi", "date_added": "2024-01-02"})
    pkg.save()


def test_collect_status_returns_all_modules(mock_site_root):
    _seed(mock_site_root)
    results = collect_status()
    sections = {section for section, _ in results}
    assert sections == {"publications", "packages", "papers", "projects"}


def test_collect_status_reports_missing_for_unseeded_pages(mock_site_root):
    _seed(mock_site_root)
    results = dict(collect_status())
    pub_statuses = {f.slug: f.status for f in results["publications"]}
    assert pub_statuses["p1"] == "missing"  # seeded in db, not generated


def test_status_cli_runs_and_reports(mock_site_root):
    from click.testing import CliRunner

    from mf.cli import main

    _seed(mock_site_root)
    result = CliRunner().invoke(main, ["status"])
    assert result.exit_code == 0
    assert "Render drift across modules" in result.output


def test_status_cli_verbose_lists_drift(mock_site_root):
    from click.testing import CliRunner

    from mf.cli import main

    _seed(mock_site_root)
    result = CliRunner().invoke(main, ["status", "--verbose"])
    assert result.exit_code == 0
    assert "p1" in result.output  # the missing publication page is listed


def test_collect_status_survives_module_error(mock_site_root, monkeypatch):
    import mf.packages.generator as pkg_gen

    def boom():
        raise RuntimeError("kaboom")

    monkeypatch.setattr(pkg_gen, "make_renderer", boom)

    from mf.core.status import collect_status

    results = dict(collect_status())
    # All four sections still present; packages reports a single error finding.
    assert set(results) == {"publications", "packages", "papers", "projects"}
    pkg_findings = results["packages"]
    assert len(pkg_findings) == 1
    assert pkg_findings[0].status == "error"
    assert "kaboom" in pkg_findings[0].detail
