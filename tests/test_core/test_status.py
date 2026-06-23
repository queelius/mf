import io

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


def test_print_status_aggregation(mock_site_root):
    """print_status TOTAL drift = stale + missing + orphan + error across all modules.

    Build a hand-crafted results list that includes one errored module and
    a mix of statuses in others. Verify the TOTAL row and the error label.
    """
    from rich.console import Console

    from mf.core.drift import RenderFinding
    from mf.core.status import print_status

    results = [
        (
            "papers",
            [
                RenderFinding(slug="p1", status="current"),
                RenderFinding(slug="p2", status="stale", detail="generate would update"),
                RenderFinding(slug="p3", status="missing", detail="generate would create"),
            ],
        ),
        (
            "packages",
            [
                RenderFinding(slug="pkg1", status="orphan", detail="on disk, unknown to database"),
                RenderFinding(slug="pkg2", status="current"),
            ],
        ),
        (
            "projects",
            [
                RenderFinding(slug="(module)", status="error", detail="some failure"),
            ],
        ),
        (
            "publications",
            [
                RenderFinding(slug="pub1", status="current"),
            ],
        ),
    ]

    # TOTAL drift = stale(1) + missing(1) + orphan(1) + error(1) = 4
    # The TOTAL row uses bold style so markup can obscure numbers; use a
    # second pass with markup=False to get a plain string for regex scanning.
    buf_plain = io.StringIO()
    console_plain = Console(file=buf_plain, width=200, highlight=False, markup=False)
    print_status(results, console=console_plain)
    plain = buf_plain.getvalue()

    # Find the TOTAL row: it contains "TOTAL" and must show drift count 4.
    total_lines = [ln for ln in plain.splitlines() if "TOTAL" in ln]
    assert total_lines, "Expected a TOTAL row in print_status output"
    # The last numeric token in the TOTAL line is the grand drift count.
    import re
    numbers_in_total = re.findall(r"\b\d+\b", total_lines[0])
    assert numbers_in_total, "No numbers found in TOTAL row"
    grand_drift = int(numbers_in_total[-1])
    assert grand_drift == 4, (
        f"Expected grand drift 4 (1 stale + 1 missing + 1 orphan + 1 error), got {grand_drift}"
    )

    # The errored module row label must contain "(error)".
    error_lines = [ln for ln in plain.splitlines() if "projects" in ln]
    assert error_lines, "Expected a row for 'projects' in output"
    assert "(error)" in error_lines[0], (
        f"Expected '(error)' in projects row, got: {error_lines[0]!r}"
    )
