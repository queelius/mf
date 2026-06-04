from mf.core.drift import check_render_drift


def _make_renderer(mock_site_root):
    from mf.core.config import get_paths
    from mf.publications.database import PubEntry, PubsDatabase
    from mf.publications.generate import PublicationsRenderer

    db = PubsDatabase()
    db.load()
    db.set(PubEntry(slug="p1", title="Paper One", status="published", type="preprint", date="2024-01-02"))
    db.save()
    return PublicationsRenderer(db, get_paths())


def test_missing_then_current_after_generate(mock_site_root):
    from mf.publications.generate import generate_publications

    renderer = _make_renderer(mock_site_root)
    findings = {f.slug: f.status for f in check_render_drift(renderer)}
    assert findings["p1"] == "missing"

    generate_publications(slug="p1", dry_run=False, force=False)
    findings = {f.slug: f.status for f in check_render_drift(renderer)}
    assert findings["p1"] == "current"


def test_stale_after_title_change(mock_site_root):
    from mf.publications.generate import generate_publications

    renderer = _make_renderer(mock_site_root)
    generate_publications(slug="p1", dry_run=False, force=False)

    entry = renderer._db.get("p1")
    entry.title = "Paper One (Revised)"
    renderer._db.set(entry)
    renderer._db.save()

    findings = {f.slug: f.status for f in check_render_drift(renderer)}
    assert findings["p1"] == "stale"


def test_diff_cli_reports_missing(mock_site_root):
    from click.testing import CliRunner

    from mf.cli import main

    _make_renderer(mock_site_root)  # seeds p1, no page generated yet
    result = CliRunner().invoke(main, ["pubs", "diff"])
    assert result.exit_code == 0
    assert "missing" in result.output


def test_generate_dry_run_says_would_create(mock_site_root):
    from click.testing import CliRunner

    from mf.cli import main

    _make_renderer(mock_site_root)
    result = CliRunner().invoke(main, ["--dry-run", "pubs", "generate"])
    assert result.exit_code == 0
    assert "would create" in result.output
